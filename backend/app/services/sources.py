"""Composable public job-source adapters. Each adapter returns normalized live listings and diagnostics."""
import asyncio, html, os, re, time, json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import httpx

GREENHOUSE_DEFAULT_BOARDS=("figma","stripe","airbnb","anthropic","gitlab","reddit","databricks")
SOURCE_USER_AGENT="JobPilotAI/0.3 (local job discovery; see source attribution on listing)"
GENERIC_TITLE_WORDS={"designer","design","digital","senior","junior","lead","team","manager","director","specialist","associate","principal","head","artist"}
_REMOTIVE_CACHE_PATH=Path(__file__).resolve().parents[3]/"data"/"remotive-cache.json"
try:_remotive_cache=json.loads(_REMOTIVE_CACHE_PATH.read_text(encoding="utf-8"))
except (OSError,ValueError,TypeError):_remotive_cache={"at":0.0,"jobs":None,"http_status":None,"error":""}
_JOBICY_CACHE_PATH=Path(__file__).resolve().parents[3]/"data"/"jobicy-cache.json"
try:_jobicy_cache=json.loads(_JOBICY_CACHE_PATH.read_text(encoding="utf-8"))
except (OSError,ValueError,TypeError):_jobicy_cache={"at":0.0,"jobs":None,"http_status":None,"error":""}
_REMOTEOK_CACHE_PATH=Path(__file__).resolve().parents[3]/"data"/"remoteok-cache.json"
try:_REMOTEOK_CACHE=json.loads(_REMOTEOK_CACHE_PATH.read_text(encoding="utf-8"))
except (OSError,ValueError,TypeError):_REMOTEOK_CACHE={"at":0.0,"jobs":None,"http_status":None,"error":""}

def _norm(value): return re.sub(r"[^a-z0-9]+"," ",str(value or "").lower()).strip()

def deduplicate_listings(jobs):
    """Deduplicate exact URLs and cross-source copies of the same employer/title/location."""
    output=[];urls=set();fingerprints=[]
    for job in jobs:
        url=str(job.get("url") or "").strip()
        if not url or url in urls:continue
        urls.add(url);title=_norm(job.get("title"));company=_norm(job.get("company"));location=set(_norm(job.get("location")).split())-{"remote","hybrid","office","job","work","worldwide","global"}
        if any(title==t and company==c and (not location or not old_loc or location<=old_loc or old_loc<=location) for t,c,old_loc in fingerprints):continue
        output.append(job);fingerprints.append((title,company,location))
    return output

def search_variants(roles):
    """Create deduplicated exact-title and role-specific query terms from the model role map."""
    values=[]
    for role in roles:
        kws=role.get("keywords") or {};title=str(role.get("title") or "").strip()
        concepts=[str(x).strip() for x in [*kws.get("skills",[]),*kws.get("tools",[]),*kws.get("industries",[])] if str(x).strip()]
        combinations=[f"{title} {term}" for term in concepts[:3] if title]
        for value in [title,*role.get("synonyms",[]),*(kws.get("titles",[]) or []),*combinations,*role.get("search_terms",[]),*role.get("search_keywords",[])]:
            value=str(value or "").strip()
            if len(value)>=3 and value.casefold() not in {v.casefold() for v in values}: values.append(value)
    return values

def _matched_role(job,roles):
    title=_norm(job.get("title")); description=_norm(job.get("description"));title_words=set(title.split())
    for role in roles:
        phrases=[(role.get("title"),True),*((x,False) for x in role.get("synonyms",[])),*((x,False) for x in ((role.get("keywords") or {}).get("titles",[]) or []))]
        for phrase,direct in phrases:
            p=_norm(phrase)
            words=set(p.split())
            meaningful=words-GENERIC_TITLE_WORDS
            if p and ((direct and p in title) or (meaningful and meaningful<=title_words and (len(meaningful)>=2 or p in title))):
                return role,str(phrase)
    # Skill terms may widen discovery only when the vacancy title still belongs to the role family.
    for role in roles:
        role_words=set(_norm(" ".join([role.get("title", ""),*role.get("synonyms",[])] )).split())
        family_overlap=(role_words-GENERIC_TITLE_WORDS) & title_words
        if len(family_overlap)<2: continue
        kws=role.get("keywords",{}) or {}
        terms=[str(x) for x in [*kws.get("skills",[]),*kws.get("tools",[]),*kws.get("industries",[]),*role.get("search_keywords",[])] if len(_norm(x))>=4]
        hits=[x for x in terms if _norm(x) in title or _norm(x) in description]
        if len({ _norm(x) for x in hits})>=2: return role,"; ".join(hits[:3])
    return None,""

def _clean_html(value):
    value=re.sub(r"(?is)<(script|style).*?>.*?</\1>"," ",str(value or ""))
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",value))).strip()

def _date(value):
    if value in (None,""): return ""
    try:
        if isinstance(value,(int,float)) or str(value).isdigit():
            number=float(value);number=number/1000 if number>10_000_000_000 else number
            return datetime.fromtimestamp(number,tz=timezone.utc).isoformat().replace("+00:00","Z")
    except (ValueError,OverflowError,OSError):pass
    return str(value)

def _mode(location,description="",explicit=None):
    if explicit is True: return "Remote"
    if explicit is False:return "Office"
    if isinstance(explicit,str) and explicit.strip().lower() in {"remote","hybrid","onsite","on-site","office"}:
        value=explicit.strip().lower()
        return "Remote" if value=="remote" else "Hybrid" if value=="hybrid" else "Office"
    place=str(location or "").lower()
    if re.search(r"\b(remote|work from home|distributed|anywhere)\b",place): return "Remote"
    if re.search(r"\bhybrid\b",place): return "Hybrid"
    if re.search(r"\b(on[- ]?site|in[- ]office|office based)\b",place): return "Office"
    text=str(description or "")[:3500].lower()
    if re.search(r"\b(fully remote|100% remote|remote (?:position|role|job|work|first)|work remotely|work from home|remote arrangement)\b",text):return "Remote"
    if re.search(r"\bhybrid (?:position|role|work|schedule|arrangement)\b",text):return "Hybrid"
    if re.search(r"\b(on[- ]?site (?:position|role|work)|in[- ]office (?:position|role|work)|office based)\b",text):return "Office"
    return "Not specified"

def _location_match(location,locations,allow_remote,description="",explicit_remote=None):
    if not locations: return True
    text=_norm(str(location or ""))
    if any(_norm(part) in text for loc in locations for part in str(loc).split(",") if len(_norm(part))>2): return True
    if allow_remote and _mode(location,description,explicit_remote)=="Remote":
        # A remote label paired with another place usually means remote only
        # within that place. Accept unqualified/worldwide remote postings, or
        # ones whose stated region already matched the candidate above.
        words=set(text.split())
        unrestricted={"remote","work","from","home","distributed","anywhere","worldwide","global","unspecified","location","not","specified","friendly","travel","required","position","role","job","workplace","based","only"}
        return not bool(words-unrestricted)
    return False

def _is_unrestricted_remote(location,allow_remote):
    normalized=_norm(location)
    restricted=("united states","usa","canada","north america","europe","united kingdom","uk remote","australia","germany")
    return bool(allow_remote and "remote" in str(location or "").lower() and not re.match(r"^(?:us|usa|uk|ca|au)\b",normalized) and not any(x in normalized for x in restricted))

def normalize_board_url(url):
    """Resolve only public Greenhouse/Lever hosted board URLs; caller verifies the endpoint."""
    parsed=urlparse(url.strip())
    host=(parsed.hostname or "").lower(); parts=[p for p in parsed.path.split("/") if p]
    if parsed.scheme not in {"http","https"}: raise ValueError("Use a public HTTPS careers URL.")
    if host in {"boards.greenhouse.io","job-boards.greenhouse.io"} and parts:
        token=parts[0].lower()
        return {"provider":"greenhouse","identifier":token,"label":token}
    if host in {"jobs.lever.co","jobs.eu.lever.co"} and parts:
        site=parts[0].lower()
        return {"provider":"lever","identifier":site,"label":site,"region":"eu" if host=="jobs.eu.lever.co" else "global"}
    raise ValueError("Supported board URL patterns are boards.greenhouse.io/{board} or jobs.lever.co/{site}.")

def _entry(source,query="",board=""):
    return {"source":source,"query":query,"board":board,"status":"pending","http_status":None,"available":0,"matched":0,"role_filtered":0,"location_filtered":0,"error":"","retry_after":""}

def _job(title,company,location,url,description,source,posted_at="",salary="",job_type="",remote=None,roles=(),extra=None):
    matched,phrase=_matched_role({"title":title,"description":description},roles)
    if not matched: return None
    result={"title":str(title or ""),"company":str(company or ""),"location":str(location or ""),"url":str(url or ""),"description":_clean_html(description),"source":source,"posted_at":_date(posted_at),"salary":str(salary or ""),"job_type":str(job_type or ""),"work_mode":_mode(location,description,remote),"matched_role":matched.get("title",""),"matched_synonym":phrase}
    if extra: result.update(extra)
    return result

async def _request(client,url,params=None):
    """Bounded retries for transient failures; respect publisher Retry-After values."""
    last=None
    for attempt in range(3):
        try:
            response=await client.get(url,params=params)
            if response.status_code==429:
                # Never retry aggressively. Report the 429 if the server asks for a long wait.
                delay=response.headers.get("Retry-After","")
                try: wait=min(3.0,max(0.25,float(delay)))
                except (ValueError,TypeError): wait=1.0
                if attempt<2 and wait<=2.0:
                    await asyncio.sleep(wait);continue
                return response
            if response.status_code>=500 and attempt<2:
                await asyncio.sleep(.25*(attempt+1));continue
            return response
        except (httpx.TimeoutException,httpx.NetworkError) as exc:
            last=exc
            if attempt==2: raise
            await asyncio.sleep(.25*(attempt+1))
    if last: raise last

async def search_greenhouse(roles,locations=None,allow_remote=False,boards=None):
    locations=list(locations or []); board_list=list(dict.fromkeys(str(x).strip().lower() for x in (boards or GREENHOUSE_DEFAULT_BOARDS) if str(x).strip()))
    results=[];report=[];variants=search_variants(roles)
    async with httpx.AsyncClient(timeout=25,follow_redirects=True,headers={"User-Agent":SOURCE_USER_AGENT,"Accept":"application/json"}) as client:
      for board in board_list:
        e=_entry("Greenhouse public Job Board API",board=board); started=time.perf_counter()
        try:
            r=await _request(client,f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs",{"content":"true"});e["http_status"]=r.status_code
            if r.status_code==429:e.update(status="rate_limited",error="Greenhouse returned HTTP 429",retry_after=r.headers.get("Retry-After",""))
            elif r.status_code!=200:e.update(status="http_error",error=f"Greenhouse returned HTTP {r.status_code}")
            else:
                data=r.json();rows=data.get("jobs")
                if not isinstance(rows,list):raise ValueError("Expected jobs array in Greenhouse response")
                e.update(status="ok",available=len(rows))
                for row in rows:
                    loc=(row.get("location") or {}).get("name","");desc=row.get("content","");job=_job(row.get("title"),row.get("company_name") or board.title(),loc,row.get("absolute_url"),desc,f"Greenhouse ({board})",row.get("first_published") or row.get("updated_at"),roles=roles,extra={"work_mode":_mode(loc,desc)})
                    if not job:e["role_filtered"]+=1;continue
                    if not _location_match(loc,locations,allow_remote,desc):e["location_filtered"]+=1;continue
                    if job["url"]:e["matched"]+=1;results.append(job)
        except (httpx.HTTPError,ValueError,KeyError,TypeError) as ex:e.update(status="network_error" if isinstance(ex,httpx.HTTPError) else "parse_error",error=f"{type(ex).__name__}: {str(ex)[:200]}")
        e["duration_ms"]=round((time.perf_counter()-started)*1000);e["search_variants"]=[v for v in variants if v][:40];report.append(e)
      await asyncio.sleep(.15)
    return results,{"source":"Greenhouse public Job Board API","checked":len(report),"status":"ok" if any(x['status']=='ok' for x in report) else "error" if report else "configuration_required","error":"No Greenhouse boards configured." if not report else "","boards":report,"locations":locations,"remote_allowed":allow_remote,"coverage":"Per-employer public boards only; not a global Greenhouse search."}

async def search_lever(roles,locations=None,allow_remote=False,boards=None):
    locations=list(locations or []); results=[]; report=[];sites=list(boards or [])
    async with httpx.AsyncClient(timeout=25,follow_redirects=True,headers={"User-Agent":SOURCE_USER_AGENT,"Accept":"application/json"}) as client:
      for item in sites:
        site=item if isinstance(item,dict) else {"identifier":str(item),"region":"global"};token=site["identifier"];region=site.get("region","global");host="api.eu.lever.co" if region=="eu" else "api.lever.co";e=_entry("Lever Postings API",board=token);started=time.perf_counter()
        try:
          skip=0;rows=[]
          while skip<1000:
            r=await _request(client,f"https://{host}/v0/postings/{token}",{"mode":"json","limit":100,"skip":skip});e["http_status"]=r.status_code
            if r.status_code==429:e.update(status="rate_limited",retry_after=r.headers.get("Retry-After",""),error="Lever returned HTTP 429");break
            if r.status_code!=200:e.update(status="http_error",error=f"Lever returned HTTP {r.status_code}");break
            batch=r.json()
            if not isinstance(batch,list):raise ValueError("Expected postings array in Lever response")
            rows.extend(batch)
            if len(batch)<100: e["status"]="ok";break
            skip+=len(batch)
          e["available"]=len(rows)
          if e["status"]=="pending":e["status"]="ok"
          for row in rows:
            cats=row.get("categories") or {};loc=cats.get("location","");desc=row.get("descriptionPlain") or row.get("description") or row.get("additionalPlain") or "";hosted=row.get("hostedUrl") or row.get("applyUrl") or "";job=_job(row.get("text"),row.get("company") or token,loc,hosted,desc,f"Lever ({token})",row.get("createdAt") or row.get("updatedAt"),job_type=", ".join(cats.get("commitment",[]) if isinstance(cats.get("commitment"),list) else [str(cats.get("commitment") or "")]),remote=row.get("workplaceType") or cats.get("workplaceType"),roles=roles)
            if not job:e["role_filtered"]+=1;continue
            if not _location_match(loc,locations,allow_remote,desc):e["location_filtered"]+=1;continue
            if job["url"]:e["matched"]+=1;results.append(job)
        except (httpx.HTTPError,ValueError,KeyError,TypeError) as ex:e.update(status="network_error" if isinstance(ex,httpx.HTTPError) else "parse_error",error=f"{type(ex).__name__}: request failed" if isinstance(ex,httpx.HTTPError) else f"{type(ex).__name__}: {str(ex)[:200]}")
        e["duration_ms"]=round((time.perf_counter()-started)*1000);report.append(e)
    status="ok" if any(x["status"]=="ok" for x in report) else "configuration_required" if not report else "error"
    return results,{"source":"Lever Postings API","checked":len(report),"boards":report,"status":status,"error":"No Lever employer boards configured. Add a public jobs.lever.co/{site} URL in Source settings." if not report else "","locations":locations,"coverage":"Per-employer public sites only; not a global Lever search."}

async def search_arbeitnow(roles,locations=None,allow_remote=False,max_pages=3):
    source="Arbeitnow public Job Board API";locations=list(locations or []);results=[];report=[];seen=set()
    async with httpx.AsyncClient(timeout=25,follow_redirects=True,headers={"User-Agent":SOURCE_USER_AGENT,"Accept":"application/json"}) as client:
      for page in range(1,max_pages+1):
        e=_entry(source,query=f"page {page}");started=time.perf_counter()
        try:
          r=await _request(client,"https://www.arbeitnow.com/api/job-board-api",{"page":page});e["http_status"]=r.status_code
          if r.status_code==429:e.update(status="rate_limited",retry_after=r.headers.get("Retry-After",""),error="Arbeitnow returned HTTP 429")
          elif r.status_code!=200:e.update(status="http_error",error=f"Arbeitnow returned HTTP {r.status_code}")
          else:
            data=r.json();rows=data.get("data")
            if not isinstance(rows,list):raise ValueError("Expected data array in Arbeitnow response")
            e.update(status="ok",available=len(rows))
            for row in rows:
              loc=row.get("location","");desc=row.get("description","")+" "+" ".join(row.get("tags",[]) or []);job=_job(row.get("title"),row.get("company_name"),loc,row.get("url"),desc,source,str(row.get("created_at") or ""),remote=row.get("remote"),roles=roles)
              if not job:e["role_filtered"]+=1;continue
              if not _location_match(loc,locations,allow_remote,desc,row.get("remote")):e["location_filtered"]+=1;continue
              if job["url"] and job["url"] not in seen:seen.add(job["url"]);e["matched"]+=1;results.append(job)
        except (httpx.HTTPError,ValueError,KeyError,TypeError) as ex:e.update(status="network_error" if isinstance(ex,httpx.HTTPError) else "parse_error",error=f"{type(ex).__name__}: {str(ex)[:200]}")
        e["duration_ms"]=round((time.perf_counter()-started)*1000);report.append(e)
        if e["status"]!="ok" or e["available"]==0:break
    return results,{"source":source,"checked":len(report),"queries":report,"status":"ok" if any(x["status"]=="ok" for x in report) else "error","locations":locations,"coverage":"Public feed is primarily European; no server-side keyword/location filters."}

async def search_remotive(roles,locations=None,allow_remote=False):
    """One API call per six hours (the publisher advises at most four per day); filter locally."""
    global _remotive_cache
    source="Remotive public remote-jobs API";locations=list(locations or []);now=time.time();cached=_remotive_cache["jobs"] is not None and now-_remotive_cache["at"]<21600
    if cached: rows=_remotive_cache["jobs"];status="cached";http_status=_remotive_cache["http_status"];error=_remotive_cache["error"]
    else:
      try:
        async with httpx.AsyncClient(timeout=30,follow_redirects=True,headers={"User-Agent":SOURCE_USER_AGENT,"Accept":"application/json"}) as client:r=await _request(client,"https://remotive.com/api/remote-jobs")
        http_status=r.status_code
        if r.status_code!=200: rows=None;status="rate_limited" if r.status_code==429 else "http_error";error=f"Remotive returned HTTP {r.status_code}"
        else:
          payload=r.json();rows=payload.get("jobs")
          if not isinstance(rows,list):raise ValueError("Expected jobs array in Remotive response")
          status="ok";error="";_remotive_cache={"at":now,"jobs":rows,"http_status":http_status,"error":""}
          try:_REMOTIVE_CACHE_PATH.write_text(json.dumps(_remotive_cache,ensure_ascii=False),encoding="utf-8")
          except OSError:pass
      except (httpx.HTTPError,ValueError,TypeError) as ex:rows=None;http_status=None;status="network_error" if isinstance(ex,httpx.HTTPError) else "parse_error";error=f"{type(ex).__name__}: {str(ex)[:200]}"
    e=_entry(source);e.update(status=status,http_status=http_status,available=len(rows or []),error=error,cache_hit=cached,fetched_at=datetime.fromtimestamp(_remotive_cache['at'],tz=timezone.utc).isoformat().replace('+00:00','Z') if _remotive_cache.get('at') else None);results=[];location_filtered=0
    for row in rows or []:
      loc=row.get("candidate_required_location","") or "Remote (location unspecified)";job=_job(row.get("title"),row.get("company_name"),loc,row.get("url"),row.get("description"),source,row.get("publication_date"),row.get("salary"),row.get("job_type"),True,roles)
      if not job:e["role_filtered"]+=1;continue
      # Remotive listings are remote but may restrict eligible countries. Unknown/worldwide is allowed.
      required=_norm(row.get("candidate_required_location",""));worldwide=not required or any(x in required for x in ("worldwide","anywhere","global","all countries"));india="india" in required or any(_norm(loc) in required for loc in locations if loc)
      if locations and not(worldwide or india):location_filtered+=1;continue
      if job["url"]:results.append(job)
    e["matched"]=len(results);e["location_filtered"]=location_filtered
    if not allow_remote:results=[];e["matched"]=0;e.update(status="skipped_remote_preference",error="Candidate preferences do not include remote work.")
    return results,{"source":source,"checked":1,"queries":[e],"status":status,"error":error,"locations":locations,"remote_allowed":allow_remote,"attribution":"Remotive","rate_limit_policy":"Cached for 6 hours; publisher recommends at most 4 requests/day and blocks >2/minute."}

async def search_jobicy(roles,locations=None,allow_remote=False):
    """Search Jobicy's public remote feed; cache for an hour per its fair-use guidance."""
    global _jobicy_cache
    source="Jobicy public remote-jobs API";locations=list(locations or []);now=time.time()
    cached=_jobicy_cache.get("jobs") is not None and now-_jobicy_cache.get("at",0)<3600
    page_count=_jobicy_cache.get("page_count",1) if cached else 0;has_more=bool(_jobicy_cache.get("has_more",False)) if cached else False
    if cached:
        rows=_jobicy_cache["jobs"];status="cached";http_status=_jobicy_cache.get("http_status");error=""
    else:
        rows=[];cursor=None;status="ok";error="";http_status=None;has_more=False
        try:
            async with httpx.AsyncClient(timeout=25,follow_redirects=True,headers={"User-Agent":SOURCE_USER_AGENT,"Accept":"application/json"}) as client:
                for _ in range(10):
                    params={"count":100}
                    if cursor:params["cursor"]=cursor
                    response=await _request(client,"https://jobicy.com/api/jobs",params);http_status=response.status_code
                    if response.status_code!=200:
                        status="rate_limited" if response.status_code==429 else "http_error"
                        error="Jobicy returned HTTP 429; the publisher asks clients to reduce polling frequency." if response.status_code==429 else f"Jobicy returned HTTP {response.status_code}"
                        break
                    payload=response.json()
                    if payload.get("success") is False:raise ValueError(str(payload.get("error") or "Jobicy reported success=false"))
                    batch=payload.get("jobs")
                    if not isinstance(batch,list):raise ValueError("Expected jobs array in Jobicy response")
                    rows.extend(batch);page_count+=1;cursor=payload.get("nextCursor")
                    if not cursor:break
                has_more=bool(cursor)
                if rows:
                    if has_more:
                        status="partial";error="Jobicy has more pages than the 10-page safety limit; search used the first 1,000 recent listings."
                    elif status!="ok":status="partial"
                    _jobicy_cache={"at":now,"jobs":rows,"http_status":http_status,"error":error,"page_count":page_count,"has_more":has_more}
                    try:_JOBICY_CACHE_PATH.write_text(json.dumps(_jobicy_cache,ensure_ascii=False),encoding="utf-8")
                    except OSError:pass
                elif status=="ok":raise ValueError("Jobicy returned an empty page set without a valid jobs array")
        except (httpx.HTTPError,ValueError,TypeError) as exc:
            status="network_error" if isinstance(exc,httpx.HTTPError) else "parse_error";error=f"{type(exc).__name__}: {str(exc)[:200]}"
            rows=[]
        if not rows and _jobicy_cache.get("jobs") is not None:
            rows=_jobicy_cache["jobs"];status="cached";error=f"Refresh failed ({error}); showing cached Jobicy feed.";cached=True
            page_count=_jobicy_cache.get("page_count",1);has_more=bool(_jobicy_cache.get("has_more",False))
    entry=_entry(source);entry.update(status=status,http_status=http_status,available=len(rows or []),error=error,cache_hit=cached,
        fetched_at=datetime.fromtimestamp(_jobicy_cache["at"],tz=timezone.utc).isoformat().replace("+00:00","Z") if _jobicy_cache.get("at") else None)
    results=[];location_filtered=0;role_filtered=0
    for row in rows or []:
        title=row.get("jobTitle","");company=row.get("companyName","");geo=str(row.get("jobGeo") or "Remote (location unspecified)");description=row.get("jobDescription") or row.get("jobExcerpt") or ""
        job_type=row.get("jobType") or "";job_type=", ".join(map(str,job_type)) if isinstance(job_type,list) else str(job_type)
        salary=""
        if row.get("salaryMin") or row.get("salaryMax"):
            salary=f"{row.get('salaryMin') or ''} - {row.get('salaryMax') or ''} {row.get('salaryCurrency') or ''} {row.get('salaryPeriod') or ''}".strip()
        job=_job(title,company,geo,row.get("url"),description,source,row.get("pubDate"),salary,job_type,True,roles,
                 extra={"source_id":row.get("id"),"source_attribution":"Jobicy","industry":row.get("jobIndustry") or [],"seniority":row.get("jobLevel") or ""})
        if not job:role_filtered+=1;continue
        if not allow_remote:
            location_filtered+=1;continue
        geo_norm=_norm(geo)
        worldwide=any(term in geo_norm for term in ("anywhere","worldwide","global","all countries"))
        eligible=worldwide or any(_norm(part) in geo_norm for loc in locations for part in str(loc).split(",") if len(_norm(part))>2)
        if locations and not eligible:location_filtered+=1;continue
        entry["matched"]+=1;results.append(job)
    entry["location_filtered"]=location_filtered;entry["role_filtered"]=role_filtered
    report_status="cached" if status=="cached" else status
    return results,{"source":source,"checked":page_count or (1 if status not in {"configuration_required"} else 0),"queries":[entry],"status":report_status,"error":error,"locations":locations,
        "remote_allowed":allow_remote,"attribution":"Jobicy; original Jobicy listing URLs retained.",
        "rate_limit_policy":"Public publisher requests no more frequently than once per hour; local feed cache is retained for one hour.",
        "coverage":f"Public remote listings published within the latest 7 days; {page_count} page(s) loaded, {len(rows or [])} listings available"+("; more pages remain" if has_more else ".")}

async def search_adzuna(roles,locations=None,countries=None,app_id=None,app_key=None):
    app_id=app_id or os.getenv("ADZUNA_APP_ID","");app_key=app_key or os.getenv("ADZUNA_APP_KEY","");source="Adzuna Jobs API";locations=list(locations or [])
    if not app_id or not app_key:return [],{"source":source,"checked":0,"status":"configuration_required","error":"Adzuna needs ADZUNA_APP_ID and ADZUNA_APP_KEY from developer.adzuna.com.","queries":[]}
    countries=countries or ["in"];variants=search_variants(roles);queries=variants[:10];report=[];results=[];seen=set()
    async with httpx.AsyncClient(timeout=25,follow_redirects=True,headers={"User-Agent":SOURCE_USER_AGENT,"Accept":"application/json"}) as client:
      for country in countries:
       for query in queries:
        e=_entry(source,query=query);started=time.perf_counter()
        try:
          r=await _request(client,f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",{"app_id":app_id,"app_key":app_key,"results_per_page":50,"what":query,"where":", ".join(locations) if locations else "","content-type":"application/json"});e["http_status"]=r.status_code
          if r.status_code==429:e.update(status="rate_limited",retry_after=r.headers.get("Retry-After",""),error="Adzuna returned HTTP 429")
          elif r.status_code!=200:e.update(status="http_error",error=f"Adzuna returned HTTP {r.status_code}: {r.text[:160]}")
          else:
            data=r.json();rows=data.get("results")
            if not isinstance(rows,list):raise ValueError("Expected results array in Adzuna response")
            e.update(status="ok",available=len(rows))
            for row in rows:
              loc=(row.get("location") or {}).get("display_name","");desc=row.get("description","");salary=row.get("salary_min");sal=f"{salary} - {row.get('salary_max')} {row.get('salary_currency','')}" if salary else "";company=(row.get("company") or {}).get("display_name","");job=_job(row.get("title"),company,loc,row.get("redirect_url") or row.get("url"),desc,source,row.get("created"),sal,remote=None,roles=roles)
              if not job:e["role_filtered"]+=1;continue
              if job["url"] and job["url"] not in seen:seen.add(job["url"]);e["matched"]+=1;results.append(job)
        except (httpx.HTTPError,ValueError,KeyError,TypeError) as ex:e.update(status="network_error" if isinstance(ex,httpx.HTTPError) else "parse_error",error=f"{type(ex).__name__}: Adzuna request failed" if isinstance(ex,httpx.HTTPError) else f"{type(ex).__name__}: {str(ex)[:200]}")
        e["duration_ms"]=round((time.perf_counter()-started)*1000);report.append(e)
    return results,{"source":source,"checked":len(report),"queries":report,"status":"ok" if any(x["status"]=="ok" for x in report) else "error","countries":countries,"locations":locations}

async def search_remoteok(roles,locations=None,allow_remote=False):
    """Remote OK public JSON feed, polled at most once per hour and attributed per listing."""
    global _REMOTEOK_CACHE
    source="Remote OK public jobs feed";now=time.time();locations=list(locations or [])
    if not allow_remote:return [],{"source":source,"checked":0,"status":"skipped_remote_preference","error":"Remote work is not in the candidate preferences.","queries":[]}
    cached=_REMOTEOK_CACHE["jobs"] is not None and now-_REMOTEOK_CACHE["at"]<3600
    if cached:rows=_REMOTEOK_CACHE["jobs"];status="cached";http_status=_REMOTEOK_CACHE["http_status"];error=""
    else:
        try:
            async with httpx.AsyncClient(timeout=25,follow_redirects=True,headers={"User-Agent":SOURCE_USER_AGENT,"Accept":"application/json"}) as client:
                response=await _request(client,"https://remoteok.com/api")
            http_status=response.status_code
            if response.status_code!=200:rows=[];status="rate_limited" if response.status_code==429 else "http_error";error=f"Remote OK returned HTTP {response.status_code}"
            else:
                payload=response.json()
                if not isinstance(payload,list):raise ValueError("Expected a JSON array from Remote OK")
                rows=[x for x in payload if isinstance(x,dict) and (x.get("position") or x.get("title"))]
                status="ok";error="";_REMOTEOK_CACHE={"at":now,"jobs":rows,"http_status":http_status,"error":""}
                try:_REMOTEOK_CACHE_PATH.write_text(json.dumps(_REMOTEOK_CACHE,ensure_ascii=False),encoding="utf-8")
                except OSError:pass
        except (httpx.HTTPError,ValueError,TypeError) as exc:
            rows=[];http_status=None;status="network_error" if isinstance(exc,httpx.HTTPError) else "parse_error";error=f"{type(exc).__name__}: {str(exc)[:200]}"
    entry=_entry(source);entry.update(status=status,http_status=http_status,available=len(rows),error=error,cache_hit=cached,
        attribution="Remote OK",attribution_url="https://remoteok.com",rate_limit_policy="Public feed cached locally for one hour; every result links directly to its Remote OK listing.")
    results=[]
    for row in rows:
        title=row.get("position") or row.get("title");url=row.get("url") or (f"https://remoteok.com/remote-jobs/{row.get('id')}" if row.get("id") else "")
        tags=row.get("tags") or [];description=str(row.get("description") or "")+" "+" ".join(map(str,tags))
        salary="";minimum=row.get("salary_min");maximum=row.get("salary_max")
        if minimum or maximum:salary=f"{minimum or ''} - {maximum or ''} {row.get('salary_currency') or 'USD'}"
        job=_job(title,row.get("company"),row.get("location") or "Remote (location unspecified)",url,description,source,row.get("date"),salary,remote=True,roles=roles,
            extra={"source_id":row.get("id"),"external_application_url":row.get("apply_url"),"source_attribution":"Remote OK","industry":tags})
        if not job:entry["role_filtered"]+=1;continue
        region=_norm(row.get("location"));if_countries={"worldwide","anywhere","global","remote","unspecified"}
        if locations and region and not any(_norm(loc) in region for loc in locations) and not any(x in region for x in if_countries):entry["location_filtered"]+=1;continue
        if url:results.append(job)
    entry["matched"]=len(results)
    return results,{"source":source,"checked":1,"status":status,"error":error,"queries":[entry],"attribution":"Remote OK","coverage":"Official public remote jobs JSON feed. Remote OK requests feed credit and a direct link to each original job post."}

async def verify_board(url):
    board=normalize_board_url(url);token=board["identifier"]
    if board["provider"]=="greenhouse":endpoint=f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    else:endpoint=f"https://{'api.eu.lever.co' if board.get('region')=='eu' else 'api.lever.co'}/v0/postings/{token}?mode=json&limit=1"
    async with httpx.AsyncClient(timeout=15,follow_redirects=True,headers={"User-Agent":SOURCE_USER_AGENT,"Accept":"application/json"}) as client:r=await client.get(endpoint)
    if r.status_code!=200:raise ValueError(f"The detected {board['provider']} board returned HTTP {r.status_code}; not saved.")
    data=r.json();count=len(data.get("jobs",[])) if isinstance(data,dict) else len(data) if isinstance(data,list) else 0
    return {**board,"verified":True,"http_status":r.status_code,"available":count}
