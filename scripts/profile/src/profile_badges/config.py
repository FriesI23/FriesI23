"""Load the catalog and resolve project and channel references."""

import re
import tomllib
from pathlib import Path

CATALOG = Path("scripts/profile/pyproject.toml")


def repository_root():
    for directory in (Path.cwd(), *Path.cwd().parents):
        if (directory / CATALOG).is_file():
            return directory
    raise ValueError(
        "Run from the profile repository or supply --root "
        f"(expected {CATALOG})"
    )


def load_config(root):
    with (root / CATALOG).open("rb") as source:
        config = tomllib.load(source)["tool"]["profile-badges"]
    projects = {}
    owner = config["profile"]["owner"]
    for project in config["projects"]:
        key = project["id"]
        if key in projects or not re.fullmatch(r"[\w.-]+", key):
            raise ValueError(f"Duplicate or invalid project ID: {key}")
        projects[key] = project
        repo = project.setdefault("repo", key)
        project.setdefault("url", f"https://github.com/{owner}/{repo}")
        project.setdefault("stars", project["kind"] != "github")

    app = config["app"]
    featured = projects[app["project"]]
    if featured["kind"] != "app":
        raise ValueError("Select the app project in [app].project")
    app.update(name=featured["name"], repo=featured["repo"])
    substitutions = {
        "owner": owner,
        "repo": app["repo"],
        "package_id": app["package_id"],
        "app_name": app["name"],
    }
    extensions = [ext.lstrip(".") for ext in app["asset_extensions"]]
    substitutions["extensions"] = (
        ", ".join(extensions[:-1]) + " and " + extensions[-1]
        if len(extensions) > 1
        else extensions[0]
    )
    # Resolve the daily archive date when fetching each report.
    substitutions["datepath"] = "{datepath}"
    for key, url in config["urls"].items():
        config["urls"][key] = url.format_map(substitutions)
    flathub_api = config["urls"]["flathub_api"].rstrip("/")
    config["urls"]["flathub_summary"] = (
        f"{flathub_api}/stats/{app['package_id']}?days=7"
    )
    substitutions.update(config["urls"])
    for project in projects.values():
        for key in ("name", "url"):
            project[key] = project[key].format_map(substitutions)
    for channel in config["channels"].values():
        if "project" in channel:
            channel["url"] = projects[channel["project"]]["url"]
        for key in ("url", "listing_url", "note"):
            if key in channel:
                channel[key] = channel[key].format_map(substitutions)

    days = config["downloads"]["period_days"]
    if days < 1 or days > config["downloads"]["flathub_cache_days"]:
        raise ValueError(
            "Download period must fit within the Flathub daily cache"
        )
    if config["profile"]["pub_downloads_threshold"] < 0:
        raise ValueError("Download threshold must be nonnegative")
    return config
