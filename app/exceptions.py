"""Shared exceptions for the application.

This module contains exception classes used across multiple services
to avoid cross-domain dependencies between services.
"""


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

    def __init__(self, message: str, from_status: "TaskStatus", to_status: "TaskStatus"):
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
