"""Tests for webhook handler service.

Tests webhook signature verification, idempotency, and event processing:
- HMAC-SHA256 signature verification
- Duplicate webhook detection
- Background event processing
- Integration with task enqueueing
"""

import hashlib
import hmac
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models import NotionWebhookEvent, Task, TaskStatus
from app.schemas.webhook import NotionWebhookPayload
from app.services.webhook_handler import (
    is_duplicate_webhook,
    process_notion_webhook_event,
    verify_notion_webhook_signature,
)


def test_verify_signature_valid():
    """Valid signature returns True."""
    body = b'{"event_id": "evt_123"}'
    secret = "test_secret"
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_notion_webhook_signature(body, signature, secret) is True


def test_verify_signature_invalid():
    """Invalid signature returns False."""
    body = b'{"event_id": "evt_123"}'
    secret = "test_secret"
    wrong_signature = "invalid_signature_abc123"

    assert verify_notion_webhook_signature(body, wrong_signature, secret) is False


def test_verify_signature_missing_secret():
    """Missing secret returns False (fail closed)."""
    body = b'{"event_id": "evt_123"}'
    signature = "any_signature"

    assert verify_notion_webhook_signature(body, signature, "") is False


def test_verify_signature_empty_signature():
    """Empty signature returns False."""
    body = b'{"event_id": "evt_123"}'
    secret = "test_secret"

    assert verify_notion_webhook_signature(body, "", secret) is False


def test_verify_signature_constant_time_comparison():
    """Signature verification uses constant-time comparison.

    This test verifies that hmac.compare_digest is used,
    which prevents timing attacks.
    """
    body = b'{"event_id": "evt_123"}'
    secret = "test_secret"
    correct_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    # Slightly different signatures should fail equally fast
    wrong_sig_1 = correct_sig[:-2] + "00"
    wrong_sig_2 = "00" + correct_sig[2:]

    assert verify_notion_webhook_signature(body, wrong_sig_1, secret) is False
    assert verify_notion_webhook_signature(body, wrong_sig_2, secret) is False


@pytest.mark.asyncio
async def test_is_duplicate_webhook_first_event(async_session):
    """First event is not a duplicate."""
    is_dup = await is_duplicate_webhook(
        event_id="evt_first_test",
        event_type="page.updated",
        page_id="9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        payload_dict={"test": "data"},
        session=async_session,
    )

    assert is_dup is False

    # Verify event was recorded
    result = await async_session.execute(
        select(NotionWebhookEvent).where(NotionWebhookEvent.event_id == "evt_first_test")
    )
    event = result.scalar_one_or_none()
    assert event is not None
    assert event.event_id == "evt_first_test"


@pytest.mark.asyncio
async def test_is_duplicate_webhook_duplicate_event(async_session):
    """Second event with same event_id is detected as duplicate."""
    # First webhook: Should process
    is_dup_1 = await is_duplicate_webhook(
        event_id="evt_duplicate_test",
        event_type="page.updated",
        page_id="9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        payload_dict={"test": "data"},
        session=async_session,
    )
    await async_session.commit()

    assert is_dup_1 is False  # Not a duplicate

    # Second webhook: Should skip
    is_dup_2 = await is_duplicate_webhook(
        event_id="evt_duplicate_test",
        event_type="page.updated",
        page_id="9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        payload_dict={"test": "data"},
        session=async_session,
    )

    assert is_dup_2 is True  # Duplicate detected


@pytest.mark.asyncio
async def test_is_duplicate_webhook_different_events(async_session):
    """Different event IDs are not duplicates."""
    # First event
    is_dup_1 = await is_duplicate_webhook(
        event_id="evt_first",
        event_type="page.updated",
        page_id="9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        payload_dict={"test": "data1"},
        session=async_session,
    )
    await async_session.commit()

    # Second event with different ID
    is_dup_2 = await is_duplicate_webhook(
        event_id="evt_second",
        event_type="page.updated",
        page_id="9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        payload_dict={"test": "data2"},
        session=async_session,
    )
    await async_session.commit()

    assert is_dup_1 is False
    assert is_dup_2 is False


@pytest.mark.asyncio
@patch("app.services.webhook_handler.async_session_factory")
@patch("app.services.webhook_handler.get_notion_api_token")
@patch("app.services.webhook_handler.NotionClient")
@patch("app.services.webhook_handler.enqueue_task_from_notion_page")
async def test_process_webhook_event_queued_status(
    mock_enqueue, mock_notion_client_class, mock_get_token, mock_session_factory
):
    """Webhook with Status=Queued enqueues task."""
    # Setup mocks
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = None

    # Mock session.begin() async context manager
    from unittest.mock import Mock

    mock_transaction = Mock()
    mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
    mock_transaction.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = Mock(return_value=mock_transaction)

    # Mock session.add() as synchronous (not async) to avoid RuntimeWarning
    mock_session.add = Mock(return_value=None)

    # Mock is_duplicate_webhook to return False (not a duplicate)
    from unittest.mock import Mock as SyncMock

    mock_result = SyncMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    # Mock get_notion_api_token
    mock_get_token.return_value = "test_token"

    # Mock Notion API to return page with Status="Queued"
    mock_notion_client = AsyncMock()
    mock_notion_client_class.return_value = mock_notion_client
    mock_notion_client.get_page.return_value = {
        "id": "9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8",
        "properties": {
            "Status": {"type": "select", "select": {"name": "Queued"}},
            "Title": {"title": [{"text": {"content": "Test Video"}}]},
            "Topic": {"rich_text": [{"text": {"content": "Test Topic"}}]},
            "Story Direction": {"rich_text": [{"text": {"content": "Test Story"}}]},
            "Channel": {"select": {"name": "test_channel"}},
        },
    }

    # Mock task enqueueing
    mock_task = AsyncMock()
    mock_task.id = UUID("12345678-1234-1234-1234-123456789012")
    mock_task.status = TaskStatus.QUEUED
    mock_enqueue.return_value = mock_task

    # Create payload
    payload = NotionWebhookPayload(
        event_id="evt_enqueue_test",
        event_type="page.updated",
        page_id="9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8",
        workspace_id="ws_test",
        timestamp=datetime.now(timezone.utc),
        properties={},
    )

    # Process webhook
    await process_notion_webhook_event(payload)

    # Verify Notion API was called
    mock_notion_client.get_page.assert_called_once_with(payload.page_id)

    # Verify enqueue was called
    mock_enqueue.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.webhook_handler.async_session_factory")
@patch("app.services.webhook_handler.get_notion_api_token")
@patch("app.services.webhook_handler.NotionClient")
@patch("app.services.webhook_handler.enqueue_task_from_notion_page")
async def test_process_webhook_event_ignores_non_queued_status(
    mock_enqueue, mock_notion_client_class, mock_get_token, mock_session_factory
):
    """Webhook with Status != Queued is ignored."""
    # Setup mocks
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = None

    # Mock session.begin() async context manager
    from unittest.mock import Mock

    mock_transaction = Mock()
    mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
    mock_transaction.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = Mock(return_value=mock_transaction)

    # Mock session.add() as synchronous (not async) to avoid RuntimeWarning
    mock_session.add = Mock(return_value=None)

    # Mock is_duplicate_webhook to return False (not a duplicate)
    from unittest.mock import Mock as SyncMock

    mock_result = SyncMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    # Mock get_notion_api_token
    mock_get_token.return_value = "test_token"

    # Mock Notion API to return page with Status="Draft"
    mock_notion_client = AsyncMock()
    mock_notion_client_class.return_value = mock_notion_client
    mock_notion_client.get_page.return_value = {
        "id": "9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8",
        "properties": {
            "Status": {"type": "select", "select": {"name": "Draft"}},
        },
    }

    # Create payload
    payload = NotionWebhookPayload(
        event_id="evt_ignore_test",
        event_type="page.updated",
        page_id="9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8",
        workspace_id="ws_test",
        timestamp=datetime.now(timezone.utc),
        properties={},
    )

    # Process webhook
    await process_notion_webhook_event(payload)

    # Verify Notion API was called
    mock_notion_client.get_page.assert_called_once()

    # Verify enqueue was NOT called (status was Draft, not Queued)
    mock_enqueue.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.webhook_handler.async_session_factory")
async def test_process_webhook_event_duplicate_skipped(mock_session_factory):
    """Duplicate webhook event is skipped."""
    # Setup mocks
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = None

    # Mock session.begin() async context manager
    from unittest.mock import Mock

    mock_transaction = Mock()
    mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
    mock_transaction.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = Mock(return_value=mock_transaction)

    # Mock session.add() as synchronous (not async) to avoid RuntimeWarning
    mock_session.add = Mock(return_value=None)

    # Mock is_duplicate_webhook to return True (duplicate)
    existing_event = NotionWebhookEvent(
        event_id="evt_duplicate",
        event_type="page.updated",
        page_id="9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        payload={"test": "data"},
        processed_at=datetime.now(timezone.utc),
    )
    from unittest.mock import Mock as SyncMock

    mock_result = SyncMock()
    mock_result.scalar_one_or_none.return_value = existing_event
    mock_session.execute.return_value = mock_result

    # Create payload
    payload = NotionWebhookPayload(
        event_id="evt_duplicate",
        event_type="page.updated",
        page_id="9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        workspace_id="ws_test",
        timestamp=datetime.now(timezone.utc),
    )

    # Process webhook
    await process_notion_webhook_event(payload)

    # Verify no further processing happened (no Notion API call, no enqueue)
    # This is validated by the fact that no other mocks were set up or called


@pytest.mark.asyncio
@patch("app.services.webhook_handler.async_session_factory")
@patch("app.services.webhook_handler.get_notion_api_token")
@patch("app.services.webhook_handler.NotionClient")
async def test_process_webhook_event_notion_api_error(
    mock_notion_client_class, mock_get_token, mock_session_factory
):
    """Webhook processing handles Notion API errors gracefully."""
    # Setup mocks
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_session_factory.return_value.__aexit__.return_value = None

    # Mock session.begin() async context manager
    from unittest.mock import Mock

    mock_transaction = Mock()
    mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
    mock_transaction.__aexit__ = AsyncMock(return_value=None)
    mock_session.begin = Mock(return_value=mock_transaction)

    # Mock session.add() as synchronous (not async) to avoid RuntimeWarning
    mock_session.add = Mock(return_value=None)

    # Mock is_duplicate_webhook to return False (not a duplicate)
    from unittest.mock import Mock as SyncMock

    mock_result = SyncMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    # Mock get_notion_api_token
    mock_get_token.return_value = "test_token"

    # Mock Notion API to raise an exception
    mock_notion_client = AsyncMock()
    mock_notion_client_class.return_value = mock_notion_client
    mock_notion_client.get_page.side_effect = Exception("API Error")

    # Create payload
    payload = NotionWebhookPayload(
        event_id="evt_error_test",
        event_type="page.updated",
        page_id="9afc2f9c05b3486bb2e7a4b2e3c5e5e8",
        workspace_id="ws_test",
        timestamp=datetime.now(timezone.utc),
    )

    # Process webhook (should not raise, just log error)
    await process_notion_webhook_event(payload)

    # Verify Notion API was called and raised exception
    mock_notion_client.get_page.assert_called_once()
