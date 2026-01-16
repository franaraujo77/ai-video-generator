"""Video Assembly Service for FFmpeg-powered final video assembly.

This module implements the final stage (Step 6) of the 8-step video generation pipeline.
It orchestrates the assembly of 18 video clips, narration audio, and SFX into a complete
90-second documentary using FFmpeg, following the "Smart Agent + Dumb Scripts" architectural pattern.

Key Responsibilities:
- Probe audio durations with ffprobe for accurate video trimming synchronization
- Create assembly manifests mapping 18 clips (video + narration + SFX)
- Validate all 54 input files exist before assembly (18 video + 18 audio + 18 SFX)
- Orchestrate CLI script invocation via async wrapper (Story 3.1)
- Validate final video output (H.264/AAC codec, 1920x1080, playability)
- Handle assembly errors with detailed context for debugging

Architecture Pattern:
    Service (Smart): Probes durations, validates files, constructs manifest JSON
    CLI Script (Dumb): Invokes FFmpeg with manifest, returns success/failure

FFmpeg Operations:
    - Trim each 10-second video clip to match narration duration (6-8 seconds)
    - Mix narration (0dB) + SFX (-20dB) into single audio track
    - Concatenate 18 trimmed clips with hard cuts (no transitions)
    - Output H.264 video + AAC audio in 1920x1080 (16:9, YouTube-compatible)

Dependencies:
    - Story 3.1: CLI wrapper (run_cli_script, CLIScriptError)
    - Story 3.2: Filesystem helpers (get_project_dir, get_video_dir, get_audio_dir, get_sfx_dir)
    - Story 3.5: Video clip generation (18 video clips, 10-second MP4s)
    - Story 3.6: Narration generation (18 narration audio clips, 6-8 second MP3s)
    - Story 3.7: Sound effects generation (18 SFX audio clips, WAV files)
    - scripts/assemble_video.py: FFmpeg CLI script (brownfield)

Usage:
    from app.services.video_assembly import VideoAssemblyService

    service = VideoAssemblyService("poke1", "vid_abc123")
    manifest = await service.create_assembly_manifest(clip_count=18)
    await service.validate_input_files(manifest)
    result = await service.assemble_video(manifest)
    print(f"Assembled video: {result['duration']}s, {result['file_size_mb']}MB")
"""

import asyncio
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.cli_wrapper import CLIScriptError, run_cli_script
from app.utils.filesystem import (
    get_audio_dir,
    get_project_dir,
    get_sfx_dir,
    get_video_dir,
)
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


@dataclass
class ClipAssemblySpec:
    """Specification for assembling a single clip with audio synchronization.

    Attributes:
        clip_number: Clip number (1-18)
        video_path: Path to 10-second video clip MP4
        narration_path: Path to narration audio MP3 (6-8 seconds typical)
        sfx_path: Path to sound effects WAV file
        narration_duration: Measured audio duration in seconds (from ffprobe)
    """

    clip_number: int
    video_path: Path
    narration_path: Path
    sfx_path: Path
    narration_duration: float  # Measured with ffprobe


@dataclass
class AssemblyManifest:
    """Complete manifest for assembling final video from 18 clips.

    Attributes:
        clips: List of ClipAssemblySpec objects (18 total, one per clip)
        output_path: Path where final assembled MP4 will be saved
    """

    clips: list[ClipAssemblySpec]
    output_path: Path

    def to_json_dict(self) -> dict[str, Any]:
        """Convert manifest to JSON format for CLI script.

        Returns:
            Dictionary with 'clips' list containing clip specs with string paths.
        """
        return {
            "clips": [
                {
                    "clip_number": clip.clip_number,
                    "video_path": str(clip.video_path),
                    "narration_path": str(clip.narration_path),
                    "sfx_path": str(clip.sfx_path),
                    "narration_duration": clip.narration_duration,
                }
                for clip in self.clips
            ]
        }


class VideoAssemblyService:
    """Service for assembling final documentary video from clips using FFmpeg.

    Responsibilities:
    - Probe audio durations with ffprobe for accurate video trimming
    - Validate all input files exist before assembly
    - Create assembly manifest JSON for CLI script
    - Orchestrate CLI script invocation for FFmpeg processing
    - Validate final video output (codec, duration, playability)
    - Handle assembly errors and provide detailed failure context

    Architecture: "Smart Agent + Dumb Scripts"
    - Service (Smart): Probes durations, validates files, constructs manifest
    - CLI Script (Dumb): Invokes FFmpeg with manifest, returns success/failure

    Attributes:
        channel_id: Channel identifier for path isolation
        project_id: Project/task identifier (UUID from database)
    """

    def __init__(self, channel_id: str, project_id: str):
        """Initialize video assembly service for specific project.

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

    async def create_assembly_manifest(self, clip_count: int = 18) -> AssemblyManifest:
        """Create assembly manifest by probing audio durations and validating files.

        Assembly Manifest Creation Strategy:
        1. For each clip (1-18):
           a. Construct paths: video, narration, SFX files
           b. Validate all 3 files exist on filesystem
           c. Probe narration audio duration with ffprobe
           d. Create ClipAssemblySpec with measured duration
        2. Set output path for final assembled video
        3. Return complete manifest with 18 clip specs

        Args:
            clip_count: Number of clips to assemble (default: 18)

        Returns:
            AssemblyManifest with 18 ClipAssemblySpec objects

        Raises:
            FileNotFoundError: If any required file (video/audio/SFX) is missing
            ValueError: If ffprobe fails to measure audio duration

        Example:
            >>> manifest = await service.create_assembly_manifest(clip_count=18)
            >>> print(len(manifest.clips))
            18
            >>> print(manifest.clips[0].narration_duration)
            7.2
        """
        self.log.info(
            "creating_assembly_manifest",
            channel_id=self.channel_id,
            project_id=self.project_id,
            clip_count=clip_count,
        )

        # Get directory paths
        video_dir = get_video_dir(self.channel_id, self.project_id)
        audio_dir = get_audio_dir(self.channel_id, self.project_id)
        sfx_dir = get_sfx_dir(self.channel_id, self.project_id)
        project_dir = get_project_dir(self.channel_id, self.project_id)

        # Build clip specifications
        clips: list[ClipAssemblySpec] = []

        for clip_num in range(1, clip_count + 1):
            # Construct file paths
            video_path = video_dir / f"clip_{clip_num:02d}.mp4"
            narration_path = audio_dir / f"clip_{clip_num:02d}.mp3"
            sfx_path = sfx_dir / f"sfx_{clip_num:02d}.wav"

            # Validate files exist
            if not self.check_file_exists(video_path):
                raise FileNotFoundError(f"Video file missing: {video_path}")
            if not self.check_file_exists(narration_path):
                raise FileNotFoundError(f"Narration audio file missing: {narration_path}")
            if not self.check_file_exists(sfx_path):
                raise FileNotFoundError(f"SFX audio file missing: {sfx_path}")

            # Probe narration audio duration
            narration_duration = await self.probe_audio_duration(narration_path)

            self.log.debug(
                "clip_spec_created",
                clip_number=clip_num,
                video_path=str(video_path),
                narration_duration=narration_duration,
            )

            clips.append(
                ClipAssemblySpec(
                    clip_number=clip_num,
                    video_path=video_path,
                    narration_path=narration_path,
                    sfx_path=sfx_path,
                    narration_duration=narration_duration,
                )
            )

        # Set output path for final video
        output_path = project_dir / f"{self.project_id}_final.mp4"

        self.log.info(
            "assembly_manifest_created",
            clip_count=len(clips),
            output_path=str(output_path),
            total_estimated_duration=sum(clip.narration_duration for clip in clips),
        )

        return AssemblyManifest(clips=clips, output_path=output_path)

    async def validate_input_files(self, manifest: AssemblyManifest) -> None:
        """Validate all input files exist before assembly.

        Validation Checks:
        - All 18 video MP4 files exist
        - All 18 narration MP3 files exist
        - All 18 SFX WAV files exist
        - Files are readable
        - File sizes > 0 (not empty)

        Args:
            manifest: AssemblyManifest with clip file paths

        Raises:
            FileNotFoundError: If any required file is missing or empty

        Example:
            >>> await service.validate_input_files(manifest)
            # Raises FileNotFoundError if clip_07.mp4 missing
        """
        self.log.info("validating_input_files", clip_count=len(manifest.clips))

        missing_files = []

        for clip in manifest.clips:
            if not self.check_file_exists(clip.video_path):
                missing_files.append(f"Video: {clip.video_path}")
            if not self.check_file_exists(clip.narration_path):
                missing_files.append(f"Narration: {clip.narration_path}")
            if not self.check_file_exists(clip.sfx_path):
                missing_files.append(f"SFX: {clip.sfx_path}")

        if missing_files:
            self.log.error("input_validation_failed", missing_files=missing_files)
            raise FileNotFoundError(
                f"Missing {len(missing_files)} input files: {', '.join(missing_files[:3])}"
            )

        self.log.info("input_validation_passed", total_files=len(manifest.clips) * 3)

    async def probe_audio_duration(self, audio_path: Path) -> float:
        """Probe audio file duration using ffprobe.

        ffprobe Command:
        ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 audio.mp3

        Args:
            audio_path: Path to audio file (MP3 or WAV)

        Returns:
            Duration in seconds (e.g., 7.2)

        Raises:
            FileNotFoundError: If audio file doesn't exist
            subprocess.CalledProcessError: If ffprobe fails
            ValueError: If ffprobe output is not a valid float

        Example:
            >>> duration = await service.probe_audio_duration(Path("audio/clip_01.mp3"))
            >>> print(duration)
            7.2
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        self.log.debug("probing_audio_duration", audio_path=str(audio_path))

        # Run ffprobe command to get duration
        # Use asyncio.to_thread to prevent blocking event loop
        result = await asyncio.to_thread(
            subprocess.run,
            [
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
            timeout=5,  # ffprobe is fast
        )

        if result.returncode != 0:
            self.log.error(
                "ffprobe_failed",
                audio_path=str(audio_path),
                exit_code=result.returncode,
                stderr=result.stderr,
            )
            raise subprocess.CalledProcessError(
                result.returncode, "ffprobe", output=result.stdout, stderr=result.stderr
            )

        # Parse duration from stdout
        try:
            duration = float(result.stdout.strip())
            self.log.debug("audio_duration_probed", audio_path=str(audio_path), duration=duration)
            return duration
        except ValueError as e:
            self.log.error(
                "invalid_ffprobe_output",
                audio_path=str(audio_path),
                output=result.stdout,
                error=str(e),
            )
            raise ValueError(
                f"Invalid ffprobe output for {audio_path}: {result.stdout.strip()}"
            ) from e

    async def assemble_video(self, manifest: AssemblyManifest) -> dict[str, Any]:
        """Assemble final video by invoking FFmpeg CLI script.

        Orchestration Flow:
        1. Write manifest to temporary JSON file
        2. Call `scripts/assemble_video.py`:
           - Pass manifest JSON path and output path
           - Wait 60-120 seconds (typical), up to 180 seconds max
        3. Wait for completion (CLI script handles FFmpeg execution)
        4. Verify output file exists
        5. Validate output video with ffprobe (playable, correct codec)
        6. Return summary (duration, file size, codec info)

        Args:
            manifest: AssemblyManifest with 18 clip specs and output path

        Returns:
            Summary dict with keys:
                - duration: Final video duration in seconds (~90s)
                - file_size_mb: Output file size in MB
                - resolution: Video resolution (e.g., "1920x1080")
                - codec: Video/audio codec (e.g., "h264/aac")

        Raises:
            CLIScriptError: If FFmpeg assembly fails (non-retriable)
            FileNotFoundError: If output video not created
            ValueError: If output video validation fails

        Example:
            >>> result = await service.assemble_video(manifest)
            >>> print(result)
            {"duration": 91.5, "file_size_mb": 142.3, "resolution": "1920x1080", "codec": "h264/aac"}
        """
        self.log.info(
            "starting_video_assembly",
            output_path=str(manifest.output_path),
            clip_count=len(manifest.clips),
            estimated_time_seconds=90,  # 60-120 seconds typical
        )

        # Write manifest to temporary JSON file
        project_dir = get_project_dir(self.channel_id, self.project_id)
        manifest_path = project_dir / "assembly_manifest.json"

        manifest_json = json.dumps(manifest.to_json_dict(), indent=2)
        manifest_path.write_text(manifest_json, encoding="utf-8")

        self.log.debug("manifest_written", manifest_path=str(manifest_path))

        # Call FFmpeg assembly CLI script
        try:
            result = await run_cli_script(
                "assemble_video.py",
                ["--manifest", str(manifest_path), "--output", str(manifest.output_path)],
                timeout=180,  # 3 minutes max (60-120 seconds typical)
            )

            self.log.info(
                "ffmpeg_assembly_complete",
                output_path=str(manifest.output_path),
                stdout=result.stdout[:200],  # Truncate for logging
            )

        except CLIScriptError as e:
            self.log.error(
                "ffmpeg_assembly_failed",
                script=e.script,
                exit_code=e.exit_code,
                stderr=e.stderr[:500],  # Truncate stderr
                manifest_path=str(manifest_path),
            )
            raise

        except asyncio.TimeoutError:
            self.log.error(
                "ffmpeg_timeout",
                timeout=180,
                output_path=str(manifest.output_path),
            )
            raise

        # Verify output file exists
        if not manifest.output_path.exists():
            raise FileNotFoundError(
                f"FFmpeg completed but output file not found: {manifest.output_path}"
            )

        # Validate output video
        video_metadata = await self.validate_output_video(manifest.output_path)

        self.log.info(
            "video_assembly_validated",
            duration=video_metadata["duration"],
            file_size_mb=video_metadata["file_size_mb"],
            resolution=video_metadata["resolution"],
            codec=video_metadata.get("video_codec", "unknown")
            + "/"
            + video_metadata.get("audio_codec", "unknown"),
        )

        return video_metadata

    async def validate_output_video(self, video_path: Path) -> dict[str, Any]:
        """Validate final assembled video using ffprobe.

        Validation Checks:
        - File exists and is readable
        - Video stream present (H.264 codec)
        - Audio stream present (AAC codec)
        - Resolution is 1920x1080 (16:9)
        - Duration > 0 seconds
        - File is playable (no corruption)

        Args:
            video_path: Path to assembled MP4 file

        Returns:
            Video metadata dict with keys:
                - duration: Video duration in seconds
                - resolution: Video resolution (e.g., "1920x1080")
                - video_codec: Video codec name (e.g., "h264")
                - audio_codec: Audio codec name (e.g., "aac")
                - file_size_mb: File size in MB

        Raises:
            FileNotFoundError: If video file doesn't exist
            ValueError: If video validation fails (corrupt, wrong codec, etc.)

        Example:
            >>> metadata = await service.validate_output_video(Path("final.mp4"))
            >>> print(metadata["duration"])
            91.5
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        self.log.info("validating_output_video", video_path=str(video_path))

        # Run ffprobe to get video metadata
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_name,width,height",
                "-of",
                "json",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            self.log.error(
                "ffprobe_validation_failed",
                video_path=str(video_path),
                exit_code=result.returncode,
                stderr=result.stderr,
            )
            raise ValueError(f"ffprobe validation failed: {result.stderr}")

        # Parse ffprobe JSON output
        try:
            metadata = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid ffprobe JSON output: {result.stdout}") from e

        # Extract video stream info
        streams = metadata.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if not video_stream:
            raise ValueError(f"No video stream found in {video_path}")
        if not audio_stream:
            raise ValueError(f"No audio stream found in {video_path}")

        # Extract metadata
        duration = float(metadata.get("format", {}).get("duration", 0))
        width = video_stream.get("width", 0)
        height = video_stream.get("height", 0)
        video_codec = video_stream.get("codec_name", "unknown")
        audio_codec = audio_stream.get("codec_name", "unknown")

        # Calculate file size
        file_size_mb = video_path.stat().st_size / (1024 * 1024)

        # Validate resolution (must be 1920x1080 for YouTube)
        if width != 1920 or height != 1080:
            self.log.warning(
                "unexpected_resolution",
                video_path=str(video_path),
                width=width,
                height=height,
                expected="1920x1080",
            )

        # Validate codec (H.264 + AAC for YouTube compatibility)
        if video_codec != "h264":
            self.log.warning(
                "unexpected_video_codec",
                video_path=str(video_path),
                codec=video_codec,
                expected="h264",
            )

        if audio_codec != "aac":
            self.log.warning(
                "unexpected_audio_codec",
                video_path=str(video_path),
                codec=audio_codec,
                expected="aac",
            )

        self.log.info(
            "output_video_validated",
            duration=duration,
            resolution=f"{width}x{height}",
            video_codec=video_codec,
            audio_codec=audio_codec,
            file_size_mb=round(file_size_mb, 2),
        )

        return {
            "duration": duration,
            "resolution": f"{width}x{height}",
            "video_codec": video_codec,
            "audio_codec": audio_codec,
            "file_size_mb": round(file_size_mb, 2),
        }

    def check_file_exists(self, file_path: Path) -> bool:
        """Check if file exists on filesystem.

        Used for input validation before assembly.

        Args:
            file_path: Full path to file

        Returns:
            True if file exists and is readable, False otherwise
        """
        return file_path.exists() and file_path.is_file() and file_path.stat().st_size > 0
