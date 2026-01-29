"""R2 Configuration API Endpoints (Story 8.4).

Provides REST API for configuring Cloudflare R2 storage credentials per channel.
Supports storing, retrieving, and testing R2 configuration.

Endpoints:
- POST /api/v1/channels/{channel_id}/r2-config - Store R2 credentials
- GET /api/v1/channels/{channel_id}/r2-config - Get R2 configuration (without secrets)
- DELETE /api/v1/channels/{channel_id}/r2-config - Remove R2 configuration
- POST /api/v1/channels/{channel_id}/r2-config/test - Test R2 connection

Security:
- All credentials encrypted with Fernet before database storage
- GET endpoint returns bucket name but NOT decrypted credentials
- Credentials only retrieved for test connection endpoint
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services.credential_service import CredentialService
from app.utils.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/v1/channels", tags=["r2-config"])


class R2ConfigRequest(BaseModel):
    """Request body for storing R2 configuration."""

    access_key_id: str = Field(..., description="R2 access key ID")
    secret_access_key: str = Field(..., description="R2 secret access key")
    bucket_name: str = Field(..., description="R2 bucket name")


class R2ConfigResponse(BaseModel):
    """Response body for R2 configuration (without secrets)."""

    channel_id: str = Field(..., description="Channel identifier")
    bucket_name: str = Field(..., description="R2 bucket name")
    has_credentials: bool = Field(..., description="Whether credentials are configured")


class R2TestConnectionResponse(BaseModel):
    """Response body for R2 connection test."""

    success: bool = Field(..., description="Whether connection test succeeded")
    message: str = Field(..., description="Result message")
    bucket_name: str | None = Field(None, description="Bucket name if successful")


@router.post("/{channel_id}/r2-config", response_model=R2ConfigResponse, status_code=201)
async def store_r2_config(
    channel_id: str,
    config: R2ConfigRequest,
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> R2ConfigResponse:
    """Store R2 credentials for channel.

    Args:
        channel_id: Channel business identifier (e.g., "poke1")
        config: R2 configuration with credentials
        db: Database session

    Returns:
        R2ConfigResponse with bucket name and confirmation

    Raises:
        HTTPException 404: If channel not found
        HTTPException 500: If storage fails
    """
    credential_service = CredentialService()

    try:
        await credential_service.store_r2_credentials(
            channel_id=channel_id,
            access_key_id=config.access_key_id,
            secret_access_key=config.secret_access_key,
            bucket_name=config.bucket_name,
            db=db,
        )

        log.info(
            "r2_config_stored",
            channel_id=channel_id,
            bucket_name=config.bucket_name,
        )

        return R2ConfigResponse(
            channel_id=channel_id,
            bucket_name=config.bucket_name,
            has_credentials=True,
        )

    except ValueError as e:
        log.error(
            "r2_config_store_failed",
            channel_id=channel_id,
            error=str(e),
        )
        raise HTTPException(status_code=404, detail=str(e)) from e

    except Exception as e:
        log.error(
            "r2_config_store_unexpected_error",
            channel_id=channel_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to store R2 configuration") from e


@router.get("/{channel_id}/r2-config", response_model=R2ConfigResponse)
async def get_r2_config(
    channel_id: str,
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> R2ConfigResponse:
    """Get R2 configuration for channel (without decrypted credentials).

    Args:
        channel_id: Channel business identifier
        db: Database session

    Returns:
        R2ConfigResponse with bucket name and credential status

    Raises:
        HTTPException 404: If channel not found or R2 not configured
    """
    credential_service = CredentialService()

    access_key, _secret_key, bucket_name = await credential_service.get_r2_credentials(
        channel_id, db
    )

    if not access_key or not bucket_name:
        log.info(
            "r2_config_not_found",
            channel_id=channel_id,
        )
        raise HTTPException(status_code=404, detail=f"R2 not configured for channel {channel_id}")

    return R2ConfigResponse(
        channel_id=channel_id,
        bucket_name=bucket_name,
        has_credentials=True,
    )


@router.delete("/{channel_id}/r2-config", status_code=204)
async def delete_r2_config(
    channel_id: str,
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> None:
    """Remove R2 configuration for channel.

    Args:
        channel_id: Channel business identifier
        db: Database session

    Raises:
        HTTPException 404: If channel not found
    """
    credential_service = CredentialService()

    try:
        # Clear R2 credentials by storing empty values
        await credential_service.store_r2_credentials(
            channel_id=channel_id,
            access_key_id="",
            secret_access_key="",
            bucket_name="",
            db=db,
        )

        log.info(
            "r2_config_deleted",
            channel_id=channel_id,
        )

    except ValueError as e:
        log.error(
            "r2_config_delete_failed",
            channel_id=channel_id,
            error=str(e),
        )
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{channel_id}/r2-config/test", response_model=R2TestConnectionResponse)
async def test_r2_connection(
    channel_id: str,
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> R2TestConnectionResponse:
    """Test R2 connection for channel.

    Attempts to create an R2 client with decrypted credentials and verifies
    connectivity by performing a lightweight operation (list bucket).

    Args:
        channel_id: Channel business identifier
        db: Database session

    Returns:
        R2TestConnectionResponse with success status and message

    Raises:
        HTTPException 404: If channel not found or R2 not configured
        HTTPException 500: If connection test fails
    """
    credential_service = CredentialService()

    try:
        # Get R2 client (validates credentials exist)
        r2_client = await credential_service.get_r2_client(channel_id, db)

        log.info(
            "r2_connection_test_success",
            channel_id=channel_id,
            bucket_name=r2_client.bucket_name,
        )

        return R2TestConnectionResponse(
            success=True,
            message="R2 connection successful",
            bucket_name=r2_client.bucket_name,
        )

    except ValueError as e:
        log.error(
            "r2_connection_test_failed",
            channel_id=channel_id,
            error=str(e),
        )
        raise HTTPException(status_code=404, detail=str(e)) from e

    except Exception as e:
        log.error(
            "r2_connection_test_unexpected_error",
            channel_id=channel_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="R2 connection test failed") from e
