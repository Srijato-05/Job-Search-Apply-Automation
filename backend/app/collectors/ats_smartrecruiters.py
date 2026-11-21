"""SmartRecruiters ATS direct connector polling official postings API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.collectors.location_filter import is_india_location
from app.pipeline.orchestrator import RawJobInput

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 15.0
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


async def fetch_smartrecruiters_jobs(
    client: httpx.AsyncClient,
    company_id: str,
    company_name: str,
    filter_india_only: bool = True,
    fetch_details: bool = True,
) -> list[RawJobInput]:
    """Fetch open postings from SmartRecruiters public API with optional detail fetching."""
    url = f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings?limit=100"
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}

    response = await client.get(url, headers=headers, timeout=_DEFAULT_TIMEOUT)
    if response.status_code == 429:
        raise httpx.HTTPStatusError("SmartRecruiters Rate Limited (429)", request=response.request, response=response)
    if response.status_code == 403:
        raise httpx.HTTPStatusError("SmartRecruiters Access Forbidden (403)", request=response.request, response=response)

    response.raise_for_status()
    data = response.json()
    raw_postings: list[dict[str, Any]] = data.get("content", [])

    results: list[RawJobInput] = []
    for item in raw_postings:
        job_id = str(item.get("id", ""))
        title = item.get("name", "").strip()
        if not title:
            continue

        loc_obj = item.get("location", {}) or {}
        city = loc_obj.get("city", "")
        region = loc_obj.get("region", "")
        country = (loc_obj.get("country", "") or "").lower()
        location_raw = f"{city}, {region}".strip(", ")

        if filter_india_only:
            is_india = (country == "in") or is_india_location(f"{city} {region} {country}")[0]
            if not is_india:
                continue

        ref_number = item.get("refNumber")
        job_url = f"https://jobs.smartrecruiters.com/{company_id}/{job_id}"

        # Fetch detail for full job description if requested
        description = ""
        if fetch_details:
            detail_url = f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings/{job_id}"
            try:
                detail_resp = await client.get(detail_url, headers=headers, timeout=_DEFAULT_TIMEOUT)
                if detail_resp.status_code == 200:
                    detail_data = detail_resp.json()
                    job_ad = detail_data.get("jobAd", {})
                    sections = job_ad.get("sections", {})
                    jd_text = sections.get("jobDescription", {}).get("text", "")
                    qual_text = sections.get("qualifications", {}).get("text", "")
                    add_text = sections.get("additionalInformation", {}).get("text", "")
                    description = f"{jd_text}\n\n{qual_text}\n\n{add_text}".strip()
            except Exception as e:
                logger.debug(f"SmartRecruiters detail fetch failed for {job_id}: {e}")

        if not description:
            description = f"{title}\nLocation: {location_raw}\nReference Number: {ref_number or 'N/A'}"

        results.append(
            RawJobInput(
                title=title,
                company_name=company_name,
                description_raw=description,
                location_raw=location_raw,
                portal_name="smartrecruiters",
                external_job_id=job_id,
                job_url=job_url,
                apply_url=job_url,
                portal_metadata={
                    "ref_number": ref_number,
                    "company_id": company_id,
                    "released_date": item.get("releasedDate"),
                },
            )
        )

    logger.info(f"SmartRecruiters ({company_id}): fetched {len(raw_postings)} total, {len(results)} India postings.")
    return results

