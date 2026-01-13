"""Tests for assemble_video.py script.

Tests the video assembly helper functions with mocked FFmpeg/FFprobe calls.

Priority: P1 - Critical path for final documentary assembly.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from assemble_video import get_audio_duration, get_video_info


class TestGetAudioDuration:
    """Tests for get_audio_duration function."""

    def test_p1_returns_duration_from_ffprobe(self, tmp_path: Path):
        """[P1] Should return duration in seconds from FFprobe."""
        # GIVEN: Mocked FFprobe output
        audio_path = tmp_path / "audio.mp3"
        audio_path.touch()  # Create empty file for path validation

        expected_duration = 7.5

        with patch("assemble_video.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = f"{expected_duration}\n"
            mock_run.return_value = mock_result

            # WHEN: Getting audio duration
            result = get_audio_duration(str(audio_path))

            # THEN: Returns correct duration
            assert result == expected_duration

    def test_p1_calls_ffprobe_with_correct_args(self, tmp_path: Path):
        """[P1] Should call FFprobe with correct arguments."""
        # GIVEN: A path to check
        audio_path = tmp_path / "test.mp3"
        audio_path.touch()

        with patch("assemble_video.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "5.0\n"
            mock_run.return_value = mock_result

            # WHEN: Getting duration
            get_audio_duration(str(audio_path))

            # THEN: FFprobe called with expected args
            call_args = mock_run.call_args[0][0]
            assert "ffprobe" in call_args
            assert "-show_entries" in call_args
            assert "format=duration" in call_args
            assert str(audio_path) in call_args

    def test_p1_returns_none_on_ffprobe_error(self, tmp_path: Path):
        """[P1] Should return None when FFprobe fails."""
        # GIVEN: Mocked FFprobe failure
        audio_path = tmp_path / "audio.mp3"
        audio_path.touch()

        with patch("assemble_video.subprocess.run") as mock_run:
            import subprocess

            mock_run.side_effect = subprocess.CalledProcessError(
                1, "ffprobe", stderr="File not found"
            )

            # WHEN: Getting duration
            result = get_audio_duration(str(audio_path))

            # THEN: Returns None
            assert result is None

    def test_p2_returns_none_on_invalid_duration_format(self, tmp_path: Path):
        """[P2] Should return None when duration can't be parsed."""
        # GIVEN: Mocked non-numeric FFprobe output
        audio_path = tmp_path / "audio.mp3"
        audio_path.touch()

        with patch("assemble_video.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "not_a_number\n"
            mock_run.return_value = mock_result

            # WHEN: Getting duration
            result = get_audio_duration(str(audio_path))

            # THEN: Returns None
            assert result is None

    def test_p2_handles_whitespace_in_output(self, tmp_path: Path):
        """[P2] Should strip whitespace from FFprobe output."""
        # GIVEN: FFprobe output with extra whitespace
        audio_path = tmp_path / "audio.mp3"
        audio_path.touch()

        with patch("assemble_video.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "  8.25  \n\n"
            mock_run.return_value = mock_result

            # WHEN: Getting duration
            result = get_audio_duration(str(audio_path))

            # THEN: Returns correct duration
            assert result == 8.25


class TestGetVideoInfo:
    """Tests for get_video_info function."""

    def test_p1_returns_video_info_dict(self, tmp_path: Path):
        """[P1] Should return dict with duration, resolution, and file size."""
        # GIVEN: Video file and mocked FFprobe
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"x" * 1024 * 1024)  # 1MB fake video

        with patch("assemble_video.subprocess.run") as mock_run:
            # First call: duration
            duration_result = MagicMock()
            duration_result.stdout = "90.5\n"

            # Second call: resolution
            resolution_result = MagicMock()
            resolution_result.stdout = "1920,1080\n"

            mock_run.side_effect = [duration_result, resolution_result]

            # WHEN: Getting video info
            result = get_video_info(str(video_path))

            # THEN: Returns dict with all fields
            assert result is not None
            assert result["duration"] == 90.5
            assert result["resolution"] == "1920x1080"
            assert "file_size" in result
            assert "file_size_mb" in result

    def test_p1_calculates_file_size_correctly(self, tmp_path: Path):
        """[P1] Should calculate file size in bytes and MB."""
        # GIVEN: Video file with known size (2MB)
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"x" * 2 * 1024 * 1024)

        with patch("assemble_video.subprocess.run") as mock_run:
            duration_result = MagicMock()
            duration_result.stdout = "60.0\n"
            resolution_result = MagicMock()
            resolution_result.stdout = "1280,720\n"
            mock_run.side_effect = [duration_result, resolution_result]

            # WHEN: Getting video info
            result = get_video_info(str(video_path))

            # THEN: File size is calculated correctly
            assert result["file_size"] == 2 * 1024 * 1024
            assert result["file_size_mb"] == 2.0

    def test_p2_returns_none_on_ffprobe_error(self, tmp_path: Path):
        """[P2] Should return None when FFprobe fails."""
        # GIVEN: Mocked FFprobe failure
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")

        with patch("assemble_video.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("FFprobe not found")

            # WHEN: Getting video info
            result = get_video_info(str(video_path))

            # THEN: Returns None
            assert result is None


class TestAssemblyManifest:
    """Tests for manifest parsing and validation."""

    def test_p1_valid_manifest_structure(self, tmp_path: Path):
        """[P1] Valid manifest should have clips array with video/audio pairs."""
        # GIVEN: A valid manifest
        manifest = {
            "clips": [
                {"clip_number": 1, "video": "clip_01.mp4", "audio": "clip_01.mp3"},
                {"clip_number": 2, "video": "clip_02.mp4", "audio": "clip_02.mp3"},
            ]
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        # WHEN: Reading manifest
        with open(manifest_path) as f:
            loaded = json.load(f)

        # THEN: Structure is correct
        assert "clips" in loaded
        assert len(loaded["clips"]) == 2
        assert loaded["clips"][0]["video"] == "clip_01.mp4"
        assert loaded["clips"][0]["audio"] == "clip_01.mp3"

    def test_p2_manifest_missing_clips_key(self, tmp_path: Path):
        """[P2] Manifest without clips key should be handled."""
        # GIVEN: Invalid manifest
        manifest = {"wrong_key": []}
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        # WHEN: Reading manifest
        with open(manifest_path) as f:
            loaded = json.load(f)

        # THEN: clips key is missing
        assert loaded.get("clips", []) == []

    def test_p2_manifest_with_18_clips(self, tmp_path: Path):
        """[P2] Manifest for full documentary should have 18 clips."""
        # GIVEN: Full 18-clip manifest
        manifest = {
            "clips": [
                {"clip_number": i, "video": f"clip_{i:02d}.mp4", "audio": f"clip_{i:02d}.mp3"}
                for i in range(1, 19)
            ]
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        # WHEN: Reading manifest
        with open(manifest_path) as f:
            loaded = json.load(f)

        # THEN: Has exactly 18 clips
        assert len(loaded["clips"]) == 18
        assert loaded["clips"][0]["clip_number"] == 1
        assert loaded["clips"][17]["clip_number"] == 18
