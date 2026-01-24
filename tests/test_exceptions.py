"""Tests for custom exception classes.

Tests cover:
- ConfigurationError exception (P2)
- Exception inheritance from base Exception class
- Exception message handling and retrieval
- Raise and catch behavior
- TransientAPIError and PermanentAPIError hierarchy (Story 6.1)
- RateLimitError with retry_after field
- ValidationError for client errors
"""

import pytest

from app.exceptions import (
    ConfigurationError,
    PermanentAPIError,
    RateLimitError,
    TransientAPIError,
    ValidationError,
)


class TestConfigurationError:
    """Tests for ConfigurationError exception (P2 - Medium priority)."""

    def test_configuration_error_can_be_raised(self) -> None:
        """[P2] Test ConfigurationError can be raised.

        GIVEN: ConfigurationError class exists
        WHEN: Raising ConfigurationError with a message
        THEN: Exception is raised successfully
        """
        # WHEN/THEN: Raising ConfigurationError
        with pytest.raises(ConfigurationError):
            raise ConfigurationError("Test configuration error")

    def test_configuration_error_message_is_preserved(self) -> None:
        """[P2] Test ConfigurationError preserves error message.

        GIVEN: ConfigurationError with a specific message
        WHEN: Exception is caught
        THEN: Message can be retrieved from exception instance
        """
        # GIVEN: Error message
        error_message = "Missing voice_id configuration"

        # WHEN: Raising and catching ConfigurationError
        with pytest.raises(ConfigurationError) as exc_info:
            raise ConfigurationError(error_message)

        # THEN: Message is preserved
        assert str(exc_info.value) == error_message

    def test_configuration_error_inherits_from_exception(self) -> None:
        """[P2] Test ConfigurationError inherits from base Exception.

        GIVEN: ConfigurationError class
        WHEN: Checking class hierarchy
        THEN: ConfigurationError is subclass of Exception
        """
        # WHEN/THEN: Checking inheritance
        assert issubclass(ConfigurationError, Exception)

    def test_configuration_error_can_be_caught_as_exception(self) -> None:
        """[P2] Test ConfigurationError can be caught as generic Exception.

        GIVEN: ConfigurationError is raised
        WHEN: Catching as base Exception type
        THEN: Exception is caught successfully
        """
        # GIVEN: ConfigurationError
        error_message = "R2 storage selected without credentials"

        # WHEN: Catching as generic Exception
        with pytest.raises(Exception) as exc_info:
            raise ConfigurationError(error_message)

        # THEN: Exception is caught and message is preserved
        assert isinstance(exc_info.value, ConfigurationError)
        assert str(exc_info.value) == error_message

    def test_configuration_error_with_empty_message(self) -> None:
        """[P2] Test ConfigurationError handles empty message.

        GIVEN: ConfigurationError with empty string message
        WHEN: Exception is raised and caught
        THEN: Exception is raised successfully with empty message
        """
        # WHEN: Raising ConfigurationError with empty message
        with pytest.raises(ConfigurationError) as exc_info:
            raise ConfigurationError("")

        # THEN: Empty message is preserved
        assert str(exc_info.value) == ""

    def test_configuration_error_with_no_message(self) -> None:
        """[P2] Test ConfigurationError can be raised without message.

        GIVEN: ConfigurationError with no arguments
        WHEN: Exception is raised
        THEN: Exception is raised successfully
        """
        # WHEN/THEN: Raising ConfigurationError without message
        with pytest.raises(ConfigurationError):
            raise ConfigurationError()

    def test_configuration_error_with_multiline_message(self) -> None:
        """[P2] Test ConfigurationError handles multiline error messages.

        GIVEN: ConfigurationError with multiline message
        WHEN: Exception is caught
        THEN: Multiline message is preserved correctly
        """
        # GIVEN: Multiline error message
        error_message = """Configuration validation failed:
- Missing voice_id
- R2 credentials not provided
- Invalid channel configuration"""

        # WHEN: Raising and catching ConfigurationError
        with pytest.raises(ConfigurationError) as exc_info:
            raise ConfigurationError(error_message)

        # THEN: Multiline message is preserved
        assert str(exc_info.value) == error_message
        assert "\n" in str(exc_info.value)


class TestTransientAPIError:
    """Test TransientAPIError base class (Story 6.1)."""

    def test_transient_api_error_creation(self) -> None:
        """Verify TransientAPIError can be created and raised."""
        error = TransientAPIError("Service temporarily unavailable")

        assert str(error) == "Service temporarily unavailable"
        assert isinstance(error, Exception)

    def test_transient_api_error_is_exception(self) -> None:
        """Verify TransientAPIError inherits from Exception."""
        error = TransientAPIError("test")

        assert isinstance(error, Exception)


class TestPermanentAPIError:
    """Test PermanentAPIError base class (Story 6.1)."""

    def test_permanent_api_error_creation(self) -> None:
        """Verify PermanentAPIError can be created and raised."""
        error = PermanentAPIError("Invalid API key")

        assert str(error) == "Invalid API key"
        assert isinstance(error, Exception)

    def test_permanent_api_error_is_exception(self) -> None:
        """Verify PermanentAPIError inherits from Exception."""
        error = PermanentAPIError("test")

        assert isinstance(error, Exception)


class TestRateLimitError:
    """Test RateLimitError for 429 responses (Story 6.1)."""

    def test_rate_limit_error_creation_basic(self) -> None:
        """Verify RateLimitError with basic message."""
        error = RateLimitError("Rate limit exceeded")

        assert str(error) == "Rate limit exceeded"
        assert isinstance(error, TransientAPIError)
        assert error.retry_after is None

    def test_rate_limit_error_with_retry_after(self) -> None:
        """Verify RateLimitError stores retry_after field."""
        error = RateLimitError("Rate limit exceeded", retry_after=60)

        assert error.retry_after == 60
        assert isinstance(error, TransientAPIError)

    def test_rate_limit_error_inheritance(self) -> None:
        """Verify RateLimitError inherits from TransientAPIError."""
        error = RateLimitError("test")

        assert isinstance(error, TransientAPIError)
        assert isinstance(error, Exception)

    def test_rate_limit_error_retry_after_none_by_default(self) -> None:
        """Verify retry_after defaults to None when not provided."""
        error = RateLimitError("Rate limit")

        assert error.retry_after is None


class TestValidationError:
    """Test ValidationError for 400/422 responses (Story 6.1)."""

    def test_validation_error_creation(self) -> None:
        """Verify ValidationError can be created and raised."""
        error = ValidationError("Invalid request payload")

        assert str(error) == "Invalid request payload"
        assert isinstance(error, PermanentAPIError)

    def test_validation_error_inheritance(self) -> None:
        """Verify ValidationError inherits from PermanentAPIError."""
        error = ValidationError("test")

        assert isinstance(error, PermanentAPIError)
        assert isinstance(error, Exception)


class TestExceptionHierarchy:
    """Test exception hierarchy relationships (Story 6.1)."""

    def test_hierarchy_transient_vs_permanent(self) -> None:
        """Verify TransientAPIError and PermanentAPIError are separate hierarchies."""
        transient = TransientAPIError("transient")
        permanent = PermanentAPIError("permanent")

        assert not isinstance(transient, PermanentAPIError)
        assert not isinstance(permanent, TransientAPIError)

    def test_rate_limit_error_is_transient(self) -> None:
        """Verify RateLimitError is classified as transient."""
        error = RateLimitError("rate limit")

        assert isinstance(error, TransientAPIError)
        assert not isinstance(error, PermanentAPIError)

    def test_validation_error_is_permanent(self) -> None:
        """Verify ValidationError is classified as permanent."""
        error = ValidationError("validation failed")

        assert isinstance(error, PermanentAPIError)
        assert not isinstance(error, TransientAPIError)

    def test_exception_catching_transient(self) -> None:
        """Verify catching TransientAPIError catches RateLimitError."""
        try:
            raise RateLimitError("rate limit", retry_after=30)
        except TransientAPIError as e:
            assert isinstance(e, RateLimitError)
            assert e.retry_after == 30  # type: ignore

    def test_exception_catching_permanent(self) -> None:
        """Verify catching PermanentAPIError catches ValidationError."""
        try:
            raise ValidationError("bad request")
        except PermanentAPIError as e:
            assert isinstance(e, ValidationError)
