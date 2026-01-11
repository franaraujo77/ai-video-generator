# Core Architectural Decisions

## Decision Priority Analysis

**Critical Decisions (Block Implementation):**
1. Database Schema Pattern
2. Transaction Management Strategy
3. OAuth Token Storage
4. Notion Status Update Pattern
5. CI/CD Pipeline

**Important Decisions (Shape Architecture):**
6. Migration Strategy
7. Error Response Format
8. Logging Strategy
9. Worker Scaling Strategy
10. Monitoring & Alerting

**Established by Starter Template:**
- Language & Runtime (Python 3.10+, FastAPI)
- Queue System (PostgreSQL + PgQueuer)
- Worker Pattern (Independent processes)
- Rate Limiting (PostgreSQL-based)
- HTTP Client (httpx)
- ORM (SQLAlchemy 2.0+)

---

## Data Architecture

### **Decision 1: Database Schema Pattern**

**Choice:** Denormalized Tenant Discriminator (Enhanced Option 2)

**Rationale:**
- Sub-millisecond task claims (<1ms vs 5-10ms with JOINs)
- Simple round-robin scheduling via `DISTINCT channel_id`
- Proven multi-tenant queue pattern (validated by Hatchet.run research)
- Optimized for PgQueuer's `FOR UPDATE SKIP LOCKED` + `LISTEN/NOTIFY`
- Linear scalability to 100K tasks, 50 channels

**Schema Design:**

```sql
-- Channels table (reference data, rarely queried)
CREATE TABLE channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    youtube_channel_id TEXT,
    elevenlabs_voice_id TEXT,
    brand_style TEXT,
    storage_strategy TEXT DEFAULT 'notion',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tasks table (hot path, denormalized for performance)
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Channel discriminator (denormalized - NO FK)
    channel_id UUID NOT NULL,
    channel_name TEXT NOT NULL,  -- Avoid JOIN for display

    -- Task metadata
    title TEXT NOT NULL,
    topic TEXT,
    story_direction TEXT,

    -- Queue fields
    status TEXT NOT NULL DEFAULT 'draft',
    priority INT DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    claimed_at TIMESTAMPTZ,  -- For round-robin fairness

    -- Error tracking
    last_error TEXT,
    retry_count INT DEFAULT 0,
    next_retry_at TIMESTAMPTZ,

    -- Results
    youtube_url TEXT,
    notion_page_id TEXT,
    notion_synced_at TIMESTAMPTZ,

    -- Constraints
    CHECK (status IN ('draft', 'queued', 'processing', 'assets_ready',
                      'video_ready', 'audio_ready', 'published', 'failed'))
);

-- Queue-optimized partial indexes
CREATE INDEX idx_tasks_queue_claim ON tasks
    (channel_id, status, priority DESC, created_at ASC)
    WHERE status = 'queued';

CREATE INDEX idx_tasks_processing ON tasks
    (channel_id, status, claimed_at)
    WHERE status = 'processing';

CREATE INDEX idx_tasks_retry ON tasks
    (next_retry_at)
    WHERE next_retry_at IS NOT NULL;

-- Rate limits table (per-channel, per-service)
CREATE TABLE rate_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id UUID NOT NULL,
    service TEXT NOT NULL,
    current_count INT DEFAULT 0,
    max_concurrent INT NOT NULL,
    window_start TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(channel_id, service)
);

-- Global rate limits (cross-channel coordination)
CREATE TABLE global_rate_limits (
    service TEXT PRIMARY KEY,
    current_count INT DEFAULT 0,
    max_concurrent INT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- OAuth tokens (encrypted storage)
CREATE TABLE oauth_tokens (
    channel_id UUID PRIMARY KEY,
    access_token TEXT NOT NULL,   -- Encrypted with Fernet
    refresh_token TEXT NOT NULL,  -- Encrypted with Fernet
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Round-robin scheduling function
CREATE OR REPLACE FUNCTION get_next_channel_for_processing()
RETURNS UUID AS $$
    SELECT channel_id
    FROM tasks
    WHERE status = 'queued'
    GROUP BY channel_id
    ORDER BY MAX(COALESCE(claimed_at, '1970-01-01'::TIMESTAMPTZ)) ASC
    LIMIT 1;
$$ LANGUAGE SQL;

-- Atomic task claim function
CREATE OR REPLACE FUNCTION claim_task(p_channel_id UUID)
RETURNS TABLE(task_id UUID, title TEXT, channel_name TEXT) AS $$
    UPDATE tasks
    SET status = 'processing',
        claimed_at = NOW(),
        updated_at = NOW()
    WHERE id = (
        SELECT id FROM tasks
        WHERE channel_id = p_channel_id
          AND status = 'queued'
        ORDER BY priority DESC, created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id, title, channel_name;
$$ LANGUAGE SQL;

-- LISTEN/NOTIFY trigger for instant worker wake-up
CREATE OR REPLACE FUNCTION notify_new_task()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('task_queue', json_build_object(
        'task_id', NEW.id,
        'channel_id', NEW.channel_id,
        'priority', NEW.priority
    )::TEXT);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER task_queue_notify
AFTER INSERT ON tasks
FOR EACH ROW
WHEN (NEW.status = 'queued')
EXECUTE FUNCTION notify_new_task();
```

**Performance Characteristics:**
- Task claim: <1ms
- Round-robin selection: <5ms
- Rate limit check: <0.5ms
- Status update: <1ms

**Trade-offs Accepted:**
- Data redundancy: ~50 bytes × 10K tasks = 500KB (negligible)
- No FK enforcement (application validates channel existence)
- Channel renames require migration script (rare operation)

**Phase 2 Migration Path:**
- Add table partitioning if scaling to 20+ channels or 100K+ tasks
- Partitioning provides query pruning and parallel scans

---

### **Decision 2: Database Migration Strategy**

**Choice:** Alembic with Manual Migrations

**Rationale:**
- Full control for zero-downtime operations (`CREATE INDEX CONCURRENTLY`)
- Critical for 24/7 worker operations
- Auto-generate as starting point, then manual refinement

**Implementation Pattern:**

```python
# alembic/versions/001_add_youtube_url.py
def upgrade():
    # Use CONCURRENTLY for zero-downtime index creation
    op.execute("""
        CREATE INDEX CONCURRENTLY idx_tasks_youtube_url
        ON tasks (youtube_url)
        WHERE youtube_url IS NOT NULL
    """)

    # Add column with default (safe for large tables)
    op.add_column('tasks',
        sa.Column('youtube_url', sa.Text(), nullable=True))

def downgrade():
    op.drop_index('idx_tasks_youtube_url')
    op.drop_column('tasks', 'youtube_url')
```

**Migration Workflow:**
```bash
# Generate starting point
alembic revision --autogenerate -m "description"

# Edit migration for production safety
# - Add CONCURRENTLY to index creation
# - Add NOT VALID to constraints
# - Split large migrations into smaller steps

# Apply migration
alembic upgrade head
```

---

### **Decision 3: Transaction Management Strategy**

**Choice:** Short Transactions + Idempotent Operations

**Rationale:**
- Prevents connection pool exhaustion during 10-minute Kling timeouts
- Scales well with multiple workers
- Standard pattern for queue systems

**Implementation Pattern:**

```python
async def process_video_generation(task_id: UUID):
    # Transaction 1: Claim task (fast, <1ms)
    async with db.begin():
        task = await claim_task_from_queue(task_id)
        if not task:
            return  # Already claimed by another worker

    # NO TRANSACTION: Long-running CLI script execution
    try:
        result = await run_cli_script(
            "scripts/generate_video.py",
            args=["--image", task.composite_url, "--output", task.video_path],
            timeout=600  # 10 minutes
        )
    except subprocess.TimeoutExpired:
        result = {"error": "Kling timeout after 10 minutes"}

    # Transaction 2: Update status (fast, <1ms)
    async with db.begin():
        if result.get("error"):
            await mark_task_failed(task_id, result["error"])
        else:
            await mark_task_completed(task_id, result["video_url"])
```

**Stale Task Cleanup:**

```python
# Background job runs every 5 minutes
async def cleanup_stale_tasks():
    """Mark tasks stuck in 'processing' for >15 minutes as failed"""
    async with db.begin():
        await db.execute("""
            UPDATE tasks
            SET status = 'failed',
                last_error = 'Worker timeout or crash',
                updated_at = NOW()
            WHERE status = 'processing'
              AND claimed_at < NOW() - INTERVAL '15 minutes'
        """)
```

**Benefits:**
- Worker crash doesn't hold database connections
- Connection pool sized for concurrent workers, not concurrent tasks
- Failed tasks automatically retried by stale task cleanup

---

## Authentication & Security

### **Decision 4: OAuth Token Storage**

**Choice:** PostgreSQL Database (Encrypted with Fernet)

**Rationale:**
- Tokens refresh every 50 minutes (frequent updates favor database)
- Database already persistent, no extra infrastructure
- Python `cryptography.fernet` provides simple symmetric encryption
- Encryption key stored in Railway secrets

**Implementation:**

```python
from cryptography.fernet import Fernet
from datetime import datetime, timedelta

class OAuthTokenManager:
    def __init__(self, encryption_key: str):
        self.fernet = Fernet(encryption_key.encode())

    async def store_tokens(self, channel_id: UUID, access_token: str,
                          refresh_token: str, expires_in: int):
        """Encrypt and store OAuth tokens"""
        encrypted_access = self.fernet.encrypt(access_token.encode()).decode()
        encrypted_refresh = self.fernet.encrypt(refresh_token.encode()).decode()
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        await db.execute("""
            INSERT INTO oauth_tokens (channel_id, access_token, refresh_token, expires_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (channel_id) DO UPDATE
            SET access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                updated_at = NOW()
        """, channel_id, encrypted_access, encrypted_refresh, expires_at)

    async def get_access_token(self, channel_id: UUID) -> str:
        """Retrieve and decrypt access token, refresh if needed"""
        row = await db.fetchrow("""
            SELECT access_token, refresh_token, expires_at
            FROM oauth_tokens
            WHERE channel_id = $1
        """, channel_id)

        if not row:
            raise ValueError(f"No OAuth tokens for channel {channel_id}")

        # Check if token expires in next 10 minutes
        if row['expires_at'] < datetime.utcnow() + timedelta(minutes=10):
            # Refresh token
            await self.refresh_tokens(channel_id, row['refresh_token'])
            return await self.get_access_token(channel_id)  # Recursive call

        # Decrypt and return
        return self.fernet.decrypt(row['access_token'].encode()).decode()
```

**Configuration:**

```bash
# Railway secrets
OAUTH_ENCRYPTION_KEY=<generate with Fernet.generate_key()>
```

---

### **Decision 5: Notion Webhook Security**

**Choice:** FastAPI Middleware Validation (HMAC)

**Rationale:**
- Centralized validation for all webhook endpoints
- Automatic protection via dependency injection
- FastAPI standard pattern

**Implementation:**

```python
import hmac
import hashlib
from fastapi import Depends, HTTPException, Request

async def validate_notion_signature(request: Request) -> bool:
    """Validate Notion webhook HMAC signature"""
    signature = request.headers.get("X-Notion-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")

    # Read raw body (before JSON parsing)
    body = await request.body()

    # Compute expected signature
    expected = hmac.new(
        settings.notion_webhook_secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    # Constant-time comparison (prevents timing attacks)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid signature")

    return True

@app.post("/webhook/notion")
async def notion_webhook(
    payload: dict,
    validated: bool = Depends(validate_notion_signature)
):
    """Handle Notion webhook events"""
    await enqueue_task(payload)
    return {"status": "queued"}
```

---

### **Decision 6: API Key Management**

**Choice:** Railway Secrets + Pydantic Settings

**Rationale:**
- Type-safe configuration
- Railway secrets in production (encrypted at rest)
- `.env` file for local development
- FastAPI/Pydantic best practice

**Implementation:**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str

    # AI Service API Keys
    gemini_api_key: str
    kie_api_key: str
    elevenlabs_api_key: str
    elevenlabs_voice_id: str

    # Notion
    notion_api_key: str
    notion_webhook_secret: str

    # YouTube OAuth
    youtube_client_id: str
    youtube_client_secret: str

    # Security
    oauth_encryption_key: str

    # Alerts
    slack_webhook_url: str | None = None

    # Environment
    environment: str = "production"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

---

## API & Communication Patterns

### **Decision 7: Error Response Format**

**Choice:** Custom Structured Format with request_id

**Rationale:**
- Simple to implement
- `request_id` critical for debugging multi-worker issues
- Error codes enable programmatic handling
- Timestamp for log correlation

**Format:**

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task with ID uuid-123 does not exist",
    "timestamp": "2026-01-09T10:30:00Z",
    "request_id": "req-abc123"
  }
}
```

**Implementation:**

```python
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
import uuid

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.detail.get("code", "INTERNAL_ERROR"),
                "message": exc.detail.get("message", str(exc.detail)),
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "request_id": request.state.request_id
            }
        }
    )

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add unique request_id to every request"""
    request.state.request_id = f"req-{uuid.uuid4().hex[:12]}"
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response
```

---

### **Decision 8: Logging Strategy**

**Choice:** Structured JSON Logging (structlog)

**Rationale:**
- Machine-readable logs
- Easy filtering by `task_id`, `channel_id`, `worker_id`
- Railway captures JSON automatically
- Correlate all logs for a single task

**Implementation:**

```python
import structlog

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()

# Usage in workers
async def process_asset_generation(task_id: UUID, channel_id: UUID):
    log = logger.bind(task_id=str(task_id), channel_id=str(channel_id),
                     worker_id=os.getpid())

    log.info("asset_generation_started", asset_count=22)

    try:
        result = await run_cli_script("scripts/generate_asset.py", args)
        log.info("asset_generation_completed", duration_seconds=45.2)
    except Exception as e:
        log.error("asset_generation_failed", error=str(e), exc_info=True)
        raise
```

**Log Output:**

```json
{
  "event": "asset_generation_started",
  "task_id": "uuid-123",
  "channel_id": "uuid-456",
  "worker_id": 42,
  "asset_count": 22,
  "timestamp": "2026-01-09T10:30:00.123Z",
  "level": "info"
}
```

---

### **Decision 9: Notion Status Update Pattern**

**Choice:** Fire-and-Forget with Mandatory Retry Logic

**Rationale:**
- Workers never blocked by Notion API (3 req/sec limit)
- Fast processing (video generation not delayed by Notion updates)
- Failed updates don't stop video generation
- Retry logic ensures eventual consistency

**Critical Requirement:** Implement retry logic for failed Notion updates (separate from task retry)

**Implementation:**

```python
from fastapi import BackgroundTasks

async def update_task_status(task_id: UUID, status: str,
                             background_tasks: BackgroundTasks):
    """Update database immediately, sync to Notion asynchronously"""

    # Transaction 1: Update database (fast)
    async with db.begin():
        await db.execute("""
            UPDATE tasks
            SET status = $1, updated_at = NOW()
            WHERE id = $2
        """, status, task_id)

    # Fire-and-forget: Queue Notion update
    background_tasks.add_task(sync_to_notion, task_id, status)

async def sync_to_notion(task_id: UUID, status: str, retry_count: int = 0):
    """Sync task status to Notion with retry logic"""
    try:
        task = await db.fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)

        await notion_client.pages.update(
            page_id=task['notion_page_id'],
            properties={
                "Status": {"select": {"name": status}},
                "Updated": {"date": {"start": datetime.utcnow().isoformat()}}
            }
        )

        # Mark as synced
        await db.execute("""
            UPDATE tasks
            SET notion_synced_at = NOW()
            WHERE id = $1
        """, task_id)

        logger.info("notion_sync_success", task_id=str(task_id), status=status)

    except Exception as e:
        logger.error("notion_sync_failed", task_id=str(task_id),
                    retry_count=retry_count, error=str(e))

        # Retry with exponential backoff (max 3 attempts)
        if retry_count < 3:
            await asyncio.sleep(2 ** retry_count)  # 1s, 2s, 4s
            await sync_to_notion(task_id, status, retry_count + 1)
        else:
            # Terminal failure - send alert
            await alert_notion_sync_failure(task_id, status, str(e))
```

---

## Infrastructure & Deployment

### **Decision 10: CI/CD Pipeline**

**Choice:** Railway Auto-Deploy with Protected Main Branch

**Rationale:**
- Zero-config deployment (Railway watches main branch)
- Safety through PR workflow (tests run before merge)
- Fast iteration (automatic after merge)

**GitHub Actions Workflow:**

```yaml
# .github/workflows/pr-checks.yml
name: PR Checks
on:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install uv
          uv sync

      - name: Run tests
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost/test
        run: pytest tests/ -v --cov=orchestrator --cov=workers

  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - run: |
          pip install uv
          uv sync
          mypy orchestrator/ workers/

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - run: |
          pip install uv
          uv sync
          ruff check orchestrator/ workers/
```

**Workflow:**
1. Create feature branch
2. Make changes, commit
3. Create PR
4. GitHub Actions run tests/type-check/lint
5. Merge to main (only if checks pass)
6. Railway auto-deploys to production

---

### **Decision 11: Environment Management**

**Choice:** Single Production Environment (Start Simple)

**Rationale:**
- Simple, no staging complexity
- Test locally before deploying
- Railway secrets for production, `.env` for dev

**Configuration:**

```python
class Settings(BaseSettings):
    environment: str = "production"
    database_url: str
    log_level: str = "INFO"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    class Config:
        env_file = ".env"

settings = Settings()
```

---

### **Decision 12: Worker Scaling Strategy**

**Choice:** Fixed Worker Count (3 Workers)

**Rationale:**
- Predictable cost (~$5-10/month for 3 workers)
- Sufficient for 100 videos/week target
- Simple to reason about

**Configuration:**

```toml
# railway.toml
[[services]]
name = "workers"
startCommand = "python workers/worker.py --workers 3"
```

**Capacity:**
- 3 workers × parallel limits = 12 Gemini, 5-8 Kling, 6 ElevenLabs concurrent
- Bottleneck: Kling (5-8 concurrent)
- Throughput: ~60-100 videos/day

---

### **Decision 13: Monitoring & Alerting**

**Choice:** Structured Logging + Slack Alerts

**Rationale:**
- Proactive notification of critical failures
- Free (Slack webhook)
- Sufficient for solo developer

**Alert Triggers:**
1. Worker crash (no heartbeat for 5 minutes)
2. API quota exhausted
3. Task terminal failure (retry exhausted)
4. Rate limit violations

**Implementation:**

```python
class SlackAlerter:
    def __init__(self, webhook_url: str | None):
        self.webhook_url = webhook_url
        self.enabled = webhook_url is not None

    async def alert(self, message: str, level: str = "warning"):
        """Send alert to Slack"""
        if not self.enabled:
            return

        emoji = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "critical": "🚨"}.get(level, "ℹ️")

        async with httpx.AsyncClient() as client:
            await client.post(
                self.webhook_url,
                json={"text": f"{emoji} {message}"}
            )

# Usage
await alerter.alert(
    f"Task {task_id} failed after 4 retries: {error}",
    level="error"
)
```

---

## Decision Impact Analysis

**Implementation Sequence:**

1. **Phase 1: Database & Core Infrastructure**
   - Create PostgreSQL schema (Decision 1)
   - Set up Alembic migrations (Decision 2)
   - Configure Pydantic Settings (Decision 6)
   - Implement structured logging (Decision 8)

2. **Phase 2: Security & Authentication**
   - Implement OAuth token encryption (Decision 4)
   - Add Notion webhook validation (Decision 5)
   - Set up Railway secrets

3. **Phase 3: Orchestrator**
   - FastAPI webhook endpoint
   - Error response format (Decision 7)
   - Notion status updates with retry (Decision 9)

4. **Phase 4: Workers**
   - Worker main loop (short transactions, Decision 3)
   - CLI script wrappers
   - Pipeline step handlers

5. **Phase 5: Deployment**
   - Set up GitHub Actions (Decision 10)
   - Configure Railway (Decision 11, 12)
   - Implement Slack alerts (Decision 13)

**Cross-Component Dependencies:**

- **Database schema** affects: Workers, Orchestrator, Migrations
- **OAuth tokens** affects: YouTube upload worker, Token refresh job
- **Structured logging** affects: All components (standardized format)
- **Error format** affects: Orchestrator endpoints, Worker error handling
- **Notion updates** affects: All workers (status synchronization)

**Critical Path Dependencies:**

```
Database Schema (1)
    ↓
Transaction Management (3)
    ↓
Workers Implementation
    ↓
CI/CD Pipeline (10)
    ↓
Production Deployment
```

---
