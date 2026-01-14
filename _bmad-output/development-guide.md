# Development Guide

## Prerequisites
- **Python:** 3.10 or higher
- **Package Manager:** `uv` (recommended for speed) or `pip`
- **FFmpeg:** Installed and added to system PATH (required for video assembly)

## Installation

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Sync dependencies
uv sync
```

## Environment Configuration
Create a `.env` file in the `scripts/` directory by copying the example:

```bash
cp scripts/.env.example scripts/.env
```

Populate the following keys:
- `GEMINI_API_KEY`: For image generation.
- `KIE_API_KEY`: For Kling video generation.
- `ELEVENLABS_API_KEY`: For voiceover/SFX.
- `ELEVENLABS_VOICE_ID`: Target voice ID.

## Common Tasks

### 1. Generating Assets
Use the `generate_asset.py` script to create raw images.

```bash
python scripts/generate_asset.py --prompt "Hyper-realistic Pikachu..." --output "pikachu/assets/char.png"
```

### 2. Creating Composites
Combine character and environment images into a 16:9 frame for video generation.

```bash
python scripts/create_composite.py --character "path/to/char.png" --environment "path/to/env.png" --output "path/to/comp.png"
```

### 3. Generating Video
Animate the composite using Kling.

```bash
python scripts/generate_video.py --image "path/to/comp.png" --prompt "Pikachu walking..." --output "path/to/video.mp4"
```

### 4. Assembling Final Cut
Stitch video and audio clips together.

```bash
python scripts/assemble_video.py --manifest "path/to/manifest.json" --output "path/to/final.mp4"
```

## Testing
There are no formal unit tests configured for this project as it relies on external generative AI services. Verification is done by inspecting the generated media files in the workspace folders.
