"""Align reporting windows and publish complete download snapshots."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from github import Github

from ._downloads.aggregation import SOURCES, collect_totals, collect_window
from ._downloads.common import DownloadContext, iso_date, shift_day, sum_counts

__all__ = ["collect_downloads"]


def collect_downloads(
    previous, *, config, github: Github, fetch_json, today=None
):
    """Return (snapshot, warnings) for a UTC date or YYYY-MM-DD.

    The default is today in UTC.
    """
    today = iso_date(
        today if today is not None else datetime.now(timezone.utc).date()
    )
    context = DownloadContext(config, github, fetch_json, today)
    previous = previous or {}
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        cache, failures = collect_totals(
            previous.get("cache", {}), context, pool
        )
        start, end, monthly, monthly_reason = collect_window(
            cache, failures, previous, context, pool
        )

    warnings = list(failures.values())
    if monthly_reason:
        warnings.append(monthly_reason)
    total_reason = None
    published = cache
    if failures:
        total_reason = (
            "Retained the previous complete total because "
            f"{', '.join(failures)} could not be refreshed."
        )
        published = {item["id"]: item for item in previous["sources"]}

    sources = []
    for key in SOURCES:
        source = published[key]
        value = monthly.get(key)
        stale_days = context.settings[
            "fdroid_stale_days" if key == "fdroid" else "stale_days"
        ]
        channel = config["channels"][key]
        sources.append(
            {
                "id": key,
                "name": channel["name"],
                "url": channel["url"],
                "from": source["from"],
                "through": source["through"],
                "total": source["total"],
                "monthly": value,
                "monthlyStart": start if value is not None else None,
                "monthlyEnd": end if value is not None else None,
                "stale": key in failures
                or source["through"] < shift_day(today, -stale_days),
            }
        )
    return {
        "total": sum_counts(source["total"] for source in sources),
        "monthly": sum_counts(source["monthly"] or 0 for source in sources),
        "start": start,
        "end": end,
        "totalRetainedReason": total_reason,
        "monthlyRetainedReason": monthly_reason,
        "sources": sources,
        "cache": cache,
    }, warnings
