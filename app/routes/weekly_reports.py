"""Weekly metrics reporting API endpoints (Story 8.6).

Provides HTTP endpoints for weekly success rate metrics and trend analysis.
Enables visibility into pipeline health, success rates, and failure patterns.

Endpoints:
- GET /api/v1/channels/{channel_id}/weekly-metrics - List weekly metrics with pagination
- GET /api/v1/channels/{channel_id}/weekly-metrics/{week_date} - Single week detail
- GET /api/v1/channels/{channel_id}/success-rate-trend - Trend analysis
- GET /api/v1/reports/weekly-summary - Cross-channel weekly summary
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Channel
from app.services.weekly_metrics_service import (
    get_success_rate_trend,
    get_week_starting_date,
    get_weekly_metrics,
    get_weekly_metrics_range,
)

router = APIRouter(prefix="/api/v1", tags=["weekly-reports"])


class WeeklyMetricsResponse(BaseModel):
    """Response schema for weekly metrics."""

    channel_id: UUID
    week_starting_date: str  # ISO date format
    total_videos_processed: int
    successful_videos: int
    success_rate: Decimal = Field(description="Success rate percentage (0.00-100.00)")
    avg_processing_time_seconds: int | None
    auto_recovery_rate: Decimal | None
    transient_failures: int
    permanent_failures: int
    unknown_failures: int
    failed_at_assets: int
    failed_at_video: int
    failed_at_audio: int
    failed_at_upload: int
    calculated_at: str  # ISO datetime format
    updated_at: str  # ISO datetime format


class WeeklyMetricsListResponse(BaseModel):
    """Response schema for paginated weekly metrics list."""

    channel_id: UUID
    metrics: list[WeeklyMetricsResponse]
    total_count: int
    start_date: str  # ISO date format
    end_date: str  # ISO date format


class SuccessRateTrendResponse(BaseModel):
    """Response schema for success rate trend analysis."""

    channel_id: UUID
    weeks: int
    trend: list[dict] = Field(
        description="List of {week_starting_date, success_rate, total_videos, successful_videos}"
    )


class WeekOverWeekComparisonResponse(BaseModel):
    """Response schema for week-over-week comparison."""

    channel_id: UUID
    current_week: dict | None = Field(
        description="Current week metrics (week_starting_date, success_rate, ...)"
    )
    previous_week: dict | None = Field(
        description="Previous week metrics (week_starting_date, success_rate, ...)"
    )
    delta: dict | None = Field(
        description="Week-over-week changes (success_rate_change, total_videos_change, ...)"
    )


class FailurePatternAnalysisResponse(BaseModel):
    """Response schema for failure pattern analysis."""

    channel_id: UUID
    weeks: int
    time_range: dict = Field(description="Analysis time range (start_week, end_week)")
    category_breakdown: dict = Field(
        description="Failures by category (transient, permanent, unknown)"
    )
    stage_breakdown: dict = Field(description="Failures by stage (assets, video, audio, upload)")
    most_common_category: str
    most_common_stage: str


class WeeklySummaryResponse(BaseModel):
    """Response schema for cross-channel weekly summary."""

    week_starting_date: str  # ISO date format
    total_channels: int
    channels_meeting_target: int = Field(description="Channels with success rate >= 90%")
    overall_success_rate: Decimal = Field(description="Weighted average across all channels")
    total_videos_processed: int
    total_successful_videos: int


@router.get(
    "/channels/{channel_id}/weekly-metrics",
    response_model=WeeklyMetricsListResponse,
    status_code=status.HTTP_200_OK,
    summary="List weekly metrics for channel",
    description="Returns paginated list of weekly metrics within date range",
)
async def list_weekly_metrics(
    channel_id: UUID,
    start_date: date = Query(description="Range start date (Monday)"),
    end_date: date = Query(description="Range end date (Monday)"),
    db: AsyncSession = Depends(get_session),
) -> WeeklyMetricsListResponse:
    """List weekly metrics for a channel within date range.

    Args:
        channel_id: UUID of the channel
        start_date: Range start date (Monday)
        end_date: Range end date (Monday)
        db: Database session (injected)

    Returns:
        WeeklyMetricsListResponse with paginated metrics

    Raises:
        HTTPException: 404 if channel not found
    """
    # Verify channel exists
    stmt = select(Channel).where(Channel.id == channel_id)
    result = await db.execute(stmt)
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )

    # Get metrics in range
    metrics_list = await get_weekly_metrics_range(channel_id, start_date, end_date, db)

    # Convert to response models
    metrics_responses = [
        WeeklyMetricsResponse(
            channel_id=m.channel_id,
            week_starting_date=m.week_starting_date.isoformat(),
            total_videos_processed=m.total_videos_processed,
            successful_videos=m.successful_videos,
            success_rate=m.success_rate,
            avg_processing_time_seconds=m.avg_processing_time_seconds,
            auto_recovery_rate=m.auto_recovery_rate,
            transient_failures=m.transient_failures,
            permanent_failures=m.permanent_failures,
            unknown_failures=m.unknown_failures,
            failed_at_assets=m.failed_at_assets,
            failed_at_video=m.failed_at_video,
            failed_at_audio=m.failed_at_audio,
            failed_at_upload=m.failed_at_upload,
            calculated_at=m.calculated_at.isoformat(),
            updated_at=m.updated_at.isoformat(),
        )
        for m in metrics_list
    ]

    return WeeklyMetricsListResponse(
        channel_id=channel_id,
        metrics=metrics_responses,
        total_count=len(metrics_responses),
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )


@router.get(
    "/channels/{channel_id}/weekly-metrics/{week_date}",
    response_model=WeeklyMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single week metrics",
    description="Returns detailed metrics for a specific week",
)
async def get_single_week_metrics(
    channel_id: UUID,
    week_date: date,
    db: AsyncSession = Depends(get_session),
) -> WeeklyMetricsResponse:
    """Get metrics for a specific week.

    Args:
        channel_id: UUID of the channel
        week_date: Week starting date (Monday)
        db: Database session (injected)

    Returns:
        WeeklyMetricsResponse with week details

    Raises:
        HTTPException: 404 if channel or metrics not found
    """
    # Verify channel exists
    stmt = select(Channel).where(Channel.id == channel_id)
    result = await db.execute(stmt)
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )

    # Normalize to Monday (ISO week start)
    week_start = get_week_starting_date(week_date)

    # Get metrics for week
    metrics = await get_weekly_metrics(channel_id, week_start, db)

    if not metrics:
        # Include normalized date in error message for clarity
        if week_date != week_start:
            detail = (
                f"No metrics found for channel {channel_id} week {week_start} "
                f"(requested date {week_date} normalized to Monday)"
            )
        else:
            detail = f"No metrics found for channel {channel_id} week {week_start}"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )

    return WeeklyMetricsResponse(
        channel_id=metrics.channel_id,
        week_starting_date=metrics.week_starting_date.isoformat(),
        total_videos_processed=metrics.total_videos_processed,
        successful_videos=metrics.successful_videos,
        success_rate=metrics.success_rate,
        avg_processing_time_seconds=metrics.avg_processing_time_seconds,
        auto_recovery_rate=metrics.auto_recovery_rate,
        transient_failures=metrics.transient_failures,
        permanent_failures=metrics.permanent_failures,
        unknown_failures=metrics.unknown_failures,
        failed_at_assets=metrics.failed_at_assets,
        failed_at_video=metrics.failed_at_video,
        failed_at_audio=metrics.failed_at_audio,
        failed_at_upload=metrics.failed_at_upload,
        calculated_at=metrics.calculated_at.isoformat(),
        updated_at=metrics.updated_at.isoformat(),
    )


@router.get(
    "/channels/{channel_id}/success-rate-trend",
    response_model=SuccessRateTrendResponse,
    status_code=status.HTTP_200_OK,
    summary="Get success rate trend",
    description="Returns success rate trend analysis for charting (default 12 weeks)",
)
async def get_channel_success_rate_trend(
    channel_id: UUID,
    weeks: int = Query(default=12, ge=1, le=52, description="Number of recent weeks"),
    db: AsyncSession = Depends(get_session),
) -> SuccessRateTrendResponse:
    """Get success rate trend for charting.

    Args:
        channel_id: UUID of the channel
        weeks: Number of recent weeks to include (default: 12, max: 52)
        db: Database session (injected)

    Returns:
        SuccessRateTrendResponse with trend data for charting

    Raises:
        HTTPException: 404 if channel not found
    """
    # Verify channel exists
    stmt = select(Channel).where(Channel.id == channel_id)
    result = await db.execute(stmt)
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )

    # Get trend data
    trend = await get_success_rate_trend(channel_id, db, weeks=weeks)

    return SuccessRateTrendResponse(
        channel_id=channel_id,
        weeks=weeks,
        trend=trend,
    )


@router.get(
    "/reports/weekly-summary",
    response_model=WeeklySummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get cross-channel weekly summary",
    description="Returns aggregated weekly metrics across all active channels",
)
async def get_weekly_summary(
    week_date: date = Query(description="Week starting date (defaults to last completed week)"),
    db: AsyncSession = Depends(get_session),
) -> WeeklySummaryResponse:
    """Get cross-channel weekly summary for specified week.

    Args:
        week_date: Week starting date (Monday). Defaults to last completed week.
        db: Database session (injected)

    Returns:
        WeeklySummaryResponse with aggregated metrics across all channels

    Raises:
        HTTPException: 404 if no metrics found for week
    """
    # Normalize to Monday (ISO week start)
    week_start = get_week_starting_date(week_date)

    # Get all active channels
    stmt = select(Channel).where(Channel.is_active == True)  # noqa: E712
    result = await db.execute(stmt)
    channels = list(result.scalars().all())

    if not channels:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active channels found",
        )

    # Get metrics for all channels for this week
    metrics_list = []
    for channel in channels:
        metrics = await get_weekly_metrics(channel.id, week_start, db)
        if metrics:
            metrics_list.append(metrics)

    if not metrics_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No metrics found for week {week_start}",
        )

    # Calculate aggregated metrics
    total_videos = sum(m.total_videos_processed for m in metrics_list)
    total_successful = sum(m.successful_videos for m in metrics_list)
    overall_success_rate = (
        Decimal(str(total_successful / total_videos * 100)) if total_videos > 0 else Decimal("0.00")
    )

    # Count channels meeting target (>= 90%)
    channels_meeting_target = sum(1 for m in metrics_list if m.success_rate >= Decimal("90.00"))

    return WeeklySummaryResponse(
        week_starting_date=week_start.isoformat(),
        total_channels=len(metrics_list),
        channels_meeting_target=channels_meeting_target,
        overall_success_rate=overall_success_rate,
        total_videos_processed=total_videos,
        total_successful_videos=total_successful,
    )
