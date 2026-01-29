"""Asset URL API endpoints (Story 8.3).

Provides HTTP API for accessing asset URLs and triggering manual Notion sync.
Used by content creators to access all generated assets directly from API.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Channel, Task
from app.services.asset_url_storage import get_task_assets, get_unsynced_assets
from app.services.credential_service import CredentialService
from app.services.notion_asset_sync import sync_task_assets_to_notion
from app.utils.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["asset-urls"])


class AssetMetadataResponse(BaseModel):
    """Response schema for asset metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    channel_id: UUID
    asset_type: str
    asset_name: str
    asset_url: str
    storage_strategy: str
    notion_synced_at: datetime | None
    created_at: datetime


class TaskAssetsResponse(BaseModel):
    """Response schema for task assets list."""

    task_id: UUID
    asset_count: int
    assets: list[AssetMetadataResponse]


@router.get("/tasks/{task_id}/assets", response_model=TaskAssetsResponse)
async def get_task_asset_urls(
    task_id: UUID,
    asset_type: str | None = Query(
        None, description="Filter by asset type (character, video_clip, etc.)"
    ),
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> TaskAssetsResponse:
    """Get all asset URLs for a task, optionally filtered by asset type.

    Args:
        task_id: Task UUID
        asset_type: Optional asset type filter
        db: Database session (injected)

    Returns:
        TaskAssetsResponse with list of assets

    Raises:
        HTTPException: 404 if no assets found for task
    """
    assets = await get_task_assets(db, task_id, asset_type)

    if not assets:
        raise HTTPException(status_code=404, detail="No assets found for task")

    return TaskAssetsResponse(
        task_id=task_id,
        asset_count=len(assets),
        assets=[AssetMetadataResponse.model_validate(asset) for asset in assets],
    )


@router.get("/tasks/{task_id}/assets/unsynced", response_model=TaskAssetsResponse)
async def get_task_unsynced_assets(
    task_id: UUID,
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> TaskAssetsResponse:
    """Get all assets for task that haven't been synced to Notion.

    Useful for debugging Notion sync failures and manual recovery.

    Args:
        task_id: Task UUID
        db: Database session (injected)

    Returns:
        TaskAssetsResponse with unsynced assets only
    """
    assets = await get_unsynced_assets(db, task_id)

    return TaskAssetsResponse(
        task_id=task_id,
        asset_count=len(assets),
        assets=[AssetMetadataResponse.model_validate(asset) for asset in assets],
    )


@router.post("/tasks/{task_id}/sync-assets")
async def trigger_asset_sync(
    task_id: UUID,
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict:
    """Trigger manual Notion asset sync for task.

    Retries failed Notion syncs for all unsynced assets. Use this endpoint
    when automatic sync fails and assets need manual recovery.

    Args:
        task_id: Task UUID
        db: Database session (injected)

    Returns:
        Success message with sync status

    Raises:
        HTTPException: 404 if task not found
        HTTPException: 400 if task has no Notion page ID
        HTTPException: 400 if channel has no Notion token
    """
    # Get task and validate
    task = await db.get(Task, task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if not task.notion_page_id:
        raise HTTPException(status_code=400, detail="Task has no Notion page ID")

    # Get channel for Notion token
    channel = await db.get(Channel, task.channel_id)
    if not channel or not channel.notion_token_encrypted:
        raise HTTPException(status_code=400, detail="Channel has no Notion token")

    # Decrypt Notion token
    credential_service = CredentialService()
    notion_token = credential_service.decrypt(channel.notion_token_encrypted)

    # Get unsynced assets count before sync
    unsynced_before = await get_unsynced_assets(db, task_id)

    # Trigger sync
    await sync_task_assets_to_notion(db, task_id, notion_token)

    # Get unsynced assets count after sync
    unsynced_after = await get_unsynced_assets(db, task_id)

    synced_count = len(unsynced_before) - len(unsynced_after)

    log.info(
        "manual_asset_sync_triggered",
        task_id=str(task_id),
        unsynced_before=len(unsynced_before),
        unsynced_after=len(unsynced_after),
        synced_count=synced_count,
    )

    return {
        "success": True,
        "message": "Asset sync triggered",
        "unsynced_before": len(unsynced_before),
        "unsynced_after": len(unsynced_after),
        "synced_count": synced_count,
    }
