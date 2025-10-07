#!/usr/bin/env python3
"""
Migration script to update transaction constraints to allow zero amounts and prices.

This allows importing gifted shares with zero cost basis.
"""

import shutil
from datetime import datetime

from sqlalchemy import text

from src.lib.db import DEFAULT_DB_PATH, get_engine


def backup_database():
    """Create a backup of the database before migration."""
    backup_path = DEFAULT_DB_PATH.with_suffix(
        f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    )
    print(f"Creating backup: {backup_path}")
    shutil.copy2(DEFAULT_DB_PATH, backup_path)
    print("✓ Backup created")
    return backup_path


def migrate_constraints():
    """Migrate transaction table constraints to allow zero amounts and prices."""
    engine = get_engine()

    with engine.connect() as conn:
        # Begin transaction
        trans = conn.begin()

        try:
            print("\nStarting constraint migration...")

            # Step 1: Create new table with updated constraints
            print("1. Creating new transactions table with updated constraints...")
            conn.execute(
                text(
                    """
                CREATE TABLE transactions_new (
                    id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    holding_id TEXT,
                    import_batch_id TEXT,
                    type TEXT NOT NULL,
                    date DATE NOT NULL,
                    amount NUMERIC(12, 2) NOT NULL,
                    currency VARCHAR(3) NOT NULL,
                    debit_credit VARCHAR(1) NOT NULL,
                    quantity NUMERIC(12, 4),
                    price NUMERIC(12, 4),
                    conversion_from_amount NUMERIC(12, 2),
                    conversion_from_currency VARCHAR(3),
                    fees NUMERIC(12, 2) NOT NULL DEFAULT 0,
                    tax_amount NUMERIC(12, 2),
                    exchange_rate NUMERIC(12, 6) NOT NULL,
                    notes TEXT,
                    broker_source VARCHAR(50),
                    broker_reference_id VARCHAR(100),
                    original_data JSON,
                    PRIMARY KEY (id),
                    FOREIGN KEY(account_id) REFERENCES accounts (id),
                    FOREIGN KEY(holding_id) REFERENCES holdings (id),
                    FOREIGN KEY(import_batch_id) REFERENCES import_batches (id),
                    CONSTRAINT check_amount_positive CHECK (amount >= 0),
                    CONSTRAINT check_fees_non_negative CHECK (fees >= 0),
                    CONSTRAINT check_quantity_positive_if_present
                        CHECK (quantity IS NULL OR quantity > 0),
                    CONSTRAINT check_price_positive_if_present CHECK (price IS NULL OR price >= 0),
                    CONSTRAINT check_exchange_rate_positive CHECK (exchange_rate > 0),
                    CONSTRAINT check_debit_credit_valid CHECK (debit_credit IN ('D', 'K')),
                    CONSTRAINT check_conversion_fields CHECK (
                        (conversion_from_amount IS NULL AND conversion_from_currency IS NULL)
                        OR (conversion_from_amount IS NOT NULL
                            AND conversion_from_currency IS NOT NULL)
                    )
                )
            """
                )
            )
            print("   ✓ New table created")

            # Step 2: Copy all data from old table to new table
            print("2. Copying data from old table...")
            result = conn.execute(
                text(
                    """
                INSERT INTO transactions_new
                SELECT * FROM transactions
            """
                )
            )
            print(f"   ✓ Copied {result.rowcount} rows")

            # Step 3: Drop old table
            print("3. Dropping old transactions table...")
            conn.execute(text("DROP TABLE transactions"))
            print("   ✓ Old table dropped")

            # Step 4: Rename new table to original name
            print("4. Renaming new table...")
            conn.execute(text("ALTER TABLE transactions_new RENAME TO transactions"))
            print("   ✓ Table renamed")

            # Commit transaction
            trans.commit()
            print("\n✓ Migration completed successfully!")

        except Exception as e:
            trans.rollback()
            print(f"\n✗ Migration failed: {e}")
            print("Database has been rolled back to original state.")
            raise


if __name__ == "__main__":
    print("=" * 60)
    print("Transaction Constraints Migration")
    print("=" * 60)
    print("\nThis migration updates constraints to allow:")
    print("  - amount >= 0 (was: amount > 0)")
    print("  - price >= 0 (was: price > 0)")
    print("\nThis enables importing gifted shares with zero cost basis.")
    print("=" * 60)

    # Create backup
    backup_path = backup_database()

    # Run migration
    try:
        migrate_constraints()
        print(f"\nBackup location: {backup_path}")
        print("You can delete the backup if everything works correctly.")
    except Exception:
        print(f"\nMigration failed. Your data is safe in the backup: {backup_path}")
        print("You can restore it by copying it back to the original location.")
        exit(1)
