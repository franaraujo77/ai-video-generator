"""Asset URL Storage Service (Story 8.3).

Provides asset URL recording functionality for video generation pipeline.
Records URLs in database for access from Notion and supports both Notion-hosted
and R2 storage strategies.

Architecture:
- Database persistence: AssetMetadata model
- Storage strategy resolution: StorageStrategyService
- URL validation: HEAD request to verify accessibility
- Correlation IDs: Distributed tracing from Story 8.1

Dependencies:
- Story 1.5: StorageStrategyService for channel storage config
- Story 8.1: Correlation ID context variables
- Epic 3: Worker integration for asset generation
"""

from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AssetMetadata
from app.utils.context import get_correlation_id
from app.utils.logging import get_logger

log = get_logger(__name__)

__all__ = [
    "get_task_assets",
    "get_unsynced_assets",
    "mark_assets_synced_batch",
    "mark_synced",
    "record_asset_url",
]


async def record_asset_url(
    db: AsyncSession,
    task_id: UUID,
    channel_id: UUID,
    asset_type: str,
    asset_name: str,
    storage_strategy: str,
    asset_url: str,
    local_file_path: str | None = None,
) -> AssetMetadata:
    """Record asset URL in database for Notion sync.

    Persists asset metadata to database for background Notion sync.
    Validates URL accessibility before storing.

    Args:
        db: Database session (AsyncSession from SQLAlchemy)
        task_id: Task UUID
        channel_id: Channel UUID
        asset_type: Asset type (character, environment, video_clip, etc.)
        asset_name: Asset filename or identifier
        storage_strategy: Storage backend ("notion" or "r2")
        asset_url: Public URL for asset access
        local_file_path: Optional local filesystem path

    Returns:
        AssetMetadata record with URL and metadata

    Raises:
        ValueError: If URL is not accessible (404, 403, etc.)
        httpx.HTTPError: If validation request fails

    Example:
        >>> asset = await record_asset_url(
        ...     db=db,
        ...     task_id=task.id,
        ...     channel_id=channel.id,
        ...     asset_type="character",
        ...     asset_name="bulbasaur_01.png",
        ...     storage_strategy="r2",
        ...     asset_url="https://bucket.r2.dev/poke1/vid_123/characters/bulbasaur.png",
        ...     local_file_path="/app/workspace/poke1/vid_123/assets/bulbasaur.png",
        ... )
    """
    correlation_id = get_correlation_id()

    try:
        # Validate URL accessibility (HEAD request)
        # Timeout increased to 10s for production reliability (Notion S3 + R2 can be slow)
        async with httpx.AsyncClient() as client:
            response = await client.head(asset_url, timeout=10.0, follow_redirects=True)
            if response.status_code not in [200, 301, 302]:
                raise ValueError(
                    f"Asset URL not accessible: {asset_url} (status: {response.status_code})"
                )

        # Create asset metadata record
        asset = AssetMetadata(
            task_id=task_id,
            channel_id=channel_id,
            asset_type=asset_type,
            asset_name=asset_name,
            storage_strategy=storage_strategy,
            local_file_path=local_file_path,
            asset_url=asset_url,
            notion_synced_at=None,  # Not synced yet
        )

        db.add(asset)
        await db.commit()
        await db.refresh(asset)

        log.info(
            "asset_url_recorded",
            task_id=str(task_id),
            channel_id=str(channel_id),
            asset_type=asset_type,
            asset_name=asset_name,
            asset_url=asset_url,
            storage_strategy=storage_strategy,
            correlation_id=correlation_id,
        )

        return asset

    except Exception as e:
        log.error(
            "asset_url_recording_failed",
            task_id=str(task_id),
            asset_type=asset_type,
            asset_name=asset_name,
            error=str(e),
            correlation_id=correlation_id,
            exc_info=True,
        )
        await db.rollback()
        raise


async def get_unsynced_assets(db: AsyncSession, task_id: UUID) -> list[AssetMetadata]:
    """Get all assets for task that haven't been synced to Notion.

    Args:
        db: Database session
        task_id: Task UUID

    Returns:
        List of AssetMetadata records with notion_synced_at IS NULL
    """
    stmt = select(AssetMetadata).where(
        AssetMetadata.task_id == task_id, AssetMetadata.notion_synced_at.is_(None)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_task_assets(
    db: AsyncSession, task_id: UUID, asset_type: str | None = None
) -> list[AssetMetadata]:
    """Get all assets for task, optionally filtered by asset type.

    Args:
        db: Database session
        task_id: Task UUID
        asset_type: Optional asset type filter (character, video_clip, etc.)

    Returns:
        List of AssetMetadata records ordered by created_at
    """
    stmt = select(AssetMetadata).where(AssetMetadata.task_id == task_id)

    if asset_type:
        stmt = stmt.where(AssetMetadata.asset_type == asset_type)

    stmt = stmt.order_by(AssetMetadata.created_at)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def mark_synced(db: AsyncSession, asset_id: UUID) -> None:
    """Mark asset as synced to Notion with timestamp.

    Args:
        db: Database session
        asset_id: AssetMetadata UUID

    Returns:
        None
    """
    correlation_id = get_correlation_id()
    asset = await db.get(AssetMetadata, asset_id)
    if asset:
        asset.notion_synced_at = datetime.now(timezone.utc)
        await db.commit()
    else:
        log.warning(
            "mark_synced_asset_not_found",
            asset_id=str(asset_id),
            correlation_id=correlation_id,
            msg="Asset not found when marking as synced (may have been deleted)",
        )


async def mark_assets_synced_batch(db: AsyncSession, asset_ids: list[UUID]) -> None:
    """Mark multiple assets as synced to Notion with single transaction.

    More efficient than mark_synced() for bulk operations - uses single commit.

    Args:
        db: Database session
        asset_ids: List of AssetMetadata UUIDs to mark as synced

    Returns:
        None
    """
    correlation_id = get_correlation_id()
    sync_time = datetime.now(timezone.utc)

    updated_count = 0
    for asset_id in asset_ids:
        asset = await db.get(AssetMetadata, asset_id)
        if asset:
            asset.notion_synced_at = sync_time
            updated_count += 1
        else:
            log.warning(
                "mark_synced_asset_not_found",
                asset_id=str(asset_id),
                correlation_id=correlation_id,
            )

    # Single commit for all updates
    await db.commit()

    log.info(
        "assets_marked_synced_batch",
        total_requested=len(asset_ids),
        updated_count=updated_count,
        correlation_id=correlation_id,
    )
