"""Generate profile badge assets and format their values."""

from pathlib import Path

from github import Github

from ._badges.formatting import compact, download_color
from ._badges.metrics import collect_metrics
from ._badges.trophies import update_trophies, valid_trophy

__all__ = ["compact", "download_color", "generate_badges", "valid_trophy"]


def generate_badges(
    *,
    root: Path,
    config,
    previous,
    github: Github,
    fetch_json,
    render,
    write_svg,
    download_svg,
):
    """Return the new snapshot and warnings about retained assets."""
    state, warnings = collect_metrics(
        config=config,
        previous=previous,
        github=github,
        fetch_json=fetch_json,
        render=render,
        write_svg=write_svg,
    )
    warnings.extend(
        update_trophies(
            root=root,
            trophy=config["trophy"],
            owner=config["profile"]["owner"],
            download_svg=download_svg,
            write_svg=write_svg,
        )
    )
    return state, warnings
