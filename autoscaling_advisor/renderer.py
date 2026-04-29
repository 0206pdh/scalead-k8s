from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import RecommendationResult

_STATUS_ICON = {
    "ok":    "[bold green]✓[/bold green]",
    "warn":  "[bold yellow]⚠[/bold yellow]",
    "error": "[bold red]✗[/bold red]",
    "info":  "[bold blue]ℹ[/bold blue]",
}

_STATUS_COLOR = {
    "ok": "green",
    "warn": "yellow",
    "error": "red",
    "info": "blue",
}


def render(result: RecommendationResult, console: Console | None = None) -> None:
    if console is None:
        console = Console()

    # ── Header ───────────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        f"[bold white]Autoscaling Advisor[/bold white]  "
        f"[dim]→  {result.scan.source}[/dim]",
        style="bold blue",
        padding=(0, 2),
    ))

    # ── Config Audit ─────────────────────────────────────────────────────
    table = Table(
        title="[bold]Config Audit[/bold]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold dim",
        padding=(0, 1),
    )
    table.add_column("항목", style="bold", min_width=22)
    table.add_column("", justify="center", width=3)
    table.add_column("내용")

    for item in result.audit:
        icon = _STATUS_ICON[item.status]
        color = _STATUS_COLOR[item.status]
        table.add_row(item.check, icon, f"[{color}]{item.detail}[/{color}]")

    console.print(table)
    console.print()

    # ── Recommended Strategy ─────────────────────────────────────────────
    best = result.best
    reason_lines = "\n".join(f"  • {r}" for r in best.reasons) if best.reasons else ""
    console.print(Panel(
        f"[bold green]{best.display_name}[/bold green]"
        f"  [dim]score {best.score}/100[/dim]"
        + (f"\n\n{reason_lines}" if reason_lines else ""),
        title="[bold]추천 전략[/bold]",
        border_style="green",
        padding=(0, 2),
    ))

    # ── Suggested Changes ────────────────────────────────────────────────
    if best.changes:
        console.print("[bold]권장 변경사항[/bold]")
        for c in best.changes:
            console.print(
                f"  [dim]•[/dim] [cyan]{c.path}[/cyan]"
                f"  [red]{c.old}[/red] → [green]{c.new}[/green]"
                f"  [dim]# {c.reason}[/dim]"
            )
        console.print()

    # ── Risks ────────────────────────────────────────────────────────────
    if best.risks:
        console.print("[bold yellow]리스크[/bold yellow]")
        for r in best.risks:
            console.print(f"  [yellow]⚠[/yellow]  {r}")
        console.print()

    # ── Strategy Comparison ──────────────────────────────────────────────
    console.print("[bold]전략 비교[/bold]")
    score_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    score_table.add_column("전략", min_width=20)
    score_table.add_column("점수", justify="right", width=5)
    score_table.add_column("바", width=12)

    for i, c in enumerate(result.candidates):
        filled = round(c.score / 10)
        bar = "█" * filled + "░" * (10 - filled)
        is_best = i == 0
        style = "bold green" if is_best else "dim"
        score_table.add_row(
            Text(("★ " if is_best else "  ") + c.display_name, style=style),
            Text(str(c.score), style=style),
            Text(bar, style="green" if is_best else "dim"),
        )

    console.print(score_table)
    console.print()
