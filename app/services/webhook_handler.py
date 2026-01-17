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

from datetime import datetime, timezone

from app.clients.notion import NotionClient
from app.config import get_notion_api_token
from app.database import async_session_factory
from app.models import NotionWebhookEvent, Task, TaskStatus
from app.schemas.webhook import NotionWebhookPayload
from app.services.notion_sync import extract_select
from app.services.task_service import enqueue_task_from_notion_page

log = structlog.get_logger()

# Constants
NOTION_STATUS_QUEUED = "Queued"
NOTION_APPROVAL_STATUSES = {
    "Assets Approved": "assets_approved",
    "Videos Approved": "video_approved",
    "Audio Approved": "audio_approved",
    "Review Approved": "approved",  # Final approval
}
NOTION_REJECTION_STATUSES = {
    "Asset Error": "asset_error",
    "Video Error": "video_error",
    "Audio Error": "audio_error",
    "Upload Error": "upload_error",
}


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


async def _handle_approval_status_change(
    page_id: str,
    notion_status: str,
    correlation_id: str,
) -> None:
    """Handle approval status changes from Notion.

    When user approves assets/videos/audio in Notion by changing status to
    "Assets Approved", "Videos Approved", or "Audio Approved", this function:
    1. Finds the task by notion_page_id
    2. Updates internal task status to approved state
    3. Sets review_completed_at timestamp
    4. Re-queues the task so pipeline can resume from next step

    Args:
        page_id: Notion page ID
        notion_status: Notion status value ("Assets Approved", etc.)
        correlation_id: Correlation ID for logging

    Story 5.3: Asset Review Interface - Approval Flow
    """
    internal_status_str = NOTION_APPROVAL_STATUSES.get(notion_status)
    if not internal_status_str:
        log.error(
            "approval_status_mapping_missing",
            correlation_id=correlation_id,
            notion_status=notion_status,
        )
        return

    try:
        internal_status = TaskStatus(internal_status_str)
    except ValueError:
        log.error(
            "invalid_internal_status",
            correlation_id=correlation_id,
            internal_status_str=internal_status_str,
        )
        return

    if async_session_factory is None:
        log.error(
            "approval_database_not_configured",
            correlation_id=correlation_id,
        )
        return

    async with async_session_factory() as session, session.begin():
        # Find task by notion_page_id
        result = await session.execute(
            select(Task).where(Task.notion_page_id == page_id)
        )
        task = result.scalar_one_or_none()

        if not task:
            log.warning(
                "approval_task_not_found",
                correlation_id=correlation_id,
                page_id=page_id,
                notion_status=notion_status,
            )
            return

        # Set review_completed_at timestamp
        old_status = task.status
        task.review_completed_at = datetime.now(timezone.utc)

        # Calculate review duration if review_started_at exists
        if task.review_started_at:
            duration = (task.review_completed_at - task.review_started_at).total_seconds()
        else:
            duration = None

        # Re-queue task so pipeline can resume from next step (Story 5.3 Task 4.2)
        # The pipeline orchestrator will check step completion metadata and skip
        # completed steps, resuming from the next step after the approved gate
        task.status = TaskStatus.QUEUED

        log.info(
            "review_approved_task_requeued",
            correlation_id=correlation_id,
            task_id=str(task.id),
            page_id=page_id,
            notion_status=notion_status,
            old_status=old_status.value,
            new_status=TaskStatus.QUEUED.value,
            review_duration_seconds=duration,
        )


async def _handle_rejection_status_change(
    page_id: str,
    notion_status: str,
    correlation_id: str,
    page: dict[str, Any],
) -> None:
    """Handle rejection status changes from Notion.

    When user rejects assets/videos/audio in Notion by changing status to
    "Asset Error", "Video Error", or "Audio Error", this function:
    1. Finds the task by notion_page_id
    2. Extracts rejection reason from "Error Log" property in Notion
    3. Appends rejection reason to task.error_log
    4. Updates internal task status to error state
    5. Sets review_completed_at timestamp

    Args:
        page_id: Notion page ID
        notion_status: Notion status value ("Asset Error", etc.)
        correlation_id: Correlation ID for logging
        page: Full Notion page data (for extracting Error Log)

    Story 5.3: Asset Review Interface - Rejection Flow
    """
    internal_status_str = NOTION_REJECTION_STATUSES.get(notion_status)
    if not internal_status_str:
        log.error(
            "rejection_status_mapping_missing",
            correlation_id=correlation_id,
            notion_status=notion_status,
        )
        return

    try:
        internal_status = TaskStatus(internal_status_str)
    except ValueError:
        log.error(
            "invalid_internal_status",
            correlation_id=correlation_id,
            internal_status_str=internal_status_str,
        )
        return

    # Extract error log from Notion "Error Log" property
    error_log_property = page.get("properties", {}).get("Error Log", {})
    rich_text = error_log_property.get("rich_text", [])
    rejection_reason = ""
    if rich_text:
        rejection_reason = "".join([text.get("plain_text", "") for text in rich_text])

    if async_session_factory is None:
        log.error(
            "rejection_database_not_configured",
            correlation_id=correlation_id,
        )
        return

    async with async_session_factory() as session, session.begin():
        # Find task by notion_page_id
        result = await session.execute(
            select(Task).where(Task.notion_page_id == page_id)
        )
        task = result.scalar_one_or_none()

        if not task:
            log.warning(
                "rejection_task_not_found",
                correlation_id=correlation_id,
                page_id=page_id,
                notion_status=notion_status,
            )
            return

        # Set review_completed_at timestamp
        old_status = task.status
        task.review_completed_at = datetime.now(timezone.utc)

        # Calculate review duration if review_started_at exists
        if task.review_started_at:
            duration = (task.review_completed_at - task.review_started_at).total_seconds()
        else:
            duration = None

        # Append rejection reason to error_log (Story 5.3 Task 5.3)
        current_log = task.error_log or ""
        timestamp = datetime.now(timezone.utc).isoformat()
        if rejection_reason.strip():
            new_entry = f"[{timestamp}] {notion_status}: {rejection_reason.strip()}"
        else:
            new_entry = f"[{timestamp}] {notion_status}: No rejection reason provided"
        task.error_log = f"{current_log}\n{new_entry}".strip()

        # Update task status to error state
        task.status = internal_status

        log.info(
            "review_rejected_task_marked_error",
            correlation_id=correlation_id,
            task_id=str(task.id),
            page_id=page_id,
            notion_status=notion_status,
            old_status=old_status.value,
            new_status=internal_status.value,
            review_duration_seconds=duration,
            rejection_reason=rejection_reason[:200] if rejection_reason else None,  # Truncate for logging
        )


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

    # Check status from Notion page
    status = extract_select(page["properties"].get("Status"))

    # Handle "Queued" status - create/enqueue new task
    if status == NOTION_STATUS_QUEUED:
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
        return

    # Handle approval status changes - Story 5.3: Asset Review Interface
    if status in NOTION_APPROVAL_STATUSES:
        await _handle_approval_status_change(
            page_id=payload.page_id,
            notion_status=status,
            correlation_id=correlation_id,
        )
        return

    # Handle rejection status changes - Story 5.3: Asset Review Interface
    if status in NOTION_REJECTION_STATUSES:
        await _handle_rejection_status_change(
            page_id=payload.page_id,
            notion_status=status,
            correlation_id=correlation_id,
            page=page,
        )
        return

    # Status not relevant to task lifecycle
    log.info(
        "webhook_status_ignored",
        correlation_id=correlation_id,
        page_id=payload.page_id,
        status=status,
        reason="not_queued_approval_or_rejection",
    )
