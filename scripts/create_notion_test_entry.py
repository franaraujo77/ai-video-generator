#!/usr/bin/env python3
"""Create a test entry in Notion database to verify sync."""

import asyncio
import os
import sys
import uuid
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.clients.notion import NotionClient


async def create_test_entry():
    """Create a new test entry in Notion database."""
    token = os.getenv("NOTION_API_TOKEN")
    if not token:
        print("❌ NOTION_API_TOKEN not set")
        sys.exit(1)

    # Use the known database ID
    db_id = "6b870ef4134346168f14367291bc89e6"

    print(f"🔧 Creating new test entry in Notion database {db_id}...\n")

    # Create Notion client
    client = NotionClient(token)

    # Generate unique test ID
    test_id = str(uuid.uuid4())[:8]

    # Create new page with required properties
    page_data = {
        "parent": {"database_id": db_id},
        "properties": {
            "Title": {"title": [{"text": {"content": f"Test Sync Entry {test_id}"}}]},
            "Topic": {
                "rich_text": [
                    {"text": {"content": "Testing automated sync from Notion to database"}}
                ]
            },
            "Story Direction": {
                "rich_text": [{"text": {"content": "Verify enum handling works correctly"}}]
            },
            "Channel": {"select": {"name": "poke1"}},
            "Status": {"select": {"name": "Queued"}},
            "Priority": {"select": {"name": "High"}},
        },
    }

    try:
        response = await client.client.post(
            "https://api.notion.com/v1/pages", json=page_data
        )

        if response.status_code == 200:
            page = response.json()
            print(f'✅ Created new Notion page: {page["id"]}')
            print(f"   Title: Test Sync Entry {test_id}")
            print(f'   URL: {page["url"]}')
            print(f"\n⏱️  Sync runs every 60 seconds. Check database in ~1 minute.")
        else:
            print(f"❌ Failed to create page: {response.status_code}")
            print(f"   Error: {response.text}")
            sys.exit(1)

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(create_test_entry())
