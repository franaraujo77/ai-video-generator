#!/usr/bin/env python3
"""Check what enum types exist in the database."""

import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import async_session_factory
from sqlalchemy import text


async def check_enums():
    """Check enum types in PostgreSQL database."""
    print("🔍 Checking enum types in database...\n")

    try:
        async with async_session_factory() as session:
            # Query PostgreSQL enum types
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

            if enums:
                print(f"✅ Found {len(enums)} enum type(s):\n")
                for enum in enums:
                    print(f"📊 {enum[0]}")
                    print(f"   Values: {enum[1]}\n")
            else:
                print("❌ No enum types found in database")
                print("   The database schema may be missing enum definitions")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(check_enums())
