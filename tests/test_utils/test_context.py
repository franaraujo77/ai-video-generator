"""Tests for async context variable correlation ID management.

Tests correlation ID and channel ID context variables to ensure:
- ContextVar isolation across concurrent async tasks
- set/get operations work correctly
- Context cleared properly between tasks
- worker_id retrieval from environment variables

Story: 8.1 - Structured Logging with Correlation IDs (Task 1)
"""

import asyncio
import os
from uuid import uuid4

import pytest

from app.utils.context import (
    clear_correlation_context,
    get_channel_id,
    get_correlation_id,
    get_step,
    get_worker_id,
    set_channel_id,
    set_correlation_id,
    set_step,
)


class TestCorrelationIDContext:
    """Test correlation ID context variable isolation and propagation."""

    def test_set_and_get_correlation_id(self):
        """Test basic set and get operations for correlation_id."""
        # GIVEN a correlation ID
        test_id = str(uuid4())

        # WHEN we set it in context
        set_correlation_id(test_id)

        # THEN we can retrieve it
        assert get_correlation_id() == test_id

    def test_get_correlation_id_when_not_set(self):
        """Test get_correlation_id returns None when not set."""
        # GIVEN no correlation_id is set (clear first)
        clear_correlation_context()

        # WHEN we try to get it
        result = get_correlation_id()

        # THEN it returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_correlation_id_isolation_across_async_tasks(self):
        """Test ContextVar isolates correlation IDs across concurrent async tasks."""
        # GIVEN two different correlation IDs for two tasks
        id1 = str(uuid4())
        id2 = str(uuid4())

        # Track which IDs were retrieved
        retrieved_ids = []

        async def task1():
            set_correlation_id(id1)
            await asyncio.sleep(0.01)  # Allow task switch
            retrieved_ids.append(("task1", get_correlation_id()))

        async def task2():
            set_correlation_id(id2)
            await asyncio.sleep(0.01)  # Allow task switch
            retrieved_ids.append(("task2", get_correlation_id()))

        # WHEN we run tasks concurrently
        await asyncio.gather(task1(), task2())

        # THEN each task retrieves its own correlation_id
        task1_result = next(r for r in retrieved_ids if r[0] == "task1")[1]
        task2_result = next(r for r in retrieved_ids if r[0] == "task2")[1]

        assert task1_result == id1
        assert task2_result == id2

    def test_clear_correlation_context(self):
        """Test clearing correlation context sets all values to None."""
        # GIVEN context is set with values
        set_correlation_id(str(uuid4()))
        set_channel_id("poke1")

        # WHEN we clear the context
        clear_correlation_context()

        # THEN all values are None
        assert get_correlation_id() is None
        assert get_channel_id() is None


class TestChannelIDContext:
    """Test channel ID context variable operations."""

    def test_set_and_get_channel_id(self):
        """Test basic set and get operations for channel_id."""
        # GIVEN a channel ID
        test_channel = "poke1"

        # WHEN we set it in context
        set_channel_id(test_channel)

        # THEN we can retrieve it
        assert get_channel_id() == test_channel

    def test_get_channel_id_when_not_set(self):
        """Test get_channel_id returns None when not set."""
        # GIVEN no channel_id is set (clear first)
        clear_correlation_context()

        # WHEN we try to get it
        result = get_channel_id()

        # THEN it returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_channel_id_isolation_across_async_tasks(self):
        """Test ContextVar isolates channel IDs across concurrent async tasks."""
        # GIVEN two different channel IDs for two tasks
        channel1 = "poke1"
        channel2 = "poke2"

        # Track which IDs were retrieved
        retrieved_channels = []

        async def task1():
            set_channel_id(channel1)
            await asyncio.sleep(0.01)  # Allow task switch
            retrieved_channels.append(("task1", get_channel_id()))

        async def task2():
            set_channel_id(channel2)
            await asyncio.sleep(0.01)  # Allow task switch
            retrieved_channels.append(("task2", get_channel_id()))

        # WHEN we run tasks concurrently
        await asyncio.gather(task1(), task2())

        # THEN each task retrieves its own channel_id
        task1_result = next(r for r in retrieved_channels if r[0] == "task1")[1]
        task2_result = next(r for r in retrieved_channels if r[0] == "task2")[1]

        assert task1_result == channel1
        assert task2_result == channel2


class TestWorkerID:
    """Test worker ID retrieval from environment variables."""

    def test_get_worker_id_when_set(self):
        """Test get_worker_id returns RAILWAY_SERVICE_NAME when set."""
        # GIVEN RAILWAY_SERVICE_NAME is set
        os.environ["RAILWAY_SERVICE_NAME"] = "worker-1"

        try:
            # WHEN we get worker_id
            result = get_worker_id()

            # THEN it returns the env var value
            assert result == "worker-1"
        finally:
            # Cleanup
            os.environ.pop("RAILWAY_SERVICE_NAME", None)

    def test_get_worker_id_when_not_set(self):
        """Test get_worker_id returns None when RAILWAY_SERVICE_NAME not set."""
        # GIVEN RAILWAY_SERVICE_NAME is not set
        os.environ.pop("RAILWAY_SERVICE_NAME", None)

        # WHEN we get worker_id
        result = get_worker_id()

        # THEN it returns None
        assert result is None

    def test_get_worker_id_returns_worker_2(self):
        """Test get_worker_id works with different worker instances."""
        # GIVEN RAILWAY_SERVICE_NAME is worker-2
        os.environ["RAILWAY_SERVICE_NAME"] = "worker-2"

        try:
            # WHEN we get worker_id
            result = get_worker_id()

            # THEN it returns worker-2
            assert result == "worker-2"
        finally:
            # Cleanup
            os.environ.pop("RAILWAY_SERVICE_NAME", None)


class TestContextPropagationAcrossCallStack:
    """Test ContextVar propagates through async call stack automatically."""

    @pytest.mark.asyncio
    async def test_correlation_id_propagates_through_nested_calls(self):
        """Test correlation_id automatically propagates to nested async calls."""
        # GIVEN a correlation_id set at top level
        test_id = str(uuid4())
        set_correlation_id(test_id)

        async def level_3():
            """Deepest level - no parameter passing needed."""
            return get_correlation_id()

        async def level_2():
            """Middle level - correlation_id propagates automatically."""
            await asyncio.sleep(0.001)
            return await level_3()

        async def level_1():
            """Top level - correlation_id already in context."""
            return await level_2()

        # WHEN we call through nested async functions
        result = await level_1()

        # THEN correlation_id is available at all levels without parameter passing
        assert result == test_id

    @pytest.mark.asyncio
    async def test_context_cleared_after_task_completion(self):
        """Test context clearing between tasks prevents ID leakage."""
        # GIVEN a task that sets and clears context
        task1_id = str(uuid4())

        async def task1():
            set_correlation_id(task1_id)
            assert get_correlation_id() == task1_id
            clear_correlation_context()

        # WHEN task1 completes and clears context
        await task1()

        # THEN the correlation_id is None for subsequent operations
        assert get_correlation_id() is None


class TestStepContext:
    """Test step (pipeline step name) context variable operations."""

    def test_set_and_get_step(self):
        """Test basic set and get operations for step."""
        # GIVEN a pipeline step name
        test_step = "asset_generation"

        # WHEN we set it in context
        set_step(test_step)

        # THEN we can retrieve it
        assert get_step() == test_step

    def test_get_step_when_not_set(self):
        """Test get_step returns None when not set."""
        # GIVEN no step is set (clear first)
        clear_correlation_context()

        # WHEN we try to get it
        result = get_step()

        # THEN it returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_step_isolation_across_async_tasks(self):
        """Test ContextVar isolates step across concurrent async tasks."""
        # GIVEN two different steps for two tasks
        step1 = "asset_generation"
        step2 = "video_generation"

        # Track which steps were retrieved
        retrieved_steps = []

        async def task1():
            set_step(step1)
            await asyncio.sleep(0.01)  # Allow task switch
            retrieved_steps.append(("task1", get_step()))

        async def task2():
            set_step(step2)
            await asyncio.sleep(0.01)  # Allow task switch
            retrieved_steps.append(("task2", get_step()))

        # WHEN we run tasks concurrently
        await asyncio.gather(task1(), task2())

        # THEN each task retrieves its own step
        task1_result = next(r for r in retrieved_steps if r[0] == "task1")[1]
        task2_result = next(r for r in retrieved_steps if r[0] == "task2")[1]

        assert task1_result == step1
        assert task2_result == step2

    def test_clear_correlation_context_clears_step(self):
        """Test clearing correlation context also clears step."""
        # GIVEN step is set
        set_step("asset_generation")

        # WHEN we clear the context
        clear_correlation_context()

        # THEN step is None
        assert get_step() is None

    @pytest.mark.asyncio
    async def test_step_propagates_through_nested_calls(self):
        """Test step automatically propagates to nested async calls."""
        # GIVEN a step set at top level
        test_step = "video_generation"
        set_step(test_step)

        async def level_3():
            """Deepest level - no parameter passing needed."""
            return get_step()

        async def level_2():
            """Middle level - step propagates automatically."""
            await asyncio.sleep(0.001)
            return await level_3()

        async def level_1():
            """Top level - step already in context."""
            return await level_2()

        # WHEN we call through nested async functions
        result = await level_1()

        # THEN step is available at all levels without parameter passing
        assert result == test_step

        # Cleanup
        clear_correlation_context()
