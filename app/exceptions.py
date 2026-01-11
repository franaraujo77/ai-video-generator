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
