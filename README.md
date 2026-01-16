# Pokémon Natural Geographic

A complete production pipeline for creating hyper-realistic Pokémon nature documentaries using AI tools.

## What This Is

Transform Pokémon into photorealistic wildlife documentaries in the style of David Attenborough's *Planet Earth*. This pipeline takes you from concept to finished 90-second video clip.

**Example:** "First Spark" - A juvenile Pikachu's failed hunt attracts a predatory Fearow, forcing the colony into defensive formation.

## Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://astral.sh/uv) (Python package manager)
- [FFmpeg](https://ffmpeg.org) (video processing)
- [Claude Code](https://claude.ai/claude-code) (AI assistant)
- API Keys:
  - [Gemini API](https://aistudio.google.com/app/apikey) for image generation
  - [KIE.ai API](https://kie.ai) for video generation (Kling 2.5 wrapper)
  - [ElevenLabs API](https://elevenlabs.io) for narration

### Setup

```bash
# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install FFmpeg
# macOS:
brew install ffmpeg
# Ubuntu/Debian:
sudo apt-get install ffmpeg
# Windows: Download from https://ffmpeg.org/download.html

# 3. Install dependencies
uv sync

# 4. Configure API keys
cp scripts/.env.example scripts/.env
# Edit scripts/.env and add:
#   GEMINI_API_KEY=your_gemini_key
#   KIE_API_KEY=your_kie_key
#   ELEVENLABS_API_KEY=your_elevenlabs_key
#   ELEVENLABS_VOICE_ID=your_voice_id
```

## The 8-Step Production Pipeline

### **SOP 01: Species Research** 📚

**What:** Create a biological profile for your chosen Pokémon.

**How:**
1. Open `prompts/1_research.md` in Claude Code
2. Replace `{{POKEMON_NAME}}` with your Pokémon (e.g., "Pikachu")
3. Claude generates a species profile including:
   - Physiological details (textures, anatomy)
   - Ecological niche (habitat, diet)
   - Story hooks for documentaries

**Output:** `{pokemon}/01_research.md`

**Time:** ~5 minutes (manual)

---

### **SOP 02: Story Development** 🎬

**What:** Choose a 90-second documentary story.

**How:**
1. Open `prompts/2_story_generator.md` in Claude Code
2. Claude generates 5 story options
3. You select one (e.g., "First Spark")
4. Claude creates an 18-clip production script (18 × 5 seconds = 90s)

**Output:** `{pokemon}/02_story_script.md`

**Time:** ~10 minutes (manual)

---

### **SOP 03: Asset Generation** 🎨

**What:** Generate 20-25 photorealistic seed images for video production.

**How:**
1. Open `prompts/3.5_generate_assets_agent.md` in Claude Code
2. Tell Claude: "Generate assets for {pokemon}"
3. Claude automatically:
   - Reads `{pokemon}/03_assets.md`
   - Extracts Global Atmosphere Block
   - Extracts all 22 asset definitions
   - Calls `scripts/generate_asset.py` for each asset
   - Reports progress and errors

**Output:** `{pokemon}/assets/` (characters/, props/, environments/)

**Time:** ~5-10 minutes (automated)

**Example:**
```bash
# The agent calls this for each asset:
python scripts/generate_asset.py \
  --prompt "COMBINED_ATMOSPHERE_AND_ASSET_PROMPT" \
  --output "pikachu/assets/characters/pikachu_adult_alert.png"
```

---

### **SOP 03.5: Composite Image Generation** 🖼️

**What:** Combine character and environment assets into YouTube-ready 16:9 composite seed images for Kling 2.5.

**Why This Matters:**
- Kling 2.5 requires 1920x1080 (16:9) images for proper YouTube output
- Raw environment images are often ultra-wide cinematic format (2.36:1)
- Composite generation ensures characters are properly positioned and scaled

**How:**
1. Use `scripts/create_composite.py` to combine character + environment
2. Script automatically scales/crops to 1920x1080 (16:9)
3. For split-screen shots, use `scripts/create_split_screen.py` for horizontal splits

**Output:** `{pokemon}/assets/composites/` (clip_XX_composite.png files at 1920x1080)

**Time:** ~1-2 minutes (manual or automated via agent)

**Example:**
```bash
# Standard composite (character on environment):
python scripts/create_composite.py \
  --character "haunter/assets/characters/haunter_floating_alert.png" \
  --environment "haunter/assets/environments/env_hallway_pitch_black.png" \
  --output "haunter/assets/composites/clip_02_composite.png" \
  --scale 1.0

# Horizontal split-screen (for multi-domain shots):
python scripts/create_split_screen.py \
  # Creates 1920x1080 with left/right domains
```

**Technical Details:**
- Enforces YouTube standard 1920x1080 (16:9) output
- Handles aspect ratio conversion (crop/scale/pad)
- Centers characters on final canvas
- Preserves alpha transparency during composition

---

### **SOP 04: Video Prompt Engineering** 📝

**What:** Create motion prompts for Kling 2.5 that follow the **Priority Hierarchy**.

**The Priority Hierarchy (CRITICAL):**
1. **Core Action FIRST** - What is happening
2. **Specific Details** - What parts are moving, how they're moving
3. **Logical Sequence** - Step-by-step cause and effect
4. **Environmental Context** - Atmosphere, lighting, weather
5. **Camera Movement LAST** - Aesthetic enhancement only

**Why This Order:**
- AI models prioritize the beginning of prompts
- Core action establishes what the clip is fundamentally about
- Camera movement is enhancement, not story-critical
- If the model runs out of "attention", it should drop camera movement, not core action

**Example Structure:**
```
[Subject] [does action]. [Specific body part] [does specific thing]. [Result happens]. [Environmental detail]. [Camera movement].
```

**Good Prompt:**
```
Haunter floats in dark corridor. Haunter presses both clawed hands against wall attempting to phase through. Haunter bounces backward unable to phase. Purple glow pulses brighter. Clawed hands pull back from wall. Dark purple smoke swirls. Slow zoom in.
```

**Bad Prompt (Camera First):**
```
Slow zoom in. Haunter attempts to phase through wall but bounces backward.
```

See `prompts/4_video_prompt_engineering.md` for complete guidelines.

---

### **SOP 05: Video Generation** 🎥

**What:** Animate composite seed images into 18 ten-second video clips using Kling 2.5.

**How:**
1. Open `prompts/4.5_generate_videos_agent.md` in Claude Code
2. Tell Claude: "Generate videos for {pokemon}"
3. Claude automatically:
   - Reads `{pokemon}/04_video_prompts.md` for motion prompts
   - Reads `{pokemon}/assets/composites/` for composite seed images
   - Uploads images to catbox.moe (free hosting)
   - Calls KIE.ai Kling 2.5 API for each clip
   - Downloads finished MP4s

**Output:** `{pokemon}/videos/` (clip_01.mp4 through clip_18.mp4, each 10 seconds)

**Time:** ~1-2 hours (automated, but slow API processing)

**Example:**
```bash
# The agent calls this for each clip (using composite images):
python scripts/generate_video.py \
  --image "haunter/assets/composites/clip_02_composite.png" \
  --prompt "Haunter floats in dark corridor. Haunter presses both clawed hands against wall attempting to phase through. Haunter bounces backward unable to phase. Purple glow pulses. Slow zoom in." \
  --output "haunter/videos/clip_02.mp4"
```

**Technical Details:**
- Uses KIE.ai Kling 2.5 Pro API
- Requires composite images at 1920x1080 (16:9) for YouTube output
- Uploads images to catbox.moe for public URL
- Each video takes 2-5 minutes to generate
- 10-minute timeout per clip (adjustable)
- Videos are 10 seconds (trimmed to match audio in SOP 07)

---

### **SOP 06: Audio Generation** 🎙️

**What:** Generate David Attenborough-style narration with ElevenLabs v3.

**How:**
1. Open `prompts/5.5_generate_audio_agent.md` in Claude Code
2. Tell Claude: "Generate audio for {pokemon}"
3. Claude automatically:
   - Reads `{pokemon}/05_audio_generation.md`
   - Extracts 18 narration lines (with ellipses for pacing)
   - Calls ElevenLabs API for each clip
   - Saves MP3 files

**Output:** `{pokemon}/audio/` (clip_01.mp3 through clip_18.mp3)

**Time:** ~1-2 minutes (automated, very fast)

**Example:**
```bash
# The agent calls this for each narration line:
python scripts/generate_audio.py \
  --text "After... the rain... hunger awakens." \
  --output "pikachu/audio/clip_01.mp3"
```

**Voice Settings:**
- Model: v3 (enhanced multilingual)
- Stability: 40%
- Similarity: 75%
- Style: 12%

---

### **SOP 07: Sound Effects Generation** 🔊

**What:** Generate atmospheric sound effects for each clip (rain, electricity, footsteps, etc.).

**How:**
1. Open `prompts/6.5_generate_sound_effects_agent.md` in Claude Code
2. Tell Claude: "Generate sound effects for {pokemon}"
3. Claude automatically:
   - Reads `{pokemon}/06_sound_effects.md`
   - Extracts SFX descriptions for each clip
   - Calls ElevenLabs Sound Effects API
   - Saves WAV files

**Output:** `{pokemon}/sfx/` (clip_01_sfx.wav through clip_18_sfx.wav)

**Time:** ~2-3 minutes (automated)

---

### **SOP 08: Final Assembly** 🎞️

**What:** Combine all 18 video/audio/SFX clips into the final 90-second documentary.

**How:**
1. Open `prompts/7_assemble_final_agent.md` in Claude Code
2. Tell Claude: "Assemble final video for {pokemon}"
3. Claude automatically:
   - Scans `{pokemon}/videos/` for all 18 video clips
   - Scans `{pokemon}/audio/` for all 18 audio clips
   - Scans `{pokemon}/sfx/` for all 18 sound effect clips
   - Verifies all clips exist
   - Creates assembly manifest JSON
   - Calls FFmpeg to trim videos and sync audio/SFX
   - Concatenates all clips into final MP4

**Output:** `{pokemon}/{pokemon}_final.mp4` (90-second documentary at 1080p 16:9)

**Time:** ~2-3 minutes (automated, very fast)

**Example:**
```bash
# The agent calls this internally:
python scripts/assemble_video.py \
  --manifest "pikachu/assembly_manifest.json" \
  --output "pikachu/pikachu_final.mp4"
```

**Technical Details:**
- Trims each video to match audio duration (audio clips typically 6-8s)
- Mixes narration + sound effects on separate audio tracks
- Hard cuts between clips (no transitions)
- 1080p 16:9 resolution, H.264 codec, AAC audio
- Each clip takes ~5 seconds to process
- Final concatenation takes ~10-20 seconds

---

## Example: Complete Haunter Workflow

```bash
# Already completed as examples:
# 1. Research → haunter/01_research.md ✅
# 2. Story → haunter/02_story_script.md ✅
# 3. Asset Planning → haunter/03_assets.md ✅

# SOP 03: Generate all assets (automated):
# Open prompts/3.5_generate_assets_agent.md in Claude Code
# Tell Claude: "Generate assets for haunter"
# Wait ~5-10 minutes for character/environment images
# Output: haunter/assets/characters/ and haunter/assets/environments/

# SOP 03.5: Generate composite images (automated):
# Combine character + environment into YouTube-ready 16:9 composites
# Claude automatically creates composites at 1920x1080
# Wait ~1-2 minutes
# Output: haunter/assets/composites/

# SOP 04: Create video prompts (already completed):
# → haunter/04_video_prompts.md ✅
# (Uses Priority Hierarchy: Core Action → Details → Sequence → Environment → Camera LAST)

# SOP 05: Generate all videos (automated):
# Open prompts/4.5_generate_videos_agent.md in Claude Code
# Tell Claude: "Generate videos for haunter"
# Wait ~1-2 hours for 16 video clips
# Output: haunter/videos/

# SOP 06: Generate all audio (automated):
# Open prompts/5.5_generate_audio_agent.md in Claude Code
# Tell Claude: "Generate audio for haunter"
# Wait ~1-2 minutes for 16 audio clips
# Output: haunter/audio/

# SOP 07: Generate sound effects (automated):
# Open prompts/6.5_generate_sound_effects_agent.md in Claude Code
# Tell Claude: "Generate sound effects for haunter"
# Wait ~2-3 minutes for 16 SFX clips
# Output: haunter/sfx/

# SOP 08: Assemble final video (automated):
# Open prompts/7_assemble_final_agent.md in Claude Code
# Tell Claude: "Assemble final video for haunter"
# Wait ~2-3 minutes for video assembly
# Output: haunter/haunter_final.mp4

# Done! Your 90-second Pokémon documentary is ready! 🎉
```

## Project Structure

```
pokemon-natural-geo/
├── README.md                               ← You are here
├── prompts/                                ← Agent instructions for each SOP
│   ├── 1_research.md                      ← SOP 01: Species research
│   ├── 2_story_generator.md               ← SOP 02: Story development
│   ├── 3_character_generation.md          ← SOP 03: Asset planning guide
│   ├── 3.5_generate_assets_agent.md       ← SOP 03: Automated asset generation
│   ├── 4_video_prompt_engineering.md      ← SOP 04: Video prompt engineering guide
│   ├── 4.5_generate_videos_agent.md       ← SOP 05: Automated video generation
│   ├── 5_voice_prompt_engineer.md         ← SOP 06: Audio planning guide
│   ├── 5.5_generate_audio_agent.md        ← SOP 06: Automated audio generation
│   ├── 6_sound_effects_prompt_engineering.md ← SOP 07: Sound effects planning
│   ├── 6.5_generate_sound_effects_agent.md   ← SOP 07: Automated SFX generation
│   └── 7_assemble_final_agent.md          ← SOP 08: Automated video assembly
├── scripts/                                ← Python automation tools
│   ├── generate_asset.py                  ← Image generation CLI (Gemini)
│   ├── create_composite.py                ← Composite generation (16:9 enforced)
│   ├── create_split_screen.py             ← Horizontal split-screen composites
│   ├── generate_video.py                  ← Video generation CLI (KIE.ai)
│   ├── generate_audio.py                  ← Audio generation CLI (ElevenLabs)
│   ├── assemble_video.py                  ← Video assembly CLI (FFmpeg)
│   ├── README.md                          ← Technical documentation
│   └── .env                               ← Your API keys (create this)
├── haunter/                                ← Example Pokemon (Haunter episode)
│   ├── 01_research.md                     ← Species biological profile
│   ├── 02_story_script.md                 ← Story narrative
│   ├── 03_assets.md                       ← Asset manifest
│   ├── 04_video_prompts.md                ← Kling 2.5 motion prompts
│   ├── 05_audio_generation.md             ← Narration scripts
│   ├── 06_sound_effects.md                ← SFX descriptions
│   ├── assembly_manifest.json             ← Clip manifest (SOP 08)
│   ├── assets/                            ← Generated images (SOP 03)
│   │   ├── characters/                    ← Character PNGs (transparent)
│   │   ├── environments/                  ← Environment backgrounds
│   │   └── composites/                    ← YouTube-ready 16:9 composites (SOP 03.5)
│   ├── videos/                            ← Generated videos (SOP 05)
│   ├── audio/                             ← Generated narration (SOP 06)
│   ├── sfx/                               ← Generated sound effects (SOP 07)
│   └── haunter_final.mp4                  ← Final documentary (SOP 08)
└── pyproject.toml                          ← Python dependencies (uv)
```

## Philosophy: The "Breathing Photograph" Approach

**Key Constraint:** AI video generators work best when animating **one static image with one micro-movement**, not complex action sequences.

**Examples:**
- ✅ Good: "A Pikachu standing alert, ears twitching"
- ❌ Bad: "A Pikachu crouching, then leaping at prey"

**Solution:** Break complex scenes into multiple clips, each a single "breathing photograph."

**Video/Audio Duration:**
- Kling 2.5 generates 10-second video clips (not configurable)
- Audio narration is 6-8 seconds per clip (paced with ellipses)
- FFmpeg automatically trims each 10-second video to match its 6-8 second audio
- 18 clips with trimmed durations = ~108-144 second documentary (target: ~120s = 2 minutes)

## Technical Stack

| Component | Tool | Purpose | Status |
|-----------|------|---------|--------|
| Image Generation | Google Gemini 2.5 Flash Image | Photorealistic seed images | ✅ Working |
| Video Generation | KIE.ai Kling 2.5 Pro | Animate seed images (10s clips) | ✅ Working |
| Audio Generation | ElevenLabs v3 | David Attenborough-style narration | ✅ Working |
| Video Assembly | FFmpeg | Trim, sync, and concatenate clips | ✅ Working |
| Image Hosting | catbox.moe | Free public URLs for KIE.ai | ✅ Working |
| Orchestration | Claude Code | AI agent automation | ✅ Working |
| Environment | uv + Python 3.10+ | Dependency management | ✅ Working |

## Architecture: Smart Agent + Dumb Scripts

All automation follows the same pattern:

**Agent (Smart):**
- Reads project files
- Extracts data
- Combines prompts
- Orchestrates workflow
- Handles errors

**Python Scripts (Dumb):**
- Take complete inputs
- Call one API
- Return success/failure
- No file reading
- No logic

**Example:**
```
Agent reads assets.md → Extracts prompt → Combines atmosphere
   ↓
Agent calls: python generate_asset.py --prompt "COMPLETE_PROMPT" --output "path.png"
   ↓
Script calls Gemini API → Downloads image → Exits
```

This keeps scripts simple, testable, and reusable.

## Local Development: Running Worker Processes

The orchestration platform uses separate worker processes to handle video generation tasks. Here's how to run and test workers locally:

### Running a Single Worker

```bash
# Set environment variables
export DATABASE_URL="postgresql://user:pass@localhost:5432/ai_video_gen"
export FERNET_KEY="your-44-character-base64-encryption-key"

# Start worker process
python -m app.worker
```

The worker will:
- Initialize database connection pool (pool_size=10)
- Enter continuous event loop
- Log heartbeat every 60 seconds
- Exit gracefully on Ctrl+C (SIGINT)

### Running Multiple Workers (Parallel Testing)

Test worker independence by running multiple workers in separate terminals:

```bash
# Terminal 1: Worker 1
export DATABASE_URL="postgresql://user:pass@localhost:5432/ai_video_gen"
export FERNET_KEY="your-encryption-key"
export RAILWAY_SERVICE_NAME="worker-1"
python -m app.worker

# Terminal 2: Worker 2
export DATABASE_URL="postgresql://user:pass@localhost:5432/ai_video_gen"
export FERNET_KEY="your-encryption-key"
export RAILWAY_SERVICE_NAME="worker-2"
python -m app.worker

# Terminal 3: Worker 3
export DATABASE_URL="postgresql://user:pass@localhost:5432/ai_video_gen"
export FERNET_KEY="your-encryption-key"
export RAILWAY_SERVICE_NAME="worker-3"
python -m app.worker
```

**What to verify:**
- Each worker logs with different `worker_id` (worker-1, worker-2, worker-3)
- Workers don't interfere with each other
- Stopping one worker doesn't affect others
- All workers share same database connection pool

### Expected Log Output

When a worker starts successfully, you should see:

```json
{
  "event": "worker_started",
  "worker_id": "worker-1",
  "timestamp": "2026-01-16T12:00:00Z",
  "level": "info"
}

{
  "event": "worker_heartbeat",
  "worker_id": "worker-1",
  "iteration_count": 60,
  "consecutive_errors": 0,
  "timestamp": "2026-01-16T12:01:00Z",
  "level": "info"
}
```

### Graceful Shutdown

Workers handle shutdown signals gracefully:

```bash
# Press Ctrl+C to trigger SIGINT
# Worker will:
# 1. Set shutdown flag
# 2. Complete current iteration
# 3. Close database connections
# 4. Exit with code 0
```

### Running with Web Service

You can run workers alongside the FastAPI web service:

```bash
# Terminal 1: Web service
uvicorn app.main:app --reload --port 8000

# Terminal 2: Worker
python -m app.worker

# Both share same DATABASE_URL and connection pool
```

### Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `DATABASE_URL` | Yes | PostgreSQL connection string | `postgresql://user:pass@localhost:5432/db` |
| `FERNET_KEY` | Yes | Encryption key (44-char base64) | Generate with `scripts/generate_fernet_key.py` |
| `RAILWAY_SERVICE_NAME` | No | Worker identifier for logs | `worker-1`, `worker-2`, `worker-local` (default) |
| `DATABASE_ECHO` | No | Enable SQL query logging | `true` or `false` (default) |

### Railway Deployment

On Railway, workers run as separate services:

```yaml
# Railway Configuration (via Dashboard)
Services:
  web:
    Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    Env Vars: DATABASE_URL, FERNET_KEY, RAILWAY_SERVICE_NAME=web

  worker-1:
    Start Command: python -m app.worker
    Env Vars: DATABASE_URL, FERNET_KEY, RAILWAY_SERVICE_NAME=worker-1

  worker-2:
    Start Command: python -m app.worker
    Env Vars: DATABASE_URL, FERNET_KEY, RAILWAY_SERVICE_NAME=worker-2

  worker-3:
    Start Command: python -m app.worker
    Env Vars: DATABASE_URL, FERNET_KEY, RAILWAY_SERVICE_NAME=worker-3
```

All services share the same PostgreSQL database and connection pool.

### Priority Queue Management

The orchestration platform supports **priority-based task processing** to ensure urgent content gets processed before normal workloads.

#### Priority Levels

Tasks can have one of three priority levels:

| Priority | Value | Use Case | Processing Order |
|----------|-------|----------|------------------|
| **High** | `high` | Trending topics, urgent videos, time-sensitive content | 1st (processed first) |
| **Normal** | `normal` | Regular content (most videos) | 2nd (default) |
| **Low** | `low` | Background tasks, batch jobs, non-urgent work | 3rd (processed last) |

#### How Priority Ordering Works

Workers claim tasks using a **priority-first, FIFO-within-priority** algorithm:

1. **High-priority tasks** are claimed before normal/low-priority tasks
2. **Within each priority level**, tasks are processed in **FIFO order** (first-in, first-out based on `created_at` timestamp)
3. **No starvation**: Low-priority tasks will execute when no higher-priority tasks are available

**Example Claiming Order:**
```
Pending Tasks:
  - Task A: high priority, created 1 hour ago
  - Task B: normal priority, created 2 hours ago
  - Task C: high priority, created 30 minutes ago
  - Task D: low priority, created 3 hours ago

Claiming Order:
  1. Task A (high, oldest high-priority)
  2. Task C (high, newer high-priority)
  3. Task B (normal, oldest normal-priority)
  4. Task D (low, only low-priority remaining)
```

#### Setting Task Priority

**Via Database (Current):**
```python
from app.models import Task, TaskPriority

task = Task(
    channel_id="poke1",
    notion_page_id="abc123",
    priority=TaskPriority.high,  # high, normal, or low
    status="pending"
)
```

**Via Notion (Future - Story 5.6):**
- Set the **Priority** dropdown in Notion (High/Normal/Low)
- Webhook automatically syncs to PostgreSQL
- Change priority anytime - takes effect immediately

#### Priority Logging

All worker logs include priority context for observability:

```json
{
  "event": "task_claimed",
  "worker_id": "worker-1",
  "task_id": "abc123",
  "priority": "high",
  "channel_id": "poke1"
}
```

Use this to monitor:
- Which priority levels are being processed
- High-priority task turnaround time
- Whether low-priority tasks are getting starved

#### Performance & Database Index

Priority ordering uses a **composite index** for fast queries:

```sql
CREATE INDEX idx_tasks_status_priority_created
ON tasks (status, priority, created_at);
```

**Query Performance:**
- **Without index:** 10s+ for 10,000+ tasks (full table scan)
- **With index:** <10ms (index scan)

The priority query is optimized:
```sql
SELECT * FROM tasks
WHERE status = 'pending'
ORDER BY
    CASE priority
        WHEN 'high' THEN 1
        WHEN 'normal' THEN 2
        WHEN 'low' THEN 3
    END ASC,
    created_at ASC
FOR UPDATE SKIP LOCKED
LIMIT 1
```

#### Best Practices

- **Use `normal` for 90%+ of tasks** - high/low are for exceptions
- **Reserve `high` for urgent content** - trending topics, paid tier, time-sensitive work
- **Use `low` for batch jobs** - analytics, cleanup, non-user-facing work
- **Monitor low-priority aging** - ensure low-priority tasks don't wait indefinitely
- **Don't abuse high priority** - too many high-priority tasks defeats the purpose

#### Implementation Details

- **Story 4.3:** Priority Queue Management
- **PgQueuer Integration:** Custom query configuration for priority ordering
- **Atomic Claiming:** PostgreSQL `FOR UPDATE SKIP LOCKED` ensures no race conditions
- **Migration:** `alembic/versions/20260116_0003_add_priority_index.py`

## FAQ

**Q: How much does this cost?**
A: Approximately per Pokemon documentary:
- Images (22 assets): ~$0.50-2.00 (Gemini)
- Videos (18 clips): ~$5-10 (KIE.ai credits)
- Audio (18 clips): ~$0.50-1.00 (ElevenLabs)
- **Total:** ~$6-13 per documentary

**Q: How long does generation take?**
A:
- Assets: ~5-10 minutes (automated)
- Videos: ~1-2 hours (automated but slow)
- Audio: ~1-2 minutes (automated)
- Assembly: ~1-2 minutes (automated)
- **Total automation time:** ~1.5-2.5 hours

**Q: Can I use different Pokémon?**
A: Yes! Just follow SOPs 1-2 to create research and story files for any Pokémon, then use the same automated pipeline.

**Q: Can I customize the voice?**
A: Yes! Update `ELEVENLABS_VOICE_ID` in `.env` to use any ElevenLabs voice. Default is optimized for nature documentary narration.

**Q: What if video generation fails?**
A: The agent continues with remaining clips. Check KIE.ai dashboard for failed tasks and retry manually or rerun the agent.

**Q: Can I use my own image hosting?**
A: Yes! Modify `scripts/generate_video.py` to upload to S3, Cloudinary, etc. instead of catbox.moe.

## Troubleshooting

**"Image upload failed"**
- catbox.moe may be down → Try again later or use different hosting

**"Video timeout after 10 minutes"**
- Kling AI is slow → Increase timeout in `generate_video.py:163`
- Or check KIE.ai dashboard and download manually

**"Audio sounds wrong"**
- Adjust voice settings: `--stability`, `--similarity`, `--style`
- Try different voice ID in `.env`

**"API key not found"**
- Ensure `scripts/.env` exists with all keys
- Check for typos in key names

## Contributing

This is a personal project but feel free to:
- Use it for your own Pokémon documentaries
- Report issues or suggestions
- Share your creations!

## Credits

**Concept:** Real Life Pokémon - Nature Documentary Series
**Production Pipeline:** Brandon Hancock
**AI Tools:** Google Gemini, KIE.ai Kling 2.5, ElevenLabs, Claude Code (Anthropic)
**Inspiration:** David Attenborough, National Geographic, BBC Earth

---

**Ready to start?** Follow the 6-step pipeline beginning with `prompts/1_research.md` 🚀
