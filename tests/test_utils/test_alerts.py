"""Tests for Discord webhook alert system (Story 4.5).

Tests cover:
    - send_alert: Discord webhook integration
    - Message sanitization (2000 char limit)
    - Alert levels (CRITICAL, WARNING, INFO, SUCCESS)
    - Graceful degradation (log on failure, don't crash)
    - Timeout handling (5s max)

References:
    - Story 4.5: Rate Limit Aware Task Selection
    - FR32: Alert system for terminal failures
"""

import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.utils.alerts import send_alert


@pytest.fixture
def mock_webhook_url(monkeypatch):
    """Mock DISCORD_WEBHOOK_URL environment variable."""
    webhook_url = "https://discord.com/api/webhooks/test/webhook"
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", webhook_url)
    return webhook_url


@pytest.fixture
def no_webhook_url(monkeypatch):
    """Remove DISCORD_WEBHOOK_URL environment variable."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)


class TestSendAlert:
    """Test send_alert function."""

    @pytest.mark.asyncio
    async def test_send_critical_alert(self, mock_webhook_url):
        """Scenario 1: Send CRITICAL alert with details."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 204
            mock_post.return_value = mock_response

            await send_alert(
                level="CRITICAL",
                message="YouTube quota exhausted",
                details={
                    "channel_id": "poke1",
                    "usage": 10600,
                    "limit": 10000,
                },
            )

            # Verify webhook called
            mock_post.assert_called_once()
            call_args = mock_post.call_args

            # Verify URL
            assert call_args[0][0] == mock_webhook_url

            # Verify payload structure
            payload = call_args[1]["json"]
            assert "CRITICAL" in payload["content"]
            assert "YouTube quota exhausted" in payload["content"]
            assert payload["embeds"][0]["color"] == 0xFF0000  # Red
            assert len(payload["embeds"][0]["fields"]) == 3  # 3 detail fields

    @pytest.mark.asyncio
    async def test_send_warning_alert(self, mock_webhook_url):
        """Scenario 2: Send WARNING alert."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 204
            mock_post.return_value = mock_response

            await send_alert(
                level="WARNING",
                message="YouTube quota at 85%",
            )

            payload = mock_post.call_args[1]["json"]
            assert "WARNING" in payload["content"]
            assert payload["embeds"][0]["color"] == 0xFFA500  # Orange

    @pytest.mark.asyncio
    async def test_send_info_alert(self, mock_webhook_url):
        """Scenario 3: Send INFO alert."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 204
            mock_post.return_value = mock_response

            await send_alert(
                level="INFO",
                message="Task processing started",
            )

            payload = mock_post.call_args[1]["json"]
            assert payload["embeds"][0]["color"] == 0x0000FF  # Blue

    @pytest.mark.asyncio
    async def test_send_success_alert(self, mock_webhook_url):
        """Scenario 4: Send SUCCESS alert."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 204
            mock_post.return_value = mock_response

            await send_alert(
                level="SUCCESS",
                message="Video uploaded successfully",
            )

            payload = mock_post.call_args[1]["json"]
            assert payload["embeds"][0]["color"] == 0x00FF00  # Green

    @pytest.mark.asyncio
    async def test_message_truncation_at_2000_chars(self, mock_webhook_url):
        """Scenario 5: Message truncated to 2000 characters (Discord limit)."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 204
            mock_post.return_value = mock_response

            # Create message longer than 2000 chars
            long_message = "X" * 3000

            await send_alert(level="INFO", message=long_message)

            payload = mock_post.call_args[1]["json"]
            # Message should be truncated to 2000 chars
            assert len(payload["embeds"][0]["description"]) == 2000
            assert payload["embeds"][0]["description"] == "X" * 2000

    @pytest.mark.asyncio
    async def test_no_webhook_url_logs_warning(self, no_webhook_url, caplog):
        """Scenario 6: Missing DISCORD_WEBHOOK_URL logs warning and returns gracefully."""
        await send_alert(level="CRITICAL", message="Test alert")

        # Should log warning about missing webhook
        assert "discord_webhook_not_configured" in caplog.text

    @pytest.mark.asyncio
    async def test_timeout_handled_gracefully(self, mock_webhook_url, caplog):
        """Scenario 7: Webhook timeout handled gracefully (5s timeout)."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            # Simulate timeout
            mock_post.side_effect = httpx.TimeoutException("Request timeout")

            # Should not raise exception
            await send_alert(level="CRITICAL", message="Test alert")

            # Should log error
            assert "discord_webhook_timeout" in caplog.text

    @pytest.mark.asyncio
    async def test_http_error_handled_gracefully(self, mock_webhook_url, caplog):
        """Scenario 8: HTTP error handled gracefully."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            # Simulate HTTP error
            from unittest.mock import MagicMock

            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Bad Request"
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Bad Request",
                request=MagicMock(),
                response=mock_response,
            )
            mock_post.return_value = mock_response

            # Should not raise exception
            await send_alert(level="CRITICAL", message="Test alert")

            # Should log error
            assert "discord_webhook_http_error" in caplog.text

    @pytest.mark.asyncio
    async def test_generic_exception_handled_gracefully(self, mock_webhook_url, caplog):
        """Scenario 9: Generic exception handled gracefully."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            # Simulate generic exception
            mock_post.side_effect = Exception("Unexpected error")

            # Should not raise exception
            await send_alert(level="CRITICAL", message="Test alert")

            # Should log error
            assert "discord_webhook_failed" in caplog.text

    @pytest.mark.asyncio
    async def test_details_field_truncation(self, mock_webhook_url):
        """Scenario 10: Detail field values truncated to 1024 characters (Discord embed field limit)."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 204
            mock_post.return_value = mock_response

            # Create detail value longer than 1024 chars
            long_value = "Y" * 2000

            await send_alert(
                level="INFO",
                message="Test",
                details={"long_field": long_value},
            )

            payload = mock_post.call_args[1]["json"]
            field_value = payload["embeds"][0]["fields"][0]["value"]

            # Field value should be truncated to 1024 chars
            assert len(field_value) == 1024
            assert field_value == "Y" * 1024
