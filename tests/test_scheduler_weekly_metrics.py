"""Tests for APScheduler weekly metrics scheduler (Story 8.6).

Tests scheduler startup, shutdown, job registration, and weekly metrics calculation.

Note: These tests are integration tests that verify scheduler configuration.
They do NOT test actual metrics calculation (tested in test_weekly_metrics_service.py).
"""

import pytest

from app import scheduler as scheduler_module


@pytest.fixture(autouse=True, scope="function")
def reset_weekly_metrics_scheduler():
    """Reset weekly metrics scheduler state before and after each test."""
    # Cleanup before test
    try:
        if scheduler_module._weekly_metrics_scheduler is not None:
            if scheduler_module._weekly_metrics_scheduler.running:
                scheduler_module._weekly_metrics_scheduler.shutdown(wait=False)
            scheduler_module._weekly_metrics_scheduler = None
    except Exception:
        pass  # Ignore cleanup errors

    yield

    # Cleanup after test
    try:
        if scheduler_module._weekly_metrics_scheduler is not None:
            if scheduler_module._weekly_metrics_scheduler.running:
                scheduler_module._weekly_metrics_scheduler.shutdown(wait=False)
            scheduler_module._weekly_metrics_scheduler = None
    except Exception:
        pass  # Ignore cleanup errors


class TestWeeklyMetricsSchedulerLifecycle:
    """Test weekly metrics scheduler startup and shutdown."""

    async def test_scheduler_starts_successfully(self):
        """Test that weekly metrics scheduler starts without errors."""
        await scheduler_module.start_weekly_metrics_scheduler()
        assert scheduler_module.is_weekly_metrics_scheduler_running() is True

    async def test_scheduler_registers_weekly_metrics_job(self):
        """Test that weekly metrics calculation job is registered."""
        await scheduler_module.start_weekly_metrics_scheduler()

        # Verify job exists
        assert scheduler_module._weekly_metrics_scheduler is not None
        job = scheduler_module._weekly_metrics_scheduler.get_job("calculate_weekly_metrics")
        assert job is not None
        assert job.id == "calculate_weekly_metrics"

    async def test_scheduler_uses_utc_timezone(self):
        """Test that weekly metrics scheduler uses UTC timezone."""
        await scheduler_module.start_weekly_metrics_scheduler()

        assert scheduler_module._weekly_metrics_scheduler is not None
        # Scheduler timezone should be UTC (not Pacific like quota resets)
        assert str(scheduler_module._weekly_metrics_scheduler.timezone) == "UTC"

    async def test_scheduler_shutdown_gracefully(self):
        """Test that weekly metrics scheduler shuts down gracefully."""
        await scheduler_module.start_weekly_metrics_scheduler()
        assert scheduler_module.is_weekly_metrics_scheduler_running() is True

        scheduler_module.shutdown_weekly_metrics_scheduler()
        assert scheduler_module.is_weekly_metrics_scheduler_running() is False

    async def test_scheduler_idempotent_start(self):
        """Test that starting scheduler multiple times doesn't cause errors."""
        await scheduler_module.start_weekly_metrics_scheduler()
        await scheduler_module.start_weekly_metrics_scheduler()  # Should not raise

        assert scheduler_module.is_weekly_metrics_scheduler_running() is True


class TestWeeklyMetricsJobConfiguration:
    """Test weekly metrics job configuration details."""

    async def test_job_scheduled_for_monday_midnight_utc(self):
        """Test that weekly metrics job runs on Monday at 00:00 UTC."""
        await scheduler_module.start_weekly_metrics_scheduler()

        assert scheduler_module._weekly_metrics_scheduler is not None
        job = scheduler_module._weekly_metrics_scheduler.get_job("calculate_weekly_metrics")
        assert job is not None

        # Verify cron trigger configuration
        trigger = job.trigger
        assert trigger.fields[0].name == "year"
        assert trigger.fields[1].name == "month"
        assert trigger.fields[2].name == "day"
        assert trigger.fields[3].name == "week"
        assert trigger.fields[4].name == "day_of_week"
        assert trigger.fields[5].name == "hour"
        assert trigger.fields[6].name == "minute"
        assert trigger.fields[7].name == "second"

        # Monday = 0 in APScheduler, hour = 0, minute = 0
        # Check that day_of_week = 0 (Monday), hour = 0, minute = 0
        assert str(trigger.fields[4]) == "0"  # Monday
        assert str(trigger.fields[5]) == "0"  # 00:00 hour
        assert str(trigger.fields[6]) == "0"  # 00:00 minute
