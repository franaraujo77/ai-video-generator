"""Structured Logging Configuration.

This module provides structured logging with JSON output and context binding.
Outputs JSON format for production log aggregation (CloudWatch, Datadog, Splunk).

Configuration:
- JSON output format (for production log aggregation)
- Context binding support (correlation IDs, task IDs, etc.)
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

Enhanced Features (Story 6.1):
- log_error() helper for error logging with required metadata
- ISO 8601 timestamp format (UTC timezone)
- Integration with error_classifier for transient/permanent classification
"""

import json
import logging
import sys
from datetime import datetime, timezone
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


def log_error(
    task_id: str,
    channel_id: str,
    step: str,
    error_type: str,
    error_message: str,
    is_transient: bool,
    retry_attempt: int,
    http_status_code: int | None = None,
    confidence: float | None = None,
) -> None:
    """Log error with required metadata for error tracking and analysis.

    This helper function ensures all error logs include consistent metadata
    fields required for error analysis, retry decisions, and observability.

    Required Fields:
    - timestamp: ISO 8601 timestamp with UTC timezone (auto-generated)
    - task_id: Database task UUID
    - channel_id: Channel identifier (for multi-channel isolation)
    - step: Pipeline step where error occurred
    - error_type: Exception class name (e.g., "HTTPStatusError", "TimeoutException")
    - error_message: Original error message
    - is_transient: Whether error is transient (retry) or permanent (fail fast)
    - retry_attempt: Current retry attempt number (0 = first attempt)

    Optional Fields:
    - http_status_code: HTTP status code if applicable (429, 500, 400, etc.)
    - confidence: Classification confidence from error_classifier (0.0-1.0)

    Args:
        task_id: Database task UUID (correlation ID)
        channel_id: Channel identifier for multi-channel isolation
        step: Pipeline step (e.g., "narration_generation", "video_generation")
        error_type: Exception type name (e.g., "HTTPStatusError", "CLIScriptError")
        error_message: Original error message from exception
        is_transient: True if error is transient (retry), False if permanent (fail fast)
        retry_attempt: Current retry attempt number (0 = first attempt, 1 = first retry, etc.)
        http_status_code: Optional HTTP status code (429, 500, 400, etc.)
        confidence: Optional classification confidence from error_classifier (0.0-1.0)

    Example:
        >>> from app.services.error_classifier import classify_error
        >>> from app.utils.logging import log_error
        >>> from app.utils.cli_wrapper import CLIScriptError
        >>>
        >>> try:
        ...     await run_cli_script("generate_audio.py", args)
        ... except CLIScriptError as e:
        ...     analysis = classify_error(e)
        ...     log_error(
        ...         task_id=str(task.id),
        ...         channel_id=task.channel_id,
        ...         step="narration_generation",
        ...         error_type=analysis.error_type,
        ...         error_message=analysis.error_message,
        ...         is_transient=analysis.retry_recommended,
        ...         retry_attempt=1,
        ...         http_status_code=analysis.http_status_code,
        ...         confidence=analysis.confidence,
        ...     )

    Story Reference: 6.1 - Transient Failure Detection (Task 4)
    """
    logger = get_logger("app.error_logging")

    # Generate ISO 8601 timestamp with UTC timezone
    timestamp = datetime.now(timezone.utc).isoformat()

    # Log error with all required metadata
    logger.error(
        "error_logged",
        timestamp=timestamp,
        task_id=task_id,
        channel_id=channel_id,
        step=step,
        error_type=error_type,
        error_message=error_message,
        is_transient=is_transient,
        retry_attempt=retry_attempt,
        http_status_code=http_status_code,
        confidence=confidence,
    )
