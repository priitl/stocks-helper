"""
Helper script to fetch historical market data for all holdings.

This is useful when:
1. You just set your ALPHA_VANTAGE_API_KEY
2. You need to populate historical data for technical analysis
3. Yahoo Finance is blocked/failing

Usage:
    export ALPHA_VANTAGE_API_KEY="your-key-here"
    python fetch_historical_data.py <portfolio-id>
"""

import asyncio
import sys

from src.lib.db import get_session
from src.models.holding import Holding
from src.services.market_data_fetcher import MarketDataFetcher


async def fetch_all_historical(portfolio_id: str) -> None:
    """Fetch historical data for all holdings in a portfolio."""
    session = get_session()

    try:
        # Get all holdings
        holdings = (
            session.query(Holding)
            .filter(Holding.portfolio_id == portfolio_id, Holding.quantity > 0)
            .all()
        )

        if not holdings:
            print(f"No holdings found in portfolio {portfolio_id}")
            return

        tickers = list(set(h.ticker for h in holdings))
        print(f"Fetching historical data for {len(tickers)} stocks...")

        fetcher = MarketDataFetcher()

        for i, ticker in enumerate(tickers):
            print(f"\n[{i+1}/{len(tickers)}] Fetching {ticker}...")

            success = await fetcher.update_market_data(ticker)

            if success:
                print(f"✓ {ticker}: Historical data stored")
            else:
                print(f"✗ {ticker}: Failed to fetch data")

            # Rate limiting (Alpha Vantage allows 5 req/min on free tier)
            if i < len(tickers) - 1:
                print("Waiting 15 seconds (rate limiting)...")
                await asyncio.sleep(15)

        print("\n" + "=" * 60)
        print("✅ Historical data fetch complete!")
        print("=" * 60)
        print("\nYou can now get technical analysis:")
        print(f"  stocks-helper recommendation refresh {portfolio_id}")

    finally:
        session.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        print("\nError: Portfolio ID required")
        print("Usage: python fetch_historical_data.py <portfolio-id>")
        sys.exit(1)

    portfolio_id = sys.argv[1]
    asyncio.run(fetch_all_historical(portfolio_id))
