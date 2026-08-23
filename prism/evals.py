"""Offline quality and latency evaluation for PRism's fallback diagram generator.

The suite deliberately uses only local, deterministic inputs.  That makes it suitable for
CI and separates PRism's own behaviour from the availability and latency of Codex, GitHub,
Greptile, and Claude-Mem.
"""

from __future__ import annotations

import argparse
import math
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from prism.generation.generator import _fallback_diagram
from prism.models import ChangedFile, DiagramSpec, DiagramType, PRReference, PullRequestContext
from prism.rendering.mermaid import render_mermaid


@dataclass(frozen=True)
class EvalCase:
    name: str
    pull_request: PullRequestContext
    expected_type: DiagramType


@dataclass(frozen=True)
class EvalReport:
    cases: int
    iterations: int
    diagram_validity: float
    evidence_coverage: float
    edge_validity: float
    diagram_type_accuracy: float
    mermaid_renderability: float
    median_latency_ms: float
    p95_latency_ms: float
    performance_budget_ms: float
    performance_budget_passed: bool

    def as_dict(self) -> dict[str, int | float | bool]:
        return asdict(self)


def evaluation_cases() -> list[EvalCase]:
    """Representative routing examples for the deterministic fallback path."""

    def make_case(
        name: str, title: str, body: str, filename: str, patch: str, expected_type: DiagramType
    ) -> EvalCase:
        return EvalCase(
            name=name,
            expected_type=expected_type,
            pull_request=PullRequestContext(
                reference=PRReference(owner="prism-evals", repository="fixtures", number=len(name)),
                title=title,
                body=body,
                head_sha="evaluation",
                html_url=f"https://github.com/prism-evals/fixtures/pull/{len(name)}",
                changed_files=[
                    ChangedFile(
                        filename=filename,
                        additions=12,
                        deletions=2,
                        patch=patch,
                        blob_url=(
                            "https://github.com/prism-evals/fixtures/blob/evaluation/"
                            f"{filename}"
                        ),
                    )
                ],
            ),
        )

    return [
        make_case(
            "flowchart",
            "Validate a checkout request",
            "Validate input, branch on errors, and retry failed validation.",
            "checkout/validation.py",
            "if invalid(request): return error\nvalidate(request)\nretry on transient error",
            DiagramType.FLOWCHART,
        ),
        make_case(
            "sequence",
            "Send payment webhook to API service",
            "The client sends a request; the API service queues an event and returns a response.",
            "payments/webhook_client.py",
            "client.request(api)\napi.queue.publish(event)\napi.response(accepted)",
            DiagramType.SEQUENCE,
        ),
        make_case(
            "state_machine",
            "Add payment lifecycle state transitions",
            "Payments move from pending to completed state after a transition.",
            "payments/state.py",
            "PENDING -> PROCESSING -> COMPLETED\npayment.transition_to(COMPLETED)",
            DiagramType.STATE_MACHINE,
        ),
    ]


def evaluate_fallback(
    cases: list[EvalCase] | None = None,
    *,
    iterations: int = 25,
    performance_budget_ms: float = 100.0,
) -> EvalReport:
    """Measure grounding, routing, Mermaid output, and local fallback latency."""

    cases = cases or evaluation_cases()
    if not cases:
        raise ValueError("At least one evaluation case is required")
    if iterations < 1:
        raise ValueError("iterations must be at least 1")

    valid_diagrams = routed_diagrams = renderable_diagrams = 0
    grounded_nodes = total_nodes = valid_edges = total_edges = 0
    samples_ms: list[float] = []

    for _ in range(iterations):
        for case in cases:
            started = time.perf_counter()
            diagram = _fallback_diagram(case.pull_request, [])
            samples_ms.append((time.perf_counter() - started) * 1_000)

            try:
                DiagramSpec.model_validate(diagram.model_dump())
                valid_diagrams += 1
            except ValueError:
                pass
            routed_diagrams += diagram.diagram_type == case.expected_type

            evidence_ids = {evidence.id for evidence in diagram.evidence}
            total_nodes += len(diagram.nodes)
            grounded_nodes += sum(
                bool(node.evidence_ids) and set(node.evidence_ids).issubset(evidence_ids)
                for node in diagram.nodes
            )
            node_ids = {node.id for node in diagram.nodes}
            total_edges += len(diagram.edges)
            valid_edges += sum(
                edge.source in node_ids and edge.target in node_ids for edge in diagram.edges
            )

            source = render_mermaid(diagram)
            expected_header = {
                DiagramType.FLOWCHART: "flowchart TD",
                DiagramType.SEQUENCE: "sequenceDiagram",
                DiagramType.STATE_MACHINE: "stateDiagram-v2",
            }[diagram.diagram_type]
            renderable_diagrams += source.startswith(expected_header) and bool(source.strip())

    evaluated = len(cases) * iterations
    p95_index = max(0, math.ceil(0.95 * len(samples_ms)) - 1)
    p95_latency_ms = sorted(samples_ms)[p95_index]
    return EvalReport(
        cases=len(cases),
        iterations=iterations,
        diagram_validity=valid_diagrams / evaluated,
        evidence_coverage=grounded_nodes / total_nodes if total_nodes else 1.0,
        edge_validity=valid_edges / total_edges if total_edges else 1.0,
        diagram_type_accuracy=routed_diagrams / evaluated,
        mermaid_renderability=renderable_diagrams / evaluated,
        median_latency_ms=statistics.median(samples_ms),
        p95_latency_ms=p95_latency_ms,
        performance_budget_ms=performance_budget_ms,
        performance_budget_passed=p95_latency_ms <= performance_budget_ms,
    )


def format_markdown(report: EvalReport) -> str:
    """Produce a small, paste-ready report with percentages and latency units."""

    def pct(value: float) -> str:
        return f"{value:.1%}"
    return "\n".join(
        [
            "# PRism evaluation results",
            "",
            f"Cases: {report.cases} | iterations per case: {report.iterations}",
            "",
            "| Metric | Result |",
            "| --- | ---: |",
            f"| Diagram schema validity | {pct(report.diagram_validity)} |",
            f"| Node evidence coverage | {pct(report.evidence_coverage)} |",
            f"| Edge reference validity | {pct(report.edge_validity)} |",
            f"| Diagram-type routing accuracy | {pct(report.diagram_type_accuracy)} |",
            f"| Mermaid source renderability | {pct(report.mermaid_renderability)} |",
            f"| Median fallback latency | {report.median_latency_ms:.3f} ms |",
            f"| P95 fallback latency | {report.p95_latency_ms:.3f} ms |",
            f"| P95 budget ({report.performance_budget_ms:.0f} ms) | "
            f"{'PASS' if report.performance_budget_passed else 'FAIL'} |",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate PRism's deterministic fallback generator."
    )
    parser.add_argument("--iterations", type=int, default=25, help="Runs per evaluation case.")
    parser.add_argument("--output", type=Path, help="Optional Markdown output path.")
    args = parser.parse_args()
    report = evaluate_fallback(iterations=args.iterations)
    markdown = format_markdown(report)
    print(markdown, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")


if __name__ == "__main__":
    main()
