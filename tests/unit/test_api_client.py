"""Unit tests for APIClient."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from src.lib.api_client import APIClient, APIError, RateLimitError


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Provide temporary cache directory."""
    return tmp_path / "cache"


@pytest.fixture
def api_client(temp_cache_dir):
    """Provide APIClient instance with temp cache."""
    return APIClient(
        base_url="https://api.example.com",
        cache_dir=temp_cache_dir,
        default_timeout=10,
        max_retries=3,
    )


@pytest.mark.asyncio
class TestAPIClient:
    """Test suite for APIClient."""

    async def test_init_creates_cache_dir(self, temp_cache_dir):
        """Cache directory is created on init."""
        APIClient(base_url="https://api.example.com", cache_dir=temp_cache_dir)
        assert temp_cache_dir.exists()

    async def test_context_manager_creates_session(self, api_client):
        """Session is created when entering context."""
        assert api_client.session is None

        async with api_client as client:
            assert client.session is not None
            assert isinstance(client.session, aiohttp.ClientSession)

    async def test_context_manager_closes_session(self, api_client):
        """Session is closed when exiting context."""
        async with api_client as client:
            session = client.session

        # Session should be closed
        assert session.closed

    async def test_get_success(self, api_client):
        """Successful GET request returns data."""
        mock_response = {"status": "ok", "data": [1, 2, 3]}

        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response

            async with api_client:
                result = await api_client.get("/test", use_cache=False)

            assert result == mock_response
            mock_req.assert_called_once()

    async def test_get_with_params(self, api_client):
        """GET request includes query parameters."""
        params = {"symbol": "AAPL", "limit": 10}

        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"data": []}

            async with api_client:
                await api_client.get("/stocks", params=params, use_cache=False)

            # Verify params were passed
            call_args = mock_req.call_args
            assert call_args[0][1] == params

    async def test_get_with_headers(self, api_client):
        """GET request includes custom headers."""
        headers = {"Authorization": "Bearer token123", "X-Custom": "value"}

        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"data": []}

            async with api_client:
                await api_client.get("/test", headers=headers, use_cache=False)

            # Verify headers were passed
            call_args = mock_req.call_args
            assert call_args[0][2] == headers

    async def test_get_uses_cache(self, api_client, temp_cache_dir):
        """GET request uses cached response when available."""
        endpoint = "/test"
        cached_data = {"cached": True, "data": [1, 2, 3]}

        # Create cache file
        cache_key = api_client._make_cache_key(endpoint, None)
        cache_file = temp_cache_dir / f"{cache_key}.json"

        with open(cache_file, "w") as f:
            json.dump(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "endpoint": endpoint,
                    "params": None,
                    "data": cached_data,
                },
                f,
            )

        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_req:
            async with api_client:
                result = await api_client.get(endpoint, use_cache=True)

            # Should use cache, not make request
            assert result == cached_data
            mock_req.assert_not_called()

    async def test_get_ignores_expired_cache(self, api_client, temp_cache_dir):
        """Expired cache is ignored and fresh request is made."""
        endpoint = "/test"
        expired_data = {"cached": True, "old": True}
        fresh_data = {"cached": False, "fresh": True}

        # Create expired cache file (2 hours old)
        cache_key = api_client._make_cache_key(endpoint, None)
        cache_file = temp_cache_dir / f"{cache_key}.json"

        old_timestamp = datetime.now(timezone.utc) - timedelta(hours=2)
        with open(cache_file, "w") as f:
            json.dump(
                {
                    "timestamp": old_timestamp.isoformat(),
                    "endpoint": endpoint,
                    "params": None,
                    "data": expired_data,
                },
                f,
            )

        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = fresh_data

            async with api_client:
                result = await api_client.get(endpoint, use_cache=True, cache_ttl=900)

            # Should ignore cache and make fresh request
            assert result == fresh_data
            mock_req.assert_called_once()

    async def test_retry_on_timeout(self, api_client):
        """Request retries with exponential backoff on timeout."""
        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_req:
            # First two attempts timeout, third succeeds
            mock_req.side_effect = [
                asyncio.TimeoutError(),
                asyncio.TimeoutError(),
                {"data": "success"},
            ]

            async with api_client:
                result = await api_client.get("/test", use_cache=False)

            assert result == {"data": "success"}
            assert mock_req.call_count == 3

    async def test_max_retries_exceeded_timeout(self, api_client):
        """TimeoutError raised after max retries."""
        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = asyncio.TimeoutError()

            async with api_client:
                with pytest.raises(asyncio.TimeoutError):
                    await api_client.get("/test", use_cache=False)

            # Should try max_retries times
            assert mock_req.call_count == api_client.max_retries

    async def test_rate_limit_retry(self, api_client):
        """Request retries on rate limit (429)."""
        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_req:
            # First attempt hits rate limit, second succeeds
            rate_limit_error = aiohttp.ClientResponseError(
                request_info=MagicMock(), history=(), status=429, message="Too Many Requests"
            )
            mock_req.side_effect = [rate_limit_error, {"data": "success"}]

            async with api_client:
                result = await api_client.get("/test", use_cache=False)

            assert result == {"data": "success"}
            assert mock_req.call_count == 2

    async def test_rate_limit_max_retries(self, api_client):
        """RateLimitError raised after max retries on 429."""
        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_req:
            rate_limit_error = aiohttp.ClientResponseError(
                request_info=MagicMock(), history=(), status=429, message="Too Many Requests"
            )
            mock_req.side_effect = rate_limit_error

            async with api_client:
                with pytest.raises(RateLimitError, match="Rate limit exceeded"):
                    await api_client.get("/test", use_cache=False)

            assert mock_req.call_count == api_client.max_retries

    async def test_http_error_no_retry(self, api_client):
        """Non-429 HTTP errors don't retry."""
        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_req:
            http_error = aiohttp.ClientResponseError(
                request_info=MagicMock(), history=(), status=500, message="Internal Server Error"
            )
            mock_req.side_effect = http_error

            async with api_client:
                with pytest.raises(APIError, match="API request failed: 500"):
                    await api_client.get("/test", use_cache=False)

            # Should only try once (no retry on 500)
            assert mock_req.call_count == 1

    async def test_network_error_no_retry(self, api_client):
        """Network errors don't retry."""
        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = aiohttp.ClientError("Connection failed")

            async with api_client:
                with pytest.raises(APIError, match="Network error"):
                    await api_client.get("/test", use_cache=False)

            # Should only try once
            assert mock_req.call_count == 1

    async def test_cache_key_generation(self, api_client):
        """Cache keys are consistent for same endpoint/params."""
        key1 = api_client._make_cache_key("/test", {"a": 1, "b": 2})
        key2 = api_client._make_cache_key("/test", {"b": 2, "a": 1})

        # Same params in different order should produce same key
        assert key1 == key2

        # Different endpoint should produce different key
        key3 = api_client._make_cache_key("/other", {"a": 1, "b": 2})
        assert key1 != key3

    async def test_cache_stores_response(self, api_client, temp_cache_dir):
        """Successful response is cached."""
        endpoint = "/test"
        response_data = {"data": [1, 2, 3]}

        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = response_data

            async with api_client:
                await api_client.get(endpoint, use_cache=True)

            # Verify cache file exists
            cache_key = api_client._make_cache_key(endpoint, None)
            cache_file = temp_cache_dir / f"{cache_key}.json"
            assert cache_file.exists()

            # Verify cache content
            with open(cache_file) as f:
                cached = json.load(f)

            assert cached["data"] == response_data
            assert "timestamp" in cached
            assert cached["endpoint"] == endpoint

    async def test_clear_cache_all(self, api_client, temp_cache_dir):
        """clear_cache removes all cache files."""
        # Create some cache files
        for i in range(3):
            cache_file = temp_cache_dir / f"cache_{i}.json"
            with open(cache_file, "w") as f:
                json.dump(
                    {"timestamp": datetime.now(timezone.utc).isoformat(), "data": {"id": i}}, f
                )

        deleted = api_client.clear_cache()
        assert deleted == 3
        assert len(list(temp_cache_dir.glob("*.json"))) == 0

    async def test_clear_cache_older_than(self, api_client, temp_cache_dir):
        """clear_cache only removes old cache files."""
        # Create old cache
        old_file = temp_cache_dir / "old.json"
        with open(old_file, "w") as f:
            old_time = datetime.now(timezone.utc) - timedelta(hours=2)
            json.dump({"timestamp": old_time.isoformat(), "data": {}}, f)

        # Create fresh cache
        fresh_file = temp_cache_dir / "fresh.json"
        with open(fresh_file, "w") as f:
            json.dump({"timestamp": datetime.now(timezone.utc).isoformat(), "data": {}}, f)

        # Clear cache older than 1 hour
        deleted = api_client.clear_cache(older_than=timedelta(hours=1))

        assert deleted == 1
        assert not old_file.exists()
        assert fresh_file.exists()

    async def test_session_required(self, api_client):
        """RuntimeError raised if session not initialized."""
        # Don't use context manager
        with pytest.raises(RuntimeError, match="must be used as context manager"):
            await api_client.get("/test")

    async def test_custom_timeout(self, api_client):
        """Custom timeout is passed to request."""
        with patch.object(api_client, "_make_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"data": []}

            async with api_client:
                await api_client.get("/test", timeout=30, use_cache=False)

            # Verify custom timeout was passed
            call_args = mock_req.call_args
            assert call_args[0][3] == 30
