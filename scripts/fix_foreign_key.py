#!/usr/bin/env python3
"""Fix foreign key to reference channels.id instead of channels.channel_id."""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import async_session_factory
from sqlalchemy import text


async def fix_foreign_key():
    """Drop and recreate foreign key with correct reference."""
    print("🔧 Fixing foreign key constraint...\n")

    try:
        async with async_session_factory() as session:
            # Step 1: Drop incorrect foreign key
            print("1️⃣  Dropping incorrect foreign key...")
            await session.execute(
                text("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS fk_tasks_channel_id;")
            )
            print("   ✅ Old foreign key dropped\n")

            # Step 2: Create correct foreign key
            print("2️⃣  Creating correct foreign key...")
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
            print("   ✅ New foreign key created (references channels.id)\n")

            # Commit changes
            await session.commit()
            print("✅ Changes committed\n")

            # Verify
            print("3️⃣  Verifying foreign key...")
            result = await session.execute(
                text(
                    """
                    SELECT
                        conname AS constraint_name,
                        conrelid::regclass AS table_name,
                        a.attname AS column_name,
                        confrelid::regclass AS foreign_table,
                        af.attname AS foreign_column
                    FROM pg_constraint c
                    JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
                    JOIN pg_attribute af ON af.attnum = ANY(c.confkey) AND af.attrelid = c.confrelid
                    WHERE conname = 'fk_tasks_channel_id';
                    """
                )
            )
            fk = result.fetchone()
            if fk:
                print(f"   Constraint: {fk[0]}")
                print(f"   Table: {fk[1]}.{fk[2]}")
                print(f"   References: {fk[3]}.{fk[4]}")

                if fk[4] == "id":
                    print("\n✅ Foreign key correctly references channels.id!")
                else:
                    print(f"\n❌ Foreign key still references {fk[4]} instead of id")
            else:
                print("   ❌ Foreign key not found after creation")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(fix_foreign_key())
