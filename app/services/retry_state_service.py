"""Retry state calculation and formatting service (Story 6.9).

This service provides functions for managing retry state visibility:
- Calculate next retry timestamps using exponential backoff
- Format retry status messages for Notion display
- Generate human-readable countdown timers
- Check retry eligibility for worker task claiming

Integration Points:
    - Story 6.2: Uses same exponential backoff schedule (1min, 5min, 15min, 1hr)
    - Story 6.4: Formats retry messages for error status display
    - Story 6.8: Similar pattern to quota exhaustion wait states

Exponential Backoff Schedule:
    - Attempt 1 → 2: Wait 1 minute
    - Attempt 2 → 3: Wait 5 minutes
    - Attempt 3 → 4: Wait 15 minutes
    - Attempt 4 → 5: Wait 1 hour
    - Attempt 5: Terminal failure (no more retries)

Example Usage:
    # Calculate next retry time
    next_retry = calculate_next_retry_time(retry_attempt=3, max_attempts=5)

    # Format status for Notion
    message = get_retry_status_message(
        retry_attempt=3,
        max_attempts=5,
        next_retry_at=next_retry
    )
    # Returns: "Attempt 3/5 - Next: 15 min"

    # Check if worker should claim retry task
    if should_retry(task.retry_count, task.next_retry_at, task.max_retry_attempts):
        # Claim and process task
        ...
"""

from datetime import datetime, timedelta, timezone

import structlog

log = structlog.get_logger()

# Exponential backoff schedule matching Story 6.2
# Each entry represents the wait time BEFORE the next retry attempt
RETRY_BACKOFF_SCHEDULE = [
    timedelta(minutes=1),  # Attempt 1 → 2: Wait 1 minute
    timedelta(minutes=5),  # Attempt 2 → 3: Wait 5 minutes
    timedelta(minutes=15),  # Attempt 3 → 4: Wait 15 minutes
    timedelta(hours=1),  # Attempt 4 → 5: Wait 1 hour
    None,  # Attempt 5: Terminal failure (no more retries)
]


def calculate_next_retry_time(
    retry_attempt: int,
    max_attempts: int = 5,
) -> datetime | None:
    """Calculate next retry timestamp using exponential backoff.

    Args:
        retry_attempt: Current retry attempt count (1-based).
            - 0 = no retries yet (original attempt)
            - 1 = first retry attempt scheduled
            - 2 = second retry attempt scheduled
            - etc.
        max_attempts: Maximum retry attempts before terminal failure (default: 5)

    Returns:
        datetime: Next retry time (UTC timezone-aware), or None if retry exhausted

    Backoff Schedule (wait time before next attempt):
        - retry_attempt=1 (first retry): Wait 1 minute
        - retry_attempt=2 (second retry): Wait 5 minutes
        - retry_attempt=3 (third retry): Wait 15 minutes
        - retry_attempt=4 (fourth retry): Wait 1 hour
        - retry_attempt=5 (fifth retry): Terminal failure (no more retries)

    Integration:
        - Story 6.2: Exponential backoff retry logic
        - Story 6.3: Resume from failure point after delay

    Example:
        >>> next_retry = calculate_next_retry_time(retry_attempt=2, max_attempts=5)
        >>> # Returns datetime approximately 5 minutes from now
        >>> # (second retry attempt uses 5-minute backoff)
    """
    # Check if retry exhausted
    if retry_attempt >= max_attempts:
        log.info(
            "retry_exhausted_calculation",
            retry_attempt=retry_attempt,
            max_attempts=max_attempts,
        )
        return None

    # Check if attempt index out of range for backoff schedule
    # Convert retry_attempt (1-based) to array index (0-based)
    # Example: retry_attempt=1 (first retry) → schedule_index=0
    # → RETRY_BACKOFF_SCHEDULE[0] = 1 minute
    schedule_index = retry_attempt - 1
    if schedule_index < 0 or schedule_index >= len(RETRY_BACKOFF_SCHEDULE):
        log.warning(
            "retry_attempt_out_of_range",
            retry_attempt=retry_attempt,
            schedule_index=schedule_index,
            schedule_length=len(RETRY_BACKOFF_SCHEDULE),
        )
        return None

    # Get backoff duration for this attempt
    # schedule_index=0 → 1min, =1 → 5min, =2 → 15min, =3 → 1hr, =4 → None (exhausted)
    backoff_delta = RETRY_BACKOFF_SCHEDULE[schedule_index]
    if backoff_delta is None:
        # Last attempt failed, no more retries
        return None

    # Calculate next retry time
    next_retry = datetime.now(timezone.utc) + backoff_delta

    log.info(
        "retry_scheduled",
        retry_attempt=retry_attempt,
        max_attempts=max_attempts,
        backoff_minutes=backoff_delta.total_seconds() / 60,
        next_retry_at=next_retry.isoformat(),
    )

    return next_retry


def get_retry_status_message(
    retry_attempt: int,
    max_attempts: int,
    next_retry_at: datetime | None,
) -> str:
    """Format retry status for Notion display.

    Args:
        retry_attempt: Current retry attempt (0 = no retries, 1-5 = retry attempts)
        max_attempts: Maximum retry attempts before terminal failure
        next_retry_at: Scheduled retry time (UTC timezone-aware), or None if no retry

    Returns:
        str: Formatted retry status message for Notion display

    Message Formats:
        - "No retries" (retry_attempt=0, next_retry_at=None)
        - "Attempt 3/5 - Next: 15 min" (active retry scheduled)
        - "Attempt 5/5 - Retry exhausted" (terminal failure)
        - "Attempt 3/5 - Retry in progress..." (next_retry_at <= now)

    Integration:
        - Story 6.4: Displayed in Notion error status column
        - Notion sync service: Updated every status sync

    Example:
        >>> message = get_retry_status_message(3, 5, next_retry)
        >>> # Returns: "Attempt 3/5 - Next: 15 min"
    """
    # No retries case
    if retry_attempt == 0 and next_retry_at is None:
        return "No retries"

    # Retry exhausted case
    if retry_attempt >= max_attempts:
        return f"Attempt {retry_attempt}/{max_attempts} - Retry exhausted"

    # No retry scheduled (shouldn't happen, but handle gracefully)
    if next_retry_at is None:
        return f"Attempt {retry_attempt}/{max_attempts}"

    now = datetime.now(timezone.utc)

    # Retry time has arrived or passed - worker is processing the retry now
    if next_retry_at <= now:
        # Show next attempt number (retry_attempt counts completed attempts)
        # Example: retry_attempt=1 means "1 retry scheduled"
        # Now processing attempt 2 (original + 1 retry)
        return f"Attempt {retry_attempt + 1}/{max_attempts} - Retry in progress..."

    # Calculate countdown to next retry
    time_until = next_retry_at - now
    countdown = format_countdown(time_until)

    return f"Attempt {retry_attempt}/{max_attempts} - Next: {countdown}"


def format_countdown(delta: timedelta) -> str:
    """Format timedelta as human-readable countdown.

    Args:
        delta: Time remaining until retry

    Returns:
        str: Formatted countdown string

    Formats:
        - Seconds: "45 sec"
        - Minutes: "2 min" (ignores seconds)
        - Hours: "1 hr 5 min" or "2 hr"
        - Days: "1 day 2 hr" or "3 day"
        - Negative: "now" (time has passed)

    Example:
        >>> format_countdown(timedelta(minutes=15, seconds=30))
        "15 min"
    """
    total_seconds = int(delta.total_seconds())

    # Negative time means retry time has passed
    if total_seconds < 0:
        return "now"

    # Calculate time components
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    # Format based on largest unit
    if days > 0:
        if hours > 0:
            return f"{days} day {hours} hr"
        return f"{days} day"
    elif hours > 0:
        if minutes > 0:
            return f"{hours} hr {minutes} min"
        return f"{hours} hr"
    elif minutes > 0:
        return f"{minutes} min"
    else:
        return f"{seconds} sec"


def should_retry(
    retry_attempt: int,
    next_retry_at: datetime | None,
    max_attempts: int = 5,
) -> bool:
    """Check if task is eligible for retry.

    Args:
        retry_attempt: Current retry attempt number
        next_retry_at: Scheduled retry time (UTC timezone-aware)
        max_attempts: Maximum retry attempts before terminal failure

    Returns:
        bool: True if retry eligible and time arrived, False otherwise

    Eligibility Rules:
        - Retry attempt must be less than max_attempts
        - next_retry_at must be set (not None)
        - Current time must be >= next_retry_at (retry time arrived)

    Used By:
        - Worker task claiming: Skip tasks not ready for retry
        - Story 6.2: Exponential backoff enforcement

    Example:
        >>> if should_retry(task.retry_count, task.next_retry_at, 5):
        >>> # Worker can claim this task for retry
        >>>     await claim_and_process_task(task)
    """
    # Check if retry exhausted
    if retry_attempt >= max_attempts:
        return False

    # Check if retry scheduled
    if next_retry_at is None:
        return False

    # Check if retry time has arrived
    now = datetime.now(timezone.utc)

    # Handle SQLite returning naive datetime (test compatibility workaround)
    # PostgreSQL (production) returns timezone-aware datetime via DateTime(timezone=True)
    # SQLite (tests) ignores timezone parameter and returns naive datetime
    # This ensures comparison works in both environments by assuming UTC for naive datetimes
    if next_retry_at.tzinfo is None:
        next_retry_at = next_retry_at.replace(tzinfo=timezone.utc)

    return next_retry_at <= now
