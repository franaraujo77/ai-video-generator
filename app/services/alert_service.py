"""Discord webhook alert service for operational monitoring.

This service provides standardized alerting for terminal failures, quota
exhaustion, and other operational events requiring human attention.

Integration:
- Story 6.1: Only alerts for permanent errors or exhausted retries
- Story 6.2: Integrates with handle_terminal_failure() after retry exhaustion
- Story 6.4: Uses ErrorPayload for alert message formatting
- Story 6.5: Logs alert delivery using structlog for Railway observability
"""

import os
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import httpx
import structlog

log = structlog.get_logger()

AlertSeverity = Literal["INFO", "WARNING", "CRITICAL"]
AlertType = Literal[
    "terminal_failure", "quota_warning", "quota_exhausted", "worker_down", "low_recovery_rate"
]

# In-memory alert batching tracker
_alert_history: dict[tuple[str, str], datetime] = {}


def should_send_alert(alert_type: str, channel_id: str, force: bool = False) -> bool:
    """Determine if alert should be sent based on batching rules.

    Args:
        alert_type: Type of alert (for deduplication)
        channel_id: Channel ID (scope batching per channel)
        force: If True, bypass batching (for CRITICAL alerts)

    Returns:
        bool: True if alert should be sent, False if suppressed
    """
    # Allow batching to be disabled via env var
    batching_enabled = os.getenv("ALERT_ENABLE_BATCHING", "true").lower() == "true"
    if not batching_enabled or force:
        return True

    batch_window = int(os.getenv("ALERT_BATCH_WINDOW_SECONDS", "60"))
    key = (alert_type, channel_id)
    now = datetime.now(UTC)

    if key in _alert_history:
        elapsed = (now - _alert_history[key]).total_seconds()
        if elapsed < batch_window:
            # Suppress duplicate alert
            log.info(
                "alert_suppressed",
                alert_type=alert_type,
                channel_id=channel_id,
                elapsed_seconds=elapsed,
                batch_window_seconds=batch_window,
            )
            return False

    # Update history and allow alert
    _alert_history[key] = now
    return True


async def send_discord_alert(
    alert_type: AlertType,
    severity: AlertSeverity,
    title: str,
    description: str,
    fields: dict[str, str],
    webhook_url: str,
    correlation_id: UUID | None = None,
) -> bool:
    """Send alert to Discord via webhook.

    Args:
        alert_type: Type of alert (for batching key)
        severity: Alert severity level
        title: Alert title (shown in Discord notification)
        description: Alert description (main message body)
        fields: Key-value pairs shown as Discord embed fields
        webhook_url: Discord webhook URL from environment
        correlation_id: Optional correlation ID for tracing

    Returns:
        bool: True if delivery succeeded, False if failed

    Raises:
        None: All exceptions caught and logged, never crashes
    """
    try:
        # Map severity to Discord embed color
        color_map = {
            "INFO": 0x3498DB,  # Blue
            "WARNING": 0xF39C12,  # Orange
            "CRITICAL": 0xE74C3C,  # Red
        }

        # Build Discord embed
        severity_emoji = {
            "INFO": "🔵",
            "WARNING": "⚠️",
            "CRITICAL": "🔴",
        }
        embed = {
            "title": f"{severity_emoji[severity]} {title}",
            "description": description,
            "color": color_map[severity],
            "fields": [
                {"name": key, "value": value, "inline": True} for key, value in fields.items()
            ],
            "footer": {"text": f"Alert Type: {alert_type} | {datetime.now(UTC).isoformat()}"},
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Add correlation ID to footer if provided
        if correlation_id:
            embed["footer"]["text"] += f" | Correlation ID: {correlation_id}"

        payload = {"embeds": [embed], "username": "AI Video Generator Alerts"}

        # Non-blocking webhook POST with 10 second timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()

        # Log successful delivery
        log.info(
            "alert_sent",
            alert_type=alert_type,
            severity=severity,
            title=title,
            correlation_id=str(correlation_id) if correlation_id else None,
            webhook_response_status=response.status_code,
        )

        return True

    except httpx.HTTPError as e:
        # Log failure but don't crash
        log.error(
            "alert_failed",
            alert_type=alert_type,
            severity=severity,
            error=str(e),
            correlation_id=str(correlation_id) if correlation_id else None,
            exc_info=True,
        )
        return False

    except Exception as e:
        # Catch-all for unexpected errors
        log.critical(
            "alert_system_error",
            alert_type=alert_type,
            error=str(e),
            correlation_id=str(correlation_id) if correlation_id else None,
            exc_info=True,
        )
        return False


async def send_alert_with_batching(
    alert_type: AlertType,
    severity: AlertSeverity,
    title: str,
    description: str,
    fields: dict[str, str],
    webhook_url: str,
    channel_id: str,
    correlation_id: UUID | None = None,
    force: bool = False,
) -> bool:
    """Send alert with automatic batching/rate limiting.

    Args:
        alert_type: Type of alert (for batching key)
        severity: Alert severity level
        title: Alert title
        description: Alert description
        fields: Discord embed fields
        webhook_url: Discord webhook URL
        channel_id: Channel ID (scope batching per channel)
        correlation_id: Optional correlation ID for tracing
        force: If True, bypass batching (for CRITICAL alerts)

    Returns:
        bool: True if alert sent, False if suppressed or failed
    """
    if not should_send_alert(alert_type, channel_id, force=force):
        return False  # Suppressed

    return await send_discord_alert(
        alert_type, severity, title, description, fields, webhook_url, correlation_id
    )


async def send_terminal_failure_alert(
    task_id: UUID,
    task_title: str,
    channel_id: str,
    failed_step: str,
    error_type: str,
    error_message: str,
    retry_count: int,
    correlation_id: UUID,
    recommendation: str | None = None,
    notion_url: str | None = None,
) -> bool:
    """Send terminal failure alert to Discord.

    Args:
        task_id: Task UUID
        task_title: Human-readable task title
        channel_id: Channel ID
        failed_step: Step name that failed
        error_type: Error category
        error_message: Error message
        retry_count: Number of retry attempts
        correlation_id: Correlation ID for tracing
        recommendation: Optional recommended action
        notion_url: Optional Notion page URL

    Returns:
        bool: True if alert sent, False otherwise
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        log.warning(
            "discord_webhook_not_configured",
            message="Terminal failure alert not sent - DISCORD_WEBHOOK_URL not set",
        )
        return False

    description = (
        f"Task **{task_title}** failed after **{retry_count}** retry attempts. "
        f"Human intervention required.\n\n"
        f"**Error:** {error_message}\n"
        f"**Step:** {failed_step}\n"
    )

    if recommendation:
        description += f"**Recommendation:** {recommendation}\n"

    if notion_url:
        description += f"\n[View in Notion]({notion_url})"

    fields = {
        "Task ID": str(task_id),
        "Channel": str(channel_id),  # Convert UUID to string
        "Failed Step": failed_step,
        "Error Type": error_type,
        "Retry Attempts": str(retry_count),
        "Correlation ID": str(correlation_id),
    }

    return await send_alert_with_batching(
        alert_type="terminal_failure",
        severity="CRITICAL",
        title=f"Task Failed Permanently: {task_title}",
        description=description,
        fields=fields,
        webhook_url=webhook_url,
        channel_id=channel_id,
        correlation_id=correlation_id,
        force=True,  # CRITICAL alerts bypass batching
    )


async def send_quota_alert(
    channel_id: str, current_usage: int, daily_limit: int, is_exhausted: bool = False
) -> bool:
    """Send YouTube quota alert to Discord.

    Args:
        channel_id: YouTube channel ID
        current_usage: Current quota units used today
        daily_limit: Daily quota limit (typically 10,000)
        is_exhausted: True if 100% threshold reached

    Returns:
        bool: True if alert sent, False otherwise
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        log.warning(
            "discord_webhook_not_configured",
            message="Quota alert not sent - DISCORD_WEBHOOK_URL not set",
        )
        return False

    usage_percent = (current_usage / daily_limit) * 100

    if is_exhausted:
        # CRITICAL: Quota exhausted (100%)
        return await send_alert_with_batching(
            alert_type="quota_exhausted",
            severity="CRITICAL",
            title=f"YouTube Quota Exhausted: {channel_id}",
            description=(
                f"**Channel {channel_id} has exhausted its YouTube API quota.**\n\n"
                f"All upload tasks for this channel are paused until midnight PST reset.\n\n"
                f"Current Usage: {current_usage:,} / {daily_limit:,} units ({usage_percent:.1f}%)"
            ),
            fields={
                "Channel": channel_id,
                "Usage": f"{current_usage:,} / {daily_limit:,} units",
                "Percentage": f"{usage_percent:.1f}%",
                "Reset Time": "Midnight PST (8AM UTC)",
                "Action": "Uploads paused",
            },
            webhook_url=webhook_url,
            channel_id=channel_id,
            force=True,  # CRITICAL
        )
    else:
        # WARNING: Approaching limit (80%)
        return await send_alert_with_batching(
            alert_type="quota_warning",
            severity="WARNING",
            title=f"YouTube Quota Warning: {channel_id}",
            description=(
                f"**Channel {channel_id} approaching YouTube API quota limit.**\n\n"
                f"Current Usage: {current_usage:,} / {daily_limit:,} units "
                f"({usage_percent:.1f}%)\n\n"
                f"Consider prioritizing high-value uploads."
            ),
            fields={
                "Channel": channel_id,
                "Usage": f"{current_usage:,} / {daily_limit:,} units",
                "Percentage": f"{usage_percent:.1f}%",
                "Remaining": f"{daily_limit - current_usage:,} units",
                "Reset Time": "Midnight PST (8AM UTC)",
            },
            webhook_url=webhook_url,
            channel_id=channel_id,
            force=False,  # Allow batching
        )
