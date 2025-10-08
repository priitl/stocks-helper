#!/usr/bin/env python3
"""Migration script to add security_lots and security_allocations tables.

Adds GAAP/IFRS compliant lot tracking tables for:
- SecurityLot: Track individual purchase lots with cost basis
- SecurityAllocation: Track FIFO lot allocations to sales

Run this script to add the tables to an existing database.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, inspect

from src.lib.db import DEFAULT_DB_PATH, Base
from src.models import SecurityAllocation, SecurityLot


def migrate():
    """Create security_lots and security_allocations tables if they don't exist."""
    db_path = DEFAULT_DB_PATH
    engine = create_engine(f"sqlite:///{db_path}")

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    tables_to_create = []

    if "security_lots" not in existing_tables:
        tables_to_create.append("security_lots")
        print("✓ Will create table: security_lots")
    else:
        print("→ Table already exists: security_lots")

    if "security_allocations" not in existing_tables:
        tables_to_create.append("security_allocations")
        print("✓ Will create table: security_allocations")
    else:
        print("→ Table already exists: security_allocations")

    if not tables_to_create:
        print("\n✅ All tables already exist. No migration needed.")
        return

    print(f"\n📝 Creating {len(tables_to_create)} table(s)...")

    # Create only the security lot tables
    SecurityLot.__table__.create(engine, checkfirst=True)
    SecurityAllocation.__table__.create(engine, checkfirst=True)

    print("\n✅ Migration complete! GAAP/IFRS lot tracking tables created.")
    print("\nNext steps:")
    print("1. Run: stocks-helper accounting chart")
    print("   (Verify Fair Value Adjustment and Unrealized G/L accounts exist)")
    print("2. Consider running: python scripts/rebuild_journal_entries_gaap.py")
    print("   (Rebuild all journal entries with lot tracking)")


if __name__ == "__main__":
    migrate()
