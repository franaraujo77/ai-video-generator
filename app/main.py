"""FastAPI application for multi-channel video orchestration.

This is the web service entry point for the orchestration platform.
Epic 1: Minimal health check endpoint for deployment validation.
Epic 2+: Adds Notion sync background task, webhook endpoints, task management, etc.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.notion import NotionClient
from app.config import get_notion_api_token
from app.database import get_session
from app.middleware.correlation import CorrelationMiddleware
from app.routes import admin, asset_urls, cost_reports, r2_config, webhooks, weekly_reports
from app.scheduler import (
    is_cleanup_scheduler_running,
    is_scheduler_running,
    is_weekly_metrics_scheduler_running,
)
from app.services.notion_sync import sync_database_to_notion_loop
from app.services.task_status_service import get_queue_depth
from app.services.worker_status_service import (
    check_database_connection,
    get_active_worker_count,
)
from app.utils.logging import configure_structlog

# Configure structlog with correlation ID processors (Story 8.1)
configure_structlog()

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup/shutdown of background tasks.

    Startup:
    - Initialize NotionClient if NOTION_API_TOKEN is set
    - Start sync_database_to_notion_loop background task
    - PgQueuer initialization deferred to Epic 4 (Worker Orchestration)

    Shutdown:
    - Cancel sync task gracefully
    - Close NotionClient HTTP connections
    """
    # Startup: Initialize Notion sync
    notion_client = None
    sync_task = None

    notion_api_token = get_notion_api_token()
    if notion_api_token:
        log.info("initializing_notion_sync", message="Notion API token found, starting sync loop")
        notion_client = NotionClient(auth_token=notion_api_token)

        # Start sync loop as background task
        sync_task = asyncio.create_task(sync_database_to_notion_loop(notion_client))
    else:
        log.warning(
            "notion_sync_disabled", message="NOTION_API_TOKEN not set, Notion sync will not run"
        )

    # Story 2.6: PgQueuer infrastructure ready for Epic 4
    log.info(
        "task_queue_ready",
        message="Task enqueueing with duplicate detection active. "
        "PgQueuer worker integration in Epic 4.",
    )

    yield  # Application runs here

    # Shutdown: Notion sync
    if sync_task:
        log.info("shutting_down_notion_sync")
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            log.info("notion_sync_task_cancelled")

    if notion_client:
        await notion_client.close()


# Create FastAPI app with lifespan
app = FastAPI(
    title="AI Video Generator - Multi-Channel Orchestration",
    description=(
        "Orchestration platform for managing multiple YouTube channels with AI-generated content"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Register correlation middleware (Story 8.1 - MUST be before route registration)
app.add_middleware(CorrelationMiddleware)

# Register webhook routes (Story 2.5)
app.include_router(webhooks.router)

# Register admin routes (Story 7.0)
app.include_router(admin.router)

# Register cost reporting routes (Story 8.2)
app.include_router(cost_reports.router)

# Register asset URL routes (Story 8.3)
app.include_router(asset_urls.router)

# Register R2 configuration routes (Story 8.4)
app.include_router(r2_config.router)

# Register weekly metrics reporting routes (Story 8.6)
app.include_router(weekly_reports.router)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check(db: AsyncSession = Depends(get_session)) -> JSONResponse:  # noqa: B008
    """Health check endpoint for Railway deployment and system monitoring (Story 8.7).

    Performs comprehensive system health checks within 500ms response budget:
    - Database connectivity check (100ms timeout)
    - Active worker count (last 5 minutes)
    - Queue depth (pending + queued tasks)
    - Scheduler status checks

    Health Status Logic:
        - unhealthy: Database connection fails (critical failure)
        - degraded: Worker count < 3 OR no recent heartbeats (partial failure)
        - healthy: All systems operational (normal state)

    Args:
        db: Async database session (dependency injection)

    Returns:
        JSONResponse: Always 200 OK (Railway expects 200 for liveness)
            {
                "status": "healthy|degraded|unhealthy",
                "database": "connected|error",
                "workers": {"count": 3, "active_timestamp": "..."},
                "queue_depth": 42,
                "schedulers": {...}
            }

    Performance:
        - Total response time budget: < 500ms
        - Database check: < 100ms
        - Worker query: < 100ms
        - Queue query: < 100ms
        - Always returns 200 OK (Railway interprets status field, not HTTP code)

    References:
        - Story 8.7: Health Check Endpoint
        - AC1: Basic Health Check with Response Time
        - AC2: Database Connectivity Check
        - AC3: Worker Heartbeat Monitoring
        - AC4: Performance Budget
    """
    log = structlog.get_logger()
    start_time = time.time()

    # Initialize response data
    overall_status = "healthy"
    database_status = "connected"
    worker_info: dict[str, int | str | None] = {"count": 0, "active_timestamp": None}
    queue_depth = 0

    # Check 1: Database Connectivity (< 100ms timeout)
    try:
        db_connected = await check_database_connection(db)
        if not db_connected:
            database_status = "error"
            overall_status = "unhealthy"
            log.warning(
                "health_check_database_failed",
                database="error",
                overall_status="unhealthy",
            )
    except Exception as e:
        database_status = "error"
        overall_status = "unhealthy"
        log.error(
            "health_check_database_exception",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )

    # Check 2: Active Worker Count (only if database is connected)
    if database_status == "connected":
        try:
            worker_info = await get_active_worker_count(db)

            # Degraded if fewer than 3 workers active
            worker_count = worker_info["count"]
            if isinstance(worker_count, int) and worker_count < 3 and overall_status == "healthy":
                overall_status = "degraded"
                log.warning(
                    "health_check_degraded_workers",
                    worker_count=worker_info["count"],
                    expected_workers=3,
                    overall_status="degraded",
                )
        except Exception as e:
            # Non-fatal - worker check failure doesn't make system unhealthy
            log.error(
                "health_check_worker_count_exception",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

        # Check 3: Queue Depth (only if database is connected)
        try:
            queue_depth = await get_queue_depth(db)
        except Exception as e:
            # Non-fatal - queue depth is informational only
            log.error(
                "health_check_queue_depth_exception",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

    # Check 4: Scheduler Statuses
    quota_scheduler_running = is_scheduler_running()
    cleanup_scheduler_running = is_cleanup_scheduler_running()
    weekly_metrics_scheduler_running = is_weekly_metrics_scheduler_running()

    # Calculate response time
    response_time_ms = (time.time() - start_time) * 1000

    # Structured logging
    log.info(
        "health_check_performed",
        status=overall_status,
        database=database_status,
        worker_count=worker_info["count"],
        queue_depth=queue_depth,
        response_time_ms=round(response_time_ms, 2),
    )

    # Return response (always 200 OK, status field indicates health)
    return JSONResponse(
        content={
            "status": overall_status,
            "database": database_status,
            "workers": worker_info,
            "queue_depth": queue_depth,
            "schedulers": {
                "quota_reset": "running" if quota_scheduler_running else "not_running",
                "cleanup": "running" if cleanup_scheduler_running else "not_running",
                "weekly_metrics": (
                    "running" if weekly_metrics_scheduler_running else "not_running"
                ),
            },
            "service": "ai-video-generator",
            "epic": "epic-8",
        }
    )


@app.get("/", status_code=status.HTTP_200_OK)
async def root() -> JSONResponse:
    """Root endpoint with API information.

    Returns:
        JSONResponse: API metadata
    """
    return JSONResponse(
        content={
            "service": "AI Video Generator - Multi-Channel Orchestration",
            "version": "0.1.0",
            "epic": "epic-1",
            "status": "foundation-deployed",
            "docs": "/docs",
            "health": "/health",
        }
    )


if __name__ == "__main__":
    import uvicorn

    # For local development
    # Binding to 0.0.0.0 is intentional for Docker/Railway compatibility
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # noqa: S104
        port=8000,
        reload=True,
    )
