"""Sidecar CLI — Claude Code session analysis tools."""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .errors import SidecarError
from .extraction.briefing import (
    BRIEFINGS_DIR,
    get_status,
    list_briefings,
    load_briefing,
    run_pipeline,
    save_briefing,
    update_insights,
)
from .extraction.reader import list_sessions
from .hooks.common import remove_lock
from .hooks.installer import check_hooks, install_hooks, uninstall_hooks

console = Console()

LOGS_DIR = Path.home() / ".config" / "sidecar" / "logs"


def _setup_background_logging(session_id: str) -> logging.Logger:
    """Configure logging for background mode."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"analyze-{session_id}.log"

    logger = logging.getLogger(f"sidecar.analyze.{session_id}")
    logger.setLevel(logging.INFO)

    # Clear existing handlers
    logger.handlers.clear()

    handler = logging.FileHandler(log_path)
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)

    return logger


def _estimate_tokens(char_count: int) -> int:
    """Estimate token count from character count (rough: 4 chars per token)."""
    return char_count // 4


def _send_notification(session_id: str) -> None:
    """Send desktop notification on completion."""
    short_id = session_id[:8]
    title = "Sidecar"
    message = f"Session {short_id} analyzed"

    system = platform.system()

    try:
        if system == "Darwin":  # macOS
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{message}" with title "{title}"',
                ],
                capture_output=True,
                timeout=5,
            )
        elif system == "Linux":
            subprocess.run(
                ["notify-send", title, message],
                capture_output=True,
                timeout=5,
            )
        # Windows and others: just skip
    except (subprocess.SubprocessError, OSError):
        pass


def _save_snapshot_briefing(
    briefing,
    briefings_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Save briefing with timestamp suffix for snapshots."""
    out_dir = briefings_dir or BRIEFINGS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"{briefing.session_id}-{timestamp}"

    json_path = out_dir / f"{filename}.json"
    md_path = out_dir / f"{filename}.md"

    json_path.write_text(json.dumps(briefing.to_dict(), indent=2))
    md_path.write_text(briefing.to_markdown())

    return json_path, md_path


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
@click.option("--background", is_flag=True, help="Run silently, log to file")
@click.option(
    "--snapshot", is_flag=True, help="Save with timestamp suffix (for pre-compact)"
)
@click.option("--notify", is_flag=True, help="Send desktop notification on completion")
def analyze(
    session_id: str | None,
    project: str | None,
    output: str,
    background: bool,
    snapshot: bool,
    notify: bool,
):
    """Analyze a Claude Code session and generate a briefing."""
    if background:
        _run_background_analysis(session_id, project, snapshot, notify)
    else:
        _run_interactive_analysis(session_id, project, output, snapshot, notify)


def _run_background_analysis(
    session_id: str | None,
    project: str | None,
    snapshot: bool,
    notify: bool,
) -> None:
    """Run analysis in background mode with logging."""
    # Determine session_id for logging
    log_session = session_id or "latest"
    logger = _setup_background_logging(log_session)

    try:
        logger.info(f"Analyzing session {log_session}...")

        # Import here to get filtered session info
        from .extraction.filter import filter_session
        from .extraction.reader import get_latest_session, read_session

        # Resolve session
        if session_id is None:
            session_info = get_latest_session(project_path=project)
            session_id = session_info.session_id
            if not project:
                project = session_info.project_path

        # Read and filter to estimate tokens
        messages = read_session(session_id, project_path=project)
        filtered = filter_session(session_id, messages)

        # Estimate tokens from filtered content
        total_chars = sum(
            len(str(msg.content)) for msg in filtered.messages
        )
        estimated_tokens = _estimate_tokens(total_chars)
        estimated_cost = estimated_tokens * 0.00000025  # Haiku input pricing

        logger.info(
            f"Filtered: {len(filtered.messages)} messages, ~{estimated_tokens:,} tokens"
        )
        logger.info(
            f"Sending to claude-haiku-4-5 (est. cost: ~${estimated_cost:.4f})"
        )

        # Run full pipeline (will re-filter but that's fine)
        briefing = run_pipeline(session_id=session_id, project_path=project)

        # Save (snapshot or regular)
        if snapshot:
            json_path, _ = _save_snapshot_briefing(briefing)
            # Don't update insights for snapshots
        else:
            json_path, _ = save_briefing(briefing)
            update_insights(briefing)

        logger.info(f"Briefing saved: {json_path}")

        if notify:
            _send_notification(session_id)

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        import traceback

        logger.error(traceback.format_exc())

    finally:
        # Always remove lock
        if session_id:
            remove_lock(session_id)
        # Always exit 0 in background mode
        sys.exit(0)


def _run_interactive_analysis(
    session_id: str | None,
    project: str | None,
    output: str,
    snapshot: bool,
    notify: bool,
) -> None:
    """Run analysis in interactive mode with console output."""
    try:
        briefing = run_pipeline(session_id=session_id, project_path=project)

        # Handle snapshot mode
        if snapshot:
            _save_snapshot_briefing(briefing)
            # Don't update insights for snapshots (already done by run_pipeline,
            # but snapshot should skip it - we need to handle this differently)

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

    if notify:
        _send_notification(briefing.session_id)


@cli.command()
@click.option("--project", "-p", default=None, help="Project path")
def sessions(project: str | None):
    """List Claude Code sessions."""
    session_list = list_sessions(project_path=project)

    if not session_list:
        console.print("[yellow]No sessions found.[/yellow]")
        return

    table = Table(title="Claude Code Sessions")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Session ID", style="cyan")
    table.add_column("Summary")
    table.add_column("Msgs", justify="right")
    table.add_column("Modified")

    for i, s in enumerate(session_list, 1):
        table.add_row(
            str(i),
            s.session_id,
            (s.summary or s.first_prompt)[:50],
            str(s.message_count),
            s.modified[:10] if s.modified else "",
        )

    console.print(table)
    console.print("\n[dim]Use: sidecar-cli analyze -s <session-id>[/dim]")


@cli.command()
@click.option("--session-id", "-s", default=None, help="Session ID")
@click.option("--detail", is_flag=True, help="Show file details and key code")
@click.option(
    "--full", is_flag=True, help="Show everything including patterns and concepts"
)
def briefing(session_id: str | None, detail: bool, full: bool):
    """View a previously generated briefing."""
    if session_id:
        b = load_briefing(session_id)
        if not b:
            console.print(f"[red]No briefing found for session {session_id}[/red]")
            sys.exit(1)

        if full:
            # Full view: show everything (existing markdown behavior)
            click.echo(b.to_markdown())
        elif detail:
            # Detail view: summary + what_got_built with descriptions + how_pieces_connect
            _print_detail_view(b)
        else:
            # Compact view: just essentials
            _print_compact_view(b)
    else:
        briefings = list_briefings()
        if not briefings:
            console.print("[yellow]No briefings generated yet.[/yellow]")
            return

        table = Table(title="Generated Briefings")
        table.add_column("#", style="dim", justify="right")
        table.add_column("Session ID", style="cyan")
        table.add_column("Summary")
        table.add_column("Created")

        for i, b in enumerate(briefings, 1):
            table.add_row(
                str(i),
                b["session_id"],
                b.get("session_summary", "")[:50],
                b.get("created_at", "")[:10],
            )
        console.print(table)
        console.print("\n[dim]Use: sidecar-cli briefing -s <session-id>[/dim]")


def _print_compact_view(b) -> None:
    """Print compact briefing view - just essentials."""
    # Header line
    file_count = len(b.what_got_built)
    pattern_count = len(b.patterns_used)
    issue_count = 1 if b.will_bite_you else 0

    console.print(
        f"[bold]Session {b.session_id[:8]}[/bold] — {b.session_summary[:60]}"
    )
    console.print(
        f"  {file_count} files changed | {pattern_count} patterns | {issue_count} issue"
    )
    console.print()

    # Will bite you (if present)
    if b.will_bite_you:
        wb = b.will_bite_you
        console.print(f"  [yellow]Warning:[/yellow] {wb.get('issue', '')}")
        where = wb.get("where", "")
        if where:
            console.print(f"    -> {where}")
        console.print()

    # File list (names only)
    if b.what_got_built:
        files = [item.get("file", "unknown") for item in b.what_got_built]
        console.print(f"  Files: {', '.join(files)}")


def _print_detail_view(b) -> None:
    """Print detail briefing view - adds descriptions and how_pieces_connect."""
    # Header
    console.print(f"[bold]Session {b.session_id[:8]}[/bold] — {b.project_path}")
    console.print()

    # Summary
    console.print(Panel(b.session_summary, title="Summary"))

    # What got built with descriptions
    if b.what_got_built:
        table = Table(title="What Got Built")
        table.add_column("File", style="cyan")
        table.add_column("Description")
        table.add_column("Key Code", style="dim")
        for item in b.what_got_built:
            table.add_row(
                item.get("file", ""),
                item.get("description", ""),
                item.get("key_code", "")[:50] if item.get("key_code") else "",
            )
        console.print(table)

    # How pieces connect
    if b.how_pieces_connect:
        console.print(Panel(b.how_pieces_connect, title="How Pieces Connect"))

    # Will bite you
    if b.will_bite_you:
        wb = b.will_bite_you
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


@cli.command()
def status():
    """Show sidecar status overview."""
    s = get_status()

    console.print(
        Panel(
            f"Sessions: {s['total_sessions']}\n"
            f"Briefings: {s['total_briefings']}\n"
            f"Projects: {', '.join(s.get('projects', [])) or 'none'}",
            title="Sidecar Status",
        )
    )

    insights = s.get("insights", {})
    if insights:
        console.print(
            Panel(
                f"Briefing count: {insights.get('briefing_count', 0)}\n"
                f"Patterns: {', '.join(insights.get('recurring_patterns', [])) or 'none'}\n"
                f"Known issues: {len(insights.get('known_issues', []))}",
                title="Accumulated Insights",
            )
        )


@cli.command()
@click.option("--remove", is_flag=True, help="Remove Sidecar hooks")
@click.option("--status", "show_status", is_flag=True, help="Show hook registration status")
def setup(remove: bool, show_status: bool):
    """Register or remove Sidecar hooks in Claude Code."""
    if show_status:
        _show_hook_status()
    elif remove:
        _remove_hooks()
    else:
        _install_hooks()


def _show_hook_status() -> None:
    """Show current hook registration status."""
    status = check_hooks()

    console.print(Panel("Hook Registration Status", style="bold"))

    for event, registered in status.items():
        if registered:
            console.print(f"  [green]✓[/green] {event}: registered")
        else:
            console.print(f"  [dim]✗[/dim] {event}: not registered")


def _install_hooks() -> None:
    """Install Sidecar hooks."""
    results = install_hooks()

    console.print(Panel("Installing Sidecar Hooks", style="bold"))

    for event, result in results.items():
        if result == "added":
            console.print(f"  [green]✓[/green] {event}: added")
        else:
            console.print(f"  [yellow]~[/yellow] {event}: already exists")

    console.print()
    console.print(
        "[yellow]Warning:[/yellow] Sidecar hooks will automatically analyze sessions using the Anthropic API."
    )
    console.print("  Model: claude-haiku-4-5 (~$0.001 per session analysis)")
    console.print("  API key: from ANTHROPIC_API_KEY environment variable")
    console.print("  Disable anytime: [dim]sidecar-cli setup --remove[/dim]")


def _remove_hooks() -> None:
    """Remove Sidecar hooks."""
    results = uninstall_hooks()

    console.print(Panel("Removing Sidecar Hooks", style="bold"))

    for event, result in results.items():
        if result == "removed":
            console.print(f"  [green]✓[/green] {event}: removed")
        else:
            console.print(f"  [dim]~[/dim] {event}: not found")


def main():
    cli()


if __name__ == "__main__":
    main()
