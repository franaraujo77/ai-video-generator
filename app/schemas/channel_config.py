"""Channel configuration schema for YAML files.

This module defines the Pydantic v2 schema for validating channel configuration
loaded from YAML files in the channel_configs/ directory.
"""

import re
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChannelConfigSchema(BaseModel):
    """Channel configuration loaded from YAML file.

    This schema validates channel configuration data loaded from YAML files.
    Required fields must be present; optional fields have sensible defaults.

    Attributes:
        channel_id: Business identifier (alphanumeric + underscore, max 50 chars).
        channel_name: Human-readable display name.
        notion_database_id: Notion database ID for video entries.
        priority: Processing priority (high, normal, low).
        is_active: Whether channel is enabled for processing.
        voice_id: ElevenLabs voice ID for narration (optional).
        storage_strategy: Asset storage strategy (notion or r2).
        max_concurrent: Maximum parallel tasks per channel.
        budget_daily_usd: Daily spending limit in USD (optional).
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_default=True,
    )

    # Required fields
    channel_id: str = Field(..., min_length=1, max_length=50)
    channel_name: str = Field(..., min_length=1, max_length=100)
    notion_database_id: str = Field(..., min_length=1)

    # Optional fields with defaults
    priority: str = Field(default="normal")
    is_active: bool = Field(default=True)
    voice_id: str | None = Field(default=None)
    storage_strategy: str = Field(default="notion")
    max_concurrent: int = Field(default=2, ge=1, le=10)
    budget_daily_usd: Decimal | None = Field(default=None, ge=0)

    @field_validator("channel_id")
    @classmethod
    def validate_channel_id(cls, v: str) -> str:
        """Channel ID must be alphanumeric with underscores only.

        Args:
            v: The channel_id value to validate.

        Returns:
            Normalized lowercase channel_id.

        Raises:
            ValueError: If channel_id contains invalid characters.
        """
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("channel_id must be alphanumeric with underscores only")
        return v.lower()  # Normalize to lowercase

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """Priority must be high, normal, or low.

        Args:
            v: The priority value to validate.

        Returns:
            Normalized lowercase priority.

        Raises:
            ValueError: If priority is not one of the allowed values.
        """
        allowed = {"high", "normal", "low"}
        if v.lower() not in allowed:
            raise ValueError(f"priority must be one of: {allowed}")
        return v.lower()

    @field_validator("storage_strategy")
    @classmethod
    def validate_storage_strategy(cls, v: str) -> str:
        """Storage strategy must be notion or r2.

        Args:
            v: The storage_strategy value to validate.

        Returns:
            Normalized lowercase storage_strategy.

        Raises:
            ValueError: If storage_strategy is not one of the allowed values.
        """
        allowed = {"notion", "r2"}
        if v.lower() not in allowed:
            raise ValueError(f"storage_strategy must be one of: {allowed}")
        return v.lower()

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"ChannelConfigSchema(channel_id={self.channel_id!r}, "
            f"channel_name={self.channel_name!r}, "
            f"priority={self.priority!r}, "
            f"is_active={self.is_active!r})"
        )
