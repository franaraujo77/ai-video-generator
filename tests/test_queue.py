"""Tests for PgQueuer queue initialization and configuration.

This module tests the queue infrastructure including:
    - PgQueuer initialization with asyncpg pool
    - Schema installation (idempotent)
    - Connection pool configuration
    - Error handling for missing configuration
    - Priority-aware task selection (Story 4.3)
    - FIFO ordering within priority levels (Story 4.3)
    - Round-robin channel scheduling (Story 4.4)
    - Query pattern extraction for logging (Story 4.4)
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncpg
from app.queue import initialize_pgqueuer, PRIORITY_QUERY, ROUND_ROBIN_QUERY, extract_query_ordering


@pytest.mark.asyncio
async def test_initialize_pgqueuer_success():
    """Test successful PgQueuer initialization with asyncpg pool."""
    # Mock asyncpg.create_pool
    mock_pool = MagicMock(spec=asyncpg.Pool)

    # Mock QueueManager and install method
    mock_qm = MagicMock()
    mock_qm.queries.install = AsyncMock()

    with (
        patch("app.queue.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool,
        patch("app.queue.QueueManager", return_value=mock_qm),
        patch("app.queue.AsyncpgPoolDriver") as mock_driver,
        patch("app.queue.PgQueuer") as mock_pgqueuer,
        patch.dict(os.environ, {"DATABASE_URL": "postgresql://test:test@localhost/test"}),
    ):
        mock_create_pool.return_value = mock_pool

        # Call initialize_pgqueuer
        _pgq, pool = await initialize_pgqueuer()

        # Assert pool created with correct parameters
        mock_create_pool.assert_called_once_with(
            dsn="postgresql://test:test@localhost/test",
            min_size=2,
            max_size=10,
            timeout=30,
            command_timeout=1800,  # 30 minutes for claim timeout
        )

        # Assert schema installation called
        mock_qm.queries.install.assert_called_once()

        # Assert driver created with pool
        mock_driver.assert_called_once_with(mock_pool)

        # Assert PgQueuer instance created
        mock_pgqueuer.assert_called_once()

        # Assert return values
        assert pool == mock_pool


@pytest.mark.asyncio
async def test_initialize_pgqueuer_missing_database_url():
    """Test PgQueuer initialization fails when DATABASE_URL not set."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="DATABASE_URL environment variable not set"):
            await initialize_pgqueuer()


@pytest.mark.asyncio
async def test_initialize_pgqueuer_connection_failure():
    """Test PgQueuer initialization handles database connection failures."""
    with (
        patch("app.queue.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool,
        patch.dict(os.environ, {"DATABASE_URL": "postgresql://test:test@localhost/test"}),
    ):
        # Simulate connection failure
        mock_create_pool.side_effect = asyncpg.PostgresError("Connection refused")

        with pytest.raises(asyncpg.PostgresError, match="Connection refused"):
            await initialize_pgqueuer()


@pytest.mark.asyncio
async def test_initialize_pgqueuer_schema_installation():
    """Test PgQueuer schema installation is called (idempotent operation)."""
    mock_pool = MagicMock(spec=asyncpg.Pool)
    mock_qm = MagicMock()
    mock_qm.queries.install = AsyncMock()

    with (
        patch("app.queue.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool,
        patch("app.queue.QueueManager", return_value=mock_qm),
        patch("app.queue.AsyncpgPoolDriver"),
        patch("app.queue.PgQueuer"),
        patch.dict(os.environ, {"DATABASE_URL": "postgresql://test:test@localhost/test"}),
    ):
        mock_create_pool.return_value = mock_pool

        await initialize_pgqueuer()

        # Verify QueueManager created with pool
        assert mock_qm.queries.install.call_count == 1


@pytest.mark.asyncio
async def test_initialize_pgqueuer_pool_configuration():
    """Test asyncpg pool is configured with correct parameters for production."""
    mock_pool = MagicMock(spec=asyncpg.Pool)
    mock_qm = MagicMock()
    mock_qm.queries.install = AsyncMock()

    with (
        patch("app.queue.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool,
        patch("app.queue.QueueManager", return_value=mock_qm),
        patch("app.queue.AsyncpgPoolDriver"),
        patch("app.queue.PgQueuer"),
        patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@host:5432/db"}),
    ):
        mock_create_pool.return_value = mock_pool

        await initialize_pgqueuer()

        # Verify pool configuration matches production requirements
        call_kwargs = mock_create_pool.call_args[1]
        assert call_kwargs["min_size"] == 2
        assert call_kwargs["max_size"] == 10
        assert call_kwargs["timeout"] == 30
        assert call_kwargs["command_timeout"] == 1800  # 30 minutes for claim timeout


@pytest.mark.asyncio
async def test_initialize_pgqueuer_driver_and_pgqueuer_creation():
    """Test AsyncpgPoolDriver and PgQueuer instance are created correctly."""
    mock_pool = MagicMock(spec=asyncpg.Pool)
    mock_qm = MagicMock()
    mock_qm.queries.install = AsyncMock()
    mock_driver_instance = MagicMock()
    mock_pgqueuer_instance = MagicMock()

    with (
        patch("app.queue.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool,
        patch("app.queue.QueueManager", return_value=mock_qm),
        patch("app.queue.AsyncpgPoolDriver", return_value=mock_driver_instance) as mock_driver,
        patch("app.queue.PgQueuer", return_value=mock_pgqueuer_instance) as mock_pgqueuer,
        patch.dict(os.environ, {"DATABASE_URL": "postgresql://test:test@localhost/test"}),
    ):
        mock_create_pool.return_value = mock_pool

        pgq, pool = await initialize_pgqueuer()

        # Verify driver created with pool
        mock_driver.assert_called_once_with(mock_pool)

        # Verify PgQueuer created with driver and round-robin query (Story 4.4)
        mock_pgqueuer.assert_called_once_with(mock_driver_instance, query=ROUND_ROBIN_QUERY)

        # Verify return values
        assert pgq == mock_pgqueuer_instance
        assert pool == mock_pool


@pytest.mark.asyncio
async def test_initialize_pgqueuer_return_values():
    """Test PgQueuer initialization returns pgq and pool."""
    mock_pool = MagicMock(spec=asyncpg.Pool)
    mock_qm = MagicMock()
    mock_qm.queries.install = AsyncMock()
    mock_pgqueuer_instance = MagicMock()

    with (
        patch("app.queue.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool,
        patch("app.queue.QueueManager", return_value=mock_qm),
        patch("app.queue.AsyncpgPoolDriver"),
        patch("app.queue.PgQueuer", return_value=mock_pgqueuer_instance),
        patch.dict(os.environ, {"DATABASE_URL": "postgresql://test:test@localhost/test"}),
    ):
        mock_create_pool.return_value = mock_pool

        pgq, pool = await initialize_pgqueuer()

        # Verify return values are correct
        assert pgq == mock_pgqueuer_instance
        assert pool == mock_pool


# Story 4.3: Priority Queue Management Tests


@pytest.mark.asyncio
async def test_round_robin_query_passed_to_pgqueuer():
    """Test PgQueuer is initialized with round-robin query (Story 4.4)."""
    mock_pool = MagicMock(spec=asyncpg.Pool)
    mock_qm = MagicMock()
    mock_qm.queries.install = AsyncMock()
    mock_driver_instance = MagicMock()
    mock_pgqueuer_instance = MagicMock()

    with (
        patch("app.queue.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool,
        patch("app.queue.QueueManager", return_value=mock_qm),
        patch("app.queue.AsyncpgPoolDriver", return_value=mock_driver_instance) as mock_driver,
        patch("app.queue.PgQueuer", return_value=mock_pgqueuer_instance) as mock_pgqueuer,
        patch.dict(os.environ, {"DATABASE_URL": "postgresql://test:test@localhost/test"}),
    ):
        mock_create_pool.return_value = mock_pool

        await initialize_pgqueuer()

        # Verify PgQueuer created with driver AND custom round-robin query
        mock_pgqueuer.assert_called_once_with(mock_driver_instance, query=ROUND_ROBIN_QUERY)


def test_priority_query_structure():
    """Test PRIORITY_QUERY has correct SQL structure for priority ordering."""
    # Verify query contains essential priority ordering logic
    assert "CASE priority" in PRIORITY_QUERY
    assert "WHEN 'high' THEN 1" in PRIORITY_QUERY
    assert "WHEN 'normal' THEN 2" in PRIORITY_QUERY
    assert "WHEN 'low' THEN 3" in PRIORITY_QUERY
    assert "created_at ASC" in PRIORITY_QUERY
    assert "FOR UPDATE SKIP LOCKED" in PRIORITY_QUERY
    assert "LIMIT 1" in PRIORITY_QUERY
    assert "status = 'pending'" in PRIORITY_QUERY


def test_priority_query_fifo_within_priority():
    """Test PRIORITY_QUERY enforces FIFO within each priority level."""
    # Verify query orders by priority first, then created_at (FIFO)
    query_lines = [line.strip() for line in PRIORITY_QUERY.split("\n") if line.strip()]

    # Find ORDER BY clause
    order_by_index = next(i for i, line in enumerate(query_lines) if "ORDER BY" in line)

    # Verify CASE priority comes before created_at in ORDER BY
    case_index = next(i for i, line in enumerate(query_lines) if "CASE priority" in line)
    created_at_index = next(i for i, line in enumerate(query_lines) if "created_at ASC" in line)

    assert (
        order_by_index < case_index < created_at_index
    ), "Query must order by priority THEN created_at (FIFO within priority)"


def test_priority_query_atomic_claiming():
    """Test PRIORITY_QUERY preserves atomic claiming with FOR UPDATE SKIP LOCKED."""
    # Verify FOR UPDATE SKIP LOCKED is present for atomic claiming
    assert "FOR UPDATE SKIP LOCKED" in PRIORITY_QUERY

    # Verify LIMIT 1 ensures exactly one task claimed
    assert "LIMIT 1" in PRIORITY_QUERY


def test_priority_query_only_pending_tasks():
    """Test PRIORITY_QUERY only selects pending tasks."""
    # Verify query filters by pending status
    assert "status = 'pending'" in PRIORITY_QUERY


# Story 4.4: Round-Robin Channel Scheduling Tests


def test_round_robin_query_structure():
    """Test ROUND_ROBIN_QUERY has correct SQL structure for round-robin scheduling."""
    # Verify query contains essential priority ordering logic (preserved from Story 4.3)
    assert "CASE priority" in ROUND_ROBIN_QUERY
    assert "WHEN 'high' THEN 1" in ROUND_ROBIN_QUERY
    assert "WHEN 'normal' THEN 2" in ROUND_ROBIN_QUERY
    assert "WHEN 'low' THEN 3" in ROUND_ROBIN_QUERY

    # Verify query contains channel_id for round-robin (NEW in Story 4.4)
    assert "channel_id ASC" in ROUND_ROBIN_QUERY

    # Verify query contains FIFO ordering (preserved from Story 4.3)
    assert "created_at ASC" in ROUND_ROBIN_QUERY

    # Verify atomic claiming and limit (preserved from Story 4.2)
    assert "FOR UPDATE SKIP LOCKED" in ROUND_ROBIN_QUERY
    assert "LIMIT 1" in ROUND_ROBIN_QUERY

    # Verify pending filter (preserved from Story 4.2)
    assert "status = 'pending'" in ROUND_ROBIN_QUERY


def test_round_robin_query_ordering():
    """Test ROUND_ROBIN_QUERY enforces priority → channel → FIFO ordering."""
    # Parse query lines
    query_lines = [line.strip() for line in ROUND_ROBIN_QUERY.split("\n") if line.strip()]

    # Find ORDER BY clause
    order_by_index = next(i for i, line in enumerate(query_lines) if "ORDER BY" in line)

    # Find ordering column positions
    case_index = next(i for i, line in enumerate(query_lines) if "CASE priority" in line)
    channel_index = next(i for i, line in enumerate(query_lines) if "channel_id ASC" in line)
    created_at_index = next(i for i, line in enumerate(query_lines) if "created_at ASC" in line)

    # Verify ordering: priority THEN channel THEN created_at
    assert (
        order_by_index < case_index < channel_index < created_at_index
    ), "Query must order by priority THEN channel_id THEN created_at"


def test_round_robin_query_atomic_claiming():
    """Test ROUND_ROBIN_QUERY preserves atomic claiming with FOR UPDATE SKIP LOCKED."""
    # Verify FOR UPDATE SKIP LOCKED is present for atomic claiming
    assert "FOR UPDATE SKIP LOCKED" in ROUND_ROBIN_QUERY

    # Verify LIMIT 1 ensures exactly one task claimed
    assert "LIMIT 1" in ROUND_ROBIN_QUERY


def test_round_robin_query_only_pending_tasks():
    """Test ROUND_ROBIN_QUERY only selects pending tasks."""
    # Verify query filters by pending status
    assert "status = 'pending'" in ROUND_ROBIN_QUERY


def test_extract_query_ordering_priority_channel_fifo():
    """Test extract_query_ordering detects priority → channel → FIFO pattern."""
    pattern = extract_query_ordering(ROUND_ROBIN_QUERY)
    assert pattern == "priority → channel → FIFO"


def test_extract_query_ordering_priority_fifo():
    """Test extract_query_ordering detects priority → FIFO pattern (Story 4.3)."""
    pattern = extract_query_ordering(PRIORITY_QUERY)
    assert pattern == "priority → FIFO"


def test_extract_query_ordering_unknown():
    """Test extract_query_ordering returns 'unknown' for unexpected patterns."""
    # Query with no recognizable ordering
    query = "SELECT * FROM tasks WHERE status = 'pending'"
    pattern = extract_query_ordering(query)
    assert pattern == "unknown"


def test_extract_query_ordering_fifo_only():
    """Test extract_query_ordering detects FIFO-only pattern."""
    query = """
        SELECT * FROM tasks
        WHERE status = 'pending'
        ORDER BY created_at ASC
    """
    pattern = extract_query_ordering(query)
    assert pattern == "FIFO"


def test_extract_query_ordering_channel_fifo():
    """Test extract_query_ordering detects channel → FIFO pattern."""
    query = """
        SELECT * FROM tasks
        WHERE status = 'pending'
        ORDER BY channel_id ASC, created_at ASC
    """
    pattern = extract_query_ordering(query)
    assert pattern == "channel → FIFO"


def test_round_robin_extends_priority_query():
    """Test ROUND_ROBIN_QUERY is an extension of PRIORITY_QUERY, not a replacement."""
    # ROUND_ROBIN_QUERY should contain all priority logic from PRIORITY_QUERY
    assert "CASE priority" in ROUND_ROBIN_QUERY
    assert "WHEN 'high' THEN 1" in ROUND_ROBIN_QUERY
    assert "WHEN 'normal' THEN 2" in ROUND_ROBIN_QUERY
    assert "WHEN 'low' THEN 3" in ROUND_ROBIN_QUERY

    # ROUND_ROBIN_QUERY should ADD channel_id (not replace anything)
    assert "channel_id ASC" in ROUND_ROBIN_QUERY
    assert "created_at ASC" in ROUND_ROBIN_QUERY

    # Both queries should preserve atomic claiming
    assert "FOR UPDATE SKIP LOCKED" in PRIORITY_QUERY
    assert "FOR UPDATE SKIP LOCKED" in ROUND_ROBIN_QUERY


def test_round_robin_query_comments():
    """Test ROUND_ROBIN_QUERY has inline comments explaining new round-robin logic."""
    # Verify inline SQL comments document the round-robin change
    assert "--" in ROUND_ROBIN_QUERY  # SQL comment syntax
    # Verify comment mentions "round-robin" or "channel"
    lines_with_channel = [line for line in ROUND_ROBIN_QUERY.split("\n") if "channel_id" in line]
    assert any(
        "--" in line for line in lines_with_channel
    ), "channel_id line should have inline comment explaining round-robin"
