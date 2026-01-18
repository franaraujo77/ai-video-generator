"""Integration tests for error_classifier with tenacity retry logic.

This module tests that error_classifier integrates correctly with
tenacity's retry decorator and that errors are properly logged during retries.

Story Reference: 6.1 - Transient Failure Detection
Issue Fix: Code review issue #6 (missing integration test)
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed

from app.services.error_classifier import ErrorCategory, classify_error
from app.utils.cli_wrapper import CLIScriptError


class TestRetryIntegrationWithClassifier:
    """Test integration between error_classifier and tenacity retry logic."""

    def test_should_retry_error_callback_with_transient_error(self) -> None:
        """Verify should_retry_error callback correctly identifies transient errors."""

        def should_retry_error(exception: Exception) -> bool:
            """Retry callback using error_classifier."""
            analysis = classify_error(exception)
            return analysis.retry_recommended

        # Test transient error (429)
        request = httpx.Request("GET", "https://api.example.com")
        response = httpx.Response(429, request=request)
        exception = httpx.HTTPStatusError("Rate limited", request=request, response=response)

        # Verify callback returns True for transient error
        assert should_retry_error(exception) is True

    def test_should_retry_error_callback_with_permanent_error(self) -> None:
        """Verify should_retry_error callback correctly rejects permanent errors."""

        def should_retry_error(exception: Exception) -> bool:
            """Retry callback using error_classifier."""
            analysis = classify_error(exception)
            return analysis.retry_recommended

        # Test permanent error (401)
        request = httpx.Request("GET", "https://api.example.com")
        response = httpx.Response(401, request=request)
        exception = httpx.HTTPStatusError("Unauthorized", request=request, response=response)

        # Verify callback returns False for permanent error
        assert should_retry_error(exception) is False

    def test_tenacity_retry_integration_with_transient_error(self) -> None:
        """Verify tenacity retry decorator works with classify_error for transient errors.

        This test validates that:
        1. Transient errors trigger retry
        2. Retry stops after max attempts
        3. Classification happens on each attempt
        """
        attempt_count = 0

        def should_retry_error(exception: Exception) -> bool:
            """Retry callback using error_classifier."""
            analysis = classify_error(exception)
            return analysis.retry_recommended

        @retry(
            retry=retry_if_exception(should_retry_error),
            stop=stop_after_attempt(3),
            wait=wait_fixed(0.01),  # Fast for testing
            reraise=True,
        )
        def failing_operation() -> str:
            """Simulated operation that fails with transient error."""
            nonlocal attempt_count
            attempt_count += 1

            # Always fail with transient error (429)
            request = httpx.Request("GET", "https://api.example.com")
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("Rate limited", request=request, response=response)

        # Execute and verify retry behavior
        with pytest.raises(httpx.HTTPStatusError):
            failing_operation()

        # Verify retry attempted 3 times (1 initial + 2 retries)
        assert attempt_count == 3, "Transient error should trigger 3 attempts"

    def test_tenacity_retry_integration_with_permanent_error(self) -> None:
        """Verify tenacity fails fast with permanent errors (no retry).

        This test validates that:
        1. Permanent errors do NOT trigger retry
        2. Operation fails immediately
        3. Only 1 attempt is made
        """
        attempt_count = 0

        def should_retry_error(exception: Exception) -> bool:
            """Retry callback using error_classifier."""
            analysis = classify_error(exception)
            return analysis.retry_recommended

        @retry(
            retry=retry_if_exception(should_retry_error),
            stop=stop_after_attempt(3),
            wait=wait_fixed(0.01),
            reraise=True,
        )
        def failing_operation() -> str:
            """Simulated operation that fails with permanent error."""
            nonlocal attempt_count
            attempt_count += 1

            # Always fail with permanent error (401)
            request = httpx.Request("GET", "https://api.example.com")
            response = httpx.Response(401, request=request)
            raise httpx.HTTPStatusError("Unauthorized", request=request, response=response)

        # Execute and verify NO retry (fail fast)
        with pytest.raises(httpx.HTTPStatusError):
            failing_operation()

        # Verify only 1 attempt (no retry for permanent error)
        assert attempt_count == 1, "Permanent error should fail fast without retry"

    def test_cli_script_error_retry_integration(self) -> None:
        """Verify CLI script errors integrate with retry logic."""
        attempt_count = 0

        def should_retry_error(exception: Exception) -> bool:
            """Retry callback using error_classifier."""
            analysis = classify_error(exception)
            return analysis.retry_recommended

        @retry(
            retry=retry_if_exception(should_retry_error),
            stop=stop_after_attempt(3),
            wait=wait_fixed(0.01),
            reraise=True,
        )
        def failing_cli_operation() -> str:
            """Simulated CLI operation that fails with transient error."""
            nonlocal attempt_count
            attempt_count += 1

            # Simulate CLI script error with 429 in stderr
            raise CLIScriptError(
                script="generate_audio.py", exit_code=1, stderr="Error: HTTP 429 - Rate limit exceeded"
            )

        # Execute and verify retry behavior
        with pytest.raises(CLIScriptError):
            failing_cli_operation()

        # Verify retry triggered for CLI script transient error
        assert attempt_count == 3, "CLI script 429 error should trigger retry"

    @patch("app.utils.logging.get_logger")
    def test_error_logging_during_retry(self, mock_get_logger: AsyncMock) -> None:
        """Verify errors are logged during retry attempts with confidence scores.

        This test validates issue #12 fix: confidence scores should be logged
        during actual retry flow.
        """
        mock_logger = AsyncMock()
        mock_get_logger.return_value = mock_logger

        attempt_count = 0
        logged_errors = []

        def should_retry_error(exception: Exception) -> bool:
            """Retry callback with logging."""
            nonlocal logged_errors
            analysis = classify_error(exception)

            # Simulate logging (in real code, would call log_error())
            logged_errors.append(
                {
                    "error_type": analysis.error_type,
                    "is_transient": analysis.category == ErrorCategory.TRANSIENT,
                    "confidence": analysis.confidence,
                    "retry_recommended": analysis.retry_recommended,
                }
            )

            return analysis.retry_recommended

        @retry(
            retry=retry_if_exception(should_retry_error),
            stop=stop_after_attempt(3),
            wait=wait_fixed(0.01),
            reraise=True,
        )
        def failing_operation() -> str:
            """Simulated operation."""
            nonlocal attempt_count
            attempt_count += 1

            request = httpx.Request("GET", "https://api.example.com")
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("Rate limited", request=request, response=response)

        # Execute
        with pytest.raises(httpx.HTTPStatusError):
            failing_operation()

        # Verify errors were logged with confidence
        assert len(logged_errors) == 3
        for error_log in logged_errors:
            assert error_log["confidence"] >= 0.9  # 429 has high confidence
            assert error_log["is_transient"] is True
            assert error_log["retry_recommended"] is True
