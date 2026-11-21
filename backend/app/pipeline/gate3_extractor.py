"""Gate 3A: Boilerplate stripping and 10-field deterministic JD signal extraction."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.vault.taxonomy import (
    extract_office_locality,
    extract_skills_from_text,
    normalize_city,
)

# --- HTML Cleaning & Boilerplate Section Stripping ---

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_BREAK_RE = re.compile(r"</?(?:p|div|section|article|h[1-6]|tr|br)\b[^>]*>", re.I)
_LI_OPEN_RE = re.compile(r"<li\b[^>]*>", re.I)
_LI_CLOSE_RE = re.compile(r"</li>", re.I)

_BOILERPLATE_HEADER_RE = re.compile(
    r"^(?:#{1,6}\s*)?(?:"
    r"about\s+(?:us|the\s+company|our\s+company|[a-z0-9&.\-\s]{2,40})|"
    r"who\s+we\s+are|our\s+(?:story|mission|vision|values|culture)|"
    r"life\s+at\s+[a-z0-9&.\-\s]{2,40}|"
    r"why\s+(?:join\s+us|work\s+(?:with|at)\s+[a-z0-9&.\-\s]{2,40})|"
    r"(?:benefits|perks)(?:\s*(?:&|and)\s*(?:perks|benefits|compensation))?|"
    r"what\s+we\s+offer|"
    r"equal\s+opportunity(?:\s+employer)?|diversity\s*(?:&|and)\s*inclusion|"
    r"eeo\s+statement|accommodation\s+statement|how\s+to\s+apply"
    r")\s*:?$",
    re.I,
)

_KEEP_HEADER_RE = re.compile(
    r"^(?:#{1,6}\s*)?(?:"
    r"(?:about\s+the\s+role|the\s+role|role\s+overview|job\s+(?:description|summary))|"
    r"(?:key\s+)?responsibilities|what\s+you(?:'ll|\s+will)\s+(?:do|build|own)|"
    r"(?:minimum\s+|basic\s+|required\s+|preferred\s+)?(?:requirements|qualifications)|"
    r"what\s+(?:we(?:'re|\s+are)\s+looking\s+for|you\s+bring)|"
    r"(?:required\s+|technical\s+|core\s+|must[- ]have\s+)?skills(?:\s*(?:&|and)\s*experience)?|"
    r"(?:nice\s+to\s+have|good\s+to\s+have|bonus\s+(?:points|skills)|preferred\s+skills)|"
    r"tech\s+stack|experience"
    r")\s*:?$",
    re.I,
)

_BONUS_HEADER_RE = re.compile(
    r"^(?:#{1,6}\s*)?(?:nice\s+to\s+have|good\s+to\s+have|bonus(?:\s+(?:points|skills))?|preferred(?:\s+(?:qualifications|skills))?|plus)\s*:?$",
    re.I,
)

_INLINE_BONUS_PREFIX_RE = re.compile(
    r"^(?:nice\s+to\s+have|good\s+to\s+have|bonus|preferred|plus)\s*[:\-]\s*",
    re.I,
)

_EEO_SENTENCE_RE = re.compile(
    r"(?:is\s+an\s+equal\s+opportunity\s+employer|without\s+regard\s+to\s+race,?\s+color,?\s+religion|"
    r"proud\s+to\s+be\s+an\s+equal\s+opportunity|celebrating\s+diversity)",
    re.I,
)

_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[•●▪▫◦‣⁃\-–—*]|\d+[.)])\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")

# --- Regex Extractors ---

_EXP_RANGE_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
    re.I,
)
_EXP_MIN_RE = re.compile(
    r"(?:(?:minimum|at\s+least|min\.?)\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b|"
    r"\b(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)\b)",
    re.I,
)

_SALARY_RANGE_RE = re.compile(
    r"(?:INR|Rs\.?|₹)?\s*(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(?:LPA|Lakhs?\s*(?:p\.?a\.?|per\s*annum)?)\b",
    re.I,
)
_SALARY_SINGLE_RE = re.compile(
    r"(?:up\s*to\s*)?(?:INR|Rs\.?|₹)?\s*(\d+(?:\.\d+)?)\s*(?:LPA|Lakhs?\s*(?:p\.?a\.?|per\s*annum))\b",
    re.I,
)

_NOTICE_IMMEDIATE_RE = re.compile(r"\b(?:immediate\s+joiner|join\s+immediately|0\s*days?\s*notice)\b", re.I)
_NOTICE_DAYS_RE = re.compile(
    r"(?:(?:max(?:imum)?|up\s*to|within|less\s*than|<=)\s*(\d+)\s*days?\s*(?:notice)?|"
    r"notice\s*(?:period)?\s*(?:of|:)?\s*(?:max(?:imum)?|up\s*to)?\s*(\d+)\s*days?)",
    re.I,
)

_REQ_ID_URL_RE = re.compile(r"(?:gh_jid|req_id|requisition_id|jobId)=([A-Za-z0-9_-]{4,})", re.I)
_REQ_ID_JR_RE = re.compile(r"(?<![A-Za-z0-9])(JR[-_]?\d{3,})(?![A-Za-z0-9])", re.I)
_REQ_ID_TEXT_RE = re.compile(
    r"\b(?:Req(?:uisition)?\s*(?:ID|No|#)?\s*[:#-]\s*)([A-Za-z0-9_-]{3,})\b",
    re.I,
)

_COMPANY_LEGAL_SUFFIX_RE = re.compile(
    r"(?:,?\s+(?:pvt\.?\s*ltd\.?|private\s+limited|limited|ltd\.?|inc\.?|llc|corp\.?|corporation|"
    r"technologies|technology|solutions|software|systems|india))+\s*$",
    re.I,
)

_STAFFING_AGENCY_RE = re.compile(
    r"(?:hiring\s+for\s+(?:a|an|one\s+of)\s+(?:leading|top|reputed|renowned)|"
    r"for\s+our\s+(?:esteemed\s+)?client|confidential\s+client|"
    r"leading\s+(?:product\s+)?mnc\s+client|"
    r"\b(?:staffing|consultancy|recruitment\s+services|manpower|talent\s+solutions)\b)",
    re.I,
)

_RULES_DATA = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "pipeline_rules.json").read_text(encoding="utf-8")
)

_IT_SERVICE_COMPANIES: frozenset[str] = frozenset(_RULES_DATA["it_service_companies"])

_DOMAIN_CUES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.I))
    for label, pattern in _RULES_DATA["domain_cues"].items()
)

_SPECIFIC_TEAM_DOMAINS: frozenset[str] = frozenset(_RULES_DATA["specific_team_domains"])

_DOMAIN_SKILL_MAP: dict[str, frozenset[str]] = {
    label: frozenset(skills)
    for label, skills in _RULES_DATA["domain_skill_map"].items()
}

_BACKEND_FALLBACK_SKILLS: frozenset[str] = frozenset(_RULES_DATA["backend_fallback_skills"])
_ENTERPRISE_ATS_DOMAINS: tuple[str, ...] = tuple(_RULES_DATA["enterprise_ats_domains"])
_FAST_APPLY_DOMAINS: tuple[str, ...] = tuple(_RULES_DATA["fast_apply_domains"])


@dataclass
class ExtractedJobSignals:
    """Complete 10-field deterministic extraction result for a collected job."""

    raw_title: str
    normalized_title: str
    company_name: str
    company_slug: str
    boilerplate_stripped_text: str
    requirement_lines: list[str] = field(default_factory=list)
    primary_skills: list[str] = field(default_factory=list)
    secondary_skills: list[str] = field(default_factory=list)
    exp_min_years: Optional[float] = None
    exp_max_years: Optional[float] = None
    salary_min_lpa: Optional[float] = None
    salary_max_lpa: Optional[float] = None
    normalized_city: str = ""
    office_locality: str = ""
    work_mode: str = "unknown"
    max_notice_days: Optional[int] = None
    req_id: Optional[str] = None
    role_subtag: str = ""
    apply_friction: str = "unknown"
    employer_type: str = "direct_product"


def html_to_clean_text(raw_text: str) -> str:
    """Convert HTML job descriptions to clean newline-preserving plain text."""
    text = raw_text or ""
    if "<" in text and ">" in text:
        text = _LI_OPEN_RE.sub("\n• ", text)
        text = _LI_CLOSE_RE.sub("\n", text)
        text = _BLOCK_BREAK_RE.sub("\n", text)
        text = _HTML_TAG_RE.sub(" ", text)
        text = html.unescape(text)

    cleaned_lines: list[str] = []
    for line in text.splitlines():
        normalized = " ".join(line.split())
        if normalized:
            cleaned_lines.append(normalized)
    return "\n".join(cleaned_lines)


def strip_boilerplate(raw_text: str) -> str:
    """Strip corporate About Us / Perks / EEO sections before similarity or scoring."""
    plain = html_to_clean_text(raw_text)
    if not plain:
        return ""

    kept_lines: list[str] = []
    in_boilerplate = False

    for line in plain.splitlines():
        stripped = line.strip()
        if len(stripped) <= 85:
            if _KEEP_HEADER_RE.match(stripped):
                in_boilerplate = False
                kept_lines.append(stripped)
                continue
            if _BOILERPLATE_HEADER_RE.match(stripped):
                in_boilerplate = True
                continue

        if in_boilerplate:
            continue
        if _EEO_SENTENCE_RE.search(stripped):
            continue
        kept_lines.append(stripped)

    result = "\n".join(kept_lines).strip()
    if result:
        return result

    # Fallback: keep original minus explicit EEO boilerplate sentences
    fallback = [ln for ln in plain.splitlines() if not _EEO_SENTENCE_RE.search(ln)]
    return "\n".join(fallback).strip()


def extract_requirement_lines(clean_text: str) -> list[str]:
    """Extract deduplicated atomic requirement/responsibility sentences for Option 3 & Diff."""
    if not clean_text.strip():
        return []

    seen: set[str] = set()
    lines_out: list[str] = []

    for raw_line in clean_text.splitlines():
        line = _BULLET_PREFIX_RE.sub("", raw_line.strip()).strip()
        if not line:
            continue
        if len(line) < 40 and (_KEEP_HEADER_RE.match(line) or line.endswith(":")):
            continue

        candidates = [line] if len(line) <= 220 else _SENTENCE_SPLIT_RE.split(line)
        for cand in candidates:
            normalized = " ".join(cand.split()).strip()
            if 15 <= len(normalized) <= 300:
                key = normalized.lower()
                if key not in seen:
                    seen.add(key)
                    lines_out.append(normalized)

    return lines_out


def normalize_job_title(title: str) -> str:
    """Normalize role titles across portals (e.g., SDE-II == SDE 2)."""
    lowered = title.lower().strip()
    lowered = re.sub(r"\bsr\.?\b", "senior", lowered)
    lowered = re.sub(r"\bjr\.?\b", "junior", lowered)
    lowered = re.sub(r"\biv\b", "4", lowered)
    lowered = re.sub(r"\biii\b", "3", lowered)
    lowered = re.sub(r"\bii\b", "2", lowered)
    lowered = re.sub(r"[^a-z0-9\s]+", " ", lowered)
    return " ".join(lowered.split())


def slugify_company(company_name: str) -> str:
    """Normalize company display name into a stable slug without legal suffixes."""
    cleaned = " ".join(company_name.strip().split())
    cleaned = _COMPANY_LEGAL_SUFFIX_RE.sub("", cleaned).strip()
    slug = re.sub(r"[^a-z0-9]+", "-", cleaned.lower()).strip("-")
    return slug or "unknown-company"


def _split_mandatory_vs_bonus_skills(title: str, clean_text: str) -> tuple[list[str], list[str]]:
    mandatory_lines: list[str] = [title]
    bonus_lines: list[str] = []
    in_bonus = False

    for line in clean_text.splitlines():
        stripped = line.strip()
        if len(stripped) <= 85:
            if _BONUS_HEADER_RE.match(stripped):
                in_bonus = True
                continue
            if _KEEP_HEADER_RE.match(stripped):
                in_bonus = False
                continue

        if _INLINE_BONUS_PREFIX_RE.match(stripped):
            bonus_lines.append(stripped)
        elif in_bonus:
            bonus_lines.append(stripped)
        else:
            mandatory_lines.append(stripped)

    primary = extract_skills_from_text("\n".join(mandatory_lines))
    primary_set = set(primary)
    bonus_candidates = extract_skills_from_text("\n".join(bonus_lines))
    secondary = [s for s in bonus_candidates if s not in primary_set]
    return primary, secondary


def _extract_experience_band(
    clean_text: str,
    meta: dict[str, Any],
) -> tuple[Optional[float], Optional[float]]:
    if meta.get("exp_min_years") is not None or meta.get("exp_max_years") is not None:
        exp_min = float(meta["exp_min_years"]) if meta.get("exp_min_years") is not None else None
        exp_max = float(meta["exp_max_years"]) if meta.get("exp_max_years") is not None else None
        return exp_min, exp_max

    match_range = _EXP_RANGE_RE.search(clean_text)
    if match_range:
        low, high = float(match_range.group(1)), float(match_range.group(2))
        if low <= high <= 40:
            return low, high

    match_min = _EXP_MIN_RE.search(clean_text)
    if match_min:
        val_str = match_min.group(1) or match_min.group(2)
        if val_str:
            val = float(val_str)
            if val <= 40:
                return val, None

    return None, None


def _extract_salary_lpa(
    clean_text: str,
    meta: dict[str, Any],
) -> tuple[Optional[float], Optional[float]]:
    if meta.get("salary_min_lpa") is not None or meta.get("salary_max_lpa") is not None:
        s_min = float(meta["salary_min_lpa"]) if meta.get("salary_min_lpa") is not None else None
        s_max = float(meta["salary_max_lpa"]) if meta.get("salary_max_lpa") is not None else None
        return s_min, s_max

    match_range = _SALARY_RANGE_RE.search(clean_text)
    if match_range:
        low, high = float(match_range.group(1)), float(match_range.group(2))
        if low <= high:
            return low, high

    match_single = _SALARY_SINGLE_RE.search(clean_text)
    if match_single:
        val = float(match_single.group(1))
        return None, val

    return None, None


def _extract_work_mode(text: str, location_raw: str) -> str:
    combined = f"{location_raw}\n{text}"
    if re.search(r"\bhybrid\b", combined, re.I):
        return "hybrid"
    if re.search(r"\b(?:remote|work\s+from\s+home|wfh)\b", combined, re.I):
        return "remote"
    if re.search(r"\b(?:on-?site|in-?office|work\s+from\s+office|wfo)\b", combined, re.I):
        return "onsite"
    return "unknown"


def _extract_max_notice_days(clean_text: str) -> Optional[int]:
    if _NOTICE_IMMEDIATE_RE.search(clean_text):
        return 0
    match = _NOTICE_DAYS_RE.search(clean_text)
    if match:
        val = match.group(1) or match.group(2)
        if val:
            return int(val)
    return None


def _extract_req_id(job_url: str, apply_url: str, raw_text: str) -> Optional[str]:
    for target in (apply_url, job_url):
        if target:
            m_url = _REQ_ID_URL_RE.search(target)
            if m_url:
                return m_url.group(1).upper()
            m_jr = _REQ_ID_JR_RE.search(target)
            if m_jr:
                return m_jr.group(1).upper()

    m_jr_text = _REQ_ID_JR_RE.search(raw_text)
    if m_jr_text:
        return m_jr_text.group(1).upper()
    m_txt = _REQ_ID_TEXT_RE.search(raw_text)
    if m_txt:
        return m_txt.group(1).upper()
    return None


def _build_role_subtag(clean_text: str, title: str, primary_skills: list[str]) -> str:
    domain = "Engineering"
    combined = f"{title}\n{clean_text}"
    skill_set = set(primary_skills)
    best_score = 0

    for label, pattern in _DOMAIN_CUES:
        text_hits = len(pattern.findall(combined))
        skill_hits = len(skill_set & _DOMAIN_SKILL_MAP.get(label, frozenset()))
        text_weight = 3 if label in _SPECIFIC_TEAM_DOMAINS else 2
        score = text_hits * text_weight + skill_hits
        if score > best_score:
            best_score = score
            domain = label

    if domain == "Engineering" and (skill_set & _BACKEND_FALLBACK_SKILLS):
        domain = "Backend"

    top_skills = primary_skills[:3]
    if top_skills:
        return f"{domain} • {' / '.join(top_skills)}"
    return domain


def _classify_apply_friction(portal_name: str, job_url: str, apply_url: str, meta: dict[str, Any]) -> str:
    dest = f"{portal_name} {job_url} {apply_url}".lower()
    if any(k in dest for k in _ENTERPRISE_ATS_DOMAINS):
        return "enterprise_ats"
    if meta.get("easy_apply") is True:
        return "fast_apply"
    if any(k in dest for k in _FAST_APPLY_DOMAINS):
        return "fast_apply"
    if "linkedin" in dest:
        return "enterprise_ats" if apply_url and "linkedin.com" not in apply_url.lower() else "fast_apply"
    return "unknown"


def _classify_employer_type(company_name: str, raw_text: str) -> str:
    lowered_company = company_name.strip().lower()
    if _STAFFING_AGENCY_RE.search(f"{company_name}\n{raw_text}"):
        return "staffing_agency"
    if any(svc in lowered_company for svc in _IT_SERVICE_COMPANIES):
        return "direct_service"
    return "direct_product"


def extract_job_signals(
    title: str,
    company_name: str,
    raw_description: str,
    location_raw: str = "",
    job_url: str = "",
    apply_url: str = "",
    portal_name: str = "",
    portal_metadata: Optional[dict[str, Any]] = None,
) -> ExtractedJobSignals:
    """Deterministically extract all 10 high-signal fields from a raw job posting."""
    meta = portal_metadata or {}
    clean_text = strip_boilerplate(raw_description)
    req_lines = extract_requirement_lines(clean_text)
    primary_skills, secondary_skills = _split_mandatory_vs_bonus_skills(title, clean_text)
    exp_min, exp_max = _extract_experience_band(clean_text, meta)
    sal_min, sal_max = _extract_salary_lpa(clean_text, meta)

    norm_city = normalize_city(location_raw)
    if not norm_city:
        norm_city = normalize_city(clean_text[:500])
    locality = extract_office_locality(f"{location_raw}\n{clean_text}")
    work_mode = _extract_work_mode(clean_text, location_raw)
    max_notice = _extract_max_notice_days(clean_text)
    req_id = _extract_req_id(job_url, apply_url, raw_description)
    subtag = _build_role_subtag(clean_text, title, primary_skills)
    friction = _classify_apply_friction(portal_name, job_url, apply_url, meta)
    emp_type = _classify_employer_type(company_name, raw_description)

    comp_slug = str(meta.get("company_slug") or "").strip().lower() or slugify_company(company_name)

    return ExtractedJobSignals(
        raw_title=title.strip(),
        normalized_title=normalize_job_title(title),
        company_name=company_name.strip(),
        company_slug=comp_slug,
        boilerplate_stripped_text=clean_text,
        requirement_lines=req_lines,
        primary_skills=primary_skills,
        secondary_skills=secondary_skills,
        exp_min_years=exp_min,
        exp_max_years=exp_max,
        salary_min_lpa=sal_min,
        salary_max_lpa=sal_max,
        normalized_city=norm_city,
        office_locality=locality,
        work_mode=work_mode,
        max_notice_days=max_notice,
        req_id=req_id,
        role_subtag=subtag,
        apply_friction=friction,
        employer_type=emp_type,
    )

