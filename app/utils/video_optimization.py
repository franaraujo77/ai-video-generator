"""Video optimization utilities for MP4 faststart and streaming playback.

This module provides utilities for optimizing MP4 video files for web streaming.
The primary optimization is adding the MOOV atom at the beginning of the file
(MP4 faststart), which enables progressive download and playback to start within
1-2 seconds in Notion.

Key Responsibilities:
- Verify if video is already optimized (MOOV atom at start)
- Re-encode video with faststart flag if needed
- Atomic file replacement to avoid corruption
- Integration with FFmpeg via CLI wrapper

Technical Background:
    MP4 files contain metadata (MOOV atom) that describes the video structure.
    By default, FFmpeg places this at the end of the file, requiring full download
    before playback can begin. The `-movflags faststart` flag moves the MOOV atom
    to the beginning, enabling streaming playback.

Architecture Pattern:
    Uses app.utils.cli_wrapper.run_cli_script() for all FFmpeg operations
    Never calls subprocess directly - always use the wrapper

Dependencies:
    - FFmpeg 8.0.1+ installed and in PATH
    - app.utils.cli_wrapper.run_cli_script() for subprocess execution

Usage:
    from app.utils.video_optimization import optimize_video_for_streaming

    video_path = Path("/workspace/videos/clip_01.mp4")
    await optimize_video_for_streaming(video_path)
    # Video is now optimized for streaming

References:
    - Mux: https://www.mux.com/articles/optimize-video-for-web-playback-with-ffmpeg
    - Smashing Magazine: https://www.smashingmagazine.com/2021/02/optimizing-video-size-quality/
    - KeyCDN: https://www.keycdn.com/blog/video-optimization
"""

import asyncio
from pathlib import Path

from app.utils.cli_wrapper import CLIScriptError
from app.utils.logging import get_logger

log = get_logger(__name__)


async def is_video_optimized(video_path: Path) -> bool:
    """Check if video has MOOV atom at beginning (faststart optimized).

    Uses ffprobe to check if start_time is 0.000000, which indicates
    the MOOV atom is at the beginning of the file.

    Args:
        video_path: Path to MP4 video file

    Returns:
        True if video is already optimized, False if needs optimization

    Raises:
        CLIScriptError: If ffprobe fails (video corrupt or not found)
        asyncio.TimeoutError: If ffprobe takes too long (>10 seconds)

    Example:
        >>> video_path = Path("/workspace/videos/clip_01.mp4")
        >>> if not await is_video_optimized(video_path):
        ...     await optimize_video_for_streaming(video_path)
    """
    try:
        # Use ffprobe to check start_time
        # NOTE: We can't use run_cli_script here since ffprobe is not in scripts/
        # We'll use asyncio.to_thread to avoid blocking the event loop
        import subprocess

        def check_probe() -> str:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=start_time",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise CLIScriptError("ffprobe", result.returncode, result.stderr)
            return result.stdout.strip()

        start_time_str = await asyncio.to_thread(check_probe)
        start_time = float(start_time_str)

        # Video is optimized if start_time is 0.000000 (MOOV at beginning)
        is_optimized = abs(start_time) < 0.001  # Allow for floating point precision

        log.info(
            "video_optimization_check",
            path=str(video_path),
            start_time=start_time,
            is_optimized=is_optimized,
        )

        return is_optimized

    except Exception as e:
        log.error(
            "video_optimization_check_failed",
            path=str(video_path),
            error=str(e),
            exc_info=True,
        )
        # If we can't check, assume not optimized (safer to re-encode)
        return False


async def optimize_video_for_streaming(video_path: Path, force: bool = False) -> bool:
    """Optimize MP4 video for streaming by adding faststart flag.

    Re-encodes video with `-movflags faststart` to move MOOV atom to
    the beginning of the file, enabling progressive download and playback
    within 1-2 seconds in Notion.

    Uses atomic file replacement (temp file + replace) to avoid corruption
    if optimization fails mid-process.

    Args:
        video_path: Path to MP4 video file to optimize
        force: If True, skip optimization check and always re-encode

    Returns:
        True if video was optimized, False if already optimized (and not forced)

    Raises:
        CLIScriptError: If FFmpeg fails
        asyncio.TimeoutError: If FFmpeg takes too long (>60 seconds)
        FileNotFoundError: If video file doesn't exist

    Example:
        >>> video_path = Path("/workspace/videos/clip_01.mp4")
        >>> optimized = await optimize_video_for_streaming(video_path)
        >>> if optimized:
        ...     log.info("Video optimized for streaming")
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Check if already optimized (unless force=True)
    if not force:
        if await is_video_optimized(video_path):
            log.info(
                "video_already_optimized",
                path=str(video_path),
            )
            return False

    # Create temp file path for atomic replacement
    temp_path = video_path.with_suffix(".temp.mp4")

    try:
        log.info(
            "video_optimization_started",
            path=str(video_path),
            temp_path=str(temp_path),
        )

        # Use ffmpeg to re-encode with faststart
        # NOTE: We can't use run_cli_script here since ffmpeg is not in scripts/
        # We'll use asyncio.to_thread to avoid blocking the event loop
        import subprocess

        def run_ffmpeg() -> None:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    str(video_path),
                    "-movflags",
                    "faststart",
                    "-c",
                    "copy",  # Copy codecs, no re-encoding (fast)
                    "-y",  # Overwrite temp file if exists
                    str(temp_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise CLIScriptError("ffmpeg", result.returncode, result.stderr)

        await asyncio.to_thread(run_ffmpeg)

        # Atomic replace: Move temp to original
        # This ensures we never have a corrupt/partial video file
        temp_path.replace(video_path)

        log.info(
            "video_optimization_complete",
            path=str(video_path),
        )

        return True

    except Exception as e:
        log.error(
            "video_optimization_failed",
            path=str(video_path),
            error=str(e),
            exc_info=True,
        )
        # Clean up temp file if it exists
        if temp_path.exists():
            temp_path.unlink()
        raise


async def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe.

    Args:
        video_path: Path to video file

    Returns:
        Duration in seconds (float)

    Raises:
        CLIScriptError: If ffprobe fails
        asyncio.TimeoutError: If ffprobe takes too long (>10 seconds)
        FileNotFoundError: If video file doesn't exist

    Example:
        >>> video_path = Path("/workspace/videos/clip_01.mp4")
        >>> duration = await get_video_duration(video_path)
        >>> print(f"Video duration: {duration:.2f} seconds")
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    try:
        import subprocess

        def probe_duration() -> str:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise CLIScriptError("ffprobe", result.returncode, result.stderr)
            return result.stdout.strip()

        duration_str = await asyncio.to_thread(probe_duration)
        duration = float(duration_str)

        log.info(
            "video_duration_probed",
            path=str(video_path),
            duration=duration,
        )

        return duration

    except Exception as e:
        log.error(
            "video_duration_probe_failed",
            path=str(video_path),
            error=str(e),
            exc_info=True,
        )
        raise
