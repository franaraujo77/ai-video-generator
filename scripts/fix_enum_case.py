#!/usr/bin/env python3
"""Fix enum types to use lowercase values matching Python enums."""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import async_session_factory
from sqlalchemy import text


async def fix_enum_case():
    """Drop and recreate enum types with lowercase values."""
    print("🔧 Fixing enum types to use lowercase values...\n")

    try:
        async with async_session_factory() as session:
            # Step 1: Drop columns that use the enums
            print("1️⃣  Dropping columns that use enum types...")
            await session.execute(text("ALTER TABLE tasks DROP COLUMN IF EXISTS status;"))
            await session.execute(text("ALTER TABLE tasks DROP COLUMN IF EXISTS priority;"))
            print("   ✅ Columns dropped\n")

            # Step 2: Drop existing enum types
            print("2️⃣  Dropping existing enum types...")
            await session.execute(text("DROP TYPE IF EXISTS taskstatus CASCADE;"))
            await session.execute(text("DROP TYPE IF EXISTS prioritylevel CASCADE;"))
            print("   ✅ Enum types dropped\n")

            # Step 3: Create taskstatus enum with lowercase values (matching Python)
            print("3️⃣  Creating taskstatus enum with lowercase values...")
            await session.execute(
                text(
                    """
                    CREATE TYPE taskstatus AS ENUM (
                        'draft',
                        'queued',
                        'claimed',
                        'generating_assets',
                        'assets_ready',
                        'assets_approved',
                        'generating_composites',
                        'composites_ready',
                        'generating_video',
                        'video_ready',
                        'video_approved',
                        'generating_audio',
                        'audio_ready',
                        'audio_approved',
                        'generating_sfx',
                        'sfx_ready',
                        'assembling',
                        'assembly_ready',
                        'final_review',
                        'approved',
                        'uploading',
                        'published',
                        'asset_error',
                        'video_error',
                        'audio_error',
                        'sfx_error',
                        'assembly_error',
                        'upload_error'
                    );
                    """
                )
            )
            print("   ✅ taskstatus enum created with 28 lowercase values\n")

            # Step 4: Create prioritylevel enum with lowercase values
            print("4️⃣  Creating prioritylevel enum with lowercase values...")
            await session.execute(
                text(
                    """
                    CREATE TYPE prioritylevel AS ENUM (
                        'high',
                        'normal',
                        'low'
                    );
                    """
                )
            )
            print("   ✅ prioritylevel enum created with lowercase values\n")

            # Step 5: Recreate columns with enum types
            print("5️⃣  Recreating columns with enum types...")
            await session.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN status taskstatus NOT NULL DEFAULT 'queued'::taskstatus;"
                )
            )
            print("   ✅ status column created with taskstatus type")

            await session.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN priority prioritylevel NOT NULL DEFAULT 'normal'::prioritylevel;"
                )
            )
            print("   ✅ priority column created with prioritylevel type\n")

            # Step 6: Create indexes
            print("6️⃣  Creating indexes...")
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
            print("7️⃣  Verifying enum values...")
            result = await session.execute(
                text(
                    """
                    SELECT t.typname as enum_name,
                           array_agg(e.enumlabel ORDER BY e.enumsortorder) as enum_values
                    FROM pg_type t
                    JOIN pg_enum e ON t.oid = e.enumtypid
                    WHERE t.typtype = 'e'
                    GROUP BY t.typname
                    ORDER BY t.typname;
                    """
                )
            )
            enums = result.fetchall()
            print("   Enum types:")
            for enum in enums:
                print(f"   - {enum[0]}: {len(enum[1])} values")
                print(f"     First 3: {enum[1][:3]}")
                print(f"     Last 3: {enum[1][-3:]}")

            print("\n✅ Enums successfully fixed with lowercase values!")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(fix_enum_case())
