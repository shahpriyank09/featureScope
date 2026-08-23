from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from prism.cache import AnalysisCache, FixtureStore
from prism.config import Settings
from prism.generation.generator import DiagramGenerator
from prism.integrations.claude_mem import ClaudeMemClient, ClaudeMemSearchResult
from prism.integrations.github import GitHubClient
from prism.integrations.greptile import GreptileClient
from prism.integrations.local_repository import LocalRepositoryMapper
from prism.models import (
    AnalysisResult,
    AnalysisSource,
    GreptileContext,
    PullRequestContext,
    RepositoryMap,
)
from prism.pr_url import parse_pull_request_url


class OfflineDataUnavailable(RuntimeError):
    pass


class ExplainPipeline:
    def __init__(
        self,
        settings: Settings,
        *,
        fixtures_dir: Path | None = None,
        github: GitHubClient | None = None,
        greptile: GreptileClient | None = None,
        claude_mem: ClaudeMemClient | None = None,
        repository_mapper: LocalRepositoryMapper | None = None,
        generator: DiagramGenerator | None = None,
    ) -> None:
        self.settings = settings
        self.cache = AnalysisCache(settings.prism_cache_dir)
        self.fixtures = FixtureStore(fixtures_dir or _default_fixtures_dir())
        self.github = github or GitHubClient(
            settings.github_token, timeout=settings.request_timeout_seconds
        )
        self.greptile = greptile or GreptileClient(
            settings.greptile_api_key,
            settings.greptile_mcp_url,
            timeout=settings.request_timeout_seconds,
        )
        self.claude_mem = claude_mem or ClaudeMemClient(
            settings.resolved_claude_mem_base_url(),
            timeout=settings.claude_mem_timeout_seconds,
        )
        self.repository_mapper = repository_mapper or LocalRepositoryMapper(
            settings.prism_cache_dir,
            settings.github_token,
            timeout=settings.request_timeout_seconds,
        )
        self.generator = generator or DiagramGenerator(
            cli_path=settings.codex_cli_path,
            model=settings.codex_model,
            timeout=settings.codex_cli_timeout_seconds,
            working_directory=Path(__file__).resolve().parent.parent,
        )

    def explain(
        self,
        pr_url: str,
        *,
        offline: bool | None = None,
        refresh: bool = False,
    ) -> AnalysisResult:
        reference = parse_pull_request_url(pr_url)
        use_offline = self.settings.prism_offline_demo if offline is None else offline

        if use_offline:
            cached = self.cache.get_latest(reference)
            if cached:
                return cached
            fixture = self.fixtures.load(reference)
            if fixture:
                return fixture
            raise OfflineDataUnavailable(
                f"No cached or fixture data is available for {reference.url}. "
                "Run it once live or choose the bundled example PR."
            )

        pull_request = self.github.get_pull_request(reference)
        cached = None if refresh else self.cache.get(pull_request.cache_key)
        if cached:
            cached = self._ensure_repository_map(cached, pull_request)
            if not self.settings.claude_mem_enabled:
                return cached.model_copy(
                    update={
                        "source": AnalysisSource.CACHE,
                        "warnings": _replace_claude_mem_warning(cached.warnings, None),
                    }
                )
            if cached.diagram.memories:
                return cached.model_copy(update={"source": AnalysisSource.CACHE})

            memory_search = self.claude_mem.search_for_pull_request(pull_request)
            if not memory_search.observations:
                return cached.model_copy(
                    update={
                        "source": AnalysisSource.CACHE,
                        "warnings": _replace_claude_mem_warning(
                            cached.warnings, memory_search.warning
                        ),
                    }
                )
            return self._generate_result(
                pull_request, cached.greptile, memory_search, cached.repository_map
            )

        repository_map = self.repository_mapper.build(pull_request)
        greptile = self.greptile.get_pull_request_context(pull_request)
        memory_search = self.claude_mem.search_for_pull_request(pull_request)
        return self._generate_result(pull_request, greptile, memory_search, repository_map)

    def _generate_result(
        self,
        pull_request: PullRequestContext,
        greptile: GreptileContext,
        memory_search: ClaudeMemSearchResult,
        repository_map: RepositoryMap | None = None,
    ) -> AnalysisResult:
        generated = self.generator.generate(
            pull_request, greptile, memory_search.observations
        )

        warnings = list(generated.warnings)
        if greptile.error:
            warnings.append(greptile.error)
        if memory_search.warning:
            warnings.append(memory_search.warning)
        if repository_map and repository_map.error:
            warnings.append(repository_map.error)

        result = AnalysisResult(
            pull_request=pull_request,
            diagram=generated.diagram,
            greptile=greptile,
            repository_map=repository_map,
            source=AnalysisSource.LIVE,
            generated_at=datetime.now(UTC).isoformat(),
            warnings=warnings,
        )
        self.cache.put(result)
        return result

    def _ensure_repository_map(
        self, cached: AnalysisResult, pull_request: PullRequestContext
    ) -> AnalysisResult:
        if cached.repository_map is not None and cached.repository_map.blocks:
            return cached
        repository_map = self.repository_mapper.build(pull_request)
        warnings = list(cached.warnings)
        if repository_map.error and repository_map.error not in warnings:
            warnings.append(repository_map.error)
        updated = cached.model_copy(
            update={
                "pull_request": pull_request,
                "repository_map": repository_map,
                "warnings": warnings,
            }
        )
        self.cache.put(updated)
        return updated


def _default_fixtures_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "fixtures" / "demo"


def _replace_claude_mem_warning(
    warnings: list[str], replacement: str | None
) -> list[str]:
    updated = [warning for warning in warnings if "Claude-Mem" not in warning]
    if replacement:
        updated.append(replacement)
    return updated
