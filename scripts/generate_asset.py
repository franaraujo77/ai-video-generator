#!/usr/bin/env python3
"""
Asset Generator CLI for Pokémon Natural Geographic Documentary
Uses Google Gemini 2.5 Flash Image to generate photorealistic assets.

Usage:
    python generate_asset.py --prompt "COMPLETE_PROMPT" --output "path/to/output.png"

Note: The prompt should already include the Global Atmosphere Block prepended by the calling agent.
"""

import argparse
import os
import sys
from io import BytesIO
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image

# Load environment variables from .env file in same directory as script
script_dir = Path(__file__).parent
load_dotenv(script_dir / ".env")


def create_composite(character_path, environment_path, output_path):
    """
    Create a composite image by centering character on environment background.

    Args:
        character_path: Path to character PNG (with transparency)
        environment_path: Path to environment background PNG
        output_path: Path to save composite PNG

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        print(f"🎨 Creating composite image...")
        print(f"   Character: {character_path}")
        print(f"   Environment: {environment_path}")

        # Load images
        environment = Image.open(environment_path).convert("RGBA")
        character = Image.open(character_path).convert("RGBA")

        # Get dimensions
        env_width, env_height = environment.size
        char_width, char_height = character.size

        print(f"📐 Environment: {env_width}x{env_height}")
        print(f"📐 Character: {char_width}x{char_height}")

        # Center character on environment
        x_offset = (env_width - char_width) // 2
        y_offset = (env_height - char_height) // 2

        # Create composite
        composite = environment.copy()
        composite.paste(character, (x_offset, y_offset), character)  # Use character's alpha as mask

        # Convert to RGB for final output
        final = Image.new("RGB", composite.size, (0, 0, 0))
        final.paste(composite, mask=composite.split()[3])  # Use alpha channel as mask

        # Ensure output directory exists
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save
        final.save(output_path, "PNG")
        print(f"✅ Composite saved: {output_path}")
        print(f"📐 Final dimensions: {final.size[0]}x{final.size[1]}")

        return True

    except Exception as e:
        print(f"❌ Error creating composite: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return False


def create_split_vertical(top_image_path, bottom_image_path, output_path):
    """
    Create a vertical split composite showing two images (top and bottom halves).

    Args:
        top_image_path: Path to image for top half
        bottom_image_path: Path to image for bottom half
        output_path: Path to save split composite PNG

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        print(f"🎨 Creating vertical split composite...")
        print(f"   Top: {top_image_path}")
        print(f"   Bottom: {bottom_image_path}")

        # Load images
        top_img = Image.open(top_image_path).convert("RGB")
        bottom_img = Image.open(bottom_image_path).convert("RGB")

        # Get dimensions
        top_width, top_height = top_img.size
        bottom_width, bottom_height = bottom_img.size

        print(f"📐 Top image: {top_width}x{top_height}")
        print(f"📐 Bottom image: {bottom_width}x{bottom_height}")

        # Use the widest width and sum the heights
        final_width = max(top_width, bottom_width)
        final_height = top_height + bottom_height

        # Create final canvas
        final = Image.new("RGB", (final_width, final_height), (0, 0, 0))

        # Paste top image (centered if narrower)
        top_x_offset = (final_width - top_width) // 2
        final.paste(top_img, (top_x_offset, 0))

        # Paste bottom image (centered if narrower)
        bottom_x_offset = (final_width - bottom_width) // 2
        final.paste(bottom_img, (bottom_x_offset, top_height))

        # Ensure output directory exists
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save
        final.save(output_path, "PNG")
        print(f"✅ Vertical split composite saved: {output_path}")
        print(f"📐 Final dimensions: {final_width}x{final_height}")

        return True

    except Exception as e:
        print(f"❌ Error creating vertical split: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return False


def generate_image(prompt, output_path, api_key, reference_image_paths=None):
    """
    Generate an image using Gemini 3 Pro Image API.

    Args:
        prompt: Complete prompt including atmosphere block
        output_path: Where to save the generated PNG
        api_key: Gemini API key
        reference_image_paths: Optional list of paths to reference images for variations (image-to-image)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Configure Gemini API
        genai.configure(api_key=api_key)

        if reference_image_paths:
            print(f"🎨 Generating image variation with Gemini 3 Pro Image...")
            print(f"🖼️  Reference images ({len(reference_image_paths)}):")
            for i, path in enumerate(reference_image_paths, 1):
                print(f"     {i}. {path}")
        else:
            print(f"🎨 Generating image with Gemini 3 Pro Image...")

        print(f"📝 Prompt length: {len(prompt)} characters")

        # Initialize model
        model = genai.GenerativeModel("gemini-3-pro-image-preview")

        # Prepare content for generation
        if reference_image_paths:
            # Load all reference images
            reference_images = []
            for path in reference_image_paths:
                img = Image.open(path)
                reference_images.append(img)
                print(f"📐 Reference dimensions ({path}): {img.size[0]}x{img.size[1]}")

            # Generate with reference images + text prompt
            # API format: [image1, image2, ..., prompt]
            content = reference_images + [prompt]
            response = model.generate_content(content)
        else:
            # Generate from text prompt only
            response = model.generate_content(prompt)

        # Extract image data from response
        if not response.parts:
            print("❌ Error: No parts in API response", file=sys.stderr)
            return False

        # Look for image data in response
        image_data = None
        for part in response.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                image_data = part.inline_data.data
                break

        if not image_data:
            print("❌ Error: No image data in API response", file=sys.stderr)
            print(f"Response: {response}", file=sys.stderr)
            return False

        # Convert to PIL Image and save
        image = Image.open(BytesIO(image_data))

        # Ensure output directory exists
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save as PNG
        image.save(output_path, "PNG")
        print(f"✅ Image saved successfully: {output_path}")
        print(f"📐 Dimensions: {image.size[0]}x{image.size[1]}")

        return True

    except Exception as e:
        print(f"❌ Error generating image: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate photorealistic Pokémon documentary assets using Gemini 2.5 Flash Image or create composites"
    )
    parser.add_argument(
        "--prompt",
        required=False,
        help="Complete asset generation prompt (should already include Global Atmosphere Block)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path (e.g., pikachu/assets/characters/pikachu_walking.png)",
    )
    parser.add_argument(
        "--reference-image",
        action="append",
        required=False,
        help="Optional reference image(s) for variations (image-to-image generation). Can be specified multiple times for multi-reference generation. Use for character variations based on core assets.",
    )
    parser.add_argument(
        "--character",
        required=False,
        help="Character image path for composite mode (requires --environment)",
    )
    parser.add_argument(
        "--environment",
        required=False,
        help="Environment image path for composite mode (requires --character)",
    )
    parser.add_argument(
        "--split-vertical",
        nargs=2,
        metavar=("TOP_IMAGE", "BOTTOM_IMAGE"),
        required=False,
        help="Create vertical split composite with two images (top and bottom)",
    )

    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"🎬 Pokémon Natural Geographic - Asset Generator")
    print(f"{'=' * 60}")
    print(f"💾 Output: {args.output}")

    # Check if split-vertical mode
    if args.split_vertical:
        print(f"🖼️  Mode: Vertical Split Composite")
        print(f"{'=' * 60}\n")
        success = create_split_vertical(args.split_vertical[0], args.split_vertical[1], args.output)
    # Check if composite mode
    elif args.character and args.environment:
        # Composite mode
        print(f"🖼️  Mode: Composite")
        print(f"{'=' * 60}\n")
        success = create_composite(args.character, args.environment, args.output)
    elif args.character or args.environment:
        # Error: only one specified
        print(
            "❌ Error: Both --character and --environment required for composite mode",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        # Generation mode
        if not args.prompt:
            print("❌ Error: --prompt required for generation mode", file=sys.stderr)
            sys.exit(1)

        # Verify API key exists
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print(
                "❌ Error: GEMINI_API_KEY not found in environment variables",
                file=sys.stderr,
            )
            print("💡 Create a .env file in the scripts/ directory with:", file=sys.stderr)
            print("   GEMINI_API_KEY=your_api_key_here", file=sys.stderr)
            sys.exit(1)

        print(f"📝 Prompt length: {len(args.prompt)} characters")
        if args.reference_image:
            if len(args.reference_image) == 1:
                print(f"🖼️  Reference: {args.reference_image[0]}")
            else:
                print(f"🖼️  References ({len(args.reference_image)}):")
                for i, ref in enumerate(args.reference_image, 1):
                    print(f"     {i}. {ref}")
        print(f"{'=' * 60}\n")

        # Generate the image
        success = generate_image(args.prompt, args.output, api_key, args.reference_image)

    print(f"\n{'=' * 60}\n")

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
