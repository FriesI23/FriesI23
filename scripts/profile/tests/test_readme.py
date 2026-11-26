from pathlib import Path

import pytest

from profile_badges.config import CATALOG, load_config
from profile_badges.readme import END, START, render_readme


def test_one_catalog_entry_drives_project_row_and_metric_names(tmp_path):
    catalog = tmp_path / CATALOG
    catalog.parent.mkdir(parents=True)
    original = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text()
    catalog.write_text(
        original
        + """
[[tool.profile-badges.projects]]
id = "fixture"
repo = "sample-repo"
pub = "sample_package"
kind = "dart"
name = "Sample package"
"""
    )
    config = load_config(tmp_path)
    pkg = config["projects"][-1]
    assert pkg["stars"] and pkg["repo"] == "sample-repo"
    scores = {
        p.get("pub", p["repo"]): 0
        for p in config["projects"]
        if p["kind"] == "dart"
    }
    threshold = config["profile"]["pub_downloads_threshold"]
    scores["sample_package"] = threshold
    manual = (
        f"Handwritten intro\n\n{START}\nold rows\n"
        f"{END}\n\nHandwritten footer\n"
    )
    readme = render_readme(manual, config, scores)
    row = next(
        line for line in readme.splitlines() if "[Sample package]" in line
    )
    owner = config["profile"]["owner"]
    assert f"[Sample package](https://github.com/{owner}/sample-repo)" in row
    assert (
        "sample_package-downloads.svg" in row
        and "sample-repo-stars.svg" in row
    )
    assert readme.startswith(manual.split(START)[0]) and readme.endswith(
        manual.split(END)[1]
    )
    assert readme == render_readme(readme, config, scores)
    config["profile"]["pub_downloads_threshold"] += 1
    assert "sample_package-downloads.svg" not in render_readme(
        readme, config, scores
    )
    config["projects"].pop()
    assert "Sample package" not in render_readme(readme, config, scores)


@pytest.mark.parametrize(
    "original", ["handwritten", END + START, START + END * 2]
)
def test_refuse_ambiguous_managed_region(original):
    with pytest.raises(ValueError):
        render_readme(original, {}, {})
