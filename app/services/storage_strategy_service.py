"""Storage strategy service for resolving per-channel asset storage configuration.

This service provides storage strategy resolution for channels, allowing each
channel to configure where generated assets are stored (Notion or Cloudflare R2).

Storage Strategies (FR12):
    - "notion" (default): Assets stored as Notion file attachments
    - "r2": Assets uploaded to Cloudflare R2 object storage

R2 Credentials:
    When storage_strategy is "r2", the service retrieves and decrypts the
    R2 credentials (account_id, access_key_id, secret_access_key, bucket_name)
    from the database.

Usage:
    from app.services.storage_strategy_service import StorageStrategyService

    service = StorageStrategyService()
    strategy = await service.get_storage_strategy(channel_id, db)
    if strategy == "r2":
        r2_config = await service.get_r2_config(channel_id, db)
        # Use r2_config.bucket_name, r2_config.access_key_id, etc.
"""

from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConfigurationError
from app.models import Channel
from app.utils.encryption import DecryptionError, get_encryption_service

log = structlog.get_logger(__name__)


@dataclass
class R2Credentials:
    """Decrypted Cloudflare R2 credentials for asset storage.

    This dataclass holds the decrypted R2 credentials retrieved from the
    database. All credential fields are required when using R2 storage.

    Attributes:
        account_id: Cloudflare account ID.
        access_key_id: R2 access key ID.
        secret_access_key: R2 secret access key.
        bucket_name: R2 bucket name.

    Note:
        NEVER log or expose these credentials in plain text.
        Use the __repr__ method which masks sensitive fields.
    """

    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket_name: str

    def __repr__(self) -> str:
        """Return string representation for debugging.

        Masks sensitive credential fields for security.
        """
        return (
            f"R2Credentials(bucket_name={self.bucket_name!r}, "
            f"account_id=*****, access_key_id=*****, secret_access_key=*****)"
        )


class StorageStrategyService:
    """Service for resolving channel storage strategy and R2 credentials.

    This service handles storage strategy resolution for channels, including
    retrieval and decryption of R2 credentials when needed.

    Example:
        >>> service = StorageStrategyService()
        >>> strategy = await service.get_storage_strategy("poke1", db)
        >>> if strategy == "r2":
        ...     r2_config = await service.get_r2_config("poke1", db)
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

    async def get_storage_strategy(
        self, channel_id: str, db: AsyncSession
    ) -> str:
        """Get storage strategy for channel with fallback to default.

        Resolution:
        1. Channel-specific storage_strategy from database
        2. Default to "notion" if not set or channel not found

        Args:
            channel_id: Business identifier (e.g., "poke1").
            db: Async database session.

        Returns:
            Storage strategy: "notion" or "r2".
        """
        channel = await self._get_channel(channel_id, db)

        if channel is None:
            log.warning(
                "storage_strategy_channel_not_found",
                channel_id=channel_id,
                fallback="notion",
            )
            return "notion"

        strategy = channel.storage_strategy or "notion"

        log.info(
            "storage_strategy_resolved",
            channel_id=channel_id,
            storage_strategy=strategy,
        )

        return strategy

    async def get_r2_config(
        self, channel_id: str, db: AsyncSession
    ) -> R2Credentials:
        """Retrieve and decrypt R2 credentials for channel.

        This method retrieves and decrypts the R2 credentials stored in the
        database for the specified channel. All four credential fields must
        be present for R2 storage to work.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            db: Async database session.

        Returns:
            R2Credentials dataclass with decrypted credentials.

        Raises:
            ConfigurationError: If channel not found, storage_strategy is not "r2",
                or R2 credentials are missing or incomplete.
            DecryptionError: If credential decryption fails.

        Example:
            >>> r2_config = await service.get_r2_config("poke1", db)
            >>> print(r2_config.bucket_name)
        """
        channel = await self._get_channel(channel_id, db)

        if channel is None:
            log.error(
                "r2_config_channel_not_found",
                channel_id=channel_id,
            )
            raise ConfigurationError(
                f"Channel not found: {channel_id}"
            )

        # Validate storage strategy
        if channel.storage_strategy != "r2":
            log.warning(
                "r2_config_not_r2_strategy",
                channel_id=channel_id,
                storage_strategy=channel.storage_strategy,
            )
            raise ConfigurationError(
                f"Cannot get R2 config for channel with "
                f"storage_strategy='{channel.storage_strategy}'. "
                f"Expected storage_strategy='r2'."
            )

        # Check if all R2 credentials are present
        missing_fields = []
        if channel.r2_account_id_encrypted is None:
            missing_fields.append("r2_account_id")
        if channel.r2_access_key_id_encrypted is None:
            missing_fields.append("r2_access_key_id")
        if channel.r2_secret_access_key_encrypted is None:
            missing_fields.append("r2_secret_access_key")
        if channel.r2_bucket_name is None:
            missing_fields.append("r2_bucket_name")

        if missing_fields:
            log.error(
                "r2_config_missing_credentials",
                channel_id=channel_id,
                missing_fields=missing_fields,
            )
            raise ConfigurationError(
                f"Channel {channel_id} has storage_strategy='r2' but missing R2 credentials: "
                f"{', '.join(missing_fields)}"
            )

        # Decrypt credentials
        encryption_service = get_encryption_service()

        try:
            account_id = encryption_service.decrypt(
                channel.r2_account_id_encrypted, channel_id=channel_id
            )
            access_key_id = encryption_service.decrypt(
                channel.r2_access_key_id_encrypted, channel_id=channel_id
            )
            secret_access_key = encryption_service.decrypt(
                channel.r2_secret_access_key_encrypted, channel_id=channel_id
            )
        except DecryptionError as e:
            log.error(
                "r2_config_decryption_failed",
                channel_id=channel_id,
                error=str(e),
            )
            raise

        log.info(
            "r2_config_retrieved",
            channel_id=channel_id,
            bucket_name=channel.r2_bucket_name,
            has_credentials=True,
        )

        return R2Credentials(
            account_id=account_id,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            bucket_name=channel.r2_bucket_name,
        )
