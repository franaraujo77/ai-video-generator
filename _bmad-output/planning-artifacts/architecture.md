---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
workflowType: 'architecture'
status: 'complete'
completedAt: '2026-01-10'
inputDocuments:
  - "_bmad-output/planning-artifacts/prd.md"
  - "_bmad-output/planning-artifacts/ux-design-specification.md"
  - "_bmad-output/project-context.md"
  - "_bmad-output/planning-artifacts/research/technical-notion-api-integration-research-2026-01-08.md"
  - "_bmad-output/planning-artifacts/research/technical-ai-service-pricing-limits-alternatives-research-2026-01-08.md"
  - "_bmad-output/planning-artifacts/research/market-ai-video-generation-industry-costs-roi-research-2026-01-09.md"
  - "_bmad-output/planning-artifacts/research/domain-youtube-automation-multi-channel-compliance-research-2026-01-09.md"
  - "docs/architecture.md"
  - "docs/architecture-patterns.md"
  - "docs/technology-stack.md"
  - "docs/index.md"
project_name: 'ai-video-generator'
user_name: 'Francis'
date: '2026-01-10'
---

# Architecture Decision Document - ai-video-generator

**Project:** ai-video-generator
**Author:** Francis
**Date:** 2026-01-10

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

---

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**

The project encompasses **67 functional requirements** organized across five major capability domains:

1. **Multi-Channel Management (FR-MCM)**: Channel configuration via YAML, independent video schedules, per-channel API credentials, cross-channel isolation, and scalability to 10+ channels.

2. **Notion Integration (FR-NOT)**: Bidirectional sync with Notion databases, 26-column pipeline visualization, task creation/updates, status polling, and handling Notion API rate limits (3 req/sec).

3. **Video Generation Orchestration (FR-VGO)**: Queue-based task management using PgQueuer, 3-worker concurrent execution, preserving existing CLI scripts as workers, state persistence in PostgreSQL, retry logic, and partial pipeline resumption.

4. **YouTube API Compliance (FR-YTC)**: Human review gates at strategic points, review evidence storage, quota management across channels, July 2025 policy compliance (human-in-the-loop), upload scheduling, and API quota alerts.

5. **Monitoring & Observability (FR-MON)**: Structured logging, cost tracking per video/channel, error alerting, video generation metrics, task duration tracking, and Railway dashboard integration.

**Architecturally significant patterns:**
- **Brownfield transformation**: Must integrate with 7 existing CLI scripts (`generate_asset.py`, `create_composite.py`, `generate_video.py`, etc.) without modification
- **Preservation requirement**: "Smart Agent + Dumb Scripts" pattern must remain (orchestrator reads files/combines prompts, scripts execute single API calls)
- **State transition**: Filesystem-based → Database-backed (PostgreSQL) while maintaining CLI script interfaces
- **Concurrency model**: Single-project sequential → Multi-channel parallel (3 workers, queue-based)

**Non-Functional Requirements:**

1. **Performance**:
   - Target: 100 videos/week across 5-10 channels (14.3 videos/day average)
   - 3 concurrent workers for parallel channel processing
   - Async I/O throughout FastAPI backend (SQLAlchemy async engine, asyncpg driver)
   - PgQueuer LISTEN/NOTIFY for sub-second task claiming

2. **Compliance & Regulatory**:
   - **YouTube Partner Program (July 2025)**: Human review required before upload to demonstrate non-automated content
   - Evidence storage for review actions (reviewer ID, timestamp, notes)
   - Content authenticity metadata
   - 95% autonomous operation (5% human intervention at review gates)

3. **Cost Optimization**:
   - Maintain $6-13 per video cost despite orchestration overhead
   - API quota management (YouTube: 10,000 units/day default, 1,600 per upload)
   - Multi-channel quota allocation and optimization
   - Cost tracking per video/channel for budget monitoring

4. **Reliability & Availability**:
   - Railway deployment (managed PostgreSQL, horizontal scaling support)
   - Graceful degradation when external APIs fail
   - Retry logic with exponential backoff
   - Partial pipeline resumption (recover from failures mid-pipeline)
   - Short transaction patterns (never hold DB connections during CLI script execution)

5. **Usability**:
   - Monitoring-first UX (not management-heavy)
   - Glanceable status via Notion Board View (26 columns)
   - Minimal setup friction (YAML config files, OAuth CLI tools)
   - "Card stuck = problem, moving = success" design principle

**Scale & Complexity:**

- **Primary domain**: Backend-heavy Full-Stack (FastAPI orchestrator + PostgreSQL + Notion integration + CLI worker orchestration + Railway deployment)
- **Complexity level**: **HIGH**
  - Distributed system characteristics (async workers, queue-based coordination)
  - External system integration (Notion, YouTube, Gemini, Kling, ElevenLabs)
  - Regulatory compliance requirements (YouTube policy enforcement)
  - Multi-tenant-like behavior (channel isolation, per-channel resources)
  - Long-running processes (video generation: 2-5 min per clip, 18 clips per video)
- **Estimated architectural components**: 12-15 major components
  - FastAPI backend (routes, dependencies, auth)
  - PostgreSQL schema (channels, tasks, videos, reviews, costs)
  - PgQueuer integration (task claiming, queue management)
  - 7 existing CLI scripts (preserved as workers)
  - Notion API client (bidirectional sync)
  - YouTube API client (uploads, quota management)
  - Human review gate service
  - Cost tracking service
  - Observability/logging infrastructure
  - Configuration management (YAML parsing, validation)
  - Worker orchestration layer
  - Error recovery & retry logic

### Technical Constraints & Dependencies

**Technology Stack (from project-context.md):**
- Python ≥3.10 (async/await required)
- Package manager: `uv` (NOT pip)
- Web framework: FastAPI ≥0.104.0
- Database: PostgreSQL 12+ (Railway managed, async driver required)
- ORM: SQLAlchemy ≥2.0.0 (MUST use async engine + AsyncSession)
- Database driver: `asyncpg` ≥0.29.0 (NOT psycopg2)
- Queue: PgQueuer ≥0.10.0 (PostgreSQL-based queue with LISTEN/NOTIFY)
- FFmpeg: 8.0.1+ (video processing, must be in PATH)

**Critical Transaction Pattern Constraint:**
```python
# MANDATORY: Short transactions only
# ❌ WRONG: Hold transaction during CLI script execution
async with session.begin():
    task = await claim_task()
    subprocess.run(["python", "generate_video.py", ...])  # BLOCKS DB!
    await task.mark_complete()

# ✅ CORRECT: Claim → close → process → reopen → update
async with session.begin():
    task = await claim_task()  # Fast DB operation

# DB connection closed here
subprocess.run(["python", "generate_video.py", ...])  # Long-running

async with session.begin():
    await task.mark_complete()  # Fast DB operation
```

**External API Rate Limits:**
- Notion API: 3 requests/second
- YouTube API: 10,000 units/day default (requires quota increase for multi-channel)
- Kling AI: 2-5 minutes per 10-second video clip generation
- ElevenLabs: Character-based pricing, no published rate limit

**Brownfield Integration Requirements:**
- 7 existing CLI scripts must remain unchanged (1,599 LOC total)
- Scripts expect filesystem-based inputs (project directories, file paths)
- Scripts are stateless (no DB connections, no queue awareness)
- Orchestrator must adapt to CLI interfaces, not vice versa

**Deployment Constraints:**
- Railway platform (managed PostgreSQL, environment variables, log streaming)
- Horizontal scaling support for workers (stateless worker design)
- OAuth setup must work in Railway environment

### Cross-Cutting Concerns Identified

**1. Async Transaction Management:**
- All database operations must use async patterns (async engine, AsyncSession)
- Never hold transactions during I/O-bound operations (API calls, CLI scripts, file operations)
- Pattern: claim task → close DB → execute work → reopen DB → update task

**2. Queue-Based Workflow Orchestration:**
- PgQueuer manages task lifecycle (pending → claimed → processing → completed/failed)
- PostgreSQL LISTEN/NOTIFY for real-time worker coordination
- FOR UPDATE SKIP LOCKED for concurrent task claiming
- Fairness across channels (prevent single channel from monopolizing workers)

**3. API Rate Limiting & Quota Management:**
- YouTube quota allocation across channels (prevent single channel exhaustion)
- Notion API rate limit compliance (3 req/sec, implement backoff)
- AI service rate limiting (Gemini, Kling, ElevenLabs)
- Quota alert system (warn before hitting limits)

**4. Error Recovery & Retry Logic:**
- Exponential backoff for transient failures
- Partial pipeline resumption (recover mid-pipeline, not just at start)
- Distinguish retriable errors (network timeout) vs non-retriable (invalid API key)
- Dead letter queue for permanently failed tasks

**5. Human Review Gate Integration:**
- Strategic insertion points (post-video generation, pre-YouTube upload)
- Review evidence capture (who reviewed, when, decision, notes)
- Review UI integration (Notion properties, future custom UI)
- 95% autonomous flow (only 5% should hit review gates in normal operation)

**6. Multi-Channel Resource Allocation:**
- Channel isolation (one channel's failure doesn't affect others)
- Fair worker distribution (round-robin or weighted by channel priority)
- Per-channel API credentials (YouTube, Notion workspace)
- Per-channel cost tracking and budget limits

**7. Cost Tracking & Optimization:**
- Per-video cost breakdown (assets: $0.50-2.00, video: $5-10, audio: $0.50-1.00)
- Per-channel aggregated costs (daily, weekly, monthly)
- Budget alerts (warn when approaching limits)
- Cost optimization opportunities (batch operations, caching)

**8. Observability & Monitoring:**
- Structured logging (JSON format, correlation IDs across pipeline stages)
- Metrics collection (task duration, success rate, API usage, costs)
- Railway log integration (stdout/stderr captured automatically)
- Notion Board View as primary monitoring interface (26-column pipeline viz)
- Error alerting (Discord, Slack, or email for critical failures)

**9. Configuration Management:**
- YAML-based channel configuration (channel_configs/{channel_id}.yaml)
- Environment variable management (secrets, API keys)
- Configuration validation on startup (prevent runtime config errors)
- Hot reload support for channel config changes (optional, nice-to-have)

**10. Compliance Evidence Trail:**
- Audit log for all human interactions (reviews, approvals, manual interventions)
- YouTube upload metadata (evidence of human involvement)
- Retention policy for review evidence (regulatory requirement)
- Queryable compliance reports (for YouTube Partner Program audits)

---

## Starter Template Evaluation

### Primary Technology Domain

**Backend-heavy Full-Stack** (FastAPI orchestrator + PostgreSQL + Notion integration + CLI worker orchestration + Railway deployment)

### Brownfield Transformation Context

This project is a **brownfield transformation**, not a greenfield project. Existing infrastructure:
- 7 working CLI scripts (1,599 LOC total)
- Established "Smart Agent + Dumb Scripts" pattern
- Filesystem-based pipeline architecture (8-step production workflow)
- Proven video generation pipeline with 4 complete example projects

**Traditional starter templates do not apply** because:
1. We're adding orchestration around existing tools, not creating new tools
2. CLI scripts must remain unchanged (no DB connections, no queue awareness)
3. Existing patterns must be preserved ("Smart Agent + Dumb Scripts")
4. Project structure already established with working examples

### Starter Options Considered

**Option A: Manual Foundation (Selected)**
- Explicitly document all architectural decisions for orchestration layer
- Build FastAPI backend, PostgreSQL schema, and worker architecture incrementally
- Full control over integration with existing CLI scripts
- Preserve existing patterns without starter template constraints

**Option B: FastAPI Starter as Reference (Rejected)**
- Would require research into FastAPI + SQLAlchemy + Async starters
- Significant customization needed for brownfield integration
- Risk of conflicting with existing project structure
- Unnecessary overhead for expert-level implementation

### Selected Approach: Manual Foundation

**Rationale for Selection:**

1. **Brownfield Requirements**: Existing CLI scripts and patterns must be preserved unchanged. Starters are designed for greenfield projects and would require extensive modification or removal of generated code.

2. **Expert-Level Implementation**: User has expert skill level and comprehensive technical preferences already documented. Manual architecture provides full control without starter template constraints.

3. **Unique Integration Challenges**: The orchestration layer must adapt to filesystem-based CLI interfaces. Standard starters assume database-first architectures incompatible with stateless CLI scripts.

4. **Precision Over Convention**: YouTube compliance, API quota management, and async transaction patterns require precise architectural decisions. Generic starter conventions may conflict with specific requirements.

5. **Clear Technical Stack**: Technology decisions already made (Python 3.10+, FastAPI, PostgreSQL, SQLAlchemy async, PgQueuer, Railway). No starter needed to establish stack.

### Architectural Decisions Required (Manual)

The following architectural decisions will be made explicitly in subsequent steps:

**Component Architecture:**
- FastAPI application structure (routes, dependencies, middleware)
- Worker process architecture (3 concurrent workers, task claiming)
- Integration layer between orchestrator and CLI scripts
- Notion API client design and sync patterns
- YouTube API client design and quota management

**Data Architecture:**
- PostgreSQL schema design (channels, tasks, videos, reviews, costs, audit_logs)
- SQLAlchemy models and relationships
- PgQueuer integration and queue table structure
- Migration strategy and versioning

**Deployment Architecture:**
- Railway service configuration (web service + worker processes)
- Environment variable management
- Database connection pooling and async session lifecycle
- Horizontal scaling strategy for workers

**Security Architecture:**
- API key management (per-channel credentials)
- OAuth flow for YouTube and Notion
- Environment-based configuration
- Audit logging for compliance

**Observability Architecture:**
- Structured logging format and correlation IDs
- Cost tracking data model
- Error alerting integration points
- Metrics collection strategy

**Integration Patterns:**
- CLI script invocation patterns (subprocess, async, error handling)
- Notion API sync patterns (polling, rate limiting, error recovery)
- YouTube API patterns (quota tracking, upload scheduling, retry logic)
- File system management (project directories, asset storage, cleanup)

**Note:** Each architectural decision will be documented explicitly in subsequent steps with clear rationale, alternatives considered, and implementation guidance for AI agents.

---

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
- PostgreSQL schema with Alembic migrations
- SQLAlchemy async models organization
- PgQueuer task lifecycle state machine
- Worker process architecture (3 separate processes)
- CLI script invocation via subprocess
- Filesystem storage with channel organization
- Notion/YouTube API client designs with rate limiting

**Important Decisions (Shape Architecture):**
- Database connection pooling configuration
- Encrypted credentials storage
- CLI-based OAuth setup
- Audit logging for compliance
- Railway service configuration
- Structured logging with correlation IDs
- Cost tracking per video/channel

**Deferred Decisions (Post-MVP):**
- Horizontal scaling beyond 3 workers
- Advanced caching strategies
- Custom monitoring dashboard (Notion Board View sufficient for MVP)

### Data Architecture

**Database Migration Strategy: Alembic with Autogenerate**
- **Tool**: Alembic ≥1.13.0 (latest stable)
- **Pattern**: Auto-detect model changes, manual review before applying
- **Rationale**: Standard for SQLAlchemy 2.0+ async projects, balances automation with control
- **Affects**: All database schema changes during implementation

**SQLAlchemy Models Organization: Single models.py**
- **Structure**: `app/models.py` with all models (channels, tasks, videos, reviews, costs, audit_logs, youtube_quota_usage)
- **Rationale**: ~6-7 tables fit comfortably in single file, easier to see relationships
- **Refactor Trigger**: If file exceeds 500 lines, split into `models/` directory
- **Affects**: Database layer, worker data access patterns

**Asset Storage Strategy: Filesystem with Channel Organization**
- **Path Pattern**: `{workspace_root}/channels/{channel_id}/projects/{project_id}/assets/`
- **Database Reference**: File paths stored in `videos` table
- **Rationale**: Preserves brownfield CLI script interfaces (expect filesystem paths), proven pattern from existing implementation
- **Affects**: CLI script invocation, file management, storage cleanup

**Database Connection Pooling Configuration**
- **pool_size**: 10 (supports 3 workers + web service concurrent operations)
- **max_overflow**: 5 (burst capacity for peak load)
- **pool_timeout**: 30 seconds
- **pool_pre_ping**: True (handle Railway connection recycling)
- **Rationale**: Sized for 3 concurrent workers + FastAPI requests, pool_pre_ping prevents stale connections
- **Affects**: Database engine initialization, connection reliability

### Worker Architecture

**Worker Process Design: Separate Processes**
- **Configuration**: 3 independent Python processes, each running worker loop
- **Deployment**: Railway services (worker-1, worker-2, worker-3)
- **Task Claiming**: Each worker independently claims from PgQueuer using `FOR UPDATE SKIP LOCKED`
- **Rationale**: Clean isolation, Railway-native scaling, one worker crash doesn't affect others
- **Affects**: Railway configuration, horizontal scaling strategy

**CLI Script Invocation Pattern: subprocess with Async Wrapper**
```python
import asyncio
import subprocess

async def run_cli_script(script: str, args: list[str]) -> subprocess.CompletedProcess:
    """Run CLI script without blocking event loop"""
    return await asyncio.to_thread(
        subprocess.run,
        ["python", f"scripts/{script}", *args],
        capture_output=True,
        text=True,
        timeout=600  # 10 min max for video generation
    )
```
- **Rationale**: Non-blocking (asyncio.to_thread), clean timeout handling, CLI scripts remain unchanged
- **Error Handling**: Capture stdout/stderr for structured logging, parse exit codes
- **Affects**: Worker implementation, error recovery patterns

**Task Lifecycle State Machine**

**States:**
1. `pending` - Task created in database, awaiting worker
2. `claimed` - Worker has claimed task (transitional state)
3. `processing` - Worker actively executing CLI scripts
4. `awaiting_review` - Hit human review gate (compliance requirement)
5. `approved` - Human approved, continue pipeline
6. `rejected` - Human rejected, needs manual intervention
7. `completed` - Successfully finished entire pipeline
8. `failed` - Permanent failure (non-retriable error)
9. `retry` - Temporary failure, will retry after backoff

**State Transitions:**
```
pending → claimed → processing → awaiting_review → approved → processing → completed
                                                  ↓
                                               rejected (manual fix required)
processing → failed (non-retriable: bad API key, invalid prompt)
processing → retry → pending (retriable: network timeout, rate limit)
```

**Rationale**: Covers YouTube compliance (human review gates), error recovery, partial pipeline resumption
**Affects**: PgQueuer configuration, Notion status column mapping, human review UI

### Integration Architecture

**Notion API Client Design: Client with Built-in Rate Limiting**
```python
from aiolimiter import AsyncLimiter

class NotionClient:
    def __init__(self, auth_token: str):
        self.rate_limiter = AsyncLimiter(3, 1)  # 3 requests/second
        self.client = AsyncClient(auth=auth_token)

    async def update_task_status(self, page_id: str, status: str):
        async with self.rate_limiter:
            # Automatic 429 backoff built-in
            return await self.client.pages.update(page_id, properties={...})
```
- **Rate Limit**: 3 req/sec enforced at client level
- **Backoff Strategy**: Exponential backoff on 429 responses
- **Instance**: Singleton shared across workers
- **Rationale**: Notion's published limit, client-level enforcement prevents quota exhaustion
- **Affects**: Notion sync service, status update frequency

**Notion Sync Strategy: Polling with Change Detection**
- **PostgreSQL as Source of Truth**: Database state drives Notion updates
- **Polling Frequency**: Check Notion every 60 seconds for manual user changes
- **Push Updates**: Immediately push PostgreSQL state changes to Notion (rate-limited)
- **Conflict Resolution**: PostgreSQL wins (Notion is view layer)
- **Rationale**: Simple, works with Notion's limited webhook support, sufficient for monitoring use case
- **Affects**: Background sync service, Notion integration component

**YouTube API Quota Management: Centralized Tracker with Alerts**

**Schema:**
```python
class YouTubeQuotaUsage:
    id: UUID
    channel_id: str
    date: date
    units_used: int
    daily_limit: int  # 10000 default, can be increased
```

**Quota Checking:**
```python
async def check_youtube_quota(channel_id: str, operation: str) -> bool:
    """Returns True if quota available, False if would exceed"""
    today_usage = await get_usage(channel_id, date.today())
    operation_cost = OPERATION_COSTS[operation]  # e.g., upload=1600
    return (today_usage.units_used + operation_cost) <= today_usage.daily_limit
```

**Alert Thresholds:**
- 80% of daily quota: WARNING alert
- 100% of daily quota: CRITICAL alert, pause uploads for channel

**Rationale**: Prevents quota exhaustion, enables multi-channel fairness, standard YouTube API practice
**Affects**: YouTube upload logic, alerting system, channel scheduling

**Retry Strategy for External APIs**

**Retry Policy:**
- **Max Retries**: 3 attempts
- **Backoff**: Exponential with jitter (1s, 2s, 4s + random jitter)
- **Max Delay**: 60 seconds
- **Timeout**: Per-API (Gemini: 60s, Kling: 600s, ElevenLabs: 120s, YouTube: 300s, Notion: 30s)

**Retriable Errors:**
- Network timeouts, connection errors
- HTTP 429 (rate limit exceeded)
- HTTP 500, 502, 503, 504 (server errors)

**Non-Retriable Errors:**
- HTTP 400 (bad request - fix code)
- HTTP 401 (unauthorized - check API keys)
- HTTP 403 (forbidden - check permissions)
- HTTP 404 (not found - resource doesn't exist)

**Implementation:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    retry=retry_if_exception_type((NetworkError, RateLimitError, ServerError))
)
async def call_external_api(...):
    ...
```

**Rationale**: Handles transient failures gracefully, exponential backoff prevents thundering herd
**Affects**: All external API client implementations (Gemini, Kling, ElevenLabs, YouTube, Notion)

### Security & Configuration

**Per-Channel API Credentials Storage: Encrypted Database**

**Encryption Approach:**
```python
from cryptography.fernet import Fernet

# Railway env var: FERNET_KEY (generated via Fernet.generate_key())
cipher = Fernet(os.environ["FERNET_KEY"])

# Encrypt before storing
encrypted_token = cipher.encrypt(youtube_token.encode())
channel.youtube_token_encrypted = encrypted_token

# Decrypt when needed
youtube_token = cipher.decrypt(channel.youtube_token_encrypted).decode()
```

**Schema:**
```python
class Channel:
    id: str
    youtube_token_encrypted: bytes  # OAuth refresh token
    notion_token_encrypted: bytes   # Integration token
    gemini_key_encrypted: bytes
    elevenlabs_key_encrypted: bytes
```

**Rationale**: Credentials never in plaintext, Railway env var as encryption key, standard cryptography library
**Affects**: Channel configuration, OAuth setup, worker credential access

**OAuth Flow Implementation: CLI-based Setup**

**Setup Script:**
```bash
# One-time setup per channel
python scripts/setup_channel_oauth.py --channel-id pokechannel1

# Opens browser for OAuth flow
# User authorizes YouTube + Notion access
# Script stores encrypted refresh tokens in database
```

**Token Refresh:**
- Workers auto-refresh access tokens using refresh tokens
- Refresh tokens stored encrypted in database
- Access tokens cached in memory (short-lived)

**Rationale**: Matches CLI-first architecture, one-time setup, no web callback routes needed
**Affects**: Channel setup process, OAuth token management in workers

**Environment Configuration Strategy: Railway Env Vars + Channel YAML**

**Global Secrets (Railway Environment Variables):**
```
DATABASE_URL=postgresql+asyncpg://...
FERNET_KEY=<encryption_key>
```

**Per-Channel Config (YAML files):**
```yaml
# channel_configs/pokechannel1.yaml
channel_id: pokechannel1
channel_name: "Pokémon Nature Docs"
schedule: "daily"  # daily, weekly, manual
notion_database_id: "abc123..."
youtube_channel_id: "UC123..."
budget_daily_usd: 50.00
```

**Rationale**: Secrets secure in Railway, config version-controlled, easy to add channels
**Affects**: Configuration management, channel provisioning, deployment process

**Audit Logging for Compliance**

**Schema:**
```python
class AuditLog:
    id: UUID
    timestamp: datetime  # Immutable
    channel_id: str
    video_id: UUID
    action: str  # "review_approved", "review_rejected", "manual_upload", "config_change"
    user_id: str  # Reviewer identifier (email, username)
    notes: str  # Optional reviewer notes
    metadata: dict  # Extensible JSON (video details, review criteria, etc.)
```

**Properties:**
- Immutable (no UPDATE or DELETE operations)
- Retention: 2 years minimum (compliance requirement)
- Indexed on: channel_id, video_id, timestamp, action
- Queryable for YouTube Partner Program audits

**Logged Actions:**
- Human review approvals/rejections
- Manual video uploads
- Configuration changes
- OAuth token refresh
- Quota limit overrides

**Rationale**: YouTube compliance requires evidence of human involvement, audit trail for Partner Program reviews
**Affects**: Human review gates, compliance reporting, YouTube upload logic

### Deployment & Observability

**Railway Service Configuration**

**Service Structure:**
```yaml
# railway.json
{
  "build": {
    "builder": "dockerfile",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "restartPolicyType": "on-failure"
  }
}
```

**Services:**
1. **web** - FastAPI application (uvicorn server)
   - Handles: API routes, Notion webhook callbacks, OAuth callbacks
   - Scaling: 1 instance initially (can horizontally scale)
   - Health check: `/health` endpoint

2. **worker-1, worker-2, worker-3** - Worker processes
   - Each runs: `python app/worker.py`
   - Task claiming: Independent via PgQueuer `FOR UPDATE SKIP LOCKED`
   - Scaling: Stateless, can add more workers dynamically

3. **postgres** - Railway managed PostgreSQL 16
   - Async driver: asyncpg
   - Backups: Railway automatic daily backups
   - Connection: Provided via `DATABASE_URL` env var

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project
WORKDIR /app
COPY . /app

# Install dependencies
RUN uv sync --frozen

# Worker or web determined by start command
CMD ["python", "-m", "app.worker"]
```

**Rationale**: Railway-native configuration, separate concerns (web vs workers), PostgreSQL managed by Railway
**Affects**: Deployment process, scaling strategy, Docker build

**Structured Logging Strategy**

**Logging Configuration:**
```python
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()
```

**Usage Pattern:**
```python
log.info(
    "task_processing_started",
    task_id=str(task.id),
    channel_id=task.channel_id,
    worker_id=worker_id,
    correlation_id=correlation_id,
    pipeline_stage="asset_generation"
)
```

**Log Levels:**
- **DEBUG**: Detailed execution flow, variable dumps (disabled in production)
- **INFO**: State transitions, API calls, task lifecycle events
- **WARNING**: Retriable errors, rate limits hit, quota warnings
- **ERROR**: Non-retriable failures, task failures, integration errors
- **CRITICAL**: Worker crashes, database connection loss, system failures

**Correlation IDs:**
- Generated per task: UUID tracking request across all workers and pipeline stages
- Included in all log statements
- Enables tracing entire video generation lifecycle

**Railway Integration:**
- Logs to stdout/stderr (Railway captures automatically)
- JSON format enables filtering in Railway dashboard
- No external logging service needed for MVP

**Rationale**: JSON structured logs are queryable, correlation IDs enable distributed tracing, Railway-native
**Affects**: All logging throughout application, debugging, monitoring

**Cost Tracking Implementation**

**Schema:**
```python
class VideoCost:
    id: UUID
    video_id: UUID
    channel_id: str
    component: str  # "gemini_assets", "kling_video_clips", "elevenlabs_narration", "elevenlabs_sfx"
    cost_usd: Decimal(10, 4)  # e.g., 1.2500
    api_calls: int
    units_consumed: int  # API-specific units (e.g., Gemini images generated)
    timestamp: datetime
    metadata: dict  # Extensible (e.g., {"clips_generated": 18, "tokens_used": 1500})
```

**Cost Capture Pattern:**
```python
async def track_api_cost(video_id: UUID, component: str, cost: Decimal, api_calls: int):
    """Record cost immediately after API call"""
    async with get_session() as session:
        cost_record = VideoCost(
            video_id=video_id,
            channel_id=video.channel_id,
            component=component,
            cost_usd=cost,
            api_calls=api_calls,
            timestamp=datetime.utcnow()
        )
        session.add(cost_record)
        await session.commit()
```

**Aggregation Queries:**
```sql
-- Per-video total cost
SELECT video_id, SUM(cost_usd) as total_cost
FROM video_costs
GROUP BY video_id;

-- Per-channel daily cost
SELECT channel_id, DATE(timestamp), SUM(cost_usd) as daily_cost
FROM video_costs
GROUP BY channel_id, DATE(timestamp);
```

**Budget Alerts:**
- Channel exceeds daily budget (WARNING)
- Channel exceeds weekly budget (CRITICAL, pause new tasks)
- Actual cost exceeds expected $6-13 range (investigate optimization)

**Rationale**: Granular tracking enables cost optimization, per-channel budgets prevent overrun, audit trail for expenses
**Affects**: Worker cost tracking calls, budget monitoring, financial reporting

**Error Alerting Strategy: Discord Webhooks**

**Configuration:**
```python
# Railway env var: DISCORD_WEBHOOK_URL
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

async def send_alert(level: str, message: str, context: dict):
    """Send alert to Discord channel"""
    if not DISCORD_WEBHOOK_URL:
        return  # Graceful degradation if not configured

    color = {
        "CRITICAL": 0xFF0000,  # Red
        "ERROR": 0xFF6600,     # Orange
        "WARNING": 0xFFCC00    # Yellow
    }[level]

    embed = {
        "title": f"[{level}] {message}",
        "description": json.dumps(context, indent=2),
        "color": color,
        "timestamp": datetime.utcnow().isoformat()
    }

    async with httpx.AsyncClient() as client:
        await client.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
```

**Alert Triggers:**

**CRITICAL:**
- Worker process crash (restart loop detected)
- Database connection loss (cannot reconnect after retries)
- All workers stuck (no task progress in 30+ minutes)
- YouTube API quota completely exhausted

**ERROR:**
- Task failed permanently (after max retries)
- YouTube upload failed (video lost)
- OAuth token refresh failed (requires manual re-auth)
- Filesystem full (cannot save assets)

**WARNING:**
- YouTube quota at 80% of daily limit
- Channel daily budget exceeded
- Notion API rate limit hit (throttling)
- Unusual retry rate (>20% of API calls)

**Rationale**: Discord webhook simple to setup, real-time notifications, no additional service needed, graceful degradation
**Affects**: Alerting infrastructure, monitoring setup, incident response

### Decision Impact Analysis

**Implementation Sequence:**

1. **Foundation** (Must be first)
   - PostgreSQL schema with Alembic setup
   - SQLAlchemy async models
   - Database connection pooling configuration
   - Environment configuration (Railway env vars + channel YAML)

2. **Core Services** (Build on foundation)
   - PgQueuer integration and task lifecycle
   - Worker process architecture
   - CLI script invocation wrapper
   - Filesystem management with channel organization

3. **External Integrations** (Parallel development possible)
   - Notion API client with rate limiting
   - YouTube API client with quota management
   - Retry strategies for all APIs
   - OAuth setup CLI tool

4. **Security & Compliance** (Integrate throughout)
   - Encrypted credentials storage
   - Audit logging for all sensitive actions
   - Human review gate implementation

5. **Observability** (Layer on top)
   - Structured logging with correlation IDs
   - Cost tracking per API call
   - Discord alerting integration
   - Railway deployment configuration

**Cross-Component Dependencies:**

- **Workers → Database**: Workers depend on PostgreSQL schema and PgQueuer setup
- **Workers → Filesystem**: Workers depend on channel-organized directory structure
- **Workers → CLI Scripts**: Workers invoke scripts via subprocess (scripts remain unchanged)
- **Notion Sync → Database**: Polling service reads PostgreSQL, pushes to Notion
- **YouTube Upload → Quota Tracker**: Upload checks quota before executing
- **OAuth Setup → Encryption**: OAuth tool needs Fernet key to encrypt tokens
- **Audit Logging → All Actions**: Human reviews, uploads, config changes log to audit table
- **Cost Tracking → All API Calls**: Every external API call records cost
- **Alerting → All Services**: Workers, sync service, web service can trigger alerts

---

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified:** 18 areas where AI agents could make incompatible implementation choices have been systematically addressed through explicit pattern definitions.

### Naming Patterns

**Database Naming Conventions:**

- **Tables**: Plural, lowercase, snake_case
  - ✅ Correct: `channels`, `tasks`, `video_costs`, `audit_logs`, `youtube_quota_usage`
  - ❌ Wrong: `Channel`, `task`, `VideoCost`

- **Columns**: Lowercase snake_case
  - ✅ Correct: `channel_id`, `created_at`, `youtube_token_encrypted`, `cost_usd`
  - ❌ Wrong: `channelId`, `CreatedAt`, `youtubeToken`

- **Primary Keys**: Always `id` (UUID type)

- **Foreign Keys**: `{table_singular}_id`
  - ✅ Correct: `channel_id`, `video_id`, `task_id`
  - ❌ Wrong: `channelId`, `fk_channel`, `channel`

- **Indexes**: `ix_{table}_{column}` or `ix_{table}_{col1}_{col2}`
  - ✅ Correct: `ix_tasks_channel_id`, `ix_audit_logs_timestamp_action`
  - ❌ Wrong: `tasks_channel_id_index`, `idx_audit_logs`

**API Naming Conventions:**

- **Base Prefix**: `/api/v1/`

- **Endpoints**: Plural nouns, lowercase, kebab-case for multi-word
  - ✅ Correct: `/api/v1/channels`, `/api/v1/youtube-quota`, `/api/v1/audit-logs`
  - ❌ Wrong: `/api/channel`, `/channels`, `/api/v1/YouTubeQuota`

- **Path Parameters**: `{resource_id}` in singular snake_case
  - ✅ Correct: `{channel_id}`, `{task_id}`, `{video_id}`
  - ❌ Wrong: `{id}`, `{channelId}`, `{Channel_ID}`

- **Query Parameters**: snake_case
  - ✅ Correct: `?status=pending&channel_id=poke1&date_from=2026-01-01`
  - ❌ Wrong: `?Status=pending&channelId=poke1`

- **Action Endpoints**: Verb suffix on resource
  - ✅ Correct: `/api/v1/tasks/{task_id}/approve`, `/api/v1/tasks/{task_id}/reject`
  - ❌ Wrong: `/api/v1/approve-task/{task_id}`, `/api/v1/tasks/approve`

**Code Naming Conventions:**

- **Modules/Files**: Lowercase snake_case
  - ✅ Correct: `database.py`, `youtube_client.py`, `cli_wrapper.py`, `notion_sync.py`
  - ❌ Wrong: `Database.py`, `YouTubeClient.py`, `cliWrapper.py`

- **Classes**: PascalCase
  - ✅ Correct: `Channel`, `Task`, `NotionClient`, `YouTubeQuotaManager`
  - ❌ Wrong: `channel`, `notionClient`, `YouTube_Quota_Manager`

- **Functions/Methods**: Lowercase snake_case, verb prefix
  - ✅ Correct: `get_channel_by_id()`, `claim_next_task()`, `run_cli_script()`, `check_youtube_quota()`
  - ❌ Wrong: `getChannel()`, `ClaimTask()`, `runCLIScript()`

- **Variables**: Lowercase snake_case
  - ✅ Correct: `channel_id`, `task_status`, `correlation_id`, `encrypted_token`
  - ❌ Wrong: `channelId`, `TaskStatus`, `correlationID`

- **Constants**: UPPERCASE SNAKE_CASE
  - ✅ Correct: `MAX_RETRIES`, `POOL_SIZE`, `DEFAULT_TIMEOUT`, `OPERATION_COSTS`
  - ❌ Wrong: `maxRetries`, `PoolSize`, `default_timeout`

### Structure Patterns

**Project Organization (Mandatory Layout):**

```
ai-video-generator/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application, route registration
│   ├── worker.py            # Worker process entry point
│   ├── database.py          # Async engine, session factory, get_session()
│   ├── models.py            # All SQLAlchemy models
│   ├── config.py            # Configuration loading (env vars, YAML)
│   ├── clients/             # External API clients
│   │   ├── __init__.py
│   │   ├── notion.py        # NotionClient with rate limiting
│   │   ├── youtube.py       # YouTubeClient with quota tracking
│   │   ├── gemini.py        # (optional: wrapper for existing)
│   │   ├── kling.py         # (optional: wrapper for existing)
│   │   └── elevenlabs.py    # (optional: wrapper for existing)
│   ├── services/            # Business logic, orchestration
│   │   ├── __init__.py
│   │   ├── task_orchestrator.py  # Worker task execution logic
│   │   ├── notion_sync.py         # Bidirectional sync service
│   │   ├── youtube_uploader.py    # Upload with quota checks
│   │   └── cost_tracker.py        # Cost recording service
│   ├── utils/               # Shared utilities
│   │   ├── __init__.py
│   │   ├── cli_wrapper.py   # run_cli_script() implementation
│   │   ├── encryption.py    # Fernet encrypt/decrypt helpers
│   │   ├── filesystem.py    # Path helpers (get_channel_workspace, etc.)
│   │   ├── logging.py       # Structlog configuration
│   │   └── alerts.py        # Discord webhook integration
│   └── routes/              # FastAPI route modules
│       ├── __init__.py
│       ├── channels.py      # /api/v1/channels endpoints
│       ├── tasks.py         # /api/v1/tasks endpoints
│       ├── reviews.py       # /api/v1/reviews endpoints
│       └── health.py        # /health endpoint
├── scripts/                 # Existing CLI tools (UNCHANGED)
│   ├── generate_asset.py
│   ├── create_composite.py
│   ├── generate_video.py
│   ├── generate_audio.py
│   ├── generate_sound_effects.py
│   ├── assemble_video.py
│   └── setup_channel_oauth.py  # NEW: OAuth setup CLI
├── tests/                   # All tests
│   ├── __init__.py
│   ├── conftest.py          # Pytest fixtures (test DB, etc.)
│   ├── test_models.py
│   ├── test_clients/
│   ├── test_services/
│   └── test_routes/
├── alembic/                 # Database migrations
│   ├── versions/
│   └── env.py
├── channel_configs/         # Per-channel YAML configs
│   └── pokechannel1.yaml
├── Dockerfile
├── railway.json
├── pyproject.toml           # uv dependencies
└── alembic.ini
```

**File Placement Rules:**

- **Routes**: One file per resource (`channels.py`, `tasks.py`, `reviews.py`), all in `app/routes/`
- **Business Logic**: Services in `app/services/`, one service per domain (orchestration, sync, upload, etc.)
- **External APIs**: All clients in `app/clients/`, one file per external service (Notion, YouTube, etc.)
- **Utilities**: Cross-cutting helpers in `app/utils/` (CLI wrapper, encryption, filesystem, logging, alerts)
- **Models**: All SQLAlchemy models in single `app/models.py` (refactor to `app/models/` if exceeds 500 lines)
- **Tests**: Mirror `app/` structure in `tests/`, prefixed with `test_` (e.g., `test_clients/test_notion.py`)
- **CLI Scripts**: Remain in `scripts/` root directory (brownfield preservation - NO modifications to existing scripts)

### Async Patterns

**SQLAlchemy 2.0 Async Session Management (CRITICAL):**

**Session Factory (app/database.py):**
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=5,
    pool_timeout=30,
    pool_pre_ping=True
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_session() -> AsyncSession:
    """Dependency for FastAPI routes and services"""
    async with async_session_factory() as session:
        yield session
```

**Pattern A: Short Transactions (Default - Use Everywhere Except FastAPI Routes):**
```python
# ✅ CORRECT: Claim → close → work → reopen → update
async def process_task(task_id: UUID):
    # Step 1: Claim task (short transaction)
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        task.status = "processing"
        await session.commit()

    # Step 2: Do work (NO DB CONNECTION HELD)
    result = await run_cli_script("generate_asset.py", [...])

    # Step 3: Update task (short transaction)
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        task.status = "completed"
        task.result = result
        await session.commit()

# ❌ WRONG: Holding transaction during long-running work
async def process_task_wrong(task_id: UUID):
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        task.status = "processing"
        await session.commit()

        # BLOCKS DB CONNECTION FOR 10 MINUTES!
        result = await run_cli_script("generate_video.py", [...])

        task.status = "completed"
        await session.commit()
```

**Pattern B: FastAPI Route Pattern (Use get_session Dependency):**
```python
from fastapi import Depends
from app.database import get_session

@router.get("/tasks/{task_id}")
async def get_task(
    task_id: UUID,
    session: AsyncSession = Depends(get_session)
):
    # Session automatically managed by FastAPI dependency
    result = await session.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404)
    return task
```

**Query Pattern (SQLAlchemy 2.0 Style - Mandatory):**
```python
# ✅ CORRECT: SQLAlchemy 2.0 select() style
from sqlalchemy import select

result = await session.execute(
    select(Task).where(Task.channel_id == channel_id)
)
tasks = result.scalars().all()

# ✅ CORRECT: Single result
result = await session.execute(
    select(Channel).where(Channel.id == channel_id)
)
channel = result.scalar_one_or_none()

# ✅ CORRECT: Get by primary key
task = await session.get(Task, task_id)

# ❌ WRONG: Legacy query() API (not async-compatible)
tasks = await session.query(Task).filter_by(channel_id=channel_id).all()
```

### Format Patterns

**API Response Formats:**

**Success Response (Direct Resource Return):**
```python
# ✅ CORRECT: Return resource/list directly, no wrapper
@router.get("/channels/{channel_id}")
async def get_channel(channel_id: str, ...):
    return channel  # FastAPI serializes: {"id": "poke1", "name": "...", ...}

@router.get("/channels")
async def list_channels(...):
    return channels  # FastAPI serializes: [{...}, {...}]

# ❌ WRONG: Unnecessary wrapper
return {"data": channel, "success": True}
```

**Error Response (HTTPException):**
```python
from fastapi import HTTPException

# ✅ CORRECT: Use HTTPException
if not channel:
    raise HTTPException(
        status_code=404,
        detail=f"Channel {channel_id} not found"
    )
# Response: {"detail": "Channel poke1 not found"}

# ✅ CORRECT: Custom exception handler for domain errors
# app/main.py
class QuotaExceededError(Exception):
    def __init__(self, channel_id: str, used: int, limit: int):
        self.channel_id = channel_id
        self.used = used
        self.limit = limit

@app.exception_handler(QuotaExceededError)
async def quota_exceeded_handler(request: Request, exc: QuotaExceededError):
    return JSONResponse(
        status_code=429,
        content={
            "detail": f"YouTube quota exceeded for channel {exc.channel_id}",
            "quota_used": exc.used,
            "quota_limit": exc.limit
        }
    )
```

**Data Exchange Formats:**

- **Date/Time**: ISO 8601 strings (FastAPI auto-serializes `datetime` objects)
  - ✅ Correct: `"2026-01-10T15:30:00"` (FastAPI automatic)
  - ❌ Wrong: Unix timestamps, custom formats

- **JSON Field Naming**: snake_case (matches Python)
  - ✅ Correct: `{"channel_id": "poke1", "created_at": "..."}`
  - ❌ Wrong: `{"channelId": "poke1", "createdAt": "..."}`

- **Null Handling**: Use Python `None`, serializes to JSON `null`
  - ✅ Correct: `task.error_message = None`
  - ❌ Wrong: Empty strings `""` for missing values

### Integration Patterns

**CLI Script Invocation (Mandatory Implementation):**

**Location**: `app/utils/cli_wrapper.py`

```python
import asyncio
import subprocess
from pathlib import Path
from typing import List

class CLIScriptError(Exception):
    """Raised when CLI script fails"""
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
    Run CLI script from scripts/ directory without blocking event loop.

    Args:
        script: Script name (e.g., "generate_asset.py")
        args: List of arguments
        timeout: Timeout in seconds (default: 600 = 10 min)

    Returns:
        CompletedProcess with stdout, stderr, returncode

    Raises:
        CLIScriptError: If script exits with non-zero code
        asyncio.TimeoutError: If script exceeds timeout
    """
    script_path = Path("scripts") / script
    command = ["python", str(script_path)] + args

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

try:
    result = await run_cli_script(
        "generate_asset.py",
        ["--prompt", prompt, "--output", output_path],
        timeout=60
    )
    log.info("Asset generated", stdout=result.stdout)
except CLIScriptError as e:
    log.error("Asset generation failed", script=e.script, stderr=e.stderr)
    # Handle error (mark task as failed, retry, alert, etc.)
```

**Filesystem Organization Patterns:**

**Location**: `app/utils/filesystem.py`

```python
from pathlib import Path

WORKSPACE_ROOT = Path("/app/workspace")  # Railway persistent volume

def get_channel_workspace(channel_id: str) -> Path:
    """Get workspace directory for channel"""
    path = WORKSPACE_ROOT / "channels" / channel_id
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_project_dir(channel_id: str, project_id: str) -> Path:
    """Get project directory within channel workspace"""
    path = get_channel_workspace(channel_id) / "projects" / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_asset_dir(channel_id: str, project_id: str) -> Path:
    """Get assets directory for project"""
    path = get_project_dir(channel_id, project_id) / "assets"
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_video_dir(channel_id: str, project_id: str) -> Path:
    """Get videos directory for project"""
    path = get_project_dir(channel_id, project_id) / "videos"
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_audio_dir(channel_id: str, project_id: str) -> Path:
    """Get audio directory for project"""
    path = get_project_dir(channel_id, project_id) / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path
```

**Usage Pattern:**
```python
from app.utils.filesystem import get_asset_dir

# ✅ CORRECT: Use helper functions, Pathlib
asset_dir = get_asset_dir(channel_id="poke1", project_id="vid_123")
output_path = asset_dir / "characters" / "bulbasaur.png"

# Pass string path to CLI script
await run_cli_script("generate_asset.py", ["--output", str(output_path)])

# ❌ WRONG: Hard-coded paths, string concatenation
output_path = f"/workspace/poke1/vid_123/assets/bulbasaur.png"
```

### Enforcement Guidelines

**All AI Agents MUST:**

1. **Use `async_session_factory` directly for workers/services**, `Depends(get_session)` for FastAPI routes
2. **Never hold database transactions during CLI script execution** (claim → close → work → reopen → update)
3. **Use SQLAlchemy 2.0 `select()` style**, never legacy `query()` API
4. **Import and use `run_cli_script()` from `app/utils/cli_wrapper.py`** for all subprocess calls
5. **Import and use filesystem helpers from `app/utils/filesystem.py`** for all path construction
6. **Follow exact directory structure** defined in Structure Patterns section
7. **Use snake_case for all Python code** (modules, functions, variables), PascalCase only for classes
8. **Return resources directly from FastAPI routes**, no wrapper objects
9. **Use `HTTPException` for API errors**, custom exception handlers for domain-specific errors
10. **Never modify existing CLI scripts in `scripts/`** directory (brownfield preservation)

**Pattern Enforcement:**

- **Code Review Checklist**: Verify all patterns followed before merging
- **Linting**: Configure ruff/pylint to enforce naming conventions
- **Testing**: Integration tests verify CLI wrapper and filesystem helpers work correctly
- **Documentation**: Reference this architecture document in all implementation stories

**Pattern Violation Process:**

- If pattern violation discovered: Document in architecture decision log, update this section if pattern needs refinement
- If pattern insufficient: Propose amendment to this document, get user approval, update all agents

### Pattern Examples

**Good Example - Worker Task Processing:**
```python
# app/services/task_orchestrator.py
from app.database import async_session_factory
from app.models import Task
from app.utils.cli_wrapper import run_cli_script, CLIScriptError
from app.utils.filesystem import get_asset_dir

async def generate_assets_for_task(task_id: UUID):
    """Process asset generation task"""

    # Step 1: Claim task (short transaction)
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        task.status = "processing"
        await session.commit()

        # Extract data needed for work (no lazy loading after commit)
        channel_id = task.channel_id
        project_id = task.project_id
        prompts = task.prompts  # Already loaded

    # Step 2: Generate assets (no DB connection)
    asset_dir = get_asset_dir(channel_id, project_id)

    for prompt in prompts:
        try:
            output_path = asset_dir / f"{prompt['name']}.png"
            await run_cli_script(
                "generate_asset.py",
                ["--prompt", prompt['text'], "--output", str(output_path)],
                timeout=60
            )
        except CLIScriptError as e:
            # Mark task as failed
            async with async_session_factory() as session:
                task = await session.get(Task, task_id)
                task.status = "failed"
                task.error_message = str(e)
                await session.commit()
            return

    # Step 3: Mark task complete (short transaction)
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        task.status = "completed"
        await session.commit()
```

**Good Example - FastAPI Route:**
```python
# app/routes/tasks.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.models import Task

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])

@router.get("/{task_id}")
async def get_task(
    task_id: UUID,
    session: AsyncSession = Depends(get_session)
):
    """Get task by ID"""
    result = await session.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found"
        )

    return task  # FastAPI serializes directly
```

**Anti-Patterns (Avoid These):**

**❌ Wrong: Holding DB transaction during CLI execution**
```python
async def bad_task_processing(task_id: UUID):
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        task.status = "processing"
        await session.commit()

        # BLOCKS DB FOR 10 MINUTES!
        result = await run_cli_script("generate_video.py", [...])

        task.status = "completed"
        await session.commit()
```

**❌ Wrong: Legacy SQLAlchemy query() API**
```python
async def bad_query(session):
    # This doesn't work with async SQLAlchemy 2.0
    tasks = await session.query(Task).filter_by(status="pending").all()
```

**❌ Wrong: Hard-coded filesystem paths**
```python
# Don't do this - breaks channel isolation
output_path = f"/workspace/poke1/assets/bulbasaur.png"

# Use helper functions instead
output_path = get_asset_dir("poke1", "vid_123") / "characters" / "bulbasaur.png"
```

**❌ Wrong: Direct subprocess without wrapper**
```python
# Don't do this - blocks event loop
result = subprocess.run(["python", "scripts/generate_asset.py", ...])

# Use async wrapper instead
result = await run_cli_script("generate_asset.py", [...])
```

---

## Project Structure & Boundaries

### Complete Project Directory Structure

```
ai-video-generator/
├── README.md                    # Project overview, setup instructions
├── pyproject.toml               # uv dependencies, Python 3.10+
├── alembic.ini                  # Alembic migration configuration
├── Dockerfile                   # Multi-stage build (Python 3.11-slim + FFmpeg + uv)
├── railway.json                 # Railway service configuration
├── .gitignore                   # Git ignore patterns
├── .env.example                 # Example environment variables
├── app/                          # Orchestration layer (NEW)
│   ├── __init__.py
│   ├── main.py                  # FastAPI application, route registration
│   ├── worker.py                # Worker process entry point
│   ├── database.py              # Async engine, async_session_factory, get_session()
│   ├── models.py                # SQLAlchemy models (channels, tasks, videos, reviews, costs, audit_logs, youtube_quota_usage)
│   ├── config.py                # Configuration loading (Railway env vars, channel YAML parsing)
│   ├── clients/                 # External API clients
│   │   ├── __init__.py
│   │   ├── notion.py            # NotionClient (rate limiting: 3 req/sec)
│   │   ├── youtube.py           # YouTubeClient (quota tracking, uploads)
│   │   ├── gemini.py            # (optional: wrapper if needed)
│   │   ├── kling.py             # (optional: wrapper if needed)
│   │   └── elevenlabs.py        # (optional: wrapper if needed)
│   ├── services/                # Business logic, orchestration
│   │   ├── __init__.py
│   │   ├── task_orchestrator.py # Worker task execution logic (8-step pipeline)
│   │   ├── notion_sync.py       # Bidirectional sync service (60s polling)
│   │   ├── youtube_uploader.py  # Upload service with quota checks
│   │   └── cost_tracker.py      # Cost recording service (per API call)
│   ├── utils/                   # Shared utilities
│   │   ├── __init__.py
│   │   ├── cli_wrapper.py       # run_cli_script() - MANDATORY for all subprocess calls
│   │   ├── encryption.py        # Fernet encrypt/decrypt helpers
│   │   ├── filesystem.py        # Path helpers (get_channel_workspace, get_project_dir, etc.)
│   │   ├── logging.py           # Structlog configuration (JSON format, correlation IDs)
│   │   └── alerts.py            # Discord webhook integration
│   └── routes/                  # FastAPI route modules
│       ├── __init__.py
│       ├── channels.py          # /api/v1/channels endpoints (CRUD)
│       ├── tasks.py             # /api/v1/tasks endpoints (list, get, approve, reject)
│       ├── reviews.py           # /api/v1/reviews endpoints (human review gates)
│       └── health.py            # /health endpoint (liveness probe)
├── scripts/                     # Existing CLI tools (BROWNFIELD - UNCHANGED)
│   ├── .env.example             # CLI environment variables template
│   ├── .env                     # CLI API keys (gitignored)
│   ├── generate_asset.py        # Gemini image generation (330 LOC)
│   ├── create_composite.py      # 16:9 compositing (122 LOC)
│   ├── create_split_screen.py   # Split-screen compositor (87 LOC)
│   ├── generate_video.py        # Kling video animation (330 LOC)
│   ├── generate_audio.py        # ElevenLabs narration (160 LOC)
│   ├── generate_sound_effects.py # ElevenLabs SFX (220 LOC)
│   ├── assemble_video.py        # FFmpeg assembly (350 LOC)
│   └── setup_channel_oauth.py   # NEW: OAuth setup CLI (one-time channel setup)
├── tests/                       # All tests
│   ├── __init__.py
│   ├── conftest.py              # Pytest fixtures (async test DB, mock clients)
│   ├── test_models.py           # SQLAlchemy model tests
│   ├── test_database.py         # Database connection tests
│   ├── test_clients/            # External API client tests
│   │   ├── __init__.py
│   │   ├── test_notion.py       # Mock Notion API calls
│   │   └── test_youtube.py      # Mock YouTube API calls
│   ├── test_services/           # Business logic tests
│   │   ├── __init__.py
│   │   ├── test_task_orchestrator.py
│   │   ├── test_notion_sync.py
│   │   └── test_youtube_uploader.py
│   ├── test_routes/             # FastAPI endpoint tests
│   │   ├── __init__.py
│   │   ├── test_channels.py
│   │   ├── test_tasks.py
│   │   └── test_reviews.py
│   └── test_utils/              # Utility tests
│       ├── __init__.py
│       ├── test_cli_wrapper.py  # Test subprocess wrapper
│       ├── test_encryption.py   # Test Fernet encrypt/decrypt
│       └── test_filesystem.py   # Test path helpers
├── alembic/                     # Database migrations
│   ├── versions/                # Migration files (autogenerated)
│   │   └── README              # Alembic versions placeholder
│   ├── env.py                   # Alembic environment configuration (async engine)
│   └── script.py.mako           # Migration template
├── channel_configs/             # Per-channel YAML configuration
│   ├── pokechannel1.yaml        # Example channel config
│   └── README.md                # Channel config documentation
├── docs/                        # Existing documentation (BROWNFIELD)
│   ├── index.md                 # Documentation hub
│   ├── architecture.md          # Existing system architecture
│   ├── architecture-patterns.md # "Smart Agent + Dumb Scripts" pattern
│   ├── technology-stack.md      # Tech stack documentation
│   └── project-overview.md      # Executive summary
└── _bmad-output/                # BMAD workflow outputs
    ├── project-context.md       # Implementation rules for AI agents
    └── planning-artifacts/      # PRD, UX spec, architecture, epics
        ├── prd.md
        ├── ux-design-specification.md
        ├── architecture.md       # THIS DOCUMENT
        └── research/             # Research documents
```

### Architectural Boundaries

**API Boundaries:**

- **External API** (`/api/v1/*`):
  - Public endpoints for task management, channel CRUD, human reviews
  - Authentication: Optional (can add API keys later)
  - Rate limiting: FastAPI SlowAPI middleware (optional)
  - CORS: Configured for Notion integration callbacks

- **Internal Service Boundaries**:
  - `app/services/` contains business logic, called by routes and workers
  - Services use `async_session_factory` directly (not FastAPI dependency)
  - Services never call other services directly (to avoid circular deps)

- **CLI Script Boundary** (CRITICAL):
  - CLI scripts in `scripts/` are black boxes
  - Only interface: command-line arguments, stdout/stderr, exit codes
  - Workers invoke via `run_cli_script()` wrapper (async, timeout, error handling)
  - **NO database connections** in CLI scripts
  - **NO queue awareness** in CLI scripts

**Component Boundaries:**

- **Database Layer** (`app/database.py`, `app/models.py`):
  - Single source of truth for all state
  - Async-only access (SQLAlchemy 2.0 + asyncpg)
  - Short transaction pattern enforced (claim → close → work → reopen → update)

- **External Client Layer** (`app/clients/`):
  - Each client encapsulates one external API
  - Rate limiting built into clients (Notion: 3 req/sec)
  - Retry logic applied via tenacity decorators
  - Clients are stateless, can be instantiated per-request

- **Service Layer** (`app/services/`):
  - Orchestrates between database, clients, and CLI scripts
  - Implements business logic (pipeline orchestration, sync, uploads)
  - Uses short transactions, never holds DB during long operations

- **Route Layer** (`app/routes/`):
  - Thin layer, minimal logic
  - Uses `Depends(get_session)` for DB access
  - Returns resources directly (no wrapper objects)
  - FastAPI handles serialization automatically

**Service Boundaries:**

- **Worker Service** (`app/worker.py`):
  - Runs as separate Railway service (worker-1, worker-2, worker-3)
  - Claims tasks via PgQueuer (FOR UPDATE SKIP LOCKED)
  - Executes 8-step pipeline via `task_orchestrator` service
  - No HTTP server, pure Python event loop

- **Web Service** (`app/main.py`):
  - Runs as Railway web service (uvicorn + FastAPI)
  - Handles HTTP requests (API routes, health checks)
  - Does NOT execute CLI scripts (workers do that)
  - Provides endpoints for task creation, human reviews

- **Sync Service** (future: `app/services/notion_sync.py` as background task):
  - Polls Notion every 60 seconds for manual updates
  - Pushes PostgreSQL state changes to Notion (rate-limited)
  - Runs as background asyncio task in web service

**Data Boundaries:**

- **PostgreSQL Database**:
  - Tables: `channels`, `tasks`, `videos`, `reviews`, `video_costs`, `audit_logs`, `youtube_quota_usage`
  - Access via SQLAlchemy async engine (pool_size=10, max_overflow=5)
  - Migrations via Alembic (autogenerate + manual review)

- **Filesystem Storage** (`/app/workspace` on Railway):
  - Organized: `/app/workspace/channels/{channel_id}/projects/{project_id}/assets/`
  - Assets: images, videos, audio, SFX
  - Database stores file paths as references
  - Cleanup: Manual or scheduled job (not in scope for MVP)

- **External API Data**:
  - Notion: Source for manual task updates, sink for status updates
  - YouTube: Upload destination, quota tracking required
  - Gemini/Kling/ElevenLabs: Ephemeral (request → response, no state)

### Requirements to Structure Mapping

**FR-MCM (Multi-Channel Management) → Component Mapping:**

- **FR-MCM-001 to FR-MCM-006**: Channel CRUD
  - `channel_configs/{channel_id}.yaml` - YAML configuration files
  - `app/config.py` - Load and parse YAML configs on startup
  - `app/routes/channels.py` - API endpoints for channel management
  - `app/models.py` - `Channel` model with encrypted credentials

**FR-NOT (Notion Integration) → Component Mapping:**

- **FR-NOT-001 to FR-NOT-007**: Notion sync
  - `app/clients/notion.py` - NotionClient with AsyncLimiter (3 req/sec)
  - `app/services/notion_sync.py` - Bidirectional sync logic (60s polling)
  - `app/models.py` - `Task.notion_page_id` foreign key mapping
  - Background task in `app/main.py` - Polling loop

**FR-VGO (Video Generation Orchestration) → Component Mapping:**

- **FR-VGO-001 to FR-VGO-010**: Task orchestration
  - `app/worker.py` - Worker process entry point (3 separate processes)
  - `app/services/task_orchestrator.py` - 8-step pipeline execution
  - `app/utils/cli_wrapper.py` - `run_cli_script()` implementation
  - `app/utils/filesystem.py` - Path helpers for workspace organization
  - `app/models.py` - `Task` model with 9-state machine
  - `scripts/` - Existing 7 CLI tools (invoked by workers)

**FR-YTC (YouTube API Compliance) → Component Mapping:**

- **FR-YTC-001 to FR-YTC-008**: Human review gates, quota management
  - `app/routes/reviews.py` - `/api/v1/reviews` endpoints (approve/reject)
  - `app/services/youtube_uploader.py` - Upload with quota pre-check
  - `app/clients/youtube.py` - YouTubeClient with quota tracking
  - `app/models.py` - `AuditLog` model (immutable, 2-year retention)
  - `app/models.py` - `YouTubeQuotaUsage` model (channel_id + date + units_used)

**FR-MON (Monitoring & Observability) → Component Mapping:**

- **FR-MON-001 to FR-MON-007**: Logging, cost tracking, alerting
  - `app/utils/logging.py` - Structlog configuration (JSON, correlation IDs)
  - `app/services/cost_tracker.py` - `track_api_cost()` function
  - `app/utils/alerts.py` - `send_alert()` Discord webhook
  - `app/models.py` - `VideoCost` model (per-component cost breakdown)
  - Railway logs - stdout/stderr captured automatically

**Cross-Cutting Concerns → Component Mapping:**

- **Security**:
  - `app/utils/encryption.py` - Fernet encrypt/decrypt for credentials
  - `scripts/setup_channel_oauth.py` - OAuth flow for YouTube + Notion
  - Railway env vars - `FERNET_KEY`, `DATABASE_URL`

- **Configuration**:
  - `app/config.py` - Load Railway env vars + channel YAML
  - `channel_configs/` - Per-channel configuration files
  - `.env.example` - Template for local development

- **Testing**:
  - `tests/conftest.py` - Async test database fixtures
  - `tests/test_clients/` - Mock external APIs
  - `tests/test_services/` - Business logic unit tests
  - `tests/test_routes/` - FastAPI endpoint integration tests

### Integration Points

**Internal Communication:**

- **Routes ↔ Services**: Direct function calls (async)
  - Routes receive HTTP requests → call service functions → return responses
  - Example: `POST /api/v1/tasks` → `task_orchestrator.create_task()`

- **Services ↔ Database**: Via `async_session_factory`
  - Services open sessions, query/update models, commit
  - Short transactions enforced (no DB held during long operations)

- **Services ↔ Clients**: Direct instantiation and method calls
  - Example: `youtube_uploader` → `youtube_client.upload_video()`
  - Clients handle rate limiting, retries internally

- **Workers ↔ CLI Scripts**: Via `run_cli_script()` wrapper
  - Worker calls `await run_cli_script("generate_asset.py", args)`
  - Subprocess runs, stdout/stderr captured, exit code checked
  - `CLIScriptError` raised on non-zero exit

**External Integrations:**

- **Notion API**:
  - Entry point: `app/clients/notion.py`
  - Rate limit: 3 requests/second (AsyncLimiter)
  - Polling: Every 60 seconds from `notion_sync` service
  - Push updates: On task state changes (rate-limited)

- **YouTube Data API v3**:
  - Entry point: `app/clients/youtube.py`
  - Quota tracking: `youtube_quota_usage` table, pre-check before operations
  - OAuth: Setup via `scripts/setup_channel_oauth.py`, refresh tokens in DB

- **Google Gemini 2.5 Flash**:
  - Invoked via: `scripts/generate_asset.py` (existing CLI)
  - Workers call CLI script with combined prompt + Global Atmosphere
  - Cost tracking: After each generation in `video_costs`

- **Kling AI (via KIE.ai)**:
  - Invoked via: `scripts/generate_video.py` (existing CLI)
  - Workers call CLI script with catbox.moe image URL + motion prompt
  - Cost tracking: After each video generation

- **ElevenLabs v3**:
  - Invoked via: `scripts/generate_audio.py`, `scripts/generate_sound_effects.py`
  - Workers call CLI scripts with text/description
  - Cost tracking: After each generation

**Data Flow:**

```
User/Scheduler → Notion Board View
                    ↓ (manual task creation)
Notion API ← notion_sync → PostgreSQL (tasks table)
                    ↓ (task state: pending)
PgQueuer → Worker claims task (state: claimed)
                    ↓
Worker → task_orchestrator.process_task()
    ↓ (state: processing)
    ├─→ run_cli_script("generate_asset.py") → Gemini API → Assets saved
    ├─→ run_cli_script("create_composite.py") → Composites saved
    ├─→ run_cli_script("generate_video.py") → Kling API → Videos saved
    ├─→ run_cli_script("generate_audio.py") → ElevenLabs → Audio saved
    ├─→ run_cli_script("generate_sound_effects.py") → ElevenLabs → SFX saved
    └─→ run_cli_script("assemble_video.py") → FFmpeg → Final video saved
                    ↓ (state: awaiting_review)
Human → /api/v1/reviews/{video_id}/approve → audit_log entry
                    ↓ (state: approved)
Worker → youtube_uploader.upload()
    ↓ (check quota)
    └─→ YouTube API upload → Video published
                    ↓ (state: completed)
notion_sync → Updates Notion page status
```

### File Organization Patterns

**Configuration Files:**

- **Root Level**:
  - `pyproject.toml` - Python dependencies (uv format), project metadata
  - `alembic.ini` - Alembic configuration (database URL from env var)
  - `Dockerfile` - Multi-stage build (base + dependencies + app)
  - `railway.json` - Service configuration (web + 3 workers)
  - `.env.example` - Template showing required environment variables

- **Application Config**:
  - `app/config.py` - Loads `DATABASE_URL`, `FERNET_KEY`, parses channel YAMLs
  - `channel_configs/*.yaml` - Per-channel configuration (schedule, notion_database_id, budget)

**Source Organization:**

- **Entry Points**:
  - `app/main.py` - FastAPI app creation, route registration, exception handlers
  - `app/worker.py` - Worker process, PgQueuer setup, task claiming loop

- **Layers** (following implementation patterns):
  - `app/routes/` - HTTP interface layer (thin, uses `Depends(get_session)`)
  - `app/services/` - Business logic layer (orchestration, sync, uploads)
  - `app/clients/` - External API integration layer (Notion, YouTube, etc.)
  - `app/utils/` - Cross-cutting utilities (CLI wrapper, encryption, logging, alerts)

- **Data Layer**:
  - `app/models.py` - All SQLAlchemy models (single file, refactor if >500 lines)
  - `app/database.py` - Async engine, session factory, dependency injection

**Test Organization:**

- **Structure Mirrors `app/`**:
  - `tests/test_routes/` mirrors `app/routes/`
  - `tests/test_services/` mirrors `app/services/`
  - `tests/test_clients/` mirrors `app/clients/`
  - `tests/test_utils/` mirrors `app/utils/`

- **Test Fixtures**:
  - `tests/conftest.py` - Shared fixtures (async test DB, mock clients, test data)
  - Pytest async plugins configured in `pyproject.toml`

- **Test Patterns**:
  - Unit tests: Mock external dependencies, test logic in isolation
  - Integration tests: Use test database, test DB ↔ service interactions
  - No E2E tests for MVP (manual testing sufficient)

**Asset Organization:**

- **Workspace Structure** (Railway persistent volume):
```
/app/workspace/
└── channels/
    └── {channel_id}/
        └── projects/
            └── {project_id}/
                ├── assets/
                │   ├── characters/
                │   ├── environments/
                │   ├── props/
                │   └── composites/
                ├── videos/
                ├── audio/
                ├── sfx/
                └── {project_id}_final.mp4
```

- **Path Helpers** (`app/utils/filesystem.py`):
  - `get_channel_workspace(channel_id)` → `/app/workspace/channels/{channel_id}`
  - `get_project_dir(channel_id, project_id)` → `.../projects/{project_id}`
  - `get_asset_dir()`, `get_video_dir()`, `get_audio_dir()` → Subdirectories

### Development Workflow Integration

**Development Server Structure:**

- **Local Development**:
```bash
# Terminal 1: Web service
uvicorn app.main:app --reload --port 8000

# Terminal 2: Worker process
python -m app.worker

# Terminal 3: Database migrations
alembic upgrade head

# Access API: http://localhost:8000/api/v1/
# Access docs: http://localhost:8000/docs (FastAPI auto-generated)
```

- **Environment Setup**:
```bash
# Install dependencies
uv sync

# Setup database (Railway local or Docker)
docker-compose up -d postgres

# Run migrations
alembic upgrade head

# Configure environment
cp .env.example .env
# Edit .env with: DATABASE_URL, FERNET_KEY, DISCORD_WEBHOOK_URL
```

**Build Process Structure:**

- **Dockerfile Multi-Stage Build**:
```dockerfile
# Stage 1: Base with system dependencies
FROM python:3.11-slim AS base
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Stage 2: Dependencies
FROM base AS dependencies
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Stage 3: Application
FROM dependencies AS application
COPY . /app
CMD ["python", "-m", "app.worker"]  # Overridden by Railway start command
```

- **Build Artifacts**:
  - Docker image pushed to Railway registry
  - Database migrations applied via Alembic in Railway init container

**Deployment Structure:**

- **Railway Services**:
```json
{
  "services": {
    "web": {
      "build": {"dockerfile": "Dockerfile"},
      "start": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
      "healthcheck": "/health"
    },
    "worker-1": {
      "build": {"dockerfile": "Dockerfile"},
      "start": "python -m app.worker"
    },
    "worker-2": {
      "build": {"dockerfile": "Dockerfile"},
      "start": "python -m app.worker"
    },
    "worker-3": {
      "build": {"dockerfile": "Dockerfile"},
      "start": "python -m app.worker"
    },
    "postgres": {
      "image": "postgres:16",
      "environment": {
        "POSTGRES_USER": "$POSTGRES_USER",
        "POSTGRES_PASSWORD": "$POSTGRES_PASSWORD",
        "POSTGRES_DB": "$POSTGRES_DB"
      }
    }
  }
}
```

- **Environment Variables** (Railway dashboard):
  - `DATABASE_URL` - Provided by Railway PostgreSQL service
  - `FERNET_KEY` - Generated via `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  - `DISCORD_WEBHOOK_URL` - Discord server webhook for alerts
  - `NOTION_TOKEN` - (optional: global token if not per-channel)

- **Scaling**:
  - Web service: Horizontal scaling via Railway (multiple instances)
  - Workers: Add more worker services (worker-4, worker-5) via Railway config
  - Database: Vertical scaling via Railway managed PostgreSQL plan upgrade

---

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**

All technology choices work together seamlessly without conflicts:

- FastAPI + SQLAlchemy 2.0 async + asyncpg form a compatible async stack (all use async/await consistently)
- PgQueuer integrates natively with PostgreSQL (same DB as SQLAlchemy, uses LISTEN/NOTIFY)
- uv package manager compatible with all Python 3.10+ dependencies
- Railway deployment designed for managed PostgreSQL + multi-service architecture
- Short transaction pattern explicitly designed to work with CLI subprocess calls (claim → close → work → reopen → update prevents connection exhaustion)
- Alembic 1.13.0+ fully supports SQLAlchemy 2.0 async migrations (async engine in env.py)
- Filesystem storage preserves brownfield CLI script interfaces (scripts expect file paths, not DB connections)

**Pattern Consistency:**

Implementation patterns fully support and align with architectural decisions:

- **Naming conventions unified across all layers**:
  - Database: snake_case tables, `id` for primary keys, `{table}_id` for foreign keys
  - API: plural nouns, kebab-case for multi-word resources
  - Code: snake_case functions/variables, PascalCase classes, UPPERCASE constants
- **Async patterns consistent throughout**:
  - `async_session_factory` for workers/services (short transactions)
  - `Depends(get_session)` for FastAPI routes (automatic lifecycle)
  - `asyncio.to_thread` for CLI scripts (non-blocking subprocess execution)
  - SQLAlchemy 2.0 `select()` style (never legacy `query()` API)
- **CLI wrapper pattern enforces non-blocking execution**: All subprocess calls via `run_cli_script()` with timeout handling, error capture, async execution
- **Filesystem helpers enforce consistent path construction**: All path operations via `get_channel_workspace()`, `get_project_dir()`, etc.
- **API response pattern standardized**: Return resources directly (no wrappers), HTTPException for errors, FastAPI auto-serialization
- **Mandatory app/ layout with clear layer separation**: routes → services → clients/database, each layer has defined responsibilities

**Structure Alignment:**

Project structure fully supports all architectural decisions:

- **`app/` structure enables FastAPI backend**: Clear separation of concerns (main.py, routes/, services/, clients/, utils/, models.py, database.py)
- **`scripts/` preserved unchanged**: Brownfield requirement met - 7 CLI tools remain black boxes (1,599 LOC untouched)
- **Worker architecture supported**: Dedicated entry point (app/worker.py), orchestration service (task_orchestrator.py), 3 separate Railway services
- **Testing structure mirrors app/**: Maintainability through parallel organization (test_routes/, test_services/, test_clients/, test_utils/)
- **Configuration structure supports Railway**: Environment variables for secrets (FERNET_KEY, DATABASE_URL), YAML files for channel configs (version-controlled)
- **Workspace structure integrates with CLI scripts**: `/app/workspace/channels/{channel_id}/projects/{project_id}/` matches expected filesystem layout

### Requirements Coverage Validation ✅

**Epic/Feature Coverage (All 67 Functional Requirements Mapped):**

**FR-MCM (Multi-Channel Management) - 6 requirements:**
- ✅ Channel CRUD operations, YAML-based configuration, independent video schedules per channel, per-channel API credentials (encrypted), cross-channel isolation, scalability to 10+ channels
- **Components**: `channel_configs/*.yaml` (configuration files), `app/config.py` (YAML parsing), `app/routes/channels.py` (CRUD endpoints), `Channel` model with encrypted credentials (youtube_token_encrypted, notion_token_encrypted, gemini_key_encrypted, elevenlabs_key_encrypted)

**FR-NOT (Notion Integration) - ~12 requirements:**
- ✅ Bidirectional sync with Notion databases, 26-column pipeline visualization (Kanban Board View), task creation/updates, status polling (60s interval), rate limit compliance (3 req/sec), manual change detection
- **Components**: `app/clients/notion.py` (NotionClient with AsyncLimiter), `app/services/notion_sync.py` (60s polling + push updates), `Task.notion_page_id` foreign key mapping, background task in main.py

**FR-VGO (Video Generation Orchestration) - ~25 requirements:**
- ✅ Queue-based task management (PgQueuer), 3-worker concurrent execution, existing CLI scripts preserved as workers, state persistence in PostgreSQL (9-state machine), retry logic with exponential backoff, partial pipeline resumption, filesystem-based asset storage
- **Components**: `app/worker.py` (3 Railway services, independent task claiming), `app/services/task_orchestrator.py` (8-step pipeline logic), `app/utils/cli_wrapper.py` (subprocess async wrapper), `Task` model (9-state machine: pending → claimed → processing → awaiting_review → approved/rejected → completed/failed/retry), PgQueuer integration (FOR UPDATE SKIP LOCKED), 7 existing CLI scripts in `scripts/` (unchanged)

**FR-YTC (YouTube API Compliance) - ~12 requirements:**
- ✅ Human review gates at strategic points (post-video generation, pre-upload), review evidence storage (immutable audit log), quota management across channels, July 2025 policy compliance (human-in-the-loop requirement), upload scheduling, API quota alerts (80% warning, 100% critical)
- **Components**: `app/routes/reviews.py` (approve/reject endpoints), `app/services/youtube_uploader.py` (quota pre-checks before upload), `YouTubeQuotaUsage` model (channel_id + date + units_used + daily_limit), `AuditLog` model (immutable, indexed, 2-year retention), 95% autonomous operation (review gates only at critical points)

**FR-MON (Monitoring & Observability) - ~12 requirements:**
- ✅ Structured logging (JSON format), cost tracking per video/channel, error alerting (Discord webhooks), video generation metrics, task duration tracking, Railway dashboard integration (stdout/stderr capture)
- **Components**: `app/utils/logging.py` (structlog configuration, correlation IDs across pipeline stages), `app/services/cost_tracker.py` (track_api_cost function), `app/utils/alerts.py` (send_alert with Discord webhook), `VideoCost` model (per-component cost breakdown: gemini_assets, kling_video_clips, elevenlabs_narration, elevenlabs_sfx), Railway logs (automatic capture)

**Functional Requirements Coverage:**

All 67 functional requirements across 5 domains have explicit architectural support with specific components, services, models, and integration points documented. No requirements lack architectural coverage.

**Non-Functional Requirements Coverage:**

**Performance:**
- ✅ 100 videos/week target (14.3 videos/day) supported by 3 concurrent workers with PgQueuer task claiming (FOR UPDATE SKIP LOCKED prevents contention)
- ✅ Async I/O throughout: SQLAlchemy async engine, asyncpg driver, FastAPI async routes, asyncio.to_thread for CLI scripts (non-blocking)
- ✅ Connection pooling configured: pool_size=10 (supports 3 workers + web service), max_overflow=5 (burst capacity), pool_pre_ping=True (Railway connection recycling)

**Compliance & Regulatory:**
- ✅ YouTube Partner Program July 2025 policy: Human review gates strategically placed (post-video generation, pre-upload)
- ✅ Evidence storage: `AuditLog` model (immutable, no UPDATE/DELETE, indexed on channel_id/video_id/timestamp/action, 2-year retention, queryable for Partner Program audits)
- ✅ 95% autonomous operation: Review gates don't block every step, only critical checkpoints

**Cost Optimization:**
- ✅ $6-13 per video cost maintained: `VideoCost` granular tracking per component (Gemini assets $0.50-2.00, Kling videos $5-10, ElevenLabs audio $0.50-1.00)
- ✅ API quota management: `YouTubeQuotaUsage` table with pre-operation quota checks (check_youtube_quota returns True/False)
- ✅ Multi-channel quota allocation: Per-channel tracking with 80% WARNING alert, 100% CRITICAL alert + pause uploads

**Reliability & Availability:**
- ✅ Railway deployment: Managed PostgreSQL (automatic backups), horizontal scaling support for workers (stateless design)
- ✅ Graceful degradation: Retry logic with exponential backoff, tenacity decorators, retriable vs non-retriable error classification (network timeout vs bad API key)
- ✅ Partial pipeline resumption: 9-state task machine enables recovery at any stage (task stores current pipeline stage)
- ✅ Short transaction pattern: Prevents connection exhaustion during long-running CLI operations (claim → close → work → reopen → update)

**Usability:**
- ✅ Monitoring-first UX: Notion Board View as primary interface (26-column Kanban, glanceable status visualization)
- ✅ Minimal setup friction: YAML channel configs (no UI needed), CLI OAuth tool (`scripts/setup_channel_oauth.py` for one-time setup)
- ✅ "Card stuck = problem, moving = success" design principle: Notion sync pushes status updates, cards move across columns automatically

### Implementation Readiness Validation ✅

**Decision Completeness:**

All critical architectural decisions are documented with implementation-ready details:

- ✅ **Technology stack with specific versions**: FastAPI ≥0.104.0, SQLAlchemy ≥2.0.0, asyncpg ≥0.29.0, PgQueuer ≥0.10.0, Alembic ≥1.13.0, Python ≥3.10, FFmpeg 8.0.1+
- ✅ **Database migration strategy**: Alembic autogenerate + manual review before applying (prevents accidental schema changes)
- ✅ **Connection pooling configuration**: pool_size=10, max_overflow=5, pool_timeout=30s, pool_pre_ping=True (sized for 3 workers + web service)
- ✅ **Worker process architecture**: 3 independent Python processes, Railway services (worker-1, worker-2, worker-3), PgQueuer FOR UPDATE SKIP LOCKED for task claiming
- ✅ **CLI script invocation pattern with code**: `asyncio.to_thread` + `subprocess.run`, 600s timeout, capture_output=True, CLIScriptError exception handling
- ✅ **Task lifecycle state machine**: 9 states (pending, claimed, processing, awaiting_review, approved, rejected, completed, failed, retry) with complete transition diagram
- ✅ **External API integration patterns**: Notion 3 req/sec rate limiting (AsyncLimiter), YouTube quota tracking (pre-check before operations), retry strategies with tenacity (max 3 attempts, exponential backoff, retriable vs non-retriable errors)
- ✅ **Security architecture**: Fernet encryption for credentials (FERNET_KEY in Railway env var), OAuth CLI setup tool, encrypted database columns (youtube_token_encrypted, etc.), audit logging for compliance
- ✅ **Observability architecture**: structlog JSON format, correlation IDs (UUID per task, carried through all pipeline stages), Discord webhooks for alerts (CRITICAL/ERROR/WARNING), cost tracking per API call (track_api_cost function)

**Structure Completeness:**

Project structure is concrete and implementation-ready (not generic placeholders):

- ✅ **Complete directory tree**: 100+ files and directories explicitly defined with clear purposes (e.g., `app/utils/cli_wrapper.py` - CLI script subprocess wrapper, `app/services/task_orchestrator.py` - 8-step pipeline execution logic)
- ✅ **All architectural layers specified**: routes/ (HTTP interface), services/ (business logic), clients/ (external APIs), utils/ (cross-cutting concerns), models.py (database), database.py (async engine)
- ✅ **Component boundaries clearly delineated**: API boundaries (external /api/v1/*, internal service boundaries), service boundaries (worker vs web vs sync), data boundaries (PostgreSQL, filesystem, external APIs), CLI script boundary (black boxes, command-line interface only)
- ✅ **Integration points fully mapped**: Internal communication (routes → services → database/clients via direct async function calls), workers → CLI scripts (via run_cli_script wrapper), complete data flow diagram (Notion → PostgreSQL → Workers → CLI scripts → External APIs → Assets → Final video)
- ✅ **Requirements-to-structure mapping complete**: All 67 FRs mapped to specific files/directories (FR-MCM → channel_configs/ + app/routes/channels.py + Channel model, FR-NOT → app/clients/notion.py + app/services/notion_sync.py, etc.)
- ✅ **Workspace filesystem structure defined**: `/app/workspace/channels/{channel_id}/projects/{project_id}/assets/` with helpers (get_channel_workspace, get_project_dir, get_asset_dir, get_video_dir, get_audio_dir)

**Pattern Completeness:**

Implementation patterns systematically prevent AI agent conflicts:

- ✅ **Naming patterns comprehensive**:
  - Database: snake_case tables (`channels`, `tasks`, `video_costs`), `id` for primary keys, `{table}_id` for foreign keys, `ix_{table}_{column}` for indexes
  - API: `/api/v1/` prefix, plural nouns (`/channels`, `/tasks`, `/reviews`), kebab-case for multi-word (`/youtube-quota`, `/audit-logs`), `{resource_id}` path parameters, snake_case query parameters
  - Code: snake_case modules/functions/variables (`youtube_client.py`, `get_channel_by_id()`), PascalCase classes (`NotionClient`, `Task`), UPPERCASE constants (`MAX_RETRIES`, `POOL_SIZE`)

- ✅ **Structure patterns mandatory**: Defined app/ layout with clear file placement rules (routes in `app/routes/`, business logic in `app/services/`, external APIs in `app/clients/`, utilities in `app/utils/`, all models in single `app/models.py` until 500 lines, tests mirror app/ structure)

- ✅ **Async patterns critical (with detailed examples)**:
  - **Pattern A (Short Transactions)**: `async with async_session_factory() as session: claim_task() → commit()` → close DB → `run_cli_script()` → reopen DB → `async with async_session_factory() as session: update_task() → commit()`
  - **Pattern B (FastAPI Routes)**: `session: AsyncSession = Depends(get_session)` for automatic lifecycle management
  - **Query Pattern**: SQLAlchemy 2.0 `select()` style (NEVER legacy `query()` API), `await session.execute(select(Task).where(...))`, `result.scalar_one_or_none()` or `result.scalars().all()`

- ✅ **Format patterns standardized**:
  - API responses: Return resources directly (no wrapper objects), FastAPI auto-serializes
  - Error responses: `raise HTTPException(status_code=404, detail="...")` or custom exception handlers for domain errors
  - Date/time: ISO 8601 strings (FastAPI automatic from datetime objects)
  - JSON naming: snake_case (matches Python), null handling via Python `None`

- ✅ **Integration patterns with complete implementations**:
  - CLI wrapper (`app/utils/cli_wrapper.py`): `run_cli_script(script, args, timeout=600)` function with `CLIScriptError` exception, `asyncio.to_thread` for non-blocking execution, stdout/stderr capture
  - Filesystem helpers (`app/utils/filesystem.py`): `WORKSPACE_ROOT = Path("/app/workspace")`, `get_channel_workspace(channel_id)`, `get_project_dir(channel_id, project_id)`, all return Pathlib paths with automatic directory creation

- ✅ **Good examples and anti-patterns provided**: Each critical pattern includes ✅ correct implementation and ❌ wrong implementation (e.g., holding DB transaction during CLI execution, using legacy query() API, hard-coded paths, direct subprocess without wrapper)

- ✅ **Enforcement guidelines specified**: Code review checklist (verify patterns followed), linting configuration (ruff/pylint for naming), testing strategy (integration tests for CLI wrapper/filesystem helpers), documentation references (always link to this architecture doc in stories)

### Gap Analysis Results

**Critical Gaps:** ✅ **NONE** - No blocking implementation issues identified

All critical architectural decisions are complete and implementation-ready. The architecture provides sufficient detail for AI agents to implement consistently without conflicting choices.

**Important Gaps (Can be addressed during implementation with external documentation):**

1. **PgQueuer Setup Details** (Medium Priority):
   - **Gap**: PgQueuer integration mentioned (task claiming, LISTEN/NOTIFY) but queue table creation and PostgreSQL LISTEN/NOTIFY configuration not fully specified in architecture doc
   - **Impact**: Workers depend on PgQueuer for task claiming (FOR UPDATE SKIP LOCKED pattern), blocking if not set up correctly
   - **Resolution**: Reference PgQueuer documentation during implementation (queue table schema, LISTEN/NOTIFY setup are standard PgQueuer patterns). PgQueuer provides migration scripts for queue table creation. Document in `app/worker.py` during implementation.

2. **Notion 26-Column Schema Mapping** (Medium Priority):
   - **Gap**: 26-column Kanban Board View mentioned (from UX spec) but specific Notion column names, property types, and status mappings not in architecture doc
   - **Impact**: Notion sync service (`app/services/notion_sync.py`) needs to know exact schema to push status updates and poll for changes
   - **Resolution**: Reference UX Design Specification (`_bmad-output/planning-artifacts/ux-design-specification.md`) during implementation of Notion sync. UX spec contains complete Notion database schema with all 26 columns defined.

3. **OAuth Token Refresh Flow Details** (Medium Priority):
   - **Gap**: Token refresh mentioned (workers auto-refresh access tokens) but flow not detailed (check expiry → use refresh token → update DB → cache access token)
   - **Impact**: Long-term operation requires working token refresh, otherwise YouTube/Notion uploads fail after access token expiry
   - **Resolution**: Document during implementation of `app/clients/youtube.py` and `app/clients/notion.py`. Standard OAuth refresh token flow (well-documented by Google/Notion APIs). Store refresh tokens in DB (encrypted), cache access tokens in memory (short-lived).

4. **Alembic env.py Async Configuration** (Low Priority):
   - **Gap**: Async migrations mentioned (Alembic 1.13.0+ supports SQLAlchemy 2.0 async) but `alembic/env.py` async configuration not shown
   - **Impact**: Database migrations need async engine to work with AsyncSession models
   - **Resolution**: Standard SQLAlchemy 2.0 async pattern for Alembic (well-documented in Alembic docs). Configure `run_async` in env.py with async engine. Copy from SQLAlchemy 2.0 Alembic examples.

5. **Database URL Format for asyncpg** (Low Priority):
   - **Gap**: `DATABASE_URL` environment variable referenced throughout but exact format not explicitly shown
   - **Impact**: Engine initialization needs correct asyncpg URL format, Railway provides URL but might need format conversion
   - **Resolution**: Standard format: `postgresql+asyncpg://user:password@host:port/database` (Railway provides this automatically). Document in README.md during deployment setup.

**Nice-to-Have Gaps (Post-MVP, Not Blocking):**

- **Caching strategy**: Deferred decision for MVP (mentioned in "Deferred Decisions" section). Future enhancement for frequently accessed channel configs and Notion data.
- **FastAPI route rate limiting**: Mentioned as optional (SlowAPI middleware). Not needed for MVP (internal API, no public exposure).
- **Custom monitoring dashboard**: Notion Board View sufficient for MVP. Future enhancement for technical metrics (task duration histograms, API latency, worker utilization).
- **Horizontal scaling strategy beyond 3 workers**: Architecture supports adding more workers (stateless design, PgQueuer handles coordination). Implementation details for auto-scaling deferred to post-MVP.
- **Asset cleanup/retention policy**: Manual or scheduled job not in scope for MVP. Future enhancement for workspace management (delete old projects, archive completed videos).

**Gap Impact Assessment:**

All identified gaps are documentation refinements that can be resolved during implementation by referencing:
- External documentation (PgQueuer setup, Alembic async configuration, OAuth flows)
- Other project documents (UX Design Specification for Notion schema)
- Standard practices (DATABASE_URL format, token caching)

No gaps require architectural decisions or additional user input. Implementation can proceed immediately.

### Validation Issues Addressed

✅ **No critical issues found during validation**

The architecture validation revealed:
- **Coherence**: All architectural decisions work together seamlessly (compatible technology stack, consistent patterns, aligned structure)
- **Coverage**: All 67 functional requirements and all NFRs have explicit architectural support with mapped components
- **Readiness**: Implementation patterns are complete, conflict points addressed, structure is concrete (not generic placeholders)
- **Gaps**: Only minor documentation gaps that reference external docs, no blocking issues

The identified gaps in the "Gap Analysis Results" section are documentation refinements (PgQueuer setup, Notion schema mapping, OAuth flow details, Alembic async config, DATABASE_URL format) that can be addressed during implementation by consulting external documentation or other project documents. These do not represent missing architectural decisions.

**Conclusion**: The architecture is coherent, complete, and ready for AI agent implementation without additional user input required.

### Architecture Completeness Checklist

**✅ Requirements Analysis**

- [x] Project context thoroughly analyzed (67 functional requirements across 5 domains: FR-MCM, FR-NOT, FR-VGO, FR-YTC, FR-MON)
- [x] Scale and complexity assessed (HIGH complexity: distributed system characteristics, external integrations, regulatory compliance, multi-tenant-like behavior, long-running processes)
- [x] Technical constraints identified (Python ≥3.10 async/await, brownfield CLI preservation, short transaction pattern mandatory, Railway deployment, YouTube compliance)
- [x] Cross-cutting concerns mapped (10 concerns: async transaction management, queue-based orchestration, API rate limiting, error recovery, human review gates, multi-channel resource allocation, cost tracking, observability, configuration management, compliance evidence trail)

**✅ Architectural Decisions**

- [x] Critical decisions documented with versions (PostgreSQL schema + Alembic, SQLAlchemy async models, PgQueuer task lifecycle, 3-worker architecture, CLI subprocess invocation, filesystem storage, Notion/YouTube clients)
- [x] Technology stack fully specified (FastAPI ≥0.104.0, SQLAlchemy ≥2.0.0, asyncpg ≥0.29.0, PgQueuer ≥0.10.0, Alembic ≥1.13.0, Python ≥3.10, uv package manager, FFmpeg 8.0.1+, Railway platform)
- [x] Integration patterns defined (Notion rate limiting 3 req/sec, YouTube quota management, retry strategies with tenacity, OAuth CLI setup, Fernet encryption)
- [x] Performance considerations addressed (connection pooling: pool_size=10/max_overflow=5, async I/O throughout, PgQueuer LISTEN/NOTIFY, short transactions prevent connection exhaustion)

**✅ Implementation Patterns**

- [x] Naming conventions established (database: snake_case tables/columns, API: kebab-case endpoints, code: snake_case functions/vars + PascalCase classes + UPPERCASE constants)
- [x] Structure patterns defined (mandatory app/ layout: routes/, services/, clients/, utils/, models.py, database.py, 100+ files specified with purposes)
- [x] Communication patterns specified (routes → services → database/clients via direct async calls, workers → CLI scripts via run_cli_script wrapper, services use async_session_factory, routes use Depends(get_session))
- [x] Process patterns documented (short transactions: claim → close → work → reopen → update, async session management, CLI wrapper with timeout/error handling, filesystem helpers for path construction)

**✅ Project Structure**

- [x] Complete directory structure defined (app/ orchestration layer, scripts/ brownfield CLI tools, tests/ mirroring app/, alembic/ migrations, channel_configs/ YAML files, workspace/ filesystem storage)
- [x] Component boundaries established (API: external /api/v1/* + internal services, service: worker vs web vs sync, data: PostgreSQL + filesystem + external APIs, CLI scripts: black boxes with command-line interface only)
- [x] Integration points mapped (internal: routes ↔ services ↔ database/clients, workers ↔ CLI scripts, external: Notion/YouTube/Gemini/Kling/ElevenLabs, complete data flow: Notion → PostgreSQL → Workers → CLI → APIs → Assets → Final video)
- [x] Requirements to structure mapping complete (all 67 FRs mapped: FR-MCM → channel_configs/ + app/routes/channels.py, FR-NOT → app/clients/notion.py + app/services/notion_sync.py, FR-VGO → app/worker.py + app/services/task_orchestrator.py, FR-YTC → app/routes/reviews.py + app/clients/youtube.py + AuditLog, FR-MON → app/utils/logging.py + app/services/cost_tracker.py)

### Architecture Readiness Assessment

**Overall Status:** ✅ **READY FOR IMPLEMENTATION**

**Confidence Level:** **HIGH** - Architecture is comprehensive, coherent, and provides clear implementation guidance for AI agents

The architecture document is complete, validated, and ready for AI-driven implementation. All architectural decisions are documented with sufficient detail for consistent implementation across multiple AI agents. The identified gaps are minor documentation references that can be resolved during implementation without additional architectural decisions.

**Key Strengths:**

1. **Comprehensive Technology Decisions**: All critical technologies specified with exact versions (FastAPI ≥0.104.0, SQLAlchemy ≥2.0.0, asyncpg ≥0.29.0, PgQueuer ≥0.10.0, Alembic ≥1.13.0) and configuration details (pool_size=10, max_overflow=5, pool_pre_ping=True).

2. **Brownfield Integration Strategy**: Clear preservation of existing CLI scripts (1,599 LOC unchanged in `scripts/`) while adding orchestration layer in `app/` directory. "Smart Agent + Dumb Scripts" pattern maintained: orchestrator reads files/combines prompts, scripts execute single API calls.

3. **Critical Pattern Documentation**: Short transaction pattern explicitly documented with code examples (claim → close → work → reopen → update) prevents common async pitfalls where DB connections are held during long-running CLI operations (would cause connection pool exhaustion).

4. **Complete Requirements Coverage**: All 67 functional requirements mapped to specific architectural components (FR-MCM → channel configs + routes, FR-NOT → Notion client + sync service, FR-VGO → workers + task orchestrator, FR-YTC → review routes + YouTube client + audit log, FR-MON → logging + cost tracker + alerts).

5. **Conflict Prevention Through Patterns**: 18 potential AI agent conflict points systematically addressed with implementation patterns (naming conventions, structure rules, async patterns, format standards, integration helpers) including good examples and anti-patterns for each.

6. **Compliance Built-In**: YouTube July 2025 policy requirements (human-in-the-loop) architected from start: human review gates at strategic points, immutable audit log (2-year retention), review evidence storage, 95% autonomous operation design.

7. **Railway-Native Design**: Architecture tailored for Railway platform: managed PostgreSQL (connection pooling configured for Railway), separate worker services (worker-1/2/3), environment-based configuration (DATABASE_URL, FERNET_KEY), stdout/stderr logging (Railway auto-captures), horizontal scaling support.

8. **Observability Foundation**: Structured logging (structlog JSON format with correlation IDs), cost tracking after all API calls (VideoCost table with per-component breakdown), alerting system (Discord webhooks for CRITICAL/ERROR/WARNING), Railway dashboard integration baked into architecture from day one.

**Areas for Future Enhancement (Post-MVP):**

These are explicitly deferred, not gaps requiring attention now:

1. **Caching layer**: For frequently accessed channel configs and Notion data (reduce API calls, improve response time)
2. **Advanced horizontal scaling strategy**: Worker auto-scaling based on queue depth (PgQueuer metrics → add/remove workers dynamically)
3. **Custom monitoring dashboard**: Complement Notion Board View with technical metrics (task duration histograms, API latency percentiles, worker utilization, queue depth trends)
4. **Asset retention and cleanup automation**: Scheduled jobs for workspace management (delete old projects after N days, archive completed videos to cold storage)
5. **Advanced rate limiting for public API endpoints**: Protect against abuse if API becomes public (currently internal-only, so not needed)

### Implementation Handoff

**AI Agent Guidelines:**

When implementing this architecture, AI agents MUST follow these rules:

1. **Follow Architectural Decisions Exactly**: All technology choices, patterns, and structure decisions in this document are prescriptive and binding. Do not substitute technologies (e.g., do NOT use psycopg2 instead of asyncpg, do NOT use pip instead of uv, do NOT use sync SQLAlchemy instead of async).

2. **Use Implementation Patterns Consistently**: Reference the "Implementation Patterns & Consistency Rules" section for ALL coding decisions. Every file name, function name, API endpoint, database table/column, and code structure choice must follow documented patterns.

3. **Respect Brownfield Boundaries**: NEVER modify existing CLI scripts in `scripts/` directory. They remain unchanged (brownfield preservation). The 7 CLI tools (generate_asset.py, create_composite.py, create_split_screen.py, generate_video.py, generate_audio.py, generate_sound_effects.py, assemble_video.py) are black boxes - only interface is command-line arguments, stdout/stderr, exit codes.

4. **Apply Short Transaction Pattern**: ALWAYS use claim → close → work → reopen → update. NEVER hold database connections during CLI script execution. Pattern: `async with async_session_factory() as session: claim_task() → commit()` → close DB → `run_cli_script()` → reopen DB → `async with async_session_factory() as session: update_task() → commit()`.

5. **Use Provided Utilities**: ALWAYS import and use:
   - `run_cli_script()` from `app/utils/cli_wrapper.py` for ALL subprocess calls (never use subprocess.run directly)
   - Filesystem helpers from `app/utils/filesystem.py` for ALL path construction (never use hard-coded paths or string concatenation)
   - `async_session_factory` from `app/database.py` for workers/services, `Depends(get_session)` for FastAPI routes

6. **Follow Directory Structure**: Place ALL files according to "Project Structure & Boundaries" section. Routes in `app/routes/`, business logic in `app/services/`, external APIs in `app/clients/`, utilities in `app/utils/`, all models in `app/models.py` (until 500 lines), tests mirroring `app/` structure in `tests/`.

7. **Implement Observability**: Use structlog for ALL logging (import from `app/utils/logging.py`), track costs after ALL external API calls (call `track_api_cost()` from `app/services/cost_tracker.py`), send alerts for critical errors (call `send_alert()` from `app/utils/alerts.py`).

8. **Refer to This Document**: When uncertain about implementation choices, consult this architecture document FIRST. If multiple approaches seem valid, choose the one explicitly documented here. If not documented here, ask user before proceeding (do not guess).

**First Implementation Priority:**

Start with foundation layer in this sequence (implement in order, do not skip):

**1. Database Foundation** (Core infrastructure, everything depends on this):

```bash
# Set up database module
# File: app/database.py
# - Create async_engine with: DATABASE_URL, pool_size=10, max_overflow=5, pool_timeout=30, pool_pre_ping=True
# - Create async_session_factory with: engine, class_=AsyncSession, expire_on_commit=False
# - Create get_session() dependency for FastAPI routes

# Create all SQLAlchemy models
# File: app/models.py
# - Channel model (id, name, youtube_token_encrypted, notion_token_encrypted, gemini_key_encrypted, elevenlabs_key_encrypted, created_at, updated_at)
# - Task model (id, channel_id, project_id, status, notion_page_id, prompts, error_message, created_at, updated_at)
# - Video model (id, task_id, channel_id, project_id, final_video_path, duration_seconds, created_at)
# - Review model (id, video_id, reviewer_id, status, notes, reviewed_at)
# - VideoCost model (id, video_id, channel_id, component, cost_usd, api_calls, units_consumed, timestamp, metadata)
# - AuditLog model (id, timestamp, channel_id, video_id, action, user_id, notes, metadata) - immutable
# - YouTubeQuotaUsage model (id, channel_id, date, units_used, daily_limit)

# Initialize Alembic with async configuration
alembic init alembic

# Edit alembic/env.py to use async engine (reference SQLAlchemy 2.0 docs)

# Generate initial migration
alembic revision --autogenerate -m "Initial schema"

# IMPORTANT: Review migration manually before applying
# Check table names, column names, indexes match naming conventions

# Apply migration
alembic upgrade head
```

**2. Core Utilities** (Shared helpers, many components depend on these):

```python
# File: app/utils/cli_wrapper.py
# - Implement CLIScriptError exception (script, exit_code, stderr attributes)
# - Implement run_cli_script(script, args, timeout=600) function
#   - Use asyncio.to_thread to run subprocess.run non-blocking
#   - Capture stdout/stderr, check exit code
#   - Raise CLIScriptError on non-zero exit

# File: app/utils/filesystem.py
# - Define WORKSPACE_ROOT = Path("/app/workspace")
# - Implement get_channel_workspace(channel_id) → creates and returns Path
# - Implement get_project_dir(channel_id, project_id) → creates and returns Path
# - Implement get_asset_dir(channel_id, project_id) → creates and returns Path
# - Implement get_video_dir(channel_id, project_id) → creates and returns Path
# - Implement get_audio_dir(channel_id, project_id) → creates and returns Path

# File: app/utils/encryption.py
# - Import cryptography.fernet.Fernet
# - Load FERNET_KEY from environment variable
# - Implement encrypt(plaintext: str) → bytes function
# - Implement decrypt(ciphertext: bytes) → str function

# File: app/utils/logging.py
# - Configure structlog with JSON renderer, timestamper, log level, correlation ID processor
# - Export configured logger: log = structlog.get_logger()
```

**3. Configuration Layer** (Loads environment variables and channel configs):

```python
# File: app/config.py
# - Load DATABASE_URL, FERNET_KEY, DISCORD_WEBHOOK_URL from environment
# - Implement load_channel_configs() → Dict[str, ChannelConfig]
#   - Scan channel_configs/ directory for .yaml files
#   - Parse YAML (channel_id, channel_name, schedule, notion_database_id, youtube_channel_id, budget_daily_usd)
#   - Validate required fields, return dict keyed by channel_id

# Create example channel config
# File: channel_configs/pokechannel1.yaml
# - channel_id, channel_name, schedule, notion_database_id, youtube_channel_id, budget_daily_usd

# Document OAuth setup (implementation comes later)
# File: scripts/setup_channel_oauth.py
# - CLI tool for one-time channel OAuth setup (YouTube + Notion)
# - Opens browser for OAuth flow, stores encrypted refresh tokens in database
```

**4. External API Clients** (Integrations with Notion, YouTube):

```python
# File: app/clients/notion.py
# - Import aiolimiter.AsyncLimiter
# - Implement NotionClient class
#   - __init__(auth_token: str) - creates AsyncLimiter(3, 1) for rate limiting
#   - async update_task_status(page_id: str, status: str) - rate limited
#   - async get_database_pages(database_id: str) - rate limited, returns pages
#   - Automatic exponential backoff on 429 responses

# File: app/clients/youtube.py
# - Implement YouTubeClient class
#   - __init__(channel_id: str, refresh_token: str) - decrypts refresh token
#   - async check_quota(operation: str) → bool - queries YouTubeQuotaUsage table
#   - async upload_video(video_path: Path, title: str, description: str) - checks quota first
#   - Refresh access token using refresh token (standard OAuth flow)
```

**5. Worker Architecture** (Task claiming and pipeline execution):

```python
# Set up PgQueuer integration
# - Reference PgQueuer documentation for queue table creation
# - Configure LISTEN/NOTIFY for task updates
# - Document in app/worker.py

# File: app/worker.py
# - Import PgQueuer, configure with DATABASE_URL
# - Implement worker_loop() - claims tasks with FOR UPDATE SKIP LOCKED
# - For each claimed task, call task_orchestrator.process_task(task_id)
# - Handle errors, log with correlation IDs

# File: app/services/task_orchestrator.py
# - Implement process_task(task_id: UUID) - orchestrates 8-step pipeline
# - Step 1: Claim task (short transaction), extract data
# - Step 2-8: Call CLI scripts via run_cli_script, track costs, update task status
# - Use short transaction pattern throughout (claim → close → work → reopen → update)
# - Generate assets, composites, videos, audio, SFX, assemble final video
# - Transition task to awaiting_review after video generation
```

**6. API Layer** (FastAPI routes for HTTP interface):

```python
# File: app/main.py
# - Create FastAPI app
# - Register routers from app/routes/
# - Add exception handlers (HTTPException, QuotaExceededError, etc.)
# - Configure CORS if needed for Notion callbacks

# File: app/routes/health.py
# - Implement GET /health endpoint (returns 200 OK, for Railway liveness probe)

# File: app/routes/channels.py
# - Implement GET /api/v1/channels (list all channels)
# - Implement GET /api/v1/channels/{channel_id} (get single channel)
# - Implement POST /api/v1/channels (create channel)
# - Implement PUT /api/v1/channels/{channel_id} (update channel)
# - Use Depends(get_session) for database access

# File: app/routes/tasks.py
# - Implement GET /api/v1/tasks (list tasks, filter by channel_id/status)
# - Implement GET /api/v1/tasks/{task_id} (get single task)
# - Implement POST /api/v1/tasks (create task)

# File: app/routes/reviews.py
# - Implement POST /api/v1/reviews/{video_id}/approve (human approval)
# - Implement POST /api/v1/reviews/{video_id}/reject (human rejection)
# - Create audit log entry for each review action
```

**7. Deployment** (Docker, Railway configuration):

```dockerfile
# File: Dockerfile
# - Multi-stage build: base (Python 3.11-slim + FFmpeg + uv) → dependencies (uv sync) → application (copy app code)
# - WORKDIR /app
# - Default CMD: python -m app.worker (overridden by Railway start command)

# File: railway.json
# - Define services: web (uvicorn app.main:app), worker-1/2/3 (python -m app.worker), postgres (managed)
# - Configure healthcheck: /health endpoint
# - Configure environment variables: DATABASE_URL (from postgres service), FERNET_KEY, DISCORD_WEBHOOK_URL

# Railway deployment:
# 1. Create Railway project
# 2. Add PostgreSQL service (provides DATABASE_URL automatically)
# 3. Generate FERNET_KEY: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# 4. Add environment variables in Railway dashboard
# 5. Deploy web service + 3 worker services
# 6. Test end-to-end pipeline
```

**Validation During Implementation:**

After each foundation layer is complete, validate:
- ✅ All files placed in correct locations (per structure patterns)
- ✅ All naming conventions followed (snake_case, PascalCase, UPPERCASE per rules)
- ✅ Short transaction pattern applied (no DB held during CLI scripts)
- ✅ CLI wrapper and filesystem helpers used (no direct subprocess or hard-coded paths)
- ✅ Logging, cost tracking, alerting integrated (observability from start)

**Testing Strategy:**

- Unit tests: Mock external dependencies (CLI scripts, external APIs), test logic in isolation
- Integration tests: Use test database (separate from production), test database ↔ service interactions
- End-to-end tests: Manual for MVP (create channel → create task → run worker → verify video generated → approve review → upload to YouTube)

**Documentation During Implementation:**

- Update README.md with setup instructions (install Python 3.10+, install uv, install FFmpeg, configure Railway, run Alembic migrations)
- Document environment variables in .env.example (DATABASE_URL, FERNET_KEY, DISCORD_WEBHOOK_URL)
- Document channel YAML format in channel_configs/README.md
- Reference this architecture document in all implementation stories/commits

---

## Architecture Completion Summary

### Workflow Completion

**Architecture Decision Workflow:** COMPLETED ✅
**Total Steps Completed:** 8
**Date Completed:** 2026-01-10
**Document Location:** `_bmad-output/planning-artifacts/architecture.md`

### Final Architecture Deliverables

**📋 Complete Architecture Document**

- All architectural decisions documented with specific versions (FastAPI ≥0.104.0, SQLAlchemy ≥2.0.0, asyncpg ≥0.29.0, PgQueuer ≥0.10.0, Alembic ≥1.13.0, Python ≥3.10, FFmpeg 8.0.1+)
- Implementation patterns ensuring AI agent consistency (naming, structure, async, format, integration patterns with good/bad examples)
- Complete project structure with 100+ files and directories explicitly defined
- Requirements to architecture mapping (all 67 FRs mapped to specific components)
- Validation confirming coherence and completeness (HIGH confidence level)

**🏗️ Implementation Ready Foundation**

- **29 architectural decisions** made across 5 categories (Data, Worker, Integration, Security, Deployment)
- **5 implementation pattern categories** defined to prevent conflicts (18 conflict points systematically addressed)
- **7 architectural components** specified (FastAPI backend, 3 worker processes, PostgreSQL + PgQueuer, Notion/YouTube clients, 7 brownfield CLI scripts)
- **67 functional requirements** fully supported (FR-MCM: 6, FR-NOT: 12, FR-VGO: 25, FR-YTC: 12, FR-MON: 12)

**📚 AI Agent Implementation Guide**

- Technology stack with verified compatible versions and configuration (pool_size=10, max_overflow=5, pool_pre_ping=True for Railway)
- Consistency rules that prevent implementation conflicts (mandatory app/ layout, short transaction pattern, CLI wrapper usage, filesystem helpers)
- Project structure with clear boundaries (API, service, data, CLI script boundaries explicitly delineated)
- Integration patterns and communication standards (routes → services → database/clients, workers → CLI scripts via async wrapper)

### Implementation Handoff

**For AI Agents:**

This architecture document is your complete guide for implementing ai-video-generator's brownfield transformation. Follow all decisions, patterns, and structures exactly as documented. The architecture preserves existing CLI scripts (1,599 LOC unchanged) while adding FastAPI orchestration layer, PostgreSQL state management, and multi-channel concurrency.

**First Implementation Priority:**

Start with the 7-step foundation sequence documented in "Implementation Handoff" section:

1. **Database Foundation**: Set up `app/database.py` (async engine, session factory), create `app/models.py` (all 7 models), initialize Alembic, generate and review initial migration, apply with `alembic upgrade head`

2. **Core Utilities**: Implement `app/utils/cli_wrapper.py` (run_cli_script with CLIScriptError), `app/utils/filesystem.py` (workspace path helpers), `app/utils/encryption.py` (Fernet encrypt/decrypt), `app/utils/logging.py` (structlog JSON configuration)

3. **Configuration Layer**: Implement `app/config.py` (load env vars, parse channel YAMLs), create example `channel_configs/pokechannel1.yaml`, document OAuth setup in `scripts/setup_channel_oauth.py`

4. **External API Clients**: Implement `app/clients/notion.py` (NotionClient with AsyncLimiter 3 req/sec), `app/clients/youtube.py` (YouTubeClient with quota tracking)

5. **Worker Architecture**: Set up PgQueuer integration, implement `app/worker.py` (task claiming loop), implement `app/services/task_orchestrator.py` (8-step pipeline with short transactions)

6. **API Layer**: Implement `app/main.py` (FastAPI app), `app/routes/health.py` (/health), `app/routes/channels.py` (CRUD), `app/routes/tasks.py` (list/get), `app/routes/reviews.py` (approve/reject)

7. **Deployment**: Create `Dockerfile` (multi-stage with Python 3.11-slim + FFmpeg + uv), create `railway.json` (web + 3 workers + postgres), configure Railway environment variables

**Development Sequence:**

1. Initialize database schema using Alembic migrations (all 7 models: Channel, Task, Video, Review, VideoCost, AuditLog, YouTubeQuotaUsage)
2. Set up Railway services (PostgreSQL managed, web service, worker-1/2/3 services)
3. Implement core architectural foundations following the 7-step sequence above
4. Build 8-step video generation pipeline (assets → composites → videos → audio → SFX → assembly → review → upload)
5. Maintain consistency with documented patterns (short transactions, CLI wrapper, filesystem helpers, naming conventions)

### Quality Assurance Checklist

**✅ Architecture Coherence**

- [x] All decisions work together without conflicts (FastAPI + SQLAlchemy async + asyncpg + PgQueuer form compatible stack)
- [x] Technology choices are compatible (all versions verified, connection pooling sized correctly)
- [x] Patterns support the architectural decisions (short transactions prevent connection exhaustion, CLI wrapper enables non-blocking)
- [x] Structure aligns with all choices (app/ structure supports FastAPI, scripts/ preserved for brownfield, workspace/ for filesystem storage)

**✅ Requirements Coverage**

- [x] All functional requirements are supported (67 FRs mapped: FR-MCM → channel configs/routes, FR-NOT → Notion client/sync, FR-VGO → workers/orchestrator, FR-YTC → reviews/quota, FR-MON → logging/costs/alerts)
- [x] All non-functional requirements are addressed (Performance: 100 videos/week with 3 workers, Compliance: YouTube July 2025 human review gates, Cost: $6-13 per video tracking, Reliability: Railway deployment + retry logic)
- [x] Cross-cutting concerns are handled (10 concerns: async transactions, queue orchestration, rate limiting, error recovery, human reviews, multi-channel isolation, cost tracking, observability, configuration, compliance trail)
- [x] Integration points are defined (Internal: routes ↔ services ↔ database/clients, workers ↔ CLI scripts, External: Notion/YouTube/Gemini/Kling/ElevenLabs with retry strategies)

**✅ Implementation Readiness**

- [x] Decisions are specific and actionable (all technology versions specified, configurations detailed, patterns with code examples)
- [x] Patterns prevent agent conflicts (18 conflict points addressed: naming conventions, structure rules, async patterns, CLI wrapper, filesystem helpers)
- [x] Structure is complete and unambiguous (100+ files explicitly defined with purposes, no generic placeholders)
- [x] Examples are provided for clarity (good ✅ and bad ❌ examples for short transactions, CLI invocation, path construction, query patterns)

### Project Success Factors

**🎯 Clear Decision Framework**

Every technology choice was made with clear rationale addressing brownfield constraints (preserve 7 CLI scripts), compliance requirements (YouTube July 2025 policy), and performance targets (100 videos/week across 5-10 channels). All stakeholders understand the architectural direction.

**🔧 Consistency Guarantee**

Implementation patterns (mandatory app/ layout, short transaction pattern, CLI wrapper usage, filesystem helpers, naming conventions) ensure multiple AI agents will produce compatible, consistent code. 18 conflict points systematically addressed with enforcement guidelines.

**📋 Complete Coverage**

All 67 functional requirements architecturally supported with explicit component mapping. Performance (3 concurrent workers, async I/O, connection pooling), Compliance (human review gates, immutable audit log), Cost ($6-13 per video granular tracking), and Reliability (Railway deployment, retry logic, partial resumption) all addressed.

**🏗️ Solid Foundation**

Manual foundation approach (not starter template) provides precise control for brownfield transformation. Architecture preserves "Smart Agent + Dumb Scripts" pattern while adding orchestration layer. Railway-native design with managed PostgreSQL, separate worker services, and environment-based configuration.

---

**Architecture Status:** ✅ **READY FOR IMPLEMENTATION**

**Next Phase:** Begin implementation using the architectural decisions and patterns documented herein. Start with 7-step foundation sequence (database → utilities → config → clients → workers → API → deployment).

**Document Maintenance:** Update this architecture when major technical decisions are made during implementation. Document any deviations from planned architecture with rationale in architecture decision log.

---
