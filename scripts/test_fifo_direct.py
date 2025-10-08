#!/usr/bin/env python3
"""Test FIFO allocation directly for a specific transaction."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from decimal import Decimal

from sqlalchemy import select

from src.lib.db import get_session
from src.models import Holding, SecurityLot, Transaction
from src.services.lot_tracking_service import allocate_lots_fifo


def test_transaction(tx_id: str):
    """Test FIFO for a specific transaction."""
    session = get_session()

    try:
        # Get transaction
        transaction = session.get(Transaction, tx_id)
        if not transaction:
            print(f"Transaction {tx_id} not found")
            return

        print(f"Transaction: {transaction.id}")
        print(f"Type: {transaction.type.value}")
        print(f"Date: {transaction.date}")
        print(f"Quantity: {transaction.quantity}")
        print(f"Holding ID: {transaction.holding_id}")

        # Get holding
        holding = session.get(Holding, transaction.holding_id)
        print(f"\nHolding: {holding.ticker if holding else 'NOT FOUND'}")

        # Query lots directly
        stmt = (
            select(SecurityLot)
            .where(
                SecurityLot.holding_id == transaction.holding_id,
                SecurityLot.is_closed == False,  # noqa: E712
                SecurityLot.remaining_quantity > 0,
            )
            .order_by(SecurityLot.purchase_date, SecurityLot.created_at)
        )

        lots = session.execute(stmt).scalars().all()
        print(f"\nLots found by query: {len(lots)}")
        for lot in lots:
            print(f"  Lot {lot.id[:8]}: {lot.remaining_quantity} shares on {lot.purchase_date}")

        # Try FIFO allocation
        print(f"\nAttempting FIFO allocation...")
        print(f"  Quantity to sell: {transaction.quantity}")

        try:
            allocations = allocate_lots_fifo(
                session,
                transaction.holding_id,
                transaction.quantity,
                transaction.date,
                transaction.broker_source,
            )

            print(f"\n✓ FIFO SUCCESS: {len(allocations)} allocation(s)")
            for lot, qty, cost in allocations:
                print(f"  Allocated {qty} shares from lot {lot.id[:8]}")

        except Exception as e:
            print(f"\n✗ FIFO FAILED: {e}")

    finally:
        session.close()


if __name__ == "__main__":
    # Test the two transactions that should work
    print("=" * 80)
    print("Testing CPA1T SELL (should work: 60 available, 60 needed)")
    print("=" * 80)
    test_transaction("1448692c-40b0-40cc-9275-08d3d78f4159")

    print("\n" * 2)
    print("=" * 80)
    print("Testing NVDA SELL (should work: 10 available, 10 needed)")
    print("=" * 80)
    test_transaction("ed221ee4-489d-44f6-bd34-23ce1c0dbcd6")
