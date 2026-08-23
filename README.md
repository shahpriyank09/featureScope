# PRism

PRism turns a GitHub pull request into an evidence-backed visual explanation and remembers how the feature evolves.

> Paste a PR URL to see where the change fits, how it works, and why it changed.

This README is both the initial product specification and an implementation brief for a coding agent. The project should be built primarily with OpenAI Codex to satisfy the hackathon requirement. Claude or other tools may be used as secondary tools.

## Demo experience

1. The user opens PRism.
2. The user pastes a GitHub pull-request URL.
3. The user clicks **Explain this PR**.
4. PRism displays:
   - The automatically selected diagram type
   - An interactive diagram
   - A plain-English explanation
   - Code evidence for important diagram elements
   - Relevant Claude-Mem history
5. The user clicks **Export to slides**.

## Product roles

- **GitHub** provides PR metadata, changed files, patches, links, and source evidence.
- **Greptile** provides PR-review and repository-aware context from an indexed codebase.
- **Claude-Mem** retrieves previous discoveries, decisions, and diagrams.
- **OpenAI** converts the collected context into a validated structured diagram specification.
- **PRism** renders the result and exports it for sharing.

## Technical approach

Build the first version in Python.

- Python 3.11 or newer
- Streamlit for the demo website
- Typer and Rich for an optional CLI using the same pipeline
- Pydantic for structured diagram models and validation
- HTTPX for GitHub, Greptile, and Claude-Mem requests
- OpenAI Python SDK for diagram generation
- Mermaid for diagram rendering
- `python-pptx` for slide export
- Pytest for tests

The application may use Mermaid's JavaScript renderer in the browser even though the application and orchestration code are Python.

## Architecture

```text
Streamlit UI or CLI
        |
        v
PR URL parser
        |
        +----> GitHub client ------> PR metadata, patch, evidence
        |
        +----> Greptile client ----> repository-aware PR context
        |
        +----> Claude-Mem client --> related observations and timeline
        |
        v
Diagram generator
        |
        v
Pydantic validation and evidence checks
        |
        +----> Mermaid renderer
        +----> Plain-English explanation
        +----> Slide exporter
        +----> Local cache
```

## Repository structure

```text
prism/
├── app.py
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
├── prism/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── pipeline.py
│   ├── models.py
│   ├── integrations/
│   │   ├── github.py
│   │   ├── greptile.py
│   │   └── claude_mem.py
│   ├── generation/
│   │   ├── selector.py
│   │   ├── prompts.py
│   │   └── generator.py
│   ├── rendering/
│   │   ├── mermaid.py
│   │   └── slides.py
│   └── cache.py
├── fixtures/
│   └── demo/
└── tests/
    ├── test_pr_url.py
    ├── test_models.py
    └── test_pipeline.py
```

Keep this as one repository and one Python environment. Do not create microservices for the hackathon version.

## Environment variables

Create `.env` locally from `.env.example`.

```dotenv
# Required secrets
GREPTILE_API_KEY=
OPENAI_API_KEY=

# Recommended for dependable GitHub API access
GITHUB_TOKEN=

# Non-secret configuration
GREPTILE_MCP_URL=https://api.greptile.com/mcp
OPENAI_MODEL=

# Optional local Claude-Mem connection
CLAUDE_MEM_ENABLED=true
CLAUDE_MEM_BASE_URL=http://127.0.0.1:REPLACE_WITH_ACTUAL_PORT

# Demo reliability
PRISM_CACHE_DIR=.cache/prism
PRISM_OFFLINE_DEMO=false
LOG_LEVEL=INFO
REQUEST_TIMEOUT_SECONDS=90
```

Never commit `.env`. Commit only `.env.example` with empty values.

The Greptile API key must have access to the selected, indexed demo repository. For local Claude-Mem, resolve the worker port from `~/.claude-mem/settings.json`; a separate Claude-Mem API key is normally unnecessary.

## Commands

The finished project should support both interfaces.

```bash
# Install
uv sync

# Run the website
uv run streamlit run app.py

# Run the CLI
uv run prism explain https://github.com/OWNER/REPOSITORY/pull/NUMBER

# Use cached data during the presentation
uv run prism explain PR_URL --offline

# Run tests
uv run pytest
```

## Core pipeline

`explain_pull_request(pr_url)` should perform these steps:

1. Validate and parse the GitHub PR URL.
2. Fetch PR title, description, base/head SHAs, changed files, patches, and links.
3. Fetch available Greptile PR/review context.
4. Search Claude-Mem using the repository name, PR title, and important changed symbols.
5. Retrieve full details only for the most relevant memory results.
6. Ask the model to select one primary diagram type.
7. Ask the model for a structured `DiagramSpec`, not arbitrary Mermaid text.
8. Validate the structure and remove or mark unsupported claims.
9. Convert `DiagramSpec` into Mermaid.
10. Render the diagram, explanation, evidence, and memory panels.
11. Cache the result using repository, PR number, and head SHA.

## Supported diagram types

Version one supports exactly three primary diagram types:

### Flowchart

Use for algorithms, validation, branching, retries, and error paths.

### Sequence diagram

Use when behavior crosses services, APIs, queues, databases, or external systems.

### State machine

Use when an entity moves through meaningful states or lifecycle transitions.

Choose one primary diagram automatically. The user may override the choice after generation, but generating every diagram type is out of scope for version one.

## Diagram selection rules

- Prefer a **state machine** when named states and transitions dominate the behavior.
- Prefer a **sequence diagram** when ordered interactions across multiple participants dominate.
- Prefer a **flowchart** when conditions, decisions, loops, validation, or algorithmic steps dominate.
- Fall back to a flowchart when confidence is low.
- Display the selected type and a one-sentence reason in the UI.

## Structured output model

The model must return JSON compatible with a Pydantic model similar to this:

```json
{
  "diagram_type": "flowchart",
  "title": "Duplicate asset resolution",
  "selection_reason": "The feature is primarily a branching selection algorithm.",
  "summary": "The change chooses which duplicate asset to retain and synchronizes metadata.",
  "participants": [],
  "nodes": [
    {
      "id": "compare_candidates",
      "label": "Compare duplicate candidates",
      "kind": "decision",
      "evidence_ids": ["evidence_1"]
    }
  ],
  "edges": [
    {
      "source": "compare_candidates",
      "target": "keep_larger",
      "label": "one asset is larger"
    }
  ],
  "evidence": [
    {
      "id": "evidence_1",
      "source": "github",
      "file_path": "src/example.py",
      "line_start": 42,
      "line_end": 58,
      "url": "https://github.com/example/repo/blob/SHA/src/example.py#L42-L58",
      "description": "Implements candidate comparison."
    }
  ],
  "memories": [
    {
      "observation_id": "123",
      "title": "Earlier duplicate-handling decision",
      "relevance": "Explains why metadata is synchronized."
    }
  ]
}
```

## Grounding requirements

- Every important node must reference at least one evidence item.
- Evidence must include a file path or a clearly identified Claude-Mem observation.
- Code links should be pinned to the PR head SHA rather than a mutable branch.
- The UI must distinguish current code evidence from historical memory.
- Unsupported nodes should be removed or visibly marked as inferred.
- Model output must pass Pydantic validation before rendering.

## Streamlit interface

The first screen should contain:

- PRism name and one-sentence pitch
- GitHub PR URL input
- **Explain this PR** button
- One prefilled example PR

The result screen should contain:

- PR title and repository
- Selected diagram type and selection reason
- Interactive Mermaid diagram
- Plain-English explanation
- Expandable code-evidence panel
- Expandable Claude-Mem history panel
- **Export to slides** button
- Clear cached/live indicator

The interface should optimize for a projector: large diagram, limited text, high contrast, and no dense developer-only controls.

## Slide export

Create a short `.pptx`, not a full presentation system:

1. **What changed?** PR title and plain-English summary.
2. **How does it work?** Rendered diagram.
3. **Evidence and history.** Important code links and Claude-Mem observations.

If embedding a rendered diagram delays the core demo, export the Mermaid source and a diagram image first, then add `.pptx` generation.

## Caching and demo fallback

All external responses and final diagram specifications should be cacheable.

Use a cache key containing:

```text
github_owner/repository + pull_request_number + head_sha
```

The `--offline` CLI flag and a corresponding UI toggle should load cached fixtures without calling external services. The interface must clearly label offline results as cached.

Prepare and rehearse one primary PR before judging. Do not depend on a first-time Greptile indexing operation during the demo.

## Priority order

### P0: required for the demo

1. Parse a PR URL.
2. Fetch and cache GitHub PR data.
3. Fetch and cache Greptile context.
4. Generate and validate one structured diagram.
5. Render it in Streamlit.
6. Show clickable code evidence.
7. Retrieve and display relevant Claude-Mem observations.
8. Export an image or Mermaid file.

### P1: only after P0 works

1. Export a three-slide `.pptx`.
2. Allow diagram-type override.
3. Show an earlier diagram beside the new one.
4. Report measured cold-versus-memory-assisted time and context usage.

### Explicitly out of scope

- Organization-wide authentication
- Private-repository OAuth flow
- A complete graph of every file and function
- Multiple simultaneous diagrams
- Collaborative editing
- Cloud deployment
- Custom MCP server
- Real-time repository monitoring

## Definition of done

The MVP is complete when a judge can paste the prepared PR URL and, without opening source files, see:

- A useful automatically selected diagram
- A correct plain-English explanation
- At least three clickable evidence references
- At least one relevant Claude-Mem observation
- A downloadable artifact
- A cached fallback that works without external APIs

## Coding-agent instructions

Treat this README as the source of truth.

1. Implement only P0 until its end-to-end test passes.
2. Use Python for application and orchestration code.
3. Keep external services behind small typed adapters.
4. Make cached fixtures usable from the beginning.
5. Never hardcode API keys or print secrets.
6. Prefer a small working vertical slice over partially implemented integrations.
7. Add tests for URL parsing, structured-output validation, caching, and offline mode.
8. After each milestone, run the tests and the smallest relevant smoke test.
9. Keep Codex as the primary coding agent for hackathon eligibility.

Start by scaffolding the repository, configuration loader, `DiagramSpec` models, PR URL parser, and a fixture-backed end-to-end pipeline. Do not start with styling or slide export.

## Pitch

**PRism turns pull requests into living diagrams that remember how and why software evolved.**
