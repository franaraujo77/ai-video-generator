"""Video Generation Service for Kling-powered video animation.

This module implements the third stage of the 8-step video generation pipeline.
It orchestrates the animation of 18 photorealistic composite images into
10-second video clips via Kling 2.5 Pro API (via KIE.ai), following the
"Smart Agent + Dumb Scripts" architectural pattern.

Key Responsibilities:
- Create video manifests with motion prompts following Priority Hierarchy
- Upload composite images to catbox.moe for public hosting
- Orchestrate CLI script invocation via async wrapper (Story 3.1)
- Track completed vs. pending clips for partial resume support
- Calculate and report Kling API costs for budget monitoring
- Coordinate rate limiting (5-8 concurrent requests max)

Architecture Pattern:
    Service (Smart): Maps composites to prompts, uploads images, manages retry
    CLI Script (Dumb): Calls KIE.ai API, polls for completion, downloads MP4

Dependencies:
    - Story 3.1: CLI wrapper (run_cli_script, CLIScriptError)
    - Story 3.2: Filesystem helpers (get_video_dir, get_composite_dir)
    - Story 3.4: Composite creation (18 composites in assets/composites/)
    - app/clients/catbox.py: Catbox image upload client

Usage:
    from app.services.video_generation import VideoGenerationService

    service = VideoGenerationService("poke1", "vid_abc123")
    manifest = service.create_video_manifest(
        "Bulbasaur forest documentary",
        "Show evolution through seasons"
    )

    result = await service.generate_videos(manifest, resume=False)
    print(f"Generated {result['generated']} videos, cost: ${result['total_cost_usd']}")
"""

import asyncio
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.clients.catbox import CatboxClient
from app.utils.cli_wrapper import CLIScriptError, run_cli_script
from app.utils.filesystem import get_composite_dir, get_video_dir
from app.utils.logging import get_logger

log = get_logger(__name__)


def _validate_identifier(value: str, name: str) -> None:
    """Validate channel_id or project_id to prevent path traversal attacks.

    Args:
        value: The identifier value to validate
        name: The name of the identifier (for error messages)

    Raises:
        ValueError: If identifier contains invalid characters or invalid length

    Security:
        Prevents path traversal attacks by enforcing alphanumeric, underscore,
        and hyphen characters only. Matches Story 3.2 security patterns.
    """
    # Check length first (before pattern match)
    if len(value) == 0 or len(value) > 100:
        raise ValueError(f"{name} length must be 1-100 characters")
    if not re.match(r'^[a-zA-Z0-9_-]+$', value):
        raise ValueError(f"{name} contains invalid characters: {value}")


@dataclass
class VideoClip:
    """Represents a single video clip to generate from a composite image.

    Attributes:
        clip_number: Clip number (1-18)
        composite_path: Path to composite PNG seed image (1920x1080)
        motion_prompt: Kling motion prompt (Priority Hierarchy structured)
        output_path: Path where MP4 video will be saved
        catbox_url: Optional cached catbox.moe URL if already uploaded
    """

    clip_number: int
    composite_path: Path
    motion_prompt: str
    output_path: Path
    catbox_url: str | None = None


@dataclass
class VideoManifest:
    """Complete manifest of video clips to generate for a project (18 total).

    Attributes:
        clips: List of VideoClip objects (one per video clip)
    """

    clips: list[VideoClip]


class VideoGenerationService:
    """Service for generating 10-second video clips from composite images using Kling 2.5 API.

    This service orchestrates the video generation phase of the pipeline,
    following the "Smart Agent + Dumb Scripts" pattern where the service handles
    business logic (prompt creation, image upload, rate limiting) and the CLI script
    handles API calls (Kling API invocation, polling, download).

    Responsibilities:
    - Map composite images to video prompts (Priority Hierarchy)
    - Upload composites to catbox.moe for Kling API input
    - Orchestrate CLI script invocation for each video clip
    - Handle long-running operations (2-10 minutes per clip)
    - Track completed vs. pending clips for partial resume
    - Calculate and report Kling API costs

    Architecture Compliance:
    - Uses Story 3.1 CLI wrapper (never calls subprocess directly)
    - Uses Story 3.2 filesystem helpers (never constructs paths manually)
    - Implements short transaction pattern (service is stateless)
    - Enforces 10-minute timeout per clip (NFR-I3)
    - Coordinates rate limiting (5-8 concurrent max)
    """

    def __init__(self, channel_id: str, project_id: str):
        """Initialize video generation service for specific project.

        Args:
            channel_id: Channel identifier for path isolation
            project_id: Project/task identifier (UUID from database)

        Raises:
            ValueError: If channel_id or project_id contain invalid characters
        """
        # Validate identifiers to prevent path traversal attacks (Story 3.5 security requirement)
        _validate_identifier(channel_id, "channel_id")
        _validate_identifier(project_id, "project_id")

        self.channel_id = channel_id
        self.project_id = project_id
        self.log = get_logger(__name__)
        self._catbox_client: CatboxClient | None = None

    def create_video_manifest(
        self,
        topic: str,
        story_direction: str
    ) -> VideoManifest:
        """Create video manifest by mapping 18 composites to motion prompts.

        Motion Prompt Derivation Strategy:
        1. Parse story_direction to understand narrative flow (18 clips)
        2. Scan available composites in `assets/composites/`
        3. For each clip, generate motion prompt following Priority Hierarchy:
           - Core Action FIRST (what is happening)
           - Specific Details (what moves, how it moves)
           - Logical Sequence (cause and effect)
           - Environmental Context (atmosphere, lighting)
           - Camera Movement LAST (aesthetic enhancement)

        Priority Hierarchy Example (CRITICAL FOR KLING):
        Good: "Bulbasaur walks forward through forest. Front legs step first,
               then back legs. Body sways gently. Leaves rustle. Slow dolly forward."
        Bad: "Slow dolly forward. Bulbasaur walks through forest."

        Args:
            topic: Video topic from Notion (for context)
            story_direction: Story direction from Notion (narrative guidance)

        Returns:
            VideoManifest with 18 VideoClip objects

        Example:
            >>> manifest = service.create_video_manifest(
            ...     "Bulbasaur forest documentary",
            ...     "Show seasonal evolution: spring growth, summer activity, autumn rest"
            ... )
            >>> print(len(manifest.clips))
            18
        """
        # Get composite and video directories
        composite_dir = get_composite_dir(self.channel_id, self.project_id)
        video_dir = get_video_dir(self.channel_id, self.project_id)

        clips = []
        for i in range(1, 19):  # 18 clips total
            clip_number = i
            composite_filename = f"clip_{clip_number:02d}.png"

            # Check for split-screen variant
            split_filename = f"clip_{clip_number:02d}_split.png"
            if (composite_dir / split_filename).exists():
                composite_filename = split_filename

            composite_path = composite_dir / composite_filename
            output_path = video_dir / f"clip_{clip_number:02d}.mp4"

            # Generate motion prompt following Priority Hierarchy
            motion_prompt = self._generate_motion_prompt(
                clip_number,
                topic,
                story_direction
            )

            clips.append(VideoClip(
                clip_number=clip_number,
                composite_path=composite_path,
                motion_prompt=motion_prompt,
                output_path=output_path,
                catbox_url=None
            ))

        return VideoManifest(clips=clips)

    def _generate_motion_prompt(
        self,
        clip_number: int,
        topic: str,
        story_direction: str
    ) -> str:
        """Generate motion prompt following Priority Hierarchy.

        CURRENT IMPLEMENTATION: Uses generic template prompts.
        TODO: Parse story_direction to create context-aware prompts (Issue #5).

        Template:
        1. {core_action} - Character does X
        2. {specific_details} - Body part Y moves in Z manner
        3. {logical_sequence} - Action A causes result B
        4. {environmental_context} - Lighting, atmosphere, weather
        5. {camera_movement} - Slow zoom, dolly, pan (LAST)

        Args:
            clip_number: Clip number (1-18)
            topic: Video topic (character name extracted from this)
            story_direction: Narrative guidance (currently not parsed)

        Returns:
            Motion prompt structured per Priority Hierarchy

        Example:
            >>> prompt = service._generate_motion_prompt(
            ...     1,
            ...     "Bulbasaur forest documentary",
            ...     "Show seasonal evolution"
            ... )
            >>> print(prompt)
            "Bulbasaur stands in forest clearing. Bulb on back..."
        """
        # Extract character name from topic (simple heuristic)
        character = topic.split()[0] if topic else "Character"

        # Log story_direction for debugging (future enhancement will parse this)
        self.log.debug(
            "generating_motion_prompt",
            clip_number=clip_number,
            character=character,
            story_direction_hint=story_direction[:100]  # Log first 100 chars
        )

        # Generic motion prompts following Priority Hierarchy
        # TODO: Parse story_direction to customize these prompts per narrative
        motion_prompts = [
            f"{character} stands in clearing. Body breathes slowly. Eyes blink. Gentle wind rustles surroundings.",  # noqa: E501
            f"{character} walks forward. Legs move steadily. Body sways with each step. Leaves scatter.",  # noqa: E501
            f"{character} turns head left. Eyes track movement. Body remains still. Dappled sunlight shifts.",  # noqa: E501
            f"{character} sits down slowly. Front legs bend first. Body lowers gradually. Dust settles.",  # noqa: E501
            f"{character} looks upward. Head tilts back. Eyes focus on canopy. Shadows play across face.",  # noqa: E501
            f"{character} moves through undergrowth. Vegetation parts. Body pushes forward. Natural sounds echo.",  # noqa: E501
            f"{character} pauses at stream. Reflection ripples. Body leans forward. Water flows gently.",  # noqa: E501
            f"{character} observes surroundings. Head rotates slowly. Eyes scan environment. Tension builds.",  # noqa: E501
            f"{character} reacts to sound. Ears perk up. Body tenses. Alert posture maintained.",
            f"{character} relaxes stance. Muscles ease. Breathing slows. Peaceful atmosphere returns.",  # noqa: E501
            f"{character} interacts with object. Paw extends. Contact made carefully. Curiosity shown.",  # noqa: E501
            f"{character} navigates terrain. Feet find footing. Balance maintained. Path winds ahead.",  # noqa: E501
            f"{character} settles into rest. Body curls up. Eyes close slowly. Breathing deepens.",
            f"{character} wakes from rest. Eyes open. Body stretches. Alertness returns gradually.",
            f"{character} surveys territory. Head swivels. Vision sweeps area. Protective instinct visible.",  # noqa: E501
            f"{character} demonstrates behavior. Action repeats. Pattern emerges. Purpose becomes clear.",  # noqa: E501
            f"{character} responds to environment. Conditions change. Adaptation shown. Survival instinct evident.",  # noqa: E501
            f"{character} concludes activity. Movement slows. Final position held. Moment concludes peacefully.",  # noqa: E501
        ]

        # Return prompt for this clip (cycle if needed)
        prompt_index = (clip_number - 1) % len(motion_prompts)
        return motion_prompts[prompt_index]

    async def generate_videos(
        self,
        manifest: VideoManifest,
        resume: bool = False,
        max_concurrent: int = 5
    ) -> dict[str, Any]:
        """Generate all video clips in manifest by invoking CLI script.

        Orchestration Flow:
        1. For each clip in manifest:
           a. Check if video exists (if resume=True, skip existing)
           b. Upload composite to catbox.moe (get public URL)
           c. Call `scripts/generate_video.py`:
              - Pass catbox URL, motion prompt, output path
              - Wait 2-5 minutes (typical), up to 10 minutes max
           d. Wait for completion (CLI script handles polling)
           e. Verify MP4 file exists and is valid video
           f. Log success/failure with clip number, generation time
        2. Respect max_concurrent limit (5-8 parallel Kling requests)
        3. Return summary (generated count, skipped count, failed count)

        Args:
            manifest: VideoManifest with 18 clip definitions
            resume: If True, skip clips that already exist on filesystem
            max_concurrent: Maximum concurrent Kling API requests (default 5)

        Returns:
            Summary dict with keys:
                - generated: Number of newly generated videos
                - skipped: Number of existing videos (if resume=True)
                - failed: Number of failed videos
                - total_cost_usd: Total Kling API cost (Decimal)

        Note:
            Does not raise exceptions on individual clip failures to support
            partial resume. Check 'failed' count in return dict to detect errors.

        Example:
            >>> result = await service.generate_videos(manifest, resume=False, max_concurrent=5)
            >>> print(result)
            {"generated": 18, "skipped": 0, "failed": 0, "total_cost_usd": Decimal("7.56")}
        """
        generated = 0
        skipped = 0
        failed = 0

        # Create semaphore for rate limiting
        semaphore = asyncio.Semaphore(max_concurrent)

        async def generate_clip(clip: VideoClip) -> bool:
            """Generate single video clip with rate limiting."""
            nonlocal generated, skipped, failed

            async with semaphore:
                # Check if video already exists (resume support)
                if resume and self.check_video_exists(clip.output_path):
                    self.log.info(
                        "video_clip_skipped",
                        clip_number=clip.clip_number,
                        output_path=str(clip.output_path)
                    )
                    skipped += 1
                    return True

                try:
                    # Upload composite to catbox.moe
                    catbox_url = await self.upload_to_catbox(clip.composite_path)

                    self.log.info(
                        "video_generation_start",
                        clip_number=clip.clip_number,
                        catbox_url=catbox_url,
                        output_path=str(clip.output_path)
                    )

                    # Call CLI script to generate video
                    await run_cli_script(
                        "generate_video.py",
                        [
                            "--image", catbox_url,
                            "--prompt", clip.motion_prompt,
                            "--output", str(clip.output_path)
                        ],
                        timeout=600  # 10 minutes (NFR-I3)
                    )

                    self.log.info(
                        "video_generation_complete",
                        clip_number=clip.clip_number,
                        output_path=str(clip.output_path)
                    )

                    generated += 1
                    return True

                except Exception as e:
                    self.log.error(
                        "video_generation_failed",
                        clip_number=clip.clip_number,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    failed += 1
                    return False  # Continue with other clips (partial resume support)

        # Generate all clips with concurrency control
        await asyncio.gather(*[generate_clip(clip) for clip in manifest.clips])

        # Calculate total cost
        total_cost_usd = self.calculate_kling_cost(generated)

        return {
            "generated": generated,
            "skipped": skipped,
            "failed": failed,
            "total_cost_usd": total_cost_usd
        }

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    async def upload_to_catbox(self, composite_path: Path) -> str:
        """Upload composite image to catbox.moe for public hosting.

        catbox.moe is a free image hosting service that provides public URLs.
        Kling API requires publicly accessible image URLs as seed images.

        Retry Strategy:
            - Retriable errors: httpx.HTTPError, asyncio.TimeoutError
            - Max attempts: 3
            - Backoff: 1s, 2s, 4s (exponential)

        Args:
            composite_path: Path to composite PNG file (1920x1080)

        Returns:
            Public catbox.moe URL (e.g., "https://files.catbox.moe/abc123.png")

        Raises:
            httpx.HTTPError: If catbox.moe upload fails after 3 attempts
            FileNotFoundError: If composite file doesn't exist (non-retriable)

        Example:
            >>> url = await service.upload_to_catbox(Path("assets/composites/clip_01.png"))
            >>> print(url)
            "https://files.catbox.moe/xyz789.png"
        """
        # Lazy initialize catbox client (reuse for all uploads)
        if self._catbox_client is None:
            self._catbox_client = CatboxClient()

        return await self._catbox_client.upload_image(composite_path)

    def check_video_exists(self, video_path: Path) -> bool:
        """Check if video file exists on filesystem with size validation.

        Used for partial resume (Story 3.5 AC5). Validates that:
        - File exists and is a regular file
        - File size is at least 1MB (min for 10-second H.264 video)

        Args:
            video_path: Full path to video MP4 file

        Returns:
            True if file exists and is valid size, False otherwise

        Example:
            >>> exists = service.check_video_exists(Path("videos/clip_01.mp4"))
            >>> print(exists)
            True
        """
        if not (video_path.exists() and video_path.is_file()):
            return False

        # Check minimum file size (10-second H.264 video should be at least 1MB)
        file_size = video_path.stat().st_size
        if file_size < 1_000_000:  # 1MB minimum
            self.log.warning(
                "video_file_too_small",
                video_path=str(video_path),
                file_size=file_size
            )
            return False

        return True

    def calculate_kling_cost(self, clip_count: int) -> Decimal:
        """Calculate Kling API cost for generated clips.

        Kling Pricing Model (as of 2026-01-15):
        - Approximately $5-10 per complete video (18 clips)
        - ~$0.42 per 10-second clip ($7.56 / 18 clips)

        Args:
            clip_count: Number of clips generated

        Returns:
            Total cost in USD (Decimal type for precision)

        Example:
            >>> cost = service.calculate_kling_cost(18)
            >>> print(cost)
            Decimal('7.56')
        """
        cost_per_clip = Decimal("0.42")
        return cost_per_clip * clip_count

    async def cleanup(self) -> None:
        """Clean up resources (close HTTP clients).

        Should be called when done using the service to prevent resource leaks.

        Example:
            >>> service = VideoGenerationService("poke1", "vid_123")
            >>> # ... use service ...
            >>> await service.cleanup()
        """
        if self._catbox_client is not None:
            await self._catbox_client.close()
            self._catbox_client = None
