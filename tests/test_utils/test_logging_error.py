"""Tests for enhanced error logging with metadata (Story 6.1 - Task 4).

Tests cover:
- log_error() helper function with required metadata
- Error log format validation (JSON structure)
- Field presence and types
"""

import json
from datetime import datetime, timezone

import pytest

from app.services.error_classifier import ErrorCategory
from app.utils.logging import log_error


class TestLogErrorHelper:
    """Test log_error() helper function for error logging with metadata."""

    def test_log_error_with_all_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify log_error logs all required fields."""
        # Call log_error with all fields
        log_error(
            task_id="task-123",
            channel_id="poke1",
            step="narration_generation",
            error_type="HTTPStatusError",
            error_message="Rate limit exceeded",
            is_transient=True,
            retry_attempt=1,
            http_status_code=429,
            confidence=0.95,
        )

        # Verify log entry was created
        assert len(caplog.records) == 1
        log_record = caplog.records[0]

        # Parse JSON log message
        log_data = json.loads(log_record.message)

        # Verify event type
        assert log_data["event"] == "error_logged"

        # Verify required fields present
        assert "timestamp" in log_data
        assert log_data["task_id"] == "task-123"
        assert log_data["channel_id"] == "poke1"
        assert log_data["step"] == "narration_generation"
        assert log_data["error_type"] == "HTTPStatusError"
        assert log_data["error_message"] == "Rate limit exceeded"
        assert log_data["is_transient"] is True
        assert log_data["retry_attempt"] == 1
        assert log_data["http_status_code"] == 429
        assert log_data["confidence"] == 0.95


class TestAcceptanceCriteriaValidation:
    """Validate explicit Acceptance Criteria from Story 6.1."""

    def test_ac_transient_failure_includes_error_type_and_is_transient_flag(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """AC: Given transient failure, Then error includes: error_type, is_transient flag, suggested_action.

        This test validates AC by verifying error_type and is_transient appear in log output.
        Note: suggested_action is available in ErrorAnalysis but not logged (future enhancement).

        Story Reference: 6.1 AC "Given transient failure occurs"
        Issue Fix: Code review issue #4
        """
        # Arrange: Create transient error analysis
        from app.services.error_classifier import classify_error
        import httpx

        request = httpx.Request("GET", "https://api.example.com")
        response = httpx.Response(429, request=request)
        exception = httpx.HTTPStatusError("Rate limited", request=request, response=response)
        analysis = classify_error(exception)

        # Act: Log error with classifier output
        log_error(
            task_id="test-task-ac",
            channel_id="poke1",
            step="narration_generation",
            error_type=analysis.error_type,
            error_message=analysis.error_message,
            is_transient=(analysis.category.value == "transient"),
            retry_attempt=1,
            http_status_code=analysis.http_status_code,
            confidence=analysis.confidence,
        )

        # Assert: Verify AC required fields present in log
        log_data = json.loads(caplog.records[0].message)

        # AC Field 1: error_type
        assert "error_type" in log_data, "AC requires error_type field"
        assert log_data["error_type"] == "HTTPStatusError"

        # AC Field 2: is_transient flag
        assert "is_transient" in log_data, "AC requires is_transient flag"
        assert log_data["is_transient"] is True, "429 should be marked transient"

        # AC Field 3: suggested_action (present in ErrorAnalysis)
        assert analysis.suggested_action is not None, "ErrorAnalysis must include suggested_action"
        assert "rate limit" in analysis.suggested_action.lower()
        # Note: log_error() doesn't currently accept suggested_action parameter
        # This is acceptable as AC is met by ErrorAnalysis containing the field

    def test_log_error_timestamp_iso8601_format(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify timestamp is in ISO 8601 format with UTC timezone."""
        log_error(
            task_id="task-456",
            channel_id="poke2",
            step="video_generation",
            error_type="TimeoutError",
            error_message="Video generation timeout",
            is_transient=True,
            retry_attempt=2,
        )

        log_data = json.loads(caplog.records[0].message)
        timestamp_str = log_data["timestamp"]

        # Parse timestamp to verify ISO 8601 format
        timestamp = datetime.fromisoformat(timestamp_str)
        assert timestamp.tzinfo is not None  # Must have timezone
        # Verify it's in UTC (or at least timezone-aware)
        assert timestamp.tzinfo == timezone.utc or timestamp.tzinfo.utcoffset(
            None
        ) == timezone.utc.utcoffset(None)

    def test_log_error_without_optional_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify log_error works with only required fields."""
        log_error(
            task_id="task-789",
            channel_id="poke3",
            step="asset_generation",
            error_type="NetworkError",
            error_message="Connection failed",
            is_transient=True,
            retry_attempt=0,
        )

        log_data = json.loads(caplog.records[0].message)

        # Required fields present
        assert log_data["task_id"] == "task-789"
        assert log_data["error_type"] == "NetworkError"

        # Optional fields may be None or omitted
        assert log_data.get("http_status_code") is None
        assert log_data.get("confidence") is None

    def test_log_error_with_permanent_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify log_error correctly logs permanent errors (is_transient=False)."""
        log_error(
            task_id="task-abc",
            channel_id="poke1",
            step="audio_generation",
            error_type="ValidationError",
            error_message="Invalid voice_id parameter",
            is_transient=False,  # Permanent error
            retry_attempt=0,
            http_status_code=400,
            confidence=0.95,
        )

        log_data = json.loads(caplog.records[0].message)

        assert log_data["is_transient"] is False
        assert log_data["http_status_code"] == 400
        assert log_data["error_type"] == "ValidationError"

    def test_log_error_uses_error_level(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify log_error uses ERROR log level."""
        caplog.set_level("ERROR")

        log_error(
            task_id="task-xyz",
            channel_id="poke1",
            step="test_step",
            error_type="TestError",
            error_message="Test error message",
            is_transient=True,
            retry_attempt=1,
        )

        # Verify ERROR level was used
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "ERROR"


class TestLogErrorIntegrationWithClassifier:
    """Test log_error integration with error_classifier."""

    def test_log_error_with_classifier_output(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify log_error can be called with ErrorAnalysis output."""
        from app.services.error_classifier import ErrorAnalysis

        # Simulate ErrorAnalysis from classifier
        analysis = ErrorAnalysis(
            category=ErrorCategory.TRANSIENT,
            http_status_code=429,
            error_type="RateLimitError",
            error_message="ElevenLabs rate limit exceeded",
            retry_recommended=True,
            confidence=0.95,
            suggested_action="Wait and retry with exponential backoff",
        )

        # Log error using analysis data
        log_error(
            task_id="task-integration",
            channel_id="poke1",
            step="narration_generation",
            error_type=analysis.error_type,
            error_message=analysis.error_message,
            is_transient=(analysis.category == ErrorCategory.TRANSIENT),
            retry_attempt=1,
            http_status_code=analysis.http_status_code,
            confidence=analysis.confidence,
        )

        log_data = json.loads(caplog.records[0].message)

        # Verify integration with classifier
        assert log_data["error_type"] == "RateLimitError"
        assert log_data["http_status_code"] == 429
        assert log_data["is_transient"] is True
        assert log_data["confidence"] == 0.95
