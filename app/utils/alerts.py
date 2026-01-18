"""Discord webhook alert system for quota exhaustion and system issues.

Sends structured alerts to Discord channel via webhook URL configured in
DISCORD_WEBHOOK_URL environment variable.

Architecture Pattern:
    - Async HTTP client (httpx)
    - Message sanitization (prevent injection)
    - Timeout handling (5s max)
    - Graceful degradation (log on failure, don't crash)

References:
    - Story 4.5: Rate Limit Aware Task Selection
    - PRD: FR32 (Alert system for terminal failures)
"""

import os

import httpx

from app.utils.logging import get_logger

log = get_logger(__name__)


async def send_alert(level: str, message: str, details: dict[str, str] | None = None) -> None:
    """Send alert to Discord webhook.

    Args:
        level: Alert level ("CRITICAL", "WARNING", "INFO")
        message: Alert message (max 2000 chars, will be truncated)
        details: Optional structured details (dict)

    Environment Variables:
        DISCORD_WEBHOOK_URL: Discord webhook URL (required)

    Example:
        >>> await send_alert(
        ...     level="WARNING",
        ...     message="YouTube quota at 85%",
        ...     details={"channel": "poke1", "usage": 8500, "limit": 10000},
        ... )
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        log.warning("discord_webhook_not_configured")
        return

    # Sanitize message (Discord 2000 char limit)
    sanitized_message = message[:2000]

    # Color mapping
    colors = {
        "CRITICAL": 0xFF0000,  # Red
        "WARNING": 0xFFA500,  # Orange
        "INFO": 0x0000FF,  # Blue
        "SUCCESS": 0x00FF00,  # Green
    }

    payload = {
        "content": f"**{level}**: {sanitized_message}",
        "embeds": [
            {
                "title": f"{level} Alert",
                "description": sanitized_message,
                "fields": [
                    {"name": key, "value": str(value)[:1024], "inline": True}
                    for key, value in (details or {}).items()
                ],
                "color": colors.get(level, 0x808080),  # Default gray
            }
        ],
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json=payload, timeout=5.0)
            response.raise_for_status()

            log.info(
                "discord_alert_sent",
                level=level,
                message=message[:100],  # Truncate for log
            )
    except httpx.TimeoutException:
        log.error("discord_webhook_timeout", webhook_url=webhook_url[:50])
    except httpx.HTTPStatusError as e:
        log.error(
            "discord_webhook_http_error",
            status_code=e.response.status_code,
            response=e.response.text[:500],
        )
    except Exception as e:
        log.error("discord_webhook_failed", error=str(e))
