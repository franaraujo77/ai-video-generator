"""Tests for the encryption utility module.

This module tests the EncryptionService class and related functionality
including encrypt/decrypt operations, error handling, and singleton pattern.
"""

import os

import pytest
from cryptography.fernet import Fernet

from app.utils.encryption import (
    DecryptionError,
    EncryptionKeyMissingError,
    EncryptionService,
    get_encryption_service,
)


@pytest.fixture
def valid_fernet_key() -> str:
    """Generate a valid Fernet key for testing."""
    return Fernet.generate_key().decode()


@pytest.fixture
def different_fernet_key() -> str:
    """Generate a different valid Fernet key for testing wrong key scenarios."""
    return Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def reset_encryption_singleton():
    """Reset the EncryptionService singleton before and after each test.

    This ensures tests don't affect each other due to the singleton pattern.
    """
    EncryptionService.reset_instance()
    yield
    EncryptionService.reset_instance()


class TestEncryptionService:
    """Test suite for EncryptionService class."""

    def test_encrypt_decrypt_roundtrip(
        self, valid_fernet_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that encrypt followed by decrypt returns original plaintext."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        service = get_encryption_service()
        plaintext = "my-secret-oauth-token-ya29.a0..."

        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_produces_bytes(
        self, valid_fernet_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that encrypt returns bytes suitable for database storage."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        service = get_encryption_service()
        encrypted = service.encrypt("test-token")

        assert isinstance(encrypted, bytes)
        assert len(encrypted) > 0

    def test_encrypt_produces_different_ciphertext_each_time(
        self, valid_fernet_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that Fernet produces different ciphertext for same plaintext.

        This is expected behavior due to random IV in Fernet encryption.
        """
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        service = get_encryption_service()
        plaintext = "same-token"

        encrypted1 = service.encrypt(plaintext)
        encrypted2 = service.encrypt(plaintext)

        # Ciphertext should be different due to random IV
        assert encrypted1 != encrypted2

        # But both should decrypt to same plaintext
        assert service.decrypt(encrypted1) == plaintext
        assert service.decrypt(encrypted2) == plaintext

    def test_decrypt_returns_string(
        self, valid_fernet_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that decrypt returns a string (not bytes)."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        service = get_encryption_service()
        encrypted = service.encrypt("test-token")
        decrypted = service.decrypt(encrypted)

        assert isinstance(decrypted, str)

    def test_missing_key_raises_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that EncryptionKeyMissingError is raised when FERNET_KEY not set."""
        monkeypatch.delenv("FERNET_KEY", raising=False)

        with pytest.raises(EncryptionKeyMissingError) as exc_info:
            get_encryption_service()

        assert "FERNET_KEY environment variable is required" in str(exc_info.value)

    def test_empty_key_raises_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that EncryptionKeyMissingError is raised when FERNET_KEY is empty."""
        monkeypatch.setenv("FERNET_KEY", "")

        with pytest.raises(EncryptionKeyMissingError) as exc_info:
            get_encryption_service()

        assert "FERNET_KEY environment variable is required" in str(exc_info.value)

    def test_invalid_key_format_raises_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that EncryptionKeyMissingError is raised when FERNET_KEY has invalid format.

        Fernet keys must be 32 url-safe base64-encoded bytes. Invalid formats
        should raise EncryptionKeyMissingError with a clear error message.
        """
        monkeypatch.setenv("FERNET_KEY", "invalid-not-base64-key")

        with pytest.raises(EncryptionKeyMissingError) as exc_info:
            get_encryption_service()

        assert "Invalid FERNET_KEY format" in str(exc_info.value)

    def test_wrong_key_raises_decryption_error(
        self,
        valid_fernet_key: str,
        different_fernet_key: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that DecryptionError is raised when decrypting with wrong key."""
        # Encrypt with first key
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)
        service1 = get_encryption_service()
        encrypted = service1.encrypt("secret-token")

        # Reset singleton and try to decrypt with different key
        EncryptionService.reset_instance()
        monkeypatch.setenv("FERNET_KEY", different_fernet_key)
        service2 = get_encryption_service()

        with pytest.raises(DecryptionError) as exc_info:
            service2.decrypt(encrypted)

        assert "invalid encryption key or corrupted data" in str(exc_info.value)

    def test_corrupted_ciphertext_raises_decryption_error(
        self, valid_fernet_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that DecryptionError is raised for corrupted ciphertext."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        service = get_encryption_service()

        # Create corrupted ciphertext (valid base64 but invalid Fernet token)
        corrupted = b"gAAAAABhYXXYcorrupted_data_here_definitely_invalid"

        with pytest.raises(DecryptionError) as exc_info:
            service.decrypt(corrupted)

        assert "Decryption failed" in str(exc_info.value)

    def test_invalid_bytes_raises_decryption_error(
        self, valid_fernet_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that DecryptionError is raised for completely invalid bytes."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        service = get_encryption_service()

        # Completely invalid bytes
        invalid_bytes = b"not-valid-fernet-token-at-all"

        with pytest.raises(DecryptionError) as exc_info:
            service.decrypt(invalid_bytes)

        assert "Decryption failed" in str(exc_info.value)

    def test_decryption_error_includes_channel_id(
        self, valid_fernet_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that DecryptionError includes channel_id context when provided."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        service = get_encryption_service()
        corrupted = b"invalid_ciphertext"

        with pytest.raises(DecryptionError) as exc_info:
            service.decrypt(corrupted, channel_id="poke1")

        error = exc_info.value
        assert error.channel_id == "poke1"
        assert "poke1" in str(error)

    def test_singleton_pattern(
        self, valid_fernet_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that EncryptionService follows singleton pattern."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        service1 = get_encryption_service()
        service2 = get_encryption_service()
        service3 = EncryptionService()

        assert service1 is service2
        assert service2 is service3

    def test_reset_instance_allows_reinitialization(
        self, valid_fernet_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that reset_instance allows creating a new singleton."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        service1 = get_encryption_service()
        EncryptionService.reset_instance()
        service2 = get_encryption_service()

        # After reset, should be a different instance
        assert service1 is not service2

    def test_encrypt_empty_string(
        self, valid_fernet_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that empty strings can be encrypted and decrypted."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        service = get_encryption_service()
        encrypted = service.encrypt("")
        decrypted = service.decrypt(encrypted)

        assert decrypted == ""

    def test_encrypt_unicode_content(
        self, valid_fernet_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that unicode content can be encrypted and decrypted."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        service = get_encryption_service()
        plaintext = "token-with-unicode-🔐-characters-日本語"

        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_long_token(
        self, valid_fernet_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that long tokens can be encrypted and decrypted."""
        monkeypatch.setenv("FERNET_KEY", valid_fernet_key)

        service = get_encryption_service()
        # Create a long token (simulating a long OAuth token)
        plaintext = "ya29.a0" + "A" * 1000 + "end"

        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext


class TestDecryptionError:
    """Test suite for DecryptionError exception class."""

    def test_error_message_only(self) -> None:
        """Test DecryptionError with message only."""
        error = DecryptionError("Test error message")

        assert str(error) == "Test error message"
        assert error.channel_id is None

    def test_error_with_channel_id(self) -> None:
        """Test DecryptionError with channel_id context."""
        error = DecryptionError("Test error message", channel_id="nature1")

        assert "Test error message" in str(error)
        assert "nature1" in str(error)
        assert error.channel_id == "nature1"

    def test_error_with_none_channel_id(self) -> None:
        """Test DecryptionError with explicit None channel_id."""
        error = DecryptionError("Test error message", channel_id=None)

        assert str(error) == "Test error message"
        assert error.channel_id is None


class TestEncryptionKeyMissingError:
    """Test suite for EncryptionKeyMissingError exception class."""

    def test_error_message(self) -> None:
        """Test EncryptionKeyMissingError message."""
        error = EncryptionKeyMissingError("Custom error message")

        assert str(error) == "Custom error message"

    def test_error_is_exception(self) -> None:
        """Test that EncryptionKeyMissingError is a proper Exception."""
        error = EncryptionKeyMissingError("Test")

        assert isinstance(error, Exception)

    def test_error_can_be_raised_and_caught(self) -> None:
        """Test that EncryptionKeyMissingError can be raised and caught."""
        with pytest.raises(EncryptionKeyMissingError):
            raise EncryptionKeyMissingError("FERNET_KEY not set")
