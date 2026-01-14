"""Tests for generate_video.py script.

Tests the video generation helper functions with mocked external services.
API calls to KIE.ai and catbox.moe are mocked.

Priority: P1-P2 - Critical path but requires mocking external APIs.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_video import download_video, poll_task_status, upload_image_to_catbox

from tests.support.factories.image_factory import (
    create_test_image,
    save_test_image,
)


class TestUploadImageToCatbox:
    """Tests for upload_image_to_catbox function."""

    def test_p1_returns_url_on_successful_upload(self, tmp_path: Path):
        """[P1] Should return URL when upload succeeds."""
        # GIVEN: A test image and mocked successful upload
        image_path = tmp_path / "test.png"
        save_test_image(create_test_image(100, 100), image_path)

        expected_url = "https://files.catbox.moe/abc123.png"

        with patch("generate_video.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = expected_url
            mock_post.return_value = mock_response

            # WHEN: Uploading image
            result = upload_image_to_catbox(str(image_path))

            # THEN: Returns the URL
            assert result == expected_url

    def test_p1_returns_none_on_http_error(self, tmp_path: Path):
        """[P1] Should return None on HTTP error."""
        # GIVEN: A test image and mocked failed upload
        image_path = tmp_path / "test.png"
        save_test_image(create_test_image(100, 100), image_path)

        with patch("generate_video.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response

            # WHEN: Uploading image
            result = upload_image_to_catbox(str(image_path))

            # THEN: Returns None
            assert result is None

    def test_p2_returns_none_on_invalid_url_response(self, tmp_path: Path):
        """[P2] Should return None when response is not a valid URL."""
        # GIVEN: A test image and mocked invalid response
        image_path = tmp_path / "test.png"
        save_test_image(create_test_image(100, 100), image_path)

        with patch("generate_video.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "ERROR: Upload failed"  # Not a URL
            mock_post.return_value = mock_response

            # WHEN: Uploading image
            result = upload_image_to_catbox(str(image_path))

            # THEN: Returns None
            assert result is None

    def test_p2_handles_empty_response(self, tmp_path: Path):
        """[P2] Should return None on empty response."""
        # GIVEN: A test image and mocked empty response
        image_path = tmp_path / "test.png"
        save_test_image(create_test_image(100, 100), image_path)

        with patch("generate_video.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = ""
            mock_post.return_value = mock_response

            # WHEN: Uploading image
            result = upload_image_to_catbox(str(image_path))

            # THEN: Returns None
            assert result is None


class TestPollTaskStatus:
    """Tests for poll_task_status function."""

    def test_p1_returns_video_url_on_success(self):
        """[P1] Should return video URL when task succeeds."""
        # GIVEN: Mocked successful task completion
        task_id = "test-task-123"
        api_key = "test-api-key"
        expected_url = "https://cdn.kie.ai/video/result.mp4"

        with patch("generate_video.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "code": 200,
                "data": {
                    "state": "success",
                    "resultJson": f'{{"resultUrls": ["{expected_url}"]}}',
                },
            }
            mock_get.return_value = mock_response

            # WHEN: Polling task status
            result = poll_task_status(task_id, api_key, max_wait=10)

            # THEN: Returns video URL
            assert result == expected_url

    def test_p1_returns_none_on_task_failure(self):
        """[P1] Should return None when task fails."""
        # GIVEN: Mocked failed task
        task_id = "test-task-123"
        api_key = "test-api-key"

        with patch("generate_video.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "code": 200,
                "data": {
                    "state": "failed",
                    "error": "Generation failed",
                },
            }
            mock_get.return_value = mock_response

            # WHEN: Polling task status
            result = poll_task_status(task_id, api_key, max_wait=10)

            # THEN: Returns None
            assert result is None

    def test_p1_returns_none_on_api_error_code(self):
        """[P1] Should return None when API returns error code."""
        # GIVEN: Mocked API error
        task_id = "test-task-123"
        api_key = "test-api-key"

        with patch("generate_video.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "code": 500,
                "message": "Internal error",
            }
            mock_get.return_value = mock_response

            # WHEN: Polling task status
            result = poll_task_status(task_id, api_key, max_wait=10)

            # THEN: Returns None
            assert result is None

    def test_p2_returns_none_when_result_urls_empty(self):
        """[P2] Should return None when resultUrls is empty."""
        # GIVEN: Mocked success but empty URLs
        task_id = "test-task-123"
        api_key = "test-api-key"

        with patch("generate_video.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "code": 200,
                "data": {
                    "state": "success",
                    "resultJson": '{"resultUrls": []}',
                },
            }
            mock_get.return_value = mock_response

            # WHEN: Polling task status
            result = poll_task_status(task_id, api_key, max_wait=10)

            # THEN: Returns None
            assert result is None

    def test_p2_returns_none_on_malformed_result_json(self):
        """[P2] Should return None when resultJson is malformed."""
        # GIVEN: Mocked success but malformed JSON
        task_id = "test-task-123"
        api_key = "test-api-key"

        with patch("generate_video.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "code": 200,
                "data": {
                    "state": "success",
                    "resultJson": "not valid json",
                },
            }
            mock_get.return_value = mock_response

            # WHEN: Polling task status
            result = poll_task_status(task_id, api_key, max_wait=10)

            # THEN: Returns None
            assert result is None


class TestDownloadVideo:
    """Tests for download_video function."""

    def test_p1_downloads_video_to_file(self, tmp_path: Path):
        """[P1] Should download video content to specified file."""
        # GIVEN: Mocked video download
        video_url = "https://cdn.example.com/video.mp4"
        output_path = tmp_path / "video.mp4"
        video_content = b"fake video data for testing"

        with patch("generate_video.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.iter_content.return_value = [video_content]
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # WHEN: Downloading video
            download_video(video_url, str(output_path))

            # THEN: File exists with content
            assert output_path.exists()
            assert output_path.read_bytes() == video_content

    def test_p1_creates_output_directory(self, tmp_path: Path):
        """[P1] Should create output directory if it doesn't exist."""
        # GIVEN: Output in nested non-existent directory
        video_url = "https://cdn.example.com/video.mp4"
        output_path = tmp_path / "nested" / "deep" / "video.mp4"
        video_content = b"fake video data"

        with patch("generate_video.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.iter_content.return_value = [video_content]
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # WHEN: Downloading video
            download_video(video_url, str(output_path))

            # THEN: File exists in newly created directory
            assert output_path.exists()

    def test_p2_handles_chunked_download(self, tmp_path: Path):
        """[P2] Should properly handle chunked downloads."""
        # GIVEN: Multi-chunk download
        video_url = "https://cdn.example.com/video.mp4"
        output_path = tmp_path / "video.mp4"
        chunks = [b"chunk1", b"chunk2", b"chunk3"]

        with patch("generate_video.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.iter_content.return_value = chunks
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # WHEN: Downloading video
            download_video(video_url, str(output_path))

            # THEN: File contains all chunks
            assert output_path.read_bytes() == b"chunk1chunk2chunk3"
