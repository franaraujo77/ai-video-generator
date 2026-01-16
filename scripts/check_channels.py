#!/usr/bin/env python3
"""Check channels in database."""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import Channel
from app.database import async_session_factory
from sqlalchemy import select


async def check_channels() -> None:
    """List all channels in database."""
    try:
        async with async_session_factory() as session:
            # Query for all channels
            result = await session.execute(select(Channel))
            channels = result.scalars().all()

            if channels:
                print(f"✅ Found {len(channels)} channel(s) in database:")
                print()
                for channel in channels:
                    print(f"Channel ID (UUID): {channel.id}")
                    print(f"  Channel ID (string): {channel.channel_id}")
                    print(f"  Channel Name: {channel.channel_name}")
                    print(f"  Active: {channel.is_active}")
                    print()
            else:
                print("❌ No channels found in database")
                print("   You need to create a channel configuration and sync it to the database")

    except Exception as e:
        print(f"ERROR: Failed to query database: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(check_channels())
