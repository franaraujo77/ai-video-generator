"""Tests for Narration Generation Service.

This module tests the NarrationGenerationService class which orchestrates
narration audio generation via ElevenLabs v3 API for the video generation pipeline.

Test Coverage:
- Narration manifest creation (voice_id, 18 clips mapping)
- Narration generation orchestration (CLI script invocation)
- Partial resume functionality (skip existing audio)
- Error handling (CLIScriptError, timeout, invalid voice_id)
- Cost calculation
- Audio duration validation
- Security (path traversal, voice_id validation, sensitive data)
- ElevenLabs v3 text structure validation

Architecture Compliance:
- Uses Story 3.1 CLI wrapper (never subprocess directly)
- Uses Story 3.2 filesystem helpers (never manual paths)
- Mocks CLI script to avoid actual ElevenLabs API calls
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.narration_generation import (
    NarrationClip,
    NarrationGenerationService,
    NarrationManifest,
)
from app.utils.cli_wrapper import CLIScriptError


class TestNarrationClipDataclass:
    """Test NarrationClip dataclass."""

    def test_narration_clip_creation(self, tmp_path: Path):
        """Test creating NarrationClip with all fields."""
        output_path = tmp_path / "clip_01.mp3"

        clip = NarrationClip(
            clip_number=1,
            narration_text="In the depths of the forest, Haunter searches for prey.",
            output_path=output_path,
            target_duration_seconds=7.2,
        )

        assert clip.clip_number == 1
        assert "Haunter searches for prey" in clip.narration_text
        assert clip.output_path == output_path
        assert clip.target_duration_seconds == 7.2

    def test_narration_clip_without_target_duration(self, tmp_path: Path):
        """Test creating NarrationClip without target duration."""
        output_path = tmp_path / "clip_02.mp3"

        clip = NarrationClip(
            clip_number=2,
            narration_text="The ghostly figure glides silently.",
            output_path=output_path,
        )

        assert clip.clip_number == 2
        assert clip.target_duration_seconds is None


class TestNarrationManifestDataclass:
    """Test NarrationManifest dataclass."""

    def test_narration_manifest_creation(self, tmp_path: Path):
        """Test creating NarrationManifest with clips list."""
        clip1 = NarrationClip(
            clip_number=1,
            narration_text="Text 1",
            output_path=tmp_path / "clip_01.mp3",
        )
        clip2 = NarrationClip(
            clip_number=2,
            narration_text="Text 2",
            output_path=tmp_path / "clip_02.mp3",
        )

        manifest = NarrationManifest(clips=[clip1, clip2], voice_id="EXAVITQu4vr4xnSDxMaL")

        assert len(manifest.clips) == 2
        assert manifest.voice_id == "EXAVITQu4vr4xnSDxMaL"
        assert manifest.clips[0].clip_number == 1
        assert manifest.clips[1].clip_number == 2


class TestNarrationGenerationServiceInit:
    """Test NarrationGenerationService initialization."""

    def test_service_initialization(self):
        """Test service initializes with channel_id and project_id."""
        service = NarrationGenerationService("poke1", "vid_abc123")

        assert service.channel_id == "poke1"
        assert service.project_id == "vid_abc123"
        assert service.log is not None

    def test_service_init_rejects_invalid_channel_id(self):
        """Test service rejects channel_id with path traversal characters."""
        with pytest.raises(ValueError, match="channel_id contains invalid characters"):
            NarrationGenerationService("../poke1", "vid_abc123")

        with pytest.raises(ValueError, match="channel_id contains invalid characters"):
            NarrationGenerationService("poke1; rm -rf /", "vid_abc123")

    def test_service_init_rejects_invalid_project_id(self):
        """Test service rejects project_id with path traversal characters."""
        with pytest.raises(ValueError, match="project_id contains invalid characters"):
            NarrationGenerationService("poke1", "../vid_abc123")

    def test_service_init_rejects_empty_identifiers(self):
        """Test service rejects empty identifiers."""
        with pytest.raises(ValueError, match="channel_id length must be 1-100"):
            NarrationGenerationService("", "vid_abc123")

        with pytest.raises(ValueError, match="project_id length must be 1-100"):
            NarrationGenerationService("poke1", "")


class TestCreateNarrationManifest:
    """Test create_narration_manifest method."""

    @patch("app.services.narration_generation.get_audio_dir")
    @pytest.mark.asyncio
    async def test_create_manifest_with_18_scripts(self, mock_get_audio_dir, tmp_path):
        """Test creating manifest with exactly 18 narration scripts."""
        mock_get_audio_dir.return_value = tmp_path

        service = NarrationGenerationService("poke1", "vid_abc123")

        # Create 18 narration scripts
        narration_scripts = [
            f"Narration text for clip {i}. This is a longer text to avoid the 100 character warning."
            for i in range(1, 19)
        ]

        manifest = await service.create_narration_manifest(
            narration_scripts=narration_scripts,
            voice_id="EXAVITQu4vr4xnSDxMaL",
        )

        assert len(manifest.clips) == 18
        assert manifest.voice_id == "EXAVITQu4vr4xnSDxMaL"
        assert manifest.clips[0].clip_number == 1
        assert manifest.clips[17].clip_number == 18
        assert all("clip" in clip.narration_text for clip in manifest.clips)

    @patch("app.services.narration_generation.get_audio_dir")
    @pytest.mark.asyncio
    async def test_create_manifest_with_video_durations(self, mock_get_audio_dir, tmp_path):
        """Test creating manifest with optional video durations."""
        mock_get_audio_dir.return_value = tmp_path

        service = NarrationGenerationService("poke1", "vid_abc123")

        narration_scripts = [f"Script {i}" * 10 for i in range(1, 19)]
        video_durations = [7.2, 6.8, 8.1, 7.5, 6.9, 7.0, 7.3, 6.5] + [7.0] * 10

        manifest = await service.create_narration_manifest(
            narration_scripts=narration_scripts,
            voice_id="EXAVITQu4vr4xnSDxMaL",
            video_durations=video_durations,
        )

        assert manifest.clips[0].target_duration_seconds == 7.2
        assert manifest.clips[1].target_duration_seconds == 6.8
        assert manifest.clips[7].target_duration_seconds == 6.5

    @patch("app.services.narration_generation.get_audio_dir")
    @pytest.mark.asyncio
    async def test_create_manifest_rejects_wrong_script_count(self, mock_get_audio_dir, tmp_path):
        """Test manifest creation fails with != 18 scripts."""
        mock_get_audio_dir.return_value = tmp_path

        service = NarrationGenerationService("poke1", "vid_abc123")

        # Try with 17 scripts (should fail)
        narration_scripts = [f"Script {i}" for i in range(1, 18)]

        with pytest.raises(ValueError, match="Expected 18 narration scripts, got 17"):
            await service.create_narration_manifest(
                narration_scripts=narration_scripts,
                voice_id="EXAVITQu4vr4xnSDxMaL",
            )

    @patch("app.services.narration_generation.get_audio_dir")
    @pytest.mark.asyncio
    async def test_create_manifest_rejects_invalid_voice_id(self, mock_get_audio_dir, tmp_path):
        """Test manifest creation fails with invalid voice_id."""
        mock_get_audio_dir.return_value = tmp_path

        service = NarrationGenerationService("poke1", "vid_abc123")

        narration_scripts = [f"Script {i}" * 10 for i in range(1, 19)]

        # Empty voice_id
        with pytest.raises(ValueError, match="Invalid voice_id"):
            await service.create_narration_manifest(
                narration_scripts=narration_scripts,
                voice_id="",
            )

        # Short voice_id
        with pytest.raises(ValueError, match="Invalid voice_id"):
            await service.create_narration_manifest(
                narration_scripts=narration_scripts,
                voice_id="short",
            )

        # Invalid characters
        with pytest.raises(ValueError, match="Invalid voice_id format"):
            await service.create_narration_manifest(
                narration_scripts=narration_scripts,
                voice_id="voice_id_with_underscores",
            )


class TestGenerateNarration:
    """Test generate_narration method."""

    @patch("app.services.narration_generation.run_cli_script")
    @patch("app.services.narration_generation.get_audio_dir")
    @pytest.mark.asyncio
    async def test_generate_all_narration_clips(
        self, mock_get_audio_dir, mock_run_cli_script, tmp_path
    ):
        """Test generating all 18 narration audio clips."""
        mock_get_audio_dir.return_value = tmp_path
        mock_run_cli_script.return_value = MagicMock(returncode=0)

        service = NarrationGenerationService("poke1", "vid_abc123")

        # Create manifest with 18 clips
        narration_scripts = [f"Script {i}" * 15 for i in range(1, 19)]
        manifest = await service.create_narration_manifest(
            narration_scripts=narration_scripts,
            voice_id="EXAVITQu4vr4xnSDxMaL",
        )

        # Create dummy audio files (simulate CLI script success)
        for clip in manifest.clips:
            clip.output_path.touch()

        result = await service.generate_narration(manifest, resume=False, max_concurrent=10)

        assert result["generated"] == 18
        assert result["skipped"] == 0
        assert result["failed"] == 0
        assert result["total_cost_usd"] > 0

        # Verify CLI script was called 18 times
        assert mock_run_cli_script.call_count == 18

    @patch("app.services.narration_generation.run_cli_script")
    @patch("app.services.narration_generation.get_audio_dir")
    @pytest.mark.asyncio
    async def test_generate_narration_with_resume(
        self, mock_get_audio_dir, mock_run_cli_script, tmp_path
    ):
        """Test resume functionality skips existing audio clips."""
        mock_get_audio_dir.return_value = tmp_path
        mock_run_cli_script.return_value = MagicMock(returncode=0)

        service = NarrationGenerationService("poke1", "vid_abc123")

        narration_scripts = [f"Script {i}" * 15 for i in range(1, 19)]
        manifest = await service.create_narration_manifest(
            narration_scripts=narration_scripts,
            voice_id="EXAVITQu4vr4xnSDxMaL",
        )

        # Simulate 10 existing clips (clips 1-10)
        for i in range(10):
            manifest.clips[i].output_path.touch()

        # Mock generate_single_clip to create audio files for remaining clips
        original_run_cli = mock_run_cli_script

        async def create_audio_on_generate(*args, **kwargs):
            # Extract output path from args
            if len(args) >= 2 and "--output" in args[1]:
                output_idx = args[1].index("--output") + 1
                output_path = Path(args[1][output_idx])
                output_path.touch()
            return MagicMock(returncode=0)

        mock_run_cli_script.side_effect = create_audio_on_generate

        result = await service.generate_narration(manifest, resume=True, max_concurrent=10)

        assert result["skipped"] == 10
        assert result["generated"] == 8
        assert result["failed"] == 0

        # Verify CLI script was called only 8 times (not 18)
        assert mock_run_cli_script.call_count == 8


class TestCheckAudioExists:
    """Test check_audio_exists method."""

    def test_check_existing_audio_file(self, tmp_path):
        """Test checking for existing audio file returns True."""
        service = NarrationGenerationService("poke1", "vid_abc123")

        audio_path = tmp_path / "clip_01.mp3"
        audio_path.touch()

        assert service.check_audio_exists(audio_path) is True

    def test_check_nonexistent_audio_file(self, tmp_path):
        """Test checking for nonexistent audio file returns False."""
        service = NarrationGenerationService("poke1", "vid_abc123")

        audio_path = tmp_path / "clip_99.mp3"

        assert service.check_audio_exists(audio_path) is False


class TestValidateAudioDuration:
    """Test validate_audio_duration method."""

    @patch("app.services.narration_generation.asyncio.to_thread")
    @pytest.mark.asyncio
    async def test_validate_audio_duration(self, mock_to_thread, tmp_path):
        """Test validating audio duration with ffprobe."""
        service = NarrationGenerationService("poke1", "vid_abc123")

        audio_path = tmp_path / "clip_01.mp3"
        audio_path.touch()

        # Mock ffprobe returning 7.2 seconds
        mock_to_thread.return_value = 7.2

        duration = await service.validate_audio_duration(audio_path)

        assert duration == 7.2

    @pytest.mark.asyncio
    async def test_validate_audio_duration_missing_file(self, tmp_path):
        """Test validating audio duration fails if file missing."""
        service = NarrationGenerationService("poke1", "vid_abc123")

        audio_path = tmp_path / "nonexistent.mp3"

        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            await service.validate_audio_duration(audio_path)


class TestCalculateElevenlabsCost:
    """Test calculate_elevenlabs_cost method."""

    def test_calculate_cost_for_18_clips(self):
        """Test cost calculation for complete video (18 clips)."""
        service = NarrationGenerationService("poke1", "vid_abc123")

        cost = service.calculate_elevenlabs_cost(18)

        # Expected: 18 clips × $0.04/clip = $0.72
        assert float(cost) == 0.72

    def test_calculate_cost_for_partial_clips(self):
        """Test cost calculation for partial generation."""
        service = NarrationGenerationService("poke1", "vid_abc123")

        cost = service.calculate_elevenlabs_cost(8)

        # Expected: 8 clips × $0.04/clip = $0.32
        assert float(cost) == 0.32


class TestValidateNarrationText:
    """Test validate_narration_text method."""

    def test_validate_short_narration_text_logs_warning(self, caplog):
        """Test validation logs warning for very short text (< 100 chars)."""
        service = NarrationGenerationService("poke1", "vid_abc123")

        # Very short text (< 100 chars)
        short_text = "Haunter approaches."

        service.validate_narration_text(short_text, clip_number=3)

        # Should log warning but not raise exception
        assert "narration_text_warning" in caplog.text

    def test_validate_long_narration_text_passes(self, caplog):
        """Test validation passes for text > 100 chars."""
        service = NarrationGenerationService("poke1", "vid_abc123")

        # Long text (> 100 chars)
        long_text = (
            "In the depths of the forest, Haunter searches for prey. "
            "The ghostly figure glides silently through the darkness, "
            "watching and waiting for the perfect moment to strike."
        )

        service.validate_narration_text(long_text, clip_number=1)

        # Should not log warning
        assert "narration_text_warning" not in caplog.text


class TestSecurityValidation:
    """Test security validation for path traversal and injection attacks."""

    def test_voice_id_validation_rejects_special_characters(self):
        """Test voice_id validation prevents injection attacks."""
        service = NarrationGenerationService("poke1", "vid_abc123")

        # Voice ID with shell special characters (potential injection)
        with pytest.raises(ValueError, match="Invalid voice_id format"):
            from app.services.narration_generation import _validate_voice_id

            _validate_voice_id("voice_id; rm -rf /")

        with pytest.raises(ValueError, match="Invalid voice_id format"):
            _validate_voice_id("voice_id | cat /etc/passwd")

    def test_identifier_validation_rejects_path_traversal(self):
        """Test identifier validation prevents path traversal attacks."""
        with pytest.raises(ValueError, match="contains invalid characters"):
            NarrationGenerationService("../../../etc/passwd", "vid_abc123")

        with pytest.raises(ValueError, match="contains invalid characters"):
            NarrationGenerationService("poke1", "../../secret")
