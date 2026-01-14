"""Notion webhook handler service.

This module provides webhook event processing functionality:
- HMAC-SHA256 signature verification
- Webhook idempotency tracking
- Background event processing with short transactions

Architecture:
- Webhook endpoint returns immediately (<500ms)
- Background task processes event asynchronously
- Short transactions (idempotency check, API fetch, task enqueue)
- Reuses enqueue_task_from_notion_page() from task_service
"""

import hashlib
import hmac
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.notion import NotionClient
from app.config import get_notion_api_token
from app.database import async_session_factory
from app.models import NotionWebhookEvent
from app.schemas.webhook import NotionWebhookPayload
from app.services.notion_sync import extract_select
from app.services.task_service import enqueue_task_from_notion_page

log = structlog.get_logger()

# Constants
NOTION_STATUS_QUEUED = "Queued"


def verify_notion_webhook_signature(
    body: bytes,
    signature: str,
    secret: str,
) -> bool:
    """Verify Notion webhook signature using HMAC-SHA256.

    Args:
        body: Raw request body (bytes, not parsed JSON)
        signature: Signature from Notion-Webhook-Signature header
        secret: Shared secret from NOTION_WEBHOOK_SECRET env var

    Returns:
        True if signature valid, False otherwise

    Security:
        Uses constant-time comparison to prevent timing attacks
    """
    if not secret:
        log.warning("notion_webhook_secret_not_configured")
        return False  # Fail closed

    computed = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    is_valid = hmac.compare_digest(computed, signature or "")

    if not is_valid:
        log.warning(
            "webhook_signature_verification_failed",
            signature_provided=signature[:8] + "..." if signature else None,
            computed_signature=computed[:8] + "...",  # Log prefix only
        )

    return is_valid


async def is_duplicate_webhook(
    event_id: str,
    event_type: str,
    page_id: str,
    payload_dict: dict[str, Any],
    session: AsyncSession,
) -> bool:
    """Check if webhook event already processed (idempotency).

    Args:
        event_id: Notion webhook event ID
        event_type: Type of webhook event
        page_id: Notion page ID
        payload_dict: Full webhook payload as dict
        session: Database session (must be active transaction)

    Returns:
        True if duplicate (skip processing), False if new (process it)
    """
    result = await session.execute(
        select(NotionWebhookEvent).where(NotionWebhookEvent.event_id == event_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        log.info(
            "duplicate_webhook_detected",
            event_id=event_id,
            first_processed_at=existing.processed_at.isoformat(),
        )
        return True

    # Record this event
    event = NotionWebhookEvent(
        event_id=event_id,
        event_type=event_type,
        page_id=page_id,
        payload=payload_dict,
    )
    session.add(event)

    return False


async def process_notion_webhook_event(payload: NotionWebhookPayload) -> None:
    """Process Notion webhook event in background.

    Pattern:
        1. Check idempotency (short transaction)
        2. Fetch page from Notion API (outside transaction)
        3. Enqueue task if Status = "Queued" (short transaction)

    Args:
        payload: Validated webhook payload

    Returns:
        None (logs results)
    """
    correlation_id = str(uuid.uuid4())

    log.info(
        "webhook_processing_started",
        correlation_id=correlation_id,
        event_id=payload.event_id,
        event_type=payload.event_type,
        page_id=payload.page_id,
    )

    # Short transaction 1: Idempotency check
    if async_session_factory is None:
        log.error(
            "webhook_database_not_configured",
            correlation_id=correlation_id,
        )
        return

    try:
        async with async_session_factory() as session, session.begin():
            is_duplicate = await is_duplicate_webhook(
                event_id=payload.event_id,
                event_type=payload.event_type,
                page_id=payload.page_id,
                payload_dict=payload.model_dump(),
                session=session,
            )
    except IntegrityError:
        # Duplicate event_id - race condition between concurrent webhooks
        log.info(
            "webhook_duplicate_race_condition",
            correlation_id=correlation_id,
            event_id=payload.event_id,
        )
        return  # Skip processing

    if is_duplicate:
        log.info(
            "webhook_duplicate_skipped",
            correlation_id=correlation_id,
            event_id=payload.event_id,
        )
        return

    # Fetch full page details from Notion API (outside transaction)
    try:
        notion_api_token = get_notion_api_token()
        if not notion_api_token:
            log.error(
                "webhook_notion_token_missing",
                correlation_id=correlation_id,
                page_id=payload.page_id,
            )
            return

        notion_client = NotionClient(auth_token=notion_api_token)
        page = await notion_client.get_page(payload.page_id)
    except Exception as e:
        log.error(
            "webhook_notion_api_error",
            correlation_id=correlation_id,
            page_id=payload.page_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        # Don't raise - webhook already acknowledged
        return

    # Check if Status changed to "Queued"
    status = extract_select(page["properties"].get("Status"))

    if status != NOTION_STATUS_QUEUED:
        log.info(
            "webhook_status_not_queued",
            correlation_id=correlation_id,
            page_id=payload.page_id,
            status=status,
        )
        return  # Not a queuing event, ignore

    # Short transaction 2: Enqueue task
    if async_session_factory is None:
        log.error(
            "webhook_database_not_configured",
            correlation_id=correlation_id,
        )
        return

    async with async_session_factory() as session, session.begin():
        task = await enqueue_task_from_notion_page(page, session)

    if task:
        log.info(
            "webhook_task_enqueued",
            correlation_id=correlation_id,
            event_id=payload.event_id,
            page_id=payload.page_id,
            task_id=str(task.id),
            status=task.status.value,
        )
    else:
        log.warning(
            "webhook_task_not_enqueued",
            correlation_id=correlation_id,
            page_id=payload.page_id,
            reason="validation_failed_or_duplicate",
        )
