# Comprehensive Analysis: AI Video Generator CLI Tools

## Overview

This document provides an exhaustive analysis of all CLI automation scripts in the ai-video-generator project.

---

## CLI Tools Inventory

### Entry Points (7 Scripts)

| Script | Purpose | Primary API/Tool | Input | Output |
|--------|---------|------------------|-------|--------|
| `generate_asset.py` | Image generation | Gemini 2.5 Flash | Text prompt | PNG image |
| `generate_video.py` | Video animation | KIE.ai Kling 2.5 | Image + motion prompt | MP4 video |
| `generate_audio.py` | Narration synthesis | ElevenLabs v3 | Text script | MP3 audio |
| `generate_sound_effects.py` | Sound effects | ElevenLabs SFX | Effect description | WAV audio |
| `assemble_video.py` | Video assembly | FFmpeg | Manifest JSON | Final MP4 |
| `create_composite.py` | Image compositing | Pillow | Character + Environment | 1920x1080 PNG |
| `create_split_screen.py` | Split-screen compositor | Pillow | Two images | 1920x1080 PNG (hardcoded) |

---

## Detailed Script Analysis

### 1. generate_asset.py

**Purpose:** Multi-function tool for image generation and compositing

**Modes:**
1. **Generation Mode:** Create images from text prompts using Gemini
2. **Composite Mode:** Overlay character on environment
3. **Split Vertical Mode:** Create vertical split composites

**CLI Interface:**
```bash
# Generation mode
python generate_asset.py --prompt "TEXT" --output "path.png"

# With reference images (image-to-image variations)
python generate_asset.py --prompt "TEXT" --reference-image "ref1.png" --reference-image "ref2.png" --output "path.png"

# Composite mode
python generate_asset.py --character "char.png" --environment "env.png" --output "composite.png"

# Split vertical mode
python generate_asset.py --split-vertical top.png bottom.png --output "split.png"
```

**Dependencies:**
- `google-generativeai` - Gemini API SDK
- `python-dotenv` - Environment variables
- `pillow` - Image manipulation

**Functions:**
- `generate_image()` - Call Gemini API for image generation
- `create_composite()` - Layer character on environment
- `create_split_vertical()` - Create vertical split image

**API Calls:**
- Gemini 3 Pro Image Preview (`gemini-3-pro-image-preview`)

**Environment Variables:**
- `GEMINI_API_KEY` (required for generation mode)

**Exit Codes:**
- 0: Success
- 1: Failure (missing API key, API error, file error)

---

### 2. create_composite.py

**Purpose:** Create 16:9 (1920x1080) composite images for YouTube-ready video generation

**Key Feature:** **Enforces 1920x1080 output** - critical for Kling 2.5 compatibility

**CLI Interface:**
```bash
python create_composite.py \
  --character "path/to/char.png" \
  --environment "path/to/env.png" \
  --output "path/to/composite.png" \
  --scale 1.0  # Optional character scaling
```

**Technical Details:**
- **Target Dimensions:** 1920x1080 (16:9 aspect ratio)
- **Environment Handling:** Crops or pads to fit 16:9
- **Character Handling:** Centers on canvas with optional scaling
- **Alpha Channel:** Preserves transparency during compositing

**Algorithm:**
1. Load environment and character images
2. Resize/crop environment to 1920x1080
3. Optionally scale character
4. Center character on environment
5. Composite with alpha blending
6. Convert to RGB and save as PNG

**Dependencies:**
- `pillow` only (no API calls)

**Use Case:** Preparing seed images for video generation (SOP 03.5)

---

### 3. create_split_screen.py

**Purpose:** Create horizontal split-screen composite (specific to Haunter project)

**Status:** **Hardcoded for Haunter** - not a general-purpose tool

**Hardcoded Paths:**
```python
magneton_env = "haunter/assets/environments/env_generator_room_lit.png"
magneton_char = "haunter/assets/characters/magneton_hovering_standard_core.png"
haunter_env = "haunter/assets/environments/env_flooded_basement_poisoned.png"
haunter_char = "haunter/assets/characters/haunter_victorious_floating.png"
```

**Output:** `haunter/assets/composites/clip_15_split.png`

**Layout:**
- Left half (960x1080): Magneton in generator room
- Right half (960x1080): Haunter in poisoned basement
- Final: 1920x1080 (16:9)

**Note:** This script is project-specific and not reusable without modification.

---

### 4. generate_video.py

**Purpose:** Animate static images into 10-second video clips using Kling 2.5

**CLI Interface:**
```bash
python generate_video.py \
  --image "path/to/composite.png" \
  --prompt "MOTION_DESCRIPTION" \
  --output "path/to/video.mp4"
```

**Process Flow:**
1. Upload image to catbox.moe (free hosting)
2. Get public image URL
3. Call KIE.ai Kling 2.5 API with image URL + motion prompt
4. Poll for task completion (with timeout)
5. Download generated MP4
6. Save to output path

**API Details:**
- **Service:** KIE.ai (Kling 2.5 wrapper)
- **Endpoint:** `https://api.kie.ai/api/v1`
- **Authentication:** API Key + JWT token
- **Duration:** 10 seconds per video (not configurable)
- **Timeout:** 10 minutes (adjustable)

**Dependencies:**
- `requests` - HTTP client
- `pyjwt` - JWT auth
- `python-dotenv` - Config

**Environment Variables:**
- `KIE_API_KEY` (required)

**Special Features:**
- Uses catbox.moe for free image hosting (no API key needed)
- Polls task status every 10 seconds
- Handles API rate limits and retries

**Constraints:**
- Requires 1920x1080 (16:9) images for YouTube output
- Fixed 10-second duration

---

### 5. generate_audio.py

**Purpose:** Generate narration audio using ElevenLabs voice synthesis

**CLI Interface:**
```bash
python generate_audio.py \
  --text "Narration text with... ellipses for pacing" \
  --output "path/to/audio.mp3"
```

**API Details:**
- **Service:** ElevenLabs v3
- **Model:** `eleven_multilingual_v3` (enhanced multilingual)
- **Voice Settings:**
  - Stability: 40%
  - Similarity: 75%
  - Style: 12%

**Environment Variables:**
- `ELEVENLABS_API_KEY` (required)
- `ELEVENLABS_VOICE_ID` (required for voice selection)

**Output Format:** MP3 audio file

**Special Features:**
- Supports ellipses (...) for natural pacing
- Multilingual voice model
- Typically generates 6-8 second clips

**Dependencies:**
- `requests` - HTTP client
- `python-dotenv` - Config

---

### 6. generate_sound_effects.py

**Purpose:** Generate atmospheric sound effects using ElevenLabs

**CLI Interface:**
```bash
python generate_sound_effects.py \
  --prompt "Rain falling on leaves, distant thunder" \
  --output "path/to/sfx.wav"
```

**API Details:**
- **Service:** ElevenLabs Sound Effects API
- **Duration:** Typically 5-10 seconds
- **Format:** WAV audio

**Environment Variables:**
- `ELEVENLABS_API_KEY` (required)

**Use Cases:**
- Atmospheric sounds (rain, wind, electricity)
- Environmental audio (footsteps, rustling, impacts)
- Background ambience

**Dependencies:**
- `requests` - HTTP client
- `python-dotenv` - Config

---

### 7. assemble_video.py

**Purpose:** Trim, sync, and concatenate all clips into final 90-second video

**CLI Interface:**
```bash
python assemble_video.py \
  --manifest "path/to/manifest.json" \
  --output "path/to/final.mp4"
```

**Manifest Format (JSON):**
```json
{
  "clips": [
    {
      "clip_id": "clip_01",
      "video": "path/to/video.mp4",
      "audio": "path/to/audio.mp3",
      "sfx": "path/to/sfx.wav"
    }
  ]
}
```

**Process Flow:**
1. Read manifest JSON
2. For each clip:
   - Probe audio file with FFprobe to get duration
   - Trim 10-second video to match audio duration
   - Mix narration + SFX on separate audio tracks
   - Save trimmed clip
3. Concatenate all clips with FFmpeg
4. Output final MP4

**FFmpeg Operations:**
- **Trim:** Adjust video length to match audio
- **Mix:** Combine narration and SFX tracks
- **Concat:** Join clips with hard cuts (no transitions)
- **Encode:** H.264 video, AAC audio

**Output Specs:**
- **Resolution:** 1920x1080 (16:9)
- **Video Codec:** H.264
- **Audio Codec:** AAC
- **Duration:** ~90-120 seconds (18 clips × 5-8s each)

**Dependencies:**
- `ffmpeg` (system binary - must be in PATH)
- `ffprobe` (for audio duration detection)

**Special Features:**
- Automatic video trimming based on audio length
- Dual audio track mixing
- Progress reporting

---

## Configuration Management

### Environment Variables Pattern

All scripts use `.env` file in `scripts/` directory:

```bash
scripts/.env
```

**Loading Pattern:**
```python
from pathlib import Path
from dotenv import load_dotenv

script_dir = Path(__file__).parent
load_dotenv(script_dir / ".env")
```

**Required Variables:**
```bash
GEMINI_API_KEY=...              # For generate_asset.py
KIE_API_KEY=...                 # For generate_video.py
ELEVENLABS_API_KEY=...          # For generate_audio.py, generate_sound_effects.py
ELEVENLABS_VOICE_ID=...         # For generate_audio.py
```

---

## Shared Code Patterns

### Common Patterns Across Scripts

1. **Argparse CLI:**
   - All scripts use `argparse` for command-line interface
   - Consistent `--help` documentation
   - Required vs optional arguments

2. **Error Handling:**
   - Print errors to `stderr`
   - Exit with code 1 on failure
   - Print success messages with ✅ emoji

3. **Directory Creation:**
   ```python
   output_path = Path(output_path)
   output_path.parent.mkdir(parents=True, exist_ok=True)
   ```

4. **Environment Validation:**
   ```python
   api_key = os.getenv("API_KEY")
   if not api_key:
       print("❌ Error: API_KEY not found", file=sys.stderr)
       sys.exit(1)
   ```

5. **Progress Reporting:**
   - Emoji-based status (🎨, 📤, ✅, ❌)
   - Dimension reporting (📐)
   - Clear step descriptions

### No Shared Libraries

**Important:** There are **no shared utility modules** across scripts.
- Each script is fully self-contained
- Code duplication is intentional (maintains script independence)
- Facilitates standalone execution and portability

---

## Testing

### Test Coverage

**Current State:** **No automated tests found**

**Test File Patterns (from doc requirements):**
- `*.test.ts`
- `*_test.go`
- `test_*.py`
- `*.spec.ts`
- `*_spec.rb`

**Search Results:** No test files found in project

**Testing Strategy:** Manual testing via script execution

---

## Entry Points Summary

| Script | Main Function | CLI Args | API Calls | File I/O |
|--------|---------------|----------|-----------|----------|
| `generate_asset.py` | `main()` | `--prompt, --output, --character, --environment, --reference-image, --split-vertical` | Gemini | Read (optional ref images), Write (PNG) |
| `create_composite.py` | `main()` | `--character, --environment, --output, --scale` | None | Read (2 PNGs), Write (PNG) |
| `create_split_screen.py` | N/A (direct execution) | None (hardcoded) | None | Read (4 PNGs), Write (PNG) |
| `generate_video.py` | `main()` | `--image, --prompt, --output` | KIE.ai + catbox.moe | Read (PNG), Write (MP4) |
| `generate_audio.py` | `main()` | `--text, --output` | ElevenLabs | Write (MP3) |
| `generate_sound_effects.py` | `main()` | `--prompt, --output` | ElevenLabs | Write (WAV) |
| `assemble_video.py` | `main()` | `--manifest, --output` | None (FFmpeg CLI) | Read (manifest + videos + audio), Write (MP4) |

---

## Key Architectural Insights

### 1. Stateless Design

Every script is **completely stateless**:
- No caching
- No session management
- No persistent state
- Can be run independently

### 2. Complete Inputs Required

Scripts never read project files:
- Agents combine prompts before calling scripts
- Scripts receive fully-formed arguments
- No file discovery or data extraction in scripts

### 3. Single Responsibility

Each script does **exactly one thing**:
- `generate_asset.py` → Generate or composite images
- `generate_video.py` → Animate images to video
- `generate_audio.py` → Synthesize narration
- `generate_sound_effects.py` → Create SFX
- `assemble_video.py` → Combine everything

### 4. Error Isolation

Script failures don't cascade:
- One failed asset generation doesn't stop others
- Failed video generation can be retried individually
- Filesystem tracks which steps completed

### 5. Debuggability

Every intermediate output is saved:
- Images: `{pokemon}/assets/`
- Videos: `{pokemon}/videos/`
- Audio: `{pokemon}/audio/`
- SFX: `{pokemon}/sfx/`
- Easy to inspect at each pipeline stage

---

## Performance Characteristics

### API Call Durations

| Operation | Typical Duration | Timeout |
|-----------|------------------|---------|
| Gemini Image Generation | 5-15 seconds | None configured |
| Kling Video Generation | 2-5 minutes | 10 minutes |
| ElevenLabs Audio | 1-3 seconds | None configured |
| ElevenLabs SFX | 2-5 seconds | None configured |
| FFmpeg Assembly | 10-20 seconds | None configured |

### Cost Estimates (Per Documentary)

- **Images (22 assets):** ~$0.50-2.00 (Gemini)
- **Videos (18 clips):** ~$5-10 (KIE.ai)
- **Audio (18 clips):** ~$0.50-1.00 (ElevenLabs)
- **Total:** ~$6-13 per 90-second documentary

---

## Limitations and Constraints

### 1. Kling Video Duration

**Fixed at 10 seconds** - not configurable via API
- Scripts must trim to match 6-8 second audio
- Handled by `assemble_video.py`

### 2. YouTube Format Requirement

**1920x1080 (16:9) enforced** for video generation
- Composite scripts must output this exact size
- Kling API requires proper aspect ratio

### 3. Hardcoded Split-Screen

`create_split_screen.py` is **project-specific** (Haunter)
- Not reusable without code changes
- Should be refactored to accept CLI args

### 4. No Retry Logic in Scripts

Scripts fail immediately on API errors
- Agents handle retries
- No exponential backoff in scripts

### 5. No Batch Processing

Each script processes **one item at a time**
- No multi-threading or async
- Agents orchestrate parallelism

---

## Recommendations for Improvement

### 1. Add Tests

Create `tests/` directory with unit tests:
```
tests/
  test_generate_asset.py
  test_create_composite.py
  test_assemble_video.py
```

### 2. Refactor create_split_screen.py

Make it a general-purpose tool:
```bash
python create_split_screen.py \
  --left-char "char1.png" \
  --left-env "env1.png" \
  --right-char "char2.png" \
  --right-env "env2.png" \
  --output "split.png"
```

### 3. Add Shared Utilities (Optional)

Extract common patterns to `scripts/utils.py`:
- Environment variable loading
- Directory creation
- Error reporting
- Progress logging

**Trade-off:** Reduces duplication but adds dependency

### 4. Add Timeouts

Configure timeouts for all API calls:
- Gemini: 60 seconds
- ElevenLabs: 30 seconds
- Kling: 10 minutes (already implemented)

### 5. Add Dry-Run Mode

Support `--dry-run` flag to preview without API calls:
```bash
python generate_asset.py --prompt "..." --output "..." --dry-run
# Output: Would generate image with prompt (123 chars) → output.png
```

---

## Summary

The ai-video-generator CLI toolkit consists of **7 independent Python scripts** that form a pipeline-based automation system for creating AI-generated documentary videos.

**Key Strengths:**
- ✅ Simple, focused, single-purpose tools
- ✅ Easy to debug and test individually
- ✅ Clear separation of concerns
- ✅ Stateless and portable
- ✅ Filesystem-based state tracking

**Areas for Growth:**
- ⚠️ No automated testing
- ⚠️ One hardcoded script (split-screen)
- ⚠️ Code duplication across scripts
- ⚠️ Limited error recovery in scripts

**Overall:** Well-designed for AI agent orchestration with clear interfaces and predictable behavior.
