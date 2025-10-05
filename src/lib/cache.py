"""Cache manager for API responses."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


class CacheManager:
    """Manages caching of API responses to JSON files."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize cache manager.

        Args:
            cache_dir: Directory for cache files. Defaults to ~/.stocks-helper/cache/
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".stocks-helper" / "cache"

        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

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
        self, source: str, ticker: str, date: Optional[str] = None, ttl_minutes: int = 15
    ) -> Optional[dict[str, Any]]:
        """
        Retrieve cached data if valid.

        Args:
            source: API source
            ticker: Stock ticker
            date: Optional date
            ttl_minutes: Time-to-live in minutes (default: 15)

        Returns:
            Cached data dict or None if cache miss/expired
        """
        cache_key = self._get_cache_key(source, ticker, date)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            return None

        # Check if cache is expired
        file_mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - file_mtime > timedelta(minutes=ttl_minutes):
            return None

        # Read and return cached data
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, IOError):
            # Invalid cache file, remove it
            cache_path.unlink(missing_ok=True)
            return None

    def set(self, source: str, ticker: str, data: dict[str, Any], date: Optional[str] = None):
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

    def cleanup(self, max_age_days: int = 7):
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

    def clear(self):
        """Clear all cache files."""
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink(missing_ok=True)

    def clear_ticker(self, ticker: str):
        """
        Clear all cache files for a specific ticker.

        Args:
            ticker: Stock ticker to clear
        """
        pattern = f"*_{ticker}_*.json"
        for cache_file in self.cache_dir.glob(pattern):
            cache_file.unlink(missing_ok=True)
