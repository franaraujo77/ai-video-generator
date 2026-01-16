---
story_key: '4-1-worker-process-foundation'
epic_id: '4'
story_id: '1'
title: 'Worker Process Foundation'
status: 'ready-for-dev'
priority: 'critical'
story_points: 8
created_at: '2026-01-16'
assigned_to: 'Claude Sonnet 4.5'
dependencies: ['1-1-database-foundation-channel-model', '2-1-task-model-database-schema', '3-1-cli-script-wrapper-async-execution']
blocks: ['4-2-task-claiming-with-pgqueuer', '4-3-priority-queue-management']
ready_for_dev: false
ready_for_review: false
---

# Story 4.1: Worker Process Foundation

**Epic:** 4 - Worker Orchestration & Parallel Processing
**Priority:** Critical (Foundation for Multi-Channel Video Processing)
**Story Points:** 8 (Complex worker architecture with PostgreSQL integration and async execution)
**Status:** READY FOR DEVELOPMENT

## Story Description

**As a** system administrator,
**I want** independent worker processes that can be scaled horizontally,
**So that** I can add processing capacity by launching more workers (FR38).

## Context & Background

The worker process foundation is the **FIRST STORY in Epic 4** and establishes the core architecture for multi-channel video processing at scale. It creates the fundamental worker process structure that will later integrate with PgQueuer for task claiming (Story 4.2) and implement the full 8-step video generation pipeline.

**Critical Requirements:**

1. **Separate Process Architecture**: Each worker runs as an independent Python process (worker-1, worker-2, worker-3 on Railway)
2. **Async Execution**: All database operations and I/O must use async/await patterns to prevent blocking
3. **Short Transaction Pattern**: Claim task → close DB → process → reopen DB → update (NEVER hold DB during long operations)
4. **Horizontal Scalability**: Stateless design allows adding more workers dynamically (worker-4, worker-5, etc.)
5. **Railway Deployment**: Workers run as separate Railway services with shared PostgreSQL database
6. **Entry Point**: `app/worker.py` serves as worker process entry point, runs continuous event loop
7. **Database Integration**: Workers use SQLAlchemy 2.0 async patterns with asyncpg driver

**Why Worker Foundation is Critical:**

- **Parallel Processing**: Multiple channels can generate videos simultaneously (5-10 concurrent channels)
- **Horizontal Scaling**: Add capacity by launching more worker processes on Railway ($5/month per worker)
- **Fault Isolation**: One worker crash doesn't affect other workers or the web service
- **Performance**: 3 workers can handle 100 videos/week (14.3 videos/day average) across multiple channels
- **Foundation for Future Stories**: Task claiming (Story 4.2), priority queues (Story 4.3), and orchestration (Story 4.8) build on this foundation

**Referenced Architecture:**

- Architecture: Worker Process Design - Separate Processes (3 independent Python processes)
- Architecture: Database Architecture - Connection pooling (pool_size=10, max_overflow=5, pool_pre_ping=True)
- Architecture: Short Transaction Pattern (Architecture Decision 3) - CRITICAL
- project-context.md: Critical Implementation Rules (lines 56-119)
- PRD: FR38 (Horizontal scaling via multiple independent worker processes)
- PRD: NFR-PER-001 (Async I/O throughout backend for non-blocking execution)

**Key Architectural Pattern (From Stories 3.1-3.8):**

The worker foundation follows the "Short Transaction Pattern" established in Epic 3:

```python
# Step 1: Claim task (short transaction)
async with AsyncSessionLocal() as db:
    task = await db.get(Task, task_id)
    task.status = "processing"
    await db.commit()

# Step 2: Process (OUTSIDE transaction - could be minutes)
result = await process_pipeline_step(task)

# Step 3: Update task (short transaction)
async with AsyncSessionLocal() as db:
    task = await db.get(Task, task_id)
    task.status = "completed"
    await db.commit()
```

**Worker Process Architecture (From Architecture Document):**

- **Deployment**: 3 Railway services (worker-1, worker-2, worker-3), each running `python -m app.worker`
- **Task Claiming**: Independent claiming via PgQueuer FOR UPDATE SKIP LOCKED (Story 4.2 will implement)
- **Database**: Shared PostgreSQL with connection pooling (pool_size=10, supports 3 workers + web service)
- **Scaling**: Stateless design, add more workers dynamically by creating worker-4, worker-5, etc.
- **Entry Point**: `app/worker.py` runs continuous loop, exits on SIGTERM for graceful shutdown

**Existing Implementation Analysis (from Stories 3.1-3.8):**

Epic 3 established the complete 8-step video generation pipeline with 8 service modules:
- Story 3.1: CLI script wrapper (`app/utils/cli_wrapper.py`)
- Story 3.2: Filesystem helpers (`app/utils/filesystem.py`)
- Story 3.3: Asset generation service (`app/services/asset_generation.py`)
- Story 3.4: Composite creation service (`app/services/composite_creation.py`)
- Story 3.5: Video generation service (`app/services/video_generation.py`)
- Story 3.6: Narration generation service (`app/services/narration_generation.py`)
- Story 3.7: Sound effects generation service (`app/services/sound_effects_generation.py`)
- Story 3.8: Video assembly service (`app/services/video_assembly.py`)

Each service implements a step-specific worker function (e.g., `process_asset_generation_task()`). Story 4.1 creates the foundational worker process that will orchestrate these services.

**Database Schema (Existing from Epic 1 & 2):**

- **channels** table (Story 1.1): Channel configuration with encrypted credentials
- **tasks** table (Story 2.1): Task tracking with 9-state workflow (pending → claimed → processing → awaiting_review → approved/rejected → completed/failed/retry)
- **videos** table (Story 2.1): Video metadata and file paths
- **video_costs** table (Story 3.3): Per-component cost tracking
- **audit_logs** table (Story 1.1): Compliance logging for human actions

**Deployment Configuration (Railway):**

```yaml
# railway.json structure (to be created in Story 4.1)
services:
  web:
    build: {dockerfile: "Dockerfile"}
    start: "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    healthcheck: "/health"

  worker-1:
    build: {dockerfile: "Dockerfile"}
    start: "python -m app.worker"

  worker-2:
    build: {dockerfile: "Dockerfile"}
    start: "python -m app.worker"

  worker-3:
    build: {dockerfile: "Dockerfile"}
    start: "python -m app.worker"

  postgres:
    image: "postgres:16"
```

**Derived from Previous Stories (Epic 3 Learnings):**

- ✅ Short transaction pattern successfully used in all 8 Epic 3 stories (commits: 1314620, a85176e, f799965)
- ✅ Async execution prevents event loop blocking (all services use `async/await`)
- ✅ Service layer pattern established (business logic in `app/services/`, orchestration in workers)
- ✅ Structured logging with correlation IDs (`structlog` JSON format)
- ✅ CLI wrapper pattern (`run_cli_script()` with timeout handling)
- ✅ Filesystem helpers prevent path traversal attacks (regex validation)
- ✅ Error handling with retry classification (retriable vs non-retriable)

**Key Technical Decisions:**

1. **No PgQueuer in Story 4.1**: Task claiming with PgQueuer is Story 4.2. Story 4.1 creates the worker loop structure only.
2. **Worker Entry Point**: `app/worker.py` is the entry point, imports and calls pipeline orchestrator (Story 3.9 or Story 4.8)
3. **Graceful Shutdown**: Workers listen for SIGTERM signal to finish current task before exiting
4. **Connection Pooling**: Shared pool across workers (pool_size=10 sufficient for 3 workers + web service)
5. **Local Development**: Workers can run in separate terminals with `python -m app.worker` for testing

## Acceptance Criteria

### Scenario 1: Worker Process Startup and Initialization
**Given** Railway worker service (worker-1) starts with `python -m app.worker`
**When** the worker process initializes
**Then** the worker should:
- ✅ Load configuration from environment variables (DATABASE_URL, FERNET_KEY)
- ✅ Initialize async database engine with connection pooling (pool_size=10, max_overflow=5, pool_pre_ping=True)
- ✅ Initialize structured logging with worker identifier (worker_id) in all log messages
- ✅ Log startup message with worker_id and configuration summary
- ✅ Enter continuous event loop waiting for work
- ✅ Not exit unless SIGTERM received or fatal error occurs

### Scenario 2: Database Connection Pool Configuration
**Given** 3 workers (worker-1, worker-2, worker-3) and 1 web service share PostgreSQL
**When** workers initialize database connections
**Then** the connection pool should:
- ✅ Use `create_async_engine()` with DATABASE_URL from environment
- ✅ Configure pool_size=10 (supports 3 workers + web service concurrent operations)
- ✅ Configure max_overflow=5 (burst capacity for peak load)
- ✅ Configure pool_timeout=30 seconds (fail fast on exhaustion)
- ✅ Configure pool_pre_ping=True (handle Railway connection recycling)
- ✅ Use asyncpg driver (postgresql+asyncpg:// protocol)
- ✅ Share single engine instance across all worker operations

### Scenario 3: Async Session Factory for Workers
**Given** worker needs to interact with database
**When** worker creates database session
**Then** the session factory should:
- ✅ Use `async_sessionmaker()` with AsyncSession class
- ✅ Configure expire_on_commit=False (prevent lazy loading issues)
- ✅ Support context manager pattern: `async with session_factory() as session:`
- ✅ Auto-close session after context manager exits
- ✅ Support multiple concurrent sessions from same worker
- ✅ Not use `Depends()` pattern (that's for FastAPI routes only)

### Scenario 4: Graceful Shutdown on SIGTERM
**Given** worker is running continuous event loop
**When** Railway sends SIGTERM signal (e.g., during deployment)
**Then** the worker should:
- ✅ Catch SIGTERM signal with signal handler
- ✅ Set shutdown flag to stop accepting new work
- ✅ Wait for current task to complete (if any in progress)
- ✅ Close database connections gracefully
- ✅ Log shutdown message with worker_id
- ✅ Exit with code 0 (successful shutdown)
- ✅ Timeout after 30 seconds if task doesn't complete (Railway timeout)

### Scenario 5: Worker Process Continuous Loop (Placeholder Pattern)
**Given** worker has initialized and entered event loop
**When** the worker runs its main loop
**Then** the worker should:
- ✅ Run infinite `while not shutdown_requested:` loop
- ✅ Sleep briefly between iterations (e.g., 1 second) to prevent CPU spinning
- ✅ Log periodic heartbeat messages (every 60 seconds) confirming worker is alive
- ✅ Catch and log any unexpected exceptions without crashing
- ✅ Continue running until SIGTERM received
- ✅ **Note**: Task claiming logic (PgQueuer integration) will be added in Story 4.2

### Scenario 6: Structured Logging with Worker Identification
**Given** worker is processing tasks or running event loop
**When** any log message is generated
**Then** the structured log should include:
- ✅ worker_id: Unique identifier for this worker process (e.g., "worker-1", "worker-2")
- ✅ timestamp: ISO 8601 timestamp
- ✅ level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- ✅ message: Human-readable log message
- ✅ correlation_id: Task ID when processing a specific task
- ✅ JSON format: All logs output as JSON for Railway log aggregation
- ✅ stdout: All logs go to stdout (Railway captures automatically)

### Scenario 7: Multiple Workers Run Independently
**Given** 3 workers (worker-1, worker-2, worker-3) are running on Railway
**When** all workers are operational
**Then** the system should demonstrate:
- ✅ Each worker runs in separate Railway service container
- ✅ Workers do not communicate with each other directly
- ✅ Workers share same PostgreSQL database via connection pool
- ✅ Workers can start/stop independently without affecting others
- ✅ One worker crash does not impact other workers
- ✅ Workers can be scaled by adding worker-4, worker-5, etc.

### Scenario 8: Local Development Testing
**Given** developer wants to test worker locally
**When** developer runs `python -m app.worker` in terminal
**Then** the worker should:
- ✅ Start successfully with local DATABASE_URL (sqlite or local postgres)
- ✅ Log startup message to console
- ✅ Run event loop and log heartbeat messages
- ✅ Exit gracefully on Ctrl+C (SIGINT signal)
- ✅ Support running multiple workers in separate terminals for testing
- ✅ Share same local database as web service (if running)

### Scenario 9: Railway Deployment Configuration
**Given** Railway project with worker services defined
**When** `railway.json` is deployed
**Then** Railway should:
- ✅ Create 3 separate worker services (worker-1, worker-2, worker-3)
- ✅ Build all services from same Dockerfile
- ✅ Set start command for workers: `python -m app.worker`
- ✅ Set start command for web: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- ✅ Inject DATABASE_URL environment variable into all services
- ✅ Share PostgreSQL service across web + 3 workers
- ✅ Auto-restart workers on crash (Railway default behavior)

### Scenario 10: Worker Error Handling and Recovery
**Given** worker encounters unexpected exception in main loop
**When** exception is raised
**Then** the worker should:
- ✅ Catch exception in main loop try/except block
- ✅ Log error with full stack trace and worker_id
- ✅ NOT crash the worker process
- ✅ Continue running event loop after logging error
- ✅ Track consecutive error count (alert if >10 errors in 1 minute)
- ✅ Only exit on fatal errors (database unreachable, configuration invalid)

## Technical Specifications

### File Structure
```
app/
├── __init__.py
├── worker.py                      # NEW - Worker process entry point
├── database.py                    # MODIFY - Add worker-specific session patterns
├── config.py                      # EXISTING - Configuration loading
├── models.py                      # EXISTING - SQLAlchemy models
└── utils/
    └── logging.py                 # EXISTING (Story 3.1) - Structured logging

railway.json                       # NEW - Railway deployment configuration
Dockerfile                         # MODIFY - Support both web and worker start commands
```

### Core Implementation: `app/worker.py`

**Purpose:** Entry point for worker process, runs continuous event loop with graceful shutdown.

**Required Implementation:**

```python
"""
Worker process entry point for ai-video-generator orchestration platform.

This module implements the foundational worker process that runs as separate Railway
services (worker-1, worker-2, worker-3). Workers execute video generation pipeline
tasks using the services established in Epic 3.

Architecture Pattern:
    - Separate Process: Each worker runs as independent Python process
    - Async Execution: All database operations use async/await patterns
    - Short Transactions: Claim → close DB → process → reopen DB → update
    - Graceful Shutdown: Listens for SIGTERM, finishes current task, exits cleanly

Usage:
    Local Development:
        python -m app.worker

    Railway Deployment:
        Automatic via railway.json configuration
        Start command: python -m app.worker

References:
    - Architecture: Worker Process Design - Separate Processes
    - Architecture: Short Transaction Pattern (Architecture Decision 3)
    - project-context.md: Critical Implementation Rules (lines 56-119)
"""

import asyncio
import signal
import sys
import os
from typing import Optional
from datetime import datetime

from app.database import async_engine, AsyncSessionLocal
from app.utils.logging import get_logger
from app.config import get_config

# Initialize structured logger
log = get_logger(__name__)

# Shutdown flag (set by SIGTERM handler)
shutdown_requested = False


def signal_handler(signum: int, frame) -> None:
    """
    Handle SIGTERM signal for graceful shutdown.

    When Railway deploys new version or stops service, it sends SIGTERM.
    Worker should finish current task and exit cleanly within 30 seconds.

    Args:
        signum: Signal number (typically SIGTERM = 15)
        frame: Current stack frame (unused)

    Side Effects:
        Sets global shutdown_requested flag to True
    """
    global shutdown_requested
    log.info(
        "shutdown_signal_received",
        signal=signum,
        signal_name=signal.Signals(signum).name
    )
    shutdown_requested = True


async def worker_main_loop() -> None:
    """
    Main worker event loop - runs continuously until SIGTERM received.

    This function implements the foundational worker loop structure.
    Task claiming and processing will be added in future stories:
        - Story 4.2: PgQueuer integration for task claiming
        - Story 4.8: Full pipeline orchestration

    Current Behavior (Story 4.1):
        - Logs heartbeat every 60 seconds
        - Sleeps 1 second between iterations
        - Exits gracefully on shutdown signal

    Future Behavior (Story 4.2+):
        - Claim tasks from PgQueuer (FOR UPDATE SKIP LOCKED)
        - Process claimed tasks via pipeline orchestrator
        - Update task status after completion

    Error Handling:
        - Catches all exceptions to prevent worker crash
        - Logs errors with full context
        - Continues running unless fatal error (DB unreachable)

    Raises:
        No exceptions raised (catches all internally)
    """
    worker_id = os.getenv("RAILWAY_SERVICE_NAME", "worker-local")
    log.info("worker_started", worker_id=worker_id)

    last_heartbeat = datetime.utcnow()
    iteration_count = 0
    consecutive_errors = 0

    try:
        while not shutdown_requested:
            iteration_count += 1

            # Heartbeat logging (every 60 seconds)
            now = datetime.utcnow()
            if (now - last_heartbeat).total_seconds() >= 60:
                log.info(
                    "worker_heartbeat",
                    worker_id=worker_id,
                    iteration_count=iteration_count,
                    consecutive_errors=consecutive_errors
                )
                last_heartbeat = now

            try:
                # PLACEHOLDER: Task claiming will be added in Story 4.2
                # For now, just sleep to prevent CPU spinning
                await asyncio.sleep(1)

                # Reset error counter on successful iteration
                consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                log.error(
                    "worker_loop_error",
                    worker_id=worker_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    consecutive_errors=consecutive_errors,
                    exc_info=True
                )

                # Alert if too many consecutive errors (possible fatal issue)
                if consecutive_errors > 10:
                    log.critical(
                        "worker_excessive_errors",
                        worker_id=worker_id,
                        consecutive_errors=consecutive_errors,
                        message="Worker experiencing excessive errors, may need restart"
                    )
                    # Reset counter to prevent log spam
                    consecutive_errors = 0

                # Sleep before retry to prevent tight error loop
                await asyncio.sleep(5)

    except asyncio.CancelledError:
        log.info("worker_cancelled", worker_id=worker_id)
        raise

    finally:
        log.info(
            "worker_shutdown",
            worker_id=worker_id,
            total_iterations=iteration_count
        )


async def shutdown_worker() -> None:
    """
    Graceful shutdown: close database connections and cleanup resources.

    Called during worker shutdown to ensure clean exit.
    Important for Railway deployments to prevent connection leaks.

    Side Effects:
        - Closes async database engine
        - Disposes connection pool
    """
    log.info("closing_database_connections")
    await async_engine.dispose()
    log.info("database_connections_closed")


def main() -> None:
    """
    Worker process entry point.

    Initializes worker, registers signal handlers, runs main loop.

    Exit Codes:
        0: Successful shutdown (SIGTERM received)
        1: Fatal error (configuration invalid, database unreachable)
    """
    # Load configuration
    try:
        config = get_config()
        log.info(
            "worker_configuration_loaded",
            database_url_host=config.database_url.split("@")[-1].split("/")[0] if "@" in config.database_url else "local",
            pool_size=10,
            max_overflow=5
        )
    except Exception as e:
        log.critical("configuration_load_failed", error=str(e), exc_info=True)
        sys.exit(1)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)  # Also handle Ctrl+C for local dev

    # Run worker main loop
    try:
        asyncio.run(worker_main_loop())
    except KeyboardInterrupt:
        log.info("worker_interrupted_by_user")
    except Exception as e:
        log.critical("worker_fatal_error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        # Graceful shutdown
        asyncio.run(shutdown_worker())
        log.info("worker_exited_successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
```

### Database Configuration Updates: `app/database.py`

**Required Modifications:**

```python
"""
Database configuration with async SQLAlchemy 2.0 patterns.

Provides async engine and session factory for both FastAPI routes (via Depends)
and worker processes (via direct session factory usage).

Architecture Pattern:
    - Single async engine shared across all workers and web service
    - Connection pooling sized for 3 workers + web service (pool_size=10)
    - pool_pre_ping=True handles Railway connection recycling
    - AsyncSession with expire_on_commit=False prevents lazy loading issues

Usage:
    FastAPI Routes:
        async def route_handler(db: AsyncSession = Depends(get_db)):
            # Use db session, auto-closed after request

    Workers:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                # Use db session, auto-closed after context
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator

from app.config import get_config

# Load configuration
config = get_config()

# Create async engine with connection pooling
async_engine = create_async_engine(
    config.database_url,
    echo=False,  # Set to True for SQL query logging (debug mode)
    pool_size=10,  # Supports 3 workers + web service concurrent operations
    max_overflow=5,  # Burst capacity for peak load
    pool_timeout=30,  # Fail fast if pool exhausted (seconds)
    pool_pre_ping=True,  # Handle Railway connection recycling
)

# Create async session factory
# Used by workers directly: async with AsyncSessionLocal() as session:
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Prevent lazy loading issues
)

# Declarative base for SQLAlchemy models
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection for FastAPI routes.

    Provides database session that auto-closes after request.
    DO NOT use this in workers - use AsyncSessionLocal() directly.

    Usage:
        @router.get("/tasks")
        async def list_tasks(db: AsyncSession = Depends(get_db)):
            tasks = await db.execute(select(Task))
            return tasks.scalars().all()

    Yields:
        AsyncSession: Database session (auto-closed after yield)
    """
    async with AsyncSessionLocal() as session:
        yield session
```

### Railway Deployment Configuration: `railway.json`

**New File:**

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "numReplicas": 1,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

**Note**: Railway will create separate services (web, worker-1, worker-2, worker-3) via the Railway dashboard. The `railway.json` provides build configuration, but service topology is configured in the Railway UI.

### Dockerfile Modifications

**Support both web and worker start commands:**

```dockerfile
FROM python:3.11-slim

# Install system dependencies (FFmpeg required for video processing)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project
WORKDIR /app
COPY . /app

# Install dependencies
RUN uv sync --frozen

# Expose port for web service (worker doesn't need this, but doesn't hurt)
EXPOSE 8000

# Default command (overridden by Railway service configuration)
# Web service: uvicorn app.main:app --host 0.0.0.0 --port $PORT
# Worker service: python -m app.worker
CMD ["python", "-m", "app.worker"]
```

### Configuration Loading: `app/config.py`

**Ensure configuration supports worker context:**

```python
"""
Configuration management for ai-video-generator platform.

Loads configuration from environment variables for both web service and workers.
All secrets (DATABASE_URL, FERNET_KEY, API keys) come from Railway env vars.

Environment Variables:
    DATABASE_URL: PostgreSQL connection string (postgresql+asyncpg://...)
    FERNET_KEY: Encryption key for OAuth tokens (44-char base64)
    DISCORD_WEBHOOK_URL: Discord webhook for alerts (optional)
    RAILWAY_SERVICE_NAME: Service identifier (worker-1, worker-2, web)
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Application configuration loaded from environment variables"""

    database_url: str
    fernet_key: str
    discord_webhook_url: Optional[str] = None
    railway_service_name: Optional[str] = None

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable not set")

        fernet_key = os.getenv("FERNET_KEY")
        if not fernet_key:
            raise ValueError("FERNET_KEY environment variable not set")

        return cls(
            database_url=database_url,
            fernet_key=fernet_key,
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL"),
            railway_service_name=os.getenv("RAILWAY_SERVICE_NAME", "local")
        )


# Singleton configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration instance (singleton pattern)"""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
```

### Usage Pattern

```python
# ✅ CORRECT: Worker process entry point
# Terminal 1: Start worker locally
python -m app.worker

# Terminal 2: Start another worker
python -m app.worker

# Workers share same database, run independently

# ❌ WRONG: Import worker as module (it's an entry point, not a library)
from app.worker import main
main()  # Don't do this - use python -m app.worker
```

## Dev Agent Guardrails - CRITICAL REQUIREMENTS

### 🔥 Architecture Compliance (MANDATORY)

**1. Short Transaction Pattern (Architecture Decision 3 - Placeholder for Story 4.2+):**
```python
# ✅ CORRECT: Short transactions (will be used in Story 4.2+)
async with AsyncSessionLocal() as db:
    task = await db.get(Task, task_id)
    task.status = "processing"
    await db.commit()

# OUTSIDE transaction - NO DB connection held
result = await process_pipeline_step(task)

async with AsyncSessionLocal() as db:
    task = await db.get(Task, task_id)
    task.status = "completed"
    await db.commit()

# ❌ WRONG: Holding transaction during long operation
async with AsyncSessionLocal() as db:
    task = await db.get(Task, task_id)
    task.status = "processing"
    result = await process_pipeline_step(task)  # BLOCKS DB!
    task.status = "completed"
    await db.commit()
```

**2. Async Database Operations (SQLAlchemy 2.0 Patterns):**
```python
# ✅ CORRECT: Async engine and session factory
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

async_engine = create_async_engine(
    database_url,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# ✅ CORRECT: Worker usage pattern
async with AsyncSessionLocal() as session:
    async with session.begin():
        # Database operations
        pass

# ❌ WRONG: Sync engine or old SQLAlchemy patterns
from sqlalchemy import create_engine
engine = create_engine(database_url)  # Not async!
```

**3. Graceful Shutdown Pattern:**
```python
# ✅ CORRECT: Signal handler for graceful shutdown
import signal

shutdown_requested = False

def signal_handler(signum: int, frame) -> None:
    global shutdown_requested
    log.info("shutdown_signal_received", signal=signum)
    shutdown_requested = True

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Main loop checks shutdown flag
while not shutdown_requested:
    # Work loop
    await asyncio.sleep(1)

# ❌ WRONG: No signal handling (process killed abruptly)
while True:
    await asyncio.sleep(1)  # Never exits gracefully
```

**4. Structured Logging with Worker Identification:**
```python
# ✅ CORRECT: Include worker_id in all log messages
worker_id = os.getenv("RAILWAY_SERVICE_NAME", "worker-local")

log.info(
    "worker_heartbeat",
    worker_id=worker_id,
    iteration_count=100,
    consecutive_errors=0
)

# ❌ WRONG: No worker identification in logs
log.info("heartbeat")  # Can't distinguish which worker logged this
```

**5. Connection Pool Configuration:**
```python
# ✅ CORRECT: Shared pool sized for 3 workers + web service
async_engine = create_async_engine(
    database_url,
    pool_size=10,  # 3 workers + web service
    max_overflow=5,
    pool_timeout=30,
    pool_pre_ping=True
)

# ❌ WRONG: Insufficient pool size or missing pre_ping
async_engine = create_async_engine(
    database_url,
    pool_size=5,  # Too small for 3 workers
    pool_pre_ping=False  # Railway connections can go stale
)
```

### 🧠 Previous Story Learnings

**From Epic 3 (Stories 3.1-3.8):**
- ✅ Short transaction pattern works for operations up to 10 minutes (video assembly took 60-120s)
- ✅ Async execution prevents event loop blocking (all services use `async/await`)
- ✅ Structured logging with correlation IDs essential for debugging (JSON format)
- ✅ CLI wrapper pattern (`run_cli_script()`) prevents blocking and handles timeouts
- ✅ Filesystem helpers prevent path traversal attacks (regex validation)
- ✅ Service layer separation (business logic in services, orchestration in workers)

**Git Commit Analysis (Last 5 Commits):**

1. **0d1439c**: Story 3.8 complete - Video assembly with code review fixes
   - Short transaction pattern for 60-120 second FFmpeg operations
   - Graceful error handling with detailed logging
   - Async patterns throughout

2. **ad3a099**: Story 3.7 complete - Sound effects generation with code review fixes
   - Service layer pattern established
   - Type-safe dataclasses for structured data
   - Retry logic with exponential backoff

3. **1314620**: Story 3.6 complete - Narration generation with code review fixes
   - Short transaction pattern for 1.5-4.5 minute ElevenLabs operations
   - Audio duration probing pattern
   - Manifest-driven orchestration

4. **a85176e**: Story 3.5 complete - Video clip generation with code review fixes
   - Extended timeout pattern (600s for Kling video generation)
   - Output validation with ffprobe
   - Error handling with detailed stderr logging

5. **f799965**: Story 3.4 complete - Composite creation with code review fixes
   - Short transaction pattern verified working
   - Security validation enforced
   - Async patterns prevent event loop blocking

**Key Patterns Established:**
- **Worker Structure**: Service layer + worker orchestration separation
- **Transaction Management**: NEVER hold DB during long operations
- **Error Handling**: Catch, log, classify (retriable vs non-retriable), continue or fail
- **Logging**: JSON format, correlation IDs, worker identification
- **Configuration**: Environment variables only, no hard-coded values

### 📚 Library & Framework Requirements

**Required Libraries (from architecture.md and project-context.md):**
- Python ≥3.10 (async/await, type hints, match statements)
- SQLAlchemy ≥2.0 with AsyncSession (from Story 2.1)
- asyncpg ≥0.29.0 (async PostgreSQL driver)
- structlog (JSON logging from Story 3.1)
- Railway CLI (optional, for local testing with Railway services)

**DO NOT Install:**
- ❌ psycopg2 (use asyncpg instead - async required)
- ❌ SQLAlchemy 1.x (incompatible with 2.0 async patterns)
- ❌ celery (not needed - using PgQueuer in Story 4.2)
- ❌ rq (not needed - using PgQueuer in Story 4.2)

**System Dependencies:**
- **PostgreSQL 16**: Railway managed, provided via DATABASE_URL env var
- **Railway Platform**: $5/month Hobby plan, multi-service deployment

### 🗂️ File Structure Requirements

**MUST Create:**
- `app/worker.py` - Worker process entry point with main loop
- `railway.json` - Railway deployment configuration
- `tests/test_worker.py` - Worker unit tests (10+ test cases)

**MUST Modify:**
- `app/database.py` - Add async engine and session factory with connection pooling
- `app/config.py` - Add worker-specific configuration (if not exists)
- `Dockerfile` - Support both web and worker start commands

**MUST NOT Modify:**
- Any files in `scripts/` directory (brownfield constraint)
- Epic 3 service modules (they're already working)

### 🧪 Testing Requirements

**Minimum Test Coverage:**
- ✅ Worker startup and initialization: 3+ test cases
- ✅ Signal handling (SIGTERM, SIGINT): 2+ test cases
- ✅ Main loop execution: 2+ test cases
- ✅ Error handling and recovery: 3+ test cases
- ✅ Database connection pooling: 2+ test cases
- ✅ Configuration loading: 2+ test cases
- ✅ Graceful shutdown: 2+ test cases

**Mock Strategy:**
- Mock `AsyncSessionLocal()` for database transaction tests
- Mock `asyncio.sleep()` to speed up loop iteration tests
- Mock `os.getenv()` for configuration tests
- Mock signal handlers for shutdown tests
- Use `pytest.mark.asyncio` for async test functions

**Test Pattern Example:**
```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_worker_startup():
    """Test worker initializes correctly and enters main loop"""
    with patch("app.worker.get_config") as mock_config:
        mock_config.return_value = MagicMock(
            database_url="sqlite+aiosqlite:///:memory:",
            fernet_key="test-key"
        )
        # Test startup logic
        pass

@pytest.mark.asyncio
async def test_graceful_shutdown_on_sigterm():
    """Test worker exits cleanly when SIGTERM received"""
    # Mock signal handler and verify shutdown
    pass
```

### 🔒 Security Requirements

**Configuration Security:**
```python
# ✅ All secrets from environment variables
database_url = os.getenv("DATABASE_URL")  # Never hard-code
fernet_key = os.getenv("FERNET_KEY")

# ❌ WRONG: Hard-coded secrets
database_url = "postgresql://user:password@host/db"  # NEVER DO THIS
```

**Database URL Logging:**
```python
# ✅ CORRECT: Redact credentials when logging
database_host = config.database_url.split("@")[-1].split("/")[0] if "@" in config.database_url else "local"
log.info("worker_configuration_loaded", database_url_host=database_host)

# ❌ WRONG: Log full DATABASE_URL with credentials
log.info("config_loaded", database_url=config.database_url)  # Exposes password!
```

## Dependencies

**Required Before Starting:**
- ✅ Story 1.1 complete: Database models (Channel, Task, Video) established
- ✅ Story 2.1 complete: Task model with 9-state workflow
- ✅ Story 3.1 complete: Structured logging (`app/utils/logging.py`)
- ✅ Epic 3 complete: All 8 pipeline services implemented
- ✅ PostgreSQL 16: Railway managed database
- ✅ Railway account: $5/month Hobby plan with multi-service support

**Blocks These Stories:**
- Story 4.2: Task Claiming with PgQueuer (needs worker foundation)
- Story 4.3: Priority Queue Management (needs worker + task claiming)
- Story 4.6: Parallel Task Execution (needs full worker infrastructure)
- Epic 5: Review Gates (needs workers to process pipeline)

## Definition of Done

- [ ] `app/worker.py` implemented with main loop, signal handlers, graceful shutdown
- [ ] `app/database.py` updated with async engine and session factory (pool_size=10, pool_pre_ping=True)
- [ ] `app/config.py` updated with worker-specific configuration loading
- [ ] `railway.json` created with multi-service deployment configuration
- [ ] `Dockerfile` modified to support both web and worker start commands
- [ ] All worker unit tests passing (16+ test cases minimum)
- [ ] Worker startup tested locally (`python -m app.worker`)
- [ ] Multiple workers tested in separate terminals (verify independence)
- [ ] Signal handling tested (SIGTERM, SIGINT exit gracefully)
- [ ] Database connection pooling verified (3 workers + web share pool)
- [ ] Graceful shutdown tested (finishes current work, exits cleanly)
- [ ] Structured logging verified (JSON format, worker_id in all messages)
- [ ] Error handling tested (unexpected exceptions don't crash worker)
- [ ] Heartbeat logging tested (every 60 seconds)
- [ ] Configuration loading tested (DATABASE_URL, FERNET_KEY required)
- [ ] Type hints complete (all parameters and return types annotated)
- [ ] Docstrings complete (module, function-level with architecture references)
- [ ] Linting passes (`ruff check --fix .`)
- [ ] Type checking passes (`mypy app/`)
- [ ] Local development guide updated in README.md
- [ ] Railway deployment tested (3 workers + web + postgres)
- [ ] Code review approved (adversarial review with security focus)
- [ ] Merged to `main` branch

## Notes & Implementation Hints

**From Architecture (architecture.md):**
- Worker processes run as separate Railway services (worker-1, worker-2, worker-3)
- Each worker independently claims tasks via PgQueuer (Story 4.2)
- Connection pool sized for 3 workers + web service (pool_size=10 sufficient)
- Workers use short transaction pattern: claim → close → process → reopen → update
- Graceful shutdown critical for Railway deployments (SIGTERM sent during deploy)

**From project-context.md:**
- Workers use `AsyncSessionLocal()` directly, NOT `Depends(get_db)` (that's for FastAPI)
- All database operations MUST use async/await patterns
- Structured logging with JSON format for Railway log aggregation
- Configuration from environment variables only (DATABASE_URL, FERNET_KEY)
- Worker_id logged in all messages for debugging multi-worker scenarios

**Worker Process Pattern (Story 4.1):**
```python
# Foundation only - no task processing yet
async def worker_main_loop():
    worker_id = os.getenv("RAILWAY_SERVICE_NAME", "worker-local")
    log.info("worker_started", worker_id=worker_id)

    while not shutdown_requested:
        # Heartbeat every 60 seconds
        log.info("worker_heartbeat", worker_id=worker_id)

        # PLACEHOLDER: Task claiming in Story 4.2
        await asyncio.sleep(1)

    log.info("worker_shutdown", worker_id=worker_id)
```

**Railway Deployment Strategy:**
- Create 4 services in Railway dashboard: web, worker-1, worker-2, worker-3
- All services use same Dockerfile but different start commands
- Web: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Workers: `python -m app.worker`
- Share DATABASE_URL, FERNET_KEY env vars across all services
- Add RAILWAY_SERVICE_NAME to distinguish workers in logs

**Local Development Testing:**
```bash
# Terminal 1: Start PostgreSQL (or use Railway local)
docker-compose up postgres

# Terminal 2: Start web service
uvicorn app.main:app --reload --port 8000

# Terminal 3: Start worker 1
RAILWAY_SERVICE_NAME=worker-1 python -m app.worker

# Terminal 4: Start worker 2
RAILWAY_SERVICE_NAME=worker-2 python -m app.worker

# Verify all processes share same database
# Check logs for worker_id to distinguish processes
```

**Connection Pool Sizing:**
- 3 workers × 2 connections average = 6 connections
- 1 web service × 3 connections average = 3 connections
- Total: 9 connections (pool_size=10 provides headroom)
- max_overflow=5 handles burst traffic (up to 15 total connections)
- pool_timeout=30s fails fast if pool exhausted (prevents deadlock)

**Performance Considerations:**
- Worker loop sleeps 1 second between iterations to prevent CPU spinning
- Heartbeat logging every 60 seconds (not every iteration) to reduce log volume
- Consecutive error tracking alerts on excessive errors (>10 in loop)
- Graceful shutdown within 30 seconds (Railway timeout)

---

## Related Stories

- **Depends On:**
  - 1-1 (Database Foundation) - provides Channel, Task, Video models
  - 2-1 (Task Model) - provides 9-state workflow (pending → claimed → processing → completed)
  - 3-1 (CLI Script Wrapper) - provides structured logging setup
  - Epic 3 (Video Generation Pipeline) - provides all 8 service modules

- **Blocks:**
  - 4-2 (Task Claiming with PgQueuer) - needs worker foundation
  - 4-3 (Priority Queue Management) - needs worker + task claiming
  - 4-4 (Round-Robin Channel Scheduling) - needs worker infrastructure
  - 4-6 (Parallel Task Execution) - needs complete worker infrastructure
  - Epic 5 (Review Gates) - needs workers to process pipeline

- **Related:**
  - Epic 8 (Monitoring & Observability) - uses structured logging from worker
  - Epic 6 (Error Handling) - uses worker error recovery patterns

## Source References

**PRD Requirements:**
- FR38: Horizontal scaling via multiple independent worker processes
- NFR-PER-001: Async I/O throughout backend for non-blocking execution
- NFR-REL-001: Graceful shutdown within Railway timeout (30 seconds)

**Architecture Decisions:**
- Worker Process Design: Separate Processes (3 independent Python processes)
- Database Architecture: Connection pooling (pool_size=10, max_overflow=5, pool_pre_ping=True)
- Architecture Decision 3: Short Transaction Pattern (claim → close → process → reopen → update)

**Context:**
- project-context.md: Critical Implementation Rules (lines 56-119)
- project-context.md: Python Language-Specific Rules (lines 625-670)
- project-context.md: Framework-Specific Rules (lines 672-736)
- CLAUDE.md: Worker processes run as separate Railway services
- epics.md: Epic 4 Story 1 - Worker Process Foundation requirements with BDD scenarios

**SQLAlchemy Documentation:**
- [SQLAlchemy 2.0 Async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Connection Pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html)
- [asyncpg Driver](https://magicstack.github.io/asyncpg/current/)

**Railway Documentation:**
- [Multi-Service Deployment](https://docs.railway.app/deploy/deployments)
- [Environment Variables](https://docs.railway.app/deploy/variables)
- [Dockerfile Support](https://docs.railway.app/deploy/dockerfiles)

---

## Dev Agent Record

### Agent Model Used

_To be filled during implementation_

### Implementation Summary

_To be filled during implementation_

### Debug Log References

_To be filled during implementation_

### Completion Notes List

_To be filled during implementation_

### File List

_To be filled during implementation_

### Code Review Record

_To be filled during implementation_

---

## Status

**Status:** ready-for-dev
**Created:** 2026-01-16 via BMad Method workflow
**Ready for Implementation:** YES - All context gathered, comprehensive story document complete

