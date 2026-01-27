"""Factory for creating AssetMetadata test instances (Story 8.3)."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.models import AssetMetadata


def create_asset_metadata(
    task_id: UUID | None = None,
    channel_id: UUID | None = None,
    asset_type: str = "character",
    asset_name: str = "test_asset.png",
    asset_url: str = "https://example.com/asset.png",
    storage_strategy: str = "notion",
    local_file_path: str | None = None,
    notion_synced_at: datetime | None = None,
) -> AssetMetadata:
    """Factory for creating AssetMetadata test records.

    Args:
        task_id: Task UUID (generates random if None)
        channel_id: Channel UUID (generates random if None)
        asset_type: Asset type (character, environment, video_clip, etc.)
        asset_name: Asset filename or identifier
        asset_url: Public URL for asset access
        storage_strategy: Storage backend ("notion" or "r2")
        local_file_path: Optional local filesystem path
        notion_synced_at: Optional sync timestamp (None = not synced)

    Returns:
        AssetMetadata instance (not persisted to database)

    Example:
        >>> asset = create_asset_metadata(
        ...     task_id=task.id,
        ...     channel_id=channel.id,
        ...     asset_type="character",
        ...     asset_name="bulbasaur_01.png",
        ... )
    """
    return AssetMetadata(
        id=uuid4(),
        task_id=task_id or uuid4(),
        channel_id=channel_id or uuid4(),
        asset_type=asset_type,
        asset_name=asset_name,
        asset_url=asset_url,
        storage_strategy=storage_strategy,
        local_file_path=local_file_path,
        notion_synced_at=notion_synced_at,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
