from __future__ import annotations

import io
import subprocess
import zipfile
from pathlib import Path

from prism.integrations.local_repository import LocalRepositoryMapper
from prism.models import AnalysisResult, ChangedFile, PRReference, PullRequestContext
from prism.rendering.obsidian import build_obsidian_vault, obsidian_vault_filename
from prism.rendering.repository_map import render_repository_map_html


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_builds_repository_graph_and_marks_changed_neighbors(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "prism@example.com")
    _git(repository, "config", "user.name", "PRism Test")

    (repository / "pkg").mkdir()
    (repository / "tests").mkdir()
    (repository / "README.md").write_text(
        "# Example\n\nExample demonstrates a small service and its reusable validation helpers.\n",
        encoding="utf-8",
    )
    (repository / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (repository / "pkg" / "helpers.py").write_text(
        "def sanitize(value):\n    return value.strip()\n", encoding="utf-8"
    )
    (repository / "pkg" / "service.py").write_text(
        "from .helpers import sanitize\n\ndef process(value):\n    return sanitize(value)\n",
        encoding="utf-8",
    )
    (repository / "tests" / "test_service.py").write_text(
        "from pkg.service import process\n\ndef test_process():\n    assert process(' x ') == 'x'\n",
        encoding="utf-8",
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "base")
    base_sha = _git(repository, "rev-parse", "HEAD")

    (repository / "pkg" / "helpers.py").write_text(
        "def sanitize(value):\n    return value.strip().lower()\n", encoding="utf-8"
    )
    (repository / "pkg" / "state.py").write_text(
        "from .helpers import sanitize\n\nclass State:\n    READY = sanitize('READY')\n",
        encoding="utf-8",
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "change helpers")
    head_sha = _git(repository, "rev-parse", "HEAD")

    pull_request = PullRequestContext(
        reference=PRReference(owner="example", repository="service", number=7),
        title="Normalize service state",
        base_ref="main",
        base_sha=base_sha,
        head_sha=head_sha,
        html_url="https://github.com/example/service/pull/7",
        changed_files=[
            ChangedFile(filename="pkg/helpers.py", status="modified"),
            ChangedFile(filename="pkg/state.py", status="added"),
        ],
    )

    mapper = LocalRepositoryMapper(tmp_path / "cache")
    repository_map = mapper._analyze(repository / ".git", pull_request)

    nodes = {node.path: node for node in repository_map.nodes}
    assert nodes["pkg/helpers.py"].status.value == "modified"
    assert nodes["pkg/state.py"].status.value == "added"
    assert nodes["pkg/service.py"].status.value == "impacted"
    assert nodes["pkg/service.py"].focused is True
    assert nodes["tests/test_service.py"].kind.value == "test"
    assert "small service" in repository_map.overview
    assert any(
        edge.kind == "imports"
        and nodes["pkg/service.py"].id == edge.source
        and nodes["pkg/helpers.py"].id == edge.target
        for edge in repository_map.edges
    )

    blocks = {block.path: block for block in repository_map.blocks}
    assert blocks["pkg"].status.value == "modified"
    assert blocks["tests"].status.value == "impacted"
    assert "pkg/helpers.py" in blocks["pkg"].note
    assert "## Files" in blocks["pkg"].note
    assert len(repository_map.block_edges) == 1


def test_repository_map_renderer_embeds_data_safely(tmp_path: Path) -> None:
    # Reuse the model's empty-map support to verify the renderer shell without a browser.
    from prism.models import RepositoryMap

    repository_map = RepositoryMap(repository="example/repo", head_sha="abc1234")
    rendered = render_repository_map_html(repository_map)

    assert "Change impact" in rendered
    assert "Full architecture" in rendered
    assert "View Obsidian Markdown" in rendered
    assert "Repository architecture impact map" in rendered
    assert "vis-network" not in rendered
    assert 'repository="example/repo"' not in rendered


def test_exports_architecture_notes_as_obsidian_vault() -> None:
    fixture_path = (
        Path(__file__).resolve().parent.parent
        / "fixtures"
        / "demo"
        / "acme-inc__checkout-platform__42.json"
    )
    result = AnalysisResult.model_validate_json(fixture_path.read_text(encoding="utf-8"))
    assert result.repository_map is not None

    archive_bytes = build_obsidian_vault(result.repository_map)
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = archive.namelist()
        index_name = next(name for name in names if name.endswith("/README.md"))
        payments_name = next(name for name in names if name.endswith("/Blocks/payments.md"))
        index = archive.read(index_name).decode("utf-8")
        payments = archive.read(payments_name).decode("utf-8")

    assert "[[Blocks/payments|Payments]]" in index
    assert "payments/state.py" in payments
    assert obsidian_vault_filename(result.repository_map).endswith(".zip")
