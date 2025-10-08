"""CLI commands for managing stock splits."""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

from src.lib.db import db_session
from src.models import Security, StockSplit
from src.services.splits_service import SplitsService

console = Console()


@click.group(name="splits")
def splits_group() -> None:
    """Manage stock split data."""
    pass


@splits_group.command(name="sync")
@click.option(
    "--ticker",
    "-t",
    help="Ticker symbol to sync (e.g., AAPL)",
)
@click.option(
    "--all",
    "sync_all",
    is_flag=True,
    help="Sync splits for all securities in database",
)
def sync_splits(ticker: str | None, sync_all: bool) -> None:
    """Sync stock splits from yfinance.

    Examples:
        stocks-helper splits sync --ticker AAPL
        stocks-helper splits sync --all
    """
    if not ticker and not sync_all:
        console.print("[red]Error: Must specify --ticker or --all[/red]")
        raise click.Abort()

    if ticker and sync_all:
        console.print("[red]Error: Cannot specify both --ticker and --all[/red]")
        raise click.Abort()

    service = SplitsService()

    try:
        with db_session() as session:
            if sync_all:
                console.print("[bold]Syncing splits for all securities...[/bold]\n")
                results = service.sync_all_securities(session)

                # Display summary table
                table = Table(title="Sync Results")
                table.add_column("Ticker", style="cyan")
                table.add_column("New Splits", justify="right", style="green")
                table.add_column("Status", style="yellow")

                total_added = 0
                total_errors = 0

                for ticker_name, count in results.items():
                    if count == -1:
                        status = "[red]ERROR[/red]"
                        total_errors += 1
                    elif count == 0:
                        status = "No new splits"
                    else:
                        status = "[green]✓ Synced[/green]"
                        total_added += count

                    table.add_row(ticker_name, str(count) if count >= 0 else "N/A", status)

                console.print(table)
                console.print(
                    f"\n[bold]Total:[/bold] {total_added} new split(s) added, "
                    f"{total_errors} error(s)\n"
                )

            else:
                # Sync single ticker
                # Type guard: ticker is not None in this branch (checked at line 42-44)
                assert ticker is not None
                console.print(f"[bold]Syncing splits for {ticker}...[/bold]\n")

                # Find security by ticker
                stmt = select(Security).where(Security.ticker == ticker)
                security = session.execute(stmt).scalar_one_or_none()

                if not security:
                    console.print(f"[red]✗ Security not found: {ticker}[/red]")
                    console.print(
                        "\n[dim]Tip: Import transactions first to create the security[/dim]\n"
                    )
                    raise click.Abort()

                added = service.sync_splits_from_yfinance(session, security.id, ticker)
                session.commit()

                if added > 0:
                    console.print(f"[green]✓ Added {added} new split(s) for {ticker}[/green]")

                    # Show the splits
                    splits = service.get_splits_for_security(session, security.id)
                    display_splits(splits)
                else:
                    console.print(f"[yellow]No new splits found for {ticker}[/yellow]")
                    console.print("[dim]All splits are already up to date[/dim]\n")

    except Exception as e:
        console.print(f"[red]✗ Sync failed: {e}[/red]")
        raise click.Abort()


@splits_group.command(name="list")
@click.option(
    "--ticker",
    "-t",
    required=True,
    help="Ticker symbol to show splits for",
)
def list_splits(ticker: str) -> None:
    """List all splits for a security.

    Example:
        stocks-helper splits list --ticker AAPL
    """
    with db_session() as session:
        # Find security by ticker
        stmt = select(Security).where(Security.ticker == ticker)
        security = session.execute(stmt).scalar_one_or_none()

        if not security:
            console.print(f"[red]✗ Security not found: {ticker}[/red]")
            raise click.Abort()

        # Get splits
        service = SplitsService()
        splits = service.get_splits_for_security(session, security.id)

        if not splits:
            console.print(f"\n[yellow]No splits found for {ticker}[/yellow]\n")
            return

        display_splits(splits)


def display_splits(splits: list[StockSplit]) -> None:
    """Display splits in a table.

    Args:
        splits: List of StockSplit objects
    """
    table = Table(title=f"Stock Splits ({len(splits)} total)")
    table.add_column("Date", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Ratio", style="yellow")
    table.add_column("Split", style="green")
    table.add_column("Notes", style="dim")

    for split in splits:
        split_type = "Forward" if split.split_ratio >= 1 else "Reverse"
        ratio_str = f"{split.split_ratio:.4f}".rstrip("0").rstrip(".")

        table.add_row(
            str(split.split_date),
            split_type,
            ratio_str,
            f"{split.split_from}:{split.split_to}",
            split.notes or "",
        )

    console.print()
    console.print(table)
    console.print()
