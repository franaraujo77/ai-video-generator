"""Tests for custom exception classes.

Tests cover:
- ConfigurationError exception (P2)
- Exception inheritance from base Exception class
- Exception message handling and retrieval
- Raise and catch behavior
"""

import pytest

from app.exceptions import ConfigurationError


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
