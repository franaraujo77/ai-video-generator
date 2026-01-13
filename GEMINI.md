# Project Context: Pokémon Natural Geographic

## Overview
This project is an automated production pipeline for creating hyper-realistic Pokémon nature documentaries, styled after *Planet Earth*. It leverages a suite of AI tools to generate assets, video, audio, and sound effects, culminating in a final video assembly.

**Key Philosophy:** "Smart Agent + Dumb Scripts"
- **Agents (LLMs):** Handle logic, file reading, data extraction, and workflow orchestration.
- **Scripts (Python):** Single-purpose, atomic CLI tools that perform one API call or processing task. They do not hold state or business logic.

## Architecture & Tech Stack

### Core Technologies
- **Language:** Python 3.10+
- **Package Manager:** `uv`
- **Video Processing:** `FFmpeg`
- **AI Services:**
    - **Image:** Google Gemini 2.5 Flash
    - **Video:** Kling 2.5 (via KIE.ai)
    - **Audio/SFX:** ElevenLabs v3

### Directory Structure
- `scripts/`: Atomic Python scripts for individual tasks (asset gen, video gen, assembly).
- `prompts/`: Markdown files containing instructions for AI agents to drive the workflow.
- `{pokemon}/`: specific directories (e.g., `haunter/`, `pikachu/`) acting as workspaces for each documentary project. containing research, scripts, assets, and final outputs.

## Development & Usage

### 1. Setup
```bash
# Install dependencies
uv sync

# Configure Environment
# Copy scripts/.env.example to scripts/.env and populate API keys:
# - GEMINI_API_KEY
# - KIE_API_KEY
# - ELEVENLABS_API_KEY
# - ELEVENLABS_VOICE_ID
```

### 2. Production Pipeline (SOPs)
The workflow follows a strict sequential order (SOP 01 - SOP 08).

| Step | Task | Tool/Script | Description |
| :--- | :--- | :--- | :--- |
| **01** | Research | Manual/Agent | Generate species profile in `{pokemon}/01_research.md` |
| **02** | Story | Manual/Agent | Create 18-clip script in `{pokemon}/02_story_script.md` |
| **03** | Assets | `generate_asset.py` | Generate raw character/env images via Gemini |
| **03.5** | Composites | `create_composite.py` | Combine chars + envs into 16:9 images for video gen |
| **04** | Video Prompts | Manual/Agent | Define motion prompts in `{pokemon}/04_video_prompts.md` |
| **05** | Video Gen | `generate_video.py` | Animate composites using Kling (via KIE.ai) |
| **06** | Audio | `generate_audio.py` | Generate narration via ElevenLabs |
| **07** | SFX | `generate_sound_effects.py` | Generate atmospheric sounds |
| **08** | Assembly | `assemble_video.py` | FFmpeg assembly of all components |

### 3. Key Script Usage
Scripts are designed to be called by agents but can be run manually.

**Generate an Image Asset:**
```bash
python scripts/generate_asset.py --prompt "..." --output "path/to/image.png"
```

**Create a Composite (16:9):**
```bash
python scripts/create_composite.py --character "path/char.png" --environment "path/env.png" --output "path/comp.png"
```

**Generate Video (Kling):**
```bash
python scripts/generate_video.py --image "path/comp.png" --prompt "..." --output "path/video.mp4"
```

**Assemble Final Video:**
```bash
python scripts/assemble_video.py --manifest "path/manifest.json" --output "path/final.mp4"
```

## Conventions
- **Asset Naming:** Descriptive filenames (e.g., `pikachu_adult_alert.png`).
- **Video Specs:** 1920x1080 (16:9), H.264, AAC.
- **Clip Duration:** Kling generates 10s clips; these are trimmed to match audio (6-8s) during assembly.
- **State:** The file system is the source of truth. Each step reads from previous outputs and writes new files.
