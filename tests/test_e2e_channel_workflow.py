"""E2E integration tests for channel configuration and management workflow.

Tests the complete flow from YAML configuration to database persistence,
credential encryption, and channel capacity tracking. Validates Epic 1
(Foundation & Channel Management) integration points.

Priority: [P0] - Critical path testing
"""

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel
from app.schemas.channel_config import ChannelConfigSchema
from app.services.channel_config_loader import ChannelConfigLoader
from app.services.channel_capacity_service import ChannelCapacityService
from app.services.credential_service import CredentialService
from app.services.storage_strategy_service import StorageStrategyService
from app.services.voice_branding_service import VoiceBrandingService


@pytest_asyncio.fixture
async def credential_service(encryption_env: None) -> CredentialService:
    """Create CredentialService for testing."""
    return CredentialService()


@pytest_asyncio.fixture
async def config_loader() -> ChannelConfigLoader:
    """Create ChannelConfigLoader for testing."""
    return ChannelConfigLoader()


@pytest_asyncio.fixture
async def capacity_service() -> ChannelCapacityService:
    """Create ChannelCapacityService for testing."""
    return ChannelCapacityService()


@pytest_asyncio.fixture
async def storage_service() -> StorageStrategyService:
    """Create StorageStrategyService for testing."""
    return StorageStrategyService()


@pytest_asyncio.fixture
async def voice_service() -> VoiceBrandingService:
    """Create VoiceBrandingService for testing."""
    return VoiceBrandingService()


class TestE2EChannelCreation:
    """E2E tests for complete channel creation workflow."""

    @pytest.mark.asyncio
    async def test_p0_yaml_to_database_sync_with_defaults(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
    ) -> None:
        """Test complete YAML → Database sync with default values.

        Validates:
        - ChannelConfigSchema validation
        - sync_to_database() persistence
        - Default values (max_concurrent=2, storage_strategy='notion')
        """
        # Given: Valid channel config with defaults
        config = ChannelConfigSchema(
            channel_id="e2e_test1",
            channel_name="E2E Test Channel 1",
            notion_database_id="abc123",
        )

        # When: Sync to database
        channel = await config_loader.sync_to_database(config, async_session)

        # Then: Channel persisted with correct defaults
        assert channel.channel_id == "e2e_test1"
        assert channel.channel_name == "E2E Test Channel 1"
        assert channel.max_concurrent == 2  # Default
        assert channel.storage_strategy == "notion"  # Default
        assert channel.is_active is True

        # Verify persistence by reloading
        result = await async_session.execute(
            select(Channel).where(Channel.channel_id == "e2e_test1")
        )
        loaded_channel = result.scalar_one()
        assert loaded_channel.id == channel.id

    @pytest.mark.asyncio
    async def test_p0_yaml_to_database_sync_with_custom_values(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
    ) -> None:
        """Test YAML → Database sync with custom configuration values.

        Validates:
        - Custom max_concurrent setting
        - Voice configuration
        """
        # Given: Channel config with custom values
        config = ChannelConfigSchema(
            channel_id="e2e_test2",
            channel_name="E2E Test Channel 2",
            notion_database_id="def456",
            max_concurrent=5,
            storage_strategy="notion",
            voice_id="custom_voice_123",
        )

        # When: Sync to database
        channel = await config_loader.sync_to_database(config, async_session)

        # Then: All custom values persisted correctly
        assert channel.max_concurrent == 5
        assert channel.storage_strategy == "notion"
        assert channel.voice_id == "custom_voice_123"

    @pytest.mark.asyncio
    async def test_p0_yaml_to_database_update_existing(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
    ) -> None:
        """Test YAML → Database sync updates existing channel.

        Validates:
        - Idempotent sync behavior
        - Updates without creating duplicates
        - Preserves channel UUID
        """
        # Given: Channel synced once
        config_v1 = ChannelConfigSchema(
            channel_id="e2e_test3",
            channel_name="E2E Test Channel 3",
            notion_database_id="ghi789",
            max_concurrent=2,
        )
        channel_v1 = await config_loader.sync_to_database(config_v1, async_session)
        original_id = channel_v1.id

        # When: Sync again with updated values
        config_v2 = ChannelConfigSchema(
            channel_id="e2e_test3",
            channel_name="E2E Test Channel 3 Updated",
            notion_database_id="ghi789",
            max_concurrent=7,
        )
        channel_v2 = await config_loader.sync_to_database(config_v2, async_session)

        # Then: Same channel updated (UUID preserved)
        assert channel_v2.id == original_id
        assert channel_v2.channel_name == "E2E Test Channel 3 Updated"
        assert channel_v2.max_concurrent == 7

        # Verify no duplicates
        result = await async_session.execute(
            select(Channel).where(Channel.channel_id == "e2e_test3")
        )
        channels = result.scalars().all()
        assert len(channels) == 1


class TestE2ECredentialManagement:
    """E2E tests for credential encryption and storage."""

    @pytest.mark.asyncio
    async def test_p0_store_and_retrieve_encrypted_credentials(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
        credential_service: CredentialService,
    ) -> None:
        """Test complete credential encryption workflow.

        Validates:
        - CredentialService encrypt/decrypt cycle
        - Credentials stored encrypted in database
        - Decryption returns original plaintext
        """
        # Given: Channel created
        config = ChannelConfigSchema(
            channel_id="e2e_cred_test",
            channel_name="Credential Test Channel",
            notion_database_id="cred123",
        )
        channel = await config_loader.sync_to_database(config, async_session)

        # When: Store encrypted credentials
        await credential_service.store_youtube_token(
            channel.channel_id, "ya29.a0AfH6SMBxx", async_session
        )
        await credential_service.store_notion_token(
            channel.channel_id, "secret_notion123", async_session
        )
        await credential_service.store_gemini_key(channel.channel_id, "AIzaSyABC123", async_session)

        # Then: Retrieve and decrypt successfully
        youtube_token = await credential_service.get_youtube_token(
            channel.channel_id, async_session
        )
        notion_token = await credential_service.get_notion_token(channel.channel_id, async_session)
        gemini_key = await credential_service.get_gemini_key(channel.channel_id, async_session)

        assert youtube_token == "ya29.a0AfH6SMBxx"
        assert notion_token == "secret_notion123"
        assert gemini_key == "AIzaSyABC123"

        # Verify stored as encrypted bytes in database
        result = await async_session.execute(
            select(Channel).where(Channel.channel_id == "e2e_cred_test")
        )
        db_channel = result.scalar_one()
        assert isinstance(db_channel.youtube_token_encrypted, bytes)
        assert isinstance(db_channel.notion_token_encrypted, bytes)
        assert isinstance(db_channel.gemini_key_encrypted, bytes)
        # Verify NOT stored as plaintext
        assert b"ya29" not in db_channel.youtube_token_encrypted
        assert b"secret" not in db_channel.notion_token_encrypted
        assert b"AIza" not in db_channel.gemini_key_encrypted


class TestE2EChannelCapacity:
    """E2E tests for channel capacity tracking workflow."""

    @pytest.mark.asyncio
    async def test_p0_capacity_tracking_across_services(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
        capacity_service: ChannelCapacityService,
    ) -> None:
        """Test channel capacity tracking integrates with config loader.

        Validates:
        - max_concurrent from YAML affects capacity calculations
        - ChannelCapacityService reads correct max_concurrent value
        - Capacity tracking works for newly synced channels
        """
        # Given: Channel synced with custom max_concurrent
        config = ChannelConfigSchema(
            channel_id="e2e_capacity_test",
            channel_name="Capacity Test Channel",
            notion_database_id="cap123",
            max_concurrent=4,
        )
        await config_loader.sync_to_database(config, async_session)

        # When: Get channel capacity stats
        stats = await capacity_service.get_channel_capacity("e2e_capacity_test", async_session)

        # Then: Capacity stats reflect YAML configuration
        assert stats is not None
        assert stats.channel_id == "e2e_capacity_test"
        assert stats.max_concurrent == 4
        assert stats.has_capacity is True  # No tasks yet
        assert stats.pending_count == 0
        assert stats.in_progress_count == 0


class TestE2EStorageStrategy:
    """E2E tests for storage strategy configuration."""

    @pytest.mark.asyncio
    async def test_p1_storage_strategy_notion_default(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
        storage_service: StorageStrategyService,
    ) -> None:
        """Test default Notion storage strategy workflow.

        Validates:
        - Default storage_strategy='notion'
        - StorageStrategyService reads correct strategy
        """
        # Given: Channel with default storage strategy
        config = ChannelConfigSchema(
            channel_id="e2e_storage_notion",
            channel_name="Notion Storage Channel",
            notion_database_id="notion123",
        )
        await config_loader.sync_to_database(config, async_session)

        # When: Get storage strategy
        strategy = await storage_service.get_storage_strategy("e2e_storage_notion", async_session)

        # Then: Returns Notion strategy
        assert strategy == "notion"

    @pytest.mark.asyncio
    async def test_p1_storage_strategy_r2_custom(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
        storage_service: StorageStrategyService,
        credential_service: CredentialService,
        encryption_env: None,
    ) -> None:
        """Test R2 storage strategy workflow.

        Validates:
        - Custom storage_strategy='r2'
        - R2 configuration fields populated
        """
        # Given: Channel with R2 storage strategy
        from app.schemas.channel_config import R2Config

        config = ChannelConfigSchema(
            channel_id="e2e_storage_r2",
            channel_name="R2 Storage Channel",
            notion_database_id="r2_123",
            storage_strategy="r2",
            r2_config=R2Config(
                account_id="test_account_123",
                access_key_id="test_access_key",
                secret_access_key="test_secret_key",
                bucket_name="my-video-assets",
            ),
        )
        await config_loader.sync_to_database(config, async_session)

        # When: Get storage strategy
        strategy = await storage_service.get_storage_strategy("e2e_storage_r2", async_session)

        # Then: Returns R2 strategy
        assert strategy == "r2"

        # Verify R2 config persisted
        result = await async_session.execute(
            select(Channel).where(Channel.channel_id == "e2e_storage_r2")
        )
        channel = result.scalar_one()
        assert channel.r2_bucket_name == "my-video-assets"


class TestE2EVoiceBranding:
    """E2E tests for voice and branding configuration."""

    @pytest.mark.asyncio
    async def test_p1_voice_branding_complete_workflow(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
        voice_service: VoiceBrandingService,
    ) -> None:
        """Test complete voice and branding configuration workflow.

        Validates:
        - Voice ID from YAML persisted correctly
        - Branding paths from YAML accessible via service
        - VoiceBrandingService integrates with config loader
        """
        # Given: Channel with voice and branding config
        from app.schemas.channel_config import BrandingConfig

        config = ChannelConfigSchema(
            channel_id="e2e_voice_test",
            channel_name="Voice Branding Channel",
            notion_database_id="voice123",
            voice_id="EXAVITQu4vr4xnSDxMaL",
            branding=BrandingConfig(
                intro_video="channel_assets/intro.mp4",
                outro_video="channel_assets/outro.mp4",
                watermark_image="channel_assets/watermark.png",
            ),
        )
        await config_loader.sync_to_database(config, async_session)

        # When: Retrieve via VoiceBrandingService
        voice_id = await voice_service.get_voice_id("e2e_voice_test", async_session)
        branding = await voice_service.get_branding_paths("e2e_voice_test", async_session)

        # Then: Voice and branding accessible
        assert voice_id == "EXAVITQu4vr4xnSDxMaL"
        assert branding is not None
        assert branding.intro_path == "channel_assets/intro.mp4"
        assert branding.outro_path == "channel_assets/outro.mp4"
        assert branding.watermark_path == "channel_assets/watermark.png"
        assert branding.has_any_branding() is True


class TestE2EMultiChannelIsolation:
    """E2E tests for multi-channel isolation and independence."""

    @pytest.mark.asyncio
    async def test_p0_multiple_channels_isolated_configs(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
        capacity_service: ChannelCapacityService,
        voice_service: VoiceBrandingService,
        encryption_env: None,
    ) -> None:
        """Test multiple channels maintain isolated configurations.

        Validates:
        - Multiple channels can coexist
        - Each channel has independent configuration
        - Capacity tracking isolated per channel
        - No configuration leakage between channels
        """
        # Given: Three channels with different configurations
        from app.schemas.channel_config import R2Config

        config1 = ChannelConfigSchema(
            channel_id="multi1",
            channel_name="Multi Channel 1",
            notion_database_id="multi1_db",
            max_concurrent=2,
            voice_id="voice_1",
            storage_strategy="notion",
        )
        config2 = ChannelConfigSchema(
            channel_id="multi2",
            channel_name="Multi Channel 2",
            notion_database_id="multi2_db",
            max_concurrent=5,
            voice_id="voice_2",
            storage_strategy="r2",
            r2_config=R2Config(
                account_id="multi2_account",
                access_key_id="multi2_access",
                secret_access_key="multi2_secret",
                bucket_name="bucket2",
            ),
        )
        config3 = ChannelConfigSchema(
            channel_id="multi3",
            channel_name="Multi Channel 3",
            notion_database_id="multi3_db",
            max_concurrent=3,
            voice_id="voice_3",
            storage_strategy="notion",
        )

        # When: Sync all channels
        await config_loader.sync_to_database(config1, async_session)
        await config_loader.sync_to_database(config2, async_session)
        await config_loader.sync_to_database(config3, async_session)

        # Then: Each channel maintains independent configuration
        stats1 = await capacity_service.get_channel_capacity("multi1", async_session)
        stats2 = await capacity_service.get_channel_capacity("multi2", async_session)
        stats3 = await capacity_service.get_channel_capacity("multi3", async_session)

        assert stats1.max_concurrent == 2
        assert stats2.max_concurrent == 5
        assert stats3.max_concurrent == 3

        voice1 = await voice_service.get_voice_id("multi1", async_session)
        voice2 = await voice_service.get_voice_id("multi2", async_session)
        voice3 = await voice_service.get_voice_id("multi3", async_session)

        assert voice1 == "voice_1"
        assert voice2 == "voice_2"
        assert voice3 == "voice_3"

        # Verify all channels exist independently
        result = await async_session.execute(
            select(Channel).where(Channel.channel_id.in_(["multi1", "multi2", "multi3"]))
        )
        channels = result.scalars().all()
        assert len(channels) == 3
