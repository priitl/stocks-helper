"""Integration tests for APIClient with mock server."""

import asyncio

import pytest
import pytest_asyncio
from aiohttp import web

from src.lib.api_client import APIClient, APIError


@pytest_asyncio.fixture
async def mock_server():
    """Start a mock HTTP server for testing."""
    app = web.Application()

    # Track request counts for rate limiting
    request_counts = {"count": 0}

    async def success_handler(request):
        """Return successful JSON response."""
        return web.json_response({"status": "ok", "data": [1, 2, 3]})

    async def rate_limit_handler(request):
        """Return 429 on first two requests, then succeed."""
        request_counts["count"] += 1
        if request_counts["count"] <= 2:
            raise web.HTTPTooManyRequests()
        return web.json_response({"status": "ok", "recovered": True})

    async def slow_handler(request):
        """Slow response that will timeout."""
        await asyncio.sleep(15)  # Longer than default timeout
        return web.json_response({"status": "ok"})

    async def error_handler(request):
        """Return 500 error."""
        raise web.HTTPInternalServerError()

    async def with_params_handler(request):
        """Echo back query parameters."""
        params = dict(request.query)
        return web.json_response({"params": params})

    app.router.add_get("/success", success_handler)
    app.router.add_get("/rate-limit", rate_limit_handler)
    app.router.add_get("/slow", slow_handler)
    app.router.add_get("/error", error_handler)
    app.router.add_get("/with-params", with_params_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 8888)
    await site.start()

    yield "http://localhost:8888"

    # Cleanup
    await runner.cleanup()


@pytest.mark.asyncio
class TestAPIClientIntegration:
    """Integration tests with mock HTTP server."""

    async def test_successful_request(self, mock_server, tmp_path):
        """Make successful request to mock server."""
        async with APIClient(mock_server, cache_dir=tmp_path) as client:
            result = await client.get("/success", use_cache=False)

        assert result["status"] == "ok"
        assert result["data"] == [1, 2, 3]

    async def test_request_with_params(self, mock_server, tmp_path):
        """Request with query parameters."""
        async with APIClient(mock_server, cache_dir=tmp_path) as client:
            params = {"symbol": "AAPL", "limit": "10"}
            result = await client.get("/with-params", params=params, use_cache=False)

        assert result["params"] == params

    async def test_caching_behavior(self, mock_server, tmp_path):
        """Cached response is reused."""
        async with APIClient(mock_server, cache_dir=tmp_path) as client:
            # First request - should hit server
            result1 = await client.get("/success", use_cache=True)

            # Second request - should use cache
            result2 = await client.get("/success", use_cache=True)

        # Both should return same data
        assert result1 == result2

        # Verify cache file exists
        assert len(list(tmp_path.glob("*.json"))) == 1

    async def test_cache_with_different_params(self, mock_server, tmp_path):
        """Different params create separate cache entries."""
        async with APIClient(mock_server, cache_dir=tmp_path) as client:
            await client.get("/with-params", params={"id": "1"}, use_cache=True)
            await client.get("/with-params", params={"id": "2"}, use_cache=True)

        # Should have two cache files
        cache_files = list(tmp_path.glob("*.json"))
        assert len(cache_files) == 2

    async def test_rate_limit_recovery(self, mock_server, tmp_path):
        """Recovers from rate limit with retry."""
        async with APIClient(mock_server, cache_dir=tmp_path, max_retries=3) as client:
            # Will get rate limited twice, then succeed
            result = await client.get("/rate-limit", use_cache=False)

        assert result["status"] == "ok"
        assert result["recovered"] is True

    async def test_timeout_handling(self, mock_server, tmp_path):
        """Timeout is raised after retries."""
        async with APIClient(
            mock_server, cache_dir=tmp_path, default_timeout=1, max_retries=2
        ) as client:
            with pytest.raises(asyncio.TimeoutError):
                await client.get("/slow", use_cache=False)

    async def test_http_error_no_retry(self, mock_server, tmp_path):
        """HTTP errors fail immediately without retry."""
        async with APIClient(mock_server, cache_dir=tmp_path) as client:
            with pytest.raises(APIError, match="500"):
                await client.get("/error", use_cache=False)

    async def test_concurrent_requests(self, mock_server, tmp_path):
        """Multiple concurrent requests work correctly."""
        async with APIClient(mock_server, cache_dir=tmp_path) as client:
            # Make 5 concurrent requests
            tasks = [client.get("/success", use_cache=False) for _ in range(5)]
            results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 5
        assert all(r["status"] == "ok" for r in results)

    async def test_cache_clear(self, mock_server, tmp_path):
        """Cache can be cleared."""
        async with APIClient(mock_server, cache_dir=tmp_path) as client:
            # Create some cache entries
            await client.get("/success", use_cache=True)
            await client.get("/with-params", params={"id": "1"}, use_cache=True)

            # Verify cache exists
            assert len(list(tmp_path.glob("*.json"))) == 2

            # Clear cache
            deleted = client.clear_cache()

        assert deleted == 2
        assert len(list(tmp_path.glob("*.json"))) == 0
