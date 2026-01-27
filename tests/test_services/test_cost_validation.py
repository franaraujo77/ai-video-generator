"""Tests for cost validation and consistency checks (Story 8.2, Task 6).

Tests cover:
- Cost consistency validation (video_costs sum == task.total_cost_usd)
- Missing component detection
- Duplicate cost record detection
- Anomaly detection (costs outside expected ranges)
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskStatus, VideoCost
from app.services.cost_validation import (
    validate_task_cost_consistency,
    detect_missing_cost_components,
    detect_duplicate_cost_records,
    detect_cost_anomalies,
)
from tests.support.factories import create_channel, create_task


@pytest.mark.asyncio
async def test_validate_cost_consistency_pass(async_session: AsyncSession):
    """Test cost consistency validation when costs match."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    task.total_cost_usd = 10.50  # Set expected total
    async_session.add(task)
    await async_session.flush()

    # Add cost records that sum to 10.50
    costs = [
        VideoCost(task_id=task.id, component="gemini_assets", cost_usd=Decimal("1.50"), units_used=22),
        VideoCost(task_id=task.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18),
        VideoCost(task_id=task.id, component="elevenlabs_narration", cost_usd=Decimal("0.72"), units_used=18),
        VideoCost(task_id=task.id, component="elevenlabs_sfx", cost_usd=Decimal("0.72"), units_used=18),
    ]
    for cost in costs:
        async_session.add(cost)
    await async_session.commit()

    # Act: Validate consistency
    is_consistent, discrepancy = await validate_task_cost_consistency(async_session, task.id)

    # Assert: Costs are consistent
    assert is_consistent is True
    assert discrepancy == Decimal("0.00")


@pytest.mark.asyncio
async def test_validate_cost_consistency_fail(async_session: AsyncSession):
    """Test cost consistency validation when costs don't match."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    task.total_cost_usd = 15.00  # Incorrect total (should be 10.50)
    async_session.add(task)
    await async_session.flush()

    # Add cost records that sum to 10.50
    costs = [
        VideoCost(task_id=task.id, component="gemini_assets", cost_usd=Decimal("1.50"), units_used=22),
        VideoCost(task_id=task.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18),
        VideoCost(task_id=task.id, component="elevenlabs_narration", cost_usd=Decimal("0.72"), units_used=18),
        VideoCost(task_id=task.id, component="elevenlabs_sfx", cost_usd=Decimal("0.72"), units_used=18),
    ]
    for cost in costs:
        async_session.add(cost)
    await async_session.commit()

    # Act: Validate consistency
    is_consistent, discrepancy = await validate_task_cost_consistency(async_session, task.id)

    # Assert: Costs are inconsistent
    assert is_consistent is False
    assert discrepancy == Decimal("4.50")  # 15.00 - 10.50


@pytest.mark.asyncio
async def test_detect_missing_cost_components(async_session: AsyncSession):
    """Test detection of missing cost components for completed video."""
    # Arrange: Create channel and task with published status
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    async_session.add(task)
    await async_session.flush()

    # Add only 2 of 4 expected components
    costs = [
        VideoCost(task_id=task.id, component="gemini_assets", cost_usd=Decimal("1.50"), units_used=22),
        VideoCost(task_id=task.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18),
    ]
    for cost in costs:
        async_session.add(cost)
    await async_session.commit()

    # Act: Detect missing components
    missing = await detect_missing_cost_components(async_session, task.id)

    # Assert: Missing narration and sfx
    assert "elevenlabs_narration" in missing
    assert "elevenlabs_sfx" in missing
    assert len(missing) == 2


@pytest.mark.asyncio
async def test_detect_duplicate_cost_records(async_session: AsyncSession):
    """Test detection of duplicate cost records for same component."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    async_session.add(task)
    await async_session.flush()

    # Add duplicate kling_video records
    costs = [
        VideoCost(task_id=task.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18),
        VideoCost(task_id=task.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18),
        VideoCost(task_id=task.id, component="gemini_assets", cost_usd=Decimal("1.50"), units_used=22),
    ]
    for cost in costs:
        async_session.add(cost)
    await async_session.commit()

    # Act: Detect duplicates
    duplicates = await detect_duplicate_cost_records(async_session, task.id)

    # Assert: Found kling_video duplicates
    assert "kling_video" in duplicates
    assert duplicates["kling_video"] == 2


@pytest.mark.asyncio
async def test_detect_cost_anomalies(async_session: AsyncSession):
    """Test detection of cost anomalies (values outside expected ranges)."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    async_session.add(task)
    await async_session.flush()

    # Add cost with anomalous value (kling_video way too high)
    costs = [
        VideoCost(task_id=task.id, component="gemini_assets", cost_usd=Decimal("1.50"), units_used=22),
        VideoCost(task_id=task.id, component="kling_video", cost_usd=Decimal("100.00"), units_used=18),  # Anomaly!
        VideoCost(task_id=task.id, component="elevenlabs_narration", cost_usd=Decimal("0.72"), units_used=18),
    ]
    for cost in costs:
        async_session.add(cost)
    await async_session.commit()

    # Act: Detect anomalies
    anomalies = await detect_cost_anomalies(async_session, task.id)

    # Assert: Found kling_video anomaly
    assert len(anomalies) > 0
    assert any(a["component"] == "kling_video" for a in anomalies)


@pytest.mark.asyncio
async def test_no_anomalies_for_normal_costs(async_session: AsyncSession):
    """Test that normal cost values don't trigger anomaly detection."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    async_session.add(task)
    await async_session.flush()

    # Add all costs within normal ranges
    costs = [
        VideoCost(task_id=task.id, component="gemini_assets", cost_usd=Decimal("1.50"), units_used=22),
        VideoCost(task_id=task.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18),
        VideoCost(task_id=task.id, component="elevenlabs_narration", cost_usd=Decimal("0.72"), units_used=18),
        VideoCost(task_id=task.id, component="elevenlabs_sfx", cost_usd=Decimal("0.72"), units_used=18),
    ]
    for cost in costs:
        async_session.add(cost)
    await async_session.commit()

    # Act: Detect anomalies
    anomalies = await detect_cost_anomalies(async_session, task.id)

    # Assert: No anomalies found
    assert len(anomalies) == 0
