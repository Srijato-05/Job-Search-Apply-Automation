"""Deterministic pre-approved cover-note template renderer."""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

ALLOWED_TEMPLATE_VARIABLES: frozenset[str] = frozenset(
    {
        "company",
        "role_title",
        "matched_top_3_skills",
        "total_exp_years",
        "notice_period_days",
        "current_city",
    }
)


def render_cover_template(template: str, variables: dict[str, Any]) -> dict[str, Any]:
    """Substitute strictly whitelisted placeholders without fabricating missing fields."""
    unresolved: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in ALLOWED_TEMPLATE_VARIABLES:
            if key not in unresolved:
                unresolved.append(key)
            return match.group(0)
        raw_val = variables.get(key)
        if raw_val is None or str(raw_val).strip() == "":
            if key not in unresolved:
                unresolved.append(key)
            return match.group(0)
        return str(raw_val).strip()

    rendered = _PLACEHOLDER_PATTERN.sub(_replace, template)
    return {
        "rendered": rendered,
        "unresolved_placeholders": unresolved,
    }

