from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from prism.cache import AnalysisCache, FixtureStore
from prism.config import Settings
from prism.generation.generator import DiagramGenerator
from prism.integrations.claude_mem import ClaudeMemClient
from prism.integrations.github import GitHubClient
from prism.integrations.greptile import GreptileClient
from prism.models import AnalysisResult, AnalysisSource
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
            settings.resolved_claude_mem_base_url()
        )
        self.generator = generator or DiagramGenerator(
            cli_path=settings.codex_cli_path,
            model=settings.codex_model,
            timeout=settings.codex_cli_timeout_seconds,
            working_directory=Path(__file__).resolve().parent.parent,
        )

    def explain(self, pr_url: str, *, offline: bool | None = None) -> AnalysisResult:
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
        cached = self.cache.get(pull_request.cache_key)
        if cached:
            return cached.model_copy(update={"source": AnalysisSource.CACHE})

        greptile = self.greptile.get_pull_request_context(pull_request)
        memories = self.claude_mem.search_for_pull_request(pull_request)
        generated = self.generator.generate(pull_request, greptile, memories)

        warnings = list(generated.warnings)
        if greptile.error:
            warnings.append(greptile.error)
        if not memories:
            warnings.append("No matching Claude-Mem observations were available.")

        result = AnalysisResult(
            pull_request=pull_request,
            diagram=generated.diagram,
            greptile=greptile,
            source=AnalysisSource.LIVE,
            generated_at=datetime.now(UTC).isoformat(),
            warnings=warnings,
        )
        self.cache.put(result)
        return result


def _default_fixtures_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "fixtures" / "demo"
