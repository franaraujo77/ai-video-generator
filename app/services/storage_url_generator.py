"""Storage URL Generator Service (Story 8.3).

Provides storage strategy resolution and URL generation for asset URLs.
Supports both Notion-hosted and R2 storage strategies.

Usage:
    generator = StorageURLGenerator(channel)
    url = await generator.generate_asset_url(asset_path, response_data)
"""

from typing import Any

from app.models import Channel
from app.utils.logging import get_logger

log = get_logger(__name__)

__all__ = ["StorageURLGenerator", "extract_notion_file_url", "generate_r2_public_url"]


def extract_notion_file_url(notion_response: dict[str, Any], property_name: str = "Asset") -> str:
    """Extract file URL from Notion API response.

    Notion file upload responses have this structure:
    {
        "properties": {
            "Asset": {
                "files": [
                    {
                        "file": {
                            "url": "https://prod-files-secure.s3.us-west-2.amazonaws.com/..."
                        }
                    }
                ]
            }
        }
    }

    Args:
        notion_response: Notion API response dict
        property_name: Notion property name containing file (default: "Asset")

    Returns:
        str: Public file URL from Notion S3 storage

    Raises:
        ValueError: If URL cannot be extracted from response
    """
    try:
        files = notion_response["properties"][property_name]["files"]
        if not files:
            raise ValueError(f"No files found in Notion property '{property_name}'")

        file_url = files[0]["file"]["url"]
        return file_url
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(f"Failed to extract file URL from Notion response: {e}") from e


def generate_r2_public_url(
    bucket_name: str,
    channel_id: str,
    project_id: str,
    asset_path: str,
) -> str:
    """Generate public R2 URL for asset.

    R2 URL format: https://{bucket}.r2.dev/{channel_id}/{project_id}/{asset_path}

    Args:
        bucket_name: R2 bucket name (from channel.r2_bucket_name)
        channel_id: Channel identifier (from channel.channel_id)
        project_id: Task/project identifier (from task.id or task notion_page_id)
        asset_path: Relative asset path (e.g., "assets/characters/bulbasaur_01.png")

    Returns:
        str: Public R2 URL

    Example:
        >>> generate_r2_public_url(
        ...     "poke-assets",
        ...     "poke1",
        ...     "vid_123",
        ...     "assets/characters/bulbasaur_01.png"
        ... )
        "https://poke-assets.r2.dev/poke1/vid_123/assets/characters/bulbasaur_01.png"
    """
    # Normalize path (remove leading slash if present)
    if asset_path.startswith("/"):
        asset_path = asset_path[1:]

    return f"https://{bucket_name}.r2.dev/{channel_id}/{project_id}/{asset_path}"


class StorageURLGenerator:
    """Storage URL generator for channel storage strategy."""

    def __init__(self, channel: Channel):
        """Initialize generator with channel configuration.

        Args:
            channel: Channel model with storage_strategy configuration
        """
        self.channel = channel
        self.strategy = channel.storage_strategy

    async def generate_asset_url(
        self,
        asset_path: str,
        notion_response: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> str:
        """Generate asset URL based on channel storage strategy.

        Args:
            asset_path: Relative asset path (e.g., "assets/characters/bulbasaur_01.png")
            notion_response: Notion API response (required if strategy="notion")
            project_id: Task/project ID (required if strategy="r2")

        Returns:
            str: Public asset URL (Notion S3 or R2)

        Raises:
            ValueError: If required parameters missing for strategy

        Example (Notion storage):
            >>> generator = StorageURLGenerator(channel)
            >>> url = await generator.generate_asset_url(
            ...     "assets/char.png",
            ...     notion_response=notion_upload_response
            ... )

        Example (R2 storage):
            >>> generator = StorageURLGenerator(channel)
            >>> url = await generator.generate_asset_url(
            ...     "assets/char.png",
            ...     project_id="vid_123"
            ... )
        """
        if self.strategy == "notion":
            if not notion_response:
                raise ValueError("notion_response required for Notion storage strategy")

            return extract_notion_file_url(notion_response)

        elif self.strategy == "r2":
            if not project_id:
                raise ValueError("project_id required for R2 storage strategy")

            if not self.channel.r2_bucket_name:
                raise ValueError(f"Channel {self.channel.channel_id} has no R2 bucket configured")

            return generate_r2_public_url(
                bucket_name=self.channel.r2_bucket_name,
                channel_id=self.channel.channel_id,
                project_id=project_id,
                asset_path=asset_path,
            )

        else:
            raise ValueError(f"Unknown storage strategy: {self.strategy}")

    def is_notion_storage(self) -> bool:
        """Check if channel uses Notion storage."""
        return self.strategy == "notion"

    def is_r2_storage(self) -> bool:
        """Check if channel uses R2 storage."""
        return self.strategy == "r2"
