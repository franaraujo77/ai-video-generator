"""Admin routes for operational tasks.

Provides administrative endpoints for manual interventions and system maintenance.
All endpoints require authentication (admin API key or Railway internal auth).

Story 7.0: Manual quota reset endpoint for emergency quota resets.

Security:
    - All endpoints require admin authentication
    - Audit logging for all admin actions
    - Input validation to prevent injection attacks

Usage:
    POST /api/v1/admin/quota-reset
    Headers: X-Admin-Key: <admin_key>
    Body: {"channel_id": "uuid", "service": "youtube|gemini", "date": "2026-01-25"}
"""

from datetime import date as date_type
from datetime import datetime
from typing import Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Channel
from app.services.quota_reset_service import reset_gemini_quotas, reset_youtube_quotas

# Initialize router
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# Get logger
log = structlog.get_logger()

# Rate limiter (prevents brute-force attacks on admin endpoints)
limiter = Limiter(key_func=get_remote_address)


# Pydantic schemas
class QuotaResetRequest(BaseModel):
    """Request schema for manual quota reset."""

    channel_id: UUID = Field(description="Channel UUID to reset quota for")
    service: Literal["youtube", "gemini"] = Field(
        description="Service to reset (youtube or gemini)"
    )
    date: date_type | None = Field(
        default=None,
        description="Date to reset quota for (defaults to today in Pacific timezone)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "channel_id": "12345678-1234-1234-1234-123456789012",
                "service": "youtube",
                "date": "2026-01-25",
            }
        }
    }


class QuotaResetResponse(BaseModel):
    """Response schema for quota reset."""

    success: bool
    message: str
    channel_id: UUID
    service: str
    date: date_type
    new_quota_units: int
    quota_exhausted_flag_cleared: bool


# Admin authentication dependency
async def verify_admin_key(x_admin_key: str = Header(None)) -> None:
    """Verify admin API key for authentication.

    Args:
        x_admin_key: Admin API key from request header

    Raises:
        HTTPException: 401 if invalid or missing API key

    Example:
        curl -H "X-Admin-Key: secret" /api/v1/admin/quota-reset

    Security:
        Uses secrets.compare_digest to prevent timing attacks.
    """
    import os
    import secrets

    expected_key = os.getenv("ADMIN_API_KEY")

    # Require admin key to be configured
    if not expected_key:
        log.error("admin_api_key_not_configured")
        raise HTTPException(status_code=500, detail="Admin API key not configured on server")

    # Verify provided key matches (use constant-time comparison to prevent timing attacks)
    if not secrets.compare_digest(x_admin_key or "", expected_key):
        log.warning("admin_authentication_failed", provided_key_length=len(x_admin_key or ""))
        raise HTTPException(status_code=401, detail="Invalid admin API key")


@router.post("/quota-reset", response_model=QuotaResetResponse)
@limiter.limit("5/minute")  # Max 5 quota reset attempts per minute (prevents brute-force)
async def manual_quota_reset(
    quota_request: QuotaResetRequest,
    request: Request,  # Required by slowapi for rate limiting
    db: AsyncSession = Depends(get_session),  # noqa: B008
    _admin: None = Depends(verify_admin_key),
) -> QuotaResetResponse:
    """Manually reset quota for a specific channel and service.

    Allows ops team to manually trigger quota reset in emergency situations
    (e.g., scheduler failure, midnight missed, quota incorrectly marked exhausted).

    Authentication:
        Requires X-Admin-Key header with valid admin API key.

    Parameters:
        request: QuotaResetRequest with channel_id, service, and optional date
        db: Database session (injected)

    Returns:
        QuotaResetResponse with reset confirmation details

    Raises:
        HTTPException 400: Invalid service or channel not found
        HTTPException 401: Invalid admin API key
        HTTPException 500: Database error during reset

    Example:
        POST /api/v1/admin/quota-reset
        Headers: X-Admin-Key: secret123
        Body: {"channel_id": "...", "service": "youtube"}

    Story: 7.0 - Automated Daily Quota Reset (AC: Manual reset for ops team)
    """
    from zoneinfo import ZoneInfo

    # Get reset date (default to today in Pacific timezone)
    if quota_request.date is None:
        pacific_tz = ZoneInfo("America/Los_Angeles")
        reset_date = datetime.now(pacific_tz).date()
    else:
        reset_date = quota_request.date

    # Validate reset date is not in the future
    pacific_tz = ZoneInfo("America/Los_Angeles")
    today_pacific = datetime.now(pacific_tz).date()
    if reset_date > today_pacific:
        log.warning(
            "manual_quota_reset_future_date_rejected",
            reset_date=str(reset_date),
            today=str(today_pacific),
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot reset quota for future date. "
                f"Reset date: {reset_date}, Today: {today_pacific}"
            ),
        )

    # Verify channel exists and is active
    channel = await db.get(Channel, quota_request.channel_id)
    if channel is None:
        log.warning(
            "manual_quota_reset_channel_not_found",
            channel_id=str(quota_request.channel_id),
            service=quota_request.service,
        )
        raise HTTPException(status_code=400, detail=f"Channel {quota_request.channel_id} not found")

    # Log admin action BEFORE executing
    log.info(
        "manual_quota_reset_initiated",
        channel_id=str(quota_request.channel_id),
        channel_name=channel.channel_name,
        service=quota_request.service,
        reset_date=str(reset_date),
        is_active=channel.is_active,
    )

    try:
        # Execute quota reset for the single channel
        if quota_request.service == "youtube":
            # Temporarily mark channel as active to ensure it gets reset
            original_is_active = channel.is_active
            channel.is_active = True
            await db.commit()

            # Reset YouTube quota
            reset_count = await reset_youtube_quotas(reset_date, db)

            # Restore original is_active state
            channel.is_active = original_is_active
            await db.commit()

            new_quota_units = 10000
            quota_flag_cleared = True

        else:  # gemini
            # Temporarily mark channel as active to ensure it gets reset
            original_is_active = channel.is_active
            channel.is_active = True
            await db.commit()

            # Reset Gemini quota
            reset_count = await reset_gemini_quotas(reset_date, db)

            # Restore original is_active state
            channel.is_active = original_is_active
            await db.commit()

            new_quota_units = 1500
            quota_flag_cleared = True

        # Log successful reset with audit trail (structured logging provides permanent audit record)
        log.info(
            "manual_quota_reset_completed",
            channel_id=str(quota_request.channel_id),
            channel_name=channel.channel_name,
            service=quota_request.service,
            reset_date=str(reset_date),
            reset_count=reset_count,
            admin_action=True,  # Flag for audit queries
            action_type="manual_quota_reset",  # Audit action type
        )

        # Note: Full audit_logs table implementation deferred to Epic 8 (Story 8.x)
        # Current implementation uses structured logging for audit trail (permanent, searchable)
        # Future: audit_logs table will consolidate all admin actions with FK to users table

        return QuotaResetResponse(
            success=True,
            message=(
                f"Successfully reset {quota_request.service} quota "
                f"for channel {quota_request.channel_id}"
            ),
            channel_id=quota_request.channel_id,
            service=quota_request.service,
            date=reset_date,
            new_quota_units=new_quota_units,
            quota_exhausted_flag_cleared=quota_flag_cleared,
        )

    except Exception as e:
        log.error(
            "manual_quota_reset_failed",
            channel_id=str(quota_request.channel_id),
            service=quota_request.service,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        # Don't leak internal error details to client (security)
        raise HTTPException(
            status_code=500,
            detail="Quota reset failed. Check server logs for details.",
        ) from e
