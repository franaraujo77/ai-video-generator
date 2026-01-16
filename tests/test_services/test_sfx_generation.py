"""Tests for Sound Effects Generation Service.

This module tests the SFXGenerationService class which orchestrates
SFX audio generation via ElevenLabs v3 API for the video generation pipeline.

Test Coverage:
- SFX manifest creation (18 clips mapping)
- SFX generation orchestration (CLI script invocation)
- Partial resume functionality (skip existing SFX)
- Error handling (CLIScriptError, timeout, invalid parameters)
- Cost calculation
- SFX duration validation
- Security (path traversal, sensitive data)
- ElevenLabs v3 description structure validation

Architecture Compliance:
- Uses Story 3.1 CLI wrapper (never subprocess directly)
- Uses Story 3.2 filesystem helpers (never manual paths)
- Mocks CLI script to avoid actual ElevenLabs API calls
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.sfx_generation import (
    SFXClip,
    SFXGenerationService,
    SFXManifest,
)
from app.utils.cli_wrapper import CLIScriptError


class TestSFXClipDataclass:
    """Test SFXClip dataclass."""

    def test_sfx_clip_creation(self, tmp_path: Path):
        """Test creating SFXClip with all fields."""
        output_path = tmp_path / "sfx_01.wav"

        clip = SFXClip(
            clip_number=1,
            sfx_description="Gentle forest ambience with rustling leaves and distant bird calls",
            output_path=output_path,
            target_duration_seconds=7.2,
        )

        assert clip.clip_number == 1
        assert "forest ambience" in clip.sfx_description
        assert clip.output_path == output_path
        assert clip.target_duration_seconds == 7.2

    def test_sfx_clip_without_target_duration(self, tmp_path: Path):
        """Test creating SFXClip without target duration."""
        output_path = tmp_path / "sfx_02.wav"

        clip = SFXClip(
            clip_number=2,
            sfx_description="Wind howling through dark caves",
            output_path=output_path,
        )

        assert clip.clip_number == 2
        assert clip.target_duration_seconds is None


class TestSFXManifestDataclass:
    """Test SFXManifest dataclass."""

    def test_sfx_manifest_creation(self, tmp_path: Path):
        """Test creating SFXManifest with clips list."""
        clip1 = SFXClip(
            clip_number=1,
            sfx_description="Forest ambience",
            output_path=tmp_path / "sfx_01.wav",
        )
        clip2 = SFXClip(
            clip_number=2,
            sfx_description="Cave wind",
            output_path=tmp_path / "sfx_02.wav",
        )

        manifest = SFXManifest(clips=[clip1, clip2])

        assert len(manifest.clips) == 2
        assert manifest.clips[0].clip_number == 1
        assert manifest.clips[1].clip_number == 2


class TestSFXGenerationServiceInit:
    """Test SFXGenerationService initialization."""

    def test_service_initialization(self):
        """Test service initializes with channel_id and project_id."""
        service = SFXGenerationService("poke1", "vid_abc123")

        assert service.channel_id == "poke1"
        assert service.project_id == "vid_abc123"
        assert service.log is not None

    def test_service_init_rejects_invalid_channel_id(self):
        """Test service rejects channel_id with path traversal characters."""
        with pytest.raises(ValueError, match="channel_id contains invalid characters"):
            SFXGenerationService("../poke1", "vid_abc123")

        with pytest.raises(ValueError, match="channel_id contains invalid characters"):
            SFXGenerationService("poke1; rm -rf /", "vid_abc123")

    def test_service_init_rejects_invalid_project_id(self):
        """Test service rejects project_id with path traversal characters."""
        with pytest.raises(ValueError, match="project_id contains invalid characters"):
            SFXGenerationService("poke1", "../vid_abc123")

    def test_service_init_rejects_empty_identifiers(self):
        """Test service rejects empty identifiers."""
        with pytest.raises(ValueError, match="channel_id length must be 1-100"):
            SFXGenerationService("", "vid_abc123")

        with pytest.raises(ValueError, match="project_id length must be 1-100"):
            SFXGenerationService("poke1", "")


class TestCreateSFXManifest:
    """Test create_sfx_manifest method."""

    @patch("app.services.sfx_generation.get_sfx_dir")
    @pytest.mark.asyncio
    async def test_create_manifest_with_18_descriptions(self, mock_get_sfx_dir, tmp_path):
        """Test creating manifest with exactly 18 SFX descriptions."""
        mock_get_sfx_dir.return_value = tmp_path

        service = SFXGenerationService("poke1", "vid_abc123")

        # Create 18 SFX descriptions
        sfx_descriptions = [
            f"Atmospheric environmental sound effect for clip {i} with detailed description"
            for i in range(1, 19)
        ]

        manifest = await service.create_sfx_manifest(sfx_descriptions=sfx_descriptions)

        assert len(manifest.clips) == 18
        assert manifest.clips[0].clip_number == 1
        assert manifest.clips[17].clip_number == 18
        assert all("clip" in clip.sfx_description for clip in manifest.clips)

    @patch("app.services.sfx_generation.get_sfx_dir")
    @pytest.mark.asyncio
    async def test_create_manifest_with_video_durations(self, mock_get_sfx_dir, tmp_path):
        """Test creating manifest with optional video durations."""
        mock_get_sfx_dir.return_value = tmp_path

        service = SFXGenerationService("poke1", "vid_abc123")

        sfx_descriptions = [f"SFX description {i} with sufficient length" for i in range(1, 19)]
        video_durations = [7.2, 6.8, 8.1, 7.5, 6.9, 7.0, 7.3, 6.5] + [7.0] * 10

        manifest = await service.create_sfx_manifest(
            sfx_descriptions=sfx_descriptions,
            video_durations=video_durations,
        )

        assert manifest.clips[0].target_duration_seconds == 7.2
        assert manifest.clips[1].target_duration_seconds == 6.8
        assert manifest.clips[7].target_duration_seconds == 6.5

    @patch("app.services.sfx_generation.get_sfx_dir")
    @pytest.mark.asyncio
    async def test_create_manifest_rejects_wrong_description_count(
        self, mock_get_sfx_dir, tmp_path
    ):
        """Test manifest creation fails with != 18 descriptions."""
        mock_get_sfx_dir.return_value = tmp_path

        service = SFXGenerationService("poke1", "vid_abc123")

        # Try with 17 descriptions (should fail)
        sfx_descriptions = [f"Description {i}" for i in range(1, 18)]

        with pytest.raises(ValueError, match="Expected 18 SFX descriptions, got 17"):
            await service.create_sfx_manifest(sfx_descriptions=sfx_descriptions)


class TestGenerateSFX:
    """Test generate_sfx method."""

    @patch("app.services.sfx_generation.run_cli_script")
    @patch("app.services.sfx_generation.get_sfx_dir")
    @pytest.mark.asyncio
    async def test_generate_all_sfx_clips(self, mock_get_sfx_dir, mock_run_cli_script, tmp_path):
        """Test generating all 18 SFX audio clips."""
        mock_get_sfx_dir.return_value = tmp_path
        mock_run_cli_script.return_value = MagicMock(returncode=0)

        service = SFXGenerationService("poke1", "vid_abc123")

        # Create manifest with 18 clips
        sfx_descriptions = [
            f"SFX description {i} with enough length for validation" for i in range(1, 19)
        ]
        manifest = await service.create_sfx_manifest(sfx_descriptions=sfx_descriptions)

        # Create dummy audio files (simulate CLI script success)
        for clip in manifest.clips:
            clip.output_path.touch()

        result = await service.generate_sfx(manifest, resume=False, max_concurrent=10)

        assert result["generated"] == 18
        assert result["skipped"] == 0
        assert result["failed"] == 0
        assert result["total_cost_usd"] > 0

        # Verify CLI script was called 18 times
        assert mock_run_cli_script.call_count == 18

    @patch("app.services.sfx_generation.run_cli_script")
    @patch("app.services.sfx_generation.get_sfx_dir")
    @pytest.mark.asyncio
    async def test_generate_sfx_with_resume(self, mock_get_sfx_dir, mock_run_cli_script, tmp_path):
        """Test resume functionality skips existing SFX clips."""
        mock_get_sfx_dir.return_value = tmp_path
        mock_run_cli_script.return_value = MagicMock(returncode=0)

        service = SFXGenerationService("poke1", "vid_abc123")

        sfx_descriptions = [f"SFX description {i} with enough length" for i in range(1, 19)]
        manifest = await service.create_sfx_manifest(sfx_descriptions=sfx_descriptions)

        # Simulate 10 existing clips (clips 1-10)
        for i in range(10):
            manifest.clips[i].output_path.touch()

        # Mock generate_single_clip to create audio files for remaining clips
        async def create_audio_on_generate(*args, **kwargs):
            # Extract output path from args
            if len(args) >= 2 and "--output" in args[1]:
                output_idx = args[1].index("--output") + 1
                output_path = Path(args[1][output_idx])
                output_path.touch()
            return MagicMock(returncode=0)

        mock_run_cli_script.side_effect = create_audio_on_generate

        result = await service.generate_sfx(manifest, resume=True, max_concurrent=10)

        # 10 existing (skipped), 8 new (generated)
        assert result["generated"] == 8
        assert result["skipped"] == 10
        assert result["failed"] == 0

        # Verify CLI script was called only 8 times (not 18)
        assert mock_run_cli_script.call_count == 8

    @patch("app.services.sfx_generation.run_cli_script")
    @patch("app.services.sfx_generation.get_sfx_dir")
    @pytest.mark.asyncio
    async def test_generate_sfx_handles_cli_error(
        self, mock_get_sfx_dir, mock_run_cli_script, tmp_path
    ):
        """Test SFX generation handles CLI script errors."""
        mock_get_sfx_dir.return_value = tmp_path

        # Mock CLI script to raise non-retriable error (401 Unauthorized)
        mock_run_cli_script.side_effect = CLIScriptError(
            script="generate_sound_effects.py",
            exit_code=1,
            stderr="❌ HTTP 401: Invalid API key",
        )

        service = SFXGenerationService("poke1", "vid_abc123")

        sfx_descriptions = [f"SFX description {i} with enough length" for i in range(1, 19)]
        manifest = await service.create_sfx_manifest(sfx_descriptions=sfx_descriptions)

        # Expect CLIScriptError OR ValueError (file not created) to propagate
        # Both are valid outcomes depending on retry logic
        with pytest.raises((CLIScriptError, ValueError)):
            await service.generate_sfx(manifest, resume=False, max_concurrent=10)


class TestCheckSFXExists:
    """Test check_sfx_exists method."""

    def test_check_sfx_exists_returns_true_for_existing_file(self, tmp_path):
        """Test check_sfx_exists returns True for existing file."""
        service = SFXGenerationService("poke1", "vid_abc123")

        sfx_path = tmp_path / "sfx_01.wav"
        sfx_path.touch()

        assert service.check_sfx_exists(sfx_path) is True

    def test_check_sfx_exists_returns_false_for_missing_file(self, tmp_path):
        """Test check_sfx_exists returns False for missing file."""
        service = SFXGenerationService("poke1", "vid_abc123")

        sfx_path = tmp_path / "nonexistent.wav"

        assert service.check_sfx_exists(sfx_path) is False


class TestValidateSFXDuration:
    """Test validate_sfx_duration method."""

    @pytest.mark.asyncio
    async def test_validate_sfx_duration_with_valid_file(self, tmp_path):
        """Test validate_sfx_duration with valid audio file."""
        service = SFXGenerationService("poke1", "vid_abc123")

        sfx_path = tmp_path / "sfx_01.wav"
        sfx_path.touch()

        # Mock ffprobe to return duration
        with patch("app.services.sfx_generation.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="7.234567\n", stderr="")

            duration = await service.validate_sfx_duration(sfx_path)

            assert duration == pytest.approx(7.234567, rel=1e-5)
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_sfx_duration_raises_for_missing_file(self, tmp_path):
        """Test validate_sfx_duration raises FileNotFoundError for missing file."""
        service = SFXGenerationService("poke1", "vid_abc123")

        sfx_path = tmp_path / "nonexistent.wav"

        with pytest.raises(FileNotFoundError, match="SFX file not found"):
            await service.validate_sfx_duration(sfx_path)


class TestCalculateElevenLabsCost:
    """Test calculate_elevenlabs_cost method."""

    def test_calculate_cost_for_18_clips(self):
        """Test cost calculation for complete video (18 clips)."""
        service = SFXGenerationService("poke1", "vid_abc123")

        cost = service.calculate_elevenlabs_cost(18)

        # Expected: 18 clips x $0.04 = $0.72
        assert float(cost) == pytest.approx(0.72, rel=1e-5)

    def test_calculate_cost_for_partial_clips(self):
        """Test cost calculation for partial resume (8 clips)."""
        service = SFXGenerationService("poke1", "vid_abc123")

        cost = service.calculate_elevenlabs_cost(8)

        # Expected: 8 clips x $0.04 = $0.32
        assert float(cost) == pytest.approx(0.32, rel=1e-5)


class TestValidateSFXDescription:
    """Test validate_sfx_description method."""

    def test_validates_short_sfx_description(self):
        """Test validation warns for very short SFX descriptions."""
        service = SFXGenerationService("poke1", "vid_abc123")

        # Should log warning for short description (< 20 chars)
        with patch.object(service.log, "warning") as mock_warning:
            service.validate_sfx_description("Short", 1)

            mock_warning.assert_called_once()
            # Verify warning message contains expected text
            call_kwargs = mock_warning.call_args[1]
            assert "Very short SFX description" in call_kwargs["message"]
            assert "Prefer SFX descriptions > 50 characters" in call_kwargs["recommendation"]
            assert call_kwargs["clip_number"] == 1
            assert call_kwargs["description_length"] == 5

    def test_validates_adequate_sfx_description(self):
        """Test validation passes for adequate SFX descriptions."""
        service = SFXGenerationService("poke1", "vid_abc123")

        # Should NOT log warning for adequate description
        with patch.object(service.log, "warning") as mock_warning:
            service.validate_sfx_description(
                "Gentle forest ambience with rustling leaves and distant bird calls", 1
            )

            mock_warning.assert_not_called()


class TestMultiChannelIsolation:
    """Test multi-channel isolation (AC8)."""

    @patch("app.services.sfx_generation.run_cli_script")
    @patch("app.services.sfx_generation.get_sfx_dir")
    @pytest.mark.asyncio
    async def test_multi_channel_isolation(self, mock_get_sfx_dir, mock_run_cli_script, tmp_path):
        """Test two channels generate SFX simultaneously without interference."""
        # Setup separate directories for each channel
        channel1_dir = tmp_path / "poke1" / "projects" / "vid_123" / "sfx"
        channel2_dir = tmp_path / "poke2" / "projects" / "vid_456" / "sfx"
        channel1_dir.mkdir(parents=True, exist_ok=True)
        channel2_dir.mkdir(parents=True, exist_ok=True)

        # Mock get_sfx_dir to return channel-specific directories
        def get_dir_by_channel(channel_id, project_id):
            if channel_id == "poke1":
                return channel1_dir
            return channel2_dir

        mock_get_sfx_dir.side_effect = get_dir_by_channel
        mock_run_cli_script.return_value = MagicMock(returncode=0)

        # Create services for both channels
        service1 = SFXGenerationService("poke1", "vid_123")
        service2 = SFXGenerationService("poke2", "vid_456")

        # Create manifests
        sfx_desc = [f"SFX {i} with enough length" for i in range(1, 19)]
        manifest1 = await service1.create_sfx_manifest(sfx_desc)
        manifest2 = await service2.create_sfx_manifest(sfx_desc)

        # Create dummy files for both channels
        for clip in manifest1.clips:
            clip.output_path.touch()
        for clip in manifest2.clips:
            clip.output_path.touch()

        # Generate SFX for both channels
        result1 = await service1.generate_sfx(manifest1, resume=False, max_concurrent=10)
        result2 = await service2.generate_sfx(manifest2, resume=False, max_concurrent=10)

        # Verify both channels generated successfully
        assert result1["generated"] == 18
        assert result2["generated"] == 18

        # Verify files are in separate directories (no cross-channel interference)
        assert all(clip.output_path.parent == channel1_dir for clip in manifest1.clips)
        assert all(clip.output_path.parent == channel2_dir for clip in manifest2.clips)

        # Verify no file conflicts
        channel1_files = {clip.output_path.name for clip in manifest1.clips}
        channel2_files = {clip.output_path.name for clip in manifest2.clips}
        # File names are the same, but in different directories
        assert channel1_files == channel2_files


class TestPartialResumeLogging:
    """Test partial resume log messages (AC4)."""

    @patch("app.services.sfx_generation.run_cli_script")
    @patch("app.services.sfx_generation.get_sfx_dir")
    @pytest.mark.asyncio
    async def test_resume_log_message(self, mock_get_sfx_dir, mock_run_cli_script, tmp_path):
        """Test resume logs 'Skipped X existing clips, generated Y new clips'."""
        mock_get_sfx_dir.return_value = tmp_path
        mock_run_cli_script.return_value = MagicMock(returncode=0)

        service = SFXGenerationService("poke1", "vid_abc123")

        sfx_descriptions = [f"SFX {i} with enough length" for i in range(1, 19)]
        manifest = await service.create_sfx_manifest(sfx_descriptions)

        # Simulate 10 existing clips
        for i in range(10):
            manifest.clips[i].output_path.touch()

        # Mock CLI script to create remaining files
        async def create_file_on_call(*args, **kwargs):
            if len(args) >= 2 and "--output" in args[1]:
                output_idx = args[1].index("--output") + 1
                output_path = Path(args[1][output_idx])
                output_path.touch()
            return MagicMock(returncode=0)

        mock_run_cli_script.side_effect = create_file_on_call

        # Capture log output
        with patch.object(service.log, "info") as mock_log:
            result = await service.generate_sfx(manifest, resume=True, max_concurrent=10)

            # Verify result
            assert result["generated"] == 8
            assert result["skipped"] == 10

            # Verify skipped log messages (one per skipped clip)
            skipped_logs = [
                call
                for call in mock_log.call_args_list
                if call[1].get("clip_number") is not None and call[0][0] == "sfx_clip_skipped"
            ]
            assert len(skipped_logs) == 10


class TestRateLimitRetry:
    """Test rate limit retry with exponential backoff (AC5)."""

    @patch("app.services.sfx_generation.run_cli_script")
    @patch("app.services.sfx_generation.get_sfx_dir")
    @pytest.mark.asyncio
    async def test_rate_limit_429_retry(self, mock_get_sfx_dir, mock_run_cli_script, tmp_path):
        """Test HTTP 429 triggers exponential backoff retry (2s, 4s, 8s)."""
        mock_get_sfx_dir.return_value = tmp_path

        service = SFXGenerationService("poke1", "vid_abc123")

        # Create minimal manifest (1 clip for faster test)
        sfx_descriptions = [f"SFX {i} with enough length" for i in range(1, 19)]
        manifest = await service.create_sfx_manifest(sfx_descriptions)

        # Mock CLI to fail with 429 twice, then succeed
        call_count = 0

        async def mock_cli_with_429(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # First 2 calls: Rate limit error
                raise CLIScriptError(
                    script="generate_sound_effects.py",
                    exit_code=1,
                    stderr="HTTP 429: Too Many Requests - Rate limit exceeded",
                )
            # Third call: Success
            if len(args) >= 2 and "--output" in args[1]:
                output_idx = args[1].index("--output") + 1
                output_path = Path(args[1][output_idx])
                output_path.touch()
            return MagicMock(returncode=0)

        mock_run_cli_script.side_effect = mock_cli_with_429

        # Generate (should retry and succeed)
        result = await service.generate_sfx(manifest, resume=False, max_concurrent=10)

        # Verify retries happened
        # First clip: 3 attempts (fail, fail, success)
        # Remaining 17 clips: 1 attempt each (success)
        # Total: 3 + 17 = 20 calls
        assert call_count == 20
        assert result["generated"] == 18  # All clips should succeed after retries
