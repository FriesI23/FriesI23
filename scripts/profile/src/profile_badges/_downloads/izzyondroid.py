"""Collect IzzyOnDroid APK downloads from annual and daily reports."""

from .common import as_object, count, iso_date, require, sum_counts


def collect(previous, context):
    """Refresh annual totals and record the most recent daily count."""
    base = context.urls["izzy_api"].rstrip("/")
    package = context.package_id
    latest = as_object(context.fetch_json(f"{base}/daily/rolling.json"))
    require(len(latest) == 1, "Missing IzzyOnDroid reporting date")
    through = iso_date(next(iter(latest)))
    require(
        previous.get("through", "") <= through <= context.today,
        "IzzyOnDroid reporting date regressed",
    )
    first = iso_date(context.settings["izzy_first_day"])
    last_day = count(as_object(latest[through]).get(package, 0))
    years = {}
    prior_years = previous.get("years", {})
    for year_number in range(int(first[:4]), int(through[:4]) + 1):
        year = str(year_number)
        # Refresh the previous year once to include its final days.
        if year in prior_years and year < previous["through"][:4]:
            years[year] = prior_years[year]
            continue
        data = as_object(context.fetch_json(f"{base}/yearly/{year}.json"))
        require(data, "Empty IzzyOnDroid annual data")
        require(
            package in data or not prior_years.get(year),
            "IzzyOnDroid annual report lost this app",
        )
        years[year] = count(data.get(package, 0))
    require(
        years[through[:4]] >= last_day,
        "IzzyOnDroid annual data is incomplete",
    )
    return {
        "from": first,
        "through": through,
        "total": sum_counts(years.values()),
        "years": years,
        "lastDayCount": last_day,
    }


def daily_counts(cache, days, context, pool):
    """Read daily counts from the months covered by the window."""
    base = context.urls["izzy_api"].rstrip("/")
    months = sorted({day[:7] for day in days})
    urls = [f"{base}/monthly-in-days/{month}.json" for month in months]
    daily = {}
    for report in pool.map(context.fetch_json, urls):
        daily.update(as_object(report))
    counts = []
    for day in days:
        require(
            day in daily and as_object(daily[day]),
            f"Incomplete daily IzzyOnDroid report for {day}.",
        )
        counts.append(count(daily[day].get(context.package_id, 0)))
    if days[-1] == cache["through"]:
        require(
            counts[-1] == cache["lastDayCount"],
            "IzzyOnDroid daily reports disagree on the closing date.",
        )
    return counts
