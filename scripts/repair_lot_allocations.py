"""Repair script to retroactively allocate lots for old SELL transactions.

This script fixes SELL transactions that were imported before the GAAP/IFRS
lot tracking system was implemented. It retroactively allocates lots using FIFO
and creates SecurityAllocation records.

Usage:
    python scripts/repair_lot_allocations.py [--dry-run]
"""

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.lib.db import get_session
from src.models import (
    Holding,
    Portfolio,
    Security,
    SecurityAllocation,
    Transaction,
)
from src.services.lot_tracking_service import (
    allocate_lots_fifo,
    create_security_allocation,
)


def find_sell_transactions_without_allocations(session):
    """Find all SELL transactions that don't have lot allocations.

    Returns:
        List of (transaction, holding, security) tuples
    """
    # Query SELL transactions that have no allocations
    stmt = (
        select(Transaction)
        .where(Transaction.type == "SELL")
        .order_by(Transaction.date, Transaction.id)
    )

    all_sells = session.execute(stmt).scalars().all()

    # Filter to those without allocations
    sells_without_allocations = []

    for txn in all_sells:
        # Check if this transaction has any allocations
        allocation_stmt = select(SecurityAllocation).where(
            SecurityAllocation.sell_transaction_id == txn.id
        )
        allocations = session.execute(allocation_stmt).scalars().all()

        if not allocations:
            # Get holding and security
            holding = session.get(Holding, txn.holding_id) if txn.holding_id else None

            if holding:
                security = session.get(Security, holding.security_id)
                if security:
                    sells_without_allocations.append((txn, holding, security))

    return sells_without_allocations


def repair_transaction_allocations(session, transaction, holding, security, dry_run=False):
    """Repair lot allocations for a single SELL transaction.

    Args:
        session: Database session
        transaction: SELL transaction
        holding: Associated holding
        security: Associated security
        dry_run: If True, don't commit changes

    Returns:
        Tuple of (success, message)
    """
    try:
        # Validate required fields
        if transaction.quantity is None or transaction.price is None:
            return (False, f"Missing quantity or price")

        # Calculate proceeds in base currency
        # Get portfolio to determine base currency
        from src.models import Account

        account = session.get(Account, transaction.account_id)
        if not account:
            return (False, f"Account not found")

        portfolio = session.get(Portfolio, account.portfolio_id)
        if not portfolio:
            return (False, f"Portfolio not found")

        exchange_rate = transaction.exchange_rate or Decimal("1.0")
        proceeds = transaction.amount
        proceeds_base = proceeds * exchange_rate

        # Allocate lots using FIFO
        # Pass broker_source for proper split handling
        allocations = allocate_lots_fifo(
            session=session,
            holding_id=holding.id,
            quantity_to_sell=transaction.quantity,
            sell_date=transaction.date,
            broker_source=transaction.broker_source,
        )

        # Calculate total cost basis
        total_cost_basis = sum(alloc[2] for alloc in allocations)

        # Calculate realized gain/loss
        realized_gain_loss = proceeds_base - total_cost_basis

        # Create SecurityAllocation records for each lot used
        for lot, qty_allocated, cost_basis in allocations:
            # Calculate proceeds for this allocation
            allocation_proceeds = (qty_allocated / transaction.quantity) * proceeds_base

            if not dry_run:
                create_security_allocation(
                    session=session,
                    lot=lot,
                    sell_transaction_id=transaction.id,
                    quantity_allocated=qty_allocated,
                    cost_basis=cost_basis,
                    proceeds=allocation_proceeds,
                )

        # Update holding quantity
        if not dry_run:
            holding.quantity -= transaction.quantity
            session.flush()

        return (
            True,
            f"Allocated {len(allocations)} lot(s), "
            f"cost basis: {total_cost_basis:.2f}, "
            f"proceeds: {proceeds_base:.2f}, "
            f"G/L: {realized_gain_loss:+.2f}",
        )

    except ValueError as e:
        # Insufficient lots or other error
        return (False, f"Error: {str(e)}")
    except Exception as e:
        return (False, f"Unexpected error: {str(e)}")


def main():
    """Main repair script."""
    parser = argparse.ArgumentParser(
        description="Repair lot allocations for old SELL transactions"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--reset-all",
        action="store_true",
        help="Delete ALL existing allocations and re-allocate ALL SELLs in chronological order",
    )
    args = parser.parse_args()

    session = get_session()

    try:
        if args.reset_all:
            # Delete ALL existing allocations and reset lots
            print("WARNING: Resetting ALL lot allocations...")
            print("This will:")
            print("  1. Delete all SecurityAllocation records")
            print("  2. Reset all SecurityLot remaining_quantity to original quantity")
            print("  3. Re-allocate ALL SELL transactions in chronological order")
            print()

            if not args.dry_run:
                response = input("Are you sure? This cannot be undone! (yes/no): ")
                if response.lower() != "yes":
                    print("Aborted")
                    return

            # Delete all allocations
            deleted = session.query(SecurityAllocation).delete()
            print(f"Deleted {deleted} allocation records")

            # Reset all lots
            from src.models import SecurityLot
            lots = session.query(SecurityLot).all()
            for lot in lots:
                lot.remaining_quantity = lot.quantity
                lot.is_closed = False
            print(f"Reset {len(lots)} security lots")

            if args.dry_run:
                session.rollback()
            else:
                session.commit()

            # Now process ALL SELLs
            stmt = (
                select(Transaction)
                .where(Transaction.type == "SELL")
                .order_by(Transaction.date, Transaction.id)
            )
            all_sells = session.execute(stmt).scalars().all()

            sells = []
            for txn in all_sells:
                holding = session.get(Holding, txn.holding_id) if txn.holding_id else None
                if holding:
                    security = session.get(Security, holding.security_id)
                    if security:
                        sells.append((txn, holding, security))

            print(f"\nProcessing {len(sells)} SELL transactions in chronological order...\n")
        else:
            # Find SELL transactions without allocations
            print("Finding SELL transactions without lot allocations...")
            sells = find_sell_transactions_without_allocations(session)

            if not sells:
                print("✓ No SELL transactions need repair")
                return

            print(f"Found {len(sells)} SELL transactions without allocations\n")

        if args.dry_run:
            print("DRY RUN - No changes will be committed\n")

        # Process each transaction
        success_count = 0
        error_count = 0

        for txn, holding, security in sells:
            ticker = security.ticker
            print(f"Processing: {txn.date} | {ticker} | Qty: {txn.quantity}")

            success, message = repair_transaction_allocations(
                session, txn, holding, security, dry_run=args.dry_run
            )

            if success:
                print(f"  ✓ {message}")
                success_count += 1
            else:
                print(f"  ✗ {message}")
                error_count += 1

        # Commit if not dry run
        if not args.dry_run and success_count > 0:
            session.commit()
            print(f"\n✓ Repaired {success_count} transaction(s)")
        elif args.dry_run:
            session.rollback()
            print(f"\nDRY RUN: Would repair {success_count} transaction(s)")
        else:
            session.rollback()

        if error_count > 0:
            print(f"✗ {error_count} transaction(s) failed")

    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
