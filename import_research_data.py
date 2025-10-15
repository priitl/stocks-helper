#!/usr/bin/env python3
"""Import all CSV files from research directory.

This script imports transaction data from broker CSV exports (Swedbank and Lightyear)
into the stocks-helper database.

Usage:
    python import_research_data.py
"""

from pathlib import Path

from src.lib.db import db_session
from src.models import Holding, ImportBatch, Security, Transaction
from src.services.import_service import ImportService

# Initialize import service
service = ImportService()

# Define CSV files to import
files = [
    ("research/swed_2020_2021.csv", "swedbank"),
    ("research/swed_2022_2023.csv", "swedbank"),
    ("research/swed_2024_2025.csv", "swedbank"),
    ("research/lightyear_2022_2025.csv", "lightyear"),
]

print("=" * 60)
print("IMPORTING RESEARCH DATA")
print("=" * 60)

total_imported = 0
total_rows = 0

# Import each file
for filepath, broker_type in files:
    print(f"\n📥 Importing {filepath}...")
    print(f"   Broker: {broker_type}")

    try:
        result = service.import_csv(Path(filepath), broker_type=broker_type, dry_run=False)

        print(f"   ✓ Success: {result.successful_count}/{result.total_rows} transactions")
        print(f"   ⊘ Duplicates: {result.duplicate_count}")
        print(f"   ⚠ Errors: {result.error_count}")

        if result.unknown_ticker_count > 0:
            print(f"   ❓ Unknown tickers: {result.unknown_ticker_count}")

        total_imported += result.successful_count
        total_rows += result.total_rows

    except Exception as e:
        print(f"   ❌ Failed: {e}")

print("\n" + "=" * 60)
print("✓ Import completed!")
print(f"  Total rows processed: {total_rows}")
print(f"  Successfully imported: {total_imported}")
print("=" * 60)

# Show summary
print("\n📊 Verifying database contents...\n")

with db_session() as session:
    txn_count = session.query(Transaction).count()
    holding_count = session.query(Holding).count()
    security_count = session.query(Security).count()
    batch_count = session.query(ImportBatch).count()

    print("Database Summary:")
    print(f"  📈 Securities: {security_count}")
    print(f"  💼 Holdings: {holding_count}")
    print(f"  💸 Transactions: {txn_count}")
    print(f"  📦 Import Batches: {batch_count}")
    print()
