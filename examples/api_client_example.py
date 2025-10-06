"""Example usage of APIClient."""

import asyncio
from pathlib import Path

from src.lib.api_client import APIClient, APIError


async def basic_usage() -> None:
    """Basic APIClient usage example."""
    print("=== Basic Usage ===")

    # Create client with context manager
    async with APIClient("https://api.github.com") as client:
        # Simple GET request (cached by default)
        user_data = await client.get("/users/octocat")
        print(f"User: {user_data['login']}")
        print(f"Repos: {user_data['public_repos']}")


async def with_params_and_headers() -> None:
    """Request with query parameters and headers."""
    print("\n=== With Parameters and Headers ===")

    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "stocks-helper-example"}

    async with APIClient("https://api.github.com") as client:
        # Request with params
        repos = await client.get(
            "/users/octocat/repos", params={"type": "owner", "sort": "updated"}, headers=headers
        )
        # GitHub repos API returns a list (example shows API flexibility)
        print(f"Response received: {type(repos).__name__}")
        # Type system expects dict, but API may return list - handle gracefully in production
        try:
            repo_count = len(repos) if hasattr(repos, "__len__") else 0
            print(f"Repositories found: {repo_count}")
        except (TypeError, AttributeError):
            print("Unable to determine repository count")


async def caching_example() -> None:
    """Demonstrate caching behavior."""
    print("\n=== Caching Example ===")

    cache_dir = Path.home() / ".stocks-helper" / "example-cache"

    async with APIClient("https://api.github.com", cache_dir=cache_dir) as client:
        # First request - hits API
        print("First request (from API)...")
        data1 = await client.get("/users/octocat", use_cache=True)

        # Second request - uses cache
        print("Second request (from cache)...")
        data2 = await client.get("/users/octocat", use_cache=True)

        # Verify both return same data
        assert data1 == data2
        print("Cache working! Same data returned.")

        # Disable cache for fresh data
        print("Third request (cache disabled)...")
        data3 = await client.get("/users/octocat", use_cache=False)
        assert data3 == data1
        print("Fresh data matches cached data.")

        # Check cache stats
        cache_files = list(cache_dir.glob("*.json"))
        print(f"\nCache files: {len(cache_files)}")


async def error_handling() -> None:
    """Demonstrate error handling."""
    print("\n=== Error Handling ===")

    async with APIClient("https://api.github.com") as client:
        try:
            # This will fail (404)
            await client.get("/users/this-user-definitely-does-not-exist-12345")
        except APIError as e:
            print(f"Caught API error: {e}")

        try:
            # Timeout example (use very short timeout)
            await client.get("/users/octocat", timeout=1, use_cache=False)
        except asyncio.TimeoutError:
            print("Caught timeout error (expected)")


async def retry_example() -> None:
    """Demonstrate retry behavior."""
    print("\n=== Retry Example ===")

    # Client with custom retry settings
    async with APIClient("https://api.github.com", max_retries=5, default_timeout=30) as client:
        # This will automatically retry on transient failures
        data = await client.get("/users/octocat")
        print(f"Request succeeded (with retry support): {data['login']}")


async def concurrent_requests() -> None:
    """Make multiple concurrent requests."""
    print("\n=== Concurrent Requests ===")

    users = ["octocat", "torvalds", "gvanrossum"]

    async with APIClient("https://api.github.com") as client:
        # Create tasks for concurrent execution
        tasks = [client.get(f"/users/{user}") for user in users]

        # Execute all requests concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for user, result in zip(users, results):
            if isinstance(result, Exception):
                print(f"{user}: Error - {result}")
            elif isinstance(result, dict):
                print(
                    f"{user}: {result.get('name', 'N/A')} ({result.get('public_repos', 0)} repos)"
                )


async def cache_management() -> None:
    """Demonstrate cache management."""
    print("\n=== Cache Management ===")

    from datetime import timedelta

    cache_dir = Path.home() / ".stocks-helper" / "example-cache"

    async with APIClient("https://api.github.com", cache_dir=cache_dir) as client:
        # Make some requests to populate cache
        await client.get("/users/octocat")
        await client.get("/users/torvalds")

        cache_files = list(cache_dir.glob("*.json"))
        print(f"Cache files before cleanup: {len(cache_files)}")

        # Clear old cache (older than 1 second - for demo purposes)
        import asyncio

        await asyncio.sleep(1.5)

        deleted = client.clear_cache(older_than=timedelta(seconds=1))
        print(f"Deleted {deleted} old cache files")

        # Clear all cache
        deleted_all = client.clear_cache()
        print(f"Deleted {deleted_all} remaining cache files")


async def custom_api_example() -> None:
    """Example with a custom API (mock)."""
    print("\n=== Custom API Example ===")

    # Example with a stock API (if you have an API key)
    # Replace with your actual stock API endpoint
    async with APIClient("https://api.example.com") as client:
        try:
            # Example: Fetch stock data
            stock_data = await client.get(
                "/stocks/AAPL",
                params={"interval": "1d", "range": "1mo"},
                headers={"X-API-Key": "your-api-key-here"},
                cache_ttl=3600,  # Cache for 1 hour
            )
            print(f"Stock data retrieved: {len(stock_data)} data points")
        except APIError as e:
            print(f"API not available for demo: {e}")


async def main() -> None:
    """Run all examples."""
    examples = [
        basic_usage,
        with_params_and_headers,
        caching_example,
        retry_example,
        concurrent_requests,
        cache_management,
        error_handling,
    ]

    for example in examples:
        try:
            await example()
        except Exception as e:
            print(f"\nExample {example.__name__} failed: {e}")

    print("\n=== All examples complete! ===")


if __name__ == "__main__":
    asyncio.run(main())
