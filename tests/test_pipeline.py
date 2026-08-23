from pathlib import Path

import pytest

from prism.config import Settings
from prism.integrations.claude_mem import ClaudeMemSearchResult
from prism.models import AnalysisResult, AnalysisSource, DiagramType
from prism.pipeline import ExplainPipeline, OfflineDataUnavailable


DEMO_URL = "https://github.com/acme-inc/checkout-platform/pull/42"


def test_offline_pipeline_loads_bundled_fixture(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        prism_cache_dir=tmp_path / "cache",
        claude_mem_enabled=False,
    )
    pipeline = ExplainPipeline(settings)

    result = pipeline.explain(DEMO_URL, offline=True)

    assert result.source == AnalysisSource.FIXTURE
    assert result.diagram.diagram_type == DiagramType.STATE_MACHINE
    assert len(result.diagram.evidence) == 3
    assert len(result.diagram.memories) == 2


def test_offline_pipeline_fails_clearly_without_data(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        prism_cache_dir=tmp_path / "cache",
        claude_mem_enabled=False,
    )
    pipeline = ExplainPipeline(settings, fixtures_dir=tmp_path / "fixtures")

    with pytest.raises(OfflineDataUnavailable, match="No cached or fixture data"):
        pipeline.explain("https://github.com/example/missing/pull/99", offline=True)


def test_cached_analysis_rechecks_missing_claude_mem_context(tmp_path: Path) -> None:
    fixture_path = (
        Path(__file__).resolve().parent.parent
        / "fixtures"
        / "demo"
        / "acme-inc__checkout-platform__42.json"
    )
    cached = AnalysisResult.model_validate_json(fixture_path.read_text(encoding="utf-8"))
    cached = cached.model_copy(
        update={
            "diagram": cached.diagram.model_copy(update={"memories": []}),
            "warnings": ["No matching Claude-Mem observations were available."],
        }
    )

    class GitHubStub:
        def get_pull_request(self, reference):
            return cached.pull_request

    class ClaudeMemStub:
        def search_for_pull_request(self, pull_request):
            return ClaudeMemSearchResult(
                observations=[],
                warning="Claude-Mem is connected, but its database has no observations yet.",
            )

    settings = Settings(
        _env_file=None,
        prism_cache_dir=tmp_path / "cache",
        claude_mem_enabled=True,
    )
    pipeline = ExplainPipeline(
        settings,
        github=GitHubStub(),
        claude_mem=ClaudeMemStub(),
    )
    pipeline.cache.put(cached)

    result = pipeline.explain(DEMO_URL)

    assert result.source == AnalysisSource.CACHE
    assert result.warnings == [
        "Claude-Mem is connected, but its database has no observations yet."
    ]
