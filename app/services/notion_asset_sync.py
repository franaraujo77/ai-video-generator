"""Notion Asset Sync Service (Story 8.3).

Provides background sync of asset URLs to Notion database properties.
Implements fire-and-forget pattern with exponential backoff retry.

Architecture:
- Rate limiting: AsyncLimiter (3 requests per second)
- Error classification: Permanent vs transient failures
- Retry logic: Exponential backoff, max 3 attempts
- Transaction pattern: Short transactions, no DB lock during API calls

Dependencies:
- Story 8.3: AssetMetadata model and asset_url_storage service
- Story 7.5: Notion sync patterns from YouTube URL retrieval
- Architecture Decision 9: Fire-and-forget Notion update pattern
"""

import re
from typing import Any
from uuid import UUID

import httpx
from aiolimiter import AsyncLimiter
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.models import AssetMetadata, Task
from app.services.asset_url_storage import get_unsynced_assets, mark_assets_synced_batch
from app.utils.context import get_correlation_id
from app.utils.logging import get_logger

log = get_logger(__name__)

__all__ = [
    "NotionAssetSyncService",
    "NotionSyncError",
    "NotionSyncRetryError",
    "sync_task_assets_to_notion",
]


def sanitize_notion_property_name(name: str) -> str:
    """Sanitize asset name for Notion property naming.

    Notion property names have restrictions:
    - Cannot contain spaces
    - Cannot contain special characters (#, @, etc.)
    - Max length 100 characters

    Args:
        name: Original asset name (e.g., "bulbasaur 01.png", "clip #1.mp4")

    Returns:
        Sanitized name safe for Notion properties (e.g., "bulbasaur_01.png", "clip_num1.mp4")
    """
    # Replace spaces with underscores
    sanitized = name.replace(" ", "_")

    # Replace common special characters
    sanitized = sanitized.replace("#", "num")
    sanitized = sanitized.replace("@", "at")
    sanitized = sanitized.replace("&", "and")
    sanitized = sanitized.replace("%", "pct")

    # Remove any remaining non-alphanumeric characters (except underscore, dash, dot)
    sanitized = re.sub(r"[^a-zA-Z0-9_\-.]", "", sanitized)

    # Truncate to 100 chars (leaving room for prefix)
    if len(sanitized) > 80:
        sanitized = sanitized[:80]

    return sanitized


class NotionSyncError(Exception):
    """Permanent Notion sync error (don't retry)."""

    pass


class NotionSyncRetryError(Exception):
    """Transient Notion sync error (retry with backoff)."""

    pass


class NotionAssetSyncService:
    """Notion asset URL sync service with rate limiting and retry logic."""

    def __init__(self, auth_token: str):
        """Initialize Notion sync service.

        Args:
            auth_token: Notion integration token (from channel credentials)
        """
        self.auth_token = auth_token
        self.client = httpx.AsyncClient(timeout=30.0)
        # CRITICAL: 3 requests per 1 second (Notion API limit)
        self.rate_limiter = AsyncLimiter(max_rate=3, time_period=1)

    async def close(self) -> None:
        """Close HTTP client (cleanup)."""
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        retry=retry_if_exception_type(NotionSyncRetryError),
        reraise=True,
    )
    async def update_asset_urls(self, page_id: str, assets: list[AssetMetadata]) -> dict[str, Any]:
        """Update Notion page with asset URLs (rate limited, with retry).

        Args:
            page_id: Notion page ID
            assets: List of AssetMetadata records to sync

        Returns:
            Notion API response dict

        Raises:
            NotionSyncError: Permanent error (don't retry)
            NotionSyncRetryError: Transient error (retry)
        """
        correlation_id = get_correlation_id()

        # Build properties dict with asset URLs
        properties = {}
        for asset in assets:
            # Property name: asset_type + sanitized name (e.g., "character_bulbasaur_01_url")
            safe_name = sanitize_notion_property_name(asset.asset_name)
            property_name = f"{asset.asset_type}_{safe_name}_url"
            properties[property_name] = {"url": asset.asset_url}

        log.info(
            "notion_asset_sync_start",
            page_id=page_id,
            asset_count=len(assets),
            correlation_id=correlation_id,
        )

        try:
            # Rate limiting MANDATORY
            # NOTE: Notion API version 2022-06-28 is stable as of 2026-01-27
            # Monitor Notion changelog for deprecation notices
            async with self.rate_limiter:
                response = await self.client.patch(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    headers={
                        "Authorization": f"Bearer {self.auth_token}",
                        "Notion-Version": "2022-06-28",
                        "Content-Type": "application/json",
                    },
                    json={"properties": properties},
                )
        except Exception as limiter_error:
            # Rate limiter errors (resource exhaustion, timing issues)
            log.error(
                "notion_rate_limiter_error",
                page_id=page_id,
                error=str(limiter_error),
                correlation_id=correlation_id,
                exc_info=True,
            )
            raise NotionSyncError(f"Rate limiter error: {limiter_error}") from limiter_error

        try:
            # Error classification
            if response.status_code in [400, 401, 403, 404]:
                # Permanent errors - don't retry
                raise NotionSyncError(
                    f"Notion API permanent error: {response.status_code} - {response.text}"
                )

            if response.status_code in [429, 409, 503]:
                # Transient errors - retry with backoff
                retry_after = response.headers.get("Retry-After", "1")
                raise NotionSyncRetryError(
                    f"Notion API error: {response.status_code} (retry after {retry_after}s)"
                )

            response.raise_for_status()

            log.info(
                "notion_asset_sync_success",
                page_id=page_id,
                asset_count=len(assets),
                correlation_id=correlation_id,
            )

            result: dict[str, Any] = response.json()
            return result

        except (NotionSyncError, NotionSyncRetryError):
            # Re-raise for retry logic
            raise

        except Exception as e:
            # Unexpected errors - log and don't retry
            log.error(
                "notion_asset_sync_unexpected_error",
                page_id=page_id,
                error=str(e),
                correlation_id=correlation_id,
                exc_info=True,
            )
            raise NotionSyncError(f"Unexpected error: {e}") from e


async def sync_task_assets_to_notion(
    db: AsyncSession, task_id: UUID, notion_auth_token: str
) -> None:
    """Sync all unsynced assets for task to Notion (fire-and-forget background job).

    This function implements the fire-and-forget pattern:
    1. Load unsynced assets from database (short transaction)
    2. Close database connection
    3. Call Notion API (no DB lock)
    4. Reopen database connection
    5. Mark assets as synced (short transaction)

    Args:
        db: Database session
        task_id: Task UUID
        notion_auth_token: Notion API token (from channel credentials)

    Raises:
        NotionSyncError: Permanent sync failure (logged and alerted)
    """
    correlation_id = get_correlation_id()

    # Step 1: Load task and unsynced assets (read operation, implicit transaction)
    task = await db.get(Task, task_id)
    if not task or not task.notion_page_id:
        log.warning(
            "notion_sync_skipped_no_page_id",
            task_id=str(task_id),
            correlation_id=correlation_id,
        )
        return

    page_id = task.notion_page_id
    assets = await get_unsynced_assets(db, task_id)

    if not assets:
        log.info(
            "notion_sync_skipped_no_assets",
            task_id=str(task_id),
            correlation_id=correlation_id,
        )
        return

    # Step 2: Sync to Notion (NO DB LOCK)
    notion_service = NotionAssetSyncService(notion_auth_token)
    try:
        await notion_service.update_asset_urls(page_id, assets)
    except NotionSyncError as e:
        log.error(
            "notion_asset_sync_permanent_failure",
            task_id=str(task_id),
            page_id=page_id,
            error=str(e),
            correlation_id=correlation_id,
        )
        # Don't raise - log and continue (don't block pipeline)
        return
    except NotionSyncRetryError as e:
        log.error(
            "notion_asset_sync_retry_exhausted",
            task_id=str(task_id),
            page_id=page_id,
            error=str(e),
            correlation_id=correlation_id,
        )
        # Don't raise - log and continue (don't block pipeline)
        return
    finally:
        await notion_service.close()

    # Step 3: Mark assets as synced (single transaction for all assets)
    asset_ids = [asset.id for asset in assets]
    await mark_assets_synced_batch(db, asset_ids)

    log.info(
        "notion_asset_sync_complete",
        task_id=str(task_id),
        asset_count=len(assets),
        correlation_id=correlation_id,
    )
