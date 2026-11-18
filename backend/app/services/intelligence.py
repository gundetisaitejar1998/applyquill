import json
import re
import httpx
from json_repair import repair_json

STOP = set("the and for with from that this have has are was will your our you job role work team skills ability required preferred including years responsibilities responsibility candidate company position successful using use build create develop developing help support across within excellent strong good great new multiple various fast paced world class environment environments looking seeking ideal opportunity opportunities day days responsibilities qualifications requirements description based plus etc".split())

def terms(text):
    return [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z+#./-]{2,}", text or "") if w.lower() not in STOP]

def _norm(text):
    return re.sub(r"[^a-z0-9]+"," ",(text or "").lower()).strip()

def resume_evidence(profile):
    keys=("headline","summary","skills","experience","education","certifications","achievements")
    return {key:profile.get(key) for key in keys if profile.get(key)}

def parse_role_json(raw_response):
    try:return json.loads(raw_response)
    except (json.JSONDecodeError,TypeError):
        repaired=repair_json(raw_response or "",return_objects=True)
        if not isinstance(repaired,(dict,list)):raise ValueError("Ollama response did not contain a role object")
        return repaired

def classify_role(title,profile,model_category="related"):
    norm=lambda value:set(_norm(value).split())
    generic={"designer","design","senior","junior","lead","manager","director","specialist","associate","principal","head","artist","creator","coordinator","supervisor"}
    title_norm=_norm(title)
    direct=[str(x).lower() for x in [profile.get("headline", ""),*profile.get("role_titles",[])] if x]
    if any(title.lower() in item or item in title.lower() for item in direct):return "primary"
    core=norm(title)-generic
    history=set().union(*(norm(x) for x in profile.get("role_titles",[]))) if profile.get("role_titles") else set()
    skills=set().union(*(norm(x) for x in profile.get("skills",[]))) if profile.get("skills") else set()
    if core & (history-generic):return "related"
    if core & skills:return "adjacent"
    return "adjacent" if str(model_category).lower()=="adjacent" else "related"

async def generate_role_map(profile: dict, model: str, base_url="http://127.0.0.1:11434"):
    evidence={key:resume_evidence(profile).get(key) for key in ("headline","summary","skills","experience","education","certifications","achievements") if resume_evidence(profile).get(key)}
    evidence["experience"]=profile.get("role_titles",[]) or profile.get("experience",[])[:12]
    if isinstance(evidence.get("summary"),str): evidence["summary"]=evidence["summary"][:1200]
    if isinstance(evidence.get("skills"),list): evidence["skills"]=evidence["skills"][:40]
    prompt=(
        "Infer up to 14 distinct job titles from this resume, aiming for at least 10 when the actual evidence supports that many. Include primary titles directly supported by work history, equivalent titles, related titles, and adjacent roles supported by transferable resume skills. When supported, include at least 2 adjacent roles grounded in named transferable skills; do not mislabel close equivalents as adjacent. Do not pad the list: fewer than 10 is correct if the resume does not support more. "
        "Return JSON only: {\"roles\":[{\"title\":string,\"category\":\"primary|related|adjacent\",\"confidence\":0.0,\"why\":string,\"evidence_terms\":[string],\"synonyms\":[string],\"search_keywords\":[string]}]}. "
        "Each role needs 1 short reason, 2 exact evidence phrases copied from resume, 2 different equivalent title synonyms (do not repeat title), and up to 5 concrete search keywords. "
        "Use all three categories. Never duplicate role titles. Do not invent skills, tools, employers, dates, experience, or credentials. Keep output compact.\nResume evidence:\n"+json.dumps(evidence,ensure_ascii=False))
    async with httpx.AsyncClient(timeout=300) as client:
        response=await client.post(f"{base_url.rstrip('/')}/api/generate",json={"model":model,"prompt":prompt,"format":"json","stream":False,"options":{"temperature":0.1,"num_predict":1800,"num_ctx":6144}})
    if response.status_code!=200:
        raise RuntimeError(f"Ollama role generation failed (HTTP {response.status_code}): {response.text[:300]}")
    try:
        raw_response=response.json().get("response","")
        payload=parse_role_json(raw_response)
    except (ValueError,TypeError,AttributeError) as exc:
        raise RuntimeError("Ollama response could not be parsed as structured role data") from exc
    raw=payload.get("roles",[]) if isinstance(payload,dict) else payload
    if not isinstance(raw,list): raise RuntimeError("Ollama response did not contain a roles list")
    evidence_text=json.dumps(evidence,ensure_ascii=False)
    evidence_norm=_norm(evidence_text)
    evidence_terms=set(terms(evidence_text))
    tool_terms=set(terms(" ".join(profile.get("skills",[]))))
    roles=[]
    prior_titles=set()
    for item in raw[:14]:
        if not isinstance(item,dict) or not isinstance(item.get("title"),str) or not item["title"].strip(): continue
        title=item["title"].strip()
        synonyms=list(dict.fromkeys(str(x).strip() for x in item.get("synonyms",[]) if str(x).strip() and str(x).strip().lower()!=title.lower()))[:4]
        if title.lower() in prior_titles:
            title=next((syn for syn in synonyms if syn.lower() not in prior_titles),"")
            if not title: continue
            synonyms=[syn for syn in synonyms if syn.lower()!=title.lower()]
        prior_titles.add(title.lower())
        try: confidence=max(0,min(1,float(item.get("confidence",0.5))))
        except (ValueError,TypeError): confidence=0.5
        cited=list(dict.fromkeys(str(x).strip() for x in item.get("evidence_terms",[]) if str(x).strip() and _norm(str(x)) in evidence_norm))
        if not cited: cited=[t for t in terms(title+" "+str(item.get("why",""))) if t in evidence_terms]
        if not cited: continue
        proposed_category=str(item.get("category","related")).lower()
        if proposed_category not in {"primary","related","adjacent"}: proposed_category="related"
        category=classify_role(title,profile,proposed_category)
        keywords=item.get("keywords",{}) if isinstance(item.get("keywords"),dict) else {}
        normalized={k:[] for k in ("titles","skills","tools","industries","seniority")}
        for key in normalized:
            values=keywords.get(key,[])
            if isinstance(values,list):
                for value in values:
                    value=str(value).strip(); words=set(terms(value))
                    if value and value.lower()!=title.lower() and words and words<=evidence_terms and value.lower() not in {x.lower() for x in normalized[key]}:
                        normalized[key].append(value)
        search_keywords=item.get("search_keywords",[])
        for value in (search_keywords if isinstance(search_keywords,list) else []):
            value=str(value).strip(); words=set(terms(value))
            if value and words and words<=evidence_terms:
                key="tools" if words<=tool_terms else "skills"
                if value.lower() not in {x.lower() for x in normalized[key]}: normalized[key].append(value)
        normalized["titles"]=list(dict.fromkeys([*synonyms,*normalized["titles"]]))
        confidence=min(confidence,{"primary":0.95,"related":0.85,"adjacent":0.70}[category])
        roles.append({"title":title,"category":category,"confidence":round(confidence,2),
                      "why":str(item.get("why") or ("Resume supports this role through: "+", ".join(cited)))[:500],"evidence_terms":cited,
                      "synonyms":synonyms,"keywords":normalized,
                      "search_keywords":list(dict.fromkeys([*normalized["skills"],*normalized["tools"],*normalized["industries"],*normalized["seniority"]]))[:12],
                      "search_terms":list(dict.fromkeys([title,*synonyms,*normalized["titles"],*normalized["skills"],*normalized["tools"]]))[:30]})
    if not roles: raise RuntimeError("Ollama returned no usable role suggestions")
    return roles

def fallback_observed_roles(profile: dict):
    """Without a model, report only exact role titles extracted from the resume, never invented adjacent titles."""
    found=[]
    for line in profile.get("role_titles",[]):
        title=str(line).strip()
        if title and title.lower() not in {x["title"].lower() for x in found}:
            found.append({"title":title,"category":"primary","confidence":1.0,"why":"Title copied from the resume employment history.","evidence_terms":terms(title),"synonyms":[],"keywords":{"titles":[title],"skills":[],"tools":[],"industries":[],"seniority":[]},"search_terms":[title]})
    return found

def match_job(profile: dict, job: dict, preferences: dict | None = None):
    preferences=preferences or {}
    description_text=(job.get("description", "")+" "+job.get("title", ""))[:30000]
    description=_norm(description_text)
    description_terms=set(terms(description_text))
    job_title=_norm(job.get("title",""));matched_role=_norm(job.get("matched_role", ""))
    role_words=set(terms(matched_role));title_words=set(terms(job_title))
    title_fit=100 if matched_role and (matched_role in job_title or role_words<=title_words) else round(100*len(role_words&title_words)/max(1,len(role_words)))
    skills=[str(s).strip() for s in profile.get("skills",[]) if str(s).strip()]
    matching=[s for s in skills if _norm(s) in description or set(terms(s)) and set(terms(s))<=description_terms]
    missing=[s for s in skills if s not in matching]
    skills_score=min(100,round(100*len(matching)/max(1,min(len(skills),12))))
    resume_responsibilities=set(terms(" ".join([profile.get("summary",""),*profile.get("experience",[]),*profile.get("achievements",[])])))
    responsibility_overlap=resume_responsibilities & description_terms
    responsibility_score=min(100,round(100*len(responsibility_overlap)/max(1,min(15,len(resume_responsibilities)))))
    candidate_years=profile.get("experience_years")
    years_match=re.search(r"\b(\d{1,2})\s*\+?\s+years?\b",description_text,re.I)
    if not years_match: experience_score=75
    elif candidate_years and re.search(r"\d+",str(candidate_years)):
        experience_score=100 if int(re.search(r"\d+",str(candidate_years)).group())>=int(years_match.group(1)) else 30
    else: experience_score=50
    seniority_words={"intern","junior","entry","associate","mid","senior","lead","principal","manager","director","head"}
    job_level=seniority_words & set(terms(job.get("title","")))
    candidate_level=seniority_words & set(terms(profile.get("headline", " ")+" "+" ".join(profile.get("role_titles",[]))))
    seniority_score=100 if not job_level else (100 if job_level & candidate_level else 45)
    location=(job.get("location","") or "").lower()
    candidate_location=(profile.get("location","") or "").lower()
    eligibility_note=""
    if "remote" in location or str(job.get("work_mode", "")).lower()=="remote":
        if any(t in location for t in ("worldwide","global","anywhere")) or any(part.strip().lower() in location for part in candidate_location.split(",") if part.strip()):
            location_score=100
        elif set(_norm(location).split())-{"remote","job","work","anywhere","unspecified"}:
            location_score=25
            eligibility_note="Remote location names a region/country; confirm applications from the candidate's country are accepted."
        else:location_score=55
    elif any(part.strip().lower() in location for part in candidate_location.split(",") if part.strip()): location_score=100
    elif "india" in candidate_location and "india" in location: location_score=100
    else: location_score=20
    education_required=bool(re.search(r"bachelor|degree|master|phd|education",description_text,re.I))
    education_score=100 if education_required and profile.get("education") else 75 if not education_required else 25
    portfolio_terms=[str(x) for x in profile.get("portfolio_relevance_terms",[]) if str(x).strip()]
    portfolio_score=(100 if any(_norm(x) in description for x in portfolio_terms) else 0) if portfolio_terms else None
    candidate_industries=[_norm(x) for x in profile.get("industries",[]) if str(x).strip()]
    job_industry=_norm(" ".join(job.get("industry",[])) if isinstance(job.get("industry"),list) else job.get("industry",""))
    industry_score=(100 if any(x and x in job_industry for x in candidate_industries) else 0) if candidate_industries and job_industry else None
    compensation_score=None
    try:
        minimum=float(preferences.get("salary_min")) if preferences.get("salary_min") not in (None,"") else None
        currency=str(preferences.get("salary_currency") or "").upper()
        job_currency=str(job.get("salary_currency") or "").upper()
        job_min=job.get("salary_min")
        if minimum is not None and job_min is not None and currency and currency==job_currency:
            compensation_score=100 if float(job.get("salary_max") or job_min)>=minimum else 0
    except (ValueError,TypeError):pass
    score=min(100,max(0,round(title_fit*.30+skills_score*.25+experience_score*.15+responsibility_score*.10+seniority_score*.05+location_score*.10+education_score*.05)))
    return {"score":score,"classification":"Excellent" if score>=85 else "Strong" if score>=70 else "Possible" if score>=55 else "Poor",
            "matching_skills":matching[:25],"missing_skills":missing[:20],"responsibility_overlap":sorted(responsibility_overlap)[:20],
            "component_scores":{"role_relevance":title_fit,"skills":skills_score,"experience":experience_score,"responsibilities":responsibility_score,"seniority":seniority_score,"location":location_score,"education":education_score,"portfolio_relevance":portfolio_score,"industry_relevance":industry_score,"compensation_compatibility":compensation_score},
            "salary_compatible":"unknown" if compensation_score is None else "compatible" if compensation_score==100 else "below configured minimum","eligibility_note":eligibility_note,
            "explanation":f"Weighted local estimate: role-title fit {title_fit}, skills {skills_score}, experience {experience_score}, responsibilities {responsibility_score}, seniority {seniority_score}, location {location_score}, education {education_score}. Review listed requirements before applying."}
