"""Channel configuration loader from YAML files.

This module provides the ChannelConfigLoader class for loading channel
configurations from YAML files, and the ConfigManager singleton for
managing loaded configurations with hot reload support.

Syncing Configuration to Database:
    The ChannelConfigLoader.sync_to_database() method persists voice and branding
    configuration from YAML to the Channel model. This enables the orchestration
    layer to read voice_id and branding paths directly from the database without
    parsing YAML files at runtime.

    YAML → ChannelConfigSchema → sync_to_database() → Channel model
"""

import asyncio
from pathlib import Path

import structlog
import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel
from app.schemas.channel_config import ChannelConfigSchema

log = structlog.get_logger()


class ChannelConfigLoader:
    """Loads and validates channel configurations from YAML files.

    This class handles loading individual YAML files and scanning directories
    for channel configurations. Invalid files are logged and skipped.

    Also provides sync_to_database() for persisting voice and branding config
    from YAML to the Channel database model.
    """

    def __init__(self, workspace_root: Path | None = None) -> None:
        """Initialize ChannelConfigLoader.

        Args:
            workspace_root: Base path for validating branding file existence.
                           If None, file existence checks are skipped.
        """
        self._workspace_root = workspace_root

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

    def validate_branding_files(
        self, config: ChannelConfigSchema, channel_workspace: Path | None = None
    ) -> list[str]:
        """Validate branding file paths exist on filesystem.

        Args:
            config: Channel configuration with branding section.
            channel_workspace: Base path for branding files. If None, uses
                              self._workspace_root if set.

        Returns:
            List of warning messages for missing branding files.
            Empty list if all files exist or no branding configured.
        """
        warnings: list[str] = []
        workspace = channel_workspace or self._workspace_root

        if workspace is None:
            # Cannot validate without workspace path
            return warnings

        if config.branding is None:
            return warnings

        branding = config.branding

        if branding.intro_video:
            intro_path = workspace / branding.intro_video
            if not intro_path.exists():
                warnings.append(f"Branding intro video not found: {intro_path}")
                log.warning(
                    "branding_file_not_found",
                    channel_id=config.channel_id,
                    file_type="intro_video",
                    path=str(intro_path),
                )

        if branding.outro_video:
            outro_path = workspace / branding.outro_video
            if not outro_path.exists():
                warnings.append(f"Branding outro video not found: {outro_path}")
                log.warning(
                    "branding_file_not_found",
                    channel_id=config.channel_id,
                    file_type="outro_video",
                    path=str(outro_path),
                )

        if branding.watermark_image:
            watermark_path = workspace / branding.watermark_image
            if not watermark_path.exists():
                warnings.append(f"Branding watermark not found: {watermark_path}")
                log.warning(
                    "branding_file_not_found",
                    channel_id=config.channel_id,
                    file_type="watermark_image",
                    path=str(watermark_path),
                )

        return warnings

    async def sync_to_database(
        self, config: ChannelConfigSchema, db: AsyncSession
    ) -> Channel:
        """Persist voice and branding config from YAML to database.

        Creates or updates a Channel record with voice_id and branding paths
        from the parsed YAML configuration. This enables the orchestration
        layer to read configuration from the database at runtime.

        Logs warning if voice_id is missing (AC #2).

        Args:
            config: Validated ChannelConfigSchema from YAML.
            db: Async database session.

        Returns:
            Created or updated Channel model.

        Example:
            >>> config = loader.load_channel_config(Path("poke1.yaml"))
            >>> channel = await loader.sync_to_database(config, db)
        """
        # Check for existing channel
        result = await db.execute(
            select(Channel).where(Channel.channel_id == config.channel_id)
        )
        channel = result.scalar_one_or_none()

        if channel is None:
            # Create new channel
            channel = Channel(
                channel_id=config.channel_id,
                channel_name=config.channel_name,
                is_active=config.is_active,
            )
            db.add(channel)
            log.info(
                "channel_created",
                channel_id=config.channel_id,
                channel_name=config.channel_name,
            )
        else:
            # Update existing channel
            channel.channel_name = config.channel_name
            channel.is_active = config.is_active
            log.info(
                "channel_updated",
                channel_id=config.channel_id,
                channel_name=config.channel_name,
            )

        # Sync voice_id (AC #2 - log warning if missing)
        channel.voice_id = config.voice_id
        if config.voice_id is None:
            log.warning(
                "channel_voice_id_not_set",
                channel_id=config.channel_id,
                message="Channel will use DEFAULT_VOICE_ID for narration",
            )

        # Sync branding paths
        if config.branding:
            channel.branding_intro_path = config.branding.intro_video
            channel.branding_outro_path = config.branding.outro_video
            channel.branding_watermark_path = config.branding.watermark_image
            log.info(
                "channel_branding_synced",
                channel_id=config.channel_id,
                has_intro=config.branding.intro_video is not None,
                has_outro=config.branding.outro_video is not None,
                has_watermark=config.branding.watermark_image is not None,
            )
        else:
            # Clear branding if not configured
            channel.branding_intro_path = None
            channel.branding_outro_path = None
            channel.branding_watermark_path = None

        await db.commit()
        await db.refresh(channel)

        return channel


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
