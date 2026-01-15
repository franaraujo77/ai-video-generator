"""
Unit tests for app/utils/filesystem.py path helpers.

Tests verify:
- Directory auto-creation (parents=True, exist_ok=True)
- Path object return types (pathlib.Path)
- Multi-channel isolation (no cross-channel interference)
- String conversion for CLI scripts
- Idempotent directory creation
- Correct subdirectory structure
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from app.utils.filesystem import (
    WORKSPACE_ROOT,
    CHANNEL_DIR_NAME,
    PROJECT_DIR_NAME,
    ASSET_DIR_NAME,
    VIDEO_DIR_NAME,
    AUDIO_DIR_NAME,
    SFX_DIR_NAME,
    CHARACTER_DIR_NAME,
    ENVIRONMENT_DIR_NAME,
    PROPS_DIR_NAME,
    COMPOSITE_DIR_NAME,
    get_channel_workspace,
    get_project_dir,
    get_asset_dir,
    get_character_dir,
    get_environment_dir,
    get_props_dir,
    get_composite_dir,
    get_video_dir,
    get_audio_dir,
    get_sfx_dir,
)


@pytest.fixture
def mock_workspace_root(tmp_path, monkeypatch):
    """Mock WORKSPACE_ROOT to use temporary directory for testing."""
    monkeypatch.setattr("app.utils.filesystem.WORKSPACE_ROOT", tmp_path)
    return tmp_path


class TestConstants:
    """Test that constants match expected values."""

    def test_constants_match_expected_names(self):
        """Test that all directory name constants are correct."""
        assert CHANNEL_DIR_NAME == "channels"
        assert PROJECT_DIR_NAME == "projects"
        assert ASSET_DIR_NAME == "assets"
        assert VIDEO_DIR_NAME == "videos"
        assert AUDIO_DIR_NAME == "audio"
        assert SFX_DIR_NAME == "sfx"
        assert CHARACTER_DIR_NAME == "characters"
        assert ENVIRONMENT_DIR_NAME == "environments"
        assert PROPS_DIR_NAME == "props"
        assert COMPOSITE_DIR_NAME == "composites"


class TestChannelWorkspace:
    """Test get_channel_workspace() function."""

    def test_get_channel_workspace_creates_directory(self, mock_workspace_root):
        """Test that channel workspace directory is created when it doesn't exist."""
        channel_id = "poke1"

        path = get_channel_workspace(channel_id)

        assert path.exists()
        assert path.is_dir()
        assert str(path) == f"{mock_workspace_root}/channels/poke1"

    def test_get_channel_workspace_returns_path_object(self, mock_workspace_root):
        """Test that function returns pathlib.Path object."""
        channel_id = "poke1"

        path = get_channel_workspace(channel_id)

        assert isinstance(path, Path)

    def test_get_channel_workspace_idempotent(self, mock_workspace_root):
        """Test that calling function multiple times returns same path."""
        channel_id = "poke1"

        path1 = get_channel_workspace(channel_id)
        path2 = get_channel_workspace(channel_id)

        assert path1 == path2
        assert path1.exists()


class TestProjectDir:
    """Test get_project_dir() function."""

    def test_get_project_dir_creates_nested_structure(self, mock_workspace_root):
        """Test that nested directory structure is created."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        path = get_project_dir(channel_id, project_id)

        assert path.exists()
        assert path.is_dir()
        assert str(path) == f"{mock_workspace_root}/channels/poke1/projects/vid_abc123"

        # Verify parent directories were created
        assert (mock_workspace_root / "channels" / "poke1").exists()
        assert (mock_workspace_root / "channels" / "poke1" / "projects").exists()


class TestAssetDir:
    """Test get_asset_dir() function."""

    def test_get_asset_dir_returns_path_object(self, mock_workspace_root):
        """Test that function returns pathlib.Path object."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        path = get_asset_dir(channel_id, project_id)

        assert isinstance(path, Path)

    def test_get_asset_dir_creates_directory(self, mock_workspace_root):
        """Test that asset directory is created with correct structure."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        asset_dir = get_asset_dir(channel_id, project_id)

        assert asset_dir.exists()
        assert asset_dir.is_dir()
        assert str(asset_dir) == f"{mock_workspace_root}/channels/poke1/projects/vid_abc123/assets"

    def test_path_object_slash_operator(self, mock_workspace_root):
        """Test that Path object can use / operator to construct file paths."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        asset_dir = get_asset_dir(channel_id, project_id)
        file_path = asset_dir / "test_file.png"

        assert isinstance(file_path, Path)
        assert str(file_path).endswith("assets/test_file.png")


class TestSpecializedAssetSubdirectories:
    """Test specialized asset subdirectory helper functions."""

    def test_get_character_dir_creates_subdirectory(self, mock_workspace_root):
        """Test that character subdirectory is created under assets."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        character_dir = get_character_dir(channel_id, project_id)

        assert character_dir.exists()
        assert character_dir.is_dir()
        assert character_dir.name == "characters"
        assert character_dir.parent.name == "assets"

    def test_get_environment_dir_creates_subdirectory(self, mock_workspace_root):
        """Test that environment subdirectory is created under assets."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        environment_dir = get_environment_dir(channel_id, project_id)

        assert environment_dir.exists()
        assert environment_dir.is_dir()
        assert environment_dir.name == "environments"
        assert environment_dir.parent.name == "assets"

    def test_get_props_dir_creates_subdirectory(self, mock_workspace_root):
        """Test that props subdirectory is created under assets."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        props_dir = get_props_dir(channel_id, project_id)

        assert props_dir.exists()
        assert props_dir.is_dir()
        assert props_dir.name == "props"
        assert props_dir.parent.name == "assets"

    def test_get_composite_dir_creates_subdirectory(self, mock_workspace_root):
        """Test that composite subdirectory is created under assets."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        composite_dir = get_composite_dir(channel_id, project_id)

        assert composite_dir.exists()
        assert composite_dir.is_dir()
        assert composite_dir.name == "composites"
        assert composite_dir.parent.name == "assets"


class TestVideoAudioSfxDirs:
    """Test get_video_dir(), get_audio_dir(), get_sfx_dir() functions."""

    def test_get_video_dir_creates_directory(self, mock_workspace_root):
        """Test that video directory is created at correct location."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        video_dir = get_video_dir(channel_id, project_id)

        assert video_dir.exists()
        assert video_dir.is_dir()
        assert str(video_dir) == f"{mock_workspace_root}/channels/poke1/projects/vid_abc123/videos"

    def test_get_audio_dir_creates_directory(self, mock_workspace_root):
        """Test that audio directory is created at correct location."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        audio_dir = get_audio_dir(channel_id, project_id)

        assert audio_dir.exists()
        assert audio_dir.is_dir()
        assert str(audio_dir) == f"{mock_workspace_root}/channels/poke1/projects/vid_abc123/audio"

    def test_get_sfx_dir_creates_directory(self, mock_workspace_root):
        """Test that sfx directory is created at correct location."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        sfx_dir = get_sfx_dir(channel_id, project_id)

        assert sfx_dir.exists()
        assert sfx_dir.is_dir()
        assert str(sfx_dir) == f"{mock_workspace_root}/channels/poke1/projects/vid_abc123/sfx"


class TestMultiChannelIsolation:
    """Test that different channels have completely isolated storage."""

    def test_multi_channel_isolation(self, mock_workspace_root):
        """Test that paths for different channels are completely isolated."""
        project_id = "vid_123"

        path1 = get_asset_dir("poke1", project_id)
        path2 = get_asset_dir("poke2", project_id)

        # Paths should be different
        assert path1 != path2

        # Each path should contain its channel ID
        assert "poke1" in str(path1)
        assert "poke2" in str(path2)

        # Both directories should exist
        assert path1.exists()
        assert path2.exists()

    def test_same_project_id_different_channels(self, mock_workspace_root):
        """Test that same project_id in different channels creates separate paths."""
        channel1 = "poke1"
        channel2 = "poke2"
        project_id = "vid_same123"

        video_dir1 = get_video_dir(channel1, project_id)
        video_dir2 = get_video_dir(channel2, project_id)

        assert video_dir1 != video_dir2
        assert f"channels/{channel1}" in str(video_dir1)
        assert f"channels/{channel2}" in str(video_dir2)


class TestPathStringConversion:
    """Test that paths can be converted to strings for CLI scripts."""

    def test_path_string_conversion_for_cli(self, mock_workspace_root):
        """Test that Path objects can be cleanly converted to strings."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        path = get_asset_dir(channel_id, project_id)
        path_string = str(path)

        assert isinstance(path_string, str)
        assert path_string.endswith("channels/poke1/projects/vid_abc123/assets")

    def test_path_conversion_with_file_name(self, mock_workspace_root):
        """Test that file paths can be constructed and converted to strings."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        asset_dir = get_asset_dir(channel_id, project_id)
        file_path = asset_dir / "characters" / "bulbasaur.png"
        file_string = str(file_path)

        assert isinstance(file_string, str)
        assert file_string.endswith("assets/characters/bulbasaur.png")


class TestIdempotentDirectoryCreation:
    """Test that repeated calls are idempotent and don't raise errors."""

    def test_idempotent_directory_creation(self, mock_workspace_root):
        """Test that calling helper twice doesn't raise error."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        # First call
        path1 = get_asset_dir(channel_id, project_id)

        # Second call (should not raise error)
        path2 = get_asset_dir(channel_id, project_id)

        assert path1 == path2
        assert path1.exists()
        assert path2.exists()

    def test_multiple_calls_same_directory(self, mock_workspace_root):
        """Test that multiple calls to same helper are safe."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        paths = [get_character_dir(channel_id, project_id) for _ in range(5)]

        # All paths should be identical
        assert len(set(paths)) == 1

        # Directory should exist and be accessible
        assert paths[0].exists()
        assert paths[0].is_dir()


class TestCompleteDirectoryStructure:
    """Test that complete directory structure is created correctly."""

    def test_complete_structure_for_single_project(self, mock_workspace_root):
        """Test that calling all helpers creates expected directory structure."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        # Call all helper functions
        get_character_dir(channel_id, project_id)
        get_environment_dir(channel_id, project_id)
        get_props_dir(channel_id, project_id)
        get_composite_dir(channel_id, project_id)
        get_video_dir(channel_id, project_id)
        get_audio_dir(channel_id, project_id)
        get_sfx_dir(channel_id, project_id)

        # Verify complete structure exists
        base_path = mock_workspace_root / "channels" / channel_id / "projects" / project_id

        assert (base_path / "assets" / "characters").exists()
        assert (base_path / "assets" / "environments").exists()
        assert (base_path / "assets" / "props").exists()
        assert (base_path / "assets" / "composites").exists()
        assert (base_path / "videos").exists()
        assert (base_path / "audio").exists()
        assert (base_path / "sfx").exists()


class TestSecurityValidation:
    """Test security validation and path traversal prevention."""

    def test_channel_id_path_traversal_blocked(self, mock_workspace_root):
        """Test that path traversal sequences in channel_id are rejected."""
        malicious_channel_ids = [
            "../../../etc",
            "../../..",
            "../etc/passwd",
            "..\\..\\windows",
            "poke1/../../../etc",
        ]

        for malicious_id in malicious_channel_ids:
            with pytest.raises(ValueError, match="Invalid channel_id"):
                get_channel_workspace(malicious_id)

    def test_project_id_path_traversal_blocked(self, mock_workspace_root):
        """Test that path traversal sequences in project_id are rejected."""
        channel_id = "poke1"
        malicious_project_ids = [
            "../../../etc",
            "../../secrets",
            "../config",
        ]

        for malicious_id in malicious_project_ids:
            with pytest.raises(ValueError, match="Invalid project_id"):
                get_project_dir(channel_id, malicious_id)

    def test_channel_id_special_characters_rejected(self, mock_workspace_root):
        """Test that special characters in channel_id are rejected."""
        invalid_channel_ids = [
            "poke1/malicious",
            "poke1;rm -rf",
            "poke1 && cat /etc/passwd",
            "poke1|whoami",
            "poke1`pwd`",
            "poke1$(whoami)",
            "poke1\x00nullbyte",
            "poke1 spaces not allowed",
            "poke1@email.com",
            "poke1#hash",
            "poke1%percent",
        ]

        for invalid_id in invalid_channel_ids:
            with pytest.raises(ValueError, match="Invalid channel_id"):
                get_channel_workspace(invalid_id)

    def test_project_id_special_characters_rejected(self, mock_workspace_root):
        """Test that special characters in project_id are rejected."""
        channel_id = "poke1"
        invalid_project_ids = [
            "vid/malicious",
            "vid;whoami",
            "vid && ls",
            "vid|cat",
            "vid with spaces",
            "vid@test",
        ]

        for invalid_id in invalid_project_ids:
            with pytest.raises(ValueError, match="Invalid project_id"):
                get_project_dir(channel_id, invalid_id)

    def test_empty_channel_id_rejected(self, mock_workspace_root):
        """Test that empty channel_id is rejected."""
        with pytest.raises(ValueError, match="channel_id cannot be empty"):
            get_channel_workspace("")

    def test_empty_project_id_rejected(self, mock_workspace_root):
        """Test that empty project_id is rejected."""
        with pytest.raises(ValueError, match="project_id cannot be empty"):
            get_project_dir("poke1", "")

    def test_valid_identifiers_accepted(self, mock_workspace_root):
        """Test that valid alphanumeric identifiers with dashes/underscores are accepted."""
        valid_channel_ids = [
            "poke1",
            "poke-2",
            "poke_3",
            "POKE4",
            "poke-channel-1",
            "poke_channel_2",
            "123channel",
        ]

        for valid_id in valid_channel_ids:
            path = get_channel_workspace(valid_id)
            assert path.exists()
            assert valid_id in str(path)

    def test_resolved_path_stays_within_workspace(self, mock_workspace_root):
        """Test that resolved paths are verified to stay within workspace."""
        channel_id = "poke1"
        project_id = "vid_abc123"

        # Create paths
        channel_path = get_channel_workspace(channel_id)
        project_path = get_project_dir(channel_id, project_id)
        asset_path = get_asset_dir(channel_id, project_id)

        # Verify all resolved paths are within workspace
        workspace_resolved = mock_workspace_root.resolve()

        assert channel_path.resolve().is_relative_to(workspace_resolved)
        assert project_path.resolve().is_relative_to(workspace_resolved)
        assert asset_path.resolve().is_relative_to(workspace_resolved)

    def test_symlink_detection_in_identifier(self, mock_workspace_root):
        """Test that symbolic link components in identifiers are rejected."""
        # Identifiers with path components that could be symlinks
        suspicious_ids = [
            "poke1/../../etc",
            "./poke1",
            "poke1/.",
            "poke1/..",
        ]

        for suspicious_id in suspicious_ids:
            with pytest.raises(ValueError, match="Invalid channel_id"):
                get_channel_workspace(suspicious_id)

    def test_multi_channel_security_isolation(self, mock_workspace_root):
        """Test that channels cannot access each other's directories via traversal."""
        channel1 = "poke1"
        channel2 = "poke2"
        project_id = "vid_123"

        # Create legitimate paths for both channels
        path1 = get_asset_dir(channel1, project_id)
        path2 = get_asset_dir(channel2, project_id)

        # Verify paths are different and isolated
        assert path1 != path2
        assert channel1 in str(path1)
        assert channel2 in str(path2)

        # Verify neither path can reference the other channel
        assert channel2 not in str(path1)
        assert channel1 not in str(path2)
