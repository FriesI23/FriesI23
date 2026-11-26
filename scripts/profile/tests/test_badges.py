from urllib.parse import parse_qs, urlsplit

import pytest
from github_stub import github_with_responses

from profile_badges.badges import (
    compact,
    download_color,
    generate_badges,
    valid_trophy,
)

TROPHY = (
    '<svg xmlns="http://www.w3.org/2000/svg">'
    '<path d="M1 1h1"/><text>23pt</text></svg>'
)


class BadgeSources:
    def __init__(self, root):
        self.root = root
        self.written = {}
        self.requests = []
        self.trophy_urls = []
        self.config = {
            "profile": {"owner": "Owner"},
            "app": {"repo": "habit", "package_id": "example.habit"},
            "urls": {
                "github_api": "https://github.example",
                "pub_api": "https://pub.example/api",
                "flathub_api": "https://flat.example/api/v2",
                "flathub_summary": (
                    "https://flat.example/api/v2/stats/example.habit?days=7"
                ),
            },
            "projects": [
                {
                    "id": "tracker",
                    "name": "Habit",
                    "repo": "habit",
                    "kind": "app",
                    "stars": True,
                },
                {
                    "id": "ios_layout",
                    "name": "iOS Layout",
                    "repo": "layout-repo",
                    "kind": "dart",
                    "pub": "ios_layout",
                    "stars": True,
                },
                {
                    "id": "pkg2",
                    "name": "Another package",
                    "repo": "another",
                    "kind": "dart",
                },
                {
                    "id": "tap",
                    "name": "Tap",
                    "repo": "homebrew-tap",
                    "kind": "github",
                },
            ],
            "directories": [
                {
                    "project": "tap",
                    "badge": "cask",
                    "path": "Casks",
                    "extension": ".rb",
                    "label": "cask",
                    "color": "#fbb040",
                }
            ],
            "trophy": {
                "url": "https://trophy.example/",
                "row": 3,
                "column": 5,
                "rank": "SECRET,CSSS,SS,S",
                "dark_theme": "darkhub",
            },
        }

    def fetch(self, url):
        self.requests.append(url)
        parsed = urlsplit(url)
        path = parsed.path
        if parsed.hostname == "pub.example":
            if path.endswith("/score"):
                return {"likeCount": 2, "downloadCount30Days": 3603}
            return {"latest": {"version": "0.6.0"}}
        if parsed.hostname == "flat.example":
            if "/stats/" in path:
                return {"installs_total": 6851}
            return {
                "releases": [
                    {"timestamp": "9", "version": "1.0.0"},
                    {"timestamp": "10", "version": "1.1.0"},
                ]
            }
        if path == "/users/Owner/repos":
            if "page" not in parse_qs(parsed.query):
                return [
                    {"name": "habit", "stargazers_count": 1716}
                ], url + "&page=2"
            return [{"name": "layout-repo", "stargazers_count": 3}]
        if path == "/repos/Owner/homebrew-tap/contents/Casks":
            return [
                {"type": "dir", "name": "skip.rb"},
                {"type": "file", "name": "one.rb"},
                {"type": "file", "name": "skip.md"},
            ]
        if path == "/repos/Owner/habit/releases/latest":
            return {
                "draft": False,
                "prerelease": False,
                "tag_name": "v1.27.24+213",
            }
        if path == "/users/Owner":
            return {"followers": 77}
        raise AssertionError(f"Unexpected request {url}")

    def trophy(self, url):
        self.trophy_urls.append(url)
        return TROPHY

    def generate(self, *, previous=None, fetch=None, trophy=None):
        return generate_badges(
            root=self.root,
            config=self.config,
            previous=previous,
            github=github_with_responses(
                self.config["urls"]["github_api"], fetch or self.fetch
            ),
            fetch_json=fetch or self.fetch,
            render=lambda *parts: parts,
            write_svg=self.written.__setitem__,
            download_svg=trophy or self.trophy,
        )


@pytest.fixture
def source(tmp_path):
    return BadgeSources(tmp_path)


def test_config_drives_sources_and_badges(source):
    state, warnings = source.generate()
    assert warnings == []
    assert state["stars"] == {"habit": 1716, "layout-repo": 3}
    assert state["pubDownloads"] == {"ios_layout": 3603, "another": 3603}
    assert sum("/users/Owner/repos?" in url for url in source.requests) == 2
    assert (
        sum(
            url.startswith("https://github.example/")
            for url in source.requests
        )
        == 5
    )
    assert (
        sum(url.endswith("/ios_layout/score") for url in source.requests) == 1
    )
    expected = {
        "habit-stars": ("stars", "1716", "blue"),
        "ios_layout-downloads": ("downloads / 30d", "3.6k", "brightgreen"),
        "ios_layout-pub": ("pub", "v0.6.0", "orange"),
        "habit-release": ("release", "v1.27.24+213", "blue"),
        "flathub-version": ("flathub", "v1.1.0", "blue"),
        "flathub-installs": ("installs", "6.9k", "brightgreen"),
        "cask": ("cask", "1", "#fbb040"),
    }
    for stem, badge in expected.items():
        assert source.written[f"profile/badges/{stem}.svg"] == badge
    for theme, url in zip(("light", "dark"), source.trophy_urls, strict=True):
        assert source.written[f"profile/trophies/{theme}.svg"] == TROPHY
        params = parse_qs(urlsplit(url).query)
        assert params["rank"] == ["SECRET,CSSS,SS,S"]
        assert params.get("theme") == (
            ["darkhub"] if theme == "dark" else None
        )
        assert params["username"] == ["owner"]


def test_retains_failed_metrics_individually(source):
    previous, _ = source.generate()
    for theme in ("dark", "light"):
        path = source.root / "profile" / "trophies" / f"{theme}.svg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TROPHY, encoding="utf-8")

    def limited(url):
        if url.endswith("/ios_layout/score"):
            return {"likeCount": 0, "downloadCount30Days": None}
        if "/users/Owner/repos?" in url:
            raise OSError("unavailable")
        return source.fetch(url)

    source.written.clear()
    state, warnings = source.generate(
        previous=previous, fetch=limited, trophy=lambda _: "<svg>error</svg>"
    )
    assert state["stars"] == previous["stars"]
    assert state["pubLikes"]["ios_layout"] == 0
    assert state["pubDownloads"]["ios_layout"] == 3603
    assert "ios_layout downloads: missing or invalid count" in warnings
    assert "profile/trophies/dark.svg" not in source.written


def test_missing_initial_metrics_or_trophies_abort(source):
    with pytest.raises(ValueError, match="no valid previous value"):
        source.generate(fetch=lambda _: [])
    with pytest.raises(ValueError, match="no valid artwork available"):
        source.generate(trophy=lambda _: "<svg/>")


def test_trophy_requires_self_contained_artwork():
    assert valid_trophy(TROPHY)
    for source in [
        "<html>502 Bad Gateway</html>",
        "<svg/>",
        TROPHY.replace("23pt", "Service unavailable"),
        TROPHY.replace("<path", "<script/><path"),
        TROPHY.replace(
            "<path", '<image href="https://example.org/image"/><path'
        ),
    ]:
        assert not valid_trophy(source)


def test_count_notation_and_colors():
    for value, expected in [
        (0, "0"),
        (999, "999"),
        (1000, "1k"),
        (1001, "1k"),
        (2550, "2.5k"),
        (1250, "1.3k"),
        (3603, "3.6k"),
        (9_007_199_254_740_991, "9P"),
        (10500, "11k"),
        (999500, "1M"),
        (1850000, "1.9M"),
    ]:
        assert compact(value) == expected
    for value, expected in [
        (0, "red"),
        (1, "yellow"),
        (10, "yellowgreen"),
        (100, "green"),
        (1000, "brightgreen"),
    ]:
        assert download_color(value) == expected
