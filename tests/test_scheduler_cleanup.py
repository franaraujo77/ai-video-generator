"""Tests for workspace cleanup scheduler integration (Story 8.5 Task 1).

Validates APScheduler integration for daily cleanup job including:
- Scheduler startup and shutdown
- Job registration and configuration
- Job execution with proper error handling
"""

import asyncio
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scheduler import (
    is_cleanup_scheduler_running,
    shutdown_cleanup_scheduler,
    start_cleanup_scheduler,
)


@pytest.mark.asyncio
async def test_start_cleanup_scheduler_registers_job():
    """Test cleanup scheduler starts and registers job correctly."""
    with patch("app.scheduler.AsyncIOScheduler") as MockScheduler:
        mock_scheduler_instance = MagicMock()
        mock_job = MagicMock()
        mock_job.next_run_time = datetime.now()
        mock_scheduler_instance.get_job.return_value = mock_job
        MockScheduler.return_value = mock_scheduler_instance

        await start_cleanup_scheduler()

        # Verify scheduler was created
        MockScheduler.assert_called_once()

        # Verify job was added
        mock_scheduler_instance.add_job.assert_called_once()
        call_args = mock_scheduler_instance.add_job.call_args

        # Verify job configuration
        assert call_args.kwargs["id"] == "cleanup_old_workspaces"
        assert call_args.kwargs["replace_existing"] is True
        assert call_args.kwargs["misfire_grace_time"] == 60

        # Verify scheduler was started
        mock_scheduler_instance.start.assert_called_once()


@pytest.mark.asyncio
async def test_start_cleanup_scheduler_disabled_when_env_false(monkeypatch):
    """Test cleanup scheduler doesn't start when disabled via env var."""
    monkeypatch.setenv("WORKSPACE_CLEANUP_ENABLED", "false")

    with patch("app.scheduler.AsyncIOScheduler") as MockScheduler:
        await start_cleanup_scheduler()

        # Scheduler should not be created when disabled
        MockScheduler.assert_not_called()


@pytest.mark.asyncio
async def test_start_cleanup_scheduler_uses_custom_schedule(monkeypatch):
    """Test cleanup scheduler uses custom cron schedule from env."""
    monkeypatch.setenv("WORKSPACE_CLEANUP_SCHEDULE", "30 4 * * *")  # 4:30am

    # Reset global scheduler state
    with patch("app.scheduler._cleanup_scheduler", None):
        with patch("app.scheduler.AsyncIOScheduler") as MockScheduler, \
             patch("app.scheduler.CronTrigger") as MockCronTrigger:
            mock_scheduler_instance = MagicMock()
            mock_scheduler_instance.running = False
            mock_job = MagicMock()
            mock_job.next_run_time = datetime.now()
            mock_scheduler_instance.get_job.return_value = mock_job
            MockScheduler.return_value = mock_scheduler_instance

            await start_cleanup_scheduler()

            # Verify CronTrigger called with custom schedule
            MockCronTrigger.assert_called_once()
            call_kwargs = MockCronTrigger.call_args.kwargs
            assert call_kwargs["hour"] == 4
            assert call_kwargs["minute"] == 30


@pytest.mark.asyncio
async def test_start_cleanup_scheduler_handles_invalid_schedule(monkeypatch):
    """Test cleanup scheduler handles invalid cron schedule gracefully."""
    monkeypatch.setenv("WORKSPACE_CLEANUP_SCHEDULE", "invalid")

    with patch("app.scheduler.AsyncIOScheduler") as MockScheduler:
        mock_scheduler_instance = MagicMock()
        MockScheduler.return_value = mock_scheduler_instance

        await start_cleanup_scheduler()

        # Scheduler should not start with invalid schedule
        mock_scheduler_instance.start.assert_not_called()


@pytest.mark.asyncio
async def test_start_cleanup_scheduler_already_running():
    """Test cleanup scheduler handles being called when already running."""
    # Mock an already running scheduler
    mock_scheduler_instance = MagicMock()
    mock_scheduler_instance.running = True

    with patch("app.scheduler._cleanup_scheduler", mock_scheduler_instance):
        with patch("app.scheduler.AsyncIOScheduler") as MockScheduler:
            # Second call should detect running scheduler and return early
            await start_cleanup_scheduler()

            # Should not create new scheduler when already running
            MockScheduler.assert_not_called()


def test_shutdown_cleanup_scheduler():
    """Test cleanup scheduler shuts down gracefully."""
    with patch("app.scheduler._cleanup_scheduler") as mock_scheduler:
        mock_scheduler.running = True

        shutdown_cleanup_scheduler()

        # Verify shutdown was called
        mock_scheduler.shutdown.assert_called_once_with(wait=True)


def test_shutdown_cleanup_scheduler_not_running():
    """Test shutdown handles scheduler not running."""
    with patch("app.scheduler._cleanup_scheduler", None):
        # Should not raise error when scheduler not running
        shutdown_cleanup_scheduler()


def test_shutdown_cleanup_scheduler_handles_event_loop_closed():
    """Test shutdown handles event loop closed error gracefully."""
    with patch("app.scheduler._cleanup_scheduler") as mock_scheduler:
        mock_scheduler.running = True
        mock_scheduler.shutdown.side_effect = RuntimeError("Event loop is closed")

        # Should not raise error
        shutdown_cleanup_scheduler()


def test_is_cleanup_scheduler_running_true():
    """Test is_cleanup_scheduler_running returns True when running."""
    with patch("app.scheduler._cleanup_scheduler") as mock_scheduler:
        mock_scheduler.running = True
        assert is_cleanup_scheduler_running() is True


def test_is_cleanup_scheduler_running_false():
    """Test is_cleanup_scheduler_running returns False when not running."""
    with patch("app.scheduler._cleanup_scheduler", None):
        assert is_cleanup_scheduler_running() is False


@pytest.mark.asyncio
async def test_cleanup_job_execution_success():
    """Test cleanup job executes successfully."""
    from app.scheduler import _cleanup_old_workspaces_job

    mock_result = {
        "directories_cleaned": 5,
        "disk_freed_mb": 150.5,
        "r2_assets_deleted": 25,
        "duration_seconds": 12.3,
    }

    # Patch where WorkspaceCleanupService is imported inside the function
    with patch("app.services.workspace_cleanup.WorkspaceCleanupService") as MockService, \
         patch("app.scheduler.AsyncSessionLocal") as MockSessionLocal:
        # Setup mocks
        mock_db = AsyncMock()
        MockSessionLocal.return_value.__aenter__.return_value = mock_db

        mock_service_instance = AsyncMock()
        mock_service_instance.cleanup_old_workspaces.return_value = mock_result
        MockService.return_value = mock_service_instance

        # Execute job
        await _cleanup_old_workspaces_job()

        # Verify cleanup was called
        mock_service_instance.cleanup_old_workspaces.assert_called_once_with(
            mock_db, 7  # Default retention days
        )


@pytest.mark.asyncio
async def test_cleanup_job_execution_error_handling():
    """Test cleanup job handles errors without crashing scheduler."""
    from app.scheduler import _cleanup_old_workspaces_job

    with patch("app.services.workspace_cleanup.WorkspaceCleanupService") as MockService, \
         patch("app.scheduler.AsyncSessionLocal") as MockSessionLocal:
        # Setup mocks
        mock_db = AsyncMock()
        MockSessionLocal.return_value.__aenter__.return_value = mock_db

        mock_service_instance = AsyncMock()
        mock_service_instance.cleanup_old_workspaces.side_effect = Exception("Database error")
        MockService.return_value = mock_service_instance

        # Execute job - should not raise exception
        await _cleanup_old_workspaces_job()

        # Job should complete without raising (logs error internally)


@pytest.mark.asyncio
async def test_cleanup_job_uses_custom_retention_days(monkeypatch):
    """Test cleanup job uses custom retention days from config."""
    monkeypatch.setenv("WORKSPACE_CLEANUP_RETENTION_DAYS", "14")

    from app.scheduler import _cleanup_old_workspaces_job

    mock_result = {
        "directories_cleaned": 0,
        "disk_freed_mb": 0,
        "r2_assets_deleted": 0,
        "duration_seconds": 0.1,
    }

    with patch("app.services.workspace_cleanup.WorkspaceCleanupService") as MockService, \
         patch("app.scheduler.AsyncSessionLocal") as MockSessionLocal:
        mock_db = AsyncMock()
        MockSessionLocal.return_value.__aenter__.return_value = mock_db

        mock_service_instance = AsyncMock()
        mock_service_instance.cleanup_old_workspaces.return_value = mock_result
        MockService.return_value = mock_service_instance

        await _cleanup_old_workspaces_job()

        # Verify custom retention days used
        mock_service_instance.cleanup_old_workspaces.assert_called_once_with(
            mock_db, 14
        )
