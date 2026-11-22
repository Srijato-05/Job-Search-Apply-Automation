"""Workday CXS direct connector with strict limit <= 20 and loop guards."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx

from app.collectors.location_filter import is_india_location
from app.pipeline.orchestrator import RawJobInput

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 15.0
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
_MAX_WORKDAY_PAGE_LIMIT = 20
_MAX_PAGE_SAFETY_LIMIT = 50  # Cap at 1,000 jobs per run to prevent runaway loops


def _build_workday_cxs_base_url(tenant: str, site: str, instance: Optional[str] = None) -> str:
    """Format the Workday CXS API URL."""
    inst_part = f".{instance}" if instance else ""
    return f"https://{tenant}{inst_part}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"


async def fetch_workday_jobs(
    client: httpx.AsyncClient,
    tenant: str,
    site: str,
    company_name: str,
    instance: Optional[str] = "wd1",
    filter_india_only: bool = True,
    search_text: str = "",
    max_pages: int = _MAX_PAGE_SAFETY_LIMIT,
    known_external_ids: Optional[set[str]] = None,
    force_refresh_details: bool = False,
) -> list[RawJobInput]:
    """Fetch open postings from modern Workday CXS POST endpoint.

    Strictly complies with:
    - limit <= 20
    - loop stop when offset >= total or 0 results returned
    - page iteration cap
    - India location filtering and req ID extraction
    """
    base_url = _build_workday_cxs_base_url(tenant, site, instance)
    jobs_url = f"{base_url}/jobs"
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    offset = 0
    total = 0
    page_count = 0
    active_search_text = search_text
    did_india_fallback = False
    all_postings: list[dict[str, Any]] = []

    while page_count < max_pages:
        payload: dict[str, Any] = {
            "appliedFacets": {},
            "limit": _MAX_WORKDAY_PAGE_LIMIT,  # Hardcoded <= 20
            "offset": offset,
            "searchText": active_search_text,
        }

        response = await client.post(jobs_url, json=payload, headers=headers, timeout=_DEFAULT_TIMEOUT)
        if response.status_code == 429:
            raise httpx.HTTPStatusError("Workday Rate Limited (429)", request=response.request, response=response)
        if response.status_code == 403:
            raise httpx.HTTPStatusError("Workday Access Forbidden (403)", request=response.request, response=response)

        response.raise_for_status()
        data = response.json()

        total = data.get("total", 0)

        # For massive global tenants (> 1,000 jobs), automatically narrow to India
        # so India roles beyond page 50 are never truncated.
        if (
            filter_india_only
            and not did_india_fallback
            and not active_search_text
            and page_count == 0
            and total > (max_pages * _MAX_WORKDAY_PAGE_LIMIT)
        ):
            logger.info(
                f"Workday ({tenant}/{site}): global total={total} exceeds cap; "
                "switching to searchText='India' for targeted India extraction."
            )
            active_search_text = "India"
            did_india_fallback = True
            offset = 0
            page_count = 0
            all_postings = []
            continue

        postings = data.get("jobPostings", [])
        if not postings:
            break

        all_postings.extend(postings)
        offset += len(postings)
        page_count += 1

        # Strict loop stop conditions
        if offset >= total or len(postings) < _MAX_WORKDAY_PAGE_LIMIT:
            break

    results: list[RawJobInput] = []
    for item in all_postings:
        title = item.get("title", "").strip()
        if not title:
            continue

        external_path = item.get("externalPath", "")
        locations_text = item.get("locationsText", "")

        if filter_india_only:
            is_india, _ = is_india_location(locations_text)
            if not is_india:
                # Also check external_path for city/india indicators
                if not is_india_location(external_path.replace("-", " "))[0]:
                    continue

        bullet_fields = item.get("bulletFields", [])
        req_id = bullet_fields[0] if bullet_fields else None
        if not req_id and external_path:
            # Extract req id from external_path like /job/.../JR12345
            match = re.search(r"(JR[-_]?\d{3,}|R[-_]?\d{4,})", external_path, re.IGNORECASE)
            if match:
                req_id = match.group(1)

        job_url = f"https://{tenant}{('.' + instance) if instance else ''}.myworkdayjobs.com/en-US/{site}{external_path}"
        external_job_id = req_id or external_path.strip("/").split("/")[-1]

        # Incremental detail fetch: skip per-job detail HTTP call if already known in DB
        # (initial runs have empty known_external_ids so 100% of details are downloaded;
        # the full list above is still always fetched so the closed-job pruner stays 100% accurate).
        skip_detail = (
            not force_refresh_details
            and known_external_ids is not None
            and external_job_id in known_external_ids
        )

        # Fetch detail JSON if external_path exists and not skipped
        description = ""
        if external_path and not skip_detail:
            detail_url = f"{base_url}/job{external_path}"
            try:
                detail_resp = await client.get(detail_url, headers=headers, timeout=_DEFAULT_TIMEOUT)
                if detail_resp.status_code == 200:
                    detail_data = detail_resp.json()
                    info = detail_data.get("jobPostingInfo", {})
                    description = info.get("jobDescription", "")
                    if not req_id:
                        req_id = info.get("requisitionId")
            except Exception as e:
                logger.debug(f"Workday detail fetch failed for {external_path}: {e}")

        if not description:
            description = f"{title}\nLocation: {locations_text}\nRequisition ID: {req_id or 'N/A'}"

        results.append(
            RawJobInput(
                title=title,
                company_name=company_name,
                description_raw=description,
                location_raw=locations_text,
                portal_name="workday",
                external_job_id=external_job_id,
                job_url=job_url,
                apply_url=job_url,
                portal_metadata={
                    "tenant": tenant,
                    "site": site,
                    "req_id": req_id,
                    "posted_on": item.get("postedOn"),
                    "external_path": external_path,
                },
            )
        )

    logger.info(f"Workday ({tenant}/{site}): fetched {len(all_postings)} total, {len(results)} India postings.")
    return results

