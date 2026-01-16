#!/usr/bin/env python3
"""Sync channel configurations from YAML to database."""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import async_session_factory
from app.services.channel_config_loader import ChannelConfigLoader
from app.models import Channel
from sqlalchemy import select


async def sync_channels() -> None:
    """Load channel configs from YAML and sync to database."""
    try:
        # Get workspace root
        workspace_root = Path(__file__).parent.parent

        # Load channel configs from YAML
        loader = ChannelConfigLoader(workspace_root=workspace_root)
        config_dir = workspace_root / "config" / "channels"

        print(f"Loading channel configurations from: {config_dir}")
        configs = loader.load_all_configs(config_dir)

        if not configs:
            print("❌ No channel configurations found")
            print(f"   Check that {config_dir} contains .yaml files")
            sys.exit(1)

        print(f"✅ Loaded {len(configs)} channel configuration(s)")
        print()

        # Sync each config to database
        async with async_session_factory() as session:
            for channel_id, config in configs.items():
                print(f"Syncing channel: {channel_id}")

                # Sync config to database (creates or updates Channel)
                await loader.sync_to_database(config, session)
                print(f"  Synced channel: {config.channel_name}")
                print()

            # Commit all changes
            await session.commit()
            print("✅ All channels synced successfully")

        # Verify channels in database
        async with async_session_factory() as session:
            result = await session.execute(select(Channel))
            channels = result.scalars().all()
            print(f"\n📊 Total channels in database: {len(channels)}")
            for ch in channels:
                print(f"  - {ch.channel_id}: {ch.channel_name} (active: {ch.is_active})")

    except Exception as e:
        print(f"ERROR: Failed to sync channels: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(sync_channels())
