"""Channel data factories for test data generation.

Generates Channel model instances and related test data.
Uses deterministic defaults with override support for specific test scenarios.
"""

import uuid

from app.models import Channel


def create_channel(
    channel_id: str | None = None,
    channel_name: str | None = None,
    is_active: bool = True,
    voice_id: str | None = None,
    branding_intro_path: str | None = None,
    branding_outro_path: str | None = None,
    branding_watermark_path: str | None = None,
    **kwargs,
) -> Channel:
    """Create a Channel model instance with sensible defaults.

    All parameters are optional and can be overridden for specific test scenarios.

    Args:
        channel_id: Business identifier (default: auto-generated "test_channel_xxx").
        channel_name: Human-readable name (default: "Test Channel").
        is_active: Active status (default: True).
        voice_id: ElevenLabs voice ID (default: None).
        branding_intro_path: Intro video path (default: None).
        branding_outro_path: Outro video path (default: None).
        branding_watermark_path: Watermark image path (default: None).
        **kwargs: Additional attributes to set on the channel.

    Returns:
        Channel model instance (not yet added to session).

    Example:
        >>> channel = create_channel(channel_id="poke1")
        >>> session.add(channel)
        >>> await session.commit()
    """
    # Generate unique channel_id if not provided
    if channel_id is None:
        unique_suffix = uuid.uuid4().hex[:8]
        channel_id = f"test_channel_{unique_suffix}"

    # Generate channel_name from channel_id if not provided
    if channel_name is None:
        channel_name = f"Test Channel {channel_id}"

    channel = Channel(
        channel_id=channel_id,
        channel_name=channel_name,
        is_active=is_active,
        voice_id=voice_id,
        branding_intro_path=branding_intro_path,
        branding_outro_path=branding_outro_path,
        branding_watermark_path=branding_watermark_path,
    )

    # Apply any additional kwargs
    for key, value in kwargs.items():
        if hasattr(channel, key):
            setattr(channel, key, value)

    return channel


def create_channel_with_credentials(
    channel_id: str | None = None,
    youtube_token: bytes | None = b"encrypted_youtube_token",
    notion_token: bytes | None = b"encrypted_notion_token",
    gemini_key: bytes | None = b"encrypted_gemini_key",
    elevenlabs_key: bytes | None = b"encrypted_elevenlabs_key",
    **kwargs,
) -> Channel:
    """Create a Channel with pre-populated encrypted credentials.

    Useful for testing credential retrieval without the encryption layer.

    Args:
        channel_id: Business identifier.
        youtube_token: Encrypted YouTube OAuth token bytes.
        notion_token: Encrypted Notion API token bytes.
        gemini_key: Encrypted Gemini API key bytes.
        elevenlabs_key: Encrypted ElevenLabs API key bytes.
        **kwargs: Additional channel attributes.

    Returns:
        Channel model instance with encrypted credential fields set.
    """
    channel = create_channel(channel_id=channel_id, **kwargs)
    channel.youtube_token_encrypted = youtube_token
    channel.notion_token_encrypted = notion_token
    channel.gemini_key_encrypted = gemini_key
    channel.elevenlabs_key_encrypted = elevenlabs_key
    return channel


def create_channel_with_branding(
    channel_id: str | None = None,
    intro_path: str = "channel_assets/intro.mp4",
    outro_path: str = "channel_assets/outro.mp4",
    watermark_path: str = "channel_assets/watermark.png",
    **kwargs,
) -> Channel:
    """Create a Channel with branding assets configured.

    Useful for testing video assembly with channel-specific branding.

    Args:
        channel_id: Business identifier.
        intro_path: Relative path to intro video.
        outro_path: Relative path to outro video.
        watermark_path: Relative path to watermark image.
        **kwargs: Additional channel attributes.

    Returns:
        Channel model instance with branding paths set.
    """
    return create_channel(
        channel_id=channel_id,
        branding_intro_path=intro_path,
        branding_outro_path=outro_path,
        branding_watermark_path=watermark_path,
        **kwargs,
    )


def create_channels(count: int, prefix: str = "batch") -> list[Channel]:
    """Create multiple Channel instances.

    Args:
        count: Number of channels to create.
        prefix: Prefix for channel_id generation (default: "batch").

    Returns:
        List of Channel model instances.

    Example:
        >>> channels = create_channels(5)
        >>> session.add_all(channels)
    """
    return [create_channel(channel_id=f"{prefix}_channel_{i}") for i in range(count)]


def create_active_channel(**kwargs) -> Channel:
    """Create an active channel (is_active=True).

    Convenience function for tests requiring active channels.
    """
    return create_channel(is_active=True, **kwargs)


def create_inactive_channel(**kwargs) -> Channel:
    """Create an inactive channel (is_active=False).

    Convenience function for tests filtering by active status.
    """
    return create_channel(is_active=False, **kwargs)


def create_channel_with_r2_storage(
    channel_id: str | None = None,
    r2_account_id_encrypted: bytes | None = b"encrypted_account_id",
    r2_access_key_id_encrypted: bytes | None = b"encrypted_access_key",
    r2_secret_access_key_encrypted: bytes | None = b"encrypted_secret_key",
    r2_bucket_name: str = "test-bucket",
    **kwargs,
) -> Channel:
    """Create a Channel with R2 storage strategy and encrypted credentials.

    Useful for testing StorageStrategyService without the encryption layer.

    Args:
        channel_id: Business identifier.
        r2_account_id_encrypted: Encrypted Cloudflare account ID bytes.
        r2_access_key_id_encrypted: Encrypted R2 access key ID bytes.
        r2_secret_access_key_encrypted: Encrypted R2 secret access key bytes.
        r2_bucket_name: R2 bucket name (not encrypted).
        **kwargs: Additional channel attributes.

    Returns:
        Channel model instance with R2 storage configuration.
    """
    channel = create_channel(channel_id=channel_id, **kwargs)
    channel.storage_strategy = "r2"
    channel.r2_account_id_encrypted = r2_account_id_encrypted
    channel.r2_access_key_id_encrypted = r2_access_key_id_encrypted
    channel.r2_secret_access_key_encrypted = r2_secret_access_key_encrypted
    channel.r2_bucket_name = r2_bucket_name
    return channel


def create_channel_with_notion_storage(
    channel_id: str | None = None,
    **kwargs,
) -> Channel:
    """Create a Channel with Notion storage strategy (default).

    Useful for testing storage strategy fallback behavior.

    Args:
        channel_id: Business identifier.
        **kwargs: Additional channel attributes.

    Returns:
        Channel model instance with Notion storage configuration.
    """
    channel = create_channel(channel_id=channel_id, **kwargs)
    channel.storage_strategy = "notion"
    return channel
