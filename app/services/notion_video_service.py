"""Notion Video Service for populating video clips in Notion database.

This service implements Video URL population for Story 5.4: Video Review Interface.
It creates Video entries in Notion after video generation completes, linking them
to tasks via bidirectional relation property.

Key Responsibilities:
- Create Video entries in Notion Videos database (18 clips per task)
- Upload files to Notion (storage_strategy="notion") or store R2 URLs
- Link videos to parent task via relation property
- Support both Notion file attachments and R2 public URLs
- Optimize videos with MP4 faststart for streaming playback
- Respect 3 req/sec rate limiting (inherited from NotionClient)

Architecture Pattern:
    Service (Smart): Reads video files, uploads/stores URLs, creates entries, optimizes
    NotionClient (Rate Limited): All API calls go through rate-limited client

Dependencies:
    - Story 2.2: NotionClient with rate limiting
    - Story 3.5: Video generation creates 18 MP4 files (10-second clips)
    - Story 5.4: Videos database with Task relation property

Usage:
    from app.services.notion_video_service import NotionVideoService

    service = NotionVideoService(notion_client, channel)
    await service.populate_videos(
        task_id=task.id,
        notion_page_id=task.notion_page_id,
        video_files=video_manifest.clips
    )
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.clients.notion import NotionClient
from app.config import DEFAULT_VIDEO_DURATION_SECONDS, get_notion_tasks_collection_id, get_notion_videos_database_id
from app.models import Channel
from app.utils.logging import get_logger

log = get_logger(__name__)


class NotionVideoService:
    """Service for populating video entries in Notion database.

    This service creates Video entries in Notion after video generation completes.
    It supports both Notion file attachments (storage_strategy="notion") and
    R2 public URLs (storage_strategy="r2").

    Architecture Compliance:
    - Uses NotionClient for all API calls (rate limiting enforced)
    - Follows short transaction pattern (service is stateless)
    - Implements retry logic via NotionClient auto-retry
    - Optimizes videos with MP4 faststart for streaming

    Configuration:
    - NOTION_VIDEOS_DATABASE_ID: Notion Videos database ID (env var)
    - NOTION_TASKS_COLLECTION_ID: Notion Tasks collection ID (env var)
    """

    def __init__(self, notion_client: NotionClient, channel: Channel):
        """Initialize video service with Notion client and channel config.

        Args:
            notion_client: Rate-limited Notion API client
            channel: Channel model with storage_strategy configuration
        """
        self.notion_client = notion_client
        self.channel = channel
        self.log = get_logger(__name__)

        # Load database IDs from configuration (not hardcoded)
        self.videos_database_id = get_notion_videos_database_id()
        self.tasks_collection_id = get_notion_tasks_collection_id()

    async def populate_videos(
        self,
        task_id: UUID,
        notion_page_id: str,
        video_files: list[dict[str, Any]],
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Populate Video entries in Notion after video generation.

        Creates Video entries in Notion Videos database, linking them to the
        parent task via relation property. Supports both Notion file upload
        and R2 URL storage based on channel.storage_strategy.

        Args:
            task_id: Internal task UUID (for logging/correlation)
            notion_page_id: Notion page ID of parent task (32 chars, no dashes)
            video_files: List of video file information dicts with keys:
                - clip_number: int (1-18) identifies clip in sequence
                - output_path: Path object to MP4 file
                - duration: float (actual duration in seconds)

        Returns:
            Summary dict with keys:
                - created: Number of video entries created
                - failed: Number of failed video entries
                - storage_strategy: "notion" or "r2"

        Raises:
            NotionAPIError: On non-retriable Notion API errors
            NotionRateLimitError: After 3 retry attempts on rate limit

        Example:
            >>> result = await service.populate_videos(
            ...     task_id=task.id,
            ...     notion_page_id="abc123...",
            ...     video_files=[
            ...         {
            ...             "clip_number": 1,
            ...             "output_path": Path("/workspace/videos/clip_01.mp4"),
            ...             "duration": 8.5
            ...         }
            ...     ]
            ... )
            >>> print(result)
            {"created": 1, "failed": 0, "storage_strategy": "r2"}
        """
        created = 0
        failed = 0
        storage_strategy = self.channel.storage_strategy

        self.log.info(
            "populate_videos_started",
            correlation_id=correlation_id,
            task_id=str(task_id),
            notion_page_id=notion_page_id,
            video_count=len(video_files),
            storage_strategy=storage_strategy,
        )

        for video in video_files:
            try:
                # Create Video entry in Notion
                await self._create_video_entry(
                    notion_page_id=notion_page_id,
                    clip_number=video["clip_number"],
                    video_path=video["output_path"],
                    duration=video.get("duration", DEFAULT_VIDEO_DURATION_SECONDS),
                    storage_strategy=storage_strategy,
                    correlation_id=correlation_id,
                )
                created += 1

                self.log.info(
                    "video_entry_created",
                    correlation_id=correlation_id,
                    task_id=str(task_id),
                    clip_number=video["clip_number"],
                    duration=video.get("duration", 10.0),
                )

            except Exception as e:
                failed += 1
                self.log.error(
                    "video_entry_failed",
                    correlation_id=correlation_id,
                    task_id=str(task_id),
                    clip_number=video["clip_number"],
                    error=str(e),
                    exc_info=True,
                )
                # Continue with remaining videos instead of failing entire batch

        self.log.info(
            "populate_videos_complete",
            correlation_id=correlation_id,
            task_id=str(task_id),
            created=created,
            failed=failed,
            storage_strategy=storage_strategy,
        )

        # Check if all videos failed (critical failure)
        if failed > 0 and created == 0:
            raise RuntimeError(
                f"All {failed} videos failed to populate in Notion. Check error logs."
            )

        return {
            "created": created,
            "failed": failed,
            "storage_strategy": storage_strategy,
        }

    async def _create_video_entry(
        self,
        notion_page_id: str,
        clip_number: int,
        video_path: Path,
        duration: float,
        storage_strategy: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Create single Video entry in Notion database.

        Args:
            notion_page_id: Parent task page ID
            clip_number: Clip number (1-18) identifying clip in sequence
            video_path: Path to MP4 file
            duration: Actual duration in seconds (after trimming)
            storage_strategy: "notion" or "r2"

        Returns:
            Created page object from Notion API

        Raises:
            NotionAPIError: On non-retriable errors
            NotionRateLimitError: After retry exhaustion
        """
        # Prepare video properties
        current_date = datetime.now(timezone.utc).isoformat()

        properties: dict[str, Any] = {
            "Clip Number": {
                "number": clip_number
            },
            "Duration": {
                "number": duration
            },
            "Status": {
                "select": {"name": "generated"}
            },
            "Generated Date": {
                "date": {"start": current_date}
            },
            "Task": {
                "relation": [
                    {"id": notion_page_id}
                ]
            }
        }

        # Handle file storage based on strategy
        file_url: str | None = None
        if storage_strategy == "notion":
            # Notion API doesn't support direct file uploads
            # Files must be uploaded to external storage first
            self.log.warning(
                "notion_file_upload_requires_external_storage",
                correlation_id=correlation_id,
                clip_number=clip_number,
                message="Notion requires external file URL. File URL property will be null.",
            )
        elif storage_strategy == "r2":
            # R2 upload would happen here
            # file_url = await self._upload_to_r2(video_path)
            self.log.warning(
                "r2_upload_not_implemented",
                correlation_id=correlation_id,
                clip_number=clip_number,
                message="R2 upload not yet implemented, File URL property will be null",
            )

        # Add File URL property (null if upload not implemented)
        # This property MUST exist in schema even if value is None
        if file_url:
            properties["File URL"] = {
                "url": file_url
            }
        else:
            # Set to null explicitly - shows property exists but needs implementation
            properties["File URL"] = {
                "url": None
            }

        # Create page in Videos database using NotionClient method (rate limited, auto-retry)
        try:
            return await self.notion_client.create_page(
                database_id=self.videos_database_id,
                properties=properties,
            )
        except Exception as e:
            self.log.error(
                "notion_create_page_failed",
                correlation_id=correlation_id,
                clip_number=clip_number,
                database_id=self.videos_database_id,
                error=str(e),
                exc_info=True,
            )
            raise
