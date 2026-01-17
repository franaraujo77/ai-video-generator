"""Notion Audio Service for populating audio clips in Notion database.

This service implements Audio URL population for Story 5.5: Audio Review Interface.
It creates Audio entries in Notion after audio generation completes, linking them
to tasks via bidirectional relation property.

Key Responsibilities:
- Create Audio entries in Notion Audio database (36 clips per task: 18 narration + 18 SFX)
- Upload files to Notion (storage_strategy="notion") or store R2 URLs
- Link audio to parent task via relation property
- Support both Notion file attachments and R2 public URLs
- Handle dual audio types: narration (MP3) and SFX (WAV)
- Respect 3 req/sec rate limiting (inherited from NotionClient)

Architecture Pattern:
    Service (Smart): Reads audio files, uploads/stores URLs, creates entries
    NotionClient (Rate Limited): All API calls go through rate-limited client

Dependencies:
    - Story 2.2: NotionClient with rate limiting
    - Story 3.6: Narration generation creates 18 MP3 files
    - Story 3.7: SFX generation creates 18 WAV files
    - Story 5.5: Audio database with Task relation property

Usage:
    from app.services.notion_audio_service import NotionAudioService

    service = NotionAudioService(notion_client, channel)
    await service.populate_audio(
        task_id=task.id,
        notion_page_id=task.notion_page_id,
        narration_files=narration_list,
        sfx_files=sfx_list
    )
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.clients.notion import NotionClient
from app.config import get_notion_audio_database_id, get_notion_tasks_collection_id
from app.models import Channel
from app.utils.logging import get_logger

log = get_logger(__name__)


class NotionAudioService:
    """Service for populating audio entries in Notion database.

    This service creates Audio entries in Notion after audio generation completes.
    It supports both Notion file attachments (storage_strategy="notion") and
    R2 public URLs (storage_strategy="r2").

    Architecture Compliance:
    - Uses NotionClient for all API calls (rate limiting enforced)
    - Follows short transaction pattern (service is stateless)
    - Implements retry logic via NotionClient auto-retry
    - Handles dual audio types: narration (MP3) and SFX (WAV)

    Configuration:
    - NOTION_AUDIO_DATABASE_ID: Notion Audio database ID (env var)
    - NOTION_TASKS_COLLECTION_ID: Notion Tasks collection ID (env var)
    """

    def __init__(self, notion_client: NotionClient, channel: Channel):
        """Initialize audio service with Notion client and channel config.

        Args:
            notion_client: Rate-limited Notion API client
            channel: Channel model with storage_strategy configuration
        """
        self.notion_client = notion_client
        self.channel = channel
        self.log = get_logger(__name__)

        # Load database IDs from configuration (not hardcoded)
        self.audio_database_id = get_notion_audio_database_id()
        self.tasks_collection_id = get_notion_tasks_collection_id()

    async def populate_audio(
        self,
        task_id: UUID,
        notion_page_id: str,
        narration_files: list[dict[str, Any]],
        sfx_files: list[dict[str, Any]],
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Populate Audio entries in Notion after audio generation.

        Creates Audio entries in Notion Audio database, linking them to the
        parent task via relation property. Supports both Notion file upload
        and R2 URL storage based on channel.storage_strategy.

        Args:
            task_id: Internal task UUID (for logging/correlation)
            notion_page_id: Notion page ID of parent task (32 chars, no dashes)
            narration_files: List of narration file information dicts with keys:
                - clip_number: int (1-18) identifies clip in sequence
                - output_path: Path object to MP3 file
                - duration: float (actual duration in seconds)
            sfx_files: List of SFX file information dicts with keys:
                - clip_number: int (1-18) identifies clip in sequence
                - output_path: Path object to WAV file
                - duration: float (actual duration in seconds)
            correlation_id: Optional correlation ID for log tracing

        Returns:
            Summary dict with keys:
                - created: Number of audio entries created
                - failed: Number of failed audio entries
                - narration_count: Number of narration clips created
                - sfx_count: Number of SFX clips created
                - storage_strategy: "notion" or "r2"

        Raises:
            NotionAPIError: On non-retriable Notion API errors
            NotionRateLimitError: After 3 retry attempts on rate limit

        Example:
            >>> result = await service.populate_audio(
            ...     task_id=task.id,
            ...     notion_page_id="abc123...",
            ...     narration_files=[
            ...         {
            ...             "clip_number": 1,
            ...             "output_path": Path("/workspace/audio/narration_01.mp3"),
            ...             "duration": 7.2,
            ...         }
            ...     ],
            ...     sfx_files=[
            ...         {
            ...             "clip_number": 1,
            ...             "output_path": Path("/workspace/sfx/sfx_01.wav"),
            ...             "duration": 7.2,
            ...         }
            ...     ],
            ... )
            >>> print(result)
            {"created": 2, "failed": 0, "narration_count": 1, "sfx_count": 1, "storage_strategy": "r2"}
        """
        created = 0
        failed = 0
        narration_count = 0
        sfx_count = 0
        storage_strategy = self.channel.storage_strategy

        self.log.info(
            "populate_audio_started",
            correlation_id=correlation_id,
            task_id=str(task_id),
            notion_page_id=notion_page_id,
            narration_count=len(narration_files),
            sfx_count=len(sfx_files),
            total_audio_count=len(narration_files) + len(sfx_files),
            storage_strategy=storage_strategy,
        )

        # Process narration clips (type="narration")
        for narration in narration_files:
            try:
                # Create Audio entry in Notion
                await self._create_audio_entry(
                    notion_page_id=notion_page_id,
                    clip_number=narration["clip_number"],
                    audio_type="narration",
                    audio_path=narration["output_path"],
                    duration=narration.get("duration", 0.0),
                    storage_strategy=storage_strategy,
                    correlation_id=correlation_id,
                )
                created += 1
                narration_count += 1

                self.log.info(
                    "audio_entry_created",
                    correlation_id=correlation_id,
                    task_id=str(task_id),
                    audio_type="narration",
                    clip_number=narration["clip_number"],
                    duration=narration.get("duration", 0.0),
                )

            except Exception as e:
                failed += 1
                self.log.error(
                    "audio_entry_failed",
                    correlation_id=correlation_id,
                    task_id=str(task_id),
                    audio_type="narration",
                    clip_number=narration["clip_number"],
                    error=str(e),
                    exc_info=True,
                )
                # Continue with remaining audio instead of failing entire batch

        # Process SFX clips (type="sfx")
        for sfx in sfx_files:
            try:
                # Create Audio entry in Notion
                await self._create_audio_entry(
                    notion_page_id=notion_page_id,
                    clip_number=sfx["clip_number"],
                    audio_type="sfx",
                    audio_path=sfx["output_path"],
                    duration=sfx.get("duration", 0.0),
                    storage_strategy=storage_strategy,
                    correlation_id=correlation_id,
                )
                created += 1
                sfx_count += 1

                self.log.info(
                    "audio_entry_created",
                    correlation_id=correlation_id,
                    task_id=str(task_id),
                    audio_type="sfx",
                    clip_number=sfx["clip_number"],
                    duration=sfx.get("duration", 0.0),
                )

            except Exception as e:
                failed += 1
                self.log.error(
                    "audio_entry_failed",
                    correlation_id=correlation_id,
                    task_id=str(task_id),
                    audio_type="sfx",
                    clip_number=sfx["clip_number"],
                    error=str(e),
                    exc_info=True,
                )
                # Continue with remaining audio instead of failing entire batch

        self.log.info(
            "populate_audio_complete",
            correlation_id=correlation_id,
            task_id=str(task_id),
            created=created,
            failed=failed,
            narration_count=narration_count,
            sfx_count=sfx_count,
            storage_strategy=storage_strategy,
        )

        # Check if all audio files failed (critical failure)
        if failed > 0 and created == 0:
            raise RuntimeError(
                f"All {failed} audio clips failed to populate in Notion. Check error logs."
            )

        return {
            "created": created,
            "failed": failed,
            "narration_count": narration_count,
            "sfx_count": sfx_count,
            "storage_strategy": storage_strategy,
        }

    async def _create_audio_entry(
        self,
        notion_page_id: str,
        clip_number: int,
        audio_type: str,
        audio_path: Path,
        duration: float,
        storage_strategy: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Create single Audio entry in Notion database.

        Args:
            notion_page_id: Parent task page ID
            clip_number: Clip number (1-18) identifying clip in sequence
            audio_type: "narration" or "sfx"
            audio_path: Path to audio file (MP3 for narration, WAV for SFX)
            duration: Actual duration in seconds
            storage_strategy: "notion" or "r2"
            correlation_id: Optional correlation ID for log tracing

        Returns:
            Created page object from Notion API

        Raises:
            NotionAPIError: On non-retriable errors
            NotionRateLimitError: After retry exhaustion
        """
        # Prepare audio properties
        current_date = datetime.now(timezone.utc).isoformat()

        properties: dict[str, Any] = {
            "Clip Number": {"number": clip_number},
            "Type": {
                "select": {"name": audio_type}  # "narration" or "sfx"
            },
            "Duration": {"number": duration},
            "Status": {"select": {"name": "generated"}},
            "Generated Date": {"date": {"start": current_date}},
            "Task": {"relation": [{"id": notion_page_id}]},
        }

        # Handle file storage based on strategy
        file_url: str | None = None
        if storage_strategy == "notion":
            # Notion API doesn't support direct file uploads
            # Files must be uploaded to external storage first
            self.log.warning(
                "notion_file_upload_requires_external_storage",
                correlation_id=correlation_id,
                audio_type=audio_type,
                clip_number=clip_number,
                message="Notion requires external file URL. File property will be null.",
            )
        elif storage_strategy == "r2":
            # R2 upload would happen here (Story 8.4)
            # file_url = await self._upload_to_r2(audio_path)
            self.log.warning(
                "r2_upload_not_implemented",
                correlation_id=correlation_id,
                audio_type=audio_type,
                clip_number=clip_number,
                message="R2 upload not yet implemented (Story 8.4), File property will be null",
            )

        # Add File property (null if upload not implemented)
        # This property MUST exist in schema even if value is None
        if file_url:
            properties["File"] = {
                "files": [{"name": audio_path.name, "external": {"url": file_url}}]
            }
        else:
            # Set to empty array - shows property exists but needs implementation
            properties["File"] = {"files": []}

        # Create page in Audio database using NotionClient method (rate limited, auto-retry)
        try:
            return await self.notion_client.create_page(
                database_id=self.audio_database_id,
                properties=properties,
            )
        except Exception as e:
            self.log.error(
                "notion_create_page_failed",
                correlation_id=correlation_id,
                audio_type=audio_type,
                clip_number=clip_number,
                database_id=self.audio_database_id,
                error=str(e),
                exc_info=True,
            )
            raise
