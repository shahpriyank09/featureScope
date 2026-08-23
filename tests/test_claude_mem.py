from __future__ import annotations

import httpx

from prism.integrations.claude_mem import ClaudeMemClient
from prism.models import ChangedFile, PRReference, PullRequestContext


def pull_request() -> PullRequestContext:
    return PullRequestContext(
        reference=PRReference(owner="acme", repository="widgets", number=7),
        title="Validate widget state",
        head_sha="abc123",
        html_url="https://github.com/acme/widgets/pull/7",
        changed_files=[ChangedFile(filename="widgets/state.py")],
    )


def response(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json=payload,
        request=httpx.Request("GET", "http://127.0.0.1:37701/api/search"),
    )


def test_search_parses_json_observations(monkeypatch) -> None:
    captured_params: list[dict] = []

    def fake_get(*args, **kwargs):
        captured_params.append(kwargs["params"])
        return response(
            {
                "observations": [
                    {
                        "id": 42,
                        "title": "Widget validation decision",
                        "narrative": "Validate before saving.",
                        "project": "widgets",
                    }
                ],
                "totalResults": 1,
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = ClaudeMemClient("http://127.0.0.1:37701").search_for_pull_request(
        pull_request()
    )

    assert result.warning is None
    assert result.observations[0].observation_id == "42"
    assert result.observations[0].narrative == "Validate before saving."
    assert captured_params[0]["format"] == "json"


def test_search_distinguishes_an_empty_database(monkeypatch) -> None:
    responses = iter(
        [
            response({"observations": [], "totalResults": 0}),
            response(
                {
                    "observations": [],
                    "sessions": [],
                    "prompts": [],
                    "totalResults": 0,
                }
            ),
        ]
    )
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: next(responses))

    result = ClaudeMemClient("http://127.0.0.1:37701").search_for_pull_request(
        pull_request()
    )

    assert result.observations == []
    assert result.warning is not None
    assert "database has no observations" in result.warning


def test_search_surfaces_timeouts(monkeypatch) -> None:
    def raise_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("worker is warming up")

    monkeypatch.setattr(httpx, "get", raise_timeout)

    result = ClaudeMemClient(
        "http://127.0.0.1:37701", timeout=12
    ).search_for_pull_request(pull_request())

    assert result.observations == []
    assert result.warning is not None
    assert "timed out after 12 seconds" in result.warning


def test_nanochat_pr_833_uses_the_clearly_labelled_demo_memory() -> None:
    demo_pr = PullRequestContext(
        reference=PRReference(owner="karpathy", repository="nanochat", number=833),
        title="Portable attention backends",
        head_sha="def456",
        html_url="https://github.com/karpathy/nanochat/pull/833",
    )

    result = ClaudeMemClient(None).search_for_pull_request(demo_pr)

    assert result.warning is None
    assert len(result.observations) == 1
    assert result.observations[0].observation_id == "demo-nanochat-pr-833"
    assert result.observations[0].title.startswith("Demo memory:")
    assert "not persisted" in result.observations[0].narrative
