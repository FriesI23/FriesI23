"""Inputs and validation shared by the download sources."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from github import Github


@dataclass(frozen=True)
class DownloadContext:
    config: dict
    github: Github
    fetch_json: Callable[[str], dict]
    today: str

    @property
    def settings(self):
        return self.config["downloads"]

    @property
    def urls(self):
        return self.config["urls"]

    @property
    def package_id(self):
        return self.config["app"]["package_id"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def count(value):
    # Preserve the numeric range of the existing JSON snapshots.
    require(
        type(value) is int and 0 <= value < 2**53, "Invalid download count"
    )
    return value


def sum_counts(values):
    return count(sum(count(item) for item in values))


def as_object(value):
    require(isinstance(value, dict), "Expected a JSON object")
    return value


def iso_date(value):
    if type(value) is date:
        return value.isoformat()
    require(
        isinstance(value, str)
        and date.fromisoformat(value).isoformat() == value,
        "Invalid date",
    )
    return value


def shift_day(day, offset):
    return (date.fromisoformat(day) + timedelta(days=offset)).isoformat()


def iter_days(start, end):
    while start <= end:
        yield start
        start = shift_day(start, 1)
