# Project Structure & Boundaries

## Complete Project Directory Structure

```
ai-video-generator/
├── README.md
├── CLAUDE.md
├── pyproject.toml                    # uv package manager
├── alembic.ini                       # Database migration config
├── .env                              # Local development secrets (gitignored)
├── .env.example                      # Example environment variables
├── .gitignore
├── .github/
│   └── workflows/
│       └── pr-checks.yml            # CI/CD: tests, lint, type-check
│
├── scripts/                          # EXISTING: CLI automation scripts (DO NOT MODIFY)
│   ├── .env                         # API keys for scripts (gitignored)
│   ├── generate_asset.py            # Gemini image generation
│   ├── create_composite.py          # 16:9 composite creation
│   ├── create_split_screen.py       # Split-screen composites
│   ├── generate_video.py            # Kling video generation
│   ├── generate_audio.py            # ElevenLabs narration
│   ├── generate_sound_effects.py    # ElevenLabs SFX
│   └── assemble_video.py            # FFmpeg final assembly
│
├── orchestrator/                     # NEW: FastAPI webhook + queue orchestrator
│   ├── __init__.py
│   ├── main.py                      # FastAPI app entry point
│   ├── config.py                    # Pydantic Settings (DATABASE_URL, etc.)
│   ├── database.py                  # SQLAlchemy async engine, session factory
│   │
│   ├── api/                         # API route handlers
│   │   ├── __init__.py
│   │   ├── webhooks.py              # POST /webhook/notion (Notion events)
│   │   ├── tasks.py                 # GET/POST /tasks (task management)
│   │   ├── channels.py              # GET/POST /channels (channel config)
│   │   └── health.py                # GET /health, /ready (Railway healthchecks)
│   │
│   ├── models/                      # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── task.py                  # Tasks table (queue + status tracking)
│   │   ├── channel.py               # Channels table (multi-channel config)
│   │   ├── oauth_token.py           # OAuth tokens table (encrypted YouTube tokens)
│   │   └── video_clip.py            # Video clips table (tracking individual clips)
│   │
│   ├── schemas/                     # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── common.py                # SuccessResponse, ErrorResponse, PaginatedResponse
│   │   ├── task.py                  # TaskCreate, TaskUpdate, TaskResponse, TaskInDB
│   │   ├── channel.py               # ChannelCreate, ChannelUpdate, ChannelResponse
│   │   └── webhook.py               # NotionWebhookPayload
│   │
│   ├── services/                    # Business logic layer
│   │   ├── __init__.py
│   │   ├── task_service.py          # Task CRUD, claim_next_task(), round-robin
│   │   ├── channel_service.py       # Channel CRUD, channel isolation logic
│   │   ├── notion_service.py        # Notion API integration (status updates)
│   │   ├── oauth_service.py         # OAuth token refresh, YouTube auth
│   │   └── alert_service.py         # Slack webhook notifications
│   │
│   └── utils/                       # Shared utilities
│       ├── __init__.py
│       ├── logging.py               # structlog JSON configuration
│       ├── encryption.py            # Fernet encryption for OAuth tokens
│       ├── retry.py                 # Exponential backoff retry logic
│       └── exceptions.py            # Custom HTTP exceptions
│
├── workers/                          # NEW: Background task workers
│   ├── __init__.py
│   ├── main.py                      # Worker pool entry point (3 workers)
│   ├── base_worker.py               # BaseWorker class (queue polling, error handling)
│   ├── asset_worker.py              # SOP 03: Asset generation worker
│   ├── video_worker.py              # SOP 05: Video generation worker
│   ├── audio_worker.py              # SOP 06: Audio generation worker
│   ├── sfx_worker.py                # SOP 07: Sound effects worker
│   ├── assembly_worker.py           # SOP 08: Final assembly worker
│   ├── youtube_worker.py            # YouTube upload and metadata worker
│   │
│   └── utils/
│       ├── __init__.py
│       ├── cli_wrapper.py           # run_cli_script() - wrapper for scripts/
│       ├── notion_updater.py        # Fire-and-forget Notion status updates
│       └── storage_manager.py       # /workspaces/{channel_id}/{task_id}/ organization
│
├── migrations/                       # NEW: Alembic database migrations
│   ├── env.py                       # Alembic environment config
│   ├── script.py.mako               # Migration template
│   └── versions/
│       ├── 001_initial_schema.py    # Tasks, channels, oauth_tokens tables
│       ├── 002_add_video_clips.py   # Video clips tracking
│       └── 003_add_indexes.py       # Queue-optimized indexes
│
├── tests/                            # NEW: Test suite
│   ├── __init__.py
│   ├── conftest.py                  # Shared fixtures (db_session, test_client)
│   │
│   ├── orchestrator/
│   │   ├── api/
│   │   │   ├── test_webhooks.py     # Notion webhook endpoint tests
│   │   │   ├── test_tasks.py        # Task management endpoint tests
│   │   │   └── test_channels.py     # Channel management endpoint tests
│   │   ├── services/
│   │   │   ├── test_task_service.py # Task service logic tests
│   │   │   ├── test_notion_service.py
│   │   │   └── test_oauth_service.py
│   │   └── models/
│   │       └── test_task.py         # ORM model tests
│   │
│   ├── workers/
│   │   ├── test_asset_worker.py     # Asset worker tests
│   │   ├── test_video_worker.py     # Video worker tests
│   │   └── utils/
│   │       ├── test_cli_wrapper.py  # CLI wrapper tests
│   │       └── test_notion_updater.py
│   │
│   └── integration/
│       ├── test_end_to_end.py       # Full pipeline tests
│       ├── test_notion_to_youtube.py # Notion → YouTube flow
│       └── test_queue_processing.py  # Queue claim and processing
│
├── docs/                             # EXISTING: Documentation (preserve)
│   ├── architecture.md              # Legacy architecture (keep for reference)
│   ├── architecture-patterns.md
│   ├── technology-stack.md
│   ├── api-design.md
│   ├── data-architecture.md
│   ├── deployment.md
│   ├── development-workflow.md
│   ├── error-handling.md
│   ├── performance.md
│   ├── security.md
│   └── testing-strategy.md
│
├── prompts/                          # EXISTING: Agent SOPs (preserve)
│   ├── 1_research.md                # SOP 01: Species research
│   ├── 2_story_generator.md         # SOP 02: Story development
│   ├── 3.5_generate_assets_agent.md # SOP 03: Asset generation
│   ├── 4_video_prompt_engineering.md
│   ├── 4.5_generate_videos_agent.md # SOP 05: Video generation
│   ├── 5.5_generate_audio_agent.md  # SOP 06: Audio generation
│   ├── 6.5_generate_sound_effects_agent.md # SOP 07: SFX
│   └── 7_assemble_final_agent.md    # SOP 08: Final assembly
│
├── _bmad/                            # EXISTING: BMAD framework (preserve)
│   └── bmm/
│       ├── config.yaml
│       └── workflows/
│
└── _bmad-output/                     # EXISTING: Generated artifacts (preserve)
    ├── architecture.md              # THIS FILE (being updated)
    ├── planning-artifacts/
    │   ├── prd.md
    │   └── research/
    └── implementation-artifacts/
```

---

## Architectural Boundaries

### API Boundaries

**Public API (Notion Webhooks):**
- Endpoint: `POST /webhook/notion`
- Purpose: Receives Notion database change events
- Authentication: HMAC signature validation
- Rate Limit: No rate limiting (Notion sends at their rate)
- Response: `202 Accepted` (asynchronous processing)

**Internal API (Management):**
- Endpoints: `GET/POST /tasks`, `GET/POST /channels`
- Purpose: Manual task management, channel configuration
- Access: Internal only (Railway dashboard, admin scripts)
- Authentication: None (internal system)
- Rate Limit: No limit (low volume)

**Health Checks:**
- Endpoints: `GET /health`, `GET /ready`
- Purpose: Railway platform healthchecks
- Response: `200 OK` if database connection active

**Authentication Model:**
- No user-facing authentication
- Webhook signature validation only
- OAuth tokens stored encrypted in database
- API keys managed via Railway secrets

---

### Component Boundaries

**Orchestrator ↔ Database:**
- Connection: SQLAlchemy async engine (`AsyncEngine`)
- Session Management: Dependency injection in FastAPI routes
- Transaction Model: Short transactions (Decision 3)
- ORM Models: `orchestrator/models/*.py`

**Workers ↔ Database:**
- Connection: Direct async connections via `AsyncSessionLocal`
- Session Management: Context managers (`async with db:`)
- Transaction Model: Short transactions around status updates
- Queue Operations: `FOR UPDATE SKIP LOCKED` for atomic task claims

**Workers ↔ CLI Scripts:**
- Interface: `workers/utils/cli_wrapper.py`
- Communication: Subprocess calls with complete arguments
- Error Handling: Exit codes (0=success, 1=failure)
- Timeout: Configurable per script (120s assets, 600s videos)
- Working Directory: `scripts/` for `.env` access

**Workers ↔ Notion:**
- Interface: `workers/utils/notion_updater.py`
- Pattern: Fire-and-forget with retry logic
- Rate Limit: 3 req/sec enforced in `notion_service.py`
- Error Handling: Exponential backoff (1min → 2min → 4min → 1hr)

**Workers ↔ External APIs:**
- Gemini: Via `scripts/generate_asset.py` (unchanged)
- Kling: Via `scripts/generate_video.py` (unchanged)
- ElevenLabs: Via `scripts/generate_audio.py`, `scripts/generate_sound_effects.py` (unchanged)
- YouTube: Direct API calls in `workers/youtube_worker.py`

---

### Service Boundaries

**Queue Management:**
- Technology: PostgreSQL table as queue + PgQueuer for LISTEN/NOTIFY
- Worker Pool: 3 fixed workers polling queue
- Task Claim: Atomic via `FOR UPDATE SKIP LOCKED`
- Channel Selection: Round-robin fair scheduling
- Wake-up: LISTEN/NOTIFY triggers instant worker response

**Status Synchronization:**
- Pattern: Fire-and-forget (non-blocking)
- Retry: Mandatory exponential backoff (Decision 9)
- Failure Handling: Logged, retried, but workers never blocked
- Consistency: Eventually consistent with Notion

**OAuth Management:**
- Storage: PostgreSQL `oauth_tokens` table (Fernet encrypted)
- Refresh: Orchestrator background job (every 50 minutes)
- Access: Workers read current tokens from database
- Expiration: Automatic refresh before 60-minute expiration

**File Storage:**
- Location: `/workspaces/{channel_id}/{task_id}/` on Railway volumes
- Isolation: Separate directories per task
- Cleanup: After YouTube upload, workers delete task directory
- Persistence: YouTube URLs stored in Notion, not local files

---

### Data Boundaries

**Channel Isolation:**
- Pattern: Denormalized `channel_id` on every table
- Enforcement: Workers filter queries by `channel_id`
- Failures: Do not cross channel boundaries
- Queues: Per-channel queues for fair scheduling

**Task Ownership:**
- Claim: Atomic via `FOR UPDATE SKIP LOCKED`
- Ownership: One worker owns task until completion/failure
- Status: Single source of truth in `tasks.status` column
- Concurrency: Multiple tasks per channel can process in parallel

**Asset Isolation:**
- Filesystem: Separate directory per task
- No Sharing: Workers never share files between tasks
- Cleanup: Automatic after final stage (YouTube upload)
- Notion: Asset URLs stored for reference

**Encrypted Secrets:**
- OAuth Tokens: Fernet symmetric encryption in database
- API Keys: Railway environment variables (never in code)
- Webhook Secrets: Environment variables for signature validation
- Encryption Key: Railway secret (`ENCRYPTION_KEY`)

---

## Requirements to Structure Mapping

### Feature/Epic Mapping

**Content Planning & Management (FR1-FR7)**
- **Models**: `orchestrator/models/task.py` (tasks table with 26 statuses)
- **Services**: `orchestrator/services/task_service.py` (CRUD, review gates)
- **API**: `orchestrator/api/tasks.py` (GET /tasks, POST /tasks, POST /tasks/{id}/retry)
- **Database**: `migrations/versions/001_initial_schema.py`
- **Tests**: `tests/orchestrator/services/test_task_service.py`, `tests/orchestrator/api/test_tasks.py`

**Multi-Channel Orchestration (FR8-FR16)**
- **Models**: `orchestrator/models/channel.py` (channels table)
- **Services**: `orchestrator/services/channel_service.py` (isolation logic, round-robin)
- **Workers**: `workers/base_worker.py` (round-robin scheduling algorithm)
- **Database**: `migrations/versions/001_initial_schema.py` (channels table), SQL function `get_next_channel_for_processing()`
- **Tests**: `tests/integration/test_queue_processing.py` (round-robin fairness tests)

**Video Generation Pipeline (FR17-FR26)**
- **Workers**:
  - `workers/asset_worker.py` (SOP 03: Asset generation)
  - `workers/video_worker.py` (SOP 05: Video generation)
  - `workers/audio_worker.py` (SOP 06: Audio generation)
  - `workers/sfx_worker.py` (SOP 07: Sound effects)
  - `workers/assembly_worker.py` (SOP 08: Final assembly)
- **CLI Wrapper**: `workers/utils/cli_wrapper.py` (subprocess management)
- **Existing Scripts**: `scripts/generate_asset.py`, `scripts/generate_video.py`, etc. (PRESERVED)
- **Tests**: `tests/workers/test_asset_worker.py`, `tests/integration/test_end_to_end.py`

**Error Handling & Recovery (FR27-FR35)**
- **Utilities**: `orchestrator/utils/retry.py` (exponential backoff with jitter)
- **Models**: `orchestrator/models/task.py` (retry_count, next_retry_at columns)
- **Workers**: `workers/base_worker.py` (failure detection, retry scheduling)
- **Logging**: `orchestrator/utils/logging.py` (structlog JSON)
- **Alerts**: `orchestrator/services/alert_service.py` (Slack webhooks)
- **Tests**: `tests/workers/utils/test_cli_wrapper.py` (retry logic tests)

**Queue & Task Management (FR36-FR43)**
- **Webhooks**: `orchestrator/api/webhooks.py` (POST /webhook/notion)
- **Database**: `migrations/versions/001_initial_schema.py` (tasks queue table, partial indexes)
- **Functions**: SQL functions `claim_task(channel_id)`, `get_next_channel_for_processing()`
- **Workers**: `workers/main.py` (worker pool manager), `workers/base_worker.py` (queue polling loop)
- **PgQueuer**: LISTEN/NOTIFY integration for instant wake-up
- **Tests**: `tests/integration/test_queue_processing.py`

**Asset & Storage Management (FR44-FR50)**
- **Storage**: `/workspaces/{channel_id}/{task_id}/` (Railway persistent volumes)
- **Utilities**: `workers/utils/storage_manager.py` (directory creation, cleanup)
- **Notion**: `orchestrator/services/notion_service.py` (asset URL population)
- **Workers**: Cleanup logic in `workers/youtube_worker.py` after successful upload
- **Tests**: `tests/workers/utils/test_storage_manager.py`

**Status & Progress Monitoring (FR51-FR59)**
- **Models**: `orchestrator/models/task.py` (26 workflow statuses with review gates)
- **Services**: `orchestrator/services/notion_service.py` (real-time status updates)
- **Workers**: `workers/utils/notion_updater.py` (fire-and-forget with retry)
- **API**: `orchestrator/api/tasks.py` (GET /tasks?status=queued&channel_id=abc)
- **Tests**: `tests/orchestrator/services/test_notion_service.py`

**YouTube Integration (FR60-FR67)**
- **Models**: `orchestrator/models/oauth_token.py` (encrypted token storage)
- **Services**: `orchestrator/services/oauth_service.py` (token refresh, OAuth flow)
- **Workers**: `workers/youtube_worker.py` (video upload, metadata, URL retrieval)
- **Encryption**: `orchestrator/utils/encryption.py` (Fernet symmetric encryption)
- **Tests**: `tests/orchestrator/services/test_oauth_service.py`, `tests/workers/test_youtube_worker.py`

---

### Cross-Cutting Concerns

**Authentication & Security**
- **OAuth Encryption**: `orchestrator/utils/encryption.py` (Fernet)
- **Webhook Validation**: `orchestrator/api/webhooks.py` (HMAC signature middleware)
- **API Keys**: Railway environment variables → `orchestrator/config.py` (Pydantic Settings)
- **Tests**: `tests/orchestrator/api/test_webhooks.py` (signature validation tests)

**Logging & Monitoring**
- **Structured Logging**: `orchestrator/utils/logging.py` (structlog with JSONRenderer)
- **Context Binding**: All workers bind task_id, channel_id to log context
- **Event Naming**: `{component}_{action}_{status}` convention
- **Slack Alerts**: `orchestrator/services/alert_service.py` (critical errors only)

**Error Handling**
- **Custom Exceptions**: `orchestrator/utils/exceptions.py` (TaskNotFoundException, etc.)
- **Retry Logic**: `orchestrator/utils/retry.py` (exponential backoff with jitter)
- **Worker Base Class**: `workers/base_worker.py` (failure detection, retry scheduling)
- **Tests**: `tests/integration/test_error_recovery.py`

**Database Migrations**
- **Tool**: Alembic (manual migrations for zero-downtime)
- **Location**: `migrations/versions/*.py`
- **Naming**: `{version}_{description}.py` (001_initial_schema.py)
- **Workflow**: Create migration → Review SQL → Test locally → Deploy to Railway

---

## Integration Points

### Internal Communication

**Orchestrator → Workers (Asynchronous Queue)**
- **Mechanism**: PostgreSQL `tasks` table + PgQueuer LISTEN/NOTIFY
- **Flow**:
  1. Orchestrator creates task with `status='queued'`
  2. PostgreSQL trigger sends NOTIFY event
  3. Workers wake up instantly (no polling delay)
  4. Worker claims task via `FOR UPDATE SKIP LOCKED`
- **Decoupling**: Orchestrator never calls workers directly

**Workers → Database (Direct Access)**
- **Connection**: Each worker maintains own async connection pool
- **Session Management**: Context managers (`async with AsyncSessionLocal() as db:`)
- **Transactions**: Short transactions (claim → process → update)
- **Isolation**: Workers never block each other (optimistic locking)

**Workers → CLI Scripts (Subprocess)**
- **Interface**: `workers/utils/cli_wrapper.py`
- **Arguments**: Complete arguments passed (no file reading in scripts)
- **Environment**: Scripts run in `scripts/` directory for `.env` access
- **Timeout**: Configurable per script (120s Gemini, 600s Kling)
- **Error Handling**: Exit code 0 (success) or 1 (failure)

**Services → Services (Direct Imports)**
- **Within Orchestrator**: Direct Python imports, dependency injection
- **Pattern**: `task_service.py` calls `notion_service.py` directly
- **No RPC**: All services in same process (FastAPI app)

---

### External Integrations

**Notion API**
- **Inbound (Webhooks)**:
  - Endpoint: `POST /webhook/notion`
  - Validation: HMAC signature validation
  - Payload: `orchestrator/schemas/webhook.py` (NotionWebhookPayload)
  - Processing: Create task in queue, return `202 Accepted`

- **Outbound (Status Updates)**:
  - Service: `orchestrator/services/notion_service.py`
  - Pattern: Fire-and-forget via `workers/utils/notion_updater.py`
  - Rate Limit: 3 req/sec enforced
  - Retry: Exponential backoff (1min → 2min → 4min → 1hr)

**Google Gemini 2.5 Flash (Image Generation)**
- **Interface**: `scripts/generate_asset.py` (EXISTING, UNCHANGED)
- **Caller**: `workers/asset_worker.py` via `cli_wrapper.py`
- **API Key**: `scripts/.env` (GEMINI_API_KEY)
- **Timeout**: 120 seconds per image
- **Concurrency**: 12 parallel requests (Gemini rate limit)

**Kling 2.5 Pro via KIE.ai (Video Generation)**
- **Interface**: `scripts/generate_video.py` (EXISTING, UNCHANGED)
- **Caller**: `workers/video_worker.py` via `cli_wrapper.py`
- **API Key**: `scripts/.env` (KIE_API_KEY)
- **Timeout**: 600 seconds (10 minutes for Kling processing)
- **Concurrency**: 5-8 parallel requests

**ElevenLabs v3 (Audio & SFX)**
- **Interface**:
  - `scripts/generate_audio.py` (narration)
  - `scripts/generate_sound_effects.py` (SFX)
- **Callers**: `workers/audio_worker.py`, `workers/sfx_worker.py` via `cli_wrapper.py`
- **API Key**: `scripts/.env` (ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID)
- **Concurrency**: 6 parallel requests

**YouTube Data API (Upload & Metadata)**
- **Interface**: `workers/youtube_worker.py` (direct API integration)
- **Authentication**: OAuth 2.0 tokens from `oauth_tokens` table (encrypted)
- **Token Refresh**: `orchestrator/services/oauth_service.py` (background job every 50 min)
- **Quota**: 10,000 units/day (monitored, no enforcement)
- **Upload**: Resumable upload protocol for large videos

**Slack (Alerts)**
- **Interface**: `orchestrator/services/alert_service.py`
- **Webhook URL**: Railway environment variable
- **Trigger**: Critical errors (4 retries exhausted, system failures)
- **Payload**: JSON with emoji, level, message

**catbox.moe (Free Image Hosting)**
- **Purpose**: Host composite images for Kling API (requires public URL)
- **Interface**: HTTP POST to `https://catbox.moe/user/api.php`
- **Caller**: `workers/video_worker.py` before calling Kling
- **No Auth**: Free public service

---

### Data Flow

**End-to-End Flow: Notion → YouTube**

```
1. Notion Database Change (user creates entry)
       ↓
2. Notion sends webhook → POST /webhook/notion
       ↓
3. Orchestrator validates HMAC signature
       ↓
4. Create Task (channel_id, status='queued', priority=0)
       ↓
5. PostgreSQL NOTIFY event fired
       ↓
6. Worker wakes up instantly (LISTEN)
       ↓
7. Worker calls claim_task(channel_id)
       ↓  (FOR UPDATE SKIP LOCKED - atomic)
8. Task claimed (status='processing')
       ↓
9. Asset Worker:
   - Reads task.global_atmosphere + task.asset_prompts
   - Calls run_cli_script("generate_asset.py", ...)
   - Waits for completion (120s timeout)
   - Updates status='assets_ready'
   - Fire-and-forget Notion update (with retry)
       ↓
10. Video Worker claims task (status='video_generation')
    - Uploads composite to catbox.moe
    - Calls run_cli_script("generate_video.py", ...)
    - Waits for Kling processing (600s timeout)
    - Updates status='video_ready'
    - Fire-and-forget Notion update
       ↓
11. Audio Worker claims task (status='audio_generation')
    - Calls run_cli_script("generate_audio.py", ...)
    - Updates status='audio_ready'
    - Fire-and-forget Notion update
       ↓
12. SFX Worker claims task (status='sfx_generation')
    - Calls run_cli_script("generate_sound_effects.py", ...)
    - Updates status='sfx_ready'
    - Fire-and-forget Notion update
       ↓
13. Assembly Worker claims task (status='assembly')
    - Calls run_cli_script("assemble_video.py", ...)
    - FFmpeg combines videos, audio, SFX
    - Updates status='assembled'
    - Fire-and-forget Notion update
       ↓
14. YouTube Worker claims task (status='youtube_upload')
    - Reads OAuth token (decrypted)
    - Uploads video via YouTube Data API
    - Retrieves youtube_url
    - Updates status='published', youtube_url
    - Fire-and-forget Notion update (with URL)
    - Cleanup: Delete /workspaces/{channel_id}/{task_id}/
       ↓
15. Pipeline Complete (status='published')
```

**Error Recovery Flow:**

```
Worker processing fails (script exit code 1)
       ↓
Worker catches exception
       ↓
Update task:
  - status='failed'
  - retry_count += 1
  - next_retry_at = NOW() + exponential_backoff
       ↓
If retry_count < 4:
  - Task returns to queue when next_retry_at reached
  - Retry with same worker type
Else:
  - Status remains 'failed'
  - Slack alert sent
  - Manual intervention required
```

---

## File Organization Patterns

### Configuration Files

**Root Level:**
- `pyproject.toml`: Python dependencies (uv package manager)
- `alembic.ini`: Database migration configuration
- `.env`: Local development secrets (gitignored)
- `.env.example`: Template for required environment variables
- `.gitignore`: Exclude `.env`, `__pycache__`, `.pytest_cache`

**Orchestrator Configuration:**
- `orchestrator/config.py`: Pydantic Settings
  ```python
  class Settings(BaseSettings):
      DATABASE_URL: str
      NOTION_API_KEY: str
      SLACK_WEBHOOK_URL: str
      ENCRYPTION_KEY: str
  ```

**Scripts Configuration:**
- `scripts/.env`: API keys for existing scripts (gitignored)
  ```bash
  GEMINI_API_KEY=...
  KIE_API_KEY=...
  ELEVENLABS_API_KEY=...
  ELEVENLABS_VOICE_ID=...
  ```

**CI/CD Configuration:**
- `.github/workflows/pr-checks.yml`: GitHub Actions
  - Run tests on PR
  - Type checking (mypy)
  - Linting (ruff)
  - Railway auto-deploy on merge to main

---

### Source Organization

**Feature-Based Structure:**
- `orchestrator/`: FastAPI web app (webhooks, API, orchestration)
- `workers/`: Background task processors (asset, video, audio, assembly, YouTube)
- `scripts/`: Atomic CLI tools (EXISTING, PRESERVED)
- `migrations/`: Database schema versions

**Layered Within Features:**
- `orchestrator/api/`: HTTP route handlers
- `orchestrator/services/`: Business logic (no HTTP awareness)
- `orchestrator/models/`: SQLAlchemy ORM models
- `orchestrator/schemas/`: Pydantic request/response schemas
- `orchestrator/utils/`: Shared utilities

**Utilities Location:**
- `orchestrator/utils/`: Shared by orchestrator and workers
- `workers/utils/`: Worker-specific utilities (CLI wrapper, storage)

**Flat Structure:**
- Maximum 3 levels of nesting
- No deep hierarchies
- Group related files in same directory

---

### Test Organization

**Mirror Production Structure:**
- `tests/orchestrator/`: Mirrors `orchestrator/` structure
- `tests/workers/`: Mirrors `workers/` structure
- `tests/integration/`: End-to-end cross-component tests

**Test Files:**
- Naming: `test_{module}.py`
- Example: `test_task_service.py` tests `task_service.py`

**Test Functions:**
- Naming: `test_{function}_{scenario}`
- Examples:
  - `test_get_task_by_id_success()`
  - `test_get_task_by_id_not_found()`
  - `test_claim_next_task_round_robin()`

**Shared Fixtures:**
- `tests/conftest.py`: Global fixtures
  ```python
  @pytest.fixture
  async def db_session():
      # Provide test database session
      pass

  @pytest.fixture
  def test_client():
      # Provide FastAPI test client
      pass
  ```

**Test Coverage:**
- Unit: `tests/orchestrator/services/`, `tests/workers/`
- Integration: `tests/integration/`
- Target: 80%+ coverage on services and workers

---

### Asset Organization

**Development Storage:**
- Location: `/workspaces/{channel_id}/{task_id}/` on Railway volumes
- Subdirectories:
  - `assets/`: Generated images (characters, environments)
  - `composites/`: 16:9 composite images for Kling
  - `videos/`: Generated video clips
  - `audio/`: Narration MP3s
  - `sfx/`: Sound effect WAVs

**Cleanup Strategy:**
- After YouTube upload: Delete entire `/workspaces/{channel_id}/{task_id}/` directory
- Notion stores final YouTube URL for reference
- No local file persistence (saves Railway volume space)

**Asset URLs in Notion:**
- Populated by `orchestrator/services/notion_service.py`
- YouTube URL stored in task.youtube_url column
- Notion database updated via fire-and-forget API calls

---

## Development Workflow Integration

### Development Server Structure

**Local Development:**
```bash
# Terminal 1: Start orchestrator
uvicorn orchestrator.main:app --reload --port 8000

# Terminal 2: Start workers
python workers/main.py

# Terminal 3: PostgreSQL (local or Railway tunnel)
railway run psql
```

**Environment Setup:**
```bash
# Install dependencies
uv sync

# Apply migrations
alembic upgrade head

# Run tests
pytest tests/ -v --cov=orchestrator --cov=workers
```

---

### Build Process Structure

**No Build Step:**
- Pure Python project (no compilation)
- No transpilation, bundling, or asset processing

**Development Tools:**
```bash
# Type checking
mypy orchestrator/ workers/

# Linting
ruff check orchestrator/ workers/

# Testing
pytest tests/ -v --cov=orchestrator --cov=workers --cov-report=html

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
```

**Dependencies:**
```toml
# pyproject.toml
[dependencies]
fastapi = ">=0.104.0"
sqlalchemy = ">=2.0.0"
asyncpg = ">=0.29.0"
pydantic = ">=2.8.0"
pydantic-settings = ">=2.0.0"
alembic = ">=1.12.0"
structlog = ">=23.2.0"
cryptography = ">=41.0.0"  # Fernet encryption
httpx = ">=0.25.0"
pgqueuer = ">=0.10.0"

[dev-dependencies]
pytest = ">=7.4.0"
pytest-asyncio = ">=0.21.0"
pytest-cov = ">=4.1.0"
mypy = ">=1.7.0"
ruff = ">=0.1.0"
```

---

### Deployment Structure

**Platform: Railway Hobby ($5/month)**

**Services:**
1. **orchestrator** (FastAPI web app)
   - Auto-scaled based on traffic
   - Exposed on public URL for Notion webhooks
   - Environment: Railway secrets (API keys, DATABASE_URL)

2. **workers** (Background processors)
   - Fixed 3 worker processes
   - No public exposure
   - Same environment as orchestrator

3. **postgres** (Managed PostgreSQL)
   - Provided by Railway
   - Automatic backups
   - Connection pooling

**Volumes:**
- `/workspaces/`: Persistent volume for asset storage (Railway)
- Mounted on both orchestrator and workers

**Environment Variables (Railway Secrets):**
```bash
DATABASE_URL=postgresql+asyncpg://...
NOTION_API_KEY=...
SLACK_WEBHOOK_URL=...
ENCRYPTION_KEY=...
# scripts/.env variables also in Railway
GEMINI_API_KEY=...
KIE_API_KEY=...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
```

**CI/CD Pipeline:**
```yaml
# .github/workflows/pr-checks.yml
on:
  pull_request:
    branches: [main]

jobs:
  test:
    - pytest tests/

  type-check:
    - mypy orchestrator/ workers/

  lint:
    - ruff check orchestrator/ workers/

# Railway auto-deploys on merge to main
```

**Deployment Flow:**
1. Create PR
2. GitHub Actions run tests, lint, type-check
3. Code review
4. Merge to main
5. Railway auto-deploys orchestrator + workers
6. Alembic migrations run automatically (Railway release command)
7. Health checks confirm deployment

---
