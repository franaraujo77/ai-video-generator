"""Tests for error classifier with context and API service extraction (Story 6.4, Task 2).

Tests cover:
- ErrorContext creation
- API service extraction from context step_name
- API service extraction from exception message
- API service extraction fallback to "Unknown"
- classify_error() with optional context parameter
"""

import httpx
import pytest

from app.services.error_classifier import (
    ErrorCategory,
    ErrorContext,
    classify_error,
    _extract_api_service,
)
from app.utils.cli_wrapper import CLIScriptError


class TestErrorContext:
    """Test ErrorContext data structure."""

    def test_creates_context_with_clip_location(self):
        """ErrorContext stores clip index and total clips."""
        context = ErrorContext(
            step_name="video_generation",
            task_id="12345678-1234-1234-1234-123456789abc",
            channel_id="poke1",
            clip_index=11,
            total_clips=18,
        )

        assert context.step_name == "video_generation"
        assert context.clip_index == 11
        assert context.total_clips == 18

    def test_creates_context_with_asset_location(self):
        """ErrorContext stores asset index, total assets, and asset name."""
        context = ErrorContext(
            step_name="asset_generation",
            task_id="12345678-1234-1234-1234-123456789abc",
            channel_id="poke1",
            asset_index=15,
            total_assets=22,
            asset_name="environment_background_3.png",
        )

        assert context.step_name == "asset_generation"
        assert context.asset_index == 15
        assert context.total_assets == 22
        assert context.asset_name == "environment_background_3.png"


class TestAPIServiceExtraction:
    """Test API service identification from exception and context."""

    def test_extracts_service_from_video_generation_context(self):
        """Video generation context maps to KIE.ai."""
        context = ErrorContext(step_name="video_generation", task_id="123", channel_id="poke1")

        service = _extract_api_service(Exception("timeout"), context)

        assert service == "KIE.ai"

    def test_extracts_service_from_asset_generation_context(self):
        """Asset generation context maps to Gemini."""
        context = ErrorContext(step_name="asset_generation", task_id="123", channel_id="poke1")

        service = _extract_api_service(Exception("401"), context)

        assert service == "Gemini"

    def test_extracts_service_from_narration_generation_context(self):
        """Narration generation context maps to ElevenLabs."""
        context = ErrorContext(step_name="narration_generation", task_id="123", channel_id="poke1")

        service = _extract_api_service(Exception("quota exceeded"), context)

        assert service == "ElevenLabs"

    def test_extracts_service_from_sfx_generation_context(self):
        """SFX generation context maps to ElevenLabs."""
        context = ErrorContext(step_name="sfx_generation", task_id="123", channel_id="poke1")

        service = _extract_api_service(Exception("rate limit"), context)

        assert service == "ElevenLabs"

    def test_extracts_service_from_notion_sync_context(self):
        """Notion sync context maps to Notion."""
        context = ErrorContext(step_name="notion_sync", task_id="123", channel_id="poke1")

        service = _extract_api_service(Exception("API error"), context)

        assert service == "Notion"

    def test_extracts_service_from_youtube_upload_context(self):
        """YouTube upload context maps to YouTube."""
        context = ErrorContext(step_name="youtube_upload", task_id="123", channel_id="poke1")

        service = _extract_api_service(Exception("quota exceeded"), context)

        assert service == "YouTube"

    def test_extracts_kie_from_exception_message(self):
        """KIE.ai identified from exception message."""
        service = _extract_api_service(Exception("KIE.ai timeout after 600s"))

        assert service == "KIE.ai"

    def test_extracts_kling_from_exception_message(self):
        """Kling identified as KIE.ai from exception message."""
        service = _extract_api_service(Exception("Kling video generation failed"))

        assert service == "KIE.ai"

    def test_extracts_gemini_from_exception_message(self):
        """Gemini identified from exception message."""
        service = _extract_api_service(Exception("Gemini API error: 401 Unauthorized"))

        assert service == "Gemini"

    def test_extracts_google_generativeai_from_exception_message(self):
        """google.generativeai identified as Gemini."""
        service = _extract_api_service(Exception("google.generativeai.types.GenerationError"))

        assert service == "Gemini"

    def test_extracts_elevenlabs_from_exception_message(self):
        """ElevenLabs identified from exception message."""
        service = _extract_api_service(Exception("ElevenLabs quota exceeded"))

        assert service == "ElevenLabs"

    def test_extracts_notion_from_exception_message(self):
        """Notion identified from exception message."""
        service = _extract_api_service(Exception("Notion API rate limit"))

        assert service == "Notion"

    def test_extracts_youtube_from_exception_message(self):
        """YouTube identified from exception message."""
        service = _extract_api_service(Exception("YouTube quota exceeded"))

        assert service == "YouTube"

    def test_returns_unknown_for_generic_exception(self):
        """Unknown service for generic exception with no context."""
        service = _extract_api_service(Exception("Generic error"))

        assert service == "Unknown"

    def test_returns_http_client_for_httpx_exceptions(self):
        """HTTP Client for generic httpx exceptions without specific API."""
        request = httpx.Request("GET", "https://unknown-api.com")
        exception = httpx.ConnectError("Connection refused")

        service = _extract_api_service(exception)

        assert service == "HTTP Client"


class TestClassifyErrorWithContext:
    """Test classify_error() with optional context parameter."""

    def test_classify_error_accepts_context(self):
        """classify_error() accepts optional ErrorContext."""
        context = ErrorContext(
            step_name="video_generation",
            task_id="123",
            channel_id="poke1",
            clip_index=11,
            total_clips=18,
        )

        request = httpx.Request("GET", "https://api.example.com")
        response = httpx.Response(429, request=request)
        exception = httpx.HTTPStatusError("Rate limited", request=request, response=response)

        analysis = classify_error(exception, context)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.api_service == "KIE.ai"  # From context

    def test_classify_error_without_context_still_works(self):
        """classify_error() works without context (backwards compatible)."""
        request = httpx.Request("GET", "https://api.example.com")
        response = httpx.Response(500, request=request)
        exception = httpx.HTTPStatusError("Server error", request=request, response=response)

        analysis = classify_error(exception)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.api_service == "HTTP Client"  # Fallback

    def test_context_overrides_message_parsing(self):
        """Context step_name takes priority over exception message parsing."""
        context = ErrorContext(
            step_name="asset_generation",  # Maps to Gemini
            task_id="123",
            channel_id="poke1",
        )

        # Exception message says "KIE.ai" but context says "asset_generation" (Gemini)
        exception = Exception("KIE.ai error")

        service = _extract_api_service(exception, context)

        assert service == "Gemini"  # Context wins

    def test_cli_script_error_with_context(self):
        """CLI script error with context extracts API service."""
        context = ErrorContext(
            step_name="video_generation",
            task_id="123",
            channel_id="poke1",
            clip_index=5,
            total_clips=18,
        )

        exception = CLIScriptError(
            script="generate_video.py", exit_code=1, stderr="Error: 429 Rate limit exceeded"
        )

        analysis = classify_error(exception, context)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.http_status_code == 429
        assert analysis.api_service == "KIE.ai"

    def test_timeout_with_narration_context(self):
        """Timeout exception with narration context identifies ElevenLabs."""
        context = ErrorContext(
            step_name="narration_generation",
            task_id="123",
            channel_id="poke1",
            clip_index=7,
            total_clips=18,
        )

        exception = httpx.TimeoutException("Request timeout")

        analysis = classify_error(exception, context)

        assert analysis.category == ErrorCategory.TRANSIENT
        assert analysis.api_service == "ElevenLabs"
