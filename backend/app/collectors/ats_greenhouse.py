"""Greenhouse ATS direct connector polling official public boards API."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.collectors.location_filter import is_india_location
from app.pipeline.orchestrator import RawJobInput

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 15.0
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


async def fetch_greenhouse_jobs(
    client: httpx.AsyncClient,
    board_token: str,
    company_name: str,
    filter_india_only: bool = True,
) -> list[RawJobInput]:
    """Fetch all open postings from Greenhouse public boards API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}

    response = await client.get(url, headers=headers, timeout=_DEFAULT_TIMEOUT)
    if response.status_code == 429:
        raise httpx.HTTPStatusError("Greenhouse Rate Limited (429)", request=response.request, response=response)
    if response.status_code == 403:
        raise httpx.HTTPStatusError("Greenhouse Access Forbidden (403)", request=response.request, response=response)

    response.raise_for_status()
    data = response.json()
    raw_jobs: list[dict[str, Any]] = data.get("jobs", [])

    results: list[RawJobInput] = []
    for item in raw_jobs:
        job_id = str(item.get("id", ""))
        title = item.get("title", "").strip()
        if not title:
            continue

        loc_obj = item.get("location", {}) or {}
        location_raw = loc_obj.get("name", "") if isinstance(loc_obj, dict) else str(loc_obj)

        if filter_india_only:
            is_india, normalized_city = is_india_location(location_raw)
            if not is_india:
                continue

        content_html = item.get("content", "") or ""
        absolute_url = item.get("absolute_url") or f"https://boards.greenhouse.io/{board_token}/jobs/{job_id}"

        results.append(
            RawJobInput(
                title=title,
                company_name=company_name,
                description_raw=content_html,
                location_raw=location_raw,
                portal_name="greenhouse",
                external_job_id=job_id,
                job_url=absolute_url,
                apply_url=absolute_url,
                portal_metadata={
                    "board_token": board_token,
                    "updated_at": item.get("updated_at"),
                    "departments": [d.get("name") for d in item.get("departments", []) if isinstance(d, dict)],
                },
            )
        )

    logger.info(f"Greenhouse ({board_token}): fetched {len(raw_jobs)} total, {len(results)} India postings.")
    return results

