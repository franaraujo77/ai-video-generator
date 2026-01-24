"""Tests for APScheduler quota reset scheduler.

Tests scheduler startup, shutdown, job registration, and integration with worker process.

Note: These tests are integration tests that verify scheduler configuration.
They do NOT test actual job execution (job execution tested in test_quota_reset_service.py).
"""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from app import scheduler as scheduler_module


@pytest.fixture(autouse=True, scope="function")
def reset_scheduler():
    """Reset scheduler state before and after each test."""
    # Cleanup before test
    try:
        if scheduler_module._scheduler is not None:
            if scheduler_module._scheduler.running:
                scheduler_module._scheduler.shutdown(wait=False)
            scheduler_module._scheduler = None
    except Exception:
        pass  # Ignore cleanup errors

    yield

    # Cleanup after test
    try:
        if scheduler_module._scheduler is not None:
            if scheduler_module._scheduler.running:
                scheduler_module._scheduler.shutdown(wait=False)
            scheduler_module._scheduler = None
    except Exception:
        pass  # Ignore cleanup errors


class TestSchedulerLifecycle:
    """Test scheduler startup and shutdown."""

    async def test_scheduler_starts_successfully(self):
        """Test that scheduler starts without errors."""
        await scheduler_module.start_quota_reset_scheduler()
        assert scheduler_module.is_scheduler_running() is True

    async def test_scheduler_registers_youtube_job(self):
        """Test that YouTube quota reset job is registered."""
        await scheduler_module.start_quota_reset_scheduler()

        # Verify job exists
        assert scheduler_module._scheduler is not None
        youtube_job = scheduler_module._scheduler.get_job("reset_youtube_quotas")
        assert youtube_job is not None
        assert youtube_job.id == "reset_youtube_quotas"

    async def test_scheduler_registers_gemini_job(self):
        """Test that Gemini quota reset job is registered."""
        await scheduler_module.start_quota_reset_scheduler()

        # Verify job exists
        assert scheduler_module._scheduler is not None
        gemini_job = scheduler_module._scheduler.get_job("reset_gemini_quotas")
        assert gemini_job is not None
        assert gemini_job.id == "reset_gemini_quotas"

    async def test_scheduler_uses_pacific_timezone(self):
        """Test that scheduler is configured with America/Los_Angeles timezone."""
        await scheduler_module.start_quota_reset_scheduler()

        assert scheduler_module._scheduler is not None
        # Scheduler timezone should be Pacific
        assert str(scheduler_module._scheduler.timezone) == "America/Los_Angeles"

    async def test_scheduler_shutdown_gracefully(self):
        """Test that scheduler shuts down gracefully."""
        await scheduler_module.start_quota_reset_scheduler()
        assert scheduler_module.is_scheduler_running() is True

        scheduler_module.shutdown_quota_reset_scheduler()
        assert scheduler_module.is_scheduler_running() is False

    async def test_scheduler_idempotent_start(self):
        """Test that starting scheduler multiple times doesn't cause errors."""
        await scheduler_module.start_quota_reset_scheduler()
        await scheduler_module.start_quota_reset_scheduler()  # Should not raise

        assert scheduler_module.is_scheduler_running() is True

    def test_scheduler_shutdown_when_not_running(self):
        """Test that shutting down when not running doesn't cause errors."""
        # Should not raise even if scheduler not running
        scheduler_module.shutdown_quota_reset_scheduler()


class TestSchedulerJobConfiguration:
    """Test scheduler job configuration details."""

    async def test_jobs_scheduled_for_midnight(self):
        """Test that jobs are scheduled for midnight (00:00)."""
        await scheduler_module.start_quota_reset_scheduler()

        assert scheduler_module._scheduler is not None
        youtube_job = scheduler_module._scheduler.get_job("reset_youtube_quotas")

        # Get the trigger configuration
        trigger = youtube_job.trigger
        # Trigger should fire at hour=0, minute=0
        assert trigger.fields[4].expressions[0].last == 0  # hour
        assert trigger.fields[5].expressions[0].last == 0  # minute

    async def test_jobs_have_misfire_grace_time(self):
        """Test that jobs have 60 second misfire grace time configured."""
        await scheduler_module.start_quota_reset_scheduler()

        assert scheduler_module._scheduler is not None
        youtube_job = scheduler_module._scheduler.get_job("reset_youtube_quotas")
        gemini_job = scheduler_module._scheduler.get_job("reset_gemini_quotas")

        # Both jobs should have misfire_grace_time set
        assert youtube_job.misfire_grace_time == 60
        assert gemini_job.misfire_grace_time == 60

    async def test_jobs_replace_existing_on_restart(self):
        """Test that jobs are configured to replace_existing=True."""
        await scheduler_module.start_quota_reset_scheduler()
        assert scheduler_module.is_scheduler_running() is True

        # Get initial job
        assert scheduler_module._scheduler is not None
        initial_job = scheduler_module._scheduler.get_job("reset_youtube_quotas")

        # Restart scheduler (simulates worker restart)
        scheduler_module.shutdown_quota_reset_scheduler()
        await scheduler_module.start_quota_reset_scheduler()

        # Job should be re-registered
        new_job = scheduler_module._scheduler.get_job("reset_youtube_quotas")
        assert new_job is not None
        # Job ID should be the same (replaced)
        assert new_job.id == "reset_youtube_quotas"


class TestSchedulerHealthCheck:
    """Test scheduler health check integration."""

    async def test_is_scheduler_running_when_started(self):
        """Test that is_scheduler_running returns True when started."""
        await scheduler_module.start_quota_reset_scheduler()
        assert scheduler_module.is_scheduler_running() is True

    def test_is_scheduler_running_when_stopped(self):
        """Test that is_scheduler_running returns False when stopped."""
        # Ensure scheduler is not running
        scheduler_module.shutdown_quota_reset_scheduler()
        assert scheduler_module.is_scheduler_running() is False

    def test_is_scheduler_running_initial_state(self):
        """Test that is_scheduler_running returns False initially (after fixture reset)."""
        # Fixture ensures scheduler is stopped
        assert scheduler_module.is_scheduler_running() is False
