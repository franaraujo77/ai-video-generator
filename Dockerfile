# Multi-stage Dockerfile for Railway deployment
# Optimized for Python 3.11 + FFmpeg + uv package manager

# =============================================================================
# Stage 1: Base image with system dependencies
# =============================================================================
FROM python:3.11-slim AS base

# Install system dependencies
# - FFmpeg: Required for video processing (assemble_video.py)
# - curl: Health checks and debugging
# - git: Required by some Python packages during install
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# =============================================================================
# Stage 2: Dependencies installation with uv
# =============================================================================
FROM base AS dependencies

# Install uv package manager (faster than pip)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (for better layer caching)
COPY pyproject.toml ./
COPY uv.lock* ./

# Install production dependencies only (no dev dependencies)
# Using --system to install into system Python (not virtualenv)
RUN uv sync --frozen --no-dev --no-editable

# =============================================================================
# Stage 3: Application
# =============================================================================
FROM base AS application

# Copy installed packages from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Copy channel configs if they exist (optional at build time)
COPY config/ ./config/ 2>/dev/null || true

# Create workspace directory for video assets
RUN mkdir -p /app/workspace

# Expose port for web service (Railway provides $PORT)
EXPOSE 8000

# Default command (overridden by Railway service-specific start commands)
# For web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
# For workers: python -m app.worker
CMD ["python", "-m", "app.worker"]
