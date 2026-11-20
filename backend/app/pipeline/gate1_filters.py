"""Gate 1: Hard dealbreaker filters with non-destructive Hidden Audit Trail."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.db.models import FactVault
from app.pipeline.gate3_extractor import ExtractedJobSignals, slugify_company


@dataclass
class Gate1Result:
    """Outcome of deterministic dealbreaker checks."""

    hidden_by_gate1: bool
    hidden_reason: Optional[str]
    notice_compatible: bool


def effective_candidate_notice_days(vault: FactVault, today: Optional[date] = None) -> int:
    """Compute candidate's earliest realistic joining days from Fact Vault."""
    ref_today = today or date.today()
    if vault.serving_notice and vault.last_working_day is not None:
        return max(0, (vault.last_working_day - ref_today).days)
    if vault.notice_negotiable and vault.min_negotiable_days is not None:
        return max(0, min(vault.notice_period_days, vault.min_negotiable_days))
    return max(0, vault.notice_period_days)


def evaluate_gate1(
    signals: ExtractedJobSignals,
    vault: FactVault,
    company_blacklisted: bool = False,
    exp_buffer_years: float = 2.0,
) -> Gate1Result:
    """Evaluate hard dealbreakers without deleting records (stores exact hidden_reason)."""
    eff_notice = effective_candidate_notice_days(vault)
    notice_ok = True if signals.max_notice_days is None else (eff_notice <= signals.max_notice_days)

    # 1. Company Blacklist
    blacklist_norm = {item.strip().lower() for item in vault.company_blacklist_json if item.strip()}
    blacklist_slugs = {slugify_company(item) for item in vault.company_blacklist_json if item.strip()}
    if (
        company_blacklisted
        or signals.company_name.strip().lower() in blacklist_norm
        or signals.company_slug in blacklist_slugs
    ):
        return Gate1Result(
            hidden_by_gate1=True,
            hidden_reason=f"Blacklisted company: '{signals.company_name}'",
            notice_compatible=notice_ok,
        )

    # 2. Negative Title Keywords
    for raw_kw in vault.negative_keywords_json:
        kw = raw_kw.strip()
        if not kw:
            continue
        pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(kw)}(?![A-Za-z0-9])", re.I)
        if pattern.search(signals.raw_title):
            return Gate1Result(
                hidden_by_gate1=True,
                hidden_reason=f"Title matched negative keyword: '{kw}'",
                notice_compatible=notice_ok,
            )

    # 3. Extreme Experience Floor (> total_exp + configurable buffer)
    if (
        vault.total_exp_years > 0
        and signals.exp_min_years is not None
        and signals.exp_min_years > vault.total_exp_years + exp_buffer_years
    ):
        return Gate1Result(
            hidden_by_gate1=True,
            hidden_reason=(
                f"Experience floor too high: JD asks {signals.exp_min_years:g}+ yrs "
                f"vs your {vault.total_exp_years:g} yrs"
            ),
            notice_compatible=notice_ok,
        )

    return Gate1Result(
        hidden_by_gate1=False,
        hidden_reason=None,
        notice_compatible=notice_ok,
    )

