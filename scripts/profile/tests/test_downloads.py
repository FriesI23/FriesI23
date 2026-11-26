from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from github_stub import github_with_responses

from profile_badges.downloads import collect_downloads

APP = "org.example.paperplane"
TODAY = date(2026, 3, 5)
CONFIG = {
    "profile": {"owner": "example-labs"},
    "app": {
        "repo": "paper-plane",
        "package_id": APP,
        "asset_extensions": [".bundle"],
    },
    "downloads": {
        "period_days": 30,
        "flathub_cache_days": 93,
        "flathub_reseed_days": 14,
        "stale_days": 7,
        "fdroid_stale_days": 14,
        "izzy_first_day": "2024-12-08",
    },
    "urls": {
        "github_api": "https://releases.example",
        "izzy_api": "https://android.example/downloads",
        "flathub_summary": (
            f"https://flatpak.example/api/v2/stats/{APP}?days=7"
        ),
        "flathub_daily": "https://flatpak.example/stats/{datepath}.json",
        "flathub_history": "https://history.example/apps/{package_id}.json",
        "fdroid_weeks": "https://weeks.example/reports/{package_id}.json",
    },
    "channels": {
        key: {"name": name, "url": f"https://example.org/{key}"}
        for key, name in [
            ("github", "Example releases"),
            ("izzy", "Example Android downloads"),
            ("flathub", "Example Flatpak downloads"),
            ("fdroid", "Example weekly reports"),
        ]
    },
}


def dates(start, end):
    day = date.fromisoformat(start)
    while day.isoformat() <= end:
        yield day.isoformat()
        day += timedelta(days=1)


class Feeds:
    def __init__(
        self,
        *,
        izzy_end="2026-03-02",
        flat_end="2026-03-03",
        broken="",
        omit="",
        history_omit="",
        raw_zero="",
        izzy_by_day=None,
        flat_by_day=None,
        assets=None,
        weeks=None,
    ):
        self.calls = []
        self.izzy_end = izzy_end
        self.flat_end = flat_end
        self.broken = broken
        self.raw_zero = raw_zero
        self.flat_by_day = flat_by_day or {}
        self.daily = {
            day: {APP: (izzy_by_day or {}).get(day, 13)}
            for day in dates("2025-12-01", izzy_end)
            if day != omit
        }
        self.history = [
            {"date": day.replace("-", "/"), "arches": self.arches(day)}
            for day in dates("2025-12-01", flat_end)
            if day != history_omit
        ]
        self.assets = (
            assets
            if assets is not None
            else [
                {
                    "id": 50,
                    "name": "release.bundle",
                    "created_at": "2025-01-01T10:00:00Z",
                    "download_count": 150,
                }
            ]
        )
        self.weeks = weeks or {"2025-01-06": 47, "2025-01-13": 13}

    def arches(self, day, official=False):
        if day in self.flat_by_day:
            return {"x86_64": self.flat_by_day[day]}
        return {"x86_64": [6, 4] if official else [5, 3], "aarch64": [3, 1]}

    def __call__(self, url):
        self.calls.append(url)
        if self.broken and self.broken in url:
            raise OSError("Source unavailable")
        parsed = urlsplit(url)
        if parsed.hostname == "releases.example":
            if parse_qs(parsed.query).get("page") == ["2"]:
                return [{"draft": False, "assets": self.assets}]
            return [
                {
                    "draft": False,
                    "assets": [
                        {
                            "id": 80,
                            "name": "release.bundle.sha256",
                            "download_count": 99,
                        }
                    ],
                },
                {"draft": True, "assets": self.assets},
            ], url + "&page=2"
        if parsed.hostname == "weeks.example":
            return self.weeks
        if parsed.hostname == "history.example":
            return {"ref": APP, "stats": self.history}
        if parsed.hostname == "flatpak.example":
            if parsed.path.startswith("/api/"):
                return {"installs_per_day": {self.flat_end: 4}}
            day = parsed.path.removeprefix("/stats/").removesuffix(".json")
            iso = day.replace("/", "-")
            key = "org.other.App" if iso == self.raw_zero else APP
            return {"date": day, "refs": {key: self.arches(iso, True)}}
        if "/daily/rolling" in parsed.path:
            return {self.izzy_end: self.daily[self.izzy_end]}
        if "/yearly/" in parsed.path:
            return (
                {"example": 12}
                if parsed.path.endswith("/2024.json")
                else {APP: 700}
            )
        if "/monthly-in-days/" in parsed.path:
            month = parsed.path.rsplit("/", 1)[-1].removesuffix(".json")
            return {
                day: value
                for day, value in self.daily.items()
                if day.startswith(month)
            }
        raise ValueError(f"Unexpected URL: {url}")

    def collect(self, previous=None, today=TODAY, config=CONFIG):
        github = github_with_responses(config["urls"]["github_api"], self)
        return collect_downloads(
            previous,
            config=config,
            github=github,
            fetch_json=self,
            today=today,
        )


def source(state, key):
    return next(item for item in state["sources"] if item["id"] == key)


def window(state):
    return state["start"], state["end"], state["monthly"]


def test_all_release_pages_and_aligned_daily_window():
    feeds = Feeds()
    state, warnings = feeds.collect()
    assert not warnings
    assert source(state, "github")["total"] == 150
    assert source(state, "github")["monthly"] is None
    assert source(state, "fdroid")["total"] == 60
    assert source(state, "fdroid")["through"] == "2025-01-19"
    assert source(state, "fdroid")["stale"]
    assert source(state, "izzy")["total"] == 1400
    assert window(state) == ("2026-02-01", "2026-03-02", 30 * (8 + 13) + 1)
    assert source(state, "flathub")["monthly"] == 30 * 8 + 1
    assert state["total"] == sum(item["total"] for item in state["sources"])
    assert (
        sum(url.startswith("https://releases.example/") for url in feeds.calls)
        == 2
    )
    assert any(url.endswith("page=2") for url in feeds.calls)
    assert sum("flatpak.example/stats/" in url for url in feeds.calls) == 2


def test_idempotent_reruns_and_replaced_assets():
    state, _ = Feeds().collect()
    again = Feeds()
    assert again.collect(state)[0] == state
    assert not any("history.example" in url for url in again.calls)
    assert sum("/yearly/" in url for url in again.calls) == 1
    assert sum("/monthly-in-days/" in url for url in again.calls) == 2
    newer = Feeds(
        assets=[
            {
                "id": 51,
                "name": "replacement.bundle",
                "created_at": "2026-03-05",
                "download_count": 34,
            }
        ]
    )
    updated, _ = newer.collect(state)
    assert source(updated, "github")["total"] == 184
    assert source(updated, "github")["monthly"] is None
    assert "51" not in state["cache"]["github"]["assets"]


def test_monthly_failure_retains_counts_and_updates_healthy_cache():
    state, _ = Feeds().collect()
    feeds = Feeds(broken="/daily/rolling", flat_end="2026-03-04")
    updated, warnings = feeds.collect(state)
    assert any("Example Android downloads" in message for message in warnings)
    assert source(updated, "izzy")["stale"]
    assert source(updated, "izzy")["total"] == source(state, "izzy")["total"]
    assert window(updated) == window(state)
    for key in ("monthly", "total", "through"):
        assert source(updated, "flathub")[key] == source(state, "flathub")[key]
    assert updated["total"] == state["total"]
    assert (
        updated["cache"]["flathub"]["total"]
        > source(state, "flathub")["total"]
    )
    assert updated["totalRetainedReason"] and updated["monthlyRetainedReason"]
    with pytest.raises(ValueError, match="Initial download collection failed"):
        feeds.collect()


def test_rejects_incomplete_initial_window():
    with pytest.raises(ValueError, match="Incomplete daily"):
        Feeds(omit="2026-02-15").collect()


def test_truncated_archive_cannot_overwrite_previous_total():
    state, _ = Feeds().collect()
    updated, warnings = Feeds(
        weeks={"2025-01-13": 13, "2025-01-20": 17}
    ).collect(state)
    assert updated["total"] == state["total"]
    assert (
        source(updated, "fdroid")["through"]
        == source(state, "fdroid")["through"]
    )
    assert any(
        "lost previously covered weeks" in warning for warning in warnings
    )


def test_cumulative_source_failure_allows_complete_monthly_window_to_advance():
    state, _ = Feeds().collect()
    options = {"izzy_end": "2026-03-03", "flat_end": "2026-03-04"}
    updated, _ = Feeds(**options, broken="releases.example").collect(state)
    assert updated["total"] == state["total"]
    assert (
        source(updated, "flathub")["through"]
        == source(state, "flathub")["through"]
    )
    assert source(updated, "github")["stale"]
    assert updated["end"] == "2026-03-03"
    assert source(updated, "izzy")["monthlyEnd"] == updated["end"]
    assert (
        updated["totalRetainedReason"]
        and updated["monthlyRetainedReason"] is None
    )
    recovered, _ = Feeds(**options).collect(updated)
    assert recovered["total"] > updated["total"]
    assert recovered["totalRetainedReason"] is None
    assert source(recovered, "flathub")["through"] == options["flat_end"]


@pytest.mark.parametrize(
    "fields,valid",
    [
        ({}, False),
        ({"assets": None}, False),
        ({"assets": [{}]}, False),
        ({"assets": []}, True),
    ],
)
def test_partial_release_response_keeps_previous_snapshot(fields, valid):
    previous, _ = Feeds().collect()
    release_url = (
        "https://releases.example/repos/example-labs/paper-plane/releases/42"
    )
    release = {"url": release_url, "draft": False, **fields}

    class PartialRelease(Feeds):
        def __call__(self, url):
            if url == release_url:
                # The SDK can retry by loading the release.
                return release
            result = super().__call__(url)
            if url.endswith("page=2"):
                return [*result, release]
            return result

    state, warnings = PartialRelease().collect(previous)
    assert state["cache"]["github"] == previous["cache"]["github"]
    assert source(state, "github")["stale"] is (not valid)
    assert bool(warnings) is (not valid)
    if not valid:
        with pytest.raises(
            ValueError, match="Initial download collection failed"
        ):
            PartialRelease().collect()


def test_missing_flathub_archive_day_requires_a_published_official_report():
    gap = "2026-03-02"
    options = {"flat_end": "2026-03-05", "history_omit": gap}
    state, _ = Feeds(**options, izzy_end="2026-03-01").collect()
    retained, _ = Feeds(**options, broken="/2026/03/02.json").collect(state)
    assert retained["monthlyRetainedReason"] and window(retained) == window(
        state
    )
    assert gap not in retained["cache"]["flathub"]["daily"]
    zero, _ = Feeds(**options, raw_zero=gap).collect(retained)
    assert zero["monthlyRetainedReason"] is None
    assert zero["end"] == gap
    assert zero["cache"]["flathub"]["daily"][gap] == 0
    actual, _ = Feeds(**options).collect(retained)
    assert actual["cache"]["flathub"]["daily"][gap] == 9
    assert actual["total"] == zero["total"] + 9
    assert actual["monthly"] == zero["monthly"] + 9


def test_invalid_window_total_keeps_flathub_history_correction():
    gap = "2026-03-02"
    options = {"flat_end": "2026-03-05", "history_omit": gap}
    previous, _ = Feeds(**options, izzy_end="2026-03-01").collect()
    feeds = Feeds(
        **options,
        izzy_end=gap,
        izzy_by_day={"2026-02-10": 2**52, "2026-02-11": 2**52},
    )
    updated, _ = feeds.collect(previous)
    assert window(updated) == window(previous)
    assert "Invalid download count" in updated["monthlyRetainedReason"]
    assert updated["cache"]["flathub"]["daily"][gap] == 9
    assert updated["total"] == previous["total"] + 9


def test_source_reporting_delay_extends_beyond_available_history():
    state, _ = Feeds().collect()
    feeds = Feeds(flat_end="2026-09-03")
    updated, _ = feeds.collect(state, today="2026-09-06")
    assert window(updated) == window(state)
    assert (
        "beyond the available Flathub history"
        in updated["monthlyRetainedReason"]
    )
    assert not any("/monthly-in-days/" in url for url in feeds.calls)


def test_public_snapshot_october_23_to_november_21_2026():
    # The first count in each Flathub pair already includes updates.
    days = list(dates("2026-10-23", "2026-11-21"))
    apk = [
        111,
        107,
        96,
        83,
        82,
        84,
        92,
        68,
        63,
        72,
        224,
        566,
        207,
        149,
        125,
        110,
        76,
        72,
        87,
        77,
        82,
        82,
        116,
        232,
        540,
        191,
        168,
        113,
        90,
        87,
    ]
    flatpak = [
        [46, 41],
        [44, 31],
        [28, 21],
        [35, 24],
        [26, 17],
        [22, 14],
        [15, 6],
        [19, 18],
        [17, 10],
        [27, 15],
        [427, 382],
        [108, 97],
        [56, 52],
        [47, 38],
        [47, 38],
        [35, 27],
        [27, 23],
        [37, 23],
        [29, 19],
        [21, 16],
        [363, 358],
        [112, 107],
        [69, 57],
        [361, 330],
        [206, 185],
        [59, 53],
        [42, 32],
        [36, 21],
        [32, 21],
        [20, 13],
    ]
    feeds = Feeds(
        izzy_end=days[-1],
        flat_end="2026-11-24",
        izzy_by_day=dict(zip(days, apk, strict=True)),
        flat_by_day=dict(zip(days, flatpak, strict=True)),
    )
    state, _ = feeds.collect(today="2026-11-26")
    assert window(state) == ("2026-10-23", "2026-11-21", 6665)
    assert source(state, "izzy")["monthly"] == 4252
    assert source(state, "flathub")["monthly"] == 2413


def test_change_of_window_needs_complete_data_before_replacing_old_values():
    previous, _ = Feeds().collect()
    config = {**CONFIG, "downloads": {**CONFIG["downloads"], "period_days": 7}}
    with pytest.raises(
        ValueError, match="No complete 7-day window is available"
    ):
        Feeds(broken="/daily/rolling").collect(previous, config=config)
    updated, _ = Feeds().collect(previous, config=config)
    assert window(updated) == ("2026-02-24", "2026-03-02", 7 * (13 + 8) + 1)
    retained, _ = Feeds(broken="/daily/rolling").collect(
        updated, config=config
    )
    assert window(updated) == window(retained)
    assert retained["monthlyRetainedReason"]
