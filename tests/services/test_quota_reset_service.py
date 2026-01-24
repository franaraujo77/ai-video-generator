"""Tests for quota reset service.

Tests quota reset logic with time-mocking to simulate midnight Pacific Time resets.
Follows TDD pattern: write failing tests first, then implement to make them pass.
"""

import pytest
from datetime import date, datetime
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.models import Channel, YouTubeQuotaUsage, GeminiQuotaUsage
from app.services.quota_reset_service import reset_youtube_quotas, reset_gemini_quotas


@pytest.fixture
async def active_channel(async_session: AsyncSession) -> Channel:
    """Create an active channel for testing."""
    channel = Channel(
        id=uuid4(),
        channel_id="test_channel_1",
        channel_name="Test Channel",
        is_active=True,
        youtube_quota_exhausted=True,  # Start exhausted
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
        channel_id="inactive_channel",
        channel_name="Inactive Channel",
        is_active=False,
        youtube_quota_exhausted=False,
        gemini_quota_exhausted=False,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


class TestResetYouTubeQuotas:
    """Test YouTube quota reset functionality."""

    async def test_creates_new_quota_row_with_zero_usage(
        self, async_session: AsyncSession, active_channel: Channel
    ):
        """Test that reset creates new quota row with units_used=0."""
        reset_date = date(2026, 1, 25)

        # Execute reset
        reset_count = await reset_youtube_quotas(reset_date, async_session)

        # Verify new quota row created
        quota = await async_session.get(
            YouTubeQuotaUsage, (active_channel.id, reset_date)
        )
        assert quota is not None
        assert quota.units_used == 0
        assert quota.daily_limit == 10000
        assert reset_count == 1

    async def test_clears_quota_exhausted_flag(
        self, async_session: AsyncSession, active_channel: Channel
    ):
        """Test that reset clears youtube_quota_exhausted flag."""
        reset_date = date(2026, 1, 25)

        # Verify flag is set before reset
        assert active_channel.youtube_quota_exhausted is True

        # Execute reset
        await reset_youtube_quotas(reset_date, async_session)

        # Refresh channel and verify flag cleared
        await async_session.refresh(active_channel)
        assert active_channel.youtube_quota_exhausted is False

    async def test_only_resets_active_channels(
        self,
        async_session: AsyncSession,
        active_channel: Channel,
        inactive_channel: Channel,
    ):
        """Test that reset only affects active channels (is_active=True)."""
        reset_date = date(2026, 1, 25)

        # Execute reset
        reset_count = await reset_youtube_quotas(reset_date, async_session)

        # Verify only active channel was reset
        assert reset_count == 1

        # Verify active channel has quota row
        active_quota = await async_session.get(
            YouTubeQuotaUsage, (active_channel.id, reset_date)
        )
        assert active_quota is not None

        # Verify inactive channel has NO quota row
        inactive_quota = await async_session.get(
            YouTubeQuotaUsage, (inactive_channel.id, reset_date)
        )
        assert inactive_quota is None

    async def test_idempotent_reset_on_conflict_do_nothing(
        self, async_session: AsyncSession, active_channel: Channel
    ):
        """Test that running reset twice doesn't create duplicate rows."""
        reset_date = date(2026, 1, 25)

        # Run reset twice
        await reset_youtube_quotas(reset_date, async_session)
        await reset_youtube_quotas(reset_date, async_session)

        # Verify only one quota row exists
        result = await async_session.execute(
            select(YouTubeQuotaUsage).where(
                YouTubeQuotaUsage.channel_id == active_channel.id,
                YouTubeQuotaUsage.date == reset_date,
            )
        )
        quotas = result.scalars().all()
        assert len(quotas) == 1

    async def test_handles_multiple_channels(self, async_session: AsyncSession):
        """Test that reset handles multiple active channels."""
        # Create 3 active channels
        channels = []
        for i in range(3):
            channel = Channel(
                id=uuid4(),
                channel_id=f"channel_{i}",
                channel_name=f"Channel {i}",
                is_active=True,
                youtube_quota_exhausted=True,
            )
            async_session.add(channel)
            channels.append(channel)
        await async_session.commit()

        reset_date = date(2026, 1, 25)

        # Execute reset
        reset_count = await reset_youtube_quotas(reset_date, async_session)

        # Verify all 3 channels reset
        assert reset_count == 3

        # Verify quota rows for all channels
        for channel in channels:
            quota = await async_session.get(
                YouTubeQuotaUsage, (channel.id, reset_date)
            )
            assert quota is not None
            assert quota.units_used == 0

            # Verify flags cleared
            await async_session.refresh(channel)
            assert channel.youtube_quota_exhausted is False

    @freeze_time("2026-01-25 08:00:00")  # Midnight PST = 08:00 UTC (PST is UTC-8 in winter)
    async def test_timezone_handling_midnight_pst(
        self, async_session: AsyncSession, active_channel: Channel
    ):
        """Test timezone handling at midnight Pacific Time."""
        # Get Pacific midnight (when frozen at 08:00 UTC, Pacific is 00:00)
        pacific_tz = ZoneInfo("America/Los_Angeles")
        pacific_midnight = datetime.now(pacific_tz)
        reset_date = pacific_midnight.date()

        # Execute reset
        await reset_youtube_quotas(reset_date, async_session)

        # Verify quota created for correct date
        quota = await async_session.get(
            YouTubeQuotaUsage, (active_channel.id, reset_date)
        )
        assert quota is not None
        assert quota.date == date(2026, 1, 25)


class TestResetGeminiQuotas:
    """Test Gemini quota reset functionality."""

    async def test_creates_new_quota_row_with_zero_usage(
        self, async_session: AsyncSession, active_channel: Channel
    ):
        """Test that reset creates new quota row with requests_used=0."""
        reset_date = date(2026, 1, 25)

        # Execute reset
        reset_count = await reset_gemini_quotas(reset_date, async_session)

        # Verify new quota row created
        quota = await async_session.get(
            GeminiQuotaUsage, (active_channel.id, reset_date)
        )
        assert quota is not None
        assert quota.requests_used == 0
        assert quota.daily_limit == 1500
        assert reset_count == 1

    async def test_clears_quota_exhausted_flag(
        self, async_session: AsyncSession, active_channel: Channel
    ):
        """Test that reset clears gemini_quota_exhausted flag."""
        reset_date = date(2026, 1, 25)

        # Verify flag is set before reset
        assert active_channel.gemini_quota_exhausted is True

        # Execute reset
        await reset_gemini_quotas(reset_date, async_session)

        # Refresh channel and verify flag cleared
        await async_session.refresh(active_channel)
        assert active_channel.gemini_quota_exhausted is False

    async def test_only_resets_active_channels(
        self,
        async_session: AsyncSession,
        active_channel: Channel,
        inactive_channel: Channel,
    ):
        """Test that reset only affects active channels."""
        reset_date = date(2026, 1, 25)

        # Execute reset
        reset_count = await reset_gemini_quotas(reset_date, async_session)

        # Verify only active channel was reset
        assert reset_count == 1

        # Verify active channel has quota row
        active_quota = await async_session.get(
            GeminiQuotaUsage, (active_channel.id, reset_date)
        )
        assert active_quota is not None

        # Verify inactive channel has NO quota row
        inactive_quota = await async_session.get(
            GeminiQuotaUsage, (inactive_channel.id, reset_date)
        )
        assert inactive_quota is None

    async def test_idempotent_reset_on_conflict_do_nothing(
        self, async_session: AsyncSession, active_channel: Channel
    ):
        """Test that running reset twice doesn't create duplicate rows."""
        reset_date = date(2026, 1, 25)

        # Run reset twice
        await reset_gemini_quotas(reset_date, async_session)
        await reset_gemini_quotas(reset_date, async_session)

        # Verify only one quota row exists
        result = await async_session.execute(
            select(GeminiQuotaUsage).where(
                GeminiQuotaUsage.channel_id == active_channel.id,
                GeminiQuotaUsage.date == reset_date,
            )
        )
        quotas = result.scalars().all()
        assert len(quotas) == 1
