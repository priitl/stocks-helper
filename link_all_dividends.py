#!/usr/bin/env python3
"""
Link all unlinked dividend/interest transactions to holdings by ISIN.

This script processes all unlinked DIVIDEND and INTEREST transactions,
extracts ISINs from their notes, and links them to the correct holdings.
"""

from src.services.import_service import ImportService


def main():
    """Link all unlinked dividends/interest to holdings."""
    print("Linking dividends/interest to holdings by ISIN...")
    print("=" * 60)

    service = ImportService()

    # Link all dividends/interest (no security_id filter = process all)
    linked_count = service.link_dividends_to_holdings()

    if linked_count > 0:
        print(f"\n✅ Successfully linked {linked_count} dividend/interest transaction(s)")
    else:
        print("\n⚠️  No unlinked dividends/interest found, or no securities have ISINs set")

    print("\n" + "=" * 60)
    print("Complete!")


if __name__ == "__main__":
    main()
