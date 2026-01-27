"""Cost Validation Service (Story 8.2, Task 6).

Provides validation and consistency checks for cost tracking data.
Helps ensure data integrity between video_costs table and task.total_cost_usd.

Validation Checks:
- Cost consistency: video_costs sum matches task.total_cost_usd
- Missing components: All expected components have cost records
- Duplicate detection: No duplicate cost records per component
- Anomaly detection: Costs are within expected ranges

Expected Cost Ranges (per video):
- gemini_assets: $1.00 - $3.00 (22 images @ ~$0.068/image)
- kling_video: $5.00 - $12.00 (18 clips @ ~$0.42/clip)
- elevenlabs_narration: $0.50 - $1.50 (18 clips @ ~$0.04/clip)
- elevenlabs_sfx: $0.50 - $1.50 (18 clips @ ~$0.04/clip)
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import VideoCost, Task
from app.utils.logging import get_logger

log = get_logger(__name__)

# Expected cost ranges for anomaly detection
EXPECTED_COST_RANGES = {
    "gemini_assets": {"min": Decimal("1.00"), "max": Decimal("3.00")},
    "kling_video": {"min": Decimal("5.00"), "max": Decimal("12.00")},
    "elevenlabs_narration": {"min": Decimal("0.50"), "max": Decimal("1.50")},
    "elevenlabs_sfx": {"min": Decimal("0.50"), "max": Decimal("1.50")},
}

# All expected components for a complete video
EXPECTED_COMPONENTS = [
    "gemini_assets",
    "kling_video",
    "elevenlabs_narration",
    "elevenlabs_sfx",
]


async def validate_task_cost_consistency(
    db: AsyncSession, task_id: UUID
) -> tuple[bool, Decimal]:
    """Validate cost consistency between video_costs and task.total_cost_usd.

    Args:
        db: Database session
        task_id: Task UUID

    Returns:
        Tuple of (is_consistent, discrepancy)
        - is_consistent: True if costs match within $0.01 tolerance
        - discrepancy: Absolute difference between task total and video_costs sum
    """
    # Get task total_cost_usd
    task = await db.get(Task, task_id)
    if not task:
        log.warning("task_not_found_for_validation", task_id=str(task_id))
        return False, Decimal("0.00")

    task_total = Decimal(str(task.total_cost_usd))

    # Sum video_costs
    stmt = select(func.sum(VideoCost.cost_usd)).where(VideoCost.task_id == task_id)
    result = await db.execute(stmt)
    video_costs_sum = result.scalar_one_or_none() or Decimal("0.00")

    # Calculate discrepancy
    discrepancy = abs(task_total - video_costs_sum)

    # Allow $0.01 tolerance for floating-point precision
    is_consistent = discrepancy <= Decimal("0.01")

    if not is_consistent:
        log.warning(
            "cost_consistency_check_failed",
            task_id=str(task_id),
            task_total_usd=str(task_total),
            video_costs_sum=str(video_costs_sum),
            discrepancy=str(discrepancy),
        )

    return is_consistent, discrepancy


async def detect_missing_cost_components(
    db: AsyncSession, task_id: UUID
) -> list[str]:
    """Detect missing cost components for a completed task.

    Args:
        db: Database session
        task_id: Task UUID

    Returns:
        List of missing component names
    """
    # Get existing components
    stmt = select(VideoCost.component).where(VideoCost.task_id == task_id)
    result = await db.execute(stmt)
    existing_components = set(row[0] for row in result.all())

    # Find missing components
    missing = [c for c in EXPECTED_COMPONENTS if c not in existing_components]

    if missing:
        log.warning(
            "missing_cost_components_detected",
            task_id=str(task_id),
            missing_components=missing,
        )

    return missing


async def detect_duplicate_cost_records(
    db: AsyncSession, task_id: UUID
) -> dict[str, int]:
    """Detect duplicate cost records for same component.

    Args:
        db: Database session
        task_id: Task UUID

    Returns:
        Dict mapping component name to count of records (only duplicates)
        Example: {"kling_video": 2} means 2 kling_video records exist
    """
    # Count records per component
    stmt = (
        select(VideoCost.component, func.count(VideoCost.id))
        .where(VideoCost.task_id == task_id)
        .group_by(VideoCost.component)
        .having(func.count(VideoCost.id) > 1)
    )
    result = await db.execute(stmt)
    duplicates = {row[0]: row[1] for row in result.all()}

    if duplicates:
        log.warning(
            "duplicate_cost_records_detected",
            task_id=str(task_id),
            duplicates=duplicates,
        )

    return duplicates


async def detect_cost_anomalies(
    db: AsyncSession, task_id: UUID
) -> list[dict[str, Any]]:
    """Detect cost anomalies (values outside expected ranges).

    Args:
        db: Database session
        task_id: Task UUID

    Returns:
        List of anomaly dicts with component, cost, expected_min, expected_max
    """
    # Get all cost records
    stmt = select(VideoCost).where(VideoCost.task_id == task_id)
    result = await db.execute(stmt)
    costs = result.scalars().all()

    anomalies = []
    for cost in costs:
        if cost.component not in EXPECTED_COST_RANGES:
            # Unknown component - log but don't flag as anomaly
            log.info(
                "unknown_cost_component",
                task_id=str(task_id),
                component=cost.component,
            )
            continue

        expected_range = EXPECTED_COST_RANGES[cost.component]
        if not (expected_range["min"] <= cost.cost_usd <= expected_range["max"]):
            anomaly = {
                "component": cost.component,
                "cost_usd": str(cost.cost_usd),  # Convert to string for JSON serialization
                "expected_min": str(expected_range["min"]),
                "expected_max": str(expected_range["max"]),
            }
            anomalies.append(anomaly)

    if anomalies:
        log.warning(
            "cost_anomalies_detected",
            task_id=str(task_id),
            anomalies=anomalies,
        )

    return anomalies


async def validate_task_costs(db: AsyncSession, task_id: UUID) -> dict[str, Any]:
    """Run all cost validation checks for a completed task.

    This function aggregates all validation checks into a single report.
    Intended to be called after task completion for comprehensive validation.

    Args:
        db: Database session
        task_id: Task UUID

    Returns:
        Validation report dict with:
        - consistency_check: bool (True if costs match)
        - discrepancy: Decimal (difference between totals)
        - missing_components: list[str]
        - duplicate_records: dict[str, int]
        - anomalies: list[dict]
        - overall_valid: bool (True if all checks pass)
    """
    # Run all validation checks
    is_consistent, discrepancy = await validate_task_cost_consistency(db, task_id)
    missing = await detect_missing_cost_components(db, task_id)
    duplicates = await detect_duplicate_cost_records(db, task_id)
    anomalies = await detect_cost_anomalies(db, task_id)

    # Determine overall validity
    overall_valid = (
        is_consistent
        and len(missing) == 0
        and len(duplicates) == 0
        and len(anomalies) == 0
    )

    report = {
        "task_id": str(task_id),
        "consistency_check": is_consistent,
        "discrepancy": str(discrepancy),
        "missing_components": missing,
        "duplicate_records": duplicates,
        "anomalies": anomalies,
        "overall_valid": overall_valid,
    }

    if not overall_valid:
        log.warning(
            "cost_validation_failed",
            task_id=str(task_id),
            report=report,
        )
    else:
        log.info(
            "cost_validation_passed",
            task_id=str(task_id),
        )

    return report
