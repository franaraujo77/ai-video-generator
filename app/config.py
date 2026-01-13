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


def get_notion_api_token() -> str | None:
    """Get Notion API token from environment.

    Environment Variable:
        NOTION_API_TOKEN: Notion Internal Integration token

    Returns:
        Notion API token string, or None if not set.

    Note:
        Returns None when NOTION_API_TOKEN is not set, allowing the app
        to start without Notion integration. The sync service will skip
        initialization if token is None.
    """
    return os.getenv("NOTION_API_TOKEN")


def get_notion_database_ids() -> list[str]:
    """Get Notion database IDs from environment.

    Environment Variable:
        NOTION_DATABASE_IDS: Comma-separated list of Notion database IDs to sync
        Example: "abc123,def456,ghi789"

    Returns:
        List of database ID strings, empty list if not configured.

    Note:
        Returns empty list when NOTION_DATABASE_IDS is not set, allowing the app
        to run without active Notion sync. The sync service will skip polling
        if the list is empty.
    """
    ids_str = os.getenv("NOTION_DATABASE_IDS", "")
    if not ids_str:
        return []
    return [db_id.strip() for db_id in ids_str.split(",") if db_id.strip()]


def get_notion_sync_interval() -> int:
    """Get Notion sync interval in seconds from environment.

    Environment Variable:
        NOTION_SYNC_INTERVAL_SECONDS: Polling interval (default: 60)

    Returns:
        Sync interval in seconds (minimum 10, maximum 600).

    Note:
        Clamps value between 10 seconds (minimum practical polling)
        and 600 seconds (10 minutes maximum delay).
    """
    try:
        interval = int(os.getenv("NOTION_SYNC_INTERVAL_SECONDS", "60"))
        # Clamp between 10s and 600s
        return max(10, min(600, interval))
    except ValueError:
        log.warning(
            "invalid_sync_interval",
            value=os.getenv("NOTION_SYNC_INTERVAL_SECONDS"),
            using_default=60,
        )
        return 60
