"""API quota tracker to monitor and enforce rate limits."""

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class QuotaTracker:
    """Track API request quotas to prevent exceeding limits.

    Supports daily and per-minute quota tracking with persistence.
    """

    def __init__(
        self,
        api_name: str,
        daily_limit: int,
        per_minute_limit: Optional[int] = None,
        storage_dir: Optional[Path] = None,
    ):
        """Initialize quota tracker.

        Args:
            api_name: Name of the API (used for storage file)
            daily_limit: Maximum requests allowed per day
            per_minute_limit: Optional per-minute rate limit
            storage_dir: Directory for quota storage (default: ~/.stocks-helper/quota)
        """
        self.api_name = api_name
        self.daily_limit = daily_limit
        self.per_minute_limit = per_minute_limit
        self.storage_dir = storage_dir or (Path.home() / ".stocks-helper" / "quota")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_file = self.storage_dir / f"{api_name}_quota.json"

        # Load existing quota data
        self._load_quota_data()

    def _load_quota_data(self) -> None:
        """Load quota data from storage file."""
        if not self.storage_file.exists():
            self._reset_quota()
            return

        try:
            with open(self.storage_file) as f:
                data = json.load(f)

            self.current_date = date.fromisoformat(data.get("date", str(date.today())))
            self.daily_count = data.get("daily_count", 0)
            self.minute_requests = [
                datetime.fromisoformat(ts) for ts in data.get("minute_requests", [])
            ]

            # Reset if it's a new day
            if self.current_date < date.today():
                self._reset_quota()

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to load quota data for {self.api_name}: {e}")
            self._reset_quota()

    def _reset_quota(self) -> None:
        """Reset quota counters for new day."""
        self.current_date = date.today()
        self.daily_count = 0
        self.minute_requests = []
        self._save_quota_data()

    def _save_quota_data(self) -> None:
        """Save quota data to storage file."""
        try:
            data = {
                "date": self.current_date.isoformat(),
                "daily_count": self.daily_count,
                "minute_requests": [ts.isoformat() for ts in self.minute_requests],
            }
            with open(self.storage_file, "w") as f:
                json.dump(data, f, indent=2)
        except (OSError, TypeError) as e:
            logger.error(f"Failed to save quota data for {self.api_name}: {e}")

    def can_make_request(self) -> bool:
        """Check if a request can be made within quota limits.

        Returns:
            True if request is allowed, False if quota exceeded
        """
        # Check if it's a new day
        if self.current_date < date.today():
            self._reset_quota()

        # Check daily limit
        if self.daily_count >= self.daily_limit:
            logger.warning(
                f"{self.api_name} daily quota exceeded: {self.daily_count}/{self.daily_limit}"
            )
            return False

        # Check per-minute limit if configured
        if self.per_minute_limit is not None:
            # Clean up old minute requests (older than 60 seconds)
            cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=60)
            self.minute_requests = [ts for ts in self.minute_requests if ts > cutoff_time]

            if len(self.minute_requests) >= self.per_minute_limit:
                logger.warning(
                    f"{self.api_name} per-minute quota exceeded: "
                    f"{len(self.minute_requests)}/{self.per_minute_limit}"
                )
                return False

        return True

    def record_request(self) -> None:
        """Record that a request was made."""
        # Check if it's a new day
        if self.current_date < date.today():
            self._reset_quota()

        self.daily_count += 1

        if self.per_minute_limit is not None:
            self.minute_requests.append(datetime.now(timezone.utc))

        self._save_quota_data()

        logger.debug(
            f"{self.api_name} request recorded: {self.daily_count}/{self.daily_limit} daily"
        )

    def get_remaining_quota(self) -> dict[str, int]:
        """Get remaining quota information.

        Returns:
            Dict with quota information
        """
        # Check if it's a new day
        if self.current_date < date.today():
            self._reset_quota()

        result = {
            "api_name": self.api_name,
            "date": self.current_date.isoformat(),
            "daily_used": self.daily_count,
            "daily_limit": self.daily_limit,
            "daily_remaining": self.daily_limit - self.daily_count,
        }

        if self.per_minute_limit is not None:
            # Clean up old minute requests
            cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=60)
            active_minute_requests = [ts for ts in self.minute_requests if ts > cutoff_time]
            result.update(
                {
                    "per_minute_used": len(active_minute_requests),
                    "per_minute_limit": self.per_minute_limit,
                    "per_minute_remaining": self.per_minute_limit - len(active_minute_requests),
                }
            )

        return result

    def reset(self) -> None:
        """Manually reset quota (useful for testing or quota refresh)."""
        self._reset_quota()
        logger.info(f"Quota reset for {self.api_name}")
