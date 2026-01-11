# Implementation Patterns & Consistency Rules

## Purpose

This section establishes mandatory naming conventions, coding patterns, and structural guidelines to ensure **consistency across all AI agents** implementing this architecture. These patterns prevent conflicts where different agents make different choices for the same scenarios.

---

## Naming Patterns

### Python Code Naming Conventions (PEP 8)

**Standard:** Follow PEP 8 strictly for all Python code.

| Element | Convention | Examples |
|---------|-----------|----------|
| **Modules/Files** | `snake_case.py` | `task_service.py`, `oauth_manager.py`, `webhook_handlers.py` |
| **Classes** | `PascalCase` | `Task`, `Channel`, `OAuthTokenManager`, `NotionWebhookHandler` |
| **Functions** | `snake_case()` | `get_task_by_id()`, `claim_next_task()`, `refresh_oauth_token()` |
| **Variables** | `snake_case` | `task_id`, `channel_name`, `retry_count`, `next_retry_at` |
| **Constants** | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT`, `DEFAULT_PRIORITY`, `KLING_TIMEOUT_SECONDS` |
| **Private** | `_leading_underscore` | `_encrypt_token()`, `_build_prompt()`, `_internal_cache` |

**Example Module:**
```python
# orchestrator/services/task_service.py

from datetime import datetime
from uuid import UUID

MAX_RETRY_COUNT = 4  # Constant
DEFAULT_PRIORITY = 0  # Constant

class TaskService:  # Class: PascalCase
    def __init__(self, db_session):  # Function: snake_case
        self.db = db_session  # Variable: snake_case
        self._cache = {}  # Private: _leading_underscore

    async def get_task_by_id(self, task_id: UUID):  # Function: snake_case
        """Retrieve task by ID."""
        pass

    async def claim_next_task(self, channel_id: UUID):  # Function: snake_case
        """Claim next queued task for channel."""
        pass
```

---

### Database Naming Conventions

**Standard:** PostgreSQL `snake_case` with plural table names.

| Element | Convention | Examples |
|---------|-----------|----------|
| **Tables** | `snake_case`, plural | `tasks`, `channels`, `oauth_tokens`, `video_clips` |
| **Columns** | `snake_case` | `channel_id`, `created_at`, `retry_count`, `youtube_url` |
| **Indexes** | `idx_{table}_{columns}` | `idx_tasks_queue_claim`, `idx_channels_active` |
| **Constraints** | `{table}_{column}_fkey` | `tasks_channel_id_fkey` (avoided in denormalized schema) |
| **Functions** | `snake_case` | `get_next_channel_for_processing()`, `claim_task()` |
| **Triggers** | `trg_{table}_{action}` | `trg_tasks_notify_insert`, `trg_oauth_updated` |

**Example Schema:**
```sql
-- Table: plural snake_case
CREATE TABLE tasks (
    -- Columns: snake_case
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL,
    channel_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    priority INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    claimed_at TIMESTAMPTZ,
    retry_count INT DEFAULT 0,
    next_retry_at TIMESTAMPTZ,
    youtube_url TEXT,
    notion_page_id TEXT
);

-- Index: idx_{table}_{description}
CREATE INDEX idx_tasks_queue_claim ON tasks
    (channel_id, status, priority DESC, created_at ASC)
    WHERE status = 'queued';

-- Function: snake_case
CREATE FUNCTION claim_task(p_channel_id UUID)
RETURNS TABLE(task_id UUID, title TEXT);
```

---

### API Naming Conventions

**Standard:** RESTful conventions with plural resource names.

| Element | Convention | Examples |
|---------|-----------|----------|
| **Resources** | Plural nouns | `/tasks`, `/channels`, `/oauth-tokens` |
| **Nested Resources** | `/parent/{id}/child` | `/channels/{channel_id}/tasks` |
| **Actions** | `/resource/{id}/action` | `/tasks/{task_id}/retry`, `/channels/{id}/refresh-oauth` |
| **Webhooks** | `/webhook/{source}` | `/webhook/notion`, `/webhook/youtube` |
| **Health Checks** | `/health`, `/ready` | `/health`, `/ready` |

**Example Routes:**
```python
# orchestrator/api/routes.py

from fastapi import APIRouter

router = APIRouter()

# Resource collections: plural
@router.get("/tasks")
async def list_tasks():
    pass

@router.post("/tasks")
async def create_task():
    pass

# Resource items: /{id}
@router.get("/tasks/{task_id}")
async def get_task(task_id: UUID):
    pass

# Nested resources
@router.get("/channels/{channel_id}/tasks")
async def list_channel_tasks(channel_id: UUID):
    pass

# Actions: /{id}/action
@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: UUID):
    pass

# Webhooks: /webhook/{source}
@router.post("/webhook/notion")
async def notion_webhook():
    pass
```

**Query Parameters:**
```
GET /tasks?status=queued&channel_id=abc123&limit=50&offset=0
GET /channels?active=true
```

---

### Pydantic Schema Naming

**Standard:** Descriptive suffixes indicating purpose.

| Suffix | Purpose | Example |
|--------|---------|---------|
| **Create** | POST request body | `TaskCreate`, `ChannelCreate` |
| **Update** | PUT/PATCH request body | `TaskUpdate`, `ChannelUpdate` |
| **Response** | API response | `TaskResponse`, `ChannelResponse` |
| **InDB** | Database representation | `TaskInDB`, `ChannelInDB` |
| **List** | Collection response | `TaskListResponse` |

**Example Schemas:**
```python
# orchestrator/schemas/task.py

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

# POST /tasks request body
class TaskCreate(BaseModel):
    channel_id: UUID
    title: str
    pokemon_name: str
    priority: int = 0

# PATCH /tasks/{id} request body
class TaskUpdate(BaseModel):
    status: str | None = None
    priority: int | None = None
    youtube_url: str | None = None

# GET /tasks/{id} response
class TaskResponse(BaseModel):
    id: UUID
    channel_id: UUID
    channel_name: str
    status: str
    priority: int
    created_at: datetime
    youtube_url: str | None

# Database ORM model
class TaskInDB(TaskResponse):
    retry_count: int
    next_retry_at: datetime | None
    claimed_at: datetime | None

# GET /tasks response (collection)
class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int
    limit: int
    offset: int
```

---

## Structure Patterns

### Project Organization

**Standard:** Feature-based structure with clear separation.

```
ai-video-generator/
├── scripts/                    # Existing CLI scripts (preserve)
│   ├── generate_asset.py
│   ├── generate_video.py
│   ├── generate_audio.py
│   ├── generate_sound_effects.py
│   ├── assemble_video.py
│   ├── create_composite.py
│   └── create_split_screen.py
│
├── orchestrator/               # NEW: FastAPI orchestrator
│   ├── __init__.py
│   ├── main.py                # FastAPI app entry point
│   ├── config.py              # Pydantic Settings
│   ├── database.py            # SQLAlchemy setup
│   │
│   ├── api/                   # API endpoints
│   │   ├── __init__.py
│   │   ├── webhooks.py        # Notion webhook handler
│   │   ├── tasks.py           # Task management endpoints
│   │   └── channels.py        # Channel management endpoints
│   │
│   ├── models/                # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── task.py
│   │   ├── channel.py
│   │   └── oauth_token.py
│   │
│   ├── schemas/               # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── task.py
│   │   ├── channel.py
│   │   └── webhook.py
│   │
│   ├── services/              # Business logic
│   │   ├── __init__.py
│   │   ├── task_service.py
│   │   ├── notion_service.py
│   │   └── oauth_service.py
│   │
│   └── utils/                 # Shared utilities
│       ├── __init__.py
│       ├── logging.py
│       ├── encryption.py
│       └── retry.py
│
├── workers/                   # NEW: Task workers
│   ├── __init__.py
│   ├── main.py               # Worker entry point
│   ├── base_worker.py        # Base worker class
│   ├── asset_worker.py       # Asset generation worker
│   ├── video_worker.py       # Video generation worker
│   ├── audio_worker.py       # Audio generation worker
│   ├── assembly_worker.py    # Final assembly worker
│   └── utils/
│       ├── __init__.py
│       ├── cli_wrapper.py    # Wrapper for scripts/
│       └── notion_updater.py # Notion status updates
│
├── migrations/               # NEW: Alembic migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 001_initial_schema.py
│
├── tests/                    # NEW: Test suite
│   ├── orchestrator/
│   │   ├── api/
│   │   │   └── test_webhooks.py
│   │   └── services/
│   │       └── test_task_service.py
│   ├── workers/
│   │   └── test_asset_worker.py
│   └── integration/
│       └── test_end_to_end.py
│
├── docs/                     # Existing documentation (preserve)
├── prompts/                  # Existing agent SOPs (preserve)
├── pyproject.toml            # Dependencies
├── alembic.ini              # Migration config
└── .env                     # Environment variables
```

**Key Principles:**
- **Preserve `scripts/`**: Do not modify existing CLI scripts
- **Separate `orchestrator/` and `workers/`**: Independent deployment units
- **Feature folders**: Group related files (not layer folders like `models/`, `views/`)
- **Flat over nested**: Avoid deep nesting (max 3 levels)

---

### Test Structure

**Standard:** Mirror production structure with `test_` prefix.

```
tests/
├── orchestrator/
│   ├── api/
│   │   ├── test_webhooks.py          # Tests orchestrator/api/webhooks.py
│   │   ├── test_tasks.py             # Tests orchestrator/api/tasks.py
│   │   └── test_channels.py
│   ├── services/
│   │   ├── test_task_service.py      # Tests orchestrator/services/task_service.py
│   │   └── test_notion_service.py
│   └── models/
│       └── test_task.py
├── workers/
│   ├── test_asset_worker.py          # Tests workers/asset_worker.py
│   ├── test_video_worker.py
│   └── utils/
│       └── test_cli_wrapper.py
├── integration/
│   ├── test_end_to_end.py            # Full pipeline test
│   └── test_notion_to_youtube.py
└── conftest.py                       # Shared fixtures
```

**Test Naming:**
```python
# tests/orchestrator/services/test_task_service.py

import pytest
from orchestrator.services.task_service import TaskService

class TestTaskService:
    # Pattern: test_{function}_{scenario}
    async def test_get_task_by_id_success(self, db_session):
        """Test retrieving existing task by ID."""
        pass

    async def test_get_task_by_id_not_found(self, db_session):
        """Test handling missing task ID."""
        pass

    async def test_claim_next_task_round_robin(self, db_session):
        """Test round-robin channel selection."""
        pass
```

---

## Format Patterns

### API Response Format

**Standard:** Consistent JSON structure (Decision 7: Custom Structured).

**Success Response:**
```json
{
  "success": true,
  "data": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "channel_name": "Pokémon Legends",
    "status": "queued",
    "created_at": "2026-01-09T10:30:00Z"
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task with ID 123 does not exist",
    "details": {
      "task_id": "123e4567-e89b-12d3-a456-426614174000"
    }
  }
}
```

**Collection Response:**
```json
{
  "success": true,
  "data": {
    "tasks": [
      {"id": "...", "status": "queued"},
      {"id": "...", "status": "processing"}
    ],
    "pagination": {
      "total": 42,
      "limit": 20,
      "offset": 0,
      "has_more": true
    }
  }
}
```

**Pydantic Implementation:**
```python
# orchestrator/schemas/common.py

from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar('T')

class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None

class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail

class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool

class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: dict[str, T | PaginationMeta]
```

---

### Data Exchange Format

**Standard:** ISO 8601 dates, UUIDs as strings, snake_case keys.

| Data Type | Format | Example |
|-----------|--------|---------|
| **Timestamps** | ISO 8601 with timezone | `"2026-01-09T10:30:00Z"` |
| **UUIDs** | String (36 chars) | `"123e4567-e89b-12d3-a456-426614174000"` |
| **Booleans** | JSON true/false | `true`, `false` |
| **Nulls** | Omit from response | `{"name": "test"}` not `{"name": "test", "url": null}` |
| **JSON Keys** | snake_case | `"channel_id"`, `"created_at"` |

**Pydantic Configuration:**
```python
from pydantic import BaseModel, ConfigDict

class TaskResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,       # Allow SQLAlchemy models
        json_encoders={
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        },
        exclude_none=True            # Omit None values
    )

    id: UUID
    created_at: datetime
    youtube_url: str | None = None  # Omitted if None
```

---

## Communication Patterns

### Database Session Management

**Standard:** Dependency injection in orchestrator, context managers in workers.

**Orchestrator (FastAPI):**
```python
# orchestrator/database.py

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    """Dependency for FastAPI routes."""
    async with AsyncSessionLocal() as session:
        yield session

# orchestrator/api/tasks.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

@router.get("/tasks/{task_id}")
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db)  # Injected dependency
):
    task = await db.get(Task, task_id)
    return {"success": True, "data": task}
```

**Workers:**
```python
# workers/asset_worker.py

from orchestrator.database import AsyncSessionLocal

async def process_task(task_id: UUID):
    # Context manager for explicit session control
    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)

        # Short transaction pattern
        async with db.begin():
            task.status = "processing"
            await db.commit()

    # Long operation OUTSIDE transaction
    result = await generate_assets(task)

    # New session for result update
    async with AsyncSessionLocal() as db:
        async with db.begin():
            task.status = "assets_ready"
            await db.commit()
```

---

### Exception Handling

**Standard:** Custom exceptions with HTTP status codes.

```python
# orchestrator/utils/exceptions.py

from fastapi import HTTPException

class TaskNotFoundException(HTTPException):
    def __init__(self, task_id: UUID):
        super().__init__(
            status_code=404,
            detail={
                "code": "TASK_NOT_FOUND",
                "message": f"Task {task_id} does not exist",
                "details": {"task_id": str(task_id)}
            }
        )

class ChannelNotFoundException(HTTPException):
    def __init__(self, channel_id: UUID):
        super().__init__(
            status_code=404,
            detail={
                "code": "CHANNEL_NOT_FOUND",
                "message": f"Channel {channel_id} does not exist",
                "details": {"channel_id": str(channel_id)}
            }
        )

class RateLimitExceededException(HTTPException):
    def __init__(self, service: str, retry_after: int):
        super().__init__(
            status_code=429,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": f"{service} rate limit exceeded",
                "details": {"retry_after_seconds": retry_after}
            }
        )

# Usage in services
from orchestrator.utils.exceptions import TaskNotFoundException

async def get_task_by_id(task_id: UUID, db: AsyncSession):
    task = await db.get(Task, task_id)
    if not task:
        raise TaskNotFoundException(task_id)
    return task
```

---

### Logging Pattern

**Standard:** Structured JSON logging with context binding (Decision 8).

```python
# orchestrator/utils/logging.py

import structlog
from structlog.processors import JSONRenderer, TimeStamper, add_log_level

structlog.configure(
    processors=[
        TimeStamper(fmt="iso"),
        add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        JSONRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()

# Usage with context binding
from orchestrator.utils.logging import logger

async def process_task(task_id: UUID, channel_id: UUID):
    # Bind context for all subsequent logs
    log = logger.bind(
        task_id=str(task_id),
        channel_id=str(channel_id)
    )

    log.info("task_processing_started")

    try:
        result = await run_pipeline(task_id)
        log.info("task_processing_completed", duration_seconds=result.duration)
    except Exception as e:
        log.error("task_processing_failed", error=str(e), exc_info=True)
        raise

# Output (JSON):
# {"timestamp": "2026-01-09T10:30:00Z", "level": "info", "event": "task_processing_started", "task_id": "123", "channel_id": "abc"}
```

**Event Naming Convention:**
```
{component}_{action}_{status}

Examples:
- "task_processing_started"
- "task_processing_completed"
- "task_processing_failed"
- "video_generation_started"
- "notion_update_retrying"
- "oauth_token_refreshed"
```

---

## Process Patterns

### CLI Script Wrapper

**Standard:** Centralized wrapper for all `scripts/` calls.

```python
# workers/utils/cli_wrapper.py

import asyncio
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"

async def run_cli_script(
    script_name: str,
    args: list[str],
    timeout_seconds: int = 600
) -> dict:
    """
    Execute CLI script with timeout and error handling.

    Args:
        script_name: Script filename (e.g., "generate_asset.py")
        args: Command-line arguments
        timeout_seconds: Max execution time

    Returns:
        {"success": bool, "stdout": str, "stderr": str, "exit_code": int}
    """
    script_path = SCRIPTS_DIR / script_name
    cmd = ["python", str(script_path)] + args

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=SCRIPTS_DIR  # Run in scripts/ for .env access
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_seconds
        )

        return {
            "success": proc.returncode == 0,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "exit_code": proc.returncode
        }

    except asyncio.TimeoutError:
        proc.kill()
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Script timeout after {timeout_seconds}s",
            "exit_code": -1
        }

# Usage in workers
from workers.utils.cli_wrapper import run_cli_script

async def generate_assets(task):
    result = await run_cli_script(
        "generate_asset.py",
        [
            "--prompt", combined_prompt,
            "--output", str(output_path)
        ],
        timeout_seconds=120
    )

    if not result["success"]:
        raise Exception(f"Asset generation failed: {result['stderr']}")
```

---

### Retry Logic Pattern

**Standard:** Exponential backoff with jitter (Decision 9 requirement).

```python
# orchestrator/utils/retry.py

import asyncio
import random
from typing import Callable, TypeVar

T = TypeVar('T')

async def retry_with_backoff(
    func: Callable[[], T],
    max_retries: int = 4,
    base_delay: int = 60,
    max_delay: int = 3600,
    jitter: bool = True
) -> T:
    """
    Retry function with exponential backoff.

    Delays: 1min → 2min → 4min → 1hr (capped)

    Args:
        func: Async function to retry
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds (60s = 1min)
        max_delay: Maximum delay cap (3600s = 1hr)
        jitter: Add randomness to prevent thundering herd

    Returns:
        Function result

    Raises:
        Last exception if all retries exhausted
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            last_exception = e

            if attempt == max_retries:
                break  # No more retries

            # Exponential backoff: 60s → 120s → 240s → 480s → 960s → capped at 3600s
            delay = min(base_delay * (2 ** attempt), max_delay)

            # Add jitter (±25%)
            if jitter:
                delay *= (0.75 + random.random() * 0.5)

            await asyncio.sleep(delay)

    raise last_exception

# Usage
from orchestrator.utils.retry import retry_with_backoff
from workers.utils.notion_updater import update_notion_status

async def update_task_status_with_retry(task_id: UUID, status: str):
    await retry_with_backoff(
        lambda: update_notion_status(task_id, status),
        max_retries=4,
        base_delay=60  # 1min, 2min, 4min, 8min (capped at 1hr)
    )
```

---

## Enforcement Guidelines

**These rules are MANDATORY for all AI agents:**

1. **Always use PEP 8 naming conventions** for Python code (snake_case functions, PascalCase classes)

2. **Always use PostgreSQL snake_case plural table names** (`tasks`, `channels`, not `Task`, `channel`)

3. **Always use FastAPI REST conventions** for endpoints (`/tasks/{id}`, not `/getTask?id=`)

4. **Always use Pydantic schema suffixes** (`TaskCreate`, `TaskResponse`, not `Task`, `TaskDTO`)

5. **Always return errors in standardized format** (Decision 7: `{"success": false, "error": {...}}`)

6. **Always use structured JSON logging** (Decision 8: `logger.info("event_name", key=value)`)

7. **Always use short transactions** (Decision 3: claim task → close DB → run script → new DB → update)

8. **Always denormalize channel_id** (Decision 1: every table includes `channel_id` for isolation)

9. **Always use `run_cli_script()` wrapper** when calling `scripts/` (never direct `subprocess.run()`)

10. **Always implement retry logic** for external services (Notion, YouTube, Gemini, Kling, ElevenLabs)

11. **Always use dependency injection** for database sessions in FastAPI routes (`db: AsyncSession = Depends(get_db)`)

12. **Always use context managers** for database sessions in workers (`async with AsyncSessionLocal() as db:`)

13. **Always omit None values** from JSON responses (`exclude_none=True` in Pydantic)

14. **Always use ISO 8601 timestamps** in JSON (`"2026-01-09T10:30:00Z"`)

15. **Always preserve existing `scripts/`** - do not modify CLI scripts (maintain "Smart Agent + Dumb Scripts" pattern)

---

## Pattern Examples

### Good Example: Complete Worker Implementation

```python
# workers/asset_worker.py

import structlog
from uuid import UUID
from pathlib import Path
from orchestrator.database import AsyncSessionLocal
from orchestrator.models.task import Task
from workers.utils.cli_wrapper import run_cli_script
from workers.utils.notion_updater import update_notion_status
from orchestrator.utils.retry import retry_with_backoff

logger = structlog.get_logger()

class AssetWorker:
    """Worker for generating photorealistic assets via Gemini."""

    async def process_task(self, task_id: UUID):
        log = logger.bind(task_id=str(task_id))

        # Step 1: Short transaction - claim task
        async with AsyncSessionLocal() as db:
            async with db.begin():
                task = await db.get(Task, task_id)
                task.status = "processing"
                await db.commit()

        log.info("asset_generation_started", pokemon=task.pokemon_name)

        try:
            # Step 2: Long operation OUTSIDE transaction
            output_dir = Path(f"/workspaces/{task.channel_id}/{task_id}/assets")
            output_dir.mkdir(parents=True, exist_ok=True)

            # Use CLI wrapper (Rule 9)
            result = await run_cli_script(
                "generate_asset.py",
                [
                    "--prompt", self._build_prompt(task),
                    "--output", str(output_dir / "character.png")
                ],
                timeout_seconds=120
            )

            if not result["success"]:
                raise Exception(f"Asset generation failed: {result['stderr']}")

            # Step 3: Short transaction - update status
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    task.status = "assets_ready"
                    await db.commit()

            # Step 4: Fire-and-forget Notion update with retry (Rule 10, Decision 9)
            asyncio.create_task(
                retry_with_backoff(
                    lambda: update_notion_status(task.notion_page_id, "Assets Ready"),
                    max_retries=4
                )
            )

            log.info("asset_generation_completed", duration_seconds=result.get("duration"))

        except Exception as e:
            log.error("asset_generation_failed", error=str(e), exc_info=True)

            # Short transaction - mark failed
            async with AsyncSessionLocal() as db:
                async with db.begin():
                    task.status = "failed"
                    task.retry_count += 1
                    await db.commit()

            raise

    def _build_prompt(self, task) -> str:
        """Build complete prompt (private method naming)."""
        # Agent combines prompts, not script (Rule 15)
        return f"{task.global_atmosphere}\n\n{task.asset_prompt}"
```

---

### Anti-Patterns (What to Avoid)

**❌ Bad: Long Transactions**
```python
# DON'T hold transactions during long operations
async with db.begin():
    task = await claim_task(...)
    result = await run_cli_script(...)  # 10 minutes locked!
    await update_task(...)

# DO use short transactions (Decision 3)
async with db.begin():
    task = await claim_task(...)

result = await run_cli_script(...)  # Outside transaction

async with db.begin():
    await update_task(...)
```

**❌ Bad: Inconsistent Naming**
```python
# DON'T mix naming conventions
class taskService:  # Wrong: should be PascalCase
    def GetTaskByID(self, TaskID):  # Wrong: should be snake_case
        pass

# DO follow PEP 8 (Rule 1)
class TaskService:
    def get_task_by_id(self, task_id: UUID):
        pass
```

**❌ Bad: Direct Subprocess Calls**
```python
# DON'T call scripts directly
subprocess.run(["python", "scripts/generate_asset.py", ...])

# DO use CLI wrapper (Rule 9)
await run_cli_script("generate_asset.py", [...])
```

**❌ Bad: Unstructured Logging**
```python
# DON'T use plain print or string formatting
print(f"Processing task {task_id} for channel {channel_id}")

# DO use structured logging (Rule 6)
logger.info("task_processing_started", task_id=str(task_id), channel_id=str(channel_id))
```

**❌ Bad: Missing Retry Logic**
```python
# DON'T call external services without retries
await update_notion_status(task_id, "Processing")  # Fails if Notion is down

# DO implement retry logic (Rule 10)
await retry_with_backoff(
    lambda: update_notion_status(task_id, "Processing"),
    max_retries=4
)
```

---

## Summary

These patterns establish consistency across:
- **67 naming decisions** (Python, Database, API, Pydantic)
- **15 mandatory enforcement rules** for all AI agents
- **8 structural patterns** (project layout, test structure)
- **12 communication patterns** (sessions, exceptions, logging, retries)

**All future implementation must follow these patterns** to prevent agent conflicts and ensure maintainability.

---
