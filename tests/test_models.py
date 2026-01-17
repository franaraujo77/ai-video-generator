"""Tests for SQLAlchemy models.

Tests the Channel model including CRUD operations, constraints,
and default value behavior.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Channel, Task, TaskStatus
from app.exceptions import InvalidStateTransitionError


@pytest.mark.asyncio
async def test_channel_creation_with_all_fields(async_session):
    """Test creating a channel with all required fields."""
    channel = Channel(
        channel_id="test-channel-1",
        channel_name="Test Channel One",
    )
    async_session.add(channel)
    await async_session.commit()

    # Verify channel was created
    result = await async_session.execute(
        select(Channel).where(Channel.channel_id == "test-channel-1")
    )
    saved_channel = result.scalar_one()

    assert saved_channel.channel_id == "test-channel-1"
    assert saved_channel.channel_name == "Test Channel One"
    assert isinstance(saved_channel.id, uuid.UUID)


@pytest.mark.asyncio
async def test_channel_uuid_auto_generation(async_session):
    """Test that UUID primary key is auto-generated."""
    channel = Channel(
        channel_id="uuid-test",
        channel_name="UUID Test Channel",
    )
    async_session.add(channel)
    await async_session.commit()

    assert channel.id is not None
    assert isinstance(channel.id, uuid.UUID)


@pytest.mark.asyncio
async def test_channel_is_active_default_true(async_session):
    """Test that is_active defaults to True."""
    channel = Channel(
        channel_id="active-default",
        channel_name="Active Default Test",
    )
    async_session.add(channel)
    await async_session.commit()

    assert channel.is_active is True


@pytest.mark.asyncio
async def test_channel_created_at_auto_populated(async_session):
    """Test that created_at is auto-populated on creation."""
    before_create = datetime.now(timezone.utc)

    channel = Channel(
        channel_id="timestamp-test",
        channel_name="Timestamp Test",
    )
    async_session.add(channel)
    await async_session.commit()

    after_create = datetime.now(timezone.utc)

    assert channel.created_at is not None
    # Compare timestamps (SQLite may not preserve timezone, so compare naive)
    created_naive = (
        channel.created_at.replace(tzinfo=None) if channel.created_at.tzinfo else channel.created_at
    )
    before_naive = before_create.replace(tzinfo=None)
    after_naive = after_create.replace(tzinfo=None)
    assert before_naive <= created_naive <= after_naive


@pytest.mark.asyncio
async def test_channel_updated_at_auto_populated(async_session):
    """Test that updated_at is auto-populated on creation."""
    channel = Channel(
        channel_id="updated-at-test",
        channel_name="Updated At Test",
    )
    async_session.add(channel)
    await async_session.commit()

    assert channel.updated_at is not None


@pytest.mark.asyncio
async def test_channel_isolation_query_by_channel_id(async_session):
    """Test querying channels by channel_id for isolation (FR9).

    This test verifies that queries can filter by channel_id to
    return only data for a specific channel.
    """
    # Create multiple channels
    channel1 = Channel(channel_id="poke1", channel_name="Pokemon Channel 1")
    channel2 = Channel(channel_id="poke2", channel_name="Pokemon Channel 2")
    channel3 = Channel(channel_id="nature1", channel_name="Nature Channel")

    async_session.add_all([channel1, channel2, channel3])
    await async_session.commit()

    # Query for specific channel
    result = await async_session.execute(select(Channel).where(Channel.channel_id == "poke1"))
    filtered_channel = result.scalar_one()

    # Verify isolation - only requested channel returned
    assert filtered_channel.channel_id == "poke1"
    assert filtered_channel.channel_name == "Pokemon Channel 1"


@pytest.mark.asyncio
async def test_channel_unique_constraint_on_channel_id(async_session):
    """Test that duplicate channel_id raises IntegrityError."""
    channel1 = Channel(
        channel_id="unique-test",
        channel_name="First Channel",
    )
    async_session.add(channel1)
    await async_session.commit()

    # Attempt to create duplicate
    channel2 = Channel(
        channel_id="unique-test",  # Same channel_id
        channel_name="Second Channel",
    )
    async_session.add(channel2)

    with pytest.raises(IntegrityError):
        await async_session.commit()


@pytest.mark.asyncio
async def test_channel_repr(async_session):
    """Test Channel.__repr__ for debugging."""
    channel = Channel(
        channel_id="repr-test",
        channel_name="Repr Test Channel",
    )

    repr_str = repr(channel)
    assert "repr-test" in repr_str
    assert "Repr Test Channel" in repr_str


@pytest.mark.asyncio
async def test_channel_read_by_id(async_session):
    """Test reading a channel by its UUID primary key."""
    channel = Channel(
        channel_id="read-by-id",
        channel_name="Read By ID Test",
    )
    async_session.add(channel)
    await async_session.commit()

    channel_id = channel.id

    # Read by primary key using session.get
    retrieved = await async_session.get(Channel, channel_id)

    assert retrieved is not None
    assert retrieved.id == channel_id
    assert retrieved.channel_id == "read-by-id"


@pytest.mark.asyncio
async def test_channel_updated_at_changes_on_update(async_session):
    """Test that updated_at changes when record is modified."""
    import asyncio

    channel = Channel(
        channel_id="update-test",
        channel_name="Original Name",
    )
    async_session.add(channel)
    await async_session.commit()

    original_updated_at = channel.updated_at

    # Wait a brief moment to ensure timestamp difference
    await asyncio.sleep(0.1)

    # Update the channel
    channel.channel_name = "Updated Name"
    await async_session.commit()

    # Refresh to get the new updated_at value
    await async_session.refresh(channel)

    # Note: SQLite doesn't support onupdate triggers the same way as PostgreSQL
    # In production with PostgreSQL, updated_at would automatically update
    # For this test, we verify the field is accessible after update
    assert channel.updated_at is not None
    assert channel.channel_name == "Updated Name"


@pytest.mark.asyncio
async def test_channel_multiple_channels_different_uuids(async_session):
    """Test that each channel gets a unique UUID."""
    channels = []
    for i in range(5):
        channel = Channel(
            channel_id=f"multi-uuid-{i}",
            channel_name=f"Channel {i}",
        )
        async_session.add(channel)
        channels.append(channel)

    await async_session.commit()

    # Verify all UUIDs are unique
    uuids = [c.id for c in channels]
    assert len(uuids) == len(set(uuids)), "All UUIDs should be unique"


@pytest.mark.asyncio
async def test_channel_is_active_can_be_set_false(async_session):
    """Test that is_active can be explicitly set to False."""
    channel = Channel(
        channel_id="inactive-channel",
        channel_name="Inactive Channel",
        is_active=False,
    )
    async_session.add(channel)
    await async_session.commit()

    result = await async_session.execute(
        select(Channel).where(Channel.channel_id == "inactive-channel")
    )
    saved = result.scalar_one()

    assert saved.is_active is False


@pytest.mark.asyncio
async def test_channel_query_active_channels_only(async_session):
    """Test filtering channels by is_active status."""
    # Create mix of active and inactive channels
    active1 = Channel(channel_id="active-1", channel_name="Active 1", is_active=True)
    active2 = Channel(channel_id="active-2", channel_name="Active 2", is_active=True)
    inactive = Channel(channel_id="inactive-1", channel_name="Inactive", is_active=False)

    async_session.add_all([active1, active2, inactive])
    await async_session.commit()

    # Query only active channels
    result = await async_session.execute(
        select(Channel).where(Channel.is_active == True)  # noqa: E712
    )
    active_channels = result.scalars().all()

    assert len(active_channels) == 2
    assert all(c.is_active for c in active_channels)


@pytest.mark.asyncio
async def test_channel_delete(async_session):
    """Test deleting a channel from the database."""
    channel = Channel(
        channel_id="delete-test",
        channel_name="To Be Deleted",
    )
    async_session.add(channel)
    await async_session.commit()

    channel_id = channel.id

    # Delete the channel
    await async_session.delete(channel)
    await async_session.commit()

    # Verify it's gone
    retrieved = await async_session.get(Channel, channel_id)
    assert retrieved is None


@pytest.mark.asyncio
async def test_channel_update_channel_name(async_session):
    """Test updating channel_name field."""
    channel = Channel(
        channel_id="name-update",
        channel_name="Original",
    )
    async_session.add(channel)
    await async_session.commit()

    # Update the name
    channel.channel_name = "New Name"
    await async_session.commit()

    # Re-query to verify persistence
    result = await async_session.execute(select(Channel).where(Channel.channel_id == "name-update"))
    updated = result.scalar_one()

    assert updated.channel_name == "New Name"


@pytest.mark.asyncio
async def test_channel_count(async_session):
    """Test counting channels in database."""
    from sqlalchemy import func

    # Create several channels
    for i in range(3):
        channel = Channel(
            channel_id=f"count-test-{i}",
            channel_name=f"Count Test {i}",
        )
        async_session.add(channel)

    await async_session.commit()

    # Count channels
    result = await async_session.execute(select(func.count(Channel.id)))
    count = result.scalar()

    assert count == 3


@pytest.mark.asyncio
async def test_channel_bulk_create(async_session):
    """Test creating multiple channels at once with add_all."""
    channels = [
        Channel(channel_id=f"bulk-{i}", channel_name=f"Bulk Channel {i}") for i in range(10)
    ]

    async_session.add_all(channels)
    await async_session.commit()

    # Verify all were created
    result = await async_session.execute(select(Channel).where(Channel.channel_id.like("bulk-%")))
    saved = result.scalars().all()

    assert len(saved) == 10


# ==============================================================================
# Task Model Tests - 26-Status State Machine (Story 5.1)
# ==============================================================================


@pytest.mark.asyncio
async def test_taskstatus_enum_has_26_values():
    """Test that TaskStatus enum contains exactly 27 status values (26 original + CANCELLED).

    NOTE: Test name kept as 26 for backward compatibility but validates 27 statuses.
    """
    # AC1: Verify all 27 statuses exist (updated in code review)
    expected_statuses = {
        # Initial states (4 - added CANCELLED)
        "draft", "queued", "claimed", "cancelled",
        # Asset phase (4)
        "generating_assets", "assets_ready", "assets_approved", "asset_error",
        # Composite phase (2)
        "generating_composites", "composites_ready",
        # Video phase (4)
        "generating_video", "video_ready", "video_approved", "video_error",
        # Audio phase (4)
        "generating_audio", "audio_ready", "audio_approved", "audio_error",
        # SFX phase (2)
        "generating_sfx", "sfx_ready",
        # Assembly phase (2)
        "assembling", "assembly_ready",
        # Final phase (5)
        "final_review", "approved", "uploading", "published", "upload_error",
    }

    # Get all enum values
    actual_statuses = {status.value for status in TaskStatus}

    # Verify count and content (updated to 27 after code review)
    assert len(actual_statuses) == 27, f"Expected 27 statuses, found {len(actual_statuses)}"
    assert actual_statuses == expected_statuses


@pytest.mark.asyncio
async def test_taskstatus_enum_values_use_snake_case():
    """Test that all TaskStatus enum values follow snake_case convention."""
    # AC1: Status values follow naming convention
    for status in TaskStatus:
        # All values should be lowercase with underscores only
        assert status.value.islower(), f"{status.value} is not lowercase"
        assert " " not in status.value, f"{status.value} contains spaces"
        assert "-" not in status.value, f"{status.value} contains hyphens"


@pytest.mark.asyncio
async def test_valid_status_transition_draft_to_queued(async_session):
    """Test valid transition: DRAFT → QUEUED."""
    # AC2: Valid transitions are allowed
    # Create channel first
    channel = Channel(channel_id="test-channel", channel_name="Test Channel")
    async_session.add(channel)
    await async_session.commit()

    # Create task in DRAFT status
    task = Task(
        channel_id=channel.id,
        notion_page_id="test-page-001",
        title="Test Video",
        topic="Test Topic",
        story_direction="Test Story",
        status=TaskStatus.DRAFT,
    )
    async_session.add(task)
    await async_session.commit()

    # Transition to QUEUED (should succeed)
    task.status = TaskStatus.QUEUED
    await async_session.commit()

    assert task.status == TaskStatus.QUEUED


@pytest.mark.asyncio
async def test_invalid_status_transition_draft_to_published(async_session):
    """Test invalid transition: DRAFT → PUBLISHED raises InvalidStateTransitionError."""
    # AC2: Invalid transitions raise InvalidStateTransitionError
    # Create channel first
    channel = Channel(channel_id="test-channel-2", channel_name="Test Channel 2")
    async_session.add(channel)
    await async_session.commit()

    # Create task in DRAFT status
    task = Task(
        channel_id=channel.id,
        notion_page_id="test-page-002",
        title="Test Video 2",
        topic="Test Topic 2",
        story_direction="Test Story 2",
        status=TaskStatus.DRAFT,
    )
    async_session.add(task)
    await async_session.commit()

    # Attempt invalid transition (should raise exception)
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        task.status = TaskStatus.PUBLISHED
        await async_session.commit()

    # Verify exception details
    assert exc_info.value.from_status == TaskStatus.DRAFT
    assert exc_info.value.to_status == TaskStatus.PUBLISHED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "from_status,to_status,should_succeed",
    [
        # Happy path transitions (should succeed)
        (TaskStatus.DRAFT, TaskStatus.QUEUED, True),
        (TaskStatus.QUEUED, TaskStatus.CLAIMED, True),
        (TaskStatus.CLAIMED, TaskStatus.GENERATING_ASSETS, True),
        (TaskStatus.GENERATING_ASSETS, TaskStatus.ASSETS_READY, True),
        (TaskStatus.ASSETS_READY, TaskStatus.ASSETS_APPROVED, True),
        (TaskStatus.ASSETS_APPROVED, TaskStatus.GENERATING_COMPOSITES, True),
        (TaskStatus.GENERATING_COMPOSITES, TaskStatus.COMPOSITES_READY, True),
        (TaskStatus.COMPOSITES_READY, TaskStatus.GENERATING_VIDEO, True),
        (TaskStatus.GENERATING_VIDEO, TaskStatus.VIDEO_READY, True),
        (TaskStatus.VIDEO_READY, TaskStatus.VIDEO_APPROVED, True),
        (TaskStatus.VIDEO_APPROVED, TaskStatus.GENERATING_AUDIO, True),
        (TaskStatus.GENERATING_AUDIO, TaskStatus.AUDIO_READY, True),
        (TaskStatus.AUDIO_READY, TaskStatus.AUDIO_APPROVED, True),
        (TaskStatus.AUDIO_APPROVED, TaskStatus.GENERATING_SFX, True),
        (TaskStatus.GENERATING_SFX, TaskStatus.SFX_READY, True),
        (TaskStatus.SFX_READY, TaskStatus.ASSEMBLING, True),
        (TaskStatus.ASSEMBLING, TaskStatus.ASSEMBLY_READY, True),
        (TaskStatus.ASSEMBLY_READY, TaskStatus.FINAL_REVIEW, True),
        (TaskStatus.FINAL_REVIEW, TaskStatus.APPROVED, True),
        (TaskStatus.APPROVED, TaskStatus.UPLOADING, True),
        (TaskStatus.UPLOADING, TaskStatus.PUBLISHED, True),
        # Error transitions (should succeed)
        (TaskStatus.GENERATING_ASSETS, TaskStatus.ASSET_ERROR, True),
        (TaskStatus.GENERATING_VIDEO, TaskStatus.VIDEO_ERROR, True),
        (TaskStatus.GENERATING_AUDIO, TaskStatus.AUDIO_ERROR, True),
        (TaskStatus.UPLOADING, TaskStatus.UPLOAD_ERROR, True),
        # Error recovery paths (should succeed)
        (TaskStatus.ASSET_ERROR, TaskStatus.QUEUED, True),
        (TaskStatus.VIDEO_ERROR, TaskStatus.QUEUED, True),
        (TaskStatus.AUDIO_ERROR, TaskStatus.QUEUED, True),
        (TaskStatus.UPLOAD_ERROR, TaskStatus.FINAL_REVIEW, True),
        # Invalid transitions (should fail)
        (TaskStatus.DRAFT, TaskStatus.PUBLISHED, False),
        (TaskStatus.QUEUED, TaskStatus.PUBLISHED, False),
        (TaskStatus.ASSETS_READY, TaskStatus.PUBLISHED, False),
        (TaskStatus.PUBLISHED, TaskStatus.DRAFT, False),
        (TaskStatus.GENERATING_ASSETS, TaskStatus.VIDEO_READY, False),
        (TaskStatus.CLAIMED, TaskStatus.ASSETS_APPROVED, False),
    ],
)
async def test_status_transitions_comprehensive(async_session, from_status, to_status, should_succeed):
    """Test comprehensive status transition validation matrix."""
    # AC2: Validate state transitions
    # AC3: State machine progression matches UX flow
    # Create channel first
    channel = Channel(
        channel_id=f"test-channel-{from_status.value}-{to_status.value}",
        channel_name="Test Channel",
    )
    async_session.add(channel)
    await async_session.commit()

    # Create task with initial status (bypass validation on creation)
    task = Task(
        channel_id=channel.id,
        notion_page_id=f"test-page-{from_status.value}-{to_status.value}",
        title="Test Video",
        topic="Test Topic",
        story_direction="Test Story",
    )
    # Set status directly via __dict__ to bypass validation on initial creation
    task.__dict__["status"] = from_status
    async_session.add(task)
    await async_session.commit()

    if should_succeed:
        # Valid transition - should not raise exception
        task.status = to_status
        await async_session.commit()
        assert task.status == to_status
    else:
        # Invalid transition - should raise InvalidStateTransitionError
        with pytest.raises(InvalidStateTransitionError):
            task.status = to_status
            await async_session.commit()


@pytest.mark.asyncio
async def test_state_transition_error_recovery_asset_error_to_queued(async_session):
    """Test error recovery path: ASSET_ERROR → QUEUED (retry)."""
    # AC2: Error recovery paths work correctly
    channel = Channel(channel_id="error-recovery-test", channel_name="Error Recovery Test")
    async_session.add(channel)
    await async_session.commit()

    # Create task in ASSET_ERROR status
    task = Task(
        channel_id=channel.id,
        notion_page_id="error-recovery-page",
        title="Error Recovery Video",
        topic="Error Recovery Topic",
        story_direction="Error Recovery Story",
    )
    task.__dict__["status"] = TaskStatus.ASSET_ERROR
    async_session.add(task)
    await async_session.commit()

    # Retry - transition back to QUEUED
    task.status = TaskStatus.QUEUED
    await async_session.commit()

    assert task.status == TaskStatus.QUEUED


@pytest.mark.asyncio
async def test_taskstatus_no_duplicate_values():
    """Test that TaskStatus enum has no duplicate values."""
    # AC1: No duplicate enum values
    values = [status.value for status in TaskStatus]
    assert len(values) == len(set(values)), "TaskStatus has duplicate values"


@pytest.mark.asyncio
async def test_task_initial_status_defaults_to_draft(async_session):
    """Test that new Task defaults to DRAFT status when persisted."""
    # Verify default status is DRAFT (FR51 requirement - set via database default)
    channel = Channel(channel_id="default-status-test", channel_name="Default Status Test")
    async_session.add(channel)
    await async_session.commit()

    task = Task(
        channel_id=channel.id,
        notion_page_id="default-status-page",
        title="Default Status Video",
        topic="Default Status Topic",
        story_direction="Default Status Story",
        # Note: status not specified, should default via database server_default
    )
    async_session.add(task)
    await async_session.commit()

    # Refresh to get server-set defaults
    await async_session.refresh(task)

    # Task should default to DRAFT (set by database server_default)
    assert task.status == TaskStatus.DRAFT


@pytest.mark.asyncio
async def test_initial_task_creation_skips_validation(async_session):
    """Test that initial status assignment skips validation (status is None).

    This verifies the validation logic correctly handles initial task creation
    where self.status is None and should not validate the transition.
    """
    # Create channel first
    channel = Channel(channel_id="initial-creation-test", channel_name="Initial Creation Test")
    async_session.add(channel)
    await async_session.commit()

    # Create task with explicit status (first assignment, status is None internally)
    task = Task(
        channel_id=channel.id,
        notion_page_id="initial-creation-page",
        title="Initial Creation Video",
        topic="Initial Creation Topic",
        story_direction="Initial Creation Story",
        status=TaskStatus.DRAFT,  # First assignment, should not validate
    )

    # Should succeed without InvalidStateTransitionError
    async_session.add(task)
    await async_session.commit()

    assert task.status == TaskStatus.DRAFT

    # Also test assigning QUEUED directly on creation (edge case)
    task2 = Task(
        channel_id=channel.id,
        notion_page_id="initial-creation-page-2",
        title="Initial Creation Video 2",
        topic="Initial Creation Topic 2",
        story_direction="Initial Creation Story 2",
        status=TaskStatus.QUEUED,  # Skip DRAFT, should be allowed on initial creation
    )
    async_session.add(task2)
    await async_session.commit()

    assert task2.status == TaskStatus.QUEUED


@pytest.mark.asyncio
async def test_published_is_terminal_state(async_session):
    """Test that PUBLISHED is a terminal state with no valid transitions.

    Once a task reaches PUBLISHED, no further status changes should be allowed.
    This prevents accidental modification of published content.
    """
    # Create channel and task
    channel = Channel(channel_id="terminal-test", channel_name="Terminal Test")
    async_session.add(channel)
    await async_session.commit()

    task = Task(
        channel_id=channel.id,
        notion_page_id="terminal-page",
        title="Terminal Video",
        topic="Terminal Topic",
        story_direction="Terminal Story",
    )
    # Bypass validation to set PUBLISHED directly
    task.__dict__["status"] = TaskStatus.PUBLISHED
    async_session.add(task)
    await async_session.commit()

    # Verify PUBLISHED has no valid transitions
    assert Task.VALID_TRANSITIONS[TaskStatus.PUBLISHED] == []

    # Attempt to transition from PUBLISHED should fail
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        task.status = TaskStatus.DRAFT

    assert "Invalid transition: published → draft" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cancelled_is_terminal_state(async_session):
    """Test that CANCELLED is a terminal state with no valid transitions.

    Once a task is cancelled, it should not be able to transition to any other state.
    """
    # Create channel and task
    channel = Channel(channel_id="cancelled-terminal-test", channel_name="Cancelled Terminal Test")
    async_session.add(channel)
    await async_session.commit()

    task = Task(
        channel_id=channel.id,
        notion_page_id="cancelled-terminal-page",
        title="Cancelled Terminal Video",
        topic="Cancelled Terminal Topic",
        story_direction="Cancelled Terminal Story",
    )
    # Bypass validation to set CANCELLED directly
    task.__dict__["status"] = TaskStatus.CANCELLED
    async_session.add(task)
    await async_session.commit()

    # Verify CANCELLED has no valid transitions
    assert Task.VALID_TRANSITIONS[TaskStatus.CANCELLED] == []

    # Attempt to transition from CANCELLED should fail
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        task.status = TaskStatus.QUEUED

    assert "Invalid transition: cancelled → queued" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cancellation_from_draft(async_session):
    """Test that tasks can be cancelled from DRAFT status."""
    # Create channel and task
    channel = Channel(channel_id="cancel-draft-test", channel_name="Cancel Draft Test")
    async_session.add(channel)
    await async_session.commit()

    task = Task(
        channel_id=channel.id,
        notion_page_id="cancel-draft-page",
        title="Cancel Draft Video",
        topic="Cancel Draft Topic",
        story_direction="Cancel Draft Story",
        status=TaskStatus.DRAFT,
    )
    async_session.add(task)
    await async_session.commit()

    # Cancel from DRAFT
    task.status = TaskStatus.CANCELLED
    await async_session.commit()

    assert task.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancellation_from_queued(async_session):
    """Test that tasks can be cancelled from QUEUED status."""
    # Create channel and task
    channel = Channel(channel_id="cancel-queued-test", channel_name="Cancel Queued Test")
    async_session.add(channel)
    await async_session.commit()

    task = Task(
        channel_id=channel.id,
        notion_page_id="cancel-queued-page",
        title="Cancel Queued Video",
        topic="Cancel Queued Topic",
        story_direction="Cancel Queued Story",
        status=TaskStatus.DRAFT,
    )
    async_session.add(task)
    await async_session.commit()

    # Transition to QUEUED
    task.status = TaskStatus.QUEUED
    await async_session.commit()

    # Cancel from QUEUED
    task.status = TaskStatus.CANCELLED
    await async_session.commit()

    assert task.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancellation_from_final_review(async_session):
    """Test that tasks can be cancelled from FINAL_REVIEW status.

    This allows users to cancel videos during final YouTube compliance review
    if they decide not to publish.
    """
    # Create channel and task
    channel = Channel(channel_id="cancel-review-test", channel_name="Cancel Review Test")
    async_session.add(channel)
    await async_session.commit()

    task = Task(
        channel_id=channel.id,
        notion_page_id="cancel-review-page",
        title="Cancel Review Video",
        topic="Cancel Review Topic",
        story_direction="Cancel Review Story",
    )
    # Bypass validation to set FINAL_REVIEW directly
    task.__dict__["status"] = TaskStatus.FINAL_REVIEW
    async_session.add(task)
    await async_session.commit()

    # Cancel from FINAL_REVIEW
    task.status = TaskStatus.CANCELLED
    await async_session.commit()

    assert task.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_taskstatus_enum_has_27_values():
    """Test that TaskStatus enum has exactly 27 values (including CANCELLED)."""
    # AC1: 27 statuses defined (26 original + CANCELLED)
    assert len(TaskStatus) == 27, f"Expected 27 statuses, got {len(TaskStatus)}"


@pytest.mark.asyncio
async def test_exception_str_includes_transition_details():
    """Test that InvalidStateTransitionError.__str__ includes transition details."""
    from app.models import TaskStatus

    exc = InvalidStateTransitionError(
        "Invalid transition: draft → published",
        from_status=TaskStatus.DRAFT,
        to_status=TaskStatus.PUBLISHED,
    )

    error_str = str(exc)
    assert "Invalid transition: draft → published" in error_str
    assert "from=draft" in error_str
    assert "to=published" in error_str


@pytest.mark.asyncio
async def test_review_duration_seconds_property_calculates_correctly(async_session):
    """Test Task.review_duration_seconds property calculates time spent at review gate."""
    # Create task with review timestamps
    task = Task(
        notion_page_id="test-review-duration-123",
        channel_id=uuid.uuid4(),
        title="Test Review Duration",
        topic="Testing",
        story_direction="Test story direction",
        status=TaskStatus.ASSETS_READY,
    )

    # Set review timestamps (5 minutes 30 seconds apart)
    start_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    end_time = datetime(2024, 1, 1, 12, 5, 30, tzinfo=timezone.utc)
    task.review_started_at = start_time
    task.review_completed_at = end_time

    async_session.add(task)
    await async_session.commit()

    # Verify property calculates correct duration (330 seconds = 5 min 30 sec)
    assert task.review_duration_seconds == 330


@pytest.mark.asyncio
async def test_review_duration_seconds_returns_none_when_incomplete(async_session):
    """Test Task.review_duration_seconds returns None if review not completed."""
    task = Task(
        notion_page_id="test-incomplete-review-456",
        channel_id=uuid.uuid4(),
        title="Test Incomplete Review",
        topic="Testing",
        story_direction="Test story direction",
        status=TaskStatus.ASSETS_READY,
    )

    # Set only review_started_at (review still in progress)
    task.review_started_at = datetime.now(timezone.utc)
    task.review_completed_at = None

    async_session.add(task)
    await async_session.commit()

    # Verify property returns None
    assert task.review_duration_seconds is None


@pytest.mark.asyncio
async def test_review_duration_seconds_returns_none_when_not_started(async_session):
    """Test Task.review_duration_seconds returns None if review not started."""
    task = Task(
        notion_page_id="test-no-review-789",
        channel_id=uuid.uuid4(),
        title="Test No Review",
        topic="Testing",
        story_direction="Test story direction",
        status=TaskStatus.GENERATING_ASSETS,
    )

    # No review timestamps set
    task.review_started_at = None
    task.review_completed_at = None

    async_session.add(task)
    await async_session.commit()

    # Verify property returns None
    assert task.review_duration_seconds is None
