"""Workspace cleanup service for removing old task directories (Story 8.5).

Handles daily cleanup of completed task workspace files to prevent unbounded
disk growth. Integrates with R2 storage cleanup for channels using R2 strategy.

Architecture:
- Short transaction pattern: Query → Close DB → Delete files → New DB → Update
- Preserves error state tasks (may retry from checkpoint)
- Deletes R2 assets for storage_strategy="r2" channels
- Structured logging with correlation IDs (Story 8.1)
- APScheduler integration for daily scheduled cleanup

Dependencies:
- Story 8.1: Structured logging with correlation IDs
- Story 8.3: AssetMetadata model for R2 asset tracking
- Story 8.4: R2StorageClient for R2 asset deletion
- Story 7.0: APScheduler pattern for daily jobs
- project-context.md: Filesystem helpers for workspace paths
"""

import shutil
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AssetMetadata, Task, TaskStatus
from app.utils.context import get_correlation_id, set_correlation_id
from app.utils.filesystem import get_project_dir

log = structlog.get_logger()


class WorkspaceCleanupService:
    """Service for cleaning up old workspace directories."""

    def __init__(self, session_factory=None):
        """Initialize cleanup service.

        Args:
            session_factory: Optional session factory for creating new sessions.
                           Defaults to AsyncSessionLocal from app.database.
        """
        from app.database import AsyncSessionLocal as DefaultSessionFactory

        self._session_factory = session_factory or DefaultSessionFactory

    async def cleanup_old_workspaces(self, db: AsyncSession, retention_days: int = 7) -> dict:
        """Clean up workspace directories for completed tasks older than retention period.

        Args:
            db: Database session
            retention_days: Keep files for this many days after task completion (default: 7)

        Returns:
            Dict with cleanup metrics:
                - directories_cleaned: int
                - disk_freed_mb: float
                - r2_assets_deleted: int
                - duration_seconds: float
        """
        set_correlation_id(f"cleanup-{datetime.now(timezone.utc).isoformat()}")
        start_time = datetime.now(timezone.utc)

        log.info("workspace_cleanup_started", retention_days=retention_days)

        # Query eligible tasks (short transaction)
        # Eager load channel relationship to avoid detached instance errors
        from sqlalchemy.orm import selectinload

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        eligible_tasks_result = await db.execute(
            select(Task)
            .options(selectinload(Task.channel))  # Eager load channel
            .where(
                Task.status.in_([TaskStatus.PUBLISHED, TaskStatus.CANCELLED]),
                Task.updated_at < cutoff_date,
                Task.cleanup_performed_at.is_(None),  # Not already cleaned
            )
            .order_by(Task.updated_at.asc())  # Oldest first
        )

        tasks = list(eligible_tasks_result.scalars())

        log.info("tasks_eligible_for_cleanup", task_count=len(tasks))

        # Close DB before file operations (short transaction pattern)
        await db.close()

        # Cleanup metrics
        directories_cleaned = 0
        total_disk_freed = 0.0
        total_r2_assets_deleted = 0

        # Process each task
        for task in tasks:
            try:
                result = await self._cleanup_task_workspace(task)

                directories_cleaned += 1
                total_disk_freed += result["disk_freed_mb"]
                total_r2_assets_deleted += result["r2_assets_deleted"]

            except Exception as e:
                log.error(
                    "task_cleanup_failed",
                    task_id=str(task.id),
                    channel_id=task.channel.channel_id,
                    error=str(e),
                    exc_info=True,
                )
                # Continue cleaning other tasks despite failures

        # Update tasks with cleanup timestamp (new transaction)
        # Use new session to avoid holding transaction during file operations
        async with self._session_factory() as db_update:  # type: ignore[misc]
            cleanup_time = datetime.now(timezone.utc)
            for task in tasks:
                # Update cleanup_performed_at using direct SQL to avoid triggering status validation
                from sqlalchemy import update

                await db_update.execute(
                    update(Task).where(Task.id == task.id).values(cleanup_performed_at=cleanup_time)
                )

            await db_update.commit()

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        log.info(
            "workspace_cleanup_completed",
            directories_cleaned=directories_cleaned,
            disk_freed_mb=round(total_disk_freed, 2),
            r2_assets_deleted=total_r2_assets_deleted,
            duration_seconds=round(duration, 2),
        )

        return {
            "directories_cleaned": directories_cleaned,
            "disk_freed_mb": round(total_disk_freed, 2),
            "r2_assets_deleted": total_r2_assets_deleted,
            "duration_seconds": round(duration, 2),
        }

    async def _cleanup_task_workspace(self, task: Task) -> dict:
        """Clean up workspace directory and R2 assets for a single task.

        Args:
            task: Task model instance

        Returns:
            Dict with metrics: disk_freed_mb, r2_assets_deleted
        """
        correlation_id = get_correlation_id()

        # Get workspace path via filesystem helper
        project_dir = get_project_dir(channel_id=task.channel.channel_id, project_id=str(task.id))

        disk_freed_mb = 0.0
        r2_assets_deleted = 0

        # Calculate disk space before deletion
        if project_dir.exists():
            total_size = sum(f.stat().st_size for f in project_dir.rglob("*") if f.is_file())
            disk_freed_mb = total_size / (1024 * 1024)

            # Delete workspace directory
            try:
                shutil.rmtree(project_dir, ignore_errors=False)

                log.info(
                    "workspace_deleted",
                    task_id=str(task.id),
                    channel_id=task.channel.channel_id,
                    status=task.status.value,
                    disk_freed_mb=round(disk_freed_mb, 2),
                    correlation_id=correlation_id,
                )

            except FileNotFoundError:
                log.warning(
                    "workspace_already_deleted", task_id=str(task.id), correlation_id=correlation_id
                )

            except PermissionError as e:
                log.error(
                    "workspace_delete_permission_error",
                    task_id=str(task.id),
                    error=str(e),
                    correlation_id=correlation_id,
                    exc_info=True,
                )
                raise

        else:
            log.warning(
                "workspace_not_found",
                task_id=str(task.id),
                project_dir=str(project_dir),
                correlation_id=correlation_id,
            )

        # Delete R2 assets if storage_strategy="r2"
        if task.channel.storage_strategy == "r2":
            r2_assets_deleted = await self._cleanup_r2_assets(task)

        return {"disk_freed_mb": disk_freed_mb, "r2_assets_deleted": r2_assets_deleted}

    async def _cleanup_r2_assets(self, task: Task) -> int:
        """Delete R2 assets for task.

        Args:
            task: Task model instance

        Returns:
            Number of R2 assets deleted
        """
        from app.services.credential_service import CredentialService

        correlation_id = get_correlation_id()

        async with self._session_factory() as db:  # type: ignore[misc]
            # Query all R2 assets for task
            assets_result = await db.execute(
                select(AssetMetadata).where(
                    AssetMetadata.task_id == task.id, AssetMetadata.storage_strategy == "r2"
                )
            )

            r2_assets = list(assets_result.scalars())

            if not r2_assets:
                return 0

            # Get R2 client with decrypted credentials
            credential_service = CredentialService()
            r2_client = await credential_service.get_r2_client(task.channel.channel_id, db)

        deleted_count = 0

        for asset in r2_assets:
            # Extract R2 key from URL
            # URL format: https://{bucket}.r2.dev/{channel_id}/{task_id}/{asset_path}
            try:
                r2_key = asset.asset_url.split(f"{r2_client.bucket_name}.r2.dev/")[1]

                deleted = await r2_client.delete_asset(r2_key)

                if deleted:
                    deleted_count += 1
                    log.info(
                        "r2_asset_deleted",
                        task_id=str(task.id),
                        asset_id=str(asset.id),
                        asset_type=asset.asset_type,
                        r2_key=r2_key,
                        correlation_id=correlation_id,
                    )

            except IndexError as e:
                # URL parsing failed - malformed asset_url
                log.error(
                    "r2_asset_delete_failed",
                    task_id=str(task.id),
                    asset_id=str(asset.id),
                    asset_url=asset.asset_url,
                    error=str(e),
                    reason="malformed_url",
                    correlation_id=correlation_id,
                )
            except Exception as e:
                # R2 deletion error or other unexpected issue
                log.error(
                    "r2_asset_delete_failed",
                    task_id=str(task.id),
                    asset_id=str(asset.id),
                    asset_url=asset.asset_url,
                    error=str(e),
                    error_type=type(e).__name__,
                    correlation_id=correlation_id,
                )

        log.info(
            "r2_cleanup_completed",
            task_id=str(task.id),
            r2_assets_deleted=deleted_count,
            total_r2_assets=len(r2_assets),
            correlation_id=correlation_id,
        )

        return deleted_count
