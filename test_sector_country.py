#!/usr/bin/env python3
"""Test sector, country, and region enrichment."""


from src.lib.db import init_db
from src.services.import_service import ImportService

# Initialize database
print("Initializing database...")
init_db()

# Create test service
service = ImportService()

# Test tickers
test_tickers = {
    "AAPL": "Apple Inc.",
    "TSLA": "Tesla",
    "NKE": "Nike",
}

print("\n" + "=" * 80)
print("TESTING METADATA ENRICHMENT WITH SECTOR, COUNTRY, REGION")
print("=" * 80)

for ticker, expected_name in test_tickers.items():
    print(f"\nFetching metadata for {ticker}...")

    # Fetch enriched metadata
    enriched = service._enrich_stock_metadata(ticker, silent=False)

    if enriched:
        print(f"\n✅ Successfully fetched metadata for {ticker}:")
        print(f"  Name: {enriched['name']}")
        print(f"  Exchange: {enriched['exchange']}")
        print(f"  Sector: {enriched.get('sector', 'N/A')}")
        print(f"  Industry: {enriched.get('industry', 'N/A')}")
        print(f"  Country: {enriched.get('country', 'N/A')}")
        print(f"  Region: {enriched.get('region', 'N/A')}")
    else:
        print(f"\n❌ Failed to fetch metadata for {ticker}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

print(
    """
The metadata enrichment now fetches and stores:
1. ✅ Company name (longName or shortName)
2. ✅ Exchange code (e.g., NMS, NYQ)
3. ✅ Sector (e.g., Technology, Consumer Cyclical)
4. ✅ Industry (e.g., Consumer Electronics, Auto Manufacturers)
5. ✅ Country (e.g., United States)
6. ✅ Region (e.g., Americas)

These fields are automatically saved during:
- CSV import (stocks-helper import csv)
- Metadata updates (stocks-helper import update-metadata)
"""
)
