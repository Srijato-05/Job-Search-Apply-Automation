"""API routes for Verified Fact Vault, Learned Q&A Rules, Taxonomy, and Templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import get_session
from app.db.models import FactVault, LearnedQARule, utc_now
from app.schemas.vault import (
    FactVaultPayload,
    FactVaultResponse,
    QARuleCreate,
    QARuleResponse,
    TaxonomyNormalizeRequest,
    TaxonomyNormalizeResponse,
)
from app.vault.pii_guard import contains_sensitive_pii_value, is_blocked_pii_question
from app.vault.taxonomy import (
    extract_office_locality,
    extract_skills_from_text,
    is_india_location,
    normalize_city,
    normalize_skill_list,
)
from app.vault.templates import render_cover_template

router = APIRouter(prefix="/vault", tags=["vault"])


class TemplateRenderRequest(BaseModel):
    """Payload for deterministic cover-note template preview."""

    template: str
    variables: dict[str, str]


def _get_or_create_vault(session: Session) -> FactVault:
    vault = session.get(FactVault, 1)
    if vault is None:
        vault = FactVault(id=1)
        session.add(vault)
        session.commit()
        session.refresh(vault)
    return vault


@router.get("", response_model=FactVaultResponse)
def read_vault(session: Session = Depends(get_session)) -> FactVault:
    """Retrieve the singleton Verified Fact Vault."""
    return _get_or_create_vault(session)


@router.put("", response_model=FactVaultResponse)
def update_vault(
    payload: FactVaultPayload,
    session: Session = Depends(get_session),
) -> FactVault:
    """Update the singleton Verified Fact Vault with strict validation."""
    vault = _get_or_create_vault(session)
    for key, val in payload.model_dump().items():
        setattr(vault, key, val)
    vault.updated_at = utc_now()
    session.add(vault)
    session.commit()
    session.refresh(vault)
    return vault


@router.get("/qa-rules", response_model=list[QARuleResponse])
def list_qa_rules(session: Session = Depends(get_session)) -> list[LearnedQARule]:
    """List all verified Q&A rules ordered by most recently updated."""
    stmt = select(LearnedQARule).order_by(LearnedQARule.updated_at.desc())
    return list(session.exec(stmt).all())


@router.post("/qa-rules", response_model=QARuleResponse, status_code=status.HTTP_201_CREATED)
def upsert_qa_rule(
    payload: QARuleCreate,
    session: Session = Depends(get_session),
) -> LearnedQARule:
    """Save or update a verified Q&A rule while enforcing strict PII guardrails."""
    blocked_q, category = is_blocked_pii_question(payload.question)
    if blocked_q:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Blocked sensitive PII question ({category}): government IDs and DoB cannot be stored for autofill.",
        )

    blocked_val, val_reason = contains_sensitive_pii_value(payload.verified_answer)
    if blocked_val:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Blocked sensitive PII value ({val_reason}): PAN/Aadhaar patterns cannot be saved.",
        )

    normalized_q = " ".join(payload.question.strip().lower().split())
    existing = session.exec(
        select(LearnedQARule).where(LearnedQARule.normalized_question == normalized_q)
    ).first()

    clean_aliases = sorted(
        {a.strip().lower() for a in payload.canonical_aliases if a.strip()}
    )

    if existing is not None:
        merged_aliases = sorted(set(existing.canonical_aliases_json) | set(clean_aliases))
        existing.canonical_aliases_json = merged_aliases
        existing.verified_answer = payload.verified_answer.strip()
        existing.answer_type = payload.answer_type
        existing.portal_scope = payload.portal_scope
        existing.updated_at = utc_now()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    rule = LearnedQARule(
        normalized_question=normalized_q,
        canonical_aliases_json=clean_aliases,
        verified_answer=payload.verified_answer.strip(),
        answer_type=payload.answer_type,
        portal_scope=payload.portal_scope,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


@router.delete("/qa-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_qa_rule(rule_id: int, session: Session = Depends(get_session)) -> Response:
    """Delete a learned Q&A rule by ID."""
    rule = session.get(LearnedQARule, rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Q&A rule not found")
    session.delete(rule)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/taxonomy/normalize", response_model=TaxonomyNormalizeResponse)
def normalize_taxonomy(payload: TaxonomyNormalizeRequest) -> TaxonomyNormalizeResponse:
    """Normalize skill aliases, extract skills from text, and normalize Indian locations."""
    return TaxonomyNormalizeResponse(
        normalized_skills=normalize_skill_list(payload.skills),
        extracted_skills=extract_skills_from_text(payload.text),
        normalized_city=normalize_city(payload.city),
        office_locality=extract_office_locality(f"{payload.city} {payload.text}"),
        is_india=is_india_location(payload.city) or is_india_location(payload.text),
    )


@router.post("/templates/render")
def render_template_preview(payload: TemplateRenderRequest) -> dict[str, object]:
    """Deterministically substitute pre-approved placeholders in a cover template."""
    return render_cover_template(payload.template, payload.variables)

