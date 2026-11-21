"""Lever ATS direct connector polling official public postings API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.collectors.location_filter import is_india_location
from app.pipeline.orchestrator import RawJobInput

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 15.0
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


async def fetch_lever_jobs(
    client: httpx.AsyncClient,
    company_token: str,
    company_name: str,
    filter_india_only: bool = True,
) -> list[RawJobInput]:
    """Fetch all open postings from Lever v0 public postings API."""
    url = f"https://api.lever.co/v0/postings/{company_token}?mode=json"
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}

    response = await client.get(url, headers=headers, timeout=_DEFAULT_TIMEOUT)
    if response.status_code == 429:
        raise httpx.HTTPStatusError("Lever Rate Limited (429)", request=response.request, response=response)
    if response.status_code == 403:
        raise httpx.HTTPStatusError("Lever Access Forbidden (403)", request=response.request, response=response)

    response.raise_for_status()
    raw_postings: list[dict[str, Any]] = response.json()
    if not isinstance(raw_postings, list):
        return []

    results: list[RawJobInput] = []
    for item in raw_postings:
        job_id = str(item.get("id", ""))
        title = item.get("text", "").strip()
        if not title:
            continue

        categories = item.get("categories", {}) or {}
        location_raw = categories.get("location", "")
        all_locations = categories.get("allLocations", [])
        loc_str = location_raw
        if all_locations and isinstance(all_locations, list):
            loc_str = f"{location_raw} {' '.join(str(l) for l in all_locations)}"

        if filter_india_only:
            is_india, _ = is_india_location(loc_str)
            if not is_india:
                continue

        # Combine main description and lists
        description_plain = item.get("descriptionPlain") or item.get("description") or ""
        additional_plain = item.get("additionalPlain") or item.get("additional") or ""
        full_description = f"{description_plain}\n\n{additional_plain}".strip()

        hosted_url = item.get("hostedUrl") or f"https://jobs.lever.co/{company_token}/{job_id}"
        apply_url = item.get("applyUrl") or hosted_url

        results.append(
            RawJobInput(
                title=title,
                company_name=company_name,
                description_raw=full_description,
                location_raw=location_raw,
                portal_name="lever",
                external_job_id=job_id,
                job_url=hosted_url,
                apply_url=apply_url,
                portal_metadata={
                    "commitment": categories.get("commitment"),
                    "team": categories.get("team"),
                    "department": categories.get("department"),
                    "created_at": item.get("createdAt"),
                },
            )
        )

    logger.info(f"Lever ({company_token}): fetched {len(raw_postings)} total, {len(results)} India postings.")
    return results

