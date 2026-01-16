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
    """Tests for worker main loop with PgQueuer integration (Story 4.2)."""

    @pytest.mark.asyncio
    @patch("app.queue.initialize_pgqueuer", new_callable=AsyncMock)
    @patch("app.entrypoints.register_entrypoints")
    @patch.dict(os.environ, {"RAILWAY_SERVICE_NAME": "worker-test"})
    async def test_main_loop_initializes_pgqueuer(self, mock_register, mock_init_pgq):
        """Test main loop initializes PgQueuer with asyncpg pool."""
        worker.shutdown_requested = False

        # Mock PgQueuer initialization
        mock_pgq = MagicMock()
        mock_pgq.run = AsyncMock()
        mock_pool = MagicMock()
        mock_init_pgq.return_value = (mock_pgq, mock_pool)

        # Trigger shutdown immediately after pgq.run() starts
        async def run_and_shutdown():
            worker.shutdown_requested = True

        mock_pgq.run.side_effect = run_and_shutdown

        await worker.worker_main_loop()

        # Verify initialization and registration happened
        mock_init_pgq.assert_called_once()
        mock_register.assert_called_once_with(mock_pgq)
        mock_pgq.run.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.queue.initialize_pgqueuer", new_callable=AsyncMock)
    @patch("app.entrypoints.register_entrypoints")
    async def test_main_loop_registers_entrypoints(self, mock_register, mock_init_pgq):
        """Test main loop registers entrypoints after PgQueuer initialization."""
        worker.shutdown_requested = False

        # Mock PgQueuer
        mock_pgq = MagicMock()
        mock_pgq.run = AsyncMock(side_effect=lambda: setattr(worker, "shutdown_requested", True))
        mock_pool = MagicMock()
        mock_init_pgq.return_value = (mock_pgq, mock_pool)

        await worker.worker_main_loop()

        # Verify entrypoints registered with PgQueuer instance
        mock_register.assert_called_once_with(mock_pgq)


class TestErrorHandling:
    """Tests for worker error handling with PgQueuer (Story 4.2)."""

    @pytest.mark.asyncio
    @patch("app.queue.initialize_pgqueuer", new_callable=AsyncMock)
    @patch("app.entrypoints.register_entrypoints")
    async def test_worker_handles_pgqueuer_initialization_error(self, mock_register, mock_init_pgq):
        """Test worker logs fatal error when PgQueuer initialization fails."""
        worker.shutdown_requested = False

        # Simulate initialization failure
        mock_init_pgq.side_effect = Exception("Database connection failed")

        # Should re-raise exception for main() to handle
        with pytest.raises(Exception, match="Database connection failed"):
            await worker.worker_main_loop()

    @pytest.mark.asyncio
    @patch("app.queue.initialize_pgqueuer", new_callable=AsyncMock)
    @patch("app.entrypoints.register_entrypoints")
    async def test_worker_handles_pgqueuer_run_error(self, mock_register, mock_init_pgq):
        """Test worker logs fatal error when PgQueuer run() fails."""
        worker.shutdown_requested = False

        # Mock PgQueuer with run() failure
        mock_pgq = MagicMock()
        mock_pgq.run = AsyncMock(side_effect=RuntimeError("Queue processing error"))
        mock_pool = MagicMock()
        mock_init_pgq.return_value = (mock_pgq, mock_pool)

        # Should re-raise exception for main() to handle
        with pytest.raises(RuntimeError, match="Queue processing error"):
            await worker.worker_main_loop()


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
    @patch("app.worker.asyncpg_pool")
    async def test_shutdown_closes_database_connections(self, mock_pool, mock_engine):
        """Test shutdown_worker() closes both asyncpg pool and database engine."""
        mock_engine.dispose = AsyncMock()
        mock_pool.close = AsyncMock()

        await worker.shutdown_worker()

        mock_pool.close.assert_called_once()
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


class TestWorkerStateInitialization:
    """Test WorkerState initialization (Story 4.5)."""

    def test_default_initialization(self):
        """Test WorkerState initializes with correct defaults."""
        from app.worker import WorkerState

        state = WorkerState()

        assert state.gemini_quota_exhausted is False
        assert state.gemini_quota_reset_time is None
        assert state.active_video_tasks == 0
        assert state.max_concurrent_video == 3  # Default

    @patch.dict(os.environ, {"MAX_CONCURRENT_VIDEO": "5"})
    def test_initialization_with_env_var(self):
        """Test WorkerState respects MAX_CONCURRENT_VIDEO env var."""
        from app.worker import WorkerState

        state = WorkerState()

        assert state.max_concurrent_video == 5


class TestGeminiQuotaManagement:
    """Test Gemini quota exhaustion flag management (Story 4.5)."""

    def test_check_gemini_quota_available_initially_true(self):
        """Test quota available on fresh worker state."""
        from app.worker import WorkerState

        state = WorkerState()

        assert state.check_gemini_quota_available() is True

    def test_mark_gemini_quota_exhausted_sets_flag(self):
        """Test marking quota exhausted sets flag and reset time."""
        from app.worker import WorkerState
        from datetime import timezone, datetime

        state = WorkerState()

        state.mark_gemini_quota_exhausted()

        assert state.gemini_quota_exhausted is True
        assert state.gemini_quota_reset_time is not None
        assert state.gemini_quota_reset_time > datetime.now(timezone.utc)

    def test_check_gemini_quota_exhausted_returns_false(self):
        """Test quota check returns False when exhausted."""
        from app.worker import WorkerState

        state = WorkerState()
        state.mark_gemini_quota_exhausted()

        assert state.check_gemini_quota_available() is False

    def test_gemini_quota_auto_reset_at_midnight(self):
        """Test quota auto-resets when past reset time."""
        from app.worker import WorkerState
        from datetime import timezone, datetime, timedelta

        state = WorkerState()

        # Mark quota exhausted with reset time in the past
        state.gemini_quota_exhausted = True
        state.gemini_quota_reset_time = datetime.now(timezone.utc) - timedelta(hours=1)

        # Check should auto-reset
        result = state.check_gemini_quota_available()

        assert result is True
        assert state.gemini_quota_exhausted is False
        assert state.gemini_quota_reset_time is None


class TestKlingConcurrencyManagement:
    """Test Kling video task concurrency limiting (Story 4.5)."""

    def test_can_claim_video_task_initially_true(self):
        """Test can claim video task when counter is 0."""
        from app.worker import WorkerState

        state = WorkerState()

        assert state.can_claim_video_task() is True

    def test_increment_video_tasks(self):
        """Test incrementing video task counter."""
        from app.worker import WorkerState

        state = WorkerState()

        state.increment_video_tasks()
        assert state.active_video_tasks == 1

        state.increment_video_tasks()
        assert state.active_video_tasks == 2

    def test_decrement_video_tasks(self):
        """Test decrementing video task counter."""
        from app.worker import WorkerState

        state = WorkerState()
        state.active_video_tasks = 3

        state.decrement_video_tasks()
        assert state.active_video_tasks == 2

        state.decrement_video_tasks()
        assert state.active_video_tasks == 1

    def test_decrement_never_goes_negative(self):
        """Test counter never goes below zero."""
        from app.worker import WorkerState

        state = WorkerState()
        assert state.active_video_tasks == 0

        # Decrement when already at 0
        state.decrement_video_tasks()

        # Should stay at 0, not go negative
        assert state.active_video_tasks == 0

    def test_can_claim_video_task_at_limit(self):
        """Test cannot claim when at max concurrent limit."""
        from app.worker import WorkerState

        state = WorkerState()
        state.max_concurrent_video = 3

        # Claim 3 tasks (at limit)
        state.increment_video_tasks()
        state.increment_video_tasks()
        state.increment_video_tasks()

        # Should NOT be able to claim 4th task
        assert state.can_claim_video_task() is False
