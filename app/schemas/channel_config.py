"""Channel configuration schema for YAML files.

This module defines the Pydantic v2 schema for validating channel configuration
loaded from YAML files in the channel_configs/ directory.

Branding Configuration (FR11):
    Channels can specify intro/outro videos and watermark images for video assembly.
    Branding paths must be relative paths (no absolute paths) to ensure portability.

Voice Configuration (FR10):
    Each channel can specify an ElevenLabs voice_id for narration.
    If not set, the system falls back to DEFAULT_VOICE_ID from environment.
"""

import re
from decimal import Decimal
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BrandingConfig(BaseModel):
    """Branding configuration for channel videos (FR11).

    Specifies intro/outro videos and optional watermark for video assembly.
    All paths must be relative to the channel workspace (no absolute paths).

    Attributes:
        intro_video: Relative path to intro video file (e.g., "channel_assets/intro.mp4").
        outro_video: Relative path to outro video file (e.g., "channel_assets/outro.mp4").
        watermark_image: Optional relative path to watermark image (e.g., "channel_assets/watermark.png").

    Example YAML:
        branding:
          intro_video: "channel_assets/intro_v2.mp4"
          outro_video: "channel_assets/outro_v2.mp4"
          watermark_image: "channel_assets/watermark.png"  # Optional
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    intro_video: str | None = Field(default=None, max_length=255)
    outro_video: str | None = Field(default=None, max_length=255)
    watermark_image: str | None = Field(default=None, max_length=255)

    @field_validator("intro_video", "outro_video", "watermark_image", mode="before")
    @classmethod
    def validate_relative_path(cls, v: str | None) -> str | None:
        """Validate that branding paths are relative (not absolute).

        Args:
            v: The path value to validate.

        Returns:
            The validated path or None.

        Raises:
            ValueError: If path is absolute (starts with / or contains drive letter).
        """
        if v is None or v == "":
            return None

        # Check for absolute paths
        path = PurePosixPath(v)
        if path.is_absolute():
            raise ValueError(f"Branding path must be relative, not absolute: {v}")

        # Check for Windows-style absolute paths (e.g., C:\path)
        if len(v) >= 2 and v[1] == ":":
            raise ValueError(f"Branding path must be relative, not absolute: {v}")

        # Check for path traversal attempts
        if ".." in v:
            raise ValueError(f"Branding path cannot contain '..': {v}")

        return v

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        fields = []
        if self.intro_video:
            fields.append(f"intro={self.intro_video!r}")
        if self.outro_video:
            fields.append(f"outro={self.outro_video!r}")
        if self.watermark_image:
            fields.append(f"watermark={self.watermark_image!r}")
        return f"BrandingConfig({', '.join(fields) if fields else 'empty'})"


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
    voice_id: str | None = Field(
        default=None,
        max_length=100,
        description="ElevenLabs voice ID for channel narration (FR10)",
    )
    storage_strategy: str = Field(default="notion")
    max_concurrent: int = Field(default=2, ge=1, le=10)
    budget_daily_usd: Decimal | None = Field(default=None, ge=0)

    # Branding configuration (FR11)
    branding: BrandingConfig | None = Field(
        default=None,
        description="Intro/outro video and watermark configuration for video assembly",
    )

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
        """Return string representation for debugging.

        Shows voice_id presence (not value) and branding status for security.
        """
        voice_info = "set" if self.voice_id else "not_set"
        branding_info = "configured" if self.branding else "not_configured"
        return (
            f"ChannelConfigSchema(channel_id={self.channel_id!r}, "
            f"channel_name={self.channel_name!r}, "
            f"priority={self.priority!r}, "
            f"is_active={self.is_active!r}, "
            f"voice_id={voice_info}, "
            f"branding={branding_info})"
        )
