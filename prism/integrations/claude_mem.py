from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from prism.models import MemoryObservation, PullRequestContext


@dataclass(frozen=True)
class ClaudeMemSearchResult:
    observations: list[MemoryObservation]
    warning: str | None = None


class ClaudeMemClient:
    def __init__(self, base_url: str | None, timeout: float = 30) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout = timeout

    def search_for_pull_request(
        self, pull_request: PullRequestContext, limit: int = 5
    ) -> ClaudeMemSearchResult:
        if not self.base_url:
            return ClaudeMemSearchResult(observations=[])

        filenames = " ".join(item.filename for item in pull_request.changed_files[:4])
        query = f"{pull_request.reference.slug} {pull_request.title} {filenames}".strip()
        try:
            observations = _normalize_observations(self._search(query, limit), limit=limit)
            if observations:
                return ClaudeMemSearchResult(observations=observations)

            all_results = self._search("*", 1)
            if _total_results(all_results) == 0:
                return ClaudeMemSearchResult(
                    observations=[],
                    warning=(
                        "Claude-Mem is connected, but its database has no observations yet. "
                        "Create or import a memory, then refresh the live analysis."
                    ),
                )
            return ClaudeMemSearchResult(
                observations=[],
                warning=(
                    "Claude-Mem is connected, but no observations matched this repository "
                    "or pull request."
                ),
            )
        except httpx.TimeoutException:
            return ClaudeMemSearchResult(
                observations=[],
                warning=(
                    f"Claude-Mem search timed out after {self.timeout:g} seconds. "
                    "The worker may still be warming up; refresh the live analysis."
                ),
            )
        except httpx.HTTPStatusError as exc:
            return ClaudeMemSearchResult(
                observations=[],
                warning=f"Claude-Mem search returned HTTP {exc.response.status_code}.",
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return ClaudeMemSearchResult(
                observations=[],
                warning=f"Claude-Mem search failed: {exc}",
            )

    def _search(self, query: str, limit: int) -> Any:
        response = httpx.get(
            f"{self.base_url}/api/search",
            params={
                "query": query,
                "type": "observations",
                "format": "json",
                "limit": limit,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()


def _normalize_observations(payload: Any, limit: int) -> list[MemoryObservation]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        nested_results = payload.get("results")
        if isinstance(nested_results, dict):
            values = nested_results.get("observations", [])
        else:
            values = next(
                (
                    value
                    for key in ("observations", "data", "items", "results")
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


def _total_results(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    total = payload.get("totalResults")
    if isinstance(total, int):
        return total
    nested_results = payload.get("results")
    if isinstance(nested_results, dict):
        payload = nested_results
    return sum(
        len(value)
        for key in ("observations", "sessions", "prompts")
        if isinstance((value := payload.get(key)), list)
    )


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None
