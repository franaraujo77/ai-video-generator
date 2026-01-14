"""Notion webhook payload schemas.

Defines Pydantic models for validating incoming Notion webhook events.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class NotionSelect(BaseModel):
    """Notion select option value."""

    name: str


class NotionPropertySelect(BaseModel):
    """Notion select property structure."""

    type: str
    select: NotionSelect


class NotionWebhookPayload(BaseModel):
    """Notion webhook event payload.

    Notion sends webhooks for database changes with this structure.
    Events are deduplicated using event_id.

    Supported event types:
    - page.created: New page added to database
    - page.updated: Page properties changed
    - page.archived: Page deleted or archived
    """

    event_id: str = Field(..., min_length=1, max_length=100)
    event_type: str = Field(..., pattern=r"^page\.(created|updated|archived)$")
    page_id: str = Field(..., min_length=32, max_length=36)  # UUID with or without dashes
    workspace_id: str
    timestamp: datetime
    properties: dict[str, NotionPropertySelect] = {}
