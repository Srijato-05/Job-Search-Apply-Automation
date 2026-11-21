"""Indian location filtering and normalization for direct ATS feeds."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

_LOCATIONS_FILE = Path(__file__).resolve().parents[1] / "data" / "india_locations.json"

_CITY_ALIASES: dict[str, list[str]] = {}
_ALL_INDIA_PATTERNS: list[re.Pattern[str]] = []
_FOREIGN_COUNTRY_RE = re.compile(
    r"\b(united states|usa|united kingdom|london|canada|germany|berlin|poland|"
    r"singapore|australia|sydney|melbourne|france|paris|netherlands|amsterdam|"
    r"ireland|dublin|japan|tokyo|brazil|mexico|israel|tel aviv|spain|madrid|barcelona|"
    r"switzerland|zurich|austria|vienna|sweden|stockholm)\b",
    re.IGNORECASE,
)


def _load_locations() -> None:
    global _CITY_ALIASES, _ALL_INDIA_PATTERNS
    if _CITY_ALIASES:
        return
    if _LOCATIONS_FILE.exists():
        data = json.loads(_LOCATIONS_FILE.read_text(encoding="utf-8"))
        _CITY_ALIASES = data.get("city_aliases", {})
    else:
        _CITY_ALIASES = {
            "Bengaluru": ["bengaluru", "bangalore", "blr"],
            "Hyderabad": ["hyderabad", "hyd"],
            "Pune": ["pune"],
            "Gurugram": ["gurugram", "gurgaon"],
            "Noida": ["noida"],
            "Mumbai": ["mumbai"],
            "Chennai": ["chennai"],
            "Delhi NCR": ["delhi", "delhi ncr", "new delhi"],
        }

    patterns: list[re.Pattern[str]] = []
    # Match explicitly "India" or "IN"
    patterns.append(re.compile(r"\bindia\b", re.IGNORECASE))
    patterns.append(re.compile(r"\b(in)\b", re.IGNORECASE))

    # Match all city aliases
    for canonical_city, aliases in _CITY_ALIASES.items():
        escaped = [re.escape(a) for a in aliases]
        pattern = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(escaped) + r")(?![A-Za-z0-9])", re.IGNORECASE)
        patterns.append(pattern)

    _ALL_INDIA_PATTERNS = patterns


def is_india_location(location_str: str) -> tuple[bool, str]:
    """Determine if a job location belongs to India, returning (is_india, normalized_city).

    If the string mentions a foreign country/city without India, returns (False, '').
    If it mentions India or an Indian tech city, returns (True, matched_canonical_city).
    """
    if not location_str or not location_str.strip():
        return False, ""

    text = location_str.strip()
    _load_locations()

    # If foreign country is prominently mentioned AND 'india' is NOT in text
    has_foreign = bool(_FOREIGN_FOREIGN_MATCH(text))
    has_india_keyword = bool(re.search(r"\b(india|in)\b", text, re.IGNORECASE))

    # Search for canonical city matches
    matched_city: Optional[str] = None
    for canonical, aliases in _CITY_ALIASES.items():
        for alias in aliases:
            # Word-bounded search
            alias_pattern = r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])"
            if re.search(alias_pattern, text, re.IGNORECASE):
                matched_city = canonical
                break
        if matched_city:
            break

    if matched_city:
        # Recognized Indian city
        return True, matched_city

    if has_india_keyword and not has_foreign:
        return True, "India (Any)"

    if has_foreign and not has_india_keyword:
        return False, ""

    return False, ""


def _FOREIGN_FOREIGN_MATCH(text: str) -> bool:
    return bool(_FOREIGN_COUNTRY_RE.search(text))

