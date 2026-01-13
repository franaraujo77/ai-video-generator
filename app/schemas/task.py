"""Pydantic schemas for Task model validation and serialization.

This module defines Pydantic v2 schemas for creating, updating, and returning
Task model instances via the FastAPI orchestration API.

Schema Naming Convention:
    - TaskCreate: For POST requests (creating new tasks)
    - TaskUpdate: For PATCH requests (partial updates)
    - TaskResponse: For API responses (serializing from database)
    - TaskInDB: Internal schema matching database model exactly

All schemas use Pydantic v2 syntax with model_config instead of class Config.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import PriorityLevel, TaskStatus


class TaskCreate(BaseModel):
    """Schema for creating a new task.

    Used in POST /api/v1/tasks endpoint. Requires all metadata fields
    from Notion (notion_page_id, title, topic, story_direction) and
    associates task with a channel via channel_id.

    Notion Integration:
        notion_page_id must be exactly 32 characters (UUID without dashes).
        Example: "9afc2f9c05b3486bb2e7a4b2e3c5e5e8"

    Defaults:
        - status: TaskStatus.DRAFT (tasks start in draft state)
        - priority: PriorityLevel.NORMAL (most videos are normal priority)
    """

    model_config = ConfigDict(from_attributes=True)

    channel_id: UUID = Field(
        ...,
        description="UUID of the channel this task belongs to (references channels.id)",
    )
    notion_page_id: str = Field(
        ...,
        min_length=32,
        max_length=32,
        description="Notion page UUID without dashes (32 chars). Unique constraint.",
        examples=["9afc2f9c05b3486bb2e7a4b2e3c5e5e8"],
    )
    title: str = Field(
        ...,
        max_length=255,
        description="Video title from Notion (255 char limit)",
        examples=["Bulbasaur: The Garden Pokémon"],
    )
    topic: str = Field(
        ...,
        max_length=500,
        description="Video topic/category (500 char limit)",
        examples=["Pokémon Nature Documentary"],
    )
    story_direction: str = Field(
        ...,
        description="Rich text story direction from Notion (unlimited length)",
        examples=[
            "Create a David Attenborough-style nature documentary about Bulbasaur's "
            "lifecycle, habitat, and behavior in its natural environment."
        ],
    )
    priority: PriorityLevel = Field(
        default=PriorityLevel.NORMAL,
        description="Task priority (high/normal/low). Default: normal.",
    )


class TaskUpdate(BaseModel):
    """Schema for updating an existing task.

    Used in PATCH /api/v1/tasks/{task_id} endpoint. All fields are optional
    to support partial updates. Common use cases:
        - Status transitions (draft → queued, generating_assets → assets_ready, etc.)
        - Appending error messages to error_log
        - Setting youtube_url after successful upload
        - Changing priority (e.g., low → high for urgent content)

    Note:
        Use exclude_none=True to omit null values from JSON serialization.
        This prevents accidentally clearing fields with null values.
    """

    model_config = ConfigDict(from_attributes=True, exclude_none=True)

    status: TaskStatus | None = Field(
        default=None,
        description="Update task status (26-value enum)",
    )
    priority: PriorityLevel | None = Field(
        default=None,
        description="Update task priority (high/normal/low)",
    )
    error_log: str | None = Field(
        default=None,
        description="Append error message to log (append-only pattern)",
    )
    youtube_url: str | None = Field(
        default=None,
        max_length=255,
        description="Set YouTube URL after successful upload",
        examples=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
    )


class TaskResponse(BaseModel):
    """Schema for Task API responses.

    Used in GET /api/v1/tasks endpoints. Returns full task data including
    timestamps and all metadata. This is the primary schema for serializing
    Task models from the database.

    Serialization:
        Uses from_attributes=True to load directly from SQLAlchemy models.
        Enum values are serialized as strings (e.g., "draft", "high").
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(
        ...,
        description="Task UUID (primary key)",
    )
    channel_id: UUID = Field(
        ...,
        description="Channel UUID this task belongs to",
    )
    notion_page_id: str = Field(
        ...,
        description="Notion page UUID (32 chars, unique)",
    )
    title: str = Field(
        ...,
        description="Video title",
    )
    topic: str = Field(
        ...,
        description="Video topic/category",
    )
    story_direction: str = Field(
        ...,
        description="Story direction from Notion",
    )
    status: TaskStatus = Field(
        ...,
        description="Current pipeline status (26-value enum)",
    )
    priority: PriorityLevel = Field(
        ...,
        description="Task priority (high/normal/low)",
    )
    error_log: str | None = Field(
        default=None,
        description="Error history log (nullable)",
    )
    youtube_url: str | None = Field(
        default=None,
        description="Published YouTube URL (nullable)",
    )
    created_at: datetime = Field(
        ...,
        description="Task creation timestamp (UTC)",
    )
    updated_at: datetime = Field(
        ...,
        description="Last update timestamp (UTC)",
    )


class TaskInDB(TaskResponse):
    """Schema matching Task model exactly (internal use).

    Extends TaskResponse with no additional fields. Used for type checking
    and internal operations where we need to distinguish between API responses
    and database representations.

    Note:
        In this case TaskInDB and TaskResponse are identical because we expose
        all Task fields in the API. In future, if we add internal-only fields
        (e.g., internal_notes, processing_metadata), they would go here but
        NOT in TaskResponse.
    """

    pass
