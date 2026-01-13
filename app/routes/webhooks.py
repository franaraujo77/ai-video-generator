"""Notion webhook routes.

This module provides FastAPI routes for receiving Notion webhook events:
- POST /api/v1/webhooks/notion - Main webhook endpoint

Pattern:
- Verify signature (fast, no DB)
- Parse payload (fast, validation)
- Queue background task (async processing)
- Return 200 immediately (<500ms)
"""

import os
import time

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.schemas.webhook import NotionWebhookPayload
from app.services.webhook_handler import (
    process_notion_webhook_event,
    verify_notion_webhook_signature,
)

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

NOTION_WEBHOOK_SECRET = os.environ.get("NOTION_WEBHOOK_SECRET", "")


@router.post("/notion")
async def handle_notion_webhook(
    request: Request, background_tasks: BackgroundTasks
) -> JSONResponse:
    """Handle Notion webhook events.

    Pattern:
        1. Verify signature (fast, no DB)
        2. Parse payload (fast, validation)
        3. Queue background task (async processing)
        4. Return 200 immediately (<500ms)

    Returns:
        200 OK: Webhook accepted and queued for processing
        401 Unauthorized: Invalid signature
        400 Bad Request: Invalid payload format
    """
    start_time = time.time()

    # Step 1: Verify signature
    signature = request.headers.get("Notion-Webhook-Signature", "")
    body = await request.body()

    if not verify_notion_webhook_signature(body, signature, NOTION_WEBHOOK_SECRET):
        log.warning(
            "webhook_unauthorized", signature=signature[:8] + "..." if signature else None
        )
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Step 2: Parse and validate payload
    try:
        payload = NotionWebhookPayload.model_validate_json(body)
    except ValidationError as e:
        log.warning(
            "webhook_invalid_payload",
            error=str(e),
            body=body.decode()[:200],  # Log first 200 chars
        )
        raise HTTPException(status_code=400, detail="Invalid payload format") from e

    # Step 3: Queue background task
    background_tasks.add_task(process_notion_webhook_event, payload)

    # Step 4: Return immediately
    elapsed_ms = (time.time() - start_time) * 1000

    log.info(
        "webhook_accepted",
        event_id=payload.event_id,
        event_type=payload.event_type,
        page_id=payload.page_id,
        elapsed_ms=elapsed_ms,
    )

    if elapsed_ms > 500:
        log.warning("webhook_slow_response", elapsed_ms=elapsed_ms, target_ms=500)

    return JSONResponse(
        status_code=200, content={"status": "accepted", "event_id": payload.event_id}
    )
