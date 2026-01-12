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
COPY pyproject.toml ./

# Install production dependencies directly to system Python
# Extract dependencies from pyproject.toml and install them
RUN uv pip install --system --no-cache \
    "google-generativeai>=0.8.0" \
    "python-dotenv>=1.0.0" \
    "pillow>=10.0.0" \
    "pyjwt>=2.8.0" \
    "requests>=2.31.0" \
    "sqlalchemy[asyncio]>=2.0.0" \
    "asyncpg>=0.29.0" \
    "alembic>=1.13.0" \
    "aiosqlite>=0.19.0" \
    "pydantic>=2.8.0" \
    "pyyaml>=6.0" \
    "structlog>=23.2.0" \
    "cryptography>=41.0.0" \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0"

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

# Default command (overridden by Railway service-specific start commands)
# For web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
# For workers: python -m app.worker
CMD ["python", "-m", "app.worker"]
