"""Tests for admin routes.

Tests admin authentication, manual quota reset endpoint, rate limiting, and validation.
"""

import os
import pytest
from datetime import date, datetime
from freezegun import freeze_time
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.main import app
from app.models import Channel, YouTubeQuotaUsage, GeminiQuotaUsage


@pytest.fixture
async def active_channel(async_session: AsyncSession) -> Channel:
    """Create an active channel for testing."""
    channel = Channel(
        id=uuid4(),
        channel_id="test_channel_admin",
        channel_name="Test Admin Channel",
        is_active=True,
        youtube_quota_exhausted=True,
        gemini_quota_exhausted=True,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest.fixture
async def inactive_channel(async_session: AsyncSession) -> Channel:
    """Create an inactive channel for testing."""
    channel = Channel(
        id=uuid4(),
        channel_id="inactive_channel_admin",
        channel_name="Inactive Admin Channel",
        is_active=False,
        youtube_quota_exhausted=False,
        gemini_quota_exhausted=False,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest.fixture
def admin_api_key(monkeypatch):
    """Set ADMIN_API_KEY environment variable for tests."""
    test_key = "test-admin-key-12345"
    monkeypatch.setenv("ADMIN_API_KEY", test_key)
    return test_key


@pytest.fixture(autouse=True)
def clear_rate_limiter():
    """Clear rate limiter storage before each test."""
    from app.routes.admin import limiter

    # Clear all rate limit data
    if hasattr(limiter, "_storage"):
        limiter._storage.storage.clear()

    yield


@pytest.fixture
async def client(async_session: AsyncSession) -> AsyncClient:
    """Create async HTTP client for testing with database override."""
    from app.database import get_session

    # Override database dependency with test session
    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    # Clean up overrides
    app.dependency_overrides.clear()


class TestAdminAuthentication:
    """Test admin API key authentication."""

    async def test_missing_admin_key_returns_401(
        self, client: AsyncClient, active_channel: Channel, admin_api_key: str
    ):
        """Test that missing admin key returns 401 Unauthorized."""
        response = await client.post(
            "/api/v1/admin/quota-reset",
            json={
                "channel_id": str(active_channel.id),
                "service": "youtube",
            },
            # No X-Admin-Key header
        )
        assert response.status_code == 401
        assert "Invalid admin API key" in response.json()["detail"]

    async def test_invalid_admin_key_returns_401(
        self, client: AsyncClient, active_channel: Channel, admin_api_key: str
    ):
        """Test that invalid admin key returns 401 Unauthorized."""
        response = await client.post(
            "/api/v1/admin/quota-reset",
            json={
                "channel_id": str(active_channel.id),
                "service": "youtube",
            },
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert response.status_code == 401
        assert "Invalid admin API key" in response.json()["detail"]

    async def test_valid_admin_key_allows_access(
        self, client: AsyncClient, active_channel: Channel, admin_api_key: str
    ):
        """Test that valid admin key allows access to endpoint."""
        response = await client.post(
            "/api/v1/admin/quota-reset",
            json={
                "channel_id": str(active_channel.id),
                "service": "youtube",
            },
            headers={"X-Admin-Key": admin_api_key},
        )
        # Should not return 401 (might return 200 or other status)
        assert response.status_code != 401

    async def test_admin_key_not_configured_returns_500(
        self, client: AsyncClient, active_channel: Channel, monkeypatch
    ):
        """Test that missing ADMIN_API_KEY env var returns 500."""
        # Remove ADMIN_API_KEY from environment
        monkeypatch.delenv("ADMIN_API_KEY", raising=False)

        response = await client.post(
            "/api/v1/admin/quota-reset",
            json={
                "channel_id": str(active_channel.id),
                "service": "youtube",
            },
            headers={"X-Admin-Key": "any-key"},
        )
        assert response.status_code == 500
        assert "Admin API key not configured" in response.json()["detail"]


class TestManualQuotaReset:
    """Test manual quota reset endpoint functionality."""

    @freeze_time("2026-01-25 08:00:00")  # Midnight PST = 08:00 UTC
    async def test_reset_youtube_quota_success(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        active_channel: Channel,
        admin_api_key: str,
    ):
        """Test successful YouTube quota reset for active channel."""
        response = await client.post(
            "/api/v1/admin/quota-reset",
            json={
                "channel_id": str(active_channel.id),
                "service": "youtube",
            },
            headers={"X-Admin-Key": admin_api_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["service"] == "youtube"
        assert data["channel_id"] == str(active_channel.id)
        assert data["new_quota_units"] == 10000
        assert data["quota_exhausted_flag_cleared"] is True

        # Verify quota created in database
        quota = await async_session.get(YouTubeQuotaUsage, (active_channel.id, date(2026, 1, 25)))
        assert quota is not None
        assert quota.units_used == 0
        assert quota.daily_limit == 10000

        # Verify flag cleared
        await async_session.refresh(active_channel)
        assert active_channel.youtube_quota_exhausted is False

    @freeze_time("2026-01-25 08:00:00")  # Midnight PST = 08:00 UTC
    async def test_reset_gemini_quota_success(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        active_channel: Channel,
        admin_api_key: str,
    ):
        """Test successful Gemini quota reset for active channel."""
        response = await client.post(
            "/api/v1/admin/quota-reset",
            json={
                "channel_id": str(active_channel.id),
                "service": "gemini",
            },
            headers={"X-Admin-Key": admin_api_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["service"] == "gemini"
        assert data["new_quota_units"] == 1500
        assert data["quota_exhausted_flag_cleared"] is True

        # Verify quota created in database
        quota = await async_session.get(GeminiQuotaUsage, (active_channel.id, date(2026, 1, 25)))
        assert quota is not None
        assert quota.requests_used == 0
        assert quota.daily_limit == 1500

        # Verify flag cleared
        await async_session.refresh(active_channel)
        assert active_channel.gemini_quota_exhausted is False

    async def test_channel_not_found_returns_400(self, client: AsyncClient, admin_api_key: str):
        """Test that non-existent channel ID returns 400 Bad Request."""
        fake_uuid = str(uuid4())
        response = await client.post(
            "/api/v1/admin/quota-reset",
            json={
                "channel_id": fake_uuid,
                "service": "youtube",
            },
            headers={"X-Admin-Key": admin_api_key},
        )

        assert response.status_code == 400
        assert f"Channel {fake_uuid} not found" in response.json()["detail"]

    @freeze_time("2026-01-25 08:00:00")  # Midnight PST = 08:00 UTC
    async def test_inactive_channel_gets_reset(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        inactive_channel: Channel,
        admin_api_key: str,
    ):
        """Test that inactive channel can be manually reset (emergency use case)."""
        response = await client.post(
            "/api/v1/admin/quota-reset",
            json={
                "channel_id": str(inactive_channel.id),
                "service": "youtube",
            },
            headers={"X-Admin-Key": admin_api_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify quota created even for inactive channel
        quota = await async_session.get(YouTubeQuotaUsage, (inactive_channel.id, date(2026, 1, 25)))
        assert quota is not None

    @freeze_time("2026-01-25 08:00:00")  # Midnight PST = 08:00 UTC
    async def test_date_defaults_to_today_pacific(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        active_channel: Channel,
        admin_api_key: str,
    ):
        """Test that date parameter defaults to today in Pacific timezone."""
        # Don't provide date parameter
        response = await client.post(
            "/api/v1/admin/quota-reset",
            json={
                "channel_id": str(active_channel.id),
                "service": "youtube",
            },
            headers={"X-Admin-Key": admin_api_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["date"] == "2026-01-25"  # Should be today in Pacific timezone

    @freeze_time("2026-01-25 08:00:00")  # Midnight PST = 08:00 UTC
    async def test_explicit_date_parameter(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        active_channel: Channel,
        admin_api_key: str,
    ):
        """Test that explicit date parameter is respected."""
        response = await client.post(
            "/api/v1/admin/quota-reset",
            json={
                "channel_id": str(active_channel.id),
                "service": "youtube",
                "date": "2026-01-20",
            },
            headers={"X-Admin-Key": admin_api_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["date"] == "2026-01-20"

        # Verify quota created for specified date
        quota = await async_session.get(YouTubeQuotaUsage, (active_channel.id, date(2026, 1, 20)))
        assert quota is not None

    @freeze_time("2026-01-25 08:00:00")  # Midnight PST = 08:00 UTC
    async def test_future_date_rejected(
        self,
        client: AsyncClient,
        active_channel: Channel,
        admin_api_key: str,
    ):
        """Test that future dates are rejected with 400 Bad Request."""
        response = await client.post(
            "/api/v1/admin/quota-reset",
            json={
                "channel_id": str(active_channel.id),
                "service": "youtube",
                "date": "2027-12-31",  # Future date
            },
            headers={"X-Admin-Key": admin_api_key},
        )

        assert response.status_code == 400
        assert "Cannot reset quota for future date" in response.json()["detail"]

    async def test_invalid_service_rejected(
        self,
        client: AsyncClient,
        active_channel: Channel,
        admin_api_key: str,
    ):
        """Test that invalid service parameter is rejected with 422."""
        response = await client.post(
            "/api/v1/admin/quota-reset",
            json={
                "channel_id": str(active_channel.id),
                "service": "invalid_service",  # Not 'youtube' or 'gemini'
            },
            headers={"X-Admin-Key": admin_api_key},
        )

        # Pydantic validation should reject this
        assert response.status_code == 422
