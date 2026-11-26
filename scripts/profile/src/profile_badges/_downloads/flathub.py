"""Collect Flathub downloads from archived and daily reports."""

from .common import (
    as_object,
    count,
    iso_date,
    iter_days,
    require,
    shift_day,
    sum_counts,
)


def _architecture_total(arches):
    require(as_object(arches), "Flathub app has no architecture counts")
    downloads = []
    for pair in arches.values():
        require(
            isinstance(pair, list) and len(pair) >= 2,
            "Invalid Flathub architecture counts",
        )
        require(
            count(pair[1]) <= count(pair[0]), "Invalid Flathub update count"
        )
        downloads.append(pair[0])  # Updates are already included.
    return sum_counts(downloads)


def _daily_count(day, context):
    path = day.replace("-", "/")
    url = context.urls["flathub_daily"].format(datepath=path)
    report = context.fetch_json(url)
    require(report["date"] == path, "Flathub daily file has a different date")
    refs = as_object(report["refs"])
    require(refs, "Empty Flathub daily report")
    # An official daily report confirms zeros for absent apps.
    if context.package_id not in refs:
        return 0
    return _architecture_total(refs[context.package_id])


def _archive_counts(through, context):
    url = context.urls["flathub_history"].format(package_id=context.package_id)
    history = context.fetch_json(url)
    require(
        history["ref"] == context.package_id
        and isinstance(history["stats"], list),
        "Invalid Flathub history",
    )
    daily = {}
    for row in history["stats"]:
        day = iso_date(row["date"].replace("/", "-"))
        if day <= through:
            require(day not in daily, "Duplicate Flathub date")
            daily[day] = _architecture_total(row["arches"])
    require(daily, "Empty Flathub history")
    return daily


def _cache_start(through, context):
    return shift_day(through, 1 - context.settings["flathub_cache_days"])


def collect(previous, context):
    """Refresh the cumulative count and cache recent daily reports."""
    official = as_object(context.fetch_json(context.urls["flathub_summary"]))
    stable_days = as_object(official["installs_per_day"])
    require(stable_days, "Invalid Flathub reporting date")
    through = max(iso_date(day) for day in stable_days)
    require(
        previous.get("through", "") <= through <= context.today,
        "Invalid Flathub reporting date",
    )
    oldest = _cache_start(through, context)
    if not previous or previous["through"] < shift_day(
        through, -context.settings["flathub_reseed_days"]
    ):
        daily = _archive_counts(through, context)
        first, latest = min(daily), max(daily)
        require(
            not previous or first <= previous["from"],
            "Flathub archive lost previously covered dates",
        )
        total = sum_counts(daily.values())
    else:
        first, latest = previous["from"], previous["through"]
        total, daily = previous["total"], previous["daily"].copy()
    # Reconcile overlapping reports before adding new days.
    for day in iter_days(max(first, shift_day(latest, -1)), through):
        downloads = _daily_count(day, context)
        total += downloads - daily.get(day, 0)
        daily[day] = downloads
    return {
        "from": first,
        "through": through,
        "total": count(total),
        "daily": {day: value for day, value in daily.items() if day >= oldest},
    }


def check_window(cache, start, context):
    """Check that the cache covers the start of the window."""
    oldest = max(cache["from"], _cache_start(cache["through"], context))
    require(
        start >= oldest,
        f"The {context.settings['period_days']}-day window extends beyond "
        "the available Flathub history.",
    )


def daily_counts(cache, days, context):
    """Fill archive gaps and return counts for the requested days."""
    daily = cache["daily"]
    missing = {
        day: _daily_count(day, context) for day in days if day not in daily
    }
    cache["total"] = count(cache["total"] + sum_counts(missing.values()))
    daily.update(missing)
    return [daily[day] for day in days]
