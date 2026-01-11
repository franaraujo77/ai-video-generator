#!/usr/bin/env python3
"""
Video Assembly CLI for Pokémon Natural Geographic Documentary
Uses FFmpeg to trim and concatenate 18 video clips with synced audio.

Usage:
    python assemble_video.py --manifest manifest.json --output pikachu_final.mp4
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import shutil


def get_audio_duration(audio_path):
    """
    Get the duration of an audio file in seconds using FFprobe.

    Args:
        audio_path: Path to audio file

    Returns:
        float: Duration in seconds
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        duration = float(result.stdout.strip())
        return duration

    except subprocess.CalledProcessError as e:
        print(f"❌ Error getting audio duration: {e.stderr}", file=sys.stderr)
        return None
    except ValueError as e:
        print(f"❌ Error parsing audio duration: {e}", file=sys.stderr)
        return None


def trim_video_to_audio(video_path, audio_path, output_path):
    """
    Trim video to match audio duration and mux audio track.

    Args:
        video_path: Path to source video
        audio_path: Path to audio track
        output_path: Path to save trimmed video with audio

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get audio duration
        duration = get_audio_duration(audio_path)
        if duration is None:
            return False

        print(f"🎬 Trimming video to {duration:.2f}s and adding audio...")

        # FFmpeg command to trim video and add audio
        # -t {duration}: Trim video to audio duration
        # -i {video_path}: Input video
        # -i {audio_path}: Input audio
        # -c:v libx264: H.264 video codec
        # -preset fast: Encoding speed preset
        # -crf 18: Quality (18 = visually lossless)
        # -c:a aac: AAC audio codec
        # -b:a 192k: Audio bitrate
        # -shortest: Stop when shortest stream ends
        # -y: Overwrite output file
        subprocess.run(
            [
                "ffmpeg",
                "-t",
                str(duration),
                "-i",
                video_path,
                "-i",
                audio_path,
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "18",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                "-y",
                output_path,
            ],
            check=True,
            capture_output=True,
        )

        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Error trimming video: {e.stderr.decode()}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ Error trimming video: {e}", file=sys.stderr)
        return False


def concatenate_videos(video_list_file, output_path):
    """
    Concatenate multiple videos into a single MP4 using FFmpeg concat demuxer.

    Args:
        video_list_file: Path to text file with list of videos (FFmpeg concat format)
        output_path: Path to save final video

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        print(f"🎞️  Concatenating 18 clips into final video...")

        # FFmpeg concat demuxer command
        # -f concat: Use concat demuxer
        # -safe 0: Allow absolute paths
        # -i {list}: Input file list
        # -c copy: Copy streams without re-encoding (fast)
        # -y: Overwrite output file
        subprocess.run(
            [
                "ffmpeg",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                video_list_file,
                "-c",
                "copy",
                "-y",
                output_path,
            ],
            check=True,
            capture_output=True,
        )

        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Error concatenating videos: {e.stderr.decode()}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ Error concatenating videos: {e}", file=sys.stderr)
        return False


def get_video_info(video_path):
    """
    Get video file information (duration, size, resolution).

    Args:
        video_path: Path to video file

    Returns:
        dict: Video information
    """
    try:
        # Get duration
        duration_result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        duration = float(duration_result.stdout.strip())

        # Get resolution
        resolution_result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0",
                video_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        width, height = map(int, resolution_result.stdout.strip().split(","))

        # Get file size
        file_size = Path(video_path).stat().st_size

        return {
            "duration": duration,
            "resolution": f"{width}x{height}",
            "file_size": file_size,
            "file_size_mb": file_size / (1024 * 1024),
        }

    except Exception as e:
        print(f"⚠️  Warning: Could not get video info: {e}", file=sys.stderr)
        return None


def assemble_documentary(manifest_path, output_path):
    """
    Assemble final documentary from manifest of video/audio clip pairs.

    Args:
        manifest_path: Path to JSON manifest file
        output_path: Path to save final video

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Read manifest
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        clips = manifest.get("clips", [])

        if not clips:
            print("❌ Error: No clips found in manifest", file=sys.stderr)
            return False

        print(f"\n{'=' * 60}")
        print(f"🎬 Pokémon Natural Geographic - Video Assembly")
        print(f"{'=' * 60}")
        print(f"📋 Total clips: {len(clips)}")
        print(f"💾 Output: {output_path}")
        print(f"{'=' * 60}\n")

        # Create temporary directory for trimmed clips
        temp_dir = tempfile.mkdtemp(prefix="pokemon_assembly_")
        trimmed_clips = []

        try:
            # Step 1: Trim each video to audio duration
            for i, clip in enumerate(clips, 1):
                video_path = clip["video"]
                audio_path = clip["audio"]
                clip_number = clip.get("clip_number", i)

                print(f"\n[{i}/{len(clips)}] Processing clip {clip_number:02d}...")
                print(f"  🎥 Video: {video_path}")
                print(f"  🎙️  Audio: {audio_path}")

                # Verify files exist
                if not Path(video_path).exists():
                    print(f"❌ Error: Video file not found: {video_path}", file=sys.stderr)
                    return False

                if not Path(audio_path).exists():
                    print(f"❌ Error: Audio file not found: {audio_path}", file=sys.stderr)
                    return False

                # Trim video to audio duration
                trimmed_path = Path(temp_dir) / f"clip_{clip_number:02d}_trimmed.mp4"

                if not trim_video_to_audio(video_path, audio_path, str(trimmed_path)):
                    print(f"❌ Error: Failed to trim clip {clip_number}", file=sys.stderr)
                    return False

                trimmed_clips.append(str(trimmed_path))
                print(f"  ✅ Trimmed and synced")

            # Step 2: Create FFmpeg concat file list
            concat_file = Path(temp_dir) / "concat_list.txt"
            with open(concat_file, "w") as f:
                for trimmed_clip in trimmed_clips:
                    # FFmpeg concat format requires absolute paths and proper escaping
                    abs_path = Path(trimmed_clip).resolve()
                    f.write(f"file '{abs_path}'\n")

            print(f"\n{'=' * 60}")
            print(f"🎞️  Step 2: Concatenating all clips...")
            print(f"{'=' * 60}\n")

            # Step 3: Concatenate all trimmed clips
            if not concatenate_videos(str(concat_file), output_path):
                return False

            # Step 4: Report final video info
            print(f"\n{'=' * 60}")
            print(f"✅ Assembly Complete!")
            print(f"{'=' * 60}\n")

            video_info = get_video_info(output_path)
            if video_info:
                print(f"📊 Final Video Specifications:")
                print(
                    f"  Duration: {video_info['duration']:.2f}s ({video_info['duration'] / 60:.1f} minutes)"
                )
                print(f"  Resolution: {video_info['resolution']}")
                print(f"  File Size: {video_info['file_size_mb']:.2f} MB")
                print(f"  Location: {Path(output_path).resolve()}")
            else:
                print(f"📊 Final video saved: {Path(output_path).resolve()}")

            print(f"\n{'=' * 60}\n")

            return True

        finally:
            # Clean up temporary directory
            print(f"🧹 Cleaning up temporary files...")
            shutil.rmtree(temp_dir, ignore_errors=True)

    except FileNotFoundError:
        print(f"❌ Error: Manifest file not found: {manifest_path}", file=sys.stderr)
        return False
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in manifest: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ Error assembling documentary: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Assemble final documentary from video/audio clip pairs using FFmpeg"
    )
    parser.add_argument(
        "--manifest", required=True, help="Path to JSON manifest file with clip pairs"
    )
    parser.add_argument(
        "--output", required=True, help="Output file path (e.g., pikachu_final.mp4)"
    )

    args = parser.parse_args()

    # Verify FFmpeg is installed
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Error: FFmpeg not found", file=sys.stderr)
        print("💡 Install FFmpeg:", file=sys.stderr)
        print("   macOS: brew install ffmpeg", file=sys.stderr)
        print("   Ubuntu: sudo apt-get install ffmpeg", file=sys.stderr)
        print("   Windows: https://ffmpeg.org/download.html", file=sys.stderr)
        sys.exit(1)

    # Verify FFprobe is installed
    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Error: FFprobe not found (should come with FFmpeg)", file=sys.stderr)
        sys.exit(1)

    # Assemble the documentary
    success = assemble_documentary(args.manifest, args.output)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
