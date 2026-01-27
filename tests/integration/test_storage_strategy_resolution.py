"""Integration tests for storage strategy resolution (Story 8.3).

Tests URL generation for both Notion and R2 storage strategies.
"""

import pytest

from app.models import Channel
from app.services.storage_url_generator import (
    StorageURLGenerator,
    extract_notion_file_url,
    generate_r2_public_url,
)


def test_extract_notion_file_url_success():
    """Test extracting file URL from Notion API response."""
    notion_response = {
        "properties": {
            "Asset": {
                "files": [
                    {
                        "file": {
                            "url": "https://prod-files-secure.s3.us-west-2.amazonaws.com/test/asset.png"
                        }
                    }
                ]
            }
        }
    }

    url = extract_notion_file_url(notion_response)
    assert url == "https://prod-files-secure.s3.us-west-2.amazonaws.com/test/asset.png"


def test_extract_notion_file_url_custom_property():
    """Test extracting file URL from custom Notion property."""
    notion_response = {
        "properties": {
            "MyFile": {
                "files": [
                    {
                        "file": {
                            "url": "https://notion.so/files/test.png"
                        }
                    }
                ]
            }
        }
    }

    url = extract_notion_file_url(notion_response, property_name="MyFile")
    assert url == "https://notion.so/files/test.png"


def test_extract_notion_file_url_missing_property():
    """Test error handling when property not found."""
    notion_response = {
        "properties": {
            "OtherProperty": {}
        }
    }

    with pytest.raises(ValueError, match="Failed to extract file URL"):
        extract_notion_file_url(notion_response)


def test_extract_notion_file_url_empty_files():
    """Test error handling when files array is empty."""
    notion_response = {
        "properties": {
            "Asset": {
                "files": []
            }
        }
    }

    with pytest.raises(ValueError, match="No files found"):
        extract_notion_file_url(notion_response)


def test_generate_r2_public_url_standard():
    """Test R2 public URL generation with standard path."""
    url = generate_r2_public_url(
        bucket_name="poke-assets",
        channel_id="poke1",
        project_id="vid_123",
        asset_path="assets/characters/bulbasaur_01.png",
    )

    assert url == "https://poke-assets.r2.dev/poke1/vid_123/assets/characters/bulbasaur_01.png"


def test_generate_r2_public_url_leading_slash():
    """Test R2 URL generation normalizes leading slash."""
    url = generate_r2_public_url(
        bucket_name="test-bucket",
        channel_id="test1",
        project_id="proj1",
        asset_path="/assets/test.png",
    )

    assert url == "https://test-bucket.r2.dev/test1/proj1/assets/test.png"


def test_generate_r2_public_url_video_clip():
    """Test R2 URL generation for video clip."""
    url = generate_r2_public_url(
        bucket_name="video-assets",
        channel_id="nature1",
        project_id="doc_456",
        asset_path="videos/clips/clip_01.mp4",
    )

    assert url == "https://video-assets.r2.dev/nature1/doc_456/videos/clips/clip_01.mp4"


@pytest.mark.asyncio
async def test_storage_url_generator_notion_strategy():
    """Test StorageURLGenerator with Notion storage strategy."""
    channel = Channel(
        channel_id="test_channel",
        channel_name="Test Channel",
        storage_strategy="notion",
        max_concurrent=2,
    )

    generator = StorageURLGenerator(channel)

    assert generator.is_notion_storage()
    assert not generator.is_r2_storage()

    notion_response = {
        "properties": {
            "Asset": {
                "files": [
                    {
                        "file": {
                            "url": "https://notion.so/files/test.png"
                        }
                    }
                ]
            }
        }
    }

    url = await generator.generate_asset_url(
        asset_path="assets/char.png",
        notion_response=notion_response,
    )

    assert url == "https://notion.so/files/test.png"


@pytest.mark.asyncio
async def test_storage_url_generator_r2_strategy():
    """Test StorageURLGenerator with R2 storage strategy."""
    channel = Channel(
        channel_id="test_channel",
        channel_name="Test Channel",
        storage_strategy="r2",
        r2_bucket_name="test-bucket",
        max_concurrent=2,
    )

    generator = StorageURLGenerator(channel)

    assert generator.is_r2_storage()
    assert not generator.is_notion_storage()

    url = await generator.generate_asset_url(
        asset_path="assets/char.png",
        project_id="proj_123",
    )

    assert url == "https://test-bucket.r2.dev/test_channel/proj_123/assets/char.png"


@pytest.mark.asyncio
async def test_storage_url_generator_notion_missing_response():
    """Test StorageURLGenerator raises error when Notion response missing."""
    channel = Channel(
        channel_id="test_channel",
        channel_name="Test Channel",
        storage_strategy="notion",
        max_concurrent=2,
    )

    generator = StorageURLGenerator(channel)

    with pytest.raises(ValueError, match="notion_response required"):
        await generator.generate_asset_url(asset_path="assets/char.png")


@pytest.mark.asyncio
async def test_storage_url_generator_r2_missing_project_id():
    """Test StorageURLGenerator raises error when project_id missing."""
    channel = Channel(
        channel_id="test_channel",
        channel_name="Test Channel",
        storage_strategy="r2",
        r2_bucket_name="test-bucket",
        max_concurrent=2,
    )

    generator = StorageURLGenerator(channel)

    with pytest.raises(ValueError, match="project_id required"):
        await generator.generate_asset_url(asset_path="assets/char.png")


@pytest.mark.asyncio
async def test_storage_url_generator_r2_missing_bucket():
    """Test StorageURLGenerator raises error when R2 bucket not configured."""
    channel = Channel(
        channel_id="test_channel",
        channel_name="Test Channel",
        storage_strategy="r2",
        r2_bucket_name=None,  # Missing bucket configuration
        max_concurrent=2,
    )

    generator = StorageURLGenerator(channel)

    with pytest.raises(ValueError, match="no R2 bucket configured"):
        await generator.generate_asset_url(
            asset_path="assets/char.png",
            project_id="proj_123",
        )


@pytest.mark.asyncio
async def test_storage_url_generator_unknown_strategy():
    """Test StorageURLGenerator raises error for unknown storage strategy."""
    channel = Channel(
        channel_id="test_channel",
        channel_name="Test Channel",
        storage_strategy="s3",  # Unknown strategy
        max_concurrent=2,
    )

    generator = StorageURLGenerator(channel)

    with pytest.raises(ValueError, match="Unknown storage strategy"):
        await generator.generate_asset_url(asset_path="assets/char.png")
