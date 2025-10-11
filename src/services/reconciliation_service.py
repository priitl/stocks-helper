"""Reconciliation service for matching transactions to journal entries.

Handles automatic and manual reconciliation between imported transactions
and accounting journal entries.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import (
    JournalEntry,
    Reconciliation,
    ReconciliationStatus,
    Transaction,
)


@dataclass
class UnreconciledItem:
    """Represents an unreconciled transaction or journal entry.

    Attributes:
        transaction_id: Transaction ID (if transaction)
        journal_entry_id: Journal entry ID (if journal entry)
        date: Transaction/entry date
        amount: Amount
        description: Description
        type: "transaction" or "journal_entry"
    """

    transaction_id: str | None
    journal_entry_id: str | None
    date: date
    amount: Decimal
    description: str
    type: str


def reconcile_transaction(
    session: Session,
    transaction_id: str,
    journal_entry_id: str,
    status: ReconciliationStatus = ReconciliationStatus.RECONCILED,
    notes: str | None = None,
    reconciled_by: str = "system",
) -> Reconciliation:
    """Reconcile a transaction to a journal entry.

    Creates a reconciliation record linking the transaction to its journal entry.

    Args:
        session: Database session
        transaction_id: Transaction ID
        journal_entry_id: Journal entry ID
        status: Reconciliation status
        notes: Optional reconciliation notes
        reconciled_by: User performing reconciliation

    Returns:
        Created Reconciliation record
    """
    # Check if already reconciled
    existing = (
        session.query(Reconciliation)
        .filter(Reconciliation.transaction_id == transaction_id)
        .first()
    )

    if existing:
        # Update existing reconciliation
        existing.journal_entry_id = journal_entry_id
        existing.status = status
        existing.notes = notes
        existing.reconciled_by = reconciled_by
        session.flush()
        return existing

    # Create new reconciliation
    reconciliation = Reconciliation(
        transaction_id=transaction_id,
        journal_entry_id=journal_entry_id,
        status=status,
        notes=notes,
        reconciled_by=reconciled_by,
    )

    session.add(reconciliation)
    session.flush()
    return reconciliation


def auto_reconcile_by_reference(
    session: Session,
    portfolio_id: str | None = None,
) -> int:
    """Automatically reconcile transactions to journal entries by reference ID.

    Matches transactions to journal entries where the entry's reference
    field contains the transaction ID.

    Args:
        session: Database session
        portfolio_id: Optional portfolio filter

    Returns:
        Number of reconciliations created
    """
    # Find unreconciled transactions
    stmt = (
        select(Transaction)
        .outerjoin(Reconciliation, Transaction.id == Reconciliation.transaction_id)
        .where(Reconciliation.id.is_(None))  # Not yet reconciled
    )

    if portfolio_id:
        from src.models import Account

        stmt = stmt.join(Account, Transaction.account_id == Account.id).where(
            Account.portfolio_id == portfolio_id
        )

    unreconciled_txns = session.execute(stmt).scalars().all()

    reconciled_count = 0

    for txn in unreconciled_txns:
        # Find journal entry with this transaction as reference
        journal_entry = session.query(JournalEntry).filter(JournalEntry.reference == txn.id).first()

        if journal_entry:
            reconcile_transaction(
                session,
                transaction_id=txn.id,
                journal_entry_id=journal_entry.id,
                status=ReconciliationStatus.RECONCILED,
                reconciled_by="auto",
            )
            reconciled_count += 1

    session.flush()
    return reconciled_count


def get_unreconciled_transactions(
    session: Session,
    portfolio_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[UnreconciledItem]:
    """Get all unreconciled transactions for a portfolio.

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of UnreconciledItem for transactions
    """
    from src.models import Account

    stmt = (
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .outerjoin(Reconciliation, Transaction.id == Reconciliation.transaction_id)
        .where(
            Account.portfolio_id == portfolio_id,
            Reconciliation.id.is_(None),  # Not reconciled
        )
    )

    if start_date:
        stmt = stmt.where(Transaction.date >= start_date)
    if end_date:
        stmt = stmt.where(Transaction.date <= end_date)

    stmt = stmt.order_by(Transaction.date)

    transactions = session.execute(stmt).scalars().all()

    items = []
    for txn in transactions:
        items.append(
            UnreconciledItem(
                transaction_id=txn.id,
                journal_entry_id=None,
                date=txn.date,
                amount=txn.amount,
                description=f"{txn.type.value}: {txn.notes or ''}",
                type="transaction",
            )
        )

    return items


def get_unreconciled_journal_entries(
    session: Session,
    portfolio_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[UnreconciledItem]:
    """Get all journal entries not linked to transactions.

    Finds journal entries that don't have a corresponding reconciliation record.
    This could indicate manual journal entries or discrepancies.

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of UnreconciledItem for journal entries
    """
    stmt = (
        select(JournalEntry)
        .outerjoin(Reconciliation, JournalEntry.id == Reconciliation.journal_entry_id)
        .where(
            JournalEntry.portfolio_id == portfolio_id,
            Reconciliation.id.is_(None),  # Not reconciled
        )
    )

    if start_date:
        stmt = stmt.where(JournalEntry.entry_date >= start_date)
    if end_date:
        stmt = stmt.where(JournalEntry.entry_date <= end_date)

    stmt = stmt.order_by(JournalEntry.entry_date)

    entries = session.execute(stmt).scalars().all()

    items = []
    for entry in entries:
        items.append(
            UnreconciledItem(
                transaction_id=None,
                journal_entry_id=entry.id,
                date=entry.entry_date,
                amount=entry.total_debits,  # Use total debits as amount
                description=entry.description,
                type="journal_entry",
            )
        )

    return items


@dataclass
class ReconciliationSummary:
    """Summary of reconciliation status.

    Attributes:
        total_transactions: Total transactions
        reconciled_transactions: Reconciled transactions
        unreconciled_transactions: Unreconciled transactions
        total_journal_entries: Total journal entries
        reconciled_journal_entries: Journal entries with reconciliation
        unreconciled_journal_entries: Journal entries without reconciliation
        discrepancies: Count of reconciliations with discrepancy status
    """

    total_transactions: int
    reconciled_transactions: int
    unreconciled_transactions: int
    total_journal_entries: int
    reconciled_journal_entries: int
    unreconciled_journal_entries: int
    discrepancies: int


def get_reconciliation_summary(
    session: Session,
    portfolio_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> ReconciliationSummary:
    """Get reconciliation summary for a portfolio.

    Args:
        session: Database session
        portfolio_id: Portfolio ID
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        ReconciliationSummary
    """
    from src.models import Account

    # Count transactions
    txn_stmt = (
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.portfolio_id == portfolio_id)
    )

    if start_date:
        txn_stmt = txn_stmt.where(Transaction.date >= start_date)
    if end_date:
        txn_stmt = txn_stmt.where(Transaction.date <= end_date)

    total_transactions = len(session.execute(txn_stmt).scalars().all())

    # Count reconciled transactions
    reconciled_txn_stmt = (
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .join(Reconciliation, Transaction.id == Reconciliation.transaction_id)
        .where(Account.portfolio_id == portfolio_id)
    )

    if start_date:
        reconciled_txn_stmt = reconciled_txn_stmt.where(Transaction.date >= start_date)
    if end_date:
        reconciled_txn_stmt = reconciled_txn_stmt.where(Transaction.date <= end_date)

    reconciled_transactions = len(session.execute(reconciled_txn_stmt).scalars().all())

    unreconciled_transactions = total_transactions - reconciled_transactions

    # Count journal entries
    je_stmt = select(JournalEntry).where(JournalEntry.portfolio_id == portfolio_id)

    if start_date:
        je_stmt = je_stmt.where(JournalEntry.entry_date >= start_date)
    if end_date:
        je_stmt = je_stmt.where(JournalEntry.entry_date <= end_date)

    total_journal_entries = len(session.execute(je_stmt).scalars().all())

    # Count reconciled journal entries
    reconciled_je_stmt = (
        select(JournalEntry)
        .join(Reconciliation, JournalEntry.id == Reconciliation.journal_entry_id)
        .where(JournalEntry.portfolio_id == portfolio_id)
    )

    if start_date:
        reconciled_je_stmt = reconciled_je_stmt.where(JournalEntry.entry_date >= start_date)
    if end_date:
        reconciled_je_stmt = reconciled_je_stmt.where(JournalEntry.entry_date <= end_date)

    reconciled_journal_entries = len(session.execute(reconciled_je_stmt).scalars().all())

    unreconciled_journal_entries = total_journal_entries - reconciled_journal_entries

    # Count discrepancies
    discrepancy_stmt = select(Reconciliation).where(
        Reconciliation.status == ReconciliationStatus.DISCREPANCY
    )

    discrepancies = len(session.execute(discrepancy_stmt).scalars().all())

    return ReconciliationSummary(
        total_transactions=total_transactions,
        reconciled_transactions=reconciled_transactions,
        unreconciled_transactions=unreconciled_transactions,
        total_journal_entries=total_journal_entries,
        reconciled_journal_entries=reconciled_journal_entries,
        unreconciled_journal_entries=unreconciled_journal_entries,
        discrepancies=discrepancies,
    )


def mark_discrepancy(
    session: Session,
    reconciliation_id: str,
    notes: str,
) -> Reconciliation:
    """Mark a reconciliation as having a discrepancy.

    Args:
        session: Database session
        reconciliation_id: Reconciliation ID
        notes: Description of the discrepancy

    Returns:
        Updated Reconciliation record
    """
    reconciliation = session.get(Reconciliation, reconciliation_id)
    if not reconciliation:
        raise ValueError(f"Reconciliation {reconciliation_id} not found")

    reconciliation.status = ReconciliationStatus.DISCREPANCY
    reconciliation.notes = notes
    session.flush()

    return reconciliation


def resolve_discrepancy(
    session: Session,
    reconciliation_id: str,
    notes: str,
) -> Reconciliation:
    """Resolve a reconciliation discrepancy.

    Args:
        session: Database session
        reconciliation_id: Reconciliation ID
        notes: Resolution notes

    Returns:
        Updated Reconciliation record
    """
    reconciliation = session.get(Reconciliation, reconciliation_id)
    if not reconciliation:
        raise ValueError(f"Reconciliation {reconciliation_id} not found")

    reconciliation.status = ReconciliationStatus.RECONCILED
    reconciliation.notes = f"{reconciliation.notes}\n\nRESOLVED: {notes}"
    session.flush()

    return reconciliation
