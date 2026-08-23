import json
import subprocess
from pathlib import Path

from prism.generation.generator import DiagramGenerator
from prism.models import ChangedFile, GreptileContext, PRReference, PullRequestContext


def pull_request() -> PullRequestContext:
    return PullRequestContext(
        reference=PRReference(owner="acme", repository="widgets", number=7),
        title="Validate widget state",
        body="Adds a validation branch.",
        head_sha="abc123",
        html_url="https://github.com/acme/widgets/pull/7",
        changed_files=[
            ChangedFile(
                filename="widgets/state.py",
                additions=12,
                patch="+def validate_state(value): ...",
                blob_url="https://github.com/acme/widgets/blob/abc123/widgets/state.py",
            )
        ],
    )


def diagram_payload() -> dict:
    return {
        "diagram_type": "flowchart",
        "title": "Validate widget state",
        "selection_reason": "The change adds a validation branch.",
        "summary": "The widget state is validated before it is saved.",
        "participants": [],
        "nodes": [
            {
                "id": "validate",
                "label": "Validate state",
                "kind": "decision",
                "evidence_ids": ["code_1"],
            }
        ],
        "edges": [],
        "evidence": [
            {
                "id": "code_1",
                "source": "github",
                "file_path": "widgets/state.py",
                "url": "https://github.com/acme/widgets/blob/abc123/widgets/state.py",
                "description": "Changed file: widgets/state.py",
            }
        ],
        "memories": [],
    }


def test_uses_fallback_when_codex_is_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("prism.generation.generator.shutil.which", lambda _: None)
    generator = DiagramGenerator(cli_path="missing-codex", working_directory=tmp_path)

    result = generator.generate(pull_request(), GreptileContext(), [])

    assert result.diagram.title == "Validate widget state"
    assert "not found" in result.warnings[0]


def test_runs_codex_with_schema_and_sanitized_environment(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}
    monkeypatch.setattr("prism.generation.generator.shutil.which", lambda _: "/usr/bin/codex")
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-reach-codex")
    monkeypatch.setenv("GREPTILE_API_KEY", "must-not-reach-codex")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        schema_path = Path(command[command.index("--output-schema") + 1])
        captured["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(diagram_payload()), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("prism.generation.generator.subprocess.run", fake_run)
    generator = DiagramGenerator(working_directory=tmp_path)

    result = generator.generate(pull_request(), GreptileContext(), [])

    assert result.warnings == []
    assert result.diagram.nodes[0].id == "validate"
    assert "--output-schema" in captured["command"]
    assert "read-only" in captured["command"]
    assert "--ephemeral" in captured["command"]
    assert captured["schema"]["additionalProperties"] is False
    assert set(captured["schema"]["required"]) == set(captured["schema"]["properties"])
    assert "GITHUB_TOKEN" not in captured["environment"]
    assert "GREPTILE_API_KEY" not in captured["environment"]
