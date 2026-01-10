---
project_name: 'ai-video-generator'
user_name: 'Francis'
date: '2026-01-10'
sections_completed: ['technology_stack', 'brownfield_preservation', 'integration_utilities', 'external_service_patterns', 'project_structure', 'enhanced_naming', 'language_rules', 'framework_rules', 'testing_rules', 'code_quality_rules']
status: 'complete'
architecture_integration: 'complete'
rule_count: 150+
optimized_for_llm: true
last_updated: '2026-01-10'
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

**Python:** >=3.10 (async/await required, 3.14.2 installed)
**Package Manager:** uv (use `uv add` not `pip install`)
**Web Framework:** FastAPI >=0.104.0 (async routes, dependency injection)
**Database:** PostgreSQL 12+ (Railway managed, async driver required)
**ORM:** SQLAlchemy >=2.0.0 (MUST use async engine: `create_async_engine`, `AsyncSession`)
**Database Driver:** asyncpg >=0.29.0 (NOT psycopg2 - async only)
**Queue:** PgQueuer >=0.10.0 (PostgreSQL LISTEN/NOTIFY, `FOR UPDATE SKIP LOCKED`)
**Migrations:** Alembic >=1.13.0 (manual review required before applying migrations)
**Validation:** Pydantic >=2.8.0 (v2 syntax, `model_config` not `Config`)
**Logging:** structlog >=23.2.0 (JSON output, context binding required)
**Encryption:** cryptography >=41.0.0 (Fernet symmetric encryption for OAuth tokens)
**HTTP Client:** httpx >=0.25.0 (async, NOT requests for async code)
**Rate Limiting:** aiolimiter (async rate limiting - Notion 3 req/sec compliance)
**Retry Logic:** tenacity >=8.0.0 (exponential backoff, max 3 attempts)
**Testing:** pytest >=7.4.0, pytest-asyncio >=0.21.0 (async test fixtures)
**Type Checking:** mypy >=1.7.0 (strict mode)
**Linting:** ruff >=0.1.0 (replaces flake8, black, isort)
**Video Processing:** FFmpeg 8.0.1 (system dependency, must be in PATH)

**Critical Version Constraints:**
- SQLAlchemy 2.0+ REQUIRED (1.x incompatible - async patterns changed)
- Pydantic 2.x REQUIRED (1.x incompatible - `model_config` vs `Config` class)
- Python 3.10+ REQUIRED (match type `|` syntax, async improvements)
- asyncpg REQUIRED for async (psycopg2/psycopg3 NOT compatible with async SQLAlchemy)
- PgQueuer REQUIRED for worker coordination (native LISTEN/NOTIFY + FOR UPDATE SKIP LOCKED)
- aiolimiter REQUIRED for Notion API compliance (3 requests per second rate limit)

**Deployment Platform:**
- Railway Multi-Service ($5/month Hobby plan, auto-deploy on main branch)
- Services: web (FastAPI orchestrator), worker-1/2/3 (3 independent processes), postgres (managed)
- Workspace Volume: `/app/workspace/` (persistent storage for channel assets, videos, audio)
- Connection Pooling: pool_size=10, max_overflow=5, pool_pre_ping=True (Railway connection recycling)

---

## Critical Implementation Rules

### CLI Scripts Architecture

**Scripts Directory (`scripts/`):**
- Contains 7 CLI tools: `generate_asset.py`, `create_composite.py`, `create_split_screen.py`, `generate_video.py`, `generate_audio.py`, `generate_sound_effects.py`, `assemble_video.py`
- Scripts are stateless CLI tools invoked via subprocess from the orchestration layer
- Scripts can be modified when needed (bug fixes, improvements, new features)

**Orchestration Integration Pattern:**
- Orchestration layer (`app/` directory) invokes scripts via subprocess wrapper
- Worker processes call scripts via `run_cli_script()`, never import them as modules
- Scripts communicate via command-line arguments, stdout/stderr, and exit codes

**Architecture Boundary:**
```
┌─────────────────────────────────────────────┐
│ app/ (Orchestration Layer)                  │
│ - FastAPI web service                       │
│ - 3 worker processes                        │
│ - PostgreSQL state management               │
│ - Notion/YouTube API clients                │
│                                             │
│ MUST USE: subprocess calls via wrapper     │
└─────────────────────────────────────────────┘
                    ↓ subprocess
┌─────────────────────────────────────────────┐
│ scripts/ (CLI Tools)                        │
│ - 7 CLI tools                               │
│ - Command-line interface only               │
│ - Stateless execution                       │
│ - No knowledge of orchestration internals   │
└─────────────────────────────────────────────┘
```

**Anti-Patterns (FORBIDDEN):**
- ❌ NEVER import CLI scripts as Python modules: `from scripts.generate_asset import main`
- ❌ NEVER add database calls or state management to CLI scripts
- ❌ NEVER add orchestration-specific logic to CLI scripts

**Correct Pattern:**
```python
# ✅ CORRECT: Use subprocess wrapper
from app.utils.cli_wrapper import run_cli_script

result = await run_cli_script(
    "generate_asset.py",
    ["--prompt", prompt, "--output", str(output_path)],
    timeout=60
)

# ❌ WRONG: Import as module
from scripts.generate_asset import generate_asset_main
generate_asset_main(prompt, output_path)
```

**Rationale:**
- Maintains "Smart Agent + Dumb Scripts" architectural pattern
- Scripts remain portable and testable independently
- Orchestration layer handles state, coordination, and error recovery

### Integration Utilities (MANDATORY)

**CLI Script Wrapper (Required Implementation):**

**Location:** `app/utils/cli_wrapper.py`

**MUST use this wrapper for ALL subprocess calls** - never use `subprocess.run()` directly in orchestration code.

```python
import asyncio
import subprocess
from pathlib import Path
from typing import List

class CLIScriptError(Exception):
    """Raised when CLI script fails with non-zero exit code"""
    def __init__(self, script: str, exit_code: int, stderr: str):
        self.script = script
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(f"{script} failed with exit code {exit_code}: {stderr}")

async def run_cli_script(
    script: str,
    args: List[str],
    timeout: int = 600
) -> subprocess.CompletedProcess:
    """
    Run CLI script without blocking async event loop.

    Args:
        script: Script name (e.g., "generate_asset.py")
        args: List of command-line arguments
        timeout: Timeout in seconds (default: 600 = 10 min for Kling videos)

    Returns:
        CompletedProcess with stdout, stderr, returncode

    Raises:
        CLIScriptError: If script exits with non-zero code
        asyncio.TimeoutError: If script exceeds timeout
    """
    script_path = Path("scripts") / script
    command = ["python", str(script_path)] + args

    # Use asyncio.to_thread to avoid blocking event loop
    result = await asyncio.to_thread(
        subprocess.run,
        command,
        capture_output=True,
        text=True,
        timeout=timeout
    )

    if result.returncode != 0:
        raise CLIScriptError(script, result.returncode, result.stderr)

    return result
```

**Usage Pattern:**
```python
from app.utils.cli_wrapper import run_cli_script, CLIScriptError

# ✅ CORRECT: Use wrapper, handle errors, log appropriately
try:
    result = await run_cli_script(
        "generate_asset.py",
        ["--prompt", full_prompt, "--output", str(output_path)],
        timeout=60
    )
    log.info("Asset generated", stdout=result.stdout, path=output_path)
except CLIScriptError as e:
    log.error("Asset generation failed", script=e.script, stderr=e.stderr, exit_code=e.exit_code)
    raise  # Re-raise for worker to handle (mark task failed, retry, etc.)
except asyncio.TimeoutError:
    log.error("Asset generation timeout", script="generate_asset.py", timeout=60)
    raise

# ❌ WRONG: Direct subprocess call (blocks event loop)
result = subprocess.run(["python", "scripts/generate_asset.py", "--prompt", prompt], ...)
```

**Filesystem Helpers (Required Implementation):**

**Location:** `app/utils/filesystem.py`

**MUST use these helpers for ALL path construction** - never use hard-coded paths or f-string concatenation.

```python
from pathlib import Path

WORKSPACE_ROOT = Path("/app/workspace")  # Railway persistent volume

def get_channel_workspace(channel_id: str) -> Path:
    """Get workspace directory for channel (auto-creates)"""
    path = WORKSPACE_ROOT / "channels" / channel_id
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_project_dir(channel_id: str, project_id: str) -> Path:
    """Get project directory within channel workspace (auto-creates)"""
    path = get_channel_workspace(channel_id) / "projects" / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_asset_dir(channel_id: str, project_id: str) -> Path:
    """Get assets directory for project (auto-creates)"""
    path = get_project_dir(channel_id, project_id) / "assets"
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_video_dir(channel_id: str, project_id: str) -> Path:
    """Get videos directory for project (auto-creates)"""
    path = get_project_dir(channel_id, project_id) / "videos"
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_audio_dir(channel_id: str, project_id: str) -> Path:
    """Get audio directory for project (auto-creates)"""
    path = get_project_dir(channel_id, project_id) / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_sfx_dir(channel_id: str, project_id: str) -> Path:
    """Get sound effects directory for project (auto-creates)"""
    path = get_project_dir(channel_id, project_id) / "sfx"
    path.mkdir(parents=True, exist_ok=True)
    return path
```

**Usage Pattern:**
```python
from app.utils.filesystem import get_asset_dir, get_video_dir

# ✅ CORRECT: Use helpers, Pathlib, convert to string for CLI
asset_dir = get_asset_dir(channel_id="poke1", project_id="vid_123")
output_path = asset_dir / "characters" / "bulbasaur.png"

# Pass string path to CLI script
await run_cli_script("generate_asset.py", ["--output", str(output_path)])

# ❌ WRONG: Hard-coded paths with f-strings
output_path = f"/workspace/poke1/vid_123/assets/bulbasaur.png"

# ❌ WRONG: String concatenation
output_path = "/workspace/" + channel_id + "/" + project_id + "/assets/bulbasaur.png"
```

**Why These Utilities Are Mandatory:**
- **CLI Wrapper:** Prevents blocking async event loop, standardizes error handling, enforces timeout management
- **Filesystem Helpers:** Ensures consistent path structure, auto-creates directories, supports multi-channel isolation
- **Architecture Compliance:** Both utilities are documented in architecture as required patterns
- **Testing:** These utilities are the boundary layer - mock them in tests, not individual subprocess calls

### External Service Integration Patterns

**Notion API Integration (3 req/sec Rate Limiting):**

**Location:** `app/clients/notion.py`

**MUST enforce 3 requests per second rate limit** - Notion API blocks over 3 req/sec.

```python
from aiolimiter import AsyncLimiter
import httpx

class NotionClient:
    """Notion API client with mandatory rate limiting"""

    def __init__(self, auth_token: str):
        self.auth_token = auth_token
        self.client = httpx.AsyncClient()
        # CRITICAL: 3 requests per 1 second (Notion API limit)
        self.rate_limiter = AsyncLimiter(max_rate=3, time_period=1)

    async def update_task_status(self, page_id: str, status: str) -> dict:
        """Update task status in Notion database (rate limited)"""
        async with self.rate_limiter:
            response = await self.client.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers={"Authorization": f"Bearer {self.auth_token}"},
                json={"properties": {"Status": {"status": {"name": status}}}}
            )
            response.raise_for_status()
            return response.json()

    async def get_database_pages(self, database_id: str) -> list[dict]:
        """Get all pages from Notion database (rate limited)"""
        async with self.rate_limiter:
            response = await self.client.post(
                f"https://api.notion.com/v1/databases/{database_id}/query",
                headers={"Authorization": f"Bearer {self.auth_token}"},
                json={}
            )
            response.raise_for_status()
            return response.json()["results"]
```

**YouTube API Integration (Quota Management):**

**Location:** `app/clients/youtube.py`

**MUST check quota before operations** - YouTube has 10,000 units/day limit, uploads cost 1,600 units.

```python
from app.models import YouTubeQuotaUsage
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date

class YouTubeClient:
    """YouTube API client with quota tracking"""

    async def check_quota(self, channel_id: str, operation: str, db: AsyncSession) -> bool:
        """
        Check if quota available for operation before executing.

        Returns:
            True if quota available, False if quota exceeded
        """
        today = date.today()

        # Get today's usage for channel
        quota = await db.get(YouTubeQuotaUsage, (channel_id, today))
        if not quota:
            quota = YouTubeQuotaUsage(channel_id=channel_id, date=today, units_used=0, daily_limit=10000)
            db.add(quota)

        # Operation costs (YouTube API pricing)
        operation_costs = {
            "upload": 1600,
            "update": 50,
            "list": 1,
            "search": 100
        }

        cost = operation_costs.get(operation, 0)

        # Check if operation would exceed quota
        if quota.units_used + cost > quota.daily_limit:
            return False  # Quota exceeded

        return True  # Quota available

    async def upload_video(self, video_path: str, title: str, description: str, channel_id: str, db: AsyncSession):
        """Upload video to YouTube (checks quota first)"""
        # CRITICAL: Check quota before upload
        if not await self.check_quota(channel_id, "upload", db):
            raise QuotaExceededError(f"YouTube quota exceeded for channel {channel_id}")

        # Perform upload...
        # After success, record quota usage
        await self.record_quota_usage(channel_id, "upload", 1600, db)
```

**Retry Strategy with Exponential Backoff:**

**Pattern:** Use tenacity decorators for all external API calls (Gemini, Kling, ElevenLabs, Notion, YouTube).

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

# Retriable errors: network timeouts, 5xx server errors, 429 rate limits
RETRIABLE_ERRORS = (httpx.TimeoutException, httpx.HTTPStatusError)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(RETRIABLE_ERRORS),
    reraise=True
)
async def call_external_api_with_retry(url: str, **kwargs):
    """
    Call external API with automatic retry on transient failures.

    Retry strategy:
    - Attempt 1: Immediate
    - Attempt 2: After 2 seconds
    - Attempt 3: After 4 seconds
    - Max 3 attempts, then raise exception
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(url, **kwargs)
        response.raise_for_status()  # Raises HTTPStatusError for 4xx/5xx
        return response.json()
```

**Non-Retriable Errors (Fail Fast):**
- ❌ 401 Unauthorized (bad API key) - NO RETRY
- ❌ 403 Forbidden (permission denied) - NO RETRY
- ❌ 400 Bad Request (invalid parameters) - NO RETRY
- ✅ 429 Too Many Requests (rate limit) - RETRY with backoff
- ✅ 500/502/503 Server Error - RETRY with backoff
- ✅ Network timeout - RETRY with backoff

**Error Classification Example:**
```python
def is_retriable_error(exception: Exception) -> bool:
    """Determine if error should be retried"""
    if isinstance(exception, httpx.HTTPStatusError):
        # Retry server errors and rate limits
        return exception.response.status_code in [429, 500, 502, 503, 504]
    if isinstance(exception, (httpx.TimeoutException, httpx.ConnectError)):
        # Retry network errors
        return True
    # Don't retry auth errors, bad requests, etc.
    return False
```

**Integration Pattern Summary:**
- **Notion:** ALWAYS use `AsyncLimiter(3, 1)` for rate limiting
- **YouTube:** ALWAYS call `check_quota()` before operations, record usage after success
- **Retry Logic:** Use tenacity decorators, max 3 attempts, exponential backoff (2s, 4s, 8s)
- **Error Handling:** Classify errors as retriable vs non-retriable, fail fast on auth/validation errors

### Project Structure & Organization (MANDATORY)

**Orchestration Layer Structure:**

The `app/` directory has a MANDATORY layout - all files must be placed according to these rules:

```
app/
├── __init__.py
├── main.py                    # FastAPI application, route registration, middleware
├── worker.py                  # Worker process entry point (3 instances on Railway)
├── database.py                # Async engine, session factory, get_session() dependency
├── models.py                  # All SQLAlchemy models (until 500 lines, then split)
├── config.py                  # Configuration loading (env vars, YAML channel configs)
│
├── routes/                    # FastAPI route handlers (HTTP interface)
│   ├── __init__.py
│   ├── health.py              # /health endpoint (Railway liveness probe)
│   ├── channels.py            # /api/v1/channels CRUD
│   ├── tasks.py               # /api/v1/tasks list/get
│   ├── reviews.py             # /api/v1/reviews approve/reject
│   └── webhooks.py            # /webhook/notion (future)
│
├── services/                  # Business logic, orchestration
│   ├── __init__.py
│   ├── task_orchestrator.py  # 8-step pipeline execution logic
│   ├── notion_sync.py         # Notion polling + push updates (60s interval)
│   ├── youtube_uploader.py    # YouTube upload with quota checks
│   ├── cost_tracker.py        # track_api_cost() function
│   └── ...                    # Other business logic services
│
├── clients/                   # External API clients (third-party integrations)
│   ├── __init__.py
│   ├── notion.py              # NotionClient (AsyncLimiter 3 req/sec)
│   ├── youtube.py             # YouTubeClient (quota tracking)
│   └── ...                    # Future: gemini.py, kling.py, elevenlabs.py wrappers
│
└── utils/                     # Cross-cutting utilities (helpers, tools)
    ├── __init__.py
    ├── cli_wrapper.py         # run_cli_script() - MANDATORY for subprocess
    ├── filesystem.py          # Workspace path helpers - MANDATORY
    ├── encryption.py          # Fernet encrypt/decrypt for OAuth tokens
    ├── logging.py             # structlog configuration
    └── alerts.py              # send_alert() Discord webhook
```

**File Placement Rules (CRITICAL):**

- **Routes (`app/routes/`)**: FastAPI endpoint handlers ONLY
  - ✅ Correct: HTTP request/response handling, parameter validation, call services
  - ❌ Wrong: Business logic, database queries, external API calls

- **Services (`app/services/`)**: Business logic and orchestration
  - ✅ Correct: Task orchestration, workflow coordination, complex business rules
  - ❌ Wrong: HTTP handling, direct database access (use dependency injection)

- **Clients (`app/clients/`)**: Third-party API wrappers
  - ✅ Correct: External service integration, rate limiting, authentication
  - ❌ Wrong: Business logic, database access, orchestration

- **Utils (`app/utils/`)**: Pure helper functions
  - ✅ Correct: CLI wrapper, filesystem helpers, encryption, logging setup
  - ❌ Wrong: Business logic, API clients, route handlers

**Models Organization:**
- ALL SQLAlchemy models in single `app/models.py` until ~500 lines
- After 500 lines: Split by domain (`app/models/tasks.py`, `app/models/channels.py`, etc.)
- NEVER split models prematurely (causes circular import issues)

**Configuration Management:**
- Environment variables: `app/config.py` loads from Railway env vars
- Channel configs: YAML files in `channel_configs/*.yaml` (version controlled)
- Secrets: Railway environment variables only (FERNET_KEY, DATABASE_URL)

**Testing Structure (Mirrors app/):**
```
tests/
├── conftest.py                # Shared fixtures (async DB session, mock clients)
├── test_routes/               # FastAPI route tests
├── test_services/             # Business logic tests
├── test_clients/              # External API client tests
└── test_utils/                # Utility function tests
```

**Anti-Patterns (FORBIDDEN):**
- ❌ Business logic in route handlers
- ❌ Database queries in route handlers (use services)
- ❌ External API calls in route handlers (use clients via services)
- ❌ Creating `helpers/`, `lib/`, `shared/` directories (use `utils/`)
- ❌ Splitting models before 500 lines
- ❌ Putting configuration in Python files (use env vars + YAML)

### Enhanced Naming Conventions (From Architecture)

**API Endpoint Naming (MANDATORY):**

- **Base Prefix:** ALL API endpoints MUST start with `/api/v1/`
  - ✅ Correct: `/api/v1/channels`, `/api/v1/tasks`
  - ❌ Wrong: `/channels`, `/v1/channels`, `/api/channels`

- **Resource Names:** Plural nouns, kebab-case for multi-word
  - ✅ Correct: `/api/v1/youtube-quota`, `/api/v1/audit-logs`, `/api/v1/video-costs`
  - ❌ Wrong: `/api/v1/YouTubeQuota`, `/api/v1/auditLogs`, `/api/v1/video_costs`

- **Path Parameters:** Singular resource name in snake_case
  - ✅ Correct: `{channel_id}`, `{task_id}`, `{video_id}`
  - ❌ Wrong: `{id}`, `{channelId}`, `{Channel_ID}`

- **Action Endpoints:** Verb suffix on resource
  - ✅ Correct: `/api/v1/tasks/{task_id}/approve`, `/api/v1/tasks/{task_id}/reject`, `/api/v1/tasks/{task_id}/retry`
  - ❌ Wrong: `/api/v1/approve-task/{task_id}`, `/api/v1/tasks/approve`, `/api/v1/task/{task_id}/approve`

- **Query Parameters:** snake_case
  - ✅ Correct: `?status=pending&channel_id=poke1&date_from=2026-01-01`
  - ❌ Wrong: `?Status=pending&channelId=poke1&dateFrom=2026-01-01`

**Enhanced Database Naming (From Architecture):**

- **Primary Keys:** ALWAYS `id` (UUID type), NEVER `{table}_id`
  - ✅ Correct: `channels.id`, `tasks.id`, `videos.id`
  - ❌ Wrong: `channels.channel_id`, `tasks.task_id`

- **Foreign Keys:** `{table_singular}_id`
  - ✅ Correct: `tasks.channel_id` (references `channels.id`)
  - ✅ Correct: `videos.task_id` (references `tasks.id`)
  - ❌ Wrong: `tasks.channelId`, `videos.taskId`, `tasks.channel`

- **Indexes:** `ix_{table}_{column}` or `ix_{table}_{col1}_{col2}`
  - ✅ Correct: `ix_tasks_channel_id`, `ix_tasks_status`, `ix_audit_logs_timestamp_action`
  - ❌ Wrong: `tasks_channel_id_index`, `idx_tasks_channel`, `index_tasks_on_channel_id`

- **Encrypted Columns:** `{field}_encrypted`
  - ✅ Correct: `youtube_token_encrypted`, `notion_token_encrypted`, `gemini_key_encrypted`
  - ❌ Wrong: `youtube_token`, `encrypted_youtube_token`, `youtube_token_enc`

- **Composite Primary Keys:** For quota/cost tracking tables
  - ✅ Correct: `YouTubeQuotaUsage(channel_id, date)` - composite PK
  - Rationale: One row per channel per day

**FastAPI Route Naming Consistency:**

Routes MUST match resource names:
```python
# ✅ CORRECT: Route matches resource
@router.get("/api/v1/channels")
@router.get("/api/v1/channels/{channel_id}")
@router.post("/api/v1/channels")

# ✅ CORRECT: Action endpoint
@router.post("/api/v1/tasks/{task_id}/approve")

# ❌ WRONG: Inconsistent naming
@router.get("/api/v1/channel")  # Should be plural
@router.get("/channels")  # Missing /api/v1 prefix
@router.post("/approve/{task_id}")  # Should be /tasks/{task_id}/approve
```

**Pydantic Schema Naming:**
- Suffix indicates usage: `{Model}Create`, `{Model}Update`, `{Model}Response`, `{Model}InDB`
  - ✅ Correct: `TaskCreate`, `TaskUpdate`, `TaskResponse`, `ChannelInDB`
  - ❌ Wrong: `CreateTask`, `Task`, `TaskDTO`, `TaskModel`

### Python Language-Specific Rules

**PEP 8 Naming Conventions (MANDATORY):**
- **Modules/Files:** `snake_case.py` → `task_service.py`, `oauth_manager.py`
- **Classes:** `PascalCase` → `TaskService`, `OAuthTokenManager`
- **Functions:** `snake_case()` → `get_task_by_id()`, `claim_next_task()`
- **Variables:** `snake_case` → `task_id`, `channel_name`, `retry_count`
- **Constants:** `UPPER_SNAKE_CASE` → `MAX_RETRY_COUNT`, `DEFAULT_PRIORITY`
- **Private:** `_leading_underscore` → `_encrypt_token()`, `_internal_cache`

**Async/Await Patterns (CRITICAL):**
- ALL database operations MUST use `async/await` (SQLAlchemy 2.0 async engine)
- ALL HTTP requests in async code MUST use `httpx` async client (NOT `requests`)
- FastAPI route handlers MUST be `async def` when accessing database
- Worker functions MUST be `async def` for database and API calls
- Use `asyncio.create_subprocess_exec()` for subprocess calls in async context

**Type Hints (REQUIRED):**
- ALL functions MUST have type hints for parameters and return values
- Use Python 3.10+ union syntax: `str | None` (NOT `Optional[str]`)
- Import types explicitly: `from uuid import UUID`, `from datetime import datetime`
- SQLAlchemy models: use `Mapped[type]` for ORM columns

**Import Organization:**
- Standard library imports first
- Third-party imports second
- Local application imports third
- Use absolute imports: `from orchestrator.models.task import Task`
- Group related imports together

**Error Handling Patterns:**
- Custom exceptions MUST extend `HTTPException` in FastAPI routes
- Include structured error details: `{"code": "ERROR_CODE", "message": "...", "details": {...}}`
- Log exceptions with `exc_info=True` for full stack traces
- NEVER silently catch exceptions without logging or re-raising

**Database Session Management:**
- **FastAPI routes:** Use dependency injection: `db: AsyncSession = Depends(get_db)`
- **Workers:** Use context managers: `async with AsyncSessionLocal() as db:`
- **Transactions:** Keep short (claim → close DB → process → new DB → update)
- NEVER hold transactions during long operations (CLI scripts, API calls, video processing)

**Context Managers:**
- ALWAYS use `async with` for database sessions
- ALWAYS use `async with db.begin():` for explicit transactions
- Clean up resources in `finally` blocks when needed

---

### Framework-Specific Rules

**FastAPI Route Conventions:**
- Plural resource names: `/tasks`, `/channels` (NOT `/task`, `/channel`)
- Nested resources: `/channels/{channel_id}/tasks`
- Actions: `/tasks/{task_id}/retry`
- Webhooks: `/webhook/notion`
- Health checks: `/health`, `/ready`

**Dependency Injection (MANDATORY):**
- Database sessions: `db: AsyncSession = Depends(get_db)`
- NEVER create sessions manually in routes
- Dependencies auto-close after request

**API Response Format (REQUIRED):**
- Success: `{"success": true, "data": {...}}`
- Error: `{"success": false, "error": {"code": "ERROR_CODE", "message": "...", "details": {...}}}`
- Paginated: `{"success": true, "data": {"items": [...], "pagination": {...}}}`

**Pydantic Schema Conventions:**
- Naming: `TaskCreate`, `TaskUpdate`, `TaskResponse`, `TaskInDB`
- Config: `model_config = ConfigDict(from_attributes=True, exclude_none=True)`
- ALWAYS exclude None values from JSON (`exclude_none=True`)
- Use `from_attributes=True` to load from SQLAlchemy models

**SQLAlchemy 2.0 Async Patterns (CRITICAL):**
- Engine: `create_async_engine(DATABASE_URL)`
- Sessions: `AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)`
- ORM columns: Use `Mapped[type]` annotation (NOT old `Column()` syntax)
- Queries: `await db.execute(select(Model).where(...))`
- Single record: `await db.get(Model, id)`
- ALWAYS use `await` with all database operations

**Database Table/Column Naming:**
- Tables: plural snake_case (`tasks`, `channels`, `oauth_tokens`)
- Columns: snake_case (`channel_id`, `created_at`, `retry_count`)
- Indexes: `idx_{table}_{columns}` → `idx_tasks_queue_claim`
- Functions: snake_case → `claim_task()`, `get_next_channel_for_processing()`

**Transaction Patterns (MANDATORY - Architecture Decision 3):**
- **Short transactions only:** Claim → close DB → process → new DB → update
- **NEVER hold transaction during:** CLI scripts, API calls, video processing
- **Pattern:**
  ```python
  # Step 1: Claim (short transaction)
  async with AsyncSessionLocal() as db:
      async with db.begin():
          task.status = "processing"
          await db.commit()

  # Step 2: Process (OUTSIDE transaction)
  result = await run_cli_script(...)

  # Step 3: Update (short transaction)
  async with AsyncSessionLocal() as db:
      async with db.begin():
          task.status = "completed"
          await db.commit()
  ```

**Queue Operations:**
- Use `FOR UPDATE SKIP LOCKED` for atomic task claims
- Use PostgreSQL LISTEN/NOTIFY via PgQueuer for instant wake-up
- Partial indexes on queue tables: `WHERE status = 'queued'`

**Alembic Migrations:**
- ALWAYS manual migrations (NEVER autogenerate without review)
- Naming: `{version}_{description}.py` → `001_initial_schema.py`
- MUST include both `upgrade()` and `downgrade()` functions
- Test migrations locally before deploying to Railway

---

### Testing Rules

**Test Structure & Organization:**
- **Directory:** `tests/` mirroring script structure
- **File Naming:** `test_{script_name}.py` → `test_generate_asset.py`, `test_assemble_video.py`
- **Function Naming:** `test_{scenario}` → `test_api_key_missing()`, `test_generate_asset_success()`
- **Fixtures:** Shared mocks in `tests/conftest.py`

**Testing CLI Scripts (CRITICAL):**
- Mock ALL external API calls (Gemini, Kling, ElevenLabs) - NEVER call real APIs in tests
- Test argument parsing with `argparse`
- Verify file output creation and content
- Test error exit codes: 0 (success), 1 (failure)
- Mock environment variables (`.env` files)

**Mocking External Services:**
- **Gemini API:** Mock `google.generativeai.ImageGenerationModel.generate_images()`
- **KIE.ai (Kling):** Mock `requests.post()` to `https://api.kie.ai/api/v1`
- **ElevenLabs:** Mock audio generation endpoints
- **catbox.moe:** Mock image upload endpoint
- Use `unittest.mock.patch()` or `pytest-mock` for API mocking
- Fixtures in `tests/conftest.py` with `@pytest.fixture`

**Testing File Operations:**
- Use `pytest.tmpdir` or `tmp_path` fixture for temporary files
- Verify output file exists: `assert output_path.exists()`
- Verify file format: Check PNG/MP4/MP3 headers with Pillow/PIL
- Test composite dimensions: `assert img.size == (1920, 1080)` for 16:9

**Testing Error Scenarios (MANDATORY):**
- Missing API keys (`GEMINI_API_KEY` not set)
- API timeout errors (Kling long-running jobs)
- Invalid input files (missing character image, corrupt PNG)
- Network failures (catbox.moe upload fails)
- Invalid arguments (missing required flags)
- Exit code verification: `assert result.returncode == 1`

**Testing FFmpeg Operations:**
- Mock `subprocess.run()` calls to FFmpeg/ffprobe
- Test manifest JSON parsing
- Verify FFmpeg command construction
- Test audio duration probing calculations
- Test video trimming calculations

**Coverage Requirements:**
- CLI argument parsing: 100%
- API error handling: 100%
- File I/O operations: 80%+
- Success paths: 100%
- Exclude: `if __name__ == "__main__":` blocks, `.env` loading, debug prints

**Integration Testing:**
- **Unit tests (default):** Mock all external APIs, test script logic in isolation
- **Integration tests (manual):** Mark with `@pytest.mark.integration` and `@pytest.mark.slow`
- Skip by default: `pytest -m "not integration"` (integration tests cost money!)
- Only run integration tests manually when needed

**Pytest Configuration:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_functions = "test_*"
addopts = "-v --strict-markers"
markers = [
    "slow: marks tests as slow",
    "integration: marks tests requiring external services"
]
```

---

### Code Quality & Style Rules

**Linting & Formatting Tools:**
- **Linter:** ruff >=0.1.0 (replaces flake8, black, isort)
- **Type Checker:** mypy >=1.7.0 (strict mode)
- **Line Length:** 100 characters maximum
- **Indentation:** 4 spaces (NO TABS)
- **Quotes:** Double quotes `"` preferred

**Ruff Configuration (pyproject.toml):**
```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "N", "UP"]
ignore = ["E501"]
```

**Mypy Configuration (pyproject.toml):**
```toml
[tool.mypy]
python_version = "3.10"
strict = true
disallow_untyped_defs = true
```

**Type Hint Requirements (MANDATORY):**
- ALL functions MUST have complete type hints (parameters + return)
- Use Python 3.10+ union syntax: `str | None` (NOT `Optional[str]`)
- Import types explicitly: `from uuid import UUID`, `from datetime import datetime`
- No `# type: ignore` without justification comment

**Documentation Standards:**
- **Module docstrings:** Required at top of every `.py` file
- **Function docstrings:** Required for all public functions (Google style)
- **Inline comments:** Only for non-obvious logic, explain "why" not "what"
- **CLI error messages:** Use emoji prefix (`❌` error, `✅` success, `⏳` progress)

**Import Organization (Auto-sorted by Ruff):**
1. Standard library imports
2. Third-party imports
3. Local application imports

**Error Message Formatting:**
```python
# Good: Clear, actionable
print("❌ GEMINI_API_KEY not found in environment", file=sys.stderr)

# Bad: Vague
print("Error", file=sys.stderr)
```

**Code Quality Checks (Pre-commit):**
```bash
# Format code
ruff format .

# Lint and auto-fix
ruff check --fix .

# Type check
mypy scripts/

# Run tests
pytest
```

**Anti-Patterns to AVOID:**
- Silently catching exceptions: `except Exception: pass`
- Bare `except:` clauses without specific exception type
- Mutable default arguments: `def func(items=[]):`
- Using `print()` for logging in production (use structlog)
- Leaving TODO comments without GitHub issues
- Ignoring type hints or excessive `# type: ignore`

**Script File Structure:**
```python
"""Module docstring."""

# Imports (standard → third-party → local)

# Constants (UPPER_SNAKE_CASE)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Helper functions (_private_prefix)
def _validate_input(...) -> None:
    """Private helper."""
    ...

# Main public function
def main_function(...) -> ReturnType:
    """Public API with full docstring."""
    ...

# CLI entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(...)
    args = parser.parse_args()
    sys.exit(0 if success else 1)
```

---

## Usage Guidelines

**For AI Agents:**

- Read this file BEFORE implementing any code in this project
- Follow ALL rules exactly as documented (brownfield preservation, integration utilities, external service patterns)
- When in doubt, prefer the more restrictive/explicit option
- MANDATORY: Use `run_cli_script()` for subprocess, filesystem helpers for paths, rate limiters for external APIs
- NEVER modify files in `scripts/` directory (brownfield preservation boundary)
- Reference architecture document (`_bmad-output/planning-artifacts/architecture.md`) for additional context

**For Humans:**

- Keep this file lean and focused on unobvious details agents might miss
- Update when technology stack changes (new dependencies, version upgrades)
- Update when architectural patterns change (new utilities, integration requirements)
- Review quarterly for outdated rules (remove what becomes obvious)
- This file complements the architecture document (architecture = decisions, project-context = implementation rules)

**Last Updated:** 2026-01-10 (Architecture integration complete)
