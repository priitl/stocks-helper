"""Import service for bulk transaction CSV imports.

Handles CSV parsing, duplicate detection, validation, and batch tracking.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from src.lib.db import db_session
from src.models import (
    Account,
    Bond,
    Holding,
    ImportBatch,
    ImportError,
    ImportErrorType,
    ImportStatus,
    PaymentFrequency,
    Portfolio,
    Security,
    SecurityType,
    Stock,
    StockSplit,
    Transaction,
)
from src.services.csv_parser import (
    CSVParseError,
    LightyearCSVParser,
    ParsedTransaction,
    SwedbankCSVParser,
)
from src.services.ticker_validator import TickerValidator

# Known stock splits (hardcoded until API integration complete)
# Format: {"ticker": [{"date": date, "ratio": Decimal, "from": int, "to": int}]}
KNOWN_SPLITS = {
    "LHV1T": [{"date": date(2021, 6, 1), "ratio": Decimal("10.0"), "from": 1, "to": 10}],
    "SONY": [{"date": date(2024, 10, 9), "ratio": Decimal("5.0"), "from": 1, "to": 5}],
    "AMZN": [{"date": date(2022, 6, 6), "ratio": Decimal("20.0"), "from": 1, "to": 20}],
    "AAPL": [{"date": date(2020, 8, 31), "ratio": Decimal("4.0"), "from": 1, "to": 4}],
}

# No manual ticker mappings needed - bonds are detected by PCT pattern


@dataclass
class ImportSummary:
    """Summary of import operation results."""

    batch_id: int
    total_rows: int
    successful_count: int
    duplicate_count: int
    error_count: int
    unknown_ticker_count: int
    processing_duration: float  # seconds
    requires_ticker_review: bool  # True if unknown_ticker_count > 0
    errors_requiring_intervention: list["ImportErrorDetail"]
    unknown_tickers: list["UnknownTickerDetail"]


@dataclass
class ImportErrorDetail:
    """Details of a single import error for manual review."""

    row_number: int
    error_type: str
    error_message: str
    original_row_data: dict[str, str]


@dataclass
class UnknownTickerDetail:
    """Details of an unknown ticker requiring manual review."""

    row_number: int
    ticker: str
    suggestions: list[str]
    confidence: list[str]
    transaction_preview: str
    original_row_data: dict[str, str]


@dataclass
class ImportBatchInfo:
    """Summary information about an import batch."""

    batch_id: int
    filename: str
    broker_type: str
    upload_timestamp: datetime
    total_rows: int
    successful_count: int
    duplicate_count: int
    error_count: int
    unknown_ticker_count: int
    status: str
    processing_duration: float


class DatabaseError(Exception):
    """Raised when database operation fails."""

    pass


class ImportService:
    """Service for importing transactions from broker CSV files."""

    def __init__(self, known_tickers: set[str] | None = None):
        """Initialize import service.

        Args:
            known_tickers: Set of known valid tickers for validation.
                          If None, ticker validation will be disabled.
        """
        self.parsers = {
            "swedbank": SwedbankCSVParser(),
            "lightyear": LightyearCSVParser(),
        }
        self.ticker_validator = TickerValidator(known_tickers) if known_tickers else None
        self._metadata_cache: dict[str, dict[str, str] | None] = {}

    def import_csv(
        self,
        filepath: Path,
        broker_type: str,
        dry_run: bool = False,
    ) -> ImportSummary:
        """Import transactions from CSV file.

        Args:
            filepath: Path to CSV file
            broker_type: 'swedbank' or 'lightyear'
            dry_run: If True, validate but don't commit to database

        Returns:
            ImportSummary with counts and errors

        Raises:
            FileNotFoundError: CSV file doesn't exist
            ValueError: broker_type not valid
            CSVParseError: File format invalid
            DatabaseError: Database operation failure
        """
        # Validate inputs
        if not filepath.exists():
            raise FileNotFoundError(f"CSV file not found: {filepath}")

        if broker_type not in self.parsers:
            raise ValueError("Invalid broker_type: must be 'swedbank' or 'lightyear'")

        start_time = datetime.now(timezone.utc)

        try:
            # Parse CSV file
            parser = self.parsers[broker_type]
            parse_result = parser.parse_file(filepath)  # type: ignore[attr-defined]

            if dry_run:
                # Dry run: just validate, don't save
                return ImportSummary(
                    batch_id=0,
                    total_rows=parse_result.total_rows,
                    successful_count=len(parse_result.transactions),
                    duplicate_count=0,
                    error_count=len(parse_result.errors),
                    unknown_ticker_count=0,
                    processing_duration=(datetime.now(timezone.utc) - start_time).total_seconds(),
                    requires_ticker_review=False,
                    errors_requiring_intervention=[],
                    unknown_tickers=[],
                )

            # Import to database
            with db_session() as session:
                # Create import batch
                batch = ImportBatch(
                    broker_source=broker_type,
                    filename=str(filepath.name),
                    status=ImportStatus.IN_PROGRESS,
                    total_rows=parse_result.total_rows,
                    started_at=start_time,
                )
                session.add(batch)
                session.flush()  # Get batch ID

                # Get existing broker references for duplicate detection
                existing_refs = self._get_existing_references(session, broker_type)

                successful_count = 0
                duplicate_count = 0
                error_count = 0
                unknown_ticker_count = 0
                errors_list = []
                unknown_tickers_list = []

                # Handle parse errors from CSV parser
                for parse_error in parse_result.errors:
                    error_count += 1
                    row_num = parse_error.get("row", 0)
                    error_msg = parse_error.get("error", "Unknown parse error")

                    # Create ImportError record
                    error = ImportError(
                        batch_id=batch.id,
                        row_number=row_num,
                        error_type=ImportErrorType.PARSE,
                        error_message=error_msg,
                        original_data={},  # Parse errors don't have original data
                    )
                    session.add(error)

                    # Add to errors list for summary
                    errors_list.append(
                        ImportErrorDetail(
                            row_number=row_num,
                            error_type="parse",
                            error_message=error_msg,
                            original_row_data={},
                        )
                    )

                # Process each transaction
                for idx, txn in enumerate(parse_result.transactions):
                    row_num = idx + 2  # +2 for header and 1-indexing

                    # Check for duplicate using composite key
                    # (reference_id, transaction_type, currency)
                    composite_key = (txn.broker_reference_id, txn.transaction_type, txn.currency)
                    if composite_key in existing_refs:
                        duplicate_count += 1
                        continue

                    # Determine if this transaction needs a holding
                    # Stock-related transactions (with ticker): BUY, SELL, FEE, DIVIDEND, DISTRIBUTION, INTEREST
                    # Account-level transactions (no ticker): DEPOSIT, WITHDRAWAL, standalone fees
                    needs_holding = txn.ticker is not None and txn.transaction_type in (
                        "BUY",
                        "SELL",
                        "FEE",
                        "DIVIDEND",
                        "DISTRIBUTION",
                        "INTEREST",
                    )

                    # Validate ticker if validator is enabled
                    if self.ticker_validator and txn.ticker:
                        validation_result = self.ticker_validator.validate_ticker_sync(txn.ticker)

                        if not validation_result.valid:
                            # Create error record for unknown ticker
                            unknown_ticker_count += 1
                            error_count += 1

                            error = ImportError(
                                batch_id=batch.id,
                                row_number=row_num,
                                error_type=ImportErrorType.UNKNOWN_TICKER,
                                error_message=f"Unknown ticker: {txn.ticker}",
                                original_data=txn.original_data,
                                suggested_fix={
                                    "suggestions": validation_result.suggestions,
                                    "confidence": validation_result.confidence,
                                    "validation_source": validation_result.validation_source,
                                },
                            )
                            session.add(error)

                            # Add to unknown tickers list for summary
                            unknown_tickers_list.append(
                                UnknownTickerDetail(
                                    row_number=row_num,
                                    ticker=txn.ticker,
                                    suggestions=validation_result.suggestions,
                                    confidence=validation_result.confidence,
                                    transaction_preview=self._format_transaction_preview(
                                        txn.original_data
                                    ),
                                    original_row_data=txn.original_data,
                                )
                            )

                            continue  # Skip import for now, user will correct later

                    # Import transaction
                    try:
                        portfolio = self._get_or_create_default_portfolio(session)

                        # Create account for this broker
                        account = self._get_or_create_account(
                            session, portfolio.id, txn.broker_source
                        )

                        holding_id = None

                        if needs_holding:
                            # Stock-related transactions: create security and holding
                            security = self._get_or_create_security(session, txn)
                            # At least one identifier is required per database constraint
                            ticker = security.ticker or security.isin
                            if not ticker:
                                raise ValueError("Security must have ticker or ISIN")
                            holding = self._get_or_create_holding(
                                session,
                                portfolio.id,
                                ticker,
                                txn,
                                security.id,
                            )
                            holding_id = holding.id

                        # Create transaction record (with or without holding)
                        transaction = self._create_transaction(
                            txn, account.id, holding_id, batch.id
                        )
                        session.add(transaction)
                        successful_count += 1
                        existing_refs.add(
                            (txn.broker_reference_id, txn.transaction_type, txn.currency)
                        )

                        # Create FEE transactions for BUY and CONVERSION
                        # For BUY: Fee is separate from share cost
                        #   Example: Buy shares for 582.65, Fee 0.58
                        #   NET=582.65 (amount debited), but total paid = 583.23
                        #   Need FEE transaction for 0.58 ✓
                        # For CONVERSION: Fee is separate from exchanged amount
                        #   Example: Convert 1000 EUR → USD, Fee 3.50 EUR
                        #   NET=-996.50 (converted), need FEE -3.50 for total -1000 ✓
                        # For SELL/DIVIDEND/DISTRIBUTION/INTEREST: Fee already in NET
                        #   Example: SELL for 4443.33, Fee 1.00, NET 4442.33
                        #   Cash received: 4442.33 (fee already deducted) ✓
                        if (
                            txn.fees > Decimal("0")
                            and broker_type == "lightyear"
                            and txn.transaction_type in ("BUY", "CONVERSION")
                        ):
                            fee_transaction = self._create_fee_transaction(
                                txn, account.id, batch.id
                            )
                            session.add(fee_transaction)
                            successful_count += 1
                            existing_refs.add(
                                (f"{txn.broker_reference_id}-FEE", "FEE", txn.currency)
                            )
                    except Exception as e:
                        error_count += 1
                        error = ImportError(
                            batch_id=batch.id,
                            row_number=row_num,
                            error_type=ImportErrorType.VALIDATION,
                            error_message=str(e),
                            original_data=txn.original_data,
                        )
                        session.add(error)
                        errors_list.append(
                            ImportErrorDetail(
                                row_number=row_num,
                                error_type="validation",
                                error_message=str(e),
                                original_row_data=txn.original_data,
                            )
                        )

                # Update batch with final counts
                batch.successful_count = successful_count
                batch.duplicate_count = duplicate_count
                batch.error_count = error_count
                batch.unknown_ticker_count = unknown_ticker_count
                batch.completed_at = datetime.now(timezone.utc)
                batch.duration_seconds = (batch.completed_at - start_time).total_seconds()

                # Recalculate holding quantities and avg prices from transactions
                if successful_count > 0:
                    session.flush()  # Ensure all transactions are visible
                    self._recalculate_holdings(session)

                    # NOTE: Lightyear reconciliation is disabled by default
                    # Manual transfers to ICSUSSDP don't appear in CSV, but:
                    # - We can't auto-reconcile because new deposits would be wrongly written off
                    # - Use manual reconciliation tools when needed

                # CRITICAL: Link conversion pairs and create currency lots for FIFO tracking
                # Works for all brokers (Swedbank: VV: EUR -> NOK, Lightyear: separate rows)
                if successful_count > 0:
                    try:
                        self._link_conversion_pairs_and_create_lots(session, batch.id)
                    except Exception as e:
                        logger.warning(f"Failed to create currency lots for batch {batch.id}: {e}")

                batch.status = (
                    ImportStatus.COMPLETED if error_count == 0 else ImportStatus.NEEDS_REVIEW
                )

                session.commit()

                return ImportSummary(
                    batch_id=batch.id,
                    total_rows=parse_result.total_rows,
                    successful_count=successful_count,
                    duplicate_count=duplicate_count,
                    error_count=error_count,
                    unknown_ticker_count=unknown_ticker_count,
                    processing_duration=batch.duration_seconds,
                    requires_ticker_review=unknown_ticker_count > 0,
                    errors_requiring_intervention=errors_list,
                    unknown_tickers=unknown_tickers_list,
                )

        except CSVParseError:
            raise
        except Exception as e:
            raise DatabaseError(f"Database error during import: {e}")

    def _get_existing_references(
        self, session: Session, broker_source: str
    ) -> set[tuple[str, str, str]]:
        """Get set of existing (broker_reference_id, transaction_type, currency) tuples.

        Uses composite key to allow same reference ID for different transaction types
        and currencies (e.g., a trade and its fee, or currency conversion pairs).
        """
        stmt = select(
            Transaction.broker_reference_id, Transaction.type, Transaction.currency
        ).where(
            Transaction.broker_source == broker_source,
            Transaction.broker_reference_id.isnot(None),
        )
        result = session.execute(stmt)
        return {
            (row[0], row[1].value if hasattr(row[1], "value") else row[1], row[2]) for row in result
        }

    def _get_or_create_default_portfolio(self, session: Session) -> Portfolio:
        """Get or create a default portfolio for imports."""
        stmt = select(Portfolio).limit(1)
        portfolio = session.execute(stmt).scalar_one_or_none()

        if not portfolio:
            portfolio = Portfolio(
                name="Default Portfolio",
                base_currency="EUR",  # Default to EUR, can be configurable
            )
            session.add(portfolio)
            session.flush()

        return portfolio

    def _get_or_create_account(
        self,
        session: Session,
        portfolio_id: str,
        broker_source: str,
        account_number: str | None = None,
    ) -> Account:
        """Get or create Account for the broker.

        Args:
            session: Database session
            portfolio_id: Portfolio ID
            broker_source: Broker source (e.g., 'lightyear', 'swedbank')
            account_number: Optional account number

        Returns:
            Account record
        """
        # Query for existing account
        stmt = select(Account).where(
            Account.portfolio_id == portfolio_id,
            Account.broker_source == broker_source,
        )
        if account_number:
            stmt = stmt.where(Account.account_number == account_number)

        account = session.execute(stmt).scalar_one_or_none()

        if not account:
            # Create account with friendly name
            name = broker_source.capitalize()
            account = Account(
                portfolio_id=portfolio_id,
                name=name,
                broker_source=broker_source,
                account_number=account_number,
                base_currency="EUR",
            )
            session.add(account)
            session.flush()

        return account

    def _get_or_create_security(self, session: Session, txn: ParsedTransaction) -> Security:
        """Get or create Security record (and Stock/Bond details if needed).

        Args:
            session: Database session
            txn: Parsed transaction

        Returns:
            Security record

        Raises:
            ValueError: If neither ticker nor ISIN provided
        """
        # Use ticker as-is (no manual mappings needed)
        resolved_ticker = txn.ticker

        # Query by ticker or ISIN
        stmt = select(Security)
        if resolved_ticker:
            stmt = stmt.where(Security.ticker == resolved_ticker)
        elif txn.isin:
            stmt = stmt.where(Security.isin == txn.isin)
        else:
            raise ValueError("Either ticker or ISIN required")

        security = session.execute(stmt).scalar_one_or_none()

        if not security:
            # Determine security type (check if bond by description pattern or mapping)
            is_bond = self._is_bond_identifier(txn)

            # Securities are not archived by default - use CLI archive command to mark manually
            archived = False

            # Handle special cash placeholder
            if resolved_ticker == "ICSUSSDP":
                security_type = SecurityType.FUND  # Treat as cash fund
            elif is_bond:
                security_type = SecurityType.BOND
            else:
                security_type = SecurityType.STOCK

            # Try to enrich metadata for stocks using yfinance
            company_name = txn.company_name or resolved_ticker
            exchange = txn.exchange or "UNKNOWN"
            sector = None
            industry = None
            country = None
            region = None

            if security_type == SecurityType.STOCK and resolved_ticker:
                enriched = self._enrich_stock_metadata(resolved_ticker)
                if enriched:
                    company_name = enriched.get("name", company_name)
                    exchange = enriched.get("exchange", exchange)
                    sector = enriched.get("sector")
                    industry = enriched.get("industry")
                    country = enriched.get("country")
                    region = enriched.get("region")

            # Create Security with enriched data
            security = Security(
                security_type=security_type,
                ticker=resolved_ticker,
                isin=txn.isin,
                name=company_name or resolved_ticker or txn.isin or "Unknown",
                currency=txn.currency,
                archived=archived,
            )
            session.add(security)
            session.flush()

            # Create Stock or Bond details
            if security_type == SecurityType.STOCK:
                stock = Stock(
                    security_id=security.id,
                    exchange=exchange,
                    sector=sector,
                    industry=industry,
                    country=country,
                    region=region,
                )
                session.add(stock)
                session.flush()

                # Create stock splits if this ticker has known splits
                self._create_stock_splits(session, security, resolved_ticker)
            else:
                # For bonds, create with minimal data (can be enriched later)
                bond = Bond(
                    security_id=security.id,
                    issuer=txn.company_name or "Unknown",
                    coupon_rate=Decimal("0.0"),  # Will be enriched later
                    maturity_date=datetime(2099, 12, 31).date(),  # Placeholder
                    face_value=Decimal("1000.00"),  # Standard default
                    payment_frequency=PaymentFrequency.ANNUAL,  # Default
                )
                session.add(bond)
                session.flush()

        return security

    def _get_or_create_holding(
        self,
        session: Session,
        portfolio_id: str,
        ticker: str,
        txn: ParsedTransaction,
        security_id: str,
    ) -> Holding:
        """Get or create Holding record for the security in the portfolio.

        Args:
            session: Database session
            portfolio_id: Portfolio ID
            ticker: Stock ticker (or ISIN for bonds)
            txn: Parsed transaction
            security_id: Security ID

        Returns:
            Holding record
        """
        # Check if holding exists
        stmt = select(Holding).where(
            Holding.portfolio_id == portfolio_id,
            Holding.security_id == security_id,
        )
        holding = session.execute(stmt).scalar_one_or_none()

        if not holding:
            # Create new holding with initial transaction data
            holding = Holding(
                portfolio_id=portfolio_id,
                security_id=security_id,
                ticker=ticker,
                quantity=Decimal("0"),  # Will be updated by transactions
                avg_purchase_price=txn.price if txn.price else Decimal("0"),
                original_currency=txn.currency,
                first_purchase_date=txn.date.date() if hasattr(txn.date, "date") else txn.date,
            )
            session.add(holding)
            session.flush()

        return holding

    def _create_transaction(
        self,
        txn: ParsedTransaction,
        account_id: str,
        holding_id: str | None,
        batch_id: int,
    ) -> Transaction:
        """Create Transaction model from parsed transaction.

        Args:
            txn: Parsed transaction
            account_id: Account ID (required)
            holding_id: Holding ID to link transaction to (None for account-level txns)
            batch_id: Import batch ID

        Returns:
            Transaction record
        """
        return Transaction(
            account_id=account_id,
            holding_id=holding_id,
            type=txn.transaction_type,
            date=txn.date.date() if hasattr(txn.date, "date") else txn.date,
            amount=txn.amount,
            currency=txn.currency,
            debit_credit=txn.debit_credit,
            quantity=txn.quantity,
            price=txn.price,
            conversion_from_amount=txn.conversion_from_amount,
            conversion_from_currency=txn.conversion_from_currency,
            fees=txn.fees,
            tax_amount=txn.tax_amount,
            exchange_rate=txn.exchange_rate,  # Use exchange rate from CSV
            notes=txn.description,
            broker_source=txn.broker_source,
            broker_reference_id=txn.broker_reference_id,
            import_batch_id=batch_id,
        )

    def _create_fee_transaction(
        self,
        txn: ParsedTransaction,
        account_id: str,
        batch_id: int,
    ) -> Transaction:
        """Create FEE transaction from a transaction with fees.

        Args:
            txn: Parsed transaction (containing fee amount in fees field)
            account_id: Account ID
            batch_id: Import batch ID

        Returns:
            FEE Transaction record
        """
        import uuid

        return Transaction(
            id=str(uuid.uuid4()),
            account_id=account_id,
            holding_id=None,  # Fees are account-level, not holding-specific
            type="FEE",
            date=txn.date.date() if hasattr(txn.date, "date") else txn.date,
            amount=txn.fees,
            currency=txn.currency,
            debit_credit="D",  # Fee debits cash
            quantity=None,
            price=None,
            conversion_from_amount=None,
            conversion_from_currency=None,
            fees=Decimal("0"),  # The fee transaction itself has no additional fees
            tax_amount=None,
            exchange_rate=txn.exchange_rate,  # Use same exchange rate as main transaction
            notes=f"Fee for {txn.transaction_type} transaction",
            broker_source=txn.broker_source,
            broker_reference_id=f"{txn.broker_reference_id}-FEE",  # Unique reference
            import_batch_id=batch_id,
        )

    def get_import_history(self, limit: int = 10) -> list[ImportBatchInfo]:
        """Get recent import history.

        Args:
            limit: Maximum number of batches to return

        Returns:
            List of ImportBatchInfo ordered by upload_timestamp DESC
        """
        with db_session() as session:
            stmt = select(ImportBatch).order_by(ImportBatch.started_at.desc()).limit(limit)
            batches = session.execute(stmt).scalars().all()

            return [
                ImportBatchInfo(
                    batch_id=b.id,
                    filename=b.filename,
                    broker_type=b.broker_source,
                    upload_timestamp=b.started_at,
                    total_rows=b.total_rows,
                    successful_count=b.successful_count,
                    duplicate_count=b.duplicate_count,
                    error_count=b.error_count,
                    unknown_ticker_count=b.unknown_ticker_count,
                    status=b.status.value,
                    processing_duration=float(b.duration_seconds) if b.duration_seconds else 0.0,
                )
                for b in batches
            ]

    def get_import_errors(self, batch_id: int) -> list[ImportErrorDetail]:
        """Get detailed errors for a specific import batch.

        Args:
            batch_id: ImportBatch ID

        Returns:
            List of ImportErrorDetail

        Raises:
            ValueError: batch_id doesn't exist
        """
        with db_session() as session:
            # Check batch exists
            batch = session.get(ImportBatch, batch_id)
            if not batch:
                raise ValueError(f"Batch {batch_id} not found")

            # Get errors
            stmt = (
                select(ImportError)
                .where(ImportError.batch_id == batch_id)
                .order_by(ImportError.row_number)
            )
            errors = session.execute(stmt).scalars().all()

            return [
                ImportErrorDetail(
                    row_number=e.row_number,
                    error_type=e.error_type.value,
                    error_message=e.error_message,
                    original_row_data=e.original_data,
                )
                for e in errors
            ]

    def get_unknown_tickers(self, batch_id: int) -> list[UnknownTickerDetail]:
        """Get unknown tickers from import batch for manual review.

        Args:
            batch_id: ImportBatch ID

        Returns:
            List of UnknownTickerDetail

        Raises:
            ValueError: batch_id doesn't exist
        """
        with db_session() as session:
            # Check batch exists
            batch = session.get(ImportBatch, batch_id)
            if not batch:
                raise ValueError(f"Batch {batch_id} not found")

            # Get unknown ticker errors
            stmt = (
                select(ImportError)
                .where(
                    ImportError.batch_id == batch_id,
                    ImportError.error_type == ImportErrorType.UNKNOWN_TICKER,
                )
                .order_by(ImportError.row_number)
            )
            errors = session.execute(stmt).scalars().all()

            return [
                UnknownTickerDetail(
                    row_number=e.row_number,
                    ticker=e.original_data.get("Ticker") or e.original_data.get("ticker", ""),
                    suggestions=e.suggested_fix.get("suggestions", []) if e.suggested_fix else [],
                    confidence=e.suggested_fix.get("confidence", []) if e.suggested_fix else [],
                    transaction_preview=self._format_transaction_preview(e.original_data),
                    original_row_data=e.original_data,
                )
                for e in errors
            ]

    def _format_transaction_preview(self, row_data: dict[str, Any]) -> str:
        """Format transaction preview string."""
        txn_type = row_data.get("Type", row_data.get("type", "Transaction"))
        qty = row_data.get("Quantity", row_data.get("quantity", ""))
        price = row_data.get("Price/share", row_data.get("price", ""))
        ccy = row_data.get("CCY", row_data.get("currency", ""))

        if qty and price:
            return f"{txn_type} {qty} @ {price} {ccy}"
        else:
            net_amt = row_data.get("Net Amt.", row_data.get("net_amount", ""))
            return f"{txn_type} {net_amt} {ccy}"

    def correct_ticker(
        self,
        batch_id: int,
        row_numbers: list[int],
        corrected_ticker: str,
    ) -> int:
        """Correct ticker for specific rows and re-import transactions.

        Args:
            batch_id: ImportBatch ID
            row_numbers: List of row numbers to correct
            corrected_ticker: New ticker to use

        Returns:
            Number of transactions successfully imported after correction

        Raises:
            ValueError: batch_id doesn't exist or row_numbers invalid
        """
        with db_session() as session:
            # Verify batch exists
            batch = session.get(ImportBatch, batch_id)
            if not batch:
                raise ValueError(f"Batch {batch_id} not found")

            # Re-validate corrected ticker if validator enabled
            if self.ticker_validator:
                validation_result = self.ticker_validator.validate_ticker_sync(corrected_ticker)
                if not validation_result.valid:
                    raise ValueError(
                        f"Corrected ticker '{corrected_ticker}' is also invalid. "
                        f"Suggestions: {', '.join(validation_result.suggestions)}"
                    )

            # Get error records for these row numbers
            stmt = (
                select(ImportError)
                .where(
                    ImportError.batch_id == batch_id,
                    ImportError.row_number.in_(row_numbers),
                    ImportError.error_type == ImportErrorType.UNKNOWN_TICKER,
                )
                .order_by(ImportError.row_number)
            )
            errors = session.execute(stmt).scalars().all()

            if not errors:
                raise ValueError(
                    f"No unknown ticker errors found for rows {row_numbers} in batch {batch_id}"
                )

            imported_count = 0

            # Import each corrected transaction
            for error in errors:
                try:
                    # Update original data with corrected ticker
                    corrected_data = error.original_data.copy()
                    if "ticker" in corrected_data:
                        corrected_data["ticker"] = corrected_ticker
                    elif "Ticker" in corrected_data:
                        corrected_data["Ticker"] = corrected_ticker
                    else:
                        # Find ticker field (could be other variations)
                        for key in corrected_data:
                            if key.lower() == "ticker":
                                corrected_data[key] = corrected_ticker
                                break

                    # Note: We'd need to parse a single row here, but parsers work on files
                    # For now, we'll reconstruct a ParsedTransaction from the original data
                    # This is a limitation - ideally we'd have a parse_row() method

                    # Import the transaction
                    portfolio = self._get_or_create_default_portfolio(session)

                    # Get account
                    account = self._get_or_create_account(
                        session, portfolio.id, batch.broker_source
                    )

                    # Create security with corrected ticker
                    security_stmt = select(Security).where(Security.ticker == corrected_ticker)
                    security = session.execute(security_stmt).scalar_one_or_none()

                    if not security:
                        # Get currency and ISIN from original data
                        currency = (
                            corrected_data.get("CCY") or corrected_data.get("Valuuta") or "EUR"
                        )
                        isin = corrected_data.get("ISIN") or corrected_data.get("isin")

                        # Try to enrich metadata using corrected ticker
                        company_name = corrected_ticker
                        exchange = "UNKNOWN"
                        sector = None
                        industry = None
                        country = None
                        region = None

                        enriched = self._enrich_stock_metadata(corrected_ticker)
                        if enriched:
                            company_name = enriched.get("name", company_name)
                            exchange = enriched.get("exchange", exchange)
                            sector = enriched.get("sector")
                            industry = enriched.get("industry")
                            country = enriched.get("country")
                            region = enriched.get("region")

                        security = Security(
                            security_type=SecurityType.STOCK,
                            ticker=corrected_ticker,
                            isin=isin,
                            name=company_name,
                            currency=currency,
                        )
                        session.add(security)
                        session.flush()

                        # Create Stock details with enriched data
                        stock = Stock(
                            security_id=security.id,
                            exchange=exchange,
                            sector=sector,
                            industry=industry,
                            country=country,
                            region=region,
                        )
                        session.add(stock)
                        session.flush()

                    # Get or create holding
                    holding_stmt = select(Holding).where(
                        Holding.portfolio_id == portfolio.id,
                        Holding.security_id == security.id,
                    )
                    holding = session.execute(holding_stmt).scalar_one_or_none()

                    if not holding:
                        holding = Holding(
                            portfolio_id=portfolio.id,
                            security_id=security.id,
                            ticker=corrected_ticker,
                            quantity=Decimal("0"),
                            avg_purchase_price=Decimal("0"),
                            original_currency=security.currency,
                            first_purchase_date=datetime.now(timezone.utc).date(),
                        )
                        session.add(holding)
                        session.flush()

                    # Create transaction from original data
                    currency = corrected_data.get("CCY") or corrected_data.get("Valuuta", "EUR")
                    net_amt = Decimal(
                        corrected_data.get("Net Amt.") or corrected_data.get("net_amount", "0")
                    )

                    transaction = Transaction(
                        account_id=account.id,
                        holding_id=holding.id,
                        type=corrected_data.get("Type", "BUY").upper(),
                        date=datetime.now(timezone.utc).date(),  # TODO: Parse from original_data
                        amount=abs(net_amt),
                        currency=currency,
                        debit_credit="D" if net_amt < 0 else "K",
                        quantity=Decimal(corrected_data.get("Quantity", "0")),
                        price=Decimal(
                            corrected_data.get("Price/share") or corrected_data.get("price", "0")
                        ),
                        conversion_from_amount=None,
                        conversion_from_currency=None,
                        fees=Decimal(corrected_data.get("Fee") or corrected_data.get("fees", "0")),
                        tax_amount=(
                            Decimal(corrected_data.get("Tax Amt.") or "0")
                            if corrected_data.get("Tax Amt.")
                            else None
                        ),
                        exchange_rate=Decimal("1.0"),
                        notes="Corrected from unknown ticker",
                        broker_source=batch.broker_source,
                        broker_reference_id=corrected_data.get(
                            "Reference", f"corrected-{error.row_number}"
                        ),
                        import_batch_id=batch.id,
                    )
                    session.add(transaction)

                    # Delete error record (successfully imported)
                    session.delete(error)
                    imported_count += 1

                except Exception:
                    # Keep error record if import fails
                    continue

            # Update batch statistics
            batch.unknown_ticker_count = max(0, batch.unknown_ticker_count - imported_count)
            batch.error_count = max(0, batch.error_count - imported_count)
            batch.successful_count += imported_count

            # Update status if all errors resolved
            if batch.error_count == 0:
                batch.status = ImportStatus.COMPLETED

            session.commit()
            return imported_count

    def ignore_unknown_tickers(
        self,
        batch_id: int,
        row_numbers: list[int],
    ) -> int:
        """Import transactions with unknown tickers (skip validation).

        Args:
            batch_id: ImportBatch ID
            row_numbers: List of row numbers to import

        Returns:
            Number of transactions imported

        Raises:
            ValueError: batch_id doesn't exist or row_numbers invalid
        """
        with db_session() as session:
            # Verify batch exists
            batch = session.get(ImportBatch, batch_id)
            if not batch:
                raise ValueError(f"Batch {batch_id} not found")

            # Get error records for these row numbers
            stmt = (
                select(ImportError)
                .where(
                    ImportError.batch_id == batch_id,
                    ImportError.row_number.in_(row_numbers),
                    ImportError.error_type == ImportErrorType.UNKNOWN_TICKER,
                )
                .order_by(ImportError.row_number)
            )
            errors = session.execute(stmt).scalars().all()

            if not errors:
                raise ValueError(
                    f"No unknown ticker errors found for rows {row_numbers} in batch {batch_id}"
                )

            imported_count = 0

            # Import each transaction with unknown ticker as-is
            for error in errors:
                try:
                    original_data = error.original_data
                    ticker = (
                        original_data.get("ticker")
                        or original_data.get("Ticker")
                        or next(
                            (v for k, v in original_data.items() if k.lower() == "ticker"),
                            None,
                        )
                    )

                    if not ticker:
                        continue

                    # Import transaction with unknown ticker
                    portfolio = self._get_or_create_default_portfolio(session)

                    # Get account
                    account = self._get_or_create_account(
                        session, portfolio.id, batch.broker_source
                    )

                    # Create security with unknown ticker
                    security_stmt = select(Security).where(Security.ticker == ticker)
                    security = session.execute(security_stmt).scalar_one_or_none()

                    if not security:
                        currency = original_data.get("CCY") or original_data.get("Valuuta") or "EUR"
                        isin = original_data.get("ISIN") or original_data.get("isin")

                        # Try to enrich metadata using the ticker
                        company_name = ticker
                        exchange = "UNKNOWN"
                        sector = None
                        industry = None
                        country = None
                        region = None

                        enriched = self._enrich_stock_metadata(ticker)
                        if enriched:
                            company_name = enriched.get("name", company_name)
                            exchange = enriched.get("exchange", exchange)
                            sector = enriched.get("sector")
                            industry = enriched.get("industry")
                            country = enriched.get("country")
                            region = enriched.get("region")

                        security = Security(
                            security_type=SecurityType.STOCK,
                            ticker=ticker,
                            isin=isin,
                            name=company_name,
                            currency=currency,
                        )
                        session.add(security)
                        session.flush()

                        # Create Stock details with enriched data
                        stock = Stock(
                            security_id=security.id,
                            exchange=exchange,
                            sector=sector,
                            industry=industry,
                            country=country,
                            region=region,
                        )
                        session.add(stock)
                        session.flush()

                    # Get or create holding
                    holding_stmt = select(Holding).where(
                        Holding.portfolio_id == portfolio.id,
                        Holding.security_id == security.id,
                    )
                    holding = session.execute(holding_stmt).scalar_one_or_none()

                    if not holding:
                        holding = Holding(
                            portfolio_id=portfolio.id,
                            security_id=security.id,
                            ticker=ticker,
                            quantity=Decimal("0"),
                            avg_purchase_price=Decimal("0"),
                            original_currency=security.currency,
                            first_purchase_date=datetime.now(timezone.utc).date(),
                        )
                        session.add(holding)
                        session.flush()

                    # Create transaction from original data
                    currency = original_data.get("CCY") or original_data.get("Valuuta", "EUR")
                    net_amt = Decimal(
                        original_data.get("Net Amt.") or original_data.get("net_amount", "0")
                    )

                    transaction = Transaction(
                        account_id=account.id,
                        holding_id=holding.id,
                        type=original_data.get("Type", "BUY").upper(),
                        date=datetime.now(timezone.utc).date(),  # TODO: Parse from original_data
                        amount=abs(net_amt),
                        currency=currency,
                        debit_credit="D" if net_amt < 0 else "K",
                        quantity=Decimal(original_data.get("Quantity", "0")),
                        price=Decimal(
                            original_data.get("Price/share") or original_data.get("price", "0")
                        ),
                        conversion_from_amount=None,
                        conversion_from_currency=None,
                        fees=Decimal(original_data.get("Fee") or original_data.get("fees", "0")),
                        tax_amount=(
                            Decimal(original_data.get("Tax Amt.") or "0")
                            if original_data.get("Tax Amt.")
                            else None
                        ),
                        exchange_rate=Decimal("1.0"),
                        notes=f"Imported with unknown ticker: {ticker}",
                        broker_source=batch.broker_source,
                        broker_reference_id=original_data.get(
                            "Reference", f"unknown-{error.row_number}"
                        ),
                        import_batch_id=batch.id,
                    )
                    session.add(transaction)

                    # Delete error record (transaction imported successfully)
                    session.delete(error)
                    imported_count += 1

                except Exception:
                    # Keep error record if import fails
                    continue

            # Update batch statistics
            batch.unknown_ticker_count = max(0, batch.unknown_ticker_count - imported_count)
            batch.error_count = max(0, batch.error_count - imported_count)
            batch.successful_count += imported_count

            # Update status if all errors resolved
            if batch.error_count == 0:
                batch.status = ImportStatus.COMPLETED

            session.commit()
            return imported_count

    def delete_error_rows(
        self,
        batch_id: int,
        row_numbers: list[int],
    ) -> int:
        """Delete error rows (don't import these transactions).

        Args:
            batch_id: ImportBatch ID
            row_numbers: List of row numbers to delete

        Returns:
            Number of rows deleted

        Raises:
            ValueError: batch_id doesn't exist or row_numbers invalid
        """
        with db_session() as session:
            # Verify batch exists
            batch = session.get(ImportBatch, batch_id)
            if not batch:
                raise ValueError(f"Batch {batch_id} not found")

            # Get error records for these row numbers
            stmt = select(ImportError).where(
                ImportError.batch_id == batch_id,
                ImportError.row_number.in_(row_numbers),
            )
            errors = session.execute(stmt).scalars().all()

            if not errors:
                raise ValueError(f"No errors found for rows {row_numbers} in batch {batch_id}")

            deleted_count = 0
            unknown_ticker_deleted = 0

            # Delete error records
            for error in errors:
                if error.error_type == ImportErrorType.UNKNOWN_TICKER:
                    unknown_ticker_deleted += 1
                session.delete(error)
                deleted_count += 1

            # Update batch statistics
            batch.error_count = max(0, batch.error_count - deleted_count)
            batch.unknown_ticker_count = max(0, batch.unknown_ticker_count - unknown_ticker_deleted)
            batch.total_rows = max(0, batch.total_rows - deleted_count)

            # Update status if all errors resolved
            if batch.error_count == 0:
                batch.status = ImportStatus.COMPLETED

            session.commit()
            return deleted_count

    def _recalculate_holdings(self, session: Session) -> None:
        """Recalculate holding quantities and average prices from transactions.

        This method aggregates all transactions for each holding to calculate:
        - Current quantity (sum of BUY minus SELL quantities)
        - Average purchase price (weighted average of BUY transactions)
        - Applies stock split adjustments to historical transactions

        Should be called after importing transactions to ensure holdings reflect
        the actual position with split-adjusted values.

        Args:
            session: Database session
        """
        # Get all holdings
        holdings = session.query(Holding).all()

        for holding in holdings:
            # Get stock splits for this security
            splits = (
                session.query(StockSplit)
                .filter(StockSplit.security_id == holding.security_id)
                .order_by(StockSplit.split_date)
                .all()
            )

            # Get all transactions for this holding ordered by date
            transactions = (
                session.query(Transaction)
                .filter(Transaction.holding_id == holding.id)
                .order_by(Transaction.date)
                .all()
            )

            if not transactions:
                continue

            # Calculate quantity and weighted average price with split adjustments
            # IMPORTANT: Don't modify transaction records - calculate on-the-fly
            # NOTE: Different brokers handle split recording differently:
            # - Swedbank: Records ALL transactions in pre-split terms
            # - Lightyear: Records in actual traded terms (apply only before split)
            total_quantity = Decimal("0")
            total_cost = Decimal("0")
            first_buy_date = None

            for txn in transactions:
                if txn.type in ("BUY", "SELL"):
                    # Start with stored values from CSV
                    quantity = txn.quantity or Decimal("0")
                    price = txn.price or Decimal("0")

                    # Apply splits based on broker and transaction date
                    for split in splits:
                        # Swedbank records ALL in pre-split terms, always apply
                        # Lightyear records in actual terms, only apply before split
                        should_apply = (
                            txn.broker_source == "swedbank" or txn.date < split.split_date
                        )

                        if should_apply:
                            # Adjust quantity and price for split
                            # Example: 10 shares @ $100 with 2:1 split → 20 shares @ $50
                            quantity = quantity * split.split_ratio
                            price = price / split.split_ratio

                    if txn.type == "BUY":
                        total_quantity += quantity
                        total_cost += quantity * price
                        if first_buy_date is None:
                            first_buy_date = txn.date
                    elif txn.type == "SELL":
                        # When selling, reduce cost basis using average cost method
                        if total_quantity > 0:
                            # Calculate current average price before the sale
                            current_avg_price = total_cost / total_quantity
                            # Reduce both quantity and cost proportionally
                            total_cost -= quantity * current_avg_price
                        total_quantity -= quantity
                elif txn.type == "FEE":
                    # Add fees to cost basis (increases average purchase price)
                    fee_amount = txn.amount or Decimal("0")
                    total_cost += fee_amount

            # Update holding
            # Clamp negative quantities to 0 (incomplete transaction history)
            if total_quantity < 0:
                print(
                    f"⚠️  Warning: Negative quantity for {holding.ticker}: {total_quantity}. "
                    f"This likely means transactions were sold before the import date range. "
                    f"Setting quantity to 0."
                )
                total_quantity = Decimal("0")

            holding.quantity = total_quantity
            if total_quantity > 0 and total_cost > 0:
                holding.avg_purchase_price = total_cost / total_quantity
            elif total_quantity == 0:
                # No shares held - keep existing avg price for history
                pass
            if first_buy_date:
                holding.first_purchase_date = first_buy_date

    def _reconcile_lightyear_cash(self, session: Session, account: Account) -> int:
        """Reconcile Lightyear cash by creating synthetic ICSUSSDP BUY transactions.

        Lightyear's "add to savings" action doesn't create transactions in CSV exports.
        This method detects orphaned USD cash and creates synthetic BUY transactions
        to move it into ICSUSSDP (money market fund used as savings account).

        Args:
            session: Database session
            account: Lightyear account to reconcile

        Returns:
            Number of synthetic transactions created
        """
        # Calculate current cash balance by currency
        from sqlalchemy import func, case

        cash_balances = (
            session.query(
                Transaction.currency,
                func.sum(
                    case(
                        (Transaction.debit_credit == "K", Transaction.amount),
                        else_=-Transaction.amount
                    )
                ).label("balance")
            )
            .filter(Transaction.account_id == account.id)
            .group_by(Transaction.currency)
            .all()
        )

        created_count = 0

        for currency, balance in cash_balances:
            balance = Decimal(str(balance))

            # Skip if balance is negligible
            if balance <= Decimal("0.01"):
                continue

            # Handle USD cash: write off as missing transfer fees
            # Manual ICSUSSDP transfers don't appear in CSV
            if currency == "USD":
                created_count += self._reconcile_usd_conversion_fees(session, account, balance)

            # NOTE: We don't auto-reconcile EUR cash because it could be:
            # - Fresh deposits waiting to be converted
            # - Pending withdrawals
            # - Real EUR that hasn't been used yet
            # Only USD reconciliation is safe because ICSUSSDP is the designated savings account

        return created_count

    def _reconcile_usd_conversion_fees(self, session: Session, account: Account, balance: Decimal) -> int:
        """Reconcile USD cash by writing off as conversion/transfer fees.

        Manual ICSUSSDP transfers and some conversion fees don't appear as separate
        transactions in CSV exports. These show up as orphaned USD cash.

        Args:
            session: Database session
            account: Lightyear account
            balance: USD cash balance to reconcile

        Returns:
            Number of synthetic transactions created (0 or 1)
        """
        import uuid
        from datetime import datetime, timezone

        # Create a FEE transaction to write off conversion/transfer fees
        fee_txn = Transaction(
            id=str(uuid.uuid4()),
            account_id=account.id,
            holding_id=None,  # Account-level fee
            type="FEE",
            date=date.today(),
            amount=balance,
            currency="USD",
            debit_credit="D",  # Debit (money out)
            quantity=None,
            price=None,
            fees=Decimal("0"),
            exchange_rate=Decimal("1.0"),
            notes="Synthetic transaction: Lightyear conversion/transfer fees reconciliation",
            broker_source="lightyear",
            broker_reference_id=f"RECONCILE-USD-{date.today().isoformat()}",
            created_at=datetime.now(timezone.utc),
        )
        session.add(fee_txn)
        return 1

    def _reconcile_eur_conversion_fees(self, session: Session, account: Account, balance: Decimal) -> int:
        """Reconcile EUR cash by writing off as conversion fees.

        Lightyear charges conversion fees during EUR→USD conversions that don't
        appear as separate FEE transactions in CSV exports. These show up as
        orphaned EUR cash in our accounting.

        Args:
            session: Database session
            account: Lightyear account
            balance: EUR cash balance to reconcile

        Returns:
            Number of synthetic transactions created (0 or 1)
        """
        import uuid
        from datetime import datetime, timezone

        # Create a FEE transaction to write off conversion fees
        fee_txn = Transaction(
            id=str(uuid.uuid4()),
            account_id=account.id,
            holding_id=None,  # Account-level fee
            type="FEE",
            date=date.today(),
            amount=balance,
            currency="EUR",
            debit_credit="D",  # Debit (money out)
            quantity=None,
            price=None,
            fees=Decimal("0"),
            exchange_rate=Decimal("1.0"),
            notes="Synthetic transaction: Lightyear conversion fees reconciliation",
            broker_source="lightyear",
            broker_reference_id=f"RECONCILE-EUR-{date.today().isoformat()}",
            created_at=datetime.now(timezone.utc),
        )
        session.add(fee_txn)
        return 1

    def _link_conversion_pairs_and_create_lots(self, session: Session, batch_id: int) -> None:
        """
        Link conversion pairs and create currency lots for FIFO tracking.

        This method:
        1. Groups CONVERSION transactions by broker_reference_id
        2. Links pairs (debit/credit) by setting conversion_from fields
        3. Creates currency lots from conversions
        4. Allocates BUY transactions to lots using FIFO

        Args:
            session: Database session
            batch_id: Import batch ID
        """
        from collections import defaultdict
        from src.models.transaction import TransactionType
        from src.services.currency_lot_service import CurrencyLotService

        # Get all CONVERSION transactions from this batch
        conversions = (
            session.query(Transaction)
            .filter(
                Transaction.import_batch_id == batch_id,
                Transaction.type == TransactionType.CONVERSION,
            )
            .order_by(Transaction.date, Transaction.id)
            .all()
        )

        if not conversions:
            logger.debug(f"No conversions found in batch {batch_id}")
            return

        # Group conversions by broker_reference_id
        by_ref: dict[str, list[Transaction]] = defaultdict(list)
        for conv in conversions:
            by_ref[conv.broker_reference_id].append(conv)

        # Link conversion pairs
        paired_count = 0
        for ref_id, txns in by_ref.items():
            if len(txns) != 2:
                logger.warning(f"Conversion reference {ref_id} has {len(txns)} transactions (expected 2)")
                continue

            # Identify debit (source) and credit (target)
            debit_txn = next((t for t in txns if t.debit_credit == "D"), None)
            credit_txn = next((t for t in txns if t.debit_credit == "K"), None)

            if not debit_txn or not credit_txn:
                logger.warning(f"Conversion reference {ref_id} missing debit or credit transaction")
                continue

            # Update credit (target) transaction with conversion_from fields
            credit_txn.conversion_from_currency = debit_txn.currency
            credit_txn.conversion_from_amount = debit_txn.amount
            paired_count += 1

        logger.info(f"Linked {paired_count} conversion pairs in batch {batch_id}")
        session.flush()

        # Create currency lots from conversions
        lot_service = CurrencyLotService(session)
        lots_created = 0

        for conv in conversions:
            # Only create lots for credit (target) transactions
            if conv.debit_credit == "K" and conv.conversion_from_currency and conv.conversion_from_amount:
                try:
                    lot_service.create_lot_from_conversion(conv)
                    lots_created += 1
                except Exception as e:
                    logger.warning(f"Failed to create lot from conversion {conv.id}: {e}")

        logger.info(f"Created {lots_created} currency lots in batch {batch_id}")
        session.flush()

        # Allocate BUY transactions to lots
        buy_transactions = (
            session.query(Transaction)
            .filter(
                Transaction.import_batch_id == batch_id,
                Transaction.type == TransactionType.BUY,
                Transaction.holding_id.isnot(None),
            )
            .order_by(Transaction.date, Transaction.id)
            .all()
        )

        # Get account base currency (assume EUR for now)
        base_currency = "EUR"
        if buy_transactions:
            account = session.query(Account).filter_by(id=buy_transactions[0].account_id).first()
            if account:
                base_currency = account.base_currency

        allocated_count = 0
        skipped_count = 0

        for buy_txn in buy_transactions:
            # Skip base currency purchases
            if buy_txn.currency == base_currency:
                continue

            # Calculate purchase amount
            purchase_amount = buy_txn.quantity * buy_txn.price

            try:
                lot_service.allocate_purchase_to_lots(buy_txn, purchase_amount)
                allocated_count += 1
            except ValueError as e:
                logger.warning(f"Failed to allocate purchase {buy_txn.id}: {e}")
                skipped_count += 1

        logger.info(f"Allocated {allocated_count} purchases to lots in batch {batch_id} ({skipped_count} skipped)")
        session.flush()

    def _enrich_stock_metadata(self, ticker: str, silent: bool = False) -> dict[str, str] | None:
        """Fetch real company name, exchange, sector, country, region, and ISIN from Yahoo Finance.

        Args:
            ticker: Stock ticker symbol
            silent: If True, suppress error messages

        Returns:
            Dictionary with "name", "exchange", "sector", "industry", "country", "region", "isin"
            keys, or None if fetch fails
        """
        # Check cache first
        if ticker in self._metadata_cache:
            return self._metadata_cache[ticker]

        try:
            # Fetch ticker info from yfinance
            yf_ticker = yf.Ticker(ticker)
            info = yf_ticker.info

            # Extract company name (prefer longName, fallback to shortName)
            company_name = info.get("longName") or info.get("shortName")

            # Extract all metadata fields
            exchange = info.get("exchange", "UNKNOWN")
            sector = info.get("sector")
            industry = info.get("industry")
            country = info.get("country")
            region = info.get("region")
            isin = info.get("isin")  # ISIN code if available

            if company_name:
                result = {
                    "name": company_name,
                    "exchange": exchange,
                    "sector": sector,
                    "industry": industry,
                    "country": country,
                    "region": region,
                    "isin": isin,
                }
                self._metadata_cache[ticker] = result
                return result

            # No valid data found
            self._metadata_cache[ticker] = None
            return None

        except Exception as e:
            # Log error but don't fail import
            if not silent:
                print(f"Warning: Failed to fetch metadata for {ticker}: {e}")
            self._metadata_cache[ticker] = None
            return None

    def _is_bond_identifier(self, txn: ParsedTransaction) -> bool:
        """Check if transaction represents a bond.

        Bonds are identified by:
        1. Having "PCT" in the transaction description (for SELL transactions)
        2. Having "/" in ticker (e.g., BIG25-2035/1)
        3. Ending with 6 consecutive digits (e.g., LHVGRP290933, IUTECR061026)

        Args:
            txn: Parsed transaction with original_data

        Returns:
            True if this is a bond, False otherwise
        """
        ticker = txn.ticker

        # Check for PCT in transaction description
        if txn.original_data:
            description = txn.original_data.get("Selgitus", "")
            if "PCT" in description.upper():
                return True

        # Check ticker patterns
        if ticker:
            # Bonds with slash notation (e.g., BIG25-2035/1)
            if "/" in ticker:
                return True

            # Bonds ending with 6 digits (maturity dates like 290933, 061026)
            if len(ticker) > 6 and ticker[-6:].isdigit():
                return True

        return False

    def _create_stock_splits(
        self, session: Session, security: Security, ticker: str | None
    ) -> None:
        """Create StockSplit records from KNOWN_SPLITS for this security.

        Args:
            session: Database session
            security: Security record
            ticker: Ticker symbol to look up in KNOWN_SPLITS
        """
        if not ticker or ticker not in KNOWN_SPLITS:
            return

        # Check if splits already exist for this security
        existing_splits = (
            session.query(StockSplit).filter(StockSplit.security_id == security.id).count()
        )

        if existing_splits > 0:
            # Splits already created, skip
            return

        # Create split records from KNOWN_SPLITS
        splits_data = KNOWN_SPLITS[ticker]
        for split_info in splits_data:
            split = StockSplit(
                security_id=security.id,
                split_date=split_info["date"],
                split_ratio=split_info["ratio"],
                split_from=split_info["from"],
                split_to=split_info["to"],
                notes="Imported from KNOWN_SPLITS dictionary",
            )
            session.add(split)
            split_ratio = f"{split_info['from']}:{split_info['to']}"
            print(f"   📊 Added {ticker} split: {split_ratio} on {split_info['date']}")

        session.flush()

    def get_securities_needing_enrichment(self) -> list[dict[str, Any]]:
        """Get securities that need metadata enrichment (no company name).

        Returns:
            List of dicts with security_id, ticker, current_name, security_type
        """
        with db_session() as session:
            stmt = (
                select(Security, Stock)
                .outerjoin(Stock, Security.id == Stock.security_id)
                .where(
                    Security.security_type == SecurityType.STOCK,
                    Security.ticker.isnot(None),
                )
            )

            results = session.execute(stmt).all()

            securities_needing_enrichment = []
            for security, stock in results:
                # Check if name is just the ticker (not enriched)
                if security.name == security.ticker or stock is None or stock.exchange == "UNKNOWN":
                    securities_needing_enrichment.append(
                        {
                            "security_id": security.id,
                            "ticker": security.ticker,
                            "current_name": security.name,
                            "current_exchange": stock.exchange if stock else "N/A",
                            "security_type": security.security_type.value,
                        }
                    )

            return securities_needing_enrichment

    def update_security_metadata(self, security_id: str, yahoo_ticker: str | None = None) -> bool:
        """Update security metadata by fetching from Yahoo Finance.

        Args:
            security_id: Security ID to update
            yahoo_ticker: Optional corrected Yahoo ticker (if different from stored)

        Returns:
            True if metadata was successfully updated, False otherwise

        Raises:
            ValueError: security_id doesn't exist
        """
        with db_session() as session:
            # Get security and stock
            stmt = (
                select(Security, Stock)
                .outerjoin(Stock, Security.id == Stock.security_id)
                .where(Security.id == security_id)
            )

            result = session.execute(stmt).one_or_none()
            if not result:
                raise ValueError(f"Security not found: {security_id}")

            security, stock = result

            # Use provided yahoo_ticker or fallback to stored ticker
            ticker_to_fetch = yahoo_ticker or security.ticker

            if not ticker_to_fetch:
                return False

            # Clear cache if using corrected ticker
            if yahoo_ticker and yahoo_ticker in self._metadata_cache:
                del self._metadata_cache[yahoo_ticker]

            # Fetch metadata
            enriched = self._enrich_stock_metadata(ticker_to_fetch, silent=False)

            if enriched:
                # Always overwrite with Yahoo data
                security.name = enriched["name"]

                # Update ISIN if available from Yahoo Finance (only if not already set)
                if enriched.get("isin") and not security.isin:
                    security.isin = enriched["isin"]

                # Update ticker if corrected ticker was provided
                if yahoo_ticker:
                    security.ticker = yahoo_ticker

                    # Also update ticker in all holdings for this security
                    stmt_holdings = select(Holding).where(Holding.security_id == security.id)
                    holdings = session.execute(stmt_holdings).scalars().all()
                    for holding in holdings:
                        holding.ticker = yahoo_ticker

                # Update stock fields (exchange, sector, industry, country, region)
                if stock:
                    stock.exchange = enriched["exchange"]
                    stock.sector = enriched.get("sector")
                    stock.industry = enriched.get("industry")
                    stock.country = enriched.get("country")
                    stock.region = enriched.get("region")
                else:
                    # Create stock record if it doesn't exist
                    stock = Stock(
                        security_id=security.id,
                        exchange=enriched["exchange"],
                        sector=enriched.get("sector"),
                        industry=enriched.get("industry"),
                        country=enriched.get("country"),
                        region=enriched.get("region"),
                    )
                    session.add(stock)

                session.commit()
                isin_msg = f" [ISIN: {security.isin}]" if security.isin else ""
                print(f"✅ Updated {security.ticker}: {enriched['name']} ({enriched['exchange']}){isin_msg}")
                return True
            else:
                print(f"❌ Failed to fetch metadata for {ticker_to_fetch}")
                return False

    def link_dividends_to_holdings(
        self, security_id: str | None = None, session: Session | None = None
    ) -> int:
        """Link dividend/interest transactions to their holdings by matching ISIN from notes or metadata.

        Args:
            security_id: Optional security ID to limit linking to a specific security
            session: Optional existing database session (creates new one if not provided)

        Returns:
            Number of dividend/interest transactions linked
        """
        import re

        own_session = session is None
        if own_session:
            session = db_session().__enter__()

        try:
            from src.models import TransactionType

            # Build query for unlinked dividend/interest transactions
            query = select(Transaction).where(
                Transaction.type.in_([TransactionType.DIVIDEND, TransactionType.INTEREST]),
                Transaction.holding_id.is_(None)
            )

            unlinked_dividends = session.execute(query).scalars().all()

            if not unlinked_dividends:
                return 0

            linked_count = 0

            # Pattern to extract ISIN from notes (format: "'/123456/ EE0000001105 Company Name dividend...")
            isin_pattern = re.compile(r"'/\d+/ ([A-Z]{2}[A-Z0-9]{10}) ")

            for dividend in unlinked_dividends:
                # Get account to find portfolio
                account = session.query(Account).filter(Account.id == dividend.account_id).first()
                if not account:
                    continue

                portfolio_id = account.portfolio_id

                # Try to extract ISIN
                isin = None

                # Method 1: Check metadata
                if dividend.metadata and "isin" in dividend.metadata:
                    isin = dividend.metadata["isin"]

                # Method 2: Extract from notes field
                if not isin and dividend.notes:
                    match = isin_pattern.search(dividend.notes)
                    if match:
                        isin = match.group(1)

                if not isin:
                    continue

                # Find security by ISIN
                security = session.query(Security).filter(Security.isin == isin).first()

                if not security:
                    continue

                # Filter by security_id if provided
                if security_id and security.id != security_id:
                    continue

                # Find holding for this security in the portfolio
                holding = (
                    session.query(Holding)
                    .filter(
                        Holding.security_id == security.id,
                        Holding.portfolio_id == portfolio_id,
                    )
                    .first()
                )

                if holding:
                    dividend.holding_id = holding.id
                    linked_count += 1

            if linked_count > 0:
                session.commit()

            return linked_count

        finally:
            if own_session:
                session.__exit__(None, None, None)
