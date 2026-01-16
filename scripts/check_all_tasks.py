#!/usr/bin/env python3
"""Check all tasks in database."""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import Task
from app.database import async_session_factory
from sqlalchemy import select


async def check_all_tasks() -> None:
    """List all tasks in database."""
    try:
        async with async_session_factory() as session:
            # Query for all tasks
            result = await session.execute(select(Task).order_by(Task.created_at.desc()).limit(10))
            tasks = result.scalars().all()

            if tasks:
                print(f"✅ Found {len(tasks)} task(s) in database:")
                print()
                for task in tasks:
                    print(f"Task ID: {task.id}")
                    print(f"  Title: {task.title}")
                    print(f"  Status: {task.status}")
                    print(f"  Channel: {task.channel_id}")
                    print(f"  Notion Page ID: {task.notion_page_id}")
                    print(f"  Created: {task.created_at}")
                    print()
            else:
                print("❌ No tasks found in database")
                print(
                    "   The sync loop may not have run yet or there are no Queued tasks in Notion"
                )

    except Exception as e:
        print(f"ERROR: Failed to query database: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(check_all_tasks())
