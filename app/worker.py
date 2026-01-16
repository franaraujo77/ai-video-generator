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
import contextlib
import os
import signal
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import get_database_url, get_fernet_key
from app.database import async_engine
from app.utils.logging import get_logger

# Initialize structured logger
log = get_logger(__name__)

# Shutdown flag (set by SIGTERM handler)
shutdown_requested = False


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
    """Main worker event loop - runs continuously until SIGTERM received.

    This function implements the foundational worker loop structure.
    Task claiming and processing will be added in future stories:
        - Story 4.2: PgQueuer integration for task claiming
        - Story 4.8: Full pipeline orchestration

    Current Behavior (Story 4.1):
        - Logs heartbeat every 60 seconds
        - Sleeps 1 second between iterations
        - Exits gracefully on shutdown signal

    Future Behavior (Story 4.2+):
        - Claim tasks from PgQueuer (FOR UPDATE SKIP LOCKED)
        - Process claimed tasks via pipeline orchestrator
        - Update task status after completion

    Error Handling:
        - Catches all exceptions to prevent worker crash
        - Logs errors with full context
        - Continues running unless fatal error (DB unreachable)

    Raises:
        No exceptions raised (catches all internally)
    """
    worker_id = os.getenv("RAILWAY_SERVICE_NAME", "worker-local")
    log.info("worker_started", worker_id=worker_id)

    # Use datetime.now(timezone.utc) instead of deprecated datetime.utcnow()
    # Python 3.12+ deprecates utcnow() in favor of timezone-aware timestamps
    last_heartbeat = datetime.now(timezone.utc)
    iteration_count = 0
    consecutive_errors = 0

    try:
        while not shutdown_requested:
            iteration_count += 1

            # Heartbeat logging (every 60 seconds)
            now = datetime.now(timezone.utc)
            if (now - last_heartbeat).total_seconds() >= 60:
                log.info(
                    "worker_heartbeat",
                    worker_id=worker_id,
                    iteration_count=iteration_count,
                    consecutive_errors=consecutive_errors,
                )
                last_heartbeat = now

            try:
                # PLACEHOLDER: Task claiming will be added in Story 4.2
                # For now, just sleep to prevent CPU spinning
                await asyncio.sleep(1)

                # Reset error counter on successful iteration
                consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                log.error(
                    "worker_loop_error",
                    worker_id=worker_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    consecutive_errors=consecutive_errors,
                    exc_info=True,
                )

                # Alert if too many consecutive errors (possible fatal issue)
                if consecutive_errors > 10:
                    log.critical(
                        "worker_excessive_errors",
                        worker_id=worker_id,
                        consecutive_errors=consecutive_errors,
                        message="Worker experiencing excessive errors, may need restart",
                    )
                    # Reset counter to prevent log spam
                    consecutive_errors = 0

                # Sleep before retry to prevent tight error loop
                # Suppress cancellation during error recovery (allows graceful shutdown)
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.sleep(5)

    except asyncio.CancelledError:
        log.info("worker_cancelled", worker_id=worker_id)
        raise

    finally:
        log.info(
            "worker_shutdown",
            worker_id=worker_id,
            total_iterations=iteration_count,
        )


async def shutdown_worker() -> None:
    """Graceful shutdown: close database connections and cleanup resources.

    Called during worker shutdown to ensure clean exit.
    Important for Railway deployments to prevent connection leaks.

    Side Effects:
        - Closes async database engine
        - Disposes connection pool
    """
    log.info("closing_database_connections")
    if async_engine:
        await async_engine.dispose()
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
        log.critical("configuration_load_failed", error=str(e), exc_info=True)
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
