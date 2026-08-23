# PRism

PRism turns a GitHub pull request into an evidence-backed visual explanation and remembers how the feature evolves.

> Paste a PR URL to see where the change fits, how it works, and why it changed.

## Quick setup

### 1. Check the prerequisites

PRism requires Python 3.11 or newer, `uv`, and the Codex CLI.

```bash
python3 --version
uv --version
codex --version
```

On macOS, install missing tools with:

```bash
brew install uv
curl -fsSL https://chatgpt.com/codex/install.sh | sh
```

See the official [Codex CLI documentation](https://developers.openai.com/codex/cli) for other
platforms and installation methods.

### 2. Install the Python dependencies

From the repository root:

```bash
uv sync --extra dev
```

### 3. Sign in to Codex CLI

```bash
codex
codex login status
```

Choose **Sign in with ChatGPT** when prompted. PRism uses this Codex CLI session, so an
`OPENAI_API_KEY` is not required.

### 4. Configure PRism

```bash
cp .env.example .env
```

Open `.env` and set:

```dotenv
GREPTILE_API_KEY=your_greptile_key
GITHUB_TOKEN=your_github_token
CODEX_MODEL=gpt-5.6-sol
```

- `GREPTILE_API_KEY` should be the hackathon-provided key. The repository must also be available
  to Greptile for repository-aware context.
- `GITHUB_TOKEN` is recommended for public repositories and required when accessing a private
  repository. Never commit this token.
- `CODEX_MODEL=gpt-5.6-sol` prioritizes diagram quality for judging. Use `gpt-5.6-terra` if live
  generation needs to be faster.
- Claude-Mem is optional. Leave `CLAUDE_MEM_BASE_URL` empty for automatic local worker discovery,
  or set `CLAUDE_MEM_ENABLED=false` until Claude-Mem is running. The worker must contain at least
  one observation before PRism can show relevant history.

Confirm that configuration was loaded without printing secret values:

```bash
uv run prism show-config
```

### 5. Run the website

```bash
uv run streamlit run app.py
```

Open `http://localhost:8501` and choose the mode that matches the PR:

- For a real GitHub PR, leave **Offline demo** unchecked. PRism uses GitHub, Greptile, and Codex.
- For the bundled example, enable **Offline demo** and use
  `https://github.com/acme-inc/checkout-platform/pull/42`.

An arbitrary PR cannot run in offline mode until it has been analyzed live and cached. If you see
`No cached or fixture data is available`, uncheck **Offline demo** and submit the PR again.

### 6. Verify the CLI and tests

```bash
uv run prism explain https://github.com/karpathy/nanochat/pull/826
uv run pytest
```

For deterministic quality and local fallback-latency measurements, see [EVALS.md](EVALS.md):

```bash
uv run prism-evals --iterations 100
```

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

## Current build

The first working vertical slice is implemented:

- Streamlit website and Typer CLI
- Strict GitHub PR URL parsing
- Live GitHub PR and changed-file retrieval
- Greptile MCP adapter with graceful degradation
- Claude-Mem local search adapter with automatic worker-port discovery
- Codex CLI structured-output generation with a deterministic fallback
- Pydantic evidence and graph validation
- Flowchart, sequence-diagram, and state-machine Mermaid rendering
- SHA-aware JSON caching and offline fixtures
- Mermaid and complete-analysis downloads
- Automated tests and a browser-tested offline demo

Slide export remains a P1 feature. The bundled example is deliberately synthetic so it works
without API credentials:

```text
https://github.com/acme-inc/checkout-platform/pull/42
```

## Product roles

- **GitHub** provides PR metadata, changed files, patches, links, and source evidence.
- **Greptile** provides PR-review and repository-aware context from an indexed codebase.
- **Claude-Mem** retrieves previous discoveries, decisions, and diagrams.
- **Codex CLI** converts the collected context into a validated structured diagram specification.
- **PRism** renders the result and exports it for sharing.

## Technical approach

Build the first version in Python.

- Python 3.11 or newer
- Streamlit for the demo website
- Typer and Rich for an optional CLI using the same pipeline
- Pydantic for structured diagram models and validation
- HTTPX for GitHub, Greptile, and Claude-Mem requests
- Codex CLI non-interactive mode for diagram generation
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
│   ├── pr_url.py
│   ├── integrations/
│   │   ├── github.py
│   │   ├── greptile.py
│   │   └── claude_mem.py
│   ├── generation/
│   │   └── generator.py
│   ├── rendering/
│   │   └── mermaid.py
│   └── cache.py
├── fixtures/
│   └── demo/
└── tests/
    ├── test_pr_url.py
    ├── test_models.py
    ├── test_mermaid.py
    └── test_pipeline.py
```

Keep this as one repository and one Python environment. Do not create microservices for the hackathon version.

## Configuration reference

Create `.env` locally from `.env.example`.

```dotenv
# Recommended for repository-aware Greptile context
GREPTILE_API_KEY=

# Recommended for dependable GitHub API access
GITHUB_TOKEN=

# Non-secret configuration
GREPTILE_MCP_URL=https://api.greptile.com/mcp

# Codex CLI uses the account authenticated by `codex login`; no OpenAI API key is needed
CODEX_CLI_PATH=codex
CODEX_MODEL=gpt-5.6-sol
CODEX_CLI_TIMEOUT_SECONDS=240

# Optional local Claude-Mem connection
CLAUDE_MEM_ENABLED=true
CLAUDE_MEM_BASE_URL=
CLAUDE_MEM_TIMEOUT_SECONDS=30

# Demo reliability
PRISM_CACHE_DIR=.cache/prism
PRISM_OFFLINE_DEMO=false
LOG_LEVEL=INFO
REQUEST_TIMEOUT_SECONDS=90
```

Never commit `.env`. Commit only `.env.example` with empty values.

The Greptile API key must have access to the selected, indexed demo repository. For local Claude-Mem, resolve the worker port from `~/.claude-mem/settings.json`; a separate Claude-Mem API key is normally unnecessary.

PRism runs `codex exec` in an ephemeral, read-only sandbox and constrains its final response with
the `DiagramSpec` JSON Schema. Check local authentication before the demo:

```bash
codex login status
```

No OpenAI API key is required when Codex CLI is authenticated with ChatGPT. PRism does not pass
the GitHub or Greptile token into the Codex subprocess.

## Useful commands

```bash
# Install or update dependencies
uv sync --extra dev

# Show configuration status without revealing secrets
uv run prism show-config

# Run the website
uv run streamlit run app.py

# Run the CLI
uv run prism explain https://github.com/OWNER/REPOSITORY/pull/NUMBER

# Ignore cached context after adding new Claude-Mem observations
uv run prism explain PR_URL --refresh

# Use cached data during the presentation
uv run prism explain PR_URL --offline

# Run tests
uv run pytest
```

To try the bundled example immediately, enable **Offline demo** in the website or run:

```bash
uv run prism explain https://github.com/acme-inc/checkout-platform/pull/42 --offline
```

Before a live Greptile demo, verify the organizer-provided key, repository indexing, and MCP tool
names. Greptile failures are surfaced as warnings so GitHub plus Codex analysis can still finish.

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
