# PRism evals

`prism-evals` measures the deterministic fallback generator without making network requests or
calling Codex. This keeps regression checks repeatable and makes the measured latency meaningful:
it is PRism's local generation overhead, not provider latency.

Run the suite with the supported Python 3.11+ environment:

```bash
uv run pytest
uv run prism-evals --iterations 100
```

To save a fresh, machine-specific report:

```bash
uv run prism-evals --iterations 100 --output .cache/prism/eval-results.md
```

## What is measured

| Metric | Meaning | Regression expectation |
| --- | --- | --- |
| Diagram schema validity | Generated diagram passes `DiagramSpec` validation. | 100% |
| Node evidence coverage | Each node names at least one supplied evidence item. | 100% |
| Edge reference validity | Every edge points to existing nodes. | 100% |
| Diagram-type routing accuracy | The fallback picks flowchart, sequence, or state-machine for the curated case. | 100% (3/3) |
| Mermaid source renderability | Generated Mermaid has the correct diagram header. | 100% |
| Fallback latency | Median and P95 local generation time. | P95 ≤ 100 ms |

## Expected regression result

The regression test evaluates three representative PRs (one for each diagram type) for three
iterations. Its required result is **100%** on all five quality metrics and a **passing P95
latency budget of 100 ms**. The command prints the exact median and P95 from the current machine;
latency is intentionally not checked into this document because it varies with hardware and load.

The evaluator does not score live Codex output. Model quality should be evaluated separately with
a versioned, human-labelled PR set, because it depends on the selected model and external context.
