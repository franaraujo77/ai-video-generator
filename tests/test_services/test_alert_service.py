"""
Tests for Discord webhook alert service.

Tests cover:
- Discord webhook delivery (5 tests)
- Alert batching/rate limiting (5 tests)
- Terminal failure alerts (3 tests)
- YouTube quota alerts (3 tests)
- Error handling (3 tests)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta, UTC
from uuid import uuid4
import httpx

from app.services.alert_service import (
    send_discord_alert,
    send_alert_with_batching,
    send_terminal_failure_alert,
    send_quota_alert,
    should_send_alert,
    _alert_history,
)


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for Discord webhook calls."""
    with patch("app.services.alert_service.httpx.AsyncClient") as mock_client:
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock()
        mock_instance.post = AsyncMock(return_value=mock_response)

        mock_client.return_value = mock_instance
        yield mock_instance


@pytest.fixture(autouse=True)
def reset_alert_history():
    """Reset alert history between tests."""
    _alert_history.clear()
    yield
    _alert_history.clear()


# =============================================================================
# Discord Webhook Delivery Tests (5 tests)
# =============================================================================


@pytest.mark.asyncio
async def test_send_discord_alert_formats_embed_correctly(mock_httpx_client):
    """Verify Discord embed formatting with all fields."""
    webhook_url = "https://discord.com/api/webhooks/test"
    correlation_id = uuid4()

    result = await send_discord_alert(
        alert_type="terminal_failure",
        severity="CRITICAL",
        title="Task Failed",
        description="Task failed after 3 retries",
        fields={"Task ID": "abc-123", "Channel": "poke1"},
        webhook_url=webhook_url,
        correlation_id=correlation_id,
    )

    assert result is True
    assert mock_httpx_client.post.called

    # Verify embed structure
    call_args = mock_httpx_client.post.call_args
    payload = call_args.kwargs["json"]
    embed = payload["embeds"][0]

    assert "🔴" in embed["title"]  # CRITICAL emoji
    assert "Task Failed" in embed["title"]
    assert embed["color"] == 0xE74C3C  # Red color
    assert embed["description"] == "Task failed after 3 retries"
    assert len(embed["fields"]) == 2
    assert embed["fields"][0]["name"] == "Task ID"
    assert embed["fields"][0]["value"] == "abc-123"
    assert "terminal_failure" in embed["footer"]["text"]
    assert str(correlation_id) in embed["footer"]["text"]


@pytest.mark.asyncio
async def test_send_discord_alert_severity_colors(mock_httpx_client):
    """Verify severity maps to correct Discord embed colors and emojis."""
    webhook_url = "https://discord.com/api/webhooks/test"

    # Test CRITICAL (Red, 🔴)
    await send_discord_alert(
        alert_type="terminal_failure",
        severity="CRITICAL",
        title="Critical Alert",
        description="Critical issue",
        fields={},
        webhook_url=webhook_url,
    )
    payload = mock_httpx_client.post.call_args.kwargs["json"]
    assert payload["embeds"][0]["color"] == 0xE74C3C  # Red
    assert "🔴" in payload["embeds"][0]["title"]

    # Test WARNING (Orange, ⚠️)
    await send_discord_alert(
        alert_type="quota_warning",
        severity="WARNING",
        title="Warning Alert",
        description="Warning issue",
        fields={},
        webhook_url=webhook_url,
    )
    payload = mock_httpx_client.post.call_args.kwargs["json"]
    assert payload["embeds"][0]["color"] == 0xF39C12  # Orange
    assert "⚠️" in payload["embeds"][0]["title"]

    # Test INFO (Blue, blue circle emoji)
    await send_discord_alert(
        alert_type="worker_down",
        severity="INFO",
        title="Info Alert",
        description="Info issue",
        fields={},
        webhook_url=webhook_url,
    )
    payload = mock_httpx_client.post.call_args.kwargs["json"]
    assert payload["embeds"][0]["color"] == 0x3498DB  # Blue
    assert "🔵" in payload["embeds"][0]["title"]


@pytest.mark.asyncio
async def test_send_discord_alert_webhook_delivery_success(mock_httpx_client):
    """Verify successful webhook delivery returns True."""
    webhook_url = "https://discord.com/api/webhooks/test"

    result = await send_discord_alert(
        alert_type="terminal_failure",
        severity="CRITICAL",
        title="Test Alert",
        description="Test description",
        fields={},
        webhook_url=webhook_url,
    )

    assert result is True
    mock_httpx_client.post.assert_called_once()
    call_args = mock_httpx_client.post.call_args
    assert call_args.args[0] == webhook_url


@pytest.mark.asyncio
async def test_send_discord_alert_webhook_http_error():
    """Verify HTTP errors are handled gracefully and logged."""
    webhook_url = "https://discord.com/api/webhooks/test"

    with patch("app.services.alert_service.httpx.AsyncClient") as mock_client:
        mock_instance = MagicMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock()
        mock_instance.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Bad Request", request=MagicMock(), response=MagicMock(status_code=400)
            )
        )
        mock_client.return_value = mock_instance

        result = await send_discord_alert(
            alert_type="terminal_failure",
            severity="CRITICAL",
            title="Test Alert",
            description="Test",
            fields={},
            webhook_url=webhook_url,
        )

        assert result is False  # Delivery failed


@pytest.mark.asyncio
async def test_send_discord_alert_unexpected_exception():
    """Verify unexpected exceptions are caught and logged."""
    webhook_url = "https://discord.com/api/webhooks/test"

    with patch("app.services.alert_service.httpx.AsyncClient") as mock_client:
        mock_client.side_effect = ValueError("Unexpected error")

        result = await send_discord_alert(
            alert_type="terminal_failure",
            severity="CRITICAL",
            title="Test Alert",
            description="Test",
            fields={},
            webhook_url=webhook_url,
        )

        assert result is False  # System error caught


# =============================================================================
# Alert Batching Tests (5 tests)
# =============================================================================


def test_should_send_alert_allows_first_alert():
    """Verify first alert is always allowed."""
    result = should_send_alert("terminal_failure", "poke1", force=False)
    assert result is True


def test_should_send_alert_suppresses_duplicate_within_window():
    """Verify duplicate alerts within 60 seconds are suppressed."""
    # First alert allowed
    result1 = should_send_alert("terminal_failure", "poke1", force=False)
    assert result1 is True

    # Second alert (duplicate) suppressed
    result2 = should_send_alert("terminal_failure", "poke1", force=False)
    assert result2 is False


def test_should_send_alert_allows_after_batch_window():
    """Verify alerts allowed after batch window expires."""
    alert_type = "terminal_failure"
    channel_id = "poke1"

    # First alert
    should_send_alert(alert_type, channel_id, force=False)

    # Manually expire the batch window
    _alert_history[(alert_type, channel_id)] = datetime.now(UTC) - timedelta(seconds=61)

    # Second alert after window should be allowed
    result = should_send_alert(alert_type, channel_id, force=False)
    assert result is True


def test_should_send_alert_force_bypasses_batching():
    """Verify force=True bypasses batching."""
    # First alert
    should_send_alert("terminal_failure", "poke1", force=False)

    # Second alert with force=True should bypass
    result = should_send_alert("terminal_failure", "poke1", force=True)
    assert result is True


def test_should_send_alert_scoped_per_channel_and_type():
    """Verify batching is scoped per (alert_type, channel_id)."""
    # Same type, different channels
    result1 = should_send_alert("terminal_failure", "poke1", force=False)
    result2 = should_send_alert("terminal_failure", "poke2", force=False)
    assert result1 is True
    assert result2 is True

    # Different types, same channel
    result3 = should_send_alert("terminal_failure", "poke1", force=False)
    result4 = should_send_alert("quota_warning", "poke1", force=False)
    assert result3 is False  # Duplicate
    assert result4 is True  # Different type


# =============================================================================
# Alert Batching Integration Tests (2 tests)
# =============================================================================


@pytest.mark.asyncio
async def test_send_alert_with_batching_suppresses_duplicates(mock_httpx_client):
    """Verify send_alert_with_batching respects batching rules."""
    webhook_url = "https://discord.com/api/webhooks/test"

    # First alert should send
    result1 = await send_alert_with_batching(
        alert_type="terminal_failure",
        severity="CRITICAL",
        title="Task Failed",
        description="First failure",
        fields={},
        webhook_url=webhook_url,
        channel_id="poke1",
        force=False,
    )
    assert result1 is True
    assert mock_httpx_client.post.call_count == 1

    # Second alert (duplicate) should be suppressed
    result2 = await send_alert_with_batching(
        alert_type="terminal_failure",
        severity="CRITICAL",
        title="Task Failed",
        description="Second failure",
        fields={},
        webhook_url=webhook_url,
        channel_id="poke1",
        force=False,
    )
    assert result2 is False  # Suppressed
    assert mock_httpx_client.post.call_count == 1  # No additional call


@pytest.mark.asyncio
async def test_send_alert_with_batching_env_var_disable(mock_httpx_client):
    """Verify batching can be disabled via environment variable."""
    webhook_url = "https://discord.com/api/webhooks/test"

    with patch.dict("os.environ", {"ALERT_ENABLE_BATCHING": "false"}):
        # First alert
        result1 = await send_alert_with_batching(
            alert_type="terminal_failure",
            severity="CRITICAL",
            title="Task Failed",
            description="First failure",
            fields={},
            webhook_url=webhook_url,
            channel_id="poke1",
            force=False,
        )
        assert result1 is True

        # Second alert should also send (batching disabled)
        result2 = await send_alert_with_batching(
            alert_type="terminal_failure",
            severity="CRITICAL",
            title="Task Failed",
            description="Second failure",
            fields={},
            webhook_url=webhook_url,
            channel_id="poke1",
            force=False,
        )
        assert result2 is True
        assert mock_httpx_client.post.call_count == 2


# =============================================================================
# Terminal Failure Alert Tests (3 tests)
# =============================================================================


@pytest.mark.asyncio
async def test_send_terminal_failure_alert_success(mock_httpx_client):
    """Verify terminal failure alert formatting and delivery."""
    task_id = uuid4()
    correlation_id = uuid4()

    with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://webhook.url"}):
        result = await send_terminal_failure_alert(
            task_id=task_id,
            task_title="Generate Bulbasaur Video",
            channel_id="poke1",
            failed_step="video_generation",
            error_type="PERMANENT",
            error_message="Invalid API key",
            retry_count=3,
            correlation_id=correlation_id,
            recommendation="Check API credentials",
            notion_url="https://notion.so/page123",
        )

    assert result is True
    assert mock_httpx_client.post.called

    payload = mock_httpx_client.post.call_args.kwargs["json"]
    embed = payload["embeds"][0]

    assert "Task Failed Permanently" in embed["title"]
    assert "Generate Bulbasaur Video" in embed["title"]
    assert "Invalid API key" in embed["description"]
    assert "video_generation" in embed["description"]
    assert "Check API credentials" in embed["description"]
    assert "https://notion.so/page123" in embed["description"]
    assert embed["color"] == 0xE74C3C  # CRITICAL red


@pytest.mark.asyncio
async def test_send_terminal_failure_alert_no_webhook_configured():
    """Verify terminal failure alert logs warning when webhook not configured."""
    with patch.dict("os.environ", {}, clear=True):
        result = await send_terminal_failure_alert(
            task_id=uuid4(),
            task_title="Test Task",
            channel_id="poke1",
            failed_step="video_generation",
            error_type="PERMANENT",
            error_message="Error",
            retry_count=3,
            correlation_id=uuid4(),
        )

    assert result is False  # Not sent


@pytest.mark.asyncio
async def test_send_terminal_failure_alert_forces_critical_bypass(mock_httpx_client):
    """Verify terminal failure alerts bypass batching (force=True)."""
    with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://webhook.url"}):
        # Send two identical terminal failure alerts
        result1 = await send_terminal_failure_alert(
            task_id=uuid4(),
            task_title="Test Task",
            channel_id="poke1",
            failed_step="video_generation",
            error_type="PERMANENT",
            error_message="Error",
            retry_count=3,
            correlation_id=uuid4(),
        )

        result2 = await send_terminal_failure_alert(
            task_id=uuid4(),
            task_title="Test Task",
            channel_id="poke1",
            failed_step="video_generation",
            error_type="PERMANENT",
            error_message="Error",
            retry_count=3,
            correlation_id=uuid4(),
        )

    # Both should send because force=True bypasses batching
    assert result1 is True
    assert result2 is True
    assert mock_httpx_client.post.call_count == 2


# =============================================================================
# YouTube Quota Alert Tests (3 tests)
# =============================================================================


@pytest.mark.asyncio
async def test_send_quota_alert_exhausted(mock_httpx_client):
    """Verify quota exhausted alert (100% threshold)."""
    with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://webhook.url"}):
        result = await send_quota_alert(
            channel_id="poke1", current_usage=10000, daily_limit=10000, is_exhausted=True
        )

    assert result is True
    payload = mock_httpx_client.post.call_args.kwargs["json"]
    embed = payload["embeds"][0]

    assert "YouTube Quota Exhausted" in embed["title"]
    assert "100.0%" in embed["description"]
    assert embed["color"] == 0xE74C3C  # CRITICAL red
    assert "Uploads paused" in str(embed["fields"])


@pytest.mark.asyncio
async def test_send_quota_alert_warning(mock_httpx_client):
    """Verify quota warning alert (80% threshold)."""
    with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://webhook.url"}):
        result = await send_quota_alert(
            channel_id="poke1", current_usage=8500, daily_limit=10000, is_exhausted=False
        )

    assert result is True
    payload = mock_httpx_client.post.call_args.kwargs["json"]
    embed = payload["embeds"][0]

    assert "YouTube Quota Warning" in embed["title"]
    assert "85.0%" in embed["description"]
    assert embed["color"] == 0xF39C12  # WARNING orange
    assert "1,500 units" in str(embed["fields"])  # Remaining


@pytest.mark.asyncio
async def test_send_quota_alert_no_webhook_configured():
    """Verify quota alert logs warning when webhook not configured."""
    with patch.dict("os.environ", {}, clear=True):
        result = await send_quota_alert(
            channel_id="poke1", current_usage=10000, daily_limit=10000, is_exhausted=True
        )

    assert result is False  # Not sent
