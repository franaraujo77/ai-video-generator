"""Actionable error recommendations for common failure scenarios (Story 6.4, Task 6).

This module generates user-facing recommendations based on error category and API service.
Recommendations guide users toward resolution (check API keys, increase timeouts, review inputs).

Architecture Pattern:
    - Maps ErrorCategory + API service → specific recommendation
    - Never executes recommendations (action suggestions only)
    - Recommendations included in Notion Error Log footer

Example:
    >>> from app.services.error_classifier import ErrorCategory, ErrorAnalysis
    >>> analysis = ErrorAnalysis(
    ...     category=ErrorCategory.CONFIGURATION,
    ...     http_status_code=401,
    ...     error_type="HTTPStatusError",
    ...     error_message="Unauthorized",
    ...     retry_recommended=False,
    ...     confidence=0.95,
    ...     suggested_action="Check API key",
    ...     api_service="Gemini",
    ... )
    >>> recommendation = get_error_recommendation(analysis)
    >>> print(recommendation)
    "Check GEMINI_API_KEY in channel config (Railway environment variables)"
"""

from app.services.error_classifier import ErrorAnalysis, ErrorCategory


def get_error_recommendation(error_analysis: ErrorAnalysis) -> str:
    """Generate actionable recommendation based on error category and API service.

    Maps error patterns to specific actions that users can take to resolve or mitigate issues.
    Recommendations consider both the error category (TRANSIENT, PERMANENT, etc.) and the
    specific API service that failed.

    Args:
        error_analysis: Error classification from Story 6.1 error_classifier

    Returns:
        Human-readable recommendation string

    Examples:
        >>> # Configuration error + Gemini
        >>> analysis = ErrorAnalysis(
        ...     category=ErrorCategory.CONFIGURATION,
        ...     api_service="Gemini",
        ...     ...
        ... )
        >>> get_error_recommendation(analysis)
        "Check GEMINI_API_KEY in channel config (Railway environment variables)"

        >>> # Transient error + timeout
        >>> analysis = ErrorAnalysis(
        ...     category=ErrorCategory.TRANSIENT,
        ...     api_service="KIE.ai",
        ...     suggested_action="Network timeout - retry with longer timeout",
        ...     ...
        ... )
        >>> get_error_recommendation(analysis)
        "Video generation timeout - retry in progress (consider simpler prompts if recurring)"
    """
    api_service = error_analysis.api_service or "Unknown"

    # Configuration errors - API credentials or setup issues
    if error_analysis.category == ErrorCategory.CONFIGURATION:
        return _get_configuration_recommendation(api_service)

    # Transient errors - retry in progress
    if error_analysis.category == ErrorCategory.TRANSIENT:
        return _get_transient_recommendation(error_analysis, api_service)

    # Quota exceeded errors
    if error_analysis.category == ErrorCategory.QUOTA_EXCEEDED:
        return _get_quota_recommendation(api_service)

    # Permanent errors - won't succeed on retry
    if error_analysis.category == ErrorCategory.PERMANENT:
        return _get_permanent_recommendation(error_analysis)

    # Unknown errors - conservative guidance
    return "Check error details and logs for more information"


def _get_configuration_recommendation(api_service: str) -> str:
    """Generate recommendation for configuration errors (auth, API keys).

    Args:
        api_service: API service that failed (e.g., "Gemini", "KIE.ai")

    Returns:
        Recommendation to check specific API credentials
    """
    recommendations = {
        "Gemini": "Check GEMINI_API_KEY in channel config (Railway environment variables)",
        "KIE.ai": "Verify KIE_API_KEY and ensure API subscription is active",
        "ElevenLabs": "Check ELEVENLABS_API_KEY and verify API subscription status",
        "YouTube": "Verify YouTube OAuth tokens are valid (re-run setup_channel_oauth.py)",
        "Notion": "Check Notion API token and ensure workspace access is granted",
    }
    return recommendations.get(
        api_service, f"Check API credentials for {api_service}"
    )


def _get_transient_recommendation(error_analysis: ErrorAnalysis, api_service: str) -> str:
    """Generate recommendation for transient errors (network, rate limits, timeouts).

    Args:
        error_analysis: Error classification with suggested_action
        api_service: API service that failed

    Returns:
        Recommendation for transient error (retry in progress)
    """
    # Check if error is timeout-related
    if "timeout" in error_analysis.suggested_action.lower():
        if api_service == "KIE.ai":
            prompt_tip = " (consider simpler prompts if recurring)"
            return f"Video generation timeout - retry in progress{prompt_tip}"
        else:
            return f"{api_service} timeout - retry scheduled with exponential backoff"

    # Check if error is rate limit
    if "rate limit" in error_analysis.suggested_action.lower():
        return f"{api_service} rate limit - waiting before retry (automatic backoff)"

    # Generic transient error
    return "Transient network error - automatic retry in progress"


def _get_quota_recommendation(api_service: str) -> str:
    """Generate recommendation for quota exceeded errors.

    Args:
        api_service: API service that exceeded quota

    Returns:
        Recommendation to check quota limits
    """
    recommendations = {
        "YouTube": "YouTube daily quota exceeded (10,000 units) - uploads paused until tomorrow",
        "ElevenLabs": "ElevenLabs character limit reached - check monthly quota in dashboard",
        "KIE.ai": "KIE.ai quota exceeded - check credit balance and upgrade plan if needed",
        "Gemini": "Gemini API quota exceeded - check usage limits in Google Cloud Console",
    }
    default = f"{api_service} quota exceeded - check usage limits and upgrade plan if needed"
    return recommendations.get(api_service, default)


def _get_permanent_recommendation(error_analysis: ErrorAnalysis) -> str:
    """Generate recommendation for permanent errors (validation, bad requests).

    Args:
        error_analysis: Error classification with suggested_action

    Returns:
        Recommendation for permanent error (manual investigation)
    """
    # Check for specific error patterns in suggested_action
    if "prompt" in error_analysis.suggested_action.lower():
        return "Invalid prompt detected - review task inputs and regenerate"
    elif "file" in error_analysis.suggested_action.lower():
        return "File operation failed - check filesystem permissions and disk space"
    elif "bad request" in error_analysis.suggested_action.lower():
        return "API request invalid - review request parameters and API documentation"
    elif "not found" in error_analysis.suggested_action.lower():
        return "Resource not found - verify resource exists and is accessible"
    else:
        return "Permanent error - manual investigation required (see error log)"
