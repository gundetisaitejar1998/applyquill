from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timedelta, timezone
import json, re, uuid, logging, os, asyncio, time, hashlib
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .database import connect, init_db, rowdict, ROOT, UPLOADS, GENERATED, USE_POSTGRES
from .services.resume import extract_text, parse_resume, MAX_BYTES
from .services.intelligence import generate_role_map, fallback_observed_roles, match_job
from .services.sources import (search_greenhouse,search_lever,search_arbeitnow,search_remotive,search_jobicy,search_adzuna,search_remoteok,verify_board,deduplicate_listings,GREENHOUSE_DEFAULT_BOARDS)
from .services.security import hash_password, verify_password, opaque_token, token_hash
from .services.eligibility import evaluate_eligibility, profile_is_verified
import httpx

OLLAMA_BASE_URL=os.getenv("JOBPILOT_OLLAMA_URL","http://127.0.0.1:11434").rstrip("/")
PREFERRED_MODEL=os.getenv("JOBPILOT_OLLAMA_MODEL","").strip()

def load_project_env():
    env_path=ROOT/".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            key,value=line.split("=",1);os.environ.setdefault(key.strip(),value.strip().strip("\"'"))

load_project_env()
PREFERRED_MODEL=os.getenv("JOBPILOT_OLLAMA_MODEL",PREFERRED_MODEL).strip()
OLLAMA_BASE_URL=os.getenv("JOBPILOT_OLLAMA_URL",OLLAMA_BASE_URL).rstrip("/")
APP_ENV=os.getenv("APP_ENV","development").strip().lower()
AUTH_ENABLED=os.getenv("AUTH_ENABLED","true" if APP_ENV=="production" else "false").lower() in {"1","true","yes","on"}
if APP_ENV=="production" and AUTH_ENABLED and len(os.getenv("JOBPILOT_SECRET_KEY",""))<32:
    raise RuntimeError("JOBPILOT_SECRET_KEY must be set to at least 32 characters when production authentication is enabled.")
SESSION_COOKIE="jobpilot_session"
CSRF_COOKIE="jobpilot_csrf"
SESSION_TTL_SECONDS=7*24*60*60
AUTH_RATE_LIMIT={}
logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"),format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger=logging.getLogger("jobpilot")

@asynccontextmanager
async def lifespan(app):
    init_db()
    from .worker import worker_loop
    worker=asyncio.create_task(worker_loop(),name="jobpilot-db-worker")
    try:yield
    finally:
        worker.cancel()
        try:await worker
        except asyncio.CancelledError:pass

app = FastAPI(title="JobPilot AI", version="0.1.0", lifespan=lifespan)
allowed_origins=[x.strip() for x in os.getenv("CORS_ORIGINS","").split(",") if x.strip()]
if not allowed_origins and APP_ENV!="production":
    allowed_origins=[f"http://{host}:{port}" for host in ("localhost","127.0.0.1") for port in range(5173,5200)]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"], allow_headers=["Content-Type","X-CSRF-Token"])

PUBLIC_API_PATHS={"/api/health","/api/health/ready","/api/health/worker","/api/auth/login","/api/auth/register","/api/auth/me"}

@app.middleware("http")
async def production_security(request:Request,call_next):
    path=request.url.path
    if AUTH_ENABLED and request.method!="OPTIONS" and path.startswith("/api/") and path not in PUBLIC_API_PATHS:
        raw=request.cookies.get(SESSION_COOKIE,"")
        with connect() as db:
            session=db.execute("SELECT user_id,csrf_hash FROM auth_sessions WHERE session_hash=? AND expires_at>?",(token_hash(raw) if raw else "",int(time.time()))).fetchone()
        if not session:
            response=JSONResponse({"detail":"Authentication required."},status_code=401)
            response.delete_cookie(SESSION_COOKIE,path="/");response.delete_cookie(CSRF_COOKIE,path="/")
            return response
        request.state.user_id=session["user_id"]
        if request.method in {"POST","PUT","PATCH","DELETE"}:
            csrf_cookie=request.cookies.get(CSRF_COOKIE,"");csrf_header=request.headers.get("X-CSRF-Token","")
            if not csrf_cookie or not csrf_header or not secrets_compare(csrf_cookie,csrf_header) or not secrets_compare(token_hash(csrf_header),session["csrf_hash"]):
                return JSONResponse({"detail":"CSRF validation failed."},status_code=403)
    response=await call_next(request)
    response.headers.setdefault("X-Content-Type-Options","nosniff")
    response.headers.setdefault("Referrer-Policy","strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options","DENY")
    response.headers.setdefault("X-Request-ID",request.headers.get("X-Request-ID") or uuid.uuid4().hex)
    if APP_ENV=="production":
        response.headers.setdefault("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        response.headers.setdefault("Strict-Transport-Security","max-age=31536000; includeSubDomains")
    return response


def secrets_compare(left:str,right:str)->bool:
    import hmac
    return hmac.compare_digest(left,right)


def request_user_id(request:Request)->int|None:
    return getattr(request.state,"user_id",None)


def check_auth_rate(request:Request):
    now=time.time();key=request.client.host if request.client else "unknown";recent=[x for x in AUTH_RATE_LIMIT.get(key,[]) if now-x<60]
    if len(recent)>=20:raise HTTPException(429,"Too many authentication attempts. Try again in a minute.")
    AUTH_RATE_LIMIT[key]=[*recent,now]

class CandidateIn(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    location: str = ""
    summary: str = ""
    profile: dict = Field(default_factory=dict)
    preferences: dict = Field(default_factory=dict)

class ProfileUpdate(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    location: str = ""
    summary: str = ""
    profile: dict = Field(default_factory=dict)
    preferences: dict = Field(default_factory=dict)

class AuthIn(BaseModel):
    email:str=Field(min_length=3,max_length=320)
    password:str=Field(min_length=1,max_length=128)
    name:str=Field(default="",max_length=200)

def set_session(response:Response,user_id:int):
    session=opaque_token();csrf=opaque_token(24);expires=int(time.time())+SESSION_TTL_SECONDS
    with connect() as db:
        db.execute("DELETE FROM auth_sessions WHERE expires_at<?",(int(time.time()),))
        db.execute("INSERT INTO auth_sessions(session_hash,user_id,csrf_hash,expires_at) VALUES(?,?,?,?)",(token_hash(session),user_id,token_hash(csrf),expires))
    secure=APP_ENV=="production"
    response.set_cookie(SESSION_COOKIE,session,max_age=SESSION_TTL_SECONDS,httponly=True,secure=secure,samesite="strict",path="/")
    response.set_cookie(CSRF_COOKIE,csrf,max_age=SESSION_TTL_SECONDS,httponly=False,secure=secure,samesite="strict",path="/")

@app.post("/api/auth/register")
def register(body:AuthIn,request:Request,response:Response):
    check_auth_rate(request)
    email=body.email.strip().lower();name=body.name.strip()
    if not re.fullmatch(r"[^@\s]{1,128}@[^@\s]{1,255}\.[^@\s]{2,63}",email):raise HTTPException(422,"Enter a valid email address.")
    if len(body.password)<12:raise HTTPException(422,"Password must be at least 12 characters.")
    if not name:raise HTTPException(422,"Enter your name.")
    try:
        with connect() as db:
            row=db.execute("INSERT INTO users(email,name,password_hash) VALUES(?,?,?) ON CONFLICT(email) DO NOTHING RETURNING id",(email,name,hash_password(body.password))).fetchone()
    except Exception:
        logger.exception("Account registration failed")
        raise HTTPException(500,"Account could not be created. Try again later.")
    if not row:raise HTTPException(409,"An account with this email already exists.")
    set_session(response,row["id"])
    return {"user":{"id":row["id"],"email":email,"name":name}}

@app.post("/api/auth/login")
def login(body:AuthIn,request:Request,response:Response):
    check_auth_rate(request);email=body.email.strip().lower()
    with connect() as db:
        row=db.execute("SELECT id,email,name,password_hash FROM users WHERE email=?",(email,)).fetchone()
    if not row or not verify_password(body.password,row["password_hash"]):raise HTTPException(401,"Email or password is incorrect.")
    set_session(response,row["id"])
    return {"user":{"id":row["id"],"email":row["email"],"name":row["name"]}}

@app.get("/api/auth/me")
def auth_me(request:Request):
    if not AUTH_ENABLED:return {"required":False,"user":None}
    raw=request.cookies.get(SESSION_COOKIE,"")
    with connect() as db:
        session=db.execute("SELECT user_id FROM auth_sessions WHERE session_hash=? AND expires_at>?",(token_hash(raw) if raw else "",int(time.time()))).fetchone()
        user_id=session["user_id"] if session else None
        if user_id is None:return {"required":True,"user":None}
        row=db.execute("SELECT id,email,name FROM users WHERE id=?",(user_id,)).fetchone()
    return {"required":True,"user":dict(row) if row else None}

@app.post("/api/auth/logout")
def logout(request:Request,response:Response):
    raw=request.cookies.get(SESSION_COOKIE,"")
    if raw:
        with connect() as db:db.execute("DELETE FROM auth_sessions WHERE session_hash=?",(token_hash(raw),))
    response.delete_cookie(SESSION_COOKIE,path="/",secure=APP_ENV=="production",httponly=True,samesite="strict")
    response.delete_cookie(CSRF_COOKIE,path="/",secure=APP_ENV=="production",samesite="strict")
    return {"ok":True}

@app.get("/api/health")
def health():
    return {"status":"ok","environment":APP_ENV}

@app.get("/api/health/ready")
def health_ready():
    try:
        with connect() as db:db.execute("SELECT 1").fetchone()
        return {"status":"ready","database":"postgresql" if USE_POSTGRES else "sqlite"}
    except Exception:
        logger.exception("Readiness check failed")
        raise HTTPException(503,"Database is not ready.")

@app.get("/api/health/worker")
def health_worker():
    from .worker import WORKER_HEARTBEAT
    age=time.time()-WORKER_HEARTBEAT if WORKER_HEARTBEAT else None
    return {"status":"ready" if age is not None and age<60 else "starting_or_stale","last_heartbeat_age_seconds":round(age,1) if age is not None else None}

@app.exception_handler(Exception)
async def unhandled_exception(request:Request,exc:Exception):
    request_id=uuid.uuid4().hex
    logger.error("Unhandled API error request_id=%s method=%s path=%s error_type=%s",request_id,request.method,request.url.path,type(exc).__name__)
    return JSONResponse({"detail":"An unexpected server error occurred.","request_id":request_id},status_code=500,headers={"X-Request-ID":request_id})

@app.get("/api/candidates")
def candidates(user_id:int|None=Depends(request_user_id)):
    with connect() as db:
        rows=db.execute("SELECT * FROM candidates WHERE user_id=? ORDER BY id DESC",(user_id,)).fetchall() if user_id is not None else db.execute("SELECT * FROM candidates ORDER BY id DESC").fetchall()
        return [dict(r) | {"profile": json.loads(r["profile_json"]), "preferences": json.loads(r["preferences_json"])} for r in rows]

@app.post("/api/candidates")
def create_candidate(body: CandidateIn,user_id:int|None=Depends(request_user_id)):
    preferences=dict(body.preferences)
    preferences.setdefault("preferred_roles",["AI Product Designer","Product Designer","Founding Designer","SaaS Designer","UI/UX Designer"])
    preferences.setdefault("employment_types",["Full-time","Contract"])
    preferences.setdefault("experience_levels",["Junior","Associate","Mid-level"])
    preferences.setdefault("remote_countries",["India"])
    preferences.setdefault("salary_currencies",["USD","EUR"])
    with connect() as db:
        row=db.execute("INSERT INTO candidates(user_id,name,email,phone,location,summary,profile_json,preferences_json) VALUES(?,?,?,?,?,?,?,?) RETURNING id",
            (user_id,body.name,body.email,body.phone,body.location,body.summary,json.dumps(body.profile),json.dumps(preferences))).fetchone()
        return {"id":row["id"],"name":body.name}

@app.get("/api/candidates/{cid}")
def get_candidate(cid: int,user_id:int|None=Depends(request_user_id)):
    return candidate_record(cid,user_id)

def candidate_record(cid:int,user_id:int|None=None):
    with connect() as db:
        row=db.execute("SELECT * FROM candidates WHERE id=? AND user_id=?",(cid,user_id)).fetchone() if user_id is not None else db.execute("SELECT * FROM candidates WHERE id=?",(cid,)).fetchone()
        if not row: raise HTTPException(404, "Candidate not found")
        return dict(row) | {"profile": json.loads(row["profile_json"]), "preferences": json.loads(row["preferences_json"])}

@app.put("/api/candidates/{cid}")
def update_candidate(cid: int, body: ProfileUpdate,user_id:int|None=Depends(request_user_id)):
    profile=dict(body.profile)
    # Editing candidate facts invalidates the previous attestation; re-verify explicitly.
    profile.pop("verified_at",None)
    with connect() as db:
        cur=db.execute("UPDATE candidates SET name=?,email=?,phone=?,location=?,summary=?,profile_json=?,preferences_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND (? IS NULL OR user_id=?)",
          (body.name,body.email,body.phone,body.location,body.summary,json.dumps(profile),json.dumps(body.preferences),cid,user_id,user_id))
        if not cur.rowcount: raise HTTPException(404, "Candidate not found")
        return {"ok": True}

@app.post("/api/candidates/{cid}/resume")
async def upload_resume(cid: int, file: UploadFile = File(...),user_id:int|None=Depends(request_user_id)):
    candidate_record(cid,user_id)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx"}: raise HTTPException(400, "Upload a PDF or DOCX resume")
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES: raise HTTPException(413, "Resume exceeds 10 MB limit")
    original_name=Path(file.filename or ("resume"+suffix)).name
    safe_stem=re.sub(r"[^A-Za-z0-9_.-]", "_", Path(original_name).stem)[:80].strip("._-") or "resume"
    safe_name=safe_stem+suffix
    path = UPLOADS / f"candidate-{cid}-{uuid.uuid4().hex[:10]}-{safe_name}"
    path.write_bytes(content)
    try:
        text = extract_text(path)
        if not text.strip(): raise ValueError("No selectable text found. Scanned-image PDFs need OCR, which is not enabled in this MVP.")
        profile = parse_resume(text, safe_name)
    except Exception as e:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(e))
    with connect() as db:
        row=db.execute("SELECT profile_json FROM candidates WHERE id=? AND (? IS NULL OR user_id=?)",(cid,user_id,user_id)).fetchone()
        prior=json.loads(row["profile_json"]); prior.update(profile)
        db.execute("UPDATE candidates SET name=CASE WHEN ?!='' THEN ? ELSE name END,email=?,phone=?,location=?,summary=?,profile_json=?,resume_path=?,resume_name=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
          (profile["name"],profile["name"],profile["email"],profile["phone"],profile["location"],profile["summary"],json.dumps(prior),str(path),safe_name,cid))
        db.execute("UPDATE resume_versions SET is_active=0 WHERE candidate_id=?",(cid,))
        db.execute("INSERT INTO resume_versions(candidate_id,file_path,file_name,profile_json,sha256,is_active) VALUES(?,?,?,?,?,1)",(cid,str(path),safe_name,json.dumps(profile),hashlib.sha256(content).hexdigest()))
        db.execute("DELETE FROM role_maps WHERE candidate_id=?",(cid,))
    return {"profile": profile, "text_chars": len(text), "filename": safe_name}

@app.get("/api/candidates/{cid}/resume-versions")
def resume_versions(cid:int,user_id:int|None=Depends(request_user_id)):
    candidate_record(cid,user_id)
    with connect() as db:return [dict(r) for r in db.execute("SELECT id,file_name,sha256,is_active,created_at FROM resume_versions WHERE candidate_id=? ORDER BY id DESC",(cid,))]

@app.put("/api/candidates/{cid}/resume-versions/{version_id}/activate")
def activate_resume_version(cid:int,version_id:int,user_id:int|None=Depends(request_user_id)):
    candidate_record(cid,user_id)
    with connect() as db:
        version=db.execute("SELECT * FROM resume_versions WHERE id=? AND candidate_id=?",(version_id,cid)).fetchone()
        if not version:raise HTTPException(404,"Resume version not found for candidate")
        path=Path(version["file_path"]).resolve()
        if not path.is_relative_to(UPLOADS.resolve()) or not path.is_file():raise HTTPException(404,"Stored resume file is unavailable")
        db.execute("UPDATE resume_versions SET is_active=0 WHERE candidate_id=?",(cid,))
        db.execute("UPDATE resume_versions SET is_active=1 WHERE id=? AND candidate_id=?",(version_id,cid))
        db.execute("UPDATE candidates SET resume_path=?,resume_name=?,profile_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND (? IS NULL OR user_id=?)",(str(path),version["file_name"],version["profile_json"],cid,user_id,user_id))
        db.execute("DELETE FROM role_maps WHERE candidate_id=?",(cid,))
    return {"ok":True,"active_version_id":version_id,"message":"Resume version activated. Regenerate the role map and review the extracted candidate facts."}

@app.get("/api/candidates/{cid}/resume-versions/{version_id}/file")
def download_resume_version(cid:int,version_id:int,user_id:int|None=Depends(request_user_id)):
    candidate_record(cid,user_id)
    with connect() as db:version=db.execute("SELECT file_path,file_name FROM resume_versions WHERE id=? AND candidate_id=?",(version_id,cid)).fetchone()
    if not version:raise HTTPException(404,"Resume version not found for candidate")
    path=Path(version["file_path"]).resolve()
    if not path.is_relative_to(UPLOADS.resolve()) or not path.is_file():raise HTTPException(404,"Resume file is unavailable")
    return FileResponse(path,filename=version["file_name"])

@app.put("/api/candidates/{cid}/verification")
def verify_profile(cid:int,body:dict,user_id:int|None=Depends(request_user_id)):
    person=candidate_record(cid,user_id);profile=person["profile"]
    if body.get("verified") is not True: raise HTTPException(422,"Verification must be explicitly confirmed by the candidate.")
    profile["profile_verified"]=True;profile["verified_at"]=datetime.utcnow().isoformat()+"Z"
    with connect() as db:db.execute("UPDATE candidates SET profile_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND (? IS NULL OR user_id=?)",(json.dumps(profile),cid,user_id,user_id))
    return {"verified":True,"verified_at":profile["verified_at"]}

@app.get("/api/candidates/{cid}/automation")
def automation_config(cid:int,user_id:int|None=Depends(request_user_id)):
    candidate_record(cid,user_id)
    with connect() as db:
        row=db.execute("SELECT * FROM automation_configs WHERE candidate_id=? AND (? IS NULL OR user_id=?)",(cid,user_id,user_id)).fetchone()
        runs=[dict(r) for r in db.execute("SELECT * FROM automation_runs WHERE candidate_id=? ORDER BY id DESC LIMIT 10",(cid,))]
        events=[dict(r) for r in db.execute("SELECT * FROM automation_events WHERE candidate_id=? ORDER BY id DESC LIMIT 20",(cid,))]
        queues=[dict(r) for r in db.execute("SELECT status,COUNT(*) count FROM automation_queue WHERE candidate_id=? GROUP BY status",(cid,))]
    for event in events:
        try:event["detail"]=json.loads(event.get("detail") or "{}")
        except (TypeError,ValueError):event["detail"]={}
    return {"config":dict(row) if row else {"enabled":0,"submissions_enabled":0,"schedule_enabled":0,"config_json":"{}"},"runs":runs,"events":events,"queue":queues,"submissions_allowed_by_environment":os.getenv("ALLOW_REAL_SUBMISSIONS","false").lower() in {"1","true","yes"}}

@app.put("/api/candidates/{cid}/automation")
def save_automation(cid:int,body:dict,user_id:int|None=Depends(request_user_id)):
    candidate_record(cid,user_id)
    config=body.get("config",{});config.setdefault("daily_limit",10);config.setdefault("company_limit",2);config.setdefault("minimum_score",75)
    try:
        if not 1<=int(config["daily_limit"])<=10:raise ValueError
        if not 1<=int(config["company_limit"])<=2:raise ValueError
        if not 0<=float(config["minimum_score"])<=100:raise ValueError
    except (ValueError,TypeError,KeyError):raise HTTPException(422,"Set daily limit 1–10, company limit 1–2, and minimum score 0–100.")
    config["daily_limit"]=int(config["daily_limit"]);config["company_limit"]=int(config["company_limit"]);config["minimum_score"]=float(config["minimum_score"])
    with connect() as db:db.execute("INSERT INTO automation_configs(candidate_id,user_id,config_json,enabled,submissions_enabled,schedule_enabled,schedule_time,timezone) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET config_json=excluded.config_json,enabled=excluded.enabled,submissions_enabled=excluded.submissions_enabled,schedule_enabled=excluded.schedule_enabled,schedule_time=excluded.schedule_time,timezone=excluded.timezone,updated_at=CURRENT_TIMESTAMP",(cid,user_id,json.dumps(config),int(bool(body.get("enabled"))),int(bool(body.get("submissions_enabled"))),int(bool(body.get("schedule_enabled"))),str(body.get("schedule_time","09:00")),str(body.get("timezone","UTC"))))
    return {"ok":True,"effective_submission_enabled":bool(body.get("submissions_enabled")) and os.getenv("ALLOW_REAL_SUBMISSIONS","false").lower() in {"1","true","yes"}}

@app.post("/api/candidates/{cid}/automation/start")
def automation_start(cid:int,body:dict,user_id:int|None=Depends(request_user_id)):
    person=candidate_record(cid,user_id)
    with connect() as db:
        conf=db.execute("SELECT * FROM automation_configs WHERE candidate_id=?",(cid,)).fetchone()
        config=json.loads(conf["config_json"] or "{}") if conf else {}
    requested_submit=bool(body.get("submit"))
    task_type="prepare"
    if requested_submit:
        if not conf or not conf["submissions_enabled"]:raise HTTPException(409,"Candidate submission opt-in is disabled.")
        if not profile_is_verified(person["profile"]):raise HTTPException(409,"Verify the candidate profile before submission automation.")
        if os.getenv("ALLOW_REAL_SUBMISSIONS","false").lower() not in {"1","true","yes"}:raise HTTPException(409,"Real submissions are disabled by server policy.")
        if not person.get("resume_path") or not Path(person["resume_path"]).is_file():raise HTTPException(409,"An active candidate resume is required before submission automation.")
        task_type="submit"
    with connect() as db:
        cur=db.execute("INSERT INTO automation_runs(candidate_id,user_id,status,config_json) VALUES(?,?, 'queued',?) RETURNING id",(cid,user_id,json.dumps({**body,"task_type":task_type})));run_id=cur.fetchone()["id"]
        db.execute("INSERT INTO automation_events(run_id,candidate_id,event_type,detail) VALUES(?,?,?,?)",(run_id,cid,"run_queued",json.dumps({"mode":"submission" if task_type=="submit" else "dry_run","profile_verified":profile_is_verified(person["profile"])})))
    from .worker import enqueue_jobs,_complete_run_if_idle
    count=enqueue_jobs(run_id,cid,task_type,config.get("minimum_score",75),config.get("daily_limit",10),config.get("company_limit",2),config.get("allowed_sources",[]))
    if not count:_complete_run_if_idle(run_id)
    return {"run_id":run_id,"status":"queued" if count else "completed","queued_jobs":count,"mode":"submission" if task_type=="submit" else "dry_run","message":f"Queued {count} eligible application task(s)." if count else "No jobs currently pass the configured eligibility and score requirements."}

@app.post("/api/candidates/{cid}/automation/stop")
def automation_stop(cid:int,user_id:int|None=Depends(request_user_id)):
    candidate_record(cid,user_id)
    with connect() as db:
        db.execute("UPDATE automation_runs SET stop_requested=1,status='stopped',completed_at=? WHERE candidate_id=? AND status IN ('queued','running')",(datetime.utcnow().isoformat()+"Z",cid))
        db.execute("UPDATE automation_queue SET status='cancelled',lease_until=NULL,last_error='Emergency STOP requested' WHERE candidate_id=? AND status='queued'",(cid,))
        db.execute("INSERT INTO automation_events(candidate_id,event_type,detail) VALUES(?,?,?)",(cid,"emergency_stop",json.dumps({"message":"STOP requested by candidate"})))
    return {"stopped":True}

@app.get("/api/ai/status")
async def ai_status():
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response=await client.get(f"{OLLAMA_BASE_URL}/api/tags")
        if response.status_code!=200:
            return {"available":False,"models":[],"mode":"unavailable","reason":f"Ollama returned HTTP {response.status_code}"}
        models=response.json().get("models", [])
        names=[m.get("name") for m in models if m.get("name")]
        selected=PREFERRED_MODEL or ("qwen2.5:3b" if "qwen2.5:3b" in names else (names[0] if names else ""))
        return {"available":bool(selected and selected in names),"reachable":True,"models":names,"configured_model":selected,
                "mode":"ollama" if selected and selected in names else "unavailable",
                "reason":"" if selected and selected in names else (f"Configured model '{selected}' is not installed" if selected else "Ollama responds, but no model is installed")}
    except httpx.HTTPError as exc:
        logger.exception("Ollama status request failed")
        return {"available":False,"reachable":False,"models":[],"mode":"unavailable","reason":f"Ollama is not reachable: {type(exc).__name__}"}

@app.get("/api/candidates/{cid}/roles")
async def roles(cid: int,refresh:bool=False,user_id:int|None=Depends(request_user_id)):
    person=candidate_record(cid,user_id)
    if not person.get("resume_path"):
        raise HTTPException(400,"Upload a resume before generating roles.")
    if not refresh:
        with connect() as db:
            stored=db.execute("SELECT model,roles_json FROM role_maps WHERE candidate_id=? ORDER BY id DESC LIMIT 1",(cid,)).fetchone()
        if stored:
            return {"roles":json.loads(stored["roles_json"]),"mode":"stored","model":stored["model"],
                    "notice":"Loaded the last generated role map used for job discovery. Regenerate roles to create a new map."}
    status=await ai_status()
    if not status["available"]:
        observed=fallback_observed_roles(person["profile"])
        return {"roles":observed,"mode":"resume titles only","model_status":status,
                "notice":status["reason"]+". Only titles copied from the candidate's employment history are shown; related role discovery is unavailable until a local model is installed."}
    try:
        generated=await generate_role_map(person["profile"],status["configured_model"],OLLAMA_BASE_URL)
        with connect() as db:
            db.execute("INSERT INTO role_maps(candidate_id,model,roles_json) VALUES(?,?,?)",(cid,status["configured_model"],json.dumps(generated,ensure_ascii=False)))
        return {"roles":generated,"mode":"ollama","model":status["configured_model"],"notice":"Model-generated role map. Evidence terms are checked against the uploaded resume; review title relevance before searching."}
    except (RuntimeError,httpx.HTTPError) as exc:
        logger.error("Role generation failed candidate_id=%s error_type=%s",cid,type(exc).__name__)
        raise HTTPException(502,f"Role generation failed: {exc}. See logs/jobpilot.log.")

@app.put("/api/candidates/{cid}/preferences")
def preferences(cid:int, body:dict,user_id:int|None=Depends(request_user_id)):
    with connect() as db:
        cur=db.execute("UPDATE candidates SET preferences_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND (? IS NULL OR user_id=?)",(json.dumps(body),cid,user_id,user_id))
        if not cur.rowcount: raise HTTPException(404,"Candidate not found")
    return {"ok":True}

def configured_boards(user_id:int|None=None):
    gh=[x.strip().lower() for x in os.getenv("JOBPILOT_GREENHOUSE_BOARDS","").split(",") if x.strip()]
    lv=[x.strip().lower() for x in os.getenv("JOBPILOT_LEVER_SITES","").split(",") if x.strip()]
    with connect() as db:
        saved=[dict(r) for r in db.execute("SELECT provider,identifier,region,label FROM source_boards WHERE user_id IS NULL ORDER BY id").fetchall()] if user_id is None else [dict(r) for r in db.execute("SELECT provider,identifier,region,label FROM source_boards WHERE user_id=? ORDER BY id",(user_id,)).fetchall()]
    greenhouse=list(dict.fromkeys([*GREENHOUSE_DEFAULT_BOARDS,*gh,*[x['identifier'] for x in saved if x['provider']=='greenhouse']]))
    lever=[{"identifier":x,"region":"global"} for x in lv]
    lever.extend({"identifier":x['identifier'],"region":x['region']} for x in saved if x['provider']=='lever')
    return greenhouse,lever,saved

@app.get("/api/job-sources")
def job_sources(user_id:int|None=Depends(request_user_id)):
    gh,lever,saved=configured_boards(user_id)
    sources=[{"name":"Greenhouse Job Board API","status":"configured","board_count":len(gh),"scope":"Employer boards only"},{"name":"Lever Postings API","status":"configured" if lever else "configuration_required","board_count":len(lever),"scope":"Employer sites only"},{"name":"Arbeitnow public API","status":"configured","scope":"Public feed; primarily European jobs"},{"name":"Remotive public API","status":"configured","scope":"Remote jobs; cached for six hours"},{"name":"Jobicy public API","status":"configured","scope":"Remote jobs; cached for one hour"},{"name":"Remote OK public feed","status":"configured","scope":"Public remote jobs JSON; feed attribution and direct source links retained"},{"name":"Adzuna API","status":"configured" if os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY") else "configuration_required","missing_credentials":[] if os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY") else ["ADZUNA_APP_ID","ADZUNA_APP_KEY"]},{"name":"LinkedIn","status":"partner_required","scope":"No public job seeker search API; no scraping performed"},{"name":"Indeed","status":"partner_required","scope":"No public job seeker search API; no scraping performed"},{"name":"Wellfound","status":"prohibited_automation","scope":"Automated harvesting is not used"}]
    with connect() as db: health={r["source"]:dict(r) for r in db.execute("SELECT * FROM source_health").fetchall()}
    for source in sources:
        source["health"]=health.get(source["name"],{})
    return {"sources":sources,"boards":saved,"health":list(health.values())}

@app.get("/api/job-sources/health")
def source_health(user_id:int|None=Depends(request_user_id)):
    with connect() as db:return [dict(r) for r in db.execute("SELECT * FROM source_health ORDER BY checked_at DESC").fetchall()]

@app.post("/api/job-sources/discover-board")
async def discover_board(body:dict,user_id:int|None=Depends(request_user_id)):
    url=str(body.get("url","")).strip()
    if not url: raise HTTPException(422,"Enter the employer's public Greenhouse or Lever job-board URL.")
    try: board=await verify_board(url)
    except (ValueError,httpx.HTTPError) as exc:
        logger.exception("Public employer board verification failed url=%s",url)
        raise HTTPException(422,f"Board was not added: {exc}")
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO source_boards(user_id,provider,identifier,region,label) VALUES(?,?,?,?,?)",(user_id,board['provider'],board['identifier'],board.get('region','global'),board['label']))
    return {"ok":True,"board":board,"message":"Verified public employer board saved locally for future searches."}

@app.post("/api/candidates/{cid}/discover")
async def discover(cid:int, body:dict,user_id:int|None=Depends(request_user_id)):
    person=candidate_record(cid,user_id)
    role_list=body.get("roles")
    if not isinstance(role_list,list) or not role_list:
        try:
            role_response=await roles(cid,user_id=user_id)
            role_list=role_response["roles"]
        except HTTPException as exc:
            raise HTTPException(exc.status_code,f"Cannot search jobs until role discovery succeeds: {exc.detail}")
    if body.get("query"):
        role_list=[*role_list,{"title":str(body["query"]).strip(),"synonyms":[],"keywords":{"titles":[str(body["query"]).strip()]}}]
    role_list=[r for r in role_list if isinstance(r,dict) and r.get("title")]
    if not role_list: raise HTTPException(422,"The resume did not yield any searchable role titles. Check the parsed experience section.")
    if isinstance(body.get("roles"),list):
        role_model=str(body.get("role_model") or "generated")[:120]
        with connect() as db:
            db.execute("INSERT INTO role_maps(candidate_id,model,roles_json) VALUES(?,?,?)",(cid,role_model,json.dumps(role_list,ensure_ascii=False)))
    prefs=person.get("preferences",{})
    preferred_cities=prefs.get("cities",[])
    if isinstance(preferred_cities,str): preferred_cities=[x.strip() for x in preferred_cities.split(",") if x.strip()]
    default_location=person.get("profile",{}).get("location") or person.get("location","")
    locations=body.get("locations") or ([body["location"]] if body.get("location") else preferred_cities or ([default_location] if default_location else []))
    remote_preference=prefs.get("work_mode","Any") in {"Remote","Any"} or bool(re.search(r"open to remote|remote opportunit",json.dumps(person.get("profile",{})),re.I))
    allow_remote=bool(body.get("allow_remote",remote_preference))
    greenhouse_boards,lever_boards,_=configured_boards(user_id)
    country_codes=prefs.get("country_codes") or (["in"] if any("india" in str(x).lower() for x in locations) else ["in"])
    # Keep live role matches visible by default; hard eligibility labels handle geography.
    # Users can opt into provider-side location filtering when they prefer fewer results.
    source_locations=locations if body.get("strict_location_filter") is True else []
    source_calls={"greenhouse":search_greenhouse(role_list,source_locations,allow_remote,greenhouse_boards),"lever":search_lever(role_list,source_locations,allow_remote,lever_boards),"arbeitnow":search_arbeitnow(role_list,source_locations,allow_remote),"remotive":search_remotive(role_list,source_locations,allow_remote),"jobicy":search_jobicy(role_list,source_locations,allow_remote),"remoteok":search_remoteok(role_list,source_locations,allow_remote),"adzuna":search_adzuna(role_list,source_locations,country_codes)}
    source_results={};source_reports=[]
    async def run_source(key,call):
        try:
            jobs_found,report=await call;return key,jobs_found,report
        except Exception as exc:
            logger.error("Source connector crashed candidate_id=%s source=%s error_type=%s",cid,key,type(exc).__name__)
            return key,[],{"source":key,"checked":0,"status":"connector_error","error":f"{type(exc).__name__}: {str(exc)[:220]}"}
    for key,jobs_found,report in await asyncio.gather(*(run_source(k,v) for k,v in source_calls.items())):
        source_results[key]=jobs_found;source_reports.append(report)
        for detail in report.get("boards",report.get("queries",[])):
            health_status=detail.get("status","error")
            try:
                with connect() as db:
                    db.execute("INSERT INTO source_health(source,status,checked_at,duration_ms,http_status,success_count,error_count,last_error) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET status=excluded.status,checked_at=excluded.checked_at,duration_ms=excluded.duration_ms,http_status=excluded.http_status,success_count=source_health.success_count+excluded.success_count,error_count=source_health.error_count+excluded.error_count,last_error=excluded.last_error",
                     (report.get("source",key),health_status,datetime.utcnow().isoformat()+"Z",detail.get("duration_ms",0),detail.get("http_status"),1 if health_status in {"ok","cached"} else 0,0 if health_status in {"ok","cached"} else 1,detail.get("error","")[:500]))
            except Exception: logger.exception("Could not persist provider health source=%s",key)
    collected=[item for rows in source_results.values() for item in rows]
    results=deduplicate_listings(collected)
    source_report={"sources":source_reports,"checked":sum(s.get("checked",0) for s in source_reports),"duplicate_listings_removed":len(collected)-len(results),
                   "locations":locations,"provider_location_filter":bool(source_locations),"remote_allowed":allow_remote,"salary_filter_applied":False,"experience_filter_applied":False}
    source_errors=[]
    for source in source_report["sources"]:
        for detail in source.get("boards",source.get("queries",[])):
            if detail.get("status") not in {"ok","cached","partial"}: source_errors.append({"source":source["source"],**detail})
        if source.get("status") not in {None,"ok","cached","partial"}: source_errors.append({"source":source.get("source"),"status":source.get("status"),"error":source.get("error","")})
    successful_sources=[s for s in source_report["sources"] if s.get("status") in {"ok","cached"} or any(d.get("status") in {"ok","cached"} for d in s.get("boards",s.get("queries",[])))]
    if not results and not successful_sources:
        message="All active public job sources failed or were skipped. See the per-source diagnostics below and logs/jobpilot.log."
    elif not results:
        role_filtered=sum(d.get("role_filtered",0) for s in source_report["sources"] for d in s.get("boards",s.get("queries",[])))
        location_filtered=sum(d.get("location_filtered",0) for s in source_report["sources"] for d in s.get("boards",s.get("queries",[])))
        if location_filtered:
            message=f"Sources responded; {location_filtered} source listing(s) matched generated role titles but did not meet the selected location or remote eligibility. {role_filtered} additional listing(s) were filtered by role relevance. Salary and experience filters were not applied; review the selected location and provider country restrictions."
        elif role_filtered:
            message=f"Sources responded, but {role_filtered} available listing(s) did not match the generated titles, synonyms, or role keywords. Salary and experience filters were not applied."
        else:
            message="Sources responded, but their available feeds contained no eligible listings for this search. Salary and experience filters were not applied; review provider coverage and configuration below."
    else:
        message=f"Found {len(results)} live listing(s) matched to generated role titles. Salary and experience filters were not applied."
    with connect() as db:
        run_cursor=db.execute("INSERT INTO source_runs(candidate_id,query_json,report_json) VALUES(?,?,?) RETURNING id",(cid,json.dumps({"roles":role_list,"locations":locations}),json.dumps(source_report)))
        run_id=run_cursor.fetchone()["id"]
        for job in results:
            if not job.get("url"):
                continue
            job["discovered_at"]=datetime.utcnow().isoformat()+"Z"
            values=(job["title"],job["company"],job["location"],job["description"],job["source"],job["posted_at"],job.get("salary",""),job.get("job_type",""),job.get("matched_role",""),run_id,job.get("work_mode","Not specified"),cid,job["url"])
            db.execute("INSERT OR IGNORE INTO jobs(candidate_id,title,company,location,url,description,source,posted_at,salary,job_type,matched_role,last_seen_run_id,work_mode) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (cid,job["title"],job["company"],job["location"],job["url"],job["description"],job["source"],job["posted_at"],job.get("salary",""),job.get("job_type",""),job.get("matched_role",""),run_id,job.get("work_mode","Not specified")))
            db.execute("UPDATE jobs SET title=?,company=?,location=?,description=?,source=?,posted_at=?,salary=?,job_type=?,matched_role=?,last_seen_run_id=?,work_mode=? WHERE candidate_id=? AND url=?",values)
            row=db.execute("SELECT * FROM jobs WHERE candidate_id=? AND url=?",(cid,job["url"])).fetchone()
            rowdict_value=dict(row)
            evaluation_prefs={**prefs,"locations":prefs.get("locations") or prefs.get("cities") or locations}
            eligibility=evaluate_eligibility(person["profile"],evaluation_prefs,job)
            match=match_job(person["profile"],job,prefs)
            db.execute("UPDATE jobs SET discovered_at=COALESCE(discovered_at,?),canonical_url=?,external_id=?,employment_type=?,salary_min=?,salary_max=?,salary_currency=?,experience_min=?,experience_max=?,match_score=?,eligibility_status=?,eligibility_reasons=?,last_checked_at=? WHERE id=?",
                (job["discovered_at"],job.get("canonical_url") or job["url"],str(job.get("source_id") or ""),job.get("employment_type") or job.get("job_type") or "",job.get("salary_min"),job.get("salary_max"),job.get("salary_currency") or "",job.get("experience_min"),job.get("experience_max"),match["score"],eligibility["status"],json.dumps(eligibility["reasons"]),datetime.utcnow().isoformat()+"Z",rowdict_value["id"]))
        urls=[j["url"] for j in results if j.get("url")]
        saved=[]
        if urls:
            marks=','.join('?' for _ in urls)
            saved=[dict(r) for r in db.execute(f"SELECT * FROM jobs WHERE candidate_id=? AND url IN ({marks}) ORDER BY id DESC",[cid,*urls])]
    evaluation_prefs={**prefs,"locations":prefs.get("locations") or prefs.get("cities") or locations}
    for job in saved:
        job["match"]=match_job(person["profile"],job,prefs)
        job["eligibility"]=evaluate_eligibility(person["profile"],evaluation_prefs,job)
    logger.info("job_discovery candidate_id=%s role_count=%s live_results=%s locations=%s remote_allowed=%s salary_filter_applied=%s experience_filter_applied=%s source_status=%s",cid,len(role_list),len(saved),locations,allow_remote,source_report["salary_filter_applied"],source_report["experience_filter_applied"],[(s.get("source"),s.get("status"),[(x.get("query"),x.get("status"),x.get("http_status"),x.get("available"),x.get("matched"),x.get("location_filtered"),x.get("error")) for x in s.get("boards",s.get("queries",[]))]) for s in source_report["sources"]])
    for error in source_errors: logger.warning("job_source_error candidate_id=%s details=%s",cid,json.dumps(error,ensure_ascii=False))
    return {"found":len(saved),"jobs":saved,"role_map":role_list,"source_report":source_report,"errors":source_errors,"note":message}

@app.get("/api/candidates/{cid}/source-runs")
def source_runs(cid:int,user_id:int|None=Depends(request_user_id)):
    candidate_record(cid,user_id)
    with connect() as db:
        return [{"id":r["id"],"query":json.loads(r["query_json"]),"report":json.loads(r["report_json"]),"created_at":r["created_at"]} for r in db.execute("SELECT * FROM source_runs WHERE candidate_id=? ORDER BY id DESC LIMIT 20",(cid,))]

@app.get("/api/candidates/{cid}/jobs")
def jobs(cid:int,user_id:int|None=Depends(request_user_id),posted:str="all"):
    person=candidate_record(cid,user_id)
    evaluation_prefs=dict(person.get("preferences",{}))
    with connect() as db:
        latest=db.execute("SELECT id FROM source_runs WHERE candidate_id=? ORDER BY id DESC LIMIT 1",(cid,)).fetchone()
        if latest:
            rows=[dict(r) for r in db.execute("SELECT DISTINCT j.* FROM jobs j LEFT JOIN applications a ON a.job_id=j.id AND a.candidate_id=j.candidate_id WHERE j.candidate_id=? AND (j.last_seen_run_id=? OR a.id IS NOT NULL) ORDER BY CASE WHEN COALESCE(j.posted_at,'')='' THEN 1 ELSE 0 END,j.posted_at DESC,j.id DESC",(cid,latest["id"]))]
        else:
            rows=[dict(r) for r in db.execute("SELECT * FROM jobs WHERE candidate_id=? ORDER BY CASE WHEN COALESCE(posted_at,'')='' THEN 1 ELSE 0 END,posted_at DESC,id DESC",(cid,))]
        if latest:
            query_row=db.execute("SELECT query_json FROM source_runs WHERE id=?",(latest["id"],)).fetchone()
            try:evaluation_prefs["locations"]=evaluation_prefs.get("locations") or evaluation_prefs.get("cities") or json.loads(query_row["query_json"]).get("locations",[])
            except (TypeError,ValueError):pass
    now=datetime.now().astimezone()
    def in_bucket(job):
        if posted in ("all",""):return True
        raw=job.get("posted_at") or ""
        if not raw:return posted=="unknown"
        try:
            dt=datetime.fromisoformat(raw.replace("Z","+00:00"));age=(now-dt.astimezone()).total_seconds()/3600
        except (ValueError,TypeError):return posted=="unknown"
        return {"24h":age<=24,"3d":age<=72,"7d":age<=168,"older":age>168}.get(posted,True)
    return [{**job,"match":match_job(person["profile"],job,evaluation_prefs),"eligibility":evaluate_eligibility(person["profile"],evaluation_prefs,job)} for job in rows if in_bucket(job)]

@app.post("/api/candidates/{cid}/applications")
def add_application(cid:int, body:dict,user_id:int|None=Depends(request_user_id)):
    candidate_record(cid,user_id)
    if body.get("status")=="Submitted":raise HTTPException(409,"Submitted status is reserved for a browser-observed confirmation.")
    with connect() as db:
        job=db.execute("SELECT * FROM jobs WHERE id=? AND candidate_id=?",(body.get("job_id"),cid)).fetchone()
        if not job: raise HTTPException(404,"Job not found for candidate")
        try:
            cur=db.execute("INSERT INTO applications(candidate_id,job_id,status,match_score,notes) VALUES(?,?,?,?,?) RETURNING id",(cid,job["id"],body.get("status","Discovered"),body.get("match_score",0),body.get("notes","")))
        except Exception: raise HTTPException(409,"Application already exists for this job")
        return {"id":cur.fetchone()["id"],"status":body.get("status","Discovered")}

@app.post("/api/candidates/{cid}/jobs/{job_id}/prepare-application")
async def prepare_job_application(cid:int,job_id:int,body:dict,user_id:int|None=Depends(request_user_id)):
    person=candidate_record(cid,user_id)
    with connect() as db: job=db.execute("SELECT * FROM jobs WHERE id=? AND candidate_id=?",(job_id,cid)).fetchone()
    if not job:raise HTTPException(404,"Job not found for candidate")
    from .services.automation import prepare_application
    job=dict(job);eligibility=evaluate_eligibility(person["profile"],person.get("preferences",{}),job);requested_submit=bool(body.get("submit"))
    if requested_submit:
        if not profile_is_verified(person["profile"]):raise HTTPException(409,"Candidate profile must be explicitly verified before submission.")
        if eligibility["status"]!="eligible":raise HTTPException(409,"Hard eligibility is not confirmed; the application was not submitted.")
        if not person.get("resume_path") or not Path(person["resume_path"]).is_file():raise HTTPException(409,"An active resume file is required before submission.")
        with connect() as db:
            conf=db.execute("SELECT submissions_enabled,config_json FROM automation_configs WHERE candidate_id=?",(cid,)).fetchone()
            prior=db.execute("SELECT submission_status FROM applications WHERE candidate_id=? AND job_id=?",(cid,job_id)).fetchone()
        if not conf or not conf["submissions_enabled"]:raise HTTPException(409,"Candidate automation submission opt-in is disabled.")
        try:minimum=float(json.loads(conf["config_json"] or "{}").get("minimum_score",75))
        except (TypeError,ValueError):minimum=75
        match=match_job(person["profile"],job,person.get("preferences",{}))
        if match["score"]<minimum:raise HTTPException(409,f"Match score {match['score']} is below configured minimum {minimum:g}.")
        if prior and prior["submission_status"] in {"confirmed","submission_unconfirmed","in_progress"}:raise HTTPException(409,"This application was submitted or needs manual confirmation; automatic retry is blocked.")
        if os.getenv("ALLOW_REAL_SUBMISSIONS","false").lower() not in {"1","true","yes"}:raise HTTPException(409,"Real submissions are disabled by server policy.")
    result=await prepare_application(job["url"],person["profile"],person.get("resume_path") or "",submit=requested_submit,candidate_id=cid)
    status={"prepared":"Ready to apply","confirmed":"Submitted","verification_required":"Verification required","submission_unconfirmed":"Verification required","failed":"Submission failed","skipped":"Rejected"}.get(result["status"],"Discovered")
    with connect() as db:
        existing=db.execute("SELECT id FROM applications WHERE candidate_id=? AND job_id=?",(cid,job_id)).fetchone()
        if existing:
            aid=existing["id"];db.execute("UPDATE applications SET status=?,match_score=?,submission_status=?,confirmation_details=?,failure_reason=?,application_date=CASE WHEN ?='confirmed' THEN ? ELSE application_date END,last_activity_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(status,job.get("match_score") or 0,result["status"],result.get("confirmation","")[:1000],result.get("reason","") if result["status"] in {"prepared","confirmed"} else result.get("reason",""),result["status"],datetime.utcnow().isoformat()+"Z",datetime.utcnow().isoformat()+"Z",aid))
        else:
            cur=db.execute("INSERT INTO applications(candidate_id,job_id,status,match_score,normalized_job_url,company_key,job_key,submission_status,confirmation_details,failure_reason,application_date,last_activity_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id",(cid,job_id,status,job.get("match_score") or 0,job["url"].split("?")[0].rstrip("/").lower(),re.sub(r"\W+","",job.get("company","").lower()),re.sub(r"\W+","",job.get("title","").lower()),result["status"],result.get("confirmation","")[:1000],result.get("reason","") if result["status"] not in {"prepared","confirmed"} else "",datetime.utcnow().isoformat()+"Z" if result["status"]=="confirmed" else None,datetime.utcnow().isoformat()+"Z"));aid=cur.fetchone()["id"]
        db.execute("INSERT INTO automation_events(candidate_id,job_id,event_type,detail) VALUES(?,?,?,?)",(cid,job_id,"application_prepared",json.dumps({"application_id":aid,"status":result["status"],"eligibility":eligibility,"diagnostics":result},ensure_ascii=False)))
    return {"application_id":aid,"eligibility":eligibility,"automation":result,"note":"Submitted status is saved only after a recognized confirmation." if result["status"]=="confirmed" else "No submission was reported without a verified confirmation."}

@app.get("/api/candidates/{cid}/applications")
def applications(cid:int,user_id:int|None=Depends(request_user_id)):
    candidate_record(cid,user_id)
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT a.*,j.title,j.company,j.url,j.location FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.candidate_id=? ORDER BY a.id DESC",(cid,))]

@app.put("/api/candidates/{cid}/applications/{aid}")
def update_application(cid:int,aid:int,body:dict,user_id:int|None=Depends(request_user_id)):
    candidate_record(cid,user_id)
    allowed={"Discovered","Matched","Ready to apply","Application prepared","Submitted","Requires manual action","Assessment","Interview","Rejected","Offer","Withdrawn"}
    status=body.get("status")
    if status not in allowed: raise HTTPException(400,"Unsupported application status")
    if status=="Submitted":raise HTTPException(409,"Submitted status is reserved for a browser-observed confirmation.")
    with connect() as db:
        cur=db.execute("UPDATE applications SET status=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND candidate_id=?",(status,body.get("notes",""),aid,cid))
        if not cur.rowcount: raise HTTPException(404,"Application not found for candidate")
    return {"ok":True}

@app.get("/api/candidates/{cid}/stats")
def stats(cid:int,user_id:int|None=Depends(request_user_id)):
    candidate_record(cid,user_id)
    with connect() as db:
        # Keep dashboard totals in sync with /jobs, which only shows listings from
        # the latest discovery run (plus jobs already in the application tracker).
        latest=db.execute("SELECT id FROM source_runs WHERE candidate_id=? ORDER BY id DESC LIMIT 1",(cid,)).fetchone()
        if latest:
            jobs_count=db.execute("SELECT COUNT(DISTINCT j.id) AS n FROM jobs j LEFT JOIN applications a ON a.job_id=j.id AND a.candidate_id=j.candidate_id WHERE j.candidate_id=? AND (j.last_seen_run_id=? OR a.id IS NOT NULL)",(cid,latest["id"])).fetchone()["n"]
        else:
            jobs_count=db.execute("SELECT COUNT(*) AS n FROM jobs WHERE candidate_id=?",(cid,)).fetchone()["n"]
        apps=db.execute("SELECT status,COUNT(*) n FROM applications WHERE candidate_id=? GROUP BY status",(cid,)).fetchall()
        day_start=datetime.now().astimezone().replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc).isoformat().replace('+00:00','Z')
        today=db.execute("SELECT COUNT(*) n FROM jobs WHERE candidate_id=? AND discovered_at>=?",(cid,day_start)).fetchone()["n"]
        cutoff=datetime.now(timezone.utc)-timedelta(hours=24)
        published_rows=db.execute("SELECT posted_at FROM jobs WHERE candidate_id=? AND COALESCE(posted_at,'')!=''",(cid,)).fetchall()
        published_24h=0
        for item in published_rows:
            try:
                posted=datetime.fromisoformat(str(item["posted_at"]).replace("Z","+00:00"))
                if posted.tzinfo is not None and cutoff<=posted.astimezone(timezone.utc)<=datetime.now(timezone.utc):published_24h+=1
            except (ValueError,TypeError):pass
        eligible=db.execute("SELECT COUNT(*) n FROM jobs WHERE candidate_id=? AND eligibility_status='eligible'",(cid,)).fetchone()["n"]
        avg=db.execute("SELECT AVG(match_score) n FROM jobs WHERE candidate_id=?",(cid,)).fetchone()["n"]
    statuses={r["status"]:r["n"] for r in apps}
    return {"jobs":jobs_count,"discovered_today":today,"published_24h":published_24h,"eligible":eligible,"applications":sum(statuses.values()),"submitted":statuses.get("Submitted",0),"failed":statuses.get("Submission failed",0),"average_match":round(avg or 0),"interviews":statuses.get("Interview",0),"offers":statuses.get("Offer",0),"statuses":statuses}

@app.post("/api/candidates/{cid}/documents/{job_id}")
def generate_resume(cid:int,job_id:int,body:dict | None = None,user_id:int|None=Depends(request_user_id)):
    person=candidate_record(cid,user_id)
    with connect() as db:
        job=db.execute("SELECT * FROM jobs WHERE id=? AND candidate_id=?",(job_id,cid)).fetchone()
        if not job: raise HTTPException(404,"Job not found")
    from docx import Document
    doc=Document(); doc.add_heading(person["name"],0)
    contact=" | ".join(x for x in [person.get("email"),person.get("phone"),person.get("location")] if x)
    if contact: doc.add_paragraph(contact)
    doc.add_heading("Professional Summary",1); doc.add_paragraph(person["summary"] or "Summary not provided in resume")
    profile=person["profile"]
    for heading,key in [("Skills","skills"),("Experience","experience"),("Education","education"),("Certifications","certifications"),("Achievements","achievements")]:
        values=profile.get(key,[])
        if values:
            doc.add_heading(heading,1)
            for value in values: doc.add_paragraph(value,style="List Bullet")
    path=GENERATED/f"candidate-{cid}-job-{job_id}-resume.docx"; doc.save(path)
    from reportlab.lib.pagesizes import LETTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    pdf_path=path.with_suffix(".pdf")
    styles=getSampleStyleSheet(); styles.add(ParagraphStyle(name="Section",parent=styles["Heading2"],textColor=colors.HexColor("#273b73"),spaceBefore=10,spaceAfter=4))
    story=[Paragraph(person["name"],styles["Title"])]
    if contact: story.append(Paragraph(contact,styles["Normal"]))
    story.extend([Spacer(1,10),Paragraph("Professional Summary",styles["Section"]),Paragraph((person["summary"] or "Summary not provided in resume").replace("&","&amp;"),styles["BodyText"])])
    for heading,key in [("Skills","skills"),("Experience","experience"),("Education","education"),("Certifications","certifications"),("Achievements","achievements")]:
        values=profile.get(key,[])
        if values:
            story.append(Paragraph(heading,styles["Section"]))
            story.extend(Paragraph("• "+str(v).replace("&","&amp;"),styles["BodyText"]) for v in values)
    SimpleDocTemplate(str(pdf_path),pagesize=LETTER,rightMargin=48,leftMargin=48,topMargin=44,bottomMargin=44).build(story)
    cover=Document()
    cover.add_heading("Cover Letter",0)
    if contact: cover.add_paragraph(contact)
    cover.add_paragraph("Dear Hiring Team,")
    intro=person["summary"] or "My background and the experience documented in my resume align with the role described in your vacancy."
    cover.add_paragraph(f"I am applying for the {job['title']} position at {job['company']}. {intro}")
    supported_skills=profile.get("skills",[])
    if supported_skills:
        cover.add_paragraph("My resume lists relevant skills including " + ", ".join(str(x) for x in supported_skills[:8]) + ".")
    cover.add_paragraph("I would welcome the opportunity to discuss how my documented experience can contribute to your team.")
    cover.add_paragraph("Sincerely,")
    cover.add_paragraph(person["name"])
    cover_path=GENERATED/f"candidate-{cid}-job-{job_id}-cover-letter.docx"; cover.save(cover_path)
    with connect() as db:
        db.execute("INSERT INTO documents(candidate_id,job_id,kind,path) VALUES(?,?,?,?)",(cid,job_id,"resume_docx",str(path)))
        db.execute("INSERT INTO documents(candidate_id,job_id,kind,path) VALUES(?,?,?,?)",(cid,job_id,"resume_pdf",str(pdf_path)))
        db.execute("INSERT INTO documents(candidate_id,job_id,kind,path) VALUES(?,?,?,?)",(cid,job_id,"cover_letter_docx",str(cover_path)))
    return {"filename":path.name,"url":f"/api/documents/{path.name}","pdf_url":f"/api/documents/{pdf_path.name}","cover_letter_url":f"/api/documents/{cover_path.name}","note":"Resume and cover letter generated from extracted resume facts; review before use."}

@app.get("/api/documents/{filename}")
def download(filename:str,user_id:int|None=Depends(request_user_id)):
    record=None
    with connect() as db:
        rows=db.execute("SELECT d.path FROM documents d JOIN candidates c ON c.id=d.candidate_id WHERE c.user_id=?",(user_id,)).fetchall() if user_id is not None else db.execute("SELECT d.path FROM documents d").fetchall()
        record=next((r["path"] for r in rows if r["path"].replace("\\","/").rsplit("/",1)[-1]==Path(filename).name),None)
    if not record:raise HTTPException(404,"Document not found")
    path=(GENERATED/Path(filename).name).resolve()
    if not path.is_relative_to(GENERATED.resolve()) or not path.exists():raise HTTPException(404,"Document not found")
    return FileResponse(path,filename=path.name)

@app.get("/api/candidates/{cid}/resume/file")
def download_resume(cid:int,user_id:int|None=Depends(request_user_id)):
    person=candidate_record(cid,user_id)
    path=Path(person.get("resume_path") or "").resolve()
    if not path.is_relative_to(UPLOADS.resolve()) or not path.exists():raise HTTPException(404,"Resume file not found")
    return FileResponse(path,filename=person.get("resume_name") or path.name)

frontend=ROOT/"frontend"/"dist"
if frontend.exists(): app.mount("/",StaticFiles(directory=frontend,html=True),name="frontend")
