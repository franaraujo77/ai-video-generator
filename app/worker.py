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
