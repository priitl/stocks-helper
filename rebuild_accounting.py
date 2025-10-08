#!/usr/bin/env python3
"""Rebuild accounting journal entries with GAAP/IFRS compliant multi-currency handling.

This script:
1. Backs up existing journal entries
2. Deletes all journal entries and reconciliations
3. Recreates chart of accounts (adds new currency accounts)
4. Reprocesses all transactions in chronological order
5. Creates mark-to-market adjustments for:
   - Securities (IFRS 9)
   - Foreign currency cash (IAS 21)
   - Currency conversion spreads (realized FX gains/losses)

Run with: python rebuild_accounting.py
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select

from src.lib.db import db_session, get_engine
from src.models import (
    Account,
    ChartAccount,
    CurrencyAllocation,
    CurrencyLot,
    Holding,
    JournalEntry,
    JournalEntryStatus,
    JournalEntryType,
    JournalLine,
    Portfolio,
    Reconciliation,
    SecurityAllocation,
    SecurityLot,
    Transaction,
    TransactionType,
)
from src.services.accounting_service import (
    get_next_entry_number,
    initialize_chart_of_accounts,
    record_transaction_as_journal_entry,
)
from src.services.currency_converter import CurrencyConverter
from src.services.currency_lot_service import CurrencyLotService
from src.services.lot_tracking_service import (
    mark_currency_to_market,
    mark_securities_to_market,
)


def backup_journal_entries(session) -> int:
    """Backup existing journal entries to a text file."""
    entries = session.execute(select(JournalEntry)).scalars().all()
    count = len(entries)

    if count == 0:
        print("No existing journal entries to backup")
        return 0

    backup_file = Path("journal_entries_backup.txt")
    with backup_file.open("w") as f:
        f.write(f"Journal Entries Backup - {date.today()}\n")
        f.write(f"Total entries: {count}\n\n")

        for entry in entries:
            f.write(f"Entry #{entry.entry_number} - {entry.entry_date}\n")
            f.write(f"  Type: {entry.type.value}, Status: {entry.status.value}\n")
            f.write(f"  Description: {entry.description}\n")
            f.write("  Lines:\n")
            for line in entry.lines:
                f.write(f"    {line.account.name}: ")
                if line.debit_amount > 0:
                    f.write(f"DR {line.currency} {line.debit_amount}")
                else:
                    f.write(f"CR {line.currency} {line.credit_amount}")
                if line.foreign_currency and line.foreign_amount:
                    f.write(f" (orig: {line.foreign_currency} {line.foreign_amount})")
                f.write("\n")
            f.write("\n")

    print(f"✓ Backed up {count} journal entries to {backup_file}")
    return count


def clean_accounting_data(session) -> None:
    """Delete all journal entries, lines, reconciliations, security lots, and currency lots."""
    # Delete in correct order (foreign key constraints)
    session.execute(delete(CurrencyAllocation))
    session.execute(delete(CurrencyLot))
    session.execute(delete(SecurityAllocation))
    session.execute(delete(SecurityLot))
    session.execute(delete(JournalLine))
    session.execute(delete(Reconciliation))
    session.execute(delete(JournalEntry))
    session.commit()
    print("✓ Deleted existing journal entries, security lots, and currency lots")


def recreate_chart_of_accounts(session, portfolio_id: str) -> dict:
    """Recreate chart of accounts with new currency accounts."""
    # Delete existing chart
    session.execute(delete(ChartAccount).where(ChartAccount.portfolio_id == portfolio_id))
    session.commit()

    # Create new chart (includes currency gain/loss accounts)
    accounts = initialize_chart_of_accounts(session, portfolio_id)
    session.commit()

    print(f"✓ Created {len(accounts)} accounts in chart of accounts:")
    for key, acc in sorted(accounts.items()):
        print(f"  {acc.code} - {acc.name} ({key})")

    return accounts


def process_all_transactions(session, portfolio_id: str) -> int:
    """Process all transactions in chronological order."""
    # Get chart of accounts
    accounts_stmt = select(ChartAccount).where(ChartAccount.portfolio_id == portfolio_id)
    all_accounts = session.execute(accounts_stmt).scalars().all()

    accounts = {}
    name_map = {
        "Cash": "cash",
        "Bank Accounts": "bank",
        "Currency Exchange Clearing": "currency_clearing",
        "Investments - Securities": "investments",
        "Fair Value Adjustment - Investments": "fair_value_adjustment",
        "Owner's Capital": "capital",
        "Retained Earnings": "retained_earnings",
        "Dividend Income": "dividend_income",
        "Interest Income": "interest_income",
        "Realized Capital Gains": "capital_gains",
        "Unrealized Gains on Investments": "unrealized_gains",
        "Fees and Commissions": "fees",
        "Tax Expense": "taxes",
        "Realized Capital Losses": "capital_losses",
        "Unrealized Losses on Investments": "unrealized_losses",
        "Realized Currency Gains": "currency_gains",
        "Unrealized Currency Gains": "unrealized_currency_gains",
        "Realized Currency Losses": "currency_losses",
        "Unrealized Currency Losses": "unrealized_currency_losses",
    }

    for account in all_accounts:
        key = name_map.get(account.name)
        if key:
            accounts[key] = account

    # Verify all required accounts exist
    required_accounts = [
        "cash", "bank", "currency_clearing", "investments", "fair_value_adjustment",
        "capital", "retained_earnings", "dividend_income", "interest_income",
        "capital_gains", "unrealized_gains", "fees", "taxes",
        "capital_losses", "unrealized_losses",
        "currency_gains", "unrealized_currency_gains",
        "currency_losses", "unrealized_currency_losses"
    ]

    missing = [acc for acc in required_accounts if acc not in accounts]
    if missing:
        print(f"✗ ERROR: Missing required accounts in chart: {', '.join(missing)}")
        print(f"\nAvailable accounts ({len(accounts)}):")
        for key in sorted(accounts.keys()):
            print(f"  {key}: {accounts[key].name}")
        print(f"\nAll chart accounts ({len(all_accounts)}):")
        for acc in all_accounts:
            print(f"  {acc.code} - {acc.name}")
        return 0

    # Get all transactions ordered by date
    transactions = (
        session.execute(select(Transaction).order_by(Transaction.date, Transaction.created_at))
        .scalars()
        .all()
    )

    processed = 0
    errors = 0

    for txn in transactions:
        try:
            record_transaction_as_journal_entry(session, txn, accounts)
            processed += 1

            if processed % 100 == 0:
                print(f"  Processed {processed} transactions...")
                session.commit()
        except Exception as e:
            errors += 1
            print(f"  ✗ Error processing transaction {txn.id} ({txn.date}, {txn.type}): {e}")

    session.commit()
    print(f"✓ Processed {processed} transactions ({errors} errors)")
    return processed


def apply_all_stock_splits(session, portfolio_id: str) -> int:
    """Apply all recorded stock splits to newly created lots.

    After rebuild clears and recreates lots, splits need to be reapplied
    since lots are created with as-traded (pre-split) quantities.
    """
    from src.models import Security, StockSplit
    from src.services.lot_tracking_service import apply_split_to_existing_lots

    # Get all securities in this portfolio
    securities_stmt = (
        select(Security)
        .join(Holding, Security.id == Holding.security_id)
        .where(Holding.portfolio_id == portfolio_id)
        .distinct()
    )
    securities = session.execute(securities_stmt).scalars().all()

    total_updates = 0
    for security in securities:
        # Get all splits for this security
        splits_stmt = (
            select(StockSplit)
            .where(StockSplit.security_id == security.id)
            .order_by(StockSplit.split_date)
        )
        splits = session.execute(splits_stmt).scalars().all()

        for split in splits:
            updated = apply_split_to_existing_lots(session, security.id, split)
            if updated > 0:
                print(f"  Applied {split.split_ratio}:1 split ({split.split_date}) to {updated} lots of {security.ticker}")
                total_updates += updated

    session.commit()
    return total_updates


def reprocess_sell_transactions(session, portfolio_id: str, accounts: dict) -> int:
    """Reprocess SELL transactions after splits have been applied to lots.

    During initial transaction processing, lots haven't been split-adjusted yet,
    causing FIFO to fail for SELL transactions. After applying splits, we need
    to recreate SELL journal entries with proper lot matching.

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        accounts: Chart of accounts dict

    Returns:
        Number of SELL transactions reprocessed
    """
    # Find all SELL transactions for this portfolio
    transactions_stmt = (
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.portfolio_id == portfolio_id,
            Transaction.type == TransactionType.SELL,
        )
        .order_by(Transaction.date, Transaction.created_at)
    )
    sell_transactions = session.execute(transactions_stmt).scalars().all()

    if not sell_transactions:
        return 0

    reprocessed = 0
    for txn in sell_transactions:
        try:
            # First: Get allocations BEFORE deleting to restore lot quantities
            allocs_stmt = select(SecurityAllocation).where(
                SecurityAllocation.sell_transaction_id == txn.id
            )
            allocations = session.execute(allocs_stmt).scalars().all()

            # Restore lot quantities from allocations
            for alloc in allocations:
                lot = session.get(SecurityLot, alloc.lot_id)
                if lot:
                    lot.remaining_quantity += alloc.quantity_allocated
                    lot.is_closed = False

            # Now delete allocations and journal entry
            if allocations:
                alloc_delete_stmt = delete(SecurityAllocation).where(
                    SecurityAllocation.sell_transaction_id == txn.id
                )
                session.execute(alloc_delete_stmt)

            entry_stmt = select(JournalEntry).where(JournalEntry.reference == txn.id)
            entry = session.execute(entry_stmt).scalar_one_or_none()

            if entry:
                session.delete(entry)

            session.flush()

            # Recreate journal entry with split-adjusted lots
            record_transaction_as_journal_entry(session, txn, accounts)
            reprocessed += 1

            if reprocessed % 50 == 0:
                print(f"  Reprocessed {reprocessed} SELL transactions...")
                session.commit()

        except Exception as e:
            print(f"  ✗ Error reprocessing SELL {txn.id} ({txn.date}): {e}")

    session.commit()
    return reprocessed


def allocate_currency_lots_and_post_realized_fx(session, portfolio_id: str) -> int:
    """Allocate foreign currency spending to lots and post realized FX gains/losses.

    Per IAS 21, when foreign currency is spent (BUY/FEE), we must:
    1. Allocate spending to currency lots using FIFO
    2. Calculate realized FX gain/loss for each allocation
    3. Post realized FX to journal entries

    Realized FX = allocated_amount * (spot_rate - acquisition_rate)

    Args:
        session: Database session
        portfolio_id: Portfolio ID

    Returns:
        Number of transactions allocated
    """
    from src.models import ChartAccount

    # Get portfolio
    portfolio = session.get(Portfolio, portfolio_id)
    if not portfolio:
        raise ValueError(f"Portfolio {portfolio_id} not found")

    base_currency = portfolio.base_currency

    # Get currency gain/loss accounts
    currency_gains_stmt = select(ChartAccount).where(
        ChartAccount.portfolio_id == portfolio_id,
        ChartAccount.code == "4300"
    )
    currency_gains_account = session.execute(currency_gains_stmt).scalar_one_or_none()

    currency_losses_stmt = select(ChartAccount).where(
        ChartAccount.portfolio_id == portfolio_id,
        ChartAccount.code == "5300"
    )
    currency_losses_account = session.execute(currency_losses_stmt).scalar_one_or_none()

    if not currency_gains_account or not currency_losses_account:
        raise ValueError("Currency Gains/Losses accounts not found")

    # Initialize currency lot service
    lot_service = CurrencyLotService(session)
    currency_converter = CurrencyConverter()

    # Get all BUY transactions in foreign currency
    # TODO: Add support for FEE transactions later
    query = (
        session.query(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .filter(
            Account.portfolio_id == portfolio_id,
            Transaction.type == TransactionType.BUY,
            Transaction.currency != base_currency,
        )
        .order_by(Transaction.date, Transaction.created_at)
    )

    transactions = query.all()

    allocated_count = 0
    total_realized_fx = Decimal("0")

    for txn in transactions:
        # Check if already allocated
        existing = (
            session.query(CurrencyAllocation)
            .filter(CurrencyAllocation.purchase_transaction_id == txn.id)
            .first()
        )

        if existing:
            continue

        # Calculate amount to allocate (quantity * price)
        if not txn.quantity or not txn.price:
            continue
        amount_to_allocate = txn.quantity * txn.price

        try:
            # Allocate to lots using FIFO
            allocations = lot_service.allocate_purchase_to_lots(txn, amount_to_allocate)

            # Calculate realized FX for each allocation
            import asyncio

            # Get current exchange rate at transaction date
            current_rate_float = asyncio.run(
                currency_converter.get_rate(
                    from_currency=txn.currency,
                    to_currency=base_currency,
                    rate_date=txn.date,
                )
            )
            current_rate = Decimal(str(current_rate_float)) if current_rate_float else Decimal("1.0")

            # Calculate total realized FX for this transaction
            txn_realized_fx = Decimal("0")
            for allocation in allocations:
                # Get the lot for this allocation
                lot = session.get(CurrencyLot, allocation.currency_lot_id)
                if not lot:
                    continue

                # Realized FX = allocated_amount * (current_rate - 1/lot.exchange_rate)
                # current_rate: EUR/USD (base per foreign)
                # lot.exchange_rate: USD/EUR (foreign per base)
                # 1/lot.exchange_rate: EUR/USD (base per foreign)
                acquisition_rate = Decimal("1") / lot.exchange_rate
                realized_fx = allocation.allocated_amount * (current_rate - acquisition_rate)
                txn_realized_fx += realized_fx

            # Post realized FX if significant
            if abs(txn_realized_fx) >= Decimal("0.01"):
                # Create journal entry for realized FX
                entry = JournalEntry(
                    portfolio_id=portfolio_id,
                    entry_number=get_next_entry_number(session, portfolio_id),
                    entry_date=txn.date,
                    posting_date=txn.date,
                    type=JournalEntryType.TRANSACTION,
                    status=JournalEntryStatus.POSTED,
                    description=f"Realized FX on {txn.type.value} (IAS 21)",
                    reference=txn.id,
                    created_by="system",
                )
                session.add(entry)
                session.flush()

                lines = []
                if txn_realized_fx > 0:
                    # Realized gain: DR Cash, CR Realized Currency Gains
                    lines.append(
                        JournalLine(
                            journal_entry_id=entry.id,
                            account_id=session.execute(
                                select(ChartAccount).where(
                                    ChartAccount.portfolio_id == portfolio_id,
                                    ChartAccount.code == "1000"
                                )
                            ).scalar_one().id,
                            line_number=1,
                            debit_amount=txn_realized_fx,
                            credit_amount=Decimal("0"),
                            currency=base_currency,
                            description="Realized FX gain on spending",
                        )
                    )
                    lines.append(
                        JournalLine(
                            journal_entry_id=entry.id,
                            account_id=currency_gains_account.id,
                            line_number=2,
                            debit_amount=Decimal("0"),
                            credit_amount=txn_realized_fx,
                            currency=base_currency,
                            description=f"Realized FX gain - {txn.currency}",
                        )
                    )
                else:
                    # Realized loss: DR Realized Currency Losses, CR Cash
                    loss_amount = abs(txn_realized_fx)
                    lines.append(
                        JournalLine(
                            journal_entry_id=entry.id,
                            account_id=currency_losses_account.id,
                            line_number=1,
                            debit_amount=loss_amount,
                            credit_amount=Decimal("0"),
                            currency=base_currency,
                            description=f"Realized FX loss - {txn.currency}",
                        )
                    )
                    lines.append(
                        JournalLine(
                            journal_entry_id=entry.id,
                            account_id=session.execute(
                                select(ChartAccount).where(
                                    ChartAccount.portfolio_id == portfolio_id,
                                    ChartAccount.code == "1000"
                                )
                            ).scalar_one().id,
                            line_number=2,
                            debit_amount=Decimal("0"),
                            credit_amount=loss_amount,
                            currency=base_currency,
                            description="Realized FX loss on spending",
                        )
                    )

                for line in lines:
                    session.add(line)

                session.flush()

                # Verify entry is balanced
                if not entry.is_balanced:
                    raise ValueError(
                        f"Realized FX entry not balanced: "
                        f"DR={entry.total_debits}, CR={entry.total_credits}"
                    )

            total_realized_fx += txn_realized_fx
            allocated_count += 1

        except ValueError as e:
            print(f"  ⚠ Warning: Could not allocate {txn.type.value} {txn.id} ({txn.date}): {e}")

    session.commit()

    print(f"✓ Allocated {allocated_count} foreign currency transactions")
    if abs(total_realized_fx) >= Decimal("0.01"):
        print(f"  Total realized FX: {base_currency} {total_realized_fx:,.2f}")

    return allocated_count


def clear_currency_clearing_account(session, portfolio_id: str) -> None:
    """Clear Currency Clearing account to Realized Currency Gains/Losses.

    The Currency Clearing account accumulates FX spread losses from currency
    conversions (difference between mid-market rate and broker's rate).
    This function moves any balance to Realized Currency Gains/Losses.
    """
    from src.models import ChartAccount
    from src.services.accounting_service import get_account_balance, get_next_entry_number

    # Get portfolio
    portfolio = session.get(Portfolio, portfolio_id)
    if not portfolio:
        raise ValueError(f"Portfolio {portfolio_id} not found")

    # Get Currency Clearing account
    clearing_stmt = select(ChartAccount).where(
        ChartAccount.portfolio_id == portfolio_id,
        ChartAccount.code == "1150"
    )
    clearing_account = session.execute(clearing_stmt).scalar_one_or_none()

    if not clearing_account:
        print("  ✗ Currency Clearing account not found")
        return

    # Get Realized Currency Gains/Losses accounts
    currency_gains_stmt = select(ChartAccount).where(
        ChartAccount.portfolio_id == portfolio_id,
        ChartAccount.code == "4300"
    )
    currency_gains_account = session.execute(currency_gains_stmt).scalar_one_or_none()

    currency_losses_stmt = select(ChartAccount).where(
        ChartAccount.portfolio_id == portfolio_id,
        ChartAccount.code == "5300"
    )
    currency_losses_account = session.execute(currency_losses_stmt).scalar_one_or_none()

    if not currency_gains_account or not currency_losses_account:
        print("  ✗ Currency Gains/Losses accounts not found")
        return

    # Get current balance
    balance = get_account_balance(session, clearing_account.id, date.today())

    # Check if adjustment is needed (use small threshold for rounding)
    if abs(balance) < Decimal("0.01"):
        print("  No Currency Clearing balance to clear")
        return

    # Create journal entry to clear the balance
    entry = JournalEntry(
        portfolio_id=portfolio_id,
        entry_number=get_next_entry_number(session, portfolio_id),
        entry_date=date.today(),
        posting_date=date.today(),
        type=JournalEntryType.ADJUSTMENT,
        status=JournalEntryStatus.POSTED,
        description="Clear Currency Clearing account (FX conversion spread)",
        created_by="system",
    )
    session.add(entry)
    session.flush()

    lines = []

    if balance > 0:
        # Clearing account has debit balance (gain)
        # DR Realized Currency Gains (contra), CR Currency Clearing (reduce)
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=currency_gains_account.id,
                line_number=1,
                debit_amount=Decimal("0"),
                credit_amount=balance,
                currency=portfolio.base_currency,
                description="FX conversion gain (spread)",
            )
        )
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=clearing_account.id,
                line_number=2,
                debit_amount=balance,
                credit_amount=Decimal("0"),
                currency=portfolio.base_currency,
                description="Clear Currency Clearing",
            )
        )
    else:
        # Clearing account has credit balance (loss)
        loss_amount = abs(balance)
        # DR Currency Clearing (reduce), CR Realized Currency Losses
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=clearing_account.id,
                line_number=1,
                debit_amount=Decimal("0"),
                credit_amount=loss_amount,
                currency=portfolio.base_currency,
                description="Clear Currency Clearing",
            )
        )
        lines.append(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=currency_losses_account.id,
                line_number=2,
                debit_amount=loss_amount,
                credit_amount=Decimal("0"),
                currency=portfolio.base_currency,
                description="FX conversion loss (spread)",
            )
        )

    # Add lines to entry
    for line in lines:
        session.add(line)

    session.flush()

    # Verify entry is balanced
    if not entry.is_balanced:
        raise ValueError(
            f"Currency clearing entry not balanced: "
            f"DR={entry.total_debits}, CR={entry.total_credits}"
        )

    session.commit()
    print(f"✓ Cleared Currency Clearing balance: {portfolio.base_currency} {balance:,.2f} (Entry #{entry.entry_number})")


def run_mark_to_market(session, portfolio_id: str) -> None:
    """Run mark-to-market for securities and foreign currency (IFRS 9 / IAS 21)."""
    # Get portfolio and cash account for currency mark-to-market
    from src.models import ChartAccount
    portfolio = session.get(Portfolio, portfolio_id)
    if not portfolio:
        raise ValueError(f"Portfolio {portfolio_id} not found")

    # Get cash account
    cash_stmt = select(ChartAccount).where(
        ChartAccount.portfolio_id == portfolio_id,
        ChartAccount.code == "1000"
    )
    cash_account = session.execute(cash_stmt).scalar_one_or_none()

    # 1. Mark securities to market (IFRS 9)
    try:
        entry = mark_securities_to_market(session, portfolio_id, date.today())
        if entry:
            session.commit()
            print(f"✓ Created securities mark-to-market adjustment (Entry #{entry.entry_number})")
        else:
            print("  No securities mark-to-market adjustment needed")
    except Exception as e:
        print(f"  ✗ Securities mark-to-market failed: {e}")

    # 2. Mark foreign currency to market (IAS 21)
    if cash_account:
        try:
            entry = mark_currency_to_market(
                session,
                portfolio_id,
                cash_account.id,
                portfolio.base_currency,
                date.today()
            )
            if entry:
                session.commit()
                print(f"✓ Created currency mark-to-market adjustment (Entry #{entry.entry_number})")
            else:
                print("  No currency mark-to-market adjustment needed")
        except Exception as e:
            print(f"  ✗ Currency mark-to-market failed: {e}")
    else:
        print("  ✗ Cash account not found for currency mark-to-market")

    # 3. Clear Currency Clearing account (realized FX from conversion spreads)
    try:
        clear_currency_clearing_account(session, portfolio_id)
    except Exception as e:
        print(f"  ✗ Clear Currency Clearing failed: {e}")


def main():
    """Main rebuild process."""
    import sys

    print("\n" + "=" * 70)
    print("REBUILD ACCOUNTING - GAAP/IFRS Multi-Currency Compliance")
    print("=" * 70 + "\n")

    # Confirm with user (skip if --yes flag provided)
    skip_confirm = "--yes" in sys.argv or "-y" in sys.argv
    if not skip_confirm:
        response = input("This will DELETE all journal entries and rebuild them. Continue? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            return

    print("\nStarting rebuild process...\n")

    with db_session() as session:
        # Get default portfolio
        portfolio = session.execute(select(Portfolio).limit(1)).scalar_one_or_none()
        if not portfolio:
            print("✗ No portfolio found")
            return

        print(f"Portfolio: {portfolio.name} (ID: {portfolio.id})")
        print(f"Base Currency: {portfolio.base_currency}\n")

        # Step 1: Backup
        print("[1/5] Backing up existing journal entries...")
        backup_journal_entries(session)

        # Step 2: Clean
        print("\n[2/5] Cleaning existing accounting data...")
        clean_accounting_data(session)

        # Step 3: Recreate chart
        print("\n[3/5] Recreating chart of accounts...")
        accounts = recreate_chart_of_accounts(session, portfolio.id)

        # Step 4: Process transactions (creates lots for BUY and CONVERSION transactions)
        print("\n[4/8] Processing all transactions...")
        process_all_transactions(session, portfolio.id)

        # Step 5: Allocate currency lots and post realized FX
        print("\n[5/8] Allocating currency lots and posting realized FX...")
        allocated = allocate_currency_lots_and_post_realized_fx(session, portfolio.id)
        if allocated == 0:
            print("  No foreign currency transactions to allocate")

        # Step 6: Apply stock splits to newly created lots
        # Lots are created during BUY processing with as-traded quantities
        # Splits must be applied before SELL transactions can use FIFO correctly
        print("\n[6/8] Applying stock splits to lots...")
        splits_applied = apply_all_stock_splits(session, portfolio.id)
        if splits_applied > 0:
            print(f"✓ Applied splits to {splits_applied} lots")
        else:
            print("  No stock splits to apply")

        # Step 7: Reprocess SELL transactions with split-adjusted lots
        # During initial processing, lots weren't split-adjusted yet, causing FIFO failures
        # Now that splits are applied, we can recreate SELL journal entries with proper FIFO
        print("\n[7/8] Reprocessing SELL transactions with split-adjusted lots...")
        sells_reprocessed = reprocess_sell_transactions(session, portfolio.id, accounts)
        if sells_reprocessed > 0:
            print(f"✓ Reprocessed {sells_reprocessed} SELL transactions")
        else:
            print("  No SELL transactions to reprocess")

        # Step 8: Mark-to-market
        print("\n[8/8] Running mark-to-market...")
        run_mark_to_market(session, portfolio.id)

    print("\n" + "=" * 70)
    print("✓ REBUILD COMPLETE")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Run: stocks-helper accounting trial-balance")
    print("  2. Run: stocks-helper accounting balance-sheet")
    print("  3. Verify cash matches portfolio overview")
    print("\nCash should now show:")
    print("  - EUR amounts in EUR")
    print("  - USD amounts in USD")
    print("  - NOK amounts in NOK")
    print("  - Separate currency gain/loss accounts")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
