"""Structured Logging Configuration.

This module provides structured logging with JSON output and context binding.
Outputs JSON format for production log aggregation (CloudWatch, Datadog, Splunk).

Configuration:
- JSON output format (for production log aggregation)
- Context binding support (correlation IDs, task IDs, etc.)
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
"""

import json
import logging
import sys
from typing import Any


class StructuredLogger:
    """Wrapper around standard Logger with structured JSON logging support.

    Provides structured logging methods (info, error, warning) that accept
    keyword arguments and output JSON format for production log aggregation.
    """

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _format_json(self, event: str, **kwargs: Any) -> str:
        """Format log entry as JSON with event and context fields."""
        log_entry = {"event": event, **kwargs}
        return json.dumps(log_entry)

    def info(self, event: str, **kwargs: Any) -> None:
        """Log info message with structured context as JSON."""
        self._logger.info(self._format_json(event, **kwargs))

    def error(self, event: str, **kwargs: Any) -> None:
        """Log error message with structured context as JSON."""
        self._logger.error(self._format_json(event, **kwargs))

    def warning(self, event: str, **kwargs: Any) -> None:
        """Log warning message with structured context as JSON."""
        self._logger.warning(self._format_json(event, **kwargs))

    def debug(self, event: str, **kwargs: Any) -> None:
        """Log debug message with structured context as JSON."""
        self._logger.debug(self._format_json(event, **kwargs))


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance for the given module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured StructuredLogger instance
    """
    logger = logging.getLogger(name)

    # Configure basic logging if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return StructuredLogger(logger)
