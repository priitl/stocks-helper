#!/usr/bin/env python3
"""Import all CSV files from research/ directory into the database.

This script:
1. Clears the existing database
2. Imports all CSVs from research/ directory
3. Reports import statistics
"""

from pathlib import Path

from src.lib.db import init_db, reset_db
from src.services.import_service import ImportService


def main():
    """Import all research CSVs."""
    # Database path
    db_path = Path.home() / ".stocks-helper" / "stocks.db"

    print("📊 Stocks Helper - CSV Import")
    print("=" * 60)
    print(f"Database: {db_path}\n")

    # 1. Reset database
    print("🗑️  Clearing existing database...")
    reset_db(db_path)
    init_db(db_path)
    print("✅ Database cleared and initialized\n")

    # 2. Import CSVs
    research_dir = Path(__file__).parent / "research"
    csv_files = [
        ("lightyear_2022_2025.csv", "lightyear"),
        ("swed_2020_2021.csv", "swedbank"),
        ("swed_2022_2023.csv", "swedbank"),
        ("swed_2024_2025.csv", "swedbank"),
    ]

    service = ImportService()
    results = []

    for filename, broker_type in csv_files:
        csv_path = research_dir / filename
        if not csv_path.exists():
            print(f"⚠️  File not found: {csv_path}")
            continue

        print(f"📥 Importing {filename} ({broker_type})...")
        try:
            result = service.import_csv(csv_path, broker_type=broker_type)
            results.append((filename, result))

            # Print summary
            print(f"   ✅ Total rows: {result.total_rows}")
            print(f"   ✅ Successful: {result.successful_count}")
            print(f"   ⏭️  Duplicates: {result.duplicate_count}")
            print(f"   ❌ Errors: {result.error_count}")
            if result.requires_ticker_review:
                print(f"   ⚠️  Unknown tickers: {result.unknown_ticker_count}")
            print()

        except Exception as e:
            print(f"   ❌ Error: {e}\n")
            continue

    # 3. Final summary
    print("=" * 60)
    print("📈 Import Summary")
    print("=" * 60)

    total_rows = sum(r.total_rows for _, r in results)
    total_successful = sum(r.successful_count for _, r in results)
    total_duplicates = sum(r.duplicate_count for _, r in results)
    total_errors = sum(r.error_count for _, r in results)
    total_unknowns = sum(r.unknown_ticker_count for _, r in results)

    print(f"Files imported: {len(results)}/{len(csv_files)}")
    print(f"Total rows processed: {total_rows}")
    print(f"Successful imports: {total_successful}")
    print(f"Duplicates skipped: {total_duplicates}")
    print(f"Errors: {total_errors}")
    print(f"Unknown tickers: {total_unknowns}")
    print()

    # List unknown tickers if any
    if total_unknowns > 0:
        print("⚠️  Unknown tickers requiring review:")
        for filename, result in results:
            if result.unknown_ticker_count > 0:
                print(f"\n  {filename}:")
                unknowns = service.get_unknown_tickers(result.batch_id)
                for unknown in unknowns:
                    suggestions_str = (
                        ", ".join(unknown.suggestions[:3]) if unknown.suggestions else "none"
                    )
                    print(f"    - {unknown.ticker} (suggestions: {suggestions_str})")

    print()
    print("✅ Import complete!")


if __name__ == "__main__":
    main()
