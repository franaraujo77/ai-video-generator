"""Catbox.moe image upload client.

This module provides a client for uploading images to catbox.moe, a free
image hosting service. The Kling API requires publicly accessible image URLs,
and catbox.moe provides this without authentication requirements.

Architecture Pattern:
    Simple HTTP client wrapper - no retry logic (handled at service layer)
    Async-only interface using httpx.AsyncClient

Dependencies:
    - httpx: Async HTTP client library

Usage:
    from app.clients.catbox import CatboxClient

    client = CatboxClient()
    url = await client.upload_image(Path("composite.png"))
    print(f"Uploaded: {url}")
    await client.close()

Security:
    - No authentication required (public service)
    - File validation prevents uploading nonexistent files
    - Uses HTTPS for secure transmission
"""

from pathlib import Path

import httpx

from app.utils.logging import get_logger

log = get_logger(__name__)


class CatboxClient:
    """Client for uploading images to catbox.moe for public hosting.

    catbox.moe is a free image hosting service that returns public URLs.
    Kling API requires publicly accessible image URLs as seed images.

    Attributes:
        base_url: catbox.moe API endpoint for file uploads
        client: Async HTTP client for making requests

    Example:
        >>> client = CatboxClient()
        >>> url = await client.upload_image(Path("image.png"))
        >>> print(url)
        "https://files.catbox.moe/abc123.png"
        >>> await client.close()
    """

    def __init__(self) -> None:
        """Initialize catbox.moe client with default configuration."""
        self.base_url = "https://catbox.moe/user/api.php"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def upload_image(self, image_path: Path) -> str:
        """Upload image to catbox.moe and return public URL.

        Args:
            image_path: Path to image file (PNG, JPEG, etc.)

        Returns:
            Public catbox URL (e.g., "https://files.catbox.moe/abc123.png")

        Raises:
            FileNotFoundError: If image file doesn't exist
            httpx.HTTPStatusError: If catbox.moe returns HTTP error
            httpx.ConnectError: If network connection fails

        Example:
            >>> client = CatboxClient()
            >>> url = await client.upload_image(Path("assets/composites/clip_01.png"))
            >>> print(url)
            "https://files.catbox.moe/xyz789.png"
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        # Validate file size
        file_size = image_path.stat().st_size
        if file_size == 0:
            raise ValueError(f"Image file is empty: {image_path}")
        if file_size > 200 * 1024 * 1024:  # 200MB limit
            raise ValueError(f"Image file too large ({file_size} bytes): {image_path}")

        # Read file synchronously (OK: catbox.moe API requires sync file handle)
        with open(image_path, "rb") as f:  # noqa: ASYNC230
            files = {"fileToUpload": f}
            data = {"reqtype": "fileupload"}

            response = await self.client.post(
                self.base_url,
                data=data,
                files=files
            )
            response.raise_for_status()

            url = response.text.strip()
            log.info("catbox_upload_success", image_path=str(image_path), url=url)
            return url

    async def close(self) -> None:
        """Close HTTP client connection.

        Should be called when done using the client to clean up resources.

        Example:
            >>> client = CatboxClient()
            >>> # ... use client ...
            >>> await client.close()
        """
        await self.client.aclose()
