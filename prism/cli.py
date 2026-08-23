from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from prism.config import get_settings
from prism.pipeline import ExplainPipeline, OfflineDataUnavailable
from prism.pr_url import InvalidPullRequestURL
from prism.rendering.mermaid import render_mermaid


app = typer.Typer(
    name="prism",
    help="Turn a GitHub pull request into an evidence-backed visual explanation.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def explain(
    pr_url: Annotated[str, typer.Argument(help="GitHub pull-request URL")],
    offline: Annotated[
        bool,
        typer.Option("--offline", help="Use only cached or bundled fixture data."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the complete result as JSON."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write Mermaid source to this path."),
    ] = None,
) -> None:
    """Explain one pull request."""

    pipeline = ExplainPipeline(get_settings())
    try:
        result = pipeline.explain(pr_url, offline=offline)
    except (InvalidPullRequestURL, OfflineDataUnavailable) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        console.print(f"[bold red]Analysis failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    mermaid = render_mermaid(result.diagram)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(mermaid + "\n", encoding="utf-8")

    if json_output:
        console.print_json(result.model_dump_json())
        return

    console.print(
        Panel.fit(
            f"[bold]{result.diagram.title}[/bold]\n"
            f"{result.pull_request.reference.slug}#{result.pull_request.reference.number}\n"
            f"Source: {result.source.value}",
            title="PRism",
        )
    )
    console.print(f"[bold cyan]{result.diagram.diagram_type.value}[/bold cyan]")
    console.print(result.diagram.selection_reason)
    console.print()
    console.print(Markdown(result.diagram.summary))
    console.print()
    console.print(Panel(mermaid, title="Mermaid", border_style="blue"))

    evidence_table = Table(title="Evidence")
    evidence_table.add_column("ID", style="cyan")
    evidence_table.add_column("Source")
    evidence_table.add_column("Location")
    evidence_table.add_column("Description")
    for item in result.diagram.evidence:
        location = item.file_path or item.observation_id or item.url or "—"
        evidence_table.add_row(item.id, item.source.value, location, item.description)
    console.print(evidence_table)

    if result.diagram.memories:
        memory_table = Table(title="Claude-Mem history")
        memory_table.add_column("Observation")
        memory_table.add_column("Why it matters")
        for memory in result.diagram.memories:
            memory_table.add_row(memory.title, memory.relevance)
        console.print(memory_table)

    for warning in result.warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")
    if output:
        console.print(f"[green]Mermaid written to[/green] {output}")


@app.command("show-config")
def show_config() -> None:
    """Show configuration status without revealing secrets."""

    settings = get_settings()
    payload = {
        "greptile_api_key": bool(settings.greptile_api_key),
        "github_token": bool(settings.github_token),
        "codex_cli_path": settings.codex_cli_path,
        "codex_model": settings.codex_model,
        "codex_cli_timeout_seconds": settings.codex_cli_timeout_seconds,
        "claude_mem_enabled": settings.claude_mem_enabled,
        "claude_mem_base_url": settings.resolved_claude_mem_base_url(),
        "cache_dir": str(settings.prism_cache_dir),
        "offline_demo": settings.prism_offline_demo,
    }
    console.print_json(json.dumps(payload))


if __name__ == "__main__":
    app()
