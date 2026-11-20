"""Strict PII guardrails blocking Indian government IDs and DoB storage/autofill."""

from __future__ import annotations

import re
from typing import Optional

_BLOCKED_QUESTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pan_card", re.compile(r"\b(pan\s*card|pan\s*number|pan\s*no|permanent\s+account\s+number)\b", re.I)),
    ("aadhaar", re.compile(r"\b(aadhaar|aadhar|uidai)\b", re.I)),
    ("passport", re.compile(r"\b(passport\s*(number|no|#)?|passport_number)\b", re.I)),
    ("date_of_birth", re.compile(r"\b(date\s+of\s+birth|dob|birth\s*date)\b", re.I)),
    ("bank_account", re.compile(r"\b(bank\s+account|ifsc|account\s+number)\b", re.I)),
    ("uan_pf", re.compile(r"\b(uan\s*(number|no)?|pf\s+account|epfo)\b", re.I)),
)

_PAN_VALUE_PATTERN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_AADHAAR_VALUE_PATTERN = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")


def is_blocked_pii_question(question: str) -> tuple[bool, Optional[str]]:
    """Return (True, category) if the question asks for a restricted PII field."""
    normalized = " ".join(question.strip().split())
    if not normalized:
        return False, None

    # Allow isolated 'pan' only when clearly asking for PAN id/code
    if normalized.lower() in {"pan", "pan?"}:
        return True, "pan_card"

    for category, pattern in _BLOCKED_QUESTION_PATTERNS:
        if pattern.search(normalized):
            return True, category
    return False, None


def contains_sensitive_pii_value(value: str) -> tuple[bool, Optional[str]]:
    """Detect Indian PAN or 12-digit Aadhaar patterns in candidate values."""
    cleaned = value.strip()
    if not cleaned:
        return False, None
    if _PAN_VALUE_PATTERN.search(cleaned.upper()):
        return True, "pan_value_detected"
    if _AADHAAR_VALUE_PATTERN.search(cleaned):
        return True, "aadhaar_value_detected"
    return False, None

