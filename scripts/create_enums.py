#!/usr/bin/env python3
"""Create missing enum types in PostgreSQL database."""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import async_session_factory
from sqlalchemy import text


async def create_enums():
    """Create taskstatus and prioritylevel enum types."""
    print("🔧 Creating missing enum types...\n")

    try:
        async with async_session_factory() as session:
            # Create taskstatus enum
            print("Creating taskstatus enum...")
            await session.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taskstatus') THEN
                            CREATE TYPE taskstatus AS ENUM (
                                'QUEUED',
                                'CLAIMED',
                                'GENERATING_ASSETS',
                                'ASSETS_READY',
                                'ASSETS_APPROVED',
                                'GENERATING_COMPOSITES',
                                'COMPOSITES_READY',
                                'GENERATING_VIDEO',
                                'VIDEO_READY',
                                'VIDEO_APPROVED',
                                'GENERATING_AUDIO',
                                'AUDIO_READY',
                                'AUDIO_APPROVED',
                                'GENERATING_SFX',
                                'SFX_READY',
                                'ASSEMBLING',
                                'ASSEMBLY_READY',
                                'FINAL_REVIEW',
                                'APPROVED',
                                'UPLOADING',
                                'PUBLISHED',
                                'ASSET_ERROR',
                                'VIDEO_ERROR',
                                'AUDIO_ERROR',
                                'SFX_ERROR',
                                'ASSEMBLY_ERROR',
                                'UPLOAD_ERROR'
                            );
                        END IF;
                    END$$;
                    """
                )
            )
            print("✅ taskstatus enum created")

            # Create prioritylevel enum
            print("Creating prioritylevel enum...")
            await session.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'prioritylevel') THEN
                            CREATE TYPE prioritylevel AS ENUM (
                                'HIGH',
                                'NORMAL',
                                'LOW'
                            );
                        END IF;
                    END$$;
                    """
                )
            )
            print("✅ prioritylevel enum created")

            # Commit the changes
            await session.commit()
            print("\n✅ All enum types created successfully")

            # Verify
            print("\n🔍 Verifying enum types...")
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

            print(f"✅ Found {len(enums)} enum type(s):\n")
            for enum in enums:
                print(f"   - {enum[0]}: {len(enum[1])} values")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(create_enums())
