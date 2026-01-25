"""Tests for Content Uniqueness Validator (Story 7.7 AC1)."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from PIL import Image

from app.services.compliance.content_uniqueness_validator import (
    ContentUniquenessValidator,
    UNIQUENESS_THRESHOLDS,
)


@pytest.fixture
def validator():
    """Create ContentUniquenessValidator instance."""
    return ContentUniquenessValidator()


@pytest.fixture
def video_metadata():
    """Sample video metadata for testing."""
    return {
        "thumbnail_path": "/tmp/test_thumbnail.png",
        "story_script": {
            "clips": [
                {"description": "Pikachu feeds on berries in forest"},
                {"description": "Pikachu hunts for insects"},
                {"description": "Pikachu rests under tree"},
            ]
        },
        "title": "Pikachu's Forest Adventure",
        "description": "Documentary about Pikachu behavior",
        "tags": ["pokemon", "nature", "forest", "wildlife"],
    }


@pytest.fixture
def recent_videos():
    """Sample recent videos for comparison."""
    return [
        {
            "id": "video1",
            "thumbnail_path": "/tmp/video1_thumbnail.png",
            "story_script": {
                "clips": [
                    {"description": "Charizard flies over mountains"},
                    {"description": "Charizard breathes fire"},
                ]
            },
            "title": "Charizard's Mountain Flight",
            "description": "Documentary about Charizard migration",
            "tags": ["pokemon", "flying", "mountain", "fire"],
        }
    ]


class TestUniquenessValidation:
    """Test content uniqueness validation logic."""

    def test_first_video_always_unique(self, validator, video_metadata):
        """First video on channel should always pass uniqueness check."""
        result = validator.validate_video_uniqueness(video_metadata, [])

        assert result["passes"] is True
        assert result["overall_score"] == 1.0
        assert result["scores"]["visual_uniqueness"] == 1.0
        assert result["scores"]["narrative_uniqueness"] == 1.0
        assert result["scores"]["metadata_uniqueness"] == 1.0

    @patch("app.services.compliance.content_uniqueness_validator.Image.open")
    @patch("app.services.compliance.content_uniqueness_validator.imagehash.phash")
    def test_visual_uniqueness_calculation(
        self, mock_phash, mock_image_open, validator, video_metadata, recent_videos
    ):
        """Test perceptual hash visual uniqueness scoring."""
        # Mock images
        mock_current_img = MagicMock()
        mock_recent_img = MagicMock()
        mock_image_open.side_effect = [mock_current_img, mock_recent_img]

        # Mock perceptual hashes with distance of 32 (50% different)
        mock_current_hash = MagicMock()
        mock_recent_hash = MagicMock()
        mock_current_hash.__sub__ = lambda self, other: 32  # Hash distance
        mock_phash.side_effect = [mock_current_hash, mock_recent_hash]

        # Create temporary test files
        Path(video_metadata["thumbnail_path"]).touch()
        Path(recent_videos[0]["thumbnail_path"]).touch()

        try:
            result = validator.validate_video_uniqueness(
                video_metadata, recent_videos
            )

            # 32/64 = 50% similarity → 50% uniqueness
            assert result["scores"]["visual_uniqueness"] == pytest.approx(0.5, abs=0.1)
        finally:
            # Clean up
            Path(video_metadata["thumbnail_path"]).unlink(missing_ok=True)
            Path(recent_videos[0]["thumbnail_path"]).unlink(missing_ok=True)

    def test_narrative_uniqueness_different_behaviors(
        self, validator, video_metadata, recent_videos
    ):
        """Test story uniqueness with completely different behavior sequences."""
        result = validator.validate_video_uniqueness(video_metadata, recent_videos)

        # Different behaviors: feeding/hunting/resting vs flying/fire
        # Should score moderate to high uniqueness (>50%)
        assert result["scores"]["narrative_uniqueness"] > 0.5

    def test_narrative_uniqueness_similar_behaviors(
        self, validator, video_metadata, recent_videos
    ):
        """Test story uniqueness with similar behavior sequences."""
        # Make recent video similar to current video
        recent_videos[0]["story_script"] = {
            "clips": [
                {"description": "Charizard feeds on berries"},
                {"description": "Charizard hunts prey"},
                {"description": "Charizard rests"},
            ]
        }

        result = validator.validate_video_uniqueness(video_metadata, recent_videos)

        # Similar behaviors: feeding/hunting/resting vs feeding/hunting/resting
        # Should score lower uniqueness
        assert result["scores"]["narrative_uniqueness"] < 0.5

    def test_metadata_uniqueness_different_titles(
        self, validator, video_metadata, recent_videos
    ):
        """Test metadata uniqueness with different titles/descriptions/tags."""
        result = validator.validate_video_uniqueness(video_metadata, recent_videos)

        # Completely different metadata
        # "Pikachu's Forest Adventure" vs "Charizard's Mountain Flight"
        # Note: Some overlap in tags ("pokemon") lowers uniqueness score
        assert result["scores"]["metadata_uniqueness"] > 0.5

    def test_metadata_uniqueness_similar_titles(
        self, validator, video_metadata, recent_videos
    ):
        """Test metadata uniqueness with similar titles/descriptions/tags."""
        # Make recent video similar to current video
        recent_videos[0]["title"] = "Pikachu's Forest Journey"
        recent_videos[0]["description"] = "Documentary about Pikachu foraging behavior"
        recent_videos[0]["tags"] = ["pokemon", "nature", "forest", "behavior"]

        result = validator.validate_video_uniqueness(video_metadata, recent_videos)

        # Very similar metadata
        assert result["scores"]["metadata_uniqueness"] < 0.5

    def test_uniqueness_threshold_enforcement(
        self, validator, video_metadata, recent_videos
    ):
        """Test that all scores must pass 70% threshold."""
        # Make story very similar (below threshold)
        recent_videos[0]["story_script"] = video_metadata["story_script"]

        result = validator.validate_video_uniqueness(video_metadata, recent_videos)

        # Even if visual and metadata are unique, narrative fails → overall fails
        assert result["passes"] is False
        assert result["scores"]["narrative_uniqueness"] < UNIQUENESS_THRESHOLDS["narrative_uniqueness"]


class TestBehaviorClassification:
    """Test story behavior classification logic."""

    def test_feeding_behavior_classification(self, validator):
        """Test classification of feeding behavior."""
        clip = "Pikachu feeds on berries in the forest"
        category = validator.classify_behavior(clip)

        assert category == "feeding"

    def test_hunting_behavior_classification(self, validator):
        """Test classification of hunting behavior."""
        clip = "Pikachu stalks and chases an insect"
        category = validator.classify_behavior(clip)

        assert category == "hunting"

    def test_social_behavior_classification(self, validator):
        """Test classification of social behavior."""
        clip = "Pikachu plays with other Pokemon in the group"
        category = validator.classify_behavior(clip)

        assert category == "social"

    def test_defensive_behavior_classification(self, validator):
        """Test classification of defensive behavior."""
        clip = "Pikachu defends its territory with electric shock"
        category = validator.classify_behavior(clip)

        assert category == "defensive"

    def test_general_behavior_fallback(self, validator):
        """Test fallback to general category for unmatched behaviors."""
        clip = "Pikachu stands in a field"
        category = validator.classify_behavior(clip)

        assert category == "general"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_thumbnail_path(self, validator, video_metadata, recent_videos):
        """Test handling of missing thumbnail path."""
        video_metadata["thumbnail_path"] = None

        result = validator.validate_video_uniqueness(video_metadata, recent_videos)

        # Should handle gracefully with conservative scoring
        assert "visual_uniqueness" in result["scores"]
        assert result["scores"]["visual_uniqueness"] == 1.0  # Conservative: assume unique

    def test_missing_story_script(self, validator, video_metadata, recent_videos):
        """Test handling of missing story script."""
        video_metadata["story_script"] = None

        result = validator.validate_video_uniqueness(video_metadata, recent_videos)

        # Should handle gracefully
        assert "narrative_uniqueness" in result["scores"]
        assert result["scores"]["narrative_uniqueness"] == 1.0  # Conservative: assume unique

    def test_string_story_script_format(self, validator, video_metadata, recent_videos):
        """Test handling of story script as plain string (not dict)."""
        video_metadata["story_script"] = "Pikachu explores the forest and hunts for food"

        result = validator.validate_video_uniqueness(video_metadata, recent_videos)

        # Should handle both string and dict formats
        assert "narrative_uniqueness" in result["scores"]

    def test_empty_recent_videos_list(self, validator, video_metadata):
        """Test with empty recent videos list."""
        result = validator.validate_video_uniqueness(video_metadata, [])

        assert result["passes"] is True
        assert result["overall_score"] == 1.0
