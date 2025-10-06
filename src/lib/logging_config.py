"""Logging configuration with security filters."""

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class APIKeyFilter(logging.Filter):
    """Filter to redact API keys and sensitive data from log messages."""

    # Patterns to match sensitive data
    SENSITIVE_PATTERNS = [
        (
            re.compile(r"(apikey|api_key|token|password|secret)=([^&\s]+)", re.IGNORECASE),
            r"\1=[REDACTED]",
        ),
        (re.compile(r'("apikey"\s*:\s*)"([^"]+)"', re.IGNORECASE), r'\1"[REDACTED]"'),
        (re.compile(r"('apikey'\s*:\s*)'([^']+)'", re.IGNORECASE), r"\1'[REDACTED]'"),
        (re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE), "Bearer [REDACTED]"),
        (re.compile(r"Authorization:\s*[^\s]+", re.IGNORECASE), "Authorization: [REDACTED]"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log record to redact sensitive information.

        Args:
            record: Log record to filter

        Returns:
            True to keep the record, False to drop it
        """
        # Redact sensitive data from message
        if isinstance(record.msg, str):
            for pattern, replacement in self.SENSITIVE_PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)

        # Redact from args if present
        if record.args:
            if isinstance(record.args, dict):
                record.args = self._redact_dict(record.args)
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(self._redact_value(arg) for arg in record.args)

        return True

    def _redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive keys from dictionary."""
        sensitive_keys = {"apikey", "api_key", "token", "password", "secret", "authorization"}
        return {
            k: "[REDACTED]" if k.lower() in sensitive_keys else self._redact_value(v)
            for k, v in data.items()
        }

    def _redact_value(self, value: Any) -> Any:
        """Redact sensitive data from any value type."""
        if isinstance(value, str):
            for pattern, replacement in self.SENSITIVE_PATTERNS:
                value = pattern.sub(replacement, value)
        elif isinstance(value, dict):
            value = self._redact_dict(value)
        elif isinstance(value, (list, tuple)):
            value = type(value)(self._redact_value(item) for item in value)
        return value


def setup_logging(level: int = logging.INFO, log_file: str | None = None) -> None:
    """
    Configure logging with security filters and file rotation.

    Args:
        level: Logging level (default: INFO)
        log_file: Path to log file (default: ~/.stocks-helper/stocks-helper.log)
                 Set to None to disable file logging

    Example:
        >>> from src.lib.logging_config import setup_logging
        >>> setup_logging(logging.DEBUG)
        >>> setup_logging(logging.INFO, log_file="/var/log/stocks-helper.log")
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Add API key filter to all handlers
    api_key_filter = APIKeyFilter()

    # Format
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Configure handlers if not already configured
    if not root_logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(api_key_filter)
        root_logger.addHandler(console_handler)

        # File handler with rotation (only if log_file is provided or using default)
        if log_file is None:
            # Use default log file path
            log_file = os.getenv(
                "LOG_FILE", str(Path.home() / ".stocks-helper" / "stocks-helper.log")
            )

        if log_file:
            # Create log directory if it doesn't exist
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            # Rotating file handler: 10MB per file, keep 5 backup files
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(api_key_filter)
            root_logger.addHandler(file_handler)
    else:
        # Add filter to existing handlers
        for handler in root_logger.handlers:
            handler.addFilter(api_key_filter)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with API key filtering enabled.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance

    Example:
        >>> from src.lib.logging_config import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("API request: apikey=secret123")  # Logs: API request: apikey=[REDACTED]
    """
    logger = logging.getLogger(name)

    # Ensure API key filter is added
    if not any(isinstance(f, APIKeyFilter) for f in logger.filters):
        logger.addFilter(APIKeyFilter())

    return logger
