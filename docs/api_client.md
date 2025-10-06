# APIClient Documentation

Modern async HTTP client with automatic retry, caching, and rate limit handling.

## Features

- **Async/await support** using aiohttp
- **Automatic retries** with exponential backoff (max 3 attempts)
- **Rate limit detection** handles 429 status codes gracefully
- **Response caching** with configurable TTL
- **Timeout handling** with configurable defaults
- **Context manager** support for proper resource cleanup

## Installation

Dependencies are already included in `pyproject.toml`:
- `aiohttp>=3.9`

## Quick Start

```python
import asyncio
from src.lib.api_client import APIClient

async def main():
    async with APIClient("https://api.example.com") as client:
        data = await client.get("/endpoint")
        print(data)

asyncio.run(main())
```

## Usage

### Basic GET Request

```python
async with APIClient("https://api.example.com") as client:
    # Simple request
    data = await client.get("/stocks/AAPL")

    # With query parameters
    data = await client.get("/stocks", params={"symbol": "AAPL", "limit": 10})

    # With custom headers
    headers = {"Authorization": "Bearer token123"}
    data = await client.get("/protected", headers=headers)
```

### Caching

By default, responses are cached for 15 minutes (900 seconds):

```python
async with APIClient("https://api.example.com") as client:
    # First request - hits API
    data1 = await client.get("/stocks/AAPL", use_cache=True)

    # Second request - uses cache
    data2 = await client.get("/stocks/AAPL", use_cache=True)

    # Disable cache
    fresh_data = await client.get("/stocks/AAPL", use_cache=False)

    # Custom cache TTL (1 hour)
    data = await client.get("/stocks/AAPL", cache_ttl=3600)
```

### Custom Cache Directory

```python
from pathlib import Path

cache_dir = Path.home() / ".my-app" / "cache"
async with APIClient("https://api.example.com", cache_dir=cache_dir) as client:
    data = await client.get("/endpoint")
```

### Retry Behavior

The client automatically retries on:
- **Timeout errors** (up to max_retries)
- **Rate limit errors (429)** with exponential backoff

It does NOT retry on:
- Other HTTP errors (400, 404, 500, etc.)
- Network errors

```python
# Customize retry settings
async with APIClient(
    "https://api.example.com",
    max_retries=5,
    default_timeout=30
) as client:
    data = await client.get("/endpoint")
```

### Timeout Configuration

```python
async with APIClient("https://api.example.com", default_timeout=10) as client:
    # Use default timeout (10 seconds)
    data1 = await client.get("/endpoint")

    # Override timeout for specific request
    data2 = await client.get("/slow-endpoint", timeout=30)
```

### Concurrent Requests

```python
async with APIClient("https://api.example.com") as client:
    # Create tasks
    tasks = [
        client.get(f"/stocks/{symbol}")
        for symbol in ["AAPL", "GOOGL", "MSFT"]
    ]

    # Execute concurrently
    results = await asyncio.gather(*tasks)
```

### Cache Management

```python
from datetime import timedelta

async with APIClient("https://api.example.com") as client:
    # Make some requests
    await client.get("/endpoint1")
    await client.get("/endpoint2")

    # Clear cache older than 1 hour
    deleted = client.clear_cache(older_than=timedelta(hours=1))
    print(f"Deleted {deleted} cache files")

    # Clear all cache
    deleted = client.clear_cache()
    print(f"Deleted {deleted} cache files")
```

### Error Handling

```python
from src.lib.api_client import APIClient, APIError, RateLimitError

async with APIClient("https://api.example.com") as client:
    try:
        data = await client.get("/endpoint")
    except RateLimitError:
        print("Rate limit exceeded after retries")
    except APIError as e:
        print(f"API error: {e}")
    except asyncio.TimeoutError:
        print("Request timed out after retries")
```

## API Reference

### APIClient

#### Constructor

```python
APIClient(
    base_url: str,
    cache_dir: Optional[Path] = None,
    default_timeout: int = 10,
    max_retries: int = 3
)
```

**Parameters:**
- `base_url`: Base URL for all requests (e.g., "https://api.example.com")
- `cache_dir`: Cache directory (default: `~/.stocks-helper/cache`)
- `default_timeout`: Default timeout in seconds (default: 10)
- `max_retries`: Maximum retry attempts (default: 3)

#### Methods

##### get()

```python
async def get(
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    use_cache: bool = True,
    cache_ttl: int = 900,
    timeout: Optional[int] = None
) -> Dict[str, Any]
```

Make GET request with retry and caching.

**Parameters:**
- `endpoint`: API endpoint (appended to base_url)
- `params`: Query parameters
- `headers`: Request headers
- `use_cache`: Enable caching (default: True)
- `cache_ttl`: Cache TTL in seconds (default: 900)
- `timeout`: Request timeout (uses default_timeout if None)

**Returns:** JSON response as dictionary

**Raises:**
- `RateLimitError`: Rate limit exceeded
- `APIError`: API request failed
- `asyncio.TimeoutError`: Request timed out

##### clear_cache()

```python
def clear_cache(older_than: Optional[timedelta] = None) -> int
```

Clear cached responses.

**Parameters:**
- `older_than`: Only clear cache older than this (default: clear all)

**Returns:** Number of cache files deleted

## Exception Hierarchy

```
Exception
├── RateLimitError - Rate limit exceeded (429) after retries
└── APIError - API request failed (HTTP errors, network errors)
```

## Best Practices

### 1. Always Use Context Manager

```python
# Good
async with APIClient("https://api.example.com") as client:
    data = await client.get("/endpoint")

# Bad - session not properly closed
client = APIClient("https://api.example.com")
data = await client.get("/endpoint")  # RuntimeError!
```

### 2. Cache Expensive Requests

```python
# Cache data that changes infrequently
async with APIClient("https://api.example.com") as client:
    # Cache for 1 hour
    stock_info = await client.get("/stocks/AAPL/info", cache_ttl=3600)

    # Don't cache real-time data
    live_price = await client.get("/stocks/AAPL/price", use_cache=False)
```

### 3. Handle Errors Gracefully

```python
from src.lib.api_client import APIError, RateLimitError

async with APIClient("https://api.example.com") as client:
    try:
        data = await client.get("/endpoint")
    except RateLimitError:
        # Wait longer before retrying
        await asyncio.sleep(60)
    except APIError as e:
        # Log error and continue
        logger.error(f"API error: {e}")
```

### 4. Use Concurrent Requests for Performance

```python
# Process multiple stocks in parallel
async with APIClient("https://api.example.com") as client:
    tasks = [client.get(f"/stocks/{s}") for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle individual failures
    for symbol, result in zip(symbols, results):
        if isinstance(result, Exception):
            print(f"{symbol} failed: {result}")
        else:
            process_data(result)
```

### 5. Clean Up Cache Periodically

```python
from datetime import timedelta

# In a scheduled task or at app shutdown
async with APIClient("https://api.example.com") as client:
    # Clear cache older than 1 day
    deleted = client.clear_cache(older_than=timedelta(days=1))
    logger.info(f"Cleaned up {deleted} old cache files")
```

## Performance Considerations

- **Cache directory**: Use SSD storage for better cache performance
- **Concurrent requests**: Limited by aiohttp connection pool (default: 100)
- **Memory usage**: Responses are loaded into memory (consider streaming for large files)
- **Cache size**: No automatic cleanup - implement periodic cleanup

## Examples

See `/Users/priitlaht/Repository/stocks-helper/examples/api_client_example.py` for complete examples.

## Testing

Run tests:
```bash
# Unit tests
pytest tests/unit/test_api_client.py -v

# Integration tests
pytest tests/integration/test_api_client_integration.py -v

# All tests
pytest tests/ -v
```
