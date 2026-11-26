"""Aggregate Google Play country reports at the project level."""

import codecs
import csv
import hashlib
import io
import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from google.cloud import storage
from google.oauth2.credentials import Credentials

SUMMARY_KEYS = (
    "total",
    "from",
    "through",
    "monthly",
    "monthlyStart",
    "monthlyEnd",
    "missingDays",
)


def _day(value):
    if type(value) is date:
        return value
    day = date.fromisoformat(value)
    if day.isoformat() != value:
        raise ValueError("Expected an ISO calendar date")
    return day


def _integer(value):
    if not re.fullmatch("[0-9]+", value):
        raise ValueError("Expected a non-negative count")
    return int(value)


def _read_csv(data, month, package, start, today):
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encoding = "utf-16"
    else:
        encoding = "utf-16-be" if data.startswith(b"\0") else "utf-16-le"
    reader = csv.DictReader(
        io.StringIO(data.decode(encoding), newline=""), strict=True
    )
    columns = reader.fieldnames or []
    if not {
        "Date",
        "Package Name",
        "Country",
        "Daily Device Installs",
    }.issubset(columns):
        raise ValueError("Missing report columns")
    if len(set(columns)) != len(columns):
        raise ValueError("Repeated report column")

    installs, upgrades = Counter(), Counter()
    seen = set()
    incomplete_upgrades = set()
    for row in reader:
        if (
            None in row
            or None in row.values()
            or row["Package Name"] != package
        ):
            raise ValueError("Invalid report row")
        day = _day(row["Date"])
        key = day, row["Country"]
        if day.strftime("%Y%m") != month or key in seen:
            raise ValueError("Unexpected report date or duplicate country")
        seen.add(key)
        install_count = _integer(row["Daily Device Installs"])
        if (start and day < start) or day >= today:
            continue
        installs[day] += install_count
        if "Daily Device Upgrades" in row:
            upgrade_count = row["Daily Device Upgrades"]
            if upgrade_count:
                upgrades[day] += _integer(upgrade_count)
            else:
                incomplete_upgrades.add(day)
    for day in incomplete_upgrades:
        upgrades.pop(day, None)
    return installs, upgrades


def _month_summary(daily):
    total = sum(daily.values())
    if total >= 2**53:
        raise ValueError("Invalid install report total")
    return {
        "from": min(daily).isoformat() if daily else None,
        "through": max(daily).isoformat() if daily else None,
        "total": total,
        "days": len(daily),
    }


def _summarize(months, metric, daily, end, period_days):
    reported = [
        month[metric] for month in months.values() if month[metric]["days"]
    ]
    if not reported:
        return dict.fromkeys(SUMMARY_KEYS)
    first = _day(min(report["from"] for report in reported))
    last = _day(max(report["through"] for report in reported))
    start = end - timedelta(days=period_days - 1)
    window = [value for day, value in daily.items() if start <= day <= end]
    complete = len(window) == period_days
    total = sum(report["total"] for report in reported)
    if total >= 2**53:
        raise ValueError("Invalid install report total")
    return {
        "from": first.isoformat(),
        "through": last.isoformat(),
        "total": total,
        "missingDays": (last - first).days
        + 1
        - sum(report["days"] for report in reported),
        "monthly": sum(window) if complete else None,
        "monthlyStart": start.isoformat() if complete else None,
        "monthlyEnd": end.isoformat() if complete else None,
    }


def _collect(previous, *, package, period_days, bucket, start, today):
    prefix = f"stats/installs/installs_{package}_"
    name = re.compile(
        re.escape(prefix) + r"([0-9]{4}(?:0[1-9]|1[0-2]))_country\.csv"
    )
    first_month = start.strftime("%Y%m") if start else ""
    current_month = today.strftime("%Y%m")
    objects = {}
    for blob in bucket.list_blobs(
        prefix=prefix,
        fields="nextPageToken,items(name,generation)",
        timeout=30,
    ):
        match = name.fullmatch(blob.name)
        if match and first_month <= match[1] <= current_month:
            objects[match[1]] = blob
    cached = previous.get("months", {})
    if any(month >= first_month and month not in objects for month in cached):
        raise ValueError("Previously covered month is missing")

    months = {}
    recent_installs, recent_upgrades = {}, {}
    end = None
    for month, blob in sorted(objects.items(), reverse=True):
        # Match the revision hashes in existing snapshots.
        generation = blob.generation
        revision = None
        if generation is not None:
            identity = [
                bucket.name,
                blob.name,
                str(generation),
                start.isoformat() if start else "",
            ]
            encoded = json.dumps(
                identity, separators=(",", ":"), ensure_ascii=False
            ).encode()
            revision = hashlib.sha256(encoded).hexdigest()
        older = end is not None and month < (
            end - timedelta(days=period_days - 1)
        ).strftime("%Y%m")
        saved = cached.get(month, {})
        if (
            older
            and revision
            and saved.get("revision") == revision
            and saved.get("complete")
        ):
            months[month] = saved
            continue
        # Read the object only if its generation still matches.
        data = bucket.blob(blob.name).download_as_bytes(
            if_generation_match=generation, timeout=30
        )
        installs, upgrades = _read_csv(data, month, package, start, today)
        months[month] = {
            "revision": revision,
            "complete": month < current_month,
            "installs": _month_summary(installs),
            "upgrades": _month_summary(upgrades),
        }
        if not older:
            if installs and end is None:
                end = max(installs)
            recent_installs.update(installs)
            recent_upgrades.update(upgrades)
    if end is None:
        raise ValueError("No completed report dates")

    installs = _summarize(
        months, "installs", recent_installs, end, period_days
    )
    month = _day(installs["from"]).replace(day=1)
    while month <= end:
        if month.strftime("%Y%m") not in months:
            raise ValueError("Missing month within report period")
        month = (month + timedelta(days=32)).replace(day=1)
    if previous.get("from") and previous.get("through"):
        first = max(previous["from"], start.isoformat() if start else "")
        if (
            installs["from"] > first
            or installs["through"] < previous["through"]
        ):
            raise ValueError("Previously covered dates are missing")
    return {
        "status": "current",
        **installs,
        "upgrades": _summarize(
            months, "upgrades", recent_upgrades, end, period_days
        ),
        "months": months,
    }


def collect_store_installs(
    previous=None,
    *,
    config,
    access_token=None,
    bucket=None,
    start_date="",
    today=None,
):
    """Return (summary, warnings), retaining the last good sample."""
    previous = previous or {}
    has_previous = (
        type(previous.get("total")) is int and previous["total"] >= 0
    )
    saved = previous if has_previous else {}
    period_days = config["downloads"]["period_days"]

    def previous_metric(metric):
        summary = {key: metric.get(key) for key in SUMMARY_KEYS}
        try:
            covered = (
                _day(summary["monthlyEnd"]) - _day(summary["monthlyStart"])
            ).days + 1
        except (TypeError, ValueError):
            covered = 0
        if covered != period_days or summary["monthly"] is None:
            summary.update(monthly=None, monthlyStart=None, monthlyEnd=None)
        return summary

    def fallback(status):
        return {
            **previous_metric(saved),
            "status": "stale" if has_previous else status,
            "upgrades": previous_metric(saved.get("upgrades", {})),
            "months": saved.get("months", {}),
        }

    if not access_token or not bucket:
        if access_token or bucket:
            return fallback("unavailable"), [
                "Google Play reporting is not fully configured "
                "for this refresh."
            ]
        warnings = (
            ["Google Play refresh skipped. Keeping the previous report."]
            if has_previous
            else []
        )
        return fallback("unconfigured"), warnings
    try:
        # Reading reports requires only object access. Skip the SDK's
        # bucket metadata lookup.
        os.environ.setdefault(
            "DISABLE_GCS_PYTHON_CLIENT_OTEL_BUCKET_METADATA", "true"
        )
        with storage.Client(
            project=None, credentials=Credentials(access_token)
        ) as client:
            state = _collect(
                previous,
                package=config["app"]["package_id"],
                period_days=period_days,
                bucket=client.bucket(bucket),
                start=_day(start_date) if start_date else None,
                today=_day(today)
                if today
                else datetime.now(timezone.utc).date(),
            )
    except Exception:
        # Transport errors can contain private URLs or report data.
        return fallback("unavailable"), [
            "Google Play install reports could not be refreshed."
        ]
    return state, []
