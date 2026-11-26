"""Render the catalog inside the README project markers."""

START = "<!-- profile-projects:start -->"
END = "<!-- profile-projects:end -->"


def _badge(name, label, destination=None):
    image = f"![{label}](profile/badges/{name}.svg)"
    return f"[{image}]({destination})" if destination else image


def report_path(config):
    return f"profile/{config['app']['repo']}-downloads.md"


def _project_badges(project, config, pub_downloads):
    repo = project["repo"]
    if project["kind"] == "dart":
        pkg = project.get("pub", repo)
        url = f"https://pub.dev/packages/{pkg}"
        yield _badge(pkg + "-pub", "pub", url)
        yield _badge(pkg + "-likes", "likes", url)
        if pub_downloads[pkg] >= config["profile"]["pub_downloads_threshold"]:
            yield _badge(pkg + "-downloads", "downloads / 30d", url)
    if project["stars"]:
        yield _badge(repo + "-stars", "stars")
    if project["id"] == config["app"]["project"]:
        yield _badge(
            repo + "-release", "release", config["channels"]["github"]["url"]
        )
        for period in (f"{config['downloads']['period_days']}d", "total"):
            yield _badge(
                f"{repo}-downloads-{period}",
                f"downloads / {period}",
                report_path(config),
            )

    link = project.get("badge_link", project["url"])
    for directory in config["directories"]:
        if directory["project"] == project["id"]:
            yield _badge(directory["badge"], directory["label"], link)
    for extra in project.get("extras", []):
        channel = extra.get("channel", "")
        url = (
            config["channels"][channel]["url"]
            if channel
            else extra.get("url", link)
        )
        yield _badge(extra["badge"], extra.get("label", channel), url)


def render_readme(original, config, pub_downloads):
    if original.count(START) != 1 or original.count(END) != 1:
        raise ValueError(
            "Expected one marked profile project table in README.md"
        )
    before, _, managed = original.partition(START)
    if END not in managed:
        raise ValueError("Profile README markers are out of order")
    _, _, after = managed.partition(END)
    rows = ["| Type | Project | Desc |", "| --- | --- | --- |"]
    for project in config["projects"]:
        kind = project["kind"]
        icon = _badge("static/icon-" + kind, kind)
        link = f"[{project['name']}]({project['url']})"
        badges = " ".join(_project_badges(project, config, pub_downloads))
        rows.append(f"| {icon} | {link} | {badges} |")
    return before + START + "\n\n" + "\n".join(rows) + "\n\n" + END + after
