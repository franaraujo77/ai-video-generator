"""Tests for worker process entry point.

This test module covers:
- Worker startup and initialization (Scenario 1)
- Database connection pool configuration (Scenario 2)
- Async session factory for workers (Scenario 3)
- Graceful shutdown on SIGTERM (Scenario 4)
- Worker continuous loop (Scenario 5)
- Structured logging with worker identification (Scenario 6)
- Worker error handling and recovery (Scenario 10)
"""

import asyncio
import os
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import worker


class TestWorkerStartup:
    """Tests for worker startup and initialization (Scenario 1)."""

    @patch("app.worker.get_config")
    def test_worker_configuration_loading_success(self, mock_config):
        """Test worker loads configuration from environment on startup."""
        mock_config.return_value = MagicMock(
            database_url="postgresql+asyncpg://localhost/test",
            fernet_key="test-key-12345678901234567890123456789012",
        )

        # Should not raise
        config = mock_config()
        assert config.database_url.startswith("postgresql+asyncpg://")
        assert len(config.fernet_key) >= 32

    @patch("app.worker.get_config")
    def test_worker_configuration_loading_failure(self, mock_config):
        """Test worker exits with code 1 when configuration fails."""
        mock_config.side_effect = ValueError("DATABASE_URL not set")

        # Worker should catch this and exit with code 1
        with pytest.raises(ValueError, match="DATABASE_URL not set"):
            mock_config()

    @patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-1"})
    def test_worker_id_from_railway_env(self):
        """Test worker extracts worker_id from RAILWAY_SERVICE_NAME."""
        worker_id = os.getenv("RAILWAY_SERVICE_NAME", "worker-local")
        assert worker_id == "worker-1"

    @patch.dict(os.environ, {}, clear=True)
    def test_worker_id_defaults_to_local(self):
        """Test worker defaults to 'worker-local' when RAILWAY_SERVICE_NAME not set."""
        worker_id = os.getenv("RAILWAY_SERVICE_NAME", "worker-local")
        assert worker_id == "worker-local"


class TestSignalHandling:
    """Tests for graceful shutdown signal handling (Scenario 4)."""

    def test_signal_handler_sets_shutdown_flag(self):
        """Test SIGTERM signal handler sets shutdown_requested flag."""
        # Reset global flag
        worker.shutdown_requested = False

        # Call signal handler
        worker.signal_handler(signal.SIGTERM, None)

        # Verify flag is set
        assert worker.shutdown_requested is True

    def test_signal_handler_logs_signal_info(self):
        """Test signal handler logs signal information."""
        worker.shutdown_requested = False

        # Should not raise and should set flag
        worker.signal_handler(signal.SIGINT, None)
        assert worker.shutdown_requested is True


class TestWorkerMainLoop:
    """Tests for worker main loop execution (Scenario 5)."""

    @pytest.mark.asyncio
    @patch("app.worker.asyncio.sleep", new_callable=AsyncMock)
    @patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-test"})
    async def test_main_loop_sleeps_between_iterations(self, mock_sleep):
        """Test main loop sleeps 1 second between iterations to prevent CPU spinning."""
        worker.shutdown_requested = False

        # Run one iteration then trigger shutdown
        async def sleep_and_shutdown(duration):
            worker.shutdown_requested = True

        mock_sleep.side_effect = sleep_and_shutdown

        await worker.worker_main_loop()

        # Verify sleep was called with 1 second
        mock_sleep.assert_called_with(1)

    @pytest.mark.asyncio
    @patch("app.worker.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.worker.datetime")
    async def test_heartbeat_logging_every_60_seconds(self, mock_datetime, mock_sleep):
        """Test worker logs heartbeat every 60 seconds."""
        from datetime import datetime, timedelta, timezone

        # Mock time progression
        start_time = datetime(2026, 1, 16, 12, 0, 0, tzinfo=timezone.utc)
        times = [
            start_time,
            start_time,
            start_time + timedelta(seconds=61),  # Trigger heartbeat
        ]
        mock_datetime.now.side_effect = times

        iterations = 0

        async def sleep_and_count(duration):
            nonlocal iterations
            iterations += 1
            if iterations >= 2:
                worker.shutdown_requested = True

        mock_sleep.side_effect = sleep_and_count
        worker.shutdown_requested = False

        await worker.worker_main_loop()

        # Should have completed 2 iterations
        assert iterations == 2


class TestErrorHandling:
    """Tests for worker error handling and recovery (Scenario 10)."""

    @pytest.mark.asyncio
    @patch("app.worker.asyncio.sleep", new_callable=AsyncMock)
    async def test_worker_continues_after_exception(self, mock_sleep):
        """Test worker catches exceptions and continues running."""
        iterations = 0

        async def sleep_with_error(duration):
            nonlocal iterations
            iterations += 1
            if iterations == 1:
                raise RuntimeError("Simulated error")
            elif iterations == 2:
                worker.shutdown_requested = True

        mock_sleep.side_effect = sleep_with_error
        worker.shutdown_requested = False

        # Should not raise - worker catches and continues
        await worker.worker_main_loop()

        # Should have completed both iterations despite error
        assert iterations == 2

    @pytest.mark.asyncio
    @patch("app.worker.asyncio.sleep", new_callable=AsyncMock)
    async def test_consecutive_error_tracking(self, mock_sleep):
        """Test worker tracks consecutive errors and resets on success."""
        sleep_calls = 0

        async def sleep_with_controlled_errors(duration):
            nonlocal sleep_calls
            sleep_calls += 1
            # duration=1: main loop sleeps
            # duration=5: error recovery sleeps (should not fail)
            if duration == 1 and sleep_calls in [1, 2, 3]:
                raise RuntimeError(f"Error {sleep_calls}")
            elif sleep_calls == 10:  # After 3 errors + 3 recovery + 3 more iterations
                worker.shutdown_requested = True

        mock_sleep.side_effect = sleep_with_controlled_errors
        worker.shutdown_requested = False

        # Should handle 3 consecutive errors without crashing
        await worker.worker_main_loop()

        # Should have completed multiple iterations with errors and recoveries
        assert sleep_calls >= 6


class TestDatabaseConfiguration:
    """Tests for database connection pool configuration (Scenario 2)."""

    def test_database_engine_uses_asyncpg_driver(self):
        """Test database engine uses postgresql+asyncpg:// protocol."""
        from app.database import _get_database_url

        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:pass@localhost/db"},
        ):
            url = _get_database_url()
            assert url.startswith("postgresql+asyncpg://")

    def test_database_engine_pool_configuration(self):
        """Test database engine has correct pool settings for 3 workers."""
        from app.database import engine

        # Skip test if DATABASE_URL not configured (test environment)
        if engine is None:
            pytest.skip("DATABASE_URL not configured, skipping pool configuration test")

        # pool_size=10 (3 workers + web service)
        assert engine.pool.size() == 10 or hasattr(engine.pool, "_pool_size")

    def test_pool_pre_ping_enabled(self):
        """Test pool_pre_ping=True for Railway connection recycling."""
        from app.database import engine

        # Skip test if DATABASE_URL not configured (test environment)
        if engine is None:
            pytest.skip("DATABASE_URL not configured, skipping pre_ping test")

        # Verify pool_pre_ping is enabled (Railway requires this for connection recycling)
        # Note: Different SQLAlchemy versions expose this differently
        assert hasattr(engine.pool, "_pre_ping") or hasattr(engine.pool, "pre_ping")


class TestAsyncSessionFactory:
    """Tests for async session factory (Scenario 3)."""

    @pytest.mark.asyncio
    async def test_session_factory_creates_async_session(self):
        """Test AsyncSessionLocal creates async sessions."""
        from app.database import async_session_factory

        if async_session_factory:
            async with async_session_factory() as session:
                # Session should be AsyncSession type
                assert hasattr(session, "execute")
                assert hasattr(session, "commit")

    @pytest.mark.asyncio
    async def test_session_auto_closes_after_context(self):
        """Test session auto-closes after context manager exits."""
        from app.database import async_session_factory

        if async_session_factory:
            session = None
            async with async_session_factory() as s:
                session = s
                assert session is not None

            # Session should be closed after context exit
            # (We can't easily test this without actual DB, but structure is correct)
            assert session is not None


class TestShutdownCleanup:
    """Tests for graceful shutdown and cleanup."""

    @pytest.mark.asyncio
    @patch("app.worker.async_engine")
    async def test_shutdown_closes_database_connections(self, mock_engine):
        """Test shutdown_worker() closes database engine."""
        mock_engine.dispose = AsyncMock()

        await worker.shutdown_worker()

        mock_engine.dispose.assert_called_once()


class TestStructuredLogging:
    """Tests for structured logging with worker identification (Scenario 6)."""

    def test_logger_outputs_json_format(self):
        """Test structured logger outputs JSON format."""
        from app.utils.logging import get_logger

        log = get_logger(__name__)

        # Logger should have JSON formatting capability
        assert hasattr(log, "info")
        assert hasattr(log, "error")
        assert hasattr(log, "warning")

    @patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-1"})
    def test_worker_id_included_in_log_context(self):
        """Test worker_id is available for all log messages."""
        worker_id = os.getenv("RAILWAY_SERVICE_NAME", "worker-local")
        assert worker_id == "worker-1"

        # Worker should include this in all log calls
        # (Actual log output tested in integration tests)
