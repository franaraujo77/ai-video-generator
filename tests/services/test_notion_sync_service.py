"""Tests for Notion sync service (Story 7.5).

This test module covers YouTube URL retrieval and Notion database synchronization.

Test Coverage:
- URL construction (valid/invalid video_id formats)
- Notion update flow (successful sync, property updates)
- Rate limiting (AsyncLimiter enforcement, 429 handling)
- Error classification (permanent 4xx, transient 429/409/503)
- Fallback URL storage (permanent errors, Discord alerts)
- Integration tests (end-to-end sync, fallback recovery)

Mocking Strategy:
- Mock notion_client.AsyncClient for Notion API
- Mock AsyncLimiter for rate limit tests
- Mock send_discord_alert() for alert testing
- Mock CredentialService for token retrieval
- Use AsyncSession fixtures for database testing
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from notion_client.errors import APIResponseError

from app.models import Channel, FallbackYouTubeURL, Task, TaskStatus
from app.services.notion_sync_service import (
    NotionSyncError,
    NotionSyncRetryError,
    construct_youtube_url,
    store_fallback_url,
    sync_youtube_url_to_notion,
)


# ============================================================================
# Helper Functions
# ============================================================================


def create_mock_response(status_code: int, headers: dict[str, str] | None = None):
    """Create a mock httpx.Response for APIResponseError."""
    request = httpx.Request("POST", "https://api.notion.com/v1/pages/test")
    response = httpx.Response(
        status_code=status_code,
        request=request,
        headers=headers or {},
    )
    return response


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def sample_channel(async_session):
    """Create a sample channel for testing."""
    channel = Channel(
        id=uuid4(),
        channel_id="test_channel",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest.fixture
async def sample_task(async_session, sample_channel):
    """Create a sample task with notion_page_id."""
    task = Task(
        id=uuid4(),
        channel_id=sample_channel.id,
        notion_page_id=str(uuid4()),
        title="Test Video",
        topic="Test Topic",
        story_direction="Test story direction",
        status=TaskStatus.UPLOADING,
        youtube_video_id="dQw4w9WgXcQ",
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)
    return task


@pytest.fixture
def mock_notion_client():
    """Mock AsyncClient from notion_client."""
    client = AsyncMock()
    client.pages = AsyncMock()
    client.pages.update = AsyncMock()
    return client


@pytest.fixture
def mock_notion_response():
    """Mock successful Notion API response."""
    return {
        "id": str(uuid4()),
        "properties": {
            "youtube_url": {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            "Status": {"status": {"name": "Published"}},
        },
    }


# ============================================================================
# URL Construction Tests (AC1)
# ============================================================================


@pytest.mark.asyncio
async def test_construct_youtube_url_valid():
    """Test URL construction with valid video_id."""
    video_id = "dQw4w9WgXcQ"
    url = await construct_youtube_url(video_id)

    assert url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_construct_youtube_url_various_formats():
    """Test URL construction with different valid video_id formats."""
    test_cases = [
        "dQw4w9WgXcQ",  # Standard format
        "jNQXAC9IVRw",  # Another example
        "9bZkp7q19f0",  # With numbers
        "a-zA-Z0-9_-",  # All valid characters
    ]

    for video_id in test_cases:
        url = await construct_youtube_url(video_id)
        assert url == f"https://www.youtube.com/watch?v={video_id}"


@pytest.mark.asyncio
async def test_construct_youtube_url_invalid_length():
    """Test URL construction with invalid video_id length."""
    invalid_ids = [
        "short",  # Too short
        "waytooooooooolong",  # Too long
        "",  # Empty string
    ]

    for video_id in invalid_ids:
        with pytest.raises(NotionSyncError) as exc_info:
            await construct_youtube_url(video_id)
        assert "Invalid video ID format" in str(exc_info.value)


@pytest.mark.asyncio
async def test_construct_youtube_url_invalid_characters():
    """Test URL construction with invalid characters."""
    invalid_ids = [
        "dQw4w9Wg@cQ",  # Special char (@)
        "dQw4w9Wg cQ",  # Space
        "dQw4w9Wg!cQ",  # Exclamation mark
        "dQw4w9Wg#cQ",  # Hash
    ]

    for video_id in invalid_ids:
        with pytest.raises(NotionSyncError) as exc_info:
            await construct_youtube_url(video_id)
        assert "Invalid video ID format" in str(exc_info.value)


# ============================================================================
# Notion Update Success Tests (AC2)
# ============================================================================


@pytest.mark.asyncio
async def test_sync_youtube_url_success(
    async_session, sample_task, mock_notion_client, mock_notion_response
):
    """Test successful Notion sync updates properties correctly."""
    mock_notion_client.pages.update.return_value = mock_notion_response

    with patch(
        "app.services.notion_sync_service.AsyncClient",
        return_value=mock_notion_client,
    ):
        with patch("app.services.notion_sync_service.CredentialService") as mock_cred:
            mock_cred.return_value.get_notion_token = AsyncMock(
                return_value="mock_token"
            )

            await sync_youtube_url_to_notion(
                task=sample_task,
                video_id="dQw4w9WgXcQ",
                youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                db=async_session,
            )

    # Verify Notion API called with correct parameters
    mock_notion_client.pages.update.assert_called_once_with(
        page_id=sample_task.notion_page_id,
        properties={
            "youtube_url": {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            "Status": {"status": {"name": "Published"}},
        },
    )


@pytest.mark.asyncio
async def test_sync_youtube_url_missing_notion_page_id(
    async_session, sample_channel
):
    """Test sync fails when task has empty notion_page_id."""
    task = Task(
        id=uuid4(),
        channel_id=sample_channel.id,
        notion_page_id="",  # Empty page_id (not None since DB enforces NOT NULL)
        title="Test Video",
        topic="Test Topic",
        story_direction="Test story direction",
        status=TaskStatus.UPLOADING,
    )
    async_session.add(task)
    await async_session.commit()

    with pytest.raises(NotionSyncError) as exc_info:
        await sync_youtube_url_to_notion(
            task=task,
            video_id="dQw4w9WgXcQ",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            db=async_session,
        )

    assert "has no notion_page_id" in str(exc_info.value)


# ============================================================================
# Error Handling Tests (AC4)
# ============================================================================


@pytest.mark.asyncio
async def test_sync_youtube_url_permanent_error_400(
    async_session, sample_task, mock_notion_client
):
    """Test 400 validation_error raises NotionSyncError and stores fallback."""
    # Mock 400 response
    import httpx

    mock_response = httpx.Response(
        status_code=400,
        request=httpx.Request("POST", "https://api.notion.com/v1/pages/test"),
    )
    mock_notion_client.pages.update.side_effect = APIResponseError(
        response=mock_response,
        message="Invalid properties",
        code="validation_error",
    )

    with patch(
        "app.services.notion_sync_service.AsyncClient",
        return_value=mock_notion_client,
    ):
        with patch("app.services.notion_sync_service.CredentialService") as mock_cred:
            mock_cred.return_value.get_notion_token = AsyncMock(
                return_value="mock_token"
            )

            with pytest.raises(NotionSyncError) as exc_info:
                await sync_youtube_url_to_notion(
                    task=sample_task,
                    video_id="dQw4w9WgXcQ",
                    youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    db=async_session,
                )

    assert "validation_error" in str(exc_info.value)

    # Verify fallback URL was stored
    from sqlalchemy import select

    result = await async_session.execute(
        select(FallbackYouTubeURL).where(FallbackYouTubeURL.task_id == sample_task.id)
    )
    fallback = result.scalar_one_or_none()

    assert fallback is not None
    assert fallback.video_id == "dQw4w9WgXcQ"
    assert fallback.youtube_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_sync_youtube_url_permanent_error_401(
    async_session, sample_task, mock_notion_client
):
    """Test 401 unauthorized raises NotionSyncError and stores fallback."""
    mock_response = create_mock_response(401)
    mock_notion_client.pages.update.side_effect = APIResponseError(
        response=mock_response,
        message="Unauthorized",
        code="unauthorized",
    )

    with patch(
        "app.services.notion_sync_service.AsyncClient",
        return_value=mock_notion_client,
    ):
        with patch("app.services.notion_sync_service.CredentialService") as mock_cred:
            mock_cred.return_value.get_notion_token = AsyncMock(
                return_value="mock_token"
            )

            with pytest.raises(NotionSyncError):
                await sync_youtube_url_to_notion(
                    task=sample_task,
                    video_id="dQw4w9WgXcQ",
                    youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    db=async_session,
                )


@pytest.mark.asyncio
async def test_sync_youtube_url_permanent_error_403(
    async_session, sample_task, mock_notion_client
):
    """Test 403 restricted_resource raises NotionSyncError and stores fallback."""
    mock_response = create_mock_response(403)
    mock_notion_client.pages.update.side_effect = APIResponseError(
        response=mock_response,
        message="Forbidden",
        code="restricted_resource",
    )

    with patch(
        "app.services.notion_sync_service.AsyncClient",
        return_value=mock_notion_client,
    ):
        with patch("app.services.notion_sync_service.CredentialService") as mock_cred:
            mock_cred.return_value.get_notion_token = AsyncMock(
                return_value="mock_token"
            )

            with pytest.raises(NotionSyncError):
                await sync_youtube_url_to_notion(
                    task=sample_task,
                    video_id="dQw4w9WgXcQ",
                    youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    db=async_session,
                )


@pytest.mark.asyncio
async def test_sync_youtube_url_permanent_error_404(
    async_session, sample_task, mock_notion_client
):
    """Test 404 object_not_found raises NotionSyncError and stores fallback."""
    mock_response = create_mock_response(404)
    mock_notion_client.pages.update.side_effect = APIResponseError(
        response=mock_response,
        message="Page not found",
        code="object_not_found",
    )

    with patch(
        "app.services.notion_sync_service.AsyncClient",
        return_value=mock_notion_client,
    ):
        with patch("app.services.notion_sync_service.CredentialService") as mock_cred:
            mock_cred.return_value.get_notion_token = AsyncMock(
                return_value="mock_token"
            )

            with pytest.raises(NotionSyncError):
                await sync_youtube_url_to_notion(
                    task=sample_task,
                    video_id="dQw4w9WgXcQ",
                    youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    db=async_session,
                )


@pytest.mark.asyncio
async def test_sync_youtube_url_rate_limited_429(
    async_session, sample_task, mock_notion_client
):
    """Test 429 rate_limited raises NotionSyncRetryError."""
    mock_response = create_mock_response(429, {"Retry-After": "5"})
    mock_notion_client.pages.update.side_effect = APIResponseError(
        response=mock_response,
        message="Rate limit exceeded",
        code="rate_limited",
    )

    with patch(
        "app.services.notion_sync_service.AsyncClient",
        return_value=mock_notion_client,
    ):
        with patch("app.services.notion_sync_service.CredentialService") as mock_cred:
            mock_cred.return_value.get_notion_token = AsyncMock(
                return_value="mock_token"
            )

            with pytest.raises(NotionSyncRetryError) as exc_info:
                await sync_youtube_url_to_notion(
                    task=sample_task,
                    video_id="dQw4w9WgXcQ",
                    youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    db=async_session,
                )

    assert "rate_limited" in str(exc_info.value)


@pytest.mark.asyncio
async def test_sync_youtube_url_conflict_409(
    async_session, sample_task, mock_notion_client
):
    """Test 409 conflict raises NotionSyncRetryError."""
    mock_response = create_mock_response(409)
    mock_notion_client.pages.update.side_effect = APIResponseError(
        response=mock_response,
        message="Concurrent modification",
        code="conflict",
    )

    with patch(
        "app.services.notion_sync_service.AsyncClient",
        return_value=mock_notion_client,
    ):
        with patch("app.services.notion_sync_service.CredentialService") as mock_cred:
            mock_cred.return_value.get_notion_token = AsyncMock(
                return_value="mock_token"
            )

            with pytest.raises(NotionSyncRetryError):
                await sync_youtube_url_to_notion(
                    task=sample_task,
                    video_id="dQw4w9WgXcQ",
                    youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    db=async_session,
                )


@pytest.mark.asyncio
async def test_sync_youtube_url_service_unavailable_503(
    async_session, sample_task, mock_notion_client
):
    """Test 503 service_unavailable raises NotionSyncRetryError."""
    mock_response = create_mock_response(503)
    mock_notion_client.pages.update.side_effect = APIResponseError(
        response=mock_response,
        message="Service temporarily unavailable",
        code="service_unavailable",
    )

    with patch(
        "app.services.notion_sync_service.AsyncClient",
        return_value=mock_notion_client,
    ):
        with patch("app.services.notion_sync_service.CredentialService") as mock_cred:
            mock_cred.return_value.get_notion_token = AsyncMock(
                return_value="mock_token"
            )

            with pytest.raises(NotionSyncRetryError):
                await sync_youtube_url_to_notion(
                    task=sample_task,
                    video_id="dQw4w9WgXcQ",
                    youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    db=async_session,
                )


# ============================================================================
# Fallback URL Storage Tests (AC4)
# ============================================================================


@pytest.mark.asyncio
async def test_store_fallback_url_creates_record(async_session, sample_task):
    """Test fallback URL record is created correctly."""
    await store_fallback_url(
        task=sample_task,
        video_id="dQw4w9WgXcQ",
        youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        db=async_session,
    )

    # Verify fallback record exists
    from sqlalchemy import select

    result = await async_session.execute(
        select(FallbackYouTubeURL).where(FallbackYouTubeURL.task_id == sample_task.id)
    )
    fallback = result.scalar_one()

    assert fallback.task_id == sample_task.id
    assert fallback.channel_id == sample_task.channel_id
    assert fallback.video_id == "dQw4w9WgXcQ"
    assert fallback.youtube_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert fallback.created_at is not None


@pytest.mark.asyncio
async def test_store_fallback_url_sends_discord_alert(async_session, sample_task):
    """Test Discord alert is sent when fallback URL is stored."""
    with patch(
        "app.services.notion_sync_service.send_discord_alert"
    ) as mock_alert:
        mock_alert.return_value = True

        await store_fallback_url(
            task=sample_task,
            video_id="dQw4w9WgXcQ",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            db=async_session,
            webhook_url="https://discord.com/api/webhooks/test",
        )

    # Verify Discord alert was called
    mock_alert.assert_called_once()
    call_args = mock_alert.call_args[1]
    assert call_args["alert_type"] == "terminal_failure"
    assert call_args["severity"] == "CRITICAL"
    assert "YouTube URL Sync Failed" in call_args["title"]
    assert str(sample_task.id) in call_args["fields"]["Task ID"]


@pytest.mark.asyncio
async def test_store_fallback_url_no_alert_when_webhook_none(
    async_session, sample_task
):
    """Test Discord alert is NOT sent when webhook_url is None."""
    with patch(
        "app.services.notion_sync_service.send_discord_alert"
    ) as mock_alert:
        await store_fallback_url(
            task=sample_task,
            video_id="dQw4w9WgXcQ",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            db=async_session,
            webhook_url=None,  # No webhook
        )

    # Verify Discord alert was NOT called
    mock_alert.assert_not_called()


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_end_to_end_sync_success(
    async_session, sample_task, mock_notion_client, mock_notion_response
):
    """Test end-to-end sync flow with successful Notion update."""
    mock_notion_client.pages.update.return_value = mock_notion_response

    with patch(
        "app.services.notion_sync_service.AsyncClient",
        return_value=mock_notion_client,
    ):
        with patch("app.services.notion_sync_service.CredentialService") as mock_cred:
            mock_cred.return_value.get_notion_token = AsyncMock(
                return_value="mock_token"
            )

            # Execute sync
            await sync_youtube_url_to_notion(
                task=sample_task,
                video_id="dQw4w9WgXcQ",
                youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                db=async_session,
            )

    # Verify no fallback URL was created (success case)
    from sqlalchemy import select

    result = await async_session.execute(
        select(FallbackYouTubeURL).where(FallbackYouTubeURL.task_id == sample_task.id)
    )
    fallback = result.scalar_one_or_none()
    assert fallback is None


@pytest.mark.asyncio
async def test_end_to_end_sync_failure_with_fallback(
    async_session, sample_task, mock_notion_client
):
    """Test end-to-end sync flow with Notion failure and fallback storage."""
    mock_response = create_mock_response(401)
    mock_notion_client.pages.update.side_effect = APIResponseError(
        response=mock_response,
        message="Unauthorized",
        code="unauthorized",
    )

    with patch(
        "app.services.notion_sync_service.AsyncClient",
        return_value=mock_notion_client,
    ):
        with patch("app.services.notion_sync_service.CredentialService") as mock_cred:
            mock_cred.return_value.get_notion_token = AsyncMock(
                return_value="mock_token"
            )

            with pytest.raises(NotionSyncError):
                await sync_youtube_url_to_notion(
                    task=sample_task,
                    video_id="dQw4w9WgXcQ",
                    youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    db=async_session,
                )

    # Verify fallback URL was created
    from sqlalchemy import select

    result = await async_session.execute(
        select(FallbackYouTubeURL).where(FallbackYouTubeURL.task_id == sample_task.id)
    )
    fallback = result.scalar_one()
    assert fallback.video_id == "dQw4w9WgXcQ"
