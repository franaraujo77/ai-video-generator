"""Tests for VideoGenerationService.

This module tests the video generation service that orchestrates
the Kling 2.5 API video generation workflow.

Test Coverage:
- Video manifest creation
- Video generation orchestration
- Catbox upload integration
- Cost calculation
- Partial resume functionality
- Rate limiting coordination
- Error handling (retriable vs non-retriable)
"""

import asyncio
import pytest
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, call
from app.services.video_generation import (
    VideoClip,
    VideoManifest,
    VideoGenerationService,
    _validate_identifier,
)
from app.utils.cli_wrapper import CLIScriptError


class TestValidateIdentifier:
    """Test identifier validation."""

    def test_valid_identifiers(self):
        """Test valid channel_id and project_id formats."""
        _validate_identifier("poke1", "channel_id")
        _validate_identifier("nature-channel", "channel_id")
        _validate_identifier("abc_123-def", "project_id")
        _validate_identifier("X" * 100, "channel_id")  # Max length

    def test_invalid_characters(self):
        """Test identifier with invalid characters is rejected."""
        with pytest.raises(ValueError, match="contains invalid characters"):
            _validate_identifier("poke/1", "channel_id")

        with pytest.raises(ValueError, match="contains invalid characters"):
            _validate_identifier("../../../etc/passwd", "channel_id")

        with pytest.raises(ValueError, match="contains invalid characters"):
            _validate_identifier("test@channel", "channel_id")

    def test_invalid_length(self):
        """Test identifier length validation."""
        with pytest.raises(ValueError, match="length must be 1-100"):
            _validate_identifier("", "channel_id")

        with pytest.raises(ValueError, match="length must be 1-100"):
            _validate_identifier("X" * 101, "channel_id")


class TestVideoGenerationService:
    """Test suite for VideoGenerationService."""

    @pytest.fixture
    def service(self):
        """Create VideoGenerationService instance."""
        return VideoGenerationService("poke1", "vid_abc123")

    @pytest.fixture
    def mock_video_clip(self, tmp_path):
        """Create a mock VideoClip."""
        composite_path = tmp_path / "clip_01.png"
        composite_path.write_bytes(b"fake-png")
        output_path = tmp_path / "videos" / "clip_01.mp4"
        output_path.parent.mkdir(exist_ok=True)

        return VideoClip(
            clip_number=1,
            composite_path=composite_path,
            motion_prompt="Bulbasaur walks forward. Legs move steadily.",
            output_path=output_path,
            catbox_url=None,
        )

    def test_init_valid_identifiers(self):
        """Test service initialization with valid identifiers."""
        service = VideoGenerationService("poke1", "vid_123")
        assert service.channel_id == "poke1"
        assert service.project_id == "vid_123"

    def test_init_invalid_channel_id(self):
        """Test service rejects invalid channel_id."""
        with pytest.raises(ValueError, match="channel_id contains invalid characters"):
            VideoGenerationService("../etc/passwd", "vid_123")

    def test_init_invalid_project_id(self):
        """Test service rejects invalid project_id."""
        with pytest.raises(ValueError, match="project_id contains invalid characters"):
            VideoGenerationService("poke1", "vid@123")

    def test_create_video_manifest(self, service, tmp_path):
        """Test video manifest creation from topic and story."""
        topic = "Bulbasaur forest documentary"
        story_direction = "Show seasonal evolution through 18 clips"

        # Mock filesystem helpers to use tmp_path
        with (
            patch(
                "app.services.video_generation.get_composite_dir",
                return_value=tmp_path / "composites",
            ),
            patch("app.services.video_generation.get_video_dir", return_value=tmp_path / "videos"),
        ):
            manifest = service.create_video_manifest(topic, story_direction)

            # Verify manifest structure
            assert isinstance(manifest, VideoManifest)
            assert len(manifest.clips) == 18
            assert all(isinstance(clip, VideoClip) for clip in manifest.clips)

            # Verify clip numbering
            for i, clip in enumerate(manifest.clips, 1):
                assert clip.clip_number == i
                assert f"clip_{i:02d}" in str(clip.composite_path)
                assert f"clip_{i:02d}" in str(clip.output_path)

            # Verify motion prompts follow Priority Hierarchy
            for clip in manifest.clips:
                assert clip.motion_prompt  # Non-empty
                # Motion prompts should NOT start with camera movement
                assert not clip.motion_prompt.lower().startswith(
                    ("slow", "fast", "zoom", "pan", "dolly")
                )

    def test_check_video_exists(self, service, tmp_path):
        """Test video existence check with size validation."""
        # Valid video (>= 1MB)
        existing_video = tmp_path / "clip_01.mp4"
        existing_video.write_bytes(b"x" * 1_500_000)  # 1.5MB
        assert service.check_video_exists(existing_video) is True

        # Too small video (< 1MB)
        small_video = tmp_path / "clip_02.mp4"
        small_video.write_bytes(b"fake-video")  # Only 10 bytes
        assert service.check_video_exists(small_video) is False

        # Nonexistent video
        nonexistent_video = tmp_path / "clip_99.mp4"
        assert service.check_video_exists(nonexistent_video) is False

    def test_calculate_kling_cost(self, service):
        """Test Kling API cost calculation."""
        # Single clip
        cost_1 = service.calculate_kling_cost(1)
        assert isinstance(cost_1, Decimal)
        assert cost_1 == Decimal("0.42")

        # Full video (18 clips)
        cost_18 = service.calculate_kling_cost(18)
        assert cost_18 == Decimal("7.56")

        # Zero clips
        cost_0 = service.calculate_kling_cost(0)
        assert cost_0 == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_upload_to_catbox_success(self, service, tmp_path):
        """Test successful catbox.moe upload."""
        composite_path = tmp_path / "clip_01.png"
        composite_path.write_bytes(b"fake-png")
        expected_url = "https://files.catbox.moe/abc123.png"

        with patch("app.services.video_generation.CatboxClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.upload_image = AsyncMock(return_value=expected_url)
            mock_client.close = AsyncMock()

            url = await service.upload_to_catbox(composite_path)

            assert url == expected_url
            mock_client.upload_image.assert_called_once_with(composite_path)

    @pytest.mark.asyncio
    async def test_upload_to_catbox_file_not_found(self, service, tmp_path):
        """Test catbox upload fails for missing file."""
        nonexistent_path = tmp_path / "missing.png"

        with patch("app.services.video_generation.CatboxClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.upload_image = AsyncMock(side_effect=FileNotFoundError("File not found"))
            mock_client.close = AsyncMock()

            with pytest.raises(FileNotFoundError):
                await service.upload_to_catbox(nonexistent_path)

    @pytest.mark.asyncio
    async def test_generate_videos_single_clip(self, service, mock_video_clip, tmp_path):
        """Test generating single video clip."""
        manifest = VideoManifest(clips=[mock_video_clip])

        with (
            patch("app.services.video_generation.CatboxClient") as MockClient,
            patch(
                "app.services.video_generation.run_cli_script", new_callable=AsyncMock
            ) as mock_cli,
        ):
            # Mock catbox upload
            mock_client = MockClient.return_value
            mock_client.upload_image = AsyncMock(return_value="https://files.catbox.moe/abc123.png")
            mock_client.close = AsyncMock()

            # Mock CLI script success
            mock_cli.return_value = Mock(returncode=0, stdout="Success")

            # Generate videos
            result = await service.generate_videos(manifest, resume=False, max_concurrent=5)

            # Verify result
            assert result["generated"] == 1
            assert result["skipped"] == 0
            assert result["failed"] == 0
            assert result["total_cost_usd"] == Decimal("0.42")

            # Verify CLI script was called
            mock_cli.assert_called_once()
            call_args = mock_cli.call_args[0]
            assert call_args[0] == "generate_video.py"
            assert "--image" in call_args[1]
            assert "--prompt" in call_args[1]
            assert "--output" in call_args[1]

    @pytest.mark.asyncio
    async def test_generate_videos_with_resume(self, service, mock_video_clip, tmp_path):
        """Test resume skips existing videos with valid size."""
        # Create existing video (>= 1MB minimum size)
        mock_video_clip.output_path.write_bytes(b"x" * 1_500_000)  # 1.5MB

        manifest = VideoManifest(clips=[mock_video_clip])

        with (
            patch("app.services.video_generation.CatboxClient") as MockClient,
            patch(
                "app.services.video_generation.run_cli_script", new_callable=AsyncMock
            ) as mock_cli,
        ):
            mock_client = MockClient.return_value
            mock_client.close = AsyncMock()

            # Generate videos with resume=True
            result = await service.generate_videos(manifest, resume=True, max_concurrent=5)

            # Verify clip was skipped
            assert result["generated"] == 0
            assert result["skipped"] == 1
            assert result["failed"] == 0
            assert result["total_cost_usd"] == Decimal("0.00")

            # Verify CLI script was NOT called
            mock_cli.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_videos_rate_limiting(self, service, tmp_path):
        """Test rate limiting with max_concurrent."""
        # Create 5 video clips
        clips = []
        for i in range(1, 6):
            composite_path = tmp_path / f"clip_{i:02d}.png"
            composite_path.write_bytes(b"fake-png")
            output_path = tmp_path / "videos" / f"clip_{i:02d}.mp4"
            clips.append(
                VideoClip(
                    clip_number=i,
                    composite_path=composite_path,
                    motion_prompt=f"Motion for clip {i}",
                    output_path=output_path,
                    catbox_url=None,
                )
            )

        manifest = VideoManifest(clips=clips)

        # Track concurrent calls
        concurrent_calls = []
        max_observed = 0

        async def mock_cli_with_tracking(*args, **kwargs):
            concurrent_calls.append(1)
            nonlocal max_observed
            max_observed = max(max_observed, len(concurrent_calls))
            await asyncio.sleep(0.01)  # Simulate work
            concurrent_calls.pop()
            return Mock(returncode=0, stdout="Success")

        with (
            patch("app.services.video_generation.CatboxClient") as MockClient,
            patch(
                "app.services.video_generation.run_cli_script", new_callable=AsyncMock
            ) as mock_cli,
        ):
            mock_client = MockClient.return_value
            mock_client.upload_image = AsyncMock(return_value="https://files.catbox.moe/abc.png")
            mock_client.close = AsyncMock()
            mock_cli.side_effect = mock_cli_with_tracking

            # Generate with max_concurrent=2
            result = await service.generate_videos(manifest, resume=False, max_concurrent=2)

            # Verify rate limiting worked
            assert result["generated"] == 5
            assert max_observed <= 2  # Never exceeded max_concurrent

    @pytest.mark.asyncio
    async def test_generate_videos_cli_error(self, service, mock_video_clip, tmp_path):
        """Test handling of CLI script errors - continues with other clips."""
        manifest = VideoManifest(clips=[mock_video_clip])

        with (
            patch("app.services.video_generation.CatboxClient") as MockClient,
            patch(
                "app.services.video_generation.run_cli_script", new_callable=AsyncMock
            ) as mock_cli,
        ):
            mock_client = MockClient.return_value
            mock_client.upload_image = AsyncMock(return_value="https://files.catbox.moe/abc.png")
            mock_client.close = AsyncMock()

            # Mock CLI script failure
            mock_cli.side_effect = CLIScriptError(
                "generate_video.py", 1, "Kling API error: Invalid API key"
            )

            # Generate videos - should NOT raise, returns failed count instead
            result = await service.generate_videos(manifest, resume=False, max_concurrent=5)

            # Verify failure was tracked
            assert result["generated"] == 0
            assert result["failed"] == 1
            assert result["total_cost_usd"] == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_generate_videos_timeout(self, service, mock_video_clip, tmp_path):
        """Test handling of timeout errors - continues with other clips."""
        manifest = VideoManifest(clips=[mock_video_clip])

        with (
            patch("app.services.video_generation.CatboxClient") as MockClient,
            patch(
                "app.services.video_generation.run_cli_script", new_callable=AsyncMock
            ) as mock_cli,
        ):
            mock_client = MockClient.return_value
            mock_client.upload_image = AsyncMock(return_value="https://files.catbox.moe/abc.png")
            mock_client.close = AsyncMock()

            # Mock timeout
            mock_cli.side_effect = asyncio.TimeoutError()

            # Generate videos - should NOT raise, returns failed count instead
            result = await service.generate_videos(manifest, resume=False, max_concurrent=5)

            # Verify failure was tracked
            assert result["generated"] == 0
            assert result["failed"] == 1
            assert result["total_cost_usd"] == Decimal("0.00")
