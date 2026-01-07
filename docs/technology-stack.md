# Technology Stack

## Overview

**Project:** ai-video-generator
**Type:** CLI Automation Pipeline
**Language:** Python 3.10+
**Architecture Pattern:** Pipeline-based CLI with AI service orchestration

---

## Core Technologies

| Category | Technology | Version | Justification |
|----------|-----------|---------|---------------|
| **Language** | Python | 3.10+ (3.14.2 installed) | Required for AI SDK compatibility and async operations |
| **Package Manager** | uv | Latest | Modern Python package manager, fast dependency resolution |
| **Video Processing** | FFmpeg | 8.0.1 | Industry-standard video manipulation, trimming, and concatenation |

---

## Python Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `google-generativeai` | >=0.8.0 | Google Gemini 2.5 Flash image generation SDK |
| `python-dotenv` | >=1.0.0 | Environment variable management for API keys |
| `pillow` | >=10.0.0 | Image manipulation (compositing, resizing, format conversion) |
| `pyjwt` | >=2.8.0 | JWT token generation for KIE.ai API authentication |
| `requests` | >=2.31.0 | HTTP client for API calls and image uploads |

---

## External AI Services

| Service | Purpose | API Endpoint | Authentication |
|---------|---------|--------------|----------------|
| **Google Gemini 2.5 Flash** | Photorealistic image generation | `generativeai` SDK | API Key (GEMINI_API_KEY) |
| **KIE.ai Kling 2.5 Pro** | Video generation from images | `https://api.kie.ai/api/v1` | API Key + JWT (KIE_API_KEY) |
| **ElevenLabs v3** | Audio narration and sound effects | ElevenLabs API | API Key (ELEVENLABS_API_KEY) |
| **catbox.moe** | Free public image hosting | `https://catbox.moe/user/api.php` | None (free service) |

---

## Architecture Pattern

### Pipeline-Based CLI Automation

**Pattern Description:**
- **Single-purpose scripts:** Each Python script performs one atomic operation (generate asset, generate video, assemble final)
- **Agent orchestration:** AI agents (Claude Code, Gemini) read project files and call scripts with complete arguments
- **Filesystem as state:** No databases or state management - all inputs/outputs are files
- **Separation of concerns:** "Smart Agent + Dumb Scripts" - agents handle logic, scripts handle API calls

**Key Characteristics:**
1. **Stateless Scripts:** Each script is a pure CLI tool with no internal state
2. **Complete Inputs:** Scripts receive fully-formed prompts and paths from agents
3. **Atomic Operations:** One script = one API call or processing task
4. **Orchestration Layer:** Agents combine prompts, manage workflows, handle errors

**Example Flow:**
```
Agent reads {pokemon}/03_assets.md
  → Extracts Global Atmosphere + Asset Prompts
  → Combines prompts
  → Calls: python generate_asset.py --prompt "COMBINED" --output "path.png"
  → Script calls Gemini API → Downloads image → Exits
  → Agent reports success/failure
```

---

## Development Tools

| Tool | Purpose |
|------|---------|
| **uv** | Fast Python package management and virtual environment |
| **FFmpeg** | Video trimming, audio sync, concatenation |
| **Claude Code** | AI agent orchestration and workflow automation |

---

## Configuration Management

**Method:** Environment variables via `.env` file

**Required Variables:**
```bash
GEMINI_API_KEY=...              # Google Gemini API
KIE_API_KEY=...                 # KIE.ai Kling 2.5
ELEVENLABS_API_KEY=...          # ElevenLabs narration
ELEVENLABS_VOICE_ID=...         # ElevenLabs voice selection
```

**Configuration Location:** `scripts/.env` (gitignored)

---

## System Requirements

### Required
- Python 3.10 or higher
- FFmpeg (any recent version with H.264 support)
- Internet connection (for API calls)
- API keys for Gemini, KIE.ai, ElevenLabs

### Recommended
- 8GB+ RAM (for video processing)
- 10GB+ free disk space (for video outputs)
- macOS, Linux, or Windows with WSL

---

## Technology Justification Summary

**Python 3.10+:** Required for modern async/await support and AI SDK compatibility

**uv Package Manager:** Significantly faster than pip, better dependency resolution

**FFmpeg:** De facto standard for video processing, supports all required codecs

**Gemini 2.5 Flash:** Cost-effective photorealistic image generation with high quality

**Kling 2.5:** State-of-the-art AI video generation from static images

**ElevenLabs v3:** Industry-leading voice cloning and narration quality

**Pillow:** Pure Python image library, easy to use for compositing and transformations

**catbox.moe:** Free, reliable image hosting without API keys (simplifies workflow)
