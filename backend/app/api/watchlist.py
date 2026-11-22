"""Watchlist API for managing target companies, ATS configurations, and seed synchronization."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.api.deps import get_session, get_settings
from app.collectors.manager import CollectorManager, seed_watchlist
from app.config import Settings
from app.db.models import Company
from app.schemas.watchlist import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
    WatchlistSeedResponse,
    WatchlistVerifyResponse,
)

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


@router.get("", response_model=list[CompanyResponse])
def list_watchlist_companies(
    session: Session = Depends(get_session),
    watched_only: bool = Query(default=True, description="Filter for watched companies only"),
    ats_type: Optional[str] = Query(default=None, description="Filter by ATS provider (greenhouse, lever, etc.)"),
    search: Optional[str] = Query(default=None, description="Search term for display name or slug"),
) -> list[Company]:
    """Retrieve all tracked companies and their ATS endpoint configurations."""
    stmt = select(Company)
    if watched_only:
        stmt = stmt.where(Company.is_watched.is_(True))
    if ats_type:
        stmt = stmt.where(Company.ats_type == ats_type.lower().strip())
    if search:
        s = f"%{search.strip().lower()}%"
        stmt = stmt.where(Company.display_name.ilike(s) | Company.slug.ilike(s))  # type: ignore[attr-defined]

    stmt = stmt.order_by(Company.display_name.asc())
    return list(session.exec(stmt).all())


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_or_update_company(
    payload: CompanyCreate,
    session: Session = Depends(get_session),
) -> Company:
    """Register or update a target company and its ATS settings."""
    existing = session.exec(select(Company).where(Company.slug == payload.slug)).first()
    if existing:
        existing.display_name = payload.display_name
        existing.employer_type = payload.employer_type
        existing.ats_type = payload.ats_type
        existing.ats_config_json = payload.ats_config_json
        existing.is_watched = payload.is_watched
        existing.is_blacklisted = payload.is_blacklisted
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    company = Company(
        slug=payload.slug,
        display_name=payload.display_name,
        employer_type=payload.employer_type,
        ats_type=payload.ats_type,
        ats_config_json=payload.ats_config_json,
        is_watched=payload.is_watched,
        is_blacklisted=payload.is_blacklisted,
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


@router.patch("/{slug}", response_model=CompanyResponse)
def patch_company(
    slug: str,
    payload: CompanyUpdate,
    session: Session = Depends(get_session),
) -> Company:
    """Modify specific attributes of a tracked company."""
    company = session.exec(select(Company).where(Company.slug == slug)).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Company '{slug}' not found")

    if payload.display_name is not None:
        company.display_name = payload.display_name
    if payload.employer_type is not None:
        company.employer_type = payload.employer_type
    if payload.ats_type is not None:
        company.ats_type = payload.ats_type
    if payload.ats_config_json is not None:
        company.ats_config_json = payload.ats_config_json
    if payload.is_watched is not None:
        company.is_watched = payload.is_watched
    if payload.is_blacklisted is not None:
        company.is_blacklisted = payload.is_blacklisted

    session.add(company)
    session.commit()
    session.refresh(company)
    return company


@router.delete("/{slug}", status_code=status.HTTP_200_OK)
def delete_or_unwatch_company(
    slug: str,
    hard_delete: bool = Query(default=False, description="Permanently delete from database if True, else unwatch"),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    """Remove a company from watchlist or permanently remove record."""
    company = session.exec(select(Company).where(Company.slug == slug)).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Company '{slug}' not found")

    if hard_delete:
        session.delete(company)
        session.commit()
        return {"status": "deleted", "slug": slug}
    else:
        company.is_watched = False
        session.add(company)
        session.commit()
        return {"status": "unwatched", "slug": slug}


@router.post("/seed", response_model=WatchlistSeedResponse)
def trigger_watchlist_seed(
    session: Session = Depends(get_session),
) -> WatchlistSeedResponse:
    """Synchronize pre-seeded 60+ Indian Tech Unicorns & GCCs into database."""
    seeded, updated, total = seed_watchlist(session)
    return WatchlistSeedResponse(
        seeded_count=seeded,
        updated_count=updated,
        total_count=total,
        message=f"Successfully synced watchlist: {seeded} new companies added, {updated} updated (total: {total}).",
    )


@router.post("/verify", response_model=WatchlistVerifyResponse)
async def verify_watchlist_endpoints(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> WatchlistVerifyResponse:
    """Concurrently probe all watched ATS board tokens and flag any 404s as invalid_config."""
    manager = CollectorManager(settings=settings)
    return await manager.verify_watchlist_boards(session)

