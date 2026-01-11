"""Configuration management for the orchestration layer.

This module provides centralized configuration loading from environment variables.
All configuration values are loaded at import time and cached.

Environment Variables:
    DATABASE_URL: PostgreSQL connection URL (required for production)
    FERNET_KEY: Encryption key for credentials (required)
    DEFAULT_VOICE_ID: Fallback ElevenLabs voice ID when channel voice not set (optional)

Usage:
    from app.config import get_default_voice_id, get_database_url

    voice_id = get_default_voice_id()  # Returns None if not set
    db_url = get_database_url()  # Raises if DATABASE_URL not set
"""

import os
from functools import lru_cache

import structlog

log = structlog.get_logger(__name__)


def get_default_voice_id() -> str | None:
    """Get default ElevenLabs voice ID from environment.

    This is the fallback voice ID used when a channel doesn't have a
    channel-specific voice_id configured. If not set, and a channel
    needs a voice ID, the VoiceBrandingService will raise ConfigurationError.

    Environment Variable:
        DEFAULT_VOICE_ID: ElevenLabs voice ID string (e.g., "21m00Tcm4TlvDq8ikWAM")

    Returns:
        Voice ID string, or None if not set.

    Example:
        >>> voice_id = get_default_voice_id()
        >>> if voice_id:
        ...     print(f"Using default voice: {voice_id[:8]}...")
    """
    return os.getenv("DEFAULT_VOICE_ID")


@lru_cache
def get_database_url() -> str:
    """Get database URL from environment.

    Converts postgresql:// to postgresql+asyncpg:// for async SQLAlchemy.

    Environment Variable:
        DATABASE_URL: PostgreSQL connection URL

    Returns:
        Database URL with asyncpg driver.

    Raises:
        ValueError: If DATABASE_URL not set.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable is required")

    # Railway provides postgresql:// but we need postgresql+asyncpg://
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return url


@lru_cache
def get_fernet_key() -> str:
    """Get Fernet encryption key from environment.

    Environment Variable:
        FERNET_KEY: Base64-encoded Fernet key for credential encryption

    Returns:
        Fernet key string.

    Raises:
        ValueError: If FERNET_KEY not set.
    """
    key = os.getenv("FERNET_KEY")
    if not key:
        raise ValueError("FERNET_KEY environment variable is required")
    return key


def get_channel_configs_dir() -> str:
    """Get channel configurations directory from environment.

    Environment Variable:
        CHANNEL_CONFIGS_DIR: Path to channel YAML configs (default: "channel_configs")

    Returns:
        Directory path string.
    """
    return os.getenv("CHANNEL_CONFIGS_DIR", "channel_configs")


def get_workspace_root() -> str:
    """Get workspace root directory from environment.

    Environment Variable:
        WORKSPACE_ROOT: Base path for workspace files (default: "/app/workspace")

    Returns:
        Directory path string.
    """
    return os.getenv("WORKSPACE_ROOT", "/app/workspace")
