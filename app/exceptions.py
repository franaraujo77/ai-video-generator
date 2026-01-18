"""Shared exceptions for the application.

This module contains exception classes used across multiple services
to avoid cross-domain dependencies between services.

Exception Hierarchy (Story 6.1):
- TransientAPIError: Retriable errors (429, 5xx, timeouts, network issues)
- PermanentAPIError: Fail-fast errors (400, 401, 403, 404, 422)
- RateLimitError(TransientAPIError): HTTP 429 with retry_after field
- ValidationError(PermanentAPIError): HTTP 400/422 validation errors
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import TaskStatus



class TransientAPIError(Exception):
    """Base class for transient API errors that should be retried.

    Transient errors are temporary failures that are likely to succeed
    if retried after a brief delay. Examples:
    - HTTP 429 (rate limit)
    - HTTP 500-504 (server errors)
    - Network timeouts
    - Connection errors

    Story Reference: 6.1 - Transient Failure Detection
    """

    pass


class PermanentAPIError(Exception):
    """Base class for permanent API errors that should NOT be retried.

    Permanent errors are client-side failures that won't succeed on retry
    without changing the request. Examples:
    - HTTP 400 (bad request)
    - HTTP 401 (unauthorized)
    - HTTP 403 (forbidden)
    - HTTP 404 (not found)
    - HTTP 422 (unprocessable entity)

    Story Reference: 6.1 - Transient Failure Detection
    """

    pass


class RateLimitError(TransientAPIError):
    """Raised when API rate limit is exceeded (HTTP 429).

    Attributes:
        retry_after: Optional seconds to wait before retrying (from Retry-After header).
                    If None, use exponential backoff strategy.

    Example:
        >>> raise RateLimitError("ElevenLabs rate limit exceeded", retry_after=60)

    Story Reference: 6.1 - Transient Failure Detection (Task 2.3)
    """

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        """Initialize RateLimitError with optional retry_after.

        Args:
            message: Error message describing the rate limit
            retry_after: Optional seconds to wait before retry (from Retry-After header)
        """
        self.retry_after = retry_after
        super().__init__(message)


class ValidationError(PermanentAPIError):
    """Raised when API request validation fails (HTTP 400, 422).

    Validation errors indicate the request payload is malformed or doesn't
    meet API requirements. These errors won't succeed on retry without
    fixing the request data.

    Example:
        >>> raise ValidationError("Missing required field: voice_id")

    Story Reference: 6.1 - Transient Failure Detection (Task 2.4)
    """

    pass



class ConfigurationError(Exception):
    """Raised when required configuration is missing.

    This error indicates a configuration problem that prevents
    video generation from proceeding (e.g., no voice_id configured
    and no global default set, or R2 storage selected without credentials).
    """

    pass


class InvalidStateTransitionError(Exception):
    """Raised when attempting an invalid state transition in TaskStatus workflow.

    This exception enforces the 26-status workflow state machine (Story 5.1).
    Only valid transitions defined in Task.VALID_TRANSITIONS are allowed.

    Attributes:
        message: Human-readable error message describing the invalid transition.
        from_status: The current TaskStatus before the attempted transition.
        to_status: The TaskStatus that was attempted but is not valid.

    Example:
        >>> task.status = TaskStatus.DRAFT
        >>> task.status = TaskStatus.PUBLISHED  # Invalid - skips entire pipeline
        InvalidStateTransitionError: Invalid transition: draft → published

    Related:
        - Story 5.1: 26-Status Workflow State Machine
        - FR51: 26 workflow status progression
        - Task.VALID_TRANSITIONS: Dictionary defining allowed transitions
    """

    def __init__(self, message: str, from_status: "TaskStatus", to_status: "TaskStatus") -> None:
        """Initialize InvalidStateTransitionError with transition details.

        Args:
            message: Human-readable error message.
            from_status: Current status before transition attempt.
            to_status: Target status that was attempted.
        """
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(message)

    def __str__(self) -> str:
        """Return detailed error message with transition context.

        Returns:
            Error message including from_status and to_status values for debugging.
        """
        base_message = super().__str__()
        return f"{base_message} (from={self.from_status.value}, to={self.to_status.value})"
