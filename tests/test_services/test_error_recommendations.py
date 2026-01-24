"""Tests for error recommendations (Story 6.4, Task 6).

Tests cover:
- Configuration error recommendations (API keys, credentials)
- Transient error recommendations (retry in progress, timeouts)
- Quota exceeded recommendations (check usage limits)
- Permanent error recommendations (manual investigation)
- API-specific recommendations (Gemini, KIE.ai, ElevenLabs, YouTube, Notion)
"""

import pytest

from app.services.error_classifier import ErrorAnalysis, ErrorCategory
from app.services.error_recommendations import get_error_recommendation


class TestConfigurationRecommendations:
    """Test recommendations for configuration errors (API keys, auth)."""

    def test_recommends_check_gemini_api_key(self):
        """Gemini 401 recommends checking GEMINI_API_KEY."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.CONFIGURATION,
            http_status_code=401,
            error_type="HTTPStatusError",
            error_message="Unauthorized",
            retry_recommended=False,
            confidence=0.95,
            suggested_action="Unauthorized - check API key/credentials",
            api_service="Gemini",
        )

        recommendation = get_error_recommendation(analysis)

        assert "GEMINI_API_KEY" in recommendation
        assert "channel config" in recommendation

    def test_recommends_check_kie_api_key(self):
        """KIE.ai 401 recommends checking KIE_API_KEY."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.CONFIGURATION,
            http_status_code=401,
            error_type="HTTPStatusError",
            error_message="Unauthorized",
            retry_recommended=False,
            confidence=0.95,
            suggested_action="Unauthorized - check API key/credentials",
            api_service="KIE.ai",
        )

        recommendation = get_error_recommendation(analysis)

        assert "KIE_API_KEY" in recommendation
        assert "subscription" in recommendation

    def test_recommends_check_elevenlabs_api_key(self):
        """ElevenLabs 401 recommends checking ELEVENLABS_API_KEY."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.CONFIGURATION,
            http_status_code=401,
            error_type="HTTPStatusError",
            error_message="Unauthorized",
            retry_recommended=False,
            confidence=0.95,
            suggested_action="Unauthorized - check API key/credentials",
            api_service="ElevenLabs",
        )

        recommendation = get_error_recommendation(analysis)

        assert "ELEVENLABS_API_KEY" in recommendation

    def test_recommends_reauth_youtube(self):
        """YouTube 401 recommends re-running OAuth setup."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.CONFIGURATION,
            http_status_code=401,
            error_type="HTTPStatusError",
            error_message="Unauthorized",
            retry_recommended=False,
            confidence=0.95,
            suggested_action="Unauthorized - check API key/credentials",
            api_service="YouTube",
        )

        recommendation = get_error_recommendation(analysis)

        assert "OAuth" in recommendation
        assert "setup_channel_oauth.py" in recommendation


class TestTransientRecommendations:
    """Test recommendations for transient errors (retry in progress)."""

    def test_recommends_retry_for_kie_timeout(self):
        """KIE.ai timeout recommends simpler prompts if recurring."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.TRANSIENT,
            http_status_code=None,
            error_type="TimeoutException",
            error_message="Timeout",
            retry_recommended=True,
            confidence=0.85,
            suggested_action="Network timeout - retry with longer timeout",
            api_service="KIE.ai",
        )

        recommendation = get_error_recommendation(analysis)

        assert "retry in progress" in recommendation
        assert "simpler prompts" in recommendation.lower()

    def test_recommends_retry_for_generic_timeout(self):
        """Generic timeout recommends exponential backoff."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.TRANSIENT,
            http_status_code=None,
            error_type="TimeoutException",
            error_message="Timeout",
            retry_recommended=True,
            confidence=0.85,
            suggested_action="Network timeout - retry with longer timeout",
            api_service="Gemini",
        )

        recommendation = get_error_recommendation(analysis)

        assert "retry" in recommendation.lower()
        assert "backoff" in recommendation.lower()

    def test_recommends_automatic_backoff_for_rate_limit(self):
        """Rate limit recommends automatic backoff."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.TRANSIENT,
            http_status_code=429,
            error_type="HTTPStatusError",
            error_message="Rate limited",
            retry_recommended=True,
            confidence=0.95,
            suggested_action="Rate limit exceeded - wait and retry with exponential backoff",
            api_service="ElevenLabs",
        )

        recommendation = get_error_recommendation(analysis)

        assert "rate limit" in recommendation.lower()
        assert "automatic backoff" in recommendation.lower()

    def test_recommends_retry_for_network_error(self):
        """Generic network error recommends automatic retry."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.TRANSIENT,
            http_status_code=None,
            error_type="NetworkError",
            error_message="Network error",
            retry_recommended=True,
            confidence=0.8,
            suggested_action="Network error - check connectivity",
            api_service="Unknown",
        )

        recommendation = get_error_recommendation(analysis)

        assert "retry in progress" in recommendation.lower()


class TestQuotaExceededRecommendations:
    """Test recommendations for quota exceeded errors."""

    def test_recommends_check_youtube_quota(self):
        """YouTube quota recommends waiting until tomorrow."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.QUOTA_EXCEEDED,
            http_status_code=429,
            error_type="HTTPStatusError",
            error_message="Quota exceeded",
            retry_recommended=False,
            confidence=0.95,
            suggested_action="Quota exceeded",
            api_service="YouTube",
        )

        recommendation = get_error_recommendation(analysis)

        assert "10,000 units" in recommendation
        assert "tomorrow" in recommendation.lower()

    def test_recommends_check_elevenlabs_quota(self):
        """ElevenLabs quota recommends checking dashboard."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.QUOTA_EXCEEDED,
            http_status_code=429,
            error_type="HTTPStatusError",
            error_message="Quota exceeded",
            retry_recommended=False,
            confidence=0.95,
            suggested_action="Quota exceeded",
            api_service="ElevenLabs",
        )

        recommendation = get_error_recommendation(analysis)

        assert "character limit" in recommendation.lower()
        assert "dashboard" in recommendation.lower()

    def test_recommends_check_kie_quota(self):
        """KIE.ai quota recommends checking credit balance."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.QUOTA_EXCEEDED,
            http_status_code=429,
            error_type="HTTPStatusError",
            error_message="Quota exceeded",
            retry_recommended=False,
            confidence=0.95,
            suggested_action="Quota exceeded",
            api_service="KIE.ai",
        )

        recommendation = get_error_recommendation(analysis)

        assert "credit balance" in recommendation.lower()
        assert "upgrade" in recommendation.lower()


class TestPermanentRecommendations:
    """Test recommendations for permanent errors (manual investigation)."""

    def test_recommends_review_prompt_for_validation_error(self):
        """Prompt validation error recommends reviewing inputs."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.PERMANENT,
            http_status_code=400,
            error_type="HTTPStatusError",
            error_message="Invalid prompt",
            retry_recommended=False,
            confidence=0.95,
            suggested_action="Bad request - invalid prompt",
            api_service="Gemini",
        )

        recommendation = get_error_recommendation(analysis)

        assert "prompt" in recommendation.lower()
        assert "review" in recommendation.lower()

    def test_recommends_check_filesystem_for_file_error(self):
        """File operation error recommends checking permissions."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.PERMANENT,
            http_status_code=None,
            error_type="OSError",
            error_message="File not found",
            retry_recommended=False,
            confidence=0.9,
            suggested_action="File operation failed",
            api_service="Unknown",
        )

        recommendation = get_error_recommendation(analysis)

        assert "file" in recommendation.lower() or "File" in recommendation
        assert "permissions" in recommendation.lower() or "disk space" in recommendation.lower()

    def test_recommends_manual_investigation_for_unknown_permanent(self):
        """Unknown permanent error recommends manual investigation."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.PERMANENT,
            http_status_code=422,
            error_type="HTTPStatusError",
            error_message="Unprocessable entity",
            retry_recommended=False,
            confidence=0.95,
            suggested_action="Unprocessable entity - check data format",
            api_service="Unknown",
        )

        recommendation = get_error_recommendation(analysis)

        assert "manual investigation" in recommendation.lower()
        assert "error log" in recommendation.lower()


class TestDefaultRecommendations:
    """Test fallback recommendations for unknown error categories."""

    def test_returns_generic_recommendation_for_unknown_category(self):
        """Unknown error category returns generic recommendation."""
        analysis = ErrorAnalysis(
            category=ErrorCategory.UNKNOWN,
            http_status_code=None,
            error_type="GenericError",
            error_message="Something went wrong",
            retry_recommended=True,
            confidence=0.3,
            suggested_action="Unknown error - investigate",
            api_service="Unknown",
        )

        recommendation = get_error_recommendation(analysis)

        assert "error details" in recommendation.lower()
        assert "logs" in recommendation.lower()
