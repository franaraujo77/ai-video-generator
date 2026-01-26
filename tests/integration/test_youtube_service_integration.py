"""Integration tests for YouTubeService with database.

These tests verify YouTubeService works correctly with a real database
session (async SQLite test database), validating the full flow including:
- Database queries for refresh tokens
- Cache management with database state
- Error handling with database transactions
- Channel flag updates on token failures

Story: 7.2 - OAuth Token Refresh Automation
Architecture: Integration testing pattern with async test database
"""

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch, MagicMock

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from app.models import Channel
from app.services.youtube_service import YouTubeService, YouTubeAuthError
from app.services.credential_service import CredentialService


@pytest.fixture
async def test_channel(async_session):
    """Create test channel with YouTube credentials in database.

    Returns:
        Channel model with encrypted refresh token.
    """
    channel = Channel(
        channel_id="integration_test_channel",
        channel_name="Integration Test Channel",
        is_active=True,
        youtube_token_invalid=False,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest.fixture
def youtube_service():
    """YouTubeService instance with test credentials.

    Returns:
        YouTubeService configured for testing.
    """
    service = YouTubeService(
        client_id="test-integration-client.apps.googleusercontent.com",
        client_secret="GOCSPX-test-integration-secret",
    )
    # Clear cache between tests
    service._credentials_cache.clear()
    return service


@pytest.mark.asyncio
async def test_full_refresh_flow_with_database(youtube_service, async_session, test_channel):
    """Test complete token refresh flow with database integration.

    Verifies:
    1. Fetch refresh token from database (via CredentialService)
    2. Create Credentials object
    3. Refresh access token
    4. Cache credentials in memory
    5. Subsequent calls use cache (no DB query)
    """
    mock_refresh_token = "1//0gBtest-integration-refresh-token"

    # Mock CredentialService to return refresh token from database
    with patch.object(CredentialService, "get_youtube_token", return_value=mock_refresh_token):
        # Mock google-auth refresh
        with patch("google.auth.transport.requests.Request"):
            with patch.object(Credentials, "refresh", autospec=True) as mock_refresh:

                def mock_refresh_callback(self_creds, request):
                    # Simulate successful token refresh (modify credentials object)
                    self_creds.token = "fresh-access-token"
                    self_creds.expiry = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)

                mock_refresh.side_effect = mock_refresh_callback

                # First call: should fetch from DB, refresh, cache
                creds1 = await youtube_service.get_credentials(
                    "integration_test_channel", async_session
                )

                assert creds1.token == "fresh-access-token"
                assert creds1.refresh_token == mock_refresh_token
                assert "integration_test_channel" in youtube_service._credentials_cache

                # Second call: should use cache (no DB fetch)
                creds2 = await youtube_service.get_credentials(
                    "integration_test_channel", async_session
                )

                # Same object from cache
                assert creds2 is creds1
                assert creds2.token == "fresh-access-token"


@pytest.mark.asyncio
async def test_refresh_error_updates_database_flag(youtube_service, async_session, test_channel):
    """Test RefreshError properly updates database youtube_token_invalid flag.

    Verifies:
    1. RefreshError triggers database update
    2. youtube_token_invalid set to True
    3. Channel remains in database (not deleted)
    4. Alert sent to operators
    """
    mock_refresh_token = "1//0gBinvalid-refresh-token"

    # Mock CredentialService
    with patch.object(CredentialService, "get_youtube_token", return_value=mock_refresh_token):
        # Mock google-auth to raise RefreshError
        with patch("google.auth.transport.requests.Request"):
            with patch.object(Credentials, "refresh", side_effect=RefreshError("invalid_grant")):
                # Mock send_alert
                with patch("app.services.youtube_service.send_alert") as mock_alert:
                    # Attempt refresh (should fail and update DB)
                    with pytest.raises(YouTubeAuthError):
                        await youtube_service.get_credentials(
                            "integration_test_channel", async_session
                        )

                    # Verify alert was sent
                    assert mock_alert.called

                    # Refresh channel from database
                    await async_session.refresh(test_channel)

                    # Verify flag was set
                    assert test_channel.youtube_token_invalid is True

                    # Verify cache cleared
                    assert "integration_test_channel" not in youtube_service._credentials_cache


@pytest.mark.asyncio
async def test_network_error_clears_cache_but_not_database_flag(
    youtube_service, async_session, test_channel
):
    """Test network errors clear cache but don't mark token invalid.

    Verifies:
    1. Network error during refresh clears cache
    2. youtube_token_invalid flag NOT set (transient error)
    3. Exception re-raised for worker retry logic
    """
    from requests.exceptions import ConnectionError

    mock_refresh_token = "1//0gBvalid-but-network-failed"

    # Mock CredentialService
    with patch.object(CredentialService, "get_youtube_token", return_value=mock_refresh_token):
        # Mock google-auth to raise ConnectionError
        with patch("google.auth.transport.requests.Request"):
            with patch.object(
                Credentials,
                "refresh",
                side_effect=ConnectionError("Network unreachable"),
            ):
                # Attempt refresh (should fail with network error)
                with pytest.raises(ConnectionError):
                    await youtube_service.get_credentials("integration_test_channel", async_session)

                # Refresh channel from database
                await async_session.refresh(test_channel)

                # Verify flag was NOT set (network error is transient)
                assert test_channel.youtube_token_invalid is False

                # Verify cache cleared (prevent using stale creds)
                assert "integration_test_channel" not in youtube_service._credentials_cache
