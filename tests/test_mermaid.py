from prism.models import DiagramSpec
from prism.rendering.mermaid import render_mermaid


def test_renders_state_machine() -> None:
    diagram = DiagramSpec.model_validate(
        {
            "diagram_type": "state_machine",
            "title": "Lifecycle",
            "selection_reason": "States dominate.",
            "summary": "Moves from pending to done.",
            "nodes": [
                {"id": "pending", "label": "Pending", "evidence_ids": ["e1"]},
                {"id": "done", "label": "Done", "evidence_ids": ["e1"]},
            ],
            "edges": [{"source": "pending", "target": "done", "label": "complete"}],
            "evidence": [
                {
                    "id": "e1",
                    "source": "github",
                    "file_path": "state.py",
                    "description": "Defines the states.",
                }
            ],
        }
    )

    rendered = render_mermaid(diagram)

    assert rendered.startswith("stateDiagram-v2")
    assert "pending --> done : complete" in rendered
