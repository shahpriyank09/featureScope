from prism.evals import evaluate_fallback, evaluation_cases, format_markdown


def test_fallback_eval_meets_quality_and_latency_budget() -> None:
    report = evaluate_fallback(iterations=3)

    assert report.cases == 3
    assert report.diagram_validity == 1.0
    assert report.evidence_coverage == 1.0
    assert report.edge_validity == 1.0
    assert report.diagram_type_accuracy == 1.0
    assert report.mermaid_renderability == 1.0
    assert report.performance_budget_passed


def test_eval_report_is_readable_and_covers_each_routing_class() -> None:
    report = evaluate_fallback(iterations=1)
    markdown = format_markdown(report)

    assert {case.expected_type.value for case in evaluation_cases()} == {
        "flowchart",
        "sequence",
        "state_machine",
    }
    assert "Diagram schema validity" in markdown
    assert "P95 fallback latency" in markdown
