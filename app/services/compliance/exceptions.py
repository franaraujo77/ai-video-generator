"""Compliance enforcement exceptions."""


class ComplianceViolationError(Exception):
    """Raised when YouTube Partner Program compliance checks fail.

    This exception indicates that a video cannot be uploaded due to:
    - Content uniqueness failure (below 70% threshold)
    - Duplicate content detection (similarity >90%)
    - Upload frequency limit exceeded
    - Missing human review evidence
    - Missing AI disclosure metadata

    Attributes:
        violation_type: Type of violation (uniqueness_failure, duplicate_content, etc.)
        validation_results: Detailed validation data for audit trail
        message: Human-readable error description
    """

    def __init__(
        self,
        message: str,
        violation_type: str | None = None,
        validation_results: dict[str, bool] | None = None,
    ):
        """Initialize compliance violation error.

        Args:
            message: Human-readable error description
            violation_type: Type of violation (uniqueness_failure, duplicate_content, etc.)
            validation_results: Detailed validation data for audit logging
        """
        super().__init__(message)
        self.violation_type = violation_type or "unknown"
        self.validation_results = validation_results or {}
