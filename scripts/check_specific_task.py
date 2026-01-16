#!/usr/bin/env python3
"""Check for specific notion_page_id in database."""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import Task
from app.database import async_session_factory
from sqlalchemy import select


async def check_specific_task() -> None:
    """Check for specific test entry in database."""
    test_notion_page_id = "2e8088e8-988b-81d4-93bd-eeb49e35233e"

    try:
        async with async_session_factory() as session:
            # Query for specific notion_page_id
            result = await session.execute(
                select(Task).where(Task.notion_page_id == test_notion_page_id)
            )
            task = result.scalar_one_or_none()

            if task:
                print(f"✅ Found task with notion_page_id: {test_notion_page_id}")
                print(f"   Task ID: {task.id}")
                print(f"   Title: {task.title}")
                print(f"   Status: {task.status}")
                print(f"   Channel ID: {task.channel_id}")
                print(f"   Created: {task.created_at}")
                print(f"   Updated: {task.updated_at}")
            else:
                print(f"❌ No task found with notion_page_id: {test_notion_page_id}")
                print("   This means the task is NOT in the database")
                print("   But the sync log shows it was skipped")
                print("   Possible issue:")
                print("   - Check if Railway app is connected to the correct database")
                print("   - Or there's a different reason for skipping (not duplicate)")

    except Exception as e:
        print(f"ERROR: Failed to query database: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(check_specific_task())
