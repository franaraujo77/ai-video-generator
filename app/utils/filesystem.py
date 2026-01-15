"""Filesystem path helpers for channel-organized video generation workspace.

This module provides standardized path construction functions that enforce
channel isolation and consistent directory structure for the video generation
pipeline. All path helpers automatically create directories if they don't exist.

Security:
    All path helpers validate inputs to prevent path traversal attacks.
    Channel IDs and project IDs must be alphanumeric with optional underscores/dashes.
    Resolved paths are verified to stay within WORKSPACE_ROOT.

Architecture Pattern:
    /app/workspace/channels/{channel_id}/projects/{project_id}/
    ├── assets/
    │   ├── characters/
    │   ├── environments/
    │   ├── props/
    │   └── composites/
    ├── videos/
    ├── audio/
    └── sfx/

Usage:
    from app.utils.filesystem import get_asset_dir, get_video_dir

    # Get asset directory (auto-creates)
    asset_dir = get_asset_dir("poke1", "vid_abc123")
    character_path = asset_dir / "characters" / "bulbasaur.png"

    # Pass string path to CLI script
    await run_cli_script(
        "generate_asset.py",
        ["--output", str(character_path)]
    )
"""

import re
from pathlib import Path

__all__ = [
    "ASSET_DIR_NAME",
    "AUDIO_DIR_NAME",
    "CHANNEL_DIR_NAME",
    "CHARACTER_DIR_NAME",
    "COMPOSITE_DIR_NAME",
    "ENVIRONMENT_DIR_NAME",
    "PROJECT_DIR_NAME",
    "PROPS_DIR_NAME",
    "SFX_DIR_NAME",
    "VIDEO_DIR_NAME",
    "WORKSPACE_ROOT",
    "get_asset_dir",
    "get_audio_dir",
    "get_channel_workspace",
    "get_character_dir",
    "get_composite_dir",
    "get_environment_dir",
    "get_project_dir",
    "get_props_dir",
    "get_sfx_dir",
    "get_video_dir",
]

# Railway persistent volume mount point
WORKSPACE_ROOT = Path("/app/workspace")

# Subdirectory names (constants for consistency)
CHANNEL_DIR_NAME = "channels"
PROJECT_DIR_NAME = "projects"
ASSET_DIR_NAME = "assets"
VIDEO_DIR_NAME = "videos"
AUDIO_DIR_NAME = "audio"
SFX_DIR_NAME = "sfx"

# Asset subdirectory names
CHARACTER_DIR_NAME = "characters"
ENVIRONMENT_DIR_NAME = "environments"
PROPS_DIR_NAME = "props"
COMPOSITE_DIR_NAME = "composites"

# Validation pattern: alphanumeric, underscores, dashes only
_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


def _validate_identifier(identifier: str, name: str) -> None:
    """Validate identifier to prevent path traversal attacks.

    Args:
        identifier: The identifier to validate (channel_id or project_id)
        name: Human-readable name for error messages

    Raises:
        ValueError: If identifier is invalid or contains path traversal sequences
    """
    if not identifier:
        raise ValueError(f"{name} cannot be empty")

    if not _ID_PATTERN.match(identifier):
        raise ValueError(
            f"Invalid {name}: '{identifier}'. "
            f"Only alphanumeric characters, underscores, and dashes are allowed."
        )


def _verify_path_in_workspace(path: Path) -> None:
    """Verify that resolved path stays within WORKSPACE_ROOT.

    This prevents path traversal attacks where malicious identifiers
    could escape the workspace directory.

    Args:
        path: The path to verify

    Raises:
        ValueError: If resolved path escapes WORKSPACE_ROOT
    """
    resolved = path.resolve()
    workspace_resolved = WORKSPACE_ROOT.resolve()

    if not resolved.is_relative_to(workspace_resolved):
        raise ValueError(
            f"Path traversal detected: resolved path '{resolved}' "
            f"is outside workspace '{workspace_resolved}'"
        )


def get_channel_workspace(channel_id: str) -> Path:
    """Get workspace directory for a specific channel.

    Creates the directory if it doesn't exist.

    Security:
        Validates channel_id to prevent path traversal attacks.
        Only alphanumeric characters, underscores, and dashes allowed.

    Args:
        channel_id: Channel identifier (e.g., "poke1", "poke2")

    Returns:
        Path to channel workspace: /app/workspace/channels/{channel_id}/

    Raises:
        ValueError: If channel_id is invalid or contains path traversal sequences

    Example:
        >>> path = get_channel_workspace("poke1")
        >>> print(path)
        /app/workspace/channels/poke1
        >>> assert path.exists()
    """
    _validate_identifier(channel_id, "channel_id")

    path = WORKSPACE_ROOT / CHANNEL_DIR_NAME / channel_id
    _verify_path_in_workspace(path)

    path.mkdir(parents=True, exist_ok=True)
    return path


def get_project_dir(channel_id: str, project_id: str) -> Path:
    """Get project directory within channel workspace.

    Creates the directory if it doesn't exist.

    Security:
        Validates both channel_id and project_id to prevent path traversal.

    Args:
        channel_id: Channel identifier
        project_id: Project/task identifier (e.g., UUID from database)

    Returns:
        Path to project directory: /app/workspace/channels/{channel_id}/projects/{project_id}/

    Raises:
        ValueError: If channel_id or project_id is invalid

    Example:
        >>> path = get_project_dir("poke1", "vid_abc123")
        >>> print(path)
        /app/workspace/channels/poke1/projects/vid_abc123
    """
    _validate_identifier(project_id, "project_id")

    path = get_channel_workspace(channel_id) / PROJECT_DIR_NAME / project_id
    _verify_path_in_workspace(path)

    path.mkdir(parents=True, exist_ok=True)
    return path


def get_asset_dir(channel_id: str, project_id: str) -> Path:
    """Get assets directory for a project.

    Creates the directory if it doesn't exist.

    Args:
        channel_id: Channel identifier
        project_id: Project/task identifier

    Returns:
        Path to assets directory: .../projects/{project_id}/assets/

    Raises:
        ValueError: If channel_id or project_id is invalid

    Example:
        >>> path = get_asset_dir("poke1", "vid_abc123")
        >>> print(path)
        /app/workspace/channels/poke1/projects/vid_abc123/assets
    """
    path = get_project_dir(channel_id, project_id) / ASSET_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_character_dir(channel_id: str, project_id: str) -> Path:
    """Get character assets subdirectory.

    Creates the directory if it doesn't exist.

    Args:
        channel_id: Channel identifier
        project_id: Project/task identifier

    Returns:
        Path to character assets directory: .../assets/characters/

    Raises:
        ValueError: If channel_id or project_id is invalid

    Example:
        >>> path = get_character_dir("poke1", "vid_abc123")
        >>> print(path)
        /app/workspace/channels/poke1/projects/vid_abc123/assets/characters
    """
    path = get_asset_dir(channel_id, project_id) / CHARACTER_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_environment_dir(channel_id: str, project_id: str) -> Path:
    """Get environment assets subdirectory.

    Creates the directory if it doesn't exist.

    Args:
        channel_id: Channel identifier
        project_id: Project/task identifier

    Returns:
        Path to environment assets directory: .../assets/environments/

    Raises:
        ValueError: If channel_id or project_id is invalid

    Example:
        >>> path = get_environment_dir("poke1", "vid_abc123")
        >>> print(path)
        /app/workspace/channels/poke1/projects/vid_abc123/assets/environments
    """
    path = get_asset_dir(channel_id, project_id) / ENVIRONMENT_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_props_dir(channel_id: str, project_id: str) -> Path:
    """Get props assets subdirectory.

    Creates the directory if it doesn't exist.

    Args:
        channel_id: Channel identifier
        project_id: Project/task identifier

    Returns:
        Path to props assets directory: .../assets/props/

    Raises:
        ValueError: If channel_id or project_id is invalid

    Example:
        >>> path = get_props_dir("poke1", "vid_abc123")
        >>> print(path)
        /app/workspace/channels/poke1/projects/vid_abc123/assets/props
    """
    path = get_asset_dir(channel_id, project_id) / PROPS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_composite_dir(channel_id: str, project_id: str) -> Path:
    """Get composite images subdirectory.

    Creates the directory if it doesn't exist.

    Args:
        channel_id: Channel identifier
        project_id: Project/task identifier

    Returns:
        Path to composite images directory: .../assets/composites/

    Raises:
        ValueError: If channel_id or project_id is invalid

    Example:
        >>> path = get_composite_dir("poke1", "vid_abc123")
        >>> print(path)
        /app/workspace/channels/poke1/projects/vid_abc123/assets/composites
    """
    path = get_asset_dir(channel_id, project_id) / COMPOSITE_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_video_dir(channel_id: str, project_id: str) -> Path:
    """Get videos directory.

    Creates the directory if it doesn't exist.

    Args:
        channel_id: Channel identifier
        project_id: Project/task identifier

    Returns:
        Path to videos directory: .../projects/{project_id}/videos/

    Raises:
        ValueError: If channel_id or project_id is invalid

    Example:
        >>> path = get_video_dir("poke1", "vid_abc123")
        >>> print(path)
        /app/workspace/channels/poke1/projects/vid_abc123/videos
    """
    path = get_project_dir(channel_id, project_id) / VIDEO_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_audio_dir(channel_id: str, project_id: str) -> Path:
    """Get audio directory.

    Creates the directory if it doesn't exist.

    Args:
        channel_id: Channel identifier
        project_id: Project/task identifier

    Returns:
        Path to audio directory: .../projects/{project_id}/audio/

    Raises:
        ValueError: If channel_id or project_id is invalid

    Example:
        >>> path = get_audio_dir("poke1", "vid_abc123")
        >>> print(path)
        /app/workspace/channels/poke1/projects/vid_abc123/audio
    """
    path = get_project_dir(channel_id, project_id) / AUDIO_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_sfx_dir(channel_id: str, project_id: str) -> Path:
    """Get sound effects directory.

    Creates the directory if it doesn't exist.

    Args:
        channel_id: Channel identifier
        project_id: Project/task identifier

    Returns:
        Path to sound effects directory: .../projects/{project_id}/sfx/

    Raises:
        ValueError: If channel_id or project_id is invalid

    Example:
        >>> path = get_sfx_dir("poke1", "vid_abc123")
        >>> print(path)
        /app/workspace/channels/poke1/projects/vid_abc123/sfx
    """
    path = get_project_dir(channel_id, project_id) / SFX_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path
