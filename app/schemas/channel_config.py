"""Channel configuration schema for YAML files.

This module defines the Pydantic v2 schema for validating channel configuration
loaded from YAML files in the channel_configs/ directory.

Branding Configuration (FR11):
    Channels can specify intro/outro videos and watermark images for video assembly.
    Branding paths must be relative paths (no absolute paths) to ensure portability.

Voice Configuration (FR10):
    Each channel can specify an ElevenLabs voice_id for narration.
    If not set, the system falls back to DEFAULT_VOICE_ID from environment.

Storage Strategy Configuration (FR12):
    Channels can specify where generated assets are stored:
    - "notion" (default): Assets stored as Notion file attachments
    - "r2": Assets uploaded to Cloudflare R2 storage

    When storage_strategy="r2", the r2_config section must be provided with
    Cloudflare R2 credentials (account_id, access_key_id, secret_access_key, bucket_name).
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
        intro_video: Relative path to intro video file.
        outro_video: Relative path to outro video file.
        watermark_image: Optional relative path to watermark image.

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


# R2 bucket name validation pattern (S3/R2 compliant):
# - Start and end with lowercase alphanumeric
# - Middle can contain lowercase alphanumeric and hyphens
# - Length constraint (3-63 chars) enforced by Pydantic Field validators
R2_BUCKET_NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


class R2Config(BaseModel):
    """Cloudflare R2 storage configuration for channel assets (FR12).

    When storage_strategy is set to "r2", this configuration provides the
    credentials needed to upload assets to Cloudflare R2 object storage.

    All credential fields (account_id, access_key_id, secret_access_key) are
    stored encrypted in the database using Fernet symmetric encryption.
    The bucket_name is not encrypted as it is not sensitive.

    Attributes:
        account_id: Cloudflare account ID (sensitive, will be encrypted).
        access_key_id: R2 access key ID (sensitive, will be encrypted).
        secret_access_key: R2 secret access key (sensitive, will be encrypted).
        bucket_name: R2 bucket name (3-63 chars, lowercase alphanumeric + hyphens).

    Example YAML:
        storage_strategy: "r2"
        r2_config:
          account_id: "cloudflare-account-id"
          access_key_id: "r2-access-key-id"
          secret_access_key: "r2-secret-access-key"
          bucket_name: "pokemon-assets"
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
    )

    account_id: str = Field(..., min_length=1, max_length=100)
    access_key_id: str = Field(..., min_length=1, max_length=100)
    secret_access_key: str = Field(..., min_length=1, max_length=200)
    bucket_name: str = Field(..., min_length=3, max_length=63)

    @field_validator("bucket_name")
    @classmethod
    def validate_bucket_name(cls, v: str) -> str:
        """Validate R2 bucket name format.

        R2 bucket names must be:
        - 3-63 characters long
        - Lowercase alphanumeric and hyphens only
        - Start and end with alphanumeric character
        - Cannot start or end with hyphen

        Args:
            v: The bucket_name value to validate.

        Returns:
            Normalized lowercase bucket_name.

        Raises:
            ValueError: If bucket_name format is invalid.
        """
        v_lower = v.lower()
        if not R2_BUCKET_NAME_PATTERN.match(v_lower):
            raise ValueError(
                f"R2 bucket name must be 3-63 chars, lowercase alphanumeric "
                f"and hyphens, start/end with alphanumeric: {v}"
            )
        return v_lower

    def __repr__(self) -> str:
        """Return string representation for debugging.

        Note:
            NEVER expose credentials in repr - security risk.
            Shows bucket_name and credential presence only.
        """
        has_credentials = all(
            [self.account_id, self.access_key_id, self.secret_access_key]
        )
        creds = "set" if has_credentials else "incomplete"
        return f"R2Config(bucket_name={self.bucket_name!r}, credentials={creds})"


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
        branding: Branding configuration for video assembly (optional).
        r2_config: Cloudflare R2 storage configuration (required when storage_strategy="r2").
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

    # R2 storage configuration (FR12)
    # Required when storage_strategy="r2", ignored when storage_strategy="notion"
    r2_config: R2Config | None = Field(
        default=None,
        description="Cloudflare R2 storage credentials (required when storage_strategy='r2')",
    )

    @model_validator(mode="after")
    def validate_r2_config_required(self) -> "ChannelConfigSchema":
        """Validate that r2_config is provided when storage_strategy is 'r2'.

        If storage_strategy is 'r2' but r2_config is not provided, raises
        a validation error since R2 credentials are required for R2 storage.

        If storage_strategy is 'notion' and r2_config is provided, the r2_config
        is silently ignored (no error raised).

        Returns:
            Self with validated configuration.

        Raises:
            ValueError: If storage_strategy='r2' but r2_config is None.
        """
        if self.storage_strategy == "r2" and self.r2_config is None:
            raise ValueError(
                "r2_config is required when storage_strategy is 'r2'. "
                "Provide account_id, access_key_id, secret_access_key, and bucket_name."
            )
        return self

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

        Shows voice_id presence (not value), branding, and r2_config status for security.
        """
        voice_info = "set" if self.voice_id else "not_set"
        branding_info = "configured" if self.branding else "not_configured"
        r2_info = "configured" if self.r2_config else "not_configured"
        return (
            f"ChannelConfigSchema(channel_id={self.channel_id!r}, "
            f"channel_name={self.channel_name!r}, "
            f"priority={self.priority!r}, "
            f"is_active={self.is_active!r}, "
            f"voice_id={voice_info}, "
            f"storage_strategy={self.storage_strategy!r}, "
            f"branding={branding_info}, "
            f"r2_config={r2_info})"
        )
