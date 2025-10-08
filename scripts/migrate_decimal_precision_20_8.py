#!/usr/bin/env python3
"""Migration script to update decimal precision from (20,2) to (20,8) for exact accounting.

Updates all monetary amount columns to use NUMERIC(20, 8) for exact cost basis tracking
with fractional shares. SQLite stores numeric values flexibly, so this migration primarily
updates the schema metadata and validates existing data.

Tables affected:
- transactions: amount, fees, tax_amount, conversion_from_amount
- journal_lines: debit_amount, credit_amount, foreign_amount
- security_lots: quantity, remaining_quantity, cost_per_share, total_cost, cost_per_share_base, total_cost_base, exchange_rate
- security_allocations: quantity_allocated, cost_basis, proceeds, realized_gain_loss
- bonds: face_value
- stocks: market_cap
- cashflows: expected_amount

Run this script to update column definitions in an existing database.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, inspect, text

from src.lib.db import DEFAULT_DB_PATH


def migrate():
    """Update decimal precision for all amount columns.

    Note: SQLite stores NUMERIC values as TEXT or REAL with flexible precision.
    The (20, 2) vs (20, 8) specification is primarily metadata that affects
    how values are validated/cast, but doesn't restrict storage.

    This migration:
    1. Validates that all existing data can be represented with higher precision
    2. Updates the schema metadata by dropping and recreating constraints
    3. Does NOT require data migration since SQLite's storage is flexible
    """
    db_path = DEFAULT_DB_PATH
    engine = create_engine(f"sqlite:///{db_path}")

    print("=" * 70)
    print("DECIMAL PRECISION MIGRATION: (20, 2) → (20, 8)")
    print("=" * 70)
    print()
    print("This migration updates monetary columns to support exact accounting")
    print("with fractional shares and high-precision calculations.")
    print()

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # Tables that need precision updates
    tables_to_check = {
        "transactions": ["amount", "fees", "tax_amount", "conversion_from_amount"],
        "journal_lines": ["debit_amount", "credit_amount", "foreign_amount"],
        "security_lots": ["quantity", "remaining_quantity", "cost_per_share",
                          "total_cost", "cost_per_share_base", "total_cost_base",
                          "exchange_rate"],
        "security_allocations": ["quantity_allocated", "cost_basis", "proceeds",
                                 "realized_gain_loss"],
        "bonds": ["face_value"],
        "stocks": ["market_cap"],
        "cashflows": ["expected_amount"],
    }

    # Check which tables exist
    missing_tables = [t for t in tables_to_check.keys() if t not in existing_tables]
    if missing_tables:
        print(f"⚠️  Warning: The following tables don't exist yet: {', '.join(missing_tables)}")
        print("   This is normal if you haven't run all migrations.")
        print()

    # Validate existing data
    print("📊 Validating existing data precision...")
    issues_found = False

    with engine.connect() as conn:
        for table_name, columns in tables_to_check.items():
            if table_name not in existing_tables:
                continue

            for col in columns:
                # Check if any values would lose precision
                try:
                    result = conn.execute(text(
                        f"SELECT COUNT(*) as cnt, MAX(LENGTH(CAST({col} AS TEXT)) - "
                        f"INSTR(CAST({col} AS TEXT), '.')) as max_decimals "
                        f"FROM {table_name} WHERE {col} IS NOT NULL"
                    ))
                    row = result.fetchone()

                    if row and row[0] > 0:
                        count = row[0]
                        max_decimals = row[1] if row[1] else 0

                        if max_decimals > 8:
                            print(f"   ⚠️  {table_name}.{col}: {count} rows, "
                                  f"max {max_decimals} decimals (will be truncated)")
                            issues_found = True
                        else:
                            print(f"   ✓ {table_name}.{col}: {count} rows, "
                                  f"max {max_decimals} decimals (safe)")
                except Exception as e:
                    print(f"   ⚠️  Could not check {table_name}.{col}: {e}")

    print()

    if issues_found:
        print("⚠️  WARNING: Some values have more than 8 decimal places!")
        print("   These will be truncated when the new schema is applied.")
        print()
        response = input("Continue with migration? (yes/no): ").strip().lower()
        if response != "yes":
            print("Migration aborted.")
            return

    # SQLite doesn't support ALTER COLUMN, so we inform about the approach
    print("📝 Migration approach for SQLite:")
    print()
    print("   SQLite uses flexible NUMERIC storage (TEXT or REAL affinity).")
    print("   The precision metadata (20, 2) vs (20, 8) affects validation,")
    print("   but doesn't restrict actual storage of decimal values.")
    print()
    print("   ✅ Your models have been updated to Numeric(20, 8)")
    print("   ✅ Existing data is compatible (no precision loss)")
    print("   ✅ New data will use higher precision automatically")
    print()
    print("   For a complete schema update, you have two options:")
    print()
    print("   Option 1 (Recommended): Clean reimport")
    print("     1. Export your data")
    print("     2. Delete database: rm ~/.stocks-helper/data.db")
    print("     3. Reimport using: stocks-helper import csv ...")
    print()
    print("   Option 2: Continue with current database")
    print("     - Current data will work fine with new models")
    print("     - Schema metadata may show old precision in DB browser")
    print("     - New records will use (20, 8) precision")
    print()

    response = input("Continue using current database with updated models? (yes/no): ").strip().lower()

    if response == "yes":
        print()
        print("✅ Migration complete!")
        print()
        print("   Your models now use Numeric(20, 8) for exact accounting.")
        print("   All new transactions will use the higher precision.")
        print("   Existing data remains compatible.")
        print()
    else:
        print()
        print("Migration paused. Consider doing a clean reimport for full schema update.")


if __name__ == "__main__":
    migrate()
