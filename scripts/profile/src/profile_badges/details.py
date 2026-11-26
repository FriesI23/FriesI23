"""Render the distribution report from the README badge snapshots."""

from jinja2 import Environment, PackageLoader, StrictUndefined


def _number(value):
    return f"{value:,}" if type(value) is int else "—"


def _period(start, end):
    return f"{start} to {end}" if start and end else "—"


def render_details(download_state, store_state, config):
    env = Environment(
        loader=PackageLoader("profile_badges"),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters.update(number=_number, period=_period)
    store = store_state or {}
    return env.get_template("distribution.md.j2").render(
        config=config,
        downloads=download_state,
        store=store,
        upgrades=store.get("upgrades", {}),
        days=config["downloads"]["period_days"],
        links={
            key: row.get("listing_url") or row["url"]
            for key, row in config["channels"].items()
        },
        latest=max(
            (
                s["through"]
                for s in download_state["sources"]
                if s.get("through")
            ),
            default="unavailable",
        ),
        store_status={
            "current": "Reported",
            "stale": "Last successful report",
            "unavailable": "Report unavailable",
        }.get(store.get("status"), "Reporting not connected"),
    )
