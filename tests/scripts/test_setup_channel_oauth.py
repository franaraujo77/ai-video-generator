"""Tests for YouTube OAuth setup CLI script.

Tests the OAuth flow, token storage, encryption integration, and error handling
for the setup_channel_oauth.py script.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add app directory to path (same as script does)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models import Channel
from app.services.credential_service import CredentialService
from app.utils.encryption import EncryptionKeyMissingError
from scripts.setup_channel_oauth import setup_oauth
from tests.support.factories.channel_factory import create_channel


@pytest.mark.asyncio
async def test_successful_oauth_setup(async_session, encryption_env):
    """Test successful OAuth flow stores encrypted token in database."""
    # Create test channel
    channel = create_channel(channel_id="poke1", channel_name="Test Channel")
    async_session.add(channel)
    await async_session.commit()

    # Mock OAuth flow
    mock_credentials = MagicMock()
    mock_credentials.refresh_token = "1//0gBL9i8xYZ123456789"

    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_credentials

    with patch(
        "scripts.setup_channel_oauth.InstalledAppFlow.from_client_secrets_file",
        return_value=mock_flow,
    ):
        with patch("scripts.setup_channel_oauth.Path.exists", return_value=True):
            # Patch the async_session_factory used by the script
            with patch(
                "scripts.setup_channel_oauth.async_session_factory",
                return_value=async_session,
            ):
                await setup_oauth("poke1", "client_secret.json")

    # Verify token was stored and encrypted
    service = CredentialService()
    stored_token = await service.get_youtube_token("poke1", async_session)
    assert stored_token == "1//0gBL9i8xYZ123456789"


@pytest.mark.asyncio
async def test_channel_not_found_error(async_session, encryption_env):
    """Test error when channel doesn't exist in database."""
    from scripts.setup_channel_oauth import EXIT_GENERIC_ERROR

    with patch("scripts.setup_channel_oauth.Path.exists", return_value=True):
        with patch(
            "scripts.setup_channel_oauth.async_session_factory",
            return_value=async_session,
        ):
            with pytest.raises(SystemExit) as exc_info:
                with patch("builtins.print"):  # Suppress error output
                    await setup_oauth("nonexistent", "client_secret.json")

    assert exc_info.value.code == EXIT_GENERIC_ERROR


@pytest.mark.asyncio
async def test_fernet_key_missing_error(async_session, monkeypatch):
    """Test error when FERNET_KEY environment variable not set."""
    from scripts.setup_channel_oauth import EXIT_CONFIG_ERROR

    # Remove FERNET_KEY from environment
    monkeypatch.delenv("FERNET_KEY", raising=False)

    # Reset encryption service singleton to pick up missing env var
    from app.utils.encryption import EncryptionService

    EncryptionService.reset_instance()

    # Create test channel
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Mock OAuth flow
    mock_credentials = MagicMock()
    mock_credentials.refresh_token = "1//0gBL9i8xYZ123456789"

    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_credentials

    with patch(
        "scripts.setup_channel_oauth.InstalledAppFlow.from_client_secrets_file",
        return_value=mock_flow,
    ):
        with patch("scripts.setup_channel_oauth.Path.exists", return_value=True):
            with patch(
                "scripts.setup_channel_oauth.async_session_factory",
                return_value=async_session,
            ):
                with pytest.raises(SystemExit) as exc_info:
                    with patch("builtins.print"):  # Suppress error output
                        await setup_oauth("poke1", "client_secret.json")

    assert exc_info.value.code == EXIT_CONFIG_ERROR  # Issue #4: Config error exit code


@pytest.mark.asyncio
async def test_client_secret_not_found_error(async_session, encryption_env):
    """Test error when client_secret.json doesn't exist."""
    from scripts.setup_channel_oauth import EXIT_CONFIG_ERROR

    # Create test channel
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Mock Path.exists to return False (file not found)
    with patch("scripts.setup_channel_oauth.Path.exists", return_value=False):
        with patch(
            "scripts.setup_channel_oauth.async_session_factory",
            return_value=async_session,
        ):
            with pytest.raises(SystemExit) as exc_info:
                with patch("builtins.print"):  # Suppress error output
                    await setup_oauth("poke1", "client_secret.json")

    assert exc_info.value.code == EXIT_CONFIG_ERROR  # Issue #4: Config error exit code


@pytest.mark.asyncio
async def test_oauth_consent_denied(async_session, encryption_env):
    """Test error when user denies OAuth consent in browser."""
    from scripts.setup_channel_oauth import EXIT_OAUTH_ERROR

    # Create test channel
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Mock OAuth flow to raise access_denied error
    mock_flow = MagicMock()
    mock_flow.run_local_server.side_effect = Exception("access_denied: User denied access")

    with patch(
        "scripts.setup_channel_oauth.InstalledAppFlow.from_client_secrets_file",
        return_value=mock_flow,
    ):
        with patch("scripts.setup_channel_oauth.Path.exists", return_value=True):
            with patch(
                "scripts.setup_channel_oauth.async_session_factory",
                return_value=async_session,
            ):
                with pytest.raises(SystemExit) as exc_info:
                    with patch("builtins.print"):  # Suppress error output
                        await setup_oauth("poke1", "client_secret.json")

    assert exc_info.value.code == EXIT_OAUTH_ERROR  # Issue #4: OAuth error exit code


@pytest.mark.asyncio
async def test_no_refresh_token_received(async_session, encryption_env):
    """Test error when OAuth doesn't return refresh token (re-authorization case)."""
    from scripts.setup_channel_oauth import EXIT_OAUTH_ERROR

    # Create test channel
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Mock OAuth flow with None refresh_token (user already authorized)
    mock_credentials = MagicMock()
    mock_credentials.refresh_token = None  # CRITICAL: No refresh token

    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_credentials

    with patch(
        "scripts.setup_channel_oauth.InstalledAppFlow.from_client_secrets_file",
        return_value=mock_flow,
    ):
        with patch("scripts.setup_channel_oauth.Path.exists", return_value=True):
            with patch(
                "scripts.setup_channel_oauth.async_session_factory",
                return_value=async_session,
            ):
                with pytest.raises(SystemExit) as exc_info:
                    with patch("builtins.print"):  # Suppress error output
                        await setup_oauth("poke1", "client_secret.json")

    assert exc_info.value.code == EXIT_OAUTH_ERROR  # Issue #4: OAuth error exit code


@pytest.mark.asyncio
async def test_reauthorization_replaces_old_token(async_session, encryption_env):
    """Test that re-running setup replaces old token with new token."""
    # Create channel with existing token
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Store initial token
    service = CredentialService()
    await service.store_youtube_token("poke1", "old_refresh_token", async_session)
    await async_session.commit()

    # Verify old token exists
    old_token = await service.get_youtube_token("poke1", async_session)
    assert old_token == "old_refresh_token"

    # Mock OAuth flow with new token
    mock_credentials = MagicMock()
    mock_credentials.refresh_token = "new_refresh_token"

    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_credentials

    with patch(
        "scripts.setup_channel_oauth.InstalledAppFlow.from_client_secrets_file",
        return_value=mock_flow,
    ):
        with patch("scripts.setup_channel_oauth.Path.exists", return_value=True):
            with patch(
                "scripts.setup_channel_oauth.async_session_factory",
                return_value=async_session,
            ):
                await setup_oauth("poke1", "client_secret.json")

    # Verify new token replaced old token
    new_token = await service.get_youtube_token("poke1", async_session)
    assert new_token == "new_refresh_token"
    assert new_token != old_token


@pytest.mark.asyncio
async def test_multi_channel_isolation(async_session, encryption_env):
    """Test that each channel has its own independent OAuth token."""
    # Create two channels
    channel1 = create_channel(channel_id="poke1", channel_name="Channel 1")
    channel2 = create_channel(channel_id="poke2", channel_name="Channel 2")
    async_session.add_all([channel1, channel2])
    await async_session.commit()

    # Setup OAuth for first channel
    mock_credentials1 = MagicMock()
    mock_credentials1.refresh_token = "token_for_poke1"

    mock_flow1 = MagicMock()
    mock_flow1.run_local_server.return_value = mock_credentials1

    with patch(
        "scripts.setup_channel_oauth.InstalledAppFlow.from_client_secrets_file",
        return_value=mock_flow1,
    ):
        with patch("scripts.setup_channel_oauth.Path.exists", return_value=True):
            with patch(
                "scripts.setup_channel_oauth.async_session_factory",
                return_value=async_session,
            ):
                await setup_oauth("poke1", "client_secret.json")

    # Setup OAuth for second channel
    mock_credentials2 = MagicMock()
    mock_credentials2.refresh_token = "token_for_poke2"

    mock_flow2 = MagicMock()
    mock_flow2.run_local_server.return_value = mock_credentials2

    with patch(
        "scripts.setup_channel_oauth.InstalledAppFlow.from_client_secrets_file",
        return_value=mock_flow2,
    ):
        with patch("scripts.setup_channel_oauth.Path.exists", return_value=True):
            with patch(
                "scripts.setup_channel_oauth.async_session_factory",
                return_value=async_session,
            ):
                await setup_oauth("poke2", "client_secret.json")

    # Verify each channel has its own token
    service = CredentialService()
    token1 = await service.get_youtube_token("poke1", async_session)
    token2 = await service.get_youtube_token("poke2", async_session)

    assert token1 == "token_for_poke1"
    assert token2 == "token_for_poke2"
    assert token1 != token2


@pytest.mark.asyncio
async def test_integration_setup_and_retrieve(async_session, encryption_env):
    """Integration test: Setup token, decrypt, verify same value (no mocking encryption)."""
    # Create test channel
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Mock OAuth flow
    mock_credentials = MagicMock()
    mock_credentials.refresh_token = "1//integration_test_token"

    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_credentials

    with patch(
        "scripts.setup_channel_oauth.InstalledAppFlow.from_client_secrets_file",
        return_value=mock_flow,
    ):
        with patch("scripts.setup_channel_oauth.Path.exists", return_value=True):
            with patch(
                "scripts.setup_channel_oauth.async_session_factory",
                return_value=async_session,
            ):
                await setup_oauth("poke1", "client_secret.json")

    # Retrieve and verify token (full encryption/decryption cycle)
    service = CredentialService()
    retrieved_token = await service.get_youtube_token("poke1", async_session)

    assert retrieved_token == "1//integration_test_token"

    # Verify token is actually encrypted in database
    # Re-fetch the channel from database to get updated state
    from sqlalchemy import select

    result = await async_session.execute(select(Channel).where(Channel.channel_id == "poke1"))
    refreshed_channel = result.scalar_one()

    assert refreshed_channel.youtube_token_encrypted is not None
    assert isinstance(refreshed_channel.youtube_token_encrypted, bytes)
    assert (
        b"integration_test_token" not in refreshed_channel.youtube_token_encrypted
    )  # Not plaintext


@pytest.mark.asyncio
async def test_network_error_during_oauth(async_session, encryption_env):
    """Test error handling for network failures during OAuth."""
    from scripts.setup_channel_oauth import EXIT_NETWORK_ERROR

    # Create test channel
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Mock network error
    mock_flow = MagicMock()
    mock_flow.run_local_server.side_effect = Exception("network error: connection timeout")

    with patch(
        "scripts.setup_channel_oauth.InstalledAppFlow.from_client_secrets_file",
        return_value=mock_flow,
    ):
        with patch("scripts.setup_channel_oauth.Path.exists", return_value=True):
            with patch(
                "scripts.setup_channel_oauth.async_session_factory",
                return_value=async_session,
            ):
                with pytest.raises(SystemExit) as exc_info:
                    with patch("builtins.print"):  # Suppress error output
                        await setup_oauth("poke1", "client_secret.json")

    assert exc_info.value.code == EXIT_NETWORK_ERROR  # Issue #4: Network error exit code


@pytest.mark.asyncio
async def test_database_schema_verification(async_session):
    """Verify youtube_token_encrypted field exists with correct schema (Story 7.1 Issue #1)."""
    from sqlalchemy import LargeBinary, inspect

    # Create channel to verify schema
    channel = create_channel(channel_id="poke1")
    async_session.add(channel)
    await async_session.commit()

    # Verify field exists in model
    assert hasattr(Channel, "youtube_token_encrypted")

    # Verify field schema via SQLAlchemy inspection
    inspector = inspect(Channel)
    columns = {col.name: col for col in inspector.columns}

    assert "youtube_token_encrypted" in columns
    field = columns["youtube_token_encrypted"]

    # Verify field type is LargeBinary (for Fernet encryption)
    assert isinstance(field.type, LargeBinary)

    # Verify field is nullable (channels without YouTube don't need token)
    assert field.nullable is True


@pytest.mark.asyncio
async def test_no_plaintext_token_in_output(async_session, encryption_env, capsys):
    """Verify no plaintext tokens logged to stdout/stderr (Story 7.1 Issue #3 - Security Audit)."""
    # Create test channel
    channel = create_channel(channel_id="poke1", channel_name="Test Channel")
    async_session.add(channel)
    await async_session.commit()

    # Mock OAuth flow with recognizable token
    test_token = "1//SUPER_SECRET_TOKEN_12345_SHOULD_NEVER_APPEAR_IN_LOGS"
    mock_credentials = MagicMock()
    mock_credentials.refresh_token = test_token

    mock_flow = MagicMock()
    mock_flow.run_local_server.return_value = mock_credentials

    with patch(
        "scripts.setup_channel_oauth.InstalledAppFlow.from_client_secrets_file",
        return_value=mock_flow,
    ):
        with patch("scripts.setup_channel_oauth.Path.exists", return_value=True):
            with patch(
                "scripts.setup_channel_oauth.async_session_factory",
                return_value=async_session,
            ):
                await setup_oauth("poke1", "client_secret.json")

    # Capture all stdout/stderr output
    captured = capsys.readouterr()
    combined_output = captured.out + captured.err

    # CRITICAL: Verify plaintext token NEVER appears in output
    assert test_token not in combined_output, "SECURITY VIOLATION: Plaintext token found in output!"
    assert "SUPER_SECRET" not in combined_output, (
        "SECURITY VIOLATION: Token substring found in output!"
    )

    # Verify channel_id (non-sensitive) CAN appear
    assert "poke1" in combined_output or "Test Channel" in combined_output
