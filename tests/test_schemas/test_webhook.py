"""Tests for Notion webhook payload validation schemas.

Tests webhook schema validation:
- Valid payload parsing
- Invalid event type rejection
- Missing required fields
- Field validation (min/max length, patterns)
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.webhook import NotionWebhookPayload


def test_notion_webhook_payload_valid():
    """Valid payload parses successfully."""
    data = {
        "event_id": "evt_abc123",
        "event_type": "page.updated",
        "page_id": "9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
    }

    payload = NotionWebhookPayload(**data)

    assert payload.event_id == "evt_abc123"
    assert payload.event_type == "page.updated"
    assert payload.page_id == "9afc2f9c05b3486bb2e7a4b2e3c5e5e8"
    assert payload.workspace_id == "ws_xyz789"
    assert isinstance(payload.timestamp, datetime)


def test_notion_webhook_payload_with_properties():
    """Valid payload with properties parses successfully."""
    data = {
        "event_id": "evt_abc123",
        "event_type": "page.updated",
        "page_id": "9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
        "properties": {
            "Status": {"type": "select", "select": {"name": "Queued"}}
        },
    }

    payload = NotionWebhookPayload(**data)

    assert payload.properties is not None
    assert "Status" in payload.properties
    assert payload.properties["Status"].type == "select"
    assert payload.properties["Status"].select.name == "Queued"


def test_notion_webhook_payload_page_created():
    """page.created event type is valid."""
    data = {
        "event_id": "evt_abc123",
        "event_type": "page.created",
        "page_id": "9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
    }

    payload = NotionWebhookPayload(**data)
    assert payload.event_type == "page.created"


def test_notion_webhook_payload_page_archived():
    """page.archived event type is valid."""
    data = {
        "event_id": "evt_abc123",
        "event_type": "page.archived",
        "page_id": "9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
    }

    payload = NotionWebhookPayload(**data)
    assert payload.event_type == "page.archived"


def test_notion_webhook_payload_invalid_event_type():
    """Invalid event_type raises ValidationError."""
    data = {
        "event_id": "evt_abc123",
        "event_type": "invalid_type",  # Not page.created/updated/archived
        "page_id": "9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
    }

    with pytest.raises(ValidationError) as exc_info:
        NotionWebhookPayload(**data)

    # Check that event_type field is in the error
    errors = exc_info.value.errors()
    assert any(error["loc"] == ("event_type",) for error in errors)


def test_notion_webhook_payload_missing_event_id():
    """Missing event_id raises ValidationError."""
    data = {
        # Missing event_id
        "event_type": "page.updated",
        "page_id": "9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
    }

    with pytest.raises(ValidationError) as exc_info:
        NotionWebhookPayload(**data)

    errors = exc_info.value.errors()
    assert any(error["loc"] == ("event_id",) for error in errors)


def test_notion_webhook_payload_missing_event_type():
    """Missing event_type raises ValidationError."""
    data = {
        "event_id": "evt_abc123",
        # Missing event_type
        "page_id": "9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
    }

    with pytest.raises(ValidationError) as exc_info:
        NotionWebhookPayload(**data)

    errors = exc_info.value.errors()
    assert any(error["loc"] == ("event_type",) for error in errors)


def test_notion_webhook_payload_missing_page_id():
    """Missing page_id raises ValidationError."""
    data = {
        "event_id": "evt_abc123",
        "event_type": "page.updated",
        # Missing page_id
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
    }

    with pytest.raises(ValidationError) as exc_info:
        NotionWebhookPayload(**data)

    errors = exc_info.value.errors()
    assert any(error["loc"] == ("page_id",) for error in errors)


def test_notion_webhook_payload_empty_properties():
    """Empty properties dict is valid (optional field)."""
    data = {
        "event_id": "evt_abc123",
        "event_type": "page.updated",
        "page_id": "9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
        "properties": {},
    }

    payload = NotionWebhookPayload(**data)
    assert payload.properties == {}


def test_notion_webhook_payload_properties_optional():
    """Properties field is optional."""
    data = {
        "event_id": "evt_abc123",
        "event_type": "page.updated",
        "page_id": "9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
        # No properties field
    }

    payload = NotionWebhookPayload(**data)
    assert payload.properties == {}


def test_notion_webhook_payload_page_id_with_dashes():
    """Page ID with dashes is valid (UUID format)."""
    data = {
        "event_id": "evt_abc123",
        "event_type": "page.updated",
        "page_id": "9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8",  # With dashes
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
    }

    payload = NotionWebhookPayload(**data)
    assert payload.page_id == "9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8"


def test_notion_webhook_payload_page_id_without_dashes():
    """Page ID without dashes is valid (32 chars)."""
    data = {
        "event_id": "evt_abc123",
        "event_type": "page.updated",
        "page_id": "9afc2f9c05b3486bb2e7a4b2e3c5e5e8",  # Without dashes
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
    }

    payload = NotionWebhookPayload(**data)
    assert payload.page_id == "9afc2f9c05b3486bb2e7a4b2e3c5e5e8"
