# Starter Template Evaluation

## Primary Technology Domain

**Brownfield Python Extension** - Adding FastAPI orchestration layer + PostgreSQL queue + Python workers to existing CLI pipeline

**Context:** This is not a greenfield "starter template" scenario. The project already has 7 production Python CLI scripts that must remain unchanged. The evaluation focuses on best practices for extending the existing architecture with orchestration capabilities.

## Architectural Approach Evaluated

**Three Options Analyzed:**

1. **Pure Python Stack (FastAPI + PostgreSQL + Python Workers)**
   - Hosting: Railway ($5/month)
   - Single language, single codebase
   - Natural fit for existing Python CLI scripts

2. **Hybrid Stack (Node.js Orchestrator + Python Workers)**
   - Hosting: Vercel (free) + Railway ($5/month)
   - Two languages, two codebases
   - Cost optimization at expense of complexity

3. **Python on Render Free Tier**
   - Hosting: Render (free with limitations)
   - 15-minute auto-sleep (breaks webhooks)
   - Requires ping service workarounds

## Selected Approach: Pure Python Stack on Railway

**Rationale for Selection:**

1. **Architectural Continuity:** Extends proven "Smart Agent + Dumb Scripts" pattern with Python orchestration layer rather than introducing Node.js complexity

2. **Natural Integration:** Python workers calling Python CLI scripts via subprocess is idiomatic and maintainable

3. **Single Language Simplicity:** Avoids cross-language debugging, dual deployment pipelines, and team knowledge fragmentation

4. **Production-Ready Compute:** Railway provides persistent processes (no cold starts), 10-minute+ timeouts (Kling compatibility), and no auto-sleep issues

5. **Cost-Benefit Analysis:** $5/month is negligible compared to 50-100 hours of additional development time and 2x maintenance burden of hybrid architecture

**Key Technical Decisions:**

- **Orchestrator Framework:** FastAPI (async webhook handling, modern Python)
- **Queue System:** PostgreSQL + PgQueuer (LISTEN/NOTIFY, no Redis dependency)
- **Worker Pattern:** Direct PostgreSQL polling with independent Python processes
- **Database:** PostgreSQL (persistent queue + state tracking)
- **Rate Limiting:** PostgreSQL-based (simpler than Redis for AI API rate limits)
- **Deployment:** Railway (persistent compute, $5/month, includes PostgreSQL)

## Technology Stack Summary

| Component | Technology | Version/Details | Justification |
|-----------|-----------|-----------------|---------------|
| **Orchestrator** | FastAPI | Latest stable | Async webhook handling, native Python, modern framework |
| **Queue Management** | PgQueuer | Latest (Python 3.11+) | PostgreSQL LISTEN/NOTIFY, eliminates polling, lightweight |
| **Database** | PostgreSQL | 12+ | Persistent queue, state tracking, rate limit counters |
| **Workers** | Python processes | 3.10+ | Direct queue polling, subprocess management |
| **Subprocess Handling** | threading + subprocess | Python stdlib | Non-blocking CLI script execution |
| **Multi-tenancy** | Tenant discriminator | Pattern | `channel_id` on every row, fair round-robin queueing |
| **HTTP Client** | httpx | Latest | Async HTTP for Notion/YouTube APIs |
| **ORM** | SQLAlchemy | 2.0+ | Async database operations |
| **Environment Config** | python-dotenv | Existing | Consistent with current scripts |
| **Hosting** | Railway | Hobby plan ($5/mo) | Persistent compute, includes PostgreSQL |

## Project Structure for Extension

**Recommended Organization (Module-Functionality Pattern):**

```
ai-video-generator/
├── scripts/                           # EXISTING - UNCHANGED
│   ├── generate_asset.py
│   ├── create_composite.py
│   ├── generate_video.py
│   ├── generate_audio.py
│   ├── generate_sound_effects.py
│   ├── assemble_video.py
│   ├── youtube_auth.py
│   └── .env
│
├── orchestrator/                      # NEW - FastAPI Service
│   ├── main.py                        # FastAPI app entry point
│   ├── api/
│   │   ├── webhooks.py               # Notion webhook endpoints
│   │   ├── health.py                 # Health check endpoints
│   │   └── admin.py                  # Admin management endpoints
│   ├── services/
│   │   ├── notion.py                 # Notion API client
│   │   ├── queue.py                  # Queue management (PgQueuer)
│   │   ├── youtube.py                # YouTube OAuth management
│   │   └── rate_limit.py             # Rate limit coordinator
│   ├── models/
│   │   ├── task.py                   # SQLAlchemy task model
│   │   ├── rate_limit.py             # Rate limit counters
│   │   └── channel.py                # Channel configuration
│   ├── schemas/
│   │   ├── task.py                   # Pydantic task schemas
│   │   └── webhook.py                # Webhook payload schemas
│   └── core/
│       ├── config.py                 # Configuration management
│       ├── database.py               # Database connection
│       └── dependencies.py           # Dependency injection
│
├── workers/                           # NEW - Background Workers
│   ├── worker.py                     # Main worker process
│   ├── handlers/                     # Pipeline step handlers
│   │   ├── asset_generation.py      # Calls scripts/generate_asset.py
│   │   ├── video_generation.py      # Calls scripts/generate_video.py
│   │   ├── audio_generation.py      # Calls scripts/generate_audio.py
│   │   ├── assembly.py               # Calls scripts/assemble_video.py
│   │   └── upload.py                 # YouTube upload handler
│   ├── cli_wrapper.py                # Subprocess management utility
│   └── retry.py                      # Exponential backoff retry logic
│
├── channels.yaml                      # Channel configuration file
├── workspaces/                        # Asset storage (existing pattern)
│   └── {channel_id}/{task_id}/
├── pyproject.toml                     # New dependencies
├── railway.toml                       # Railway deployment config
└── README.md
```

## Architectural Decisions Established by This Approach

### **1. Language & Runtime**

- **Python 3.10+** throughout (orchestrator + workers + existing scripts)
- **FastAPI** for async HTTP handling (webhook endpoints)
- **asyncio** for I/O-bound operations (database, API calls)
- **threading + subprocess** for CLI script execution within workers

### **2. Database & Queue Architecture**

- **PostgreSQL** as single source of truth (queue + state + rate limits)
- **PgQueuer** library for queue management:
  - `FOR UPDATE SKIP LOCKED` - Lock-free concurrent task claiming
  - `LISTEN/NOTIFY` - Instant worker wake-up (no polling)
  - Supports both sync and async PostgreSQL drivers
- **Tenant discriminator pattern** - `channel_id` column on all tables
- **Fair round-robin queueing** - Prevent channel starvation

### **3. Worker Pool Pattern**

- **Independent Python processes** (not Celery, not RQ)
- **Direct PostgreSQL polling** via PgQueuer
- **Horizontal scaling** - Launch more worker processes as needed
- **Process-level isolation** - One worker crash doesn't affect others
- **State persistence** - Queue survives worker restarts

### **4. Multi-Channel Orchestration**

- **Channel configuration file** (`channels.yaml`) - Per-channel settings
- **Isolated channel queues** - Failures don't cross channels
- **Per-channel OAuth tokens** - Stored in configuration or secrets manager
- **Round-robin scheduling** - Fair distribution across channels
- **Global rate limit tracking** - Coordinated across all workers

### **5. Rate Limiting Strategy**

- **PostgreSQL-based** (start) - Simpler than Redis for AI API limits (3-10 req/sec)
- **Atomic counters** via `ON CONFLICT DO UPDATE`
- **Shared across workers** - All workers see same limit state
- **Per-service tracking** - Gemini, Kling, ElevenLabs, Notion, YouTube
- **Future Redis migration path** if performance bottleneck identified

### **6. Subprocess Management**

- **threading + subprocess.run()** within worker processes
- **Complete argument passing** - Workers provide full args to CLI scripts
- **Timeout handling** - 10-minute max for Kling, configurable per service
- **Output capture** - stdout/stderr logged for debugging
- **Error propagation** - Non-zero exit codes trigger retry logic

### **7. Error Handling & Retry**

- **Exponential backoff** - 1min → 5min → 15min → 1hr
- **Transient vs permanent detection** - Retry strategy differs
- **Resume from failure** - Don't regenerate completed assets
- **Retry state tracking** - PostgreSQL stores attempt count, next retry time
- **Alert on terminal failure** - Slack/email after retry exhaustion

### **8. Development Experience**

- **Hot reload** - FastAPI development server with auto-reload
- **Type safety** - Pydantic schemas for validation
- **Database migrations** - Alembic for schema changes
- **Testing infrastructure** - pytest for unit/integration tests
- **Logging** - Structured logging for debugging

## Deployment Configuration

### **Railway Setup**

**Initial Deployment:**

```bash
# Install Railway CLI
npm install -g railway

# Login and link project
railway login
railway init

# Configure services
railway add --database postgres
railway add --service orchestrator
railway add --service workers

# Deploy
railway up
```

**railway.toml:**

```toml
[build]
builder = "NIXPACKS"
buildCommand = "pip install -r requirements.txt"

[deploy]
startCommand = "uvicorn orchestrator.main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10

[[services]]
name = "orchestrator"
source = "."

[[services]]
name = "workers"
source = "."
startCommand = "python workers/worker.py --workers 3"

[[services]]
name = "postgres"
image = "postgres:15"
```

### **Environment Variables (Railway Secrets):**

```bash
# Database
DATABASE_URL=postgresql://...  # Provided by Railway

# API Keys
GEMINI_API_KEY=...
KIE_API_KEY=...
ELEVENLABS_API_KEY=...

# Notion
NOTION_API_KEY=...
NOTION_WEBHOOK_SECRET=...

# YouTube OAuth (per channel)
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...

# Alert System
SLACK_WEBHOOK_URL=...
```

## Key Dependencies

**New Dependencies (add to pyproject.toml):**

```toml
[project]
dependencies = [
    # Existing
    "google-generativeai>=0.8.0",
    "python-dotenv>=1.0.0",
    "pillow>=10.0.0",
    "pyjwt>=2.8.0",
    "requests>=2.31.0",

    # NEW - Orchestrator
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "httpx>=0.27.0",

    # NEW - Database & Queue
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.29.0",
    "pgqueuer>=0.12.0",
    "alembic>=1.13.0",

    # NEW - Validation & Config
    "pydantic>=2.8.0",
    "pydantic-settings>=2.4.0",

    # NEW - Utilities
    "pyyaml>=6.0.0",
]
```

## Migration Path from Current Architecture

**Phase 1: Setup Infrastructure**
1. Create Railway account, provision PostgreSQL database
2. Set up orchestrator/ and workers/ directories
3. Add new dependencies to pyproject.toml
4. Create database schema (tasks, rate_limits, channels)

**Phase 2: Implement Orchestrator**
1. FastAPI app with webhook endpoint
2. Notion API integration (read/write)
3. Task enqueueing logic
4. Health check endpoints

**Phase 3: Implement Workers**
1. Worker main loop (poll queue)
2. CLI script wrapper (subprocess management)
3. Pipeline step handlers (asset, video, audio, assembly, upload)
4. Retry logic and error handling

**Phase 4: Integration**
1. Configure channels.yaml with first test channel
2. Set up Notion database structure
3. YouTube OAuth flow for test channel
4. Deploy to Railway

**Phase 5: Testing & Validation**
1. End-to-end test: Notion entry → Published YouTube video
2. Validate auto-retry on transient failures
3. Test multi-channel orchestration (2-3 channels)
4. Performance tuning (parallelism limits, rate limits)

**Phase 6: Production Rollout**
1. Add remaining channels (up to 10)
2. Enable monitoring and alerts
3. Optimize cost (worker count, parallelism)
4. Document operational runbooks

## Alternative Considered: Hybrid Vercel + Railway

**Why Not Selected:**

- **Increased Complexity:** Two languages (Node.js + Python), two codebases, two deployment pipelines
- **Marginal Cost Savings:** $0/month savings (Vercel free vs Railway $5) not worth 50-100 hours of additional dev time
- **Cross-Language Awkwardness:** Node.js calling Python subprocess less natural than Python→Python
- **Maintenance Burden:** 2x ongoing maintenance (two languages, two frameworks)
- **Team Knowledge:** Requires Node.js expertise in addition to Python
- **Commercial Use Risk:** Vercel Hobby plan is personal/non-commercial only

**When This Alternative Makes Sense:**

- Team already has strong Node.js expertise
- Orchestrator logic becomes complex enough to benefit from Node.js ecosystem
- Cost sensitivity absolute (every $5/month matters)
- Willingness to accept 2x maintenance complexity

## Research Sources

This evaluation is based on comprehensive research of current (2025) best practices:

**FastAPI Project Structure:**
- [FastAPI Best Practices (GitHub)](https://github.com/zhanymkanov/fastapi-best-practices)
- [Structuring a FastAPI Project: Best Practices](https://dev.to/mohammad222pr/structuring-a-fastapi-project-best-practices-53l6)
- [FastAPI Project Structure for Large Applications (2026)](https://medium.com/@devsumitg/the-perfect-structure-for-a-large-production-ready-fastapi-app-78c55271d15c)

**PostgreSQL Queue Management:**
- [PgQueuer: PostgreSQL-leveraging job queuing](https://github.com/janbjorge/pgqueuer)
- [Procrastinate: PostgreSQL-based Task Queue](https://github.com/procrastinate-org/procrastinate)
- [Using an SQL database as a job queue](https://www.mgaillard.fr/2024/12/01/job-queue-postgresql.html)

**Multi-Tenant Queue Management:**
- [Build multi-tenant task queues using PostgreSQL and Python](https://lalokalabs.co/en/events/build-multi-tenant-task-queues-using-postgresql-and-python-pyconid/)
- [An unfair advantage: multi-tenant queues in Postgres](https://docs.hatchet.run/blog/multi-tenant-queues)
- [Multi-tenancy implementation with PostgreSQL](https://blog.logto.io/implement-multi-tenancy)

**Hosting Platform Comparisons:**
- [Railway Pricing 2025](https://railway.com/pricing)
- [Render vs Vercel (2025)](https://northflank.com/blog/render-vs-vercel)
- [Vercel Backend Limitations](https://northflank.com/blog/vercel-backend-limitations)
- [FastAPI Deployment Options](https://render.com/articles/fastapi-deployment-options)

---
