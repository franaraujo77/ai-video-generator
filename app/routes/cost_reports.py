"""Cost reporting API endpoints (Story 8.2).

Provides HTTP endpoints for cost tracking queries and trend analysis.
Enables visibility into video production costs at task and channel level.

Endpoints:
- GET /api/v1/tasks/{task_id}/costs - Cost breakdown for specific task
- GET /api/v1/channels/{channel_id}/cost-summary - Channel cost aggregation
- GET /api/v1/reports/cost-trends - Cost trends over time
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.cost_tracker import (
    get_average_cost_per_video,
    get_channel_cost_summary,
    get_task_cost_breakdown,
    get_task_total_cost,
)
from app.services.cost_validation import validate_task_costs

router = APIRouter(prefix="/api/v1", tags=["cost-reports"])


class TaskCostBreakdown(BaseModel):
    """Response schema for task cost breakdown."""

    task_id: UUID
    total_cost_usd: Decimal
    breakdown: dict[str, Decimal] = Field(
        description="Cost breakdown by component (gemini_assets, kling_video, etc.)"
    )


class ChannelCostSummary(BaseModel):
    """Response schema for channel cost summary."""

    channel_id: UUID
    total_cost_usd: Decimal
    video_count: int
    avg_cost_per_video: Decimal
    breakdown_by_component: dict[str, Decimal]
    start_date: datetime | None = None
    end_date: datetime | None = None


class CostTrendsResponse(BaseModel):
    """Response schema for cost trends."""

    channel_id: UUID
    days: int
    avg_cost_per_video: Decimal


@router.get(
    "/tasks/{task_id}/costs",
    response_model=TaskCostBreakdown,
    status_code=status.HTTP_200_OK,
    summary="Get task cost breakdown",
    description="Returns component-level cost breakdown for a specific task",
)
async def get_task_costs(
    task_id: UUID,
    db: AsyncSession = Depends(get_session),
) -> TaskCostBreakdown:
    """Get cost breakdown for a specific task.

    Args:
        task_id: UUID of the task
        db: Database session (injected)

    Returns:
        TaskCostBreakdown with total and component breakdown

    Raises:
        HTTPException: 404 if no cost data found for task
    """
    breakdown = await get_task_cost_breakdown(db, task_id)
    total = await get_task_total_cost(db, task_id)

    if not breakdown:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No cost data found for task {task_id}",
        )

    return TaskCostBreakdown(
        task_id=task_id,
        total_cost_usd=total,
        breakdown=breakdown,
    )


@router.get(
    "/channels/{channel_id}/cost-summary",
    response_model=ChannelCostSummary,
    status_code=status.HTTP_200_OK,
    summary="Get channel cost summary",
    description="Returns aggregated cost summary for a channel with optional date filtering",
)
async def get_channel_costs(
    channel_id: UUID,
    start_date: datetime | None = Query(None, description="Start date for filtering (UTC)"),
    end_date: datetime | None = Query(None, description="End date for filtering (UTC)"),
    db: AsyncSession = Depends(get_session),
) -> ChannelCostSummary:
    """Get aggregated cost summary for a channel.

    Args:
        channel_id: UUID of the channel
        start_date: Optional start date for filtering (UTC)
        end_date: Optional end date for filtering (UTC)
        db: Database session (injected)

    Returns:
        ChannelCostSummary with total, average, and breakdown

    Example:
        GET /api/v1/channels/123e4567-e89b-12d3-a456-426614174000/cost-summary
        GET /api/v1/channels/{channel_id}/cost-summary?start_date=2026-01-01T00:00:00Z
    """
    summary = await get_channel_cost_summary(db, channel_id, start_date, end_date)

    return ChannelCostSummary(
        channel_id=channel_id,
        total_cost_usd=summary["total_cost"],
        video_count=summary["video_count"],
        avg_cost_per_video=summary["avg_cost_per_video"],
        breakdown_by_component=summary["breakdown_by_component"],
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/reports/cost-trends",
    response_model=CostTrendsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get cost trends",
    description="Returns average cost per video for last N days",
)
async def get_cost_trends(
    channel_id: UUID = Query(..., description="Channel UUID"),
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze (1-365)"),
    db: AsyncSession = Depends(get_session),
) -> CostTrendsResponse:
    """Get cost trends for last N days.

    Args:
        channel_id: UUID of the channel
        days: Number of days to look back (default: 30, max: 365)
        db: Database session (injected)

    Returns:
        CostTrendsResponse with average cost per video

    Example:
        GET /api/v1/reports/cost-trends?channel_id=123e4567-e89b-12d3-a456-426614174000&days=30
    """
    avg_cost = await get_average_cost_per_video(db, channel_id, days)

    return CostTrendsResponse(
        channel_id=channel_id,
        days=days,
        avg_cost_per_video=avg_cost,
    )


@router.get(
    "/tasks/{task_id}/validate-costs",
    status_code=status.HTTP_200_OK,
    summary="Validate task costs",
    description="Run comprehensive validation checks on task cost data",
)
async def validate_costs(
    task_id: UUID,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Validate cost data for a task.

    Runs comprehensive validation checks:
    - Consistency: video_costs sum matches task.total_cost_usd
    - Completeness: All expected components have cost records
    - Duplicates: No duplicate cost records per component
    - Anomalies: Costs are within expected ranges

    Args:
        task_id: UUID of the task
        db: Database session (injected)

    Returns:
        Validation report with overall_valid flag and details

    Example:
        GET /api/v1/tasks/123e4567-e89b-12d3-a456-426614174000/validate-costs
    """
    report = await validate_task_costs(db, task_id)
    return report
