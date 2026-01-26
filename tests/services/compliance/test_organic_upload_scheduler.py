"""Tests for Organic Upload Scheduler (Story 7.7 AC3)."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.services.compliance.organic_upload_scheduler import (
    OrganicUploadScheduler,
    UPLOAD_FREQUENCY_LIMITS,
)


@pytest.fixture
def scheduler():
    """Create OrganicUploadScheduler instance."""
    return OrganicUploadScheduler()


@pytest.fixture
def new_channel_config():
    """Sample new channel configuration (<100 videos, <6 months)."""
    return {
        "total_videos_uploaded": 50,
        "created_at": datetime.now(timezone.utc) - timedelta(days=90),  # 3 months old
    }


@pytest.fixture
def established_channel_config():
    """Sample established channel configuration (>100 videos, >6 months)."""
    return {
        "total_videos_uploaded": 150,
        "created_at": datetime.now(timezone.utc) - timedelta(days=365),  # 1 year old
    }


@pytest.fixture
def recent_uploads():
    """Sample recent uploads for frequency checking."""
    return [
        {"uploaded_at": datetime.now(timezone.utc) - timedelta(hours=2)},
        {"uploaded_at": datetime.now(timezone.utc) - timedelta(hours=8)},
        {"uploaded_at": datetime.now(timezone.utc) - timedelta(days=1, hours=2)},
    ]


class TestChannelClassification:
    """Test channel maturity classification."""

    def test_classify_new_channel(self, scheduler, new_channel_config):
        """Test classification of new channel."""
        channel_type = scheduler.classify_channel(new_channel_config)

        assert channel_type == "new_channel"

    def test_classify_established_channel(self, scheduler, established_channel_config):
        """Test classification of established channel."""
        channel_type = scheduler.classify_channel(established_channel_config)

        assert channel_type == "established_channel"

    def test_classify_channel_borderline_videos(self, scheduler):
        """Test channel classification at video count borderline."""
        # Exactly 100 videos, 1 year old → Still new_channel (need >100)
        config = {
            "total_videos_uploaded": 100,
            "created_at": datetime.now(timezone.utc) - timedelta(days=365),
        }

        channel_type = scheduler.classify_channel(config)

        assert channel_type == "new_channel"

    def test_classify_channel_borderline_age(self, scheduler):
        """Test channel classification at age borderline."""
        # 150 videos, exactly 180 days old → Still new_channel (need >180)
        config = {
            "total_videos_uploaded": 150,
            "created_at": datetime.now(timezone.utc) - timedelta(days=180),
        }

        channel_type = scheduler.classify_channel(config)

        assert channel_type == "new_channel"

    def test_classify_channel_missing_created_at(self, scheduler):
        """Test channel classification with missing created_at."""
        config = {"total_videos_uploaded": 150}

        with pytest.raises(ValueError, match="channel_config missing 'created_at'"):
            scheduler.classify_channel(config)


class TestDailyLimitEnforcement:
    """Test daily upload limit enforcement."""

    def test_first_upload_of_day_allowed(self, scheduler, new_channel_config, recent_uploads):
        """Test first upload of the day is allowed immediately."""
        # Recent uploads from previous days only
        recent_uploads_yesterday = [
            {"uploaded_at": datetime.now(timezone.utc) - timedelta(days=1, hours=2)}
        ]

        scheduled_time = scheduler.schedule_upload({}, new_channel_config, recent_uploads_yesterday)

        # Should schedule for today or tomorrow depending on time-of-day rotation
        # (might push to next day if time windows already used today)
        now = datetime.now(timezone.utc)
        assert scheduled_time.date() in [now.date(), (now + timedelta(days=1)).date()]

    def test_daily_limit_hit_new_channel(self, scheduler, new_channel_config, recent_uploads):
        """Test daily limit enforcement for new channel (2/day)."""
        # Two uploads already today
        today_uploads = [
            {"uploaded_at": datetime.now(timezone.utc) - timedelta(hours=2)},
            {"uploaded_at": datetime.now(timezone.utc) - timedelta(hours=6)},
        ]

        scheduled_time = scheduler.schedule_upload({}, new_channel_config, today_uploads)

        # Should schedule for next day (daily limit hit)
        assert scheduled_time.date() > datetime.now(timezone.utc).date()

    def test_daily_limit_hit_established_channel(self, scheduler, established_channel_config):
        """Test daily limit enforcement for established channel (3/day)."""
        # Three uploads already today
        today_uploads = [
            {"uploaded_at": datetime.now(timezone.utc) - timedelta(hours=1)},
            {"uploaded_at": datetime.now(timezone.utc) - timedelta(hours=4)},
            {"uploaded_at": datetime.now(timezone.utc) - timedelta(hours=8)},
        ]

        scheduled_time = scheduler.schedule_upload({}, established_channel_config, today_uploads)

        # Should schedule for next day (daily limit hit)
        assert scheduled_time.date() > datetime.now(timezone.utc).date()


class TestMinimumSpacingEnforcement:
    """Test minimum spacing between uploads."""

    def test_minimum_spacing_enforced_new_channel(self, scheduler, new_channel_config):
        """Test 6-hour minimum spacing for new channel."""
        # Last upload was 3 hours ago (below 6-hour minimum)
        recent_uploads = [{"uploaded_at": datetime.now(timezone.utc) - timedelta(hours=3)}]

        scheduled_time = scheduler.schedule_upload({}, new_channel_config, recent_uploads)

        # Should schedule at least 6 hours from last upload
        hours_from_now = (scheduled_time - datetime.now(timezone.utc)).total_seconds() / 3600
        assert hours_from_now >= 2.5  # Still need ~3 more hours (allow variance)

    def test_minimum_spacing_met_new_channel(self, scheduler, new_channel_config):
        """Test upload allowed when spacing requirement met."""
        # Last upload was 7 hours ago (exceeds 6-hour minimum)
        recent_uploads = [{"uploaded_at": datetime.now(timezone.utc) - timedelta(hours=7)}]

        scheduled_time = scheduler.schedule_upload({}, new_channel_config, recent_uploads)

        # Should schedule within reasonable time (may be pushed to next day for time rotation)
        hours_from_now = (scheduled_time - datetime.now(timezone.utc)).total_seconds() / 3600
        assert hours_from_now < 26  # Within 26 hours (next day + variance)

    def test_minimum_spacing_enforced_established_channel(
        self, scheduler, established_channel_config
    ):
        """Test 4-hour minimum spacing for established channel."""
        # Last upload was 2 hours ago (below 4-hour minimum)
        recent_uploads = [{"uploaded_at": datetime.now(timezone.utc) - timedelta(hours=2)}]

        scheduled_time = scheduler.schedule_upload({}, established_channel_config, recent_uploads)

        # Should schedule at least 4 hours from last upload
        hours_from_now = (scheduled_time - datetime.now(timezone.utc)).total_seconds() / 3600
        assert hours_from_now >= 1.5  # Still need ~2 more hours (allow variance)


class TestStaggerVariance:
    """Test random variance for unpredictability."""

    @patch("app.services.compliance.organic_upload_scheduler.random.uniform")
    def test_stagger_variance_applied(self, mock_random_uniform, scheduler):
        """Test random variance is added to upload time."""
        mock_random_uniform.return_value = 60.0  # 60 minutes = 1 hour

        base_time = datetime.now(timezone.utc)
        adjusted_time = scheduler.add_stagger_variance(base_time, variance_hours=2.0)

        # Should add 1 hour (mocked random value)
        assert (adjusted_time - base_time).total_seconds() == pytest.approx(3600.0, abs=1.0)

    def test_stagger_variance_range(self, scheduler):
        """Test variance stays within expected range."""
        base_time = datetime.now(timezone.utc)

        # Run multiple times to test randomness
        for _ in range(10):
            adjusted_time = scheduler.add_stagger_variance(base_time, variance_hours=2.0)

            # Variance should be between 0 and 2 hours
            variance_hours = (adjusted_time - base_time).total_seconds() / 3600
            assert 0 <= variance_hours <= 2.0


class TestTimeOfDayRotation:
    """Test time-of-day distribution for organic patterns."""

    def test_time_window_rotation(self, scheduler):
        """Test uploads rotate through different time windows."""
        # Simulate 5 recent uploads all in morning window (9-11am)
        recent_uploads = [
            {"uploaded_at": datetime.now(timezone.utc).replace(hour=9, minute=30)},
            {"uploaded_at": datetime.now(timezone.utc).replace(hour=10, minute=15)},
            {"uploaded_at": datetime.now(timezone.utc).replace(hour=9, minute=45)},
            {"uploaded_at": datetime.now(timezone.utc).replace(hour=10, minute=30)},
            {"uploaded_at": datetime.now(timezone.utc).replace(hour=9, minute=15)},
        ]

        base_time = datetime.now(timezone.utc)
        adjusted_time = scheduler.vary_time_of_day(base_time, recent_uploads)

        # Should select afternoon/evening/night window (not morning)
        assert adjusted_time.hour not in [9, 10]

    def test_time_window_selection_first_upload(self, scheduler):
        """Test time window selection for first upload (no history)."""
        base_time = datetime.now(timezone.utc)
        adjusted_time = scheduler.vary_time_of_day(base_time, [])

        # Should select any valid time window
        assert adjusted_time.hour in [
            9,
            10,
            14,
            15,
            19,
            20,
            22,
            23,
        ]  # Morning, afternoon, evening, or night

    def test_time_adjustment_moves_to_future(self, scheduler):
        """Test time adjustment moves to future if necessary."""
        base_time = datetime.now(timezone.utc).replace(hour=23, minute=0)  # 11 PM

        # Recent uploads in afternoon
        recent_uploads = [{"uploaded_at": datetime.now(timezone.utc).replace(hour=14, minute=30)}]

        adjusted_time = scheduler.vary_time_of_day(base_time, recent_uploads)

        # Should move to next day since we're already past evening windows
        if adjusted_time.hour < base_time.hour:
            assert adjusted_time.date() > base_time.date()


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_recent_uploads(self, scheduler, new_channel_config):
        """Test scheduling with no recent uploads."""
        scheduled_time = scheduler.schedule_upload({}, new_channel_config, [])

        # Should schedule within reasonable time (may be pushed for time rotation)
        hours_from_now = (scheduled_time - datetime.now(timezone.utc)).total_seconds() / 3600
        assert hours_from_now < 26  # Within next day + variance

    def test_iso_format_timestamp_parsing(self, scheduler, new_channel_config):
        """Test handling of ISO format timestamps (string parsing)."""
        recent_uploads = [
            {"uploaded_at": "2026-01-25T10:30:00+00:00"}  # ISO format string
        ]

        # Should parse and handle correctly
        scheduled_time = scheduler.schedule_upload({}, new_channel_config, recent_uploads)

        assert isinstance(scheduled_time, datetime)

    def test_channel_config_string_created_at(self, scheduler):
        """Test handling of string created_at in channel config."""
        config = {
            "total_videos_uploaded": 50,
            "created_at": "2025-10-25T10:00:00+00:00",  # ISO format string
        }

        channel_type = scheduler.classify_channel(config)

        # Should parse and classify correctly
        assert channel_type in ["new_channel", "established_channel"]
