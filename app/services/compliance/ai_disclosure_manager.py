"""AI disclosure automation for YouTube Partner Program compliance.

Sets mandatory AI disclosure labels via YouTube Data API v3:
- hasAlteredContent=true (MANDATORY as of May 21, 2025)
- Belt-and-suspenders text disclosure in video description
- Validation that disclosure was successfully set

Failure to disclose AI content results in demonetization.
"""

from typing import Any

import structlog

log = structlog.get_logger(__name__)


class AIDisclosureManager:
    """Manage AI disclosure labels for YouTube uploads.

    YouTube's May 2025 mandate requires ALL synthetic/altered content to be labeled:
    - Synthetic voices (ElevenLabs narration)
    - AI-generated visuals (Gemini images)
    - AI-animated scenes (Kling videos)
    """

    def set_ai_disclosure(self, video_id: str, youtube_service: Any) -> None:
        """Set AI disclosure via YouTube Data API v3.

        MUST be called after video upload, before video goes public.

        Args:
            video_id: YouTube video ID
            youtube_service: Authenticated YouTube API service object
                (from google-api-python-client)

        Raises:
            Exception: If YouTube API call fails
        """
        video_metadata = {
            "id": video_id,
            "contentDetails": {
                "hasCustomThumbnail": True,  # We upload custom thumbnails
                "hasAlteredContent": True,  # CRITICAL: Marks video as AI-generated
            },
        }

        try:
            # Update video via YouTube Data API
            youtube_service.videos().update(part="contentDetails", body=video_metadata).execute()

            log.info(
                "ai_disclosure_set",
                video_id=video_id,
                disclosure_type="SYNTHETIC_MEDIA",
                status="success",
            )

        except Exception as e:
            log.error(
                "ai_disclosure_failed",
                video_id=video_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def add_disclosure_to_description(self, description: str) -> str:
        """Add text disclosure to video description (belt-and-suspenders approach).

        Adds disclosure section at the beginning of description for maximum visibility.

        Args:
            description: Original video description

        Returns:
            Updated description with AI disclosure prepended
        """
        disclosure_text = (
            "🤖 AI DISCLOSURE:\n"
            "This documentary was created using AI tools:\n"
            "- Imagery: Google Gemini AI\n"
            "- Animation: Kling AI Video Generator\n"
            "- Narration: ElevenLabs AI Voice Synthesis\n"
            "- Script & Editing: Human-directed creative process\n\n"
        )

        # Check if disclosure already present (avoid duplicates)
        if "🤖 AI DISCLOSURE" in description:
            log.debug("disclosure_already_present", skipping_add=True)
            return description

        updated_description = disclosure_text + description

        log.debug(
            "disclosure_added_to_description",
            original_length=len(description),
            new_length=len(updated_description),
        )

        return updated_description

    def validate_disclosure_set(self, video_id: str, youtube_service: Any) -> bool:
        """Verify AI disclosure was successfully set on YouTube.

        Args:
            video_id: YouTube video ID
            youtube_service: Authenticated YouTube API service object

        Returns:
            True if disclosure successfully set

        Raises:
            ValueError: If disclosure not set (upload blocked to prevent policy violation)
        """
        try:
            # Fetch video metadata to verify disclosure
            video = youtube_service.videos().list(part="contentDetails", id=video_id).execute()

            if not video.get("items"):
                raise ValueError(f"Video {video_id} not found in YouTube API response")

            content_details = video["items"][0].get("contentDetails", {})
            has_altered_content = content_details.get("hasAlteredContent", False)

            if not has_altered_content:
                log.error(
                    "ai_disclosure_validation_failed",
                    video_id=video_id,
                    has_altered_content=has_altered_content,
                )

                raise ValueError(
                    f"AI disclosure not set for video {video_id}. "
                    f"Upload blocked to prevent policy violation."
                )

            log.info(
                "ai_disclosure_validated",
                video_id=video_id,
                has_altered_content=has_altered_content,
                validation_status="passed",
            )

            return True

        except Exception as e:
            log.error(
                "ai_disclosure_validation_error",
                video_id=video_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise
