#!/usr/bin/env python3
"""Demonstrate metadata enrichment update workflow."""

from sqlalchemy import select

from src.lib.db import db_session
from src.models import Security, Stock
from src.services.import_service import ImportService

service = ImportService()

print("=" * 80)
print("SECURITIES NEEDING METADATA ENRICHMENT")
print("=" * 80)

# Get all securities that need enrichment
securities = service.get_securities_needing_enrichment()

if not securities:
    print("✅ All securities have been enriched!")
else:
    print(f"\nFound {len(securities)} securities that need enrichment:\n")
    print(f"{'Ticker':<15} {'Current Name':<40} {'Exchange':<15}")
    print("-" * 70)
    for sec in securities:
        print(f"{sec['ticker']:<15} {sec['current_name']:<40} {sec['current_exchange']:<15}")

print("\n" + "=" * 80)
print("CORRECTED YAHOO TICKER MAPPINGS")
print("=" * 80)

# Example corrected Yahoo Finance tickers for Estonian/European stocks
CORRECTED_TICKERS = {
    "EFT1T": "EFT1T.TL",  # Tallinn Stock Exchange
    "LHV1T": "LHV1T.TL",  # Tallinn Stock Exchange
    "SAB1L": "SAB1L.HE",  # Helsinki Stock Exchange
    "IGN1L": "IGN1L.HE",  # Helsinki Stock Exchange
    "NES1V": "NES1V.HE",  # Helsinki Stock Exchange
    "IWDA-NA": "IWDA.AS",  # Amsterdam Euronext
    "HAUTO-NO": "HAUTO.OL",  # Oslo Stock Exchange
}

print("\nThese are example corrected tickers. In practice, you would provide these")
print("based on which exchange the stock trades on:\n")
for orig, corrected in CORRECTED_TICKERS.items():
    print(f"  {orig:<15} → {corrected}")

print("\n" + "=" * 80)
print("UPDATING METADATA (Example: IWDA-NA → IWDA.AS)")
print("=" * 80)

# Find IWDA-NA security
iwda_security_id = None
with db_session() as session:
    stmt = select(Security).where(Security.ticker == "IWDA-NA")
    iwda_security = session.execute(stmt).scalar_one_or_none()
    if iwda_security:
        iwda_security_id = iwda_security.id
        print("\nBefore update:")
        print(f"  Ticker: {iwda_security.ticker}")
        print(f"  Name: {iwda_security.name}")

if iwda_security_id:

    # Update with corrected Yahoo ticker
    print("\nUpdating with Yahoo ticker: IWDA.AS...")
    success = service.update_security_metadata(iwda_security_id, "IWDA.AS")

    if success:
        # Read updated data
        with db_session() as session:
            stmt = (
                select(Security, Stock)  # type: ignore[assignment]
                .outerjoin(Stock, Security.id == Stock.security_id)
                .where(Security.id == iwda_security_id)
            )
            result = session.execute(stmt).one()
            security, stock = result

            print("\n✅ After update:")
            print(f"  Ticker: {security.ticker}")
            print(f"  Name: {security.name}")
            print(f"  Exchange: {stock.exchange if stock else 'N/A'}")
else:
    print("\nIWDA-NA security not found in database")

print("\n" + "=" * 80)
print("HOW TO USE THIS IN PRACTICE")
print("=" * 80)

print(
    """
1. After importing, run: service.get_securities_needing_enrichment()
2. For each security that failed enrichment, determine the correct Yahoo ticker
3. Update metadata: service.update_security_metadata(security_id, corrected_ticker)
4. The system will fetch from Yahoo and ALWAYS overwrite the name and exchange

Example usage:

    from src.services.import_service import ImportService

    service = ImportService()

    # Get securities needing enrichment
    securities = service.get_securities_needing_enrichment()

    # Update specific security with corrected Yahoo ticker
    service.update_security_metadata(
        security_id="abc-123",
        yahoo_ticker="IWDA.AS"  # Corrected ticker
    )

    # Or update without changing ticker (retry with current ticker)
    service.update_security_metadata(security_id="abc-123")
"""
)
