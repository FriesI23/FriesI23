"""Validate badge values and apply the Shields display conventions."""

import re
from decimal import ROUND_HALF_UP, Decimal


def validate_count(value):
    if type(value) is not int or not 0 <= value < 2**53:
        raise ValueError("missing or invalid count")
    return value


def compact(value):
    """Format a count using Shields SI units."""
    validate_count(value)
    units = ("", "k", "M", "G", "T", "P")
    scaled = value
    unit = 0
    while scaled >= 1000:
        unit += 1
        scaled /= 1000
    if not unit:
        return str(value)

    # JS toFixed rounds the binary float, with ties up.
    # For example, 2550 / 1000 is just below 2.55, and displays as 2.5k.
    precision = Decimal("0.1") if scaled < 10 else Decimal(1)
    rounded = Decimal.from_float(scaled).quantize(
        precision, rounding=ROUND_HALF_UP
    )
    if rounded == 1000:
        return "1" + units[unit + 1]
    return format(rounded, "f").removesuffix(".0") + units[unit]


def download_color(count):
    for ceiling, color in (
        (1, "red"),
        (10, "yellow"),
        (100, "yellowgreen"),
        (1000, "green"),
    ):
        if count < ceiling:
            return color
    return "brightgreen"


def validate_version(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"v?[0-9]+[\w.+-]*", value, flags=re.ASCII
    ):
        raise ValueError("missing or invalid version")
    return value


def version_badge(value):
    """Return the display text and color for a validated version."""
    color = (
        "orange"
        if re.search(
            r"^v?0|alpha|beta|snapshot|dev|pre|rc|scm|cvs", value, re.I
        )
        else "blue"
    )
    return value if value.startswith("v") else "v" + value, color
