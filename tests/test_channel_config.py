"""Tests for channel configuration schema and loader.

This module tests:
- Pydantic schema validation (ChannelConfigSchema)
- YAML file loading
- Config directory scanning
- ConfigManager singleton with reload support
"""

import pytest
from decimal import Decimal
from pathlib import Path
from pydantic import ValidationError

from app.schemas.channel_config import ChannelConfigSchema
from app.services.channel_config_loader import (
    ChannelConfigLoader,
    ConfigManager,
)


class TestChannelConfigSchema:
    """Tests for Pydantic schema validation."""

    def test_valid_config_all_fields(self):
        """Test valid config with all fields provided."""
        config = ChannelConfigSchema(
            channel_id="pokemon_nature",
            channel_name="Pokemon Nature Docs",
            notion_database_id="abc123def456",
            priority="high",
            is_active=False,
            voice_id="voice123",
            storage_strategy="r2",
            max_concurrent=5,
            budget_daily_usd=Decimal("50.00"),
        )

        assert config.channel_id == "pokemon_nature"
        assert config.channel_name == "Pokemon Nature Docs"
        assert config.notion_database_id == "abc123def456"
        assert config.priority == "high"
        assert config.is_active is False
        assert config.voice_id == "voice123"
        assert config.storage_strategy == "r2"
        assert config.max_concurrent == 5
        assert config.budget_daily_usd == Decimal("50.00")

    def test_valid_config_required_only(self):
        """Test valid config with only required fields (defaults applied)."""
        config = ChannelConfigSchema(
            channel_id="poke1",
            channel_name="Test Channel",
            notion_database_id="db-123",
        )

        assert config.channel_id == "poke1"
        assert config.channel_name == "Test Channel"
        assert config.notion_database_id == "db-123"
        # Check defaults
        assert config.priority == "normal"
        assert config.is_active is True
        assert config.voice_id is None
        assert config.storage_strategy == "notion"
        assert config.max_concurrent == 2
        assert config.budget_daily_usd is None

    def test_missing_channel_id(self):
        """Test that missing channel_id raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_name="Test Channel",
                notion_database_id="db-123",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("channel_id",) for e in errors)

    def test_missing_channel_name(self):
        """Test that missing channel_name raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="poke1",
                notion_database_id="db-123",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("channel_name",) for e in errors)

    def test_missing_notion_database_id(self):
        """Test that missing notion_database_id raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="poke1",
                channel_name="Test Channel",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("notion_database_id",) for e in errors)

    def test_invalid_channel_id_format_special_chars(self):
        """Test that special characters in channel_id are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="poke-1",  # Hyphen not allowed
                channel_name="Test Channel",
                notion_database_id="db-123",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("channel_id",) for e in errors)

    def test_invalid_channel_id_format_spaces(self):
        """Test that spaces in channel_id are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="poke 1",  # Space not allowed
                channel_name="Test Channel",
                notion_database_id="db-123",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("channel_id",) for e in errors)

    def test_channel_id_too_long(self):
        """Test that channel_id > 50 chars is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="a" * 51,  # 51 chars
                channel_name="Test Channel",
                notion_database_id="db-123",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("channel_id",) for e in errors)

    def test_channel_id_normalized_lowercase(self):
        """Test that channel_id is normalized to lowercase."""
        config = ChannelConfigSchema(
            channel_id="PokeChannel1",
            channel_name="Test Channel",
            notion_database_id="db-123",
        )

        assert config.channel_id == "pokechannel1"

    def test_invalid_priority_value(self):
        """Test that invalid priority values are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="poke1",
                channel_name="Test Channel",
                notion_database_id="db-123",
                priority="urgent",  # Invalid - only high/normal/low
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("priority",) for e in errors)

    def test_priority_normalized_lowercase(self):
        """Test that priority is normalized to lowercase."""
        config = ChannelConfigSchema(
            channel_id="poke1",
            channel_name="Test Channel",
            notion_database_id="db-123",
            priority="HIGH",
        )

        assert config.priority == "high"

    def test_invalid_storage_strategy_value(self):
        """Test that invalid storage_strategy values are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="poke1",
                channel_name="Test Channel",
                notion_database_id="db-123",
                storage_strategy="s3",  # Invalid - only notion/r2
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("storage_strategy",) for e in errors)

    def test_storage_strategy_normalized_lowercase(self):
        """Test that storage_strategy is normalized to lowercase."""
        config = ChannelConfigSchema(
            channel_id="poke1",
            channel_name="Test Channel",
            notion_database_id="db-123",
            storage_strategy="R2",
        )

        assert config.storage_strategy == "r2"

    def test_max_concurrent_below_min(self):
        """Test that max_concurrent < 1 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="poke1",
                channel_name="Test Channel",
                notion_database_id="db-123",
                max_concurrent=0,
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("max_concurrent",) for e in errors)

    def test_max_concurrent_above_max(self):
        """Test that max_concurrent > 10 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="poke1",
                channel_name="Test Channel",
                notion_database_id="db-123",
                max_concurrent=11,
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("max_concurrent",) for e in errors)

    def test_budget_negative_value(self):
        """Test that negative budget_daily_usd is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="poke1",
                channel_name="Test Channel",
                notion_database_id="db-123",
                budget_daily_usd=Decimal("-10.00"),
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("budget_daily_usd",) for e in errors)

    def test_whitespace_stripped(self):
        """Test that whitespace is stripped from string fields."""
        config = ChannelConfigSchema(
            channel_id="  poke1  ",
            channel_name="  Test Channel  ",
            notion_database_id="  db-123  ",
        )

        assert config.channel_id == "poke1"
        assert config.channel_name == "Test Channel"
        assert config.notion_database_id == "db-123"

    def test_empty_channel_id_rejected(self):
        """Test that empty channel_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="",
                channel_name="Test Channel",
                notion_database_id="db-123",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("channel_id",) for e in errors)

    def test_valid_channel_id_with_underscores(self):
        """Test that underscores in channel_id are allowed."""
        config = ChannelConfigSchema(
            channel_id="pokemon_nature_docs_1",
            channel_name="Test Channel",
            notion_database_id="db-123",
        )

        assert config.channel_id == "pokemon_nature_docs_1"

    def test_valid_channel_id_with_numbers(self):
        """Test that numbers in channel_id are allowed."""
        config = ChannelConfigSchema(
            channel_id="poke123",
            channel_name="Test Channel",
            notion_database_id="db-123",
        )

        assert config.channel_id == "poke123"


class TestChannelConfigLoader:
    """Tests for YAML file loading."""

    def test_load_valid_yaml(self, tmp_path: Path):
        """Test loading a valid YAML config file."""
        config_file = tmp_path / "poke1.yaml"
        config_file.write_text("""
channel_id: poke1
channel_name: "Pokemon Nature Docs"
notion_database_id: "abc123"
priority: high
is_active: true
""")

        loader = ChannelConfigLoader()
        config = loader.load_channel_config(config_file)

        assert config is not None
        assert config.channel_id == "poke1"
        assert config.channel_name == "Pokemon Nature Docs"
        assert config.notion_database_id == "abc123"
        assert config.priority == "high"
        assert config.is_active is True

    def test_load_valid_yaml_required_only(self, tmp_path: Path):
        """Test loading YAML with only required fields."""
        config_file = tmp_path / "poke2.yaml"
        config_file.write_text("""
channel_id: poke2
channel_name: "Test Channel"
notion_database_id: "def456"
""")

        loader = ChannelConfigLoader()
        config = loader.load_channel_config(config_file)

        assert config is not None
        assert config.channel_id == "poke2"
        # Defaults should be applied
        assert config.priority == "normal"
        assert config.is_active is True
        assert config.storage_strategy == "notion"

    def test_load_invalid_yaml_syntax(self, tmp_path: Path):
        """Test that invalid YAML syntax returns None."""
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text("""
channel_id: poke1
channel_name: "Test Channel
  invalid: yaml: syntax
""")

        loader = ChannelConfigLoader()
        config = loader.load_channel_config(config_file)

        assert config is None

    def test_load_empty_file(self, tmp_path: Path):
        """Test that empty YAML file returns None."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        loader = ChannelConfigLoader()
        config = loader.load_channel_config(config_file)

        assert config is None

    def test_load_missing_required_field(self, tmp_path: Path):
        """Test that missing required field returns None."""
        config_file = tmp_path / "missing.yaml"
        config_file.write_text("""
channel_id: poke1
# Missing channel_name and notion_database_id
""")

        loader = ChannelConfigLoader()
        config = loader.load_channel_config(config_file)

        assert config is None

    def test_load_missing_file(self, tmp_path: Path):
        """Test that non-existent file returns None."""
        config_file = tmp_path / "nonexistent.yaml"

        loader = ChannelConfigLoader()
        config = loader.load_channel_config(config_file)

        assert config is None

    def test_load_all_configs(self, tmp_path: Path):
        """Test loading all configs from a directory."""
        # Create valid config files
        (tmp_path / "poke1.yaml").write_text("""
channel_id: poke1
channel_name: "Channel 1"
notion_database_id: "db1"
""")
        (tmp_path / "poke2.yaml").write_text("""
channel_id: poke2
channel_name: "Channel 2"
notion_database_id: "db2"
""")
        # Create an invalid config file (should be skipped)
        (tmp_path / "invalid.yaml").write_text("""
channel_id: invalid
# Missing required fields
""")

        loader = ChannelConfigLoader()
        configs = loader.load_all_configs(tmp_path)

        # Should have 2 valid configs
        assert len(configs) == 2
        assert "poke1" in configs
        assert "poke2" in configs
        assert "invalid" not in configs

    def test_load_all_configs_empty_directory(self, tmp_path: Path):
        """Test loading configs from empty directory."""
        loader = ChannelConfigLoader()
        configs = loader.load_all_configs(tmp_path)

        assert configs == {}

    def test_load_all_configs_skips_non_yaml(self, tmp_path: Path):
        """Test that non-YAML files are skipped."""
        # Create a valid YAML file
        (tmp_path / "poke1.yaml").write_text("""
channel_id: poke1
channel_name: "Channel 1"
notion_database_id: "db1"
""")
        # Create a non-YAML file
        (tmp_path / "readme.txt").write_text("This is not a YAML file")
        (tmp_path / "config.json").write_text('{"not": "yaml"}')

        loader = ChannelConfigLoader()
        configs = loader.load_all_configs(tmp_path)

        assert len(configs) == 1
        assert "poke1" in configs

    def test_load_all_configs_skips_underscore_prefix(self, tmp_path: Path):
        """Test that files starting with underscore are skipped."""
        # Create a valid config
        (tmp_path / "poke1.yaml").write_text("""
channel_id: poke1
channel_name: "Channel 1"
notion_database_id: "db1"
""")
        # Create an example file with underscore prefix
        (tmp_path / "_example.yaml").write_text("""
channel_id: example
channel_name: "Example Channel"
notion_database_id: "db-example"
""")

        loader = ChannelConfigLoader()
        configs = loader.load_all_configs(tmp_path)

        # Should only load poke1, not _example
        assert len(configs) == 1
        assert "poke1" in configs
        assert "example" not in configs

    def test_load_all_configs_supports_yml_extension(self, tmp_path: Path):
        """Test that both .yaml and .yml extensions are supported."""
        # Create a .yaml config
        (tmp_path / "poke1.yaml").write_text("""
channel_id: poke1
channel_name: "Channel 1"
notion_database_id: "db1"
""")
        # Create a .yml config
        (tmp_path / "poke2.yml").write_text("""
channel_id: poke2
channel_name: "Channel 2"
notion_database_id: "db2"
""")

        loader = ChannelConfigLoader()
        configs = loader.load_all_configs(tmp_path)

        # Should load both .yaml and .yml files
        assert len(configs) == 2
        assert "poke1" in configs
        assert "poke2" in configs


class TestConfigManager:
    """Tests for config manager singleton."""

    @pytest.mark.asyncio
    async def test_reload_loads_configs(self, tmp_path: Path):
        """Test that reload loads configs from directory."""
        # Create a config file
        (tmp_path / "poke1.yaml").write_text("""
channel_id: poke1
channel_name: "Channel 1"
notion_database_id: "db1"
""")

        # Reset singleton for testing
        ConfigManager._instance = None
        manager = ConfigManager.get_instance(tmp_path)
        await manager.reload()

        configs = manager.get_all_configs()
        assert len(configs) == 1
        assert "poke1" in configs

    @pytest.mark.asyncio
    async def test_reload_detects_new_config(self, tmp_path: Path):
        """Test that reload detects newly added config files."""
        # Create initial config
        (tmp_path / "poke1.yaml").write_text("""
channel_id: poke1
channel_name: "Channel 1"
notion_database_id: "db1"
""")

        # Reset singleton for testing
        ConfigManager._instance = None
        manager = ConfigManager.get_instance(tmp_path)
        await manager.reload()

        assert len(manager.get_all_configs()) == 1

        # Add a new config file
        (tmp_path / "poke2.yaml").write_text("""
channel_id: poke2
channel_name: "Channel 2"
notion_database_id: "db2"
""")

        # Reload and check new config is detected
        await manager.reload()

        configs = manager.get_all_configs()
        assert len(configs) == 2
        assert "poke1" in configs
        assert "poke2" in configs

    @pytest.mark.asyncio
    async def test_get_config_returns_none_for_unknown(self, tmp_path: Path):
        """Test that get_config returns None for unknown channel."""
        ConfigManager._instance = None
        manager = ConfigManager.get_instance(tmp_path)
        await manager.reload()

        config = manager.get_config("nonexistent")
        assert config is None

    @pytest.mark.asyncio
    async def test_get_config_returns_config(self, tmp_path: Path):
        """Test that get_config returns correct config."""
        (tmp_path / "poke1.yaml").write_text("""
channel_id: poke1
channel_name: "Channel 1"
notion_database_id: "db1"
priority: high
""")

        ConfigManager._instance = None
        manager = ConfigManager.get_instance(tmp_path)
        await manager.reload()

        config = manager.get_config("poke1")
        assert config is not None
        assert config.channel_id == "poke1"
        assert config.priority == "high"

    @pytest.mark.asyncio
    async def test_singleton_returns_same_instance(self, tmp_path: Path):
        """Test that get_instance returns the same instance."""
        ConfigManager._instance = None
        manager1 = ConfigManager.get_instance(tmp_path)
        manager2 = ConfigManager.get_instance()

        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_get_all_configs_returns_copy(self, tmp_path: Path):
        """Test that get_all_configs returns a copy, not the original dict."""
        (tmp_path / "poke1.yaml").write_text("""
channel_id: poke1
channel_name: "Channel 1"
notion_database_id: "db1"
""")

        ConfigManager._instance = None
        manager = ConfigManager.get_instance(tmp_path)
        await manager.reload()

        configs1 = manager.get_all_configs()
        configs2 = manager.get_all_configs()

        # Should be equal but not the same object
        assert configs1 == configs2
        assert configs1 is not configs2

    @pytest.mark.asyncio
    async def test_reload_concurrent_safe(self, tmp_path: Path):
        """Test that concurrent reload calls are safe with asyncio.Lock."""
        import asyncio

        (tmp_path / "poke1.yaml").write_text("""
channel_id: poke1
channel_name: "Channel 1"
notion_database_id: "db1"
""")

        ConfigManager._instance = None
        manager = ConfigManager.get_instance(tmp_path)

        # Run multiple reloads concurrently
        await asyncio.gather(
            manager.reload(),
            manager.reload(),
            manager.reload(),
        )

        # Should still have correct configs
        configs = manager.get_all_configs()
        assert len(configs) == 1
        assert "poke1" in configs
