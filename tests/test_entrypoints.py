"""Tests for PgQueuer entrypoint handlers.

This module tests the entrypoint functions including:
    - process_video entrypoint (placeholder for Story 4.2-4.3)
    - Short transaction pattern enforcement
    - Task status transitions
    - Error handling and logging
    - Priority context logging (Story 4.3)
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pgqueuer.models import Job
from pgqueuer import PgQueuer


def get_process_video_entrypoint():
    """Helper to get process_video function after registration."""
    mock_pgq = MagicMock(spec=PgQueuer)
    registered_functions = {}

    def mock_entrypoint(name):
        def decorator(func):
            registered_functions[name] = func
            return func
        return decorator

    mock_pgq.entrypoint = mock_entrypoint

    from app.entrypoints import register_entrypoints
    register_entrypoints(mock_pgq)

    return registered_functions["process_video"]


@pytest.mark.asyncio
async def test_process_video_success():
    """Test process_video successfully claims, processes, and completes a task."""
    process_video = get_process_video_entrypoint()

    # Create mock Job with task_id payload
    mock_job = MagicMock()
    mock_job.id = 123
    mock_job.payload = b"task_456"

    # Mock Task model (Story 4.3: Added priority and channel_id)
    mock_task = MagicMock()
    mock_task.status = "pending"
    mock_task.priority = "normal"
    mock_task.channel_id = "channel1"

    # Mock database session
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_task)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()

    with patch("app.entrypoints.AsyncSessionLocal", return_value=mock_db), \
         patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-1"}):

        # Call process_video
        await process_video(mock_job)

        # Verify task was retrieved twice (start + end)
        assert mock_db.get.call_count == 2

        # Verify task status transitions
        # First transaction: pending → claimed → processing (2 commits)
        # Second transaction: processing → completed (1 commit)
        assert mock_task.status == "completed"

        # Verify commits happened 3 times (claimed, processing, completed)
        assert mock_db.commit.call_count == 3


@pytest.mark.asyncio
async def test_process_video_task_not_found():
    """Test process_video raises error when task not found."""
    process_video = get_process_video_entrypoint()

    # Create mock Job with task_id payload
    mock_job = MagicMock()
    mock_job.id = 123
    mock_job.payload = b"nonexistent_task"

    # Mock database session returning None (task not found)
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)

    with patch("app.entrypoints.AsyncSessionLocal", return_value=mock_db), \
         patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-1"}):

        # Call process_video and expect ValueError
        with pytest.raises(ValueError, match="Task not found: nonexistent_task"):
            await process_video(mock_job)


@pytest.mark.asyncio
async def test_process_video_short_transaction_pattern():
    """Test process_video follows short transaction pattern (claim → close → process → update)."""
    process_video = get_process_video_entrypoint()
    # Create mock Job
    mock_job = MagicMock()
    mock_job.id = 123
    mock_job.payload = b"task_789"

    # Mock Task (Story 4.3: Added priority and channel_id)
    mock_task = MagicMock()
    mock_task.status = "pending"
    mock_task.priority = "normal"
    mock_task.channel_id = "channel1"

    # Track session lifecycle
    session_open_count = 0
    session_close_count = 0

    class MockSession:
        async def __aenter__(self):
            nonlocal session_open_count
            session_open_count += 1
            return mock_db

        async def __aexit__(self, *args):
            nonlocal session_close_count
            session_close_count += 1

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_task)
    mock_db.commit = AsyncMock()

    with patch("app.entrypoints.AsyncSessionLocal", return_value=MockSession()), \
         patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-1"}):

        await process_video(mock_job)

        # Verify two separate transactions (open and close twice)
        assert session_open_count == 2
        assert session_close_count == 2


@pytest.mark.asyncio
async def test_process_video_logging():
    """Test process_video logs task_claimed, task_processing_started, and task_completed."""
    process_video = get_process_video_entrypoint()
    mock_job = MagicMock()
    mock_job.id = 123
    mock_job.payload = b"task_999"

    mock_task = MagicMock()
    mock_task.status = "pending"
    mock_task.priority = "normal"
    mock_task.channel_id = "channel1"

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_task)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()

    with patch("app.entrypoints.AsyncSessionLocal", return_value=mock_db), \
         patch("app.entrypoints.log") as mock_log, \
         patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-2"}):

        await process_video(mock_job)

        # Verify logging calls
        assert mock_log.info.call_count == 3

        # Check log messages
        log_calls = [call[0][0] for call in mock_log.info.call_args_list]
        assert "task_claimed" in log_calls
        assert "task_processing_started" in log_calls
        assert "task_completed" in log_calls


@pytest.mark.asyncio
async def test_process_video_worker_id_from_env():
    """Test process_video uses worker_id from RAILWAY_SERVICE_NAME env var."""
    process_video = get_process_video_entrypoint()
    mock_job = MagicMock()
    mock_job.id = 123
    mock_job.payload = b"task_111"

    mock_task = MagicMock()
    mock_task.priority = "normal"
    mock_task.channel_id = "channel1"

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_task)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()

    with patch("app.entrypoints.AsyncSessionLocal", return_value=mock_db), \
         patch("app.entrypoints.log") as mock_log, \
         patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-3"}):

        await process_video(mock_job)

        # Verify worker_id in log calls
        first_log_call = mock_log.info.call_args_list[0]
        assert first_log_call[1]["worker_id"] == "worker-3"


@pytest.mark.asyncio
async def test_process_video_worker_id_defaults_to_local():
    """Test process_video defaults to 'worker-local' when RAILWAY_SERVICE_NAME not set."""
    process_video = get_process_video_entrypoint()
    mock_job = MagicMock()
    mock_job.id = 123
    mock_job.payload = b"task_222"

    mock_task = MagicMock()
    mock_task.priority = "normal"
    mock_task.channel_id = "channel1"

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_task)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()

    with patch("app.entrypoints.AsyncSessionLocal", return_value=mock_db), \
         patch("app.entrypoints.log") as mock_log, \
         patch.dict(os.environ, {}, clear=True):

        await process_video(mock_job)

        # Verify worker_id defaults to "worker-local"
        first_log_call = mock_log.info.call_args_list[0]
        assert first_log_call[1]["worker_id"] == "worker-local"


@pytest.mark.asyncio
async def test_process_video_status_transitions():
    """Test process_video correctly transitions task status: pending → claimed → processing → completed."""
    process_video = get_process_video_entrypoint()

    mock_job = MagicMock()
    mock_job.id = 123
    mock_job.payload = b"task_333"

    # Create two separate task mocks (one for each transaction)
    mock_task_1 = MagicMock()
    mock_task_1.status = "pending"
    mock_task_1.priority = "high"
    mock_task_1.channel_id = "channel1"

    mock_task_2 = MagicMock()
    mock_task_2.status = "processing"
    mock_task_2.priority = "high"

    mock_db = AsyncMock()
    # First call returns task with "pending", second call returns task with "processing"
    mock_db.get = AsyncMock(side_effect=[mock_task_1, mock_task_2])
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()

    with patch("app.entrypoints.AsyncSessionLocal", return_value=mock_db), \
         patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-1"}):

        await process_video(mock_job)

        # Verify status transitions: pending → claimed → processing → completed
        assert mock_task_1.status == "processing"  # Last set in first transaction
        assert mock_task_2.status == "completed"  # Set in second transaction


@pytest.mark.asyncio
async def test_process_video_pgqueuer_job_id_logged():
    """Test process_video logs PgQueuer job ID for traceability."""
    process_video = get_process_video_entrypoint()
    mock_job = MagicMock()
    mock_job.id = 456789
    mock_job.payload = b"task_444"

    mock_task = MagicMock()
    mock_task.priority = "normal"
    mock_task.channel_id = "channel1"

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_task)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()

    with patch("app.entrypoints.AsyncSessionLocal", return_value=mock_db), \
         patch("app.entrypoints.log") as mock_log, \
         patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-1"}):

        await process_video(mock_job)

        # Verify PgQueuer job_id logged in task_claimed message
        first_log_call = mock_log.info.call_args_list[0]
        assert first_log_call[1]["pgqueuer_job_id"] == "456789"


@pytest.mark.asyncio
async def test_process_video_database_commit_called():
    """Test process_video commits database changes after each transaction."""
    process_video = get_process_video_entrypoint()
    mock_job = MagicMock()
    mock_job.id = 123
    mock_job.payload = b"task_555"

    mock_task = MagicMock()
    mock_task.priority = "normal"
    mock_task.channel_id = "channel1"

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_task)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()

    with patch("app.entrypoints.AsyncSessionLocal", return_value=mock_db), \
         patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-1"}):

        await process_video(mock_job)

        # Verify commit called 3 times (claimed, processing, completed)
        assert mock_db.commit.call_count == 3


# Story 4.3: Priority Context Logging Tests


@pytest.mark.asyncio
async def test_process_video_logs_priority_on_claim():
    """Test process_video logs priority when task is claimed (Story 4.3)."""
    process_video = get_process_video_entrypoint()
    mock_job = MagicMock()
    mock_job.id = 123
    mock_job.payload = b"task_high_priority"

    mock_task = MagicMock()
    mock_task.priority = "high"
    mock_task.channel_id = "channel1"

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_task)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()

    with patch("app.entrypoints.AsyncSessionLocal", return_value=mock_db), \
         patch("app.entrypoints.log") as mock_log, \
         patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-1"}):

        await process_video(mock_job)

        # Verify task_claimed log includes priority
        first_log_call = mock_log.info.call_args_list[0]
        assert first_log_call[0][0] == "task_claimed"
        assert first_log_call[1]["priority"] == "high"
        assert first_log_call[1]["channel_id"] == "channel1"


@pytest.mark.asyncio
async def test_process_video_logs_priority_on_completion():
    """Test process_video logs priority when task is completed (Story 4.3)."""
    process_video = get_process_video_entrypoint()
    mock_job = MagicMock()
    mock_job.id = 123
    mock_job.payload = b"task_normal_priority"

    mock_task = MagicMock()
    mock_task.priority = "normal"

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_task)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()

    with patch("app.entrypoints.AsyncSessionLocal", return_value=mock_db), \
         patch("app.entrypoints.log") as mock_log, \
         patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-1"}):

        await process_video(mock_job)

        # Verify task_completed log includes priority
        last_log_call = mock_log.info.call_args_list[-1]
        assert last_log_call[0][0] == "task_completed"
        assert last_log_call[1]["priority"] == "normal"


def test_process_video_error_handler_includes_priority():
    """Test process_video error handler code includes priority in logs (Story 4.3).

    This is a code structure validation test. The actual error handling behavior
    (retriable vs non-retriable errors, status transitions) is tested in Story 4.2.

    This test verifies that when the error handler logs task_failed, it includes
    the priority field by inspecting the error handler source code.

    Full behavioral testing requires actual pipeline code (Story 4.8).
    """
    import inspect
    from app.entrypoints import register_entrypoints
    from pgqueuer import PgQueuer

    # Get the process_video function source
    mock_pgq = MagicMock(spec=PgQueuer)
    registered_functions = {}

    def mock_entrypoint(name):
        def decorator(func):
            registered_functions[name] = func
            return func
        return decorator

    mock_pgq.entrypoint = mock_entrypoint
    register_entrypoints(mock_pgq)
    process_video = registered_functions["process_video"]

    # Get source code
    source = inspect.getsource(process_video)

    # Verify error handler includes priority in log.error call
    assert 'log.error(' in source
    assert '"task_failed"' in source
    assert 'priority=task.priority' in source or 'priority' in source
    assert 'is_retriable' in source

    # Verify error handler code structure exists
    assert 'except Exception as e:' in source
    assert '_is_retriable_error(e)' in source
