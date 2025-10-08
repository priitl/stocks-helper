#!/usr/bin/env python3
"""Rebuild journal entries with proper multi-currency accounting.

This script:
1. Deletes all existing journal entries and reconciliations
2. Deletes the chart of accounts
3. Recreates journal entries using the new multi-currency logic

Run this after implementing the multi-currency fix to correct existing data.
"""

import sys
from datetime import datetime

from sqlalchemy import select

from src.lib.db import get_session
from src.models import (
    ChartAccount,
    JournalEntry,
    JournalLine,
    Portfolio,
    Reconciliation,
    Transaction,
)
from src.services.accounting_service import (
    initialize_chart_of_accounts,
    record_transaction_as_journal_entry,
)


def rebuild_journal_entries(portfolio_id: str | None = None, dry_run: bool = False):
    """Rebuild all journal entries for a portfolio.

    Args:
        portfolio_id: Portfolio ID (None = all portfolios)
        dry_run: If True, show what would be done without making changes
    """
    session = get_session()

    try:
        # Get portfolios to process
        if portfolio_id:
            portfolio = session.get(Portfolio, portfolio_id)
            if not portfolio:
                print(f"❌ Portfolio {portfolio_id} not found")
                return
            portfolios = [portfolio]
        else:
            portfolios = session.query(Portfolio).all()

        print(f"{'[DRY RUN] ' if dry_run else ''}Rebuilding journal entries for {len(portfolios)} portfolio(s)...\n")

        for portfolio in portfolios:
            print(f"Portfolio: {portfolio.name} ({portfolio.id})")

            # Get counts before deletion
            journal_entries = session.query(JournalEntry).filter(
                JournalEntry.portfolio_id == portfolio.id
            ).all()
            journal_lines = session.query(JournalLine).join(JournalEntry).filter(
                JournalEntry.portfolio_id == portfolio.id
            ).all()
            reconciliations = session.query(Reconciliation).join(JournalEntry).filter(
                JournalEntry.portfolio_id == portfolio.id
            ).all()
            chart_accounts = session.query(ChartAccount).filter(
                ChartAccount.portfolio_id == portfolio.id
            ).all()

            print(f"  Found:")
            print(f"    - {len(journal_entries)} journal entries")
            print(f"    - {len(journal_lines)} journal lines")
            print(f"    - {len(reconciliations)} reconciliations")
            print(f"    - {len(chart_accounts)} chart accounts")

            if dry_run:
                print(f"  [DRY RUN] Would delete and recreate these records")
            else:
                # Step 1: Delete old data
                print(f"  Deleting old journal entries...")
                for reconciliation in reconciliations:
                    session.delete(reconciliation)
                for line in journal_lines:
                    session.delete(line)
                for entry in journal_entries:
                    session.delete(entry)
                for account in chart_accounts:
                    session.delete(account)
                session.flush()
                print(f"  ✓ Deleted old records")

                # Step 2: Recreate chart of accounts
                print(f"  Creating chart of accounts...")
                accounts = initialize_chart_of_accounts(session, portfolio.id)
                session.flush()
                print(f"  ✓ Created {len(accounts)} accounts")

                # Step 3: Get all transactions for this portfolio
                stmt = (
                    select(Transaction)
                    .join(Transaction.account)
                    .where(Transaction.account.has(portfolio_id=portfolio.id))
                    .order_by(Transaction.date, Transaction.created_at)
                )
                transactions = session.execute(stmt).scalars().all()
                print(f"  Processing {len(transactions)} transactions...")

                # Step 4: Create journal entries
                created = 0
                errors = 0
                for i, transaction in enumerate(transactions, 1):
                    try:
                        record_transaction_as_journal_entry(session, transaction, accounts)
                        created += 1
                        if i % 100 == 0:
                            print(f"    Progress: {i}/{len(transactions)} ({created} entries created)")
                            session.flush()
                    except Exception as e:
                        errors += 1
                        print(f"    ❌ Error processing transaction {transaction.id}: {e}")

                session.flush()
                print(f"  ✓ Created {created} journal entries ({errors} errors)")

            print()

        if not dry_run:
            # Commit all changes
            print("Committing changes...")
            session.commit()
            print("✓ Rebuild complete!")
        else:
            print("[DRY RUN] No changes made")

    except Exception as e:
        print(f"❌ Error: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rebuild journal entries with multi-currency support")
    parser.add_argument("--portfolio-id", help="Portfolio ID (default: all portfolios)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print("⚠️  WARNING: This will delete all existing journal entries and recreate them.")
        print("⚠️  Make sure you have a backup of your database!")
        print()
        response = input("Are you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            sys.exit(0)

    rebuild_journal_entries(args.portfolio_id, args.dry_run)
