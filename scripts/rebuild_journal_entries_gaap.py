#!/usr/bin/env python3
"""Rebuild all journal entries with GAAP/IFRS compliance.

This script:
1. Deletes all existing journal entries, lots, and allocations
2. Recreates chart of accounts with new GAAP/IFRS accounts
3. Reprocesses all transactions in chronological order
4. Creates security lots for BUY transactions
5. Uses FIFO matching for SELL transactions
6. Properly tracks realized gains/losses

Usage:
    python scripts/rebuild_journal_entries_gaap.py [--portfolio-id ID] [--dry-run]
"""

import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from sqlalchemy import delete, select

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lib.db import db_session
from src.models import (
    ChartAccount,
    JournalEntry,
    JournalLine,
    Portfolio,
    Reconciliation,
    SecurityAllocation,
    SecurityLot,
    Transaction,
)
from src.services.accounting_service import (
    initialize_chart_of_accounts,
    record_transaction_as_journal_entry,
)

console = Console()


def rebuild_journal_entries(
    portfolio_id: str,
    dry_run: bool = False,
) -> None:
    """Rebuild all journal entries for a portfolio with GAAP/IFRS compliance.

    Args:
        portfolio_id: Portfolio ID to rebuild
        dry_run: If True, don't commit changes
    """
    with db_session() as session:
        # Get portfolio
        portfolio = session.get(Portfolio, portfolio_id)
        if not portfolio:
            console.print(f"[red]Portfolio {portfolio_id} not found[/red]")
            return

        console.print(f"\n[cyan]Rebuilding journal entries for portfolio: {portfolio.name}[/cyan]\n")

        # Step 1: Get all transactions in chronological order
        console.print("[yellow]1. Loading transactions...[/yellow]")
        transactions = (
            session.execute(
                select(Transaction)
                .join(Transaction.account)
                .where(Transaction.account.has(portfolio_id=portfolio_id))
                .order_by(Transaction.date, Transaction.created_at)
            )
            .scalars()
            .all()
        )

        console.print(f"   Found {len(transactions)} transactions")

        if dry_run:
            console.print("\n[yellow]DRY RUN - No changes will be made[/yellow]\n")
            return

        # Step 2: Delete existing journal entries and lots
        console.print("\n[yellow]2. Deleting existing journal entries and lots...[/yellow]")

        # Delete in correct order due to foreign keys
        stmt = delete(SecurityAllocation).where(
            SecurityAllocation.lot.has(
                SecurityLot.holding.has(portfolio_id=portfolio_id)
            )
        )
        result = session.execute(stmt)
        console.print(f"   Deleted {result.rowcount} security allocations")

        stmt = delete(SecurityLot).where(
            SecurityLot.holding.has(portfolio_id=portfolio_id)
        )
        result = session.execute(stmt)
        console.print(f"   Deleted {result.rowcount} security lots")

        stmt = delete(Reconciliation).where(
            Reconciliation.journal_entry.has(portfolio_id=portfolio_id)
        )
        result = session.execute(stmt)
        console.print(f"   Deleted {result.rowcount} reconciliations")

        stmt = delete(JournalLine).where(
            JournalLine.journal_entry.has(portfolio_id=portfolio_id)
        )
        result = session.execute(stmt)
        console.print(f"   Deleted {result.rowcount} journal lines")

        stmt = delete(JournalEntry).where(JournalEntry.portfolio_id == portfolio_id)
        result = session.execute(stmt)
        console.print(f"   Deleted {result.rowcount} journal entries")

        session.flush()

        # Step 3: Delete and recreate chart of accounts
        console.print("\n[yellow]3. Recreating chart of accounts with GAAP/IFRS accounts...[/yellow]")

        stmt = delete(ChartAccount).where(ChartAccount.portfolio_id == portfolio_id)
        result = session.execute(stmt)
        console.print(f"   Deleted {result.rowcount} chart accounts")

        accounts = initialize_chart_of_accounts(session, portfolio_id)
        console.print(f"   Created {len(accounts)} chart accounts")
        console.print("   [green]✓[/green] New accounts include:")
        console.print("     - Realized Gains/Losses (4200/5200)")
        console.print("     - Unrealized Gains/Losses (4210/5210)")
        console.print("     - Fair Value Adjustment (1210)")

        session.flush()

        # Step 4: Reprocess all transactions
        console.print("\n[yellow]4. Reprocessing transactions with GAAP/IFRS logic...[/yellow]")

        success_count = 0
        error_count = 0
        errors = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Processing {len(transactions)} transactions...",
                total=len(transactions),
            )

            for txn in transactions:
                try:
                    # Record transaction with new GAAP/IFRS logic
                    record_transaction_as_journal_entry(
                        session=session,
                        transaction=txn,
                        accounts=accounts,
                    )
                    success_count += 1
                    progress.advance(task)

                except Exception as e:
                    error_count += 1
                    errors.append((txn, str(e)))
                    progress.advance(task)

        console.print(f"\n   [green]✓ Successfully processed: {success_count}[/green]")
        if error_count > 0:
            console.print(f"   [red]✗ Errors: {error_count}[/red]")

        # Step 5: Show errors if any
        if errors:
            console.print("\n[red]Errors encountered:[/red]")
            for txn, error in errors[:10]:  # Show first 10 errors
                console.print(f"   Transaction {txn.id} ({txn.date}): {error}")
            if len(errors) > 10:
                console.print(f"   ... and {len(errors) - 10} more errors")

        # Step 6: Get statistics
        console.print("\n[yellow]5. Verifying results...[/yellow]")

        # Count lots created
        lot_count = session.execute(
            select(SecurityLot)
            .where(SecurityLot.holding.has(portfolio_id=portfolio_id))
        ).scalar()
        lot_count = session.execute(
            select(SecurityLot)
            .where(SecurityLot.holding.has(portfolio_id=portfolio_id))
        ).scalars().all()
        console.print(f"   Security lots created: {len(lot_count)}")

        # Count allocations created
        alloc_count = session.execute(
            select(SecurityAllocation)
            .where(SecurityAllocation.lot.has(
                SecurityLot.holding.has(portfolio_id=portfolio_id)
            ))
        ).scalars().all()
        console.print(f"   Security allocations created: {len(alloc_count)}")

        # Count journal entries
        entry_count = session.execute(
            select(JournalEntry).where(JournalEntry.portfolio_id == portfolio_id)
        ).scalars().all()
        console.print(f"   Journal entries created: {len(entry_count)}")

        # Verify all entries balanced
        unbalanced = [e for e in entry_count if not e.is_balanced]
        if unbalanced:
            console.print(f"   [red]✗ Unbalanced entries: {len(unbalanced)}[/red]")
        else:
            console.print("   [green]✓ All entries balanced[/green]")

        # Step 7: Commit or rollback
        if error_count == 0:
            session.commit()
            console.print("\n[bold green]✓ Rebuild completed successfully![/bold green]")
            console.print("\n[dim]Run 'stocks-helper accounting trial-balance' to verify.[/dim]")
        else:
            session.rollback()
            console.print("\n[bold red]✗ Rebuild failed due to errors. Changes rolled back.[/bold red]")


@click.command()
@click.option(
    "--portfolio-id",
    help="Portfolio ID (defaults to first portfolio)",
    default=None,
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without making changes",
)
@click.confirmation_option(
    prompt="This will delete and rebuild ALL journal entries. Continue?"
)
def main(portfolio_id: str | None, dry_run: bool) -> None:
    """Rebuild all journal entries with GAAP/IFRS compliance."""
    try:
        with db_session() as session:
            # Get portfolio
            if portfolio_id:
                portfolio = session.get(Portfolio, portfolio_id)
                if not portfolio:
                    console.print(f"[red]Portfolio {portfolio_id} not found[/red]")
                    return
            else:
                portfolio = session.execute(select(Portfolio).limit(1)).scalar_one_or_none()
                if not portfolio:
                    console.print("[red]No portfolios found[/red]")
                    return

            rebuild_journal_entries(portfolio.id, dry_run)

    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        console.print(f"\n[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    main()
