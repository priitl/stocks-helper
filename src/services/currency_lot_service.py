"""
Currency lot tracking service for precise currency gain calculations.

Manages currency lots (from CONVERSION transactions) and allocates purchases
to specific lots using FIFO, enabling accurate currency gain tracking.
"""

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from src.models.currency_lot import CurrencyAllocation, CurrencyLot
from src.models.transaction import Transaction, TransactionType

logger = logging.getLogger(__name__)


class CurrencyLotService:
    """Service for managing currency lots and allocations."""

    def __init__(self, session: Session):
        """
        Initialize currency lot service.

        Args:
            session: Database session
        """
        self.session = session

    def create_lot_from_conversion(self, conversion_txn: Transaction) -> CurrencyLot:
        """
        Create a currency lot from a CONVERSION transaction.

        Args:
            conversion_txn: The CONVERSION transaction

        Returns:
            Created CurrencyLot

        Raises:
            ValueError: If transaction is not a CONVERSION type
        """
        if conversion_txn.type != TransactionType.CONVERSION:
            raise ValueError(f"Transaction {conversion_txn.id} is not a CONVERSION")

        if not conversion_txn.conversion_from_currency or not conversion_txn.conversion_from_amount:
            raise ValueError(
                f"CONVERSION transaction {conversion_txn.id} missing conversion_from fields"
            )

        # Check if lot already exists
        existing_lot = (
            self.session.query(CurrencyLot)
            .filter(CurrencyLot.conversion_transaction_id == conversion_txn.id)
            .first()
        )

        if existing_lot:
            logger.debug(f"Lot already exists for conversion {conversion_txn.id}")
            return existing_lot

        # Calculate exchange rate: to_currency per unit of from_currency
        # e.g., 110 USD for 100 EUR = 110/100 = 1.1 USD/EUR
        exchange_rate = conversion_txn.amount / conversion_txn.conversion_from_amount

        # Create new lot
        lot = CurrencyLot(
            account_id=conversion_txn.account_id,
            conversion_transaction_id=conversion_txn.id,
            from_currency=conversion_txn.conversion_from_currency,
            to_currency=conversion_txn.currency,
            from_amount=conversion_txn.conversion_from_amount,
            to_amount=conversion_txn.amount,
            remaining_amount=conversion_txn.amount,  # Initially all available
            exchange_rate=exchange_rate,
            conversion_date=conversion_txn.date,
        )

        self.session.add(lot)
        self.session.flush()

        logger.info(
            f"Created lot {lot.id[:8]}: {lot.from_currency} -> {lot.to_currency} "
            f"@ {exchange_rate:.6f}, amount={lot.to_amount}"
        )

        return lot

    def allocate_purchase_to_lots(
        self, purchase_txn: Transaction, purchase_amount: Decimal
    ) -> list[CurrencyAllocation]:
        """
        Allocate a purchase to available currency lots using FIFO.

        Args:
            purchase_txn: The BUY transaction
            purchase_amount: Amount to allocate (in purchase currency)

        Returns:
            List of created CurrencyAllocation records

        Raises:
            ValueError: If insufficient currency lots available
        """
        if purchase_txn.type != TransactionType.BUY:
            raise ValueError(f"Transaction {purchase_txn.id} is not a BUY")

        # Get available lots in the purchase currency, ordered by date (FIFO)
        available_lots = (
            self.session.query(CurrencyLot)
            .filter(
                CurrencyLot.account_id == purchase_txn.account_id,
                CurrencyLot.to_currency == purchase_txn.currency,
                CurrencyLot.remaining_amount > 0,
                CurrencyLot.conversion_date
                <= purchase_txn.date,  # Only use lots from before/on purchase date
            )
            .order_by(CurrencyLot.conversion_date, CurrencyLot.id)  # FIFO
            .all()
        )

        if not available_lots:
            raise ValueError(
                f"No currency lots available for {purchase_txn.currency} "
                f"purchase {purchase_txn.id} on {purchase_txn.date}"
            )

        # Allocate using FIFO
        remaining_to_allocate = purchase_amount
        allocations: list[CurrencyAllocation] = []

        for lot in available_lots:
            if remaining_to_allocate <= Decimal("0.01"):  # Allow small rounding errors
                break

            # Allocate from this lot
            allocated_from_lot = min(remaining_to_allocate, lot.remaining_amount)

            # Skip if allocation amount is too small (rounding errors)
            if allocated_from_lot < Decimal("0.01"):
                continue

            allocation = CurrencyAllocation(
                currency_lot_id=lot.id,
                purchase_transaction_id=purchase_txn.id,
                allocated_amount=allocated_from_lot,
            )

            self.session.add(allocation)
            allocations.append(allocation)

            # Update lot remaining amount
            lot.remaining_amount -= allocated_from_lot
            remaining_to_allocate -= allocated_from_lot

            logger.debug(
                f"Allocated {allocated_from_lot} {lot.to_currency} from lot {lot.id[:8]} "
                f"to purchase {purchase_txn.id[:8]}, remaining in lot: {lot.remaining_amount}"
            )

        if remaining_to_allocate > Decimal("0.01"):  # Allow small rounding errors
            raise ValueError(
                f"Insufficient currency lots for purchase {purchase_txn.id}. "
                f"Need {purchase_amount} {purchase_txn.currency}, "
                f"still need {remaining_to_allocate} more"
            )

        self.session.flush()

        logger.info(
            f"Allocated purchase {purchase_txn.id[:8]} ({purchase_amount} {purchase_txn.currency}) "
            f"to {len(allocations)} lot(s)"
        )

        return allocations

    def get_allocations_for_holding(
        self, holding_id: str, session: Optional[Session] = None
    ) -> list[tuple[CurrencyAllocation, CurrencyLot, Transaction]]:
        """
        Get all currency allocations for a holding's transactions.

        Returns allocations with their lots and original purchase transactions.

        Args:
            holding_id: Holding ID
            session: Optional session (uses self.session if not provided)

        Returns:
            List of (allocation, lot, purchase_transaction) tuples
        """
        session = session or self.session

        # Get all BUY transactions for this holding
        buy_transactions = (
            session.query(Transaction)
            .filter(
                Transaction.holding_id == holding_id,
                Transaction.type == TransactionType.BUY,
            )
            .all()
        )

        if not buy_transactions:
            return []

        buy_txn_ids = [txn.id for txn in buy_transactions]

        # Get allocations for these transactions
        results = (
            session.query(CurrencyAllocation, CurrencyLot, Transaction)
            .join(CurrencyLot, CurrencyAllocation.currency_lot_id == CurrencyLot.id)
            .join(Transaction, CurrencyAllocation.purchase_transaction_id == Transaction.id)
            .filter(CurrencyAllocation.purchase_transaction_id.in_(buy_txn_ids))
            .order_by(Transaction.date, CurrencyAllocation.created_at)
            .all()
        )

        return results

    def process_all_conversions(self, account_id: Optional[str] = None) -> int:
        """
        Process all CONVERSION transactions into currency lots.

        Args:
            account_id: Optional account ID to process (None = all accounts)

        Returns:
            Number of lots created
        """
        query = self.session.query(Transaction).filter(
            Transaction.type == TransactionType.CONVERSION
        )

        if account_id:
            query = query.filter(Transaction.account_id == account_id)

        conversion_txns = query.order_by(Transaction.date, Transaction.id).all()

        created_count = 0
        for txn in conversion_txns:
            try:
                self.create_lot_from_conversion(txn)
                created_count += 1
            except Exception as e:
                logger.warning(f"Failed to create lot from conversion {txn.id}: {e}")

        self.session.commit()
        logger.info(f"Created {created_count} currency lots from conversions")

        return created_count

    def allocate_all_purchases(
        self, account_id: Optional[str] = None, base_currency: str = "EUR"
    ) -> int:
        """
        Allocate all BUY transactions to currency lots using FIFO.

        Only allocates purchases in foreign currencies (not base currency).

        Args:
            account_id: Optional account ID to process (None = all accounts)
            base_currency: Base currency (purchases in this currency are skipped)

        Returns:
            Number of purchases allocated
        """
        query = (
            self.session.query(Transaction)
            .filter(Transaction.type == TransactionType.BUY)
            .filter(Transaction.holding_id.isnot(None))  # Only stock/security purchases
            .filter(Transaction.currency != base_currency)  # Skip base currency purchases
        )

        if account_id:
            query = query.filter(Transaction.account_id == account_id)

        buy_transactions = query.order_by(Transaction.date, Transaction.id).all()

        allocated_count = 0
        skipped_count = 0
        for txn in buy_transactions:
            # Check if already allocated
            existing = (
                self.session.query(CurrencyAllocation)
                .filter(CurrencyAllocation.purchase_transaction_id == txn.id)
                .first()
            )

            if existing:
                logger.debug(f"Purchase {txn.id} already allocated")
                continue

            # Calculate purchase amount (cost in transaction currency)
            purchase_amount = txn.quantity * txn.price

            try:
                self.allocate_purchase_to_lots(txn, purchase_amount)
                allocated_count += 1
            except ValueError as e:
                logger.warning(f"Failed to allocate purchase {txn.id}: {e}")
                skipped_count += 1

        self.session.commit()
        logger.info(
            f"Allocated {allocated_count} purchases to currency lots ({skipped_count} skipped)"
        )

        return allocated_count

    def get_weighted_average_rate_for_holding(
        self, holding_id: str, base_currency: str
    ) -> Optional[Decimal]:
        """
        Calculate weighted average exchange rate for a holding based on lot allocations.

        Args:
            holding_id: Holding ID
            base_currency: Portfolio base currency

        Returns:
            Weighted average rate (base_currency per unit of security currency), or None
        """
        allocations = self.get_allocations_for_holding(holding_id)

        if not allocations:
            return None

        total_amount_in_security_currency = Decimal("0")
        total_amount_in_base_currency = Decimal("0")

        for allocation, lot, purchase_txn in allocations:
            # Amount allocated in security currency
            amount_security = allocation.allocated_amount

            # Convert to base currency using lot's rate
            # lot.exchange_rate is: to_currency per unit of from_currency
            # If lot is EUR->USD @ 1.1, and we allocated 110 USD
            # Then we paid 110/1.1 = 100 EUR
            amount_base = amount_security / lot.exchange_rate

            total_amount_in_security_currency += amount_security
            total_amount_in_base_currency += amount_base

        if total_amount_in_security_currency > 0:
            # Weighted average rate: base_currency per unit of security_currency
            weighted_avg_rate = total_amount_in_base_currency / total_amount_in_security_currency
            return weighted_avg_rate

        return None

    def get_realized_currency_gain_for_holding(
        self, holding_id: str, base_currency: str
    ) -> Decimal:
        """
        Calculate realized currency gain from sales using TRUE FIFO.

        For each SELL transaction:
        1. Determine which purchase batches are being sold (FIFO order)
        2. For each portion, get the specific purchase rate from currency lot allocations
        3. Find CONVERSION transactions that converted proceeds back to base currency
        4. Calculate: cost_basis * (conversion_rate - purchase_rate) for each portion

        IMPORTANT:
        - Uses TRUE FIFO to track which specific shares are sold
        - Uses cost basis (not sale proceeds) to avoid inflating currency gain
        - Different portions of a sale may have different purchase rates

        Args:
            holding_id: Holding ID
            base_currency: Portfolio base currency

        Returns:
            Total realized currency gain in base currency
        """
        # Get all transactions for this holding in chronological order
        transactions = (
            self.session.query(Transaction)
            .filter(Transaction.holding_id == holding_id)
            .order_by(Transaction.date, Transaction.id)
            .all()
        )

        buy_txns = [txn for txn in transactions if txn.type == TransactionType.BUY]
        sell_txns = [txn for txn in transactions if txn.type == TransactionType.SELL]

        if not sell_txns or not buy_txns:
            return Decimal("0")

        security_currency = buy_txns[0].currency
        if security_currency == base_currency:
            return Decimal("0")

        # Build a queue of purchase batches with their rates (FIFO)
        # Each batch: {qty, price, cost, purchase_rate}
        purchase_queue = []

        for buy_txn in buy_txns:
            # Skip transactions with missing quantity or price
            if not buy_txn.quantity or not buy_txn.price:
                continue
            # Get the purchase rate for this specific buy transaction
            # by looking at its currency lot allocations
            allocations = (
                self.session.query(CurrencyAllocation, CurrencyLot)
                .join(CurrencyLot, CurrencyAllocation.currency_lot_id == CurrencyLot.id)
                .filter(CurrencyAllocation.purchase_transaction_id == buy_txn.id)
                .all()
            )

            if allocations:
                # Calculate weighted average rate for THIS purchase
                total_allocated = Decimal("0")
                total_eur_paid = Decimal("0")

                for allocation, lot in allocations:
                    total_allocated += allocation.allocated_amount
                    # lot.exchange_rate is to_currency/from_currency (e.g., USD/EUR)
                    # We need EUR/USD for currency gain calculation
                    total_eur_paid += allocation.allocated_amount / lot.exchange_rate

                purchase_rate = (
                    total_eur_paid / total_allocated if total_allocated > 0 else Decimal("1.0")
                )
            else:
                # Fallback to transaction's exchange rate
                purchase_rate = (
                    buy_txn.exchange_rate
                    if buy_txn.exchange_rate != Decimal("1.0")
                    else Decimal("1.0")
                )

            purchase_queue.append(
                {
                    "qty": buy_txn.quantity,
                    "price": buy_txn.price,
                    "cost": buy_txn.quantity * buy_txn.price,
                    "purchase_rate": purchase_rate,
                    "remaining": buy_txn.quantity,  # Track remaining shares from this batch
                }
            )

        # Process each sale using FIFO
        total_realized_gain = Decimal("0")

        for sell_txn in sell_txns:
            # Skip transactions with missing quantity or price
            if not sell_txn.quantity or not sell_txn.price:
                continue

            qty_to_sell = sell_txn.quantity
            sale_proceeds = sell_txn.quantity * sell_txn.price

            # Find matching conversion transaction
            conversions = (
                self.session.query(Transaction)
                .filter(
                    Transaction.type == TransactionType.CONVERSION,
                    Transaction.account_id == sell_txn.account_id,
                    Transaction.conversion_from_currency == security_currency,
                    Transaction.currency == base_currency,
                    Transaction.date >= sell_txn.date - timedelta(days=7),
                    Transaction.date <= sell_txn.date + timedelta(days=7),
                )
                .all()
            )

            # Match by amount
            matched_conversion = None
            for conv in conversions:
                if conv.conversion_from_amount:
                    diff = abs(conv.conversion_from_amount - sale_proceeds) / sale_proceeds
                    if diff < Decimal("0.01"):
                        matched_conversion = conv
                        break

            if not matched_conversion:
                continue  # Skip if no conversion found

            conversion_rate = matched_conversion.amount / matched_conversion.conversion_from_amount

            # Allocate this sale to purchase batches using FIFO
            remaining_to_sell = qty_to_sell

            for batch in purchase_queue:
                if remaining_to_sell <= 0:
                    break

                if batch["remaining"] <= 0:
                    continue  # This batch is fully sold

                # How many shares from this batch?
                qty_from_batch = min(remaining_to_sell, batch["remaining"])

                # Cost basis for these shares
                cost_basis_from_batch = qty_from_batch * batch["price"]

                # Currency gain for this portion
                portion_gain = cost_basis_from_batch * (conversion_rate - batch["purchase_rate"])
                total_realized_gain += portion_gain

                # Update remaining quantities
                batch["remaining"] -= qty_from_batch
                remaining_to_sell -= qty_from_batch

        return total_realized_gain
