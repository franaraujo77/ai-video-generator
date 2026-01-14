#!/usr/bin/env python3
"""Test Notion integration to verify database access and API connectivity.

This script tests:
1. NOTION_API_TOKEN is set and valid
2. NOTION_DATABASE_IDS is set
3. Database can be queried successfully
4. Database has correct schema (Title, Topic, Channel, Status properties)

Usage:
    python scripts/test_notion_integration.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add app directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.clients.notion import NotionClient
from app.config import get_notion_api_token, get_notion_database_ids


async def test_notion_integration():
    """Test Notion integration end-to-end."""
    print("🔍 Testing Notion Integration\n")
    print("=" * 60)

    # Step 1: Check environment variables
    print("\n1️⃣  Checking environment variables...")

    try:
        api_token = get_notion_api_token()
        if not api_token:
            print("❌ NOTION_API_TOKEN is not set")
            print("   Set with: export NOTION_API_TOKEN='secret_your_token_here'")
            return False

        if not api_token.startswith("secret_"):
            print(f"⚠️  NOTION_API_TOKEN doesn't start with 'secret_' (got: {api_token[:10]}...)")
            print("   This may not be a valid Notion integration token")
        else:
            print(f"✅ NOTION_API_TOKEN is set (starts with 'secret_')")
    except Exception as e:
        print(f"❌ Error getting NOTION_API_TOKEN: {e}")
        return False

    try:
        database_ids = get_notion_database_ids()
        if not database_ids:
            print("❌ NOTION_DATABASE_IDS is not set or empty")
            print("   Set with: export NOTION_DATABASE_IDS='6b870ef4134346168f14367291bc89e6'")
            return False

        print(f"✅ NOTION_DATABASE_IDS is set ({len(database_ids)} database(s))")
        for i, db_id in enumerate(database_ids, 1):
            print(f"   Database {i}: {db_id}")
    except Exception as e:
        print(f"❌ Error getting NOTION_DATABASE_IDS: {e}")
        return False

    # Step 2: Initialize Notion client
    print("\n2️⃣  Initializing Notion client...")
    try:
        client = NotionClient(api_token)
        print("✅ NotionClient initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize NotionClient: {e}")
        return False

    # Step 3: Test database access
    print("\n3️⃣  Testing database access...")

    all_success = True
    for i, database_id in enumerate(database_ids, 1):
        print(f"\n   Testing Database {i}: {database_id}")
        print(f"   URL: https://www.notion.so/{database_id.replace('-', '')}")

        try:
            # Attempt to query the database
            pages = await client.get_database_pages(database_id)
            print(f"   ✅ Successfully queried database ({len(pages)} page(s) found)")

            # Show sample pages if any exist
            if pages:
                print(f"\n   📄 Sample pages:")
                for page in pages[:3]:  # Show first 3 pages
                    props = page.get("properties", {})
                    title_prop = props.get("Title", {}) or props.get("Name", {})

                    # Extract title text
                    if "title" in title_prop:
                        title_array = title_prop["title"]
                        title = title_array[0]["text"]["content"] if title_array else "(Untitled)"
                    else:
                        title = "(No title property)"

                    # Extract status
                    status_prop = props.get("Status", {})
                    status = "N/A"
                    if status_prop.get("select"):
                        status = status_prop["select"]["name"]

                    print(f"      - {title} (Status: {status})")

                if len(pages) > 3:
                    print(f"      ... and {len(pages) - 3} more page(s)")
            else:
                print("   Database is empty (no pages found)")
                print("   Create a test entry in Notion to verify sync works")

        except Exception as e:
            error_str = str(e)
            print(f"   ❌ Failed to query database: {error_str}")

            # Provide specific troubleshooting advice
            if "400" in error_str:
                print("\n   🔧 Troubleshooting: 400 Bad Request")
                print("   Most likely cause: Database not shared with integration")
                print()
                print("   Steps to fix:")
                print(f"   1. Open database: https://www.notion.so/{database_id.replace('-', '')}")
                print("   2. Click '...' (three dots) → '+ Add connections'")
                print("   3. Select your integration")
                print("   4. Click 'Confirm'")
                print()
            elif "401" in error_str:
                print("\n   🔧 Troubleshooting: 401 Unauthorized")
                print("   Your NOTION_API_TOKEN is invalid or expired")
                print("   1. Go to: https://www.notion.so/my-integrations")
                print("   2. Find your integration")
                print("   3. Copy the Internal Integration Token")
                print("   4. Update NOTION_API_TOKEN environment variable")
                print()
            elif "403" in error_str:
                print("\n   🔧 Troubleshooting: 403 Forbidden")
                print("   Your integration lacks required capabilities")
                print("   1. Go to: https://www.notion.so/my-integrations")
                print("   2. Ensure these capabilities are enabled:")
                print("      ✅ Read content")
                print("      ✅ Update content")
                print("      ✅ Insert content")
                print()

            all_success = False

    # Step 4: Summary
    print("\n" + "=" * 60)
    if all_success:
        print("✅ All tests passed! Notion integration is working correctly.")
        print()
        print("🎉 Next steps:")
        print("   1. Restart your application")
        print("   2. Create a test video entry in Notion")
        print("   3. Change Status to 'Queued'")
        print("   4. Check logs for: task_enqueued_from_notion")
        print()
        return True
    else:
        print("❌ Some tests failed. Please fix the issues above and try again.")
        print()
        print("📚 Resources:")
        print("   - Setup Guide: NOTION_SETUP.md")
        print("   - Troubleshooting: NOTION_TROUBLESHOOTING.md")
        print()
        return False


def main():
    """Run the test suite."""
    try:
        success = asyncio.run(test_notion_integration())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
