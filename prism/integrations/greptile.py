from __future__ import annotations

import json
from typing import Any

import httpx

from prism.models import GreptileContext, PullRequestContext


class GreptileClient:
    """Small adapter around Greptile's remote MCP endpoint.

    Greptile's MCP surface is centered on PR and review data. The adapter deliberately
    returns a graceful unavailable result when access or repository indexing is missing.
    """

    def __init__(self, api_key: str | None, mcp_url: str, timeout: float = 90) -> None:
        self.api_key = api_key
        self.mcp_url = mcp_url
        self.timeout = timeout

    def get_pull_request_context(self, pull_request: PullRequestContext) -> GreptileContext:
        if not self.api_key:
            return GreptileContext(error="GREPTILE_API_KEY is not configured")

        arguments = {
            "name": pull_request.reference.slug,
            "remote": "github",
            "defaultBranch": pull_request.base_ref,
            "prNumber": pull_request.reference.number,
        }
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_merge_request", "arguments": arguments},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        try:
            response = httpx.post(
                self.mcp_url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
            rpc_payload = _decode_mcp_response(response)
            if "error" in rpc_payload:
                message = rpc_payload["error"].get("message", "unknown MCP error")
                return GreptileContext(error=f"Greptile MCP error: {message}")

            data = _extract_tool_payload(rpc_payload)
            if tool_error := _tool_error_message(data):
                return GreptileContext(
                    raw=data if isinstance(data, dict) else {"value": data},
                    error=f"Greptile repository context unavailable: {tool_error}",
                )
            comments = _collect_review_comments(data)
            summary = _extract_summary(data) or "Greptile returned PR context."
            return GreptileContext(
                available=True,
                summary=summary,
                review_comments=comments[:20],
                raw=data if isinstance(data, dict) else {"value": data},
            )
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return GreptileContext(error=f"Greptile context unavailable: {exc}")


def _decode_mcp_response(response: httpx.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Greptile returned a non-object JSON-RPC response")
        return payload

    for line in reversed(response.text.splitlines()):
        if line.startswith("data:"):
            payload = json.loads(line.removeprefix("data:").strip())
            if isinstance(payload, dict):
                return payload
    raise ValueError("Greptile returned an empty event stream")


def _extract_tool_payload(rpc_payload: dict[str, Any]) -> Any:
    result = rpc_payload.get("result", {})
    content = result.get("content", []) if isinstance(result, dict) else []
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = item.get("text", "")
        try:
            return json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return {"text": str(text)}
    return result


def _extract_summary(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates = [
        payload.get("summary"),
        payload.get("description"),
        (payload.get("mergeRequest") or {}).get("summary")
        if isinstance(payload.get("mergeRequest"), dict)
        else None,
    ]
    return next((str(value) for value in candidates if value), "")


def _collect_review_comments(payload: Any) -> list[str]:
    comments: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            body = value.get("body") or value.get("comment")
            if isinstance(body, str) and body.strip():
                comments.append(body.strip())
            for key, nested in value.items():
                if key in {"comments", "codeReviews", "reviews"}:
                    visit(nested)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return list(dict.fromkeys(comments))


def _tool_error_message(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    text = payload.get("text")
    if not isinstance(text, str):
        return None
    normalized = text.strip().lower()
    error_prefixes = (
        "repository not found:",
        "repository is not indexed",
        "knowledge base not found",
    )
    return text.strip() if normalized.startswith(error_prefixes) else None
