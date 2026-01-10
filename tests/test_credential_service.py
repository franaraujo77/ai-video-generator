"""Tests for the credential management service.

This module tests the CredentialService class including storing and retrieving
encrypted credentials, multi-channel isolation, and error handling.
"""

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel
from app.services.credential_service import CredentialService
from app.utils.encryption import DecryptionError, EncryptionService


@pytest.fixture
def valid_fernet_key() -> str:
    """Generate a valid Fernet key for testing."""
    return Fernet.generate_key().decode()


@pytest.fixture
def different_fernet_key() -> str:
    """Generate a different Fernet key for testing decryption errors."""
    return Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def reset_encryption_singleton():
    """Reset the EncryptionService singleton before and after each test."""
    EncryptionService.reset_instance()
    yield
    EncryptionService.reset_instance()


@pytest.fixture
def credential_service() -> CredentialService:
    """Create a CredentialService instance for testing."""
    return CredentialService()


@pytest_asyncio.fixture
async def channel_poke1(async_session: AsyncSession) -> Channel:
    """Create test channel 'poke1'."""
    channel = Channel(
        channel_id="poke1",
        channel_name="Pokemon Channel 1",
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest_asyncio.fixture
async def channel_nature1(async_session: AsyncSession) -> Channel:
    """Create test channel 'nature1'."""
    channel = Channel(
        channel_id="nature1",
        channel_name="Nature Channel 1",
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


class TestCredentialServiceYouTubeToken:
    """Test suite for YouTube token storage and retrieval."""

    async def test_store_and_retrieve_youtube_token(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test storing and retrieving a YouTube token for a channel."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        token = "ya29.a0AVA9y1t...test_token"

        # Store token
        await credential_service.store_youtube_token("poke1", token, async_session)

        # Retrieve token
        retrieved = await credential_service.get_youtube_token("poke1", async_session)

        assert retrieved == token

    async def test_get_token_returns_none_for_channel_without_token(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that get_youtube_token returns None when channel has no token."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        # Channel exists but has no token
        token = await credential_service.get_youtube_token("poke1", async_session)

        assert token is None

    async def test_get_token_returns_none_for_nonexistent_channel(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that get_youtube_token returns None for nonexistent channel."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        token = await credential_service.get_youtube_token("nonexistent", async_session)

        assert token is None

    async def test_store_token_raises_for_nonexistent_channel(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that store_youtube_token raises ValueError for nonexistent channel."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        with pytest.raises(ValueError) as exc_info:
            await credential_service.store_youtube_token(
                "nonexistent", "token", async_session
            )

        assert "Channel not found: nonexistent" in str(exc_info.value)

    async def test_token_update_overwrites_existing(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that storing a new token overwrites the existing one."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        # Store first token
        await credential_service.store_youtube_token(
            "poke1", "first_token", async_session
        )

        # Store second token (should overwrite)
        await credential_service.store_youtube_token(
            "poke1", "second_token", async_session
        )

        # Should get the second token
        retrieved = await credential_service.get_youtube_token("poke1", async_session)

        assert retrieved == "second_token"


class TestCredentialServiceNotionToken:
    """Test suite for Notion token storage and retrieval."""

    async def test_store_and_retrieve_notion_token(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test storing and retrieving a Notion token for a channel."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        token = "secret_abc123xyz..."

        await credential_service.store_notion_token("poke1", token, async_session)
        retrieved = await credential_service.get_notion_token("poke1", async_session)

        assert retrieved == token

    async def test_get_notion_token_returns_none_when_not_set(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that get_notion_token returns None when not set."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        token = await credential_service.get_notion_token("poke1", async_session)

        assert token is None


class TestCredentialServiceMultiChannel:
    """Test suite for multi-channel credential isolation."""

    async def test_multiple_channels_have_independent_tokens(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        channel_nature1: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that different channels can have different YouTube tokens (AC: #3)."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        poke1_token = "ya29.poke1_specific_token"
        nature1_token = "ya29.nature1_specific_token"

        # Store tokens for each channel
        await credential_service.store_youtube_token(
            "poke1", poke1_token, async_session
        )
        await credential_service.store_youtube_token(
            "nature1", nature1_token, async_session
        )

        # Retrieve and verify isolation
        retrieved_poke1 = await credential_service.get_youtube_token(
            "poke1", async_session
        )
        retrieved_nature1 = await credential_service.get_youtube_token(
            "nature1", async_session
        )

        assert retrieved_poke1 == poke1_token
        assert retrieved_nature1 == nature1_token
        assert retrieved_poke1 != retrieved_nature1

    async def test_multiple_credential_types_per_channel(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that a channel can have multiple credential types."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        youtube_token = "ya29.youtube_token"
        notion_token = "secret_notion_token"
        gemini_key = "AIza_gemini_key"
        elevenlabs_key = "el_elevenlabs_key"

        # Store all credential types
        await credential_service.store_youtube_token(
            "poke1", youtube_token, async_session
        )
        await credential_service.store_notion_token(
            "poke1", notion_token, async_session
        )
        await credential_service.store_gemini_key("poke1", gemini_key, async_session)
        await credential_service.store_elevenlabs_key(
            "poke1", elevenlabs_key, async_session
        )

        # Retrieve and verify all credentials
        assert (
            await credential_service.get_youtube_token("poke1", async_session)
            == youtube_token
        )
        assert (
            await credential_service.get_notion_token("poke1", async_session)
            == notion_token
        )
        assert (
            await credential_service.get_gemini_key("poke1", async_session) == gemini_key
        )
        assert (
            await credential_service.get_elevenlabs_key("poke1", async_session)
            == elevenlabs_key
        )


class TestCredentialServiceDecryptionErrors:
    """Test suite for decryption error handling."""

    async def test_decryption_error_raised_with_wrong_key(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        valid_fernet_key: str,
        different_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that DecryptionError is raised when decrypting with wrong key (AC: #2)."""
        # Store with first key
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)
        await credential_service.store_youtube_token(
            "poke1", "test_token", async_session
        )

        # Reset singleton and try to retrieve with different key
        EncryptionService.reset_instance()
        monkeypatch.setenv("FERNET_KEY", different_fernet_key)

        with pytest.raises(DecryptionError) as exc_info:
            await credential_service.get_youtube_token("poke1", async_session)

        # Should include channel_id in error
        assert exc_info.value.channel_id == "poke1"

    async def test_decryption_error_is_not_generic_exception(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        valid_fernet_key: str,
        different_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that decryption failure raises DecryptionError, not generic Exception (AC: #2)."""
        # Store with first key
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)
        await credential_service.store_youtube_token(
            "poke1", "test_token", async_session
        )

        # Reset singleton and try to retrieve with different key
        EncryptionService.reset_instance()
        monkeypatch.setenv("FERNET_KEY", different_fernet_key)

        # Should raise DecryptionError specifically, not a generic Exception
        with pytest.raises(DecryptionError):
            await credential_service.get_youtube_token("poke1", async_session)


class TestCredentialServiceGeminiKey:
    """Test suite for Gemini API key storage and retrieval."""

    async def test_store_and_retrieve_gemini_key(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test storing and retrieving a Gemini API key."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        api_key = "AIzaSyB-test-key-123"

        await credential_service.store_gemini_key("poke1", api_key, async_session)
        retrieved = await credential_service.get_gemini_key("poke1", async_session)

        assert retrieved == api_key

    async def test_get_gemini_key_returns_none_when_not_set(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that get_gemini_key returns None when not set."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        key = await credential_service.get_gemini_key("poke1", async_session)

        assert key is None


class TestCredentialServiceElevenLabsKey:
    """Test suite for ElevenLabs API key storage and retrieval."""

    async def test_store_and_retrieve_elevenlabs_key(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test storing and retrieving an ElevenLabs API key."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        api_key = "el-test-key-456"

        await credential_service.store_elevenlabs_key("poke1", api_key, async_session)
        retrieved = await credential_service.get_elevenlabs_key("poke1", async_session)

        assert retrieved == api_key

    async def test_get_elevenlabs_key_returns_none_when_not_set(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that get_elevenlabs_key returns None when not set."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        key = await credential_service.get_elevenlabs_key("poke1", async_session)

        assert key is None


class TestCredentialServiceDatabaseStorage:
    """Test suite for verifying credentials are actually encrypted in database."""

    async def test_stored_token_is_encrypted_in_database(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that the token stored in database is encrypted, not plaintext."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        plaintext_token = "ya29.a0_plaintext_token"

        await credential_service.store_youtube_token(
            "poke1", plaintext_token, async_session
        )

        # Refresh to get latest data from database
        await async_session.refresh(channel_poke1)

        # Verify stored data is bytes (encrypted)
        assert isinstance(channel_poke1.youtube_token_encrypted, bytes)

        # Verify stored data is NOT the plaintext
        assert channel_poke1.youtube_token_encrypted != plaintext_token.encode()

        # Verify we can still decrypt it
        retrieved = await credential_service.get_youtube_token("poke1", async_session)
        assert retrieved == plaintext_token


class TestCredentialServiceUnicodeChannelIds:
    """Test suite for unicode channel ID handling (edge case)."""

    async def test_unicode_channel_id_store_and_retrieve(
        self,
        credential_service: CredentialService,
        async_session: AsyncSession,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test storing and retrieving credentials with unicode channel ID."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        # Create channel with unicode ID
        unicode_channel = Channel(
            channel_id="ポケモン1",
            channel_name="Pokemon Japanese Channel",
        )
        async_session.add(unicode_channel)
        await async_session.commit()

        token = "ya29.unicode_test_token"

        # Store and retrieve
        await credential_service.store_youtube_token("ポケモン1", token, async_session)
        retrieved = await credential_service.get_youtube_token("ポケモン1", async_session)

        assert retrieved == token


class TestDatabaseMigration:
    """Test suite for database migration (Task 6.11).

    These tests verify the Alembic migration correctly adds encrypted
    credential columns to the channels table.
    """

    def test_channel_model_has_encrypted_columns(self) -> None:
        """Test that Channel model has all encrypted credential columns."""
        from app.models import Channel

        # Verify all encrypted columns exist in the model
        assert hasattr(Channel, "youtube_token_encrypted")
        assert hasattr(Channel, "notion_token_encrypted")
        assert hasattr(Channel, "gemini_key_encrypted")
        assert hasattr(Channel, "elevenlabs_key_encrypted")

    def test_encrypted_columns_are_nullable(self) -> None:
        """Test that encrypted columns are nullable (channels may not have credentials)."""
        from app.models import Channel

        # Get column definitions
        youtube_col = Channel.__table__.columns["youtube_token_encrypted"]
        notion_col = Channel.__table__.columns["notion_token_encrypted"]
        gemini_col = Channel.__table__.columns["gemini_key_encrypted"]
        elevenlabs_col = Channel.__table__.columns["elevenlabs_key_encrypted"]

        # All should be nullable
        assert youtube_col.nullable is True
        assert notion_col.nullable is True
        assert gemini_col.nullable is True
        assert elevenlabs_col.nullable is True

    def test_encrypted_columns_are_largebinary(self) -> None:
        """Test that encrypted columns use LargeBinary type for Fernet bytes."""
        from sqlalchemy import LargeBinary

        from app.models import Channel

        youtube_col = Channel.__table__.columns["youtube_token_encrypted"]
        notion_col = Channel.__table__.columns["notion_token_encrypted"]
        gemini_col = Channel.__table__.columns["gemini_key_encrypted"]
        elevenlabs_col = Channel.__table__.columns["elevenlabs_key_encrypted"]

        # All should be LargeBinary type
        assert isinstance(youtube_col.type, LargeBinary)
        assert isinstance(notion_col.type, LargeBinary)
        assert isinstance(gemini_col.type, LargeBinary)
        assert isinstance(elevenlabs_col.type, LargeBinary)

    def test_migration_file_is_valid(self) -> None:
        """Test that the migration file can be imported and has required functions."""
        import importlib.util
        from pathlib import Path

        migration_path = Path(
            "alembic/versions/20260110_0002_002_add_encrypted_credential_columns.py"
        )
        assert migration_path.exists(), f"Migration file not found: {migration_path}"

        # Load the migration module
        spec = importlib.util.spec_from_file_location("migration", migration_path)
        assert spec is not None
        assert spec.loader is not None

        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        # Verify required Alembic attributes
        assert hasattr(migration, "revision")
        assert hasattr(migration, "down_revision")
        assert hasattr(migration, "upgrade")
        assert hasattr(migration, "downgrade")

        # Verify revision chain
        assert migration.revision == "002_add_encrypted_credentials"
        assert migration.down_revision == "001_initial_channels"

    def test_migration_upgrade_adds_columns(self) -> None:
        """Test that migration upgrade function references all 4 columns."""
        import inspect
        from pathlib import Path

        migration_path = Path(
            "alembic/versions/20260110_0002_002_add_encrypted_credential_columns.py"
        )
        content = migration_path.read_text()

        # Verify upgrade adds all 4 columns
        assert "youtube_token_encrypted" in content
        assert "notion_token_encrypted" in content
        assert "gemini_key_encrypted" in content
        assert "elevenlabs_key_encrypted" in content
        assert "op.add_column" in content

    def test_migration_downgrade_removes_columns(self) -> None:
        """Test that migration downgrade function removes all 4 columns."""
        from pathlib import Path

        migration_path = Path(
            "alembic/versions/20260110_0002_002_add_encrypted_credential_columns.py"
        )
        content = migration_path.read_text()

        # Verify downgrade drops all 4 columns
        assert "op.drop_column" in content
        # Count drop_column calls (should be 4)
        assert content.count("op.drop_column") == 4
