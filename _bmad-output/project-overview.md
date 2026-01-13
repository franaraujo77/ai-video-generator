# Project Overview

## Pokémon Natural Geographic

**Purpose:** An automated production pipeline for creating hyper-realistic Pokémon nature documentaries, styled after *Planet Earth*.

## Key Characteristics
- **Type:** Monolith (CLI/Pipeline)
- **Primary Language:** Python
- **Core Philosophy:** "Smart Agent + Dumb Scripts"
- **Output:** MP4 Video Files (1920x1080)

## Repository Structure
The project is organized as a single repository containing:
1.  **Tooling:** `scripts/` contains the logic for generating assets and videos.
2.  **Instructions:** `prompts/` contains the "software" for the AI agents driving the process.
3.  **Workspaces:** Directories like `pikachu/` or `charizard/` serve as self-contained project files for each video.

## Status
- **Active Development:** The pipeline is functional with scripts for all major stages (Asset, Video, Audio, Assembly).
- **Documentation:** Well-documented via `GEMINI.md` and individual script usage guides.
