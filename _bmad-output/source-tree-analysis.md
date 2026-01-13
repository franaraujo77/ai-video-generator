# Source Tree Analysis

## Project Structure

```
.
├── scripts/                # Atomic Python scripts for pipeline tasks
│   ├── generate_asset.py   # Image generation (Gemini)
│   ├── generate_video.py   # Video generation (Kling)
│   ├── assemble_video.py   # FFmpeg assembly
│   └── ...
├── prompts/                # Markdown instructions for AI agents
│   ├── 1_research.md       # SOP 01
│   ├── 2_story_generator.md # SOP 02
│   └── ...
├── {pokemon}/              # Workspace folders (e.g., pikachu/, bulbasaur/)
│   ├── 01_research.md      # Generated research
│   ├── assets/             # Generated images/composites
│   ├── audio/              # Generated voice/sfx
│   └── final/              # Final video output
├── GEMINI.md               # Project Context & Architecture
├── pyproject.toml          # Python dependencies
└── README.md               # Project documentation
```

## Critical Directories

| Directory | Purpose |
| :--- | :--- |
| **`scripts/`** | **The Execution Engine.** Contains stateless, atomic Python scripts. Each script performs a single task (e.g., generate an image, create a composite, synthesize audio). They are designed to be invoked by agents or humans via CLI. |
| **`prompts/`** | **The Logic Layer.** Contains Markdown files defining Standard Operating Procedures (SOPs) for AI agents. These prompts drive the workflow, instructing agents on how to use the scripts and manage state. |
| **`{pokemon}/`** | **The Data Layer / Workspace.** Dynamic directories created for each subject (e.g., `pikachu/`, `haunter/`). These act as the source of truth, storing all intermediate artifacts (research docs, script drafts) and final media (images, audio, video). |
| **`_bmad/`** | **Agent System.** Contains the configuration for the BMad agentic framework managing this project. |

## Entry Points

- **Manual/Agent:** The workflow starts by creating a workspace folder (e.g., `mkdir charizard`) and invoking the agent with `prompts/1_research.md`.
- **Scripts:** Individual steps are executed via `python scripts/<script_name>.py`.
