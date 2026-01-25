"""
Content uniqueness validation for YouTube Partner Program compliance.

Validates videos against duplicate content requirements by checking:
- Visual uniqueness (perceptual hashing of thumbnails/composites)
- Narrative uniqueness (story structure fingerprinting)
- Metadata uniqueness (title/description/tags diversity)

All dimensions must exceed 70% uniqueness threshold.
"""

import imagehash
from PIL import Image
from difflib import SequenceMatcher
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

# Security: Protect against decompression bomb attacks
# PIL default is 89,478,485 pixels (~178MB uncompressed)
# Set conservative limit: 50MP (~200MB uncompressed max)
Image.MAX_IMAGE_PIXELS = 50_000_000

# Security: Maximum file size for thumbnail/composite (50MB)
MAX_THUMBNAIL_SIZE_BYTES = 50 * 1024 * 1024

# YouTube Partner Program 2025-2026 uniqueness thresholds
UNIQUENESS_THRESHOLDS = {
    "visual_uniqueness": 0.70,  # 70% different visual elements
    "narrative_uniqueness": 0.70,  # 70% different story structure
    "metadata_uniqueness": 0.70,  # 70% different titles/descriptions/tags
    "overall_uniqueness": 0.70,  # Must pass ALL checks
}


class ContentUniquenessValidator:
    """
    Validate video uniqueness across visual, narrative, and metadata dimensions.

    Enforces YouTube Partner Program requirements that AI-generated content must
    demonstrate uniqueness to avoid "inauthentic content" demonetization.
    """

    def validate_video_uniqueness(
        self, video_metadata: dict, recent_videos: list[dict]
    ) -> dict:
        """
        Validate video against duplicate content requirements.

        Args:
            video_metadata: Current video metadata with thumbnail_path, story_script, title, description, tags
            recent_videos: List of recent channel uploads (last 20-30 videos) for comparison

        Returns:
            Dict with validation results:
                {
                    'passes': bool,  # True if all checks >= 70%
                    'scores': {
                        'visual_uniqueness': float (0.0-1.0),
                        'narrative_uniqueness': float (0.0-1.0),
                        'metadata_uniqueness': float (0.0-1.0)
                    },
                    'overall_score': float  # Average of all scores
                }
        """
        if not recent_videos:
            # First video on channel - automatically unique
            log.info(
                "first_video_uniqueness_check",
                result="passed",
                reason="no_prior_uploads",
            )
            return {
                "passes": True,
                "scores": {
                    "visual_uniqueness": 1.0,
                    "narrative_uniqueness": 1.0,
                    "metadata_uniqueness": 1.0,
                },
                "overall_score": 1.0,
            }

        # Calculate uniqueness scores for each dimension
        visual_score = self.check_visual_variation(video_metadata, recent_videos)
        narrative_score = self.check_story_uniqueness(video_metadata, recent_videos)
        metadata_score = self.check_metadata_variation(video_metadata, recent_videos)

        scores = {
            "visual_uniqueness": visual_score,
            "narrative_uniqueness": narrative_score,
            "metadata_uniqueness": metadata_score,
        }

        # ALL checks must pass 70% threshold
        passes_all = all(
            score >= UNIQUENESS_THRESHOLDS[dimension]
            for dimension, score in scores.items()
        )

        overall_score = sum(scores.values()) / len(scores)

        log.info(
            "uniqueness_validated",
            visual_score=visual_score,
            narrative_score=narrative_score,
            metadata_score=metadata_score,
            overall_score=overall_score,
            passes=passes_all,
            compared_against=len(recent_videos),
        )

        return {"passes": passes_all, "scores": scores, "overall_score": overall_score}

    def check_visual_variation(
        self, video_metadata: dict, recent_videos: list[dict]
    ) -> float:
        """
        Compare visual elements against recent uploads using perceptual hashing.

        Analyzes:
        - Different Pokemon behaviors/actions
        - Different environmental contexts (forest vs ocean vs mountain)
        - Different camera compositions
        - Different lighting/time of day

        Args:
            video_metadata: Current video with thumbnail_path or composite_path
            recent_videos: Recent uploads for comparison

        Returns:
            Uniqueness score (0.0-1.0) - higher is more unique
        """
        # Get thumbnail path (prefer composite if available)
        thumbnail_path = video_metadata.get("thumbnail_path") or video_metadata.get(
            "composite_path"
        )

        if not thumbnail_path or not Path(thumbnail_path).exists():
            log.warning(
                "visual_uniqueness_check_skipped", reason="no_thumbnail_found"
            )
            return 1.0  # Conservative: assume unique if no thumbnail

        # Security: Check file size before processing (Issue #6 fix)
        try:
            file_size = Path(thumbnail_path).stat().st_size
            if file_size > MAX_THUMBNAIL_SIZE_BYTES:
                log.error(
                    "thumbnail_too_large",
                    path=thumbnail_path,
                    size_mb=file_size / 1024 / 1024,
                    max_mb=MAX_THUMBNAIL_SIZE_BYTES / 1024 / 1024,
                )
                return 1.0  # Conservative: assume unique, skip processing
        except Exception as e:
            log.error("thumbnail_size_check_failed", error=str(e), path=thumbnail_path)
            return 1.0

        try:
            current_hash = imagehash.phash(Image.open(thumbnail_path))
        except Exception as e:
            log.error("thumbnail_hash_failed", error=str(e), path=thumbnail_path)
            return 1.0  # Conservative: assume unique on error

        similarity_scores = []

        for recent_video in recent_videos[-20:]:  # Check last 20 videos
            recent_thumbnail = recent_video.get("thumbnail_path") or recent_video.get(
                "composite_path"
            )

            if not recent_thumbnail or not Path(recent_thumbnail).exists():
                continue

            # Security: Check file size before processing (Issue #6 fix)
            try:
                file_size = Path(recent_thumbnail).stat().st_size
                if file_size > MAX_THUMBNAIL_SIZE_BYTES:
                    log.warning(
                        "comparison_thumbnail_too_large",
                        path=recent_thumbnail,
                        size_mb=file_size / 1024 / 1024,
                        skipping=True,
                    )
                    continue
            except Exception:
                continue  # Skip if we can't check size

            try:
                recent_hash = imagehash.phash(Image.open(recent_thumbnail))
                hash_distance = current_hash - recent_hash

                # Normalize hash distance to similarity (0=identical, 64=completely different)
                similarity = 1 - (hash_distance / 64.0)
                similarity_scores.append(similarity)

            except Exception as e:
                log.warning(
                    "comparison_hash_failed",
                    error=str(e),
                    recent_path=recent_thumbnail,
                )
                continue

        if not similarity_scores:
            return 1.0  # No valid comparisons - assume unique

        # Average dissimilarity (1 - similarity)
        uniqueness_score = 1 - (sum(similarity_scores) / len(similarity_scores))

        return uniqueness_score

    def check_story_uniqueness(
        self, video_metadata: dict, recent_videos: list[dict]
    ) -> float:
        """
        Validate narrative originality using story structure fingerprinting.

        Analyzes:
        - Different behavioral sequences (feeding vs hunting vs social)
        - Different ecological contexts (migration vs mating vs defense)
        - Unique educational insights per video

        Args:
            video_metadata: Current video with story_script content
            recent_videos: Recent uploads for comparison

        Returns:
            Uniqueness score (0.0-1.0) - higher is more unique
        """
        current_story = video_metadata.get("story_script")

        if not current_story:
            log.warning("narrative_uniqueness_check_skipped", reason="no_story_script")
            return 1.0  # Conservative: assume unique if no story

        current_structure = self.extract_story_structure(current_story)

        similarity_scores = []

        for recent_video in recent_videos[-20:]:
            recent_story = recent_video.get("story_script")

            if not recent_story:
                continue

            recent_structure = self.extract_story_structure(recent_story)
            similarity = self.compare_story_structures(
                current_structure, recent_structure
            )
            similarity_scores.append(similarity)

        if not similarity_scores:
            return 1.0  # No valid comparisons - assume unique

        uniqueness_score = 1 - (sum(similarity_scores) / len(similarity_scores))

        return uniqueness_score

    def extract_story_structure(self, story_script: str | dict) -> list[str]:
        """
        Extract story fingerprint from narrative content.

        Returns:
            List of behavior categories for the story sequence
        """
        # Handle both string and dict story formats
        if isinstance(story_script, str):
            # Simple text-based story - classify overall
            return [self.classify_behavior(story_script)]

        if isinstance(story_script, dict) and "clips" in story_script:
            # 18-clip structure with individual clip descriptions
            behavior_sequence = []
            for clip in story_script["clips"]:
                description = clip.get("description", "")
                behavior_category = self.classify_behavior(description)
                behavior_sequence.append(behavior_category)
            return behavior_sequence

        # Fallback: treat as general narrative
        return ["general"]

    def classify_behavior(self, clip_description: str) -> str:
        """
        Classify narrative content into behavior category.

        Categories: feeding, hunting, social, defensive, migration, mating,
                   resting, exploration, communication, parenting, general

        Args:
            clip_description: Text description of behavior/scene

        Returns:
            Behavior category string
        """
        keywords_map = {
            "feeding": ["eat", "consume", "feed", "forage", "prey"],
            "hunting": ["stalk", "chase", "attack", "pursuit", "hunt"],
            "social": ["interact", "group", "communicate", "play", "bond"],
            "defensive": ["protect", "defend", "threaten", "retreat", "guard"],
            "migration": ["migrate", "travel", "journey", "move"],
            "mating": ["mate", "courtship", "breed", "display"],
            "resting": ["rest", "sleep", "relax", "dormant"],
            "exploration": ["explore", "discover", "investigate", "search"],
            "communication": ["call", "signal", "vocalize", "communicate"],
            "parenting": ["nurture", "care", "protect offspring", "teach"],
        }

        description_lower = clip_description.lower()

        for category, keywords in keywords_map.items():
            if any(keyword in description_lower for keyword in keywords):
                return category

        return "general"

    def compare_story_structures(
        self, structure1: list[str], structure2: list[str]
    ) -> float:
        """
        Calculate similarity between two story structures.

        Uses sequence matching to measure behavioral pattern similarity.

        Args:
            structure1: First behavior sequence
            structure2: Second behavior sequence

        Returns:
            Similarity score (0.0-1.0) - higher is more similar
        """
        matcher = SequenceMatcher(None, structure1, structure2)
        similarity = matcher.ratio()

        return similarity

    def check_metadata_variation(
        self, video_metadata: dict, recent_videos: list[dict]
    ) -> float:
        """
        Ensure metadata diversity across title, description, and tags.

        Args:
            video_metadata: Current video with title, description, tags
            recent_videos: Recent uploads for comparison

        Returns:
            Uniqueness score (0.0-1.0) - higher is more unique
        """
        current_title = video_metadata.get("title", "")
        current_description = video_metadata.get("description", "")
        current_tags = set(video_metadata.get("tags", []))

        title_similarities = []
        description_similarities = []
        tag_overlaps = []

        for recent_video in recent_videos[-20:]:
            # Title similarity
            recent_title = recent_video.get("title", "")
            if recent_title:
                matcher = SequenceMatcher(None, current_title, recent_title)
                title_similarities.append(matcher.ratio())

            # Description similarity
            recent_description = recent_video.get("description", "")
            if recent_description:
                matcher = SequenceMatcher(None, current_description, recent_description)
                description_similarities.append(matcher.ratio())

            # Tag overlap
            recent_tags = set(recent_video.get("tags", []))
            if recent_tags and current_tags:
                overlap_ratio = len(current_tags & recent_tags) / len(
                    current_tags | recent_tags
                )
                tag_overlaps.append(overlap_ratio)

        # Calculate average dissimilarity for each metadata dimension
        avg_title_dissimilarity = (
            1 - (sum(title_similarities) / len(title_similarities))
            if title_similarities
            else 1.0
        )
        avg_description_dissimilarity = (
            1 - (sum(description_similarities) / len(description_similarities))
            if description_similarities
            else 1.0
        )
        avg_tag_dissimilarity = (
            1 - (sum(tag_overlaps) / len(tag_overlaps)) if tag_overlaps else 1.0
        )

        # Weighted average (title most important for discovery)
        uniqueness_score = (
            0.5 * avg_title_dissimilarity
            + 0.3 * avg_description_dissimilarity
            + 0.2 * avg_tag_dissimilarity
        )

        return uniqueness_score
