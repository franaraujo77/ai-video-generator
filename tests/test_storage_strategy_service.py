"""Tests for the storage strategy service.

This module tests the StorageStrategyService class including storage strategy
resolution, R2 credential retrieval, and error handling.
"""

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConfigurationError
from app.models import Channel
from app.services.storage_strategy_service import (
    R2Credentials,
    StorageStrategyService,
)
from app.utils.encryption import EncryptionService, get_encryption_service


@pytest.fixture
def valid_fernet_key() -> str:
    """Generate a valid Fernet key for testing."""
    return Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def reset_encryption_singleton():
    """Reset the EncryptionService singleton before and after each test."""
    EncryptionService.reset_instance()
    yield
    EncryptionService.reset_instance()


@pytest.fixture
def storage_service() -> StorageStrategyService:
    """Create a StorageStrategyService instance for testing."""
    return StorageStrategyService()


@pytest_asyncio.fixture
async def channel_notion(async_session: AsyncSession) -> Channel:
    """Create test channel with notion storage strategy."""
    channel = Channel(
        channel_id="notion_channel",
        channel_name="Notion Storage Channel",
        storage_strategy="notion",
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest_asyncio.fixture
async def channel_r2_complete(
    async_session: AsyncSession,
    valid_fernet_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Channel:
    """Create test channel with r2 storage strategy and all credentials."""
    monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

    encryption_service = get_encryption_service()

    channel = Channel(
        channel_id="r2_channel",
        channel_name="R2 Storage Channel",
        storage_strategy="r2",
        r2_account_id_encrypted=encryption_service.encrypt("test_account_id"),
        r2_access_key_id_encrypted=encryption_service.encrypt("test_access_key_id"),
        r2_secret_access_key_encrypted=encryption_service.encrypt("test_secret_key"),
        r2_bucket_name="test-bucket",
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest_asyncio.fixture
async def channel_r2_incomplete(async_session: AsyncSession) -> Channel:
    """Create test channel with r2 strategy but missing credentials."""
    channel = Channel(
        channel_id="r2_incomplete",
        channel_name="R2 Incomplete Channel",
        storage_strategy="r2",
        # Missing all R2 credentials
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


class TestStorageStrategyResolution:
    """Test suite for storage strategy resolution."""

    @pytest.mark.asyncio
    async def test_get_storage_strategy_returns_notion_for_notion_channel(
        self,
        storage_service: StorageStrategyService,
        async_session: AsyncSession,
        channel_notion: Channel,
    ) -> None:
        """Test that get_storage_strategy returns 'notion' for notion channel."""
        strategy = await storage_service.get_storage_strategy(
            "notion_channel", async_session
        )
        assert strategy == "notion"

    @pytest.mark.asyncio
    async def test_get_storage_strategy_returns_r2_for_r2_channel(
        self,
        storage_service: StorageStrategyService,
        async_session: AsyncSession,
        channel_r2_complete: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that get_storage_strategy returns 'r2' for r2 channel."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        strategy = await storage_service.get_storage_strategy(
            "r2_channel", async_session
        )
        assert strategy == "r2"

    @pytest.mark.asyncio
    async def test_get_storage_strategy_defaults_to_notion_for_nonexistent_channel(
        self,
        storage_service: StorageStrategyService,
        async_session: AsyncSession,
    ) -> None:
        """Test that get_storage_strategy returns 'notion' for nonexistent channel."""
        strategy = await storage_service.get_storage_strategy(
            "nonexistent_channel", async_session
        )
        assert strategy == "notion"

    @pytest.mark.asyncio
    async def test_get_storage_strategy_defaults_to_notion_when_null(
        self,
        storage_service: StorageStrategyService,
        async_session: AsyncSession,
    ) -> None:
        """Test that get_storage_strategy returns 'notion' when storage_strategy is None."""
        # Create channel without explicit storage_strategy (should be None before migration)
        channel = Channel(
            channel_id="null_strategy",
            channel_name="Null Strategy Channel",
        )
        # Manually set to None to simulate pre-migration state
        channel.storage_strategy = None  # type: ignore[assignment]
        async_session.add(channel)
        await async_session.commit()

        strategy = await storage_service.get_storage_strategy(
            "null_strategy", async_session
        )
        assert strategy == "notion"


class TestR2CredentialRetrieval:
    """Test suite for R2 credential retrieval."""

    @pytest.mark.asyncio
    async def test_get_r2_config_returns_credentials_for_r2_channel(
        self,
        storage_service: StorageStrategyService,
        async_session: AsyncSession,
        channel_r2_complete: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that get_r2_config returns decrypted credentials for r2 channel."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        r2_config = await storage_service.get_r2_config("r2_channel", async_session)

        assert isinstance(r2_config, R2Credentials)
        assert r2_config.account_id == "test_account_id"
        assert r2_config.access_key_id == "test_access_key_id"
        assert r2_config.secret_access_key == "test_secret_key"
        assert r2_config.bucket_name == "test-bucket"

    @pytest.mark.asyncio
    async def test_get_r2_config_raises_for_nonexistent_channel(
        self,
        storage_service: StorageStrategyService,
        async_session: AsyncSession,
    ) -> None:
        """Test that get_r2_config raises ConfigurationError for nonexistent channel."""
        with pytest.raises(ConfigurationError) as exc_info:
            await storage_service.get_r2_config("nonexistent", async_session)

        assert "Channel not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_r2_config_raises_for_notion_channel(
        self,
        storage_service: StorageStrategyService,
        async_session: AsyncSession,
        channel_notion: Channel,
    ) -> None:
        """Test that get_r2_config raises ConfigurationError for notion channel."""
        with pytest.raises(ConfigurationError) as exc_info:
            await storage_service.get_r2_config("notion_channel", async_session)

        assert "storage_strategy='notion'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_r2_config_raises_for_incomplete_credentials(
        self,
        storage_service: StorageStrategyService,
        async_session: AsyncSession,
        channel_r2_incomplete: Channel,
    ) -> None:
        """Test that get_r2_config raises ConfigurationError for missing credentials."""
        with pytest.raises(ConfigurationError) as exc_info:
            await storage_service.get_r2_config("r2_incomplete", async_session)

        assert "missing R2 credentials" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_r2_config_raises_for_partial_credentials(
        self,
        storage_service: StorageStrategyService,
        async_session: AsyncSession,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that get_r2_config raises ConfigurationError for partial credentials."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        encryption_service = get_encryption_service()

        # Channel with only account_id and bucket_name (missing access keys)
        channel = Channel(
            channel_id="r2_partial",
            channel_name="R2 Partial Channel",
            storage_strategy="r2",
            r2_account_id_encrypted=encryption_service.encrypt("acc123"),
            r2_bucket_name="test-bucket",
            # Missing r2_access_key_id_encrypted and r2_secret_access_key_encrypted
        )
        async_session.add(channel)
        await async_session.commit()

        with pytest.raises(ConfigurationError) as exc_info:
            await storage_service.get_r2_config("r2_partial", async_session)

        # Should list missing fields
        assert "r2_access_key_id" in str(exc_info.value)
        assert "r2_secret_access_key" in str(exc_info.value)


class TestR2CredentialsDataclass:
    """Test suite for R2Credentials dataclass."""

    def test_r2_credentials_repr_masks_secrets(self) -> None:
        """Test that R2Credentials repr masks sensitive fields."""
        creds = R2Credentials(
            account_id="secret_account",
            access_key_id="secret_key_id",
            secret_access_key="super_secret",
            bucket_name="my-bucket",
        )

        repr_str = repr(creds)

        # Bucket name should be visible
        assert "my-bucket" in repr_str
        # Secrets should be masked
        assert "secret_account" not in repr_str
        assert "secret_key_id" not in repr_str
        assert "super_secret" not in repr_str
        assert "*****" in repr_str

    def test_r2_credentials_stores_all_fields(self) -> None:
        """Test that R2Credentials stores all fields correctly."""
        creds = R2Credentials(
            account_id="acc123",
            access_key_id="key456",
            secret_access_key="secret789",
            bucket_name="test-bucket",
        )

        assert creds.account_id == "acc123"
        assert creds.access_key_id == "key456"
        assert creds.secret_access_key == "secret789"
        assert creds.bucket_name == "test-bucket"


class TestMultiChannelStorageIsolation:
    """Test suite for multi-channel storage isolation."""

    @pytest.mark.asyncio
    async def test_different_channels_have_different_storage_strategies(
        self,
        storage_service: StorageStrategyService,
        async_session: AsyncSession,
        channel_notion: Channel,
        channel_r2_complete: Channel,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that different channels can have different storage strategies."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        notion_strategy = await storage_service.get_storage_strategy(
            "notion_channel", async_session
        )
        r2_strategy = await storage_service.get_storage_strategy(
            "r2_channel", async_session
        )

        assert notion_strategy == "notion"
        assert r2_strategy == "r2"
        assert notion_strategy != r2_strategy

    @pytest.mark.asyncio
    async def test_multiple_r2_channels_have_independent_credentials(
        self,
        storage_service: StorageStrategyService,
        async_session: AsyncSession,
        valid_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that different R2 channels have independent credentials."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        encryption_service = get_encryption_service()

        # Create two R2 channels with different credentials
        channel1 = Channel(
            channel_id="r2_channel1",
            channel_name="R2 Channel 1",
            storage_strategy="r2",
            r2_account_id_encrypted=encryption_service.encrypt("account1"),
            r2_access_key_id_encrypted=encryption_service.encrypt("key1"),
            r2_secret_access_key_encrypted=encryption_service.encrypt("secret1"),
            r2_bucket_name="bucket-1",
        )
        channel2 = Channel(
            channel_id="r2_channel2",
            channel_name="R2 Channel 2",
            storage_strategy="r2",
            r2_account_id_encrypted=encryption_service.encrypt("account2"),
            r2_access_key_id_encrypted=encryption_service.encrypt("key2"),
            r2_secret_access_key_encrypted=encryption_service.encrypt("secret2"),
            r2_bucket_name="bucket-2",
        )
        async_session.add(channel1)
        async_session.add(channel2)
        await async_session.commit()

        # Get credentials for each channel
        creds1 = await storage_service.get_r2_config("r2_channel1", async_session)
        creds2 = await storage_service.get_r2_config("r2_channel2", async_session)

        # Verify isolation
        assert creds1.account_id == "account1"
        assert creds2.account_id == "account2"
        assert creds1.bucket_name == "bucket-1"
        assert creds2.bucket_name == "bucket-2"


class TestDatabaseMigration:
    """Test suite for storage strategy migration."""

    def test_channel_model_has_storage_strategy_column(self) -> None:
        """Test that Channel model has storage_strategy column."""
        from app.models import Channel

        assert hasattr(Channel, "storage_strategy")

    def test_channel_model_has_r2_credential_columns(self) -> None:
        """Test that Channel model has all R2 credential columns."""
        from app.models import Channel

        assert hasattr(Channel, "r2_account_id_encrypted")
        assert hasattr(Channel, "r2_access_key_id_encrypted")
        assert hasattr(Channel, "r2_secret_access_key_encrypted")
        assert hasattr(Channel, "r2_bucket_name")

    def test_storage_strategy_column_has_default(self) -> None:
        """Test that storage_strategy column has default value of 'notion'."""
        from app.models import Channel

        col = Channel.__table__.columns["storage_strategy"]
        assert col.server_default is not None
        assert col.server_default.arg == "notion"

    def test_r2_credential_columns_are_nullable(self) -> None:
        """Test that R2 credential columns are nullable."""
        from app.models import Channel

        account_col = Channel.__table__.columns["r2_account_id_encrypted"]
        access_col = Channel.__table__.columns["r2_access_key_id_encrypted"]
        secret_col = Channel.__table__.columns["r2_secret_access_key_encrypted"]
        bucket_col = Channel.__table__.columns["r2_bucket_name"]

        assert account_col.nullable is True
        assert access_col.nullable is True
        assert secret_col.nullable is True
        assert bucket_col.nullable is True

    def test_migration_file_exists_and_is_valid(self) -> None:
        """Test that the storage strategy migration file exists and is valid."""
        import importlib.util
        from pathlib import Path

        # Use glob to find migration file (more robust to renames)
        migrations_dir = Path("alembic/versions")
        assert migrations_dir.exists(), f"Migrations directory not found: {migrations_dir}"

        # Find migration with "storage_strategy" in name
        migration_files = list(migrations_dir.glob("*storage_strategy*.py"))
        assert len(migration_files) >= 1, (
            "No migration file found with 'storage_strategy' in name"
        )

        migration_path = migration_files[0]

        # Load the migration module
        spec = importlib.util.spec_from_file_location("migration", migration_path)
        assert spec is not None
        assert spec.loader is not None

        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        # Verify revision chain
        assert migration.revision == "004_add_storage_strategy"
        assert migration.down_revision == "003_add_voice_branding"

        # Verify upgrade and downgrade functions exist and are callable
        assert hasattr(migration, "upgrade"), "Migration missing upgrade function"
        assert hasattr(migration, "downgrade"), "Migration missing downgrade function"
        assert callable(migration.upgrade), "upgrade is not callable"
        assert callable(migration.downgrade), "downgrade is not callable"
