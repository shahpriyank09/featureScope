from __future__ import annotations

import html
import json
import re

from prism.models import DiagramNode, DiagramSpec, DiagramType


def render_mermaid(diagram: DiagramSpec) -> str:
    if diagram.diagram_type == DiagramType.SEQUENCE:
        return _render_sequence(diagram)
    if diagram.diagram_type == DiagramType.STATE_MACHINE:
        return _render_state_machine(diagram)
    return _render_flowchart(diagram)


def render_mermaid_html(source: str, height: int = 640) -> str:
    """Return a self-contained Streamlit component shell around Mermaid source."""

    encoded = json.dumps(source)
    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      body {{ margin: 0; background: transparent; font-family: Inter, sans-serif; }}
      #diagram {{ display: flex; justify-content: center; min-height: {height - 24}px; }}
      #diagram svg {{ max-width: 100%; height: auto; }}
      #error {{ color: #b42318; white-space: pre-wrap; }}
    </style>
  </head>
  <body>
    <div id="diagram"></div>
    <pre id="error"></pre>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({{
        startOnLoad: false,
        securityLevel: "strict",
        theme: "neutral",
        flowchart: {{ curve: "basis", htmlLabels: true }}
      }});
      const source = {encoded};
      try {{
        const {{ svg }} = await mermaid.render("prism-diagram", source);
        document.getElementById("diagram").innerHTML = svg;
      }} catch (error) {{
        document.getElementById("error").textContent = "Could not render diagram: " + error;
      }}
    </script>
  </body>
</html>
"""


def _render_flowchart(diagram: DiagramSpec) -> str:
    lines = ["flowchart TD"]
    for node in diagram.nodes:
        lines.append(f"    {node.id}{_flowchart_shape(node)}")
    for edge in diagram.edges:
        label = f"|{_label(edge.label)}|" if edge.label else ""
        lines.append(f"    {edge.source} -->{label} {edge.target}")
    return "\n".join(lines)


def _render_sequence(diagram: DiagramSpec) -> str:
    lines = ["sequenceDiagram"]
    node_map = {node.id: node for node in diagram.nodes}
    for node in diagram.nodes:
        lines.append(f"    participant {node.id} as {_label(node.label)}")
    for edge in diagram.edges:
        if edge.source in node_map and edge.target in node_map:
            lines.append(f"    {edge.source}->>{edge.target}: {_label(edge.label or 'continues')}")
    return "\n".join(lines)


def _render_state_machine(diagram: DiagramSpec) -> str:
    lines = ["stateDiagram-v2"]
    for node in diagram.nodes:
        lines.append(f'    state "{_quoted(node.label)}" as {node.id}')
    for edge in diagram.edges:
        suffix = f" : {_label(edge.label)}" if edge.label else ""
        lines.append(f"    {edge.source} --> {edge.target}{suffix}")
    return "\n".join(lines)


def _flowchart_shape(node: DiagramNode) -> str:
    label = _label(node.label)
    if node.kind.lower() in {"decision", "condition"}:
        return f'{{"{label}"}}'
    if node.kind.lower() in {"start", "end", "terminal"}:
        return f'(["{label}"])'
    if node.kind.lower() in {"database", "store"}:
        return f'[("{label}")]'
    return f'["{label}"]'


def _label(value: str) -> str:
    return html.escape(re.sub(r"\s+", " ", value).strip(), quote=True).replace("|", "&#124;")


def _quoted(value: str) -> str:
    return _label(value).replace('"', "&quot;")
