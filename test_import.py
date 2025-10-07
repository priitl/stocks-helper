#!/usr/bin/env python3
"""Test script to import CSVs and verify metadata enrichment."""

from pathlib import Path

from src.lib.db import db_session, init_db
from src.services.import_service import ImportService

# Initialize database first
print("Initializing database...")
init_db()

PORTFOLIO_ID = "2f6a9903-fbac-4c55-a3c4-83928845ee2e"

files_to_import = [
    ("research/swed_2020_2021.csv", "swedbank"),
    ("research/swed_2022_2023.csv", "swedbank"),
    ("research/swed_2024_2025.csv", "swedbank"),
    ("research/lightyear_2022_2025.csv", "lightyear"),
]

service = ImportService()

print("Starting imports...")
for filepath, broker_type in files_to_import:
    print(f"\nImporting {filepath} ({broker_type})...")
    result = service.import_csv(
        filepath=Path(filepath),
        broker_type=broker_type,
    )
    print(f"  Total rows: {result.total_rows}")
    print(f"  Successful: {result.successful_count}")
    print(f"  Duplicates: {result.duplicate_count}")
    print(f"  Errors: {result.error_count}")
    print(f"  Unknown tickers: {result.unknown_ticker_count}")
    if result.unknown_ticker_count > 0:
        print(f"  Requires ticker review: {result.requires_ticker_review}")

print("\n\nNow checking holdings with enriched metadata...")
with db_session() as session:
    from sqlalchemy import select

    from src.models import Holding, Security, Stock

    stmt = (
        select(Holding, Security, Stock)
        .join(Security, Holding.security_id == Security.id)
        .outerjoin(Stock, Security.id == Stock.security_id)
        .where(Holding.quantity > 0)
        .order_by(Security.ticker)
    )

    results = session.execute(stmt).all()

    print(f"\n{'Ticker':<15} {'Name':<40} {'Exchange':<15}")
    print("=" * 70)
    for holding, security, stock in results:
        exchange = stock.exchange if stock else "N/A"
        print(f"{security.ticker:<15} {security.name:<40} {exchange:<15}")
