"""YouTube service with automatic OAuth token refresh.

This service manages YouTube API credentials with automatic token refresh
before expiration. Access tokens are cached in memory (not database) and
refreshed proactively when expires in < 5 minutes.

Usage:
    from app.services.youtube_service import YouTubeService
    from app.config import get_config

    config = get_config()
    youtube_service = YouTubeService(
        client_id=config.google_client_id,
        client_secret=config.google_client_secret
    )

    # Get credentials (auto-refresh if expired)
    creds = await youtube_service.get_credentials("poke1", db)

    # Build YouTube API client
    youtube = await youtube_service.build_youtube_client("poke1", db)

Architecture Pattern:
    - In-memory credentials cache (NOT database) per channel
    - Proactive refresh when expiry < 5 minutes
    - Thread-safe asyncio.Lock for concurrent access
    - RefreshError → Alert + Database flag + YouTubeAuthError raised
    - Uses google-auth libraries (Credentials, Request, RefreshError)

Security Rules (CRITICAL):
    - NEVER log access tokens or refresh tokens
    - NEVER store access tokens in database (memory cache only)
    - Always use asyncio.to_thread for synchronous refresh() call

References:
    - Story 7.2: OAuth Token Refresh Automation
    - Story 7.1: YouTube OAuth Setup CLI (refresh token storage)
    - PRD: FR61 (Auto-refresh), NFR-I5 (No upload failures)
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

import structlog
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from requests.exceptions import ConnectionError, RequestException, Timeout
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel
from app.services.credential_service import CredentialService
from app.utils.alerts import send_alert

log = structlog.get_logger(__name__)


class YouTubeAuthError(Exception):
    """Raised when YouTube authentication fails (refresh token invalid/revoked).

    This exception is raised when:
    - Refresh token is revoked by user in Google Account settings
    - Refresh token is invalid or expired
    - OAuth client credentials are incorrect
    - Refresh token not found in database

    Workers should catch this exception and skip YouTube tasks for the channel
    until re-authorization is completed via Story 7.1 CLI.
    """

    pass


class YouTubeService:
    """YouTube API service with automatic token refresh.

    This service manages YouTube OAuth credentials with proactive token refresh
    before expiration. Access tokens are cached in memory (not database) for
    performance. Credentials are automatically refreshed when expired or when
    expiry is within 5 minutes.

    Class Attributes:
        _credentials_cache: Class-level cache shared across all instances.
            Dict mapping channel_id → Credentials object.
        _cache_lock: AsyncIO lock for thread-safe cache access.
        PROACTIVE_REFRESH_WINDOW_MINUTES: Refresh tokens this many minutes
            before expiry to prevent race conditions during API calls.

    Instance Attributes:
        client_id: Google OAuth client ID (from GOOGLE_CLIENT_ID env var).
        client_secret: Google OAuth client secret (from GOOGLE_CLIENT_SECRET).
        credential_service: CredentialService for database access.

    Example:
        >>> from app.config import get_config
        >>> config = get_config()
        >>> service = YouTubeService(
        ...     client_id=config.google_client_id, client_secret=config.google_client_secret
        ... )
        >>> creds = await service.get_credentials("poke1", db)
        >>> youtube = await service.build_youtube_client("poke1", db)
    """

    # Class-level cache (shared across all instances)
    _credentials_cache: ClassVar[dict[str, Credentials]] = {}
    _cache_lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    # Proactive refresh window: Refresh tokens 5 minutes before expiry
    # to prevent race conditions where token expires during API call
    PROACTIVE_REFRESH_WINDOW_MINUTES = 5

    def __init__(self, client_id: str, client_secret: str):
        """Initialize YouTube service with OAuth client credentials.

        Args:
            client_id: Google OAuth client ID (from GOOGLE_CLIENT_ID env var).
                Must match client_secret.json value. Format:
                xxxxx.apps.googleusercontent.com
            client_secret: Google OAuth client secret (from GOOGLE_CLIENT_SECRET).
                Must match client_secret.json value. Format: GOCSPX-xxxxx
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.credential_service = CredentialService()

    async def get_credentials(self, channel_id: str, db: AsyncSession) -> Credentials:
        """Get valid YouTube credentials for channel (auto-refresh if needed).

        This method retrieves credentials from cache if available and still valid.
        If not cached or expired, it fetches the refresh token from database,
        creates a new Credentials object, performs initial refresh, and caches
        the result.

        Args:
            channel_id: Channel business ID (e.g., "poke1").
            db: Database session for fetching refresh token.

        Returns:
            Credentials object with valid access token (good for 1 hour).

        Raises:
            YouTubeAuthError: If refresh token is invalid/revoked or not found.

        Example:
            >>> creds = await service.get_credentials("poke1", db)
            >>> print(creds.token)  # Valid access token
            >>> print(creds.expiry)  # Expiry timestamp
        """
        async with self._cache_lock:
            # Check cache first
            if channel_id in self._credentials_cache:
                creds = self._credentials_cache[channel_id]

                # Refresh if expired or expiring soon
                await self._refresh_token_if_needed(creds, channel_id, db)
                return creds

            # Not in cache: Fetch refresh token from database
            refresh_token = await self.credential_service.get_youtube_token(channel_id, db)
            if not refresh_token:
                raise YouTubeAuthError(f"No YouTube credentials found for channel {channel_id}")

            # Create Credentials object
            creds = Credentials(
                token=None,  # Will be populated on first refresh
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token", # noqa: S106
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=[
                    "https://www.googleapis.com/auth/youtube.upload",
                    "https://www.googleapis.com/auth/youtube.force-ssl",
                ],
            )

            # Initial refresh to get access token
            await self._refresh_token_if_needed(creds, channel_id, db)

            # Cache credentials
            self._credentials_cache[channel_id] = creds

            return creds

    async def _refresh_token_if_needed(
        self, creds: Credentials, channel_id: str, db: AsyncSession
    ) -> None:
        """Refresh access token if expired or expiring soon.

        This method checks if the access token needs refresh (expired or expires
        within PROACTIVE_REFRESH_WINDOW_MINUTES) and performs the refresh if needed.
        If refresh fails, it handles different error types appropriately:
        - RefreshError: Invalid/revoked token → alert, mark invalid, remove cache
        - Network errors: Transient failure → log warning, clear cache, raise for retry
        - Other exceptions: Unexpected failure → clear cache, re-raise

        Args:
            creds: Credentials object to check/refresh.
            channel_id: Channel ID for logging/alerts.
            db: Database session for marking invalid tokens.

        Raises:
            YouTubeAuthError: If refresh token is invalid/revoked.
            RequestException: If network error during refresh (retryable).
            Exception: For unexpected errors.
        """
        # Check if refresh needed
        needs_refresh = (
            not creds.token  # No access token yet
            or creds.expired  # Already expired
            or (  # Expires soon (proactive refresh window)
                creds.expiry
                and creds.expiry
                < datetime.now(timezone.utc).replace(tzinfo=None)
                + timedelta(minutes=self.PROACTIVE_REFRESH_WINDOW_MINUTES)
            )
        )

        if not needs_refresh:
            return  # Token still valid

        try:
            # Refresh access token (synchronous call, use to_thread to avoid blocking)
            request = Request()
            await asyncio.to_thread(creds.refresh, request)

            log.info(
                "youtube_token_refreshed",
                channel_id=channel_id,
                expiry=creds.expiry.isoformat() if creds.expiry else None,
            )

        except RefreshError as e:
            # Refresh token is invalid or revoked (permanent failure)
            log.critical("youtube_token_refresh_failed", channel_id=channel_id, error=str(e))

            # Send alert to operators
            await send_alert(
                level="CRITICAL",
                message=f"YouTube re-authorization required for channel '{channel_id}'",
                details={
                    "channel_id": channel_id,
                    "error": str(e),
                    "action_required": (
                        f"Run: python scripts/setup_channel_oauth.py --channel {channel_id}"
                    ),
                },
            )

            # Mark channel token as invalid in database
            await db.execute(
                update(Channel)
                .where(Channel.channel_id == channel_id)
                .values(youtube_token_invalid=True)
            )
            await db.commit()

            # Remove from cache
            if channel_id in self._credentials_cache:
                del self._credentials_cache[channel_id]

            raise YouTubeAuthError(
                f"YouTube refresh token invalid for channel {channel_id}. "
                f"Re-authorization required."
            ) from e

        except (ConnectionError, Timeout, RequestException) as e:
            # Network error during refresh (transient failure, retryable)
            log.warning(
                "youtube_token_refresh_network_error",
                channel_id=channel_id,
                error=str(e),
                error_type=type(e).__name__,
            )

            # Clear cache to force fresh fetch on retry
            if channel_id in self._credentials_cache:
                del self._credentials_cache[channel_id]

            # Re-raise for worker retry logic
            raise

        except Exception as e:
            # Unexpected error - log and clear cache
            log.error(
                "youtube_token_refresh_unexpected_error",
                channel_id=channel_id,
                error=str(e),
                error_type=type(e).__name__,
            )

            # Clear cache to prevent using stale credentials
            if channel_id in self._credentials_cache:
                del self._credentials_cache[channel_id]

            # Re-raise for caller to handle
            raise

    async def build_youtube_client(self, channel_id: str, db: AsyncSession) -> Any:
        """Build YouTube Data API v3 client with valid credentials.

        This is a convenience method that gets credentials and builds the YouTube
        API client in one call. The client is ready to use for YouTube operations.

        Args:
            channel_id: Channel business ID (e.g., "poke1").
            db: Database session.

        Returns:
            YouTube API client resource object (googleapiclient.discovery.Resource).

        Raises:
            YouTubeAuthError: If credentials are invalid/revoked.

        Example:
            >>> youtube = await service.build_youtube_client("poke1", db)
            >>> request = youtube.videos().list(part="snippet", id="video_id")
            >>> response = request.execute()
        """
        creds = await self.get_credentials(channel_id, db)

        # Build YouTube client (synchronous, use to_thread to avoid blocking)
        youtube = await asyncio.to_thread(build, "youtube", "v3", credentials=creds)

        return youtube
