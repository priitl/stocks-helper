"""Unit tests for MarketDataFetcher."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.market_data_fetcher import MarketDataFetcher


@pytest.fixture
def market_data_fetcher():
    """Provide MarketDataFetcher instance."""
    with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "test_key"}):
        fetcher = MarketDataFetcher()
        # Reset quota tracker for each test
        fetcher.quota_tracker.reset()
        return fetcher


@pytest.fixture
def mock_alpha_vantage_response():
    """Provide mock Alpha Vantage API response."""
    return {
        "Meta Data": {
            "1. Information": "Daily Prices",
            "2. Symbol": "AAPL",
        },
        "Time Series (Daily)": {
            "2025-10-05": {
                "1. open": "150.00",
                "2. high": "155.00",
                "3. low": "149.00",
                "4. close": "154.00",
                "5. volume": "75000000",
            },
            "2025-10-04": {
                "1. open": "148.00",
                "2. high": "152.00",
                "3. low": "147.00",
                "4. close": "150.00",
                "5. volume": "70000000",
            },
        },
    }


@pytest.fixture
def mock_yahoo_history():
    """Provide mock Yahoo Finance history DataFrame."""
    import pandas as pd

    data = {
        "Open": [150.25, 148.50],
        "High": [155.10, 152.30],
        "Low": [149.85, 147.90],
        "Close": [154.50, 150.00],
        "Volume": [75234567, 68912345],
    }

    dates = pd.date_range(end=datetime.now(), periods=2, freq="D")
    return pd.DataFrame(data, index=dates)


@pytest.mark.unit
class TestMarketDataFetcher:
    """Test suite for MarketDataFetcher."""

    @pytest.mark.asyncio
    async def test_fetch_daily_data_yahoo_finance_success(
        self, market_data_fetcher, mock_yahoo_history
    ):
        """Fetch daily data successfully from Yahoo Finance (primary source)."""
        with (
            patch("yfinance.Ticker") as mock_ticker,
            patch.object(market_data_fetcher.cache, "get", return_value=None),
        ):
            mock_ticker.return_value.history.return_value = mock_yahoo_history

            result = await market_data_fetcher.fetch_daily_data("AAPL")

            assert result is not None
            assert "historical" in result
            assert "latest" in result
            assert len(result["historical"]) == 2
            assert result["latest"]["ticker"] == "AAPL"
            assert result["latest"]["source"] == "yahoo_finance"

    @pytest.mark.asyncio
    async def test_fetch_daily_data_fallback_to_alpha_vantage(
        self, market_data_fetcher, mock_alpha_vantage_response
    ):
        """Fallback to Alpha Vantage when Yahoo Finance fails."""
        with (
            patch("yfinance.Ticker") as mock_yf,
            patch.object(market_data_fetcher.api_client, "get", new_callable=AsyncMock) as mock_get,
            patch.object(market_data_fetcher.cache, "get", return_value=None),
        ):
            # Yahoo Finance fails
            mock_yf.return_value.history.side_effect = Exception("Yahoo unavailable")

            # Alpha Vantage succeeds
            mock_get.return_value = mock_alpha_vantage_response

            result = await market_data_fetcher.fetch_daily_data("AAPL")

            # Should have fallen back to Alpha Vantage
            assert result is not None
            assert "historical" in result
            assert result["latest"]["source"] == "alpha_vantage"

    @pytest.mark.asyncio
    async def test_fetch_daily_data_all_sources_fail(self, market_data_fetcher):
        """Return None when all data sources fail."""
        with (
            patch("yfinance.Ticker") as mock_yf,
            patch.object(market_data_fetcher.api_client, "get", new_callable=AsyncMock) as mock_av,
        ):
            # Both sources fail
            mock_yf.return_value.history.side_effect = Exception("Yahoo failed")
            mock_av.side_effect = Exception("Alpha Vantage failed")

            result = await market_data_fetcher.fetch_daily_data("INVALID")

            # Should return None when all sources fail
            assert result is None

    @pytest.mark.asyncio
    async def test_alpha_vantage_quota_check(self, market_data_fetcher):
        """Alpha Vantage respects quota limits."""
        with (
            patch.object(market_data_fetcher.quota_tracker, "can_make_request") as mock_quota,
            patch.object(market_data_fetcher.cache, "get", return_value=None),
        ):
            mock_quota.return_value = False

            # Should return None without making request
            result = await market_data_fetcher._fetch_alpha_vantage("AAPL")

            assert result is None

    @pytest.mark.asyncio
    async def test_alpha_vantage_quota_tracking(
        self, market_data_fetcher, mock_alpha_vantage_response
    ):
        """Alpha Vantage quota counter increments after successful request."""
        with (
            patch.object(market_data_fetcher.api_client, "get", new_callable=AsyncMock) as mock_get,
            patch.object(market_data_fetcher.quota_tracker, "record_request") as mock_record,
            patch.object(market_data_fetcher.cache, "get", return_value=None),
        ):
            mock_get.return_value = mock_alpha_vantage_response

            await market_data_fetcher._fetch_alpha_vantage("AAPL")

            # Quota should have been recorded
            mock_record.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_hit_alpha_vantage(self, market_data_fetcher):
        """Cached Alpha Vantage data is returned without making API call."""
        cached_data = {
            "ticker": "AAPL",
            "close": 150.0,
            "is_latest": True,
            "source": "alpha_vantage",
        }

        with (
            patch.object(market_data_fetcher.cache, "get", return_value=cached_data),
            patch.object(market_data_fetcher.api_client, "get", new_callable=AsyncMock) as mock_get,
        ):
            result = await market_data_fetcher._fetch_alpha_vantage("AAPL")

            # Should return cached data without API call
            assert result == cached_data
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_hit_yahoo_finance(self, market_data_fetcher):
        """Cached Yahoo Finance data is returned without making API call."""
        cached_data = {
            "ticker": "AAPL",
            "close": 150.0,
            "is_latest": True,
            "source": "yahoo_finance",
        }

        with (
            patch.object(market_data_fetcher.cache, "get", return_value=cached_data),
            patch("yfinance.Ticker") as mock_yf,
        ):
            result = await market_data_fetcher._fetch_yahoo_finance("AAPL")

            # Should return cached data without API call
            assert result == cached_data
            mock_yf.assert_not_called()

    @pytest.mark.asyncio
    async def test_alpha_vantage_error_handling(self, market_data_fetcher):
        """Alpha Vantage API errors are handled gracefully."""
        error_response = {"Error Message": "Invalid API key"}

        with (
            patch.object(market_data_fetcher.api_client, "get", new_callable=AsyncMock) as mock_get,
            patch.object(market_data_fetcher.cache, "get", return_value=None),
        ):
            mock_get.return_value = error_response

            result = await market_data_fetcher._fetch_alpha_vantage("AAPL")

            # Should return None on error
            assert result is None

    @pytest.mark.asyncio
    async def test_alpha_vantage_rate_limit_response(self, market_data_fetcher):
        """Alpha Vantage rate limit response is handled."""
        rate_limit_response = {"Note": "API call frequency is too high"}

        with (
            patch.object(market_data_fetcher.api_client, "get", new_callable=AsyncMock) as mock_get,
            patch.object(market_data_fetcher.cache, "get", return_value=None),
        ):
            mock_get.return_value = rate_limit_response

            result = await market_data_fetcher._fetch_alpha_vantage("AAPL")

            # Should return None on rate limit
            assert result is None

    @pytest.mark.asyncio
    async def test_yahoo_finance_empty_data(self, market_data_fetcher):
        """Yahoo Finance empty DataFrame is handled gracefully."""
        import pandas as pd

        with patch("yfinance.Ticker") as mock_yf:
            mock_yf.return_value.history.return_value = pd.DataFrame()

            result = await market_data_fetcher._fetch_yahoo_finance("INVALID")

            assert result is None

    @pytest.mark.asyncio
    @patch("src.services.market_data_fetcher.db_session")
    async def test_update_market_data_with_historical(
        self, mock_db, market_data_fetcher, mock_alpha_vantage_response
    ):
        """Market data with historical data is stored in database."""
        mock_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_session
        # Mock query to return None (no existing data)
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with (
            patch.object(market_data_fetcher.api_client, "get", new_callable=AsyncMock) as mock_get,
            patch.object(market_data_fetcher.cache, "get", return_value=None),
            patch("yfinance.Ticker") as mock_yf,
        ):
            mock_get.return_value = mock_alpha_vantage_response
            # Mock Yahoo Finance to fail so Alpha Vantage is used
            mock_yf.return_value.history.side_effect = Exception("Yahoo failed")

            result = await market_data_fetcher.update_market_data("AAPL")

            assert result is True
            # Should have added data to session
            assert mock_session.add.call_count > 0

    @pytest.mark.asyncio
    @patch("src.services.market_data_fetcher.db_session")
    async def test_update_market_data_no_data(self, mock_db, market_data_fetcher):
        """Update operation handles missing data gracefully."""
        with (
            patch("yfinance.Ticker") as mock_yf,
            patch.object(market_data_fetcher.api_client, "get", new_callable=AsyncMock) as mock_av,
        ):
            mock_yf.return_value.history.side_effect = Exception("Failed")
            mock_av.side_effect = Exception("Failed")

            result = await market_data_fetcher.update_market_data("INVALID")

            # Should return False when no data available
            assert result is False

    def test_quota_tracker_interface(self, market_data_fetcher):
        """QuotaTracker has expected interface."""
        assert hasattr(market_data_fetcher.quota_tracker, "can_make_request")
        assert hasattr(market_data_fetcher.quota_tracker, "record_request")
        assert hasattr(market_data_fetcher.quota_tracker, "get_remaining_quota")
        assert hasattr(market_data_fetcher.quota_tracker, "reset")

    def test_get_remaining_quota(self, market_data_fetcher):
        """Get remaining quota returns expected format."""
        quota = market_data_fetcher.quota_tracker.get_remaining_quota()

        assert isinstance(quota, dict)
        assert "api_name" in quota
        assert "daily_used" in quota
        assert "daily_limit" in quota
        assert "daily_remaining" in quota

    @pytest.mark.asyncio
    async def test_batch_update_rate_limiting(self, market_data_fetcher, mock_yahoo_history):
        """Batch update respects rate limiting between requests."""
        with (
            patch("yfinance.Ticker") as mock_yf,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_yf.return_value.history.return_value = mock_yahoo_history

            tickers = ["AAPL", "GOOGL", "MSFT"]
            await market_data_fetcher.batch_update(tickers)

            # Should have enforced rate limiting between requests
            # (sleep called between tickers, not after last one)
            assert mock_sleep.call_count == len(tickers) - 1

    @pytest.mark.asyncio
    async def test_data_source_preference_order(self, market_data_fetcher, mock_yahoo_history):
        """Yahoo Finance is tried first (preferred), then Alpha Vantage."""
        with (
            patch("yfinance.Ticker") as mock_yf,
            patch.object(market_data_fetcher.cache, "get", return_value=None),
        ):
            mock_yf.return_value.history.return_value = mock_yahoo_history

            result = await market_data_fetcher.fetch_daily_data("AAPL")

            # Yahoo should be tried first (and succeed)
            assert result is not None
            assert result["latest"]["source"] == "yahoo_finance"
            # Alpha Vantage should not be called if Yahoo succeeds
            assert market_data_fetcher.quota_tracker.get_remaining_quota()["daily_used"] == 0

    @pytest.mark.asyncio
    async def test_alpha_vantage_without_api_key(self):
        """Alpha Vantage gracefully handles missing API key."""
        with patch.dict("os.environ", {}, clear=True):
            fetcher = MarketDataFetcher()
            result = await fetcher._fetch_alpha_vantage("AAPL")

            assert result is None

    @pytest.mark.asyncio
    async def test_fallback_to_cache(self, market_data_fetcher):
        """Falls back to cache when all APIs fail."""
        cached_data = {
            "ticker": "AAPL",
            "close": 150.0,
            "source": "cache",
        }

        with (
            patch("yfinance.Ticker") as mock_yf,
            patch.object(market_data_fetcher.api_client, "get", new_callable=AsyncMock) as mock_av,
            patch.object(market_data_fetcher.cache, "get") as mock_cache,
        ):
            # All APIs fail
            mock_yf.return_value.history.side_effect = Exception("Yahoo failed")
            mock_av.side_effect = Exception("AV failed")

            # Cache succeeds (third get call is for fallback cache)
            def cache_side_effect(category, ticker, ttl_minutes=None):
                if ttl_minutes == 1440:  # Fallback cache
                    return cached_data
                return None

            mock_cache.side_effect = cache_side_effect

            result = await market_data_fetcher.fetch_daily_data("AAPL")

            # Should return cached data
            assert result == cached_data

    @pytest.mark.asyncio
    async def test_alpha_vantage_parses_all_historical_data(
        self, market_data_fetcher, mock_alpha_vantage_response
    ):
        """Alpha Vantage returns all historical data points."""
        with (
            patch.object(market_data_fetcher.api_client, "get", new_callable=AsyncMock) as mock_get,
            patch.object(market_data_fetcher.cache, "get", return_value=None),
        ):
            mock_get.return_value = mock_alpha_vantage_response

            result = await market_data_fetcher._fetch_alpha_vantage("AAPL")

            assert result is not None
            assert "historical" in result
            assert len(result["historical"]) == 2
            # Latest should be marked
            latest_items = [item for item in result["historical"] if item["is_latest"]]
            assert len(latest_items) == 1
            assert latest_items[0]["timestamp"] == "2025-10-05"

    def test_get_current_price_from_bulk(self, market_data_fetcher):
        """Get current price uses bulk fetch with caching."""
        # Mock get_current_prices to return a known value
        with patch.object(market_data_fetcher, "get_current_prices") as mock_bulk:
            mock_bulk.return_value = {"AAPL": 154.50}

            price = market_data_fetcher.get_current_price("AAPL")

            assert price == 154.50
            mock_bulk.assert_called_once_with(["AAPL"])

    def test_get_current_price_not_found(self, market_data_fetcher):
        """Get current price returns None when ticker not found."""
        # Mock get_current_prices to return empty dict
        with patch.object(market_data_fetcher, "get_current_prices") as mock_bulk:
            mock_bulk.return_value = {}

            price = market_data_fetcher.get_current_price("INVALID")

            assert price is None
            mock_bulk.assert_called_once_with(["INVALID"])
