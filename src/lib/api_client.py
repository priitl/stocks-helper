"""Async HTTP client with retry logic, rate limiting, and caching."""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

from src.lib.config import DEFAULT_CACHE_TTL

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when rate limit is exceeded after retries."""


class APIError(Exception):
    """Raised when API request fails."""


class APIClient:
    """Async HTTP client with built-in retry, caching, and rate limit handling.

    Features:
    - Exponential backoff retry (max 3 attempts)
    - Rate limit detection (429 status)
    - Configurable timeout (default 10s)
    - JSON response caching with TTL
    - Context manager support

    Example:
        async with APIClient("https://api.example.com") as client:
            data = await client.get("/stocks/AAPL")
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        default_timeout: int = 10,
        max_retries: int = 3,
    ):
        """Initialize API client.

        Args:
            base_url: Base URL for all API requests (optional, can use full URLs instead)
            cache_dir: Directory for caching responses (default: ~/.stocks-helper/cache)
            default_timeout: Default request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.base_url = base_url.rstrip("/") if base_url else None
        self.cache_dir = cache_dir or (Path.home() / ".stocks-helper" / "cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "APIClient":
        """Enter async context manager."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager and cleanup session."""
        if self.session:
            await self.session.close()

    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        use_cache: bool = True,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Make GET request with retry logic and caching.

        Args:
            endpoint: API endpoint (will be appended to base_url)
            params: Query parameters
            headers: Request headers
            use_cache: Whether to use cached responses
            cache_ttl: Cache time-to-live in seconds (default: 900 = 15 minutes)
            timeout: Request timeout in seconds (uses default_timeout if None)

        Returns:
            JSON response as dictionary

        Raises:
            RateLimitError: Rate limit exceeded after all retries
            APIError: API request failed
            asyncio.TimeoutError: Request timed out after all retries
        """
        if not self.session:
            raise RuntimeError("APIClient must be used as context manager")

        # Check cache first
        if use_cache:
            cached = self._get_cached(endpoint, params, cache_ttl)
            if cached is not None:
                return cached

        # Retry with exponential backoff
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                data = await self._make_request(
                    endpoint, params, headers, timeout or self.default_timeout
                )

                # Cache successful response
                if use_cache:
                    self._cache_response(endpoint, params, data)

                return data

            except aiohttp.ClientResponseError as e:
                if e.status == 429:
                    # Rate limit - exponential backoff
                    if attempt < self.max_retries - 1:
                        wait_time = 2**attempt
                        await asyncio.sleep(wait_time)
                        continue
                    raise RateLimitError(
                        f"Rate limit exceeded after {self.max_retries} attempts"
                    ) from e
                # Other HTTP errors - don't retry
                raise APIError(f"API request failed: {e.status} {e.message}") from e

            except asyncio.TimeoutError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
                    continue
                raise

            except aiohttp.ClientError as e:
                # Network errors - don't retry
                raise APIError(f"Network error: {str(e)}") from e

        # Should not reach here, but just in case
        if last_error:
            raise last_error
        raise APIError("Max retries exceeded")

    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]],
        headers: Optional[Dict[str, str]],
        timeout: int,
    ) -> Dict[str, Any]:
        """Make single HTTP request.

        Args:
            endpoint: API endpoint
            params: Query parameters
            headers: Request headers
            timeout: Request timeout in seconds

        Returns:
            JSON response as dictionary

        Raises:
            aiohttp.ClientResponseError: HTTP error
            asyncio.TimeoutError: Request timeout
            aiohttp.ClientError: Network error
        """
        # Support both full URLs and relative endpoints
        if self.base_url:
            url = f"{self.base_url}{endpoint}"
        else:
            # Endpoint should be a full URL
            url = endpoint

        timeout_obj = aiohttp.ClientTimeout(total=timeout)

        async with self.session.get(
            url, params=params, headers=headers, timeout=timeout_obj
        ) as response:
            response.raise_for_status()
            return await response.json()

    def _get_cached(
        self, endpoint: str, params: Optional[Dict[str, Any]], cache_ttl: int
    ) -> Optional[Dict[str, Any]]:
        """Get cached response if valid.

        Args:
            endpoint: API endpoint
            params: Query parameters
            cache_ttl: Cache TTL in seconds

        Returns:
            Cached data if valid, None otherwise
        """
        cache_key = self._make_cache_key(endpoint, params)
        cache_file = self.cache_dir / f"{cache_key}.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file) as f:
                cached = json.load(f)

            # Validate cache structure
            if not isinstance(cached, dict) or "timestamp" not in cached or "data" not in cached:
                return None

            # Check TTL
            cached_time = datetime.fromisoformat(cached["timestamp"])
            age = datetime.now() - cached_time

            if age < timedelta(seconds=cache_ttl):
                return cached["data"]

        except (json.JSONDecodeError, ValueError, KeyError):
            # Invalid cache file - ignore
            pass

        return None

    def _sanitize_params(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Remove sensitive data from params before caching.

        Args:
            params: Query parameters that may contain sensitive data

        Returns:
            Sanitized copy of params with sensitive keys redacted
        """
        if not params:
            return {}

        sanitized = params.copy()
        sensitive_keys = {"apikey", "api_key", "token", "password", "secret", "key"}

        for key in list(sanitized.keys()):
            if key.lower() in sensitive_keys:
                sanitized[key] = "[REDACTED]"

        return sanitized

    def _cache_response(
        self, endpoint: str, params: Optional[Dict[str, Any]], data: Dict[str, Any]
    ) -> None:
        """Cache response to file.

        Args:
            endpoint: API endpoint
            params: Query parameters
            data: Response data to cache
        """
        cache_key = self._make_cache_key(endpoint, params)
        cache_file = self.cache_dir / f"{cache_key}.json"

        try:
            with open(cache_file, "w") as f:
                json.dump(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "endpoint": endpoint,
                        "params": self._sanitize_params(params),
                        "data": data,
                    },
                    f,
                    indent=2,
                )
        except (OSError, TypeError) as e:
            # Cache write failed - log but don't fail the request
            logger.warning(f"Failed to write cache for {endpoint}: {e}")

    def _make_cache_key(self, endpoint: str, params: Optional[Dict[str, Any]]) -> str:
        """Generate cache key from endpoint and params.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            MD5 hash of endpoint and sorted params
        """
        key_parts = [endpoint]
        if params:
            # Sort params for consistent cache keys
            key_parts.append(str(sorted(params.items())))
        key = "_".join(key_parts)
        return hashlib.md5(key.encode()).hexdigest()

    def clear_cache(self, older_than: Optional[timedelta] = None) -> int:
        """Clear cached responses.

        Args:
            older_than: Only clear cache older than this timedelta (default: all)

        Returns:
            Number of cache files deleted
        """
        deleted = 0

        for cache_file in self.cache_dir.glob("*.json"):
            try:
                if older_than is not None:
                    # Check file age
                    with open(cache_file) as f:
                        cached = json.load(f)
                    cached_time = datetime.fromisoformat(cached["timestamp"])
                    age = datetime.now() - cached_time

                    if age < older_than:
                        continue

                cache_file.unlink()
                deleted += 1

            except (json.JSONDecodeError, ValueError, KeyError, OSError):
                # Invalid cache file - delete it
                try:
                    cache_file.unlink()
                    deleted += 1
                except OSError:
                    pass

        return deleted
