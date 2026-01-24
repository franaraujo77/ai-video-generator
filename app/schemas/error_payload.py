"""Structured error payloads for Notion sync and debugging (Story 6.4).

This module defines data structures for rich error information that combines:
- Error classification from Story 6.1 (error_classifier.py)
- Retry metadata from Story 6.2 (retry_orchestrator.py)
- Checkpoint progress from Story 6.3 (checkpoint_service.py)

ErrorPayload Format:
    Timestamp, correlation ID, step name, failure location (clip/asset index),
    error category, error message, API service, retry attempt, next retry time,
    partial progress from checkpoints, and actionable recommendations.

Architecture Pattern:
    - Pydantic dataclasses for validation and serialization
    - format_for_notion() generates Notion-compatible rich text markdown
    - Never instantiated during database transactions (build outside transaction)

Example:
    location = FailureLocation(
        step_name="video_generation",
        item_index=11,
        total_items=18
    )

    payload = ErrorPayload(
        timestamp=datetime.now(timezone.utc),
        correlation_id=UUID("..."),
        step_name="video_generation",
        failure_location=location,
        error_category="TRANSIENT",
        error_message="KIE.ai API timeout after 600s",
        api_service="KIE.ai",
        retry_attempt=2,
        next_retry_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        partial_progress={"completed_video_clips": [1, 2, ..., 10], "total_clips": 18},
        recommendation="Video generation timeout - retry in progress"
    )

    notion_markdown = payload.format_for_notion()
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class FailureLocation(BaseModel):
    """Structured failure location within pipeline step.

    Attributes:
        step_name: Pipeline step name (e.g., "video_generation", "asset_generation")
        item_index: Item index where failure occurred (e.g., 11 for clip 11)
        total_items: Total items in step (e.g., 18 for 18 total clips)
        item_name: Optional item name (e.g., "environment_background_3.png")

    Examples:
        >>> location = FailureLocation(step_name="video_generation", item_index=11, total_items=18)
        >>> location.format()
        'Video Generation: Item 11 of 18'

        >>> location = FailureLocation(
        ...     step_name="asset_generation",
        ...     item_index=15,
        ...     total_items=22,
        ...     item_name="environment_background_3.png",
        ... )
        >>> location.format()
        'Asset Generation: Item 15 of 22 (environment_background_3.png)'
    """

    step_name: str = Field(description="Pipeline step name")
    item_index: int | None = Field(default=None, description="Item index where failure occurred")
    total_items: int | None = Field(default=None, description="Total items in step")
    item_name: str | None = Field(default=None, description="Optional item name")

    def format(self) -> str:
        """Format location as human-readable string.

        Returns:
            Formatted location string (e.g., "Video Generation: Item 11 of 18")
        """
        # Convert snake_case to Title Case (video_generation -> Video Generation)
        step_display = self.step_name.replace("_", " ").title()

        if self.item_index is not None and self.total_items is not None:
            location = f"{step_display}: Item {self.item_index} of {self.total_items}"
            if self.item_name:
                location += f" ({self.item_name})"
            return location

        return step_display


class ErrorPayload(BaseModel):
    """Structured error information for Notion sync and debugging.

    This class combines error classification (Story 6.1), retry metadata (Story 6.2),
    and checkpoint progress (Story 6.3) into a single payload for Notion display.

    Attributes:
        timestamp: When error occurred (UTC)
        correlation_id: Request correlation ID for log tracing
        step_name: Pipeline step where failure occurred
        failure_location: Structured location (clip/asset index)
        error_category: Error classification (TRANSIENT, PERMANENT, CONFIGURATION, QUOTA_EXCEEDED)
        error_message: Original error message
        api_service: API service that failed (KIE.ai, Gemini, ElevenLabs, etc.)
        retry_attempt: Current retry attempt number (1-5)
        next_retry_at: When next retry scheduled (None if terminal failure)
        partial_progress: Checkpoint data (completed clips/assets)
        recommendation: Actionable next step for user

    Example:
        >>> payload = ErrorPayload(
        ...     timestamp=datetime(2026, 1, 18, 14, 25, 0, tzinfo=timezone.utc),
        ...     correlation_id=UUID("12345678-1234-1234-1234-123456789abc"),
        ...     step_name="video_generation",
        ...     failure_location=FailureLocation(
        ...         step_name="video_generation", item_index=11, total_items=18
        ...     ),
        ...     error_category="TRANSIENT",
        ...     error_message="KIE.ai API timeout after 600s",
        ...     api_service="KIE.ai",
        ...     retry_attempt=2,
        ...     next_retry_at=datetime(2026, 1, 18, 14, 26, 0, tzinfo=timezone.utc),
        ...     partial_progress={"completed_video_clips": list(range(1, 11)), "total_clips": 18},
        ...     recommendation="Video generation timeout - retry in progress",
        ... )
        >>> markdown = payload.format_for_notion()
        >>> "Clip 11 of 18" in markdown or "Item 11 of 18" in markdown
        True
    """

    timestamp: datetime = Field(description="When error occurred (UTC)")
    correlation_id: UUID = Field(description="Request correlation ID for log tracing")
    step_name: str = Field(description="Pipeline step where failure occurred")
    failure_location: FailureLocation = Field(description="Structured location (clip/asset index)")
    error_category: str = Field(
        description="Error classification (TRANSIENT, PERMANENT, CONFIGURATION, QUOTA_EXCEEDED)"
    )
    error_message: str = Field(description="Original error message")
    api_service: str = Field(
        description="API service that failed (KIE.ai, Gemini, ElevenLabs, etc.)"
    )
    retry_attempt: int = Field(description="Current retry attempt number (1-5)")
    next_retry_at: datetime | None = Field(
        default=None, description="When next retry scheduled (None if terminal)"
    )
    partial_progress: dict[str, Any] = Field(
        default_factory=dict, description="Checkpoint data (completed clips/assets)"
    )
    recommendation: str | None = Field(default=None, description="Actionable next step for user")

    def format_for_notion(self) -> str:
        """Format error payload as Notion rich text markdown.

        Generates multi-line markdown with:
        - Timestamp and step name
        - Failure location (e.g., "Clip 11 of 18")
        - Error category and message
        - API service
        - Retry information (next retry time or terminal status)
        - Partial progress (from checkpoints)
        - Actionable recommendation

        Returns:
            Notion-compatible markdown string

        Example:
            >>> payload = ErrorPayload(...)
            >>> markdown = payload.format_for_notion()
            >>> print(markdown)
            **[2026-01-18 14:25:00]** video_generation failed
            **Location:** Video Generation: Item 11 of 18
            **Error:** KIE.ai API timeout after 600s (TRANSIENT)
            **API:** KIE.ai
            **Next retry:** 2026-01-18 14:26:00 (Attempt 3/5)
            **Progress:** 10 of 18 clips completed
            **Action:** Video generation timeout - retry in progress
        """
        lines = [
            f"**[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}]** {self.step_name} failed",
            f"**Location:** {self.failure_location.format()}",
            f"**Error:** {self.error_message} ({self.error_category})",
            f"**API:** {self.api_service}",
        ]

        # Add retry information
        if self.next_retry_at:
            lines.append(
                f"**Next retry:** {self.next_retry_at.strftime('%Y-%m-%d %H:%M:%S')} "
                f"(Attempt {self.retry_attempt + 1}/5)"
            )
        else:
            lines.append(f"**Status:** Terminal failure after {self.retry_attempt} attempts")

        # Add partial progress if available
        if self.partial_progress:
            progress_str = self._format_progress(self.partial_progress)
            if progress_str:
                lines.append(f"**Progress:** {progress_str}")

        # Add recommendation
        if self.recommendation:
            lines.append(f"**Action:** {self.recommendation}")

        return "\n".join(lines)

    def _format_progress(self, progress: dict[str, Any]) -> str:
        """Format checkpoint progress as human-readable string.

        Args:
            progress: Checkpoint data from Story 6.3 checkpoint service

        Returns:
            Progress string (e.g., "10 of 18 clips completed")

        Patterns:
            - completed_video_clips: "10 of 18 clips completed"
            - completed_assets: "15 of 22 assets completed"
            - completed_narration_clips: "5 of 18 narration clips completed"
            - completed_sfx_clips: "3 of 18 SFX clips completed"
        """
        if "completed_video_clips" in progress:
            count = len(progress["completed_video_clips"])
            total = progress.get("total_clips", 18)
            return f"{count} of {total} clips completed"
        elif "completed_assets" in progress:
            count = len(progress["completed_assets"])
            total = progress.get("total_assets", 22)
            return f"{count} of {total} assets completed"
        elif "completed_narration_clips" in progress:
            count = len(progress["completed_narration_clips"])
            total = progress.get("total_clips", 18)
            return f"{count} of {total} narration clips completed"
        elif "completed_sfx_clips" in progress:
            count = len(progress["completed_sfx_clips"])
            total = progress.get("total_clips", 18)
            return f"{count} of {total} SFX clips completed"

        return ""
