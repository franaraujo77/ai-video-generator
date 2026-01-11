#!/usr/bin/env python3
"""
Sound Effects Generator CLI for Pokémon Natural Geographic Documentary
Uses ElevenLabs Sound Effects API to generate ambient background audio from text prompts.

Usage:
    python generate_sound_effects.py --text "Abandoned power station ambience with rain and thunder" --output "haunter/audio/background_ambient.mp3"
"""

import argparse
import os
import sys
import subprocess
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in same directory as script
script_dir = Path(__file__).parent
load_dotenv(script_dir / ".env")

# ElevenLabs API Configuration
ELEVENLABS_API_BASE = "https://api.elevenlabs.io"


def generate_sound_effect(
    text,
    output_path,
    api_key,
    duration_seconds=10.0,
    prompt_influence=0.3,
    output_format="mp3_44100_128",
):
    """
    Generate ambient sound effect using ElevenLabs Sound Effects API.

    Args:
        text: Description of the sound effect to generate
        output_path: Where to save the generated MP3
        api_key: ElevenLabs API key
        duration_seconds: Duration of sound effect (0.5-30 seconds, default: 10.0)
        prompt_influence: How strictly to follow prompt 0-1 (default: 0.3)
        output_format: Audio format (default: mp3_44100_128)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Prepare request
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}

        payload = {
            "text": text,
            "duration_seconds": duration_seconds,
            "prompt_influence": prompt_influence,
        }

        # Make API request
        endpoint = f"{ELEVENLABS_API_BASE}/v1/sound-generation"
        params = {"output_format": output_format}

        print(f"🔊 Calling ElevenLabs Sound Effects API...")
        print(f"📝 Prompt: {text}")
        print(f"⏱️  Duration: {duration_seconds}s")
        print(f"⚙️  Prompt Influence: {prompt_influence}")

        response = requests.post(endpoint, headers=headers, json=payload, params=params)

        if response.status_code != 200:
            print(f"❌ API Error: {response.status_code}", file=sys.stderr)
            print(f"Response: {response.text}", file=sys.stderr)
            return False

        # Save audio to file
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "wb") as f:
            f.write(response.content)

        file_size = output_path.stat().st_size / 1024  # KB
        print(f"✅ Sound effect saved successfully: {output_path}")
        print(f"📦 File size: {file_size:.1f} KB")
        return True

    except Exception as e:
        print(f"❌ Error generating sound effect: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return False


def normalize_audio(input_path, target_lufs=-30.0):
    """
    Normalize audio to consistent volume level using ffmpeg.

    Args:
        input_path: Path to the audio file to normalize
        target_lufs: Target loudness in LUFS (default: -30.0 for background effects)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        input_path = Path(input_path)
        temp_path = input_path.parent / f"{input_path.stem}_temp{input_path.suffix}"

        print(f"🔧 Normalizing audio to {target_lufs} LUFS...")

        # Use ffmpeg loudnorm filter for consistent volume
        cmd = [
            "ffmpeg",
            "-i",
            str(input_path),
            "-af",
            f"loudnorm=I={target_lufs}:TP=-2:LRA=7",
            "-ar",
            "44100",
            "-y",  # Overwrite output file
            str(temp_path),
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0:
            print(f"❌ Normalization failed: {result.stderr}", file=sys.stderr)
            return False

        # Replace original with normalized version
        temp_path.replace(input_path)

        print(f"✅ Audio normalized successfully")
        return True

    except Exception as e:
        print(f"❌ Error normalizing audio: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate ambient sound effects using ElevenLabs Sound Effects API"
    )
    parser.add_argument(
        "--text",
        required=True,
        help='Description of the sound effect (e.g., "Abandoned power station with rain and thunder")',
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path (e.g., haunter/audio/background_ambient.mp3)",
    )
    parser.add_argument(
        "--duration", type=float, default=10.0, help="Duration in seconds (0.5-30, default: 10.0)"
    )
    parser.add_argument(
        "--prompt-influence",
        type=float,
        default=0.3,
        help="Prompt adherence 0-1 (default: 0.3, higher = stricter)",
    )
    parser.add_argument(
        "--format", default="mp3_44100_128", help="Output format (default: mp3_44100_128)"
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        default=True,
        help="Normalize audio volume for consistent levels (default: True)",
    )
    parser.add_argument(
        "--no-normalize", action="store_false", dest="normalize", help="Skip audio normalization"
    )
    parser.add_argument(
        "--target-volume",
        type=float,
        default=-30.0,
        help="Target volume in LUFS for normalization (default: -30.0 for background effects)",
    )

    args = parser.parse_args()

    # Validate duration
    if args.duration < 0.5 or args.duration > 30.0:
        print("❌ Error: Duration must be between 0.5 and 30 seconds", file=sys.stderr)
        sys.exit(1)

    # Validate prompt influence
    if args.prompt_influence < 0 or args.prompt_influence > 1:
        print("❌ Error: Prompt influence must be between 0 and 1", file=sys.stderr)
        sys.exit(1)

    # Verify API key exists
    api_key = os.getenv("ELEVENLABS_API_KEY")

    if not api_key:
        print("❌ Error: ELEVENLABS_API_KEY not found in environment variables", file=sys.stderr)
        print("💡 Create a .env file in the scripts/ directory with:", file=sys.stderr)
        print("   ELEVENLABS_API_KEY=your_api_key_here", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"🔊 Pokémon Natural Geographic - Sound Effects Generator")
    print(f"{'=' * 60}")
    print(f"💾 Output: {args.output}")
    print(f"{'=' * 60}\n")

    # Generate the sound effect
    success = generate_sound_effect(
        args.text,
        args.output,
        api_key,
        duration_seconds=args.duration,
        prompt_influence=args.prompt_influence,
        output_format=args.format,
    )

    # Normalize audio if requested
    if success and args.normalize:
        success = normalize_audio(args.output, target_lufs=args.target_volume)

    print(f"\n{'=' * 60}\n")

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
