"""Channel configuration loader from YAML files.

This module provides the ChannelConfigLoader class for loading channel
configurations from YAML files, and the ConfigManager singleton for
managing loaded configurations with hot reload support.
"""

import asyncio
from pathlib import Path

import structlog
import yaml
from pydantic import ValidationError

from app.schemas.channel_config import ChannelConfigSchema

log = structlog.get_logger()


class ChannelConfigLoader:
    """Loads and validates channel configurations from YAML files.

    This class handles loading individual YAML files and scanning directories
    for channel configurations. Invalid files are logged and skipped.
    """

    def load_channel_config(self, file_path: Path) -> ChannelConfigSchema | None:
        """Load and validate channel config from YAML file.

        Args:
            file_path: Path to YAML configuration file.

        Returns:
            Validated ChannelConfigSchema or None if invalid/missing.
        """
        if not file_path.exists():
            log.warning("config_file_not_found", file=str(file_path))
            return None

        try:
            with file_path.open("r", encoding="utf-8") as f:
                raw_config = yaml.safe_load(f)

            if raw_config is None:
                log.warning("config_file_empty", file=str(file_path))
                return None

            config = ChannelConfigSchema.model_validate(raw_config)
            log.info("config_loaded", channel_id=config.channel_id, file=str(file_path))
            return config

        except yaml.YAMLError as e:
            # Extract line number if available
            line_num = None
            if hasattr(e, "problem_mark") and e.problem_mark is not None:
                line_num = e.problem_mark.line

            log.error(
                "yaml_parse_error",
                file=str(file_path),
                error=str(e),
                line=line_num,
            )
            return None

        except ValidationError as e:
            log.error(
                "config_validation_error",
                file=str(file_path),
                errors=e.errors(),
            )
            return None

        except Exception as e:
            log.error(
                "config_load_error",
                file=str(file_path),
                error=str(e),
            )
            return None

    def load_all_configs(self, config_dir: Path) -> dict[str, ChannelConfigSchema]:
        """Load all channel configs from a directory.

        Scans the directory for *.yaml and *.yml files and loads each one.
        Files starting with underscore are skipped (e.g., _example.yaml).
        Invalid files are logged and skipped.

        Args:
            config_dir: Directory containing YAML config files.

        Returns:
            Dictionary mapping channel_id to ChannelConfigSchema.
        """
        configs: dict[str, ChannelConfigSchema] = {}
        loaded_count = 0
        skipped_count = 0

        if not config_dir.exists():
            log.warning("config_directory_not_found", directory=str(config_dir))
            return configs

        # Support both .yaml and .yml extensions
        yaml_files = list(config_dir.glob("*.yaml")) + list(config_dir.glob("*.yml"))
        for file_path in yaml_files:
            # Skip files starting with underscore (e.g., _example.yaml)
            if file_path.name.startswith("_"):
                log.debug("skipping_example_file", file=str(file_path))
                continue

            config = self.load_channel_config(file_path)
            if config is not None:
                configs[config.channel_id] = config
                loaded_count += 1
            else:
                skipped_count += 1

        log.info(
            "configs_scan_complete",
            directory=str(config_dir),
            loaded=loaded_count,
            skipped=skipped_count,
        )

        return configs


class ConfigManager:
    """Thread-safe configuration manager with reload support.

    Singleton class that manages loaded channel configurations
    and provides hot reload functionality.
    """

    _instance: "ConfigManager | None" = None

    def __init__(self, config_dir: Path) -> None:
        """Initialize ConfigManager.

        Args:
            config_dir: Directory containing channel YAML config files.
        """
        self._config_dir = config_dir
        self._configs: dict[str, ChannelConfigSchema] = {}
        self._lock = asyncio.Lock()
        self._loader = ChannelConfigLoader()

    @classmethod
    def get_instance(cls, config_dir: Path | None = None) -> "ConfigManager":
        """Get singleton instance.

        Args:
            config_dir: Directory for config files. Required on first call,
                       optional on subsequent calls.

        Returns:
            ConfigManager singleton instance.
        """
        if cls._instance is None:
            if config_dir is None:
                config_dir = Path("channel_configs")
            cls._instance = cls(config_dir)
        return cls._instance

    async def reload(self) -> None:
        """Reload all configurations from disk.

        Async-safe reload using asyncio.Lock. Uses asyncio.to_thread()
        to avoid blocking the event loop during file I/O. Logs changes
        (added/removed configs) after reload.
        """
        async with self._lock:
            # Use to_thread to avoid blocking event loop during file I/O
            new_configs = await asyncio.to_thread(
                self._loader.load_all_configs, self._config_dir
            )

            # Log changes
            added = set(new_configs.keys()) - set(self._configs.keys())
            removed = set(self._configs.keys()) - set(new_configs.keys())

            if added:
                log.info("configs_added", channel_ids=list(added))
            if removed:
                log.info("configs_removed", channel_ids=list(removed))

            self._configs = new_configs

    def get_config(self, channel_id: str) -> ChannelConfigSchema | None:
        """Get config for specific channel.

        Args:
            channel_id: The channel ID to look up.

        Returns:
            ChannelConfigSchema for the channel or None if not found.
        """
        return self._configs.get(channel_id)

    def get_all_configs(self) -> dict[str, ChannelConfigSchema]:
        """Get all loaded configs.

        Returns:
            Copy of the configs dictionary.
        """
        return self._configs.copy()
