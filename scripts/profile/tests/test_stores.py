import csv
import io
import json
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

from requests import Response
from requests.adapters import HTTPAdapter
from urllib3.response import HTTPResponse

from profile_badges.details import render_details
from profile_badges.stores import collect_store_installs

PACKAGE = "io.github.example.app"
PREFIX = f"stats/installs/installs_{PACKAGE}_"
OCTOBER = [f"2026-10-{i:02}" for i in range(1, 32)]
OPTIONS = dict(
    config={"app": {"package_id": PACKAGE}, "downloads": {"period_days": 30}},
    access_token="fake-token",
    bucket="test-bucket",
    today="2026-11-02",
)


def report(dates, *, revised=False, legacy=False):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    header = ["Date", "Package Name", "Country", "Daily Device Installs"]
    writer.writerow(
        header + ([] if legacy else ["Daily Device Upgrades"]) + ["Notes"]
    )
    for day in dates:
        for country in ("US", "GB"):
            count = (
                5 if revised and day.endswith("-30") and country == "US" else 1
            )
            writer.writerow(
                [day, PACKAGE, country, count]
                + ([] if legacy else [999])
                + ['a comma, quote " and\nline']
            )
    return buffer.getvalue().encode("utf-16")


class Reports:
    """Serve two listing pages and generation-checked downloads."""

    def __init__(
        self,
        *,
        historical=False,
        revised_history=False,
        revised=False,
        legacy=False,
        missing_date=None,
        malformed=False,
    ):
        self.historical = historical
        self.revised_history = revised_history
        self.revised = revised
        self.legacy = legacy
        self.missing_date = missing_date
        self.malformed = malformed
        self.requests = []

    def __call__(self, url, headers):
        self.requests.append(url)
        parsed = urlsplit(url)
        assert parsed.hostname == "storage.googleapis.com"
        assert headers["Authorization"] == "Bearer fake-token"
        params = parse_qs(parsed.query)
        if "alt" in params:
            # Match the current generation even in versioned buckets.
            assert "generation" not in params
            name = unquote(parsed.path)
            if name.endswith("202609_country.csv"):
                assert params["ifGenerationMatch"] == [
                    "13" if self.revised_history else "12"
                ]
                return report(["2026-09-30"], revised=self.revised_history)
            assert params["ifGenerationMatch"] == ["12"]
            if name.endswith("202610_country.csv"):
                return report(
                    [day for day in OCTOBER if day != self.missing_date],
                    revised=self.revised,
                    legacy=self.legacy,
                )
            assert name.endswith("202611_country.csv")
            return (
                b"bad"
                if self.malformed
                else report(["2026-11-01", "2026-11-02"])
            )
        assert params["prefix"] == [PREFIX]
        if params.get("pageToken") == ["more"]:
            page = {
                "items": [
                    {"name": PREFIX + "202611_country.csv", "generation": "12"}
                ]
            }
        else:
            items = [
                {"name": PREFIX + "202610_country.csv", "generation": "12"},
                {"name": PREFIX + "202610_carrier.csv", "generation": "12"},
            ]
            if self.historical:
                items.append(
                    {
                        "name": PREFIX + "202609_country.csv",
                        "generation": "13" if self.revised_history else "12",
                    }
                )
            page = {"nextPageToken": "more", "items": items}
        return json.dumps(page).encode()

    def send(self, request, **kwargs):
        response = Response()
        response.status_code = 200
        response.request = request
        response.url = request.url
        data = self(request.url, request.headers)
        response.headers["Content-Length"] = str(len(data))
        response.raw = HTTPResponse(
            body=io.BytesIO(data),
            headers=response.headers,
            preload_content=False,
        )
        return response

    def collect(self, previous=None, **options):
        with patch.object(HTTPAdapter, "send", side_effect=self.send):
            return collect_store_installs(previous, **(OPTIONS | options))


def test_country_reports_include_completed_days_and_separate_device_metrics():
    fetch = Reports()
    state, warnings = fetch.collect()
    assert not warnings
    assert len(fetch.requests) == 4
    assert {
        k: state[k]
        for k in (
            "from",
            "through",
            "total",
            "monthly",
            "monthlyStart",
            "monthlyEnd",
            "missingDays",
        )
    } == {
        "total": 64,
        "from": "2026-10-01",
        "through": "2026-11-01",
        "monthly": 60,
        "monthlyStart": "2026-10-03",
        "monthlyEnd": "2026-11-01",
        "missingDays": 0,
    }
    assert state["upgrades"]["total"] == 64 * 999
    assert state["upgrades"]["monthly"] == 60 * 999
    assert sorted(state["months"]) == ["202610", "202611"]
    published = json.dumps(state)
    assert not any(
        value in published
        for value in ("test-bucket", "fake-token", "US", "GB", "2026-10-15")
    )
    assert Reports().collect(state) == (state, [])
    revised, _ = Reports(revised=True).collect(state)
    assert (revised["total"], revised["monthly"], revised["upgrades"]) == (
        68,
        64,
        state["upgrades"],
    )


def test_reports_without_upgrade_fields_keep_install_totals():
    state, _ = Reports(legacy=True).collect()
    assert state["total"] == 64
    assert state["upgrades"] == {
        "total": 1998,
        "from": "2026-11-01",
        "through": "2026-11-01",
        "monthly": None,
        "monthlyStart": None,
        "monthlyEnd": None,
        "missingDays": 0,
    }


def test_historical_revision_cache_and_missing_objects():
    first, _ = Reports(historical=True).collect()
    assert first["total"] == 66
    # Existing snapshots hash generation numbers as strings.
    assert (
        first["months"]["202609"]["revision"]
        == "8119b773de277af66f9dfa3a25662bed4685251ab46a2f58ee355c27f5a40d9f"
    )
    fetch = Reports(historical=True)
    assert fetch.collect(first) == (first, [])
    assert not any("202609_country.csv" in url for url in fetch.requests)
    fetch = Reports(historical=True, revised_history=True)
    revised, _ = fetch.collect(first)
    assert any("202609_country.csv" in url for url in fetch.requests)
    assert (revised["total"], revised["monthly"]) == (70, 60)
    missing, warnings = Reports().collect(revised)
    assert warnings
    assert missing == revised | {"status": "stale"}


def test_missing_day_is_unavailable_in_rolling_window():
    state, warnings = Reports(missing_date="2026-10-15").collect()
    assert not warnings
    assert (
        state["total"],
        state["missingDays"],
        state["monthly"],
        state["monthlyStart"],
    ) == (
        62,
        1,
        None,
        None,
    )


def test_changed_window_keeps_only_compatible_stale_metrics():
    previous, _ = Reports().collect()
    config = OPTIONS["config"] | {"downloads": {"period_days": 7}}
    stale, _ = collect_store_installs(previous, config=config)
    for metric in (stale, stale["upgrades"]):
        assert metric["total"] > 0
        assert [
            metric[key] for key in ("monthly", "monthlyStart", "monthlyEnd")
        ] == [None] * 3
    fresh, _ = Reports().collect(previous, config=config)
    assert fresh["monthly"] == 14
    assert fresh["monthlyStart"] == "2026-10-26"
    assert fresh["upgrades"]["monthly"] == 14 * 999


def test_errors_do_not_expose_private_details_or_replace_previous_results():
    previous, _ = Reports().collect()
    with patch.object(
        HTTPAdapter, "send", side_effect=ValueError("test-bucket/fake-token")
    ):
        failed = collect_store_installs(previous, **OPTIONS)
    for state, warnings in (
        Reports(malformed=True).collect(previous),
        failed,
        Reports().collect(previous, access_token=None),
    ):
        assert state == previous | {"status": "stale"}
        assert len(warnings) == 1
        assert (
            "fake-token" not in warnings[0]
            and "test-bucket" not in warnings[0]
        )
    with patch.object(HTTPAdapter, "send") as send:
        empty, warnings = collect_store_installs(config=OPTIONS["config"])
        send.assert_not_called()
    assert (empty["status"], empty["total"], warnings) == (
        "unconfigured",
        None,
        [],
    )


def test_distribution_details_include_report_coverage_and_public_listing():
    channels = {
        key: {
            "name": key,
            "url": f"https://example.org/{key}",
            "note": "Published daily.",
        }
        for key in (
            "github izzy flathub fdroid google apple microsoft "
            "homebrew scoop altstore sidestore obtainium testflight"
        ).split()
    }
    channels["flathub"]["name"] = "Flathub"
    config = {
        "app": {"name": "Example app"},
        "downloads": {"period_days": 30},
        "channels": channels,
        "distribution": {
            "Sandbox platform": ["scoop", "flathub"],
            "Second platform": ["google"],
        },
        "urls": {
            key: f"https://example.org/{key}"
            for key in (
                "google_play_reports",
                "apple_agreement",
                "microsoft_agreement",
            )
        },
        "google_play": {
            "listing_milestone": "1K+",
            "milestone_date": "2026-11-26",
        },
    }
    source = dict(
        id="flathub",
        name="Flathub",
        url="https://example.org/source",
        total=100,
        monthly=50,
        through="2026-10-31",
        monthlyStart="2026-10-02",
        monthlyEnd="2026-10-31",
        stale=True,
    )
    source["from"] = "2026-09-01"
    downloads = {
        "sources": [source],
        "start": source["monthlyStart"],
        "end": source["monthlyEnd"],
        "monthly": 50,
        "total": 100,
        "monthlyRetainedReason": "Waiting for a complete window.",
    }
    store = {
        "status": "stale",
        "total": 800,
        "from": "2026-01-01",
        "through": "2026-10-30",
        "missingDays": 5,
    }
    text = render_details(downloads, store, config)
    for value in (
        "100 reported downloads",
        "50 downloads over 30 days",
        "2026-10-02 to 2026-10-31",
        "800",
        "Last successful report",
        "Last available report",
        "Waiting for a complete window.",
        "5 dates",
        "Apple App Store",
        "Microsoft Store",
        "TestFlight",
        "Obtainium",
        "Device upgrades",
        "1K+ downloads",
        "2026-11-26",
        "https://example.org/google",
        "https://example.org/source",
        "Example app",
    ):
        assert value in text
    section = text.split("## Distribution links\n\n", 1)[1].split("\n\n", 1)[0]
    assert section.splitlines() == [
        "- **Sandbox platform** — [scoop](https://example.org/scoop), "
        "[Flathub](https://example.org/flathub).",
        "- **Second platform** — [google](https://example.org/google).",
    ]
