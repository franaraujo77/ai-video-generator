"""
Integration tests for alert system with retry orchestrator and quota monitoring.

Tests cover:
- Terminal failure → Discord alert integration (3 tests)
- Retry orchestration → alert integration (2 tests)
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from uuid import uuid4

from app.models import Task, TaskStatus
from app.services.retry_orchestrator import schedule_retry, _handle_terminal_failure
from app.services.error_classifier import ErrorAnalysis, ErrorCategory, ErrorContext
from tests.support.factories import create_task


@pytest.fixture
def mock_discord_webhook():
    """Mock Discord webhook POST for alert tests."""
    with patch("app.services.alert_service.httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None  # Synchronous method

        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock()
        mock_instance.post = AsyncMock(return_value=mock_response)

        mock_client.return_value = mock_instance
        yield mock_instance


# =============================================================================
# Terminal Failure → Discord Alert Integration Tests (3 tests)
# =============================================================================


@pytest.mark.asyncio
async def test_handle_terminal_failure_sends_alert(async_session, mock_discord_webhook):
    """Verify terminal failure triggers Discord alert with rich context."""
    task = create_task(channel_id="poke1", retry_count=5, status=TaskStatus.VIDEO_ERROR)
    async_session.add(task)
    await async_session.commit()

    error_analysis = ErrorAnalysis(
        category=ErrorCategory.PERMANENT,
        http_status_code=401,
        error_type="API_AUTHENTICATION",
        error_message="Invalid API key for Kling video generation",
        retry_recommended=False,
        confidence=0.95,
        suggested_action="Verify KLING_API_KEY environment variable is set correctly",
        api_service="kling",
    )

    context = ErrorContext(
        task_id=task.id,
        channel_id=task.channel_id,
        step_name="video_generation",
        clip_index=3,
        total_clips=18,
        asset_name="clip_003_haunter_phasing.mp4",
    )

    with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test"}):
        error_payload = await _handle_terminal_failure(task, error_analysis, async_session, context)
        await async_session.commit()

    # Verify alert sent
    assert mock_discord_webhook.post.called
    payload = mock_discord_webhook.post.call_args.kwargs["json"]
    embed = payload["embeds"][0]

    # Verify alert content
    assert "Task Failed Permanently" in embed["title"]
    assert "video_error" in embed["title"]  # TaskStatus.value returns lowercase
    assert "Invalid API key" in embed["description"]
    assert embed["color"] == 0xE74C3C  # CRITICAL red

    # Verify fields
    fields = {field["name"]: field["value"] for field in embed["fields"]}
    assert str(task.id) == fields["Task ID"]
    assert str(task.channel_id) == fields["Channel"]  # Channel field contains UUID FK
    assert fields["Failed Step"] == "video_generation"
    assert fields["Error Type"] == "permanent"  # ErrorCategory.value returns lowercase


@pytest.mark.asyncio
async def test_handle_terminal_failure_no_webhook_logs_warning(async_session):
    """Verify terminal failure logs warning when webhook not configured."""
    task = create_task(channel_id="poke1", retry_count=5, status=TaskStatus.ASSET_ERROR)
    async_session.add(task)
    await async_session.commit()

    error_analysis = ErrorAnalysis(
        category=ErrorCategory.PERMANENT,
        http_status_code=429,
        error_type="API_QUOTA_EXCEEDED",
        error_message="Gemini API quota exhausted",
        retry_recommended=False,
        confidence=0.99,
        suggested_action="Wait until quota resets at midnight PST",
        api_service="gemini",
    )

    # No DISCORD_WEBHOOK_URL configured
    with patch.dict("os.environ", {}, clear=True):
        error_payload = await _handle_terminal_failure(task, error_analysis, async_session, None)
        await async_session.commit()

    # Verify task updated but no crash
    assert task.retry_count == 5
    assert error_payload is not None
    assert error_payload.error_category == "permanent"  # Lowercase from ErrorCategory.value


@pytest.mark.asyncio
async def test_terminal_failure_alert_includes_recommendation(async_session, mock_discord_webhook):
    """Verify terminal failure alert includes actionable recommendation."""
    task = create_task(channel_id="poke2", retry_count=5, status=TaskStatus.AUDIO_ERROR)
    async_session.add(task)
    await async_session.commit()

    error_analysis = ErrorAnalysis(
        category=ErrorCategory.PERMANENT,
        http_status_code=401,
        error_type="AUTHENTICATION_ERROR",
        error_message="ElevenLabs API key invalid",
        retry_recommended=False,
        confidence=0.98,
        suggested_action="Update ELEVENLABS_API_KEY in Railway environment variables",
        api_service="elevenlabs",
    )

    with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test"}):
        await _handle_terminal_failure(task, error_analysis, async_session, None)
        await async_session.commit()

    # Verify recommendation in alert
    payload = mock_discord_webhook.post.call_args.kwargs["json"]
    embed = payload["embeds"][0]

    assert "Update ELEVENLABS_API_KEY" in embed["description"]
    assert "Recommendation" in embed["description"]


# =============================================================================
# Retry Orchestration → Alert Integration Tests (2 tests)
# =============================================================================


@pytest.mark.asyncio
async def test_schedule_retry_no_alert_for_transient_error(async_session, mock_discord_webhook):
    """Verify transient errors DO NOT trigger alerts (retries handle them)."""
    task = create_task(channel_id="poke1", retry_count=0, status=TaskStatus.VIDEO_ERROR)
    async_session.add(task)
    await async_session.commit()

    # Simulate transient network error
    exception = TimeoutError("Kling API request timed out after 30 seconds")

    with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test"}):
        with patch("app.services.retry_orchestrator.classify_error") as mock_classify:
            mock_classify.return_value = ErrorAnalysis(
                category=ErrorCategory.TRANSIENT,
                http_status_code=None,
                error_type="NETWORK_TIMEOUT",
                error_message="Request timeout",
                retry_recommended=True,
                confidence=0.90,
                suggested_action="Retry automatically",
                api_service="kling",
            )

            error_payload = await schedule_retry(task.id, exception, async_session, None)
            await async_session.commit()

    # Verify NO alert sent (transient errors handled by retry)
    assert not mock_discord_webhook.post.called

    # Verify retry scheduled
    assert task.retry_count == 1
    assert task.next_retry_at is not None


@pytest.mark.asyncio
async def test_schedule_retry_alerts_on_permanent_error(async_session, mock_discord_webhook):
    """Verify permanent errors trigger immediate alert (no retry)."""
    task = create_task(channel_id="poke1", retry_count=0, status=TaskStatus.ASSET_ERROR)
    async_session.add(task)
    await async_session.commit()

    # Simulate permanent authentication error
    exception = ValueError("Invalid API key")

    with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/test"}):
        with patch("app.services.retry_orchestrator.classify_error") as mock_classify:
            mock_classify.return_value = ErrorAnalysis(
                category=ErrorCategory.PERMANENT,
                http_status_code=401,
                error_type="API_AUTHENTICATION",
                error_message="Invalid API key for Gemini",
                retry_recommended=False,
                confidence=0.99,
                suggested_action="Check GEMINI_API_KEY environment variable",
                api_service="gemini",
            )

            error_payload = await schedule_retry(task.id, exception, async_session, None)
            await async_session.commit()

    # Verify alert sent (permanent error)
    assert mock_discord_webhook.post.called

    # Verify terminal failure recorded
    assert task.retry_count == 5  # MAX_RETRY_ATTEMPTS
    assert task.next_retry_at is None  # No more retries
