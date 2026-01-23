"""
Tests for quota_service.py - YouTube and Gemini API quota tracking.

Story 6.8: API Quota Monitoring
Tests cover:
- Quota recording (YouTube/Gemini)
- Quota checking (availability)
- Threshold alerting (80%/100%)
- Edge cases (concurrent updates, timezone boundaries)
"""

import asyncio
import pytest
from datetime import datetime, date, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from app.services.quota_service import (
    record_youtube_operation,
    check_youtube_quota,
    get_youtube_quota_usage,
    record_gemini_operation,
    check_gemini_quota,
    get_gemini_quota_usage,
    YOUTUBE_OPERATION_COSTS,
)
from app.models import YouTubeQuotaUsage, GeminiQuotaUsage
from tests.support.factories import create_channel


# ============================================================================
# YOUTUBE QUOTA TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_record_youtube_operation_creates_new_record(async_session):
    """Verify quota recording creates new record for channel (Task 2, Subtask 2.3)."""
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    task_id = uuid4()

    # Mock alert service to avoid Discord webhook calls
    with patch("app.services.quota_service.check_youtube_quota_thresholds", new_callable=AsyncMock):
        # Record upload operation
        await record_youtube_operation(
            channel_id=channel.id,
            operation="upload",
            task_id=task_id,
            video_id="vid_abc",
            db=async_session
        )

    # Verify quota record created
    quota = await get_youtube_quota_usage(channel.id, date.today(), async_session)

    assert quota is not None
    assert quota.units_used == YOUTUBE_OPERATION_COSTS["upload"]  # 1600
    assert quota.daily_limit == 10000
    assert quota.channel_id == channel.id
    assert quota.date == date.today()


@pytest.mark.asyncio
async def test_record_youtube_operation_updates_existing_record(async_session):
    """Verify quota recording updates existing record atomically (Task 2, Subtask 2.3)."""
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Create initial quota record
    initial_quota = YouTubeQuotaUsage(
        channel_id=channel.id,
        date=date.today(),
        units_used=1000,
        daily_limit=10000
    )
    async_session.add(initial_quota)
    await async_session.commit()

    # Mock alert service
    with patch("app.services.quota_service.check_youtube_quota_thresholds", new_callable=AsyncMock):
        # Record another upload (adds 1600)
        await record_youtube_operation(
            channel_id=channel.id,
            operation="upload",
            db=async_session
        )

    # Verify quota was updated (not duplicated)
    quota = await get_youtube_quota_usage(channel.id, date.today(), async_session)

    assert quota.units_used == 2600  # 1000 + 1600
    assert quota.daily_limit == 10000


@pytest.mark.asyncio
async def test_record_youtube_operation_invalid_operation_raises_error(async_session):
    """Verify invalid operation type raises ValueError (Task 2, Subtask 2.2)."""
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    with pytest.raises(ValueError, match="Unknown YouTube operation"):
        await record_youtube_operation(
            channel_id=channel.id,
            operation="invalid_operation",
            db=async_session
        )


@pytest.mark.asyncio
async def test_check_youtube_quota_returns_true_when_available(async_session):
    """Verify quota check allows operation when quota available (Task 4, Subtask 4.4)."""
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Create quota with plenty of space (5000 / 10000 = 50%)
    quota = YouTubeQuotaUsage(
        channel_id=channel.id,
        date=date.today(),
        units_used=5000,
        daily_limit=10000
    )
    async_session.add(quota)
    await async_session.commit()

    # Check if upload allowed (costs 1600)
    can_upload = await check_youtube_quota(
        channel_id=channel.id,
        operation="upload",
        db=async_session
    )

    assert can_upload is True


@pytest.mark.asyncio
async def test_check_youtube_quota_returns_false_when_exhausted(async_session):
    """Verify quota check prevents operation when quota exhausted (Task 4, Subtask 4.4)."""
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Create quota at 100%
    quota = YouTubeQuotaUsage(
        channel_id=channel.id,
        date=date.today(),
        units_used=10000,
        daily_limit=10000
    )
    async_session.add(quota)
    await async_session.commit()

    # Check if upload allowed
    can_upload = await check_youtube_quota(
        channel_id=channel.id,
        operation="upload",
        db=async_session
    )

    assert can_upload is False


@pytest.mark.asyncio
async def test_check_youtube_quota_returns_true_no_prior_usage(async_session):
    """Verify quota check allows first operation of day (Task 4, Subtask 4.2)."""
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # No quota record exists yet
    can_upload = await check_youtube_quota(
        channel_id=channel.id,
        operation="upload",
        db=async_session
    )

    assert can_upload is True


@pytest.mark.asyncio
async def test_youtube_quota_threshold_80_triggers_warning_alert(async_session, mocker):
    """Verify 80% threshold triggers WARNING alert (Task 5, Subtask 5.3)."""
    # Mock Discord alert
    mock_alert = mocker.patch("app.services.quota_service.send_discord_alert", new_callable=AsyncMock)
    mocker.patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"})

    from app.services.quota_service import check_youtube_quota_thresholds

    # Create quota at 85%
    quota = YouTubeQuotaUsage(
        channel_id=uuid4(),
        date=date.today(),
        units_used=8500,
        daily_limit=10000
    )

    await check_youtube_quota_thresholds(quota)

    # Verify WARNING alert sent
    mock_alert.assert_called_once()
    call_kwargs = mock_alert.call_args[1]
    assert call_kwargs["alert_type"] == "quota_warning"
    assert call_kwargs["severity"] == "WARNING"
    assert "80" in call_kwargs["description"] or "85" in call_kwargs["description"]


@pytest.mark.asyncio
async def test_youtube_quota_threshold_100_triggers_critical_alert(async_session, mocker):
    """Verify 100% threshold triggers CRITICAL alert (Task 6, Subtask 6.1)."""
    # Mock Discord alert
    mock_alert = mocker.patch("app.services.quota_service.send_discord_alert", new_callable=AsyncMock)
    mocker.patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"})

    from app.services.quota_service import check_youtube_quota_thresholds

    # Create quota at 100%
    quota = YouTubeQuotaUsage(
        channel_id=uuid4(),
        date=date.today(),
        units_used=10000,
        daily_limit=10000
    )

    await check_youtube_quota_thresholds(quota)

    # Verify CRITICAL alert sent
    mock_alert.assert_called_once()
    call_kwargs = mock_alert.call_args[1]
    assert call_kwargs["alert_type"] == "quota_exhausted"
    assert call_kwargs["severity"] == "CRITICAL"
    assert "100" in call_kwargs["description"]
    assert "exhausted" in call_kwargs["description"].lower()


@pytest.mark.asyncio
async def test_youtube_quota_no_alert_below_80(async_session, mocker):
    """Verify no alert sent below 80% threshold (Task 5, Subtask 5.1)."""
    # Mock Discord alert
    mock_alert = mocker.patch("app.services.quota_service.send_discord_alert", new_callable=AsyncMock)
    mocker.patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"})

    from app.services.quota_service import check_youtube_quota_thresholds

    # Create quota at 75% (below WARNING threshold)
    quota = YouTubeQuotaUsage(
        channel_id=uuid4(),
        date=date.today(),
        units_used=7500,
        daily_limit=10000
    )

    await check_youtube_quota_thresholds(quota)

    # Verify NO alert sent
    mock_alert.assert_not_called()


# ============================================================================
# GEMINI QUOTA TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_record_gemini_operation_creates_new_record(async_session):
    """Verify Gemini quota recording creates new record (Task 7, Subtask 7.2)."""
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    task_id = uuid4()

    # Mock alert service
    with patch("app.services.quota_service.check_gemini_quota_thresholds", new_callable=AsyncMock):
        # Record image generation request
        await record_gemini_operation(
            channel_id=channel.id,
            task_id=task_id,
            asset_name="bulbasaur.png",
            db=async_session
        )

    # Verify quota record created
    quota = await get_gemini_quota_usage(channel.id, date.today(), async_session)

    assert quota is not None
    assert quota.requests_used == 1
    assert quota.daily_limit == 1500
    assert quota.channel_id == channel.id
    assert quota.date == date.today()


@pytest.mark.asyncio
async def test_record_gemini_operation_updates_existing_record(async_session):
    """Verify Gemini quota updates existing record atomically (Task 7, Subtask 7.2)."""
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Create initial quota record
    initial_quota = GeminiQuotaUsage(
        channel_id=channel.id,
        date=date.today(),
        requests_used=100,
        daily_limit=1500
    )
    async_session.add(initial_quota)
    await async_session.commit()

    # Mock alert service
    with patch("app.services.quota_service.check_gemini_quota_thresholds", new_callable=AsyncMock):
        # Record another request
        await record_gemini_operation(
            channel_id=channel.id,
            db=async_session
        )

    # Verify quota was updated
    quota = await get_gemini_quota_usage(channel.id, date.today(), async_session)

    assert quota.requests_used == 101  # 100 + 1


@pytest.mark.asyncio
async def test_check_gemini_quota_returns_true_when_available(async_session):
    """Verify Gemini quota check allows operation when available (Task 7, Subtask 7.4)."""
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Create quota with plenty of space
    quota = GeminiQuotaUsage(
        channel_id=channel.id,
        date=date.today(),
        requests_used=500,
        daily_limit=1500
    )
    async_session.add(quota)
    await async_session.commit()

    # Check if request allowed
    can_proceed = await check_gemini_quota(
        channel_id=channel.id,
        db=async_session
    )

    assert can_proceed is True


@pytest.mark.asyncio
async def test_check_gemini_quota_returns_false_when_exhausted(async_session):
    """Verify Gemini quota check prevents operation when exhausted (Task 7, Subtask 7.5)."""
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Create quota at 100%
    quota = GeminiQuotaUsage(
        channel_id=channel.id,
        date=date.today(),
        requests_used=1500,
        daily_limit=1500
    )
    async_session.add(quota)
    await async_session.commit()

    # Check if request allowed
    can_proceed = await check_gemini_quota(
        channel_id=channel.id,
        db=async_session
    )

    assert can_proceed is False


@pytest.mark.asyncio
async def test_gemini_quota_threshold_80_triggers_warning_alert(async_session, mocker):
    """Verify Gemini 80% threshold triggers WARNING alert (Task 7, Subtask 7.5)."""
    # Mock Discord alert
    mock_alert = mocker.patch("app.services.quota_service.send_discord_alert", new_callable=AsyncMock)
    mocker.patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"})

    from app.services.quota_service import check_gemini_quota_thresholds

    # Create quota at 85%
    quota = GeminiQuotaUsage(
        channel_id=uuid4(),
        date=date.today(),
        requests_used=1275,  # 85% of 1500
        daily_limit=1500
    )

    await check_gemini_quota_thresholds(quota)

    # Verify WARNING alert sent
    mock_alert.assert_called_once()
    call_kwargs = mock_alert.call_args[1]
    assert call_kwargs["alert_type"] == "quota_warning"
    assert call_kwargs["severity"] == "WARNING"


@pytest.mark.asyncio
async def test_gemini_quota_threshold_100_triggers_critical_alert(async_session, mocker):
    """Verify Gemini 100% threshold triggers CRITICAL alert (Task 7, Subtask 7.5)."""
    # Mock Discord alert
    mock_alert = mocker.patch("app.services.quota_service.send_discord_alert", new_callable=AsyncMock)
    mocker.patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"})

    from app.services.quota_service import check_gemini_quota_thresholds

    # Create quota at 100%
    quota = GeminiQuotaUsage(
        channel_id=uuid4(),
        date=date.today(),
        requests_used=1500,
        daily_limit=1500
    )

    await check_gemini_quota_thresholds(quota)

    # Verify CRITICAL alert sent
    mock_alert.assert_called_once()
    call_kwargs = mock_alert.call_args[1]
    assert call_kwargs["alert_type"] == "quota_exhausted"
    assert call_kwargs["severity"] == "CRITICAL"
    assert "exhausted" in call_kwargs["description"].lower()


# ============================================================================
# INTEGRATION TESTS (Story 6.8 Task 10 Subtask 10.2)
# ============================================================================


@pytest.mark.asyncio
async def test_upload_integration_records_quota_and_triggers_alert(async_session, mocker):
    """Integration test: Upload → record quota → check threshold → send alert (Task 10 Subtask 10.2)."""
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Mock Discord alert
    mock_alert = mocker.patch("app.services.quota_service.send_discord_alert", new_callable=AsyncMock)
    mocker.patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"})

    # Simulate 5 uploads (each costs 1600 units = 8000 total = 80%)
    for i in range(5):
        await record_youtube_operation(
            channel_id=channel.id,
            operation="upload",
            task_id=uuid4(),
            video_id=f"vid_{i}",
            db=async_session
        )

    # Verify quota recorded correctly (5 * 1600 = 8000)
    quota = await get_youtube_quota_usage(channel.id, date.today(), async_session)
    assert quota.units_used == 8000
    assert quota.daily_limit == 10000

    # Verify WARNING alert sent (80% threshold)
    assert mock_alert.call_count >= 1
    last_call_kwargs = mock_alert.call_args[1]
    assert last_call_kwargs["alert_type"] == "quota_warning"
    assert last_call_kwargs["severity"] == "WARNING"


@pytest.mark.asyncio
async def test_quota_exhaustion_sets_channel_flag(async_session, mocker):
    """Integration test: 100% quota sets channel.quota_exhausted flag (Task 6 Subtasks 6.3-6.4)."""
    from app.models import Channel

    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Mock Discord alert
    mock_alert = mocker.patch("app.services.quota_service.send_discord_alert", new_callable=AsyncMock)
    mocker.patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"})

    # Create quota at 100%
    quota = YouTubeQuotaUsage(
        channel_id=channel.id,
        date=date.today(),
        units_used=10000,
        daily_limit=10000
    )
    async_session.add(quota)
    await async_session.commit()

    # Trigger threshold check
    from app.services.quota_service import check_youtube_quota_thresholds
    await check_youtube_quota_thresholds(quota, async_session)

    # Verify channel flag set
    await async_session.refresh(channel)
    assert channel.youtube_quota_exhausted is True

    # Verify CRITICAL alert sent
    mock_alert.assert_called_once()
    call_kwargs = mock_alert.call_args[1]
    assert call_kwargs["severity"] == "CRITICAL"


@pytest.mark.asyncio
async def test_gemini_integration_records_quota_on_generation(async_session, mocker):
    """Integration test: Asset generation → Gemini quota recorded (Task 7 Subtask 7.3)."""
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Mock Discord alert
    mocker.patch("app.services.quota_service.send_discord_alert", new_callable=AsyncMock)
    mocker.patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/webhook/test"})

    # Record 5 Gemini operations
    for i in range(5):
        await record_gemini_operation(
            channel_id=channel.id,
            task_id=uuid4(),
            asset_name=f"bulbasaur_{i}.png",
            db=async_session
        )

    # Verify quota recorded
    quota = await get_gemini_quota_usage(channel.id, date.today(), async_session)
    assert quota.requests_used == 5
    assert quota.daily_limit == 1500


# ============================================================================
# CONCURRENCY TESTS (Story 6.8 Task 10 Subtask 10.4)
# ============================================================================


@pytest.mark.asyncio
async def test_concurrent_youtube_quota_updates_no_lost_updates(async_session, async_session_factory):
    """Concurrency test: Multiple workers updating same channel quota (Task 10 Subtask 10.4).

    This test verifies atomic upsert prevents race conditions when multiple workers
    record quota simultaneously for the same channel on the same day.
    Each worker uses a separate database session (as in production).
    """
    from unittest.mock import AsyncMock, patch

    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Mock alert threshold checks to focus on atomicity
    with patch("app.services.quota_service.check_youtube_quota_thresholds", new_callable=AsyncMock):
        # Simulate 3 concurrent workers each recording 2 uploads (1600 each)
        # Expected result: 6 * 1600 = 9600 units (no lost updates)
        # Each worker gets its own session (simulates real production workers)
        async def record_with_own_session(worker_id, upload_num):
            async with async_session_factory() as worker_session:
                await record_youtube_operation(
                    channel_id=channel.id,
                    operation="upload",
                    task_id=uuid4(),
                    video_id=f"worker{worker_id}_vid{upload_num}",
                    db=worker_session
                )

        tasks = []
        for worker_id in range(3):
            for upload_num in range(2):
                tasks.append(record_with_own_session(worker_id, upload_num))

        # Execute all operations concurrently
        await asyncio.gather(*tasks)

    # Verify no updates were lost
    quota = await get_youtube_quota_usage(channel.id, date.today(), async_session)
    assert quota.units_used == 9600  # 6 uploads * 1600 each
    assert quota.daily_limit == 10000


@pytest.mark.asyncio
async def test_concurrent_gemini_quota_updates_no_lost_updates(async_session, async_session_factory):
    """Concurrency test: Multiple workers updating Gemini quota atomically (Task 10 Subtask 10.4).

    Each worker uses a separate database session (as in production).
    """
    from unittest.mock import AsyncMock, patch

    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Mock alert threshold checks
    with patch("app.services.quota_service.check_gemini_quota_thresholds", new_callable=AsyncMock):
        # Simulate 5 concurrent workers each generating 3 assets
        # Expected result: 15 requests total
        # Each worker gets its own session (simulates real production workers)
        async def record_with_own_session(worker_id, asset_num):
            async with async_session_factory() as worker_session:
                await record_gemini_operation(
                    channel_id=channel.id,
                    task_id=uuid4(),
                    asset_name=f"worker{worker_id}_asset{asset_num}.png",
                    db=worker_session
                )

        tasks = []
        for worker_id in range(5):
            for asset_num in range(3):
                tasks.append(record_with_own_session(worker_id, asset_num))

        # Execute all operations concurrently
        await asyncio.gather(*tasks)

    # Verify no updates were lost
    quota = await get_gemini_quota_usage(channel.id, date.today(), async_session)
    assert quota.requests_used == 15  # 5 workers * 3 assets each
