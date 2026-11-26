"""Count app downloads from F-Droid weekly reports."""

from .common import as_object, iso_date, require, shift_day, sum_counts


def collect(previous, context):
    """Sum all reporting weeks and record their covered dates."""
    url = context.urls["fdroid_weeks"].format(package_id=context.package_id)
    data = as_object(context.fetch_json(url))
    require(data, "No F-Droid weekly reports")
    weeks = sorted(iso_date(day) for day in data)
    require(
        not previous or weeks[0] <= previous["from"],
        "F-Droid archive lost previously covered weeks",
    )
    require(
        weeks[-1] <= context.today, "F-Droid returned a future reporting week"
    )
    through = min(context.today, shift_day(weeks[-1], 6))
    require(
        previous.get("through", "") <= through,
        "F-Droid reporting date regressed",
    )
    return {
        "from": weeks[0],
        "through": through,
        "total": sum_counts(data.values()),
    }
