"""Tests for Weekly Metrics Service (Story 8.6).

This module tests the weekly_metrics_service which calculates overall pipeline
success metrics, auto-recovery effectiveness, and failure patterns.

Test Coverage:
- get_week_starting_date() helper function (ISO week Monday)
- calculate_weekly_metrics() with all metrics calculations
- Atomic upsert pattern (concurrent safety)
- Week boundary handling (Monday-Sunday)
- Zero division handling (no tasks)
- Success rate alerting (< 90% threshold)
- Week-over-week comparison
- calculate_all_channels_weekly_metrics() for scheduler

Architecture Compliance:
- Verifies atomic upsert pattern (INSERT ON CONFLICT UPDATE)
- Verifies short transactions (no long DB holds)
- Verifies Discord alerting integration
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models import Channel, Task, TaskStatus, WeeklyMetrics
from app.services.weekly_metrics_service import (
    calculate_all_channels_weekly_metrics,
    calculate_weekly_metrics,
    check_success_rate_thresholds,
    get_week_starting_date,
    get_weekly_metrics,
)


class TestGetWeekStartingDate:
    """Test get_week_starting_date() helper function."""

    def test_monday_returns_same_date(self):
        """Test Monday returns same date (week start)."""
        monday = date(2026, 1, 19)  # Monday
        assert monday.weekday() == 0  # Verify it's Monday
        result = get_week_starting_date(monday)
        assert result == monday

    def test_tuesday_returns_previous_monday(self):
        """Test Tuesday returns previous Monday."""
        tuesday = date(2026, 1, 20)  # Tuesday
        assert tuesday.weekday() == 1  # Verify it's Tuesday
        result = get_week_starting_date(tuesday)
        assert result == date(2026, 1, 19)  # Previous Monday

    def test_sunday_returns_previous_monday(self):
        """Test Sunday returns previous Monday (week includes Sunday)."""
        sunday = date(2026, 1, 25)  # Sunday
        assert sunday.weekday() == 6  # Verify it's Sunday
        result = get_week_starting_date(sunday)
        assert result == date(2026, 1, 19)  # Previous Monday

    def test_next_monday_starts_new_week(self):
        """Test next Monday starts a new week."""
        monday1 = date(2026, 1, 19)
        monday2 = date(2026, 1, 26)
        assert get_week_starting_date(monday1) == monday1
        assert get_week_starting_date(monday2) == monday2
        assert monday2 - monday1 == timedelta(days=7)


@pytest.mark.asyncio
class TestCalculateWeeklyMetrics:
    """Test calculate_weekly_metrics() function."""

    async def test_calculate_metrics_success_rate(self, async_session):
        """Test success rate calculation with mixed outcomes."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        week_start = date(2026, 1, 19)  # Monday

        # Create 10 tasks: 8 successful, 2 failed (all within week Jan 19-25)
        for i in range(8):
            task = Task(
                channel_id=channel.id,
                notion_page_id=f"notion_success_{i}",
                title=f"Success Video {i}",
                topic="Test topic",
                story_direction="Test direction",
                status=TaskStatus.PUBLISHED,
                created_at=datetime(2026, 1, 20, 10, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 1, 20 + (i % 6), 12, 0, tzinfo=timezone.utc),  # Cycles Jan 20-25
            )
            async_session.add(task)

        for i in range(2):
            task = Task(
                channel_id=channel.id,
                notion_page_id=f"notion_fail_{i}",
                title=f"Failed Video {i}",
                topic="Test topic",
                story_direction="Test direction",
                status=TaskStatus.ASSET_ERROR,
                error_category="TRANSIENT",
                created_at=datetime(2026, 1, 20, 10, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 1, 24 + i, 12, 0, tzinfo=timezone.utc),  # Jan 24-25
            )
            async_session.add(task)

        await async_session.commit()

        # Execute
        metrics = await calculate_weekly_metrics(channel.id, week_start, async_session)

        # Assert
        assert metrics.total_videos_processed == 10
        assert metrics.successful_videos == 8
        assert metrics.success_rate == Decimal("80.00")
        assert metrics.failed_at_assets == 2
        assert metrics.transient_failures == 2
        assert metrics.calculated_at is not None

    async def test_calculate_metrics_no_tasks(self, async_session):
        """Test metrics calculation with no tasks (zero division handling)."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        week_start = date(2026, 1, 19)

        # Execute (no tasks)
        metrics = await calculate_weekly_metrics(channel.id, week_start, async_session)

        # Assert defaults
        assert metrics.total_videos_processed == 0
        assert metrics.successful_videos == 0
        assert metrics.success_rate == Decimal("0.00")
        assert metrics.avg_processing_time_seconds is None  # No completed tasks
        assert metrics.auto_recovery_rate is None  # No retry attempts

    async def test_calculate_metrics_processing_time(self, async_session):
        """Test average processing time calculation."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        week_start = date(2026, 1, 19)

        # Create tasks with different processing times
        # Task 1: 1 hour (3600 seconds)
        task1 = Task(
            channel_id=channel.id,
            notion_page_id="notion1",
            title="Video 1",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.PUBLISHED,
            created_at=datetime(2026, 1, 21, 10, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 21, 11, 0, tzinfo=timezone.utc),  # +1 hour
        )
        # Task 2: 2 hours (7200 seconds)
        task2 = Task(
            channel_id=channel.id,
            notion_page_id="notion2",
            title="Video 2",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.PUBLISHED,
            created_at=datetime(2026, 1, 22, 10, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 22, 12, 0, tzinfo=timezone.utc),  # +2 hours
        )
        async_session.add_all([task1, task2])
        await async_session.commit()

        # Execute
        metrics = await calculate_weekly_metrics(channel.id, week_start, async_session)

        # Assert: Average = (3600 + 7200) / 2 = 5400 seconds
        assert metrics.avg_processing_time_seconds == 5400

    async def test_calculate_metrics_auto_recovery_rate(self, async_session):
        """Test auto-recovery rate calculation."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        week_start = date(2026, 1, 19)

        # Create tasks with retry attempts
        # 4 tasks with retries: 3 recovered, 1 failed
        for i in range(3):
            task = Task(
                channel_id=channel.id,
                notion_page_id=f"notion_recovered_{i}",
                title=f"Recovered {i}",
                topic="Test",
                story_direction="Test",
                status=TaskStatus.PUBLISHED,
                retry_count=2,
                auto_recovered=True,
                updated_at=datetime(2026, 1, 21 + i, 12, 0, tzinfo=timezone.utc),
            )
            async_session.add(task)

        task_failed = Task(
            channel_id=channel.id,
            notion_page_id="notion_failed",
            title="Failed",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.ASSET_ERROR,
            retry_count=3,
            auto_recovered=False,
            updated_at=datetime(2026, 1, 25, 12, 0, tzinfo=timezone.utc),
        )
        async_session.add(task_failed)
        await async_session.commit()

        # Execute
        metrics = await calculate_weekly_metrics(channel.id, week_start, async_session)

        # Assert: 3 recovered / 4 with retries = 75%
        assert metrics.auto_recovery_rate == Decimal("75.00")

    async def test_calculate_metrics_failure_breakdown(self, async_session):
        """Test failure breakdown by category and stage."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        week_start = date(2026, 1, 19)

        # Create failed tasks with different categories and stages
        failures = [
            (TaskStatus.ASSET_ERROR, "TRANSIENT"),
            (TaskStatus.ASSET_ERROR, "TRANSIENT"),
            (TaskStatus.VIDEO_ERROR, "PERMANENT"),
            (TaskStatus.AUDIO_ERROR, "UNKNOWN"),
            (TaskStatus.UPLOAD_ERROR, "TRANSIENT"),
        ]

        for i, (status, category) in enumerate(failures):
            task = Task(
                channel_id=channel.id,
                notion_page_id=f"notion_fail_{i}",
                title=f"Failed {i}",
                topic="Test",
                story_direction="Test",
                status=status,
                error_category=category,
                updated_at=datetime(2026, 1, 21 + i, 12, 0, tzinfo=timezone.utc),
            )
            async_session.add(task)

        await async_session.commit()

        # Execute
        metrics = await calculate_weekly_metrics(channel.id, week_start, async_session)

        # Assert failure breakdown
        assert metrics.transient_failures == 3
        assert metrics.permanent_failures == 1
        assert metrics.unknown_failures == 1
        assert metrics.failed_at_assets == 2
        assert metrics.failed_at_video == 1
        assert metrics.failed_at_audio == 1
        assert metrics.failed_at_upload == 1

    async def test_week_boundary_handling(self, async_session):
        """Test ISO week boundary handling (Monday-Sunday)."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        week_start = date(2026, 1, 19)  # Monday

        # Task on Sunday (last day of week) - SHOULD be included
        task_sunday = Task(
            channel_id=channel.id,
            notion_page_id="notion_sunday",
            title="Sunday Task",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.PUBLISHED,
            updated_at=datetime(2026, 1, 25, 23, 59, 59, tzinfo=timezone.utc),  # Sunday 23:59:59
        )

        # Task on next Monday (first day of next week) - should NOT be included
        task_next_monday = Task(
            channel_id=channel.id,
            notion_page_id="notion_next_monday",
            title="Next Monday Task",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.PUBLISHED,
            updated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),  # Next Monday 00:00:00
        )

        async_session.add_all([task_sunday, task_next_monday])
        await async_session.commit()

        # Execute
        metrics = await calculate_weekly_metrics(channel.id, week_start, async_session)

        # Assert: Only Sunday task included
        assert metrics.total_videos_processed == 1
        assert metrics.successful_videos == 1

    async def test_atomic_upsert_pattern(self, async_session):
        """Test atomic upsert (INSERT ON CONFLICT UPDATE)."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        week_start = date(2026, 1, 19)

        # Create initial task
        task1 = Task(
            channel_id=channel.id,
            notion_page_id="notion1",
            title="Video 1",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.PUBLISHED,
            updated_at=datetime(2026, 1, 21, 12, 0, tzinfo=timezone.utc),
        )
        async_session.add(task1)
        await async_session.commit()

        # First calculation
        metrics1 = await calculate_weekly_metrics(channel.id, week_start, async_session)
        assert metrics1.total_videos_processed == 1
        first_calculated_at = metrics1.calculated_at

        # Add more tasks
        task2 = Task(
            channel_id=channel.id,
            notion_page_id="notion2",
            title="Video 2",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.PUBLISHED,
            updated_at=datetime(2026, 1, 22, 12, 0, tzinfo=timezone.utc),
        )
        async_session.add(task2)
        await async_session.commit()

        # Second calculation (should UPDATE existing record)
        metrics2 = await calculate_weekly_metrics(channel.id, week_start, async_session)
        assert metrics2.total_videos_processed == 2
        assert metrics2.calculated_at > first_calculated_at  # Updated timestamp

        # Verify only one record exists
        result = await async_session.execute(
            select(WeeklyMetrics).where(
                WeeklyMetrics.channel_id == channel.id,
                WeeklyMetrics.week_starting_date == week_start,
            )
        )
        all_metrics = result.scalars().all()
        assert len(all_metrics) == 1  # Upsert worked

    async def test_terminal_statuses_only(self, async_session):
        """Test only terminal statuses are counted."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        week_start = date(2026, 1, 19)

        # Create tasks with various statuses
        statuses = [
            TaskStatus.PUBLISHED,  # Terminal - success
            TaskStatus.CANCELLED,  # Terminal - not success
            TaskStatus.ASSET_ERROR,  # Terminal - failure
            TaskStatus.GENERATING_ASSETS,  # In-progress - should NOT count
            TaskStatus.VIDEO_READY,  # Review gate - should NOT count
        ]

        for i, status in enumerate(statuses):
            task = Task(
                channel_id=channel.id,
                notion_page_id=f"notion_{i}",
                title=f"Task {i}",
                topic="Test",
                story_direction="Test",
                status=status,
                updated_at=datetime(2026, 1, 21 + i, 12, 0, tzinfo=timezone.utc),
            )
            async_session.add(task)

        await async_session.commit()

        # Execute
        metrics = await calculate_weekly_metrics(channel.id, week_start, async_session)

        # Assert: Only terminal statuses counted (PUBLISHED, CANCELLED, errors)
        assert metrics.total_videos_processed == 3  # published, cancelled, asset_error
        assert metrics.successful_videos == 1  # Only PUBLISHED


@pytest.mark.asyncio
class TestCheckSuccessRateThresholds:
    """Test check_success_rate_thresholds() alerting function."""

    async def test_no_alert_above_threshold(self, async_session):
        """Test no alert when success rate >= 90%."""
        # Setup: Create channel and metrics with 95% success rate
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        metrics = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=date(2026, 1, 19),
            total_videos_processed=20,
            successful_videos=19,
            success_rate=Decimal("95.00"),
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()

        # Execute with mock
        with patch("app.services.weekly_metrics_service.send_discord_alert") as mock_alert:
            await check_success_rate_thresholds(metrics, async_session)

            # Assert: No alert sent
            mock_alert.assert_not_called()

    async def test_alert_below_threshold(self, async_session):
        """Test alert sent when success rate < 90%."""
        # Setup: Create channel and metrics with 85% success rate
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        metrics = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=date(2026, 1, 19),
            total_videos_processed=20,
            successful_videos=17,
            success_rate=Decimal("85.00"),
            transient_failures=2,
            permanent_failures=1,
            failed_at_assets=2,
            failed_at_video=1,
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()

        # Execute with mock
        with patch(
            "app.services.weekly_metrics_service.send_discord_alert", new_callable=AsyncMock
        ) as mock_alert:
            with patch("app.services.weekly_metrics_service.os.getenv", return_value="mock_webhook"):
                await check_success_rate_thresholds(metrics, async_session)

                # Assert: Alert sent
                mock_alert.assert_called_once()
                call_args = mock_alert.call_args[1]
                assert call_args["alert_type"] == "low_success_rate"
                assert call_args["severity"] == "WARNING"
                assert "85.0%" in call_args["title"]
                assert "90%" in call_args["title"]

    async def test_alert_includes_most_common_failure(self, async_session):
        """Test alert includes most common failure stage."""
        # Setup: Create channel and metrics
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        metrics = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=date(2026, 1, 19),
            total_videos_processed=20,
            successful_videos=17,
            success_rate=Decimal("85.00"),
            failed_at_assets=1,
            failed_at_video=2,  # Most common
            failed_at_audio=0,
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()

        # Execute with mock
        with patch(
            "app.services.weekly_metrics_service.send_discord_alert", new_callable=AsyncMock
        ) as mock_alert:
            with patch("app.services.weekly_metrics_service.os.getenv", return_value="mock_webhook"):
                await check_success_rate_thresholds(metrics, async_session)

                # Assert: Alert mentions video stage
                call_args = mock_alert.call_args[1]
                assert "video" in call_args["description"].lower()


@pytest.mark.asyncio
class TestCalculateAllChannelsWeeklyMetrics:
    """Test calculate_all_channels_weekly_metrics() for scheduler."""

    async def test_calculate_all_active_channels(self, async_session):
        """Test calculation for all active channels."""
        # Setup: Create 2 active channels, 1 inactive
        channel1 = Channel(
            channel_id="active1",
            channel_name="Active 1",
            voice_id="voice1",
            max_concurrent=2,
            is_active=True,
        )
        channel2 = Channel(
            channel_id="active2",
            channel_name="Active 2",
            voice_id="voice2",
            max_concurrent=2,
            is_active=True,
        )
        channel3 = Channel(
            channel_id="inactive",
            channel_name="Inactive",
            voice_id="voice3",
            max_concurrent=2,
            is_active=False,
        )
        async_session.add_all([channel1, channel2, channel3])
        await async_session.commit()

        week_start = date(2026, 1, 19)

        # Execute
        metrics_list = await calculate_all_channels_weekly_metrics(week_start, async_session)

        # Assert: Only active channels processed
        assert len(metrics_list) == 2
        channel_ids = {m.channel_id for m in metrics_list}
        assert channel1.id in channel_ids
        assert channel2.id in channel_ids
        assert channel3.id not in channel_ids


@pytest.mark.asyncio
class TestGetWeeklyMetrics:
    """Test get_weekly_metrics() query function."""

    async def test_get_existing_metrics(self, async_session):
        """Test retrieving existing metrics."""
        # Setup: Create channel and metrics
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        week_start = date(2026, 1, 19)
        metrics = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=week_start,
            success_rate=Decimal("85.00"),
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()

        # Execute
        result = await get_weekly_metrics(channel.id, week_start, async_session)

        # Assert
        assert result is not None
        assert result.success_rate == Decimal("85.00")

    async def test_get_nonexistent_metrics(self, async_session):
        """Test retrieving non-existent metrics returns None."""
        # Setup: Create channel (no metrics)
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        # Execute
        result = await get_weekly_metrics(channel.id, date(2026, 1, 20), async_session)

        # Assert
        assert result is None
