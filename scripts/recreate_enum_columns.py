#!/usr/bin/env python3
"""Recreate status and priority columns with proper enum types."""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import async_session_factory
from sqlalchemy import text


async def recreate_columns():
    """Drop and recreate status/priority columns with enum types."""
    print("🔧 Recreating columns with enum types...\n")

    try:
        async with async_session_factory() as session:
            # Step 1: Check if table has any data
            print("1️⃣  Checking for existing data...")
            result = await session.execute(text("SELECT COUNT(*) FROM tasks;"))
            count = result.scalar()
            print(f"   Found {count} row(s) in tasks table")

            if count > 0:
                print("   ⚠️  WARNING: Table has data! Proceeding will lose data.")
                print("   Aborting for safety.")
                return

            print("   ✅ Table is empty, safe to proceed\n")

            # Step 2: Drop existing columns
            print("2️⃣  Dropping existing status and priority columns...")
            await session.execute(text("ALTER TABLE tasks DROP COLUMN IF EXISTS status;"))
            await session.execute(text("ALTER TABLE tasks DROP COLUMN IF EXISTS priority;"))
            print("   ✅ Columns dropped\n")

            # Step 3: Recreate columns with enum types
            print("3️⃣  Creating new columns with enum types...")
            await session.execute(
                text("ALTER TABLE tasks ADD COLUMN status taskstatus NOT NULL DEFAULT 'QUEUED'::taskstatus;")
            )
            print("   ✅ status column created with taskstatus type")

            await session.execute(
                text("ALTER TABLE tasks ADD COLUMN priority prioritylevel NOT NULL DEFAULT 'NORMAL'::prioritylevel;")
            )
            print("   ✅ priority column created with prioritylevel type\n")

            # Step 4: Create indexes
            print("4️⃣  Creating indexes...")
            await session.execute(
                text("CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks(status);")
            )
            print("   ✅ Index created on status")

            await session.execute(
                text("CREATE INDEX IF NOT EXISTS ix_tasks_priority ON tasks(priority);")
            )
            print("   ✅ Index created on priority\n")

            # Commit changes
            await session.commit()
            print("✅ All changes committed\n")

            # Verify
            print("5️⃣  Verifying column types...")
            result = await session.execute(
                text(
                    """
                    SELECT column_name, data_type, udt_name, column_default
                    FROM information_schema.columns
                    WHERE table_name = 'tasks'
                    AND column_name IN ('status', 'priority')
                    ORDER BY column_name;
                    """
                )
            )
            columns = result.fetchall()
            print("   Column types:")
            for col in columns:
                print(f"   - {col[0]}: {col[1]} (udt: {col[2]}, default: {col[3]})")

            print("\n✅ Columns successfully recreated with enum types!")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(recreate_columns())
