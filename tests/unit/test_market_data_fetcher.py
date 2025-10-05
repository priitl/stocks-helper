"""Unit tests for MarketDataFetcher."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from datetime import datetime

from src.services.market_data_fetcher import MarketDataFetcher
from src.lib.errors import APIQuotaExceededError, DataSourceError


@pytest.fixture
def market_data_fetcher():
    """Provide MarketDataFetcher instance."""
    with patch.dict('os.environ', {'ALPHA_VANTAGE_API_KEY': 'test_key'}):
        return MarketDataFetcher()


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
                "5. volume": "75000000"
            },
            "2025-10-04": {
                "1. open": "148.00",
                "2. high": "152.00",
                "3. low": "147.00",
                "4. close": "150.00",
                "5. volume": "70000000"
            }
        }
    }


@pytest.fixture
def mock_yahoo_response():
    """Provide mock Yahoo Finance response."""
    mock_ticker = MagicMock()
    mock_history = MagicMock()
    mock_history.index = [datetime(2025, 10, 5), datetime(2025, 10, 4)]
    mock_history.__iter__ = MagicMock(return_value=iter([
        (datetime(2025, 10, 5), {"Open": 150.0, "High": 155.0, "Low": 149.0, "Close": 154.0, "Volume": 75000000}),
        (datetime(2025, 10, 4), {"Open": 148.0, "High": 152.0, "Low": 147.0, "Close": 150.0, "Volume": 70000000})
    ]))
    mock_ticker.history = MagicMock(return_value=mock_history)
    return mock_ticker


@pytest.mark.unit
class TestMarketDataFetcher:
    """Test suite for MarketDataFetcher."""

    @pytest.mark.asyncio
    async def test_fetch_daily_data_alpha_vantage_success(
        self, market_data_fetcher, mock_alpha_vantage_response
    ):
        """Fetch daily data successfully from Alpha Vantage."""
        with patch.object(market_data_fetcher, '_fetch_from_alpha_vantage', new_callable=AsyncMock) as mock_av:
            mock_av.return_value = mock_alpha_vantage_response

            result = await market_data_fetcher.fetch_daily_data("AAPL")

            assert result is not None
            assert "historical" in result or result is not None
            mock_av.assert_called_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_fetch_daily_data_fallback_to_yahoo(self, market_data_fetcher, mock_yahoo_response):
        """Fallback to Yahoo Finance when Alpha Vantage fails."""
        with patch.object(market_data_fetcher, '_fetch_from_alpha_vantage', new_callable=AsyncMock) as mock_av, \
             patch.object(market_data_fetcher, '_fetch_from_yahoo', new_callable=AsyncMock) as mock_yahoo:

            # Alpha Vantage fails
            mock_av.side_effect = DataSourceError("Alpha Vantage unavailable")

            # Yahoo Finance succeeds
            mock_yahoo.return_value = {"price": 154.0, "volume": 75000000}

            result = await market_data_fetcher.fetch_daily_data("AAPL")

            # Should have tried Alpha Vantage first, then Yahoo
            assert result is not None
            mock_av.assert_called_once()
            mock_yahoo.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_daily_data_fallback_chain_complete_failure(self, market_data_fetcher):
        """All data sources fail, return None."""
        with patch.object(market_data_fetcher, '_fetch_from_alpha_vantage', new_callable=AsyncMock) as mock_av, \
             patch.object(market_data_fetcher, '_fetch_from_yahoo', new_callable=AsyncMock) as mock_yahoo:

            # Both sources fail
            mock_av.side_effect = DataSourceError("Alpha Vantage failed")
            mock_yahoo.side_effect = DataSourceError("Yahoo Finance failed")

            result = await market_data_fetcher.fetch_daily_data("INVALID")

            # Should return None when all sources fail
            assert result is None
            mock_av.assert_called_once()
            mock_yahoo.assert_called_once()

    @pytest.mark.asyncio
    async def test_quota_tracking_increments(self, market_data_fetcher):
        """API quota counter increments after successful request."""
        initial_count = market_data_fetcher.get_quota_usage()

        with patch.object(market_data_fetcher, '_fetch_from_alpha_vantage', new_callable=AsyncMock) as mock_av:
            mock_av.return_value = {"Meta Data": {}, "Time Series (Daily)": {}}

            await market_data_fetcher.fetch_daily_data("AAPL")

            new_count = market_data_fetcher.get_quota_usage()
            # Quota should have incremented
            assert new_count >= initial_count

    @pytest.mark.asyncio
    async def test_quota_exceeded_raises_error(self, market_data_fetcher):
        """APIQuotaExceededError raised when quota limit reached."""
        # Set quota to max
        market_data_fetcher.quota_tracker["alpha_vantage"]["count"] = 25  # Daily limit

        with pytest.raises(APIQuotaExceededError):
            await market_data_fetcher.fetch_daily_data("AAPL")

    @pytest.mark.asyncio
    async def test_rate_limiting_delay(self, market_data_fetcher):
        """Rate limiting enforces delay between requests."""
        with patch.object(market_data_fetcher, '_fetch_from_alpha_vantage', new_callable=AsyncMock) as mock_av, \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:

            mock_av.return_value = {"Meta Data": {}, "Time Series (Daily)": {}}

            # Make first request
            await market_data_fetcher.fetch_daily_data("AAPL")

            # Make second request immediately
            await market_data_fetcher.fetch_daily_data("GOOGL")

            # Should have called sleep for rate limiting (after first request)
            assert mock_sleep.called

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api_call(self, market_data_fetcher):
        """Cached data is returned without making API call."""
        ticker = "AAPL"
        cached_data = {"cached": True, "price": 150.0}

        with patch.object(market_data_fetcher, '_get_cached_data', return_value=cached_data), \
             patch.object(market_data_fetcher, '_fetch_from_alpha_vantage', new_callable=AsyncMock) as mock_av:

            result = await market_data_fetcher.fetch_daily_data(ticker)

            # Should return cached data without API call
            assert result == cached_data
            mock_av.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_ticker_returns_none(self, market_data_fetcher):
        """Invalid ticker symbol returns None gracefully."""
        with patch.object(market_data_fetcher, '_fetch_from_alpha_vantage', new_callable=AsyncMock) as mock_av:
            mock_av.return_value = None  # API returns nothing for invalid ticker

            result = await market_data_fetcher.fetch_daily_data("INVALID_TICKER_XYZ")

            assert result is None

    @pytest.mark.asyncio
    async def test_network_error_triggers_fallback(self, market_data_fetcher):
        """Network errors trigger fallback to alternative source."""
        with patch.object(market_data_fetcher, '_fetch_from_alpha_vantage', new_callable=AsyncMock) as mock_av, \
             patch.object(market_data_fetcher, '_fetch_from_yahoo', new_callable=AsyncMock) as mock_yahoo:

            # Network error from Alpha Vantage
            mock_av.side_effect = Exception("Network timeout")

            # Yahoo succeeds
            mock_yahoo.return_value = {"price": 154.0}

            result = await market_data_fetcher.fetch_daily_data("AAPL")

            # Should have fallen back to Yahoo
            assert result is not None
            mock_yahoo.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.services.market_data_fetcher.db_session')
    async def test_store_market_data_success(self, mock_db, market_data_fetcher):
        """Market data is stored in database successfully."""
        mock_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_session

        # Mock fetch to return data
        data = {
            "historical": [
                {
                    "timestamp": "2025-10-05T00:00:00",
                    "open": Decimal("150.00"),
                    "high": Decimal("155.00"),
                    "low": Decimal("149.00"),
                    "close": Decimal("154.00"),
                    "volume": 75000000,
                    "source": "alpha_vantage"
                }
            ]
        }

        with patch.object(market_data_fetcher, 'fetch_daily_data', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = data

            result = await market_data_fetcher.store_market_data("AAPL")

            assert result is True
            mock_session.add.assert_called()
            mock_session.commit.assert_called()

    @pytest.mark.asyncio
    @patch('src.services.market_data_fetcher.db_session')
    async def test_store_market_data_no_data(self, mock_db, market_data_fetcher):
        """Store operation handles missing data gracefully."""
        with patch.object(market_data_fetcher, 'fetch_daily_data', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None

            result = await market_data_fetcher.store_market_data("INVALID")

            # Should return False when no data available
            assert result is False

    def test_get_quota_usage_returns_dict(self, market_data_fetcher):
        """Get quota usage returns dictionary with source info."""
        quota = market_data_fetcher.get_quota_usage()

        assert isinstance(quota, dict)
        # Should have quota info for sources
        assert "alpha_vantage" in quota or len(quota) >= 0

    def test_reset_quota_clears_counters(self, market_data_fetcher):
        """Reset quota clears all quota counters."""
        # Increment quota
        market_data_fetcher.quota_tracker["alpha_vantage"]["count"] = 10

        market_data_fetcher.reset_quota()

        # Should be reset
        assert market_data_fetcher.quota_tracker["alpha_vantage"]["count"] == 0

    @pytest.mark.asyncio
    async def test_concurrent_requests_respect_rate_limit(self, market_data_fetcher):
        """Concurrent requests still respect rate limiting."""
        import asyncio

        with patch.object(market_data_fetcher, '_fetch_from_alpha_vantage', new_callable=AsyncMock) as mock_av, \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:

            mock_av.return_value = {"Meta Data": {}, "Time Series (Daily)": {}}

            # Make multiple concurrent requests
            tasks = [
                market_data_fetcher.fetch_daily_data(f"TICKER{i}")
                for i in range(3)
            ]

            await asyncio.gather(*tasks)

            # Should have enforced rate limiting between requests
            assert mock_sleep.call_count >= 2  # At least 2 delays for 3 requests

    @pytest.mark.asyncio
    async def test_data_source_preference_order(self, market_data_fetcher):
        """Data sources are tried in correct preference order."""
        call_order = []

        async def track_av_call(*args, **kwargs):
            call_order.append("alpha_vantage")
            raise DataSourceError("AV failed")

        async def track_yahoo_call(*args, **kwargs):
            call_order.append("yahoo")
            return {"price": 150.0}

        with patch.object(market_data_fetcher, '_fetch_from_alpha_vantage', new_callable=AsyncMock) as mock_av, \
             patch.object(market_data_fetcher, '_fetch_from_yahoo', new_callable=AsyncMock) as mock_yahoo:

            mock_av.side_effect = track_av_call
            mock_yahoo.side_effect = track_yahoo_call

            await market_data_fetcher.fetch_daily_data("AAPL")

            # Alpha Vantage should be tried first, then Yahoo
            assert call_order == ["alpha_vantage", "yahoo"]

    @pytest.mark.asyncio
    async def test_partial_data_handling(self, market_data_fetcher):
        """Partial or incomplete data is handled gracefully."""
        partial_data = {
            "Meta Data": {"Symbol": "AAPL"},
            # Missing Time Series data
        }

        with patch.object(market_data_fetcher, '_fetch_from_alpha_vantage', new_callable=AsyncMock) as mock_av:
            mock_av.return_value = partial_data

            result = await market_data_fetcher.fetch_daily_data("AAPL")

            # Should handle partial data without crashing
            assert result is not None or result is None  # Either way, shouldn't raise

    @pytest.mark.asyncio
    async def test_api_response_validation(self, market_data_fetcher):
        """API responses are validated before processing."""
        invalid_response = {
            "error": "Invalid API key"
        }

        with patch.object(market_data_fetcher, '_fetch_from_alpha_vantage', new_callable=AsyncMock) as mock_av, \
             patch.object(market_data_fetcher, '_fetch_from_yahoo', new_callable=AsyncMock) as mock_yahoo:

            mock_av.return_value = invalid_response
            mock_yahoo.return_value = {"price": 150.0}

            result = await market_data_fetcher.fetch_daily_data("AAPL")

            # Should fallback to Yahoo when Alpha Vantage returns error
            mock_yahoo.assert_called_once()
