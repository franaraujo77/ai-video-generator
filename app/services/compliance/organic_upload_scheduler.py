"""Organic upload frequency throttling for YouTube Partner Program compliance.

Schedules uploads with human-like patterns to avoid spam detection:
- Daily limits: 2-3 videos per day (channel age dependent)
- Minimum spacing: 4-6 hours between uploads
- Stagger variance: 2-hour randomness for unpredictability
- Time-of-day rotation: Morning/afternoon/evening/night distribution

Prevents YouTube's spam detection from flagging automated upload patterns.
"""

import random
from datetime import datetime, timedelta, timezone

import structlog

log = structlog.get_logger(__name__)

# Upload frequency limits based on channel maturity
UPLOAD_FREQUENCY_LIMITS = {
    "new_channel": {  # <100 videos, <6 months old
        "daily_max": 2,
        "weekly_max": 10,
        "min_hours_between": 6,
        "stagger_variance_hours": 2,
    },
    "established_channel": {  # >100 videos, >6 months old
        "daily_max": 3,
        "weekly_max": 15,
        "min_hours_between": 4,
        "stagger_variance_hours": 2,
    },
}

# Time-of-day windows (24-hour format)
TIME_WINDOWS = {
    "morning": (9, 11),  # 9-11 AM
    "afternoon": (14, 16),  # 2-4 PM
    "evening": (19, 21),  # 7-9 PM
    "night": (22, 24),  # 10 PM-midnight
}


class OrganicUploadScheduler:
    """Schedule uploads with organic timing patterns to avoid spam detection.

    YouTube's spam detection flags accounts based on:
    - High-frequency uploads with low engagement
    - Bulk upload patterns (dozens daily)
    - Predictable timing patterns (always same time)
    """

    def schedule_upload(
        self,
        video_metadata: dict,
        channel_config: dict,
        recent_uploads: list[dict],
    ) -> datetime:
        """Schedule upload with organic timing patterns.

        Args:
            video_metadata: Current video metadata
            channel_config: Channel configuration with total_videos_uploaded, created_at
            recent_uploads: Recent uploads with uploaded_at timestamps

        Returns:
            Datetime of next available upload slot

        Raises:
            ValueError: If channel_config missing required fields
        """
        # Classify channel maturity
        channel_type = self.classify_channel(channel_config)
        limits = UPLOAD_FREQUENCY_LIMITS[channel_type]

        log.info(
            "scheduling_upload",
            channel_type=channel_type,
            daily_max=limits["daily_max"],
            min_hours_between=limits["min_hours_between"],
        )

        # Check daily limit
        today = datetime.now(timezone.utc).date()
        today_uploads = []
        for u in recent_uploads:
            uploaded_at = u.get("uploaded_at", datetime.min)

            # Handle string timestamps
            if isinstance(uploaded_at, str):
                uploaded_at = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00"))

            # Ensure timezone-aware
            if uploaded_at.tzinfo is None:
                uploaded_at = uploaded_at.replace(tzinfo=timezone.utc)

            if uploaded_at.date() == today:
                today_uploads.append(u)

        if len(today_uploads) >= limits["daily_max"]:
            # Daily limit hit - schedule for next day
            next_slot = datetime.now(timezone.utc).replace(
                hour=9, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)

            log.warning(
                "daily_limit_hit",
                uploads_today=len(today_uploads),
                daily_max=limits["daily_max"],
                scheduled_for=next_slot.isoformat(),
            )

            return self.add_stagger_variance(next_slot, limits["stagger_variance_hours"])

        # Check minimum spacing between uploads
        if recent_uploads:
            last_upload_time = recent_uploads[0].get("uploaded_at", datetime.min)

            if isinstance(last_upload_time, str):
                # Parse ISO format timestamp
                last_upload_time = datetime.fromisoformat(last_upload_time.replace("Z", "+00:00"))

            # Ensure timezone-aware
            if last_upload_time.tzinfo is None:
                last_upload_time = last_upload_time.replace(tzinfo=timezone.utc)

            min_next_time = last_upload_time + timedelta(hours=limits["min_hours_between"])

            now = datetime.now(timezone.utc)
            if now < min_next_time:
                # Must wait for minimum spacing
                next_slot = min_next_time

                log.info(
                    "upload_throttled",
                    hours_since_last=((now - last_upload_time).total_seconds() / 3600),
                    min_hours_required=limits["min_hours_between"],
                    scheduled_for=next_slot.isoformat(),
                )
            else:
                # Can upload now
                next_slot = now
        else:
            # First upload - schedule now
            next_slot = datetime.now(timezone.utc)

        # Add stagger variance (human-like randomness)
        next_slot = self.add_stagger_variance(next_slot, limits["stagger_variance_hours"])

        # Rotate time of day to avoid predictable patterns
        next_slot = self.vary_time_of_day(next_slot, recent_uploads)

        log.info(
            "upload_scheduled",
            scheduled_time=next_slot.isoformat(),
            hours_from_now=(next_slot - datetime.now(timezone.utc)).total_seconds() / 3600,
        )

        return next_slot

    def add_stagger_variance(self, base_time: datetime, variance_hours: float) -> datetime:
        """Add random variance to upload time (human-like unpredictability).

        Args:
            base_time: Base upload time
            variance_hours: Maximum variance in hours (e.g., 2 hours)

        Returns:
            Adjusted datetime with random variance added
        """
        variance_minutes = random.uniform(0, variance_hours * 60) # noqa: S311
        adjusted_time = base_time + timedelta(minutes=variance_minutes)

        log.debug(
            "stagger_variance_applied",
            variance_minutes=variance_minutes,
            original_time=base_time.isoformat(),
            adjusted_time=adjusted_time.isoformat(),
        )

        return adjusted_time

    def vary_time_of_day(self, base_time: datetime, recent_uploads: list[dict]) -> datetime:
        """Rotate upload times to avoid predictable patterns.

        Distributes uploads across time windows:
        - Morning (9-11am)
        - Afternoon (2-4pm)
        - Evening (7-9pm)
        - Night (10pm-midnight)

        Args:
            base_time: Proposed upload time
            recent_uploads: Recent uploads for pattern analysis

        Returns:
            Adjusted datetime in least-used time window
        """
        # Extract hour-of-day from recent uploads
        recent_hours = []
        for upload in recent_uploads[-5:]:  # Last 5 uploads
            uploaded_at = upload.get("uploaded_at")

            if isinstance(uploaded_at, str):
                uploaded_at = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00"))

            if uploaded_at:
                recent_hours.append(uploaded_at.hour)

        # Count usage of each time window
        window_usage = {
            window: sum(1 for h in recent_hours if start <= h < end)
            for window, (start, end) in TIME_WINDOWS.items()
        }

        # Find least-used window
        least_used_window = min(window_usage, key=window_usage.get)
        start_hour, end_hour = TIME_WINDOWS[least_used_window]

        log.debug(
            "time_window_selection",
            window_usage=window_usage,
            selected_window=least_used_window,
        )

        # Adjust base_time to fall within least-used window
        target_hour = random.randint(start_hour, end_hour - 1) # noqa: S311
        target_minute = random.randint(0, 59) # noqa: S311

        adjusted_time = base_time.replace(
            hour=target_hour, minute=target_minute, second=0, microsecond=0
        )

        # If adjusted time is in the past, move to next day
        now = datetime.now(timezone.utc)
        if adjusted_time < now:
            adjusted_time += timedelta(days=1)

        return adjusted_time

    def classify_channel(self, channel_config: dict) -> str:
        """Classify channel as new or established.

        Args:
            channel_config: Channel configuration with total_videos_uploaded, created_at

        Returns:
            "new_channel" or "established_channel"

        Raises:
            ValueError: If required fields missing
        """
        total_videos = channel_config.get("total_videos_uploaded", 0)
        created_at = channel_config.get("created_at")

        if created_at is None:
            raise ValueError("channel_config missing 'created_at' field")

        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        # Ensure both datetimes are timezone-aware for comparison
        now = datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        channel_age_days = (now - created_at).days

        # Established: >100 videos AND >180 days old
        if total_videos > 100 and channel_age_days > 180:
            return "established_channel"
        else:
            return "new_channel"
