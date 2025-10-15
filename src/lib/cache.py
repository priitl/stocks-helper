"""Cache manager for API responses with market-hours aware TTL."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, cast

from src.lib.market_hours import get_cache_ttl


class CacheManager:
    """Manages caching of API responses to JSON files.

    Features:
    - Market-hours aware TTL (shorter during trading hours)
    - JSON file-based storage
    - Automatic expiration and cleanup
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        use_market_hours: bool = True,
        exchange: str = "NYSE",
    ):
        """
        Initialize cache manager.

        Args:
            cache_dir: Directory for cache files. Defaults to ~/.stocks-helper/cache/
            use_market_hours: Use market-hours aware TTL (default: True)
            exchange: Exchange for market hours (default: NYSE)
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".stocks-helper" / "cache"

        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_market_hours = use_market_hours
        self.exchange = exchange

    def _get_cache_key(self, source: str, ticker: str, date: Optional[str] = None) -> str:
        """
        Generate cache key from source, ticker, and date.

        Args:
            source: API source (e.g., 'alpha_vantage', 'yahoo_finance')
            ticker: Stock ticker symbol
            date: Optional date string (YYYY-MM-DD)

        Returns:
            Cache key string
        """
        if date:
            return f"{source}_{ticker}_{date}"
        return f"{source}_{ticker}_latest"

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get file path for cache key."""
        return self.cache_dir / f"{cache_key}.json"

    def get(
        self,
        source: str,
        ticker: str,
        date: Optional[str] = None,
        ttl_minutes: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Retrieve cached data if valid.

        Args:
            source: API source
            ticker: Stock ticker
            date: Optional date
            ttl_minutes: Time-to-live in minutes (default: market-hours aware if enabled,
                        otherwise 15 minutes)

        Returns:
            Cached data dict or None if cache miss/expired
        """
        cache_key = self._get_cache_key(source, ticker, date)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            return None

        # Determine TTL
        if ttl_minutes is None:
            if self.use_market_hours:
                # Use market-hours aware TTL (in seconds, convert to minutes)
                ttl_seconds = get_cache_ttl(self.exchange)
                ttl_minutes = ttl_seconds // 60
            else:
                ttl_minutes = 15  # Default 15 minutes

        # Check if cache is expired
        file_mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - file_mtime > timedelta(minutes=ttl_minutes):
            return None

        # Read and return cached data
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            return cast(dict[str, Any], data)
        except (json.JSONDecodeError, IOError):
            # Invalid cache file, remove it
            cache_path.unlink(missing_ok=True)
            return None

    def set(
        self, source: str, ticker: str, data: dict[str, Any], date: Optional[str] = None
    ) -> None:
        """
        Store data in cache.

        Args:
            source: API source
            ticker: Stock ticker
            data: Data to cache
            date: Optional date
        """
        cache_key = self._get_cache_key(source, ticker, date)
        cache_path = self._get_cache_path(cache_key)

        try:
            with open(cache_path, "w") as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            # Log error but don't fail if cache write fails
            print(f"Warning: Failed to write cache: {e}")

    def cleanup(self, max_age_days: int = 7) -> None:
        """
        Remove cache files older than max_age_days.

        Args:
            max_age_days: Maximum age in days (default: 7)
        """
        cutoff_time = datetime.now() - timedelta(days=max_age_days)

        for cache_file in self.cache_dir.glob("*.json"):
            file_mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if file_mtime < cutoff_time:
                cache_file.unlink(missing_ok=True)

    def clear(self) -> None:
        """Clear all cache files."""
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink(missing_ok=True)

    def clear_ticker(self, ticker: str) -> None:
        """
        Clear all cache files for a specific ticker.

        Args:
            ticker: Stock ticker to clear
        """
        pattern = f"*_{ticker}_*.json"
        for cache_file in self.cache_dir.glob(pattern):
            cache_file.unlink(missing_ok=True)
