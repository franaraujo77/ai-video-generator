# Project Overview

## Project Identity

**Name:** ai-video-generator
**Description:** Generic video generation automation
**Version:** 0.1.0
**Type:** CLI Automation Toolkit
**License:** Not specified

---

## Executive Summary

The ai-video-generator is a Python-based CLI automation pipeline that transforms text prompts and planning documents into professional-quality, AI-generated documentary videos. The system orchestrates multiple AI services (Google Gemini, Kling AI, ElevenLabs) through a series of atomic, single-purpose scripts coordinated by AI agents (Claude Code, Gemini).

**Primary Use Case:** Create 90-second photorealistic documentary-style videos through an 8-step production workflow.

**Key Innovation:** "Smart Agent + Dumb Scripts" architecture separates intelligent orchestration (agents) from simple execution (scripts), enabling maintainable, testable, and extensible automation.

---

## Project Purpose

### What Problem Does It Solve?

**Manual video production is time-consuming and expensive.** Creating a 90-second professional documentary requires:
- Concept development and storyboarding
- Asset creation (images, illustrations)
- Video shooting or animation
- Voice-over recording
- Sound design
- Video editing and assembly

**Traditional Timeline:** Weeks to months
**With ai-video-generator:** 1.5-2.5 hours (mostly automated)

### Who Is It For?

1. **Content Creators:** Generate video content quickly
2. **Educators:** Create educational documentaries
3. **Marketers:** Produce promotional videos
4. **Developers:** Learn AI service orchestration patterns
5. **Hobbyists:** Experiment with AI video generation

---

## Technology Stack Summary

### Core Technologies

| Category | Technology | Purpose |
|----------|-----------|---------|
| **Language** | Python 3.10+ | Runtime environment |
| **Package Manager** | uv | Dependency management |
| **Video Processing** | FFmpeg 8.0.1+ | Video manipulation |
| **Orchestration** | Claude Code | AI agent automation |

### AI Services

| Service | Purpose | Cost |
|---------|---------|------|
| **Google Gemini 2.5 Flash** | Photorealistic image generation | ~$0.50-2.00 per project |
| **Kling 2.5 (via KIE.ai)** | Video animation from images | ~$5-10 per project |
| **ElevenLabs v3** | Narration and sound effects | ~$0.50-1.00 per project |

**Total Cost Per Video:** ~$6-13 for 90-second documentary

---

## Architecture Type Classification

### Primary Pattern

**Pipeline-Based CLI Automation**

- **Definition:** Series of independent scripts that transform inputs through discrete stages
- **Orchestration:** AI agents coordinate script execution
- **State Management:** Filesystem-based (no databases)
- **Data Flow:** Sequential pipeline with intermediate outputs

### Architecture Characteristics

- ✅ **Stateless Components:** Each script is independent
- ✅ **Clear Separation:** Tools, orchestration, and data are isolated
- ✅ **Filesystem as State:** File existence indicates completion
- ✅ **Single Responsibility:** Each script performs one task
- ✅ **Idempotent Operations:** Re-running overwrites outputs

---

## Repository Structure

### Organization Type

**Monolith** - Single cohesive codebase with one part

**Key Directories:**
```
ai-video-generator/
├── scripts/         # 7 CLI automation tools (entry points)
├── prompts/         # Agent orchestration instructions
├── {project}/       # Per-project workspaces (isolated)
└── docs/            # Generated documentation
```

### Parts Breakdown

| Part ID | Type | Root Path | Description |
|---------|------|-----------|-------------|
| main | CLI | `/Users/francisaraujo/repos/ai-video-generator` | AI video generation automation pipeline |

**Integration Points:** None (single-part monolith)

---

## Quick Reference

### Tech Stack by Category

**Runtime:**
- Python 3.10+ (3.14.2 installed)
- uv package manager
- FFmpeg 8.0.1

**Python Dependencies:**
- `google-generativeai` - Gemini SDK
- `pillow` - Image manipulation
- `requests` - HTTP client
- `pyjwt` - JWT authentication
- `python-dotenv` - Configuration

**External Services:**
- Google Gemini 2.5 Flash
- KIE.ai (Kling 2.5)
- ElevenLabs v3
- catbox.moe (free image hosting)

### Entry Points

**All scripts located in `scripts/`:**

1. `generate_asset.py` - Image generation via Gemini
2. `create_composite.py` - 16:9 compositing for YouTube
3. `create_split_screen.py` - Split-screen compositor
4. `generate_video.py` - Video animation via Kling
5. `generate_audio.py` - Narration via ElevenLabs
6. `generate_sound_effects.py` - SFX via ElevenLabs
7. `assemble_video.py` - FFmpeg video assembly

### Architecture Pattern

**Smart Agent + Dumb Scripts**

```
AI Agents (Intelligent Orchestration)
  ↓ Read files, extract data, combine prompts
Python Scripts (Simple Execution)
  ↓ Call external APIs, generate content
Output Files (Intermediate Results)
  ↓ Assembly and concatenation
Final Video (MP4, 90 seconds)
```

---

## Production Pipeline Overview

### 8-Step Workflow

| Step | Name | Type | Duration | Output |
|------|------|------|----------|--------|
| **SOP 01** | Species Research | Manual | ~5 min | `01_research.md` |
| **SOP 02** | Story Development | Manual | ~10 min | `02_story_script.md` |
| **SOP 03** | Asset Generation | Automated | ~5-10 min | `assets/` (22 images) |
| **SOP 03.5** | Composite Creation | Automated | ~1-2 min | `assets/composites/` (18 images) |
| **SOP 04** | Video Prompt Engineering | Manual | ~10 min | `04_video_prompts.md` |
| **SOP 05** | Video Generation | Automated | ~60-90 min | `videos/` (18 MP4s) |
| **SOP 06** | Audio Generation | Automated | ~1-2 min | `audio/` (18 MP3s) |
| **SOP 07** | Sound Effects | Automated | ~2-3 min | `sfx/` (18 WAVs) |
| **SOP 08** | Final Assembly | Automated | ~2-3 min | `{project}_final.mp4` |

**Total Time:** ~90-120 minutes (mostly automated)

---

## Key Features

### 1. Complete Automation

- **Automated Steps:** 6 out of 8 steps fully automated
- **Agent Orchestration:** Claude Code manages workflows
- **Error Handling:** Automatic retry and error reporting
- **Progress Tracking:** Real-time status updates

### 2. Modular Design

- **Independent Scripts:** Each tool works standalone
- **Reusable Components:** Scripts can be called from any orchestrator
- **Clear Interfaces:** Standard CLI argument patterns
- **Easy Testing:** Test scripts in isolation

### 3. Quality Output

- **Resolution:** 1920x1080 (16:9 YouTube-ready)
- **Video Codec:** H.264 (universal compatibility)
- **Audio Codec:** AAC (high quality)
- **Duration:** 90 seconds (18 × 5s clips)

### 4. Cost-Effective

- **Total Cost:** ~$6-13 per documentary
- **No Subscriptions:** Pay-per-use API pricing
- **Free Tools:** FFmpeg, catbox.moe hosting
- **Efficient Processing:** Minimal API calls

### 5. Extensible Architecture

- **Add New Scripts:** Drop in new tools easily
- **Support New Services:** Add API wrappers
- **Customize Pipelines:** Modify workflows
- **Adapt for Other Uses:** Generic templates available

---

## Example Projects

### Completed Examples

The repository includes 4 complete example projects in various stages:

1. **bulbasaur/** - "First Light" documentary (most complete)
2. **charizard/** - Evolution and dominance story
3. **haunter/** - Ghost-type horror documentary
4. **pikachu/** - "First Spark" colony defense story

Each example demonstrates the full workflow from planning to final video.

---

## Getting Started

### Prerequisites

1. **Install Python 3.10+**
2. **Install uv:** `curl -LsSf https://astral.sh/uv/install.sh | sh`
3. **Install FFmpeg:** `brew install ffmpeg` (macOS)
4. **Get API Keys:** Gemini, KIE.ai, ElevenLabs

### Quick Start

```bash
# 1. Install dependencies
uv sync

# 2. Configure API keys
cp scripts/.env.example scripts/.env
# Edit scripts/.env with your keys

# 3. Test a script
python scripts/generate_asset.py \
  --prompt "A test image" \
  --output "test.png"
```

### Documentation

- **Main README:** `README.md` - Project overview and pipeline guide
- **Claude Guide:** `CLAUDE.md` - Claude Code integration (important!)
- **Architecture:** `docs/architecture.md` - Complete technical architecture
- **Development:** `docs/development-guide.md` - Setup and usage guide
- **Source Tree:** `docs/source-tree-analysis.md` - Directory structure

---

## Project Statistics

### Codebase Metrics

- **Primary Language:** Python (100%)
- **CLI Scripts:** 7 entry points
- **Total Scripts LOC:** ~1,500 lines
- **Agent Orchestration Files:** 5 workflows
- **Example Projects:** 4 complete workspaces

### Output Characteristics

- **Images Per Project:** ~22-25 (characters, environments, props)
- **Composites Per Project:** 18 (1920x1080 16:9)
- **Videos Per Project:** 18 (10-second clips)
- **Audio Clips:** 18 (6-8 seconds)
- **Sound Effects:** 18 (5-10 seconds)
- **Final Video:** 1 (90 seconds, 1080p)

### Typical Project Size

- **Assets:** ~100 MB (images)
- **Videos:** ~500 MB (18 × 10s clips)
- **Audio:** ~5 MB
- **Final Output:** ~50 MB (90s compressed video)
- **Total:** ~650 MB per project

---

## Links to Detailed Documentation

| Document | Purpose | Location |
|----------|---------|----------|
| **Architecture** | Complete technical architecture | `docs/architecture.md` |
| **Technology Stack** | Detailed tech stack breakdown | `docs/technology-stack.md` |
| **Architecture Patterns** | Pattern explanations and benefits | `docs/architecture-patterns.md` |
| **Comprehensive Analysis** | Exhaustive CLI tool analysis | `docs/comprehensive-analysis-main.md` |
| **Source Tree** | Annotated directory structure | `docs/source-tree-analysis.md` |
| **Development Guide** | Setup and development instructions | `docs/development-guide.md` |
| **Project Structure** | Project classification details | `docs/project-structure.md` |
| **Existing Docs** | Inventory of pre-existing documentation | `docs/existing-documentation-inventory.md` |

---

## Getting Started Checklist

- [ ] Read `README.md` for pipeline overview
- [ ] Review `CLAUDE.md` for Claude Code integration
- [ ] Install prerequisites (Python, uv, FFmpeg)
- [ ] Run `uv sync` to install dependencies
- [ ] Configure `scripts/.env` with API keys
- [ ] Test `generate_asset.py` with sample prompt
- [ ] Explore example projects (bulbasaur/, pikachu/)
- [ ] Review `docs/architecture.md` for deep dive
- [ ] Start your first project!

---

## Support and Community

### Getting Help

- **Documentation:** Start with `README.md` and `CLAUDE.md`
- **Examples:** Review complete projects in `bulbasaur/`, `pikachu/`
- **Troubleshooting:** Check `docs/development-guide.md`

### Contributing

Currently a personal project. Feel free to:
- Use for your own projects
- Report issues or suggestions
- Share your creations

---

## Project Health

**Status:** ✅ Production-Ready

**Strengths:**
- ✅ Clear architecture and documentation
- ✅ Working automated pipeline
- ✅ Multiple complete examples
- ✅ Cost-effective ($6-13 per video)
- ✅ Fast generation (90-120 min)

**Areas for Improvement:**
- ⚠️ No automated tests
- ⚠️ One hardcoded script (split-screen)
- ⚠️ No CI/CD pipeline
- ⚠️ Limited error recovery in scripts

**Overall Assessment:** Well-designed CLI toolkit with solid foundation and clear documentation. Ready for production use with opportunities for enhancement.

---

## License

Not specified in repository. Contact project owner for licensing information.

---

## Last Updated

**Documentation Generated:** 2026-01-06
**Project Version:** 0.1.0
**Documentation Workflow:** bmad:bmm:workflows:document-project v1.2.0
