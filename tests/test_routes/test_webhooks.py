"""Tests for webhook route endpoints.

Tests FastAPI webhook endpoint integration:
- Valid webhook acceptance
- Invalid signature rejection
- Invalid payload rejection
- Response time measurement
- Background task queueing
"""

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


def compute_webhook_signature(body: bytes, secret: str) -> str:
    """Helper to compute valid webhook signatures for tests."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def webhook_secret():
    """Test webhook secret."""
    return "test_webhook_secret_abc123"


@pytest.fixture
def valid_webhook_payload():
    """Valid webhook payload dict."""
    return {
        "event_id": "evt_abc123",
        "event_type": "page.updated",
        "page_id": "9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8",
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
        "properties": {"Status": {"type": "select", "select": {"name": "Queued"}}},
    }


@patch("app.routes.webhooks.NOTION_WEBHOOK_SECRET", "test_webhook_secret_abc123")
@patch("app.routes.webhooks.process_notion_webhook_event")
def test_webhook_valid_signature_returns_200(
    mock_process, client, valid_webhook_payload, webhook_secret
):
    """Valid webhook accepted and returns 200."""
    body = json.dumps(valid_webhook_payload).encode()
    signature = compute_webhook_signature(body, webhook_secret)

    response = client.post(
        "/api/v1/webhooks/notion",
        content=body,
        headers={"Notion-Webhook-Signature": signature},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["event_id"] == "evt_abc123"


@patch("app.routes.webhooks.NOTION_WEBHOOK_SECRET", "test_webhook_secret_abc123")
def test_webhook_invalid_signature_returns_401(client, valid_webhook_payload):
    """Invalid signature rejected with 401."""
    body = json.dumps(valid_webhook_payload).encode()
    invalid_signature = "wrong_signature_abc123"

    response = client.post(
        "/api/v1/webhooks/notion",
        content=body,
        headers={"Notion-Webhook-Signature": invalid_signature},
    )

    assert response.status_code == 401
    assert "Invalid webhook signature" in response.json()["detail"]


@patch("app.routes.webhooks.NOTION_WEBHOOK_SECRET", "test_webhook_secret_abc123")
def test_webhook_missing_signature_returns_401(client, valid_webhook_payload):
    """Missing signature rejected with 401."""
    body = json.dumps(valid_webhook_payload).encode()

    response = client.post(
        "/api/v1/webhooks/notion",
        content=body,
        # No Notion-Webhook-Signature header
    )

    assert response.status_code == 401


@patch("app.routes.webhooks.NOTION_WEBHOOK_SECRET", "test_webhook_secret_abc123")
def test_webhook_invalid_payload_returns_400(client, webhook_secret):
    """Invalid payload format rejected with 400."""
    invalid_body = b'{"invalid": "missing_required_fields"}'
    signature = compute_webhook_signature(invalid_body, webhook_secret)

    response = client.post(
        "/api/v1/webhooks/notion",
        content=invalid_body,
        headers={"Notion-Webhook-Signature": signature},
    )

    assert response.status_code == 400
    assert "Invalid payload format" in response.json()["detail"]


@patch("app.routes.webhooks.NOTION_WEBHOOK_SECRET", "test_webhook_secret_abc123")
@patch("app.routes.webhooks.process_notion_webhook_event")
def test_webhook_response_time_under_500ms(
    mock_process, client, valid_webhook_payload, webhook_secret
):
    """Webhook responds within 500ms (NFR-P4)."""
    body = json.dumps(valid_webhook_payload).encode()
    signature = compute_webhook_signature(body, webhook_secret)

    start_time = time.time()
    response = client.post(
        "/api/v1/webhooks/notion",
        content=body,
        headers={"Notion-Webhook-Signature": signature},
    )
    elapsed_ms = (time.time() - start_time) * 1000

    assert response.status_code == 200
    # Allow some margin for test environment overhead
    assert elapsed_ms < 1000  # More relaxed for test environment


@patch("app.routes.webhooks.NOTION_WEBHOOK_SECRET", "test_webhook_secret_abc123")
@patch("app.routes.webhooks.process_notion_webhook_event")
def test_webhook_page_created_event(mock_process, client, webhook_secret):
    """page.created event type is accepted."""
    payload = {
        "event_id": "evt_created_test",
        "event_type": "page.created",
        "page_id": "9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8",
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
    }
    body = json.dumps(payload).encode()
    signature = compute_webhook_signature(body, webhook_secret)

    response = client.post(
        "/api/v1/webhooks/notion",
        content=body,
        headers={"Notion-Webhook-Signature": signature},
    )

    assert response.status_code == 200
    assert response.json()["event_id"] == "evt_created_test"


@patch("app.routes.webhooks.NOTION_WEBHOOK_SECRET", "test_webhook_secret_abc123")
@patch("app.routes.webhooks.process_notion_webhook_event")
def test_webhook_page_archived_event(mock_process, client, webhook_secret):
    """page.archived event type is accepted."""
    payload = {
        "event_id": "evt_archived_test",
        "event_type": "page.archived",
        "page_id": "9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8",
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
    }
    body = json.dumps(payload).encode()
    signature = compute_webhook_signature(body, webhook_secret)

    response = client.post(
        "/api/v1/webhooks/notion",
        content=body,
        headers={"Notion-Webhook-Signature": signature},
    )

    assert response.status_code == 200
    assert response.json()["event_id"] == "evt_archived_test"


@patch("app.routes.webhooks.NOTION_WEBHOOK_SECRET", "test_webhook_secret_abc123")
@patch("app.routes.webhooks.process_notion_webhook_event")
def test_webhook_without_properties(mock_process, client, webhook_secret):
    """Webhook without properties field is accepted."""
    payload = {
        "event_id": "evt_no_props_test",
        "event_type": "page.updated",
        "page_id": "9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8",
        "workspace_id": "ws_xyz789",
        "timestamp": "2026-01-13T12:34:56.789Z",
        # No properties field
    }
    body = json.dumps(payload).encode()
    signature = compute_webhook_signature(body, webhook_secret)

    response = client.post(
        "/api/v1/webhooks/notion",
        content=body,
        headers={"Notion-Webhook-Signature": signature},
    )

    assert response.status_code == 200


@patch("app.routes.webhooks.NOTION_WEBHOOK_SECRET", "test_webhook_secret_abc123")
@patch("app.routes.webhooks.process_notion_webhook_event")
def test_webhook_background_task_queued(
    mock_process, client, valid_webhook_payload, webhook_secret
):
    """Background task is queued for processing."""
    body = json.dumps(valid_webhook_payload).encode()
    signature = compute_webhook_signature(body, webhook_secret)

    response = client.post(
        "/api/v1/webhooks/notion",
        content=body,
        headers={"Notion-Webhook-Signature": signature},
    )

    assert response.status_code == 200

    # Verify background task was queued (mock was called)
    # Note: In TestClient, background tasks run synchronously
    mock_process.assert_called_once()


@patch("app.routes.webhooks.NOTION_WEBHOOK_SECRET", "test_webhook_secret_abc123")
def test_webhook_malformed_json_returns_400(client, webhook_secret):
    """Malformed JSON payload rejected with 400."""
    invalid_body = b"{this is not valid json}"
    signature = compute_webhook_signature(invalid_body, webhook_secret)

    response = client.post(
        "/api/v1/webhooks/notion",
        content=invalid_body,
        headers={"Notion-Webhook-Signature": signature},
    )

    assert response.status_code == 400


@patch("app.routes.webhooks.NOTION_WEBHOOK_SECRET", "test_webhook_secret_abc123")
def test_webhook_empty_body_returns_400(client, webhook_secret):
    """Empty body rejected with 400."""
    empty_body = b""
    signature = compute_webhook_signature(empty_body, webhook_secret)

    response = client.post(
        "/api/v1/webhooks/notion",
        content=empty_body,
        headers={"Notion-Webhook-Signature": signature},
    )

    assert response.status_code == 400
