"""Conservative, evidence-only hard eligibility checks for candidate/job pairs."""
import re


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _as_list(value):
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    return [str(x).strip() for x in value or [] if str(x).strip()]


def _salary(job):
    minimum, maximum = job.get("salary_min"), job.get("salary_max")
    currency = str(job.get("salary_currency") or "").upper()
    if minimum is not None or maximum is not None:
        return minimum, maximum, currency
    text = str(job.get("salary") or "")
    match = re.search(r"(USD|EUR|GBP|INR|\$|€|£)\s*([\d,.]+)(?:\s*[-–]\s*(?:USD|EUR|GBP|INR|\$|€|£)?\s*([\d,.]+))?", text, re.I)
    if not match:
        return None, None, currency
    token = match.group(1).upper()
    currency = {"$": "USD", "€": "EUR", "£": "GBP"}.get(token, token)
    return float(match.group(2).replace(",", "")), float(match.group(3).replace(",", "")) if match.group(3) else None, currency


def evaluate_eligibility(profile: dict, preferences: dict, job: dict) -> dict:
    """Return eligible/ineligible/unknown with explicit reasons; never fill missing facts."""
    checks = {}
    reasons = []
    title = _norm(job.get("title"))
    description = str(job.get("description") or "")
    location = _norm(job.get("location"))
    work_mode = str(job.get("work_mode") or "").lower()

    if job.get("expired") is True:
        checks["availability"] = "ineligible"
        reasons.append("The source explicitly marks this vacancy as expired.")
    else:
        checks["availability"] = "eligible"

    remote_countries = [x for x in _as_list(preferences.get("remote_countries"))]
    target_locations = _as_list(preferences.get("locations") or preferences.get("cities"))
    candidate_location = str(profile.get("location") or "")
    if target_locations and any(_norm(x) in location for x in target_locations):
        checks["location"] = "eligible"
    elif work_mode == "remote":
        allowed = remote_countries or (["India"] if "india" in _norm(candidate_location) else [])
        if any(_norm(country) in location for country in allowed) or any(x in location for x in ("worldwide", "global", "anywhere", "all countries")):
            checks["location"] = "eligible"
        elif any(x in location for x in ("united states", "usa", "canada", "europe", "united kingdom", "australia", "germany")) or re.search(r"\bus\b",location):
            checks["location"] = "ineligible"
            reasons.append("Remote location restrictions do not include the candidate's configured work location.")
        else:
            checks["location"] = "unknown"
            reasons.append("Remote country eligibility is not explicit in the vacancy.")
    elif target_locations:
        checks["location"] = "ineligible"
        reasons.append("The vacancy location does not match the candidate's configured locations.")
    else:
        checks["location"] = "unknown"
        reasons.append("No candidate location preference is configured.")

    preferred_types = {_norm(x) for x in _as_list(preferences.get("employment_types"))}
    job_type = _norm(job.get("employment_type") or job.get("job_type"))
    if preferred_types and job_type:
        type_aliases = {"full time": {"full time", "fulltime", "permanent"}, "contract": {"contract", "contractor", "temporary"}}
        matched_type = any(job_type in type_aliases.get(pref, {pref}) for pref in preferred_types)
        checks["employment_type"] = "eligible" if matched_type else "ineligible"
        if not matched_type:
            reasons.append("Employment type is outside the candidate's selected preferences.")
    else:
        checks["employment_type"] = "unknown"
        reasons.append("Employment type or employment preferences are missing.")

    candidate_years = profile.get("experience_years")
    required_years = job.get("experience_min")
    if required_years is None:
        m = re.search(r"(?:at least|minimum of|minimum|\b)(\d{1,2})\+?\s+years?", description, re.I)
        required_years = float(m.group(1)) if m else None
    if required_years is not None and candidate_years is not None:
        try:
            checks["experience"] = "eligible" if float(candidate_years) >= float(required_years) else "ineligible"
            if checks["experience"] == "ineligible": reasons.append("Required years of experience exceed the candidate's recorded experience.")
        except (TypeError, ValueError):
            checks["experience"] = "unknown"
            reasons.append("Candidate experience is not recorded as a comparable number of years.")
    elif re.search(r"\b(senior|staff|principal|director|head of)\b", title) and not any(x in title for x in ("junior", "associate")):
        checks["experience"] = "ineligible" if any(x in {_norm(v) for v in _as_list(preferences.get("experience_levels"))} for x in ("junior", "associate", "mid level")) else "unknown"
        if checks["experience"] == "ineligible": reasons.append("The vacancy seniority is outside the candidate's selected experience levels.")
    else:
        checks["experience"] = "unknown"
        reasons.append("The source or candidate profile does not establish comparable experience requirements.")

    required_degree = re.search(r"\b(required|must have|minimum qualification)\b.{0,100}\b(bachelor|degree|master|phd)\b", description, re.I)
    if required_degree and not profile.get("education"):
        checks["qualifications"] = "unknown"
        reasons.append("A required education qualification is present, but candidate education is not recorded.")
    else:
        checks["qualifications"] = "eligible" if not required_degree else "unknown"
        if required_degree:
            reasons.append("Candidate education needs review against the stated qualification.")

    authorization_required = bool(re.search(r"(must be authorized|work authorization required|legally authorized|right to work|visa sponsorship not available)", description, re.I))
    authorization = profile.get("work_authorization")
    if authorization_required:
        if authorization and profile.get("work_authorization_verified") is True:
            checks["work_authorization"] = "eligible" if _norm(authorization) in location or _norm(authorization) in _norm(candidate_location) else "unknown"
            if checks["work_authorization"] == "unknown": reasons.append("Recorded work authorization does not establish eligibility for the vacancy location.")
        else:
            checks["work_authorization"] = "unknown"
            reasons.append("Work authorization is not verified for this vacancy's location.")
    else:
        checks["work_authorization"] = "unknown"

    minimum_salary = preferences.get("salary_min")
    salary_currency = str(preferences.get("salary_currency") or "").upper()
    if minimum_salary not in (None, ""):
        low, high, currency = _salary(job)
        if low is None or not currency:
            checks["salary"] = "unknown"
            reasons.append("The vacancy does not provide a comparable salary and currency.")
        elif salary_currency and currency != salary_currency:
            checks["salary"] = "unknown"
            reasons.append("Vacancy and preference currencies differ; no exchange-rate assumption was made.")
        elif (high if high is not None else low) < float(minimum_salary):
            checks["salary"] = "ineligible"
            reasons.append("The stated salary range is below the candidate's configured minimum.")
        else:
            checks["salary"] = "eligible"
    else:
        checks["salary"] = "unknown"

    required_checks = ["availability", "location", "employment_type", "experience", "qualifications"]
    if authorization_required:
        required_checks.append("work_authorization")
    if minimum_salary not in (None, ""):
        required_checks.append("salary")
    if any(checks.get(k) == "ineligible" for k in required_checks):
        status = "ineligible"
    elif all(checks.get(k) == "eligible" for k in required_checks):
        status = "eligible"
    else:
        status = "unknown"
    return {"status": status, "checks": checks, "reasons": reasons}


def profile_is_verified(profile: dict) -> bool:
    return profile.get("profile_verified") is True and bool(profile.get("verified_at"))
