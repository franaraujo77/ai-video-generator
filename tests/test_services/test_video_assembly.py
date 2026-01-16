"""Tests for Video Assembly Service.

This module tests the VideoAssemblyService class which orchestrates
final video assembly via FFmpeg for the video generation pipeline.

Test Coverage:
- Assembly manifest creation (18 clips mapping, audio probing)
- File validation (54 files: 18 video + 18 audio + 18 SFX)
- Audio duration probing with ffprobe
- Video assembly orchestration (CLI script invocation)
- Output video validation (codec, resolution, duration)
- Error handling (FileNotFoundError, CLIScriptError, ValueError)
- Security (path traversal, identifier validation)

Architecture Compliance:
- Uses Story 3.1 CLI wrapper (never subprocess directly)
- Uses Story 3.2 filesystem helpers (never manual paths)
- Mocks CLI script to avoid actual FFmpeg execution
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.video_assembly import (
    AssemblyManifest,
    ClipAssemblySpec,
    VideoAssemblyService,
)
from app.utils.cli_wrapper import CLIScriptError


class TestClipAssemblySpecDataclass:
    """Test ClipAssemblySpec dataclass."""

    def test_clip_assembly_spec_creation(self, tmp_path: Path):
        """Test creating ClipAssemblySpec with all fields."""
        video_path = tmp_path / "videos" / "clip_01.mp4"
        narration_path = tmp_path / "audio" / "clip_01.mp3"
        sfx_path = tmp_path / "sfx" / "sfx_01.wav"

        clip = ClipAssemblySpec(
            clip_number=1,
            video_path=video_path,
            narration_path=narration_path,
            sfx_path=sfx_path,
            narration_duration=7.2,
        )

        assert clip.clip_number == 1
        assert clip.video_path == video_path
        assert clip.narration_path == narration_path
        assert clip.sfx_path == sfx_path
        assert clip.narration_duration == 7.2


class TestAssemblyManifestDataclass:
    """Test AssemblyManifest dataclass."""

    def test_assembly_manifest_creation(self, tmp_path: Path):
        """Test creating AssemblyManifest with clips list."""
        clip1 = ClipAssemblySpec(
            clip_number=1,
            video_path=tmp_path / "clip_01.mp4",
            narration_path=tmp_path / "clip_01.mp3",
            sfx_path=tmp_path / "sfx_01.wav",
            narration_duration=7.2,
        )
        clip2 = ClipAssemblySpec(
            clip_number=2,
            video_path=tmp_path / "clip_02.mp4",
            narration_path=tmp_path / "clip_02.mp3",
            sfx_path=tmp_path / "sfx_02.wav",
            narration_duration=6.8,
        )

        output_path = tmp_path / "final.mp4"
        manifest = AssemblyManifest(clips=[clip1, clip2], output_path=output_path)

        assert len(manifest.clips) == 2
        assert manifest.output_path == output_path
        assert manifest.clips[0].clip_number == 1
        assert manifest.clips[1].clip_number == 2

    def test_to_json_dict(self, tmp_path: Path):
        """Test converting AssemblyManifest to JSON dict."""
        clip = ClipAssemblySpec(
            clip_number=1,
            video_path=tmp_path / "clip_01.mp4",
            narration_path=tmp_path / "clip_01.mp3",
            sfx_path=tmp_path / "sfx_01.wav",
            narration_duration=7.2,
        )

        manifest = AssemblyManifest(
            clips=[clip], output_path=tmp_path / "final.mp4"
        )

        json_dict = manifest.to_json_dict()

        assert "clips" in json_dict
        assert len(json_dict["clips"]) == 1
        assert json_dict["clips"][0]["clip_number"] == 1
        assert json_dict["clips"][0]["narration_duration"] == 7.2
        assert "video_path" in json_dict["clips"][0]
        assert isinstance(json_dict["clips"][0]["video_path"], str)


class TestVideoAssemblyServiceInit:
    """Test VideoAssemblyService initialization."""

    def test_service_initialization(self):
        """Test service initializes with channel_id and project_id."""
        service = VideoAssemblyService("poke1", "vid_abc123")

        assert service.channel_id == "poke1"
        assert service.project_id == "vid_abc123"
        assert service.log is not None

    def test_service_init_rejects_invalid_channel_id(self):
        """Test service rejects channel_id with path traversal characters."""
        with pytest.raises(ValueError, match="channel_id contains invalid characters"):
            VideoAssemblyService("../poke1", "vid_abc123")

        with pytest.raises(ValueError, match="channel_id contains invalid characters"):
            VideoAssemblyService("poke1; rm -rf /", "vid_abc123")

    def test_service_init_rejects_invalid_project_id(self):
        """Test service rejects project_id with path traversal characters."""
        with pytest.raises(ValueError, match="project_id contains invalid characters"):
            VideoAssemblyService("poke1", "../vid_abc123")

    def test_service_init_rejects_empty_identifiers(self):
        """Test service rejects empty identifiers."""
        with pytest.raises(ValueError, match="channel_id length must be 1-100"):
            VideoAssemblyService("", "vid_abc123")

        with pytest.raises(ValueError, match="project_id length must be 1-100"):
            VideoAssemblyService("poke1", "")


class TestProbeAudioDuration:
    """Test probe_audio_duration method."""

    @patch("app.services.video_assembly.asyncio.to_thread")
    @pytest.mark.asyncio
    async def test_probe_audio_duration_success(self, mock_to_thread, tmp_path):
        """Test probing audio duration with ffprobe."""
        # Create test audio file
        audio_path = tmp_path / "clip_01.mp3"
        audio_path.write_text("fake audio content")

        # Mock subprocess result
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "7.234567\n"
        mock_to_thread.return_value = mock_result

        service = VideoAssemblyService("poke1", "vid_abc123")
        duration = await service.probe_audio_duration(audio_path)

        assert duration == 7.234567
        mock_to_thread.assert_called_once()

    @patch("app.services.video_assembly.asyncio.to_thread")
    @pytest.mark.asyncio
    async def test_probe_audio_duration_ffprobe_failure(self, mock_to_thread, tmp_path):
        """Test probing audio duration when ffprobe fails."""
        audio_path = tmp_path / "clip_01.mp3"
        audio_path.write_text("fake audio content")

        # Mock subprocess failure
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Invalid audio file"
        mock_to_thread.return_value = mock_result

        service = VideoAssemblyService("poke1", "vid_abc123")

        with pytest.raises(subprocess.CalledProcessError):
            await service.probe_audio_duration(audio_path)

    @pytest.mark.asyncio
    async def test_probe_audio_duration_file_not_found(self, tmp_path):
        """Test probing audio duration when file doesn't exist."""
        audio_path = tmp_path / "nonexistent.mp3"

        service = VideoAssemblyService("poke1", "vid_abc123")

        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            await service.probe_audio_duration(audio_path)

    @patch("app.services.video_assembly.asyncio.to_thread")
    @pytest.mark.asyncio
    async def test_probe_audio_duration_invalid_output(self, mock_to_thread, tmp_path):
        """Test probing audio duration when ffprobe output is invalid."""
        audio_path = tmp_path / "clip_01.mp3"
        audio_path.write_text("fake audio content")

        # Mock subprocess with invalid output
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not a number\n"
        mock_to_thread.return_value = mock_result

        service = VideoAssemblyService("poke1", "vid_abc123")

        with pytest.raises(ValueError, match="Invalid ffprobe output"):
            await service.probe_audio_duration(audio_path)


class TestCreateAssemblyManifest:
    """Test create_assembly_manifest method."""

    @patch("app.services.video_assembly.get_video_dir")
    @patch("app.services.video_assembly.get_audio_dir")
    @patch("app.services.video_assembly.get_sfx_dir")
    @patch("app.services.video_assembly.get_project_dir")
    @patch("app.services.video_assembly.VideoAssemblyService.probe_audio_duration")
    @pytest.mark.asyncio
    async def test_create_manifest_with_18_clips(
        self,
        mock_probe_duration,
        mock_get_project_dir,
        mock_get_sfx_dir,
        mock_get_audio_dir,
        mock_get_video_dir,
        tmp_path,
    ):
        """Test creating manifest with exactly 18 clips."""
        # Setup directories
        video_dir = tmp_path / "videos"
        audio_dir = tmp_path / "audio"
        sfx_dir = tmp_path / "sfx"
        project_dir = tmp_path

        video_dir.mkdir()
        audio_dir.mkdir()
        sfx_dir.mkdir()

        mock_get_video_dir.return_value = video_dir
        mock_get_audio_dir.return_value = audio_dir
        mock_get_sfx_dir.return_value = sfx_dir
        mock_get_project_dir.return_value = project_dir

        # Create 18 test files
        for i in range(1, 19):
            (video_dir / f"clip_{i:02d}.mp4").write_text("fake video")
            (audio_dir / f"clip_{i:02d}.mp3").write_text("fake audio")
            (sfx_dir / f"sfx_{i:02d}.wav").write_text("fake sfx")

        # Mock audio duration probing
        mock_probe_duration.return_value = 7.2

        service = VideoAssemblyService("poke1", "vid_abc123")
        manifest = await service.create_assembly_manifest(clip_count=18)

        assert len(manifest.clips) == 18
        assert manifest.output_path == project_dir / "vid_abc123_final.mp4"
        assert all(clip.narration_duration == 7.2 for clip in manifest.clips)

    @patch("app.services.video_assembly.get_video_dir")
    @patch("app.services.video_assembly.get_audio_dir")
    @patch("app.services.video_assembly.get_sfx_dir")
    @patch("app.services.video_assembly.get_project_dir")
    @pytest.mark.asyncio
    async def test_create_manifest_missing_video_file(
        self,
        mock_get_project_dir,
        mock_get_sfx_dir,
        mock_get_audio_dir,
        mock_get_video_dir,
        tmp_path,
    ):
        """Test creating manifest when video file is missing."""
        video_dir = tmp_path / "videos"
        audio_dir = tmp_path / "audio"
        sfx_dir = tmp_path / "sfx"

        video_dir.mkdir()
        audio_dir.mkdir()
        sfx_dir.mkdir()

        mock_get_video_dir.return_value = video_dir
        mock_get_audio_dir.return_value = audio_dir
        mock_get_sfx_dir.return_value = sfx_dir
        mock_get_project_dir.return_value = tmp_path

        # Create only audio and sfx files (missing video)
        (audio_dir / "clip_01.mp3").write_text("fake audio")
        (sfx_dir / "sfx_01.wav").write_text("fake sfx")

        service = VideoAssemblyService("poke1", "vid_abc123")

        with pytest.raises(FileNotFoundError, match="Video file missing"):
            await service.create_assembly_manifest(clip_count=1)


class TestValidateInputFiles:
    """Test validate_input_files method."""

    @pytest.mark.asyncio
    async def test_validate_all_files_exist(self, tmp_path):
        """Test validation passes when all files exist."""
        # Create test files
        clip = ClipAssemblySpec(
            clip_number=1,
            video_path=tmp_path / "clip_01.mp4",
            narration_path=tmp_path / "clip_01.mp3",
            sfx_path=tmp_path / "sfx_01.wav",
            narration_duration=7.2,
        )

        clip.video_path.write_text("fake video")
        clip.narration_path.write_text("fake audio")
        clip.sfx_path.write_text("fake sfx")

        manifest = AssemblyManifest(
            clips=[clip], output_path=tmp_path / "final.mp4"
        )

        service = VideoAssemblyService("poke1", "vid_abc123")
        await service.validate_input_files(manifest)  # Should not raise

    @pytest.mark.asyncio
    async def test_validate_missing_file_raises_error(self, tmp_path):
        """Test validation raises error when file is missing."""
        clip = ClipAssemblySpec(
            clip_number=1,
            video_path=tmp_path / "clip_01.mp4",
            narration_path=tmp_path / "clip_01.mp3",
            sfx_path=tmp_path / "sfx_01.wav",
            narration_duration=7.2,
        )

        # Only create video and audio (missing SFX)
        clip.video_path.write_text("fake video")
        clip.narration_path.write_text("fake audio")

        manifest = AssemblyManifest(
            clips=[clip], output_path=tmp_path / "final.mp4"
        )

        service = VideoAssemblyService("poke1", "vid_abc123")

        with pytest.raises(FileNotFoundError, match="Missing 1 input files"):
            await service.validate_input_files(manifest)


class TestAssembleVideo:
    """Test assemble_video method."""

    @patch("app.services.video_assembly.run_cli_script")
    @patch("app.services.video_assembly.get_project_dir")
    @patch("app.services.video_assembly.VideoAssemblyService.validate_output_video")
    @pytest.mark.asyncio
    async def test_assemble_video_success(
        self,
        mock_validate_output,
        mock_get_project_dir,
        mock_run_cli_script,
        tmp_path,
    ):
        """Test assembling video successfully."""
        project_dir = tmp_path
        mock_get_project_dir.return_value = project_dir

        # Create clip
        clip = ClipAssemblySpec(
            clip_number=1,
            video_path=tmp_path / "clip_01.mp4",
            narration_path=tmp_path / "clip_01.mp3",
            sfx_path=tmp_path / "sfx_01.wav",
            narration_duration=7.2,
        )

        output_path = tmp_path / "final.mp4"
        manifest = AssemblyManifest(clips=[clip], output_path=output_path)

        # Mock CLI script success
        mock_result = MagicMock()
        mock_result.stdout = "FFmpeg completed successfully"
        mock_run_cli_script.return_value = mock_result

        # Create fake output file
        output_path.write_text("fake video data")

        # Mock validation
        mock_validate_output.return_value = {
            "duration": 91.5,
            "file_size_mb": 142.3,
            "resolution": "1920x1080",
            "video_codec": "h264",
            "audio_codec": "aac",
        }

        service = VideoAssemblyService("poke1", "vid_abc123")
        result = await service.assemble_video(manifest)

        assert result["duration"] == 91.5
        assert result["file_size_mb"] == 142.3
        assert result["resolution"] == "1920x1080"

        # Verify manifest JSON was written
        manifest_path = project_dir / "assembly_manifest.json"
        assert manifest_path.exists()
        manifest_data = json.loads(manifest_path.read_text())
        assert len(manifest_data["clips"]) == 1

    @patch("app.services.video_assembly.run_cli_script")
    @patch("app.services.video_assembly.get_project_dir")
    @pytest.mark.asyncio
    async def test_assemble_video_cli_script_error(
        self, mock_get_project_dir, mock_run_cli_script, tmp_path
    ):
        """Test assembling video when CLI script fails."""
        mock_get_project_dir.return_value = tmp_path

        clip = ClipAssemblySpec(
            clip_number=1,
            video_path=tmp_path / "clip_01.mp4",
            narration_path=tmp_path / "clip_01.mp3",
            sfx_path=tmp_path / "sfx_01.wav",
            narration_duration=7.2,
        )

        manifest = AssemblyManifest(
            clips=[clip], output_path=tmp_path / "final.mp4"
        )

        # Mock CLI script failure
        mock_run_cli_script.side_effect = CLIScriptError(
            "assemble_video.py", 1, "FFmpeg error: invalid codec"
        )

        service = VideoAssemblyService("poke1", "vid_abc123")

        with pytest.raises(CLIScriptError):
            await service.assemble_video(manifest)


class TestValidateOutputVideo:
    """Test validate_output_video method."""

    @patch("app.services.video_assembly.asyncio.to_thread")
    @pytest.mark.asyncio
    async def test_validate_output_video_success(self, mock_to_thread, tmp_path):
        """Test validating output video successfully."""
        video_path = tmp_path / "final.mp4"
        video_path.write_text("fake video data " * 1000)  # Create non-empty file

        # Mock ffprobe result
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1920,
                        "height": 1080,
                    },
                    {
                        "codec_type": "audio",
                        "codec_name": "aac",
                    },
                ],
                "format": {
                    "duration": "91.5",
                },
            }
        )
        mock_to_thread.return_value = mock_result

        service = VideoAssemblyService("poke1", "vid_abc123")
        metadata = await service.validate_output_video(video_path)

        assert metadata["duration"] == 91.5
        assert metadata["resolution"] == "1920x1080"
        assert metadata["video_codec"] == "h264"
        assert metadata["audio_codec"] == "aac"
        assert metadata["file_size_mb"] > 0

    @pytest.mark.asyncio
    async def test_validate_output_video_file_not_found(self, tmp_path):
        """Test validating video when file doesn't exist."""
        video_path = tmp_path / "nonexistent.mp4"

        service = VideoAssemblyService("poke1", "vid_abc123")

        with pytest.raises(FileNotFoundError, match="Video file not found"):
            await service.validate_output_video(video_path)

    @patch("app.services.video_assembly.asyncio.to_thread")
    @pytest.mark.asyncio
    async def test_validate_output_video_no_video_stream(self, mock_to_thread, tmp_path):
        """Test validating video when no video stream found."""
        video_path = tmp_path / "final.mp4"
        video_path.write_text("fake video data")

        # Mock ffprobe result with only audio stream
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "streams": [
                    {
                        "codec_type": "audio",
                        "codec_name": "aac",
                    }
                ],
                "format": {
                    "duration": "91.5",
                },
            }
        )
        mock_to_thread.return_value = mock_result

        service = VideoAssemblyService("poke1", "vid_abc123")

        with pytest.raises(ValueError, match="No video stream found"):
            await service.validate_output_video(video_path)


class TestCheckFileExists:
    """Test check_file_exists method."""

    def test_check_file_exists_true(self, tmp_path):
        """Test checking file exists."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        service = VideoAssemblyService("poke1", "vid_abc123")
        assert service.check_file_exists(file_path) is True

    def test_check_file_exists_false(self, tmp_path):
        """Test checking file that doesn't exist."""
        file_path = tmp_path / "nonexistent.txt"

        service = VideoAssemblyService("poke1", "vid_abc123")
        assert service.check_file_exists(file_path) is False

    def test_check_empty_file_returns_false(self, tmp_path):
        """Test checking empty file returns False."""
        file_path = tmp_path / "empty.txt"
        file_path.touch()  # Create empty file

        service = VideoAssemblyService("poke1", "vid_abc123")
        assert service.check_file_exists(file_path) is False
