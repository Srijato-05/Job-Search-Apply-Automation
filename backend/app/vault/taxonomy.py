"""Canonical Indian city/hub normalizer and tech skill taxonomy loaded from JSON data."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load_json(filename: str) -> dict:
    path = _DATA_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


# --- Indian Cities & Tech Corridors ---

_LOCATIONS_DATA = _load_json("india_locations.json")

CITY_CANONICAL_MAP: dict[str, tuple[str, ...]] = {
    city: tuple(aliases) for city, aliases in _LOCATIONS_DATA["city_aliases"].items()
}
OFFICE_LOCALITIES: tuple[str, ...] = tuple(_LOCATIONS_DATA["office_localities"])
_NCR_GROUP: frozenset[str] = frozenset(_LOCATIONS_DATA["ncr_group"])

_CITY_ALIAS_INDEX: list[tuple[str, re.Pattern[str]]] = []
for _canon_city, _aliases in CITY_CANONICAL_MAP.items():
    for _alias in sorted(_aliases, key=len, reverse=True):
        _CITY_ALIAS_INDEX.append(
            (_canon_city, re.compile(rf"(?<![A-Za-z0-9]){re.escape(_alias)}(?![A-Za-z0-9])", re.I))
        )

_LOCALITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (loc, re.compile(rf"(?<![A-Za-z0-9]){re.escape(loc)}(?![A-Za-z0-9])", re.I))
    for loc in OFFICE_LOCALITIES
]

_INDIA_COUNTRY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(india|in-\w+|remote\s*[-–/]\s*in)(?![A-Za-z0-9])|,\s*IN\b|\(IN\)",
    re.I,
)


def normalize_city(raw_location: str) -> str:
    """Normalize an Indian city, alias, or corridor string to its canonical city name."""
    cleaned = " ".join(raw_location.strip().split())
    if not cleaned:
        return ""
    for canon_city, pattern in _CITY_ALIAS_INDEX:
        if pattern.search(cleaned):
            return canon_city
    if cleaned.lower() == "remote":
        return "Remote"
    return cleaned


def extract_office_locality(text: str) -> str:
    """Extract a recognizable Indian tech hub / office corridor from location or JD text."""
    for locality, pattern in _LOCALITY_PATTERNS:
        if pattern.search(text):
            return locality
    return ""


def is_india_location(raw_location: str) -> bool:
    """Return True if the location string refers to an Indian hub, Remote-India, or India."""
    if not raw_location.strip():
        return False
    for _, pattern in _CITY_ALIAS_INDEX:
        if pattern.search(raw_location):
            return True
    return bool(_INDIA_COUNTRY_PATTERN.search(raw_location))


def cities_compatible(city_a: str, city_b: str) -> bool:
    """Return True when two normalized cities represent the same metro area (e.g., Delhi NCR)."""
    norm_a = normalize_city(city_a)
    norm_b = normalize_city(city_b)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    if "Remote (India)" in (norm_a, norm_b):
        return True
    if norm_a in _NCR_GROUP and norm_b in _NCR_GROUP:
        return True
    return False


# --- 500+ Entry Canonical Tech Skill Taxonomy ---

_SKILLS_DATA = _load_json("skills_taxonomy.json")

CORE_LANGUAGES: frozenset[str] = frozenset(_SKILLS_DATA["core_languages"])
SKILL_SYNONYM_GROUPS: dict[str, tuple[str, ...]] = {
    canon: tuple(aliases) for canon, aliases in _SKILLS_DATA["skill_synonym_groups"].items()
}
CANONICAL_SKILLS: tuple[str, ...] = tuple(SKILL_SYNONYM_GROUPS.keys())

SKILL_ALIASES: dict[str, str] = {}
for _canon, _aliases in SKILL_SYNONYM_GROUPS.items():
    SKILL_ALIASES[_canon.lower()] = _canon
    for _alias in _aliases:
        SKILL_ALIASES[_alias.lower()] = _canon

_STRICT_CASED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Go", re.compile(r"(?<![A-Za-z0-9_])Go(?![A-Za-z0-9_])")),
    ("C", re.compile(r"(?<![A-Za-z0-9_+.#-])C(?![A-Za-z0-9_+.#-])(?=\s*(?:,|/|lang\b|programming\b|and\s+C\+\+))")),
    ("R", re.compile(r"(?<![A-Za-z0-9_+.#-])R(?![A-Za-z0-9_+.#-])(?=\s*(?:,|/|programming\b|studio\b|and\s+Python))")),
)

_AMBIGUOUS_LOWERCASE: frozenset[str] = frozenset(_SKILLS_DATA["ambiguous_lowercase_aliases"])
_UPPERCASE_ONLY_SHORT: frozenset[str] = frozenset(_SKILLS_DATA["uppercase_only_short_aliases"])
_ALIAS_PATTERNS: list[tuple[str, re.Pattern[str]]] = []

for _alias_lower, _canon in sorted(SKILL_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
    if _alias_lower in {"go", "c", "r"}:
        continue
    flags = 0 if _alias_lower in _AMBIGUOUS_LOWERCASE else re.IGNORECASE
    token_for_regex = (
        _alias_lower.upper()
        if (_alias_lower in _AMBIGUOUS_LOWERCASE and len(_alias_lower) <= 3)
        else _alias_lower
    )
    if _alias_lower in _UPPERCASE_ONLY_SHORT:
        flags = 0
        token_for_regex = _alias_lower.upper()
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_]){re.escape(token_for_regex)}(?![A-Za-z0-9_])",
        flags,
    )
    _ALIAS_PATTERNS.append((_canon, pattern))


def normalize_skill(raw_skill: str) -> str:
    """Map any raw skill string or alias to its canonical skill name."""
    cleaned = " ".join(raw_skill.strip().split())
    if not cleaned:
        return ""
    found = SKILL_ALIASES.get(cleaned.lower())
    if found:
        return found
    return cleaned


def normalize_skill_list(raw_skills: Iterable[str]) -> list[str]:
    """Normalize and deduplicate a list of skills while preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in raw_skills:
        norm = normalize_skill(item)
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def extract_skills_from_text(text: str) -> list[str]:
    """Deterministically extract canonical tech skills from text without false positives."""
    if not text or not text.strip():
        return []

    found_order: list[str] = []
    seen: set[str] = set()

    for canon, pattern in _STRICT_CASED_PATTERNS:
        if canon not in seen and pattern.search(text):
            seen.add(canon)
            found_order.append(canon)

    for canon, pattern in _ALIAS_PATTERNS:
        if canon not in seen and pattern.search(text):
            seen.add(canon)
            found_order.append(canon)

    return found_order
