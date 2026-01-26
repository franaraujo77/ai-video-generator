"""Tests for Duplicate Content Detector (Story 7.7 AC2)."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from app.services.compliance.duplicate_content_detector import (
    DuplicateContentDetector,
    DUPLICATE_HASH_DISTANCE,
    DUPLICATE_SIMILARITY_THRESHOLD,
)


@pytest.fixture
def detector():
    """Create DuplicateContentDetector instance."""
    return DuplicateContentDetector()


@pytest.fixture
def video_metadata():
    """Sample video metadata for testing."""
    return {
        "thumbnail_path": "/tmp/current_video.png", # noqa: S108
        "story_script": "Pikachu explores the forest and hunts for food",
        "title": "Pikachu's Forest Adventure",
        "description": "A nature documentary about Pikachu behavior in the wild",
        "tags": ["pokemon", "nature", "forest"],
    }


@pytest.fixture
def all_channel_videos():
    """Sample channel videos for duplicate checking."""
    return [
        {
            "id": "existing_video_1",
            "thumbnail_path": "/tmp/existing_video_1.png", # noqa: S108
            "story_script": "Charizard flies over mountains and breathes fire",
            "title": "Charizard's Mountain Flight",
            "description": "Documentary about Charizard migration patterns",
            "tags": ["pokemon", "flying", "fire"],
        }
    ]


class TestDuplicateDetection:
    """Test duplicate content detection logic."""

    def test_first_video_never_duplicate(self, detector, video_metadata):
        """First video on channel cannot be a duplicate."""
        result = detector.detect_duplicate(video_metadata, [])

        assert result["is_duplicate"] is False
        assert result["duplicate_of"] is None
        assert result["similarity_score"] == 0.0

    @patch("app.services.compliance.duplicate_content_detector.Image.open")
    @patch("app.services.compliance.duplicate_content_detector.imagehash.phash")
    def test_duplicate_detected_identical_images(
        self, mock_phash, mock_image_open, detector, video_metadata, all_channel_videos
    ):
        """Test duplicate detection with identical perceptual hashes."""
        # Mock images
        mock_current_img = MagicMock()
        mock_existing_img = MagicMock()
        mock_image_open.side_effect = [mock_current_img, mock_existing_img]

        # Mock perceptual hashes - identical images (distance = 0)
        mock_current_hash = MagicMock()
        mock_existing_hash = MagicMock()
        mock_current_hash.__sub__ = lambda self, other: 0  # Perfect match
        mock_phash.side_effect = [mock_current_hash, mock_existing_hash]

        # Make story and metadata nearly identical too
        all_channel_videos[0]["story_script"] = video_metadata["story_script"]
        all_channel_videos[0]["title"] = video_metadata["title"]
        all_channel_videos[0]["description"] = video_metadata["description"]
        all_channel_videos[0]["tags"] = video_metadata["tags"]

        # Create temporary test files
        Path(video_metadata["thumbnail_path"]).touch()
        Path(all_channel_videos[0]["thumbnail_path"]).touch()

        try:
            result = detector.detect_duplicate(video_metadata, all_channel_videos)

            # Should detect as duplicate (visual + story + metadata all >90% similar)
            assert result["is_duplicate"] is True
            assert result["duplicate_of"] == "existing_video_1"
            assert result["similarity_score"] > DUPLICATE_SIMILARITY_THRESHOLD
        finally:
            # Clean up
            Path(video_metadata["thumbnail_path"]).unlink(missing_ok=True)
            Path(all_channel_videos[0]["thumbnail_path"]).unlink(missing_ok=True)

    @patch("app.services.compliance.duplicate_content_detector.Image.open")
    @patch("app.services.compliance.duplicate_content_detector.imagehash.phash")
    def test_not_duplicate_different_images(
        self, mock_phash, mock_image_open, detector, video_metadata, all_channel_videos
    ):
        """Test non-duplicate with visually different images."""
        # Mock images
        mock_current_img = MagicMock()
        mock_existing_img = MagicMock()
        mock_image_open.side_effect = [mock_current_img, mock_existing_img]

        # Mock perceptual hashes - completely different (distance = 50)
        mock_current_hash = MagicMock()
        mock_existing_hash = MagicMock()
        mock_current_hash.__sub__ = lambda self, other: 50  # Very different
        mock_phash.side_effect = [mock_current_hash, mock_existing_hash]

        # Create temporary test files
        Path(video_metadata["thumbnail_path"]).touch()
        Path(all_channel_videos[0]["thumbnail_path"]).touch()

        try:
            result = detector.detect_duplicate(video_metadata, all_channel_videos)

            # Should NOT detect as duplicate (visual dissimilarity)
            assert result["is_duplicate"] is False
            assert result["duplicate_of"] is None
        finally:
            # Clean up
            Path(video_metadata["thumbnail_path"]).unlink(missing_ok=True)
            Path(all_channel_videos[0]["thumbnail_path"]).unlink(missing_ok=True)

    @patch("app.services.compliance.duplicate_content_detector.Image.open")
    @patch("app.services.compliance.duplicate_content_detector.imagehash.phash")
    def test_not_duplicate_similar_visual_different_story(
        self, mock_phash, mock_image_open, detector, video_metadata, all_channel_videos
    ):
        """Test non-duplicate when visual similar but story different."""
        # Mock images
        mock_current_img = MagicMock()
        mock_existing_img = MagicMock()
        mock_image_open.side_effect = [mock_current_img, mock_existing_img]

        # Mock perceptual hashes - similar images (distance = 3)
        mock_current_hash = MagicMock()
        mock_existing_hash = MagicMock()
        mock_current_hash.__sub__ = lambda self, other: 3  # Similar
        mock_phash.side_effect = [mock_current_hash, mock_existing_hash]

        # Keep story and metadata different
        # (default from fixtures)

        # Create temporary test files
        Path(video_metadata["thumbnail_path"]).touch()
        Path(all_channel_videos[0]["thumbnail_path"]).touch()

        try:
            result = detector.detect_duplicate(video_metadata, all_channel_videos)

            # Should NOT detect as duplicate (story/metadata different)
            assert result["is_duplicate"] is False
            assert result["duplicate_of"] is None
        finally:
            # Clean up
            Path(video_metadata["thumbnail_path"]).unlink(missing_ok=True)
            Path(all_channel_videos[0]["thumbnail_path"]).unlink(missing_ok=True)


class TestStoryComparison:
    """Test story similarity comparison."""

    def test_identical_stories(self, detector, video_metadata, all_channel_videos):
        """Test story comparison with identical narratives."""
        video_metadata["story_script"] = "Pikachu explores the forest"
        all_channel_videos[0]["story_script"] = "Pikachu explores the forest"

        similarity = detector.compare_stories(video_metadata, all_channel_videos[0])

        assert similarity > 0.95  # Nearly identical

    def test_completely_different_stories(self, detector, video_metadata, all_channel_videos):
        """Test story comparison with completely different narratives."""
        video_metadata["story_script"] = "Pikachu explores the forest"
        all_channel_videos[0]["story_script"] = "Charizard flies over mountains"

        similarity = detector.compare_stories(video_metadata, all_channel_videos[0])

        # Some word overlap is expected (pokemon names, actions)
        assert similarity < 0.4  # Moderately different

    def test_missing_story_script(self, detector, video_metadata, all_channel_videos):
        """Test story comparison with missing story script."""
        video_metadata["story_script"] = None

        similarity = detector.compare_stories(video_metadata, all_channel_videos[0])

        assert similarity == 0.0  # No comparison possible


class TestMetadataComparison:
    """Test metadata similarity comparison."""

    def test_identical_metadata(self, detector, video_metadata, all_channel_videos):
        """Test metadata comparison with identical titles/descriptions/tags."""
        all_channel_videos[0]["title"] = video_metadata["title"]
        all_channel_videos[0]["description"] = video_metadata["description"]
        all_channel_videos[0]["tags"] = video_metadata["tags"]

        similarity = detector.compare_metadata(video_metadata, all_channel_videos[0])

        assert similarity > 0.95  # Nearly identical

    def test_different_metadata(self, detector, video_metadata, all_channel_videos):
        """Test metadata comparison with completely different metadata."""
        # Use default fixtures (already different)
        similarity = detector.compare_metadata(video_metadata, all_channel_videos[0])

        # Some tag overlap is expected ("pokemon" tag common)
        assert similarity < 0.5  # Moderately different

    def test_similar_titles_only(self, detector, video_metadata, all_channel_videos):
        """Test metadata comparison with similar titles but different descriptions/tags."""
        all_channel_videos[0]["title"] = "Pikachu's Forest Journey"
        # Keep description and tags different

        similarity = detector.compare_metadata(video_metadata, all_channel_videos[0])

        # Title is 50% weight, so similarity should be moderate
        assert 0.3 < similarity < 0.7


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_thumbnail_path(self, detector, video_metadata, all_channel_videos):
        """Test handling of missing thumbnail path."""
        video_metadata["thumbnail_path"] = None

        result = detector.detect_duplicate(video_metadata, all_channel_videos)

        # Should handle gracefully (skip visual check)
        assert result["is_duplicate"] is False

    def test_corrupt_thumbnail_file(self, detector, video_metadata, all_channel_videos):
        """Test handling of corrupt thumbnail file."""
        # Create corrupt file
        Path(video_metadata["thumbnail_path"]).write_text("corrupt")

        try:
            result = detector.detect_duplicate(video_metadata, all_channel_videos)

            # Should handle error gracefully
            assert result["is_duplicate"] is False
        finally:
            Path(video_metadata["thumbnail_path"]).unlink(missing_ok=True)

    def test_empty_tags_list(self, detector, video_metadata, all_channel_videos):
        """Test metadata comparison with empty tags list."""
        video_metadata["tags"] = []
        all_channel_videos[0]["tags"] = []

        similarity = detector.compare_metadata(video_metadata, all_channel_videos[0])

        # Should handle empty tags gracefully
        assert similarity >= 0.0
