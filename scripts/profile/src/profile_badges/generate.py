"""Build public artifacts from one consistent set of metrics."""

import json
import os
import re
import tempfile
from functools import cache
from pathlib import Path
from xml.etree import ElementTree

from .badges import compact, generate_badges
from .details import render_details
from .downloads import collect_downloads
from .readme import render_readme, report_path
from .stores import collect_store_installs
from .svg import render

METRICS = Path("profile/metrics")


def load_state(root, name):
    path = root / METRICS / (name + ".json")
    return json.loads(path.read_bytes()) if path.is_file() else {}


def _json(data):
    return (
        json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    )


def _write_changed(path, content):
    if path.is_file() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as temp:
        try:
            temp.write(content)
            temp.close()
            os.chmod(temp.name, 0o644)
            os.replace(temp.name, path)
        finally:
            Path(temp.name).unlink(missing_ok=True)
    return True


def generate(root, config, *, github, http, store_result=None, store_job=None):
    def read_json(url):
        return http.get(url).raise_for_status().json()

    # Cache the shared summary. Release daily archives after use.
    flathub_summary = cache(read_json)

    def fetch_json(url):
        if url == config["urls"]["flathub_summary"]:
            return flathub_summary(url)
        return read_json(url)

    pending = {}
    badges, warnings = generate_badges(
        root=root,
        config=config,
        previous=load_state(root, "badges"),
        github=github,
        fetch_json=fetch_json,
        render=render,
        write_svg=pending.__setitem__,
        download_svg=lambda url: http.get(url).raise_for_status().text,
    )
    downloads, download_warnings = collect_downloads(
        load_state(root, "downloads"),
        config=config,
        github=github,
        fetch_json=fetch_json,
    )
    if store_result is None:
        stores, store_warnings = collect_store_installs(
            load_state(root, "google-play"), config=config
        )
        if store_job == "failure":
            if stores["status"] == "unconfigured":
                stores["status"] = "unavailable"
            store_warnings.append(
                "Google Play collection job failed. See the workflow run."
            )
    else:
        stores, store_warnings = (
            store_result["state"],
            store_result["warnings"],
        )
    warnings.extend(download_warnings)
    warnings.extend(store_warnings)

    period = f"{config['downloads']['period_days']}d"
    repo = config["app"]["repo"]
    for label, count in (
        (period, downloads["monthly"]),
        ("total", downloads["total"]),
    ):
        pending[f"profile/badges/{repo}-downloads-{label}.svg"] = render(
            f"downloads / {label}",
            compact(count),
            "brightgreen",
        )
    for name, state in (
        ("badges", badges),
        ("downloads", downloads),
        ("google-play", stores),
    ):
        pending[str(METRICS / (name + ".json"))] = _json(state)
    pending[report_path(config)] = render_details(downloads, stores, config)
    readme = render_readme(
        (root / "README.md").read_text(encoding="utf-8"),
        config,
        badges["pubDownloads"],
    )
    pending["README.md"] = readme

    # Validate every asset before writing, including vendored logos
    # and trophies retained from a previous run.
    assets = set(
        re.findall(
            r"profile/(?:badges/(?:static/)?|trophies/)[\w.-]+\.svg", readme
        )
    )
    for name in assets.union(
        name for name in pending if name.endswith(".svg")
    ):
        svg = (
            pending[name]
            if name in pending
            else (root / name).read_text(encoding="utf-8")
        )
        if (
            ElementTree.fromstring(svg).tag
            != "{http://www.w3.org/2000/svg}svg"
        ):
            raise ValueError(f"Invalid profile asset: {name}")
    return sum(
        _write_changed(root / name, content)
        for name, content in pending.items()
    ), warnings
