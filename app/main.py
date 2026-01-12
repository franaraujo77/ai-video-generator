"""FastAPI application for multi-channel video orchestration.

This is the web service entry point for the orchestration platform.
Epic 1: Minimal health check endpoint for deployment validation.
Epic 2+: Will add webhook endpoints, task management, etc.
"""

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

# Create FastAPI app
app = FastAPI(
    title="AI Video Generator - Multi-Channel Orchestration",
    description=(
        "Orchestration platform for managing multiple YouTube channels "
        "with AI-generated content"
    ),
    version="0.1.0",
)


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
