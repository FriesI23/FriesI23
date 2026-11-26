"""Collect source totals and align the daily reporting window."""

from . import fdroid, flathub, izzyondroid
from . import github as github_releases
from .common import iter_days, require, shift_day, sum_counts

SOURCES = {
    "github": github_releases.collect,
    "izzy": izzyondroid.collect,
    "flathub": flathub.collect,
    "fdroid": fdroid.collect,
}


def collect_totals(previous_cache, context, pool):
    jobs = {
        key: pool.submit(read, previous_cache.get(key, {}), context)
        for key, read in SOURCES.items()
    }
    cache, failures = {}, {}
    for key, job in jobs.items():
        try:
            cache[key] = job.result()
        except Exception as error:
            message = f"{context.config['channels'][key]['name']}: {error}"
            if key not in previous_cache:
                raise ValueError(
                    f"Initial download collection failed: {message}"
                ) from error
            cache[key] = previous_cache[key]
            failures[key] = message
    return cache, failures


def collect_window(cache, failures, previous, context, pool):
    period = context.settings["period_days"]
    end = min(cache["flathub"]["through"], cache["izzy"]["through"])
    start = shift_day(end, 1 - period)
    try:
        unavailable = [key for key in ("izzy", "flathub") if key in failures]
        require(
            not unavailable, f"Could not refresh {', '.join(unavailable)}."
        )
        flathub.check_window(cache["flathub"], start, context)
        days = list(iter_days(start, end))
        daily = {
            "izzy": izzyondroid.daily_counts(
                cache["izzy"], days, context, pool
            ),
            "flathub": flathub.daily_counts(cache["flathub"], days, context),
        }
        monthly = {key: sum_counts(counts) for key, counts in daily.items()}
        return start, end, monthly, None
    except Exception as error:
        if not previous.get("sources"):
            raise
        start, end = previous["start"], previous["end"]
        if start != shift_day(end, 1 - period):
            raise ValueError(
                f"No complete {period}-day window is available. "
                f"The saved window runs from {start} to {end}."
            ) from error
        reason = f"Retained the previous {period}-day window. {error}"
        monthly = {
            source["id"]: source["monthly"] for source in previous["sources"]
        }
        return start, end, monthly, reason
