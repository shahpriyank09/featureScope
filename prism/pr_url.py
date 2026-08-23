from __future__ import annotations

import re
from urllib.parse import urlparse

from prism.models import PRReference


class InvalidPullRequestURL(ValueError):
    pass


_PATH_PATTERN = re.compile(
    r"^/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/pull/(?P<number>[1-9][0-9]*)/?$"
)


def parse_pull_request_url(value: str) -> PRReference:
    """Parse a canonical GitHub pull-request URL into a stable reference."""

    normalized = value.strip()
    if not normalized:
        raise InvalidPullRequestURL("A GitHub pull-request URL is required")
    if "://" not in normalized:
        normalized = f"https://{normalized}"

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "github.com",
        "www.github.com",
    }:
        raise InvalidPullRequestURL("Only github.com pull-request URLs are supported")

    match = _PATH_PATTERN.fullmatch(parsed.path)
    if not match:
        raise InvalidPullRequestURL(
            "Expected a URL like https://github.com/OWNER/REPOSITORY/pull/123"
        )

    return PRReference(
        owner=match.group("owner"),
        repository=match.group("repo"),
        number=int(match.group("number")),
    )
