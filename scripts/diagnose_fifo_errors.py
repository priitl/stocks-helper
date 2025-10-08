#!/usr/bin/env python3
"""Diagnose FIFO allocation errors by checking lot availability."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.lib.db import get_session
from src.models import Holding, Security, SecurityLot, Transaction, TransactionType


def diagnose_transaction(session, transaction_id: str):
    """Diagnose why a SELL transaction failed FIFO allocation."""
    # Get the transaction
    transaction = session.get(Transaction, transaction_id)
    if not transaction:
        print(f"Transaction {transaction_id} not found")
        return

    print(f"\n{'=' * 80}")
    print(f"Transaction: {transaction_id}")
    print(f"Type: {transaction.type.value}")
    print(f"Date: {transaction.date}")
    print(f"Quantity: {transaction.quantity}")
    print(f"{'=' * 80}")

    if transaction.type != TransactionType.SELL:
        print("Not a SELL transaction")
        return

    # Get the holding
    holding = session.get(Holding, transaction.holding_id)
    if not holding:
        print(f"Holding {transaction.holding_id} not found")
        return

    print(f"\nHolding: {holding.ticker}")
    print(f"Security ID: {holding.security_id}")

    # Get the security
    security = session.get(Security, holding.security_id)
    print(f"Security: {security.name} ({security.ticker})")

    # Get all BUY transactions for this holding
    buy_stmt = (
        select(Transaction)
        .where(
            Transaction.holding_id == holding.id,
            Transaction.type == TransactionType.BUY,
            Transaction.date <= transaction.date,
        )
        .order_by(Transaction.date)
    )
    buy_transactions = session.execute(buy_stmt).scalars().all()

    print(f"\nBUY transactions before this SELL ({len(buy_transactions)}):")
    total_bought = 0
    for buy in buy_transactions:
        print(f"  {buy.date}: {buy.quantity} shares @ {buy.price}")
        total_bought += buy.quantity
    print(f"Total bought: {total_bought}")

    # Get all lots for this holding
    lot_stmt = (
        select(SecurityLot)
        .where(
            SecurityLot.holding_id == holding.id,
            SecurityLot.purchase_date <= transaction.date,
        )
        .order_by(SecurityLot.purchase_date)
    )
    lots = session.execute(lot_stmt).scalars().all()

    print(f"\nSecurity lots created ({len(lots)}):")
    total_remaining = 0
    for lot in lots:
        print(f"  {lot.purchase_date}: {lot.quantity} shares, "
              f"{lot.remaining_quantity} remaining, closed={lot.is_closed}")
        total_remaining += lot.remaining_quantity
    print(f"Total remaining: {total_remaining}")

    # Get all SELL transactions for this holding (before this one)
    sell_stmt = (
        select(Transaction)
        .where(
            Transaction.holding_id == holding.id,
            Transaction.type == TransactionType.SELL,
            Transaction.date <= transaction.date,
            Transaction.id != transaction.id,
        )
        .order_by(Transaction.date)
    )
    sell_transactions = session.execute(sell_stmt).scalars().all()

    print(f"\nSELL transactions before this SELL ({len(sell_transactions)}):")
    total_sold = 0
    for sell in sell_transactions:
        print(f"  {sell.date}: {sell.quantity} shares @ {sell.price}")
        total_sold += sell.quantity
    print(f"Total sold: {total_sold}")

    # Get splits for this security
    from src.models import StockSplit
    split_stmt = (
        select(StockSplit)
        .where(StockSplit.security_id == security.id)
        .order_by(StockSplit.split_date)
    )
    splits = session.execute(split_stmt).scalars().all()

    print(f"\nStock splits ({len(splits)}):")
    for split in splits:
        print(f"  {split.split_date}: {split.split_from}:{split.split_to} "
              f"(ratio={split.split_ratio})")

    # Calculate expected remaining after splits
    if splits:
        print("\nSplit-adjusted analysis:")

        # Calculate what the lots should be after forward-adjustment
        print(f"  BUY transactions use 'as-traded' quantities: {total_bought}")

        # Check if forward-adjustment was applied to lots
        splits_after_first_buy = [s for s in splits if s.split_date > buy_transactions[0].date] if buy_transactions else []
        if splits_after_first_buy:
            cumulative_ratio = 1
            for split in splits_after_first_buy:
                cumulative_ratio *= split.split_ratio
            print(f"  Future splits would multiply by: {cumulative_ratio}")
            print(f"  Expected lot total: {total_bought * cumulative_ratio}")

        # Check what the SELL quantity would be after adjustment
        splits_after_sell = [s for s in splits if s.split_date > transaction.date]
        if splits_after_sell:
            sell_ratio = 1
            for split in splits_after_sell:
                sell_ratio *= split.split_ratio
            print(f"  SELL adjustment multiplier: {sell_ratio}")
            print(f"  Adjusted SELL quantity: {transaction.quantity * sell_ratio}")

    print("\n" + "=" * 80)
    print("DIAGNOSIS:")
    print("=" * 80)

    if len(buy_transactions) == 0:
        print("❌ NO BUY TRANSACTIONS FOUND before this SELL")
        print("   → Check if BUY transactions were imported")
        print("   → Check if transactions are in date order")
    elif len(lots) == 0:
        print("❌ NO SECURITY LOTS CREATED from BUY transactions")
        print("   → Check if lot creation is enabled in accounting_service.py")
        print("   → Check for errors during BUY transaction processing")
    elif total_remaining == 0:
        print("❌ ALL LOTS ARE DEPLETED (remaining_quantity = 0)")
        print("   → Check if previous SELLs allocated correctly")
        print("   → Check if split adjustments caused issues")
    elif total_remaining < transaction.quantity:
        print(f"❌ INSUFFICIENT LOTS: need {transaction.quantity}, have {total_remaining}")
        print(f"   Total bought: {total_bought}")
        print(f"   Total sold before: {total_sold}")
        print(f"   Expected remaining: {total_bought - total_sold}")

        if splits:
            print("   → This may be a split adjustment issue")
            print("   → Check if forward-adjustment was applied to lots")
            print("   → Check if SELL quantity adjustment is working")
    else:
        print("✓ Sufficient lots available - FIFO should have worked")
        print("   → Check FIFO allocation logic")


def main():
    """Run diagnostics for failed SELL transactions."""
    # Transaction IDs from error messages
    failed_transactions = [
        "1448692c-40b0-40cc-9275-08d3d78f4159",
        "96355039-1c38-4971-a6aa-e6f5350f321d",
        "10f05db9-ac86-42d5-8d64-2b350fb08252",
        "ed221ee4-489d-44f6-bd34-23ce1c0dbcd6",
    ]

    session = get_session()
    try:
        for tx_id in failed_transactions:
            try:
                diagnose_transaction(session, tx_id)
            except Exception as e:
                print(f"\n❌ Error diagnosing {tx_id}: {e}")
                import traceback
                traceback.print_exc()

    finally:
        session.close()


if __name__ == "__main__":
    main()
