"""Tests for Retry State Service (Story 6.9).

This module tests the retry state calculation and formatting service:
- calculate_next_retry_time(): Exponential backoff schedule
- get_retry_status_message(): Notion display formatting
- format_countdown(): Human-readable time formatting
- should_retry(): Retry eligibility checking
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.services.retry_state_service import (
    calculate_next_retry_time,
    get_retry_status_message,
    format_countdown,
    should_retry,
)


# Test calculate_next_retry_time()


def test_calculate_next_retry_time_attempt_1():
    """Verify attempt 1 schedules retry after 1 minute."""
    next_retry = calculate_next_retry_time(retry_attempt=1, max_attempts=5)

    assert next_retry is not None

    # Should be approximately 1 minute from now
    expected_time = datetime.now(timezone.utc) + timedelta(minutes=1)
    delta = (next_retry - expected_time).total_seconds()
    assert abs(delta) < 5  # Within 5 seconds tolerance


def test_calculate_next_retry_time_attempt_2():
    """Verify attempt 2 schedules retry after 5 minutes."""
    next_retry = calculate_next_retry_time(retry_attempt=2, max_attempts=5)

    assert next_retry is not None

    # Should be approximately 5 minutes from now
    expected_time = datetime.now(timezone.utc) + timedelta(minutes=5)
    delta = (next_retry - expected_time).total_seconds()
    assert abs(delta) < 5  # Within 5 seconds tolerance


def test_calculate_next_retry_time_attempt_3():
    """Verify attempt 3 schedules retry after 15 minutes."""
    next_retry = calculate_next_retry_time(retry_attempt=3, max_attempts=5)

    assert next_retry is not None

    # Should be approximately 15 minutes from now
    expected_time = datetime.now(timezone.utc) + timedelta(minutes=15)
    delta = (next_retry - expected_time).total_seconds()
    assert abs(delta) < 5  # Within 5 seconds tolerance


def test_calculate_next_retry_time_attempt_4():
    """Verify attempt 4 schedules retry after 1 hour."""
    next_retry = calculate_next_retry_time(retry_attempt=4, max_attempts=5)

    assert next_retry is not None

    # Should be approximately 1 hour from now
    expected_time = datetime.now(timezone.utc) + timedelta(hours=1)
    delta = (next_retry - expected_time).total_seconds()
    assert abs(delta) < 5  # Within 5 seconds tolerance


def test_calculate_next_retry_time_attempt_5_exhausted():
    """Verify attempt 5 returns None (retry exhausted)."""
    next_retry = calculate_next_retry_time(retry_attempt=5, max_attempts=5)

    # Should return None (no more retries)
    assert next_retry is None


def test_calculate_next_retry_time_exceeds_max():
    """Verify retry attempt exceeding max returns None."""
    next_retry = calculate_next_retry_time(retry_attempt=10, max_attempts=5)

    # Should return None (retry exhausted)
    assert next_retry is None


# Test get_retry_status_message()


def test_get_retry_status_message_no_retries():
    """Verify status message for task with no retries."""
    message = get_retry_status_message(
        retry_attempt=0,
        max_attempts=5,
        next_retry_at=None,
    )

    assert message == "No retries"


def test_get_retry_status_message_active_retry():
    """Verify status message for active retry with countdown."""
    next_retry = datetime.now(timezone.utc) + timedelta(minutes=15)

    message = get_retry_status_message(
        retry_attempt=3,
        max_attempts=5,
        next_retry_at=next_retry,
    )

    # Should show attempt count and countdown
    assert "Attempt 3/5" in message
    assert "Next:" in message
    assert "min" in message  # Should show time unit


def test_get_retry_status_message_retry_exhausted():
    """Verify status message when retry attempts exhausted."""
    message = get_retry_status_message(
        retry_attempt=5,
        max_attempts=5,
        next_retry_at=None,
    )

    assert "Attempt 5/5" in message
    assert "Retry exhausted" in message


def test_get_retry_status_message_retry_in_progress():
    """Verify status message when retry time has arrived."""
    # Next retry in the past (time has arrived)
    next_retry = datetime.now(timezone.utc) - timedelta(minutes=1)

    message = get_retry_status_message(
        retry_attempt=2,
        max_attempts=5,
        next_retry_at=next_retry,
    )

    # Should show retry is starting
    assert "Attempt 3/5" in message  # Next attempt (2 + 1)
    assert "Retry in progress" in message


# Test format_countdown()


def test_format_countdown_seconds():
    """Verify countdown formatting for seconds."""
    delta = timedelta(seconds=45)
    countdown = format_countdown(delta)
    assert countdown == "45 sec"


def test_format_countdown_minutes():
    """Verify countdown formatting for minutes."""
    delta = timedelta(minutes=2, seconds=30)
    countdown = format_countdown(delta)
    assert countdown == "2 min"


def test_format_countdown_hours():
    """Verify countdown formatting for hours."""
    delta = timedelta(hours=1, minutes=5)
    countdown = format_countdown(delta)
    assert countdown == "1 hr 5 min"


def test_format_countdown_hours_only():
    """Verify countdown formatting for hours with no minutes."""
    delta = timedelta(hours=2, minutes=0)
    countdown = format_countdown(delta)
    assert countdown == "2 hr"


def test_format_countdown_days():
    """Verify countdown formatting for days."""
    delta = timedelta(days=1, hours=2)
    countdown = format_countdown(delta)
    assert countdown == "1 day 2 hr"


def test_format_countdown_days_only():
    """Verify countdown formatting for days with no hours."""
    delta = timedelta(days=3, hours=0)
    countdown = format_countdown(delta)
    assert countdown == "3 day"


def test_format_countdown_negative():
    """Verify countdown formatting for negative time (overdue)."""
    delta = timedelta(seconds=-30)
    countdown = format_countdown(delta)
    assert countdown == "now"


# Test should_retry()


def test_should_retry_eligible_and_ready():
    """Verify should_retry returns True when eligible and time arrived."""
    next_retry = datetime.now(timezone.utc) - timedelta(seconds=1)  # Past

    result = should_retry(
        retry_attempt=2,
        next_retry_at=next_retry,
        max_attempts=5,
    )

    assert result is True


def test_should_retry_eligible_but_not_ready():
    """Verify should_retry returns False when eligible but time not arrived."""
    next_retry = datetime.now(timezone.utc) + timedelta(minutes=10)  # Future

    result = should_retry(
        retry_attempt=2,
        next_retry_at=next_retry,
        max_attempts=5,
    )

    assert result is False


def test_should_retry_exhausted():
    """Verify should_retry returns False when retry attempts exhausted."""
    next_retry = datetime.now(timezone.utc)  # Time doesn't matter

    result = should_retry(
        retry_attempt=5,
        next_retry_at=next_retry,
        max_attempts=5,
    )

    assert result is False


def test_should_retry_no_retry_scheduled():
    """Verify should_retry returns False when no retry scheduled."""
    result = should_retry(
        retry_attempt=2,
        next_retry_at=None,  # No retry scheduled
        max_attempts=5,
    )

    assert result is False


def test_should_retry_exceeds_max():
    """Verify should_retry returns False when attempt exceeds max."""
    next_retry = datetime.now(timezone.utc)

    result = should_retry(
        retry_attempt=10,  # Way over max
        next_retry_at=next_retry,
        max_attempts=5,
    )

    assert result is False
