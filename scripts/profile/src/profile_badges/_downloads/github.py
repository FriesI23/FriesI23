"""Count downloads of app release assets on GitHub."""

from .common import count, iso_date, require, sum_counts


def collect(previous, context):
    """Refresh counts by asset ID, including removed assets."""
    owner = context.config["profile"]["owner"]
    app = context.config["app"]
    extensions = tuple(ext.lower() for ext in app["asset_extensions"])
    repository = context.github.get_repo(f"{owner}/{app['repo']}")
    assets = previous.get("assets", {}).copy()
    first = previous.get("from")
    matched = False
    for release in repository.get_releases():
        if release.draft:
            continue
        # Release listings already include their assets.
        for asset in release.assets:
            if not asset.name.lower().endswith(extensions):
                continue
            require(count(asset.id) > 0, "Invalid GitHub asset ID")
            key = str(asset.id)
            created = iso_date(asset.created_at.date())
            first = min(first or created, created)
            assets[key] = max(assets.get(key, 0), count(asset.download_count))
            matched = True
    require(matched, "No public app release assets")
    return {
        "from": first,
        "through": context.today,
        "total": sum_counts(assets.values()),
        "assets": assets,
    }
