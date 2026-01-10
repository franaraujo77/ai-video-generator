"""Fernet symmetric encryption for OAuth tokens and API keys.

This module provides secure encryption and decryption of sensitive credentials
using Fernet symmetric encryption from the cryptography library.

The FERNET_KEY environment variable must be set with a valid Fernet key
generated via `Fernet.generate_key()` or the `scripts/generate_fernet_key.py`
CLI tool.

Usage:
    from app.utils.encryption import get_encryption_service

    service = get_encryption_service()
    encrypted = service.encrypt("my-secret-token")
    decrypted = service.decrypt(encrypted)

Security Notes:
    - NEVER log or expose encrypted values or plaintext tokens
    - Use Railway environment variables for FERNET_KEY storage
    - Key rotation requires re-encrypting all stored credentials
"""

import os
from typing import ClassVar

from cryptography.fernet import Fernet, InvalidToken


class EncryptionKeyMissing(Exception):
    """Raised when FERNET_KEY environment variable is not set.

    This exception indicates that the application cannot perform encryption
    or decryption operations because the required encryption key is missing.

    Example:
        >>> from app.utils.encryption import EncryptionService, EncryptionKeyMissing
        >>> try:
        ...     service = EncryptionService()  # FERNET_KEY not set
        ... except EncryptionKeyMissing as e:
        ...     print(f"Setup required: {e}")
    """

    pass


class DecryptionError(Exception):
    """Raised when decryption fails due to invalid key or corrupted data.

    This exception provides context about the failure without exposing
    sensitive ciphertext data.

    Attributes:
        channel_id: The channel ID associated with the failed decryption
            (if available). Useful for debugging without exposing secrets.

    Example:
        >>> from app.utils.encryption import DecryptionError
        >>> raise DecryptionError("Invalid encryption key or corrupted data", channel_id="poke1")
    """

    def __init__(self, message: str, channel_id: str | None = None) -> None:
        """Initialize DecryptionError with message and optional context.

        Args:
            message: Human-readable error description.
            channel_id: Optional channel ID for debugging context.
        """
        self.channel_id = channel_id
        super().__init__(message)

    def __str__(self) -> str:
        """Return string representation with channel context if available."""
        if self.channel_id:
            return f"{super().__str__()} (channel_id={self.channel_id})"
        return super().__str__()


class EncryptionService:
    """Fernet symmetric encryption service for credential storage.

    This service provides encrypt/decrypt operations using Fernet symmetric
    encryption. It implements the singleton pattern with lazy initialization
    to ensure the encryption key is loaded only once.

    The FERNET_KEY environment variable must contain a valid Fernet key
    (44 URL-safe base64-encoded bytes).

    Attributes:
        _instance: Class-level singleton instance.
        _cipher: Fernet cipher initialized with FERNET_KEY.

    Example:
        >>> service = get_encryption_service()
        >>> encrypted = service.encrypt("my-oauth-token")
        >>> decrypted = service.decrypt(encrypted)
        >>> assert decrypted == "my-oauth-token"

    Raises:
        EncryptionKeyMissing: If FERNET_KEY environment variable is not set.
    """

    _instance: ClassVar["EncryptionService | None"] = None
    _cipher: Fernet

    def __new__(cls) -> "EncryptionService":
        """Create or return singleton instance.

        Returns:
            The singleton EncryptionService instance.

        Raises:
            EncryptionKeyMissing: If FERNET_KEY environment variable is not set.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize Fernet cipher with key from environment.

        Raises:
            EncryptionKeyMissing: If FERNET_KEY environment variable is not set
                or has an invalid format.
        """
        key = os.environ.get("FERNET_KEY")
        if not key:
            raise EncryptionKeyMissing(
                "FERNET_KEY environment variable is required. "
                "Generate a key using: python scripts/generate_fernet_key.py"
            )
        try:
            self._cipher = Fernet(key.encode())
        except ValueError as e:
            raise EncryptionKeyMissing(
                "Invalid FERNET_KEY format: Fernet key must be 32 url-safe "
                "base64-encoded bytes. Generate a valid key using: "
                "python scripts/generate_fernet_key.py"
            ) from e

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt plaintext string to bytes using Fernet.

        Args:
            plaintext: The sensitive string to encrypt (e.g., OAuth token).

        Returns:
            Encrypted bytes suitable for database storage.

        Example:
            >>> service = get_encryption_service()
            >>> encrypted = service.encrypt("ya29.a0...")
            >>> isinstance(encrypted, bytes)
            True
        """
        return self._cipher.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes, channel_id: str | None = None) -> str:
        """Decrypt ciphertext bytes to plaintext string.

        Args:
            ciphertext: The encrypted bytes from database storage.
            channel_id: Optional channel ID for error context.

        Returns:
            Decrypted plaintext string.

        Raises:
            DecryptionError: If decryption fails (invalid key or corrupted data).

        Example:
            >>> service = get_encryption_service()
            >>> encrypted = service.encrypt("my-token")
            >>> decrypted = service.decrypt(encrypted)
            >>> assert decrypted == "my-token"
        """
        try:
            return self._cipher.decrypt(ciphertext).decode()
        except InvalidToken as e:
            raise DecryptionError(
                "Decryption failed: invalid encryption key or corrupted data",
                channel_id=channel_id,
            ) from e
        except Exception as e:
            # Catch other potential errors (malformed data, encoding issues)
            raise DecryptionError(
                f"Decryption failed: {type(e).__name__}",
                channel_id=channel_id,
            ) from e

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing only).

        This method allows tests to reinitialize the service with different
        environment variables. Should NOT be used in production code.
        """
        cls._instance = None


def get_encryption_service() -> EncryptionService:
    """Get the singleton EncryptionService instance.

    This is the recommended way to access the encryption service. It ensures
    lazy initialization and singleton pattern enforcement.

    Returns:
        The singleton EncryptionService instance.

    Raises:
        EncryptionKeyMissing: If FERNET_KEY environment variable is not set.

    Example:
        >>> service = get_encryption_service()
        >>> encrypted = service.encrypt("secret")
    """
    return EncryptionService()
