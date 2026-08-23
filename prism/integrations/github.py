from __future__ import annotations

from typing import Any

import httpx

from prism.models import ChangedFile, PRReference, PullRequestContext


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, token: str | None, timeout: float = 90) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "PRism-Hackathon-Demo",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url="https://api.github.com",
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )

    def get_pull_request(self, reference: PRReference) -> PullRequestContext:
        pull = self._get(f"/repos/{reference.slug}/pulls/{reference.number}")
        files = self._get_all_pages(
            f"/repos/{reference.slug}/pulls/{reference.number}/files", per_page=100
        )

        changed_files = [
            ChangedFile(
                filename=item["filename"],
                status=item.get("status", "modified"),
                additions=item.get("additions", 0),
                deletions=item.get("deletions", 0),
                patch=item.get("patch"),
                blob_url=item.get("blob_url"),
            )
            for item in files
        ]

        return PullRequestContext(
            reference=reference,
            title=pull["title"],
            body=pull.get("body") or "",
            base_ref=pull.get("base", {}).get("ref") or "main",
            head_sha=pull["head"]["sha"],
            html_url=pull["html_url"],
            author=(pull.get("user") or {}).get("login"),
            changed_files=changed_files,
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = _github_error_detail(exc.response)
            raise GitHubError(
                f"GitHub returned {exc.response.status_code} for {path}: {detail}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise GitHubError(f"Could not fetch GitHub data for {path}: {exc}") from exc

    def _get_all_pages(self, path: str, per_page: int) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._get(path, params={"per_page": per_page, "page": page})
            if not isinstance(payload, list):
                raise GitHubError(f"Expected a list from GitHub endpoint {path}")
            items.extend(payload)
            if len(payload) < per_page:
                break
            page += 1
            if page > 10:
                break
        return items


def _github_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return str(payload.get("message") or payload)
    except ValueError:
        pass
    return response.text[:300] or "unknown error"
