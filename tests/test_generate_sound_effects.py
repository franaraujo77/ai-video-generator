"""Tests for generate_sound_effects.py script.

Tests the ElevenLabs Sound Effects API and FFmpeg normalization
with mocked external calls.

Priority: P1-P2 - Critical for ambient audio pipeline.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_sound_effects import generate_sound_effect, normalize_audio


class TestGenerateSoundEffect:
    """Tests for generate_sound_effect function."""

    def test_p1_returns_true_on_successful_generation(self, tmp_path: Path):
        """[P1] Should return True when sound effect generation succeeds."""
        # GIVEN: Mocked successful API response
        output_path = tmp_path / "sfx.mp3"
        fake_audio_content = b"fake mp3 sound effect data"

        with patch("generate_sound_effects.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = fake_audio_content
            mock_post.return_value = mock_response

            # WHEN: Generating sound effect
            result = generate_sound_effect(
                text="Rain and thunder ambience",
                output_path=str(output_path),
                api_key="test-api-key",
            )

            # THEN: Returns True and file exists
            assert result is True
            assert output_path.exists()
            assert output_path.read_bytes() == fake_audio_content

    def test_p1_returns_false_on_api_error(self, tmp_path: Path):
        """[P1] Should return False when API returns error."""
        # GIVEN: Mocked failed API response
        output_path = tmp_path / "sfx.mp3"

        with patch("generate_sound_effects.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response

            # WHEN: Generating sound effect
            result = generate_sound_effect(
                text="Rain sounds",
                output_path=str(output_path),
                api_key="test-key",
            )

            # THEN: Returns False
            assert result is False

    def test_p1_calls_sound_generation_endpoint(self, tmp_path: Path):
        """[P1] Should call ElevenLabs sound-generation endpoint."""
        # GIVEN: Test parameters
        output_path = tmp_path / "sfx.mp3"

        with patch("generate_sound_effects.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio"
            mock_post.return_value = mock_response

            # WHEN: Generating sound effect
            generate_sound_effect(
                text="Thunder",
                output_path=str(output_path),
                api_key="key",
            )

            # THEN: Correct endpoint called
            call_args = mock_post.call_args
            endpoint = call_args[0][0]
            assert "/v1/sound-generation" in endpoint

    def test_p1_sends_correct_headers(self, tmp_path: Path):
        """[P1] Should send API key in headers."""
        # GIVEN: Test API key
        output_path = tmp_path / "sfx.mp3"
        api_key = "test-elevenlabs-key"

        with patch("generate_sound_effects.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio"
            mock_post.return_value = mock_response

            # WHEN: Generating sound effect
            generate_sound_effect(
                text="Wind",
                output_path=str(output_path),
                api_key=api_key,
            )

            # THEN: API key in headers
            call_kwargs = mock_post.call_args[1]
            headers = call_kwargs.get("headers", {})
            assert headers.get("xi-api-key") == api_key

    def test_p1_sends_correct_payload(self, tmp_path: Path):
        """[P1] Should send text, duration, and prompt_influence in payload."""
        # GIVEN: Test parameters
        output_path = tmp_path / "sfx.mp3"
        text = "Abandoned power station ambience with rain"
        duration = 15.0
        prompt_influence = 0.5

        with patch("generate_sound_effects.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio"
            mock_post.return_value = mock_response

            # WHEN: Generating sound effect
            generate_sound_effect(
                text=text,
                output_path=str(output_path),
                api_key="key",
                duration_seconds=duration,
                prompt_influence=prompt_influence,
            )

            # THEN: Payload contains correct parameters
            call_kwargs = mock_post.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["text"] == text
            assert payload["duration_seconds"] == duration
            assert payload["prompt_influence"] == prompt_influence

    def test_p1_creates_output_directory(self, tmp_path: Path):
        """[P1] Should create output directory if it doesn't exist."""
        # GIVEN: Output in nested non-existent directory
        output_path = tmp_path / "nested" / "deep" / "sfx.mp3"

        with patch("generate_sound_effects.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio data"
            mock_post.return_value = mock_response

            # WHEN: Generating sound effect
            result = generate_sound_effect(
                text="Rain",
                output_path=str(output_path),
                api_key="key",
            )

            # THEN: File exists in newly created directory
            assert result is True
            assert output_path.exists()

    def test_p2_uses_default_duration(self, tmp_path: Path):
        """[P2] Should use 10 seconds duration by default."""
        # GIVEN: Default parameters
        output_path = tmp_path / "sfx.mp3"

        with patch("generate_sound_effects.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio"
            mock_post.return_value = mock_response

            # WHEN: Generating sound effect without specifying duration
            generate_sound_effect(
                text="Thunder",
                output_path=str(output_path),
                api_key="key",
            )

            # THEN: Default 10s duration used
            call_kwargs = mock_post.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["duration_seconds"] == 10.0

    def test_p2_uses_default_prompt_influence(self, tmp_path: Path):
        """[P2] Should use 0.3 prompt influence by default."""
        # GIVEN: Default parameters
        output_path = tmp_path / "sfx.mp3"

        with patch("generate_sound_effects.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio"
            mock_post.return_value = mock_response

            # WHEN: Generating sound effect without specifying prompt_influence
            generate_sound_effect(
                text="Wind",
                output_path=str(output_path),
                api_key="key",
            )

            # THEN: Default 0.3 prompt influence used
            call_kwargs = mock_post.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["prompt_influence"] == 0.3

    def test_p2_passes_output_format_as_param(self, tmp_path: Path):
        """[P2] Should pass output_format as query parameter."""
        # GIVEN: Custom output format
        output_path = tmp_path / "sfx.mp3"
        output_format = "mp3_44100_192"

        with patch("generate_sound_effects.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio"
            mock_post.return_value = mock_response

            # WHEN: Generating sound effect with custom format
            generate_sound_effect(
                text="Wind",
                output_path=str(output_path),
                api_key="key",
                output_format=output_format,
            )

            # THEN: Format passed as query param
            call_kwargs = mock_post.call_args[1]
            params = call_kwargs.get("params", {})
            assert params.get("output_format") == output_format

    def test_p2_handles_exception(self, tmp_path: Path):
        """[P2] Should return False on exception."""
        # GIVEN: Exception during API call
        output_path = tmp_path / "sfx.mp3"

        with patch("generate_sound_effects.requests.post") as mock_post:
            mock_post.side_effect = Exception("Network error")

            # WHEN: Generating sound effect
            result = generate_sound_effect(
                text="Rain",
                output_path=str(output_path),
                api_key="key",
            )

            # THEN: Returns False
            assert result is False


class TestNormalizeAudio:
    """Tests for normalize_audio function."""

    def test_p1_returns_true_on_successful_normalization(self, tmp_path: Path):
        """[P1] Should return True when normalization succeeds."""
        # GIVEN: Audio file and mocked FFmpeg success
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio data")

        with patch("generate_sound_effects.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            # Mock the temp file replacement
            with patch.object(Path, "replace") as mock_replace:
                # WHEN: Normalizing audio
                result = normalize_audio(str(audio_path))

                # THEN: Returns True
                assert result is True

    def test_p1_returns_false_on_ffmpeg_error(self, tmp_path: Path):
        """[P1] Should return False when FFmpeg fails."""
        # GIVEN: Audio file and mocked FFmpeg failure
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio data")

        with patch("generate_sound_effects.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "FFmpeg error"
            mock_run.return_value = mock_result

            # WHEN: Normalizing audio
            result = normalize_audio(str(audio_path))

            # THEN: Returns False
            assert result is False

    def test_p1_calls_ffmpeg_with_loudnorm_filter(self, tmp_path: Path):
        """[P1] Should call FFmpeg with loudnorm filter."""
        # GIVEN: Audio file
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"audio")

        with patch("generate_sound_effects.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            with patch.object(Path, "replace"):
                # WHEN: Normalizing audio
                normalize_audio(str(audio_path))

                # THEN: FFmpeg called with loudnorm filter
                call_args = mock_run.call_args[0][0]
                assert "ffmpeg" in call_args
                assert "-af" in call_args
                # Find the filter argument
                af_index = call_args.index("-af")
                filter_arg = call_args[af_index + 1]
                assert "loudnorm" in filter_arg

    def test_p1_uses_target_lufs(self, tmp_path: Path):
        """[P1] Should use specified target LUFS in loudnorm filter."""
        # GIVEN: Audio file and target LUFS
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"audio")
        target_lufs = -25.0

        with patch("generate_sound_effects.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            with patch.object(Path, "replace"):
                # WHEN: Normalizing audio with custom LUFS
                normalize_audio(str(audio_path), target_lufs=target_lufs)

                # THEN: Target LUFS in filter argument
                call_args = mock_run.call_args[0][0]
                af_index = call_args.index("-af")
                filter_arg = call_args[af_index + 1]
                assert f"I={target_lufs}" in filter_arg

    def test_p2_uses_default_lufs(self, tmp_path: Path):
        """[P2] Should use -30.0 LUFS by default for background effects."""
        # GIVEN: Audio file with default LUFS
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"audio")

        with patch("generate_sound_effects.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            with patch.object(Path, "replace"):
                # WHEN: Normalizing audio without specifying LUFS
                normalize_audio(str(audio_path))

                # THEN: Default -30.0 LUFS used
                call_args = mock_run.call_args[0][0]
                af_index = call_args.index("-af")
                filter_arg = call_args[af_index + 1]
                assert "I=-30.0" in filter_arg

    def test_p2_handles_exception(self, tmp_path: Path):
        """[P2] Should return False on exception."""
        # GIVEN: Exception during FFmpeg call
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"audio")

        with patch("generate_sound_effects.subprocess.run") as mock_run:
            mock_run.side_effect = Exception("FFmpeg not found")

            # WHEN: Normalizing audio
            result = normalize_audio(str(audio_path))

            # THEN: Returns False
            assert result is False

    def test_p2_sets_sample_rate_to_44100(self, tmp_path: Path):
        """[P2] Should set sample rate to 44100 Hz."""
        # GIVEN: Audio file
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"audio")

        with patch("generate_sound_effects.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            with patch.object(Path, "replace"):
                # WHEN: Normalizing audio
                normalize_audio(str(audio_path))

                # THEN: 44100 sample rate specified
                call_args = mock_run.call_args[0][0]
                assert "-ar" in call_args
                ar_index = call_args.index("-ar")
                assert call_args[ar_index + 1] == "44100"
