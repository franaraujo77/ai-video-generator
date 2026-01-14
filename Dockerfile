# Simplified single-stage Dockerfile for Railway deployment
# Python 3.11 + FFmpeg + dependencies

FROM python:3.11-slim

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

# Install uv package manager (faster than pip)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (for better layer caching)
COPY pyproject.toml uv.lock ./

# Install production dependencies directly to system Python
# Use uv export to generate requirements.txt from pyproject.toml
# This ensures Dockerfile automatically stays in sync with pyproject.toml
# --no-dev: Exclude dev dependencies
# --no-hashes: Simpler requirements.txt format
RUN uv export --no-dev --no-hashes --frozen > requirements.txt && \
    uv pip install --system --no-cache -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Create workspace and config directories for runtime
# Channel configs will be provided via environment or mounted at runtime
RUN mkdir -p /app/workspace /app/config

# Expose port for web service (Railway provides $PORT)
EXPOSE 8000

# Default command for Epic 1: Run FastAPI web service
# Railway will use $PORT environment variable for the port
# Future epics: Override with service-specific commands in Railway dashboard
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
