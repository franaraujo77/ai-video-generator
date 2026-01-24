"""Tests for centralized error classification service.

This module tests the error_classifier service which categorizes errors
as transient (retry), permanent (fail fast), or unknown (conservative retry).

Story Reference: 6.1 - Transient Failure Detection
"""

import httpx
import pytest

from app.services.error_classifier import (
    ErrorAnalysis,
    ErrorCategory,
    classify_error,
)
from app.utils.cli_wrapper import CLIScriptError


class TestTransientErrorDetection:
    """Test detection of transient errors (retriable)."""

    def test_classify_rate_limit_429(self) -> None:
        """Verify 429 errors classified as TRANSIENT with high confidence."""
        # Create HTTP 429 error
        request = httpx.Request("GET", "https://api.example.com")
        response = httpx.Response(429, request=request)
        exception = httpx.HTTPStatusError("Rate limited", request=request, response=response)

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.retry_recommended is True
        assert analysis.http_status_code == 429
        assert analysis.confidence >= 0.9
        assert "rate limit" in analysis.suggested_action.lower()
        assert analysis.error_type == "HTTPStatusError"

    def test_classify_server_error_500(self) -> None:
        """Verify 500 errors classified as TRANSIENT."""
        request = httpx.Request("POST", "https://api.example.com")
        response = httpx.Response(500, request=request)
        exception = httpx.HTTPStatusError(
            "Internal Server Error", request=request, response=response
        )

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.retry_recommended is True
        assert analysis.http_status_code == 500
        assert analysis.confidence >= 0.9

    def test_classify_server_error_502(self) -> None:
        """Verify 502 Bad Gateway classified as TRANSIENT."""
        request = httpx.Request("GET", "https://api.example.com")
        response = httpx.Response(502, request=request)
        exception = httpx.HTTPStatusError("Bad Gateway", request=request, response=response)

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.http_status_code == 502

    def test_classify_server_error_503(self) -> None:
        """Verify 503 Service Unavailable classified as TRANSIENT."""
        request = httpx.Request("GET", "https://api.example.com")
        response = httpx.Response(503, request=request)
        exception = httpx.HTTPStatusError("Service Unavailable", request=request, response=response)

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.http_status_code == 503

    def test_classify_server_error_504(self) -> None:
        """Verify 504 Gateway Timeout classified as TRANSIENT."""
        request = httpx.Request("GET", "https://api.example.com")
        response = httpx.Response(504, request=request)
        exception = httpx.HTTPStatusError("Gateway Timeout", request=request, response=response)

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.http_status_code == 504

    def test_classify_timeout_exception(self) -> None:
        """Verify httpx.TimeoutException classified as TRANSIENT."""
        exception = httpx.TimeoutException("Request timed out")

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.retry_recommended is True
        assert analysis.http_status_code is None
        assert analysis.confidence >= 0.8
        assert "timeout" in analysis.error_type.lower()

    def test_classify_connect_timeout(self) -> None:
        """Verify httpx.ConnectTimeout classified as TRANSIENT."""
        exception = httpx.ConnectTimeout("Connection timed out")

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.retry_recommended is True

    def test_classify_read_timeout(self) -> None:
        """Verify httpx.ReadTimeout classified as TRANSIENT."""
        exception = httpx.ReadTimeout("Read timed out")

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.TRANSIENT

    def test_classify_connect_error(self) -> None:
        """Verify httpx.ConnectError classified as TRANSIENT."""
        exception = httpx.ConnectError("Failed to connect")

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.retry_recommended is True

    def test_classify_network_error(self) -> None:
        """Verify httpx.NetworkError classified as TRANSIENT."""
        exception = httpx.NetworkError("Network unreachable")

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.TRANSIENT


class TestPermanentErrorDetection:
    """Test detection of permanent errors (fail fast)."""

    def test_classify_bad_request_400(self) -> None:
        """Verify 400 errors classified as PERMANENT with high confidence."""
        request = httpx.Request("POST", "https://api.example.com")
        response = httpx.Response(400, request=request)
        exception = httpx.HTTPStatusError("Bad request", request=request, response=response)

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.PERMANENT
        assert analysis.retry_recommended is False
        assert analysis.http_status_code == 400
        assert analysis.confidence >= 0.95
        assert (
            "fix" in analysis.suggested_action.lower()
            or "check" in analysis.suggested_action.lower()
        )

    def test_classify_unauthorized_401(self) -> None:
        """Verify 401 errors classified as CONFIGURATION (Story 6.4)."""
        request = httpx.Request("GET", "https://api.example.com")
        response = httpx.Response(401, request=request)
        exception = httpx.HTTPStatusError("Unauthorized", request=request, response=response)

        analysis = classify_error(exception)

        assert (
            analysis.category == ErrorCategory.CONFIGURATION
        )  # Story 6.4: 401/403 are CONFIGURATION
        assert analysis.retry_recommended is False
        assert analysis.http_status_code == 401
        assert analysis.confidence >= 0.95

    def test_classify_forbidden_403(self) -> None:
        """Verify 403 errors classified as CONFIGURATION (Story 6.4)."""
        request = httpx.Request("GET", "https://api.example.com")
        response = httpx.Response(403, request=request)
        exception = httpx.HTTPStatusError("Forbidden", request=request, response=response)

        analysis = classify_error(exception)

        assert (
            analysis.category == ErrorCategory.CONFIGURATION
        )  # Story 6.4: 401/403 are CONFIGURATION
        assert analysis.http_status_code == 403

    def test_classify_not_found_404(self) -> None:
        """Verify 404 errors classified as PERMANENT."""
        request = httpx.Request("GET", "https://api.example.com")
        response = httpx.Response(404, request=request)
        exception = httpx.HTTPStatusError("Not found", request=request, response=response)

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.PERMANENT
        assert analysis.http_status_code == 404

    def test_classify_unprocessable_entity_422(self) -> None:
        """Verify 422 errors classified as PERMANENT."""
        request = httpx.Request("POST", "https://api.example.com")
        response = httpx.Response(422, request=request)
        exception = httpx.HTTPStatusError(
            "Unprocessable Entity", request=request, response=response
        )

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.PERMANENT
        assert analysis.http_status_code == 422


class TestUnknownErrorHandling:
    """Test handling of unknown errors (conservative retry)."""

    def test_classify_generic_exception(self) -> None:
        """Verify generic exceptions classified as UNKNOWN with low confidence."""
        exception = ValueError("Something went wrong")

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.UNKNOWN
        assert analysis.retry_recommended is True  # Conservative retry
        assert analysis.confidence <= 0.5
        assert analysis.http_status_code is None

    def test_classify_runtime_error(self) -> None:
        """Verify RuntimeError classified as UNKNOWN."""
        exception = RuntimeError("Unexpected runtime error")

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.UNKNOWN
        assert analysis.retry_recommended is True

    def test_classify_key_error(self) -> None:
        """Verify KeyError classified as UNKNOWN."""
        exception = KeyError("missing_key")

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.UNKNOWN


class TestCLIScriptErrorParsing:
    """Test parsing CLI script stderr for HTTP status codes."""

    def test_classify_cli_script_error_429(self) -> None:
        """Verify CLIScriptError with 429 in stderr classified as TRANSIENT."""
        cli_error = CLIScriptError(
            script="generate_audio.py",
            exit_code=1,
            stderr="HTTP Error 429: Rate limit exceeded",
        )

        analysis = classify_error(cli_error)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.http_status_code == 429
        assert analysis.retry_recommended is True

    def test_classify_cli_script_error_500(self) -> None:
        """Verify CLIScriptError with 500 in stderr classified as TRANSIENT."""
        cli_error = CLIScriptError(
            script="generate_video.py",
            exit_code=1,
            stderr="Server returned HTTP 500: Internal Server Error",
        )

        analysis = classify_error(cli_error)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.http_status_code == 500

    def test_classify_cli_script_error_401(self) -> None:
        """Verify CLIScriptError with 401 in stderr classified as CONFIGURATION (Story 6.4)."""
        cli_error = CLIScriptError(
            script="generate_asset.py",
            exit_code=1,
            stderr="HTTP 401: Unauthorized - check API key",
        )

        analysis = classify_error(cli_error)

        assert (
            analysis.category == ErrorCategory.CONFIGURATION
        )  # Story 6.4: 401/403 are CONFIGURATION
        assert analysis.http_status_code == 401
        assert analysis.retry_recommended is False

    def test_classify_cli_script_timeout(self) -> None:
        """Verify CLIScriptError with timeout keyword classified as TRANSIENT."""
        cli_error = CLIScriptError(
            script="generate_video.py",
            exit_code=1,
            stderr="Request timeout: operation took too long",
        )

        analysis = classify_error(cli_error)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.retry_recommended is True

    def test_classify_cli_script_rate_limit_text(self) -> None:
        """Verify CLIScriptError with 'rate limit' text classified as TRANSIENT."""
        cli_error = CLIScriptError(
            script="generate_audio.py",
            exit_code=1,
            stderr="ElevenLabs rate limit exceeded, please try again later",
        )

        analysis = classify_error(cli_error)

        assert analysis.category == ErrorCategory.TRANSIENT


class TestErrorAnalysisStructure:
    """Test ErrorAnalysis dataclass structure and fields."""

    def test_error_analysis_has_required_fields(self) -> None:
        """Verify ErrorAnalysis contains all required fields."""
        request = httpx.Request("GET", "https://api.example.com")
        response = httpx.Response(429, request=request)
        exception = httpx.HTTPStatusError("Rate limited", request=request, response=response)

        analysis = classify_error(exception)

        # Verify all fields exist
        assert hasattr(analysis, "category")
        assert hasattr(analysis, "http_status_code")
        assert hasattr(analysis, "error_type")
        assert hasattr(analysis, "error_message")
        assert hasattr(analysis, "retry_recommended")
        assert hasattr(analysis, "confidence")
        assert hasattr(analysis, "suggested_action")

        # Verify field types
        assert isinstance(analysis.category, ErrorCategory)
        assert analysis.http_status_code is None or isinstance(analysis.http_status_code, int)
        assert isinstance(analysis.error_type, str)
        assert isinstance(analysis.error_message, str)
        assert isinstance(analysis.retry_recommended, bool)
        assert isinstance(analysis.confidence, float)
        assert isinstance(analysis.suggested_action, str)

    def test_confidence_within_valid_range(self) -> None:
        """Verify confidence scores are between 0.0 and 1.0."""
        test_cases = [
            httpx.HTTPStatusError(
                "",
                request=httpx.Request("GET", "https://api.example.com"),
                response=httpx.Response(429),
            ),
            httpx.HTTPStatusError(
                "",
                request=httpx.Request("GET", "https://api.example.com"),
                response=httpx.Response(400),
            ),
            httpx.TimeoutException("timeout"),
            ValueError("unknown error"),
        ]

        for exception in test_cases:
            analysis = classify_error(exception)
            assert 0.0 <= analysis.confidence <= 1.0, (
                f"Confidence out of range: {analysis.confidence}"
            )


class TestErrorClassifierRobustness:
    """Test error classifier never crashes (graceful degradation)."""

    def test_classify_error_never_raises(self) -> None:
        """Verify classify_error never raises exceptions (returns UNKNOWN instead)."""
        # Edge cases that might cause crashes
        edge_cases = [
            None,  # type: ignore
            Exception(),
            Exception(""),
            ValueError(),
            TypeError("bad type"),
            KeyError("missing"),
        ]

        for exception in edge_cases:
            try:
                analysis = classify_error(exception)  # type: ignore
                # Should return UNKNOWN for unexpected inputs
                assert analysis.category == ErrorCategory.UNKNOWN
            except Exception as e:
                pytest.fail(f"classify_error raised exception for {exception}: {e}")
