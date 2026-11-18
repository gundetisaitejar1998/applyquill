"""Safe Playwright form preparation for public application pages.

Submission is deliberately gated twice: the process must explicitly enable it,
and each run must opt in. Development and test environments default to dry-run.
"""
import asyncio
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", str(Path(__file__).resolve().parents[3]))).resolve()
PROFILE_ROOT = STORAGE_ROOT / "browser-profiles"
ALLOW_SUBMISSIONS = os.getenv("ALLOW_REAL_SUBMISSIONS", "false").lower() in {"1", "true", "yes"}
BLOCKERS = re.compile(r"captcha|recaptcha|hcaptcha|one-time password|\botp\b|two-factor|\bmfa\b|verify your identity", re.I)
CONFIRMATION = re.compile(r"application (?:has been )?(?:submitted|received)|thank you for applying|successfully applied|we.ve received your application", re.I)


def ats_for_url(url: str) -> str:
    host = (url.split("/", 3)[2] if "://" in url else "").lower()
    if host.endswith("greenhouse.io") or "greenhouse" in host:
        return "greenhouse"
    if host.endswith("lever.co") or "lever" in host:
        return "lever"
    return "generic"


async def prepare_application(url: str, profile: dict, resume_path: str = "", *, submit: bool = False,
                              candidate_id: int = 0, run_id: int = 0, timeout_ms: int = 30000,
                              submission_guard=None) -> dict:
    """Inspect/fill known fields; never answer unknown questions or bypass challenges."""
    parsed=urlparse(url)
    if parsed.scheme!="https" and not (parsed.scheme=="http" and parsed.hostname in {"127.0.0.1","localhost"}):
        return {"status": "skipped", "reason": "Only public HTTPS pages or loopback test forms are supported."}
    profile_dir = PROFILE_ROOT / f"candidate-{candidate_id}"
    profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        profile_dir.chmod(0o700)
    except OSError:
        pass
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(profile_dir), headless=True,
                   timeout=timeout_ms, accept_downloads=False)
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if response and response.status >= 400:
                return {"status": "failed", "reason": f"Application page returned HTTP {response.status}."}
            await page.wait_for_timeout(500)
            body = await page.locator("body").inner_text(timeout=5000)
            if BLOCKERS.search(body):
                return {"status": "verification_required", "reason": "A CAPTCHA, identity check, OTP, or MFA challenge is present."}
            ats = ats_for_url(page.url)
            fields = page.locator("input:not([type=hidden]), textarea, select")
            filled, unknown, detected = [], [], []
            values = {"name": profile.get("name"), "email": profile.get("email"), "phone": profile.get("phone"),
                      "location": profile.get("location"), "linkedin": profile.get("linkedin_url"),
                      "portfolio": profile.get("portfolio_url")}
            verified_answers={re.sub(r"[^a-z0-9]+"," ",str(k).lower()).strip():v for k,v in (profile.get("verified_screening_answers") or {}).items() if v not in (None,"")}
            for i in range(await fields.count()):
                field = fields.nth(i)
                if not await field.is_visible():
                    continue
                typ = (await field.get_attribute("type") or "text").lower()
                field_id=await field.get_attribute("id")
                associated=""
                if field_id:
                    try:associated=await page.locator(f'label[for="{field_id}"]').inner_text(timeout=500)
                    except Exception:pass
                if not associated:
                    try:associated=await field.locator("xpath=ancestor::label").first.inner_text(timeout=500)
                    except Exception:pass
                label = " ".join(filter(None, [associated,await field.get_attribute("name"), field_id,
                    await field.get_attribute("placeholder"), await field.get_attribute("aria-label"),
                    await field.get_attribute("autocomplete")])).lower()
                detected.append({"type": typ, "label": label[:120]})
                if typ == "file":
                    if resume_path and Path(resume_path).is_file():
                        await field.set_input_files(resume_path)
                        filled.append("resume")
                    else:
                        unknown.append("resume upload")
                    continue
                normalized_label=re.sub(r"[^a-z0-9]+"," ",label).strip()
                answer=next((v for k,v in verified_answers.items() if k==normalized_label or (len(k)>4 and k in normalized_label)),None)
                if typ in {"checkbox", "radio"}:
                    mandatory=await field.get_attribute("required") is not None
                    if answer is not None:
                        wanted=str(answer).strip().lower() in {"true","yes","1","agree","accept"}
                        if wanted and not await field.is_checked():await field.check()
                        if not wanted and await field.is_checked():await field.uncheck()
                        filled.append("verified answer")
                    elif mandatory or re.search(r"sponsor|authorized|work eligibility|consent|privacy|terms|gender|disability|veteran|ethnicity|race",label,re.I):
                        unknown.append(label or "unlabeled required choice")
                    continue
                if typ=="select-one" or await field.evaluate("el => el.tagName.toLowerCase()") == "select":
                    if answer is not None:
                        options=await field.locator("option").all_text_contents()
                        match=next((x for x in options if str(answer).strip().lower()==x.strip().lower()),None)
                        if match:await field.select_option(label=match);filled.append("verified answer")
                        elif await field.get_attribute("required"):unknown.append(label or "required dropdown")
                    elif await field.get_attribute("required"):unknown.append(label or "required dropdown")
                    continue
                target = next((key for key in values if values[key] and key in label), None)
                if target:
                    await field.fill(str(values[target]))
                    filled.append(target)
                elif answer is not None and typ in {"text","email","tel","url","textarea"}:
                    await field.fill(str(answer));filled.append("verified answer")
                elif (await field.get_attribute("required") is not None or re.search(r"sponsor|authorized|work eligibility|salary expectation|notice period|relocat|legally|visa",label,re.I)):
                    unknown.append(label or "unlabeled required field")
            # Native ATS adapters are identifiable for diagnostics; shared field labels remain the selector source.
            if submit and not ALLOW_SUBMISSIONS:
                return {"status": "prepared", "reason": "Submission is disabled by ALLOW_REAL_SUBMISSIONS.", "ats": ats,
                        "filled": filled, "unknown_fields": unknown, "fields": detected}
            if submit:
                allowed={x.strip().lower() for x in os.getenv("AUTOMATION_ALLOWED_HOSTS","").split(",") if x.strip()}
                host=(urlparse(page.url).hostname or "").lower()
                if not any(host==x or host.endswith("."+x) for x in allowed):
                    return {"status":"requires_review","reason":"This host is not explicitly allow-listed for automated applications.","ats":ats,"filled":filled,"unknown_fields":unknown,"fields":detected}
                if unknown:
                    return {"status":"requires_review","reason":"Required or unlabeled form fields remain unanswered; no application was submitted.","ats":ats,"filled":filled,"unknown_fields":unknown,"fields":detected}
                invalid_count=await page.locator(":invalid").count()
                if invalid_count:
                    return {"status":"requires_review","reason":f"The form has {invalid_count} invalid or incomplete controls; no application was submitted.","ats":ats,"filled":filled,"unknown_fields":unknown,"fields":detected}
                if submission_guard and not await submission_guard():
                    return {"status":"stopped","reason":"Emergency STOP was requested before submission.","ats":ats,"filled":filled,"unknown_fields":unknown,"fields":detected}
                button=page.get_by_role("button",name=re.compile(r"submit|apply",re.I)).last
                if await button.count()==0:
                    return {"status":"requires_review","reason":"No accessible submit control was identified.","ats":ats,"filled":filled,"unknown_fields":unknown,"fields":detected}
                before=page.url
                await button.click(timeout=5000)
                try:await page.wait_for_load_state("domcontentloaded",timeout=5000)
                except Exception:pass
                await page.wait_for_timeout(700)
                confirmation=await page.locator("body").inner_text(timeout=5000)
                if CONFIRMATION.search(confirmation):
                    return {"status":"confirmed","reason":"The application page displayed a submission confirmation.","ats":ats,"filled":filled,"unknown_fields":unknown,"fields":detected,"confirmation":CONFIRMATION.search(confirmation).group(0),"confirmation_url":page.url}
                return {"status":"submission_unconfirmed","reason":"Submit control was activated, but no recognized confirmation appeared; verify manually and do not retry automatically.","ats":ats,"filled":filled,"unknown_fields":unknown,"fields":detected,"confirmation_url":page.url,"url_changed":page.url!=before}
            return {"status": "prepared", "reason": "Form inspected and known profile fields filled; dry-run mode is active.",
                    "ats": ats, "filled": filled, "unknown_fields": unknown, "fields": detected}
        except Exception as exc:
            if os.getenv("CAPTURE_AUTOMATION_SCREENSHOTS","false").lower() in {"1","true","yes"}:
                diagnostics=PROFILE_ROOT/"diagnostics";diagnostics.mkdir(parents=True,exist_ok=True)
                try:
                    diagnostics.chmod(0o700)
                    await page.screenshot(path=str(diagnostics/f"candidate-{candidate_id}-run-{run_id}-error.png"),full_page=True)
                except Exception:pass
            return {"status": "failed", "reason": f"Browser navigation or form detection failed ({type(exc).__name__})."}
        finally:
            await context.close()
