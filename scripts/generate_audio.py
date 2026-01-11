#!/usr/bin/env python3
"""
Audio Generator CLI for Pokémon Natural Geographic Documentary
Uses ElevenLabs v3 to generate narrator audio from text prompts.

Usage:
    python generate_audio.py --text "After... the rain... hunger awakens." --output "pikachu/audio/clip_01.mp3"
"""

import argparse
import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in same directory as script
script_dir = Path(__file__).parent
load_dotenv(script_dir / ".env")

# ElevenLabs API Configuration
ELEVENLABS_API_BASE = "https://api.elevenlabs.io"


def generate_audio(
    text,
    output_path,
    api_key,
    voice_id,
    model_id="eleven_multilingual_v2",
    stability=0.40,
    similarity_boost=0.75,
    style=0.12,
):
    """
    Generate narrator audio using ElevenLabs.

    Args:
        text: Narration text with ellipses for pacing
        output_path: Where to save the generated MP3
        api_key: ElevenLabs API key
        voice_id: ElevenLabs voice ID
        model_id: Model to use (default: eleven_multilingual_v2)
        stability: Voice stability 0-1 (default: 0.40)
        similarity_boost: Voice similarity 0-1 (default: 0.75)
        style: Voice style 0-1 (default: 0.12)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Prepare request
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}

        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
                "style": style,
                "use_speaker_boost": True,
            },
        }

        # Make API request
        endpoint = f"{ELEVENLABS_API_BASE}/v1/text-to-speech/{voice_id}"
        print(f"🎙️  Calling ElevenLabs TTS...")
        print(f"📝 Text: {text}")
        print(f"⚙️  Settings: Stability={stability}, Similarity={similarity_boost}, Style={style}")

        response = requests.post(endpoint, headers=headers, json=payload)

        if response.status_code != 200:
            print(f"❌ API Error: {response.status_code}", file=sys.stderr)
            print(f"Response: {response.text}", file=sys.stderr)
            return False

        # Save audio to file
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "wb") as f:
            f.write(response.content)

        print(f"✅ Audio saved successfully: {output_path}")
        return True

    except Exception as e:
        print(f"❌ Error generating audio: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate narrator audio using ElevenLabs v3")
    parser.add_argument(
        "--text",
        required=True,
        help='Narration text with ellipses for pacing (e.g., "After... the rain... hunger awakens.")',
    )
    parser.add_argument(
        "--output", required=True, help="Output file path (e.g., pikachu/audio/clip_01.mp3)"
    )
    parser.add_argument(
        "--model",
        default="eleven_multilingual_v2",
        help="ElevenLabs model ID (default: eleven_multilingual_v2)",
    )
    parser.add_argument(
        "--stability", type=float, default=0.40, help="Voice stability 0-1 (default: 0.40 for 40%%)"
    )
    parser.add_argument(
        "--similarity",
        type=float,
        default=0.75,
        help="Voice similarity boost 0-1 (default: 0.75 for 75%%)",
    )
    parser.add_argument(
        "--style",
        type=float,
        default=0.12,
        help="Voice style exaggeration 0-1 (default: 0.12 for 12%%)",
    )

    args = parser.parse_args()

    # Verify API key exists
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")

    if not api_key:
        print("❌ Error: ELEVENLABS_API_KEY not found in environment variables", file=sys.stderr)
        print("💡 Create a .env file in the scripts/ directory with:", file=sys.stderr)
        print("   ELEVENLABS_API_KEY=your_api_key_here", file=sys.stderr)
        sys.exit(1)

    if not voice_id:
        print("❌ Error: ELEVENLABS_VOICE_ID not found in environment variables", file=sys.stderr)
        print("💡 Add to .env file:", file=sys.stderr)
        print("   ELEVENLABS_VOICE_ID=your_voice_id_here", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"🎙️  Pokémon Natural Geographic - Audio Generator")
    print(f"{'=' * 60}")
    print(f"🗣️  Voice ID: {voice_id}")
    print(f"💾 Output: {args.output}")
    print(f"{'=' * 60}\n")

    # Generate the audio
    success = generate_audio(
        args.text,
        args.output,
        api_key,
        voice_id,
        model_id=args.model,
        stability=args.stability,
        similarity_boost=args.similarity,
        style=args.style,
    )

    print(f"\n{'=' * 60}\n")

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
