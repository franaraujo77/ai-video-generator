"""Worker process entry point for ai-video-generator orchestration platform.

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
import os
import signal
import sys
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from app.config import get_database_url, get_fernet_key
from app.database import async_engine
from app.utils.logging import get_logger

# Initialize structured logger
log = get_logger(__name__)

# Shutdown flag (set by SIGTERM handler)
shutdown_requested = False

# Global asyncpg pool reference (for cleanup in shutdown)
asyncpg_pool: asyncpg.Pool | None = None


class WorkerState:
    """Worker-local state for rate limit and concurrency tracking (Stories 4.5, 4.6).

    Each worker maintains its own in-memory state for API rate limits and
    per-stage parallelism control. This state is NOT shared between workers
    (intentionally worker-local).

    Rate Limit Tracking (Story 4.5):
        gemini_quota_exhausted: Flag indicating Gemini API quota hit 429.
            Set to True on first 429, prevents claiming asset generation tasks.
            Reset to False after midnight PST automatic check.

        gemini_quota_reset_time: Datetime when Gemini quota resets (midnight PST).
            Set when marking quota exhausted, checked for auto-reset.

    Concurrency Tracking (Story 4.6):
        active_asset_tasks: Count of currently processing asset generation tasks.
            Incremented when claiming asset task, decremented on completion/error.

        active_video_tasks: Count of currently processing video generation tasks.
            Incremented when claiming video task, decremented on completion/error.

        active_audio_tasks: Count of currently processing audio generation tasks.
            Incremented when claiming audio task, decremented on completion/error.

        max_concurrent_asset_gen: Maximum parallel asset tasks per worker.
            Default: 12 (Gemini, no published concurrency limit)

        max_concurrent_video_gen: Maximum parallel video tasks per worker.
            Default: 3 (Kling API has 10 concurrent request global limit)

        max_concurrent_audio_gen: Maximum parallel audio tasks per worker.
            Default: 6 (ElevenLabs, no published concurrency limit)

    Note:
        YouTube quota is tracked in database (YouTubeQuotaUsage table).
        Gemini/Kling/ElevenLabs limits are worker-local (transient API limits).
    """

    def __init__(self):
        """Initialize worker state with rate limit and concurrency tracking."""
        from app.config import (
            get_max_concurrent_asset_gen,
            get_max_concurrent_audio_gen,
            get_max_concurrent_video_gen,
        )

        # Rate limit tracking (Story 4.5)
        self.gemini_quota_exhausted: bool = False
        self.gemini_quota_reset_time: datetime | None = None

        # Concurrency counters (Story 4.6)
        self.active_asset_tasks: int = 0
        self.active_video_tasks: int = 0
        self.active_audio_tasks: int = 0

        # Concurrency limits from config (Story 4.6)
        self.max_concurrent_asset_gen: int = get_max_concurrent_asset_gen()
        self.max_concurrent_video_gen: int = get_max_concurrent_video_gen()
        self.max_concurrent_audio_gen: int = get_max_concurrent_audio_gen()

        # Legacy support: max_concurrent_video for backward compatibility
        self.max_concurrent_video: int = self.max_concurrent_video_gen

    def mark_gemini_quota_exhausted(self) -> None:
        """Mark Gemini quota as exhausted (resets at midnight PST).

        Sets quota exhausted flag and calculates reset time (next midnight PST).
        Workers will skip asset generation tasks until reset time passes.
        """
        from datetime import datetime, timedelta, timezone

        self.gemini_quota_exhausted = True

        # Calculate next midnight PST (UTC-8 or UTC-7 depending on DST)
        # For simplicity, use UTC midnight as approximation (8 hours ahead of PST)
        tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
        self.gemini_quota_reset_time = datetime.combine(tomorrow, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )

        log.warning(
            "gemini_quota_marked_exhausted", reset_time=self.gemini_quota_reset_time.isoformat()
        )

    def check_gemini_quota_available(self) -> bool:
        """Check if Gemini quota has reset.

        Auto-resets quota exhausted flag if past reset time.

        Returns:
            True if quota available, False if exhausted.
        """
        from datetime import datetime, timezone

        if not self.gemini_quota_exhausted:
            return True

        # Check if past reset time
        if (
            self.gemini_quota_reset_time
            and datetime.now(timezone.utc) >= self.gemini_quota_reset_time
        ):
            self.gemini_quota_exhausted = False
            self.gemini_quota_reset_time = None
            log.info("gemini_quota_auto_reset")
            return True

        return False

    def can_claim_video_task(self) -> bool:
        """Check if worker can claim another video generation task.

        Returns:
            True if under concurrency limit, False if at max.
        """
        return self.active_video_tasks < self.max_concurrent_video

    def increment_video_tasks(self) -> None:
        """Increment active video task counter.

        Called when claiming a video generation task.
        """
        self.active_video_tasks += 1
        log.debug(
            "video_tasks_incremented",
            active_tasks=self.active_video_tasks,
            max_concurrent=self.max_concurrent_video,
        )

    def decrement_video_tasks(self) -> None:
        """Decrement active video task counter.

        Called when video generation task completes or fails.
        Prevents counter from going negative.
        """
        self.active_video_tasks = max(0, self.active_video_tasks - 1)
        log.debug(
            "video_tasks_decremented",
            active_tasks=self.active_video_tasks,
            max_concurrent=self.max_concurrent_video,
        )

    def can_claim_asset_task(self) -> bool:
        """Check if worker can claim another asset generation task.

        Returns:
            True if under concurrency limit, False if at max.

        Story: 4.6 - Parallel Task Execution (AC1)
        """
        return self.active_asset_tasks < self.max_concurrent_asset_gen

    def increment_asset_tasks(self) -> None:
        """Increment active asset task counter.

        Called when claiming an asset generation task.

        Story: 4.6 - Parallel Task Execution (AC1)
        """
        self.active_asset_tasks += 1
        log.debug(
            "asset_tasks_incremented",
            active_tasks=self.active_asset_tasks,
            max_concurrent=self.max_concurrent_asset_gen,
        )

    def decrement_asset_tasks(self) -> None:
        """Decrement active asset task counter.

        Called when asset generation task completes or fails.
        Prevents counter from going negative.

        Story: 4.6 - Parallel Task Execution (AC1)
        """
        self.active_asset_tasks = max(0, self.active_asset_tasks - 1)
        log.debug(
            "asset_tasks_decremented",
            active_tasks=self.active_asset_tasks,
            max_concurrent=self.max_concurrent_asset_gen,
        )

    def can_claim_audio_task(self) -> bool:
        """Check if worker can claim another audio generation task.

        Returns:
            True if under concurrency limit, False if at max.

        Story: 4.6 - Parallel Task Execution (AC2)
        """
        return self.active_audio_tasks < self.max_concurrent_audio_gen

    def increment_audio_tasks(self) -> None:
        """Increment active audio task counter.

        Called when claiming an audio generation task.

        Story: 4.6 - Parallel Task Execution (AC2)
        """
        self.active_audio_tasks += 1
        log.debug(
            "audio_tasks_incremented",
            active_tasks=self.active_audio_tasks,
            max_concurrent=self.max_concurrent_audio_gen,
        )

    def decrement_audio_tasks(self) -> None:
        """Decrement active audio task counter.

        Called when audio generation task completes or fails.
        Prevents counter from going negative.

        Story: 4.6 - Parallel Task Execution (AC2)
        """
        self.active_audio_tasks = max(0, self.active_audio_tasks - 1)
        log.debug(
            "audio_tasks_decremented",
            active_tasks=self.active_audio_tasks,
            max_concurrent=self.max_concurrent_audio_gen,
        )

    def reload_config(self) -> None:
        """Reload parallelism configuration without worker restart.

        This allows dynamic configuration changes by re-reading environment
        variables. Call periodically (e.g., every 60s) or via signal handler.

        Story: 4.6 - Parallel Task Execution (AC4)
        """
        from app.config import (
            get_max_concurrent_asset_gen,
            get_max_concurrent_audio_gen,
            get_max_concurrent_video_gen,
        )

        old_asset = self.max_concurrent_asset_gen
        old_video = self.max_concurrent_video_gen
        old_audio = self.max_concurrent_audio_gen

        self.max_concurrent_asset_gen = get_max_concurrent_asset_gen()
        self.max_concurrent_video_gen = get_max_concurrent_video_gen()
        self.max_concurrent_audio_gen = get_max_concurrent_audio_gen()

        # Update legacy attribute for backward compatibility
        self.max_concurrent_video = self.max_concurrent_video_gen

        # Log only if values changed
        if (
            old_asset != self.max_concurrent_asset_gen
            or old_video != self.max_concurrent_video_gen
            or old_audio != self.max_concurrent_audio_gen
        ):
            log.info(
                "worker_config_reloaded",
                asset_gen=self.max_concurrent_asset_gen,
                video_gen=self.max_concurrent_video_gen,
                audio_gen=self.max_concurrent_audio_gen,
            )


# Global worker state instance
worker_state = WorkerState()


def signal_handler(signum: int, frame: object) -> None:
    """Handle SIGTERM signal for graceful shutdown.

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
        signal_name=signal.Signals(signum).name,
    )
    shutdown_requested = True


async def worker_main_loop() -> None:
    """Main worker event loop with PgQueuer task claiming.

    Replaces placeholder loop from Story 4.1 with PgQueuer integration.
    Workers claim tasks atomically via FOR UPDATE SKIP LOCKED (PgQueuer automatic).

    Behavior (Story 4.2):
        - Initialize PgQueuer with asyncpg connection pool
        - Import entrypoints to register task handlers
        - Run PgQueuer worker loop (handles polling, LISTEN/NOTIFY, claiming)
        - Exit gracefully on shutdown signal

    Error Handling:
        - Catches all exceptions to prevent worker crash
        - Logs errors with full context
        - PgQueuer handles retry logic for failed tasks

    Raises:
        No exceptions raised (catches all internally)
    """
    global asyncpg_pool

    worker_id = os.getenv("RAILWAY_SERVICE_NAME", "worker-local")
    log.info("worker_started_with_pgqueuer", worker_id=worker_id)

    try:
        # Import queue initialization
        from app.entrypoints import register_entrypoints
        from app.queue import initialize_pgqueuer

        # Initialize PgQueuer
        pgq, pool = await initialize_pgqueuer()

        # Store pool reference for cleanup
        asyncpg_pool = pool

        # Register entrypoints with PgQueuer
        register_entrypoints(pgq)

        # Run PgQueuer worker loop
        # Handles: polling, LISTEN/NOTIFY, FOR UPDATE SKIP LOCKED, retry logic
        await pgq.run()

    except asyncio.CancelledError:
        log.info("worker_cancelled", worker_id=worker_id)
        raise
    except Exception as e:
        log.error(
            "worker_fatal_error",
            worker_id=worker_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise
    finally:
        log.info(
            "worker_shutdown",
            worker_id=worker_id,
        )


async def shutdown_worker() -> None:
    """Graceful shutdown: close database connections and cleanup resources.

    Called during worker shutdown to ensure clean exit.
    Important for Railway deployments to prevent connection leaks.

    Side Effects:
        - Closes asyncpg pool (PgQueuer)
        - Closes async database engine (SQLAlchemy)
        - Disposes connection pool
    """
    log.info("closing_database_connections")

    # Close asyncpg pool (used by PgQueuer)
    if asyncpg_pool:
        await asyncpg_pool.close()
        log.info("asyncpg_pool_closed")

    # Close SQLAlchemy engine
    if async_engine:
        await async_engine.dispose()
        log.info("sqlalchemy_engine_closed")

    log.info("database_connections_closed")


@dataclass
class WorkerConfig:
    """Worker configuration loaded from environment variables."""

    database_url: str
    fernet_key: str


def get_config() -> WorkerConfig:
    """Load and validate worker configuration.

    Returns:
        WorkerConfig with database_url and fernet_key.

    Raises:
        ValueError: If required environment variables not set.
    """
    return WorkerConfig(
        database_url=get_database_url(),
        fernet_key=get_fernet_key(),
    )


def main() -> None:
    """Worker process entry point.

    Initializes worker, registers signal handlers, runs main loop.

    Exit Codes:
        0: Successful shutdown (SIGTERM received)
        1: Fatal error (configuration invalid, database unreachable)
    """
    # Load configuration
    try:
        config = get_config()
        # Redact credentials when logging
        database_host = (
            config.database_url.split("@")[-1].split("/")[0]
            if "@" in config.database_url
            else "local"
        )
        log.info(
            "worker_configuration_loaded",
            database_url_host=database_host,
            pool_size=10,
            max_overflow=5,
        )
    except Exception as e:
        log.error("configuration_load_failed", error=str(e), exc_info=True)
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
        log.error("worker_fatal_error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        # Graceful shutdown
        asyncio.run(shutdown_worker())
        log.info("worker_exited_successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
