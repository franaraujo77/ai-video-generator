"""Tests for generate_audio.py script.

Tests the ElevenLabs TTS audio generation with mocked API calls.

Priority: P1-P2 - Critical for narration pipeline.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_audio import generate_audio


class TestGenerateAudio:
    """Tests for generate_audio function."""

    def test_p1_returns_true_on_successful_generation(self, tmp_path: Path):
        """[P1] Should return True when audio generation succeeds."""
        # GIVEN: Mocked successful API response
        output_path = tmp_path / "audio.mp3"
        fake_audio_content = b"fake mp3 audio data"

        with patch("generate_audio.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = fake_audio_content
            mock_post.return_value = mock_response

            # WHEN: Generating audio
            result = generate_audio(
                text="Test narration text",
                output_path=str(output_path),
                api_key="test-api-key",
                voice_id="test-voice-id",
            )

            # THEN: Returns True and file exists
            assert result is True
            assert output_path.exists()
            assert output_path.read_bytes() == fake_audio_content

    def test_p1_returns_false_on_api_error(self, tmp_path: Path):
        """[P1] Should return False when API returns error."""
        # GIVEN: Mocked failed API response
        output_path = tmp_path / "audio.mp3"

        with patch("generate_audio.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "Invalid API key"
            mock_post.return_value = mock_response

            # WHEN: Generating audio
            result = generate_audio(
                text="Test narration",
                output_path=str(output_path),
                api_key="invalid-key",
                voice_id="test-voice-id",
            )

            # THEN: Returns False
            assert result is False

    def test_p1_calls_correct_api_endpoint(self, tmp_path: Path):
        """[P1] Should call ElevenLabs TTS endpoint with correct voice ID."""
        # GIVEN: Test parameters
        output_path = tmp_path / "audio.mp3"
        voice_id = "abc123voice"

        with patch("generate_audio.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio"
            mock_post.return_value = mock_response

            # WHEN: Generating audio
            generate_audio(
                text="Test",
                output_path=str(output_path),
                api_key="test-key",
                voice_id=voice_id,
            )

            # THEN: Correct endpoint called
            call_args = mock_post.call_args
            endpoint = call_args[0][0]
            assert f"/v1/text-to-speech/{voice_id}" in endpoint

    def test_p1_sends_correct_headers(self, tmp_path: Path):
        """[P1] Should send API key in headers."""
        # GIVEN: Test API key
        output_path = tmp_path / "audio.mp3"
        api_key = "test-elevenlabs-key"

        with patch("generate_audio.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio"
            mock_post.return_value = mock_response

            # WHEN: Generating audio
            generate_audio(
                text="Test",
                output_path=str(output_path),
                api_key=api_key,
                voice_id="voice",
            )

            # THEN: API key in headers
            call_kwargs = mock_post.call_args[1]
            headers = call_kwargs.get("headers", {})
            assert headers.get("xi-api-key") == api_key

    def test_p1_sends_correct_payload(self, tmp_path: Path):
        """[P1] Should send text and voice settings in payload."""
        # GIVEN: Test parameters
        output_path = tmp_path / "audio.mp3"
        text = "After... the rain... hunger awakens."

        with patch("generate_audio.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio"
            mock_post.return_value = mock_response

            # WHEN: Generating audio with custom settings
            generate_audio(
                text=text,
                output_path=str(output_path),
                api_key="key",
                voice_id="voice",
                stability=0.5,
                similarity_boost=0.8,
                style=0.2,
            )

            # THEN: Payload contains text and settings
            call_kwargs = mock_post.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["text"] == text
            assert payload["voice_settings"]["stability"] == 0.5
            assert payload["voice_settings"]["similarity_boost"] == 0.8
            assert payload["voice_settings"]["style"] == 0.2

    def test_p1_creates_output_directory(self, tmp_path: Path):
        """[P1] Should create output directory if it doesn't exist."""
        # GIVEN: Output in nested non-existent directory
        output_path = tmp_path / "nested" / "deep" / "audio.mp3"

        with patch("generate_audio.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio data"
            mock_post.return_value = mock_response

            # WHEN: Generating audio
            result = generate_audio(
                text="Test",
                output_path=str(output_path),
                api_key="key",
                voice_id="voice",
            )

            # THEN: File exists in newly created directory
            assert result is True
            assert output_path.exists()

    def test_p2_uses_default_model(self, tmp_path: Path):
        """[P2] Should use eleven_multilingual_v2 model by default."""
        # GIVEN: Default model
        output_path = tmp_path / "audio.mp3"

        with patch("generate_audio.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio"
            mock_post.return_value = mock_response

            # WHEN: Generating audio without specifying model
            generate_audio(
                text="Test",
                output_path=str(output_path),
                api_key="key",
                voice_id="voice",
            )

            # THEN: Default model used
            call_kwargs = mock_post.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["model_id"] == "eleven_multilingual_v2"

    def test_p2_uses_custom_model(self, tmp_path: Path):
        """[P2] Should use custom model when specified."""
        # GIVEN: Custom model
        output_path = tmp_path / "audio.mp3"
        custom_model = "eleven_turbo_v2"

        with patch("generate_audio.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio"
            mock_post.return_value = mock_response

            # WHEN: Generating audio with custom model
            generate_audio(
                text="Test",
                output_path=str(output_path),
                api_key="key",
                voice_id="voice",
                model_id=custom_model,
            )

            # THEN: Custom model used
            call_kwargs = mock_post.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["model_id"] == custom_model

    def test_p2_handles_exception(self, tmp_path: Path):
        """[P2] Should return False on exception."""
        # GIVEN: Exception during API call
        output_path = tmp_path / "audio.mp3"

        with patch("generate_audio.requests.post") as mock_post:
            mock_post.side_effect = Exception("Network error")

            # WHEN: Generating audio
            result = generate_audio(
                text="Test",
                output_path=str(output_path),
                api_key="key",
                voice_id="voice",
            )

            # THEN: Returns False
            assert result is False

    def test_p2_enables_speaker_boost(self, tmp_path: Path):
        """[P2] Should enable speaker boost in voice settings."""
        # GIVEN: Standard call
        output_path = tmp_path / "audio.mp3"

        with patch("generate_audio.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"audio"
            mock_post.return_value = mock_response

            # WHEN: Generating audio
            generate_audio(
                text="Test",
                output_path=str(output_path),
                api_key="key",
                voice_id="voice",
            )

            # THEN: Speaker boost enabled
            call_kwargs = mock_post.call_args[1]
            payload = call_kwargs.get("json", {})
            assert payload["voice_settings"]["use_speaker_boost"] is True
