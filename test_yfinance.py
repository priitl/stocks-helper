"""
Test script to verify yfinance installation and connectivity.

Tests:
1. Import yfinance
2. Fetch single data point (1 day)
3. Fetch historical data (6 months)
4. Test the new market_data_fetcher implementation

Usage:
    python test_yfinance.py [TICKER]

Example:
    python test_yfinance.py AAPL
"""

import asyncio
import sys
from datetime import datetime


def test_yfinance_import():
    """Test if yfinance is installed."""
    print("=" * 60)
    print("TEST 1: Importing yfinance")
    print("=" * 60)

    try:
        import yfinance as yf
        print("✓ yfinance imported successfully")
        print(f"  Version: {yf.__version__ if hasattr(yf, '__version__') else 'unknown'}")
        return True
    except ImportError as e:
        print(f"✗ Failed to import yfinance: {e}")
        print("\nInstall with: pip install yfinance")
        return False


def test_yfinance_single_day(ticker: str = "AAPL"):
    """Test fetching single day data."""
    print("\n" + "=" * 60)
    print(f"TEST 2: Fetching 1 day data for {ticker}")
    print("=" * 60)

    try:
        import yfinance as yf

        print(f"Fetching {ticker} data (period=1d)...")
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")

        if hist.empty:
            print(f"✗ No data returned for {ticker}")
            return False

        print(f"✓ Successfully fetched {len(hist)} row(s)")
        print("\nData preview:")
        print(hist)

        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        print(f"  Error type: {type(e).__name__}")
        return False


def test_yfinance_historical(ticker: str = "AAPL"):
    """Test fetching historical data (6 months)."""
    print("\n" + "=" * 60)
    print(f"TEST 3: Fetching 6 months data for {ticker}")
    print("=" * 60)

    try:
        import yfinance as yf

        print(f"Fetching {ticker} data (period=6mo)...")
        stock = yf.Ticker(ticker)
        hist = stock.history(period="6mo")

        if hist.empty:
            print(f"✗ No data returned for {ticker}")
            return False

        print(f"✓ Successfully fetched {len(hist)} rows")
        print(f"  Date range: {hist.index[0].strftime('%Y-%m-%d')} to {hist.index[-1].strftime('%Y-%m-%d')}")
        print(f"  Columns: {', '.join(hist.columns)}")

        print("\nFirst 3 rows:")
        print(hist.head(3))

        print("\nLast 3 rows:")
        print(hist.tail(3))

        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        print(f"  Error type: {type(e).__name__}")

        # Check for specific curl errors
        error_str = str(e)
        if "curl" in error_str.lower():
            print("\n⚠️  CURL ERROR DETECTED")
            print("  This usually means:")
            print("  - Firewall/VPN blocking Yahoo Finance")
            print("  - Network proxy configuration issues")
            print("  - Corporate network restrictions")
            print("\n  Recommendation: Use Alpha Vantage instead")

        return False


async def test_market_data_fetcher(ticker: str = "AAPL"):
    """Test our MarketDataFetcher implementation."""
    print("\n" + "=" * 60)
    print(f"TEST 4: Testing MarketDataFetcher._fetch_yahoo_finance()")
    print("=" * 60)

    try:
        from src.services.market_data_fetcher import MarketDataFetcher

        fetcher = MarketDataFetcher()

        print(f"Fetching {ticker} via MarketDataFetcher...")
        data = await fetcher._fetch_yahoo_finance(ticker)

        if not data:
            print("✗ No data returned")
            return False

        if "historical" in data:
            historical = data["historical"]
            latest = data["latest"]

            print(f"✓ Successfully fetched historical data")
            print(f"  Total data points: {len(historical)}")
            print(f"  Latest date: {latest['timestamp']}")
            print(f"  Latest close: ${latest['close']:.2f}")
            print(f"  Source: {latest['source']}")

            print("\nFirst 3 data points:")
            for i, dp in enumerate(historical[:3]):
                print(f"  {dp['timestamp']}: ${dp['close']:.2f}")

            print("\nLast 3 data points:")
            for i, dp in enumerate(historical[-3:]):
                print(f"  {dp['timestamp']}: ${dp['close']:.2f}")

            return True
        else:
            # Old format (single data point)
            print(f"✓ Fetched single data point")
            print(f"  Date: {data['timestamp']}")
            print(f"  Close: ${data['close']:.2f}")
            return True

    except Exception as e:
        print(f"✗ Error: {e}")
        print(f"  Error type: {type(e).__name__}")

        import traceback
        print("\nFull traceback:")
        traceback.print_exc()

        return False


def main():
    """Run all tests."""
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    print(f"\n{'='*60}")
    print(f"YFINANCE CONNECTIVITY TEST - {ticker}")
    print(f"{'='*60}\n")

    results = []

    # Test 1: Import
    if test_yfinance_import():
        results.append(("Import", True))

        # Test 2: Single day
        result = test_yfinance_single_day(ticker)
        results.append(("Single day fetch", result))

        # Test 3: Historical
        result = test_yfinance_historical(ticker)
        results.append(("Historical fetch (6mo)", result))

        # Test 4: MarketDataFetcher
        result = asyncio.run(test_market_data_fetcher(ticker))
        results.append(("MarketDataFetcher", result))
    else:
        results.append(("Import", False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status:8} - {test_name}")

    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)

    print(f"\nTotal: {passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n🎉 All tests passed! yfinance is working correctly.")
        print("   Historical data fetching will work as fallback.")
    elif passed_count > 0:
        print("\n⚠️  Some tests failed. Check errors above.")
        if any("Single day" in name for name, passed in results if not passed):
            print("   Recommendation: Use Alpha Vantage instead of Yahoo Finance")
    else:
        print("\n❌ All tests failed. yfinance cannot be used in this environment.")
        print("   Recommendation: Use Alpha Vantage for market data")

    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    sys.exit(main())
