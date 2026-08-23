import pytest
from pydantic import ValidationError

from prism.models import DiagramSpec


def base_diagram() -> dict:
    return {
        "diagram_type": "flowchart",
        "title": "Example",
        "selection_reason": "It branches.",
        "summary": "Example summary.",
        "nodes": [
            {"id": "start", "label": "Start", "kind": "start", "evidence_ids": ["e1"]},
            {"id": "done", "label": "Done", "kind": "end", "evidence_ids": ["e1"]},
        ],
        "edges": [{"source": "start", "target": "done", "label": "continue"}],
        "evidence": [
            {
                "id": "e1",
                "source": "github",
                "file_path": "src/example.py",
                "description": "Supports the flow.",
            }
        ],
    }


def test_accepts_grounded_diagram() -> None:
    result = DiagramSpec.model_validate(base_diagram())
    assert result.nodes[0].evidence_ids == ["e1"]


def test_rejects_unknown_evidence_reference() -> None:
    payload = base_diagram()
    payload["nodes"][0]["evidence_ids"] = ["missing"]

    with pytest.raises(ValidationError, match="unknown evidence"):
        DiagramSpec.model_validate(payload)


def test_rejects_unknown_edge_node() -> None:
    payload = base_diagram()
    payload["edges"][0]["target"] = "missing"

    with pytest.raises(ValidationError, match="unknown node"):
        DiagramSpec.model_validate(payload)
