"""Tests for worker correlation ID binding during task processing.

Tests worker integration to ensure:
- Correlation ID set when task is claimed
- Correlation ID matches task.id
- Channel ID set from task.channel_id
- Context cleared after task completion
- Worker ID logged from RAILWAY_SERVICE_NAME

Story: 8.1 - Structured Logging with Correlation IDs (Task 4)
"""

import os
from uuid import uuid4

import pytest

from app.models import Task, TaskStatus
from app.utils.context import get_channel_id, get_correlation_id, set_correlation_id


class TestWorkerCorrelationBinding:
    """Test worker correlation ID binding during task processing."""

    def test_set_correlation_id_from_task(self):
        """Test setting correlation_id to task.id when claiming task."""
        # GIVEN a task with UUID
        task_id = uuid4()

        # WHEN we set correlation_id from task
        set_correlation_id(str(task_id))

        # THEN correlation_id matches task.id
        assert get_correlation_id() == str(task_id)

    def test_worker_binds_correlation_id_on_claim(self):
        """Test worker binds correlation_id when claiming task from queue."""
        # GIVEN a task UUID
        task_id = uuid4()

        # WHEN worker claims the task and sets correlation_id
        # (simulating what happens in entrypoints.py)
        set_correlation_id(str(task_id))

        # THEN correlation_id is available from context
        correlation_id = get_correlation_id()
        assert correlation_id == str(task_id)

    def test_worker_binds_channel_id_on_claim(self):
        """Test worker binds channel_id when claiming task from queue."""
        # GIVEN a task with channel_id
        channel_id = "poke1"

        # WHEN worker claims the task and sets channel_id
        # (simulating what happens in entrypoints.py)
        from app.utils.context import set_channel_id

        set_channel_id(channel_id)

        # THEN channel_id is available from context
        retrieved_channel_id = get_channel_id()
        assert retrieved_channel_id == "poke1"

    def test_get_worker_id_from_env(self):
        """Test worker_id retrieval from RAILWAY_SERVICE_NAME."""
        # GIVEN RAILWAY_SERVICE_NAME is set
        os.environ["RAILWAY_SERVICE_NAME"] = "worker-1"

        try:
            # WHEN we get worker_id
            from app.utils.context import get_worker_id

            worker_id = get_worker_id()

            # THEN it returns the service name
            assert worker_id == "worker-1"
        finally:
            # Cleanup
            os.environ.pop("RAILWAY_SERVICE_NAME", None)

    def test_correlation_context_cleared_after_task(self):
        """Test correlation context is cleared after task completion."""
        # GIVEN correlation_id and channel_id are set
        test_id = str(uuid4())
        set_correlation_id(test_id)
        from app.utils.context import clear_correlation_context, set_channel_id

        set_channel_id("poke1")

        # WHEN worker clears context after task
        clear_correlation_context()

        # THEN context is empty
        assert get_correlation_id() is None
        assert get_channel_id() is None
