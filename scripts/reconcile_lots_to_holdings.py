"""Reconcile SecurityLot quantities to match current Holding quantities.

This script fixes mismatches between current holdings and security lots by adjusting
lot remaining_quantity to match actual holdings. This ensures mark-to-market is accurate.

Usage:
    python scripts/reconcile_lots_to_holdings.py [--dry-run]
"""

import argparse
import sys
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.lib.db import get_session
from src.models import Holding, SecurityLot


def find_holding_lot_mismatches(session):
    """Find holdings where lot quantities don't match holding quantities.

    Returns:
        List of (holding, holding_qty, lot_qty, difference) tuples
    """
    mismatches = []

    # Get all holdings with quantity > 0
    stmt = select(Holding).where(Holding.quantity > 0)
    holdings = session.execute(stmt).scalars().all()

    for holding in holdings:
        # Sum up open lots for this holding
        lot_stmt = (
            select(SecurityLot)
            .where(
                SecurityLot.holding_id == holding.id,
                SecurityLot.is_closed == False,  # noqa: E712
                SecurityLot.remaining_quantity > 0,
            )
        )
        lots = session.execute(lot_stmt).scalars().all()

        lot_qty = sum(lot.remaining_quantity for lot in lots)
        difference = holding.quantity - lot_qty

        if abs(difference) > Decimal("0.01"):  # Threshold for floating point
            mismatches.append((holding, holding.quantity, lot_qty, difference))

    return mismatches


def reconcile_holding_lots(session, holding, holding_qty, lot_qty, difference, dry_run=False):
    """Reconcile lots for a single holding by adjusting lot quantities.

    Strategy:
    - If lots show too many shares: reduce the most recent lot
    - If lots show too few shares: increase the most recent lot

    Args:
        session: Database session
        holding: Holding instance
        holding_qty: Current holding quantity
        lot_qty: Total from lots
        difference: holding_qty - lot_qty
        dry_run: If True, don't commit changes

    Returns:
        Tuple of (success, message)
    """
    try:
        # Get all open lots for this holding, ordered by purchase date
        stmt = (
            select(SecurityLot)
            .where(
                SecurityLot.holding_id == holding.id,
                SecurityLot.is_closed == False,  # noqa: E712
                SecurityLot.remaining_quantity > 0,
            )
            .order_by(SecurityLot.purchase_date.desc(), SecurityLot.created_at.desc())
        )
        lots = session.execute(stmt).scalars().all()

        if not lots:
            return (False, "No open lots to adjust")

        # Adjust the most recent lot
        most_recent_lot = lots[0]
        old_remaining = most_recent_lot.remaining_quantity
        new_remaining = old_remaining + difference

        if new_remaining < 0:
            return (False, f"Cannot adjust: would make lot negative ({new_remaining:.2f})")

        if not dry_run:
            most_recent_lot.remaining_quantity = new_remaining

            # Update is_closed status
            if new_remaining <= Decimal("0.00000001"):
                most_recent_lot.remaining_quantity = Decimal("0")
                most_recent_lot.is_closed = True

            session.flush()

        return (
            True,
            f"Adjusted lot from {old_remaining:.2f} to {new_remaining:.2f} "
            f"(lot date: {most_recent_lot.purchase_date})",
        )

    except Exception as e:
        return (False, f"Unexpected error: {str(e)}")


def main():
    """Main reconciliation script."""
    parser = argparse.ArgumentParser(
        description="Reconcile lot quantities to match current holdings"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    args = parser.parse_args()

    session = get_session()

    try:
        # Find mismatches
        print("Finding holdings with lot quantity mismatches...")
        mismatches = find_holding_lot_mismatches(session)

        if not mismatches:
            print("✓ No mismatches found - all lots match holdings")
            return

        print(f"Found {len(mismatches)} holding(s) with lot mismatches\n")

        if args.dry_run:
            print("DRY RUN - No changes will be committed\n")

        # Display mismatches
        print("Current mismatches:")
        print(f"{'Ticker':<15} {'Holding Qty':>15} {'Lot Qty':>15} {'Difference':>15}")
        print("-" * 62)
        for holding, holding_qty, lot_qty, diff in mismatches:
            print(
                f"{holding.ticker:<15} {holding_qty:>15.2f} {lot_qty:>15.2f} {diff:>+15.2f}"
            )
        print()

        # Reconcile each mismatch
        success_count = 0
        error_count = 0

        for holding, holding_qty, lot_qty, difference in mismatches:
            print(f"Reconciling: {holding.ticker} (difference: {difference:+.2f})")

            success, message = reconcile_holding_lots(
                session, holding, holding_qty, lot_qty, difference, dry_run=args.dry_run
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
            print(f"\n✓ Reconciled {success_count} holding(s)")
        elif args.dry_run:
            session.rollback()
            print(f"\nDRY RUN: Would reconcile {success_count} holding(s)")
        else:
            session.rollback()

        if error_count > 0:
            print(f"✗ {error_count} holding(s) failed")

    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
