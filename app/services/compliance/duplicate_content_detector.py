"""
Duplicate content detection for YouTube Partner Program compliance.

Detects if a video is a duplicate of existing channel content using:
- Perceptual hashing of thumbnails (visual similarity)
- Story structure fingerprinting (narrative similarity)
- Metadata similarity scoring (title/description matching)

Videos with >90% similarity across all dimensions are blocked as duplicates.
"""

import imagehash
from PIL import Image
from difflib import SequenceMatcher
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

# Duplicate detection thresholds
DUPLICATE_HASH_DISTANCE = 5  # Hash distance < 5 indicates near-identical images
DUPLICATE_SIMILARITY_THRESHOLD = 0.90  # >90% similarity = duplicate


class DuplicateContentDetector:
    """
    Detect duplicate or near-duplicate videos to prevent upload failures.

    YouTube's "inauthentic content" policy (July 2025) blocks uploads that are
    duplicates or near-duplicates of existing channel content.
    """

    def detect_duplicate(
        self, video_metadata: dict, all_channel_videos: list[dict]
    ) -> dict:
        """
        Detect if video is duplicate of existing content.

        Args:
            video_metadata: Current video metadata with thumbnail_path, story_script, title, description
            all_channel_videos: ALL videos on channel for duplicate checking

        Returns:
            Dict with detection results:
                {
                    'is_duplicate': bool,
                    'duplicate_of': video_id or None,
                    'similarity_score': float (0-1),
                    'duplicate_type': str ('visual' | 'narrative' | 'metadata' | 'combined')
                }
        """
        if not all_channel_videos:
            # First video on channel - cannot be duplicate
            log.info(
                "duplicate_check_passed", reason="no_prior_uploads", is_first_video=True
            )
            return {
                "is_duplicate": False,
                "duplicate_of": None,
                "similarity_score": 0.0,
                "duplicate_type": None,
            }

        # Check perceptual hash of thumbnail (visual similarity)
        thumbnail_path = video_metadata.get("thumbnail_path") or video_metadata.get(
            "composite_path"
        )

        if not thumbnail_path or not Path(thumbnail_path).exists():
            log.warning("duplicate_check_skipped", reason="no_thumbnail_found")
            # Conservative: cannot check duplicates without thumbnail
            return {
                "is_duplicate": False,
                "duplicate_of": None,
                "similarity_score": 0.0,
                "duplicate_type": None,
            }

        try:
            current_hash = imagehash.phash(Image.open(thumbnail_path))
        except Exception as e:
            log.error("thumbnail_hash_failed", error=str(e), path=thumbnail_path)
            return {
                "is_duplicate": False,
                "duplicate_of": None,
                "similarity_score": 0.0,
                "duplicate_type": None,
            }

        # Check each existing video for duplicate match
        for existing_video in all_channel_videos:
            existing_thumbnail = existing_video.get(
                "thumbnail_path"
            ) or existing_video.get("composite_path")

            if not existing_thumbnail or not Path(existing_thumbnail).exists():
                continue

            try:
                existing_hash = imagehash.phash(Image.open(existing_thumbnail))
                hash_distance = current_hash - existing_hash

                # Hash distance < 5 indicates near-identical images
                if hash_distance < DUPLICATE_HASH_DISTANCE:
                    # Visual similarity detected - check story and metadata
                    story_similarity = self.compare_stories(
                        video_metadata, existing_video
                    )
                    metadata_similarity = self.compare_metadata(
                        video_metadata, existing_video
                    )

                    visual_similarity = 1 - (hash_distance / 64.0)
                    combined_similarity = (
                        visual_similarity + story_similarity + metadata_similarity
                    ) / 3

                    # If visual + story + metadata all >90% similar → DUPLICATE
                    if (
                        story_similarity > DUPLICATE_SIMILARITY_THRESHOLD
                        and metadata_similarity > DUPLICATE_SIMILARITY_THRESHOLD
                    ):
                        log.warning(
                            "duplicate_content_detected",
                            duplicate_of=existing_video.get("id"),
                            visual_similarity=visual_similarity,
                            story_similarity=story_similarity,
                            metadata_similarity=metadata_similarity,
                            combined_similarity=combined_similarity,
                        )

                        return {
                            "is_duplicate": True,
                            "duplicate_of": existing_video.get("id"),
                            "similarity_score": combined_similarity,
                            "duplicate_type": "combined",
                        }

            except Exception as e:
                log.warning(
                    "comparison_hash_failed",
                    error=str(e),
                    existing_video_id=existing_video.get("id"),
                )
                continue

        # No duplicate detected
        log.info("duplicate_check_passed", videos_checked=len(all_channel_videos))

        return {
            "is_duplicate": False,
            "duplicate_of": None,
            "similarity_score": 0.0,
            "duplicate_type": None,
        }

    def compare_stories(
        self, video_metadata: dict, existing_video: dict
    ) -> float:
        """
        Compare story structure between two videos.

        Args:
            video_metadata: Current video story_script
            existing_video: Existing video story_script

        Returns:
            Similarity score (0.0-1.0) - higher is more similar
        """
        current_story = video_metadata.get("story_script")
        existing_story = existing_video.get("story_script")

        if not current_story or not existing_story:
            return 0.0  # No story comparison possible

        # Convert to strings for comparison
        current_str = str(current_story)
        existing_str = str(existing_story)

        matcher = SequenceMatcher(None, current_str, existing_str)
        return matcher.ratio()

    def compare_metadata(
        self, video_metadata: dict, existing_video: dict
    ) -> float:
        """
        Compare metadata (title, description, tags) between two videos.

        Args:
            video_metadata: Current video metadata
            existing_video: Existing video metadata

        Returns:
            Similarity score (0.0-1.0) - higher is more similar
        """
        # Compare titles
        current_title = video_metadata.get("title", "")
        existing_title = existing_video.get("title", "")

        title_similarity = 0.0
        if current_title and existing_title:
            matcher = SequenceMatcher(None, current_title, existing_title)
            title_similarity = matcher.ratio()

        # Compare descriptions
        current_description = video_metadata.get("description", "")
        existing_description = existing_video.get("description", "")

        description_similarity = 0.0
        if current_description and existing_description:
            matcher = SequenceMatcher(None, current_description, existing_description)
            description_similarity = matcher.ratio()

        # Compare tags (Jaccard similarity)
        current_tags = set(video_metadata.get("tags", []))
        existing_tags = set(existing_video.get("tags", []))

        tag_similarity = 0.0
        if current_tags and existing_tags:
            intersection = len(current_tags & existing_tags)
            union = len(current_tags | existing_tags)
            tag_similarity = intersection / union if union > 0 else 0.0

        # Weighted average (title most important)
        metadata_similarity = (
            0.5 * title_similarity + 0.3 * description_similarity + 0.2 * tag_similarity
        )

        return metadata_similarity
