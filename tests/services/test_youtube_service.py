"""Tests for YouTube service with automatic OAuth token refresh.

Test Coverage:
    - Cache hit (valid token) → No refresh
    - Cache miss → Fetch from DB, create, refresh, cache
    - Expired token → Automatic refresh
    - Expiring soon (< 5 min) → Proactive refresh
    - RefreshError → Alert sent, DB flagged, cache cleared, exception raised
    - Multi-channel isolation → Separate cache entries
    - Concurrent access → Thread-safe cache lock
    - build_youtube_client → Convenience method returns API client
    - No credentials in database → YouTubeAuthError raised
    - Credentials refresh succeeds → Token cached and returned

Story: 7.2 - OAuth Token Refresh Automation
Architecture: Service layer pattern, in-memory cache, async/await
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from app.models import Channel
from app.services.credential_service import CredentialService
from app.services.youtube_service import YouTubeAuthError, YouTubeService


@pytest.fixture
async def channel_poke1(async_session):
    """Create test channel poke1 in database.

    Returns:
        Channel model for testing.
    """
    channel = Channel(
        channel_id="poke1",
        channel_name="Pokemon Nature Docs",
        is_active=True,
        youtube_token_invalid=False,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest.fixture
async def channel_poke2(async_session):
    """Create test channel poke2 in database.

    Returns:
        Channel model for testing.
    """
    channel = Channel(
        channel_id="poke2",
        channel_name="Pokemon Wildlife Channel",
        is_active=True,
        youtube_token_invalid=False,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest.fixture
def youtube_service():
    """YouTubeService with test client credentials.

    Returns:
        YouTubeService instance with test credentials and cleared cache.
    """
    service = YouTubeService(
        client_id="test-client-id.apps.googleusercontent.com",
        client_secret="GOCSPX-test-secret",
    )

    # Clear cache between tests
    service._credentials_cache.clear()

    return service


@pytest.fixture
def mock_refresh_token():
    """Fake refresh token from database.

    Returns:
        Fake Google OAuth refresh token string.
    """
    return "1//0gBxxxxxxxxxxxxxxxxxxxxxxxx"


@pytest.fixture
def valid_credentials(mock_refresh_token, youtube_service):
    """Valid cached credentials (not expired, not expiring soon).

    Returns:
        Credentials object with valid access token expiring in 1 hour.
    """
    return Credentials(
        token="valid-access-token",
        refresh_token=mock_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=youtube_service.client_id,
        client_secret=youtube_service.client_secret,
        expiry=datetime.now(timezone.utc).replace(tzinfo=None)
        + timedelta(hours=1),  # Expires in 1 hour (fresh)
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ],
    )


@pytest.fixture
def expired_credentials(mock_refresh_token, youtube_service):
    """Expired credentials (already expired).

    Returns:
        Credentials object with expired access token.
    """
    return Credentials(
        token="expired-access-token",
        refresh_token=mock_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=youtube_service.client_id,
        client_secret=youtube_service.client_secret,
        expiry=datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(minutes=10),  # Expired 10 min ago
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ],
    )


@pytest.fixture
def expiring_soon_credentials(mock_refresh_token, youtube_service):
    """Credentials expiring soon (< 5 minutes).

    Returns:
        Credentials object with access token expiring in 4 minutes.
    """
    return Credentials(
        token="expiring-soon-token",
        refresh_token=mock_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=youtube_service.client_id,
        client_secret=youtube_service.client_secret,
        expiry=datetime.now(timezone.utc).replace(tzinfo=None)
        + timedelta(minutes=4),  # Expires in 4 min (< 5 min threshold)
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ],
    )


@pytest.mark.asyncio
async def test_get_credentials_cache_hit(youtube_service, async_session, valid_credentials):
    """Test cache hit returns cached credentials without refresh."""
    # Pre-populate cache with valid credentials
    youtube_service._credentials_cache["poke1"] = valid_credentials

    # Get credentials (should use cache, no refresh, no DB call)
    result = await youtube_service.get_credentials("poke1", async_session)

    # Verify same object returned (cache hit)
    assert result is valid_credentials
    assert result.token == "valid-access-token"


@pytest.mark.asyncio
async def test_get_credentials_cache_miss_fetches_from_db(
    youtube_service, async_session, channel_poke1, mock_refresh_token
):
    """Test cache miss fetches refresh token from DB, creates credentials, and caches."""
    # Mock CredentialService.get_youtube_token() to return fake refresh token
    with patch.object(CredentialService, "get_youtube_token", return_value=mock_refresh_token):
        # Mock Credentials.refresh() to simulate successful refresh
        with patch("google.auth.transport.requests.Request"):

            def mock_refresh_callback(self_creds, request):
                # Modify the Credentials instance that called refresh()
                self_creds.token = "new-access-token"
                self_creds.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
                    hours=1
                )

            # Patch the refresh method on Credentials class
            with patch.object(
                Credentials, "refresh", autospec=True, side_effect=mock_refresh_callback
            ):
                # Get credentials (should fetch, create, refresh, cache)
                creds = await youtube_service.get_credentials("poke1", async_session)

                # Verify credentials created and cached
                assert creds.token == "new-access-token"
                assert "poke1" in youtube_service._credentials_cache
                assert youtube_service._credentials_cache["poke1"] is creds


@pytest.mark.asyncio
async def test_get_credentials_no_refresh_token_raises_error(youtube_service, async_session):
    """Test YouTubeAuthError raised when no credentials in database."""
    # Mock CredentialService.get_youtube_token() to return None
    with patch.object(CredentialService, "get_youtube_token", return_value=None):
        # Attempt to get credentials (should raise YouTubeAuthError)
        with pytest.raises(YouTubeAuthError, match="No YouTube credentials found"):
            await youtube_service.get_credentials("poke1", async_session)


@pytest.mark.asyncio
async def test_expired_token_triggers_refresh(youtube_service, async_session, expired_credentials):
    """Test expired access token triggers automatic refresh."""
    # Pre-populate cache with expired credentials
    youtube_service._credentials_cache["poke1"] = expired_credentials

    # Mock Credentials.refresh() to simulate successful refresh
    with patch("google.auth.transport.requests.Request"):
        with patch.object(Credentials, "refresh") as mock_refresh:

            def refresh_token(request):
                expired_credentials.token = "refreshed-access-token"
                expired_credentials.expiry = datetime.now(timezone.utc).replace(
                    tzinfo=None
                ) + timedelta(hours=1)

            mock_refresh.side_effect = refresh_token

            # Get credentials (should trigger refresh)
            creds = await youtube_service.get_credentials("poke1", async_session)

            # Verify refresh was called
            assert mock_refresh.called
            assert creds.token == "refreshed-access-token"


@pytest.mark.asyncio
async def test_proactive_refresh_when_expiring_soon(
    youtube_service, async_session, expiring_soon_credentials
):
    """Test token refreshed proactively when expires in <5 minutes."""
    # Pre-populate cache with credentials expiring in 4 minutes
    youtube_service._credentials_cache["poke1"] = expiring_soon_credentials

    # Mock Credentials.refresh() to simulate successful refresh
    with patch("google.auth.transport.requests.Request"):
        with patch.object(Credentials, "refresh") as mock_refresh:

            def refresh_token(request):
                expiring_soon_credentials.token = "proactively-refreshed-token"
                expiring_soon_credentials.expiry = datetime.now(timezone.utc).replace(
                    tzinfo=None
                ) + timedelta(hours=1)

            mock_refresh.side_effect = refresh_token

            # Get credentials (should proactively refresh)
            result = await youtube_service.get_credentials("poke1", async_session)

            # Verify refresh was called
            assert mock_refresh.called
            assert result.token == "proactively-refreshed-token"


@pytest.mark.asyncio
async def test_refresh_error_sends_alert_and_marks_invalid(
    youtube_service, async_session, channel_poke1, mock_refresh_token
):
    """Test RefreshError triggers alert, marks token invalid, and raises YouTubeAuthError."""
    # Mock CredentialService.get_youtube_token()
    with patch.object(CredentialService, "get_youtube_token", return_value=mock_refresh_token):
        # Mock Credentials.refresh() to raise RefreshError
        with patch("google.auth.transport.requests.Request"):
            with patch.object(Credentials, "refresh", side_effect=RefreshError("invalid_grant")):
                # Mock send_alert
                with patch("app.services.youtube_service.send_alert") as mock_alert:
                    # Attempt to get credentials (should raise YouTubeAuthError)
                    with pytest.raises(YouTubeAuthError, match="Re-authorization required"):
                        await youtube_service.get_credentials("poke1", async_session)

                    # Verify alert was sent
                    assert mock_alert.called
                    call_kwargs = mock_alert.call_args.kwargs
                    assert call_kwargs["level"] == "CRITICAL"
                    assert "re-authorization required" in call_kwargs["message"].lower()
                    assert call_kwargs["details"]["channel_id"] == "poke1"

                    # Verify channel marked invalid
                    await async_session.refresh(channel_poke1)
                    assert channel_poke1.youtube_token_invalid is True

                    # Verify removed from cache
                    assert "poke1" not in youtube_service._credentials_cache


@pytest.mark.asyncio
async def test_multi_channel_isolation(
    youtube_service, async_session, channel_poke1, channel_poke2, mock_refresh_token
):
    """Test cache isolates credentials per channel."""
    # Mock CredentialService.get_youtube_token()
    with patch.object(CredentialService, "get_youtube_token", return_value=mock_refresh_token):
        # Mock Credentials.refresh()
        with patch("google.auth.transport.requests.Request"):
            with patch.object(Credentials, "refresh") as mock_refresh:

                def refresh_token(request):
                    # Set token on all credentials in cache
                    for creds in youtube_service._credentials_cache.values():
                        creds.token = f"token-{creds.refresh_token[-4:]}"
                        creds.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
                            hours=1
                        )

                mock_refresh.side_effect = refresh_token

                # Get credentials for channel 1
                creds1 = await youtube_service.get_credentials("poke1", async_session)

                # Get credentials for channel 2
                creds2 = await youtube_service.get_credentials("poke2", async_session)

                # Verify separate cache entries
                assert "poke1" in youtube_service._credentials_cache
                assert "poke2" in youtube_service._credentials_cache
                assert creds1 is not creds2  # Different objects
                assert creds1 is youtube_service._credentials_cache["poke1"]
                assert creds2 is youtube_service._credentials_cache["poke2"]


@pytest.mark.asyncio
async def test_concurrent_access_thread_safe(
    youtube_service, async_session, channel_poke1, mock_refresh_token
):
    """Test cache lock prevents race conditions during concurrent access."""
    # Mock CredentialService.get_youtube_token()
    with patch.object(CredentialService, "get_youtube_token", return_value=mock_refresh_token):
        # Mock Credentials.refresh()
        with patch("google.auth.transport.requests.Request"):
            with patch.object(Credentials, "refresh") as mock_refresh:
                refresh_count = 0

                def refresh_token(request):
                    nonlocal refresh_count
                    refresh_count += 1
                    # Find credentials and set token
                    for creds in youtube_service._credentials_cache.values():
                        creds.token = f"token-{refresh_count}"
                        creds.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
                            hours=1
                        )

                mock_refresh.side_effect = refresh_token

                # Launch 5 concurrent requests for same channel
                tasks = [youtube_service.get_credentials("poke1", async_session) for _ in range(5)]

                results = await asyncio.gather(*tasks)

                # Lock should prevent too many concurrent refreshes (not all 5)
                # Due to timing, may be 1-2 refreshes (first request + one concurrent)
                # but not 5 (which would indicate no locking)
                assert refresh_count < 5, f"Expected < 5 refreshes, got {refresh_count}"
                assert len(youtube_service._credentials_cache) == 1
                # All results should reference the same cached credentials
                assert all(r is youtube_service._credentials_cache["poke1"] for r in results)


@pytest.mark.asyncio
async def test_build_youtube_client(
    youtube_service, async_session, channel_poke1, mock_refresh_token, valid_credentials
):
    """Test build_youtube_client returns YouTube API client."""
    # Pre-populate cache with valid credentials
    youtube_service._credentials_cache["poke1"] = valid_credentials

    # Mock googleapiclient.discovery.build
    with patch("app.services.youtube_service.build") as mock_build:
        mock_youtube_client = MagicMock()
        mock_build.return_value = mock_youtube_client

        # Build YouTube client
        youtube = await youtube_service.build_youtube_client("poke1", async_session)

        # Verify build was called with correct arguments
        assert mock_build.called
        call_args = mock_build.call_args[0]
        assert call_args[0] == "youtube"
        assert call_args[1] == "v3"

        # Verify credentials passed
        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs["credentials"] is valid_credentials

        # Verify client returned
        assert youtube is mock_youtube_client


@pytest.mark.asyncio
async def test_build_youtube_client_with_invalid_token(
    youtube_service, async_session, mock_refresh_token
):
    """Test build_youtube_client raises YouTubeAuthError when refresh fails."""
    # Mock CredentialService.get_youtube_token()
    with patch.object(CredentialService, "get_youtube_token", return_value=mock_refresh_token):
        # Mock Credentials.refresh() to raise RefreshError
        with patch("google.auth.transport.requests.Request"):
            with patch.object(Credentials, "refresh", side_effect=RefreshError("invalid_grant")):
                # Mock send_alert
                with patch("app.services.youtube_service.send_alert"):
                    # Attempt to build client (should raise YouTubeAuthError)
                    with pytest.raises(YouTubeAuthError, match="Re-authorization required"):
                        await youtube_service.build_youtube_client("poke1", async_session)
