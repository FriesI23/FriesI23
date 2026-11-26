"""Collect public metrics and render the README badges."""

import re
from concurrent.futures import ThreadPoolExecutor

from github import Github

from .formatting import (
    compact,
    download_color,
    validate_count,
    validate_version,
    version_badge,
)


def _release_tag(release):
    if release.draft or release.prerelease:
        raise ValueError("unexpected draft or prerelease")
    return release.tag_name


def _flathub_version(data):
    def timestamp(release):
        raw = str(release["timestamp"])
        if not re.fullmatch(r"[0-9]+", raw):
            raise ValueError("invalid release timestamp")
        return int(raw)

    return max(data["releases"], key=timestamp)["version"]


def _collect_stars(user, repositories):
    wanted = set(repositories)
    stars = {}
    if not wanted:
        return stars
    for repo in user.get_repos(type="owner", sort="full_name"):
        if repo.name in wanted:
            stars[repo.name] = repo.stargazers_count
            if len(stars) == len(wanted):
                break
    return stars


def _directory_count(entries, extension):
    if not isinstance(entries, list) or len(entries) >= 1000:
        raise ValueError("incomplete GitHub directory listing")
    return sum(
        entry.type == "file" and entry.name.endswith(extension)
        for entry in entries
    )


def collect_metrics(
    *, config, previous, github: Github, fetch_json, render, write_svg
):
    """Return the new snapshot and warnings about retained metrics."""
    previous = previous or {}
    warnings = []
    state = {
        key: {}
        for key in (
            "stars",
            "pubVersions",
            "pubLikes",
            "pubDownloads",
            "directories",
        )
    }
    pub = config["urls"]["pub_api"].rstrip("/")
    flathub = config["urls"]["flathub_api"].rstrip("/")
    owner = config["profile"]["owner"]
    user = github.get_user(owner, lazy=True)
    app = config["app"]
    projects = {project["id"]: project for project in config["projects"]}
    repositories = [p["repo"] for p in projects.values() if p.get("stars")]
    packages = [
        p.get("pub", p["repo"])
        for p in projects.values()
        if p["kind"] == "dart"
    ]
    app_repo = app["repo"]
    app_id = app["package_id"]

    def read(name, load, fallback, validate=validate_count):
        try:
            return validate(load())
        except Exception as exc:
            try:
                retained = validate(fallback)
            except (ValueError, TypeError):
                raise ValueError(
                    f"{name}: {exc} (no valid previous value)"
                ) from exc
            warnings.append(f"{name}: {exc}")
            return retained

    def emit(name, label, message, color="blue"):
        write_svg(f"profile/badges/{name}.svg", render(label, message, color))

    # Fetch in parallel, then render in configuration order.
    # The two metrics from each score response share one request.
    with ThreadPoolExecutor(max_workers=6) as pool:
        stars = pool.submit(_collect_stars, user, repositories)
        versions = {
            pkg: pool.submit(fetch_json, f"{pub}/packages/{pkg}")
            for pkg in packages
        }
        scores = {
            pkg: pool.submit(fetch_json, f"{pub}/packages/{pkg}/score")
            for pkg in packages
        }
        for repo in repositories:
            value = read(
                f"{repo} stars",
                lambda: stars.result()[repo],
                previous.get("stars", {}).get(repo),
            )
            state["stars"][repo] = value
            emit(f"{repo}-stars", "stars", str(value))
        for pkg in packages:
            version = read(
                f"{pkg} version",
                lambda: versions[pkg].result()["latest"]["version"],
                previous.get("pubVersions", {}).get(pkg),
                validate_version,
            )
            likes = read(
                f"{pkg} likes",
                lambda: scores[pkg].result()["likeCount"],
                previous.get("pubLikes", {}).get(pkg),
            )
            downloads = read(
                f"{pkg} downloads",
                lambda: scores[pkg].result()["downloadCount30Days"],
                previous.get("pubDownloads", {}).get(pkg),
            )
            state["pubVersions"][pkg] = version
            state["pubLikes"][pkg] = likes
            state["pubDownloads"][pkg] = downloads
            emit(f"{pkg}-pub", "pub", *version_badge(version))
            emit(f"{pkg}-likes", "likes", compact(likes))
            emit(
                f"{pkg}-downloads",
                "downloads / 30d",
                compact(downloads),
                download_color(downloads),
            )

    for directory in config["directories"]:
        name = directory["badge"]
        repo = projects[directory["project"]]["repo"]
        repository = github.get_repo(f"{owner}/{repo}")
        value = read(
            name,
            lambda: _directory_count(
                repository.get_contents(directory["path"]),
                directory["extension"],
            ),
            previous.get("directories", {}).get(name),
        )
        state["directories"][name] = value
        emit(name, directory["label"], compact(value), directory["color"])

    state["followers"] = read(
        "followers",
        lambda: user.followers,
        previous.get("followers"),
    )
    emit("followers", "Followers", compact(state["followers"]))
    state["release"] = read(
        f"{app_repo} release",
        lambda: _release_tag(
            github.get_repo(f"{owner}/{app_repo}").get_latest_release()
        ),
        previous.get("release"),
        validate_version,
    )
    emit(f"{app_repo}-release", "release", *version_badge(state["release"]))
    state["flathubVersion"] = read(
        "Flathub version",
        lambda: _flathub_version(fetch_json(f"{flathub}/appstream/{app_id}")),
        previous.get("flathubVersion"),
        validate_version,
    )
    emit("flathub-version", "flathub", *version_badge(state["flathubVersion"]))
    state["flathubInstalls"] = read(
        "Flathub installs",
        lambda: fetch_json(config["urls"]["flathub_summary"])[
            "installs_total"
        ],
        previous.get("flathubInstalls"),
    )
    emit(
        "flathub-installs",
        "installs",
        compact(state["flathubInstalls"]),
        download_color(state["flathubInstalls"]),
    )

    return state, warnings
