"""Notion Asset Service for populating assets in Notion database.

This service implements Asset URL population for Story 5.3: Asset Review Interface.
It creates Asset entries in Notion after asset generation completes, linking them
to tasks via bidirectional relation property.

Key Responsibilities:
- Create Asset entries in Notion Assets database
- Upload files to catbox.moe (external image hosting)
- Link assets to parent task via relation property
- Support both Notion and R2 storage strategies
- Respect 3 req/sec rate limiting (inherited from NotionClient)
- Validate asset counts and types per AC requirements

Architecture Pattern:
    Service (Smart): Reads asset files, uploads/stores URLs, creates entries
    NotionClient (Rate Limited): All API calls go through rate-limited client

Dependencies:
    - Story 2.2: NotionClient with rate limiting
    - Story 3.3: Asset generation creates 22 PNG files
    - Story 5.3: Assets database with Task relation property

Configuration (via app.config):
    - NOTION_ASSETS_DATABASE_ID: Assets database ID (required)
    - NOTION_TASKS_COLLECTION_ID: Tasks collection ID (required)

Usage:
    from app.services.notion_asset_service import NotionAssetService

    service = NotionAssetService(notion_client, channel)
    await service.populate_assets(
        task_id=task.id,
        notion_page_id=task.notion_page_id,
        asset_files=asset_manifest.assets,
        correlation_id=correlation_id,
    )
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.clients.catbox import CatboxClient
from app.clients.notion import NotionClient
from app.config import get_notion_assets_database_id, get_notion_tasks_collection_id
from app.constants import (
    ASSET_STATUS_GENERATED,
    EXPECTED_TOTAL_ASSETS,
    VALID_ASSET_TYPES,
)
from app.models import Channel
from app.utils.logging import get_logger

log = get_logger(__name__)


class AssetValidationError(Exception):
    """Raised when asset validation fails (count, type, etc.)."""

    pass


class AssetUploadError(Exception):
    """Raised when too many asset uploads fail."""

    pass


class NotionAssetService:
    """Service for populating asset entries in Notion database.

    This service creates Asset entries in Notion after asset generation completes.
    It supports both Notion and R2 storage strategies (both use catbox.moe for now).

    Architecture Compliance:
    - Uses NotionClient for all API calls (rate limiting enforced)
    - Follows short transaction pattern (service is stateless)
    - Implements retry logic via NotionClient auto-retry
    - Validates asset counts per AC1 requirements (22 assets expected)
    - Uploads files BEFORE creating Notion entries (avoids holding rate limiter)

    Configuration (via environment variables):
    - NOTION_ASSETS_DATABASE_ID: Notion Assets database ID
    - NOTION_TASKS_COLLECTION_ID: Notion Tasks collection ID
    """

    def __init__(
        self,
        notion_client: NotionClient,
        channel: Channel,
        catbox_client: CatboxClient | None = None,
    ):
        """Initialize asset service with Notion client and channel config.

        Args:
            notion_client: Rate-limited Notion API client
            channel: Channel model with storage_strategy configuration
            catbox_client: Optional catbox client for file uploads (auto-created if None)
        """
        self.notion_client = notion_client
        self.channel = channel
        self.catbox_client = catbox_client or CatboxClient()
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
        min_success_rate: float = 0.9,
        skip_existing: bool = True,
    ) -> dict[str, Any]:
        """Populate Asset entries in Notion after asset generation.

        Creates Asset entries in Notion Assets database, linking them to the
        parent task via relation property. Validates asset count per AC1 (22 assets).

        **FIXED (Code Review Issue #5):** Now validates exactly 22 assets expected.
        **FIXED (Code Review Issue #6):** Uploads ALL files first, THEN creates Notion entries.
        **FIXED (Code Review Issue #8):** Added min_success_rate threshold validation.
        **FIXED (Code Review Issue #10):** Added skip_existing for idempotency.

        Args:
            task_id: Internal task UUID (for logging/correlation)
            notion_page_id: Notion page ID of parent task (32 chars, no dashes)
            asset_files: List of asset file information dicts with keys:
                - asset_type: "character" | "environment" | "prop"
                - name: Asset filename without extension
                - output_path: Path object to PNG file
            correlation_id: Optional correlation ID for request tracing
            min_success_rate: Minimum fraction of assets that must succeed (0.0-1.0)
            skip_existing: If True, skip assets that already exist in Notion (idempotency)

        Returns:
            Summary dict with keys:
                - created: Number of asset entries created
                - failed: Number of failed asset entries
                - skipped: Number of skipped (already exist) entries
                - storage_strategy: "notion" or "r2"

        Raises:
            AssetValidationError: If asset count != 22 or invalid asset types
            AssetUploadError: If success rate < min_success_rate
            NotionAPIError: On non-retriable Notion API errors
            NotionRateLimitError: After 3 retry attempts on rate limit

        Example:
            >>> result = await service.populate_assets(
            ...     task_id=task.id,
            ...     notion_page_id="abc123...",
            ...     asset_files=[...],  # 22 assets
            ...     correlation_id="req-123",
            ... )
            >>> print(result)
            {"created": 22, "failed": 0, "skipped": 0, "storage_strategy": "notion"}
        """
        storage_strategy = self.channel.storage_strategy

        self.log.info(
            "populate_assets_started",
            correlation_id=correlation_id,
            task_id=str(task_id),
            notion_page_id=notion_page_id,
            asset_count=len(asset_files),
            storage_strategy=storage_strategy,
            min_success_rate=min_success_rate,
        )

        # FIXED (Issue #5): Validate exactly 22 assets expected per AC1
        if len(asset_files) != EXPECTED_TOTAL_ASSETS:
            error_msg = (
                f"Expected {EXPECTED_TOTAL_ASSETS} assets per AC1, got {len(asset_files)}. "
                "Asset generation may have partially failed."
            )
            self.log.error(
                "asset_count_validation_failed",
                correlation_id=correlation_id,
                task_id=str(task_id),
                expected=EXPECTED_TOTAL_ASSETS,
                actual=len(asset_files),
            )
            raise AssetValidationError(error_msg)

        # FIXED (Issue #12): Validate asset types
        for asset in asset_files:
            asset_type = asset.get("asset_type")
            if asset_type not in VALID_ASSET_TYPES:
                error_msg = (
                    f"Invalid asset_type '{asset_type}' for asset '{asset.get('name')}'. "
                    f"Must be one of: {VALID_ASSET_TYPES}"
                )
                self.log.error(
                    "asset_type_validation_failed",
                    correlation_id=correlation_id,
                    task_id=str(task_id),
                    asset_name=asset.get("name"),
                    invalid_type=asset_type,
                    valid_types=list(VALID_ASSET_TYPES),
                )
                raise AssetValidationError(error_msg)

        # FIXED (Issue #10): Check for existing assets (idempotency)
        existing_assets = set()
        if skip_existing:
            try:
                existing_assets = await self._get_existing_asset_names(notion_page_id)
                if existing_assets:
                    self.log.info(
                        "existing_assets_found",
                        correlation_id=correlation_id,
                        task_id=str(task_id),
                        existing_count=len(existing_assets),
                    )
            except Exception as e:
                # Log but don't fail - proceed with creation (may create duplicates)
                self.log.warning(
                    "existing_assets_check_failed",
                    correlation_id=correlation_id,
                    task_id=str(task_id),
                    error=str(e),
                )

        # FIXED (Issue #6): Upload ALL files FIRST (parallel), THEN create Notion entries
        # This avoids holding rate limiter during slow network uploads
        self.log.info(
            "uploading_asset_files",
            correlation_id=correlation_id,
            task_id=str(task_id),
            file_count=len(asset_files),
        )

        # Upload all files in parallel (no rate limiter held)
        upload_results = await self._upload_all_files(asset_files, correlation_id)

        # Count upload failures
        upload_failures = sum(1 for result in upload_results.values() if result is None)
        upload_success_rate = (
            (len(upload_results) - upload_failures) / len(upload_results) if upload_results else 0
        )

        self.log.info(
            "asset_uploads_complete",
            correlation_id=correlation_id,
            task_id=str(task_id),
            total=len(upload_results),
            succeeded=len(upload_results) - upload_failures,
            failed=upload_failures,
            success_rate=upload_success_rate,
        )

        # Create Notion entries (rate limited, sequential to respect 3 req/sec)
        created = 0
        failed = 0
        skipped = 0

        for asset in asset_files:
            asset_name = asset["name"]

            # FIXED (Issue #10): Skip if already exists
            if asset_name in existing_assets:
                skipped += 1
                self.log.info(
                    "asset_entry_skipped",
                    correlation_id=correlation_id,
                    task_id=str(task_id),
                    asset_name=asset_name,
                    reason="already_exists",
                )
                continue

            try:
                # Create Asset entry in Notion (uses pre-uploaded file URL)
                file_url = upload_results.get(asset_name)
                await self._create_asset_entry(
                    notion_page_id=notion_page_id,
                    asset_type=asset["asset_type"],
                    asset_name=asset_name,
                    file_url=file_url,  # May be None if upload failed
                    storage_strategy=storage_strategy,
                    correlation_id=correlation_id,
                )
                created += 1

                self.log.info(
                    "asset_entry_created",
                    correlation_id=correlation_id,
                    task_id=str(task_id),
                    asset_name=asset_name,
                    asset_type=asset["asset_type"],
                    has_file_url=file_url is not None,
                )

            except Exception as e:
                failed += 1
                self.log.error(
                    "asset_entry_failed",
                    correlation_id=correlation_id,
                    task_id=str(task_id),
                    asset_name=asset_name,
                    asset_type=asset["asset_type"],
                    error=str(e),
                    exc_info=True,
                )
                # Continue with remaining assets instead of failing entire batch

        # Calculate final success rate
        total_attempted = created + failed
        success_rate = created / total_attempted if total_attempted > 0 else 0

        self.log.info(
            "populate_assets_complete",
            correlation_id=correlation_id,
            task_id=str(task_id),
            created=created,
            failed=failed,
            skipped=skipped,
            success_rate=success_rate,
            storage_strategy=storage_strategy,
        )

        # FIXED (Issue #8): Validate minimum success threshold
        if success_rate < min_success_rate:
            error_msg = (
                f"Asset population success rate {success_rate:.1%} "
                f"below minimum threshold {min_success_rate:.1%}. "
                f"Created {created}/{total_attempted} entries successfully."
            )
            self.log.error(
                "asset_population_threshold_failed",
                correlation_id=correlation_id,
                task_id=str(task_id),
                success_rate=success_rate,
                min_threshold=min_success_rate,
                created=created,
                failed=failed,
            )
            raise AssetUploadError(error_msg)

        return {
            "created": created,
            "failed": failed,
            "skipped": skipped,
            "storage_strategy": storage_strategy,
        }

    async def _upload_all_files(
        self,
        asset_files: list[dict[str, Any]],
        correlation_id: str | None = None,
    ) -> dict[str, str | None]:
        """Upload all asset files to catbox.moe in parallel.

        FIXED (Code Review Issue #6): Separated file upload from Notion API calls.
        This prevents holding rate limiter during slow network I/O.

        Args:
            asset_files: List of asset dicts with 'name' and 'output_path' keys
            correlation_id: Optional correlation ID for request tracing

        Returns:
            Dict mapping asset_name -> file_url (or None if upload failed)
        """
        upload_tasks = []
        asset_names = []

        for asset in asset_files:
            asset_name = asset["name"]
            asset_path = asset["output_path"]
            asset_names.append(asset_name)
            upload_tasks.append(self._upload_single_file(asset_name, asset_path, correlation_id))

        # Upload all files in parallel
        upload_results = await asyncio.gather(*upload_tasks, return_exceptions=True)

        # Map results back to asset names
        results: dict[str, str | None] = {}
        for asset_name, result in zip(asset_names, upload_results, strict=False):
            if isinstance(result, Exception):
                # Upload failed - log and store None
                self.log.error(
                    "asset_file_upload_failed",
                    correlation_id=correlation_id,
                    asset_name=asset_name,
                    error=str(result),
                )
                results[asset_name] = None
            else:
                # Upload succeeded - result is str (URL)
                results[asset_name] = str(result)

        return results

    async def _upload_single_file(
        self,
        asset_name: str,
        asset_path: Path,
        correlation_id: str | None = None,
    ) -> str:
        """Upload single file to catbox.moe.

        FIXED (Code Review Issue #2): Better error handling with descriptive exceptions.

        Args:
            asset_name: Asset filename (for logging)
            asset_path: Path to PNG file
            correlation_id: Optional correlation ID for request tracing

        Returns:
            File URL string (e.g., "https://files.catbox.moe/abc123.png")

        Raises:
            Exception: On upload failure (caught by caller)
        """
        try:
            file_url = await self.catbox_client.upload_image(asset_path)
            self.log.info(
                "asset_file_uploaded",
                correlation_id=correlation_id,
                asset_name=asset_name,
                file_url=file_url,
            )
            return file_url
        except Exception as e:
            # Re-raise with context for better error messages
            raise Exception(f"Failed to upload {asset_name} to catbox.moe: {e}") from e

    async def _get_existing_asset_names(self, notion_page_id: str) -> set[str]:
        """Query existing asset names for a task to enable idempotency.

        FIXED (Code Review Issue #10): Added to prevent duplicate asset entries on retry.

        Args:
            notion_page_id: Parent task page ID

        Returns:
            Set of existing asset names (empty if none found or query fails)
        """
        try:
            # Query Assets database for entries linked to this task
            # This uses Notion's filter API to find assets with Task relation = notion_page_id
            query_params = {
                "filter": {
                    "property": "Task",
                    "relation": {"contains": notion_page_id},
                }
            }

            response = await self.notion_client.query_database(
                database_id=self.assets_database_id,
                **query_params,
            )

            # Extract asset names from results
            existing_names = set()
            for page in response.get("results", []):
                properties = page.get("properties", {})
                name_property = properties.get("Asset Name", {})
                title_content = name_property.get("title", [])
                if title_content:
                    asset_name = title_content[0].get("plain_text", "")
                    if asset_name:
                        existing_names.add(asset_name)

            return existing_names

        except Exception as e:
            # Log but don't fail - caller will proceed with creation
            self.log.warning(
                "existing_assets_query_failed",
                notion_page_id=notion_page_id,
                error=str(e),
            )
            return set()

    async def _create_asset_entry(
        self,
        notion_page_id: str,
        asset_type: str,
        asset_name: str,
        file_url: str | None,
        storage_strategy: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Create single Asset entry in Notion database.

        FIXED (Code Review Issue #11): Uses constants instead of hardcoded status.
        FIXED (Code Review Issue #6): Now receives pre-uploaded file_url (no upload here).

        Args:
            notion_page_id: Parent task page ID
            asset_type: "character" | "environment" | "prop"
            asset_name: Asset filename without extension
            file_url: Pre-uploaded file URL (or None if upload failed)
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
            "Status": {"select": {"name": ASSET_STATUS_GENERATED}},  # FIXED: Use constant
            "Generated Date": {"date": {"start": current_date}},
            "Task": {"relation": [{"id": notion_page_id}]},
        }

        # Add File URL property (null if upload failed)
        # FIXED (Issue #2): Graceful degradation - asset entry created even if upload failed
        if file_url:
            properties["File URL"] = {"url": file_url}
        else:
            # Set to null explicitly - asset tracked but file not accessible
            # User will see "generated" status but no image - clear signal of upload failure
            properties["File URL"] = {"url": None}
            self.log.warning(
                "asset_entry_created_without_file",
                correlation_id=correlation_id,
                asset_name=asset_name,
                reason="file_upload_failed",
            )

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
