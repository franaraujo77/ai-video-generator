# Architecture Document

## Executive Summary

**Project:** ai-video-generator
**Type:** CLI Automation Toolkit
**Architecture Pattern:** Pipeline-Based with AI Agent Orchestration
**Primary Language:** Python 3.10+
**Status:** Production-ready CLI tools

The ai-video-generator is a sophisticated CLI automation pipeline that transforms text prompts into 90-second AI-generated documentary videos through an 8-step production workflow orchestrated by AI agents (Claude Code, Gemini).

**Key Innovation:** "Smart Agent + Dumb Scripts" - complexity lives in AI orchestration, scripts remain simple and stateless.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Technology Stack](#technology-stack)
3. [Architecture Pattern](#architecture-pattern)
4. [Component Architecture](#component-architecture)
5. [Data Architecture](#data-architecture)
6. [API Design](#api-design)
7. [Source Tree](#source-tree)
8. [Development Workflow](#development-workflow)
9. [Deployment Architecture](#deployment-architecture)
10. [Testing Strategy](#testing-strategy)
11. [Security Considerations](#security-considerations)
12. [Performance Characteristics](#performance-characteristics)
13. [Limitations and Constraints](#limitations-and-constraints)
14. [Future Enhancements](#future-enhancements)

---

## System Overview

### Purpose

Generate photorealistic video documentaries from text descriptions using AI services (Gemini, Kling, ElevenLabs) orchestrated through a command-line pipeline.

### Core Capabilities

1. **Image Generation:** Photorealistic assets via Gemini 2.5 Flash
2. **Video Animation:** 10-second clips via Kling 2.5 (KIE.ai)
3. **Audio Synthesis:** Narration via ElevenLabs v3
4. **Sound Effects:** Atmospheric audio via ElevenLabs SFX
5. **Video Assembly:** FFmpeg-based trimming, syncing, and concatenation

### High-Level Flow

```
Planning Documents (Markdown)
  ↓ (Agent reads + extracts)
Python CLI Scripts (Single-purpose tools)
  ↓ (Call external APIs)
AI Services (Gemini, Kling, ElevenLabs)
  ↓ (Generate content)
Output Files (Images, Videos, Audio)
  ↓ (Assemble)
Final Video (MP4, 90 seconds, 1080p)
```

---

## Technology Stack

### Core Technologies

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **Runtime** | Python | 3.10+ | Script execution environment |
| **Package Manager** | uv | Latest | Fast dependency management |
| **Video Processing** | FFmpeg | 8.0.1+ | Video manipulation |
| **Orchestration** | Claude Code | Latest | AI agent automation |

### Python Dependencies

```toml
[project]
dependencies = [
    "google-generativeai>=0.8.0",  # Gemini SDK
    "python-dotenv>=1.0.0",        # Environment config
    "pillow>=10.0.0",              # Image manipulation
    "pyjwt>=2.8.0",                # JWT auth for KIE.ai
    "requests>=2.31.0",            # HTTP client
]
```

### External Services

| Service | Role | API Endpoint | Authentication |
|---------|------|--------------|----------------|
| **Google Gemini 2.5 Flash** | Image generation | `google.generativeai` SDK | API Key |
| **KIE.ai (Kling 2.5 Pro)** | Video generation | `https://api.kie.ai/api/v1` | API Key + JWT |
| **ElevenLabs v3** | Narration + SFX | ElevenLabs API | API Key + Voice ID |
| **catbox.moe** | Image hosting | `https://catbox.moe/user/api.php` | None (free) |

---

## Architecture Pattern

### Pattern Name: Pipeline-Based CLI Automation

**Description:** A series of independent, single-purpose CLI tools orchestrated by AI agents to transform inputs through discrete processing stages.

### Core Principles

#### 1. Smart Agent + Dumb Scripts

**Philosophy:** Complexity lives in agents, simplicity lives in scripts.

**Agents (Smart):**
- Read and parse project files (markdown)
- Extract structured data (prompts, paths, descriptions)
- Combine prompts intelligently (e.g., Global Atmosphere + Asset Prompt)
- Orchestrate script execution with complete arguments
- Handle errors, retries, and progress reporting

**Scripts (Dumb):**
- Accept complete inputs via CLI arguments
- Perform one atomic operation (generate image, create video, etc.)
- Call one external API or tool
- Return success (exit 0) or failure (exit 1)
- No file reading, no data extraction, no business logic

#### 2. Filesystem as State

- **No databases:** All state stored in filesystem
- **No caches:** Ephemeral processing, no persistent state
- **File existence = completion:** Completed steps create files
- **Idempotent operations:** Re-running overwrites outputs

#### 3. Complete Inputs Required

Scripts receive fully-formed arguments:

```bash
# Good: Agent combines prompt first
python generate_asset.py --prompt "COMPLETE_ATMOSPHERE_AND_ASSET_PROMPT" --output "path.png"

# Bad: Script discovers and combines itself
python generate_asset.py --pokemon "pikachu" --asset-id "01"  # Don't do this
```

#### 4. Single Responsibility

Each script does **exactly one thing:**
- `generate_asset.py` → Generate or composite images
- `generate_video.py` → Animate images
- `generate_audio.py` → Synthesize narration
- `assemble_video.py` → Combine all clips

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    AI Agent Layer (Claude/Gemini)             │
│  - Reads markdown files                                       │
│  - Extracts structured data                                   │
│  - Combines prompts                                           │
│  - Orchestrates scripts                                       │
│  - Handles errors/retries                                     │
└──────────────────────┬────────────────────────────────────────┘
                       │
                       ↓ (Calls with complete arguments)
┌─────────────────────────────────────────────────────────────┐
│                    CLI Script Layer (Python)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │generate_     │  │generate_     │  │generate_     │       │
│  │asset.py      │  │video.py      │  │audio.py      │       │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘       │
│         │                  │                  │               │
│         │                  │                  │               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │create_       │  │assemble_     │  │generate_     │       │
│  │composite.py  │  │video.py      │  │sfx.py        │       │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘       │
└─────────┼──────────────────┼──────────────────┼──────────────┘
          │                  │                  │
          ↓ (API calls)      ↓ (FFmpeg CLI)     ↓ (API calls)
┌─────────────────────────────────────────────────────────────┐
│                    External Services Layer                    │
│  ┌────────────┐   ┌────────────┐   ┌──────────────┐         │
│  │  Gemini    │   │  Kling 2.5 │   │ ElevenLabs   │         │
│  │  2.5 Flash │   │  (KIE.ai)  │   │     v3       │         │
│  └────────────┘   └────────────┘   └──────────────┘         │
│  ┌────────────┐   ┌────────────┐                            │
│  │ catbox.moe │   │  FFmpeg    │                            │
│  │  (hosting) │   │  (local)   │                            │
│  └────────────┘   └────────────┘                            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓ (Generates)
┌─────────────────────────────────────────────────────────────┐
│                    Output Files Layer                         │
│  Images → Videos → Audio → SFX → Final MP4                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Architecture

### 1. CLI Scripts (Entry Points)

All located in `scripts/`:

| Script | LOC | Primary Function | Dependencies |
|--------|-----|------------------|--------------|
| `generate_asset.py` | 330 | Image generation, compositing | `genai`, `Pillow` |
| `create_composite.py` | 122 | 16:9 image compositing | `Pillow` |
| `create_split_screen.py` | 87 | Split-screen compositor | `Pillow` |
| `generate_video.py` | 330 | Video animation | `requests`, `pyjwt` |
| `generate_audio.py` | 160 | Narration synthesis | `requests` |
| `generate_sound_effects.py` | 220 | SFX generation | `requests` |
| `assemble_video.py` | 350 | Video assembly | `subprocess` (FFmpeg) |

**Common Patterns:**
- `argparse` for CLI interface
- Environment variable validation
- Progress reporting with emojis (🎨, ✅, ❌)
- Exit codes (0 = success, 1 = failure)
- Automatic directory creation

### 2. Agent Orchestration Layer

Located in `prompts/`:

| Agent File | Purpose | Automates |
|------------|---------|-----------|
| `3.5_generate_assets_agent.md` | Asset generation | SOP 03 (22 images) |
| `4.5_generate_videos_agent.md` | Video generation | SOP 05 (18 videos) |
| `5.5_generate_audio_agent.md` | Audio generation | SOP 06 (18 audio clips) |
| `6.5_generate_sound_effects_agent.md` | SFX generation | SOP 07 (18 SFX clips) |
| `7_assemble_final_agent.md` | Final assembly | SOP 08 (concatenation) |

**Agent Responsibilities:**
1. Read project markdown files
2. Extract and validate data
3. Combine prompts (e.g., Global Atmosphere + Asset Prompt)
4. Call scripts with complete arguments
5. Track progress and report errors
6. Retry failed operations (with user confirmation)

### 3. Data Layer (Filesystem)

**Workspace Structure:**
```
{pokemon}/
  ├── 01-06_*.md           # Planning documents (input)
  ├── assets/              # Generated images (intermediate)
  │   ├── characters/      # Character PNGs
  │   ├── environments/    # Environment PNGs
  │   └── composites/      # 1920x1080 seed images
  ├── videos/              # Generated MP4s (intermediate)
  ├── audio/               # Generated MP3s (intermediate)
  ├── sfx/                 # Generated WAVs (intermediate)
  ├── assembly_manifest.json  # Assembly configuration
  └── {pokemon}_final.mp4  # Final output
```

---

## Data Architecture

### Data Flow

```
1. Planning Phase (Manual)
   ├── 01_research.md        (Species biology)
   ├── 02_story_script.md    (18-clip narrative)
   ├── 03_assets.md          (Asset manifest + Global Atmosphere)
   ├── 04_video_prompts.md   (Motion descriptions)
   ├── 05_audio_generation.md  (Narration scripts)
   └── 06_sound_effects.md   (SFX descriptions)

2. Asset Generation (Automated)
   └── assets/
       ├── characters/ (22 PNGs, transparent)
       ├── environments/ (15 PNGs, backgrounds)
       └── composites/ (18 PNGs, 1920x1080)

3. Media Generation (Automated)
   ├── videos/ (18 MP4s, 10s each)
   ├── audio/ (18 MP3s, 6-8s each)
   └── sfx/ (18 WAVs, 5-10s each)

4. Assembly (Automated)
   ├── assembly_manifest.json (clip manifest)
   └── {pokemon}_final.mp4 (90s, 1080p)
```

### Data Schemas

**Assembly Manifest (JSON):**
```json
{
  "clips": [
    {
      "clip_id": "clip_01",
      "video": "bulbasaur/videos/clip_01.mp4",
      "audio": "bulbasaur/audio/clip_01.mp3",
      "sfx": "bulbasaur/sfx/clip_01_sfx.wav"
    }
    // ... 17 more clips
  ]
}
```

**Global Atmosphere Block (Markdown):**
```markdown
# Global Atmosphere Block

Early morning dawn light in temperate mixed forest, 15 minutes post-rainfall.
Thick volumetric fog at ground level (2-3 feet height).
Dew-covered vegetation glistening with backlit highlights.
Soft golden-hour sun breaking through canopy (5000K color temperature).
```

### File Naming Conventions

- **Characters:** `{pokemon}_{pose}_{variant}.png`
- **Environments:** `env_{description}.png`
- **Composites:** `clip_{XX}_composite.png`
- **Videos:** `clip_{XX}.mp4`
- **Audio:** `clip_{XX}.mp3`
- **SFX:** `clip_{XX}_sfx.wav`

---

## API Design

### CLI Interface Standard

**Pattern:**
```bash
python scripts/<tool>.py --arg1 value1 --arg2 value2 --output path.ext
```

**Example:**
```bash
python scripts/generate_asset.py \
  --prompt "Complete prompt text" \
  --output "path/to/output.png"
```

### Common Arguments

| Argument | Type | Required | Purpose |
|----------|------|----------|---------|
| `--prompt` | String | Yes* | Complete text prompt |
| `--output` | Path | Yes | Output file path |
| `--image` | Path | Sometimes | Input image path |
| `--character` | Path | Sometimes | Character image (compositing) |
| `--environment` | Path | Sometimes | Environment image (compositing) |

*Required for generation modes, optional for composite modes

### Exit Codes

- `0`: Success
- `1`: Failure (API error, file error, validation error)

### Error Handling

**Pattern:**
```python
try:
    # Operation
    return True
except Exception as e:
    print(f"❌ Error: {e}", file=sys.stderr)
    traceback.print_exc()
    return False
```

---

## Source Tree

See `docs/source-tree-analysis.md` for complete annotated directory tree.

**Key Directories:**
- `scripts/` - CLI tools (entry points)
- `prompts/` - Agent orchestration
- `{pokemon}/` - Project workspaces
- `docs/` - Generated documentation

---

## Development Workflow

See `docs/development-guide.md` for complete setup instructions.

**Quick Start:**
```bash
# 1. Install prerequisites
brew install ffmpeg  # macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install dependencies
uv sync

# 3. Configure API keys
cp scripts/.env.example scripts/.env
# Edit scripts/.env

# 4. Run a script
python scripts/generate_asset.py --prompt "Test" --output "test.png"
```

---

## Deployment Architecture

### Local Execution Only

This is a **CLI tool designed for local execution**:
- No web server
- No cloud deployment
- No containerization required

### System Requirements

**Minimum:**
- Python 3.10+
- 8GB RAM
- 10GB free disk space

**Recommended:**
- Python 3.12+
- 16GB RAM
- 50GB free disk space (for multiple projects)

### Dependencies

**Runtime:**
- Python 3.10+ (system installed)
- FFmpeg (system installed)

**Python Packages:**
- Managed by `uv` in virtual environment (`.venv/`)

---

## Testing Strategy

### Current Status

**⚠️ No automated tests exist.**

### Manual Testing Approach

Each script is tested independently:

```bash
# Test image generation
python scripts/generate_asset.py \
  --prompt "Test image" \
  --output "test.png"

# Verify output
ls -lh test.png
open test.png
```

### Recommended Test Structure

```
tests/
  ├── test_generate_asset.py
  ├── test_create_composite.py
  ├── test_generate_video.py
  ├── test_generate_audio.py
  ├── test_generate_sound_effects.py
  └── test_assemble_video.py
```

### Test Categories

1. **Unit Tests:** Test individual functions
2. **Integration Tests:** Test API calls (with mocking)
3. **End-to-End Tests:** Test complete workflow (expensive)

---

## Security Considerations

### API Key Management

**Storage:**
- Keys stored in `scripts/.env` (gitignored)
- Never committed to version control
- Template provided in `scripts/.env.example`

**Access:**
- Loaded via `python-dotenv`
- Only accessible within script execution context
- Not logged or displayed in output

### External API Calls

**Security Measures:**
- HTTPS only (all services)
- API keys passed via headers (not URL params)
- JWT tokens for KIE.ai authentication
- No sensitive data in prompts

### File System

**Permissions:**
- Scripts create files with default user permissions
- No setuid or elevated privileges required
- Output files readable by user only

---

## Performance Characteristics

### API Call Durations

| Operation | Typical Duration | Timeout |
|-----------|------------------|---------|
| Gemini Image | 5-15 seconds | None configured |
| Kling Video | 2-5 minutes | 10 minutes |
| ElevenLabs Audio | 1-3 seconds | None configured |
| ElevenLabs SFX | 2-5 seconds | None configured |
| FFmpeg Assembly | 10-20 seconds | None configured |

### Full Pipeline Duration

**For 18-clip documentary:**
- Assets (22 images): ~5-10 minutes
- Composites (18 images): ~1-2 minutes
- Videos (18 clips): ~60-90 minutes (sequential)
- Audio (18 clips): ~1-2 minutes
- SFX (18 clips): ~2-3 minutes
- Assembly: ~2-3 minutes

**Total:** ~70-110 minutes (mostly video generation)

### Cost Estimates

**Per 90-second documentary:**
- Images: ~$0.50-2.00
- Videos: ~$5-10
- Audio: ~$0.50-1.00
- **Total:** ~$6-13

---

## Limitations and Constraints

### 1. Kling Video Duration

- Fixed at 10 seconds per clip (not configurable)
- Trimmed to match audio (6-8s) during assembly

### 2. YouTube Format Requirement

- Composite images must be 1920x1080 (16:9)
- Enforced by `create_composite.py`

### 3. Sequential Processing

- Scripts process one item at a time
- No built-in parallelization
- Agents can orchestrate parallel execution

### 4. No State Persistence

- Scripts are stateless
- Progress tracked via file existence
- Agents handle workflow state

### 5. API Dependencies

- Requires active internet connection
- Subject to API rate limits
- No offline mode

---

## Future Enhancements

### Recommended Improvements

1. **Add Automated Testing**
   - Unit tests for core functions
   - Integration tests with mocked APIs
   - End-to-end workflow tests

2. **Refactor create_split_screen.py**
   - Make it accept CLI arguments (currently hardcoded)
   - Generalize for any split-screen layout

3. **Add Shared Utilities**
   - Extract common patterns to `scripts/utils.py`
   - Environment loading, error reporting, logging

4. **Implement Retry Logic**
   - Add exponential backoff for API failures
   - Automatic retry for transient errors

5. **Add Progress Tracking**
   - JSON progress file for resumable workflows
   - Percentage complete indicators

6. **Performance Optimization**
   - Built-in parallel execution for independent tasks
   - Batch API calls where possible

7. **Enhanced Error Recovery**
   - Checkpoint system for long-running operations
   - Resume from last successful step

---

## Conclusion

The ai-video-generator architecture demonstrates a well-designed **separation of concerns** between intelligent orchestration (agents) and simple, focused execution (scripts).

**Key Strengths:**
- ✅ Clear, predictable architecture
- ✅ Easy to debug and maintain
- ✅ Stateless, portable components
- ✅ Filesystem-based state tracking
- ✅ Extensible pipeline design

**Areas for Growth:**
- ⚠️ Add automated testing
- ⚠️ Implement retry logic
- ⚠️ Generalize hardcoded components
- ⚠️ Add shared utility libraries

**Overall Assessment:** Production-ready CLI toolkit with solid architectural foundation and clear paths for enhancement.
