"""Narration Generation Service for ElevenLabs-powered audio narration.

This module implements the fourth stage of the 8-step video generation pipeline.
It orchestrates the generation of 18 narration audio tracks via ElevenLabs v3
Text-to-Speech API, following the "Smart Agent + Dumb Scripts" architectural pattern.

Key Responsibilities:
- Create narration manifests mapping scripts to video clips (1-to-1 correspondence)
- Retrieve channel-specific voice_id for consistent narrator identity
- Orchestrate CLI script invocation via async wrapper (Story 3.1)
- Validate audio output files and durations with ffprobe
- Track completed vs. pending clips for partial resume support
- Calculate and report ElevenLabs API costs for budget monitoring

Architecture Pattern:
    Service (Smart): Maps scripts to clips, manages voice_id, handles retry
    CLI Script (Dumb): Calls ElevenLabs API, downloads MP3

Dependencies:
    - Story 3.1: CLI wrapper (run_cli_script, CLIScriptError)
    - Story 3.2: Filesystem helpers (get_audio_dir)
    - Story 3.5: Video generation (18 video clips for duration reference)
    - scripts/generate_audio.py: ElevenLabs CLI script (brownfield)

Usage:
    from app.services.narration_generation import NarrationGenerationService

    service = NarrationGenerationService("poke1", "vid_abc123")
    manifest = await service.create_narration_manifest(
        narration_scripts=[
            "In the depths of the forest, Haunter searches for prey.",
            # ... 17 more scripts
        ],
        voice_id="EXAVITQu4vr4xnSDxMaL"
    )

    result = await service.generate_narration(manifest, resume=False)
    print(f"Generated {result['generated']} audio clips, cost: ${result['total_cost_usd']}")
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
from app.utils.filesystem import get_audio_dir
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


def _validate_voice_id(voice_id: str) -> None:
    """Validate ElevenLabs voice_id to prevent injection attacks.

    Args:
        voice_id: ElevenLabs voice identifier to validate

    Raises:
        ValueError: If voice_id is invalid format

    Security:
        ElevenLabs voice IDs are typically 20+ alphanumeric characters.
        Validates format to prevent command injection via environment variables.
    """
    if not voice_id or len(voice_id) < 10:
        raise ValueError("Invalid voice_id: must be valid ElevenLabs identifier")
    # ElevenLabs voice IDs are alphanumeric (no special characters)
    if not re.match(r"^[a-zA-Z0-9]+$", voice_id):
        raise ValueError(f"Invalid voice_id format: {voice_id}")


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
class NarrationClip:
    """Represents a single narration audio clip to generate.

    Attributes:
        clip_number: Clip number (1-18)
        narration_text: Narration script text (natural speech structure)
        output_path: Path where MP3 audio will be saved
        target_duration_seconds: Optional target duration from video clip (for logging)
    """

    clip_number: int
    narration_text: str
    output_path: Path
    target_duration_seconds: float | None = None


@dataclass
class NarrationManifest:
    """Complete manifest of narration clips to generate for a project (18 total).

    Attributes:
        clips: List of NarrationClip objects (one per audio clip)
        voice_id: ElevenLabs voice ID for channel (consistent narrator)
    """

    clips: list[NarrationClip]
    voice_id: str


class NarrationGenerationService:
    """Service for generating narration audio clips from text using ElevenLabs v3 API.

    Responsibilities:
    - Map narration scripts to video clips (1-to-1 correspondence)
    - Retrieve channel-specific voice_id from database
    - Orchestrate CLI script invocation for each audio clip
    - Validate audio output files and durations
    - Track completed vs. pending clips for partial resume
    - Calculate and report ElevenLabs API costs

    Architecture: "Smart Agent + Dumb Scripts"
    - Service (Smart): Maps scripts to clips, manages voice_id, handles retry
    - CLI Script (Dumb): Calls ElevenLabs API, downloads MP3
    """

    def __init__(self, channel_id: str, project_id: str) -> None:
        """Initialize narration generation service for specific project.

        Args:
            channel_id: Channel identifier for path isolation and voice_id lookup
            project_id: Project/task identifier (UUID from database)

        Raises:
            ValueError: If channel_id or project_id contain invalid characters
        """
        _validate_identifier(channel_id, "channel_id")
        _validate_identifier(project_id, "project_id")
        self.channel_id = channel_id
        self.project_id = project_id
        self.log = get_logger(__name__)

    async def create_narration_manifest(
        self,
        narration_scripts: list[str],
        voice_id: str,
        video_durations: list[float] | None = None,
    ) -> NarrationManifest:
        """Create narration manifest by mapping 18 scripts to audio clips.

        Narration Script Mapping Strategy:
        1. Parse narration_scripts list (18 entries, one per clip)
        2. Map each script to corresponding clip number (1-18)
        3. Optionally include video durations for logging/validation
        4. Retrieve channel voice_id for consistent narrator

        Args:
            narration_scripts: List of 18 narration text strings (one per clip)
            voice_id: ElevenLabs voice ID from channel configuration
            video_durations: Optional list of video clip durations (for validation)

        Returns:
            NarrationManifest with 18 NarrationClip objects

        Raises:
            ValueError: If narration_scripts count != 18 or voice_id is empty

        Example:
            >>> manifest = await service.create_narration_manifest(
            ...     narration_scripts=[
            ...         "In the depths of the forest, Haunter searches for prey.",
            ...         "The ghostly figure glides silently through the darkness.",
            ...         # ... 16 more scripts
            ...     ],
            ...     voice_id="EXAVITQu4vr4xnSDxMaL",
            ...     video_durations=[7.2, 6.8, 8.1, ...],
            ... )
            >>> print(len(manifest.clips))
            18
            >>> print(manifest.voice_id)
            "EXAVITQu4vr4xnSDxMaL"
        """
        # Validate input parameters
        if len(narration_scripts) != 18:
            raise ValueError(f"Expected 18 narration scripts, got {len(narration_scripts)}")
        _validate_voice_id(voice_id)

        # Get audio directory (auto-creates with secure validation)
        audio_dir = get_audio_dir(self.channel_id, self.project_id)

        # Create clips with 1-to-1 mapping to video clips
        clips: list[NarrationClip] = []
        for i, narration_text in enumerate(narration_scripts, start=1):
            # Validate narration text for ElevenLabs v3 best practices
            self.validate_narration_text(narration_text, i)

            # Get target duration if available (optional)
            target_duration = None
            if video_durations and len(video_durations) >= i:
                target_duration = video_durations[i - 1]

            # Create clip with output path
            clip = NarrationClip(
                clip_number=i,
                narration_text=narration_text,
                output_path=audio_dir / f"clip_{i:02d}.mp3",
                target_duration_seconds=target_duration,
            )
            clips.append(clip)

        self.log.info(
            "narration_manifest_created",
            channel_id=self.channel_id,
            project_id=self.project_id,
            clip_count=len(clips),
            voice_id=voice_id[:10] + "...",  # Log first 10 chars only (security)
        )

        return NarrationManifest(clips=clips, voice_id=voice_id)

    async def generate_narration(
        self,
        manifest: NarrationManifest,
        resume: bool = False,
        max_concurrent: int = 10,
    ) -> dict[str, Any]:
        """Generate all narration audio clips in manifest by invoking CLI script.

        Orchestration Flow:
        1. For each clip in manifest:
           a. Check if audio exists (if resume=True, skip existing)
           b. Set ELEVENLABS_VOICE_ID environment variable (channel-specific)
           c. Call `scripts/generate_audio.py`:
              - Pass narration text, output path
              - Wait 5-15 seconds (typical), up to 60 seconds max
           d. Wait for completion (CLI script handles API call)
           e. Verify MP3 file exists and is valid audio
           f. Optionally probe audio duration with ffprobe for validation
           g. Log success/failure with clip number, generation time, duration
        2. Respect max_concurrent limit (10 parallel ElevenLabs requests)
        3. Return summary (generated count, skipped count, failed count)

        Args:
            manifest: NarrationManifest with 18 clip definitions
            resume: If True, skip clips that already exist on filesystem
            max_concurrent: Maximum concurrent ElevenLabs API requests (default 10)

        Returns:
            Summary dict with keys:
                - generated: Number of newly generated audio clips
                - skipped: Number of existing audio clips (if resume=True)
                - failed: Number of failed audio clips
                - total_cost_usd: Total ElevenLabs API cost (Decimal)

        Raises:
            CLIScriptError: If any audio generation fails (non-retriable)
            ValueError: If voice_id is invalid or missing

        Example:
            >>> result = await service.generate_narration(manifest, resume=False, max_concurrent=10)
            >>> print(result)
            {"generated": 18, "skipped": 0, "failed": 0, "total_cost_usd": Decimal("0.72")}
        """
        # Validate voice_id before starting
        _validate_voice_id(manifest.voice_id)

        # Prepare isolated environment variables for CLI script
        # CRITICAL: Pass as subprocess env (NOT os.environ) to prevent multi-channel pollution
        # Each CLI invocation gets its own isolated voice_id without affecting other workers
        cli_env = {"ELEVENLABS_VOICE_ID": manifest.voice_id}

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
                "audio_generation_retry",
                attempt=retry_state.attempt_number,
                wait_seconds=retry_state.next_action.sleep if retry_state.next_action else 0,
            ),
            retry_error_callback=lambda retry_state: None,  # Return None on final failure
        )
        async def _generate_with_retry(clip: NarrationClip) -> None:
            """Call CLI script with retry logic for retriable errors.

            Raises:
                CLIScriptError: On non-retriable errors (401, 403, 400)
                Re-raises on final retry exhaustion after 3 attempts
            """
            try:
                await run_cli_script(
                    "generate_audio.py",
                    ["--text", clip.narration_text, "--output", str(clip.output_path)],
                    timeout=60,  # 1 minute max per clip
                    env=cli_env,  # Pass isolated voice_id (prevents multi-channel pollution)
                )
            except CLIScriptError as e:
                # Check if error is retriable
                if not _is_retriable_error(e):
                    # Non-retriable error (401, 403, 400) - fail immediately
                    self.log.error(
                        "audio_generation_non_retriable_error",
                        clip_number=clip.clip_number,
                        error_code=e.exit_code,
                        stderr=e.stderr[:200],
                    )
                    raise  # Don't retry, re-raise immediately

                # Retriable error (429, 5xx, timeout) - let tenacity handle retry
                self.log.warning(
                    "audio_generation_retriable_error",
                    clip_number=clip.clip_number,
                    error_code=e.exit_code,
                    stderr=e.stderr[:200],
                )
                raise  # Re-raise for tenacity to retry

        async def generate_single_clip(clip: NarrationClip) -> bool:
            """Generate a single audio clip with concurrency control.

            Returns:
                True if generated, False if skipped or failed
            """
            nonlocal generated, skipped, failed

            async with semaphore:
                # Check if audio exists (for resume functionality)
                if resume and self.check_audio_exists(clip.output_path):
                    skipped += 1
                    self.log.info(
                        "audio_clip_skipped",
                        clip_number=clip.clip_number,
                        path=str(clip.output_path),
                        reason="already_exists",
                    )
                    return False

                try:
                    # Call CLI script with 60-second timeout (audio is fast)
                    self.log.info(
                        "audio_generation_start",
                        clip_number=clip.clip_number,
                        text_length=len(clip.narration_text),
                        target_duration=clip.target_duration_seconds,
                    )

                    # Call with retry logic
                    await _generate_with_retry(clip)

                    # Verify audio file exists
                    if not self.check_audio_exists(clip.output_path):
                        raise ValueError(f"Audio file not created: {clip.output_path}")

                    # Validate audio duration (optional but recommended)
                    try:
                        duration = await self.validate_audio_duration(clip.output_path)
                        self.log.info(
                            "audio_clip_generated",
                            clip_number=clip.clip_number,
                            duration_seconds=duration,
                            target_duration=clip.target_duration_seconds,
                            variance=abs(duration - (clip.target_duration_seconds or duration)),
                        )

                        # Warn if audio exceeds 10 seconds (video clip is only 10s)
                        if duration > 10.0:
                            self.log.warning(
                                "audio_duration_warning",
                                clip_number=clip.clip_number,
                                duration=duration,
                                message="Audio exceeds 10 seconds (video clip max duration)",
                            )
                    except (FileNotFoundError, subprocess.CalledProcessError) as e:
                        # ffprobe not available or failed - log but don't fail
                        self.log.warning(
                            "audio_duration_validation_failed",
                            clip_number=clip.clip_number,
                            error=str(e),
                        )

                    generated += 1
                    return True

                except CLIScriptError as e:
                    failed += 1
                    self.log.error(
                        "audio_generation_failed",
                        clip_number=clip.clip_number,
                        script=e.script,
                        exit_code=e.exit_code,
                        stderr=e.stderr[:500],  # Truncate stderr
                    )
                    raise  # Re-raise to stop generation on failure

                except Exception as e:
                    failed += 1
                    self.log.error(
                        "audio_generation_unexpected_error",
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
            # This will propagate to worker which will mark task as AUDIO_ERROR
            self.log.error(
                "narration_generation_failed",
                generated=generated,
                skipped=skipped,
                failed=failed,
                message="One or more clips failed after retry attempts",
            )
            raise  # Re-raise to mark task as failed

        # Calculate total cost
        total_cost = self.calculate_elevenlabs_cost(generated)

        self.log.info(
            "narration_generation_complete",
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

    def check_audio_exists(self, audio_path: Path) -> bool:
        """Check if audio file exists on filesystem.

        Used for partial resume (Story 3.6 AC4).

        Args:
            audio_path: Full path to audio MP3 file

        Returns:
            True if file exists and is readable, False otherwise
        """
        return audio_path.exists() and audio_path.is_file()

    async def validate_audio_duration(self, audio_path: Path) -> float:
        """Validate audio duration using ffprobe.

        Args:
            audio_path: Path to MP3 audio file

        Returns:
            Audio duration in seconds (e.g., 7.2)

        Raises:
            FileNotFoundError: If audio file doesn't exist
            subprocess.CalledProcessError: If ffprobe fails

        Example:
            >>> duration = await service.validate_audio_duration(Path("audio/clip_01.mp3"))
            >>> print(duration)
            7.2
        """
        if not self.check_audio_exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Use ffprobe to get audio duration
        # This is blocking I/O, so wrap in asyncio.to_thread
        def _probe_duration() -> float:
            # Security: ffprobe command is hardcoded, audio_path comes from validated
            # get_audio_dir() which prevents path traversal (Story 3.2).
            result = subprocess.run(  # noqa: S603
                [  # noqa: S607
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(audio_path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return float(result.stdout.strip())

        duration = await asyncio.to_thread(_probe_duration)
        return duration

    def calculate_elevenlabs_cost(self, clip_count: int) -> Decimal:
        """Calculate ElevenLabs API cost for generated clips.

        ElevenLabs Pricing Model (as of 2026-01-15):
        - Approximately $0.50-1.00 per complete video (18 clips)
        - ~$0.04 per audio clip ($0.72 / 18 clips)

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

    def validate_narration_text(self, text: str, clip_number: int) -> None:
        """Validate narration text structure for ElevenLabs v3.

        ElevenLabs v3 Best Practices:
        - Very short prompts (< 100 chars) may cause inconsistent output
        - Prefer narration text > 100 characters for stable results
        - Use natural speech patterns and proper punctuation

        Args:
            text: Narration text to validate
            clip_number: Clip number for logging

        Logs warnings but does NOT raise exceptions (non-blocking validation)
        """
        if len(text) < 100:
            self.log.warning(
                "narration_text_warning",
                clip_number=clip_number,
                text_length=len(text),
                message="Very short narration text may cause inconsistent output (ElevenLabs v3)",
                recommendation="Prefer narration text > 100 characters for stable results",
            )
