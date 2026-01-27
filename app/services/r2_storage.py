"""Cloudflare R2 Storage Client (Story 8.4).

Provides S3-compatible async client for Cloudflare R2 object storage.
Handles asset uploads with error classification and retry logic.

Architecture:
- S3-compatible API: Uses aioboto3 (async boto3 wrapper)
- Error classification: Permanent vs transient R2 errors
- Retry logic: Exponential backoff with tenacity (max 3 attempts)
- URL generation: Public R2 URLs (https://{bucket}.r2.dev/{path})

Dependencies:
- aioboto3>=12.0.0 - Async S3 client for Cloudflare R2
- tenacity>=8.0.0 - Retry logic with exponential backoff
- Story 8.1: Correlation ID context variables
- Story 8.3: AssetMetadata model and URL recording

Usage:
    client = R2StorageClient(
        bucket_name="ai-video-assets",
        access_key_id="your_access_key",
        secret_access_key="your_secret_key"
    )
    url = await client.upload_asset(
        local_file_path=Path("/workspace/asset.png"),
        r2_key="channel/task/assets/asset.png",
        content_type="image/png"
    )
"""

from pathlib import Path

import aioboto3
import structlog
from botocore.exceptions import ClientError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.utils.context import get_correlation_id

log = structlog.get_logger(__name__)


class R2StorageError(Exception):
    """Permanent R2 storage error (don't retry).

    Raised for errors that won't succeed on retry:
    - AccessDenied: Invalid credentials or no bucket access
    - InvalidBucketName: Bucket name is invalid
    - NoSuchBucket: Bucket doesn't exist
    - InvalidAccessKeyId: Access key is invalid

    Examples:
        >>> raise R2StorageError("R2 permanent error: AccessDenied")
    """

    pass


class R2StorageRetryError(Exception):
    """Transient R2 storage error (retry with backoff).

    Raised for errors that may succeed on retry:
    - SlowDown: Rate limited by Cloudflare
    - RequestLimitExceeded: Too many requests
    - ServiceUnavailable: Cloudflare temporary outage
    - Unknown errors: Classified as transient (safe default)

    Examples:
        >>> raise R2StorageRetryError("R2 transient error: SlowDown")
    """

    pass


class R2StorageClient:
    """Cloudflare R2 storage client with S3-compatible API.

    Provides async upload/delete operations for R2 object storage with automatic
    retry logic for transient errors. Uses aioboto3 for S3-compatible API access.

    Attributes:
        bucket_name: R2 bucket name (e.g., "ai-video-assets")
        access_key_id: R2 access key ID (encrypted in database)
        secret_access_key: R2 secret access key (encrypted in database)
        region: R2 region (default: "auto" for Cloudflare auto-routing)
        endpoint_url: Cloudflare R2 API endpoint URL

    Example:
        >>> client = R2StorageClient(
        ...     bucket_name="ai-video-assets",
        ...     access_key_id="your_access_key",
        ...     secret_access_key="your_secret_key"
        ... )
        >>> url = await client.upload_asset(
        ...     local_file_path=Path("/workspace/asset.png"),
        ...     r2_key="poke1/task123/assets/char.png",
        ...     content_type="image/png"
        ... )
        >>> print(url)
        "https://ai-video-assets.r2.dev/poke1/task123/assets/char.png"
    """

    def __init__(
        self,
        bucket_name: str,
        access_key_id: str,
        secret_access_key: str,
        region: str = "auto",
    ):
        """Initialize R2 storage client.

        Args:
            bucket_name: R2 bucket name (e.g., "ai-video-assets")
            access_key_id: R2 access key ID
            secret_access_key: R2 secret access key
            region: R2 region (default: "auto" for Cloudflare auto-routing)
        """
        self.bucket_name = bucket_name
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region

        # Cloudflare R2 endpoint format
        self.endpoint_url = f"https://{bucket_name}.r2.cloudflarestorage.com"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type(R2StorageRetryError),
        reraise=True,
    )
    async def upload_asset(
        self,
        local_file_path: Path,
        r2_key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload asset to R2 bucket (with retry on transient errors).

        Args:
            local_file_path: Path to local file to upload
            r2_key: R2 object key (path within bucket)
            content_type: MIME type for asset (e.g., "image/png", "video/mp4")

        Returns:
            Public R2 URL for asset

        Raises:
            R2StorageError: Permanent error (don't retry)
            R2StorageRetryError: Transient error (retry with backoff)

        Example:
            >>> client = R2StorageClient(bucket_name="ai-video-assets", ...)
            >>> url = await client.upload_asset(
            ...     local_file_path=Path("/workspace/channel/task/asset.png"),
            ...     r2_key="poke1/uuid-task-123/assets/characters/bulbasaur_01.png",
            ...     content_type="image/png"
            ... )
            >>> print(url)
            "https://ai-video-assets.r2.dev/poke1/uuid-task-123/assets/characters/bulbasaur_01.png"
        """
        correlation_id = get_correlation_id()

        try:
            # Create async S3 session for R2
            session = aioboto3.Session()

            async with session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region,
            ) as s3_client:
                # Upload file to R2
                with open(local_file_path, "rb") as file:
                    await s3_client.upload_fileobj(
                        file,
                        self.bucket_name,
                        r2_key,
                        ExtraArgs={"ContentType": content_type},
                    )

            # Generate public URL
            public_url = f"https://{self.bucket_name}.r2.dev/{r2_key}"

            log.info(
                "r2_upload_success",
                r2_key=r2_key,
                public_url=public_url,
                file_size=local_file_path.stat().st_size,
                correlation_id=correlation_id,
            )

            return public_url

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            # Classify error as permanent or transient
            if error_code in [
                "AccessDenied",
                "InvalidBucketName",
                "NoSuchBucket",
                "InvalidAccessKeyId",
            ]:
                # Permanent errors - don't retry
                log.error(
                    "r2_permanent_error",
                    error_code=error_code,
                    r2_key=r2_key,
                    correlation_id=correlation_id,
                    exc_info=True,
                )
                raise R2StorageError(f"R2 permanent error: {error_code}") from e

            elif error_code in ["SlowDown", "RequestLimitExceeded", "ServiceUnavailable"]:
                # Transient errors - retry with backoff
                log.warning(
                    "r2_transient_error",
                    error_code=error_code,
                    r2_key=r2_key,
                    correlation_id=correlation_id,
                )
                raise R2StorageRetryError(f"R2 transient error: {error_code}") from e

            else:
                # Unknown error - classify as transient (safe default)
                log.warning(
                    "r2_unknown_error_retry",
                    error_code=error_code,
                    r2_key=r2_key,
                    correlation_id=correlation_id,
                )
                raise R2StorageRetryError(f"R2 unknown error: {error_code}") from e

        except Exception as e:
            # Unexpected errors - log and don't retry
            log.error(
                "r2_upload_unexpected_error",
                r2_key=r2_key,
                error=str(e),
                correlation_id=correlation_id,
                exc_info=True,
            )
            raise R2StorageError(f"Unexpected R2 error: {e}") from e

    async def delete_asset(self, r2_key: str) -> bool:
        """Delete asset from R2 bucket.

        Args:
            r2_key: R2 object key to delete

        Returns:
            True if deleted successfully, False otherwise

        Example:
            >>> await client.delete_asset("poke1/task123/assets/char.png")
            True
        """
        correlation_id = get_correlation_id()

        try:
            session = aioboto3.Session()

            async with session.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region,
            ) as s3_client:
                await s3_client.delete_object(Bucket=self.bucket_name, Key=r2_key)

            log.info("r2_delete_success", r2_key=r2_key, correlation_id=correlation_id)

            return True

        except Exception as e:
            log.error(
                "r2_delete_failed",
                r2_key=r2_key,
                error=str(e),
                correlation_id=correlation_id,
                exc_info=True,
            )
            return False
