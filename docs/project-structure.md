# Project Structure

## Overview

**Project Name:** ai-video-generator
**Description:** Generic video generation automation
**Repository Type:** Monolith
**Primary Language:** Python 3.10+

## Classification

- **Project Type:** CLI (Command-Line Interface / Automation Toolkit)
- **Architecture Pattern:** Pipeline-based automation with AI service orchestration
- **Package Manager:** uv (Python)
- **Dependencies:** Google Generative AI, ElevenLabs, Pillow, FFmpeg

## Directory Structure

```
ai-video-generator/
├── scripts/              # Python CLI automation tools
├── prompts/             # Agent orchestration instructions
├── generic_prompts/     # Reusable workflow templates
├── bulbasaur/          # Example: Bulbasaur documentary workspace
├── charizard/          # Example: Charizard documentary workspace
├── haunter/            # Example: Haunter documentary workspace
├── pikachu/            # Example: Pikachu documentary workspace
├── pyproject.toml      # Python project configuration
└── README.md           # Project documentation
```

## Project Parts

This is a **single-part monolith** project with one cohesive codebase.

| Part ID | Type | Root Path | Description |
|---------|------|-----------|-------------|
| main | CLI | /Users/francisaraujo/repos/ai-video-generator | Generic video generation automation pipeline |
