"""Centralized error classification service for transient vs permanent failures.

This module provides error classification to distinguish transient failures (retriable)
from permanent failures (fail fast), enabling intelligent retry strategies.

Classification Rules:
- Transient (retry): 429, 500-504, timeouts, network errors
- Permanent (fail fast): 400, 401, 403, 404, 422
- Unknown (conservative retry): Unrecognized errors

Architecture Pattern:
- Error detection happens at service layer, NOT in CLI scripts
- Services parse stderr from CLIScriptError to classify errors
- Classification never fails the pipeline (graceful degradation to UNKNOWN)

Story Reference: 6.1 - Transient Failure Detection
Related: Story 6.2 will extend with task-level retry (exponential backoff)
"""

import re
from dataclasses import dataclass
from enum import Enum

import httpx

from app.utils.cli_wrapper import CLIScriptError


class ErrorCategory(Enum):
    """Error category for classification.

    TRANSIENT: Retry recommended (rate limits, server errors, network issues)
    PERMANENT: Fail fast (auth errors, bad requests, validation errors)
    CONFIGURATION: Setup errors (API keys, auth tokens, missing credentials)
    QUOTA_EXCEEDED: API quota limits reached (requires manual intervention)
    UNKNOWN: Conservative retry (unrecognized error types)
    """

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    CONFIGURATION = "configuration"
    QUOTA_EXCEEDED = "quota_exceeded"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """Context information for error classification (Story 6.4).

    Provides additional context about where and when an error occurred, enabling
    richer error messages and more targeted recommendations.

    Attributes:
        step_name: Pipeline step name (e.g., "video_generation", "asset_generation")
        task_id: Task UUID as string
        channel_id: Channel ID as string
        clip_index: Video clip index (1-18) if applicable
        total_clips: Total video clips (usually 18) if applicable
        asset_index: Asset index (1-22) if applicable
        total_assets: Total assets (usually 22) if applicable
        asset_name: Asset filename if applicable (e.g., "environment_background_3.png")

    Example:
        >>> context = ErrorContext(
        ...     step_name="video_generation",
        ...     task_id="12345678-1234-1234-1234-123456789abc",
        ...     channel_id="poke1",
        ...     clip_index=11,
        ...     total_clips=18,
        ... )
    """

    step_name: str
    task_id: str
    channel_id: str
    clip_index: int | None = None
    total_clips: int | None = None
    asset_index: int | None = None
    total_assets: int | None = None
    asset_name: str | None = None


@dataclass
class ErrorAnalysis:
    """Analysis of single error for transient vs permanent classification.

    Attributes:
        category: Error category (TRANSIENT, PERMANENT, UNKNOWN)
        http_status_code: HTTP status code if applicable, None otherwise
        error_type: Exception type name (e.g., "HTTPStatusError", "TimeoutException")
        error_message: Original error message
        retry_recommended: Whether retry is recommended based on category
        confidence: Classification confidence (0.0-1.0, higher = more certain)
        suggested_action: Human-readable suggested action for operators
        api_service: API service that failed (Story 6.4 - e.g., "KIE.ai", "Gemini")
    """

    category: ErrorCategory
    http_status_code: int | None
    error_type: str
    error_message: str
    retry_recommended: bool
    confidence: float
    suggested_action: str
    api_service: str | None = None  # Story 6.4: API service extraction


def classify_error(exception: Exception, context: ErrorContext | None = None) -> ErrorAnalysis:
    """Classify error as transient, permanent, or unknown.

    This is the main entry point for error classification. Handles httpx exceptions,
    CLI script errors (stderr parsing), and generic exceptions.

    Transient (retry recommended):
    - HTTP 429 (rate limit)
    - HTTP 500, 502, 503, 504 (server errors)
    - httpx.TimeoutException (connect, read, write timeout)
    - httpx.ConnectError, httpx.NetworkError

    Permanent (fail fast):
    - HTTP 400 (bad request)
    - HTTP 401 (unauthorized)
    - HTTP 403 (forbidden)
    - HTTP 404 (not found)
    - HTTP 422 (unprocessable entity)

    Unknown (conservative retry):
    - Other exceptions not matching patterns

    Args:
        exception: Exception to classify
        context: Optional context about where/when error occurred (Story 6.4)

    Returns:
        ErrorAnalysis with classification details and API service (Story 6.4)

    Example:
        >>> import httpx
        >>> request = httpx.Request("GET", "https://api.example.com")
        >>> response = httpx.Response(429, request=request)
        >>> exception = httpx.HTTPStatusError("Rate limited", request=request, response=response)
        >>> analysis = classify_error(exception)
        >>> print(analysis.category)
        ErrorCategory.TRANSIENT
        >>> print(analysis.retry_recommended)
        True

        >>> # With context (Story 6.4)
        >>> context = ErrorContext(
        ...     step_name="video_generation",
        ...     task_id="123",
        ...     channel_id="poke1",
        ...     clip_index=11,
        ...     total_clips=18,
        ... )
        >>> analysis = classify_error(exception, context)
        >>> print(analysis.api_service)  # Extracted from exception
    """
    try:
        # Handle httpx HTTP status errors
        if isinstance(exception, httpx.HTTPStatusError):
            analysis = _classify_http_status_error(exception)

        # Handle httpx timeout exceptions
        elif isinstance(
            exception,
            httpx.TimeoutException | httpx.ConnectTimeout | httpx.ReadTimeout | httpx.WriteTimeout,
        ):
            analysis = _classify_timeout_error(exception)

        # Handle httpx network errors
        elif isinstance(exception, httpx.ConnectError | httpx.NetworkError):
            analysis = _classify_network_error(exception)

        # Handle CLI script errors (parse stderr for HTTP codes)
        elif isinstance(exception, CLIScriptError):
            analysis = _classify_cli_script_error(exception)

        # Unknown error - conservative retry with low confidence
        else:
            analysis = _classify_unknown_error(exception)

        # Story 6.4: Extract API service from exception message/context
        analysis.api_service = _extract_api_service(exception, context)

        return analysis

    except Exception as e:
        # CRITICAL: Never fail the pipeline due to classification errors
        # Return UNKNOWN with very low confidence for graceful degradation
        return ErrorAnalysis(
            category=ErrorCategory.UNKNOWN,
            http_status_code=None,
            error_type=type(exception).__name__,
            error_message=str(exception),
            retry_recommended=True,  # Conservative retry
            confidence=0.1,
            suggested_action=f"Classification failed ({e!s}), retry conservatively",
            api_service="Unknown",
        )


def _classify_http_status_error(exception: httpx.HTTPStatusError) -> ErrorAnalysis:
    """Classify httpx.HTTPStatusError based on HTTP status code.

    Args:
        exception: HTTPStatusError from httpx

    Returns:
        ErrorAnalysis with classification
    """
    status_code = exception.response.status_code
    error_message = str(exception)

    # Transient errors (server-side issues, rate limits)
    if status_code == 429:
        return ErrorAnalysis(
            category=ErrorCategory.TRANSIENT,
            http_status_code=status_code,
            error_type="HTTPStatusError",
            error_message=error_message,
            retry_recommended=True,
            confidence=0.95,
            suggested_action="Rate limit exceeded - wait and retry with exponential backoff",
        )

    if status_code in (500, 502, 503, 504):
        return ErrorAnalysis(
            category=ErrorCategory.TRANSIENT,
            http_status_code=status_code,
            error_type="HTTPStatusError",
            error_message=error_message,
            retry_recommended=True,
            confidence=0.9,
            suggested_action=f"Server error ({status_code}) - retry after brief delay",
        )

    # Configuration errors (auth failures - Story 6.4)
    if status_code in (401, 403):
        action_map = {
            401: "Unauthorized - check API key/credentials",
            403: "Forbidden - check permissions",
        }
        return ErrorAnalysis(
            category=ErrorCategory.CONFIGURATION,
            http_status_code=status_code,
            error_type="HTTPStatusError",
            error_message=error_message,
            retry_recommended=False,
            confidence=0.95,
            suggested_action=action_map[status_code],
        )

    # Permanent errors (client-side issues, validation errors)
    if status_code in (400, 404, 422):
        action_map = {
            400: "Bad request - fix request parameters",
            404: "Not found - verify resource exists",
            422: "Unprocessable entity - fix request data format",
        }
        return ErrorAnalysis(
            category=ErrorCategory.PERMANENT,
            http_status_code=status_code,
            error_type="HTTPStatusError",
            error_message=error_message,
            retry_recommended=False,
            confidence=0.95,
            suggested_action=action_map[status_code],
        )

    # Unknown HTTP status code - conservative retry with low confidence (matches spec: 0.3-0.5)
    return ErrorAnalysis(
        category=ErrorCategory.UNKNOWN,
        http_status_code=status_code,
        error_type="HTTPStatusError",
        error_message=error_message,
        retry_recommended=True,
        confidence=0.3,
        suggested_action=f"Unknown HTTP status {status_code} - retry conservatively",
    )


def _classify_timeout_error(exception: Exception) -> ErrorAnalysis:
    """Classify timeout exceptions as transient.

    Args:
        exception: Timeout exception (TimeoutException, ConnectTimeout, etc.)

    Returns:
        ErrorAnalysis with TRANSIENT classification
    """
    # Use qualified name for better log analysis (httpx.TimeoutException vs TimeoutException)
    error_type = f"{type(exception).__module__}.{type(exception).__name__}"
    return ErrorAnalysis(
        category=ErrorCategory.TRANSIENT,
        http_status_code=None,
        error_type=error_type,
        error_message=str(exception),
        retry_recommended=True,
        confidence=0.85,
        suggested_action="Network timeout - retry with longer timeout or exponential backoff",
    )


def _classify_network_error(exception: Exception) -> ErrorAnalysis:
    """Classify network errors as transient.

    Args:
        exception: Network exception (ConnectError, NetworkError)

    Returns:
        ErrorAnalysis with TRANSIENT classification
    """
    # Use qualified name for better log analysis
    error_type = f"{type(exception).__module__}.{type(exception).__name__}"
    return ErrorAnalysis(
        category=ErrorCategory.TRANSIENT,
        http_status_code=None,
        error_type=error_type,
        error_message=str(exception),
        retry_recommended=True,
        confidence=0.8,
        suggested_action="Network error - check connectivity and retry",
    )


def _classify_cli_script_error(exception: CLIScriptError) -> ErrorAnalysis:
    """Classify CLI script error by parsing stderr for HTTP status codes.

    Parses stderr text for HTTP status codes and error keywords (rate limit, timeout).

    Args:
        exception: CLIScriptError from CLI wrapper

    Returns:
        ErrorAnalysis with classification based on stderr content
    """
    stderr = exception.stderr
    stderr_lower = stderr.lower()

    # Extract HTTP status code from stderr (supports formats: "429", "HTTP 429", "HTTP 429:", etc.)
    # Pattern matches 4xx and 5xx codes, validated against known status codes
    http_status_pattern = r"\b(4\d{2}|5\d{2})\b"
    match = re.search(http_status_pattern, stderr)

    if match:
        status_code = int(match.group(1))

        # Transient status codes
        if status_code == 429 or "rate limit" in stderr_lower:
            return ErrorAnalysis(
                category=ErrorCategory.TRANSIENT,
                http_status_code=status_code if status_code == 429 else 429,
                error_type="CLIScriptError",
                error_message=stderr,
                retry_recommended=True,
                confidence=0.9,
                suggested_action="Rate limit from CLI script - wait and retry",
            )

        if status_code in (500, 502, 503, 504):
            return ErrorAnalysis(
                category=ErrorCategory.TRANSIENT,
                http_status_code=status_code,
                error_type="CLIScriptError",
                error_message=stderr,
                retry_recommended=True,
                confidence=0.9,
                suggested_action=f"Server error {status_code} from CLI script - retry",
            )

        # Configuration errors (auth failures)
        if status_code in (401, 403):
            return ErrorAnalysis(
                category=ErrorCategory.CONFIGURATION,
                http_status_code=status_code,
                error_type="CLIScriptError",
                error_message=stderr,
                retry_recommended=False,
                confidence=0.9,
                suggested_action=f"Auth error {status_code} - check API credentials",
            )

        # Permanent status codes (validation errors)
        if status_code in (400, 404, 422):
            return ErrorAnalysis(
                category=ErrorCategory.PERMANENT,
                http_status_code=status_code,
                error_type="CLIScriptError",
                error_message=stderr,
                retry_recommended=False,
                confidence=0.9,
                suggested_action=f"Client error {status_code} - fix script parameters",
            )

    # Check for timeout keywords without HTTP status code
    if "timeout" in stderr_lower:
        return ErrorAnalysis(
            category=ErrorCategory.TRANSIENT,
            http_status_code=None,
            error_type="CLIScriptError",
            error_message=stderr,
            retry_recommended=True,
            confidence=0.8,
            suggested_action="Timeout in CLI script - retry with longer timeout",
        )

    # Check for rate limit keywords without HTTP status code
    if "rate limit" in stderr_lower:
        return ErrorAnalysis(
            category=ErrorCategory.TRANSIENT,
            http_status_code=429,
            error_type="CLIScriptError",
            error_message=stderr,
            retry_recommended=True,
            confidence=0.85,
            suggested_action="Rate limit detected - wait and retry",
        )

    # Unknown CLI error - conservative retry with low confidence
    return ErrorAnalysis(
        category=ErrorCategory.UNKNOWN,
        http_status_code=None,
        error_type="CLIScriptError",
        error_message=stderr,
        retry_recommended=True,
        confidence=0.3,
        suggested_action="Unknown CLI script error - retry conservatively or investigate logs",
    )


def _classify_unknown_error(exception: Exception) -> ErrorAnalysis:
    """Classify unknown exceptions with conservative retry strategy.

    Args:
        exception: Generic exception not matching known patterns

    Returns:
        ErrorAnalysis with UNKNOWN classification and low confidence
    """
    # Use qualified name for better log analysis
    error_type = f"{type(exception).__module__}.{type(exception).__name__}"
    action = f"Unknown error type ({error_type}) - investigate and retry conservatively"
    return ErrorAnalysis(
        category=ErrorCategory.UNKNOWN,
        http_status_code=None,
        error_type=error_type,
        error_message=str(exception),
        retry_recommended=True,  # Conservative retry
        confidence=0.3,
        suggested_action=action,
    )


def _extract_api_service(exception: Exception, context: ErrorContext | None = None) -> str:
    """Extract API service name from exception message or context (Story 6.4).

    Attempts to identify which API service caused the error by analyzing:
    1. Context step_name (primary source if available)
    2. Exception message keywords
    3. Exception type and module

    Args:
        exception: Exception to analyze
        context: Optional context with step_name

    Returns:
        API service name (e.g., "KIE.ai", "Gemini", "ElevenLabs", "Notion", "YouTube")
        or "Unknown" if service cannot be determined

    Examples:
        >>> exc = Exception("KIE.ai timeout")
        >>> _extract_api_service(exc)
        'KIE.ai'

        >>> context = ErrorContext(step_name="video_generation", task_id="123", channel_id="poke1")
        >>> _extract_api_service(Exception("timeout"), context)
        'KIE.ai'

        >>> context = ErrorContext(step_name="asset_generation", task_id="123", channel_id="poke1")
        >>> _extract_api_service(Exception("401"), context)
        'Gemini'
    """
    # Priority 1: Infer from context step_name (most reliable)
    if context:
        step_to_service = {
            "video_generation": "KIE.ai",
            "asset_generation": "Gemini",
            "narration_generation": "ElevenLabs",
            "sfx_generation": "ElevenLabs",
            "notion_sync": "Notion",
            "youtube_upload": "YouTube",
        }

        if context.step_name in step_to_service:
            return step_to_service[context.step_name]

    # Priority 2: Parse exception message for API keywords
    error_msg = str(exception).lower()

    if "kie.ai" in error_msg or "kling" in error_msg:
        return "KIE.ai"
    elif "gemini" in error_msg or "google.generativeai" in error_msg:
        return "Gemini"
    elif "elevenlabs" in error_msg:
        return "ElevenLabs"
    elif "notion" in error_msg:
        return "Notion"
    elif "youtube" in error_msg:
        return "YouTube"

    # Priority 3: Check exception type/module
    exception_type = type(exception).__module__ + "." + type(exception).__name__

    if "google" in exception_type:
        return "Gemini"
    elif "httpx" in exception_type or "requests" in exception_type:
        return "HTTP Client"  # Generic HTTP error

    return "Unknown"
