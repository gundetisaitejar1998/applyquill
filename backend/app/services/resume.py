import re
from pathlib import Path
from pypdf import PdfReader
from docx import Document

MAX_BYTES = 10 * 1024 * 1024
HEADERS = {
    "summary": r"(?:professional\s+)?summary|profile|objective",
    "skills": r"core\s+competencies|technical\s+skills|skills|tools\s*(?:and|&)\s*technologies|professional\s+skills",
    "experience": r"(?:professional\s+)?(?:experience|employment\s+history|career\s+history|work\s+history)",
    "education": r"education|academic\s+(?:background|qualifications?)|qualifications?",
    "certifications": r"certifications?|licenses?",
    "achievements": r"achievements?|awards(?:\s+and\s+recognition)?|accomplishments?",
    "portfolio": r"portfolio|links|references",
}
HEADER_RE = re.compile(r"^(?:" + "|".join(f"(?P<{key}>{pattern})" for key, pattern in HEADERS.items()) + r")\s*:?\s*$", re.I)


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if path.suffix.lower() == ".docx":
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError("Only PDF and DOCX resumes are supported")


def _skills_from(lines):
    skills = []
    for line in lines:
        clean = re.sub(r"^[^:]{2,60}:\s*", "", line)
        for item in re.split(r",|;|\s+\|\s+", clean):
            item = item.strip(" •●\t.-")
            if item and len(item) <= 90 and item.lower() not in {x.lower() for x in skills}:
                skills.append(item)
    return skills[:100]


def parse_resume(text: str, filename: str) -> dict:
    lines = [re.sub(r"\s+", " ", line).strip(" •●\t") for line in text.splitlines()]
    lines = [re.sub(r"^[●•▪◦]+\s*", "", line).strip() for line in lines]
    lines = [x for x in lines if x]
    email = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    phone = re.search(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)", text)

    name = next((x for x in lines[:8] if len(x) < 70 and "@" not in x and not re.search(r"\d{4,}", x)
                 and not re.search(r"resume|curriculum vitae|profile|phone|email", x, re.I)), "")
    headline = next((x.strip(" |") for x in lines[1:9] if "|" in x and "@" not in x and not re.search(r"linkedin|behance|\d{5,}", x, re.I)), "")
    phone_value = phone.group(0).strip() if phone else ""
    email_value = email.group(0) if email else ""
    location_line = next((x for x in lines[:14] if re.search(r"\b(India|United States|UK|Hyderabad|Bengaluru|Bangalore|Mumbai|Delhi|Chennai|Pune)\b", x, re.I)), "")
    location = location_line.split("|")[0].strip() if location_line else ""

    sections = {key: [] for key in HEADERS}
    active = None
    for line in lines:
        match = HEADER_RE.fullmatch(line)
        if match:
            active = next((key for key in HEADERS if match.group(key)), None)
            continue
        if active and active != "portfolio" and len(sections[active]) < 100:
            sections[active].append(line[:800])

    summary_text = " ".join(sections["summary"]).strip()
    # Resume headline is retained separately; a missing summary remains unknown.
    if not summary_text and headline:
        summary_text = ""
    skills = _skills_from(sections["skills"])
    experience = sections["experience"]
    role_titles=[]
    for index,line in enumerate(experience[:-1]):
        next_line=experience[index+1]
        looks_like_title=(len(line)<=100 and not re.search(r"[,;|@]|\b(?:19|20)\d\d\b|[.!?]$",line))
        looks_like_employer=(bool(re.search(r",|\b(?:19|20)\d\d\b|self[- ]employed|limited|inc\.?|llc|ltd\.?",next_line,re.I)))
        if looks_like_title and looks_like_employer and line.lower() not in {x.lower() for x in role_titles}:
            role_titles.append(line)
    education = sections["education"]
    achievements = sections["achievements"]
    experience_years = None
    year_match = re.search(r"\b(\d{1,2}\+?)\s+years?\b", text, re.I)
    if year_match:
        experience_years = year_match.group(1)
    languages = []
    language_section = next((value for key, value in sections.items() if key == "languages"), [])
    languages.extend(language_section)

    return {
        "name": name, "email": email_value, "phone": phone_value, "location": location,
        "headline": headline, "summary": summary_text,
        "experience": experience, "experience_years": experience_years,
        "role_titles": role_titles,
        "education": education, "skills": skills,
        "certifications": sections["certifications"], "achievements": achievements,
        "languages": languages, "source_filename": filename,
        "extraction_note": "Extracted resume text is preserved by section. Verify dates, titles, and parsed skills before using application documents.",
    }
