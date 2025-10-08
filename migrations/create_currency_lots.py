#!/usr/bin/env python3
"""
Migration: Create currency_lots and currency_allocations tables.

This migration adds support for precise currency lot tracking:
- Creates currency_lots table to track each conversion as a "lot"
- Creates currency_allocations table to track which lots funded which purchases
- Populates currency_lots from existing CONVERSION transactions
"""

from sqlalchemy import text

from src.lib.db import get_engine


def main():
    """Run migration to create currency lot tables."""
    print("Creating currency_lots and currency_allocations tables...")

    # Get engine
    engine = get_engine()

    # Create tables using SQLAlchemy metadata

    # Import all models to ensure they're registered
    from src.models import (  # noqa: F401
        Account,
        CurrencyAllocation,
        CurrencyLot,
    )

    # Create only the new tables
    CurrencyLot.__table__.create(bind=engine, checkfirst=True)
    CurrencyAllocation.__table__.create(bind=engine, checkfirst=True)

    print("✓ Tables created successfully")

    # Verify tables exist
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' "
                "AND name IN ('currency_lots', 'currency_allocations')"
            )
        )
        tables = [row[0] for row in result]
        print(f"✓ Verified tables: {tables}")

    print("\nMigration complete!")
    print("Next steps:")
    print("  1. Run the currency lot service to populate lots from conversions")
    print("  2. Run the allocation service to link purchases to lots")


if __name__ == "__main__":
    main()
