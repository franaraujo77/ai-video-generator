"""Tests for ErrorPayload and FailureLocation (Story 6.4, Task 1).

Tests cover:
- FailureLocation formatting (clip/asset index, item names)
- ErrorPayload creation and validation
- format_for_notion() markdown generation
- Partial progress formatting (video clips, assets, narration, SFX)
- Multi-retry history formatting
- Recommendation inclusion
"""

from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.schemas.error_payload import ErrorPayload, FailureLocation


class TestFailureLocation:
    """Test FailureLocation data structure and formatting."""

    def test_formats_video_clip_location(self):
        """Video generation failure shows 'Item 11 of 18'."""
        location = FailureLocation(step_name="video_generation", item_index=11, total_items=18)

        formatted = location.format()

        assert "Item 11 of 18" in formatted
        assert "Video Generation" in formatted

    def test_formats_asset_location_with_name(self):
        """Asset generation failure shows index + asset name."""
        location = FailureLocation(
            step_name="asset_generation",
            item_index=15,
            total_items=22,
            item_name="environment_background_3.png",
        )

        formatted = location.format()

        assert "Item 15 of 22" in formatted
        assert "environment_background_3.png" in formatted
        assert "Asset Generation" in formatted

    def test_formats_step_without_index(self):
        """Step-level failure without item index shows step name only."""
        location = FailureLocation(step_name="narration_generation")

        formatted = location.format()

        assert formatted == "Narration Generation"

    def test_converts_snake_case_to_title_case(self):
        """Step names converted from snake_case to Title Case."""
        location = FailureLocation(step_name="sound_effects_generation")

        formatted = location.format()

        assert formatted == "Sound Effects Generation"


class TestErrorPayload:
    """Test ErrorPayload data structure and Notion formatting."""

    def test_creates_error_payload_with_all_fields(self):
        """ErrorPayload validates all required and optional fields."""
        location = FailureLocation(step_name="video_generation", item_index=11, total_items=18)

        payload = ErrorPayload(
            timestamp=datetime(2026, 1, 18, 14, 25, 0, tzinfo=timezone.utc),
            correlation_id=UUID("12345678-1234-1234-1234-123456789abc"),
            step_name="video_generation",
            failure_location=location,
            error_category="TRANSIENT",
            error_message="KIE.ai API timeout after 600s",
            api_service="KIE.ai",
            retry_attempt=2,
            next_retry_at=datetime(2026, 1, 18, 14, 26, 0, tzinfo=timezone.utc),
            partial_progress={"completed_video_clips": list(range(1, 11)), "total_clips": 18},
            recommendation="Video generation timeout - retry in progress",
        )

        assert payload.step_name == "video_generation"
        assert payload.error_category == "TRANSIENT"
        assert payload.retry_attempt == 2
        assert payload.api_service == "KIE.ai"

    def test_formats_transient_error_for_notion(self):
        """Transient error shows retry information and progress."""
        location = FailureLocation(step_name="video_generation", item_index=11, total_items=18)

        payload = ErrorPayload(
            timestamp=datetime(2026, 1, 18, 14, 25, 0, tzinfo=timezone.utc),
            correlation_id=UUID("12345678-1234-1234-1234-123456789abc"),
            step_name="video_generation",
            failure_location=location,
            error_category="TRANSIENT",
            error_message="KIE.ai API timeout after 600s",
            api_service="KIE.ai",
            retry_attempt=2,
            next_retry_at=datetime(2026, 1, 18, 14, 26, 0, tzinfo=timezone.utc),
            partial_progress={"completed_video_clips": list(range(1, 11)), "total_clips": 18},
            recommendation="Video generation timeout - retry in progress",
        )

        formatted = payload.format_for_notion()

        # Verify all required fields present
        assert "[2026-01-18 14:25:00]" in formatted
        assert "video_generation failed" in formatted
        assert "Item 11 of 18" in formatted
        assert "KIE.ai API timeout" in formatted
        assert "TRANSIENT" in formatted
        assert "KIE.ai" in formatted
        assert "2026-01-18 14:26:00" in formatted  # Next retry timestamp
        assert "Attempt 3/5" in formatted
        assert "10 of 18 clips completed" in formatted
        assert "retry in progress" in formatted

    def test_formats_terminal_failure_for_notion(self):
        """Terminal failure shows attempt count, no next retry."""
        location = FailureLocation(
            step_name="asset_generation",
            item_index=15,
            total_items=22,
            item_name="environment_background_3.png",
        )

        payload = ErrorPayload(
            timestamp=datetime(2026, 1, 18, 10, 0, 0, tzinfo=timezone.utc),
            correlation_id=UUID("12345678-1234-1234-1234-123456789abc"),
            step_name="asset_generation",
            failure_location=location,
            error_category="CONFIGURATION",
            error_message="Authentication failed (401 Unauthorized)",
            api_service="Gemini",
            retry_attempt=5,
            next_retry_at=None,  # Terminal failure
            partial_progress={"completed_assets": list(range(1, 15)), "total_assets": 22},
            recommendation="Check GEMINI_API_KEY in channel config",
        )

        formatted = payload.format_for_notion()

        # Verify terminal failure fields
        assert "Terminal failure after 5 attempts" in formatted
        assert "Next retry" not in formatted  # No next retry for terminal failure
        assert "14 of 22 assets completed" in formatted
        assert "Check GEMINI_API_KEY" in formatted

    def test_formats_progress_for_video_clips(self):
        """Video clip progress formatted as '10 of 18 clips completed'."""
        payload = ErrorPayload(
            timestamp=datetime.now(timezone.utc),
            correlation_id=UUID("12345678-1234-1234-1234-123456789abc"),
            step_name="video_generation",
            failure_location=FailureLocation(step_name="video_generation"),
            error_category="TRANSIENT",
            error_message="Timeout",
            api_service="KIE.ai",
            retry_attempt=1,
            partial_progress={"completed_video_clips": list(range(1, 11)), "total_clips": 18},
        )

        progress_str = payload._format_progress(payload.partial_progress)

        assert progress_str == "10 of 18 clips completed"

    def test_formats_progress_for_assets(self):
        """Asset progress formatted as '15 of 22 assets completed'."""
        payload = ErrorPayload(
            timestamp=datetime.now(timezone.utc),
            correlation_id=UUID("12345678-1234-1234-1234-123456789abc"),
            step_name="asset_generation",
            failure_location=FailureLocation(step_name="asset_generation"),
            error_category="TRANSIENT",
            error_message="Rate limit",
            api_service="Gemini",
            retry_attempt=1,
            partial_progress={"completed_assets": list(range(1, 16)), "total_assets": 22},
        )

        progress_str = payload._format_progress(payload.partial_progress)

        assert progress_str == "15 of 22 assets completed"

    def test_formats_progress_for_narration(self):
        """Narration progress formatted as '5 of 18 narration clips completed'."""
        payload = ErrorPayload(
            timestamp=datetime.now(timezone.utc),
            correlation_id=UUID("12345678-1234-1234-1234-123456789abc"),
            step_name="narration_generation",
            failure_location=FailureLocation(step_name="narration_generation"),
            error_category="TRANSIENT",
            error_message="Network error",
            api_service="ElevenLabs",
            retry_attempt=1,
            partial_progress={"completed_narration_clips": list(range(1, 6)), "total_clips": 18},
        )

        progress_str = payload._format_progress(payload.partial_progress)

        assert progress_str == "5 of 18 narration clips completed"

    def test_formats_progress_for_sfx(self):
        """SFX progress formatted as '3 of 18 SFX clips completed'."""
        payload = ErrorPayload(
            timestamp=datetime.now(timezone.utc),
            correlation_id=UUID("12345678-1234-1234-1234-123456789abc"),
            step_name="sfx_generation",
            failure_location=FailureLocation(step_name="sfx_generation"),
            error_category="TRANSIENT",
            error_message="Timeout",
            api_service="ElevenLabs",
            retry_attempt=1,
            partial_progress={"completed_sfx_clips": list(range(1, 4)), "total_clips": 18},
        )

        progress_str = payload._format_progress(payload.partial_progress)

        assert progress_str == "3 of 18 SFX clips completed"

    def test_handles_empty_progress(self):
        """Empty progress dict returns empty string."""
        payload = ErrorPayload(
            timestamp=datetime.now(timezone.utc),
            correlation_id=UUID("12345678-1234-1234-1234-123456789abc"),
            step_name="video_generation",
            failure_location=FailureLocation(step_name="video_generation"),
            error_category="TRANSIENT",
            error_message="Error",
            api_service="KIE.ai",
            retry_attempt=1,
            partial_progress={},
        )

        progress_str = payload._format_progress(payload.partial_progress)

        assert progress_str == ""

    def test_excludes_progress_if_none(self):
        """Notion markdown excludes progress section if no progress."""
        location = FailureLocation(step_name="video_generation")

        payload = ErrorPayload(
            timestamp=datetime(2026, 1, 18, 14, 25, 0, tzinfo=timezone.utc),
            correlation_id=UUID("12345678-1234-1234-1234-123456789abc"),
            step_name="video_generation",
            failure_location=location,
            error_category="TRANSIENT",
            error_message="Timeout",
            api_service="KIE.ai",
            retry_attempt=1,
            next_retry_at=datetime(2026, 1, 18, 14, 26, 0, tzinfo=timezone.utc),
            partial_progress={},
        )

        formatted = payload.format_for_notion()

        assert "**Progress:**" not in formatted

    def test_excludes_recommendation_if_none(self):
        """Notion markdown excludes action section if no recommendation."""
        location = FailureLocation(step_name="video_generation")

        payload = ErrorPayload(
            timestamp=datetime(2026, 1, 18, 14, 25, 0, tzinfo=timezone.utc),
            correlation_id=UUID("12345678-1234-1234-1234-123456789abc"),
            step_name="video_generation",
            failure_location=location,
            error_category="TRANSIENT",
            error_message="Timeout",
            api_service="KIE.ai",
            retry_attempt=1,
            next_retry_at=datetime(2026, 1, 18, 14, 26, 0, tzinfo=timezone.utc),
            recommendation=None,
        )

        formatted = payload.format_for_notion()

        assert "**Action:**" not in formatted
