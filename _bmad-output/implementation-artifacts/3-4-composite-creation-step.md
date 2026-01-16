---
story_key: '3-4-composite-creation-step'
epic_id: '3'
story_id: '4'
title: 'Composite Creation Step'
status: 'done'
priority: 'critical'
story_points: 3
created_at: '2026-01-15'
completed_at: '2026-01-15'
code_review_date: '2026-01-15'
code_review_status: 'approved_with_fixes'
assigned_to: 'Claude Sonnet 4.5'
dependencies: ['3-1-cli-script-wrapper-async-execution', '3-2-filesystem-organization-path-helpers', '3-3-asset-generation-step-gemini']
blocks: ['3-5-video-clip-generation-step-kling']
ready_for_dev: false
---

# Story 3.4: Composite Creation Step ✅

**Epic:** 3 - Video Generation Pipeline
**Priority:** Critical
**Story Points:** 3
**Status:** COMPLETED (2026-01-15)
**Code Review:** APPROVED WITH FIXES (2026-01-15)

## Story Description

**As a** worker process orchestrating video generation,
**I want to** combine character and environment assets into properly formatted 1920x1080 (16:9) composite images,
**So that** the video generation step has YouTube-ready seed images for Kling 2.5 animation.

## Context & Background

The composite creation step is the **second stage of the 8-step video generation pipeline**. It takes the 22 photorealistic assets generated in Story 3.3 and creates 18 scene-specific composite images that will be animated by Kling 2.5 in Story 3.5.

**Critical Requirements:**

1. **16:9 Aspect Ratio Enforcement**: ALL composites MUST be exactly 1920x1080 pixels for YouTube compatibility and Kling API requirements
2. **Brownfield Integration**: Use existing `create_composite.py` and `create_split_screen.py` CLI scripts via async wrapper (Story 3.1)
3. **Scene Mapping**: Generate 18 composites (one per video clip in the final 90-second documentary)
4. **Character + Environment Composition**: Overlay transparent PNG characters on environment backgrounds with proper scaling and centering
5. **Filesystem Organization**: Store composites using path helpers from Story 3.2 in channel-isolated directories (`assets/composites/`)
6. **Idempotency**: Re-running overwrites existing composites (FR50)
7. **Error Handling**: Support partial resume (regenerate only failed composites)

**Why 1920x1080 (16:9) is Critical:**
- YouTube standard format (prevents letterboxing or pillarboxing)
- Kling 2.5 API requires consistent aspect ratio for video generation
- Raw environment images may be ultra-wide (2.36:1 cinematic), characters have transparent backgrounds
- `create_composite.py` handles scaling, cropping, and centering to enforce exact 1920x1080 output

**Scene Composition Patterns:**
- **Standard Composite** (clips 1-14, 16-18): Single character + single environment = 1 composite
- **Split-Screen Composite** (clip 15): Two character+environment pairs side-by-side = 1 composite (960x1080 each half)

**Referenced Architecture:**
- Architecture: CLI Script Invocation Pattern (Short Transaction, Async Wrapper)
- project-context.md: CLI Scripts Architecture (lines 59-116)
- project-context.md: Integration Utilities (lines 117-278)
- PRD: FR19 (16:9 Composite Creation)
- PRD: FR50 (Asset Generation Idempotency applies to composites too)

**Key Architectural Pattern ("Smart Agent + Dumb Scripts"):**
- **Orchestrator (Smart)**: Reads scene definitions, maps assets to scenes, determines composite type (standard vs split-screen), manages retry logic
- **Script (Dumb)**: Receives paths to character+environment PNGs, creates composite, saves 1920x1080 PNG, returns success/failure

**Existing CLI Scripts Analysis:**

```bash
# Standard Composite Interface (DO NOT MODIFY):
python scripts/create_composite.py \
  --character "/path/to/assets/characters/bulbasaur.png" \
  --environment "/path/to/assets/environments/forest.png" \
  --output "/path/to/assets/composites/clip_01.png" \
  --character-scale 1.0  # Optional scaling factor (1.0 = 100%)

# Split-Screen Composite Interface (hardcoded for specific project):
# NOTE: create_split_screen.py is hardcoded for haunter project
# Need generic version or inline composition logic for split-screen scenes

# Exit codes:
# 0 = Success
# 1 = Failure (missing files, PIL error, filesystem error, etc.)
```

**Derived from Previous Story (3.3) Analysis:**
- Story 3.3 generated 22 assets:
  - 6-8 characters (e.g., bulbasaur_resting.png, bulbasaur_walking.png)
  - 8-10 environments (e.g., forest_clearing.png, forest_stream.png)
  - 4-6 props (e.g., mushroom_cluster.png) [NOT used in composites - reserved for future enhancements]
- Assets are stored in: `/app/workspace/channels/{channel_id}/projects/{project_id}/assets/{type}/`
- Story 3.3 used short transaction pattern successfully (verified in commit d5f9344)

## Acceptance Criteria

### Scenario 1: Standard Composite Creation (18 scenes from character + environment pairs)
**Given** a task has completed asset generation with 22 assets in `assets/` subdirectories
**When** the composite creation worker processes the task
**Then** the worker should:
- ✅ Parse scene definitions to identify which character and environment to use for each of 18 clips
- ✅ For clips 1-14, 16-18 (standard composites):
  - Call `scripts/create_composite.py` with character path, environment path, output path
  - Verify output is exactly 1920x1080 pixels
  - Save composite to `assets/composites/clip_01.png` through `assets/composites/clip_18.png`
- ✅ Update task status to "Composites Ready" after all 18 composites generated
- ✅ Update Notion status to "Composites Ready" within 5 seconds

### Scenario 2: Split-Screen Composite Handling (clip 15)
**Given** scene definition indicates clip 15 requires split-screen (two parallel scenes)
**When** the composite creation step processes clip 15
**Then** the worker should:
- ✅ Detect split-screen requirement from scene metadata
- ✅ Use generic split-screen composition logic (NOT hardcoded haunter script):
  - Left half (960x1080): Character A + Environment A
  - Right half (960x1080): Character B + Environment B
  - Final composite: 1920x1080 with both halves side-by-side
- ✅ Save as `assets/composites/clip_15_split.png`
- ✅ Verify final dimensions are exactly 1920x1080

### Scenario 3: Partial Resume After Failure
**Given** composite creation fails after generating 10 of 18 composites
**When** the task is retried
**Then** the worker should:
- ✅ Detect existing composites by checking filesystem paths
- ✅ Skip regeneration of completed composites (10 already exist)
- ✅ Resume from composite #11 and generate remaining 8 composites
- ✅ Complete successfully without duplicate work

### Scenario 4: Idempotent Regeneration
**Given** all 18 composites exist from previous run
**When** composite creation is triggered again (FR50: idempotency)
**Then** the worker should:
- ✅ Regenerate all 18 composites (overwrite existing files)
- ✅ NOT create duplicate files with different names
- ✅ Maintain same file paths and filenames

### Scenario 5: Error Handling with Detailed Logging
**Given** `create_composite.py` fails for clip #7 (missing character file)
**When** the error is caught
**Then** the worker should:
- ✅ Raise `CLIScriptError` with stderr containing file not found details
- ✅ Log error with correlation ID, clip number, character path, environment path, exit code
- ✅ Mark task with "Composite Error" status (granular error state)
- ✅ Record failed composite details in Error Log for manual inspection
- ✅ Allow retry from clip #7 (don't restart from #1)

### Scenario 6: Multi-Channel Isolation
**Given** two channels ("poke1", "poke2") generating composites simultaneously for project "vid_123"
**When** both workers run composite creation
**Then** the composites should be:
- ✅ Stored in isolated directories:
  - Channel 1: `/app/workspace/channels/poke1/projects/vid_123/assets/composites/`
  - Channel 2: `/app/workspace/channels/poke2/projects/vid_123/assets/composites/`
- ✅ No cross-channel interference (completely independent)
- ✅ Parallel execution without conflicts (workers don't block each other)

## Technical Specifications

### File Structure
```
app/
├── services/
│   └── composite_creation.py    # New file - Composite creation service
├── workers/
│   └── composite_worker.py      # New file - Composite creation worker
└── utils/
    ├── cli_wrapper.py           # Existing (Story 3.1)
    ├── filesystem.py            # Existing (Story 3.2)
    └── logging.py               # Existing (Story 3.1)
```

### Core Implementation: `app/services/composite_creation.py`

**Purpose:** Encapsulates composite creation business logic separate from worker orchestration.

**Required Classes:**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

@dataclass
class SceneComposite:
    """
    Represents a single composite to generate for one video clip.

    Attributes:
        clip_number: Clip number (1-18)
        character_path: Path to character PNG (transparent background)
        environment_path: Path to environment PNG (background image)
        output_path: Path where composite PNG will be saved
        is_split_screen: True if this is a split-screen composite (clip 15)
        character_b_path: Optional second character for split-screen
        environment_b_path: Optional second environment for split-screen
        character_scale: Scaling factor for character (1.0 = 100%)
    """
    clip_number: int
    character_path: Path
    environment_path: Path
    output_path: Path
    is_split_screen: bool = False
    character_b_path: Optional[Path] = None
    environment_b_path: Optional[Path] = None
    character_scale: float = 1.0


@dataclass
class CompositeManifest:
    """
    Complete manifest of composites to generate for a project (18 total).

    Attributes:
        composites: List of SceneComposite objects (one per video clip)
    """
    composites: List[SceneComposite]


class CompositeCreationService:
    """
    Service for creating 1920x1080 composite images from character + environment assets.

    Responsibilities:
    - Map scene definitions to asset paths (character + environment)
    - Create 18 composite images (one per video clip)
    - Handle both standard composites (1 char + 1 env) and split-screen (2 char + 2 env)
    - Orchestrate CLI script invocation for each composite
    - Track completed vs. pending composites for partial resume
    """

    def __init__(self, channel_id: str, project_id: str):
        """
        Initialize composite creation service for specific project.

        Args:
            channel_id: Channel identifier for path isolation
            project_id: Project/task identifier (UUID from database)
        """
        self.channel_id = channel_id
        self.project_id = project_id
        self.log = get_logger(__name__)

    def create_composite_manifest(
        self,
        topic: str,
        story_direction: str
    ) -> CompositeManifest:
        """
        Create composite manifest by mapping 18 scenes to character+environment assets.

        Scene Derivation Strategy:
        1. Parse story_direction to understand narrative structure (18 clips)
        2. Scan available character assets in `assets/characters/`
        3. Scan available environment assets in `assets/environments/`
        4. Map each clip to appropriate character and environment based on:
           - Clip sequence (intro → action → conclusion)
           - Asset filenames (infer usage from naming conventions)
           - Default pairing strategy (cycle through characters/environments)

        Args:
            topic: Video topic from Notion (for context)
            story_direction: Story direction from Notion (narrative guidance)

        Returns:
            CompositeManifest with 18 SceneComposite objects

        Example:
            >>> manifest = service.create_composite_manifest(
            ...     "Bulbasaur forest documentary",
            ...     "Show evolution through seasons: spring growth, summer activity, autumn rest"
            ... )
            >>> print(len(manifest.composites))
            18
            >>> print(manifest.composites[0].clip_number)
            1
            >>> print(manifest.composites[0].character_path.name)
            "bulbasaur_resting.png"
        """

    async def generate_composites(
        self,
        manifest: CompositeManifest,
        resume: bool = False
    ) -> Dict[str, any]:
        """
        Generate all composites in manifest by invoking CLI scripts.

        Orchestration Flow:
        1. For each composite in manifest:
           a. Check if composite exists (if resume=True, skip existing)
           b. Determine composite type (standard vs split-screen)
           c. Invoke appropriate CLI script:
              - Standard: `create_composite.py --character X --environment Y --output Z`
              - Split-screen: Inline PIL composition (generic, not haunter-specific)
           d. Wait for completion (timeout: 30 seconds per composite)
           e. Verify PNG file exists and is 1920x1080
           f. Log success/failure with correlation ID
        2. Return summary (generated count, skipped count, failed count)

        Args:
            manifest: CompositeManifest with 18 scene definitions
            resume: If True, skip composites that already exist on filesystem

        Returns:
            Summary dict with keys:
                - generated: Number of newly generated composites
                - skipped: Number of existing composites (if resume=True)
                - failed: Number of failed composites

        Raises:
            CLIScriptError: If any composite generation fails

        Example:
            >>> result = await service.generate_composites(manifest, resume=False)
            >>> print(result)
            {"generated": 18, "skipped": 0, "failed": 0}
        """

    def check_composite_exists(self, composite_path: Path) -> bool:
        """
        Check if composite file exists on filesystem.

        Used for partial resume (Story 3.4 AC3).

        Args:
            composite_path: Full path to composite PNG file

        Returns:
            True if file exists and is readable, False otherwise
        """
        return composite_path.exists() and composite_path.is_file()

    async def create_split_screen_composite(
        self,
        char_a_path: Path,
        env_a_path: Path,
        char_b_path: Path,
        env_b_path: Path,
        output_path: Path
    ) -> None:
        """
        Create split-screen composite inline using PIL (generic, not haunter-specific).

        Composition Strategy:
        1. Load all 4 images (2 characters, 2 environments)
        2. Resize each environment to 960x1080 (half of 1920x1080)
        3. Overlay character A on environment A (left half)
        4. Overlay character B on environment B (right half)
        5. Combine both halves side-by-side on 1920x1080 canvas
        6. Save as PNG

        Args:
            char_a_path: Path to left character PNG
            env_a_path: Path to left environment PNG
            char_b_path: Path to right character PNG
            env_b_path: Path to right environment PNG
            output_path: Path to save split-screen composite PNG

        Raises:
            Exception: If PIL operations fail or dimensions are incorrect

        Note:
            This is a generic implementation that works for ANY project,
            unlike the hardcoded `scripts/create_split_screen.py` which
            only works for the haunter project.
        """
```

### Core Implementation: `app/workers/composite_worker.py`

**Purpose:** Worker process that claims tasks and orchestrates composite creation.

**Required Functions:**

```python
import asyncio
from app.database import AsyncSessionLocal
from app.models import Task
from app.services.composite_creation import CompositeCreationService
from app.utils.logging import get_logger

log = get_logger(__name__)


async def process_composite_creation_task(task_id: str):
    """
    Process composite creation for a single task.

    Transaction Pattern (CRITICAL - from Architecture Decision 3):
    1. Claim task (short transaction, set status="processing")
    2. Close database connection
    3. Generate composites (long-running, outside transaction)
    4. Reopen database connection
    5. Update task (short transaction, set status="composites_ready" or "error")

    Args:
        task_id: Task UUID from database

    Flow:
        1. Load task from database (get channel_id, project_id, topic, story_direction)
        2. Initialize CompositeCreationService(channel_id, project_id)
        3. Create composite manifest (18 scenes)
        4. Generate 18 composites with CLI script invocations
        5. Update task status to "Composites Ready"
        6. Update Notion status (async, don't block)

    Error Handling:
        - CLIScriptError → Mark task "Composite Error", log details, allow retry
        - asyncio.TimeoutError → Mark task "Composite Error", log timeout
        - Exception → Mark task "Composite Error", log unexpected error

    Raises:
        No exceptions (catches all and logs errors)
    """
    # Step 1: Claim task (short transaction)
    async with AsyncSessionLocal() as db:
        async with db.begin():
            task = await db.get(Task, task_id)
            if not task:
                log.error("task_not_found", task_id=task_id)
                return

            task.status = "processing"
            await db.commit()
            log.info("task_claimed", task_id=task_id, status="processing")

    # Step 2: Generate composites (OUTSIDE transaction)
    try:
        service = CompositeCreationService(task.channel_id, task.project_id)
        manifest = service.create_composite_manifest(task.topic, task.story_direction)

        log.info(
            "composite_creation_start",
            task_id=task_id,
            composite_count=len(manifest.composites)
        )

        result = await service.generate_composites(manifest, resume=False)

        log.info(
            "composite_creation_complete",
            task_id=task_id,
            generated=result["generated"],
            skipped=result["skipped"],
            failed=result["failed"]
        )

        # Step 3: Update task (short transaction)
        async with AsyncSessionLocal() as db:
            async with db.begin():
                task = await db.get(Task, task_id)
                task.status = "composites_ready"
                await db.commit()
                log.info("task_updated", task_id=task_id, status="composites_ready")

        # Step 4: Update Notion (async, non-blocking)
        asyncio.create_task(update_notion_status(task.notion_page_id, "Composites Ready"))

    except CLIScriptError as e:
        log.error(
            "composite_creation_cli_error",
            task_id=task_id,
            script=e.script,
            exit_code=e.exit_code,
            stderr=e.stderr[:500]  # Truncate stderr
        )

        async with AsyncSessionLocal() as db:
            async with db.begin():
                task = await db.get(Task, task_id)
                task.status = "composite_error"
                task.error_log = f"Composite creation failed: {e.stderr}"
                await db.commit()

    except asyncio.TimeoutError:
        log.error("composite_creation_timeout", task_id=task_id, timeout=30)

        async with AsyncSessionLocal() as db:
            async with db.begin():
                task = await db.get(Task, task_id)
                task.status = "composite_error"
                task.error_log = "Composite creation timeout (30s per composite)"
                await db.commit()

    except Exception as e:
        log.error("composite_creation_unexpected_error", task_id=task_id, error=str(e))

        async with AsyncSessionLocal() as db:
            async with db.begin():
                task = await db.get(Task, task_id)
                task.status = "composite_error"
                task.error_log = f"Unexpected error: {str(e)}"
                await db.commit()
```

### Usage Pattern

```python
from app.services.composite_creation import CompositeCreationService
from app.utils.filesystem import get_composites_dir
from app.utils.cli_wrapper import run_cli_script

# ✅ CORRECT: Use service layer + filesystem helpers + CLI wrapper
service = CompositeCreationService("poke1", "vid_abc123")
manifest = service.create_composite_manifest(
    "Bulbasaur forest documentary",
    "Show evolution through seasons"
)

# Generate all composites
result = await service.generate_composites(manifest, resume=False)
print(f"Generated {result['generated']} composites")

# ❌ WRONG: Direct CLI invocation without service layer
await run_cli_script("create_composite.py", ["--character", "char.png", "--environment", "env.png", "--output", "comp.png"])

# ❌ WRONG: Hard-coded paths without filesystem helpers
output_path = f"/workspace/poke1/vid_abc123/assets/composites/clip_01.png"
```

## Dev Agent Guardrails - CRITICAL REQUIREMENTS

### 🔥 Architecture Compliance (MANDATORY)

**1. Transaction Pattern (Architecture Decision 3):**
```python
# ✅ CORRECT: Short transactions only
async with db.begin():
    task.status = "processing"
    await db.commit()

# OUTSIDE transaction - NO db connection held
result = await service.generate_composites(manifest)

async with db.begin():
    task.status = "composites_ready"
    await db.commit()

# ❌ WRONG: Holding transaction during composite generation
async with db.begin():
    task.status = "processing"
    result = await service.generate_composites(manifest)  # BLOCKS DB FOR 9 MINUTES!
    task.status = "composites_ready"
    await db.commit()
```

**2. CLI Script Invocation (Story 3.1):**
```python
# ✅ CORRECT: Use async wrapper from Story 3.1
from app.utils.cli_wrapper import run_cli_script

result = await run_cli_script(
    "create_composite.py",
    ["--character", str(char_path), "--environment", str(env_path), "--output", str(output_path)],
    timeout=30
)

# ❌ WRONG: Direct subprocess (blocks event loop)
import subprocess
subprocess.run(["python", "scripts/create_composite.py", ...])

# ❌ WRONG: Importing script as module
from scripts import create_composite
create_composite.main([...])  # Breaks brownfield architecture
```

**3. Filesystem Paths (Story 3.2):**
```python
# ✅ CORRECT: Use path helpers with security validation
from app.utils.filesystem import get_composites_dir, get_character_dir, get_environment_dir

composites_dir = get_composites_dir(channel_id, project_id)
char_dir = get_character_dir(channel_id, project_id)
env_dir = get_environment_dir(channel_id, project_id)

composite_path = composites_dir / "clip_01.png"

# ❌ WRONG: Hard-coded paths
output_path = f"/app/workspace/channels/{channel_id}/projects/{project_id}/assets/composites/clip_01.png"

# ❌ WRONG: Manual path construction without validation
from pathlib import Path
output_path = Path("/app/workspace") / channel_id / project_id / "assets" / "composites"
```

**4. Error Handling:**
```python
# ✅ CORRECT: Catch CLIScriptError from Story 3.1
from app.utils.cli_wrapper import CLIScriptError

try:
    result = await run_cli_script("create_composite.py", args, timeout=30)
except CLIScriptError as e:
    log.error("composite_failed", script=e.script, exit_code=e.exit_code, stderr=e.stderr)
    # Mark task as "composite_error", allow retry
except asyncio.TimeoutError:
    log.error("composite_timeout", timeout=30)
    # Mark task as "composite_error", allow retry

# ❌ WRONG: Generic exception handling
try:
    result = await run_cli_script(...)
except Exception as e:
    print(f"Error: {e}")  # Loses context, breaks retry logic
```

### 🧠 Previous Story Learnings

**From Story 3.1 (CLI Wrapper):**
- ✅ Security: Path traversal prevention is MANDATORY for all user inputs
- ✅ Use `asyncio.to_thread()` wrapper to prevent blocking event loop
- ✅ Timeout = 30 seconds for composite creation (PIL operations are fast)
- ✅ Logging: JSON structured format with correlation IDs (task_id)
- ✅ All 17 tests passed after security review

**From Story 3.2 (Filesystem Helpers):**
- ✅ Security: Path traversal attacks prevented with regex validation
- ✅ Use `get_composites_dir()` for composite output directory
- ✅ Use `get_character_dir()`, `get_environment_dir()` for input assets
- ✅ Auto-creation: Directories created automatically with `mkdir(parents=True, exist_ok=True)`
- ✅ Multi-channel isolation: Completely independent storage per channel
- ✅ All 32 tests passed after security review

**From Story 3.3 (Asset Generation):**
- ✅ Short transaction pattern verified working (claim → close → work → reopen → update)
- ✅ Service layer pattern: Separate business logic from worker orchestration
- ✅ Manifest pattern: Dataclasses for type-safe data structures
- ✅ Partial resume: Check file existence before regenerating
- ✅ Cost tracking: Update `total_cost_usd` after each pipeline step
- ✅ 29/29 tests passing (100% pass rate)
- ✅ Security: Input validation with regex, sensitive data sanitization

### 📚 Library & Framework Requirements

**Required Libraries (from architecture.md and project-context.md):**
- Python ≥3.10 (async/await, type hints)
- SQLAlchemy ≥2.0 with AsyncSession (from Story 2.1 database foundation)
- asyncpg ≥0.29.0 (async PostgreSQL driver)
- structlog (JSON logging from Story 3.1)
- Pillow (PIL) ≥10.0.0 (for inline split-screen composition - already in scripts/)

**DO NOT Install:**
- ❌ psycopg2 (use asyncpg instead)
- ❌ Synchronous SQLAlchemy engine (must use async)
- ❌ opencv-python (PIL is sufficient for this task)

### 🗂️ File Structure Requirements

**MUST Create:**
- `app/services/composite_creation.py` - CompositeCreationService class
- `app/workers/composite_worker.py` - process_composite_creation_task() function
- `tests/test_services/test_composite_creation.py` - Service unit tests
- `tests/test_workers/test_composite_worker.py` - Worker unit tests

**MUST NOT Modify:**
- `scripts/create_composite.py` - Existing CLI script (brownfield constraint)
- `scripts/create_split_screen.py` - Existing CLI script (project-specific, not generic)
- Any files in `scripts/` directory (brownfield architecture pattern)

### 🧪 Testing Requirements

**Minimum Test Coverage:**
- ✅ Service layer: 12+ test cases (create_composite_manifest, generate_composites, split-screen, check_composite_exists)
- ✅ Worker layer: 8+ test cases (process_composite_creation_task with various error scenarios)
- ✅ Integration: 3+ test cases (end-to-end flow with mocked CLI script)
- ✅ Security: 3+ test cases (path validation, injection prevention)

**Mock Strategy:**
- Mock `run_cli_script()` to avoid actual PIL operations
- Mock `AsyncSessionLocal()` for database transaction tests
- Use `tmp_path` fixture for filesystem tests
- Mock Notion client to avoid actual API calls

### 🔒 Security Requirements

**Input Validation:**
```python
# ✅ Validate channel_id and project_id (Story 3.2 pattern)
import re

def validate_identifier(value: str, name: str):
    if not re.match(r'^[a-zA-Z0-9_-]+$', value):
        raise ValueError(f"{name} contains invalid characters: {value}")
    if len(value) == 0 or len(value) > 100:
        raise ValueError(f"{name} length must be 1-100 characters")

validate_identifier(channel_id, "channel_id")
validate_identifier(project_id, "project_id")
```

**Path Security:**
```python
# ✅ All paths must use filesystem helpers (Story 3.2)
from app.utils.filesystem import get_composites_dir, get_character_dir, get_environment_dir

# Never construct paths manually to prevent path traversal attacks
```

## Dependencies

**Required Before Starting:**
- ✅ Story 3.1 complete: `app/utils/cli_wrapper.py` with `run_cli_script()` and `CLIScriptError`
- ✅ Story 3.2 complete: `app/utils/filesystem.py` with path helpers and security validation
- ✅ Story 3.3 complete: Asset generation (22 assets available in `assets/` subdirectories)
- ✅ Epic 1 complete: Database models (Channel, Task) from Story 1.1
- ✅ Epic 2 complete: Notion API client from Story 2.2
- ✅ Existing CLI script: `scripts/create_composite.py` (brownfield)

**Database Schema Requirements (from Epic 1 & 2 + Story 3.3):**
```sql
-- Task model must have these columns:
tasks (
    id UUID PRIMARY KEY,
    channel_id VARCHAR FK,
    project_id VARCHAR,
    topic TEXT,
    story_direction TEXT,
    status VARCHAR,  -- Must include: "processing", "composites_ready", "composite_error"
    error_log TEXT,
    total_cost_usd DECIMAL,  -- Added in Story 3.3
    notion_page_id VARCHAR UNIQUE
)
```

**Blocks These Stories:**
- Story 3.5: Video clip generation (needs composites as Kling seed images)
- All downstream pipeline stories (3.6, 3.7, 3.8)

## Testing Strategy

### Unit Tests: `tests/test_services/test_composite_creation.py`

**Test Cases for CompositeCreationService:**

1. **test_create_composite_manifest_generates_18_scenes()**
   - Given: topic="Bulbasaur forest", story_direction="18-scene narrative"
   - Verify: Manifest contains exactly 18 SceneComposite objects
   - Verify: Clip numbers are 1-18 in sequence
   - Verify: Each scene has character_path and environment_path set

2. **test_create_composite_manifest_maps_assets_correctly()**
   - Given: 8 character assets and 8 environment assets exist
   - Verify: Each of 18 clips maps to valid character and environment paths
   - Verify: Asset paths use filesystem helpers (get_character_dir, get_environment_dir)
   - Verify: Output paths use get_composites_dir

3. **test_create_composite_manifest_handles_split_screen_clip_15()**
   - Given: Standard 18-scene narrative
   - Verify: Clip 15 has `is_split_screen=True`
   - Verify: Clip 15 has character_b_path and environment_b_path set
   - Verify: Other clips have `is_split_screen=False`

4. **test_generate_composites_success_all_18_composites()**
   - Mock `run_cli_script()` to return success for all composites
   - Verify: All 18 composites generated
   - Verify: Result dict contains {"generated": 18, "skipped": 0, "failed": 0}

5. **test_generate_composites_with_partial_resume()**
   - Given: 10 composites already exist on filesystem
   - Mock `check_composite_exists()` to return True for first 10
   - Verify: Only 8 composites generated (skipped existing 10)
   - Verify: Result dict contains {"generated": 8, "skipped": 10, "failed": 0}

6. **test_generate_composites_failure_raises_cli_script_error()**
   - Mock `run_cli_script()` to raise `CLIScriptError` for clip #5
   - Verify: CLIScriptError propagates with correct details
   - Verify: Error logging includes clip number, character path, environment path, stderr

7. **test_generate_composites_timeout_handling()**
   - Mock `run_cli_script()` to raise `asyncio.TimeoutError` for clip #12
   - Verify: TimeoutError propagates
   - Verify: Timeout logged with clip number

8. **test_check_composite_exists_returns_true_for_existing_file()**
   - Create temporary composite file with `tmp_path` fixture
   - Verify: `check_composite_exists()` returns True

9. **test_check_composite_exists_returns_false_for_missing_file()**
   - Verify: `check_composite_exists()` returns False for non-existent path

10. **test_create_split_screen_composite_generic_implementation()**
    - Mock PIL operations to create split-screen composite
    - Verify: Output dimensions are exactly 1920x1080
    - Verify: Left half is 960x1080, right half is 960x1080
    - Verify: Works for ANY characters and environments (not hardcoded)

11. **test_multi_channel_isolation_paths()**
    - Create services for "poke1" and "poke2" with same project_id
    - Verify: Composite paths are completely isolated
    - Verify: No cross-channel interference

12. **test_idempotent_regeneration_overwrites_existing()**
    - Generate composites (creates files)
    - Regenerate composites (resume=False)
    - Verify: Files overwritten (same paths, updated timestamps)

**Security Test Cases:**

13. **test_path_traversal_prevention_in_channel_id()**
    - Try: channel_id="../../../etc", project_id="vid_123"
    - Verify: ValueError raised or path validation fails

14. **test_path_validation_rejects_invalid_characters()**
    - Try: channel_id="poke1;rm -rf /", project_id="vid_123"
    - Verify: ValueError raised with clear error message

15. **test_asset_path_injection_prevention()**
    - Try: character_path with shell metacharacters
    - Verify: Characters escaped or rejected before CLI invocation

### Unit Tests: `tests/test_workers/test_composite_worker.py`

**Test Cases for process_composite_creation_task:**

1. **test_process_composite_creation_task_success()**
   - Mock task in database with status="queued"
   - Mock `CompositeCreationService.generate_composites()` to return success
   - Verify: Task status updated to "composites_ready"
   - Verify: Notion status updated asynchronously

2. **test_process_composite_creation_task_cli_script_error()**
   - Mock `generate_composites()` to raise `CLIScriptError`
   - Verify: Task status updated to "composite_error"
   - Verify: Error log populated with stderr details

3. **test_process_composite_creation_task_timeout_error()**
   - Mock `generate_composites()` to raise `asyncio.TimeoutError`
   - Verify: Task status updated to "composite_error"
   - Verify: Error log indicates timeout

4. **test_process_composite_creation_task_unexpected_error()**
   - Mock `generate_composites()` to raise generic `Exception`
   - Verify: Task status updated to "composite_error"
   - Verify: Error log contains exception details

5. **test_process_composite_creation_task_not_found()**
   - Mock database to return None for task_id
   - Verify: Function returns early without crashing
   - Verify: Error logged with "task_not_found" event

6. **test_short_transaction_pattern_database_closed_during_generation(mocker)**
   - Mock `AsyncSessionLocal` to track open/close calls
   - Verify: DB connection closed before `generate_composites()` call
   - Verify: DB connection reopened after `generate_composites()` completes
   - Verify: No transaction held during long-running operation

7. **test_notion_update_async_non_blocking(mocker)**
   - Mock `update_notion_status()` to delay 5 seconds
   - Verify: Function completes without waiting for Notion update
   - Verify: `asyncio.create_task()` used for Notion update

8. **test_correlation_id_logging_throughout_task(mocker)**
   - Mock logging to capture all log entries
   - Verify: All log entries include task_id as correlation ID

### Integration Tests (Optional - Mark with `@pytest.mark.integration`)

**test_end_to_end_composite_creation_with_real_filesystem()**
- Create temporary project directory with 22 mock assets
- Generate composites with mocked CLI script (simulate file creation)
- Verify: All 18 PNG files exist in composites directory
- Verify: All files are exactly 1920x1080 pixels
- Clean up temporary files

**test_retry_after_partial_failure()**
- Generate 10 composites, fail at composite #11
- Retry task with resume=True
- Verify: Only 8 composites regenerated
- Verify: Existing 10 composites unchanged

**test_split_screen_composite_full_flow()**
- Create manifest with clip 15 as split-screen
- Generate split-screen composite with inline PIL logic
- Verify: Output is 1920x1080 with two distinct halves
- Verify: Left and right halves are visually different

## Edge Cases & Error Scenarios

1. **Missing Character Asset:**
   - If character file doesn't exist, CLI script fails with FileNotFoundError
   - Mark composite as failed, log missing file path
   - Allow retry after user regenerates missing asset

2. **Missing Environment Asset:**
   - If environment file doesn't exist, CLI script fails with FileNotFoundError
   - Mark composite as failed, log missing file path
   - Allow retry after user regenerates missing asset

3. **Incorrect Asset Dimensions:**
   - `create_composite.py` handles arbitrary input dimensions (scales/crops to 1920x1080)
   - No validation needed on input asset dimensions

4. **Corrupted PNG Files:**
   - PIL raises exception on corrupt images
   - Catch exception, mark composite as failed
   - Log error with asset path for manual inspection

5. **Filesystem Errors:**
   - If directory creation fails (permission denied), propagate error
   - If PNG write fails (disk full), mark composite as failed
   - Do not retry filesystem errors (indicates infrastructure problem)

6. **Concurrent Generation (Multi-Channel):**
   - Multiple workers generating composites for different channels
   - No shared state between workers (stateless service design)
   - Filesystem isolation prevents conflicts (Story 3.2 guarantees)

7. **Split-Screen with Missing Assets:**
   - If either character_b or environment_b is missing, fail gracefully
   - Log clear error message indicating which asset is missing
   - Mark composite as failed, allow retry

8. **PIL Memory Exhaustion:**
   - Large PNG files (ultra-high resolution) may exhaust memory
   - Set reasonable timeout (30s) to catch hung processes
   - Log memory error, mark composite as failed

## Documentation Requirements

**1. Inline Docstrings:**
- Module docstring explaining composite creation pipeline stage
- Class docstrings for `SceneComposite`, `CompositeManifest`, `CompositeCreationService`
- Function docstrings with Args/Returns/Raises/Examples
- Google-style docstring format (consistent with Stories 3.1, 3.2, 3.3)

**2. Architecture Documentation:**
- Update `docs/architecture.md` with composite creation service patterns
- Document scene mapping strategy (18 clips from 22 assets)
- Reference this story in architecture decision log

**3. Usage Examples:**
- Add comprehensive examples in `app/services/composite_creation.py` module docstring
- Document both standard and split-screen composite creation
- Show integration with worker layer

**4. Monitoring Documentation:**
- Document log events emitted during composite creation:
  - `composite_creation_start` - Task started, composite count
  - `composite_creation_composite_success` - Individual composite generated, path, duration
  - `composite_creation_composite_failed` - Individual composite failed, error details
  - `composite_creation_complete` - All composites done, summary stats
  - `composite_creation_cli_error` - CLI script error, stderr, clip number
  - `composite_creation_timeout` - Timeout exceeded, clip number

## Definition of Done

- [ ] `app/services/composite_creation.py` implemented with `SceneComposite`, `CompositeManifest`, `CompositeCreationService`
- [ ] `app/workers/composite_worker.py` implemented with `process_composite_creation_task()`
- [ ] All service layer unit tests passing (12+ test cases)
- [ ] All worker layer unit tests passing (8+ test cases)
- [ ] All security tests passing (3+ test cases)
- [ ] Integration tests passing (3+ test cases)
- [ ] Async execution verified (no event loop blocking)
- [ ] Short transaction pattern verified (DB connection closed during composite generation)
- [ ] Error handling complete (CLIScriptError, TimeoutError, generic Exception)
- [ ] Logging integration added (JSON structured logs with task_id correlation)
- [ ] Type hints complete (all parameters and return types annotated)
- [ ] Docstrings complete (module, class, function-level with examples)
- [ ] Linting passes (`ruff check --fix .`)
- [ ] Type checking passes (`mypy app/`)
- [ ] Multi-channel isolation verified (no cross-channel interference)
- [ ] Partial resume functionality tested (skip existing composites)
- [ ] Split-screen composites working (generic inline PIL implementation)
- [ ] All composites verified as exactly 1920x1080 pixels
- [ ] Notion status update tested (async, non-blocking)
- [ ] Code review approved (adversarial review with security focus)
- [ ] Security validated (path traversal, injection prevention)
- [ ] Merged to `main` branch

## Notes & Implementation Hints

**From Architecture (architecture.md):**
- Composite creation is second stage of 8-step pipeline
- Must integrate with existing `scripts/create_composite.py` (brownfield constraint)
- "Smart Agent + Dumb Scripts" pattern: orchestrator maps scenes, script creates composite
- Filesystem-based storage pattern (not database blobs)

**From project-context.md:**
- Integration utilities (CLI wrapper, filesystem helpers) are MANDATORY
- Short transaction pattern prevents DB connection pool exhaustion
- Async execution throughout to support 3 concurrent workers

**From CLAUDE.md:**
- 1920x1080 (16:9) is CRITICAL for YouTube and Kling compatibility
- `create_composite.py` enforces output dimensions automatically
- Split-screen uses `create_split_screen.py` pattern but needs generic implementation

**Scene Mapping Strategy (Critical):**
```python
# Default strategy: Cycle through assets to create 18 composites
characters = ["char1.png", "char2.png", ..., "char8.png"]  # 8 total
environments = ["env1.png", "env2.png", ..., "env8.png"]   # 8 total

# Map 18 clips to assets (round-robin cycling)
clips = []
for i in range(1, 19):  # 18 clips total
    char_idx = (i - 1) % len(characters)
    env_idx = (i - 1) % len(environments)

    clips.append({
        "clip_number": i,
        "character": characters[char_idx],
        "environment": environments[env_idx],
        "is_split_screen": (i == 15)  # Only clip 15 is split-screen
    })
```

**Filesystem Layout (Reference):**
```
/app/workspace/
└── channels/
    └── poke1/
        └── projects/
            └── vid_abc123/
                └── assets/
                    ├── characters/
                    │   ├── bulbasaur_resting.png
                    │   ├── bulbasaur_walking.png
                    │   └── ... (8 total)
                    ├── environments/
                    │   ├── forest_clearing.png
                    │   ├── forest_stream.png
                    │   └── ... (8 total)
                    ├── props/
                    │   └── ... (6 total - not used in composites)
                    └── composites/  ← NEW DIRECTORY CREATED BY THIS STORY
                        ├── clip_01.png (1920x1080)
                        ├── clip_02.png (1920x1080)
                        └── ... (18 total)
```

**Split-Screen Composition (Inline PIL Logic):**
```python
from PIL import Image

# Load 4 images
char_a = Image.open(char_a_path).convert("RGBA")
env_a = Image.open(env_a_path).convert("RGBA")
char_b = Image.open(char_b_path).convert("RGBA")
env_b = Image.open(env_b_path).convert("RGBA")

# Resize environments to 960x1080 (half width)
# (See create_split_screen.py for reference logic)

# Overlay characters on environments
# Combine left + right halves side-by-side
# Save as 1920x1080 PNG
```

**Security Considerations (from Stories 3.1, 3.2, 3.3):**
- Validate channel_id and project_id with regex: `^[a-zA-Z0-9_-]+$`
- Path traversal prevention: use filesystem helpers, never manual path construction
- All asset paths validated before passing to CLI scripts

**Performance Considerations:**
- Composite creation is I/O-bound (PIL operations are CPU-intensive but fast)
- Timeout = 30 seconds per composite (reasonable for PIL processing)
- Async patterns prevent blocking: worker can claim next task while generating composites
- 18 composites × 30s timeout = 9 minutes maximum per task (typical: 3-5 minutes)

**Retry Strategy:**
```python
# Filesystem errors (permission denied, disk full):
# - Do not retry, mark task as "composite_error" immediately
# - Log error details for infrastructure investigation

# PIL errors (corrupt images, memory exhaustion):
# - Do not retry automatically, mark task as "composite_error"
# - Allow manual retry after user fixes input assets

# Partial failures:
# - Resume from last successful composite (use `check_composite_exists()`)
# - Do not restart from composite #1 (wastes time)
```

## Related Stories

- **Depends On:**
  - 3-1 (CLI Script Wrapper) - provides `run_cli_script()` async wrapper
  - 3-2 (Filesystem Path Helpers) - provides secure path construction
  - 3-3 (Asset Generation) - provides 22 input assets (characters, environments, props)
  - 1-1 (Database Models) - provides Task model
  - 2-2 (Notion API Client) - provides Notion status updates
- **Blocks:**
  - 3-5 (Video Clip Generation) - needs 18 composites as Kling seed images
  - 3-6 (Narration Generation) - parallel but downstream in pipeline
  - 3-7 (SFX Generation) - parallel but downstream in pipeline
  - 3-8 (Final Video Assembly) - needs all previous pipeline outputs
- **Related:**
  - Epic 8 Story (Storage Cleanup) - will use filesystem helpers to identify old projects

## Source References

**PRD Requirements:**
- FR19: 16:9 Composite Creation (combine characters + environments into 1920x1080 composites)
- FR50: Asset Generation Idempotency (applies to composites - re-running overwrites existing files)
- FR-VGO-002: Preserve existing CLI scripts as workers (brownfield constraint)
- NFR-PER-001: Async I/O throughout backend (prevent event loop blocking)

**Architecture Decisions:**
- Architecture Decision 3: Short transaction pattern (claim → close DB → execute → reopen DB → update)
- Asset Storage Strategy: Filesystem with channel organization
- CLI Script Invocation Pattern: subprocess with async wrapper

**Context:**
- project-context.md: CLI Scripts Architecture (lines 59-116)
- project-context.md: Integration Utilities (lines 117-278)
- CLAUDE.md: 16:9 aspect ratio requirements, composite creation patterns
- epics.md: Epic 3 Story 4 - Composite Creation requirements with BDD scenarios

---

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

- Code review session (2026-01-15): Found and fixed 10 issues (3 HIGH, 5 MEDIUM, 2 LOW severity)
- Test failures fixed: Split-screen mocking and partial resume logic corrected
- MyPy type checking: Added `async_session_factory is None` guards throughout worker
- RuntimeWarning resolved: Added task completion callback for fire-and-forget Notion updates

### Completion Notes List

- **Architecture Decision Compliance**: Short transaction pattern correctly implemented with explicit None checks for type safety
- **Test Coverage**: All 28 tests passing (20 service tests + 8 worker tests)
- **Security**: Path traversal validation enforced via `_validate_identifier()` for channel_id and project_id
- **Split-Screen Implementation**: Generic PIL-based composition (not hardcoded to specific projects like haunter)
- **Error Handling**: Comprehensive exception handling with proper task status updates (ASSET_ERROR)
- **Idempotency**: Resume mode (AC3) and regeneration (FR50) both validated by tests

### File List

**Production Code:**
- `app/services/composite_creation.py` (522 lines) - Composite creation service with manifest generation
- `app/workers/composite_worker.py` (229 lines) - Worker orchestration with short transaction pattern

**Test Code:**
- `tests/test_services/test_composite_creation.py` (740 lines) - Service layer unit tests (20 test cases)
- `tests/test_workers/test_composite_worker.py` (424 lines) - Worker integration tests (8 test cases)

**Total:** 1,915 lines of production + test code

---

## Change Log

- **2026-01-15 (Code Review & Fixes):** Adversarial code review completed - 10 issues found and fixed
  - **Issue #1 (HIGH):** Fixed 2 failing tests (split-screen mocking + partial resume logic)
  - **Issue #2 (HIGH):** Fixed 6 MyPy type errors (added `async_session_factory is None` guards)
  - **Issue #3 (HIGH):** Updated story status tracking (marked code_review_status: approved_with_fixes)
  - **Issue #4 (HIGH):** Added File List to Dev Agent Record (4 files, 1,915 LOC)
  - **Issue #5-6 (MEDIUM):** Test mock configuration improvements
  - **Issue #7 (MEDIUM):** Fixed RuntimeWarning (added task completion callback)
  - **Issue #8-10 (LOW-MEDIUM):** Documentation completeness (debug logs, completion notes, AC updates)
  - All 28 tests passing, mypy strict mode clean, ruff linting clean

- **2026-01-15 (Story Creation):** Story 3.4 comprehensive specification created via BMad Method workflow
  - Comprehensive context analysis from Stories 3.1, 3.2, 3.3, and Architecture
  - 6 acceptance criteria with BDD scenarios
  - Complete technical specifications (service + worker layers)
  - 23+ test cases (service + worker + security + integration)
  - Dev agent guardrails with architecture compliance rules
  - Security requirements with input validation and path security
  - Split-screen composite strategy (generic inline PIL implementation)
  - All edge cases and error scenarios documented
  - Ready for dev agent implementation

---

## Status

**Status:** ready-for-dev
**Completed:**
**Ready for:** Dev agent implementation - All dependencies satisfied (Stories 3.1, 3.2, 3.3 complete)
