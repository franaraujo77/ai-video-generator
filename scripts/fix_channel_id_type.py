#!/usr/bin/env python3
"""Fix tasks.channel_id column type from VARCHAR to UUID."""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import async_session_factory
from sqlalchemy import text


async def fix_channel_id_type():
    """Change tasks.channel_id from VARCHAR to UUID."""
    print("🔧 Fixing tasks.channel_id column type...\n")

    try:
        async with async_session_factory() as session:
            # Step 1: Check if table has data
            print("1️⃣  Checking for existing data...")
            result = await session.execute(text("SELECT COUNT(*) FROM tasks;"))
            count = result.scalar()
            print(f"   Found {count} row(s) in tasks table")

            if count > 0:
                print("   ⚠️  WARNING: Table has data! Proceeding will lose data.")
                print("   Aborting for safety.")
                return

            print("   ✅ Table is empty, safe to proceed\n")

            # Step 2: Drop foreign key constraint
            print("2️⃣  Dropping foreign key constraint...")
            await session.execute(
                text("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS fk_tasks_channel_id;")
            )
            print("   ✅ Foreign key dropped\n")

            # Step 3: Change column type from VARCHAR to UUID
            print("3️⃣  Changing column type from VARCHAR to UUID...")
            await session.execute(
                text("ALTER TABLE tasks ALTER COLUMN channel_id TYPE UUID USING channel_id::UUID;")
            )
            print("   ✅ Column type changed to UUID\n")

            # Step 4: Recreate foreign key with correct reference
            print("4️⃣  Creating foreign key to channels.id...")
            await session.execute(
                text(
                    """
                    ALTER TABLE tasks
                    ADD CONSTRAINT fk_tasks_channel_id
                    FOREIGN KEY (channel_id)
                    REFERENCES channels(id)
                    ON DELETE RESTRICT;
                    """
                )
            )
            print("   ✅ Foreign key created\n")

            # Commit changes
            await session.commit()
            print("✅ All changes committed\n")

            # Verify
            print("5️⃣  Verifying changes...")
            result = await session.execute(
                text(
                    """
                    SELECT column_name, data_type, udt_name
                    FROM information_schema.columns
                    WHERE table_name = 'tasks' AND column_name = 'channel_id';
                    """
                )
            )
            col = result.fetchone()
            print(f"   Column: {col[0]}")
            print(f"   Type: {col[1]}")
            print(f"   UDT: {col[2]}")

            result = await session.execute(
                text(
                    """
                    SELECT
                        conname AS constraint_name,
                        confrelid::regclass AS foreign_table,
                        af.attname AS foreign_column
                    FROM pg_constraint c
                    JOIN pg_attribute af ON af.attnum = ANY(c.confkey) AND af.attrelid = c.confrelid
                    WHERE conname = 'fk_tasks_channel_id';
                    """
                )
            )
            fk = result.fetchone()
            if fk:
                print(f"\n   Foreign key: {fk[0]}")
                print(f"   References: {fk[1]}.{fk[2]}")

            print("\n✅ Column type successfully fixed!")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(fix_channel_id_type())
