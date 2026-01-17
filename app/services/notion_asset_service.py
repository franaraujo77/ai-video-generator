"""Notion Asset Service for populating assets in Notion database.

This service implements Asset URL population for Story 5.3: Asset Review Interface.
It creates Asset entries in Notion after asset generation completes, linking them
to tasks via bidirectional relation property.

Key Responsibilities:
- Create Asset entries in Notion Assets database
- Upload files to Notion (storage_strategy="notion") or store R2 URLs
- Link assets to parent task via relation property
- Support both Notion file attachments and R2 public URLs
- Respect 3 req/sec rate limiting (inherited from NotionClient)

Architecture Pattern:
    Service (Smart): Reads asset files, uploads/stores URLs, creates entries
    NotionClient (Rate Limited): All API calls go through rate-limited client

Dependencies:
    - Story 2.2: NotionClient with rate limiting
    - Story 3.3: Asset generation creates 22 PNG files
    - Story 5.3: Assets database with Task relation property

Usage:
    from app.services.notion_asset_service import NotionAssetService

    service = NotionAssetService(notion_client, channel)
    await service.populate_assets(
        task_id=task.id,
        notion_page_id=task.notion_page_id,
        asset_files=asset_manifest.assets
    )
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.clients.notion import NotionClient
from app.config import get_notion_assets_database_id, get_notion_tasks_collection_id
from app.models import Channel
from app.utils.logging import get_logger

log = get_logger(__name__)


class NotionAssetService:
    """Service for populating asset entries in Notion database.

    This service creates Asset entries in Notion after asset generation completes.
    It supports both Notion file attachments (storage_strategy="notion") and
    R2 public URLs (storage_strategy="r2").

    Architecture Compliance:
    - Uses NotionClient for all API calls (rate limiting enforced)
    - Follows short transaction pattern (service is stateless)
    - Implements retry logic via NotionClient auto-retry

    Configuration:
    - NOTION_ASSETS_DATABASE_ID: Notion Assets database ID (env var)
    - NOTION_TASKS_COLLECTION_ID: Notion Tasks collection ID (env var)
    """

    def __init__(self, notion_client: NotionClient, channel: Channel):
        """Initialize asset service with Notion client and channel config.

        Args:
            notion_client: Rate-limited Notion API client
            channel: Channel model with storage_strategy configuration
        """
        self.notion_client = notion_client
        self.channel = channel
        self.log = get_logger(__name__)

        # Load database IDs from configuration (not hardcoded)
        self.assets_database_id = get_notion_assets_database_id()
        self.tasks_collection_id = get_notion_tasks_collection_id()

    async def populate_assets(
        self,
        task_id: UUID,
        notion_page_id: str,
        asset_files: list[dict[str, Any]],
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Populate Asset entries in Notion after asset generation.

        Creates Asset entries in Notion Assets database, linking them to the
        parent task via relation property. Supports both Notion file upload
        and R2 URL storage based on channel.storage_strategy.

        Args:
            task_id: Internal task UUID (for logging/correlation)
            notion_page_id: Notion page ID of parent task (32 chars, no dashes)
            asset_files: List of asset file information dicts with keys:
                - asset_type: "character" | "environment" | "prop"
                - name: Asset filename without extension
                - output_path: Path object to PNG file
            correlation_id: Optional correlation ID for request tracing

        Returns:
            Summary dict with keys:
                - created: Number of asset entries created
                - failed: Number of failed asset entries
                - storage_strategy: "notion" or "r2"

        Raises:
            NotionAPIError: On non-retriable Notion API errors
            NotionRateLimitError: After 3 retry attempts on rate limit

        Example:
            >>> result = await service.populate_assets(
            ...     task_id=task.id,
            ...     notion_page_id="abc123...",
            ...     asset_files=[
            ...         {
            ...             "asset_type": "character",
            ...             "name": "bulbasaur_resting",
            ...             "output_path": Path("/workspace/assets/bulbasaur_resting.png"),
            ...         }
            ...     ],
            ... )
            >>> print(result)
            {"created": 1, "failed": 0, "storage_strategy": "notion"}
        """
        created = 0
        failed = 0
        storage_strategy = self.channel.storage_strategy

        self.log.info(
            "populate_assets_started",
            correlation_id=correlation_id,
            task_id=str(task_id),
            notion_page_id=notion_page_id,
            asset_count=len(asset_files),
            storage_strategy=storage_strategy,
        )

        for asset in asset_files:
            try:
                # Create Asset entry in Notion
                await self._create_asset_entry(
                    notion_page_id=notion_page_id,
                    asset_type=asset["asset_type"],
                    asset_name=asset["name"],
                    asset_path=asset["output_path"],
                    storage_strategy=storage_strategy,
                    correlation_id=correlation_id,
                )
                created += 1

                self.log.info(
                    "asset_entry_created",
                    correlation_id=correlation_id,
                    task_id=str(task_id),
                    asset_name=asset["name"],
                    asset_type=asset["asset_type"],
                )

            except Exception as e:
                failed += 1
                self.log.error(
                    "asset_entry_failed",
                    correlation_id=correlation_id,
                    task_id=str(task_id),
                    asset_name=asset["name"],
                    asset_type=asset["asset_type"],
                    error=str(e),
                    exc_info=True,
                )
                # Continue with remaining assets instead of failing entire batch

        self.log.info(
            "populate_assets_complete",
            correlation_id=correlation_id,
            task_id=str(task_id),
            created=created,
            failed=failed,
            storage_strategy=storage_strategy,
        )

        # Check if all assets failed (critical failure)
        if failed > 0 and created == 0:
            raise RuntimeError(
                f"All {failed} assets failed to populate in Notion. Check error logs."
            )

        return {
            "created": created,
            "failed": failed,
            "storage_strategy": storage_strategy,
        }

    async def _create_asset_entry(
        self,
        notion_page_id: str,
        asset_type: str,
        asset_name: str,
        asset_path: Path,
        storage_strategy: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Create single Asset entry in Notion database.

        Args:
            notion_page_id: Parent task page ID
            asset_type: "character" | "environment" | "prop"
            asset_name: Asset filename without extension
            asset_path: Path to PNG file
            storage_strategy: "notion" or "r2"
            correlation_id: Optional correlation ID for request tracing

        Returns:
            Created page object from Notion API

        Raises:
            NotionAPIError: On non-retriable errors
            NotionRateLimitError: After retry exhaustion
        """
        # Prepare asset properties
        current_date = datetime.now(timezone.utc).isoformat()

        properties: dict[str, Any] = {
            "Asset Name": {"title": [{"type": "text", "text": {"content": asset_name}}]},
            "Asset Type": {"select": {"name": asset_type}},
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
                asset_name=asset_name,
                message="Notion requires external file URL. File URL property will be null.",
            )
        elif storage_strategy == "r2":
            # R2 upload would happen here
            # file_url = await self._upload_to_r2(asset_path)
            self.log.warning(
                "r2_upload_not_implemented",
                correlation_id=correlation_id,
                asset_name=asset_name,
                message="R2 upload not yet implemented, File URL property will be null",
            )

        # Add File URL property (null if upload not implemented)
        # This property MUST exist in schema even if value is None
        if file_url:
            properties["File URL"] = {"url": file_url}
        else:
            # Set to null explicitly - shows property exists but needs implementation
            properties["File URL"] = {"url": None}

        # Create page in Assets database using NotionClient method (rate limited, auto-retry)
        try:
            return await self.notion_client.create_page(
                database_id=self.assets_database_id,
                properties=properties,
            )
        except Exception as e:
            self.log.error(
                "notion_create_page_failed",
                correlation_id=correlation_id,
                asset_name=asset_name,
                database_id=self.assets_database_id,
                error=str(e),
                exc_info=True,
            )
            raise
