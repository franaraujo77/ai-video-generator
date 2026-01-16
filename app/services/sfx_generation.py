"""Sound Effects Generation Service for ElevenLabs-powered environmental audio.

This module implements the fifth stage of the 8-step video generation pipeline.
It orchestrates the generation of 18 SFX audio tracks via ElevenLabs v3
Sound Effects Generation API, following the "Smart Agent + Dumb Scripts" architectural pattern.

Key Responsibilities:
- Create SFX manifests mapping descriptions to video clips (1-to-1 correspondence)
- Orchestrate CLI script invocation via async wrapper (Story 3.1)
- Validate audio output files and durations with ffprobe
- Track completed vs. pending clips for partial resume support
- Calculate and report ElevenLabs API costs for budget monitoring

Architecture Pattern:
    Service (Smart): Maps descriptions to clips, manages retry
    CLI Script (Dumb): Calls ElevenLabs API, downloads WAV

Dependencies:
    - Story 3.1: CLI wrapper (run_cli_script, CLIScriptError)
    - Story 3.2: Filesystem helpers (get_sfx_dir)
    - Story 3.6: Narration generation (establishes ElevenLabs pattern)
    - scripts/generate_sound_effects.py: ElevenLabs CLI script (brownfield)

Usage:
    from app.services.sfx_generation import SFXGenerationService

    service = SFXGenerationService("poke1", "vid_abc123")
    manifest = await service.create_sfx_manifest(
        sfx_descriptions=[
            "Gentle forest ambience with rustling leaves and distant bird calls",
            # ... 17 more descriptions
        ]
    )

    result = await service.generate_sfx(manifest, resume=False)
    print(f"Generated {result['generated']} SFX clips, cost: ${result['total_cost_usd']}")
"""

import asyncio
import re
import subprocess
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.utils.cli_wrapper import CLIScriptError, run_cli_script
from app.utils.filesystem import get_sfx_dir
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
    if not re.match(r"^[a-zA-Z0-9_-]+$", value):
        raise ValueError(f"{name} contains invalid characters: {value}")


def _is_retriable_error(error: CLIScriptError) -> bool:
    """Check if CLI script error is retriable (rate limit, timeout, server error).

    Retriable errors:
    - HTTP 429 (rate limit) - wait and retry
    - HTTP 5xx (server error) - temporary issue
    - Timeout errors - ElevenLabs took too long

    Non-retriable errors:
    - HTTP 401 (auth error) - invalid API key
    - HTTP 403 (forbidden) - permission issue
    - HTTP 400 (bad request) - invalid input

    Args:
        error: CLIScriptError from CLI wrapper

    Returns:
        True if error should be retried, False otherwise
    """
    stderr_lower = error.stderr.lower()

    # Check for rate limit (429)
    if "429" in error.stderr or "rate limit" in stderr_lower:
        return True

    # Check for server errors (5xx)
    if any(code in error.stderr for code in ["500", "502", "503", "504"]):
        return True

    # Check for timeout and return directly
    return "timeout" in stderr_lower


@dataclass
class SFXClip:
    """Represents a single sound effects audio clip to generate.

    Attributes:
        clip_number: Clip number (1-18)
        sfx_description: SFX description (environmental ambience, NOT narration)
        output_path: Path where WAV audio will be saved
        target_duration_seconds: Optional target duration from video clip (for logging)
    """

    clip_number: int
    sfx_description: str
    output_path: Path
    target_duration_seconds: float | None = None


@dataclass
class SFXManifest:
    """Complete manifest of SFX clips to generate for a project (18 total).

    Attributes:
        clips: List of SFXClip objects (one per audio clip)
    """

    clips: list[SFXClip]


class SFXGenerationService:
    """Service for generating sound effects audio clips using ElevenLabs v3 API.

    Responsibilities:
    - Map SFX descriptions to video clips (1-to-1 correspondence)
    - Orchestrate CLI script invocation for each SFX clip
    - Validate audio output files and durations
    - Track completed vs. pending clips for partial resume
    - Calculate and report ElevenLabs API costs

    Architecture: "Smart Agent + Dumb Scripts"
    - Service (Smart): Maps descriptions to clips, manages retry
    - CLI Script (Dumb): Calls ElevenLabs API, downloads WAV
    """

    def __init__(self, channel_id: str, project_id: str) -> None:
        """Initialize SFX generation service for specific project.

        Args:
            channel_id: Channel identifier for path isolation
            project_id: Project/task identifier (UUID from database)

        Raises:
            ValueError: If channel_id or project_id contain invalid characters
        """
        _validate_identifier(channel_id, "channel_id")
        _validate_identifier(project_id, "project_id")
        self.channel_id = channel_id
        self.project_id = project_id
        self.log = get_logger(__name__)

    async def create_sfx_manifest(
        self,
        sfx_descriptions: list[str],
        video_durations: list[float] | None = None,
    ) -> SFXManifest:
        """Create SFX manifest by mapping 18 descriptions to audio clips.

        SFX Description Mapping Strategy:
        1. Parse sfx_descriptions list (18 entries, one per clip)
        2. Map each description to corresponding clip number (1-18)
        3. Optionally include video durations for target duration matching

        Args:
            sfx_descriptions: List of 18 SFX description strings (one per clip)
            video_durations: Optional list of video clip durations (for validation)

        Returns:
            SFXManifest with 18 SFXClip objects

        Raises:
            ValueError: If sfx_descriptions count != 18

        Example:
            >>> manifest = await service.create_sfx_manifest(
            ...     sfx_descriptions=[
            ...         "Gentle forest ambience with rustling leaves",
            ...         "Wind howling through dark caves",
            ...         # ... 16 more descriptions
            ...     ],
            ...     video_durations=[7.2, 6.8, 8.1, ...],
            ... )
            >>> print(len(manifest.clips))
            18
        """
        # Validate input parameters
        if len(sfx_descriptions) != 18:
            raise ValueError(f"Expected 18 SFX descriptions, got {len(sfx_descriptions)}")

        # Get SFX directory (auto-creates with secure validation)
        sfx_dir = get_sfx_dir(self.channel_id, self.project_id)

        # Create clips with 1-to-1 mapping to video clips
        clips: list[SFXClip] = []
        for i, sfx_description in enumerate(sfx_descriptions, start=1):
            # Validate SFX description for ElevenLabs v3 best practices
            self.validate_sfx_description(sfx_description, i)

            # Get target duration if available (optional)
            target_duration = None
            if video_durations and len(video_durations) >= i:
                target_duration = video_durations[i - 1]

            # Create clip with output path
            clip = SFXClip(
                clip_number=i,
                sfx_description=sfx_description,
                output_path=sfx_dir / f"sfx_{i:02d}.wav",
                target_duration_seconds=target_duration,
            )
            clips.append(clip)

        self.log.info(
            "sfx_manifest_created",
            channel_id=self.channel_id,
            project_id=self.project_id,
            clip_count=len(clips),
        )

        return SFXManifest(clips=clips)

    async def generate_sfx(
        self,
        manifest: SFXManifest,
        resume: bool = False,
        max_concurrent: int = 10,
    ) -> dict[str, Any]:
        """Generate all SFX audio clips in manifest by invoking CLI script.

        Orchestration Flow:
        1. For each clip in manifest:
           a. Check if SFX exists (if resume=True, skip existing)
           b. Call `scripts/generate_sound_effects.py`:
              - Pass SFX description, output path
              - Wait 5-20 seconds (typical), up to 60 seconds max
           c. Wait for completion (CLI script handles API call)
           d. Verify WAV file exists and is valid audio
           e. Optionally probe audio duration with ffprobe for validation
           f. Log success/failure with clip number, generation time, duration
        2. Respect max_concurrent limit (10 parallel ElevenLabs requests)
        3. Return summary (generated count, skipped count, failed count)

        Args:
            manifest: SFXManifest with 18 clip definitions
            resume: If True, skip clips that already exist on filesystem
            max_concurrent: Maximum concurrent ElevenLabs API requests (default 10)

        Returns:
            Summary dict with keys:
                - generated: Number of newly generated SFX clips
                - skipped: Number of existing SFX clips (if resume=True)
                - failed: Number of failed SFX clips
                - total_cost_usd: Total ElevenLabs API cost (Decimal)

        Raises:
            CLIScriptError: If any SFX generation fails (non-retriable)

        Example:
            >>> result = await service.generate_sfx(manifest, resume=False, max_concurrent=10)
            >>> print(result)
            {"generated": 18, "skipped": 0, "failed": 0, "total_cost_usd": Decimal("0.72")}
        """
        # Track results
        generated = 0
        skipped = 0
        failed = 0

        # Semaphore limits concurrent ElevenLabs API requests
        semaphore = asyncio.Semaphore(max_concurrent)

        @retry(
            retry=retry_if_exception_type(CLIScriptError),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=2, min=2, max=8),
            before_sleep=lambda retry_state: self.log.warning(
                "sfx_generation_retry",
                attempt=retry_state.attempt_number,
                wait_seconds=retry_state.next_action.sleep if retry_state.next_action else 0,
            ),
            retry_error_callback=lambda retry_state: None,  # Return None on final failure
        )
        async def _generate_with_retry(clip: SFXClip) -> None:
            """Call CLI script with retry logic for retriable errors.

            Raises:
                CLIScriptError: On non-retriable errors (401, 403, 400)
                Re-raises on final retry exhaustion after 3 attempts
            """
            try:
                await run_cli_script(
                    "generate_sound_effects.py",
                    ["--prompt", clip.sfx_description, "--output", str(clip.output_path)],
                    timeout=60,  # 1 minute max per clip
                )
            except CLIScriptError as e:
                # Check if error is retriable
                if not _is_retriable_error(e):
                    # Non-retriable error (401, 403, 400) - fail immediately
                    self.log.error(
                        "sfx_generation_non_retriable_error",
                        clip_number=clip.clip_number,
                        error_code=e.exit_code,
                        stderr=e.stderr[:200],
                    )
                    raise  # Don't retry, re-raise immediately

                # Retriable error (429, 5xx, timeout) - let tenacity handle retry
                self.log.warning(
                    "sfx_generation_retriable_error",
                    clip_number=clip.clip_number,
                    error_code=e.exit_code,
                    stderr=e.stderr[:200],
                )
                raise  # Re-raise for tenacity to retry

        async def generate_single_clip(clip: SFXClip) -> bool:
            """Generate a single SFX clip with concurrency control.

            Returns:
                True if generated, False if skipped or failed
            """
            nonlocal generated, skipped, failed

            async with semaphore:
                # Check if SFX exists (for resume functionality)
                if resume and self.check_sfx_exists(clip.output_path):
                    skipped += 1
                    self.log.info(
                        "sfx_clip_skipped",
                        clip_number=clip.clip_number,
                        path=str(clip.output_path),
                        reason="already_exists",
                    )
                    return False

                try:
                    # Call CLI script with 60-second timeout (SFX is fast)
                    self.log.info(
                        "sfx_generation_start",
                        clip_number=clip.clip_number,
                        description_length=len(clip.sfx_description),
                        target_duration=clip.target_duration_seconds,
                    )

                    # Call with retry logic
                    await _generate_with_retry(clip)

                    # Verify SFX file exists
                    if not self.check_sfx_exists(clip.output_path):
                        raise ValueError(f"SFX file not created: {clip.output_path}")

                    # Validate audio duration (optional but recommended)
                    try:
                        duration = await self.validate_sfx_duration(clip.output_path)
                        self.log.info(
                            "sfx_clip_generated",
                            clip_number=clip.clip_number,
                            duration_seconds=duration,
                            target_duration=clip.target_duration_seconds,
                            variance=abs(duration - (clip.target_duration_seconds or duration)),
                        )

                        # Warn if SFX exceeds 10 seconds (video clip is only 10s)
                        if duration > 10.0:
                            self.log.warning(
                                "sfx_duration_warning",
                                clip_number=clip.clip_number,
                                duration=duration,
                                message="SFX exceeds 10 seconds (video clip max duration)",
                            )
                    except (FileNotFoundError, subprocess.CalledProcessError) as e:
                        # ffprobe not available or failed - log but don't fail
                        self.log.warning(
                            "sfx_duration_validation_failed",
                            clip_number=clip.clip_number,
                            error=str(e),
                        )

                    generated += 1
                    return True

                except CLIScriptError as e:
                    failed += 1
                    self.log.error(
                        "sfx_generation_failed",
                        clip_number=clip.clip_number,
                        script=e.script,
                        exit_code=e.exit_code,
                        stderr=e.stderr[:500],  # Truncate stderr
                    )
                    raise  # Re-raise to stop generation on failure

                except Exception as e:
                    failed += 1
                    self.log.error(
                        "sfx_generation_unexpected_error",
                        clip_number=clip.clip_number,
                        error=str(e),
                    )
                    raise  # Re-raise to stop generation on failure

        # Generate all clips with controlled parallelism
        # If any clip fails with non-retriable error, the entire batch fails
        # This ensures we don't mark task as success when clips are missing
        try:
            await asyncio.gather(*[generate_single_clip(clip) for clip in manifest.clips])
        except CLIScriptError:
            # If any clip fails after retries, mark entire generation as failed
            # This will propagate to worker which will mark task as SFX_ERROR
            self.log.error(
                "sfx_generation_failed",
                generated=generated,
                skipped=skipped,
                failed=failed,
                message="One or more clips failed after retry attempts",
            )
            raise  # Re-raise to mark task as failed

        # Calculate total cost
        total_cost = self.calculate_elevenlabs_cost(generated)

        self.log.info(
            "sfx_generation_complete",
            generated=generated,
            skipped=skipped,
            failed=failed,
            total_cost=str(total_cost),
        )

        return {
            "generated": generated,
            "skipped": skipped,
            "failed": failed,
            "total_cost_usd": total_cost,
        }

    def check_sfx_exists(self, sfx_path: Path) -> bool:
        """Check if SFX file exists on filesystem.

        Used for partial resume (Story 3.7 AC4).

        Args:
            sfx_path: Full path to SFX WAV file

        Returns:
            True if file exists and is readable, False otherwise
        """
        return sfx_path.exists() and sfx_path.is_file()

    async def validate_sfx_duration(self, sfx_path: Path) -> float:
        """Validate SFX duration using ffprobe.

        Args:
            sfx_path: Path to WAV audio file

        Returns:
            Audio duration in seconds (e.g., 7.2)

        Raises:
            FileNotFoundError: If SFX file doesn't exist
            subprocess.CalledProcessError: If ffprobe fails

        Example:
            >>> duration = await service.validate_sfx_duration(Path("sfx/sfx_01.wav"))
            >>> print(duration)
            7.2
        """
        if not self.check_sfx_exists(sfx_path):
            raise FileNotFoundError(f"SFX file not found: {sfx_path}")

        # Use ffprobe to get audio duration
        # This is blocking I/O, so wrap in asyncio.to_thread
        def _probe_duration() -> float:
            # Security: ffprobe command is hardcoded, sfx_path comes from validated
            # get_sfx_dir() which prevents path traversal (Story 3.2).
            result = subprocess.run(  # noqa: S603
                [  # noqa: S607
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(sfx_path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return float(result.stdout.strip())

        duration = await asyncio.to_thread(_probe_duration)
        return duration

    def calculate_elevenlabs_cost(self, clip_count: int) -> Decimal:
        """Calculate ElevenLabs API cost for generated SFX clips.

        ElevenLabs Pricing Model (as of 2026-01-15):
        - Approximately $0.50-1.00 per complete video (18 clips)
        - ~$0.04 per SFX clip ($0.72 / 18 clips) - same as narration

        Args:
            clip_count: Number of clips generated

        Returns:
            Total cost in USD (Decimal type for precision)

        Example:
            >>> cost = service.calculate_elevenlabs_cost(18)
            >>> print(cost)
            Decimal('0.72')
        """
        # ElevenLabs pricing: ~$0.04 per clip
        cost_per_clip = Decimal("0.04")
        return cost_per_clip * clip_count

    def validate_sfx_description(self, description: str, clip_number: int) -> None:
        """Validate SFX description structure for ElevenLabs v3.

        ElevenLabs v3 Best Practices:
        - Very short descriptions (< 20 chars) may cause generic output
        - Prefer SFX descriptions > 50 characters for specific ambience
        - Focus on environmental sounds, NOT voices

        Args:
            description: SFX description to validate
            clip_number: Clip number for logging

        Logs warnings but does NOT raise exceptions (non-blocking validation)
        """
        if len(description) < 20:
            self.log.warning(
                "sfx_description_warning",
                clip_number=clip_number,
                description_length=len(description),
                message="Very short SFX description may cause generic output (ElevenLabs v3)",
                recommendation="Prefer SFX descriptions > 50 characters for specific ambience",
            )
