# Refreshing the profile

The **update readme cards** workflow refreshes the profile daily and supports manual dispatch. It publishes the project table, badge SVGs, metric snapshots and distribution report together.

Edit the `tool.profile-badges` section of [pyproject.toml](pyproject.toml) to change the catalog. The order of `[[tool.profile-badges.projects]]` sets the README row order. For a Dart package, set `id`, `name` and `kind = "dart"`. The repository and pub.dev package names default to the ID. Use `repo` or `pub` when they differ. The generator uses this same entry to collect metrics and render the row. The README outside the project table markers is hand-editable.

`profile.pub_downloads_threshold` controls when a package displays its 30-day download badge. The app report uses `downloads.period_days` for its aligned daily window and publishes cumulative totals separately. Within that section, `channels` and `distribution` define the store links and platform groups. The `directories` entries define repository file counts. Generated JSON in `profile/metrics/` is the last successful source data used on retries.

## Local development

From the repository root, use Poetry 2 and Python 3.11 or newer. The workflow runs Python 3.13. PyGithub uses `GH_TOKEN`, `GITHUB_TOKEN`, or your existing GitHub CLI login. Public requests also work anonymously within GitHub’s rate limit.

```sh
cd scripts/profile
poetry install --with test
poetry run pytest
poetry run profile-badges generate
```

The project follows the PEP 8 line limits of 79 characters for code and 72 for comments and docstrings. VS Code uses Ruff for Python in this workspace. Select the Poetry interpreter to use the locked version.

To sort imports and format all Python files, run these commands from `scripts/profile`. The workflow checks formatting and line lengths before running pytest.

```sh
poetry run ruff check --select I --fix .
poetry run ruff format .
```

The generator reads GitHub data with PyGithub and public JSON feeds with HTTPX. It renders badge SVGs offline with badgepy and formats the distribution report with Jinja.

To follow a download refresh, start at `collect_downloads` in the public module. The internal package contains the reporting window logic and one module per platform. [Downloads entry point](src/profile_badges/downloads.py) · [Download sources](src/profile_badges/_downloads/)

For badges, `generate_badges` coordinates metric collection and trophy updates. The internal modules handle those steps and format badge labels. [Badge entry point](src/profile_badges/badges.py) · [Badge implementation](src/profile_badges/_badges/)

## Google Play

To include device installs and upgrades from Play Console, set these GitHub Actions repository variables.

| Variable | Value |
| --- | --- |
| `GOOGLE_PLAY_REPORTS_BUCKET` | Play Console reporting bucket name, beginning with `pubsite_prod_rev_` |
| `GOOGLE_PLAY_IDENTITY_PROVIDER` | Full resource name of the Google Cloud Workload Identity Federation provider |
| `GOOGLE_PLAY_SERVICE_ACCOUNT` | Service account email with access to the Play Console bulk reports |

Configure the provider to trust the workflow on this repository's `master` branch and allow it to impersonate the reporting account. The separate Google Play job uses the Google Cloud Storage SDK with a short-lived token scoped to `devstorage.read_only`. Its output contains only project-level summaries and report revision fingerprints. [GitHub Actions authentication](https://github.com/google-github-actions/auth#workload-identity-federation-through-a-service-account) · [Play Console reporting access](https://support.google.com/googleplay/android-developer/answer/6135870?hl=en)
