# Development Guide

## Overview

This guide provides complete setup and development instructions for the ai-video-generator project.

---

## Prerequisites

### Required Software

| Software | Minimum Version | Purpose | Installation |
|----------|----------------|---------|--------------|
| **Python** | 3.10+ | Runtime environment | [python.org](https://www.python.org/downloads/) |
| **uv** | Latest | Package manager | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **FFmpeg** | Any recent | Video processing | See platform-specific instructions below |
| **Claude Code** | Latest | AI orchestration (optional) | [claude.ai/claude-code](https://claude.ai/claude-code) |

### Required API Keys

| Service | Purpose | Get Key From |
|---------|---------|--------------|
| **Gemini API** | Image generation | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| **KIE.ai API** | Video generation | [kie.ai](https://kie.ai) |
| **ElevenLabs API** | Audio/narration | [elevenlabs.io](https://elevenlabs.io) |
| **ElevenLabs Voice ID** | Voice selection | ElevenLabs dashboard |

---

## Installation

### 1. Install uv (Python Package Manager)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Verify installation:**
```bash
uv --version
```

### 2. Install FFmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

**Windows:**
- Download from [ffmpeg.org/download.html](https://ffmpeg.org/download.html)
- Extract and add to PATH

**Verify installation:**
```bash
ffmpeg -version
```

### 3. Clone Repository

```bash
git clone https://github.com/your-username/ai-video-generator.git
cd ai-video-generator
```

### 4. Install Python Dependencies

```bash
uv sync
```

This installs:
- `google-generativeai>=0.8.0`
- `python-dotenv>=1.0.0`
- `pillow>=10.0.0`
- `pyjwt>=2.8.0`
- `requests>=2.31.0`

### 5. Configure API Keys

```bash
# Copy the example environment file
cp scripts/.env.example scripts/.env

# Edit scripts/.env and add your API keys
nano scripts/.env  # or use your preferred editor
```

**Required configuration:**
```bash
# scripts/.env
GEMINI_API_KEY=your_actual_gemini_key_here
KIE_API_KEY=your_actual_kie_key_here
ELEVENLABS_API_KEY=your_actual_elevenlabs_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here
```

**Security Note:** The `.env` file is gitignored. Never commit API keys to version control.

---

## Environment Setup

### Virtual Environment

uv automatically creates and manages a virtual environment in `.venv/`:

**Activate manually (if needed):**
```bash
# macOS/Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

**Deactivate:**
```bash
deactivate
```

### Python Version

Check your Python version:
```bash
python3 --version
```

Must be **3.10 or higher** for compatibility with AI SDKs.

---

## Running Scripts

### CLI Usage Pattern

All scripts follow this pattern:
```bash
python scripts/<script_name>.py --arg1 value1 --arg2 value2 --output output.file
```

### Individual Script Commands

#### 1. Generate Image Assets

```bash
python scripts/generate_asset.py \
  --prompt "Complete prompt text here" \
  --output "path/to/output.png"
```

**With reference images (for variations):**
```bash
python scripts/generate_asset.py \
  --prompt "Variation prompt" \
  --reference-image "ref1.png" \
  --reference-image "ref2.png" \
  --output "variation.png"
```

#### 2. Create Composite Images

```bash
python scripts/create_composite.py \
  --character "path/to/character.png" \
  --environment "path/to/environment.png" \
  --output "path/to/composite.png" \
  --scale 1.0  # Optional character scaling
```

#### 3. Generate Videos

```bash
python scripts/generate_video.py \
  --image "path/to/composite.png" \
  --prompt "Character walks forward slowly" \
  --output "path/to/video.mp4"
```

#### 4. Generate Audio

```bash
python scripts/generate_audio.py \
  --text "After... the rain... hunger awakens." \
  --output "path/to/audio.mp3"
```

#### 5. Generate Sound Effects

```bash
python scripts/generate_sound_effects.py \
  --prompt "Rain falling on leaves, distant thunder" \
  --output "path/to/sfx.wav"
```

#### 6. Assemble Final Video

```bash
python scripts/assemble_video.py \
  --manifest "path/to/manifest.json" \
  --output "final_video.mp4"
```

---

## Development Workflow

### Typical Development Session

1. **Activate environment (if not using uv run):**
   ```bash
   source .venv/bin/activate
   ```

2. **Test a single script:**
   ```bash
   python scripts/generate_asset.py --help
   ```

3. **Run script with test inputs:**
   ```bash
   python scripts/generate_asset.py \
     --prompt "Test image generation" \
     --output "test_output.png"
   ```

4. **Check output:**
   ```bash
   ls -lh test_output.png
   open test_output.png  # macOS
   ```

5. **Deactivate when done:**
   ```bash
   deactivate
   ```

### Using uv run (Recommended)

Instead of activating the environment, use `uv run`:

```bash
uv run python scripts/generate_asset.py --prompt "..." --output "..."
```

This automatically uses the project's virtual environment.

---

## Testing

### Current Testing Status

**⚠️ No automated tests currently exist.**

### Manual Testing Approach

Test each script independently:

```bash
# Test image generation
python scripts/generate_asset.py \
  --prompt "A test image" \
  --output "test.png"

# Test compositing
python scripts/create_composite.py \
  --character "test_char.png" \
  --environment "test_env.png" \
  --output "test_composite.png"

# Test video generation (requires API credit)
python scripts/generate_video.py \
  --image "test_composite.png" \
  --prompt "Subject stands still" \
  --output "test_video.mp4"
```

### Future Test Structure (Recommended)

```
tests/
  ├── test_generate_asset.py
  ├── test_create_composite.py
  ├── test_generate_video.py
  ├── test_generate_audio.py
  ├── test_generate_sound_effects.py
  └── test_assemble_video.py
```

---

## Build Process

### No Build Step Required

This is a **pure Python project** with no compilation:
- No transpilation
- No bundling
- No minification

**Dependencies are managed by uv:**
```bash
uv sync  # Install/update all dependencies
```

---

## Common Development Tasks

### Update Dependencies

```bash
# Update all dependencies to latest compatible versions
uv sync --upgrade

# Check for outdated packages
uv pip list --outdated
```

### Add New Dependency

```bash
# Add to pyproject.toml
nano pyproject.toml  # Add to dependencies = [...]

# Install
uv sync
```

### Clean Environment

```bash
# Remove virtual environment
rm -rf .venv

# Recreate from scratch
uv sync
```

### Check Environment

```bash
# List installed packages
uv pip list

# Show dependency tree
uv pip show google-generativeai
```

---

## Troubleshooting

### "GEMINI_API_KEY not found"

**Solution:**
```bash
# Ensure .env file exists in scripts/
ls scripts/.env

# Check contents (without revealing keys)
grep "GEMINI_API_KEY" scripts/.env

# If missing, copy from example
cp scripts/.env.example scripts/.env
# Edit and add your key
```

### "FFmpeg not found"

**Solution:**
```bash
# Check if FFmpeg is in PATH
which ffmpeg  # macOS/Linux
where ffmpeg  # Windows

# If not found, reinstall FFmpeg and verify PATH
```

### "Module not found" errors

**Solution:**
```bash
# Reinstall dependencies
uv sync

# Verify Python version
python3 --version  # Must be 3.10+

# Check if in correct directory
pwd  # Should end with ai-video-generator
```

### "Permission denied" on uv install

**Solution:**
```bash
# macOS/Linux: Install to user directory
curl -LsSf https://astral.sh/uv/install.sh | sh

# Ensure ~/.local/bin is in PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Video generation timeout

**Solution:**
```bash
# Kling can take 2-5 minutes per video
# Default timeout is 10 minutes
# If timing out, check KIE.ai dashboard for task status
# Or increase timeout in generate_video.py line 163
```

---

## Performance Optimization

### Parallel Execution

Scripts are independent - run multiple in parallel:

```bash
# Generate multiple assets in parallel (use separate terminals)
python scripts/generate_asset.py --prompt "Asset 1" --output "asset1.png" &
python scripts/generate_asset.py --prompt "Asset 2" --output "asset2.png" &
python scripts/generate_asset.py --prompt "Asset 3" --output "asset3.png" &
wait  # Wait for all to complete
```

**Or use GNU parallel:**
```bash
# Install GNU parallel
brew install parallel  # macOS
sudo apt-get install parallel  # Ubuntu

# Run multiple asset generations
parallel python scripts/generate_asset.py --prompt {1} --output {2}.png ::: \
  "Prompt1" "Prompt2" "Prompt3" ::: \
  "asset1" "asset2" "asset3"
```

### Disk Space Management

```bash
# Check project size
du -sh .

# Clean up old workspaces
rm -rf old_pokemon_directory/

# Archive completed projects
tar -czf bulbasaur_archive.tar.gz bulbasaur/
rm -rf bulbasaur/
```

---

## Git Workflow

### Recommended .gitignore

Already configured to ignore:
- `*.mp4`, `*.mov` (video files)
- `*/videos/`, `*/final/` (video directories)
- `.env` (API keys)
- `.venv/` (virtual environment)
- `__pycache__/`, `*.pyc` (Python bytecode)

### Committing Changes

```bash
# Check status
git status

# Add changes
git add scripts/new_script.py

# Commit with clear message
git commit -m "Add new video processing script"

# Push to remote
git push origin main
```

**Never commit:**
- API keys (`.env`)
- Large video files
- Virtual environment files

---

## IDE Setup

### VS Code (Recommended)

**Extensions:**
- Python (Microsoft)
- Pylance (Microsoft)
- GitLens

**Workspace Settings (.vscode/settings.json):**
```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "black",
  "[python]": {
    "editor.tabSize": 4
  }
}
```

### PyCharm

1. Open project directory
2. Configure interpreter: File → Settings → Project → Python Interpreter
3. Select `.venv/bin/python`
4. Enable auto-imports and code completion

---

## Deployment

### This is a CLI Tool - No Deployment Required

The project is designed to run **locally** on your machine:
- No web server
- No cloud deployment
- No containerization needed

### Sharing with Others

**Option 1: Share Repository**
```bash
git clone https://github.com/your-username/ai-video-generator.git
cd ai-video-generator
uv sync
cp scripts/.env.example scripts/.env
# User adds their own API keys
```

**Option 2: Share Scripts Only**
```bash
# Package just the scripts
tar -czf ai-video-scripts.tar.gz scripts/ pyproject.toml README.md
```

---

## Cost Management

### Estimated Costs Per Documentary

| Service | Usage | Cost |
|---------|-------|------|
| Gemini (22 images) | ~$0.50-2.00 | Image generation |
| KIE.ai (18 videos) | ~$5-10 | Video generation |
| ElevenLabs (18+18 audio clips) | ~$0.50-1.00 | Narration + SFX |
| **Total** | **~$6-13** | Per 90-second documentary |

### Reducing Costs

1. **Test with fewer clips:** Start with 5 clips instead of 18
2. **Reuse assets:** Use existing images for multiple videos
3. **Free tier usage:** Check if services offer free credits
4. **Batch generation:** Generate multiple projects in one session

---

## Getting Help

### Documentation

- **Project README:** `README.md`
- **Claude Guide:** `CLAUDE.md`
- **Scripts Documentation:** `scripts/README.md`
- **This Guide:** `docs/development-guide.md`

### Common Issues

Check the Troubleshooting section above for:
- API key errors
- FFmpeg issues
- Module not found errors
- Permission problems

### Community

- GitHub Issues: Report bugs and request features
- GitHub Discussions: Ask questions and share tips

---

## Summary

**Quick Start Checklist:**
- ✅ Install Python 3.10+
- ✅ Install uv package manager
- ✅ Install FFmpeg
- ✅ Run `uv sync`
- ✅ Configure `scripts/.env` with API keys
- ✅ Test a single script
- ✅ Ready to generate videos!

**Key Commands:**
```bash
uv sync                    # Install dependencies
python scripts/<name>.py   # Run individual scripts
uv run python scripts/...  # Run with uv (auto-activates env)
```

**Remember:**
- Scripts are independent - test individually
- API keys must be in `scripts/.env`
- Each Pokemon gets its own workspace directory
- Filesystem tracks all state - no databases needed
