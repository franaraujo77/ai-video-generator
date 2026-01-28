"""Configuration management for the orchestration layer.

This module provides centralized configuration loading from environment variables.
All configuration values are loaded at import time and cached.

Environment Variables:
    DATABASE_URL: PostgreSQL connection URL (required for production)
    FERNET_KEY: Encryption key for credentials (required)
    GOOGLE_CLIENT_ID: Google OAuth client ID for YouTube operations (required for Story 7.2)
    GOOGLE_CLIENT_SECRET: Google OAuth client secret for YouTube operations (required for Story 7.2)
    DEFAULT_VOICE_ID: Fallback ElevenLabs voice ID when channel voice not set (optional)
    WORKSPACE_CLEANUP_ENABLED: Enable daily workspace cleanup (default: "true", Story 8.5)
    WORKSPACE_CLEANUP_RETENTION_DAYS: Days to retain workspace files (default: 7, Story 8.5)
    WORKSPACE_CLEANUP_SCHEDULE: Cron schedule for cleanup (default: "0 3 * * *", Story 8.5)

Usage:
    from app.config import get_default_voice_id, get_database_url, get_google_client_id

    voice_id = get_default_voice_id()  # Returns None if not set
    db_url = get_database_url()  # Raises if DATABASE_URL not set
    client_id = get_google_client_id()  # Raises if GOOGLE_CLIENT_ID not set
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


@lru_cache
def get_google_client_id() -> str:
    """Get Google OAuth client ID from environment.

    Environment Variable:
        GOOGLE_CLIENT_ID: Google OAuth client ID from client_secret.json
            Format: xxxxx.apps.googleusercontent.com

    Returns:
        Google client ID string.

    Raises:
        ValueError: If GOOGLE_CLIENT_ID not set or invalid format.

    Note:
        Client ID must match the value in client_secret.json (Story 7.1).
        Used by YouTubeService for OAuth token refresh automation (Story 7.2).
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise ValueError(
            "GOOGLE_CLIENT_ID environment variable is required for YouTube operations. "
            "Extract from client_secret.json: .installed.client_id"
        )

    # Validate format (must end with .apps.googleusercontent.com)
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise ValueError(
            f"Invalid GOOGLE_CLIENT_ID format: {client_id[:20]}... "
            f"Must end with '.apps.googleusercontent.com'"
        )

    return client_id


@lru_cache
def get_google_client_secret() -> str:
    """Get Google OAuth client secret from environment.

    Environment Variable:
        GOOGLE_CLIENT_SECRET: Google OAuth client secret from client_secret.json
            Format: GOCSPX-xxxxxxxxxxxxx

    Returns:
        Google client secret string.

    Raises:
        ValueError: If GOOGLE_CLIENT_SECRET not set or invalid format.

    Note:
        Client secret must match the value in client_secret.json (Story 7.1).
        Used by YouTubeService for OAuth token refresh automation (Story 7.2).
    """
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_secret:
        raise ValueError(
            "GOOGLE_CLIENT_SECRET environment variable is required for YouTube operations. "
            "Extract from client_secret.json: .installed.client_secret"
        )

    # Validate format (must start with GOCSPX-)
    if not client_secret.startswith("GOCSPX-"):
        raise ValueError(
            f"Invalid GOOGLE_CLIENT_SECRET format: {client_secret[:10]}... "
            f"Must start with 'GOCSPX-'"
        )

    return client_secret


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


def get_notion_assets_database_id() -> str:
    """Get Notion Assets database ID from environment.

    Environment Variable:
        NOTION_ASSETS_DATABASE_ID: Notion Assets database ID for Story 5.3
        Example: "d8503431f040432eb91c3b033460fbbd"

    Returns:
        Assets database ID string.

    Raises:
        ValueError: If NOTION_ASSETS_DATABASE_ID not set.

    Note:
        This database stores asset file metadata (characters, environments, props)
        created by the asset generation step. It links to the Tasks database via
        relation property.

    Story: 5.3 - Asset Review Interface
    """
    db_id = os.getenv("NOTION_ASSETS_DATABASE_ID")
    if not db_id:
        raise ValueError(
            "NOTION_ASSETS_DATABASE_ID environment variable is required. "
            "Set this to your Notion Assets database ID."
        )
    return db_id.strip()


def get_notion_tasks_collection_id() -> str:
    """Get Notion Tasks collection ID from environment.

    Environment Variable:
        NOTION_TASKS_COLLECTION_ID: Notion Tasks collection ID (includes "collection://" prefix)
        Example: "collection://1b4bdba3-2e09-4cc7-be3b-f6475d49298a"

    Returns:
        Tasks collection ID string (with collection:// prefix).

    Raises:
        ValueError: If NOTION_TASKS_COLLECTION_ID not set.

    Note:
        This is the collection (data source) ID for the Tasks database, used when
        creating asset entries that need to link back to parent tasks.

    Story: 5.3 - Asset Review Interface
    """
    collection_id = os.getenv("NOTION_TASKS_COLLECTION_ID")
    if not collection_id:
        raise ValueError(
            "NOTION_TASKS_COLLECTION_ID environment variable is required. "
            "Set this to your Notion Tasks collection ID (with 'collection://' prefix)."
        )
    return collection_id.strip()


def get_notion_videos_database_id() -> str:
    """Get Notion Videos database ID from environment.

    Environment Variable:
        NOTION_VIDEOS_DATABASE_ID: Notion Videos database ID for Story 5.4
        Example: "e9614542g151543fc02d4c144571gccf"

    Returns:
        Videos database ID string.

    Raises:
        ValueError: If NOTION_VIDEOS_DATABASE_ID not set.

    Note:
        This database stores video clip metadata (18 clips per task) created by
        the video generation step. It links to the Tasks database via relation property.
        Videos are optimized with MP4 faststart for streaming playback in Notion.

    Story: 5.4 - Video Review Interface
    """
    db_id = os.getenv("NOTION_VIDEOS_DATABASE_ID")
    if not db_id:
        raise ValueError(
            "NOTION_VIDEOS_DATABASE_ID environment variable is required. "
            "Set this to your Notion Videos database ID."
        )
    return db_id.strip()


def get_notion_audio_database_id() -> str:
    """Get Notion Audio database ID from environment.

    Environment Variable:
        NOTION_AUDIO_DATABASE_ID: Notion Audio database ID for Story 5.5
        Example: "f0725653h262654gd13e5d255682hdde"

    Returns:
        Audio database ID string.

    Raises:
        ValueError: If NOTION_AUDIO_DATABASE_ID not set.

    Note:
        This database stores audio clip metadata (36 clips per task: 18 narration + 18 SFX)
        created by the audio generation step. It links to the Tasks database via relation
        property. Audio files are web-optimized (MP3/WAV format) for direct playback in Notion.

    Story: 5.5 - Audio Review Interface
    """
    db_id = os.getenv("NOTION_AUDIO_DATABASE_ID")
    if not db_id:
        raise ValueError(
            "NOTION_AUDIO_DATABASE_ID environment variable is required. "
            "Set this to your Notion Audio database ID."
        )
    return db_id.strip()


def get_notion_sync_interval() -> int:
    """Get Notion sync interval in seconds from environment.

    Environment Variable:
        NOTION_SYNC_INTERVAL_SECONDS: Polling interval (default: 10)

    Returns:
        Sync interval in seconds (minimum 10, maximum 600).

    Note:
        Clamps value between 10 seconds (minimum practical polling)
        and 600 seconds (10 minutes maximum delay).

        Changed in Story 5.6: Default reduced from 60s to 10s for
        real-time status updates (<5s latency target, NFR-P3).
    """
    try:
        interval = int(os.getenv("NOTION_SYNC_INTERVAL_SECONDS", "10"))
        # Clamp between 10s and 600s
        return max(10, min(600, interval))
    except ValueError:
        log.warning(
            "invalid_sync_interval",
            value=os.getenv("NOTION_SYNC_INTERVAL_SECONDS"),
            using_default=10,
        )
        return 10


# Parallelism defaults (Story 4.6)
DEFAULT_MAX_CONCURRENT_ASSET = 12  # Gemini: no published limit, conservative
DEFAULT_MAX_CONCURRENT_VIDEO = 3  # Kling: 10 global limit, 3 workers x 3 = 9 total
DEFAULT_MAX_CONCURRENT_AUDIO = 6  # ElevenLabs: no published limit, conservative

# Video generation defaults (Story 5.4)
DEFAULT_VIDEO_DURATION_SECONDS = 10.0  # Kling generates 10-second clips by default


def get_max_concurrent_asset_gen() -> int:
    """Get max concurrent asset generation tasks per worker.

    This limits parallelism for Gemini asset generation within each worker.
    Rate limiting (quota exhaustion) is handled separately via WorkerState.

    Environment Variable:
        MAX_CONCURRENT_ASSET_GEN: Maximum parallel asset tasks (default: 12)

    Returns:
        Maximum concurrent asset generation tasks.

    Note:
        Default of 12 is conservative for Gemini API, which has daily quota
        limits but no published concurrency limits. Each worker enforces this
        limit independently (worker-local state, not global).

    Story: 4.6 - Parallel Task Execution (AC4)
    """
    return int(os.getenv("MAX_CONCURRENT_ASSET_GEN", str(DEFAULT_MAX_CONCURRENT_ASSET)))


def get_max_concurrent_video_gen() -> int:
    """Get max concurrent video generation tasks per worker.

    This limits parallelism for Kling video generation within each worker.
    Kling API has a GLOBAL limit of 10 concurrent requests across all clients.

    Environment Variable:
        MAX_CONCURRENT_VIDEO_GEN: Maximum parallel video tasks (default: 3)

    Returns:
        Maximum concurrent video generation tasks.

    Note:
        Default of 3 per worker is conservative. With 3 workers, this gives
        9 concurrent videos system-wide (under Kling's 10 limit). Each worker
        enforces this limit independently (worker-local state).

    Story: 4.6 - Parallel Task Execution (AC2)
    """
    return int(os.getenv("MAX_CONCURRENT_VIDEO_GEN", str(DEFAULT_MAX_CONCURRENT_VIDEO)))


def get_max_concurrent_audio_gen() -> int:
    """Get max concurrent audio generation tasks per worker.

    This limits parallelism for ElevenLabs audio generation within each worker.
    ElevenLabs has character-based pricing with no published concurrency limits.

    Environment Variable:
        MAX_CONCURRENT_AUDIO_GEN: Maximum parallel audio tasks (default: 6)

    Returns:
        Maximum concurrent audio generation tasks.

    Note:
        Default of 6 is conservative for ElevenLabs API. Each worker enforces
        this limit independently (worker-local state, not global).

    Story: 4.6 - Parallel Task Execution (AC2)
    """
    return int(os.getenv("MAX_CONCURRENT_AUDIO_GEN", str(DEFAULT_MAX_CONCURRENT_AUDIO)))


def get_workspace_cleanup_enabled() -> bool:
    """Get workspace cleanup enabled flag from environment.

    Environment Variable:
        WORKSPACE_CLEANUP_ENABLED: Enable daily workspace cleanup (default: "true")
        Values: "true", "false" (case-insensitive)

    Returns:
        True if cleanup is enabled, False otherwise.

    Note:
        When disabled, workspace cleanup scheduler will not start.
        Set to "false" in development to preserve workspace files for debugging.

    Story: 8.5 - Temporary File Cleanup
    """
    return os.getenv("WORKSPACE_CLEANUP_ENABLED", "true").lower() == "true"


def get_workspace_cleanup_retention_days() -> int:
    """Get workspace cleanup retention period from environment.

    Environment Variable:
        WORKSPACE_CLEANUP_RETENTION_DAYS: Days to retain completed task workspaces (default: 7)

    Returns:
        Number of days to retain workspace files (minimum 1, maximum 365).

    Note:
        Only tasks in PUBLISHED or CANCELLED status older than this period
        will have their workspace directories deleted. Tasks in error states
        or in-progress are preserved indefinitely.

    Story: 8.5 - Temporary File Cleanup
    """
    try:
        retention = int(os.getenv("WORKSPACE_CLEANUP_RETENTION_DAYS", "7"))
        # Clamp between 1 day and 365 days
        return max(1, min(365, retention))
    except ValueError:
        log.warning(
            "invalid_cleanup_retention_days",
            value=os.getenv("WORKSPACE_CLEANUP_RETENTION_DAYS"),
            using_default=7,
        )
        return 7


def get_workspace_cleanup_schedule() -> str:
    """Get workspace cleanup cron schedule from environment.

    Environment Variable:
        WORKSPACE_CLEANUP_SCHEDULE: Cron schedule for cleanup job (default: "0 3 * * *")
        Format: "minute hour day month day_of_week"
        Example: "0 3 * * *" = daily at 3am Pacific Time

    Returns:
        Cron schedule string.

    Note:
        Default schedule runs at 3am Pacific Time (QUOTA_TIMEZONE) to avoid
        interfering with prime-time video generation workloads. Timezone is
        configured via QUOTA_TIMEZONE environment variable (default: America/Los_Angeles).

    Story: 8.5 - Temporary File Cleanup
    """
    return os.getenv("WORKSPACE_CLEANUP_SCHEDULE", "0 3 * * *")
