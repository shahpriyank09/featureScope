from pathlib import Path

import pytest

from prism.config import Settings
from prism.models import AnalysisSource, DiagramType
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
