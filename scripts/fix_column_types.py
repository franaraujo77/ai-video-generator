#!/usr/bin/env python3
"""Fix column types to use enum types."""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import async_session_factory
from sqlalchemy import text


async def fix_column_types():
    """Alter status and priority columns to use enum types."""
    print("🔧 Fixing column types to use enums...\n")

    try:
        async with async_session_factory() as session:
            # Check current column types
            print("1️⃣  Checking current column types...")
            result = await session.execute(
                text(
                    """
                    SELECT column_name, data_type, udt_name
                    FROM information_schema.columns
                    WHERE table_name = 'tasks'
                    AND column_name IN ('status', 'priority')
                    ORDER BY column_name;
                    """
                )
            )
            columns = result.fetchall()
            print("Current column types:")
            for col in columns:
                print(f"   - {col[0]}: {col[1]} (udt: {col[2]})")
            print()

            # Alter status column
            print("2️⃣  Altering status column to use taskstatus enum...")
            print("   - Dropping default...")
            await session.execute(text("ALTER TABLE tasks ALTER COLUMN status DROP DEFAULT;"))
            print("   - Changing column type...")
            await session.execute(
                text(
                    """
                    ALTER TABLE tasks
                    ALTER COLUMN status TYPE taskstatus
                    USING status::taskstatus;
                    """
                )
            )
            print("✅ status column updated")

            # Alter priority column
            print("3️⃣  Altering priority column to use prioritylevel enum...")
            print("   - Dropping default...")
            await session.execute(text("ALTER TABLE tasks ALTER COLUMN priority DROP DEFAULT;"))
            print("   - Changing column type...")
            await session.execute(
                text(
                    """
                    ALTER TABLE tasks
                    ALTER COLUMN priority TYPE prioritylevel
                    USING priority::prioritylevel;
                    """
                )
            )
            print("✅ priority column updated")

            # Commit changes
            await session.commit()
            print("\n✅ All column types fixed")

            # Verify
            print("\n4️⃣  Verifying updated column types...")
            result = await session.execute(
                text(
                    """
                    SELECT column_name, data_type, udt_name
                    FROM information_schema.columns
                    WHERE table_name = 'tasks'
                    AND column_name IN ('status', 'priority')
                    ORDER BY column_name;
                    """
                )
            )
            columns = result.fetchall()
            print("Updated column types:")
            for col in columns:
                print(f"   - {col[0]}: {col[1]} (udt: {col[2]})")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(fix_column_types())
