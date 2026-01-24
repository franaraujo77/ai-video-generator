# Story 6.6: Alert System for Terminal Failures

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **system operator**,
I want **alerts sent to Discord when retries are exhausted**,
So that **I'm notified of failures requiring human intervention** (FR32).

## Acceptance Criteria

**Given** a task exhausts all retry attempts
**When** the terminal failure is recorded
**Then** a Discord webhook is triggered within 5 minutes (NFR-R5)
**And** the alert includes: task_id, channel, step, error summary

**Given** YouTube quota is exhausted
**When** the 100% threshold is reached
**Then** an alert is sent immediately
**And** the alert includes quota usage details

**Given** multiple failures occur rapidly
**When** alerts are sent
**Then** alerts are batched (not spammed) - max 1 per minute per error type

**Given** the system is configured with `DISCORD_WEBHOOK_URL`
**When** an alert is triggered
**Then** the `send_alert()` function posts to Discord
**And** alert delivery is logged

## Tasks / Subtasks

- [x] Task 1: Create Discord webhook integration service (AC: Alerts sent to Discord)
  - [x] Subtask 1.1: Create app/services/alert_service.py with send_discord_alert() function
  - [x] Subtask 1.2: Accept parameters: alert_type, severity, task_id, channel_id, error_summary, metadata
  - [x] Subtask 1.3: Format Discord embed with title, description, fields, color by severity
  - [x] Subtask 1.4: Use httpx.AsyncClient for non-blocking webhook POST
  - [x] Subtask 1.5: Handle webhook delivery failures gracefully (log but don't crash)

- [x] Task 2: Implement alert batching/rate limiting (AC: Max 1 per minute per error type)
  - [x] Subtask 2.1: Create alert_queue in-memory structure tracking recent alerts
  - [x] Subtask 2.2: Track last_sent_at timestamp per (alert_type, channel_id) tuple
  - [x] Subtask 2.3: Debounce: Skip alert if same type sent within 60 seconds
  - [x] Subtask 2.4: Log suppressed alerts: "alert_suppressed" with count of duplicates
  - [x] Subtask 2.5: Option to force-send critical alerts bypassing debounce

- [x] Task 3: Integrate with retry_orchestrator terminal failure (AC: Terminal failures trigger alerts)
  - [x] Subtask 3.1: Call send_terminal_failure_alert() in _handle_terminal_failure()
  - [x] Subtask 3.2: Include task_id, channel_id, retry_attempts in alert
  - [x] Subtask 3.3: Include final error type and message from error_analysis
  - [x] Subtask 3.4: Include link to Notion page (parameter added, currently None)
  - [x] Subtask 3.5: Use severity="CRITICAL" for terminal failures with force=True to bypass batching

- [x] Task 4: Create YouTube quota alert integration (AC: Quota exhaustion alerts)
  - [x] Subtask 4.1: Updated record_youtube_quota() to call send_quota_alert()
  - [x] Subtask 4.2: Alert at 80% threshold with severity="WARNING" and is_exhausted=False
  - [x] Subtask 4.3: Alert at 100% threshold with severity="CRITICAL" and is_exhausted=True
  - [x] Subtask 4.4: Include current_usage, daily_limit, and channel_id in alert
  - [x] Subtask 4.5: Integrated with existing quota_manager.py throttling logic

- [x] Task 5: Add alert configuration and environment variables (AC: Configurable via env vars)
  - [x] Subtask 5.1: Updated DISCORD_WEBHOOK_URL documentation in .env.example
  - [x] Subtask 5.2: Added ALERT_ENABLE_BATCHING (default: true) config
  - [x] Subtask 5.3: Added ALERT_BATCH_WINDOW_SECONDS (default: 60) config
  - [x] Subtask 5.4: Graceful handling: logs warning if DISCORD_WEBHOOK_URL missing
  - [x] Subtask 5.5: Documented Railway environment variable setup in .env.example

- [x] Task 6: Create Discord alert formatting templates (AC: User-friendly alert format)
  - [x] Subtask 6.1: send_terminal_failure_alert() template with task details, error summary, retry count
  - [x] Subtask 6.2: send_quota_alert() exhaustion template (100%) with usage stats, paused operations
  - [x] Subtask 6.3: send_quota_alert() warning template (80%) with remaining quota, reset time
  - [x] Subtask 6.4: Emoji indicators implemented (🔴 CRITICAL, ⚠️ WARNING, ℹ️ INFO)
  - [x] Subtask 6.5: Timestamp and correlation_id footer added to all alerts

- [x] Task 7: Write comprehensive tests for alert system (AC: All alert paths tested)
  - [x] Subtask 7.1: 5 unit tests for send_discord_alert() (embed formatting, colors, delivery)
  - [x] Subtask 7.2: 7 tests for alert batching/rate limiting logic (suppression, window expiry, force bypass)
  - [x] Subtask 7.3: 5 integration tests: Terminal failure → Discord alert (with/without webhook, recommendation)
  - [x] Subtask 7.4: 3 unit tests for quota alerts (WARNING, CRITICAL, no webhook)
  - [x] Subtask 7.5: 2 tests for webhook delivery failures (HTTP errors, unexpected exceptions)
  - **Total: 41 passing tests** (18 alert service + 5 alert integration + 18 quota manager)

- [x] Task 8: Add alert delivery monitoring (AC: Alert failures are logged and tracked)
  - [x] Subtask 8.1: Log successful delivery: "alert_sent" with alert_type, severity, title, webhook_response_status
  - [x] Subtask 8.2: Log failed delivery: "alert_failed" with error details, "alert_system_error" for unexpected errors
  - [x] Subtask 8.3: Log suppressed alerts: "alert_suppressed" with elapsed_seconds and batch_window_seconds
  - [x] Subtask 8.4: Added Railway log query patterns to docs/railway-log-queries.md (Alert Delivery Monitoring section)
  - [x] Subtask 8.5: Fallback alerting not implemented (optional, fire-and-forget pattern chosen)

## Dev Notes

### Critical Context from Story 6.6 Requirements

**FR32: Alert System for Terminal Failures**
From epics.md:1485-1512, Story 6.6 requires alerts sent to Discord when:
- Task exhausts all retry attempts (after 3 retries from Story 6.2)
- YouTube quota reaches 80% threshold (WARNING)
- YouTube quota reaches 100% threshold (CRITICAL, pause uploads)
- Alert includes: task_id, channel, step, error summary
- Alerts must be batched to prevent spam (max 1 per minute per error type)
- Alert delivery within 5 minutes (NFR-R5)

**NFR-R5: Error Alert Reliability**
From epics.md:151, architecture.md:810-850:
- 100% of terminal failures trigger alerts within 5 minutes
- Alert delivery failures must not crash the system
- If Discord webhook fails, log the error and continue
- Consider fallback alerting mechanisms (email, Slack) for high-availability setups

**Key Integration Points:**
1. **Story 6.1 (Transient Failure Detection):** Only terminal failures after classification should trigger alerts
2. **Story 6.2 (Exponential Backoff Retry):** Alerts triggered when max_retries (3) exhausted
3. **Story 6.4 (Granular Error Status Updates):** Use ErrorPayload for alert message formatting
4. **Story 6.5 (Detailed Error Logging):** Alert delivery logged using structlog for Railway observability

### Architecture Compliance

**Discord Webhook Integration (New Architectural Decision)**

From architecture.md:810-850 and requirement FR32, the system must support Discord webhook alerts for operational monitoring.

**Discord Webhook Pattern (REQUIRED):**

```python
import httpx
import structlog
from typing import Literal
from datetime import datetime

log = structlog.get_logger()

AlertSeverity = Literal["INFO", "WARNING", "CRITICAL"]
AlertType = Literal["terminal_failure", "quota_warning", "quota_exhausted", "worker_down"]

async def send_discord_alert(
    alert_type: AlertType,
    severity: AlertSeverity,
    title: str,
    description: str,
    fields: dict[str, str],
    webhook_url: str
) -> bool:
    """
    Send alert to Discord via webhook.

    Args:
        alert_type: Type of alert (for batching key)
        severity: Alert severity level
        title: Alert title (shown in Discord notification)
        description: Alert description (main message body)
        fields: Key-value pairs shown as Discord embed fields
        webhook_url: Discord webhook URL from environment

    Returns:
        bool: True if delivery succeeded, False if failed

    Raises:
        None: All exceptions caught and logged, never crashes
    """
    try:
        # Map severity to Discord embed color
        color_map = {
            "INFO": 0x3498db,     # Blue
            "WARNING": 0xf39c12,  # Orange
            "CRITICAL": 0xe74c3c  # Red
        }

        # Build Discord embed
        embed = {
            "title": f"{'🔴' if severity == 'CRITICAL' else '⚠️' if severity == 'WARNING' else 'ℹ️'} {title}",
            "description": description,
            "color": color_map[severity],
            "fields": [
                {"name": key, "value": value, "inline": True}
                for key, value in fields.items()
            ],
            "footer": {
                "text": f"Alert Type: {alert_type} | {datetime.utcnow().isoformat()}"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        payload = {
            "embeds": [embed],
            "username": "AI Video Generator Alerts"
        }

        # Non-blocking webhook POST
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()

        # Log successful delivery
        log.info(
            "alert_sent",
            alert_type=alert_type,
            severity=severity,
            title=title
        )

        return True

    except httpx.HTTPError as e:
        # Log failure but don't crash
        log.error(
            "alert_failed",
            alert_type=alert_type,
            severity=severity,
            error=str(e),
            exc_info=True
        )
        return False

    except Exception as e:
        # Catch-all for unexpected errors
        log.critical(
            "alert_system_error",
            alert_type=alert_type,
            error=str(e),
            exc_info=True
        )
        return False
```

**Alert Batching Pattern (PREVENT SPAM):**

From architecture.md:810-850, alerts must be rate-limited to prevent Discord spam:

```python
from datetime import datetime, timedelta
from collections import defaultdict

# In-memory tracking of recent alerts
_alert_history: dict[tuple[str, str], datetime] = {}  # (alert_type, channel_id) -> last_sent_at

def should_send_alert(
    alert_type: str,
    channel_id: str,
    batch_window_seconds: int = 60,
    force: bool = False
) -> bool:
    """
    Determine if alert should be sent based on batching rules.

    Args:
        alert_type: Type of alert (for deduplication)
        channel_id: Channel ID (scope batching per channel)
        batch_window_seconds: Minimum time between duplicate alerts
        force: If True, bypass batching (for CRITICAL alerts)

    Returns:
        bool: True if alert should be sent, False if suppressed
    """
    if force:
        return True

    key = (alert_type, channel_id)
    now = datetime.utcnow()

    if key in _alert_history:
        last_sent = _alert_history[key]
        elapsed = (now - last_sent).total_seconds()

        if elapsed < batch_window_seconds:
            # Suppress duplicate alert
            log.info(
                "alert_suppressed",
                alert_type=alert_type,
                channel_id=channel_id,
                elapsed_seconds=elapsed,
                batch_window_seconds=batch_window_seconds
            )
            return False

    # Update history and allow alert
    _alert_history[key] = now
    return True

async def send_alert_with_batching(
    alert_type: str,
    severity: AlertSeverity,
    title: str,
    description: str,
    fields: dict[str, str],
    webhook_url: str,
    channel_id: str,
    force: bool = False
) -> bool:
    """Send alert with automatic batching/rate limiting."""
    if not should_send_alert(alert_type, channel_id, force=force):
        return False  # Suppressed

    return await send_discord_alert(
        alert_type, severity, title, description, fields, webhook_url
    )
```

**Terminal Failure Alert Integration (Story 6.2):**

From retry_orchestrator.py (Story 6.2) and requirements FR32:

```python
# app/services/retry_orchestrator.py (MODIFY)

from app.services.alert_service import send_alert_with_batching
from app.schemas.error_payload import ErrorPayload

async def handle_terminal_failure(
    task_id: UUID,
    final_error_payload: ErrorPayload,
    db: AsyncSession
) -> None:
    """
    Handle task that exhausted all retry attempts.

    Responsibilities:
    1. Mark task as permanently failed (Story 6.2)
    2. Log terminal failure (Story 6.5)
    3. Send Discord alert (Story 6.6 - NEW)
    """
    task = await db.get(Task, task_id)

    # Step 1: Update task status (existing from Story 6.2)
    task.status = "failed"
    await db.commit()

    # Step 2: Log terminal failure (existing from Story 6.5)
    from app.services.error_logger import log_terminal_failure
    await log_terminal_failure(
        task_id=task.id,
        correlation_id=task.correlation_id,
        channel_id=task.channel_id,
        retry_attempts=task.retry_count,
        final_error_type=final_error_payload.error_category,
        final_error_message=final_error_payload.error_message
    )

    # Step 3: Send Discord alert (NEW for Story 6.6)
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_url:
        await send_alert_with_batching(
            alert_type="terminal_failure",
            severity="CRITICAL",
            title=f"Task Failed Permanently: {task.title}",
            description=(
                f"Task {task_id} failed after {task.retry_count} retry attempts. "
                f"Human intervention required.\n\n"
                f"**Error:** {final_error_payload.error_message}\n"
                f"**Step:** {final_error_payload.step_name}\n"
                f"**Recommendation:** {final_error_payload.recommendation}"
            ),
            fields={
                "Task ID": str(task_id),
                "Channel": task.channel_id,
                "Failed Step": final_error_payload.step_name,
                "Error Type": final_error_payload.error_category,
                "Retry Attempts": str(task.retry_count),
                "Correlation ID": str(task.correlation_id)
            },
            webhook_url=webhook_url,
            channel_id=task.channel_id,
            force=True  # CRITICAL alerts bypass batching
        )
    else:
        log.warning(
            "discord_webhook_not_configured",
            message="Terminal failure alert not sent - DISCORD_WEBHOOK_URL not set"
        )
```

**YouTube Quota Alert Integration (Architecture Decision 6):**

From architecture.md:457-477 and requirements FR34, YouTube quota monitoring must trigger alerts:

```python
# app/services/youtube_quota_service.py (EXTEND)

from app.services.alert_service import send_alert_with_batching

async def check_and_alert_quota(
    channel_id: str,
    current_usage: int,
    daily_limit: int,
    webhook_url: str
) -> None:
    """
    Check YouTube quota and send alerts at 80% and 100% thresholds.

    Args:
        channel_id: YouTube channel ID
        current_usage: Current quota units used today
        daily_limit: Daily quota limit (typically 10,000)
        webhook_url: Discord webhook URL
    """
    usage_percent = (current_usage / daily_limit) * 100

    # Alert at 100% threshold (CRITICAL)
    if usage_percent >= 100:
        await send_alert_with_batching(
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
                "Action": "Uploads paused"
            },
            webhook_url=webhook_url,
            channel_id=channel_id,
            force=True  # CRITICAL
        )

    # Alert at 80% threshold (WARNING)
    elif usage_percent >= 80:
        await send_alert_with_batching(
            alert_type="quota_warning",
            severity="WARNING",
            title=f"YouTube Quota Warning: {channel_id}",
            description=(
                f"**Channel {channel_id} approaching YouTube API quota limit.**\n\n"
                f"Current Usage: {current_usage:,} / {daily_limit:,} units ({usage_percent:.1f}%)\n\n"
                f"Consider prioritizing high-value uploads."
            ),
            fields={
                "Channel": channel_id,
                "Usage": f"{current_usage:,} / {daily_limit:,} units",
                "Percentage": f"{usage_percent:.1f}%",
                "Remaining": f"{daily_limit - current_usage:,} units",
                "Reset Time": "Midnight PST (8AM UTC)"
            },
            webhook_url=webhook_url,
            channel_id=channel_id,
            force=False  # Allow batching
        )
```

**Short Transaction Pattern (NEVER hold DB during alert):**

From architecture.md:126-144 and project-context.md:711-730:

```python
# ✅ CORRECT: Send alert OUTSIDE transaction
async def handle_terminal_failure(task_id: UUID, error_payload: ErrorPayload, db: AsyncSession):
    # Step 1: Update task status (short transaction)
    async with db.begin():
        task = await db.get(Task, task_id)
        task.status = "failed"

    # Step 2: Send Discord alert (NO DATABASE CONNECTION)
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_url:
        await send_alert_with_batching(
            alert_type="terminal_failure",
            severity="CRITICAL",
            ...
        )

# ❌ WRONG: Hold transaction during alert
async with db.begin():
    task.status = "failed"
    await send_alert_with_batching(...)  # BLOCKS DB!
```

### Previous Story Intelligence

**Story 6.1: Transient Failure Detection (CRITICAL INTEGRATION)**

Completed in commit 0d0702f. Story 6.6 alerts ONLY for terminal failures (non-transient errors or exhausted retries):

**Key Integration Point:**
- Only trigger alerts when error is PERMANENT or after all retries exhausted
- Do NOT alert for transient failures (handled by Story 6.2 retry logic)
- Use error_classifier to determine if error warrants immediate alert vs retry

```python
from app.services.error_classifier import classify_error, ErrorCategory

# Check if error is terminal (permanent or retry exhausted)
error_analysis = classify_error(exception, context)

if error_analysis.category == ErrorCategory.PERMANENT:
    # Alert immediately - no retry will help
    await send_alert_with_batching(
        alert_type="terminal_failure",
        severity="CRITICAL",
        ...
    )
elif task.retry_count >= 3:
    # Alert after retries exhausted
    await send_alert_with_batching(
        alert_type="terminal_failure",
        severity="CRITICAL",
        ...
    )
else:
    # Transient error - let Story 6.2 retry handle it
    log.info("transient_error_retrying", retry_attempt=task.retry_count + 1)
```

**Story 6.2: Exponential Backoff Retry Logic (CRITICAL INTEGRATION)**

Completed in commit 0b285f5. Story 6.6 integrates with handle_terminal_failure():

**Key Integration Points:**
1. **Terminal failure detection:** Alert when max_retries (3) reached
2. **Retry exhaustion:** Alert includes retry count and final error
3. **Integration point:** Modify handle_terminal_failure() to call send_alert_with_batching()

**Story 6.4: Granular Error Status Updates (CRITICAL INTEGRATION)**

Status: done (all 10 tasks complete). Story 6.6 uses ErrorPayload for alert formatting:

**Key Integration Points:**
1. **ErrorPayload structure:** Use for Discord alert message formatting
2. **Alert fields:** Include step_name, error_category, error_message, recommendation
3. **Failure location:** Use FailureLocation.format() for human-readable location

```python
# Use ErrorPayload for alert formatting
await send_alert_with_batching(
    alert_type="terminal_failure",
    severity="CRITICAL",
    title=f"Task Failed: {task.title}",
    description=(
        f"**Error:** {error_payload.error_message}\n"
        f"**Step:** {error_payload.step_name}\n"
        f"**Location:** {error_payload.failure_location.format()}\n"
        f"**Recommendation:** {error_payload.recommendation}"
    ),
    fields={
        "Error Type": error_payload.error_category,
        "Retry Attempts": str(error_payload.retry_attempt),
        "Correlation ID": str(error_payload.correlation_id)
    },
    ...
)
```

**Story 6.5: Detailed Error Logging (CRITICAL INTEGRATION)**

Status: done (all 8 tasks complete). Story 6.6 logs alert delivery using structlog:

**Key Integration Points:**
1. **Alert delivery logging:** Use structlog to log successful/failed alert delivery
2. **Railway observability:** Alert logs queryable in Railway dashboard
3. **Correlation IDs:** Link alert logs to task logs via correlation_id

```python
# Log alert delivery (from Story 6.5 pattern)
log.info(
    "alert_sent",
    event="alert_sent",
    alert_type="terminal_failure",
    severity="CRITICAL",
    task_id=str(task_id),
    correlation_id=str(correlation_id),
    channel_id=channel_id,
    webhook_response_status=200
)

# Log alert failure
log.error(
    "alert_failed",
    event="alert_failed",
    alert_type="terminal_failure",
    error=str(exception),
    task_id=str(task_id),
    correlation_id=str(correlation_id),
    exc_info=True
)
```

### Technical Requirements

**New Service: Discord Alert Service**

Create `app/services/alert_service.py`:

```python
"""
Discord webhook alert service for operational monitoring.

This service provides standardized alerting for terminal failures, quota
exhaustion, and other operational events requiring human attention.

Integration:
- Story 6.1: Only alerts for permanent errors or exhausted retries
- Story 6.2: Integrates with handle_terminal_failure() after retry exhaustion
- Story 6.4: Uses ErrorPayload for alert message formatting
- Story 6.5: Logs alert delivery using structlog for Railway observability
"""

import os
import httpx
import structlog
from datetime import datetime, timedelta
from typing import Literal
from collections import defaultdict

log = structlog.get_logger()

AlertSeverity = Literal["INFO", "WARNING", "CRITICAL"]
AlertType = Literal["terminal_failure", "quota_warning", "quota_exhausted", "worker_down"]

# In-memory alert batching tracker
_alert_history: dict[tuple[str, str], datetime] = {}

def should_send_alert(
    alert_type: str,
    channel_id: str,
    force: bool = False
) -> bool:
    """Check if alert should be sent based on batching rules."""
    batch_window = int(os.getenv("ALERT_BATCH_WINDOW_SECONDS", "60"))

    if force:
        return True

    key = (alert_type, channel_id)
    now = datetime.utcnow()

    if key in _alert_history:
        elapsed = (now - _alert_history[key]).total_seconds()
        if elapsed < batch_window:
            log.info(
                "alert_suppressed",
                alert_type=alert_type,
                channel_id=channel_id,
                elapsed_seconds=elapsed
            )
            return False

    _alert_history[key] = now
    return True

async def send_discord_alert(
    alert_type: AlertType,
    severity: AlertSeverity,
    title: str,
    description: str,
    fields: dict[str, str],
    webhook_url: str
) -> bool:
    """Send alert to Discord via webhook. See pattern above for full implementation."""
    # ... (implementation as shown in architecture pattern)

async def send_alert_with_batching(
    alert_type: str,
    severity: AlertSeverity,
    title: str,
    description: str,
    fields: dict[str, str],
    webhook_url: str,
    channel_id: str,
    force: bool = False
) -> bool:
    """Send alert with automatic batching/rate limiting."""
    if not should_send_alert(alert_type, channel_id, force=force):
        return False

    return await send_discord_alert(
        alert_type, severity, title, description, fields, webhook_url
    )
```

**Extend Retry Orchestrator (Story 6.2):**

```python
# app/services/retry_orchestrator.py (ADD alert integration)

from app.services.alert_service import send_alert_with_batching

async def handle_terminal_failure(
    task_id: UUID,
    final_error_payload: ErrorPayload,
    db: AsyncSession
) -> None:
    """
    Handle task that exhausted all retry attempts.

    NEW for Story 6.6: Send Discord alert for terminal failures.
    """
    # ... existing logic from Story 6.2/6.5

    # NEW: Send Discord alert
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_url:
        await send_alert_with_batching(
            alert_type="terminal_failure",
            severity="CRITICAL",
            title=f"Task Failed Permanently: {task.title}",
            description=f"Task failed after {task.retry_count} retries...",
            fields={
                "Task ID": str(task_id),
                "Channel": task.channel_id,
                "Failed Step": final_error_payload.step_name,
                "Error Type": final_error_payload.error_category
            },
            webhook_url=webhook_url,
            channel_id=task.channel_id,
            force=True
        )
```

**Create YouTube Quota Alert Service:**

```python
# app/services/youtube_quota_service.py (NEW or EXTEND)

from app.services.alert_service import send_alert_with_batching

async def check_and_alert_quota(
    channel_id: str,
    current_usage: int,
    daily_limit: int,
    webhook_url: str
) -> None:
    """Check quota thresholds and send alerts."""
    usage_percent = (current_usage / daily_limit) * 100

    if usage_percent >= 100:
        # CRITICAL: Quota exhausted
        await send_alert_with_batching(
            alert_type="quota_exhausted",
            severity="CRITICAL",
            ...
        )
    elif usage_percent >= 80:
        # WARNING: Approaching limit
        await send_alert_with_batching(
            alert_type="quota_warning",
            severity="WARNING",
            ...
        )
```

### Library & Framework Requirements

**New dependencies (add to pyproject.toml):**
- `httpx>=0.25.0` - Async HTTP client for webhook delivery (likely already installed)

**Existing dependencies:**
- `structlog>=23.2.0` - Logging for alert delivery tracking (already configured)
- `python-dotenv>=1.0.0` - Environment variable management (already in use)

### File Structure Requirements

**New Files:**
1. `app/services/alert_service.py` - Discord webhook integration and alert batching
2. `docs/discord-webhook-setup.md` - Guide for creating Discord webhook and Railway config
3. `tests/test_services/test_alert_service.py` - Unit tests for alert service (5+ tests)
4. `tests/test_services/test_alert_integration.py` - Integration tests for alert flows (5+ tests)

**Modified Files:**
1. `app/services/retry_orchestrator.py` - Add send_alert_with_batching() to handle_terminal_failure()
2. `app/services/youtube_quota_service.py` - Add check_and_alert_quota() integration (if file exists, else create)
3. `.env.example` - Add DISCORD_WEBHOOK_URL and ALERT_* configuration variables
4. `docs/railway-log-queries.md` - Add alert delivery query patterns

**Environment Variables (.env.example):**
```
# Discord Webhook Alerts (Story 6.6)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/1234567890/abcdefg
ALERT_ENABLE_BATCHING=true
ALERT_BATCH_WINDOW_SECONDS=60
```

### Testing Requirements

**Unit Tests (`tests/test_services/test_alert_service.py`):**

1. **Discord Webhook Delivery:**
   - Test send_discord_alert() formats embed correctly
   - Test severity maps to correct Discord embed colors
   - Test emoji indicators in title (🔴, ⚠️, ℹ️)
   - Test webhook POST with httpx.AsyncClient
   - Test delivery failure handling (log error, don't crash)

2. **Alert Batching:**
   - Test should_send_alert() allows first alert through
   - Test should_send_alert() suppresses duplicate within 60 seconds
   - Test should_send_alert() allows alert after batch window expires
   - Test force=True bypasses batching
   - Test batching is scoped per (alert_type, channel_id)

**Integration Tests (`tests/test_services/test_alert_integration.py`):**

1. **Terminal Failure Alert:**
   - Simulate task failing after 3 retries
   - Call handle_terminal_failure()
   - Verify send_alert_with_batching() called with CRITICAL severity
   - Verify alert includes task_id, channel_id, error summary
   - Verify alert delivery logged to Railway

2. **YouTube Quota Alerts:**
   - Simulate usage at 80% threshold
   - Call check_and_alert_quota()
   - Verify WARNING alert sent
   - Simulate usage at 100% threshold
   - Verify CRITICAL alert sent

3. **Alert Batching in Action:**
   - Simulate 3 terminal failures for same channel within 60 seconds
   - Verify only 1 alert sent (first one)
   - Verify subsequent 2 alerts suppressed and logged

4. **Webhook Failure Handling:**
   - Mock httpx.AsyncClient.post() to raise HTTPError
   - Verify alert delivery fails gracefully
   - Verify "alert_failed" logged
   - Verify system continues operating

**Test Pattern Example:**

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.services.alert_service import send_discord_alert, send_alert_with_batching

@pytest.mark.asyncio
async def test_discord_alert_formats_embed_correctly(mock_httpx_client):
    """Verify Discord embed formatting."""
    webhook_url = "https://discord.com/api/webhooks/test"

    result = await send_discord_alert(
        alert_type="terminal_failure",
        severity="CRITICAL",
        title="Task Failed",
        description="Task failed after 3 retries",
        fields={"Task ID": "abc-123", "Channel": "poke1"},
        webhook_url=webhook_url
    )

    assert result is True
    assert mock_httpx_client.post.called

    # Verify embed structure
    call_args = mock_httpx_client.post.call_args
    payload = call_args.kwargs["json"]
    embed = payload["embeds"][0]

    assert "🔴" in embed["title"]  # CRITICAL emoji
    assert embed["color"] == 0xe74c3c  # Red color
    assert embed["description"] == "Task failed after 3 retries"
    assert len(embed["fields"]) == 2

@pytest.mark.asyncio
async def test_alert_batching_suppresses_duplicates():
    """Verify alert batching prevents spam."""
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
        force=False
    )
    assert result1 is True

    # Second alert (duplicate) should be suppressed
    result2 = await send_alert_with_batching(
        alert_type="terminal_failure",
        severity="CRITICAL",
        title="Task Failed",
        description="Second failure",
        fields={},
        webhook_url=webhook_url,
        channel_id="poke1",
        force=False
    )
    assert result2 is False  # Suppressed

@pytest.mark.asyncio
async def test_terminal_failure_triggers_alert(db_session, mock_httpx_client):
    """Integration test: Terminal failure → Discord alert."""
    from app.services.retry_orchestrator import handle_terminal_failure
    from app.schemas.error_payload import ErrorPayload, FailureLocation

    task = create_task(channel_id="poke1", retry_count=3)
    db_session.add(task)
    await db_session.commit()

    error_payload = ErrorPayload(
        timestamp=datetime.utcnow(),
        correlation_id=task.correlation_id,
        step_name="video_generation",
        failure_location=FailureLocation(...),
        error_category="PERMANENT",
        error_message="Invalid API key",
        retry_attempt=3
    )

    with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://webhook.url"}):
        await handle_terminal_failure(task.id, error_payload, db_session)

    # Verify alert sent
    assert mock_httpx_client.post.called
    payload = mock_httpx_client.post.call_args.kwargs["json"]
    assert "Task Failed Permanently" in payload["embeds"][0]["title"]
```

### Project Structure Notes

**Alignment with Epic 6 Stories:**

Story 6.6 is the operational alerting story that completes Epic 6's error handling infrastructure:

1. **Story 6.1:** Classifies errors → Story 6.6 alerts only for terminal failures (not transient)
2. **Story 6.2:** Retries failures → Story 6.6 alerts when retries exhausted
3. **Story 6.3:** Resumes from checkpoints → Story 6.6 includes checkpoint progress in alerts
4. **Story 6.4:** Updates Notion status → Story 6.6 adds Discord alerting (complementary, not duplicate)
5. **Story 6.5:** Logs to Railway → Story 6.6 logs alert delivery for observability

**Discord vs Railway vs Notion:**

- **Discord alerts:** Real-time notifications for human intervention (Story 6.6)
- **Railway logs:** Technical debugging, correlation IDs, full stack traces (Story 6.5)
- **Notion Error Log:** User-facing error summaries in planning database (Story 6.4)
- All three use same error classification (Story 6.1) and retry tracking (Story 6.2)

**Alert Delivery Guarantees:**

From NFR-R5, alerts must be delivered within 5 minutes with 100% reliability:
- If Discord webhook fails, log error and continue (don't crash)
- Consider fallback alerting (email, Slack) for production deployments
- Alert delivery failures tracked in Railway logs for monitoring

### References

**Epic & Requirements:**
- PRD: FR32 (Alert system for terminal failures with Discord webhook)
- NFR-R5: (100% terminal failures trigger alerts within 5 minutes)
- Epic 6 Story 6.6: `/Users/francisaraujo/repos/ai-video-generator/_bmad-output/planning-artifacts/epics.md#story-66-alert-system-for-terminal-failures` (lines 1485-1512)
- Previous stories:
  - Story 6.1: `/Users/francisaraujo/repos/ai-video-generator/_bmad-output/implementation-artifacts/6-1-transient-failure-detection.md`
  - Story 6.2: `/Users/francisaraujo/repos/ai-video-generator/_bmad-output/implementation-artifacts/6-2-exponential-backoff-retry-logic.md`
  - Story 6.4: `/Users/francisaraujo/repos/ai-video-generator/_bmad-output/implementation-artifacts/6-4-granular-error-status-updates.md`
  - Story 6.5: `/Users/francisaraujo/repos/ai-video-generator/_bmad-output/implementation-artifacts/6-5-detailed-error-logging.md`

**Architecture:**
- Discord webhook pattern: `architecture.md:810-850` (alert delivery, batching, rate limiting)
- YouTube quota monitoring: `architecture.md:457-477` (quota tracking, alert thresholds)
- Short transactions: `architecture.md:126-144` (never hold DB during webhook POST)
- Project context: `project-context.md:686-730` (structlog for alert logging)

**Code References:**
- Story 6.2 retry orchestrator: `app/services/retry_orchestrator.py` (handle_terminal_failure integration point)
- Story 6.4 error payload: `app/schemas/error_payload.py` (ErrorPayload for alert formatting)
- Story 6.5 error logger: `app/services/error_logger.py` (log_terminal_failure, structlog patterns)

**Latest Best Practices (2026):**
- Discord webhooks: https://discord.com/developers/docs/resources/webhook (embed formatting, rate limits)
- httpx async client: https://www.python-httpx.org/async/ (non-blocking HTTP, timeout handling)
- Operational alerting patterns: https://sre.google/workbook/alerting-on-slos/ (alert fatigue prevention, SLO-based alerting)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

None - all tests passed on first attempt after fixing integration issues.

### Completion Notes List

1. **Discord Alert Service Created** - Implemented `app/services/alert_service.py` with:
   - `send_discord_alert()` - Core webhook delivery with embed formatting
   - `send_terminal_failure_alert()` - Terminal failure alerts with rich context
   - `send_quota_alert()` - YouTube quota threshold alerts (80%/100%)
   - `should_send_alert()` - Alert batching/rate limiting logic
   - `send_alert_with_batching()` - Wrapper with automatic batching

2. **Integration with Retry Orchestrator** - Modified `app/services/retry_orchestrator.py`:
   - Added `send_terminal_failure_alert()` call in `_handle_terminal_failure()`
   - Passes task details, error analysis, and correlation ID
   - Fire-and-forget pattern (alerts never crash pipeline)
   - Short transaction pattern (DB update first, then alert)

3. **YouTube Quota Alert Integration** - Modified `app/services/quota_manager.py`:
   - Replaced generic `send_alert()` with Story 6.6 `send_quota_alert()`
   - WARNING alerts at 80% threshold (is_exhausted=False)
   - CRITICAL alerts at 100% threshold (is_exhausted=True)
   - Preserves existing throttling logic (_should_send_alert)

4. **Comprehensive Test Coverage** - 41 passing tests:
   - 18 unit tests in `tests/test_services/test_alert_service.py`
   - 5 integration tests in `tests/test_services/test_alert_integration.py`
   - 18 quota manager tests in `tests/test_services/test_quota_manager.py`

5. **Environment Configuration** - Updated `.env.example`:
   - Enhanced DISCORD_WEBHOOK_URL documentation with use cases
   - Added ALERT_ENABLE_BATCHING config (default: true)
   - Added ALERT_BATCH_WINDOW_SECONDS config (default: 60)

6. **Railway Monitoring Documentation** - Extended `docs/railway-log-queries.md`:
   - Added "Alert Delivery Monitoring" section
   - Log query patterns for alert_sent, alert_failed, alert_suppressed events
   - Alert type filtering, quota alert monitoring, webhook troubleshooting
   - Complete alert trace queries with correlation_id

7. **Key Design Decisions**:
   - **Fire-and-forget**: Alerts never block or crash the pipeline
   - **Force bypass for CRITICAL**: Terminal failures bypass batching (force=True)
   - **Channel UUID strings**: Used UUID.str() for channel identifiers in alerts
   - **structlog patterns**: Consistent with Story 6.5 logging standards
   - **Short transactions**: Never hold DB connection during webhook POST

8. **Test Fixes Applied**:
   - Fixed structlog event parameter usage (removed explicit event= kwarg)
   - Updated datetime.utcnow() → datetime.now(UTC) for Python 3.14
   - Fixed database fixture naming (db_session → async_session)
   - Added missing ErrorAnalysis required fields (http_status_code, retry_recommended)
   - Fixed case sensitivity assertions (TaskStatus.value returns lowercase)
   - Updated quota_manager tests to use send_quota_alert signature

### File List

**Created:**
- `app/services/alert_service.py` - Discord webhook alert service (354 lines)
- `tests/test_services/test_alert_service.py` - Alert service unit tests (487 lines)
- `tests/test_services/test_alert_integration.py` - Alert integration tests (220 lines)

**Modified:**
- `app/services/retry_orchestrator.py` - Added terminal failure alert integration
- `app/services/quota_manager.py` - Updated to use Story 6.6 alert service
- `tests/test_services/test_quota_manager.py` - Updated test mocks for send_quota_alert
- `.env.example` - Added alert configuration documentation
- `docs/railway-log-queries.md` - Added alert delivery monitoring section

**All Acceptance Criteria Met:**
✅ Terminal failures trigger Discord alerts within 5 minutes (immediate delivery)
✅ YouTube quota exhaustion (100%) triggers immediate CRITICAL alert
✅ Alerts batched to prevent spam (max 1 per minute per error type)
✅ Alerts include task_id, channel, step, error summary, correlation_id
✅ Alert delivery logged with structlog (alert_sent, alert_failed, alert_suppressed)
✅ Graceful degradation (logs warning if DISCORD_WEBHOOK_URL not configured)
