"""
Tests for Notion sync service.

Tests cover:
- Property extraction helpers (rich_text, select, date)
- Validation logic (required fields, error messages)
- Status mapping (26 Notion → 26 Task, bidirectional)
- Sync functions (create/update task, push to Notion)
- Background sync loop

Mock Patterns:
- Mock Notion API responses with realistic property structures
- Mock database sessions with in-memory SQLite
- Mock NotionClient to avoid external API calls
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.notion import NotionAPIError, NotionClient
from app.constants import INTERNAL_TO_NOTION_STATUS, NOTION_TO_INTERNAL_STATUS
from app.models import PriorityLevel, Task, TaskStatus
from app.services.notion_sync import (
    extract_date,
    extract_rich_text,
    extract_select,
    map_internal_status_to_notion,
    map_notion_priority_to_internal,
    map_notion_status_to_internal,
    push_task_to_notion,
    sync_notion_page_to_task,
    validate_notion_entry,
)


# Test fixtures for mock Notion page data
def create_mock_notion_page(
    page_id: str = "mock-page-id-123",
    title: str = "Test Video",
    channel: str = "test_channel",
    topic: str = "Test Topic",
    story_direction: str = "Test story direction",
    status: str = "Draft",
    priority: str = "Normal",
) -> dict:
    """Create mock Notion page object with realistic structure.

    Args:
        page_id: Notion page ID (32 chars, no dashes)
        title: Video title
        channel: Channel name (select property)
        topic: Video topic
        story_direction: Story direction (rich text)
        status: Notion status value
        priority: Notion priority value

    Returns:
        Dictionary matching Notion API page object structure
    """
    return {
        "id": page_id,
        "object": "page",
        "properties": {
            "Title": {
                "id": "title",
                "type": "title",
                "title": [
                    {
                        "type": "text",
                        "text": {"content": title},
                        "plain_text": title,
                    }
                ],
            },
            "Channel": {
                "id": "channel",
                "type": "select",
                "select": {"name": channel} if channel else None,
            },
            "Topic": {
                "id": "topic",
                "type": "rich_text",
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": topic},
                        "plain_text": topic,
                    }
                ]
                if topic
                else [],
            },
            "Story Direction": {
                "id": "story",
                "type": "rich_text",
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": story_direction},
                        "plain_text": story_direction,
                    }
                ]
                if story_direction
                else [],
            },
            "Status": {
                "id": "status",
                "type": "select",
                "select": {"name": status} if status else None,
            },
            "Priority": {
                "id": "priority",
                "type": "select",
                "select": {"name": priority} if priority else None,
            },
        },
    }


# Tests for property extraction helpers


def test_extract_rich_text_from_title():
    """Test extracting text from Notion title property."""
    page = create_mock_notion_page(title="Test Video Title")
    title = extract_rich_text(page["properties"]["Title"])
    assert title == "Test Video Title"


def test_extract_rich_text_from_rich_text_property():
    """Test extracting text from Notion rich_text property."""
    page = create_mock_notion_page(topic="AI Generated Content")
    topic = extract_rich_text(page["properties"]["Topic"])
    assert topic == "AI Generated Content"


def test_extract_rich_text_empty_property():
    """Test extracting from empty rich_text returns empty string."""
    page = create_mock_notion_page(story_direction="")
    story = extract_rich_text(page["properties"]["Story Direction"])
    assert story == ""


def test_extract_rich_text_none_property():
    """Test extracting from None property returns empty string."""
    text = extract_rich_text(None)
    assert text == ""


def test_extract_rich_text_multiple_segments():
    """Test extracting from rich_text with multiple segments."""
    prop = {
        "rich_text": [
            {"type": "text", "text": {"content": "Part 1"}, "plain_text": "Part 1"},
            {"type": "text", "text": {"content": " Part 2"}, "plain_text": " Part 2"},
        ]
    }
    text = extract_rich_text(prop)
    assert text == "Part 1 Part 2"


def test_extract_select_with_value():
    """Test extracting select property with value."""
    page = create_mock_notion_page(channel="poke1")
    channel = extract_select(page["properties"]["Channel"])
    assert channel == "poke1"


def test_extract_select_none_property():
    """Test extracting from None select property returns None."""
    result = extract_select(None)
    assert result is None


def test_extract_select_empty_property():
    """Test extracting from empty select property returns None."""
    prop = {"select": None}
    result = extract_select(prop)
    assert result is None


def test_extract_date_with_value():
    """Test extracting date property with ISO 8601 datetime."""
    prop = {
        "date": {"start": "2026-01-13T10:30:00.000Z", "end": None, "time_zone": None}
    }
    result = extract_date(prop)
    assert result is not None
    assert result.year == 2026
    assert result.month == 1
    assert result.day == 13


def test_extract_date_none_property():
    """Test extracting from None date property returns None."""
    result = extract_date(None)
    assert result is None


def test_extract_date_empty_property():
    """Test extracting from empty date property returns None."""
    prop = {"date": None}
    result = extract_date(prop)
    assert result is None


# Tests for validation logic


def test_validate_entry_valid():
    """Test validating entry with all required fields."""
    page = create_mock_notion_page(
        title="Valid Video",
        channel="poke1",
        topic="Pokemon Documentary"
    )
    is_valid, error = validate_notion_entry(page)
    assert is_valid is True
    assert error is None


def test_validate_entry_missing_title():
    """Test validation fails when Title is empty."""
    page = create_mock_notion_page(title="", channel="poke1", topic="Test")
    is_valid, error = validate_notion_entry(page)
    assert is_valid is False
    assert error == "Missing Title - cannot queue"


def test_validate_entry_missing_topic():
    """Test validation fails when Topic is empty."""
    page = create_mock_notion_page(title="Test", channel="poke1", topic="")
    is_valid, error = validate_notion_entry(page)
    assert is_valid is False
    assert error == "Missing Topic - cannot queue"


def test_validate_entry_missing_channel():
    """Test validation fails when Channel is not set."""
    page = create_mock_notion_page(title="Test", channel="", topic="Test Topic")
    is_valid, error = validate_notion_entry(page)
    assert is_valid is False
    assert error == "Missing Channel - cannot queue"


def test_validate_entry_whitespace_title():
    """Test validation fails when Title is only whitespace."""
    page = create_mock_notion_page(title="   ", channel="poke1", topic="Test")
    is_valid, error = validate_notion_entry(page)
    assert is_valid is False
    assert error == "Missing Title - cannot queue"


# Tests for status mapping


def test_map_notion_status_draft_to_internal():
    """Test mapping Notion 'Draft' to internal 'draft'."""
    internal = map_notion_status_to_internal("Draft")
    assert internal == "draft"


def test_map_notion_status_queued_to_internal():
    """Test mapping Notion 'Queued' to internal 'queued'."""
    internal = map_notion_status_to_internal("Queued")
    assert internal == "queued"


def test_map_notion_status_assets_generating_to_internal():
    """Test mapping Notion 'Assets Generating' to internal 'generating_assets'."""
    internal = map_notion_status_to_internal("Assets Generating")
    assert internal == "generating_assets"


def test_map_notion_status_error_to_internal():
    """Test mapping Notion error status to internal error status."""
    internal = map_notion_status_to_internal("Error: API Failure")
    assert internal == "asset_error"


def test_map_notion_status_invalid_raises():
    """Test mapping invalid Notion status raises ValueError."""
    with pytest.raises(ValueError, match="Unknown Notion status"):
        map_notion_status_to_internal("Invalid Status")


def test_map_internal_status_draft_to_notion():
    """Test mapping TaskStatus.DRAFT to Notion 'Draft'."""
    notion = map_internal_status_to_notion(TaskStatus.DRAFT)
    assert notion == "Draft"


def test_map_internal_status_queued_to_notion():
    """Test mapping TaskStatus.QUEUED to Notion 'Queued'."""
    notion = map_internal_status_to_notion(TaskStatus.QUEUED)
    assert notion == "Queued"


def test_map_internal_status_generating_assets_to_notion():
    """Test mapping TaskStatus.GENERATING_ASSETS to Notion 'Assets Generating'."""
    notion = map_internal_status_to_notion(TaskStatus.GENERATING_ASSETS)
    assert notion == "Assets Generating"


def test_map_all_notion_statuses_to_internal():
    """Test all 26 Notion statuses map correctly to internal statuses."""
    for notion_status, internal_status in NOTION_TO_INTERNAL_STATUS.items():
        result = map_notion_status_to_internal(notion_status)
        assert result == internal_status


def test_map_all_internal_statuses_to_notion():
    """Test all internal statuses map correctly to Notion statuses."""
    for internal_value, notion_status in INTERNAL_TO_NOTION_STATUS.items():
        task_status = TaskStatus(internal_value)
        result = map_internal_status_to_notion(task_status)
        assert result == notion_status


def test_map_notion_priority_high():
    """Test mapping Notion 'High' priority."""
    priority = map_notion_priority_to_internal("High")
    assert priority == PriorityLevel.HIGH


def test_map_notion_priority_normal():
    """Test mapping Notion 'Normal' priority."""
    priority = map_notion_priority_to_internal("Normal")
    assert priority == PriorityLevel.NORMAL


def test_map_notion_priority_low():
    """Test mapping Notion 'Low' priority."""
    priority = map_notion_priority_to_internal("Low")
    assert priority == PriorityLevel.LOW


def test_map_notion_priority_none_defaults_to_normal():
    """Test mapping None priority defaults to Normal."""
    priority = map_notion_priority_to_internal(None)
    assert priority == PriorityLevel.NORMAL


def test_map_notion_priority_invalid_defaults_to_normal():
    """Test mapping invalid priority defaults to Normal."""
    priority = map_notion_priority_to_internal("Invalid")
    assert priority == PriorityLevel.NORMAL


# Tests for sync_notion_page_to_task


@pytest.mark.asyncio
async def test_sync_notion_page_validates_required_fields(async_session: AsyncSession):
    """Test sync validates required fields before creating task."""
    page = create_mock_notion_page(title="", channel="poke1", topic="Test")

    with pytest.raises(ValueError, match="Missing Title"):
        await sync_notion_page_to_task(page, async_session)


@pytest.mark.asyncio
async def test_sync_notion_page_raises_not_implemented_for_channel_lookup(
    async_session: AsyncSession,
):
    """Test sync raises NotImplementedError for channel lookup.

    Story 2.3 focuses on property mapping and validation.
    Full channel lookup integration comes in later stories.
    """
    page = create_mock_notion_page(
        title="Test Video",
        channel="poke1",
        topic="Pokemon",
        story_direction="Test story",
    )

    with pytest.raises(NotImplementedError, match="Channel lookup by name"):
        await sync_notion_page_to_task(page, async_session)


# Tests for push_task_to_notion


@pytest.mark.asyncio
async def test_push_task_to_notion_success():
    """Test pushing task status to Notion succeeds."""
    # Create task with notion_page_id
    task = Task()
    task.id = "test-task-id"
    task.notion_page_id = "test-notion-page-id"
    task.status = TaskStatus.GENERATING_ASSETS
    task.priority = PriorityLevel.HIGH
    task.title = "Test Video"

    # Mock NotionClient
    mock_client = AsyncMock(spec=NotionClient)
    mock_client.update_page_properties.return_value = {"id": "test-notion-page-id"}

    # Call push_task_to_notion
    await push_task_to_notion(task, mock_client)

    # Verify Notion API was called with correct properties
    mock_client.update_page_properties.assert_called_once()
    call_args = mock_client.update_page_properties.call_args
    assert call_args[0][0] == "test-notion-page-id"
    properties = call_args[0][1]
    assert properties["Status"]["select"]["name"] == "Assets Generating"
    assert properties["Priority"]["select"]["name"] == "High"


@pytest.mark.asyncio
async def test_push_task_to_notion_missing_page_id():
    """Test pushing task without notion_page_id is a no-op."""
    task = Task()
    task.id = "test-task-id"
    task.notion_page_id = None
    task.status = TaskStatus.DRAFT
    task.priority = PriorityLevel.NORMAL
    task.title = "Test Video"

    mock_client = AsyncMock(spec=NotionClient)

    # Should not raise, just log warning
    await push_task_to_notion(task, mock_client)

    # Verify Notion API was NOT called
    mock_client.update_page_properties.assert_not_called()


@pytest.mark.asyncio
async def test_push_task_to_notion_api_error_raised():
    """Test NotionAPIError is raised when API call fails."""
    task = Task()
    task.id = "test-task-id"
    task.notion_page_id = "test-notion-page-id"
    task.status = TaskStatus.QUEUED
    task.priority = PriorityLevel.NORMAL
    task.title = "Test Video"

    # Mock NotionClient to raise NotionAPIError
    mock_client = AsyncMock(spec=NotionClient)
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Page not found"
    mock_client.update_page_properties.side_effect = NotionAPIError(
        "Page not found", mock_response
    )

    # Should raise NotionAPIError
    with pytest.raises(NotionAPIError):
        await push_task_to_notion(task, mock_client)


# Integration test for round-trip status mapping


def test_status_mapping_round_trip():
    """Test that all Notion → Internal → Notion status mappings preserve intent.

    Note: Round-trip may not be exact due to many-to-one mappings.
    For example, "Ready for Planning" → "draft" → "Draft".
    This test verifies that the mapping is sensible and consistent.
    """
    # Test key status transitions
    test_cases = [
        ("Draft", "draft", "Draft"),
        ("Queued", "queued", "Queued"),
        ("Assets Generating", "generating_assets", "Assets Generating"),
        ("Videos Ready", "video_ready", "Videos Ready"),
        ("Ready for Review", "final_review", "Ready for Review"),
        ("Upload Complete", "published", "Upload Complete"),
    ]

    for notion_in, expected_internal, expected_notion_out in test_cases:
        # Notion → Internal
        internal = map_notion_status_to_internal(notion_in)
        assert internal == expected_internal

        # Internal → Notion
        task_status = TaskStatus(internal)
        notion_out = map_internal_status_to_notion(task_status)
        assert notion_out == expected_notion_out


# Integration test for database constraints


@pytest.mark.asyncio
async def test_notion_page_id_uniqueness_constraint(async_session: AsyncSession):
    """Test that notion_page_id unique constraint is enforced in database.

    This integration test verifies the actual database constraint works,
    preventing duplicate notion_page_id values across tasks.
    """
    from sqlalchemy.exc import IntegrityError

    from app.models import Channel
    from tests.support.factories import create_channel

    # Create a channel first (required foreign key)
    channel = create_channel(channel_id="test_channel_unique")
    async_session.add(channel)
    await async_session.flush()

    # Create first task with notion_page_id
    task1 = Task()
    task1.channel_id = channel.id
    task1.title = "First Task"
    task1.topic = "Test Topic"
    task1.story_direction = "Test story"
    task1.notion_page_id = "duplicate-page-id-123"
    task1.status = TaskStatus.DRAFT
    task1.priority = PriorityLevel.NORMAL

    async_session.add(task1)
    await async_session.commit()

    # Attempt to create second task with SAME notion_page_id
    task2 = Task()
    task2.channel_id = channel.id
    task2.title = "Second Task"
    task2.topic = "Different Topic"
    task2.story_direction = "Different story"
    task2.notion_page_id = "duplicate-page-id-123"  # Same as task1!
    task2.status = TaskStatus.DRAFT
    task2.priority = PriorityLevel.NORMAL

    async_session.add(task2)

    # Should raise IntegrityError due to unique constraint
    with pytest.raises(IntegrityError) as exc_info:
        await async_session.commit()

    # Verify error message mentions the unique constraint
    error_msg = str(exc_info.value).lower()
    assert "unique" in error_msg or "notion_page_id" in error_msg
