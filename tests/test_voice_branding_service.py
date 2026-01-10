"""Tests for VoiceBrandingService.

This module tests:
- Voice ID resolution with channel-specific voice
- Voice ID fallback to default when channel voice is None (AC #2)
- Voice ID isolation between channels (AC #3)
- Branding path resolution
- Branding missing gracefully handled
"""

import os
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel
from app.services.voice_branding_service import (
    BrandingPaths,
    ConfigurationError,
    VoiceBrandingService,
)


class TestVoiceBrandingService:
    """Tests for VoiceBrandingService class."""

    @pytest_asyncio.fixture
    async def service(self) -> VoiceBrandingService:
        """Create VoiceBrandingService instance."""
        return VoiceBrandingService()

    @pytest_asyncio.fixture
    async def channel_with_voice(self, async_session: AsyncSession) -> Channel:
        """Create channel with voice_id set."""
        channel = Channel(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            voice_id="voice_abc123",
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)
        return channel

    @pytest_asyncio.fixture
    async def channel_without_voice(self, async_session: AsyncSession) -> Channel:
        """Create channel without voice_id (None)."""
        channel = Channel(
            channel_id="poke2",
            channel_name="Pokemon Channel 2",
            voice_id=None,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)
        return channel

    @pytest_asyncio.fixture
    async def channel_with_branding(self, async_session: AsyncSession) -> Channel:
        """Create channel with branding paths set."""
        channel = Channel(
            channel_id="poke3",
            channel_name="Pokemon Channel 3",
            voice_id="voice_xyz789",
            branding_intro_path="channel_assets/intro.mp4",
            branding_outro_path="channel_assets/outro.mp4",
            branding_watermark_path="channel_assets/watermark.png",
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)
        return channel

    @pytest.mark.asyncio
    async def test_get_voice_id_channel_specific(
        self,
        service: VoiceBrandingService,
        channel_with_voice: Channel,
        async_session: AsyncSession,
    ):
        """Test get_voice_id returns channel-specific voice when set."""
        voice_id = await service.get_voice_id("poke1", async_session)

        assert voice_id == "voice_abc123"

    @pytest.mark.asyncio
    async def test_get_voice_id_fallback_to_default(
        self,
        service: VoiceBrandingService,
        channel_without_voice: Channel,
        async_session: AsyncSession,
    ):
        """Test get_voice_id falls back to DEFAULT_VOICE_ID when channel voice is None (AC #2)."""
        with patch.dict(os.environ, {"DEFAULT_VOICE_ID": "default_voice_123"}):
            voice_id = await service.get_voice_id("poke2", async_session)

            assert voice_id == "default_voice_123"

    @pytest.mark.asyncio
    async def test_get_voice_id_logs_warning_on_fallback(
        self,
        service: VoiceBrandingService,
        channel_without_voice: Channel,
        async_session: AsyncSession,
    ):
        """Test get_voice_id logs warning when using default (AC #2)."""
        with patch.dict(os.environ, {"DEFAULT_VOICE_ID": "default_voice_123"}):
            # Mock the structlog logger to verify warning is called
            with patch("app.services.voice_branding_service.log") as mock_log:
                await service.get_voice_id("poke2", async_session)

                # Verify warning was logged about using default voice
                mock_log.warning.assert_called_once()
                call_args = mock_log.warning.call_args

                # Check the event name is correct
                assert call_args[0][0] == "using_default_voice_id"

                # Check the keyword arguments include channel_id and reason
                assert call_args[1]["channel_id"] == "poke2"
                # Voice ID is truncated to first 8 chars + "..." for logging
                assert call_args[1]["default_voice_id"] == "default_..."
                assert call_args[1]["reason"] == "channel_voice_id_not_set"

    @pytest.mark.asyncio
    async def test_get_voice_id_raises_when_no_default(
        self,
        service: VoiceBrandingService,
        channel_without_voice: Channel,
        async_session: AsyncSession,
    ):
        """Test get_voice_id raises ConfigurationError when no voice_id and no default."""
        # Ensure DEFAULT_VOICE_ID is not set
        with patch.dict(os.environ, {}, clear=True):
            # Remove DEFAULT_VOICE_ID if it exists
            if "DEFAULT_VOICE_ID" in os.environ:
                del os.environ["DEFAULT_VOICE_ID"]

            with patch("app.config.get_default_voice_id", return_value=None):
                with pytest.raises(ConfigurationError) as exc_info:
                    await service.get_voice_id("poke2", async_session)

                assert "No voice_id configured" in str(exc_info.value)
                assert "poke2" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_voice_id_channel_not_found(
        self,
        service: VoiceBrandingService,
        async_session: AsyncSession,
    ):
        """Test get_voice_id raises ValueError when channel not found."""
        with pytest.raises(ValueError) as exc_info:
            await service.get_voice_id("nonexistent", async_session)

        assert "Channel not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_branding_paths_returns_paths(
        self,
        service: VoiceBrandingService,
        channel_with_branding: Channel,
        async_session: AsyncSession,
    ):
        """Test get_branding_paths returns channel-specific paths."""
        branding = await service.get_branding_paths("poke3", async_session)

        assert isinstance(branding, BrandingPaths)
        assert branding.intro_path == "channel_assets/intro.mp4"
        assert branding.outro_path == "channel_assets/outro.mp4"
        assert branding.watermark_path == "channel_assets/watermark.png"
        assert branding.has_any_branding() is True

    @pytest.mark.asyncio
    async def test_get_branding_paths_returns_none_when_missing(
        self,
        service: VoiceBrandingService,
        channel_with_voice: Channel,
        async_session: AsyncSession,
    ):
        """Test get_branding_paths returns None for missing branding config."""
        branding = await service.get_branding_paths("poke1", async_session)

        assert isinstance(branding, BrandingPaths)
        assert branding.intro_path is None
        assert branding.outro_path is None
        assert branding.watermark_path is None
        assert branding.has_any_branding() is False

    @pytest.mark.asyncio
    async def test_get_branding_paths_channel_not_found(
        self,
        service: VoiceBrandingService,
        async_session: AsyncSession,
    ):
        """Test get_branding_paths raises ValueError when channel not found."""
        with pytest.raises(ValueError) as exc_info:
            await service.get_branding_paths("nonexistent", async_session)

        assert "Channel not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_voice_isolation_between_channels(
        self,
        service: VoiceBrandingService,
        async_session: AsyncSession,
    ):
        """Test two channels return different voice IDs (AC #3 isolation)."""
        # Create two channels with different voice IDs
        channel1 = Channel(
            channel_id="channel_a",
            channel_name="Channel A",
            voice_id="voice_for_channel_a",
        )
        channel2 = Channel(
            channel_id="channel_b",
            channel_name="Channel B",
            voice_id="voice_for_channel_b",
        )
        async_session.add(channel1)
        async_session.add(channel2)
        await async_session.commit()

        # Get voice IDs
        voice_a = await service.get_voice_id("channel_a", async_session)
        voice_b = await service.get_voice_id("channel_b", async_session)

        # Verify isolation - each channel gets its own voice
        assert voice_a == "voice_for_channel_a"
        assert voice_b == "voice_for_channel_b"
        assert voice_a != voice_b

    @pytest.mark.asyncio
    async def test_store_voice_id(
        self,
        service: VoiceBrandingService,
        channel_without_voice: Channel,
        async_session: AsyncSession,
    ):
        """Test store_voice_id updates channel voice_id."""
        await service.store_voice_id("poke2", "new_voice_id", async_session)

        # Verify voice_id was stored
        voice_id = await service.get_voice_id("poke2", async_session)
        assert voice_id == "new_voice_id"

    @pytest.mark.asyncio
    async def test_store_voice_id_channel_not_found(
        self,
        service: VoiceBrandingService,
        async_session: AsyncSession,
    ):
        """Test store_voice_id raises ValueError when channel not found."""
        with pytest.raises(ValueError) as exc_info:
            await service.store_voice_id("nonexistent", "voice_123", async_session)

        assert "Channel not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_store_branding_paths(
        self,
        service: VoiceBrandingService,
        channel_with_voice: Channel,
        async_session: AsyncSession,
    ):
        """Test store_branding_paths updates channel branding."""
        await service.store_branding_paths(
            "poke1",
            intro_path="new_intro.mp4",
            outro_path="new_outro.mp4",
            watermark_path="new_watermark.png",
            db=async_session,
        )

        # Verify branding was stored
        branding = await service.get_branding_paths("poke1", async_session)
        assert branding.intro_path == "new_intro.mp4"
        assert branding.outro_path == "new_outro.mp4"
        assert branding.watermark_path == "new_watermark.png"

    @pytest.mark.asyncio
    async def test_store_branding_paths_channel_not_found(
        self,
        service: VoiceBrandingService,
        async_session: AsyncSession,
    ):
        """Test store_branding_paths raises ValueError when channel not found."""
        with pytest.raises(ValueError) as exc_info:
            await service.store_branding_paths(
                "nonexistent",
                intro_path="intro.mp4",
                outro_path="outro.mp4",
                watermark_path=None,
                db=async_session,
            )

        assert "Channel not found" in str(exc_info.value)


class TestBrandingPaths:
    """Tests for BrandingPaths dataclass."""

    def test_branding_paths_creation(self):
        """Test BrandingPaths can be created with all paths."""
        branding = BrandingPaths(
            intro_path="intro.mp4",
            outro_path="outro.mp4",
            watermark_path="watermark.png",
        )

        assert branding.intro_path == "intro.mp4"
        assert branding.outro_path == "outro.mp4"
        assert branding.watermark_path == "watermark.png"

    def test_branding_paths_partial(self):
        """Test BrandingPaths with only some paths set."""
        branding = BrandingPaths(
            intro_path="intro.mp4",
            outro_path=None,
            watermark_path=None,
        )

        assert branding.intro_path == "intro.mp4"
        assert branding.outro_path is None
        assert branding.watermark_path is None

    def test_branding_paths_empty(self):
        """Test BrandingPaths with no paths set."""
        branding = BrandingPaths(
            intro_path=None,
            outro_path=None,
            watermark_path=None,
        )

        assert branding.intro_path is None
        assert branding.outro_path is None
        assert branding.watermark_path is None

    def test_has_any_branding_true(self):
        """Test has_any_branding returns True when any path is set."""
        branding = BrandingPaths(
            intro_path="intro.mp4",
            outro_path=None,
            watermark_path=None,
        )

        assert branding.has_any_branding() is True

    def test_has_any_branding_false(self):
        """Test has_any_branding returns False when no paths are set."""
        branding = BrandingPaths(
            intro_path=None,
            outro_path=None,
            watermark_path=None,
        )

        assert branding.has_any_branding() is False

    def test_branding_paths_immutable(self):
        """Test BrandingPaths is immutable (frozen dataclass)."""
        branding = BrandingPaths(
            intro_path="intro.mp4",
            outro_path="outro.mp4",
            watermark_path="watermark.png",
        )

        # Attempting to modify should raise an error
        with pytest.raises(AttributeError):
            branding.intro_path = "new_intro.mp4"  # type: ignore


class TestVoiceBrandingMigration:
    """Tests for the voice/branding database migration (Task 7.12).

    These tests verify the Alembic migration correctly adds voice and branding
    columns to the channels table.
    """

    def test_migration_file_exists(self) -> None:
        """Test that the migration file exists."""
        from pathlib import Path

        migration_path = Path(
            "alembic/versions/20260110_0003_003_add_voice_branding_columns.py"
        )
        assert migration_path.exists(), f"Migration file not found: {migration_path}"

    def test_migration_file_is_valid(self) -> None:
        """Test that the migration file can be imported and has required functions."""
        import importlib.util
        from pathlib import Path

        migration_path = Path(
            "alembic/versions/20260110_0003_003_add_voice_branding_columns.py"
        )

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
        assert migration.revision == "003_add_voice_branding"
        assert migration.down_revision == "002_add_encrypted_credentials"

    def test_migration_upgrade_adds_voice_columns(self) -> None:
        """Test that migration upgrade function adds voice columns."""
        from pathlib import Path

        migration_path = Path(
            "alembic/versions/20260110_0003_003_add_voice_branding_columns.py"
        )
        content = migration_path.read_text()

        # Verify upgrade adds voice columns
        assert "voice_id" in content
        assert "default_voice_id" in content
        assert "op.add_column" in content

    def test_migration_upgrade_adds_branding_columns(self) -> None:
        """Test that migration upgrade function adds branding columns."""
        from pathlib import Path

        migration_path = Path(
            "alembic/versions/20260110_0003_003_add_voice_branding_columns.py"
        )
        content = migration_path.read_text()

        # Verify upgrade adds branding columns
        assert "branding_intro_path" in content
        assert "branding_outro_path" in content
        assert "branding_watermark_path" in content

    def test_migration_downgrade_removes_columns(self) -> None:
        """Test that migration downgrade function removes all 5 columns."""
        from pathlib import Path

        migration_path = Path(
            "alembic/versions/20260110_0003_003_add_voice_branding_columns.py"
        )
        content = migration_path.read_text()

        # Verify downgrade drops columns
        assert "op.drop_column" in content
        # Count drop_column calls (should be 5: voice_id, default_voice_id, 3 branding paths)
        assert content.count("op.drop_column") == 5
