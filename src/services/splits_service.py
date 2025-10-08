"""Stock splits service for fetching and managing split data.

Implements hybrid approach: database storage + yfinance sync.
"""

import logging
from datetime import date
from decimal import Decimal

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import Security, StockSplit

logger = logging.getLogger(__name__)


class SplitsService:
    """Service for managing stock split data."""

    def sync_splits_from_yfinance(
        self, session: Session, security_id: str, ticker: str
    ) -> int:
        """Fetch stock splits from yfinance and store in database.

        Only syncs splits that occurred after the first purchase date of the security
        to avoid storing irrelevant historical splits.

        Args:
            session: Database session
            security_id: Security ID to link splits to
            ticker: Stock ticker symbol for yfinance

        Returns:
            Number of new splits added

        Raises:
            Exception: If yfinance fetch fails
        """
        try:
            # Find the earliest purchase date for this security
            from src.models import Holding

            earliest_purchase_stmt = (
                select(Holding.first_purchase_date)
                .where(Holding.security_id == security_id)
                .order_by(Holding.first_purchase_date)
                .limit(1)
            )
            earliest_purchase = session.execute(earliest_purchase_stmt).scalar_one_or_none()

            if not earliest_purchase:
                logger.info(f"No holdings found for {ticker}, skipping split sync")
                return 0

            # Fetch splits from yfinance
            yf_ticker = yf.Ticker(ticker)
            splits_series = yf_ticker.splits

            if splits_series is None or len(splits_series) == 0:
                logger.info(f"No splits found for {ticker}")
                return 0

            # Get existing splits for this security to avoid duplicates
            existing_splits = (
                session.query(StockSplit)
                .filter(StockSplit.security_id == security_id)
                .all()
            )
            existing_dates = {split.split_date for split in existing_splits}

            added_count = 0

            # Process each split from yfinance
            for split_date_ts, split_ratio in splits_series.items():
                split_date = split_date_ts.date()

                # Skip splits that occurred before first purchase
                if split_date < earliest_purchase:
                    logger.debug(
                        f"Skipping split on {split_date} for {ticker} "
                        f"(before first purchase on {earliest_purchase})"
                    )
                    continue

                # Skip if we already have this exact split date
                if split_date in existing_dates:
                    logger.debug(f"Split on {split_date} already exists for {ticker}")
                    continue

                # Check for duplicate splits with same ratio within 7 days
                # This catches Yahoo Finance data quality issues (same split, different dates)
                is_duplicate = False
                for existing_split in existing_splits:
                    days_diff = abs((split_date - existing_split.split_date).days)
                    ratio_diff = abs(float(split_ratio) - float(existing_split.split_ratio))

                    if days_diff <= 7 and ratio_diff < 0.01:
                        logger.warning(
                            f"Skipping likely duplicate split for {ticker}: "
                            f"{split_ratio} on {split_date} (similar to "
                            f"{existing_split.split_ratio} on {existing_split.split_date})"
                        )
                        is_duplicate = True
                        break

                if is_duplicate:
                    continue

                # Convert ratio to split_from/split_to
                # yfinance gives ratio as float (e.g., 2.0 for 2:1, 0.5 for 1:2)
                split_from, split_to = self._ratio_to_from_to(float(split_ratio))

                # Create split record
                stock_split = StockSplit(
                    security_id=security_id,
                    split_date=split_date,
                    split_ratio=Decimal(str(split_ratio)),
                    split_from=split_from,
                    split_to=split_to,
                    notes=f"Synced from yfinance on {date.today()}",
                )
                session.add(stock_split)
                session.flush()  # Ensure split has an ID before updating lots
                added_count += 1

                # Add to existing_splits so subsequent iterations can check against it
                existing_splits.append(stock_split)
                existing_dates.add(split_date)

                logger.info(
                    f"Added split for {ticker}: {split_from}:{split_to} "
                    f"(ratio={split_ratio}) on {split_date}"
                )

                # Apply split to existing lots immediately (Option B architecture)
                # This updates lot quantities and cost basis for lots purchased before split date
                from src.services.lot_tracking_service import apply_split_to_existing_lots

                updated_lots = apply_split_to_existing_lots(session, security_id, stock_split)
                logger.info(f"Applied split to {updated_lots} existing lot(s) for {ticker}")

            session.flush()
            return added_count

        except Exception as e:
            logger.error(f"Failed to sync splits for {ticker}: {e}")
            raise

    def sync_all_securities(self, session: Session) -> dict[str, int]:
        """Sync splits for all securities in the database.

        Args:
            session: Database session

        Returns:
            Dictionary mapping ticker to count of new splits added
        """
        # Get all stocks (not bonds)
        securities = session.query(Security).filter(Security.type == "STOCK").all()

        results = {}

        for security in securities:
            ticker = security.ticker
            if not ticker:
                logger.warning(f"Security {security.id} has no ticker, skipping")
                continue

            try:
                added = self.sync_splits_from_yfinance(session, security.id, ticker)
                results[ticker] = added

                if added > 0:
                    logger.info(f"Synced {added} split(s) for {ticker}")

            except Exception as e:
                logger.error(f"Failed to sync {ticker}: {e}")
                results[ticker] = -1  # Indicate error

        session.commit()
        return results

    def _ratio_to_from_to(self, ratio: float) -> tuple[int, int]:
        """Convert split ratio to from/to integers.

        Args:
            ratio: Split ratio (e.g., 2.0, 0.5, 1.5)

        Returns:
            Tuple of (split_from, split_to)

        Examples:
            2.0 -> (1, 2)   # 2-for-1 split
            0.5 -> (2, 1)   # 1-for-2 reverse split
            1.5 -> (2, 3)   # 3-for-2 split
            0.1 -> (10, 1)  # 1-for-10 reverse split
        """
        # Handle common cases
        if ratio == int(ratio):
            # Simple ratios like 2.0, 3.0, etc.
            if ratio >= 1:
                return (1, int(ratio))
            else:
                return (int(1 / ratio), 1)

        # Handle fractional ratios
        # Convert to fraction and simplify
        # Use a simple algorithm: find GCD
        from math import gcd

        # Convert to hundredths to handle decimals like 1.5
        numerator = int(ratio * 100)
        denominator = 100

        # Simplify
        common = gcd(numerator, denominator)
        numerator //= common
        denominator //= common

        if ratio >= 1:
            return (denominator, numerator)
        else:
            return (numerator, denominator)

    def get_splits_for_security(
        self, session: Session, security_id: str
    ) -> list[StockSplit]:
        """Get all splits for a security, ordered by date.

        Args:
            session: Database session
            security_id: Security ID

        Returns:
            List of StockSplit objects, ordered by date (earliest first)
        """
        return (
            session.query(StockSplit)
            .filter(StockSplit.security_id == security_id)
            .order_by(StockSplit.split_date)
            .all()
        )
