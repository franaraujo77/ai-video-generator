"""Tests for workspace cleanup configuration (Story 8.5 Task 5).

Validates configuration loading, validation, and clamping behavior
for workspace cleanup settings.
"""

import os
import pytest

from app.config import (
    get_workspace_cleanup_enabled,
    get_workspace_cleanup_retention_days,
    get_workspace_cleanup_schedule,
)


def test_workspace_cleanup_enabled_default(monkeypatch):
    """Test cleanup enabled defaults to true when not set."""
    monkeypatch.delenv("WORKSPACE_CLEANUP_ENABLED", raising=False)
    assert get_workspace_cleanup_enabled() is True


def test_workspace_cleanup_enabled_true(monkeypatch):
    """Test cleanup enabled when set to 'true'."""
    monkeypatch.setenv("WORKSPACE_CLEANUP_ENABLED", "true")
    assert get_workspace_cleanup_enabled() is True


def test_workspace_cleanup_enabled_false(monkeypatch):
    """Test cleanup disabled when set to 'false'."""
    monkeypatch.setenv("WORKSPACE_CLEANUP_ENABLED", "false")
    assert get_workspace_cleanup_enabled() is False


def test_workspace_cleanup_enabled_case_insensitive(monkeypatch):
    """Test cleanup enabled is case-insensitive."""
    monkeypatch.setenv("WORKSPACE_CLEANUP_ENABLED", "TRUE")
    assert get_workspace_cleanup_enabled() is True

    monkeypatch.setenv("WORKSPACE_CLEANUP_ENABLED", "FALSE")
    assert get_workspace_cleanup_enabled() is False


def test_workspace_cleanup_retention_days_default(monkeypatch):
    """Test retention days defaults to 7 when not set."""
    monkeypatch.delenv("WORKSPACE_CLEANUP_RETENTION_DAYS", raising=False)
    assert get_workspace_cleanup_retention_days() == 7


def test_workspace_cleanup_retention_days_valid(monkeypatch):
    """Test retention days accepts valid values."""
    monkeypatch.setenv("WORKSPACE_CLEANUP_RETENTION_DAYS", "14")
    assert get_workspace_cleanup_retention_days() == 14


def test_workspace_cleanup_retention_days_clamping_minimum(monkeypatch):
    """Test retention days clamps to minimum 1 day."""
    monkeypatch.setenv("WORKSPACE_CLEANUP_RETENTION_DAYS", "0")
    assert get_workspace_cleanup_retention_days() == 1

    monkeypatch.setenv("WORKSPACE_CLEANUP_RETENTION_DAYS", "-10")
    assert get_workspace_cleanup_retention_days() == 1


def test_workspace_cleanup_retention_days_clamping_maximum(monkeypatch):
    """Test retention days clamps to maximum 365 days."""
    monkeypatch.setenv("WORKSPACE_CLEANUP_RETENTION_DAYS", "500")
    assert get_workspace_cleanup_retention_days() == 365

    monkeypatch.setenv("WORKSPACE_CLEANUP_RETENTION_DAYS", "1000")
    assert get_workspace_cleanup_retention_days() == 365


def test_workspace_cleanup_retention_days_invalid_fallback(monkeypatch):
    """Test retention days falls back to default on invalid value."""
    monkeypatch.setenv("WORKSPACE_CLEANUP_RETENTION_DAYS", "invalid")
    assert get_workspace_cleanup_retention_days() == 7

    monkeypatch.setenv("WORKSPACE_CLEANUP_RETENTION_DAYS", "12.5")
    assert get_workspace_cleanup_retention_days() == 7


def test_workspace_cleanup_schedule_default(monkeypatch):
    """Test cleanup schedule defaults to 3am daily."""
    monkeypatch.delenv("WORKSPACE_CLEANUP_SCHEDULE", raising=False)
    assert get_workspace_cleanup_schedule() == "0 3 * * *"


def test_workspace_cleanup_schedule_custom(monkeypatch):
    """Test cleanup schedule accepts custom cron values."""
    monkeypatch.setenv("WORKSPACE_CLEANUP_SCHEDULE", "30 2 * * *")
    assert get_workspace_cleanup_schedule() == "30 2 * * *"

    monkeypatch.setenv("WORKSPACE_CLEANUP_SCHEDULE", "0 0 * * 0")  # Midnight Sundays
    assert get_workspace_cleanup_schedule() == "0 0 * * 0"
