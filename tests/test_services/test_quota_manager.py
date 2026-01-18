"""Tests for YouTube quota management service (Story 4.5).

Tests cover:
    - check_youtube_quota: Pre-claim quota verification
    - record_youtube_quota: Post-operation quota recording
    - get_required_api: Status → API mapping
    - Alert threshold triggering (80%, 100%)
    - Per-channel quota isolation

References:
    - Story 4.5: Rate Limit Aware Task Selection
    - FR42: Pre-claim quota verification
    - FR34: API quota monitoring
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, YouTubeQuotaUsage
from app.services.quota_manager import (
    YOUTUBE_QUOTA_CRITICAL_THRESHOLD,
    YOUTUBE_QUOTA_WARNING_THRESHOLD,
    check_youtube_quota,
    get_required_api,
    record_youtube_quota,
)


@pytest.fixture
async def channel(async_session: AsyncSession) -> Channel:
    """Create test channel."""
    channel = Channel(
        channel_id="test_channel_1",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


class TestCheckYouTubeQuota:
    """Test check_youtube_quota function."""

    async def test_first_operation_today_returns_true(
        self, async_session: AsyncSession, channel: Channel
    ):
        """Scenario 1: First operation today - no quota record exists yet."""
        # No quota record exists
        result = await check_youtube_quota(channel.id, "upload", async_session)

        assert result is True

    async def test_quota_available_returns_true(
        self, async_session: AsyncSession, channel: Channel
    ):
        """Scenario 2: Quota available - operation would not exceed limit."""
        # Create quota record with 5000 units used (50% of 10,000 limit)
        quota = YouTubeQuotaUsage(
            channel_id=channel.id,
            date=date.today(),
            units_used=5000,
            daily_limit=10000,
        )
        async_session.add(quota)
        await async_session.commit()

        # Upload costs 1600 units → 5000 + 1600 = 6600 < 10000
        result = await check_youtube_quota(channel.id, "upload", async_session)

        assert result is True

    async def test_quota_exhausted_returns_false(
        self, async_session: AsyncSession, channel: Channel
    ):
        """Scenario 3: Quota exhausted - operation would exceed limit."""
        # Create quota record with 9500 units used (95% of 10,000 limit)
        quota = YouTubeQuotaUsage(
            channel_id=channel.id,
            date=date.today(),
            units_used=9500,
            daily_limit=10000,
        )
        async_session.add(quota)
        await async_session.commit()

        # Upload costs 1600 units → 9500 + 1600 = 11100 > 10000
        result = await check_youtube_quota(channel.id, "upload", async_session)

        assert result is False

    async def test_exactly_at_limit_returns_false(
        self, async_session: AsyncSession, channel: Channel
    ):
        """Scenario 4: Exactly at limit - operation would exceed."""
        # Create quota record with 8400 units used
        quota = YouTubeQuotaUsage(
            channel_id=channel.id,
            date=date.today(),
            units_used=8400,
            daily_limit=10000,
        )
        async_session.add(quota)
        await async_session.commit()

        # Upload costs 1600 units → 8400 + 1600 = 10000 = 10000
        # Should allow exactly at limit
        result = await check_youtube_quota(channel.id, "upload", async_session)

        assert result is True

        # But one more unit would exceed
        quota.units_used = 8401
        await async_session.commit()

        result = await check_youtube_quota(channel.id, "upload", async_session)

        assert result is False

    async def test_per_channel_isolation(self, async_session: AsyncSession, channel: Channel):
        """Scenario 5: Per-channel quota isolation."""
        # Create second channel
        channel2 = Channel(
            channel_id="test_channel_2",
            channel_name="Test Channel 2",
            is_active=True,
        )
        async_session.add(channel2)
        await async_session.commit()
        await async_session.refresh(channel2)

        # Exhaust quota for channel 1
        quota1 = YouTubeQuotaUsage(
            channel_id=channel.id,
            date=date.today(),
            units_used=9500,
            daily_limit=10000,
        )
        async_session.add(quota1)
        await async_session.commit()

        # Channel 1 quota exhausted
        result1 = await check_youtube_quota(channel.id, "upload", async_session)
        assert result1 is False

        # Channel 2 quota available (no record exists)
        result2 = await check_youtube_quota(channel2.id, "upload", async_session)
        assert result2 is True


class TestRecordYouTubeQuota:
    """Test record_youtube_quota function."""

    async def test_create_new_quota_record(self, async_session: AsyncSession, channel: Channel):
        """Scenario 6: First operation creates new quota record."""
        with patch("app.services.quota_manager.send_alert") as mock_alert:
            await record_youtube_quota(channel.id, "upload", async_session)

        # Verify quota record created
        stmt = select(YouTubeQuotaUsage).where(
            YouTubeQuotaUsage.channel_id == channel.id,
            YouTubeQuotaUsage.date == date.today(),
        )
        result = await async_session.execute(stmt)
        quota = result.scalar_one()

        assert quota.units_used == 1600  # Upload cost
        assert quota.daily_limit == 10000
        # No alert triggered (1600 / 10000 = 16%)
        mock_alert.assert_not_called()

    async def test_increment_existing_quota(self, async_session: AsyncSession, channel: Channel):
        """Scenario 7: Subsequent operation increments existing record."""
        # Create initial quota record
        quota = YouTubeQuotaUsage(
            channel_id=channel.id,
            date=date.today(),
            units_used=3000,
            daily_limit=10000,
        )
        async_session.add(quota)
        await async_session.commit()

        with patch("app.services.quota_manager.send_alert") as mock_alert:
            await record_youtube_quota(channel.id, "upload", async_session)

        # Verify quota incremented
        await async_session.refresh(quota)
        assert quota.units_used == 4600  # 3000 + 1600

        # No alert triggered (4600 / 10000 = 46%)
        mock_alert.assert_not_called()

    async def test_warning_alert_at_80_percent(self, async_session: AsyncSession, channel: Channel):
        """Scenario 8: WARNING alert triggered at 80% threshold."""
        # Create quota record at 70% (7000 / 10000)
        quota = YouTubeQuotaUsage(
            channel_id=channel.id,
            date=date.today(),
            units_used=7000,
            daily_limit=10000,
        )
        async_session.add(quota)
        await async_session.commit()

        with patch("app.services.quota_manager.send_alert") as mock_alert:
            # Upload costs 1600 → 7000 + 1600 = 8600 (86%)
            await record_youtube_quota(channel.id, "upload", async_session)

        # Verify quota updated
        await async_session.refresh(quota)
        assert quota.units_used == 8600

        # Verify WARNING alert sent
        mock_alert.assert_called_once()
        call_args = mock_alert.call_args[1]
        assert call_args["level"] == "WARNING"
        assert "86%" in call_args["message"] or "86.0%" in call_args["message"]

    async def test_critical_alert_at_100_percent(
        self, async_session: AsyncSession, channel: Channel
    ):
        """Scenario 9: CRITICAL alert triggered at 100% threshold."""
        # Create quota record at 90% (9000 / 10000)
        quota = YouTubeQuotaUsage(
            channel_id=channel.id,
            date=date.today(),
            units_used=9000,
            daily_limit=10000,
        )
        async_session.add(quota)
        await async_session.commit()

        with patch("app.services.quota_manager.send_alert") as mock_alert:
            # Upload costs 1600 → 9000 + 1600 = 10600 (106% - over limit!)
            await record_youtube_quota(channel.id, "upload", async_session)

        # Verify quota updated
        await async_session.refresh(quota)
        assert quota.units_used == 10600

        # Verify CRITICAL alert sent
        mock_alert.assert_called_once()
        call_args = mock_alert.call_args[1]
        assert call_args["level"] == "CRITICAL"
        assert "exhausted" in call_args["message"].lower()

    async def test_invalid_operation_raises_error(
        self, async_session: AsyncSession, channel: Channel
    ):
        """Scenario 10: Invalid operation type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid YouTube operation"):
            await record_youtube_quota(channel.id, "invalid_op", async_session)

    async def test_operation_costs(self, async_session: AsyncSession, channel: Channel):
        """Scenario 11: Different operations have different costs."""
        with patch("app.services.quota_manager.send_alert"):
            # Upload: 1600 units
            await record_youtube_quota(channel.id, "upload", async_session)

            stmt = select(YouTubeQuotaUsage).where(
                YouTubeQuotaUsage.channel_id == channel.id,
                YouTubeQuotaUsage.date == date.today(),
            )
            result = await async_session.execute(stmt)
            quota = result.scalar_one()
            assert quota.units_used == 1600

            # Update: 50 units
            await record_youtube_quota(channel.id, "update", async_session)
            await async_session.refresh(quota)
            assert quota.units_used == 1650  # 1600 + 50

            # List: 1 unit
            await record_youtube_quota(channel.id, "list", async_session)
            await async_session.refresh(quota)
            assert quota.units_used == 1651  # 1650 + 1

            # Search: 100 units
            await record_youtube_quota(channel.id, "search", async_session)
            await async_session.refresh(quota)
            assert quota.units_used == 1751  # 1651 + 100


class TestGetRequiredAPI:
    """Test get_required_api function."""

    def test_pending_requires_gemini(self):
        """Scenario 12: pending status requires Gemini (asset generation)."""
        assert get_required_api("pending") == "gemini"

    def test_assets_approved_requires_none(self):
        """Scenario 13: assets_approved requires no external API (internal composite creation)."""
        assert get_required_api("assets_approved") is None

    def test_composites_ready_requires_kling(self):
        """Scenario 14: composites_ready requires Kling (video generation)."""
        assert get_required_api("composites_ready") == "kling"

    def test_video_approved_requires_elevenlabs(self):
        """Scenario 15: video_approved requires ElevenLabs (audio generation)."""
        assert get_required_api("video_approved") == "elevenlabs"

    def test_audio_approved_requires_none(self):
        """Scenario 16: audio_approved requires no external API (internal FFmpeg assembly)."""
        assert get_required_api("audio_approved") is None

    def test_final_review_requires_youtube(self):
        """Scenario 17: final_review requires YouTube (upload)."""
        assert get_required_api("final_review") == "youtube"

    def test_unknown_status_returns_none(self):
        """Scenario 18: Unknown status returns None (no API required)."""
        assert get_required_api("unknown_status") is None
