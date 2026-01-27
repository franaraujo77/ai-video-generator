"""Async context variables for correlation ID and channel ID propagation.

This module provides async-safe context variables using Python's contextvars
for automatic propagation of correlation IDs and channel IDs through the
async call stack.

Key Features:
- Async-safe (task-local storage, not thread-local)
- Automatic propagation through async call stack
- No manual parameter passing required
- Isolated per async task (concurrent tasks don't interfere)

Usage:
    # Set correlation ID when task begins
    set_correlation_id(str(task.id))
    set_channel_id(task.channel_id)

    # Retrieve anywhere in async call stack
    correlation_id = get_correlation_id()
    channel_id = get_channel_id()

    # Clear when task completes
    clear_correlation_context()

Story: 8.1 - Structured Logging with Correlation IDs (Task 1)
"""

import os
from contextvars import ContextVar

# Async-safe context variables (task-local, NOT thread-local)
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_channel_id: ContextVar[str | None] = ContextVar("channel_id", default=None)
_step: ContextVar[str | None] = ContextVar("step", default=None)


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID in async context (task-local storage).

    Args:
        correlation_id: UUID string representing task or request correlation ID

    Example:
        >>> set_correlation_id(str(task.id))
    """
    _correlation_id.set(correlation_id)


def get_correlation_id() -> str | None:
    """Get correlation ID from async context.

    Returns:
        Correlation ID string if set, None otherwise

    Example:
        >>> correlation_id = get_correlation_id()
        >>> log.info("processing_task", correlation_id=correlation_id)
    """
    return _correlation_id.get()


def set_channel_id(channel_id: str) -> None:
    """Set channel ID in async context (task-local storage).

    Args:
        channel_id: Channel identifier (e.g., "poke1", "poke2")

    Example:
        >>> set_channel_id(task.channel_id)
    """
    _channel_id.set(channel_id)


def get_channel_id() -> str | None:
    """Get channel ID from async context.

    Returns:
        Channel ID string if set, None otherwise

    Example:
        >>> channel_id = get_channel_id()
        >>> log.info("task_claimed", channel_id=channel_id)
    """
    return _channel_id.get()


def get_worker_id() -> str | None:
    """Get worker ID from RAILWAY_SERVICE_NAME environment variable.

    Returns:
        Worker ID string (e.g., "worker-1", "worker-2", "worker-3") if set,
        None otherwise (e.g., running locally or in FastAPI web service)

    Example:
        >>> worker_id = get_worker_id()
        >>> log.info("worker_startup", worker_id=worker_id)
    """
    return os.getenv("RAILWAY_SERVICE_NAME")


def set_step(step: str) -> None:
    """Set current pipeline step in async context (task-local storage).

    Args:
        step: Pipeline step name (e.g., "asset_generation", "video_generation")

    Example:
        >>> set_step("asset_generation")
    """
    _step.set(step)


def get_step() -> str | None:
    """Get current pipeline step from async context.

    Returns:
        Pipeline step string if set, None otherwise

    Example:
        >>> step = get_step()
        >>> log.info("processing_step", step=step)
    """
    return _step.get()


def clear_correlation_context() -> None:
    """Clear all correlation context variables.

    This should be called after task completion to prevent ID leakage between tasks.
    Good hygiene even though ContextVar is task-local and will reset automatically
    when the async task completes.

    Example:
        >>> try:
        ...     set_correlation_id(str(task.id))
        ...     await process_task(task)
        ... finally:
        ...     clear_correlation_context()
    """
    _correlation_id.set(None)
    _channel_id.set(None)
    _step.set(None)
