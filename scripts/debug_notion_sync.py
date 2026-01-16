#!/usr/bin/env python3
"""Debug script to test Notion sync with verbose logging."""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.clients.notion import NotionClient
from app.config import get_notion_api_token, get_notion_database_ids
from app.database import async_session_factory
from app.models import Channel, Task
from app.services.task_service import enqueue_task_from_notion_page
from sqlalchemy import select


async def debug_sync():
    """Debug Notion sync process with verbose output."""
    print("🔍 Starting debug sync...\n")

    # Step 1: Check environment
    print("1️⃣  Checking environment...")
    token = get_notion_api_token()
    database_ids = get_notion_database_ids()

    if not token:
        print("❌ NOTION_API_TOKEN not set")
        return

    if not database_ids:
        print("❌ NOTION_DATABASE_IDS not set")
        return

    print(f"✅ Token: {token[:20]}...")
    print(f"✅ Database IDs: {database_ids}")
    print()

    # Step 2: Initialize Notion client
    print("2️⃣  Initializing Notion client...")
    async with NotionClient(token) as client:
        print("✅ Client initialized")
        print()

        # Step 3: Query database
        print(f"3️⃣  Querying database {database_ids[0]}...")
        try:
            pages = await client.get_database_pages(database_ids[0])
            print(f"✅ Found {len(pages)} page(s)")

            # Filter for Queued status
            queued_pages = []
            for page in pages:
                props = page.get("properties", {})
                status_prop = props.get("Status", {})
                status_value = status_prop.get("select", {})
                status_name = status_value.get("name", "") if status_value else ""

                print(f"   Page {page['id'][:8]}... Status: {status_name}")

                if status_name == "Queued":
                    queued_pages.append(page)

            print(f"✅ Found {len(queued_pages)} Queued page(s)")
            print()

            if not queued_pages:
                print("⚠️  No Queued pages found - nothing to sync")
                return

            # Step 4: Check channels
            print("4️⃣  Checking channels in database...")
            async with async_session_factory() as session:
                result = await session.execute(select(Channel))
                channels = result.scalars().all()
                print(f"✅ Found {len(channels)} channel(s) in database:")
                for ch in channels:
                    print(f"   - {ch.channel_id}: {ch.channel_name}")
                print()

            # Step 5: Process each queued page
            print("5️⃣  Processing queued pages...")
            for i, page in enumerate(queued_pages, 1):
                page_id = page["id"]
                props = page.get("properties", {})

                print(f"\n📄 Page {i}/{len(queued_pages)}: {page_id}")
                print(f"   Properties:")

                # Extract and display properties
                title_prop = props.get("Title", {})
                title_text = title_prop.get("title", [])
                title = title_text[0]["plain_text"] if title_text else ""
                print(f"   - Title: {title}")

                topic_prop = props.get("Topic", {})
                topic_text = topic_prop.get("rich_text", [])
                topic = topic_text[0]["plain_text"] if topic_text else ""
                print(f"   - Topic: {topic}")

                channel_prop = props.get("Channel", {})
                channel_select = channel_prop.get("select", {})
                channel = channel_select.get("name", "") if channel_select else ""
                print(f"   - Channel: {channel}")

                # Validate
                if not title:
                    print("   ❌ Title is empty - skipping")
                    continue
                if not topic:
                    print("   ❌ Topic is empty - skipping")
                    continue
                if not channel:
                    print("   ❌ Channel is empty - skipping")
                    continue

                print("   ✅ Validation passed")

                # Try to enqueue
                print("   🔄 Attempting to enqueue...")
                try:
                    async with async_session_factory() as session:
                        print("      - Session created")

                        async with session.begin():
                            print("      - Transaction started")

                            task = await enqueue_task_from_notion_page(page, session)
                            print("      - enqueue_task_from_notion_page returned")

                            if task:
                                print(f"      ✅ Task enqueued: {task.id}")
                            else:
                                print("      ⚠️  Task was skipped (duplicate or validation failed)")

                        print("      - Transaction committed")

                    print("      - Session closed")

                except Exception as e:
                    print(f"      ❌ Error: {e}")
                    import traceback
                    traceback.print_exc()

            print("\n✅ Debug sync completed")

        except Exception as e:
            print(f"❌ Error querying database: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_sync())
