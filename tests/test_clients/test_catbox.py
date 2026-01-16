"""Tests for CatboxClient.

This module tests the catbox.moe image upload client used to host
composite images for Kling API video generation.

Test Coverage:
- Successful image upload
- Upload failure scenarios (network errors, invalid files)
- File validation (missing files, invalid paths)
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx

from app.clients.catbox import CatboxClient


class TestCatboxClient:
    """Test suite for CatboxClient."""

    @pytest.fixture
    def client(self):
        """Create CatboxClient instance."""
        return CatboxClient()

    @pytest.fixture
    def temp_image(self, tmp_path):
        """Create a temporary test image file."""
        image_path = tmp_path / "test_composite.png"
        image_path.write_bytes(b"fake-png-data")
        return image_path

    @pytest.mark.asyncio
    async def test_upload_image_success(self, client, temp_image):
        """Test successful image upload to catbox.moe."""
        expected_url = "https://files.catbox.moe/abc123.png"

        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            # Mock successful response
            mock_response = Mock()
            mock_response.text = expected_url
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            # Upload image
            result_url = await client.upload_image(temp_image)

            # Verify result
            assert result_url == expected_url

            # Verify API call
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert client.base_url in str(call_args)

    @pytest.mark.asyncio
    async def test_upload_image_file_not_found(self, client):
        """Test upload fails when image file doesn't exist."""
        nonexistent_path = Path("/nonexistent/file.png")

        with pytest.raises(FileNotFoundError, match="Image file not found"):
            await client.upload_image(nonexistent_path)

    @pytest.mark.asyncio
    async def test_upload_image_http_error(self, client, temp_image):
        """Test upload fails when catbox.moe returns HTTP error."""
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            # Mock HTTP error response
            mock_response = Mock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=Mock(),
                response=Mock(status_code=500)
            )
            mock_post.return_value = mock_response

            with pytest.raises(httpx.HTTPStatusError):
                await client.upload_image(temp_image)

    @pytest.mark.asyncio
    async def test_upload_image_network_error(self, client, temp_image):
        """Test upload fails when network error occurs."""
        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            # Mock network error
            mock_post.side_effect = httpx.ConnectError("Connection failed")

            with pytest.raises(httpx.ConnectError):
                await client.upload_image(temp_image)

    @pytest.mark.asyncio
    async def test_close_client(self, client):
        """Test client connection is closed properly."""
        with patch.object(client.client, 'aclose', new_callable=AsyncMock) as mock_close:
            await client.close()
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_multiple_images(self, client, tmp_path):
        """Test uploading multiple images in sequence."""
        # Create multiple test images
        images = []
        for i in range(3):
            image_path = tmp_path / f"image_{i}.png"
            image_path.write_bytes(b"fake-png-data")
            images.append(image_path)

        expected_urls = [
            "https://files.catbox.moe/abc123.png",
            "https://files.catbox.moe/def456.png",
            "https://files.catbox.moe/ghi789.png",
        ]

        with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
            # Mock responses for each upload
            mock_post.side_effect = [
                Mock(text=url, raise_for_status=Mock())
                for url in expected_urls
            ]

            # Upload all images
            results = []
            for image in images:
                url = await client.upload_image(image)
                results.append(url)

            # Verify all uploads succeeded
            assert results == expected_urls
            assert mock_post.call_count == 3
