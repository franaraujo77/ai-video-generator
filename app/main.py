"""FastAPI application for multi-channel video orchestration.

This is the web service entry point for the orchestration platform.
Epic 1: Minimal health check endpoint for deployment validation.
Epic 2+: Adds Notion sync background task, webhook endpoints, task management, etc.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from app.clients.notion import NotionClient
from app.config import get_notion_api_token
from app.routes import webhooks
from app.services.notion_sync import sync_database_to_notion_loop

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup/shutdown of background tasks.

    Startup:
    - Initialize NotionClient if NOTION_API_TOKEN is set
    - Start sync_database_to_notion_loop background task

    Shutdown:
    - Cancel sync task gracefully
    - Close NotionClient HTTP connections
    """
    # Startup
    notion_client = None
    sync_task = None

    notion_api_token = get_notion_api_token()
    if notion_api_token:
        log.info("initializing_notion_sync", message="Notion API token found, starting sync loop")
        notion_client = NotionClient(auth_token=notion_api_token)

        # Start sync loop as background task
        sync_task = asyncio.create_task(
            sync_database_to_notion_loop(notion_client)
        )
    else:
        log.warning(
            "notion_sync_disabled",
            message="NOTION_API_TOKEN not set, Notion sync will not run"
        )

    yield  # Application runs here

    # Shutdown
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

# Register webhook routes (Story 2.5)
app.include_router(webhooks.router)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> JSONResponse:
    """Health check endpoint for Railway deployment validation.

    Epic 1: Validates that the application can start and respond to requests.
    Future epics will add database connectivity checks, service health checks, etc.

    Returns:
        JSONResponse: Status and basic system information
    """
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "ai-video-generator",
            "epic": "epic-1",
            "message": "Foundation services operational",
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
