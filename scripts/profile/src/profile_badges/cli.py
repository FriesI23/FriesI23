"""Run profile refreshes and Google Play collection."""

import argparse
import json
import logging
import os
import subprocess
from pathlib import Path

import httpx
from github import Auth, Consts, Github

from .config import load_config, repository_root
from .generate import generate, load_state
from .stores import collect_store_installs


def github_client(base_url):
    token = None
    if base_url.rstrip("/") == Consts.DEFAULT_BASE_URL:
        token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
        if not token:
            # Public repositories also allow anonymous access.
            try:
                token = subprocess.check_output(
                    ["gh", "auth", "token", "--hostname", "github.com"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=15,
                ).strip()
            except (OSError, subprocess.SubprocessError):
                pass
    return Github(
        base_url=base_url.rstrip("/"),
        auth=Auth.Token(token) if token else None,
        per_page=100,
        lazy=True,
        timeout=45,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate the GitHub profile badges"
    )
    parser.add_argument(
        "--root", type=Path, help="Path to the profile repository"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "generate", help="Refresh the README, public SVGs and metric snapshots"
    )
    collect = commands.add_parser(
        "google-play", help="Collect aggregate Play Console metrics"
    )
    collect.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    root = args.root.resolve() if args.root else repository_root()
    config = load_config(root)
    if args.command == "google-play":
        state, warnings = collect_store_installs(
            load_state(root, "google-play"),
            config=config,
            access_token=os.getenv("GOOGLE_PLAY_ACCESS_TOKEN"),
            bucket=os.getenv("GOOGLE_PLAY_REPORTS_BUCKET"),
            start_date=config["google_play"].get("start_date", ""),
        )
        args.output.write_text(
            json.dumps({"state": state, "warnings": warnings}),
            encoding="utf-8",
        )
    else:
        summary = os.getenv("PROFILE_STORE_RESULT")
        with (
            github_client(config["urls"]["github_api"]) as github,
            httpx.Client(
                timeout=45,
                follow_redirects=True,
                headers={"User-Agent": "profile-badges"},
            ) as http,
        ):
            changes, warnings = generate(
                root,
                config,
                github=github,
                http=http,
                store_result=json.loads(summary) if summary else None,
                store_job=os.getenv("PROFILE_STORE_JOB"),
            )
        logging.info("Updated %d profile files.", changes)
    for warning in warnings:
        logging.warning("Profile refresh warning: %s", warning)
