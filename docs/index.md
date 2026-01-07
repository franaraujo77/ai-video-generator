# Project Documentation Index

**Project:** ai-video-generator
**Type:** CLI Automation Toolkit (Monolith)
**Primary Language:** Python 3.10+
**Architecture:** Pipeline-Based with AI Agent Orchestration

**Documentation Generated:** 2026-01-06
**Workflow Version:** 1.2.0 (exhaustive scan)

---

## Project Overview

- **Name:** ai-video-generator
- **Description:** Generic video generation automation
- **Repository Type:** Monolith (single cohesive codebase)
- **Parts Count:** 1
- **Primary Technology:** Python 3.10+ with AI service integrations

---

## Quick Reference

### Tech Stack Summary

| Category | Technology | Version |
|----------|-----------|---------|
| **Language** | Python | 3.10+ (3.14.2 installed) |
| **Package Manager** | uv | Latest |
| **Video Processing** | FFmpeg | 8.0.1 |
| **AI Services** | Gemini, Kling, ElevenLabs | Various |

### Entry Points

**All CLI scripts in `scripts/`:**

1. `generate_asset.py` - Image generation (Gemini)
2. `create_composite.py` - 16:9 compositing
3. `create_split_screen.py` - Split-screen compositor
4. `generate_video.py` - Video animation (Kling)
5. `generate_audio.py` - Narration (ElevenLabs)
6. `generate_sound_effects.py` - SFX (ElevenLabs)
7. `assemble_video.py` - FFmpeg assembly

### Architecture Pattern

**Smart Agent + Dumb Scripts**
- Agents: Read files, orchestrate workflows, handle errors
- Scripts: Single-purpose CLI tools, stateless execution
- State: Filesystem-based (no databases)

---

## Generated Documentation

### Core Documentation

- [Project Overview](./project-overview.md) - Executive summary and quick start
- [Architecture](./architecture.md) - Complete technical architecture
- [Technology Stack](./technology-stack.md) - Detailed tech stack breakdown
- [Architecture Patterns](./architecture-patterns.md) - Design patterns and philosophy

### Component Documentation

- [Comprehensive Analysis](./comprehensive-analysis-main.md) - Exhaustive CLI tool analysis (7 scripts)
- [Source Tree Analysis](./source-tree-analysis.md) - Annotated directory structure
- [Development Guide](./development-guide.md) - Setup, build, and development instructions

### Meta Documentation

- [Project Structure](./project-structure.md) - Classification and organization
- [Project Parts Metadata](./project-parts-metadata.json) - Machine-readable project info
- [Existing Documentation Inventory](./existing-documentation-inventory.md) - Pre-existing docs catalog
- [User-Provided Context](./user-provided-context.md) - Additional focus areas (none specified)

---

## Existing Documentation

### Root-Level Documentation

- [README.md](../README.md) - Main project documentation (8-step pipeline guide)
- [README_GENERIC.md](../README_GENERIC.md) - Generic workflow documentation
- [CLAUDE.md](../CLAUDE.md) - **Claude Code integration guide** ⭐ IMPORTANT
- [GEMINI.md](../GEMINI.md) - Gemini-specific documentation

### Component Documentation

- [scripts/README.md](../scripts/README.md) - Technical documentation for CLI tools

---

## Getting Started

### For New Developers

1. **Read First:**
   - [README.md](../README.md) - Understand the 8-step pipeline
   - [CLAUDE.md](../CLAUDE.md) - Learn Claude Code integration
   - [Project Overview](./project-overview.md) - Get executive summary

2. **Setup Environment:**
   - Follow [Development Guide](./development-guide.md)
   - Install Python 3.10+, uv, FFmpeg
   - Configure API keys in `scripts/.env`

3. **Understand Architecture:**
   - Review [Architecture](./architecture.md)
   - Read [Architecture Patterns](./architecture-patterns.md)
   - Study [Comprehensive Analysis](./comprehensive-analysis-main.md)

4. **Explore Codebase:**
   - Navigate with [Source Tree Analysis](./source-tree-analysis.md)
   - Test individual scripts from `scripts/`
   - Review example projects (bulbasaur/, pikachu/)

### For AI Assistants (Claude, Gemini, etc.)

**Primary References:**
1. [CLAUDE.md](../CLAUDE.md) - Critical guidelines for Claude Code instances
2. [Architecture](./architecture.md) - Complete system design
3. [Comprehensive Analysis](./comprehensive-analysis-main.md) - Detailed CLI tool interfaces

**Key Patterns:**
- **Smart Agent + Dumb Scripts** - Agents orchestrate, scripts execute
- **Complete Inputs** - Scripts receive fully-formed arguments
- **Filesystem as State** - File existence = completion
- **Single Responsibility** - Each script does one thing

### For Content Creators

1. **Quick Start:** Follow [README.md](../README.md) → Quick Start section
2. **Run Pipeline:** Use agent prompts in `prompts/` directory
3. **Examples:** Study complete projects in `bulbasaur/`, `pikachu/`
4. **Troubleshooting:** Check [Development Guide](./development-guide.md) → Troubleshooting

---

## Documentation Map

### By Purpose

**Understanding the Project:**
- [Project Overview](./project-overview.md) - What, why, who
- [Architecture](./architecture.md) - How it works
- [Architecture Patterns](./architecture-patterns.md) - Design philosophy

**Setting Up:**
- [Development Guide](./development-guide.md) - Prerequisites, installation, configuration
- [README.md](../README.md) - Quick start guide

**Working with Code:**
- [Comprehensive Analysis](./comprehensive-analysis-main.md) - All 7 CLI tools documented
- [Source Tree Analysis](./source-tree-analysis.md) - Directory structure
- [Technology Stack](./technology-stack.md) - Dependencies and services

**Navigating:**
- [CLAUDE.md](../CLAUDE.md) - Claude Code workflows
- This file (`index.md`) - Documentation hub

### By Audience

**Developers:**
- [Development Guide](./development-guide.md)
- [Comprehensive Analysis](./comprehensive-analysis-main.md)
- [Source Tree Analysis](./source-tree-analysis.md)

**Architects:**
- [Architecture](./architecture.md)
- [Architecture Patterns](./architecture-patterns.md)
- [Technology Stack](./technology-stack.md)

**Content Creators:**
- [README.md](../README.md)
- [Project Overview](./project-overview.md)
- Example projects (bulbasaur/, pikachu/, etc.)

**AI Assistants:**
- [CLAUDE.md](../CLAUDE.md)
- [Architecture](./architecture.md)
- [Comprehensive Analysis](./comprehensive-analysis-main.md)

---

## Project Statistics

### Codebase Metrics

- **Primary Language:** Python 100%
- **CLI Scripts:** 7 entry points
- **Agent Workflows:** 5 automation files
- **Example Projects:** 4 (bulbasaur, charizard, haunter, pikachu)
- **Documentation Files:** 12 generated + 5 existing

### Output Characteristics

- **Images Per Project:** 22-25 assets
- **Video Clips:** 18 (10 seconds each)
- **Audio Clips:** 18 (6-8 seconds each)
- **Sound Effects:** 18 (5-10 seconds each)
- **Final Video:** 90 seconds, 1080p, 16:9

### Performance

- **Total Pipeline Time:** ~90-120 minutes
- **Cost Per Video:** ~$6-13
- **Automation Level:** 75% (6/8 steps)

---

## Key Concepts

### Smart Agent + Dumb Scripts

The core architectural pattern:
- **Agents (Smart):** Read files, extract data, combine prompts, orchestrate
- **Scripts (Dumb):** Accept inputs, call APIs, return results
- **Benefits:** Testable, maintainable, portable, extensible

### Filesystem as State

No databases, no caches:
- **Planning Docs:** Markdown files in `{project}/`
- **Intermediate Outputs:** Images, videos, audio
- **Final Output:** Assembled MP4
- **Progress Tracking:** File existence

### Pipeline-Based Processing

8 sequential steps:
1. Research (manual)
2. Story (manual)
3. Assets (automated)
4. Composites (automated)
5. Video prompts (manual)
6. Videos (automated)
7. Audio/SFX (automated)
8. Assembly (automated)

---

## Common Tasks

### Finding Information

**"How do I set up the project?"**
→ [Development Guide](./development-guide.md)

**"What's the architecture?"**
→ [Architecture](./architecture.md) or [Architecture Patterns](./architecture-patterns.md)

**"How do the scripts work?"**
→ [Comprehensive Analysis](./comprehensive-analysis-main.md)

**"Where are the files?"**
→ [Source Tree Analysis](./source-tree-analysis.md)

**"What technologies are used?"**
→ [Technology Stack](./technology-stack.md)

**"How does Claude Code integration work?"**
→ [CLAUDE.md](../CLAUDE.md)

### Running the Pipeline

**Quick Start:**
```bash
# 1. Setup (one-time)
uv sync
cp scripts/.env.example scripts/.env
# Edit scripts/.env with API keys

# 2. Generate assets (automated)
# Open prompts/3.5_generate_assets_agent.md in Claude Code
# Tell Claude: "Generate assets for myproject"

# 3. Generate videos (automated)
# Open prompts/4.5_generate_videos_agent.md in Claude Code
# Tell Claude: "Generate videos for myproject"

# 4. Generate audio (automated)
# Open prompts/5.5_generate_audio_agent.md in Claude Code
# Tell Claude: "Generate audio for myproject"

# 5. Assemble final video (automated)
# Open prompts/7_assemble_final_agent.md in Claude Code
# Tell Claude: "Assemble final video for myproject"
```

---

## Support

### Troubleshooting

See [Development Guide - Troubleshooting](./development-guide.md#troubleshooting) for common issues:
- API key errors
- FFmpeg not found
- Module import errors
- Permission issues

### Getting Help

1. Check documentation (start with this index)
2. Review example projects
3. Read error messages carefully
4. Consult [CLAUDE.md](../CLAUDE.md) for Claude-specific guidance

---

## Next Steps

**After reading this index:**

1. **New to the project?**
   - Read [README.md](../README.md) for pipeline overview
   - Review [Project Overview](./project-overview.md) for executive summary
   - Study an example (e.g., `bulbasaur/`)

2. **Ready to develop?**
   - Follow [Development Guide](./development-guide.md)
   - Test individual scripts
   - Generate your first video

3. **Understanding architecture?**
   - Read [Architecture](./architecture.md) for complete design
   - Study [Architecture Patterns](./architecture-patterns.md) for philosophy
   - Review [Comprehensive Analysis](./comprehensive-analysis-main.md) for details

4. **Using Claude Code?**
   - **Start with [CLAUDE.md](../CLAUDE.md)** - Essential reading!
   - Use agent prompts in `prompts/` directory
   - Follow "Smart Agent + Dumb Scripts" pattern

---

## Documentation Maintenance

**Last Updated:** 2026-01-06
**Generated By:** bmad:bmm:workflows:document-project v1.2.0
**Scan Level:** Exhaustive (complete source code analysis)

**To regenerate this documentation:**
```bash
# Use the document-project workflow
# (if BMAD framework is installed)
```

---

**Welcome to ai-video-generator!** Start your journey with [README.md](../README.md) or [Project Overview](./project-overview.md).
