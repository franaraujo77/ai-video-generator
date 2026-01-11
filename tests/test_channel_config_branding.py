"""Tests for BrandingConfig schema and branding-related functionality.

This module tests:
- BrandingConfig Pydantic schema validation
- YAML with branding section parsing
- YAML without branding section uses defaults
- Invalid branding paths validation
- Branding path relative path requirement
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.channel_config import BrandingConfig, ChannelConfigSchema
from app.services.channel_config_loader import ChannelConfigLoader


class TestBrandingConfig:
    """Tests for BrandingConfig Pydantic schema."""

    def test_branding_all_fields(self):
        """Test BrandingConfig with all fields populated."""
        branding = BrandingConfig(
            intro_video="channel_assets/intro.mp4",
            outro_video="channel_assets/outro.mp4",
            watermark_image="channel_assets/watermark.png",
        )

        assert branding.intro_video == "channel_assets/intro.mp4"
        assert branding.outro_video == "channel_assets/outro.mp4"
        assert branding.watermark_image == "channel_assets/watermark.png"

    def test_branding_optional_fields(self):
        """Test BrandingConfig with optional fields as None."""
        branding = BrandingConfig(
            intro_video="intro.mp4",
            outro_video=None,
            watermark_image=None,
        )

        assert branding.intro_video == "intro.mp4"
        assert branding.outro_video is None
        assert branding.watermark_image is None

    def test_branding_all_none(self):
        """Test BrandingConfig with all fields None."""
        branding = BrandingConfig(
            intro_video=None,
            outro_video=None,
            watermark_image=None,
        )

        assert branding.intro_video is None
        assert branding.outro_video is None
        assert branding.watermark_image is None

    def test_branding_empty_string_becomes_none(self):
        """Test that empty strings are converted to None."""
        branding = BrandingConfig(
            intro_video="",
            outro_video="",
            watermark_image="",
        )

        assert branding.intro_video is None
        assert branding.outro_video is None
        assert branding.watermark_image is None

    def test_branding_absolute_path_rejected(self):
        """Test that absolute paths are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BrandingConfig(
                intro_video="/home/user/videos/intro.mp4",  # Absolute path
                outro_video=None,
                watermark_image=None,
            )

        errors = exc_info.value.errors()
        assert any("relative" in str(e).lower() or "absolute" in str(e).lower() for e in errors)

    def test_branding_windows_absolute_path_rejected(self):
        """Test that Windows-style absolute paths are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BrandingConfig(
                intro_video="C:\\Users\\video\\intro.mp4",  # Windows absolute
                outro_video=None,
                watermark_image=None,
            )

        errors = exc_info.value.errors()
        assert any("relative" in str(e).lower() or "absolute" in str(e).lower() for e in errors)

    def test_branding_path_traversal_rejected(self):
        """Test that path traversal attempts are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BrandingConfig(
                intro_video="../../../etc/passwd",  # Path traversal
                outro_video=None,
                watermark_image=None,
            )

        errors = exc_info.value.errors()
        assert any(".." in str(e) for e in errors)

    def test_branding_path_max_length(self):
        """Test that paths exceeding max length are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BrandingConfig(
                intro_video="x" * 300,  # Exceeds 255 char limit
                outro_video=None,
                watermark_image=None,
            )

        errors = exc_info.value.errors()
        assert len(errors) > 0

    def test_branding_valid_relative_paths(self):
        """Test various valid relative path formats."""
        valid_paths = [
            "intro.mp4",
            "assets/intro.mp4",
            "channel_assets/video/intro.mp4",
            "2024/01/intro_v2.mp4",
            "video_with_underscores.mp4",
            "video-with-dashes.mp4",
        ]

        for path in valid_paths:
            branding = BrandingConfig(
                intro_video=path,
                outro_video=None,
                watermark_image=None,
            )
            assert branding.intro_video == path

    def test_branding_repr(self):
        """Test BrandingConfig __repr__ output."""
        branding = BrandingConfig(
            intro_video="intro.mp4",
            outro_video="outro.mp4",
            watermark_image=None,
        )

        repr_str = repr(branding)
        assert "intro" in repr_str
        assert "outro" in repr_str
        # Watermark should not appear since it's None
        assert "watermark" not in repr_str.lower() or "None" not in repr_str


class TestChannelConfigSchemaBranding:
    """Tests for ChannelConfigSchema with branding section."""

    def test_config_with_branding(self):
        """Test ChannelConfigSchema with branding section."""
        config = ChannelConfigSchema(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            notion_database_id="db123",
            branding=BrandingConfig(
                intro_video="assets/intro.mp4",
                outro_video="assets/outro.mp4",
                watermark_image="assets/watermark.png",
            ),
        )

        assert config.branding is not None
        assert config.branding.intro_video == "assets/intro.mp4"
        assert config.branding.outro_video == "assets/outro.mp4"
        assert config.branding.watermark_image == "assets/watermark.png"

    def test_config_without_branding(self):
        """Test ChannelConfigSchema without branding defaults to None."""
        config = ChannelConfigSchema(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            notion_database_id="db123",
        )

        assert config.branding is None

    def test_config_with_voice_id(self):
        """Test ChannelConfigSchema with voice_id set."""
        config = ChannelConfigSchema(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            notion_database_id="db123",
            voice_id="21m00Tcm4TlvDq8ikWAM",
        )

        assert config.voice_id == "21m00Tcm4TlvDq8ikWAM"

    def test_config_voice_id_max_length(self):
        """Test voice_id max length validation."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="poke1",
                channel_name="Pokemon Channel",
                notion_database_id="db123",
                voice_id="x" * 101,  # Exceeds 100 char limit
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("voice_id",) for e in errors)

    def test_config_repr_shows_voice_id_presence(self):
        """Test __repr__ shows voice_id presence (not value)."""
        config_with_voice = ChannelConfigSchema(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            notion_database_id="db123",
            voice_id="secret_voice_id",
        )
        config_without_voice = ChannelConfigSchema(
            channel_id="poke2",
            channel_name="Pokemon Channel 2",
            notion_database_id="db456",
        )

        repr_with = repr(config_with_voice)
        repr_without = repr(config_without_voice)

        # Should show "set" or "not_set", NOT the actual value
        assert "voice_id=set" in repr_with
        assert "voice_id=not_set" in repr_without
        # Should NOT contain the actual voice ID value
        assert "secret_voice_id" not in repr_with

    def test_config_repr_shows_branding_status(self):
        """Test __repr__ shows branding configuration status."""
        config_with_branding = ChannelConfigSchema(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            notion_database_id="db123",
            branding=BrandingConfig(intro_video="intro.mp4"),
        )
        config_without_branding = ChannelConfigSchema(
            channel_id="poke2",
            channel_name="Pokemon Channel 2",
            notion_database_id="db456",
        )

        repr_with = repr(config_with_branding)
        repr_without = repr(config_without_branding)

        assert "branding=configured" in repr_with
        assert "branding=not_configured" in repr_without


class TestChannelConfigLoaderBranding:
    """Tests for ChannelConfigLoader with branding in YAML files."""

    def test_load_yaml_with_branding(self, tmp_path: Path):
        """Test loading YAML config with branding section."""
        config_file = tmp_path / "poke1.yaml"
        config_file.write_text("""
channel_id: poke1
channel_name: "Pokemon Nature Docs"
notion_database_id: "abc123"
voice_id: "voice_xyz123"
branding:
  intro_video: "channel_assets/intro_v2.mp4"
  outro_video: "channel_assets/outro_v2.mp4"
  watermark_image: "channel_assets/watermark.png"
""")

        loader = ChannelConfigLoader()
        config = loader.load_channel_config(config_file)

        assert config is not None
        assert config.voice_id == "voice_xyz123"
        assert config.branding is not None
        assert config.branding.intro_video == "channel_assets/intro_v2.mp4"
        assert config.branding.outro_video == "channel_assets/outro_v2.mp4"
        assert config.branding.watermark_image == "channel_assets/watermark.png"

    def test_load_yaml_with_partial_branding(self, tmp_path: Path):
        """Test loading YAML config with partial branding (only some fields)."""
        config_file = tmp_path / "poke1.yaml"
        config_file.write_text("""
channel_id: poke1
channel_name: "Pokemon Nature Docs"
notion_database_id: "abc123"
branding:
  intro_video: "channel_assets/intro.mp4"
  # No outro or watermark
""")

        loader = ChannelConfigLoader()
        config = loader.load_channel_config(config_file)

        assert config is not None
        assert config.branding is not None
        assert config.branding.intro_video == "channel_assets/intro.mp4"
        assert config.branding.outro_video is None
        assert config.branding.watermark_image is None

    def test_load_yaml_without_branding(self, tmp_path: Path):
        """Test loading YAML config without branding section uses None."""
        config_file = tmp_path / "poke1.yaml"
        config_file.write_text("""
channel_id: poke1
channel_name: "Pokemon Nature Docs"
notion_database_id: "abc123"
""")

        loader = ChannelConfigLoader()
        config = loader.load_channel_config(config_file)

        assert config is not None
        assert config.branding is None

    def test_load_yaml_with_invalid_branding_path(self, tmp_path: Path):
        """Test that invalid branding paths cause validation error."""
        config_file = tmp_path / "poke1.yaml"
        config_file.write_text("""
channel_id: poke1
channel_name: "Pokemon Nature Docs"
notion_database_id: "abc123"
branding:
  intro_video: "/absolute/path/intro.mp4"
""")

        loader = ChannelConfigLoader()
        config = loader.load_channel_config(config_file)

        # Should return None due to validation error
        assert config is None

    def test_validate_branding_files_exists(self, tmp_path: Path):
        """Test validate_branding_files with existing files."""
        # Create branding files
        assets_dir = tmp_path / "channel_assets"
        assets_dir.mkdir()
        (assets_dir / "intro.mp4").touch()
        (assets_dir / "outro.mp4").touch()
        (assets_dir / "watermark.png").touch()

        config = ChannelConfigSchema(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            notion_database_id="db123",
            branding=BrandingConfig(
                intro_video="channel_assets/intro.mp4",
                outro_video="channel_assets/outro.mp4",
                watermark_image="channel_assets/watermark.png",
            ),
        )

        loader = ChannelConfigLoader(workspace_root=tmp_path)
        warnings = loader.validate_branding_files(config)

        assert warnings == []

    def test_validate_branding_files_missing(self, tmp_path: Path):
        """Test validate_branding_files with missing files."""
        config = ChannelConfigSchema(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            notion_database_id="db123",
            branding=BrandingConfig(
                intro_video="channel_assets/intro.mp4",
                outro_video="channel_assets/outro.mp4",
                watermark_image=None,
            ),
        )

        loader = ChannelConfigLoader(workspace_root=tmp_path)
        warnings = loader.validate_branding_files(config)

        assert len(warnings) == 2  # intro and outro missing
        assert any("intro" in w.lower() for w in warnings)
        assert any("outro" in w.lower() for w in warnings)

    def test_validate_branding_files_no_branding(self, tmp_path: Path):
        """Test validate_branding_files with no branding configured."""
        config = ChannelConfigSchema(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            notion_database_id="db123",
        )

        loader = ChannelConfigLoader(workspace_root=tmp_path)
        warnings = loader.validate_branding_files(config)

        assert warnings == []

    def test_validate_branding_files_no_workspace(self):
        """Test validate_branding_files without workspace root returns empty."""
        config = ChannelConfigSchema(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            notion_database_id="db123",
            branding=BrandingConfig(
                intro_video="channel_assets/intro.mp4",
            ),
        )

        loader = ChannelConfigLoader()  # No workspace_root
        warnings = loader.validate_branding_files(config)

        # Should return empty without workspace to check
        assert warnings == []
