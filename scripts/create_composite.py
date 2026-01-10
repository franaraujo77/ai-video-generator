#!/usr/bin/env python3
"""
Composite Image Generator for Pokémon Natural Geographic
Combines character and environment assets into single seed images for Kling 2.5
"""

import os
from pathlib import Path
from PIL import Image
import argparse


def create_composite(character_path: str, environment_path: str, output_path: str, character_scale: float = 1.0):
    """
    Create a composite image by overlaying character on environment.
    Forces output to 1920x1080 (16:9) for YouTube compatibility.

    Args:
        character_path: Path to character PNG (with transparency)
        environment_path: Path to environment background PNG
        output_path: Path to save composite PNG
        character_scale: Scale factor for character (1.0 = 100%, 0.5 = 50%, etc.)
    """
    # YouTube standard dimensions (16:9)
    TARGET_WIDTH = 1920
    TARGET_HEIGHT = 1080

    # Load images
    environment = Image.open(environment_path).convert("RGBA")
    character = Image.open(character_path).convert("RGBA")

    # Get original dimensions
    env_width, env_height = environment.size
    char_width, char_height = character.size

    # Resize environment to 1920x1080 (16:9) by cropping or padding
    env_aspect = env_width / env_height
    target_aspect = TARGET_WIDTH / TARGET_HEIGHT

    if env_aspect > target_aspect:
        # Environment is wider than 16:9 - crop width
        new_env_height = TARGET_HEIGHT
        new_env_width = int(env_height * target_aspect)
        # Scale to target height first
        environment = environment.resize((int(env_width * TARGET_HEIGHT / env_height), TARGET_HEIGHT), Image.Resampling.LANCZOS)
        # Crop to target width (center crop)
        left = (environment.size[0] - TARGET_WIDTH) // 2
        environment = environment.crop((left, 0, left + TARGET_WIDTH, TARGET_HEIGHT))
    else:
        # Environment is taller than 16:9 or exact - scale and pad if needed
        scale_factor = TARGET_WIDTH / env_width
        new_env_width = TARGET_WIDTH
        new_env_height = int(env_height * scale_factor)
        environment = environment.resize((new_env_width, new_env_height), Image.Resampling.LANCZOS)

        if new_env_height < TARGET_HEIGHT:
            # Need to pad height
            padded = Image.new("RGBA", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 255))
            y_offset = (TARGET_HEIGHT - new_env_height) // 2
            padded.paste(environment, (0, y_offset))
            environment = padded
        elif new_env_height > TARGET_HEIGHT:
            # Need to crop height (center crop)
            top = (new_env_height - TARGET_HEIGHT) // 2
            environment = environment.crop((0, top, TARGET_WIDTH, top + TARGET_HEIGHT))

    # Scale character if needed
    if character_scale != 1.0:
        new_width = int(char_width * character_scale)
        new_height = int(char_height * character_scale)
        character = character.resize((new_width, new_height), Image.Resampling.LANCZOS)
        char_width, char_height = new_width, new_height

    # Center character on 1920x1080 canvas
    x_offset = (TARGET_WIDTH - char_width) // 2
    y_offset = (TARGET_HEIGHT - char_height) // 2

    # Create composite
    composite = environment.copy()
    composite.paste(character, (x_offset, y_offset), character)  # Use character's alpha as mask

    # Convert to RGB for final output
    final = Image.new("RGB", composite.size, (0, 0, 0))
    final.paste(composite, mask=composite.split()[3])  # Use alpha channel as mask

    # Create output directory if needed
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Save
    final.save(output_path, "PNG")
    print(f"✅ Composite saved: {output_path} (1920x1080 16:9)")
    print(f"   - Environment: {os.path.basename(environment_path)}")
    print(f"   - Character: {os.path.basename(character_path)} (scale: {character_scale})")


def main():
    parser = argparse.ArgumentParser(description="Create composite image from character + environment")
    parser.add_argument("--character", required=True, help="Path to character PNG")
    parser.add_argument("--environment", required=True, help="Path to environment PNG")
    parser.add_argument("--output", required=True, help="Path to save composite PNG")
    parser.add_argument("--scale", type=float, default=1.0, help="Character scale factor (default: 1.0)")

    args = parser.parse_args()

    # Validate inputs exist
    if not os.path.exists(args.character):
        print(f"❌ Character file not found: {args.character}")
        return

    if not os.path.exists(args.environment):
        print(f"❌ Environment file not found: {args.environment}")
        return

    # Create output directory if needed
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Create composite
    create_composite(args.character, args.environment, args.output, args.scale)


if __name__ == "__main__":
    main()
