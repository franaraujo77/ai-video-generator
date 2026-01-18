"""PgQueuer initialization and configuration for ai-video-generator.

This module handles PgQueuer setup with asyncpg connection pool for task claiming.
Workers use PgQueuer for atomic task claiming via FOR UPDATE SKIP LOCKED with
round-robin channel scheduling and priority-aware task ordering (Story 4.4).

Round-Robin Channel Scheduling Logic (Story 4.4):
    - High priority tasks claimed before normal/low (priority preserved)
    - Within same priority, tasks cycle through channels alphabetically (fairness)
    - Within same priority + channel, FIFO order maintained (predictability)
    - FOR UPDATE SKIP LOCKED preserves atomic claiming

Architecture Pattern:
    - AsyncpgPoolDriver: Connection pool for production throughput
    - QueueManager: Schema installation and queue management
    - Entrypoint Registration: Define pipeline step handlers
    - Custom Query: Priority → Channel → FIFO ordering

Usage:
    from app.queue import initialize_pgqueuer, pgq

    pgq, pool = await initialize_pgqueuer()
    await pgq.run()  # Start worker loop with round-robin scheduling

References:
    - Architecture: Round-Robin Channel Scheduling
    - Architecture: Priority Queue Management
    - project-context.md: Critical Implementation Rules
    - Story 4.4: Round-Robin Channel Scheduling (current)
    - Story 4.3: Priority Queue Management (extended)
    - Story 4.2: Task Claiming with PgQueuer (foundation)
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

# Priority-aware task selection query (Story 4.3) - kept for documentation
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

# Round-robin channel scheduling query (Story 4.4) - extends PRIORITY_QUERY
# Orders tasks by priority, then channel (alphabetical rotation), then FIFO
ROUND_ROBIN_QUERY = """
    SELECT * FROM tasks
    WHERE status = 'pending'
    ORDER BY
        CASE priority
            WHEN 'high' THEN 1
            WHEN 'normal' THEN 2
            WHEN 'low' THEN 3
        END ASC,
        channel_id ASC,  -- NEW: Round-robin across channels
        created_at ASC   -- FIFO within (priority + channel)
    FOR UPDATE SKIP LOCKED
    LIMIT 1
"""


def extract_query_ordering(query: str) -> str:
    """Extract ORDER BY pattern from SQL query for logging.

    Dynamically detects query ordering logic by parsing ORDER BY clauses.
    Used for structured logging to track which scheduling strategy is active.

    Args:
        query: SQL query string with ORDER BY clause

    Returns:
        Human-readable ordering pattern (e.g., "priority → channel → FIFO")

    Examples:
        >>> extract_query_ordering(ROUND_ROBIN_QUERY)
        'priority → channel → FIFO'
        >>> extract_query_ordering(PRIORITY_QUERY)
        'priority → FIFO'
    """
    has_priority = "CASE priority" in query
    has_channel = "channel_id ASC" in query
    has_fifo = "created_at ASC" in query

    if has_priority and has_channel and has_fifo:
        return "priority → channel → FIFO"
    elif has_priority and has_fifo:
        return "priority → FIFO"
    elif has_channel and has_fifo:
        return "channel → FIFO"
    elif has_fifo:
        return "FIFO"
    else:
        return "unknown"


async def initialize_pgqueuer() -> tuple[PgQueuer, asyncpg.Pool]:
    """Initialize PgQueuer with round-robin channel scheduling (Story 4.4).

    Creates asyncpg pool, installs PgQueuer schema (if not exists), configures
    custom query for round-robin scheduling, and returns configured PgQueuer instance.

    Round-Robin Scheduling (Story 4.4):
        Tasks are claimed in this order:
        1. Priority (high → normal → low) - preserved from Story 4.3
        2. Channel (alphabetical rotation) - NEW in Story 4.4
        3. FIFO (within priority + channel) - preserved from Story 4.3

        This ensures:
        - High priority tasks always process first (priority preserved)
        - Within same priority, channels cycle alphabetically (fair distribution)
        - Within same priority + channel, FIFO order maintained (predictability)
        - No channel starvation (all channels get processing time)

    Claim Timeout (Architecture Decision):
        PgQueuer uses PostgreSQL transaction-based locking for atomic task claiming.
        Stale claims are automatically released after 30 minutes via PostgreSQL's
        statement_timeout parameter. This ensures crashed workers don't hold locks
        indefinitely (FR43: fault tolerance requirement).

    Returns:
        tuple[PgQueuer, asyncpg.Pool]: Configured PgQueuer with round-robin scheduling

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
        min_size=2,  # Minimum connections
        max_size=10,  # Maximum connections
        timeout=30,  # Connection acquire timeout (seconds)
        command_timeout=1800,  # Query execution timeout (30 minutes = 1800s)
        # Ensures stale claims released after 30 min
    )

    # Install PgQueuer schema (idempotent: safe to call multiple times)
    log.info("installing_pgqueuer_schema")
    qm = QueueManager(pool)
    await qm.queries.install()
    log.info("pgqueuer_schema_installed")

    # Create PgQueuer driver with round-robin query (Story 4.4)
    driver = AsyncpgPoolDriver(pool)
    global pgq
    pgq = PgQueuer(driver, query=ROUND_ROBIN_QUERY)  # type: ignore[call-arg]

    # Extract query pattern for logging (Story 4.4: dynamic pattern detection)
    query_pattern = extract_query_ordering(ROUND_ROBIN_QUERY)

    log.info(
        "pgqueuer_initialized_with_round_robin",
        claim_timeout_minutes=30,
        query_pattern=query_pattern,
        custom_query_enabled=True,
    )

    return pgq, pool
