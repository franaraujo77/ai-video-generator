# Architecture Patterns

## Primary Pattern: Pipeline-Based CLI Automation

### Overview

The ai-video-generator follows a **Pipeline-Based CLI Automation** pattern where multiple independent scripts are orchestrated by AI agents to transform inputs into final video outputs through a series of discrete steps.

---

## Pattern Components

### 1. Atomic CLI Scripts

Each script is a standalone CLI tool that:
- Performs exactly one operation (generate image, create video, assemble clips)
- Takes complete inputs via command-line arguments
- Calls one external API or performs one processing task
- Returns exit code 0 (success) or 1 (failure)
- Has no internal state or memory

**Scripts:**
- `generate_asset.py` - Image generation via Gemini
- `generate_video.py` - Video generation via Kling
- `generate_audio.py` - Narration via ElevenLabs
- `generate_sound_effects.py` - SFX via ElevenLabs
- `assemble_video.py` - FFmpeg video assembly
- `create_composite.py` - Image compositing
- `create_split_screen.py` - Split-screen composites

### 2. Intelligent Orchestration Layer (AI Agents)

AI agents (Claude Code, Gemini) handle:
- Reading project markdown files (research, scripts, asset manifests)
- Extracting structured data (prompts, file paths, descriptions)
- Combining prompts intelligently (e.g., Global Atmosphere + Asset Prompt)
- Calling scripts with complete arguments
- Error handling and retry logic
- Progress reporting

### 3. Filesystem as State

All state is stored in the filesystem:
- **Input:** Markdown files with prompts, descriptions, metadata
- **Intermediate:** Generated images, videos, audio clips
- **Output:** Final assembled video
- **Configuration:** `.env` files for API keys

**No databases, no caches, no complex state management.**

---

## 8-Step Production Pipeline

The architecture implements a sequential pipeline:

```
SOP 01: Research → {pokemon}/01_research.md
SOP 02: Story → {pokemon}/02_story_script.md
SOP 03: Assets → generate_asset.py → {pokemon}/assets/
SOP 03.5: Composites → create_composite.py → {pokemon}/assets/composites/
SOP 04: Video Prompts → {pokemon}/04_video_prompts.md
SOP 05: Videos → generate_video.py → {pokemon}/videos/
SOP 06: Audio → generate_audio.py → {pokemon}/audio/
SOP 07: SFX → generate_sound_effects.py → {pokemon}/sfx/
SOP 08: Assembly → assemble_video.py → {pokemon}/{pokemon}_final.mp4
```

Each step depends on outputs from previous steps.

---

## Key Design Principles

### 1. Smart Agent + Dumb Scripts

**Philosophy:** Complexity lives in agents, simplicity lives in scripts.

**Agents (Smart):**
- Read files
- Extract data
- Combine prompts
- Orchestrate workflows
- Handle errors

**Scripts (Dumb):**
- Take inputs
- Call one API
- Return success/failure
- No file reading
- No logic

**Benefits:**
- Scripts are testable, portable, reusable
- Agents can be updated without changing scripts
- Clear separation of concerns

### 2. Complete Inputs, Not Discovery

Scripts receive **complete, ready-to-use inputs**:

```bash
# Good: Agent combines prompt first, then calls script
python generate_asset.py --prompt "COMPLETE_ATMOSPHERE_AND_ASSET_PROMPT" --output "path.png"

# Bad: Script reads files and combines prompts itself
python generate_asset.py --pokemon "pikachu" --asset-id "01"  # Don't do this
```

### 3. Idempotent Operations

Most operations are idempotent:
- Re-running `generate_asset.py` overwrites the image
- Re-running `assemble_video.py` recreates the final video
- Allows easy regeneration of failed steps

### 4. Fail Fast, Report Clearly

Scripts exit immediately on error:
```python
if not image_data:
    print("❌ No image data in API response", file=sys.stderr)
    sys.exit(1)
```

Agents detect failures and report to user.

---

## Data Flow Example

**Goal:** Generate a photorealistic Bulbasaur character image

**Flow:**

1. **Agent reads:** `bulbasaur/03_assets.md`
   - Extracts Global Atmosphere Block: "Early morning dawn light, thick fog..."
   - Extracts Asset Prompt: "A hyper-realistic Bulbasaur in walking stance..."

2. **Agent combines:**
   ```
   COMBINED_PROMPT = "Early morning dawn light, thick fog...\n\nA hyper-realistic Bulbasaur in walking stance..."
   ```

3. **Agent calls script:**
   ```bash
   python scripts/generate_asset.py \
     --prompt "Early morning dawn light...\n\nA hyper-realistic Bulbasaur..." \
     --output "bulbasaur/assets/characters/bulbasaur_walking.png"
   ```

4. **Script executes:**
   - Loads `.env` for `GEMINI_API_KEY`
   - Calls `genai.generate_image(prompt=COMBINED_PROMPT)`
   - Downloads base64 image data
   - Saves as PNG at specified path
   - Exits with code 0

5. **Agent reports:** "✅ Generated: bulbasaur_walking.png"

---

## Extension Points

The architecture is extensible:

### Adding New Scripts
1. Create new script in `scripts/` following CLI pattern
2. Document in `prompts/` for agent use
3. No changes needed to existing scripts

### Adding New Services
1. Add API key to `.env`
2. Add dependency to `pyproject.toml`
3. Create script wrapper for service
4. Update agent instructions

### Adding New Pipelines
1. Create new workflow in `prompts/`
2. Reuse existing scripts where possible
3. Add new scripts only for unique operations

---

## Benefits of This Architecture

**Simplicity:** Each script is <500 lines, single purpose, easy to understand

**Testability:** Scripts can be tested in isolation with mock inputs

**Flexibility:** Agents can be swapped (Claude → Gemini → other)

**Portability:** Scripts work standalone, can be called from any orchestrator

**Maintainability:** Changes are localized, low coupling between components

**Debuggability:** Each step writes files, easy to inspect intermediate state

**Cost Efficiency:** Failed steps can be retried without re-running entire pipeline
