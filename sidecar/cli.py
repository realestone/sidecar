"""Sidecar CLI — Claude Code session analysis tools."""

from __future__ import annotations

import json
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .errors import SidecarError
from .extraction.briefing import (
    get_status,
    list_briefings,
    load_briefing,
    run_pipeline,
)
from .extraction.reader import list_sessions

console = Console()


@click.group()
@click.version_option(package_name="sidecar")
def cli():
    """Sidecar CLI - Claude Code session analysis tools."""


@cli.command()
@click.option("--session-id", "-s", default=None, help="Session ID to analyze")
@click.option("--project", "-p", default=None, help="Project path")
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "markdown", "text"]),
    default="text",
    help="Output format",
)
def analyze(session_id: str | None, project: str | None, output: str):
    """Analyze a Claude Code session and generate a briefing."""
    try:
        briefing = run_pipeline(session_id=session_id, project_path=project)
    except SidecarError as e:
        console.print(f"[red]Error:[/red] {e.message}")
        sys.exit(1)

    if output == "json":
        click.echo(json.dumps(briefing.to_dict(), indent=2))
    elif output == "markdown":
        click.echo(briefing.to_markdown())
    else:
        console.print(
            Panel(
                briefing.session_summary,
                title=f"Session Briefing: {briefing.session_id[:8]}...",
                subtitle=briefing.project_path,
            )
        )

        if briefing.what_got_built:
            table = Table(title="What Got Built")
            table.add_column("File", style="cyan")
            table.add_column("Description")
            for item in briefing.what_got_built:
                table.add_row(
                    item.get("file", ""),
                    item.get("description", ""),
                )
            console.print(table)

        if briefing.how_pieces_connect:
            console.print(
                Panel(briefing.how_pieces_connect, title="How Pieces Connect")
            )

        if briefing.will_bite_you:
            wb = briefing.will_bite_you
            console.print(
                Panel(
                    f"[bold]{wb.get('issue', '')}[/bold]\n"
                    f"Where: {wb.get('where', '')}\n"
                    f"Why: {wb.get('why', '')}\n"
                    f"Check: {wb.get('what_to_check', '')}",
                    title="Will Bite You",
                    border_style="red",
                )
            )

        if briefing.patterns_used:
            table = Table(title="Patterns Used")
            table.add_column("Pattern", style="green")
            table.add_column("Where")
            table.add_column("Explanation")
            for p in briefing.patterns_used:
                table.add_row(
                    p.get("pattern", ""),
                    p.get("where", ""),
                    p.get("explained", ""),
                )
            console.print(table)


@cli.command()
@click.option("--project", "-p", default=None, help="Project path")
def sessions(project: str | None):
    """List Claude Code sessions."""
    session_list = list_sessions(project_path=project)

    if not session_list:
        console.print("[yellow]No sessions found.[/yellow]")
        return

    table = Table(title="Claude Code Sessions")
    table.add_column("Session ID", style="cyan", max_width=12)
    table.add_column("Summary")
    table.add_column("Messages", justify="right")
    table.add_column("Modified")
    table.add_column("Project")

    for s in session_list:
        table.add_row(
            s.session_id[:12] + "...",
            s.summary[:60] if s.summary else s.first_prompt[:60],
            str(s.message_count),
            s.modified[:19] if s.modified else "",
            s.project_path,
        )

    console.print(table)


@cli.command()
@click.option("--session-id", "-s", default=None, help="Session ID")
def briefing(session_id: str | None):
    """View a previously generated briefing."""
    if session_id:
        b = load_briefing(session_id)
        if not b:
            console.print(f"[red]No briefing found for session {session_id}[/red]")
            sys.exit(1)
        click.echo(b.to_markdown())
    else:
        briefings = list_briefings()
        if not briefings:
            console.print("[yellow]No briefings generated yet.[/yellow]")
            return

        table = Table(title="Generated Briefings")
        table.add_column("Session ID", style="cyan", max_width=12)
        table.add_column("Summary")
        table.add_column("Created")

        for b in briefings:
            table.add_row(
                b["session_id"][:12] + "...",
                b.get("session_summary", "")[:60],
                b.get("created_at", "")[:19],
            )
        console.print(table)


@cli.command()
def status():
    """Show sidecar status overview."""
    s = get_status()

    console.print(Panel(
        f"Sessions: {s['total_sessions']}\n"
        f"Briefings: {s['total_briefings']}\n"
        f"Projects: {', '.join(s.get('projects', [])) or 'none'}",
        title="Sidecar Status",
    ))

    insights = s.get("insights", {})
    if insights:
        console.print(Panel(
            f"Briefing count: {insights.get('briefing_count', 0)}\n"
            f"Patterns: {', '.join(insights.get('recurring_patterns', [])) or 'none'}\n"
            f"Known issues: {len(insights.get('known_issues', []))}",
            title="Accumulated Insights",
        ))


def main():
    cli()


if __name__ == "__main__":
    main()
