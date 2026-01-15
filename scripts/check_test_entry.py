#!/usr/bin/env python3
"""Quick script to check if test entry synced from Notion to PostgreSQL."""

import asyncio
import os
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import Task
from app.database import async_session_factory
from sqlalchemy import select


async def check_test_entry() -> None:
    """Check if test entry exists in database."""
    test_notion_page_id = "2e8088e8-988b-81d4-93bd-eeb49e35233e"

    try:
        async with async_session_factory() as session:
            # Query for test entry
            result = await session.execute(
                select(Task).where(Task.notion_page_id == test_notion_page_id)
            )
            tasks = result.scalars().all()

            if tasks:
                print("✅ SUCCESS: Test entry found in database!")
                print(f"   Found {len(tasks)} row(s):")
                for task in tasks:
                    print(f"   - Title: {task.title}")
                    print(f"   - Status: {task.status}")
                    print(f"   - Channel: {task.channel_id}")
                    print(f"   - Notion Page ID: {task.notion_page_id}")
                    print(f"   - Created: {task.created_at}")
                print("\n✨ Notion sync is working correctly!")
                sys.exit(0)
            else:
                print("❌ Test entry NOT found in database")
                print(f"   Expected notion_page_id: {test_notion_page_id}")
                print("\n   Possible issues:")
                print("   1. Database not shared with integration in Notion")
                print("   2. Sync loop hasn't run yet (wait 60 seconds)")
                print("   3. Test entry status is not 'Queued' in Notion")
                sys.exit(1)

    except Exception as e:
        print(f"ERROR: Failed to query database: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(check_test_entry())
