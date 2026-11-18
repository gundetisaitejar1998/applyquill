import tempfile
import unittest
import os
from unittest.mock import AsyncMock,patch
from datetime import datetime,timezone,timedelta
from pathlib import Path

from backend.app import database
from backend.app.worker import enqueue_jobs,_claim_item,_handle_item


class DurableWorkerTests(unittest.TestCase):
    def setUp(self):
        self.old=database.DB_PATH;self.tmp=tempfile.TemporaryDirectory();database.DB_PATH=Path(self.tmp.name)/"worker.sqlite3";database.init_db()
        with database.connect() as db:
            self.cid=db.execute("INSERT INTO candidates(name) VALUES(?) RETURNING id",("Test candidate",)).fetchone()["id"]
            self.run_id=db.execute("INSERT INTO automation_runs(candidate_id,status) VALUES(?,'queued') RETURNING id",(self.cid,)).fetchone()["id"]
    def tearDown(self):database.DB_PATH=self.old;self.tmp.cleanup()
    def add_job(self,title,company,url,source="Greenhouse"):
        with database.connect() as db:
            return db.execute("INSERT INTO jobs(candidate_id,title,company,url,source,eligibility_status,match_score) VALUES(?,?,?,?,?,'eligible',90) RETURNING id",(self.cid,title,company,url,source)).fetchone()["id"]

    def test_daily_and_company_caps_include_reserved_queue_items(self):
        self.add_job("Designer one","Same Co","https://example.test/1")
        self.add_job("Designer two","Same Co","https://example.test/2")
        self.add_job("Designer three","Other Co","https://example.test/3")
        count=enqueue_jobs(self.run_id,self.cid,"submit",75,10,1)
        self.assertEqual(count,2)
        second=self.run_id+1
        with database.connect() as db:db.execute("INSERT INTO automation_runs(candidate_id,status) VALUES(?,'queued')",(self.cid,))
        count2=enqueue_jobs(second,self.cid,"submit",75,10,1)
        self.assertEqual(count2,0)
        with database.connect() as db:
            rows=db.execute("SELECT j.company FROM automation_queue q JOIN jobs j ON j.id=q.job_id WHERE q.candidate_id=? AND q.task_type='submit'",(self.cid,)).fetchall()
        self.assertEqual(len(rows),2);self.assertEqual([r['company'] for r in rows].count('Same Co'),1)

    def test_allowed_sources_filter_queue(self):
        self.add_job("Designer","A","https://example.test/gh","Greenhouse")
        self.add_job("Designer","B","https://example.test/le","Lever")
        self.assertEqual(enqueue_jobs(self.run_id,self.cid,"prepare",75,10,2,["lever"]),1)

    def test_default_daily_submission_limit_caps_queue_at_ten(self):
        for n in range(12):self.add_job(f"Designer {n}",f"Company {n}",f"https://example.test/{n}")
        self.assertEqual(enqueue_jobs(self.run_id,self.cid,"submit",75,10,2),10)

    def test_expired_submission_lease_is_manual_verification_not_retried(self):
        job=self.add_job("Designer","A","https://example.test/submit")
        with database.connect() as db:
            db.execute("UPDATE automation_runs SET status='running' WHERE id=?",(self.run_id,))
            db.execute("INSERT INTO automation_queue(run_id,candidate_id,job_id,task_type,status,lease_until) VALUES(?,?,?,'submit','processing',?)",(self.run_id,self.cid,job,(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat().replace('+00:00','Z')))
        self.assertIsNone(_claim_item())
        with database.connect() as db:
            status=db.execute("SELECT status FROM automation_queue WHERE run_id=?",(self.run_id,)).fetchone()["status"]
            run=db.execute("SELECT status FROM automation_runs WHERE id=?",(self.run_id,)).fetchone()["status"]
        self.assertEqual(status,"verification_required");self.assertEqual(run,"verification_required")


class WorkerExecutionTests(DurableWorkerTests):
    def test_confirmed_submission_is_audited_only_after_browser_confirmation(self):
        import asyncio
        job=self.add_job("Product Designer","Fixture Co","https://example.test/apply")
        resume=Path(self.tmp.name)/"resume.pdf";resume.write_bytes(b"test resume")
        with database.connect() as db:
            db.execute("UPDATE candidates SET profile_json=?,resume_path=? WHERE id=?",('{"profile_verified":true,"verified_at":"2026-01-01T00:00:00Z","skills":[]}',str(resume),self.cid))
            db.execute("INSERT INTO automation_configs(candidate_id,submissions_enabled) VALUES(?,1)",(self.cid,))
            db.execute("UPDATE automation_runs SET status='running' WHERE id=?",(self.run_id,))
            db.execute("INSERT INTO automation_queue(run_id,candidate_id,job_id,task_type,status) VALUES(?,?,?,'submit','processing')",(self.run_id,self.cid,job))
        item={"id":1,"run_id":self.run_id,"candidate_id":self.cid,"job_id":job,"task_type":"submit"}
        result={"status":"confirmed","reason":"The application confirmation was displayed.","confirmation":"Thank you for applying."}
        async def call():
            with patch.dict(os.environ,{"ALLOW_REAL_SUBMISSIONS":"true"}),patch("backend.app.worker.evaluate_eligibility",return_value={"status":"eligible","checks":{},"reasons":[]}),patch("backend.app.worker.prepare_application",new=AsyncMock(return_value=result)):
                await _handle_item(item)
        asyncio.run(call())
        with database.connect() as db:
            app=db.execute("SELECT status,submission_status,confirmation_details FROM applications WHERE candidate_id=? AND job_id=?",(self.cid,job)).fetchone()
            queue=db.execute("SELECT status FROM automation_queue WHERE id=?",(item["id"],)).fetchone()
        self.assertEqual(app["status"],"Submitted");self.assertEqual(app["submission_status"],"confirmed")
        self.assertEqual(app["confirmation_details"],"Thank you for applying.");self.assertEqual(queue["status"],"completed")


if __name__=="__main__":unittest.main()
