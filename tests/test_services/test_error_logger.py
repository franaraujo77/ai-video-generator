"""Tests for structured error logging service (Story 6.5).

Tests verify comprehensive error logging with Railway-compatible JSON output,
correlation IDs, and integration with Stories 6.1-6.4.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
import structlog

from app.services.error_logger import (
    log_structured_error,
    log_retry_scheduled,
    log_retry_claimed,
    log_terminal_failure,
    log_pipeline_step_started,
    log_pipeline_step_completed,
)
from app.services.error_classifier import ErrorContext, ErrorCategory
from tests.support.factories import create_task


@pytest.mark.asyncio
async def test_structured_error_includes_all_required_fields(async_session, caplog):
    """Verify log_structured_error() outputs all required fields (AC1)."""
    task_id = uuid4()
    task = create_task(channel_id="poke1", correlation_id=task_id)
    async_session.add(task)
    await async_session.commit()

    # Simulate error with context
    exception = TimeoutError("KIE.ai API timeout after 600s")
    context = ErrorContext(
        step_name="video_generation",
        task_id=str(task.id),
        channel_id="poke1",
        clip_index=11,
        total_clips=18,
    )

    # Call structured logger (use task.id as correlation_id)
    with caplog.at_level("ERROR"):
        await log_structured_error(
            exception=exception,
            task_id=task.id,
            channel_id=str(task.channel_id),  # Convert UUID to str
            correlation_id=task.id,  # Use task.id as correlation_id
            step_name="video_generation",
            retry_attempt=1,
            db=async_session,
            context=context,
        )

    # Verify JSON log output includes required fields
    assert len(caplog.records) > 0
    log_record = caplog.records[0]

    # Check log level
    assert log_record.levelname == "ERROR"

    # Parse JSON log message
    import json

    log_data = json.loads(log_record.getMessage())

    # Verify required fields (FR31)
    assert log_data["event"] == "pipeline_step_failed"
    assert log_data["task_id"] == str(task.id)
    assert log_data["channel_id"] == str(task.channel_id)
    assert log_data["correlation_id"] == str(task.id)  # correlation_id = task.id
    assert log_data["step_name"] == "video_generation"
    assert log_data["error_type"] == "TimeoutError"
    assert "KIE.ai API timeout" in log_data["error_message"]
    assert log_data["retry_attempt"] == 1
    assert "is_transient" in log_data
    assert isinstance(log_data["is_transient"], bool)


@pytest.mark.asyncio
async def test_structured_error_includes_error_category_from_story_61(async_session, caplog):
    """Verify log includes error_category from Story 6.1 classifier (Integration)."""
    task_id = uuid4()
    task = create_task(channel_id="poke1", correlation_id=task_id)
    async_session.add(task)
    await async_session.commit()

    # Simulate transient error
    exception = TimeoutError("Connection timeout")
    context = ErrorContext(step_name="asset_generation", task_id=str(task.id), channel_id="poke1")

    with caplog.at_level("ERROR"):
        await log_structured_error(
            exception=exception,
            task_id=task.id,
            channel_id=str(task.channel_id),
            correlation_id=task.id,
            step_name="asset_generation",
            retry_attempt=1,
            db=async_session,
            context=context,
        )

    # Parse log
    import json

    log_data = json.loads(caplog.records[0].getMessage())

    # Verify Story 6.1 integration
    assert "error_category" in log_data
    # Error categories are lowercase (from ErrorCategory enum)
    assert log_data["error_category"] in [
        "transient",
        "permanent",
        "configuration",
        "quota_exceeded",
        "unknown",
    ]
    assert log_data["is_transient"] == (log_data["error_category"] == "transient")


@pytest.mark.asyncio
async def test_correlation_id_propagates_through_error_logs(async_session, caplog):
    """Verify correlation_id is included in all error logs for distributed tracing (AC3)."""
    task_id = uuid4()
    task = create_task(channel_id="poke1", correlation_id=task_id)
    async_session.add(task)
    await async_session.commit()

    exception = ValueError("Invalid input")

    with caplog.at_level("ERROR"):
        await log_structured_error(
            exception=exception,
            task_id=task.id,
            channel_id=str(task.channel_id),
            correlation_id=task.id,
            step_name="sfx_generation",
            retry_attempt=2,
            db=async_session,
        )

    # Parse log
    import json

    log_data = json.loads(caplog.records[0].getMessage())

    # Verify correlation_id propagation
    assert log_data["correlation_id"] == str(task.id)


@pytest.mark.asyncio
async def test_retry_scheduled_log_includes_next_retry_at(caplog):
    """Verify log_retry_scheduled() includes retry delay and next attempt time (Task 3)."""
    task_id = uuid4()
    correlation_id = uuid4()
    next_retry_at = datetime.now(timezone.utc)

    with caplog.at_level("WARNING"):
        await log_retry_scheduled(
            task_id=task_id,
            correlation_id=correlation_id,
            retry_attempt=1,
            next_retry_at=next_retry_at,
            retry_delay_seconds=30,
        )

    # Parse log
    import json

    log_data = json.loads(caplog.records[0].getMessage())

    # Verify retry scheduling details
    assert log_data["event"] == "task_retry_scheduled"
    assert log_data["task_id"] == str(task_id)
    assert log_data["correlation_id"] == str(correlation_id)
    assert log_data["retry_attempt"] == 1
    assert log_data["retry_delay_seconds"] == 30
    assert "next_retry_at" in log_data


@pytest.mark.asyncio
async def test_retry_claimed_log_includes_worker_id(caplog):
    """Verify log_retry_claimed() includes worker identifier (Task 3)."""
    task_id = uuid4()
    correlation_id = uuid4()

    with caplog.at_level("INFO"):
        await log_retry_claimed(
            task_id=task_id,
            correlation_id=correlation_id,
            retry_attempt=2,
            worker_id="worker-1",
        )

    # Parse log
    import json

    log_data = json.loads(caplog.records[0].getMessage())

    # Verify retry claim details
    assert log_data["event"] == "task_retry_claimed"
    assert log_data["task_id"] == str(task_id)
    assert log_data["worker_id"] == "worker-1"
    assert log_data["retry_attempt"] == 2


@pytest.mark.asyncio
async def test_terminal_failure_log_includes_exhausted_retry_count(caplog):
    """Verify log_terminal_failure() logs after max retries exhausted (Task 3)."""
    task_id = uuid4()
    correlation_id = uuid4()

    with caplog.at_level("CRITICAL"):
        await log_terminal_failure(
            task_id=task_id,
            correlation_id=correlation_id,
            channel_id="poke1",
            retry_attempts=3,
            final_error_type="KlingAPITimeout",
            final_error_message="Video generation timeout after 10 minutes",
        )

    # Parse log
    import json

    log_data = json.loads(caplog.records[0].getMessage())

    # Verify terminal failure details
    assert log_data["event"] == "task_terminal_failure"
    assert log_data["task_id"] == str(task_id)
    assert log_data["retry_attempts"] == 3
    assert log_data["final_error_type"] == "KlingAPITimeout"
    assert "Video generation timeout" in log_data["final_error_message"]


@pytest.mark.asyncio
async def test_pipeline_step_started_includes_timestamp_and_step_name(caplog):
    """Verify log_pipeline_step_started() logs step initiation (Task 4)."""
    task_id = uuid4()
    correlation_id = uuid4()

    with caplog.at_level("INFO"):
        await log_pipeline_step_started(
            task_id=task_id,
            correlation_id=correlation_id,
            channel_id="poke1",
            step_name="narration_generation",
        )

    # Parse log
    import json

    log_data = json.loads(caplog.records[0].getMessage())

    # Verify step start details
    assert log_data["event"] == "pipeline_step_started"
    assert log_data["step_name"] == "narration_generation"
    assert "timestamp" in log_data


@pytest.mark.asyncio
async def test_pipeline_step_completed_includes_duration(caplog):
    """Verify log_pipeline_step_completed() logs execution time (Task 4)."""
    task_id = uuid4()
    correlation_id = uuid4()

    with caplog.at_level("INFO"):
        await log_pipeline_step_completed(
            task_id=task_id,
            correlation_id=correlation_id,
            channel_id="poke1",
            step_name="asset_generation",
            duration_seconds=45.3,
        )

    # Parse log
    import json

    log_data = json.loads(caplog.records[0].getMessage())

    # Verify step completion details
    assert log_data["event"] == "pipeline_step_completed"
    assert log_data["step_name"] == "asset_generation"
    assert log_data["duration_seconds"] == 45.3


@pytest.mark.asyncio
async def test_json_output_format_for_railway(async_session, caplog):
    """Verify all logs use JSON format for Railway aggregation (AC3)."""
    task_id = uuid4()
    task = create_task(channel_id="poke1", correlation_id=task_id)
    async_session.add(task)
    await async_session.commit()

    exception = RuntimeError("Test error")

    with caplog.at_level("ERROR"):
        await log_structured_error(
            exception=exception,
            task_id=task.id,
            channel_id=str(task.channel_id),
            correlation_id=task.id,
            step_name="video_generation",
            retry_attempt=1,
            db=async_session,
        )

    # Verify JSON parseable
    import json

    log_message = caplog.records[0].getMessage()
    log_data = json.loads(log_message)

    # Verify Railway-queryable structure
    assert isinstance(log_data, dict)
    assert "event" in log_data
    assert "task_id" in log_data
    assert "channel_id" in log_data
    assert "correlation_id" in log_data


@pytest.mark.asyncio
async def test_partial_progress_included_from_story_63(async_session, caplog):
    """Verify checkpoint progress from Story 6.3 is included in error logs (Integration)."""
    task_id = uuid4()
    task = create_task(channel_id="poke1", correlation_id=task_id)
    async_session.add(task)
    await async_session.commit()

    # Save checkpoint data (from Story 6.3)
    from app.services.checkpoint_service import save_step_checkpoint

    checkpoint_data = {"completed_video_clips": [1, 2, 3, 4, 5]}
    await save_step_checkpoint(str(task.id), "video_generation", checkpoint_data, async_session)

    exception = TimeoutError("Clip 6 timeout")

    with caplog.at_level("ERROR"):
        await log_structured_error(
            exception=exception,
            task_id=task.id,
            channel_id=str(task.channel_id),
            correlation_id=task.id,
            step_name="video_generation",
            retry_attempt=1,
            db=async_session,
        )

    # Parse log (get the ERROR log, not the INFO checkpoint log)
    import json

    # Filter to ERROR logs only
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) > 0, "Expected at least one ERROR log"
    log_data = json.loads(error_records[0].getMessage())

    # Verify checkpoint progress included
    assert "partial_progress" in log_data
    assert "completed_video_clips" in log_data["partial_progress"]
    assert log_data["partial_progress"]["completed_video_clips"] == [1, 2, 3, 4, 5]
