"""Credential management service for encrypted OAuth tokens and API keys.

This service provides secure storage and retrieval of per-channel credentials
using Fernet symmetric encryption. All credential access is logged for audit
purposes.

Usage:
    from app.services.credential_service import CredentialService

    service = CredentialService()
    await service.store_youtube_token(channel_id, token, db)
    token = await service.get_youtube_token(channel_id, db)

Security Notes:
    - Credentials are encrypted before database storage
    - Access events are logged with structlog (channel_id, operation, success)
    - NEVER log or expose plaintext credentials
    - Use short database transactions (get → close → encrypt → save)
"""

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel
from app.utils.encryption import DecryptionError, get_encryption_service

log = structlog.get_logger(__name__)


class CredentialService:
    """Service for managing encrypted channel credentials.

    This service handles encryption, storage, and retrieval of sensitive
    credentials (OAuth tokens, API keys) for each channel. All operations
    are logged for audit purposes.

    Example:
        >>> service = CredentialService()
        >>> await service.store_youtube_token("poke1", "ya29.a0...", db)
        >>> token = await service.get_youtube_token("poke1", db)
    """

    async def _get_channel(self, channel_id: str, db: AsyncSession) -> Channel | None:
        """Get channel by business identifier.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            db: Async database session.

        Returns:
            Channel model or None if not found.
        """
        result = await db.execute(select(Channel).where(Channel.channel_id == channel_id))
        return result.scalar_one_or_none()

    async def store_youtube_token(self, channel_id: str, token: str, db: AsyncSession) -> None:
        """Store encrypted YouTube OAuth refresh token for channel.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            token: Plaintext YouTube OAuth refresh token.
            db: Async database session.

        Raises:
            ValueError: If channel not found.

        Example:
            >>> await service.store_youtube_token("poke1", "ya29.a0...", db)
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "credential_store_failed",
                channel_id=channel_id,
                credential_type="youtube_token",
                reason="channel_not_found",
            )
            raise ValueError(f"Channel not found: {channel_id}")

        encryption_service = get_encryption_service()
        encrypted_token = encryption_service.encrypt(token)

        channel.youtube_token_encrypted = encrypted_token
        await db.commit()

        log.info(
            "credential_stored",
            channel_id=channel_id,
            credential_type="youtube_token",
            success=True,
        )

    async def get_youtube_token(self, channel_id: str, db: AsyncSession) -> str | None:
        """Retrieve and decrypt YouTube OAuth refresh token for channel.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            db: Async database session.

        Returns:
            Decrypted token string, or None if channel has no token.

        Raises:
            DecryptionError: If decryption fails (invalid key or corrupted data).

        Example:
            >>> token = await service.get_youtube_token("poke1", db)
            >>> if token:
            ...     # Use token for YouTube API
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "credential_get_failed",
                channel_id=channel_id,
                credential_type="youtube_token",
                reason="channel_not_found",
            )
            return None

        if channel.youtube_token_encrypted is None:
            log.info(
                "credential_get",
                channel_id=channel_id,
                credential_type="youtube_token",
                success=True,
                has_credential=False,
            )
            return None

        encryption_service = get_encryption_service()
        try:
            decrypted = encryption_service.decrypt(
                channel.youtube_token_encrypted, channel_id=channel_id
            )
            log.info(
                "credential_get",
                channel_id=channel_id,
                credential_type="youtube_token",
                success=True,
                has_credential=True,
            )
            return decrypted
        except DecryptionError:
            log.error(
                "credential_decrypt_failed",
                channel_id=channel_id,
                credential_type="youtube_token",
            )
            raise

    async def store_notion_token(self, channel_id: str, token: str, db: AsyncSession) -> None:
        """Store encrypted Notion integration token for channel.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            token: Plaintext Notion integration token.
            db: Async database session.

        Raises:
            ValueError: If channel not found.

        Example:
            >>> await service.store_notion_token("poke1", "secret_...", db)
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "credential_store_failed",
                channel_id=channel_id,
                credential_type="notion_token",
                reason="channel_not_found",
            )
            raise ValueError(f"Channel not found: {channel_id}")

        encryption_service = get_encryption_service()
        encrypted_token = encryption_service.encrypt(token)

        channel.notion_token_encrypted = encrypted_token
        await db.commit()

        log.info(
            "credential_stored",
            channel_id=channel_id,
            credential_type="notion_token",
            success=True,
        )

    async def get_notion_token(self, channel_id: str, db: AsyncSession) -> str | None:
        """Retrieve and decrypt Notion integration token for channel.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            db: Async database session.

        Returns:
            Decrypted token string, or None if channel has no token.

        Raises:
            DecryptionError: If decryption fails (invalid key or corrupted data).

        Example:
            >>> token = await service.get_notion_token("poke1", db)
            >>> if token:
            ...     # Use token for Notion API
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "credential_get_failed",
                channel_id=channel_id,
                credential_type="notion_token",
                reason="channel_not_found",
            )
            return None

        if channel.notion_token_encrypted is None:
            log.info(
                "credential_get",
                channel_id=channel_id,
                credential_type="notion_token",
                success=True,
                has_credential=False,
            )
            return None

        encryption_service = get_encryption_service()
        try:
            decrypted = encryption_service.decrypt(
                channel.notion_token_encrypted, channel_id=channel_id
            )
            log.info(
                "credential_get",
                channel_id=channel_id,
                credential_type="notion_token",
                success=True,
                has_credential=True,
            )
            return decrypted
        except DecryptionError:
            log.error(
                "credential_decrypt_failed",
                channel_id=channel_id,
                credential_type="notion_token",
            )
            raise

    async def store_gemini_key(self, channel_id: str, api_key: str, db: AsyncSession) -> None:
        """Store encrypted Gemini API key for channel.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            api_key: Plaintext Gemini API key.
            db: Async database session.

        Raises:
            ValueError: If channel not found.
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "credential_store_failed",
                channel_id=channel_id,
                credential_type="gemini_key",
                reason="channel_not_found",
            )
            raise ValueError(f"Channel not found: {channel_id}")

        encryption_service = get_encryption_service()
        encrypted_key = encryption_service.encrypt(api_key)

        channel.gemini_key_encrypted = encrypted_key
        await db.commit()

        log.info(
            "credential_stored",
            channel_id=channel_id,
            credential_type="gemini_key",
            success=True,
        )

    async def get_gemini_key(self, channel_id: str, db: AsyncSession) -> str | None:
        """Retrieve and decrypt Gemini API key for channel.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            db: Async database session.

        Returns:
            Decrypted API key string, or None if channel has no key.

        Raises:
            DecryptionError: If decryption fails (invalid key or corrupted data).
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "credential_get_failed",
                channel_id=channel_id,
                credential_type="gemini_key",
                reason="channel_not_found",
            )
            return None

        if channel.gemini_key_encrypted is None:
            log.info(
                "credential_get",
                channel_id=channel_id,
                credential_type="gemini_key",
                success=True,
                has_credential=False,
            )
            return None

        encryption_service = get_encryption_service()
        try:
            decrypted = encryption_service.decrypt(
                channel.gemini_key_encrypted, channel_id=channel_id
            )
            log.info(
                "credential_get",
                channel_id=channel_id,
                credential_type="gemini_key",
                success=True,
                has_credential=True,
            )
            return decrypted
        except DecryptionError:
            log.error(
                "credential_decrypt_failed",
                channel_id=channel_id,
                credential_type="gemini_key",
            )
            raise

    async def store_elevenlabs_key(self, channel_id: str, api_key: str, db: AsyncSession) -> None:
        """Store encrypted ElevenLabs API key for channel.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            api_key: Plaintext ElevenLabs API key.
            db: Async database session.

        Raises:
            ValueError: If channel not found.
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "credential_store_failed",
                channel_id=channel_id,
                credential_type="elevenlabs_key",
                reason="channel_not_found",
            )
            raise ValueError(f"Channel not found: {channel_id}")

        encryption_service = get_encryption_service()
        encrypted_key = encryption_service.encrypt(api_key)

        channel.elevenlabs_key_encrypted = encrypted_key
        await db.commit()

        log.info(
            "credential_stored",
            channel_id=channel_id,
            credential_type="elevenlabs_key",
            success=True,
        )

    async def get_elevenlabs_key(self, channel_id: str, db: AsyncSession) -> str | None:
        """Retrieve and decrypt ElevenLabs API key for channel.

        Args:
            channel_id: Business identifier (e.g., "poke1").
            db: Async database session.

        Returns:
            Decrypted API key string, or None if channel has no key.

        Raises:
            DecryptionError: If decryption fails (invalid key or corrupted data).
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "credential_get_failed",
                channel_id=channel_id,
                credential_type="elevenlabs_key",
                reason="channel_not_found",
            )
            return None

        if channel.elevenlabs_key_encrypted is None:
            log.info(
                "credential_get",
                channel_id=channel_id,
                credential_type="elevenlabs_key",
                success=True,
                has_credential=False,
            )
            return None

        encryption_service = get_encryption_service()
        try:
            decrypted = encryption_service.decrypt(
                channel.elevenlabs_key_encrypted, channel_id=channel_id
            )
            log.info(
                "credential_get",
                channel_id=channel_id,
                credential_type="elevenlabs_key",
                success=True,
                has_credential=True,
            )
            return decrypted
        except DecryptionError:
            log.error(
                "credential_decrypt_failed",
                channel_id=channel_id,
                credential_type="elevenlabs_key",
            )
            raise

    async def store_r2_credentials(
        self,
        channel_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        db: AsyncSession,
    ) -> None:
        """Store encrypted R2 credentials for channel (Story 8.4).

        Args:
            channel_id: Business identifier (e.g., "poke1").
            access_key_id: Plaintext R2 access key ID.
            secret_access_key: Plaintext R2 secret access key.
            bucket_name: R2 bucket name (not sensitive, stored plaintext).
            db: Async database session.

        Raises:
            ValueError: If channel not found.

        Example:
            >>> await service.store_r2_credentials(
            ...     "poke1", "access_key_id", "secret_access_key", "ai-video-assets", db
            ... )
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "credential_store_failed",
                channel_id=channel_id,
                credential_type="r2_credentials",
                reason="channel_not_found",
            )
            raise ValueError(f"Channel not found: {channel_id}")

        encryption_service = get_encryption_service()

        # Encrypt credentials
        channel.r2_access_key_id_encrypted = encryption_service.encrypt(access_key_id)
        channel.r2_secret_access_key_encrypted = encryption_service.encrypt(secret_access_key)
        channel.r2_bucket_name = bucket_name

        await db.commit()

        log.info(
            "credential_stored",
            channel_id=channel_id,
            credential_type="r2_credentials",
            bucket_name=bucket_name,
            success=True,
        )

    async def get_r2_credentials(
        self, channel_id: str, db: AsyncSession
    ) -> tuple[str | None, str | None, str | None]:
        """Retrieve and decrypt R2 credentials for channel (Story 8.4).

        Args:
            channel_id: Business identifier (e.g., "poke1").
            db: Async database session.

        Returns:
            Tuple of (access_key_id, secret_access_key, bucket_name).
            Returns (None, None, None) if channel not found or no R2 credentials.

        Raises:
            DecryptionError: If decryption fails (invalid key or corrupted data).

        Example:
            >>> access_key, secret_key, bucket = await service.get_r2_credentials("poke1", db)
            >>> if access_key:
            ...     # Use credentials for R2 client
        """
        channel = await self._get_channel(channel_id, db)
        if channel is None:
            log.warning(
                "credential_get_failed",
                channel_id=channel_id,
                credential_type="r2_credentials",
                reason="channel_not_found",
            )
            return (None, None, None)

        if (
            channel.r2_access_key_id_encrypted is None
            or channel.r2_secret_access_key_encrypted is None
        ):
            log.info(
                "credential_get",
                channel_id=channel_id,
                credential_type="r2_credentials",
                success=True,
                has_credential=False,
            )
            return (None, None, None)

        encryption_service = get_encryption_service()
        try:
            access_key_id = encryption_service.decrypt(
                channel.r2_access_key_id_encrypted, channel_id=channel_id
            )
            secret_access_key = encryption_service.decrypt(
                channel.r2_secret_access_key_encrypted, channel_id=channel_id
            )

            log.info(
                "credential_get",
                channel_id=channel_id,
                credential_type="r2_credentials",
                success=True,
                has_credential=True,
            )
            return (access_key_id, secret_access_key, channel.r2_bucket_name)

        except DecryptionError:
            log.error(
                "credential_decrypt_failed",
                channel_id=channel_id,
                credential_type="r2_credentials",
            )
            raise

    async def get_r2_client(self, channel_id: str, db: AsyncSession) -> "R2StorageClient":
        """Get R2 storage client with decrypted credentials (Story 8.4).

        Args:
            channel_id: Business identifier (e.g., "poke1").
            db: Async database session.

        Returns:
            R2StorageClient instance with decrypted credentials.

        Raises:
            ValueError: If channel not found or R2 not configured.

        Example:
            >>> client = await service.get_r2_client("poke1", db)
            >>> url = await client.upload_asset(...)
        """
        from app.services.r2_storage import R2StorageClient

        channel = await self._get_channel(channel_id, db)
        if channel is None:
            raise ValueError(f"Channel not found: {channel_id}")

        if (
            channel.r2_bucket_name is None
            or channel.r2_access_key_id_encrypted is None
            or channel.r2_secret_access_key_encrypted is None
        ):
            raise ValueError(f"Channel {channel_id} does not have R2 storage configured")

        # Decrypt credentials
        encryption_service = get_encryption_service()
        access_key_id = encryption_service.decrypt(
            channel.r2_access_key_id_encrypted, channel_id=channel_id
        )
        secret_access_key = encryption_service.decrypt(
            channel.r2_secret_access_key_encrypted, channel_id=channel_id
        )

        # Create R2 client
        return R2StorageClient(
            bucket_name=channel.r2_bucket_name,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region="auto",
        )
