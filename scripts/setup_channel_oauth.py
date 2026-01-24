#!/usr/bin/env python3
"""Setup YouTube OAuth for a channel."""

import argparse
import asyncio
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from app.database import async_session_factory
from app.models import Channel
from app.services.credential_service import CredentialService
from app.utils.encryption import EncryptionKeyMissingError
from google_auth_oauthlib.flow import InstalledAppFlow
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

# Configure structured logging
log = structlog.get_logger()

# Exit codes (Issue #4: Specific exit codes per error type)
EXIT_SUCCESS = 0
EXIT_GENERIC_ERROR = 1
EXIT_CLI_USAGE_ERROR = 2
EXIT_CONFIG_ERROR = 3  # FERNET_KEY, client_secret.json missing
EXIT_NETWORK_ERROR = 4
EXIT_DATABASE_ERROR = 5
EXIT_OAUTH_ERROR = 6

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


async def setup_oauth(channel_id: str, client_secrets_path: str, quiet: bool = False) -> None:
    """
    Run OAuth flow and store refresh token.

    Args:
        channel_id: Business identifier for channel (e.g., "poke1")
        client_secrets_path: Path to client_secret.json from Google Cloud Console
        quiet: If True, suppress verbose output (Issue #8: for automation)

    Raises:
        ValueError: If channel not found in database
        EncryptionKeyMissingError: If FERNET_KEY environment variable not set
        FileNotFoundError: If client_secret.json not found
    """
    try:
        # Validate client_secret.json exists
        client_secrets = Path(client_secrets_path)
        if not client_secrets.exists():
            print(f"❌ Error: Client secret file not found: {client_secrets_path}")
            print()
            print("Setup steps:")
            print("1. Go to Google Cloud Console (https://console.cloud.google.com)")
            print("2. Create a project or select existing project")
            print("3. Enable YouTube Data API v3")
            print("4. Create OAuth 2.0 credentials (Application type: Desktop app)")
            print("5. Download client_secret.json")
            print(f"6. Place file at: {client_secrets_path}")
            sys.exit(EXIT_CONFIG_ERROR)  # Issue #4: Specific exit code

        # Verify channel exists in database (Issue #2: Database connection error handling)
        try:
            async with async_session_factory() as db:
                result = await db.execute(select(Channel).where(Channel.channel_id == channel_id))
                channel = result.scalar_one_or_none()

                if channel is None:
                    print(f"❌ Error: Channel '{channel_id}' not found in database")
                    print()
                    print("Available channels:")

                    # List all channels
                    all_result = await db.execute(select(Channel))
                    all_channels = all_result.scalars().all()

                    if all_channels:
                        for ch in all_channels:
                            print(f"  - {ch.channel_id}: {ch.channel_name}")
                    else:
                        print("  (No channels found - run sync_channels.py first)")

                    sys.exit(EXIT_GENERIC_ERROR)  # Issue #4: Specific exit code
        except OperationalError as e:
            # Issue #2: Task 8.6 - Database connection error handling
            print("❌ Error: Database connection failed")
            print()
            print("Possible causes:")
            print("1. DATABASE_URL environment variable not set or incorrect")
            print("2. Database server not running")
            print("3. Network connectivity issues")
            print()
            print(f"Technical details: {e}")
            sys.exit(EXIT_DATABASE_ERROR)  # Issue #4: Specific exit code

        # Create OAuth flow
        if not quiet:  # Issue #8: Quiet mode for automation
            print(f"Setting up YouTube OAuth for channel: {channel.channel_name}")
            print()
            print("⏳ Opening browser for OAuth consent...")
            print("   Please authorize the application in your browser")
            print()

        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secrets), scopes=YOUTUBE_SCOPES
        )

        # Run local server and get credentials
        # port=0 means random available port
        credentials = flow.run_local_server(port=0)

        # Extract refresh token
        if not credentials.refresh_token:
            print("❌ Error: No refresh token received from Google")
            print()
            print("This can happen if you've already authorized this app.")
            print("To fix:")
            print("1. Go to https://myaccount.google.com/permissions")
            print("2. Remove this application from authorized apps")
            print("3. Run this script again")
            sys.exit(EXIT_OAUTH_ERROR)  # Issue #4: Specific exit code

        # Store encrypted token
        if not quiet:
            print("✅ OAuth consent granted")
            print("⏳ Encrypting and storing refresh token...")

        try:
            async with async_session_factory() as db:
                service = CredentialService()
                await service.store_youtube_token(channel_id, credentials.refresh_token, db)
                await db.commit()

                # Issue #5: Structured audit logging
                log.info(
                    "oauth_setup_success",
                    channel_id=channel_id,
                    channel_name=channel.channel_name,
                )
        except OperationalError as e:
            # Issue #2: Database error during token storage
            print("❌ Error: Database connection failed during token storage")
            print(f"Technical details: {e}")
            sys.exit(EXIT_DATABASE_ERROR)

        print(f"✅ OAuth setup complete for channel '{channel.channel_name}'")

        if not quiet:  # Issue #8: Verbose notes only in non-quiet mode
            print()
            print("Notes:")
            print("  - Refresh token stored in database (encrypted)")
            print("  - Access token expires after 1 hour (automatic refresh)")
            print(
                "  - To re-authorize: Remove app from "
                "https://myaccount.google.com/permissions and run again"
            )

    except EncryptionKeyMissingError:
        print("❌ Error: FERNET_KEY environment variable not set")
        print()
        print("Setup steps:")
        print("1. Run: python scripts/generate_fernet_key.py")
        print("2. Copy the generated key")
        print("3. Set environment variable: export FERNET_KEY=<key>")
        print("4. For Railway: Add FERNET_KEY to environment variables in dashboard")
        sys.exit(EXIT_CONFIG_ERROR)  # Issue #4: Specific exit code

    except Exception as e:
        # Check for specific OAuth errors
        error_str = str(e).lower()

        if "access_denied" in error_str:
            print("❌ OAuth consent denied by user")
            print("   Please run the script again and click 'Allow' in the browser")
            sys.exit(EXIT_OAUTH_ERROR)  # Issue #4: Specific exit code

        # Issue #7: YouTube API quota error handling
        if "quota" in error_str or "rate limit" in error_str or "429" in error_str:
            print("❌ YouTube API quota exceeded")
            print()
            print("Your Google Cloud project has hit the daily OAuth request limit.")
            print()
            print("Solutions:")
            print("1. Wait 24 hours for quota reset (resets at midnight Pacific Time)")
            print("2. Request quota increase in Google Cloud Console")
            print("3. Use a different Google Cloud project")
            print()
            print(f"Technical details: {e}")
            sys.exit(EXIT_OAUTH_ERROR)  # Issue #4: Specific exit code

        if "network" in error_str or "connection" in error_str:
            print("❌ Network error during OAuth")
            print("   Check your internet connection and try again")
            sys.exit(EXIT_NETWORK_ERROR)  # Issue #4: Specific exit code

        # Generic error handling
        print(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(EXIT_GENERIC_ERROR)  # Issue #4: Specific exit code


if __name__ == "__main__":
    # Issue #9: Type hints in main block
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Setup YouTube OAuth for a channel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/setup_channel_oauth.py --channel poke1
  python scripts/setup_channel_oauth.py --channel poke2 --client-secrets /path/to/client_secret.json
  python scripts/setup_channel_oauth.py --channel poke1 --quiet  # For automation

Notes:
  - Requires FERNET_KEY environment variable for encryption
  - Requires client_secret.json from Google Cloud Console
  - Opens browser for OAuth consent
  - Stores encrypted refresh token in database

Exit Codes:
  0 - Success
  1 - Generic error
  2 - CLI usage error
  3 - Configuration error (FERNET_KEY or client_secret.json missing)
  4 - Network error
  5 - Database error
  6 - OAuth error
        """,
    )
    parser.add_argument(
        "--channel", required=True, help="Channel ID (business identifier, e.g., 'poke1')"
    )
    parser.add_argument(
        "--client-secrets",
        default="client_secret.json",
        help="Path to client_secret.json (default: client_secret.json)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output (for automation)",  # Issue #8
    )
    args: argparse.Namespace = parser.parse_args()

    asyncio.run(setup_oauth(args.channel, args.client_secrets, args.quiet))
