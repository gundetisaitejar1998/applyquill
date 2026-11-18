"""Durable database-backed automation and daily discovery scheduler."""
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .database import connect, UPLOADS
from .services.automation import prepare_application
from .services.eligibility import evaluate_eligibility, profile_is_verified
from .services.intelligence import match_job

logger=logging.getLogger("jobpilot.worker")
LEASE_SECONDS=180
WORKER_HEARTBEAT=0.0


def _json(value,default=None):
    try:return json.loads(value or "{}")
    except (TypeError,ValueError):return default if default is not None else {}


def enqueue_jobs(run_id,candidate_id,task_type,minimum_score=75,daily_limit=10,company_limit=2,allowed_sources=None):
    """Enqueue only verified hard-eligible, sufficiently matched, nonduplicate jobs."""
    queued=0
    with connect() as db:
        rows=db.execute("SELECT j.* FROM jobs j WHERE j.candidate_id=? AND j.eligibility_status='eligible' AND COALESCE(j.match_score,0)>=? ORDER BY COALESCE(j.posted_at,'') DESC,j.id DESC",(candidate_id,minimum_score)).fetchall()
        today=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).isoformat().replace("+00:00","Z")
        submitted_today=db.execute("SELECT COUNT(*) n FROM applications WHERE candidate_id=? AND submission_status='confirmed' AND application_date>=?",(candidate_id,today)).fetchone()["n"]
        reserved_today=db.execute("SELECT COUNT(*) n FROM automation_queue q JOIN automation_runs r ON r.id=q.run_id WHERE q.candidate_id=? AND q.task_type='submit' AND q.status IN ('queued','processing') AND r.stop_requested=0",(candidate_id,)).fetchone()["n"]
        reserved_companies=db.execute("SELECT j.company,COUNT(*) n FROM automation_queue q JOIN jobs j ON j.id=q.job_id JOIN automation_runs r ON r.id=q.run_id WHERE q.candidate_id=? AND q.task_type='submit' AND q.status IN ('queued','processing') AND r.stop_requested=0 GROUP BY j.company",(candidate_id,)).fetchall()
        companies={}
        for row in db.execute("SELECT j.company,COUNT(*) n FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.candidate_id=? AND a.submission_status='confirmed' AND a.application_date>=? GROUP BY j.company",(candidate_id,today)).fetchall():
            companies[re.sub(r"\W+","",str(row["company"] or "").lower())]=int(row["n"])
        for row in reserved_companies:
            key=re.sub(r"\W+","",str(row["company"] or "").lower());companies[key]=companies.get(key,0)+int(row["n"])
        allowed_sources={str(x).strip().lower() for x in allowed_sources or [] if str(x).strip()}
        for row in rows:
            if allowed_sources and str(row["source"] or "").lower() not in allowed_sources:continue
            if task_type=="submit" and submitted_today+reserved_today+queued>=daily_limit:break
            company_key=re.sub(r"\W+","",str(row["company"] or "").lower())
            if task_type=="submit" and companies.get(company_key,0)>=company_limit:continue
            normalized=str(row["url"] or "").split("?")[0].rstrip("/").lower()
            company_job=(company_key,re.sub(r"\W+","",str(row["title"] or "").lower()))
            prior=db.execute("SELECT id,submission_status,status FROM applications WHERE candidate_id=? AND (job_id=? OR normalized_job_url=? OR (company_key=? AND job_key=?))",(candidate_id,row["id"],normalized,*company_job)).fetchone()
            if prior and prior["submission_status"] in {"confirmed","submission_unconfirmed","in_progress"}:continue
            if prior and prior["status"] in {"Rejected","Withdrawn"}:continue
            active=db.execute("SELECT COUNT(*) n FROM automation_queue WHERE candidate_id=? AND job_id=? AND status IN ('queued','processing')",(candidate_id,row["id"])).fetchone()["n"]
            if active:continue
            inserted=db.execute("INSERT INTO automation_queue(run_id,candidate_id,job_id,task_type,status) VALUES(?,?,?,?,'queued') ON CONFLICT DO NOTHING",(run_id,candidate_id,row["id"],task_type))
            if inserted.rowcount:
                companies[company_key]=companies.get(company_key,0)+1;queued+=1
    return queued


async def _handle_item(item):
    from .main import candidate_record
    cid=item["candidate_id"];jid=item["job_id"];run_id=item["run_id"];task=item["task_type"]
    with connect() as db:
        run=db.execute("SELECT stop_requested,status FROM automation_runs WHERE id=?",(run_id,)).fetchone()
        candidate=db.execute("SELECT * FROM candidates WHERE id=?",(cid,)).fetchone()
        job=db.execute("SELECT * FROM jobs WHERE id=? AND candidate_id=?",(jid,cid)).fetchone()
        config=db.execute("SELECT submissions_enabled FROM automation_configs WHERE candidate_id=?",(cid,)).fetchone()
    if not run or run["stop_requested"] or run["status"] in {"stopped","failed"}:
        _finish_item(item,"cancelled","Emergency STOP or run cancellation was requested.");return
    if not candidate or not job:
        _finish_item(item,"failed","Candidate or vacancy record is missing.");return
    person=dict(candidate);person["profile"]=_json(person.get("profile_json"));person["preferences"]=_json(person.get("preferences_json"))
    job=dict(job);eligibility=evaluate_eligibility(person["profile"],person["preferences"],job)
    submit=task=="submit"
    if eligibility["status"]!="eligible":
        _finish_item(item,"blocked","Hard eligibility is no longer confirmed; no application form was opened.");return
    if submit and not profile_is_verified(person["profile"]):
        _finish_item(item,"blocked","Candidate verification changed before processing.");return
    if submit and (not config or not config["submissions_enabled"] or os.getenv("ALLOW_REAL_SUBMISSIONS","false").lower() not in {"1","true","yes"}):
        _finish_item(item,"blocked","Submission opt-in or server kill switch is disabled.");return
    if submit and (not person.get("resume_path") or not os.path.isfile(person["resume_path"])):
        _finish_item(item,"blocked","Candidate resume file is unavailable; no application was submitted.");return
    async def submission_guard():
        with connect() as db:
            state=db.execute("SELECT stop_requested,status FROM automation_runs WHERE id=?",(run_id,)).fetchone()
        return bool(state and not state["stop_requested"] and state["status"]=="running")
    result=await prepare_application(job["url"],person["profile"],person.get("resume_path") or "",submit=submit,
        candidate_id=cid,run_id=run_id,submission_guard=submission_guard)
    status={"prepared":"Ready to apply","confirmed":"Submitted","verification_required":"Verification required",
            "submission_unconfirmed":"Verification required","failed":"Submission failed","skipped":"Rejected",
            "requires_review":"Requires manual action","stopped":"Requires manual action"}.get(result.get("status"),"Discovered")
    match=match_job(person["profile"],job,person["preferences"])
    with connect() as db:
        existing=db.execute("SELECT id FROM applications WHERE candidate_id=? AND job_id=?",(cid,jid)).fetchone()
        common=(status,match["score"],result.get("status"),result.get("confirmation","")[:1000],
                "" if result.get("status") in {"prepared","confirmed"} else result.get("reason","")[:1000],
                datetime.now(timezone.utc).isoformat().replace("+00:00","Z"))
        if existing:
            db.execute("UPDATE applications SET status=?,match_score=?,submission_status=?,confirmation_details=?,failure_reason=?,application_date=CASE WHEN ?='confirmed' THEN ? ELSE application_date END,last_activity_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (*common[:5],result.get("status"),common[5],common[5],existing["id"]))
        else:
            db.execute("INSERT INTO applications(candidate_id,job_id,status,match_score,normalized_job_url,company_key,job_key,submission_status,confirmation_details,failure_reason,application_date,last_activity_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid,jid,status,match["score"],str(job.get("url") or "").split("?")[0].rstrip("/").lower(),
                 re.sub(r"\W+","",str(job.get("company") or "").lower()),re.sub(r"\W+","",str(job.get("title") or "").lower()),
                 result.get("status"),result.get("confirmation","")[:1000],common[4],common[5] if result.get("status")=="confirmed" else None,common[5]))
        db.execute("INSERT INTO automation_events(run_id,candidate_id,job_id,event_type,detail) VALUES(?,?,?,?,?)",
            (run_id,cid,jid,"application_result",json.dumps({"task":task,"status":result.get("status"),"detail":result.get("reason"),"eligibility":eligibility},ensure_ascii=False)))
        db.execute("UPDATE automation_queue SET status=?,lease_until=NULL,last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",("completed" if result.get("status") in {"prepared","confirmed"} else "failed",result.get("reason","")[:1000],item["id"]))
    _complete_run_if_idle(run_id)


def _finish_item(item,status,reason):
    with connect() as db:
        db.execute("UPDATE automation_queue SET status=?,lease_until=NULL,last_error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(status,reason[:1000],item["id"]))
        db.execute("INSERT INTO automation_events(run_id,candidate_id,job_id,event_type,detail) VALUES(?,?,?,?,?)",(item["run_id"],item["candidate_id"],item.get("job_id"),"queue_item_skipped",json.dumps({"status":status,"reason":reason})))
    _complete_run_if_idle(item["run_id"])


def _complete_run_if_idle(run_id):
    with connect() as db:
        pending=db.execute("SELECT COUNT(*) n FROM automation_queue WHERE run_id=? AND status IN ('queued','processing')",(run_id,)).fetchone()["n"]
        if not pending:
            db.execute("UPDATE automation_runs SET status=CASE WHEN stop_requested=1 THEN 'stopped' ELSE 'completed' END,completed_at=? WHERE id=? AND status IN ('queued','running')",(datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),run_id))


def _claim_item():
    now=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    with connect() as db:
        stale=db.execute("SELECT id,run_id,candidate_id,job_id,task_type FROM automation_queue WHERE status='processing' AND lease_until<?",(now,)).fetchall()
        for item in stale:
            if item["task_type"]=="submit":
                db.execute("UPDATE automation_queue SET status='verification_required',lease_until=NULL,last_error='Submission lease expired; manual verification required.' WHERE id=?",(item["id"],))
                db.execute("UPDATE applications SET status='Verification required',submission_status='submission_unconfirmed',failure_reason='Worker stopped during submission; verify on the employer site before retrying.' WHERE candidate_id=? AND job_id=?",(item["candidate_id"],item["job_id"]))
                db.execute("INSERT INTO automation_events(run_id,candidate_id,job_id,event_type,detail) VALUES(?,?,?,?,?)",(item["run_id"],item["candidate_id"],item["job_id"],"submission_recovery_blocked",json.dumps({"reason":"Submission was not retried after worker interruption."})))
            else:db.execute("UPDATE automation_queue SET status='queued',lease_until=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(item["id"],))
        for run in db.execute("SELECT DISTINCT run_id FROM automation_queue WHERE status='verification_required'").fetchall():
            pending=db.execute("SELECT COUNT(*) n FROM automation_queue WHERE run_id=? AND status IN ('queued','processing')",(run["run_id"],)).fetchone()["n"]
            if not pending:db.execute("UPDATE automation_runs SET status='verification_required',completed_at=? WHERE id=?",(now,run["run_id"]))
        row=db.execute("SELECT q.* FROM automation_queue q JOIN automation_runs r ON r.id=q.run_id WHERE q.status='queued' AND r.stop_requested=0 AND r.status IN ('queued','running') ORDER BY q.id LIMIT 1").fetchone()
        if not row:return None
        updated=db.execute("UPDATE automation_queue SET status='processing',attempts=attempts+1,lease_until=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='queued'",((datetime.now(timezone.utc)+timedelta(seconds=LEASE_SECONDS)).isoformat().replace("+00:00","Z"),row["id"]))
        if not updated.rowcount:return None
        db.execute("UPDATE automation_runs SET status='running',started_at=COALESCE(started_at,?) WHERE id=? AND status='queued'",(now,row["run_id"]))
        return dict(row)


async def _run_due_schedules():
    from .main import roles,discover
    with connect() as db:configs=[dict(r) for r in db.execute("SELECT * FROM automation_configs WHERE schedule_enabled=1 AND enabled=1").fetchall()]
    for config in configs:
        try:zone=ZoneInfo(config.get("timezone") or "Asia/Kolkata")
        except ZoneInfoNotFoundError:zone=ZoneInfo("Asia/Kolkata")
        local=datetime.now(zone);date=local.date().isoformat()
        if local.strftime("%H:%M")<str(config.get("schedule_time") or "09:00") or config.get("last_scheduled_date")==date:continue
        cid=config["candidate_id"]
        try:
            role_result=await roles(cid,user_id=config.get("user_id"));role_list=role_result.get("roles",[])
            if not role_list:continue
            from .main import candidate_record
            person=candidate_record(cid,config.get("user_id"));remote=person.get("preferences",{}).get("work_mode","Any") in {"Any","Remote"}
            await discover(cid,{"roles":role_list,"role_model":role_result.get("model","scheduled"),"allow_remote":remote},config.get("user_id"))
            body=_json(config.get("config_json"));submit=bool(config.get("submissions_enabled")) and os.getenv("ALLOW_REAL_SUBMISSIONS","false").lower() in {"1","true","yes"}
            if submit:
                with connect() as db:person_row=db.execute("SELECT profile_json,resume_path FROM candidates WHERE id=?",(cid,)).fetchone()
                submit=bool(person_row and profile_is_verified(_json(person_row["profile_json"])) and person_row["resume_path"] and os.path.isfile(person_row["resume_path"]))
            with connect() as db:
                cur=db.execute("INSERT INTO automation_runs(candidate_id,user_id,status,config_json) VALUES(?,?, 'queued',?) RETURNING id",(cid,config.get("user_id"),json.dumps({"scheduled":True,"task_type":"submit" if submit else "prepare"})));run_id=cur.fetchone()["id"]
                db.execute("UPDATE automation_configs SET last_scheduled_date=? WHERE id=?",(date,config["id"]))
            count=enqueue_jobs(run_id,cid,"submit" if submit else "prepare",body.get("minimum_score",75),body.get("daily_limit",10),body.get("company_limit",2),body.get("allowed_sources",[]))
            if not count:_complete_run_if_idle(run_id)
        except Exception as exc:logger.exception("Scheduled discovery failed candidate_id=%s error=%s",cid,type(exc).__name__)


async def worker_loop():
    """Run durable DB tasks; expired leases are recovered on every poll."""
    global WORKER_HEARTBEAT
    last_schedule=0.0
    while True:
        try:
            WORKER_HEARTBEAT=datetime.now(timezone.utc).timestamp()
            if datetime.now().timestamp()-last_schedule>=30:
                await _run_due_schedules();last_schedule=datetime.now().timestamp()
            item=_claim_item()
            if item:await _handle_item(item)
            else:await asyncio.sleep(1)
        except asyncio.CancelledError:raise
        except Exception as exc:
            logger.exception("Automation worker iteration failed error=%s",type(exc).__name__)
            await asyncio.sleep(2)
