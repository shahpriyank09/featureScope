import pytest

from prism.pr_url import InvalidPullRequestURL, parse_pull_request_url


@pytest.mark.parametrize(
    ("value", "owner", "repository", "number"),
    [
        ("https://github.com/openai/openai-python/pull/123", "openai", "openai-python", 123),
        ("github.com/acme/widgets/pull/9", "acme", "widgets", 9),
        (" https://www.github.com/a/b/pull/1/ ", "a", "b", 1),
    ],
)
def test_parse_pull_request_url(value: str, owner: str, repository: str, number: int) -> None:
    result = parse_pull_request_url(value)

    assert result.owner == owner
    assert result.repository == repository
    assert result.number == number


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://gitlab.com/acme/widgets/pull/1",
        "https://github.com/acme/widgets/issues/1",
        "https://github.com/acme/widgets/pull/0",
        "not a url",
    ],
)
def test_rejects_invalid_pull_request_url(value: str) -> None:
    with pytest.raises(InvalidPullRequestURL):
        parse_pull_request_url(value)
