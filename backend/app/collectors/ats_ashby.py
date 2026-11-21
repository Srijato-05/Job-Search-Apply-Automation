"""Ashby ATS direct connector polling official public job-board API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.collectors.location_filter import is_india_location
from app.pipeline.orchestrator import RawJobInput

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 15.0
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


async def fetch_ashby_jobs(
    client: httpx.AsyncClient,
    company_name_or_token: str,
    company_name: str,
    filter_india_only: bool = True,
) -> list[RawJobInput]:
    """Fetch all open postings from Ashby posting-api."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company_name_or_token}?includeCompensation=true"
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}

    response = await client.get(url, headers=headers, timeout=_DEFAULT_TIMEOUT)
    if response.status_code == 429:
        raise httpx.HTTPStatusError("Ashby Rate Limited (429)", request=response.request, response=response)
    if response.status_code == 403:
        raise httpx.HTTPStatusError("Ashby Access Forbidden (403)", request=response.request, response=response)

    response.raise_for_status()
    data = response.json()
    raw_jobs: list[dict[str, Any]] = data.get("jobs", [])

    results: list[RawJobInput] = []
    for item in raw_jobs:
        job_id = str(item.get("id", ""))
        title = item.get("title", "").strip()
        if not title:
            continue

        location_name = item.get("locationName", "")
        secondary_locations = item.get("secondaryLocations", [])
        loc_str = location_name
        if secondary_locations and isinstance(secondary_locations, list):
            loc_str = f"{location_name} {' '.join(str(sec.get('locationName', '')) for sec in secondary_locations if isinstance(sec, dict))}"

        if filter_india_only:
            is_india, _ = is_india_location(loc_str)
            if not is_india:
                continue

        description_html = item.get("descriptionHtml") or item.get("descriptionPlain") or ""
        job_url = item.get("jobUrl") or f"https://jobs.ashbyhq.com/{company_name_or_token}/{job_id}"

        results.append(
            RawJobInput(
                title=title,
                company_name=company_name,
                description_raw=description_html,
                location_raw=location_name,
                portal_name="ashby",
                external_job_id=job_id,
                job_url=job_url,
                apply_url=job_url,
                portal_metadata={
                    "department": item.get("departmentName"),
                    "employment_type": item.get("employmentType"),
                    "compensation": item.get("compensation"),
                    "published_at": item.get("publishedAt"),
                },
            )
        )

    logger.info(f"Ashby ({company_name_or_token}): fetched {len(raw_jobs)} total, {len(results)} India postings.")
    return results

