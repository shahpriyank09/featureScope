from __future__ import annotations

from typing import Any

import httpx

from prism.models import MemoryObservation, PullRequestContext


class ClaudeMemClient:
    def __init__(self, base_url: str | None, timeout: float = 8) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout = timeout

    def search_for_pull_request(
        self, pull_request: PullRequestContext, limit: int = 5
    ) -> list[MemoryObservation]:
        if not self.base_url:
            return []

        filenames = " ".join(item.filename for item in pull_request.changed_files[:4])
        query = f"{pull_request.reference.slug} {pull_request.title} {filenames}".strip()
        try:
            response = httpx.get(
                f"{self.base_url}/api/search",
                params={
                    "query": query,
                    "type": "observations",
                    "format": "index",
                    "limit": limit,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return _normalize_observations(response.json(), limit=limit)
        except (httpx.HTTPError, ValueError, TypeError):
            return []


def _normalize_observations(payload: Any, limit: int) -> list[MemoryObservation]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        values = next(
            (
                value
                for key in ("results", "observations", "data", "items")
                if isinstance((value := payload.get(key)), list)
            ),
            [],
        )
    else:
        values = []

    observations: list[MemoryObservation] = []
    for index, item in enumerate(values[:limit]):
        if not isinstance(item, dict):
            continue
        observation_id = item.get("id") or item.get("observation_id") or f"result-{index + 1}"
        title = item.get("title") or item.get("name") or item.get("type") or "Memory observation"
        narrative = item.get("narrative") or item.get("content") or item.get("text") or ""
        relevance = item.get("relevance") or item.get("summary") or str(narrative)[:240]
        observations.append(
            MemoryObservation(
                observation_id=str(observation_id),
                title=str(title),
                relevance=str(relevance),
                narrative=str(narrative),
                project=_optional_string(item.get("project")),
                created_at=_optional_string(item.get("created_at") or item.get("createdAt")),
            )
        )
    return observations


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None
