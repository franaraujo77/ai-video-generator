# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository contains two complementary systems:

1. **Pokemon Pipeline** (`scripts/`, `prompts/`, `{pokemon}/`) - AI-powered production pipeline for creating photorealistic Pokémon nature documentaries in the style of David Attenborough's *Planet Earth*. Transforms a Pokémon concept into a finished 90-second video clip through 8 automated steps. Uses **filesystem as source of truth**.

2. **Multi-Channel Orchestration Platform** (`app/`, `alembic/`) - PostgreSQL-backed orchestration layer for managing multiple YouTube channels, each with isolated credentials, branding, and capacity limits. Uses **database as source of truth**.

## Core Architecture: "Smart Agent + Dumb Scripts"

**Critical Pattern:** All automation follows a strict separation of concerns:

- **Agents (Smart):** Read project files, extract data, combine prompts, orchestrate workflows, handle errors
- **Python Scripts (Dumb):** Take complete inputs, call one API, return success/failure, no file reading, no business logic

The filesystem is the single source of truth. Each SOP step reads from previous outputs and writes new files.

## Development Commands

### Environment Setup

```bash
# Install dependencies (uses uv package manager)
uv sync

# Configure API keys
cp scripts/.env.example scripts/.env
# Edit scripts/.env and add:
#   GEMINI_API_KEY=your_gemini_key
#   KIE_API_KEY=your_kie_key
#   ELEVENLABS_API_KEY=your_elevenlabs_key
#   ELEVENLABS_VOICE_ID=your_voice_id
```

### Running Scripts

All scripts live in `scripts/` and are designed to be called by agents but can run standalone:

```bash
# Generate image asset (Gemini)
python scripts/generate_asset.py --prompt "COMPLETE_PROMPT" --output "path/to/output.png"

# Create 16:9 composite (for Kling video generation)
python scripts/create_composite.py --character "char.png" --environment "env.png" --output "comp.png"

# Generate video (Kling 2.5 via KIE.ai)
python scripts/generate_video.py --image "comp.png" --prompt "motion prompt" --output "video.mp4"

# Generate narration (ElevenLabs)
python scripts/generate_audio.py --text "narration text" --output "audio.mp3"

# Generate sound effects (ElevenLabs)
python scripts/generate_sound_effects.py --prompt "sfx description" --output "sfx.wav"

# Assemble final video (FFmpeg)
python scripts/assemble_video.py --manifest "manifest.json" --output "final.mp4"
```

### Video Processing

```bash
# Check video duration
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 video.mp4

# Verify FFmpeg installation
ffmpeg -version
```

## Project Structure

```
pokemon-natural-geo/
├── scripts/              # Atomic Python CLI tools
│   ├── generate_asset.py           # Gemini image generation
│   ├── create_composite.py         # 16:9 composite creation
│   ├── create_split_screen.py      # Horizontal split composites
│   ├── generate_video.py           # Kling video generation
│   ├── generate_audio.py           # ElevenLabs narration
│   ├── generate_sound_effects.py   # ElevenLabs SFX
│   ├── assemble_video.py           # FFmpeg assembly
│   └── .env                        # API keys (gitignored)
├── prompts/              # Agent orchestration instructions
│   ├── 1_research.md               # SOP 01: Species research
│   ├── 2_story_generator.md        # SOP 02: Story development
│   ├── 3.5_generate_assets_agent.md    # SOP 03: Asset generation
│   ├── 4_video_prompt_engineering.md   # SOP 04: Video prompt guide
│   ├── 4.5_generate_videos_agent.md    # SOP 05: Video generation
│   ├── 5.5_generate_audio_agent.md     # SOP 06: Audio generation
│   ├── 6.5_generate_sound_effects_agent.md # SOP 07: SFX generation
│   └── 7_assemble_final_agent.md       # SOP 08: Final assembly
└── {pokemon}/            # Per-Pokemon workspaces
    ├── 01_research.md              # Species biological profile
    ├── 02_story_script.md          # 18-clip narrative
    ├── 03_assets.md                # Asset manifest with Global Atmosphere
    ├── 04_video_prompts.md         # Kling motion prompts
    ├── 05_audio_generation.md      # Narration scripts
    ├── 06_sound_effects.md         # SFX descriptions
    ├── assets/
    │   ├── characters/             # Character PNGs (transparent)
    │   ├── environments/           # Environment backgrounds
    │   └── composites/             # 1920x1080 16:9 composites
    ├── videos/                     # Generated video clips
    ├── audio/                      # Narration MP3s
    ├── sfx/                        # Sound effect WAVs
    └── {pokemon}_final.mp4         # Final documentary
```

## 8-Step Production Pipeline (SOPs)

The workflow is strictly sequential. Each SOP depends on previous outputs:

1. **SOP 01: Species Research** - Generate biological profile in `01_research.md`
2. **SOP 02: Story Development** - Create 18-clip narrative in `02_story_script.md`
3. **SOP 03: Asset Generation** - Generate 20-25 photorealistic images via Gemini (characters, environments, props)
4. **SOP 03.5: Composite Creation** - Combine characters + environments into 1920x1080 (16:9) seed images for Kling
5. **SOP 04: Video Prompt Engineering** - Define motion prompts following Priority Hierarchy
6. **SOP 05: Video Generation** - Animate composites using Kling 2.5 (10-second clips)
7. **SOP 06: Audio Generation** - Generate Attenborough-style narration via ElevenLabs
8. **SOP 07: Sound Effects** - Generate atmospheric SFX via ElevenLabs
9. **SOP 08: Final Assembly** - FFmpeg assembly (trim videos to audio, sync audio+SFX, concatenate)

## Critical Technical Requirements

### Video Specifications

- **Format:** 1920x1080 (16:9) - YouTube standard
- **Codec:** H.264 video, AAC audio
- **Duration:** Kling generates 10s clips → trimmed to match 6-8s audio during assembly
- **Composite Images:** MUST be 16:9 (1920x1080) for Kling video generation

### Video Prompt Priority Hierarchy

**CRITICAL:** Kling AI prioritizes the beginning of prompts. Always structure motion prompts in this order:

1. **Core Action FIRST** - What is happening
2. **Specific Details** - What parts move, how they move
3. **Logical Sequence** - Step-by-step cause and effect
4. **Environmental Context** - Atmosphere, lighting, weather
5. **Camera Movement LAST** - Aesthetic enhancement only

**Example:**
```
Good: "Haunter floats in dark corridor. Haunter presses both clawed hands against wall attempting to phase through. Haunter bounces backward unable to phase. Purple glow pulses brighter. Slow zoom in."

Bad: "Slow zoom in. Haunter attempts to phase through wall but bounces backward."
```

### Asset Generation Workflow

1. Agent reads `03_assets.md`
2. Agent extracts **Global Atmosphere Block** (lighting, weather, shared environmental context)
3. Agent extracts individual asset prompts
4. Agent combines: `{Global Atmosphere}\n\n{Asset Prompt}`
5. Agent calls `generate_asset.py` with COMPLETE combined prompt
6. Script calls Gemini API → Downloads image → Saves PNG

**Scripts receive complete prompts - they do NOT read files or combine prompts themselves.**

### Image Composition for Video

- Raw environment images may be ultra-wide cinematic (2.36:1)
- Characters are generated with transparent backgrounds
- `create_composite.py` enforces 1920x1080 (16:9) with proper scaling/cropping/centering
- Split-screen shots use `create_split_screen.py` for horizontal domains
- Composite images are fed to Kling for video generation

### Video Assembly Process

1. FFmpeg probes each audio file to get duration (typically 6-8 seconds)
2. Trims corresponding 10-second video to match audio duration
3. Mixes narration + SFX on separate audio tracks
4. Concatenates all clips with hard cuts (no transitions)
5. Final output: 90-second documentary (18 clips × ~5-8s each)

## Agent Orchestration Patterns

When using agent prompts (`prompts/*.5_*_agent.md`), agents follow this pattern:

1. **Read** relevant markdown files from `{pokemon}/` directory
2. **Extract** structured data (prompts, descriptions, file paths)
3. **Validate** all required inputs exist
4. **Call** Python scripts with complete arguments
5. **Report** progress and errors
6. **Retry** failed operations (with user confirmation)

Agents handle ALL file I/O, data extraction, and error recovery. Scripts are stateless.

## Common Workflow Patterns

### Generating Assets for a Pokemon

```
Agent reads: {pokemon}/03_assets.md
Agent extracts: Global Atmosphere Block + 22 individual asset prompts
For each asset:
  Agent combines: atmosphere + asset_prompt
  Agent calls: python generate_asset.py --prompt "COMBINED" --output "path.png"
  Script calls Gemini → Downloads image → Exits
  Agent reports success/failure
```

### Generating Videos

```
Agent reads: {pokemon}/04_video_prompts.md
Agent scans: {pokemon}/assets/composites/ (for 16:9 seed images)
For each clip:
  Agent uploads composite to catbox.moe (free public hosting)
  Agent calls: python generate_video.py --image "URL" --prompt "motion" --output "clip.mp4"
  Script polls KIE.ai API → Downloads MP4 → Exits
  Agent reports progress (2-5 min per clip)
```

### Assembling Final Video

```
Agent scans: {pokemon}/videos/, {pokemon}/audio/, {pokemon}/sfx/
Agent verifies: All 18 clips exist
Agent creates: assembly_manifest.json
Agent calls: python assemble_video.py --manifest "manifest.json" --output "final.mp4"
Script:
  For each clip: FFprobe audio → Trim video to match → Mix audio+SFX
  Concatenate all clips → Output final.mp4
```

## Dependencies

- **Python:** 3.10+ (managed by `uv`)
- **FFmpeg:** Required for video processing (must be in PATH)
- **Python Packages:**
  - `google-generativeai` - Gemini image generation
  - `python-dotenv` - Environment variables
  - `pillow` - Image manipulation
  - `requests` - HTTP requests (Kling API, catbox uploads)
  - `pyjwt` - KIE.ai authentication

## API Services

- **Gemini 2.5 Flash Image:** Photorealistic asset generation (~$0.50-2.00 per documentary)
- **KIE.ai (Kling 2.5 Pro):** Video generation (~$5-10 per documentary, 2-5 min per 10s clip)
- **ElevenLabs v3:** Narration + SFX generation (~$0.50-1.00 per documentary)
- **catbox.moe:** Free image hosting for Kling API

## Key Constraints

### Pokemon Pipeline Constraints
1. **One Static Image, One Micro-Movement:** AI video generators excel at "breathing photographs" - avoid complex action sequences
2. **Filesystem as Source of Truth:** For the Pokemon Pipeline, everything is markdown and generated assets - no databases
3. **Scripts Are Stateless:** Never add file reading or business logic to Python scripts - agents handle that
4. **16:9 for Video:** Composite images MUST be 1920x1080 for YouTube-ready output
5. **Sequential Pipeline:** Cannot skip SOPs - each step depends on previous outputs

### Orchestration Platform Constraints
1. **PostgreSQL as Source of Truth:** Channel configuration, credentials, and task state live in the database
2. **Encrypted Credentials:** All API keys and OAuth tokens use Fernet symmetric encryption (FERNET_KEY env var)
3. **Async-First:** All database operations use SQLAlchemy 2.0 async patterns
4. **Channel Isolation:** Each channel has independent credentials, branding, and capacity limits

## Common Issues

**"Image upload failed"**
- catbox.moe may be down → Retry or use different hosting in `generate_video.py`

**"Video timeout after 10 minutes"**
- Kling is slow → Increase timeout in `generate_video.py:163` or download from KIE.ai dashboard

**"API key not found"**
- Ensure `scripts/.env` exists with all required keys

**"FFmpeg not found"**
- Install FFmpeg and add to PATH

**"Composite image wrong aspect ratio"**
- Use `create_composite.py` to enforce 1920x1080 (16:9)

## Best Practices

- Start with 3-5 test assets before generating full sets
- Verify Global Atmosphere Block consistency across assets
- Review composite images before video generation (saves time/money)
- Monitor API usage for cost tracking
- Keep 10-minute timeout for Kling videos (2-5 min typical, up to 10 min possible)
- Hard cuts between clips (no transitions) - matches nature documentary style

---

## Multi-Channel Orchestration Platform

The orchestration layer (`app/`) manages multiple YouTube channels with isolated configuration, credentials, and task scheduling.

### Orchestration Structure

```
app/
├── models.py              # SQLAlchemy 2.0 ORM models (Channel, Task)
├── database.py            # Async session factory, connection management
├── schemas/               # Pydantic schemas for validation
│   └── channel_config.py  # YAML config validation
├── services/              # Business logic layer
│   ├── credential_service.py      # Encrypt/decrypt credentials
│   ├── channel_config_loader.py   # Load YAML configs
│   ├── storage_strategy_service.py # R2/Notion storage
│   └── channel_capacity_service.py # Capacity tracking
└── utils/
    └── encryption.py      # Fernet encryption singleton

alembic/
├── env.py                 # Migration environment (async)
└── versions/              # Database migrations
```

### Development Commands (Orchestration)

```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=app

# Lint check
uv run ruff check .

# Type check
uv run mypy app/

# Create new migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Generate Fernet encryption key
python scripts/generate_fernet_key.py
```

### Environment Variables (Orchestration)

```bash
# Database connection
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname

# Encryption key for credentials (generate with scripts/generate_fernet_key.py)
FERNET_KEY=your-44-char-base64-key

# For local testing with SQLite
DATABASE_URL=sqlite+aiosqlite:///./test.db
```

### Channel Configuration

Channels are configured via YAML files in `config/channels/`:

```yaml
# config/channels/poke1.yaml
channel_id: poke1
channel_name: Pokemon Nature Documentary
is_active: true
voice_id: EXAVITQu4vr4xnSDxMaL  # ElevenLabs voice
storage_strategy: r2  # or "notion"
max_concurrent: 3     # Parallel task limit
branding:
  intro_path: channel_assets/intro.mp4
  outro_path: channel_assets/outro.mp4
  watermark_path: channel_assets/watermark.png
```

### Key Models

- **Channel:** YouTube channel configuration (credentials, branding, capacity)
- **Task:** Video generation job with status tracking (pending → processing → completed)

### Testing Patterns

Tests use async SQLite with factory functions:

```python
from tests.support.factories import create_channel, create_channel_with_credentials

async def test_channel_creation(db_session):
    channel = create_channel(channel_id="test1")
    db_session.add(channel)
    await db_session.commit()
```
