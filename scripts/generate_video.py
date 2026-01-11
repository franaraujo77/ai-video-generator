#!/usr/bin/env python3
"""
Video Generator CLI for Pokémon Natural Geographic Documentary
Uses KIE.ai Kling 2.5 API to animate photorealistic seed images into 10-second clips.

Usage:
    python generate_video.py --image "path/to/character.png" --prompt "MOTION_DESCRIPTION" --output "path/to/output.mp4"
    python generate_video.py --image "path/to/character.png" --environment "path/to/environment.png" --prompt "MOTION" --output "output.mp4"
"""

import argparse
import os
import sys
import time
import requests
import json as jsonlib
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in same directory as script
script_dir = Path(__file__).parent
load_dotenv(script_dir / ".env")

# KIE.ai API Configuration
KIE_API_BASE = "https://api.kie.ai/api/v1"


def upload_image_to_catbox(image_path):
    """
    Upload image to catbox.moe (free, reliable file hosting - no API key needed).

    Args:
        image_path: Path to local image file

    Returns:
        str: Public URL of uploaded image
    """
    image_path = Path(image_path)

    upload_url = "https://catbox.moe/user/api.php"

    with open(image_path, "rb") as f:
        files = {"fileToUpload": (image_path.name, f, "image/png")}
        data = {"reqtype": "fileupload"}

        print(f"📤 Uploading {image_path.name} to catbox.moe...")
        response = requests.post(upload_url, files=files, data=data)

        if response.status_code != 200:
            print(f"❌ Upload failed: {response.status_code}", file=sys.stderr)
            print(f"Response: {response.text}", file=sys.stderr)
            return None

        # catbox.moe returns the URL as plain text
        image_url = response.text.strip()

        if not image_url or not image_url.startswith("http"):
            print(f"❌ Invalid URL in response: {image_url}", file=sys.stderr)
            return None

        print(f"✅ Image uploaded: {image_url}")
        return image_url


def generate_video(image_path, prompt, output_path, api_key, environment_path=None):
    """
    Generate a 10-second video from image using KIE.ai Kling 2.5.

    Args:
        image_path: Path to main seed image (character/subject)
        prompt: Text describing the desired motion/animation
        output_path: Where to save the generated MP4
        api_key: KIE.ai API key
        environment_path: Optional path to environment reference image (currently ignored - Kling uses single image)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Upload main image to catbox.moe and get public URL
        main_image_url = upload_image_to_catbox(image_path)
        if not main_image_url:
            return False

        # Note: If environment_path provided, we ignore it for now
        # Kling 2.5 API uses single image_url parameter
        if environment_path:
            print(
                "⚠️  Note: Environment image provided but Kling 2.5 uses single image input",
                file=sys.stderr,
            )
            print("⚠️  Only character image will be used for generation", file=sys.stderr)

        # Prepare request for Kling 2.5
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

        payload = {
            "model": "kling/v2-5-turbo-image-to-video-pro",
            "callBackUrl": "",  # Empty string - we'll poll instead
            "input": {
                "prompt": prompt,
                "image_url": main_image_url,
                "duration": "10",  # 10 seconds
                "negative_prompt": "blur, distort, and low quality",
                "cfg_scale": 0.5,
            },
        }

        # Make API request
        endpoint = f"{KIE_API_BASE}/jobs/createTask"
        print(f"🎬 Calling KIE.ai Kling 2.5 Pro...")
        print(f"📝 Prompt: {prompt}")
        print(f"🖼️  Image: {main_image_url}")
        print(f"⏱️  Duration: 10 seconds")

        response = requests.post(endpoint, headers=headers, data=jsonlib.dumps(payload))

        if response.status_code != 200:
            print(f"❌ API Error: {response.status_code}", file=sys.stderr)
            print(f"Response: {response.text}", file=sys.stderr)
            return False

        try:
            result = response.json()
        except Exception as e:
            print(f"❌ Failed to parse JSON response: {e}", file=sys.stderr)
            print(f"Raw response: {response.text}", file=sys.stderr)
            return False

        print(f"📋 API Response: {result}")

        # Get task ID from Kling response
        data = result.get("data", {})
        task_id = data.get("taskId")

        if not task_id:
            print(f"❌ No task ID in response: {result}", file=sys.stderr)
            return False

        print(f"✅ Task created: {task_id}")
        print(f"⏳ Waiting for video generation...")

        # Poll for completion
        video_url = poll_task_status(task_id, api_key)

        if not video_url:
            return False

        # Download video
        print(f"⬇️  Downloading video...")
        download_video(video_url, output_path)

        print(f"✅ Video saved successfully: {output_path}")
        return True

    except Exception as e:
        print(f"❌ Error generating video: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return False


def poll_task_status(task_id, api_key, max_wait=600):
    """
    Poll KIE.ai Kling task until completion.

    Args:
        task_id: Task ID from initial request
        api_key: KIE.ai API key
        max_wait: Maximum seconds to wait (default: 10 minutes)

    Returns:
        str: Video URL if successful, None otherwise
    """
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    endpoint = f"{KIE_API_BASE}/jobs/recordInfo"

    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            response = requests.get(endpoint, headers=headers, params={"taskId": task_id})

            if response.status_code == 200:
                result = response.json()

                # Check response code
                if result.get("code") != 200:
                    error_msg = result.get("message", "Unknown error")
                    print(f"❌ API error: {error_msg}", file=sys.stderr)
                    return None

                # Get task data
                data = result.get("data", {})
                state = data.get("state")

                if state == "success":
                    # Parse resultJson which is a JSON string
                    result_json_str = data.get("resultJson", "{}")
                    try:
                        result_json = jsonlib.loads(result_json_str)
                        result_urls = result_json.get("resultUrls", [])
                        if result_urls and len(result_urls) > 0:
                            video_url = result_urls[0]
                            return video_url
                        else:
                            print(
                                f"❌ Video generation succeeded but no URL in resultUrls: {result_json}",
                                file=sys.stderr,
                            )
                            return None
                    except Exception as e:
                        print(f"❌ Failed to parse resultJson: {e}", file=sys.stderr)
                        print(f"Raw resultJson: {result_json_str}", file=sys.stderr)
                        return None
                elif state == "failed":
                    print(f"❌ Video generation failed: {data}", file=sys.stderr)
                    return None
                elif state in ["pending", "processing"]:
                    print(f"⏳ {state.capitalize()}... ({int(time.time() - start_time)}s elapsed)")
                else:
                    print(f"⏳ Status: {state}... ({int(time.time() - start_time)}s elapsed)")

            time.sleep(5)  # Poll every 5 seconds

        except Exception as e:
            print(f"⚠️  Polling error: {e}", file=sys.stderr)
            time.sleep(5)

    print(f"❌ Timeout: Video generation exceeded {max_wait}s", file=sys.stderr)
    return None


def download_video(url, output_path):
    """
    Download video from URL to local file.

    Args:
        url: Video URL
        output_path: Local path to save video
    """
    response = requests.get(url, stream=True)
    response.raise_for_status()

    # Ensure output directory exists
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def main():
    parser = argparse.ArgumentParser(
        description="Generate 10-second video clips using KIE.ai Kling 2.5"
    )
    parser.add_argument(
        "--image", required=True, help="Path to main seed image (character/subject)"
    )
    parser.add_argument(
        "--environment",
        default=None,
        help="Optional path to environment reference image (currently not used by Kling 2.5)",
    )
    parser.add_argument(
        "--prompt", required=True, help="Text describing the motion/animation to apply to the image"
    )
    parser.add_argument(
        "--output", required=True, help="Output file path (e.g., pikachu/videos/clip_01.mp4)"
    )

    args = parser.parse_args()

    # Verify API key exists
    api_key = os.getenv("KIE_API_KEY")

    if not api_key:
        print("❌ Error: KIE_API_KEY not found in environment variables", file=sys.stderr)
        print("💡 Create a .env file in the scripts/ directory with:", file=sys.stderr)
        print("   KIE_API_KEY=your_api_key_here", file=sys.stderr)
        sys.exit(1)

    # Verify main image exists
    if not Path(args.image).exists():
        print(f"❌ Error: Image file not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    # Verify environment image exists if provided
    if args.environment and not Path(args.environment).exists():
        print(f"❌ Error: Environment image not found: {args.environment}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"🎬 Pokémon Natural Geographic - Video Generator")
    print(f"{'=' * 60}")
    print(f"🖼️  Character: {args.image}")
    if args.environment:
        print(f"🌄 Environment: {args.environment} (for reference only)")
    print(f"💾 Output: {args.output}")
    print(f"🎥 Model: Kling 2.5 Pro (10 seconds @ 1080p)")
    print(f"{'=' * 60}\n")

    # Generate the video
    success = generate_video(
        args.image, args.prompt, args.output, api_key, environment_path=args.environment
    )

    print(f"\n{'=' * 60}\n")

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
