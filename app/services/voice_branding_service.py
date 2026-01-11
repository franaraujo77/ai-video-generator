"""Voice and branding configuration service for per-channel settings.

This service provides resolution of voice IDs and branding paths for channels,
with fallback logic for default values when channel-specific settings are missing.

Voice Resolution (FR10):
    1. Channel-specific voice_id from database
    2. Global DEFAULT_VOICE_ID from environment
    3. Raise ConfigurationError if neither is set

Branding Resolution (FR11):
    1. Channel-specific branding paths from database
    2. Return None for missing paths (no fallback - branding is optional)

Usage:
    from app.services.voice_branding_service import VoiceBrandingService, BrandingPaths

    service = VoiceBrandingService()
    voice_id = await service.get_voice_id("poke1", db)
    branding = await service.get_branding_paths("poke1", db)
"""

from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConfigurationError
from app.models import Channel

log = structlog.get_logger(__name__)

# Re-export for backward compatibility
__all__ = ["BrandingPaths", "ConfigurationError", "VoiceBrandingService"]


@dataclass(frozen=True)
class BrandingPaths:
    """Branding asset paths for video assembly (FR11).

    Immutable dataclass containing resolved branding paths for a channel.
    All paths are relative to the channel workspace.

    Attributes:
        intro_path: Path to intro video, or None if not configured.
        outro_path: Path to outro video, or None if not configured.
        watermark_path: Path to watermark image, or None if not configured.

    Example:
        >>> branding = BrandingPaths(
        ...     intro_path="channel_assets/intro.mp4",
        ...     outro_path="channel_assets/outro.mp4",
        ...     watermark_path=None
        ... )
        >>> if branding.intro_path:
        ...     # Apply intro video during assembly
    """

    intro_path: str | None
    outro_path: str | None
    watermark_path: str | None

    def has_any_branding(self) -> bool:
        """Check if any branding is configured.

        Returns:
            True if at least one branding path is set.
        """
        return any([self.intro_path, self.outro_path, self.watermark_path])


def get_default_voice_id() -> str | None:
    """Get default voice ID from configuration.

    Returns:
        DEFAULT_VOICE_ID from environment, or None if not set.
    """
    from app.config import get_default_voice_id as _get_default_voice_id

    return _get_default_voice_id()


class VoiceBrandingService:
    """Service for resolving voice and branding configuration per channel.

    This service handles voice ID and branding path resolution for channels,
    implementing the fallback logic specified in FR10 (voice selection) and
    FR11 (branding assets).

    Voice Resolution Order (FR10):
        1. Channel-specific voice_id from database
        2. Global DEFAULT_VOICE_ID from environment
        3. Raise ConfigurationError if neither available

    Branding Resolution (FR11):
        - Returns BrandingPaths dataclass with channel-specific paths
        - All paths are relative to channel workspace
        - Missing branding is valid (returns None for each path)

    Example:
        >>> service = VoiceBrandingService()
        >>> voice_id = await service.get_voice_id("poke1", db)
        >>> branding = await service.get_branding_paths("poke1", db)
    """

    async def _get_channel(
        self, channel_id: str, db: AsyncSession
    ) -> Channel | None:
        """Get channel by business identifier.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            db: Async database session.

        Returns:
            Channel model or None if not found.
        """
        result = await db.execute(
            select(Channel).where(Channel.channel_id == channel_id)
        )
        return result.scalar_one_or_none()

    async def get_voice_id(self, channel_id: str, db: AsyncSession) -> str:
        """Get voice ID for channel with fallback to default.

        Resolution order (FR10):
            1. Channel-specific voice_id from database
            2. Global DEFAULT_VOICE_ID from environment
            3. Raise ConfigurationError if no default set

        Logs warning when falling back to default (AC #2).

        Args:
            channel_id: Business identifier (e.g., "poke1").
            db: Async database session.

        Returns:
            Voice ID string to use for narration.

        Raises:
            ConfigurationError: If no voice_id configured and no DEFAULT_VOICE_ID set.
            ValueError: If channel not found.

        Example:
            >>> voice_id = await service.get_voice_id("poke1", db)
            >>> # Use voice_id for ElevenLabs narration generation
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "voice_id_get_failed",
                channel_id=channel_id,
                reason="channel_not_found",
            )
            raise ValueError(f"Channel not found: {channel_id}")

        # First check channel-specific voice_id
        if channel.voice_id:
            log.info(
                "voice_id_resolved",
                channel_id=channel_id,
                source="channel_specific",
            )
            return channel.voice_id

        # Fallback to global default
        default = get_default_voice_id()
        if default:
            # Log warning when using default (AC #2)
            truncated_id = default[:8] + "..." if len(default) > 8 else default
            log.warning(
                "using_default_voice_id",
                channel_id=channel_id,
                default_voice_id=truncated_id,
                reason="channel_voice_id_not_set",
            )
            return default

        # No voice ID available
        log.error(
            "voice_id_resolution_failed",
            channel_id=channel_id,
            reason="no_voice_id_configured_and_no_default",
        )
        raise ConfigurationError(
            f"No voice_id configured for channel {channel_id} and no DEFAULT_VOICE_ID set"
        )

    async def get_branding_paths(
        self, channel_id: str, db: AsyncSession
    ) -> BrandingPaths:
        """Get branding asset paths for channel (FR11).

        Returns branding paths from the channel's database record.
        Missing branding is valid - returns None for unconfigured paths.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            db: Async database session.

        Returns:
            BrandingPaths with intro_path, outro_path, and watermark_path.
            Each path may be None if not configured.

        Raises:
            ValueError: If channel not found.

        Example:
            >>> branding = await service.get_branding_paths("poke1", db)
            >>> if branding.intro_path:
            ...     # Apply intro video during assembly
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "branding_get_failed",
                channel_id=channel_id,
                reason="channel_not_found",
            )
            raise ValueError(f"Channel not found: {channel_id}")

        branding = BrandingPaths(
            intro_path=channel.branding_intro_path,
            outro_path=channel.branding_outro_path,
            watermark_path=channel.branding_watermark_path,
        )

        log.info(
            "branding_resolved",
            channel_id=channel_id,
            has_intro=branding.intro_path is not None,
            has_outro=branding.outro_path is not None,
            has_watermark=branding.watermark_path is not None,
        )

        return branding

    async def store_voice_id(
        self, channel_id: str, voice_id: str | None, db: AsyncSession
    ) -> None:
        """Store voice ID for channel.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            voice_id: ElevenLabs voice ID, or None to clear.
            db: Async database session.

        Raises:
            ValueError: If channel not found.
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "voice_id_store_failed",
                channel_id=channel_id,
                reason="channel_not_found",
            )
            raise ValueError(f"Channel not found: {channel_id}")

        channel.voice_id = voice_id
        await db.commit()

        log.info(
            "voice_id_stored",
            channel_id=channel_id,
            has_voice_id=voice_id is not None,
        )

    async def store_branding_paths(
        self,
        channel_id: str,
        intro_path: str | None,
        outro_path: str | None,
        watermark_path: str | None,
        db: AsyncSession,
    ) -> None:
        """Store branding paths for channel.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            intro_path: Relative path to intro video, or None.
            outro_path: Relative path to outro video, or None.
            watermark_path: Relative path to watermark image, or None.
            db: Async database session.

        Raises:
            ValueError: If channel not found.
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "branding_store_failed",
                channel_id=channel_id,
                reason="channel_not_found",
            )
            raise ValueError(f"Channel not found: {channel_id}")

        channel.branding_intro_path = intro_path
        channel.branding_outro_path = outro_path
        channel.branding_watermark_path = watermark_path
        await db.commit()

        log.info(
            "branding_stored",
            channel_id=channel_id,
            has_intro=intro_path is not None,
            has_outro=outro_path is not None,
            has_watermark=watermark_path is not None,
        )
