# Source Tree Analysis

## Overview

**Project:** ai-video-generator
**Type:** Monolith (single cohesive codebase)
**Structure:** Pipeline-based with workspace-per-project organization

---

## Annotated Directory Tree

```
ai-video-generator/
│
├── pyproject.toml                  # Python project configuration (uv package manager)
├── README.md                       # Main project documentation
├── README_GENERIC.md               # Generic workflow guide
├── CLAUDE.md                       # Claude Code integration guide ✨ IMPORTANT
├── GEMINI.md                       # Gemini-specific documentation
├── .gitignore                      # Git ignore rules (videos, .env, Python artifacts)
│
├── scripts/                        # ⭐ CLI Automation Tools (Entry Points)
│   ├── .env                        # API keys (gitignored, copy from .env.example)
│   ├── .env.example                # Template for API configuration
│   ├── README.md                   # Scripts documentation
│   ├── generate_asset.py           # 🎨 Gemini image generation (330 lines)
│   ├── create_composite.py         # 🖼️  1920x1080 compositing (122 lines)
│   ├── create_split_screen.py      # ➗ Split-screen compositor (87 lines, hardcoded)
│   ├── generate_video.py           # 🎥 Kling video generation (11k LOC)
│   ├── generate_audio.py           # 🎙️  ElevenLabs narration (5k LOC)
│   ├── generate_sound_effects.py   # 🔊 ElevenLabs SFX (7k LOC)
│   └── assemble_video.py           # 🎞️  FFmpeg assembly (11k LOC)
│
├── prompts/                        # 🤖 Agent Orchestration Instructions
│   ├── 1_research.md               # SOP 01: Species research prompt
│   ├── 2_story_generator.md        # SOP 02: Story development prompt
│   ├── 3_character_generation.md   # SOP 03: Asset planning guide
│   ├── 3.5_generate_assets_agent.md     # SOP 03: Automated asset gen agent
│   ├── 4_video_prompt_engineering.md    # SOP 04: Video prompt guide
│   ├── 4.5_generate_videos_agent.md     # SOP 05: Automated video gen agent
│   ├── 5_voice_prompt_engineer.md       # SOP 06: Audio planning guide
│   ├── 5.5_generate_audio_agent.md      # SOP 06: Automated audio gen agent
│   ├── 6_sound_effects_prompt_engineering.md  # SOP 07: SFX planning guide
│   ├── 6.5_generate_sound_effects_agent.md    # SOP 07: Automated SFX gen agent
│   └── 7_assemble_final_agent.md        # SOP 08: Automated assembly agent
│
├── generic_prompts/                # 🔄 Reusable Workflow Templates
│   ├── 1_topic_research.md         # Generic research workflow
│   ├── 2_script_development.md     # Generic script development
│   ├── 3_visual_asset_planning.md  # Generic asset planning
│   ├── 3.5_automated_asset_generation.md  # Generic asset automation
│   └── 4_video_prompt_engineering.md      # Generic video prompt guide
│
├── {pokemon}/                      # 🗂️  Per-Project Workspaces (Example: bulbasaur/)
│   ├── 01_research.md              # Species biological profile
│   ├── 02_story_script.md          # 18-clip narrative (5s each → 90s total)
│   ├── 03_assets.md                # Asset manifest with Global Atmosphere
│   ├── 04_video_prompts.md         # Kling motion prompts (Priority Hierarchy)
│   ├── 04_kling_prompts.md         # Alternative: Kling-specific prompts
│   ├── 05_audio_generation.md      # Narration scripts with ellipses
│   ├── 06_sound_effects_prompts.md # SFX descriptions
│   │
│   ├── assets/                     # 📁 Generated Images
│   │   ├── characters/             # Character PNGs (transparent backgrounds)
│   │   │   └── {pokemon}_{pose}.png
│   │   ├── environments/           # Environment backgrounds
│   │   │   └── env_{description}.png
│   │   ├── props/                  # Optional: Props and items
│   │   │   └── {item}_description.png
│   │   └── composites/             # 🎯 1920x1080 seed images for video gen
│   │       └── clip_{XX}_composite.png
│   │
│   ├── videos/                     # 🎬 Generated Videos
│   │   └── clip_{XX}.mp4           # 10-second clips (trimmed during assembly)
│   │
│   ├── audio/                      # 🎙️  Narration
│   │   └── clip_{XX}.mp3           # 6-8 second narration clips
│   │
│   ├── sfx/                        # 🔊 Sound Effects (optional)
│   │   └── clip_{XX}_sfx.wav       # Atmospheric sound effects
│   │
│   ├── final/                      # 📦 Intermediate Assembly Files
│   │   └── concat_list.txt         # FFmpeg concatenation manifest
│   │
│   ├── assembly_manifest.json      # 🎞️  Final assembly configuration
│   └── {pokemon}_final.mp4         # ✅ FINAL OUTPUT (90-second documentary)
│
├── docs/                           # 📚 Generated Documentation (This Directory)
│   ├── project-scan-report.json    # Workflow state tracking
│   ├── project-structure.md        # Project classification
│   ├── project-parts-metadata.json # Project metadata
│   ├── technology-stack.md         # Tech stack documentation
│   ├── architecture-patterns.md    # Architecture explanation
│   ├── comprehensive-analysis-main.md  # CLI tools analysis
│   └── source-tree-analysis.md     # This file
│
└── _bmad-output/                   # 🔧 BMAD Workflow Artifacts (Optional)
    ├── planning-artifacts/         # Planning documents
    ├── implementation-artifacts/   # Implementation tracking
    └── analysis/                   # Analysis outputs
```

---

## Critical Directories

### 1. `scripts/` - CLI Automation Tools ⭐

**Purpose:** Single-purpose Python scripts for each production step

**Entry Points:**
- `generate_asset.py` - Image generation via Gemini 2.5 Flash
- `create_composite.py` - 16:9 image compositing (YouTube-ready)
- `create_split_screen.py` - Split-screen composites (hardcoded)
- `generate_video.py` - Video animation via Kling 2.5
- `generate_audio.py` - Narration synthesis via ElevenLabs
- `generate_sound_effects.py` - SFX generation via ElevenLabs
- `assemble_video.py` - FFmpeg video assembly and trimming

**Configuration:**
- `.env` - API keys (GEMINI, KIE, ELEVENLABS)
- `.env.example` - Configuration template

**Key Characteristic:** **Stateless scripts** - no shared code, no file reading, complete inputs via CLI

---

### 2. `prompts/` - Agent Orchestration Instructions 🤖

**Purpose:** Markdown files containing instructions for AI agents to automate each SOP step

**Agent Pattern:** Agents read project files, extract data, combine prompts, call scripts

**Workflow Steps:**
1. `1_research.md` - Generate species profile
2. `2_story_generator.md` - Create 18-clip narrative
3. `3.5_generate_assets_agent.md` - Generate all images
4. `4.5_generate_videos_agent.md` - Animate all clips
5. `5.5_generate_audio_agent.md` - Generate all narration
6. `6.5_generate_sound_effects_agent.md` - Generate all SFX
7. `7_assemble_final_agent.md` - Assemble final video

**Integration:** Agents orchestrate scripts, handle errors, report progress

---

### 3. `{pokemon}/` - Project Workspaces 🗂️

**Purpose:** Self-contained workspace for each documentary project

**Structure Pattern:** Every Pokemon directory follows the same layout:
```
{pokemon}/
  ├── 01-06_*.md       # Planning documents (inputs)
  ├── assets/          # Generated images (intermediate)
  ├── videos/          # Generated videos (intermediate)
  ├── audio/           # Generated narration (intermediate)
  ├── sfx/             # Generated sound effects (intermediate)
  └── {pokemon}_final.mp4  # Final output
```

**Examples:**
- `bulbasaur/` - "First Light" documentary
- `charizard/` - Charizard documentary
- `haunter/` - Haunter documentary
- `pikachu/` - "First Spark" documentary

**Key Files:**
- `03_assets.md` - Contains **Global Atmosphere Block** (critical for consistency)
- `04_video_prompts.md` - Motion prompts following **Priority Hierarchy**

---

### 4. `generic_prompts/` - Reusable Templates 🔄

**Purpose:** Generic versions of prompts for non-Pokemon projects

**Use Case:** Adapt the pipeline for any video generation project

**Structure:** Same as `prompts/` but with placeholder variables

---

## File Naming Conventions

### Asset Files

**Characters:**
```
{pokemon}_{pose}_{variant}.png
Example: bulbasaur_walking_core.png
```

**Environments:**
```
env_{description}.png
Example: env_forest_dawn_mist.png
```

**Composites:**
```
clip_{XX}_composite.png
Example: clip_03_composite.png
```

### Video/Audio Files

**Videos:**
```
clip_{XX}.mp4
Example: clip_01.mp4
```

**Audio:**
```
clip_{XX}.mp3
Example: clip_01.mp3
```

**Sound Effects:**
```
clip_{XX}_sfx.wav
Example: clip_01_sfx.wav
```

### Numbering

- **Clips:** 01-18 (zero-padded, 18 clips per documentary)
- **Sequential:** Matches narrative order in `02_story_script.md`

---

## Integration Points

### Agent ↔ Scripts

**Flow:**
```
Agent reads {pokemon}/03_assets.md
  → Extracts Global Atmosphere + Asset Prompts
  → Combines prompts
  → Calls: python scripts/generate_asset.py --prompt "COMBINED" --output "path.png"
  → Script calls Gemini API → Downloads image → Exits
  → Agent reports success
```

**Key Pattern:** Agents provide **complete inputs**, scripts perform **single operations**

### Scripts ↔ External APIs

**Services:**
- **Gemini 2.5 Flash:** `scripts/generate_asset.py` → Image generation
- **KIE.ai Kling 2.5:** `scripts/generate_video.py` → Video animation
- **ElevenLabs:** `scripts/generate_audio.py`, `scripts/generate_sound_effects.py` → Audio synthesis
- **catbox.moe:** `scripts/generate_video.py` → Free image hosting

### Data Flow

```
Planning Docs ({pokemon}/01-06_*.md)
  ↓
Images ({pokemon}/assets/)
  ↓
Composites ({pokemon}/assets/composites/)
  ↓
Videos ({pokemon}/videos/)
  ↓
Audio ({pokemon}/audio/)
  ↓
SFX ({pokemon}/sfx/)
  ↓
Assembly Manifest ({pokemon}/assembly_manifest.json)
  ↓
Final Video ({pokemon}/{pokemon}_final.mp4)
```

---

## Critical Folders Summary

| Directory | Purpose | Created By | Contains |
|-----------|---------|------------|----------|
| `scripts/` | CLI tools | Developer | Python entry points |
| `prompts/` | Agent instructions | Developer | Markdown workflows |
| `{pokemon}/` | Project workspace | User/Agent | All inputs and outputs |
| `{pokemon}/assets/` | Images | `generate_asset.py` | PNGs (chars, envs, composites) |
| `{pokemon}/videos/` | Video clips | `generate_video.py` | 10s MP4 files |
| `{pokemon}/audio/` | Narration | `generate_audio.py` | 6-8s MP3 files |
| `{pokemon}/sfx/` | Sound effects | `generate_sound_effects.py` | WAV files |
| `docs/` | Documentation | Document-project workflow | Project analysis |

---

## Navigation Tips

### Finding Entry Points

**All CLI scripts are in:**
```
scripts/*.py
```

**All agent orchestration files are in:**
```
prompts/*_agent.md
```

### Finding Examples

**Complete example workspaces:**
```
bulbasaur/    # Most complete example
charizard/    # Alternative example
haunter/      # Alternative example
pikachu/      # Alternative example
```

### Finding Configuration

**API keys:**
```
scripts/.env    (copy from scripts/.env.example)
```

**Project config:**
```
pyproject.toml  (Python dependencies)
```

### Finding Documentation

**Project docs:**
```
README.md           # Main overview
CLAUDE.md           # Claude Code guide (IMPORTANT!)
GEMINI.md           # Gemini context
scripts/README.md   # Scripts technical docs
```

**Generated docs:**
```
docs/               # This directory (generated by document-project workflow)
```

---

## Key Observations

### 1. Workspace Isolation

Each Pokemon directory is **completely independent**:
- No shared data between projects
- Can be deleted without affecting others
- Easy to archive or transfer

### 2. Filesystem as State

**No databases** - all state is in files:
- Completed steps = files exist
- Failed steps = files missing
- Progress tracking = file creation timestamps

### 3. Clear Separation

**Three distinct layers:**
1. **Tools** (`scripts/`) - Single-purpose executables
2. **Orchestration** (`prompts/`) - Workflow automation
3. **Data** (`{pokemon}/`) - Inputs and outputs

### 4. Predictable Structure

Every workspace follows the **exact same pattern**:
- Same file naming
- Same directory structure
- Same workflow steps

**Benefit:** Easy to automate, debug, and maintain

---

## Special Files

### CLAUDE.md ✨

**Purpose:** Guide for Claude Code instances
**Location:** Root directory
**Critical For:** Understanding architecture, commands, and workflows
**Created By:** `/init` command

### .env (scripts/.env)

**Purpose:** API key storage
**Location:** `scripts/.env`
**Security:** Gitignored, never commit
**Template:** `scripts/.env.example`

### pyproject.toml

**Purpose:** Python project configuration
**Package Manager:** uv
**Dependencies:** Gemini, Pillow, requests, pyjwt, dotenv

---

## Directory Growth Pattern

**Starting State:**
```
ai-video-generator/
  ├── scripts/
  ├── prompts/
  └── generic_prompts/
```

**After First Run (e.g., bulbasaur):**
```
ai-video-generator/
  ├── scripts/
  ├── prompts/
  ├── generic_prompts/
  └── bulbasaur/
      ├── 01_research.md
      ├── 02_story_script.md
      ├── 03_assets.md
      ├── assets/
      │   ├── characters/ (22 PNGs)
      │   ├── environments/ (15 PNGs)
      │   └── composites/ (18 PNGs)
      ├── videos/ (18 MP4s)
      ├── audio/ (18 MP3s)
      ├── sfx/ (18 WAVs)
      └── bulbasaur_final.mp4
```

**Typical Size:**
- Assets: ~100 MB (images)
- Videos: ~500 MB (18 × 10s clips)
- Audio: ~5 MB
- Final: ~50 MB (90s video)

**Total per project:** ~650 MB

---

## Summary

The ai-video-generator project uses a **workspace-based architecture** where:
- **Tools** live in `scripts/` (portable CLI utilities)
- **Workflows** live in `prompts/` (agent orchestration)
- **Projects** live in `{pokemon}/` (isolated workspaces)
- **Documentation** lives in `docs/` (generated analysis)

This structure enables:
- ✅ Easy project isolation and archiving
- ✅ Clear separation of tools vs data
- ✅ Straightforward agent automation
- ✅ Filesystem-based progress tracking
- ✅ No complex state management

The directory tree is **intentionally flat** for navigability and **highly predictable** for automation.
