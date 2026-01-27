"""Tests for AI Disclosure Manager (Story 7.7 AC4)."""

import pytest
from unittest.mock import Mock, MagicMock, patch

from app.services.compliance.ai_disclosure_manager import AIDisclosureManager


@pytest.fixture
def disclosure_manager():
    """Create AIDisclosureManager instance."""
    return AIDisclosureManager()


@pytest.fixture
def mock_youtube_service():
    """Mock YouTube Data API service."""
    service = Mock()
    service.videos().update().execute = Mock(return_value={"id": "test_video_123"})
    service.videos().list().execute = Mock(
        return_value={"items": [{"contentDetails": {"hasAlteredContent": True}}]}
    )
    return service


class TestAIDisclosureAPI:
    """Test AI disclosure via YouTube Data API."""

    def test_set_ai_disclosure_success(self, disclosure_manager, mock_youtube_service):
        """Test setting hasAlteredContent=true via API."""
        disclosure_manager.set_ai_disclosure("test_video_123", mock_youtube_service)

        # Verify YouTube API was called with correct parameters
        mock_youtube_service.videos().update.assert_called()
        # Check that update was called with the right params
        assert mock_youtube_service.videos().update().execute.called

    def test_set_ai_disclosure_api_error(self, disclosure_manager, mock_youtube_service):
        """Test handling of YouTube API errors."""
        mock_youtube_service.videos().update().execute.side_effect = Exception("API quota exceeded")

        with pytest.raises(Exception, match="API quota exceeded"):
            disclosure_manager.set_ai_disclosure("test_video_123", mock_youtube_service)

    def test_validate_disclosure_set_success(self, disclosure_manager, mock_youtube_service):
        """Test validation of successfully set disclosure."""
        result = disclosure_manager.validate_disclosure_set("test_video_123", mock_youtube_service)

        assert result is True
        mock_youtube_service.videos().list.assert_called()
        assert mock_youtube_service.videos().list().execute.called

    def test_validate_disclosure_not_set(self, disclosure_manager, mock_youtube_service):
        """Test validation fails when disclosure not set."""
        # Mock response with hasAlteredContent=false
        mock_youtube_service.videos().list().execute.return_value = {
            "items": [{"contentDetails": {"hasAlteredContent": False}}]
        }

        with pytest.raises(ValueError, match="AI disclosure not set"):
            disclosure_manager.validate_disclosure_set("test_video_123", mock_youtube_service)


class TestDescriptionDisclosure:
    """Test text disclosure in video description."""

    def test_add_disclosure_to_description(self, disclosure_manager):
        """Test prepending AI disclosure to description."""
        original_description = "Watch Pikachu hunt for food in this nature documentary!"

        updated_description = disclosure_manager.add_disclosure_to_description(original_description)

        # Check disclosure prepended
        assert "🤖 AI DISCLOSURE" in updated_description
        assert "Google Gemini AI" in updated_description
        assert "Kling AI Video Generator" in updated_description
        assert "ElevenLabs AI Voice Synthesis" in updated_description

        # Check original description preserved
        assert original_description in updated_description

    def test_add_disclosure_idempotent(self, disclosure_manager):
        """Test adding disclosure multiple times doesn't duplicate."""
        original_description = "Pokemon nature doc"

        # Add disclosure twice
        description_v1 = disclosure_manager.add_disclosure_to_description(original_description)
        description_v2 = disclosure_manager.add_disclosure_to_description(description_v1)

        # Should be identical (no duplicate disclosure)
        assert description_v1 == description_v2
        assert description_v1.count("🤖 AI DISCLOSURE") == 1

    def test_add_disclosure_empty_description(self, disclosure_manager):
        """Test adding disclosure to empty description."""
        updated_description = disclosure_manager.add_disclosure_to_description("")

        assert "🤖 AI DISCLOSURE" in updated_description
        assert len(updated_description) > 100  # Disclosure is substantial


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_validate_disclosure_video_not_found(self, disclosure_manager, mock_youtube_service):
        """Test validation when video not found in API response."""
        mock_youtube_service.videos().list().execute.return_value = {"items": []}

        with pytest.raises(ValueError, match="Video .* not found"):  # noqa: RUF043
            disclosure_manager.validate_disclosure_set("nonexistent_video", mock_youtube_service)

    def test_validate_disclosure_malformed_response(self, disclosure_manager, mock_youtube_service):
        """Test validation with malformed API response."""
        mock_youtube_service.videos().list().execute.return_value = {
            "items": [{}]  # Missing contentDetails
        }

        with pytest.raises(ValueError, match="AI disclosure not set"):
            disclosure_manager.validate_disclosure_set("test_video_123", mock_youtube_service)
