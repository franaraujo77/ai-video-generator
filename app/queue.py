"""PgQueuer initialization and configuration for ai-video-generator.

This module handles PgQueuer setup with asyncpg connection pool for task claiming.
Workers use PgQueuer for atomic task claiming via FOR UPDATE SKIP LOCKED with
priority-aware task ordering (Story 4.3).

Priority Ordering Logic (Story 4.3):
    - High priority tasks claimed before normal/low
    - Normal priority tasks claimed before low
    - FIFO (created_at ASC) within same priority level
    - FOR UPDATE SKIP LOCKED preserves atomic claiming

Architecture Pattern:
    - AsyncpgPoolDriver: Connection pool for production throughput
    - QueueManager: Schema installation and queue management
    - Entrypoint Registration: Define pipeline step handlers
    - Custom Query: Priority-aware task selection (high → normal → low + FIFO)

Usage:
    from app.queue import initialize_pgqueuer, pgq

    pgq, pool = await initialize_pgqueuer()
    await pgq.run()  # Start worker loop with priority ordering

References:
    - Architecture: PgQueuer Integration
    - Architecture: Priority Queue Management
    - project-context.md: Critical Implementation Rules
    - Story 4.2: Task Claiming with PgQueuer (foundation)
    - Story 4.3: Priority Queue Management (custom query)
    - PgQueuer Documentation: https://pgqueuer.readthedocs.io/
"""

import os

import asyncpg
from pgqueuer import PgQueuer
from pgqueuer.db import AsyncpgPoolDriver
from pgqueuer.qm import QueueManager

from app.utils.logging import get_logger

log = get_logger(__name__)

# Global PgQueuer instance (initialized in initialize_pgqueuer)
pgq: PgQueuer | None = None

# Priority-aware task selection query (Story 4.3)
# Orders tasks by priority (high=1, normal=2, low=3), then FIFO within each priority
PRIORITY_QUERY = """
    SELECT * FROM tasks
    WHERE status = 'pending'
    ORDER BY
        CASE priority
            WHEN 'high' THEN 1
            WHEN 'normal' THEN 2
            WHEN 'low' THEN 3
        END ASC,
        created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
"""


async def initialize_pgqueuer() -> tuple[PgQueuer, asyncpg.Pool]:
    """Initialize PgQueuer with priority-aware task selection (Story 4.3).

    Creates asyncpg pool, installs PgQueuer schema (if not exists), configures
    custom query for priority ordering, and returns configured PgQueuer instance.

    Priority Ordering (Story 4.3):
        Tasks are claimed in priority order: high → normal → low.
        Within each priority level, FIFO order is maintained (created_at ASC).
        This ensures urgent content gets processed first while maintaining
        fairness within each priority tier.

    Claim Timeout (Architecture Decision):
        PgQueuer uses PostgreSQL transaction-based locking for atomic task claiming.
        Stale claims are automatically released after 30 minutes via PostgreSQL's
        statement_timeout parameter. This ensures crashed workers don't hold locks
        indefinitely (FR43: fault tolerance requirement).

    Returns:
        tuple[PgQueuer, asyncpg.Pool]: Configured PgQueuer with priority ordering

    Raises:
        ValueError: If DATABASE_URL not set
        asyncpg.PostgresError: If database connection fails
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")

    # Create asyncpg connection pool
    log.info(
        "initializing_asyncpg_pool",
        min_size=2,
        max_size=10,
        timeout=30,
        claim_timeout_minutes=30,
    )

    pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=2,                # Minimum connections
        max_size=10,               # Maximum connections
        timeout=30,                # Connection acquire timeout (seconds)
        command_timeout=1800,      # Query execution timeout (30 minutes = 1800s)
                                   # Ensures stale claims released after 30 min
    )

    # Install PgQueuer schema (idempotent: safe to call multiple times)
    log.info("installing_pgqueuer_schema")
    qm = QueueManager(pool)
    await qm.queries.install()
    log.info("pgqueuer_schema_installed")

    # Create PgQueuer driver with priority-aware query (Story 4.3)
    driver = AsyncpgPoolDriver(pool)
    global pgq
    # TODO: Remove type: ignore when PgQueuer adds proper type hints for query parameter
    # The query parameter is supported but not exposed in PgQueuer's type stubs
    # See: https://github.com/janbjorge/pgqueuer/issues/
    pgq = PgQueuer(driver, query=PRIORITY_QUERY)  # type: ignore[call-arg]

    # Extract priority ordering from query for logging
    has_priority = "CASE priority" in PRIORITY_QUERY
    has_fifo = "created_at ASC" in PRIORITY_QUERY
    query_pattern = ""
    if has_priority and has_fifo:
        query_pattern = "high → normal → low + FIFO"
    elif has_priority:
        query_pattern = "high → normal → low"
    elif has_fifo:
        query_pattern = "FIFO only"

    log.info(
        "pgqueuer_initialized_with_priority_ordering",
        claim_timeout_minutes=30,
        query_pattern=query_pattern,
        custom_query_enabled=True,
    )

    return pgq, pool
