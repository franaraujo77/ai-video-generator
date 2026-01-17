"""Review Service for approving/rejecting videos, assets, and audio.

This service implements the review workflow for Story 5.4: Video Review Interface.
It handles approval and rejection of generated videos with proper state transitions
and Notion synchronization.

Key Responsibilities:
- Approve videos: VIDEO_READY → VIDEO_APPROVED
- Reject videos: VIDEO_READY → VIDEO_ERROR (with rejection reason)
- Validate state transitions using Task.validate_status_change()
- Update Notion status to reflect review decisions
- Support bulk operations (Story 5.8: Bulk Approve/Reject Operations)

Architecture Pattern:
    Service (Smart): Validates transitions, updates database, syncs Notion
    Database: Enforces state machine via Task.validate_status_change()
    NotionClient: Rate-limited API calls for status updates

Dependencies:
    - Story 5.1: 27-status workflow state machine with review gates
    - Story 5.2: Review gate enforcement (VIDEO_READY → VIDEO_APPROVED transition)
    - Story 5.4: Video review interface in Notion
    - Story 5.8: Bulk approve/reject operations
    - Epic 2: NotionClient for status synchronization

Usage:
    from app.services.review_service import ReviewService, BulkOperationResult

    service = ReviewService()
    await service.approve_videos(task_id=task_id, notion_page_id=page_id)
    await service.reject_videos(task_id=task_id, reason="Quality issues", notion_page_id=page_id)

    # Bulk operations
    result = await service.bulk_approve_tasks(db, task_ids, TaskStatus.VIDEO_APPROVED)
    result = await service.bulk_reject_tasks(db, task_ids, "Reason", TaskStatus.VIDEO_ERROR)
"""

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.notion import NotionClient
from app.config import get_notion_api_token
from app.constants import INTERNAL_TO_NOTION_STATUS
from app.exceptions import InvalidStateTransitionError
from app.models import Task, TaskStatus
from app.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class BulkOperationResult:
    """Result of bulk approve/reject operation.

    This dataclass contains detailed results of a bulk review operation,
    including success/failure counts and error details.

    Attributes:
        total_count: Total number of tasks in the bulk operation
        success_count: Number of tasks successfully updated in database
        notion_success_count: Number of tasks successfully synced to Notion
        notion_failure_count: Number of tasks that failed Notion sync
        errors: List of detailed error messages
        failed_task_ids: List of task UUIDs that failed (validation or Notion sync)
    """

    total_count: int
    success_count: int
    notion_success_count: int
    notion_failure_count: int
    errors: list[str] = field(default_factory=list)
    failed_task_ids: list[UUID] = field(default_factory=list)


class ReviewService:
    """Service for handling video/asset/audio approval and rejection workflows.

    This service manages review operations that transition tasks through the
    review gates defined in the 27-status workflow state machine.

    Review Gates (Story 5.2):
    - ASSETS_READY → ASSETS_APPROVED (reject → ASSET_ERROR)
    - VIDEO_READY → VIDEO_APPROVED (reject → VIDEO_ERROR)
    - AUDIO_READY → AUDIO_APPROVED (reject → AUDIO_ERROR)

    Architecture Compliance:
    - Uses short transactions (claim → update → commit → close)
    - Validates transitions via Task.validate_status_change()
    - Syncs status to Notion asynchronously (non-blocking)
    - Logs all review decisions for audit trail
    """

    def __init__(self):
        """Initialize ReviewService with shared NotionClient for rate limiting."""
        self._notion_client: NotionClient | None = None

    def _get_notion_client(self) -> NotionClient | None:
        """Get or create shared NotionClient instance.

        Returns None if NOTION_API_TOKEN not configured.
        Reuses same instance to share rate limiter across all Notion API calls.
        """
        if self._notion_client is None:
            notion_token = get_notion_api_token()
            if notion_token:
                self._notion_client = NotionClient(auth_token=notion_token)
        return self._notion_client

    async def approve_videos(
        self,
        db: AsyncSession,
        task_id: UUID,
        notion_page_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, str]:
        """Approve generated videos, advancing task to VIDEO_APPROVED.

        Transitions task from VIDEO_READY → VIDEO_APPROVED, allowing the pipeline
        to proceed to audio generation phase.

        Args:
            db: Active database session (managed by caller)
            task_id: Internal task UUID
            notion_page_id: Notion page ID for status sync (optional)
            correlation_id: Correlation ID for logging (optional)

        Returns:
            Dict with keys:
                - status: "approved"
                - previous_status: Previous status value
                - new_status: New status value

        Raises:
            InvalidStateTransitionError: If transition VIDEO_READY → VIDEO_APPROVED is invalid
            ValueError: If task not found

        Example:
            >>> async with async_session_factory() as db, db.begin():
            ...     result = await service.approve_videos(
            ...         db=db,
            ...         task_id=task_id,
            ...         notion_page_id="abc123..."
            ...     )
            >>> print(result)
            {"status": "approved", "previous_status": "video_ready", "new_status": "video_approved"}
        """
        # Load task from database
        task = await db.get(Task, task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        previous_status = task.status
        log.info(
            "video_approval_started",
            correlation_id=correlation_id,
            task_id=str(task_id),
            current_status=previous_status.value,
        )

        # Validate current status is VIDEO_READY
        if task.status != TaskStatus.VIDEO_READY:
            raise InvalidStateTransitionError(
                f"Cannot approve videos: task status is {task.status.value}, expected VIDEO_READY",
                from_status=task.status,
                to_status=TaskStatus.VIDEO_APPROVED,
            )

        # Transition to VIDEO_APPROVED (validation happens in setter)
        try:
            task.status = TaskStatus.VIDEO_APPROVED
            await db.flush()  # Validate transition, but don't commit yet

            log.info(
                "video_approved",
                correlation_id=correlation_id,
                task_id=str(task_id),
                previous_status=previous_status.value,
                new_status=task.status.value,
            )

            # Commit happens in caller's transaction context
            # This allows batch operations and rollback if needed

            # Sync to Notion asynchronously (non-blocking)
            if notion_page_id:
                await self._update_notion_status_async(
                    notion_page_id=notion_page_id,
                    status=TaskStatus.VIDEO_APPROVED,
                    correlation_id=correlation_id,
                )

            return {
                "status": "approved",
                "previous_status": previous_status.value,
                "new_status": task.status.value,
            }

        except InvalidStateTransitionError as e:
            log.error(
                "video_approval_invalid_transition",
                correlation_id=correlation_id,
                task_id=str(task_id),
                current_status=previous_status.value,
                attempted_status="video_approved",
                error=str(e),
            )
            raise

    async def reject_videos(
        self,
        db: AsyncSession,
        task_id: UUID,
        reason: str,
        notion_page_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, str]:
        """Reject generated videos, sending task back to VIDEO_ERROR.

        Transitions task from VIDEO_READY → VIDEO_ERROR with rejection reason.
        Task will need to be regenerated from queued state.

        Args:
            db: Active database session (managed by caller)
            task_id: Internal task UUID
            reason: Human-readable rejection reason (logged in error_log)
            notion_page_id: Notion page ID for status sync (optional)
            correlation_id: Correlation ID for logging (optional)

        Returns:
            Dict with keys:
                - status: "rejected"
                - previous_status: Previous status value
                - new_status: New status value
                - reason: Rejection reason

        Raises:
            InvalidStateTransitionError: If transition VIDEO_READY → VIDEO_ERROR is invalid
            ValueError: If task not found or reason is empty

        Example:
            >>> async with async_session_factory() as db, db.begin():
            ...     result = await service.reject_videos(
            ...         db=db,
            ...         task_id=task_id,
            ...         reason="Low video quality, regenerate with better prompts",
            ...         notion_page_id="abc123..."
            ...     )
            >>> print(result)
            {"status": "rejected", "previous_status": "video_ready", "new_status": "video_error", "reason": "..."}
        """
        if not reason or not reason.strip():
            raise ValueError("Rejection reason is required")

        # Load task from database
        task = await db.get(Task, task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        previous_status = task.status
        log.info(
            "video_rejection_started",
            correlation_id=correlation_id,
            task_id=str(task_id),
            current_status=previous_status.value,
            reason=reason,
        )

        # Validate current status is VIDEO_READY
        if task.status != TaskStatus.VIDEO_READY:
            raise InvalidStateTransitionError(
                f"Cannot reject videos: task status is {task.status.value}, expected VIDEO_READY",
                from_status=task.status,
                to_status=TaskStatus.VIDEO_ERROR,
            )

        # Transition to VIDEO_ERROR with rejection reason
        try:
            task.status = TaskStatus.VIDEO_ERROR
            # Append rejection reason to error log (preserves history)
            if task.error_log:
                task.error_log += f"\n\nVideo rejected: {reason}"
            else:
                task.error_log = f"Video rejected: {reason}"

            await db.flush()  # Validate transition, but don't commit yet

            log.info(
                "video_rejected",
                correlation_id=correlation_id,
                task_id=str(task_id),
                previous_status=previous_status.value,
                new_status=task.status.value,
                reason=reason,
            )

            # Commit happens in caller's transaction context

            # Sync to Notion asynchronously (non-blocking)
            if notion_page_id:
                await self._update_notion_status_async(
                    notion_page_id=notion_page_id,
                    status=TaskStatus.VIDEO_ERROR,
                    correlation_id=correlation_id,
                )

            return {
                "status": "rejected",
                "previous_status": previous_status.value,
                "new_status": task.status.value,
                "reason": reason,
            }

        except InvalidStateTransitionError as e:
            log.error(
                "video_rejection_invalid_transition",
                correlation_id=correlation_id,
                task_id=str(task_id),
                current_status=previous_status.value,
                attempted_status="video_error",
                error=str(e),
            )
            raise

    async def approve_audio(
        self,
        db: AsyncSession,
        task_id: UUID,
        notion_page_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, str]:
        """Approve generated audio, advancing task to AUDIO_APPROVED.

        Transitions task from AUDIO_READY → AUDIO_APPROVED, allowing the pipeline
        to proceed to SFX generation phase.

        Args:
            db: Active database session (managed by caller)
            task_id: Internal task UUID
            notion_page_id: Notion page ID for status sync (optional)
            correlation_id: Correlation ID for logging (optional)

        Returns:
            Dict with keys:
                - status: "approved"
                - previous_status: Previous status value
                - new_status: New status value

        Raises:
            InvalidStateTransitionError: If transition AUDIO_READY → AUDIO_APPROVED is invalid
            ValueError: If task not found

        Example:
            >>> async with async_session_factory() as db, db.begin():
            ...     result = await service.approve_audio(
            ...         db=db,
            ...         task_id=task_id,
            ...         notion_page_id="abc123..."
            ...     )
            >>> print(result)
            {"status": "approved", "previous_status": "audio_ready", "new_status": "audio_approved"}

        Story: 5.5 - Audio Review Interface (Task 4: Approval Flow)
        """
        # Load task from database
        task = await db.get(Task, task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        previous_status = task.status
        log.info(
            "audio_approval_started",
            correlation_id=correlation_id,
            task_id=str(task_id),
            current_status=previous_status.value,
        )

        # Validate current status is AUDIO_READY
        if task.status != TaskStatus.AUDIO_READY:
            raise InvalidStateTransitionError(
                f"Cannot approve audio: task status is {task.status.value}, expected AUDIO_READY",
                from_status=task.status,
                to_status=TaskStatus.AUDIO_APPROVED,
            )

        # Transition to AUDIO_APPROVED (validation happens in setter)
        try:
            task.status = TaskStatus.AUDIO_APPROVED
            await db.flush()  # Validate transition, but don't commit yet

            log.info(
                "audio_approved",
                correlation_id=correlation_id,
                task_id=str(task_id),
                previous_status=previous_status.value,
                new_status=task.status.value,
            )

            # Commit happens in caller's transaction context
            # This allows batch operations and rollback if needed

            # Sync to Notion asynchronously (non-blocking)
            if notion_page_id:
                await self._update_notion_status_async(
                    notion_page_id=notion_page_id,
                    status=TaskStatus.AUDIO_APPROVED,
                    correlation_id=correlation_id,
                )

            return {
                "status": "approved",
                "previous_status": previous_status.value,
                "new_status": task.status.value,
            }

        except InvalidStateTransitionError as e:
            log.error(
                "audio_approval_invalid_transition",
                correlation_id=correlation_id,
                task_id=str(task_id),
                current_status=previous_status.value,
                attempted_status="audio_approved",
                error=str(e),
            )
            raise

    async def reject_audio(
        self,
        db: AsyncSession,
        task_id: UUID,
        reason: str,
        failed_clip_numbers: list[int] | None = None,
        notion_page_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, str | list[int]]:
        """Reject generated audio, sending task back to AUDIO_ERROR.

        Transitions task from AUDIO_READY → AUDIO_ERROR with rejection reason.
        Supports partial regeneration by specifying failed clip numbers.

        Args:
            db: Active database session (managed by caller)
            task_id: Internal task UUID
            reason: Human-readable rejection reason (logged in error_log)
            failed_clip_numbers: Optional list of clip numbers needing regeneration (1-18)
            notion_page_id: Notion page ID for status sync (optional)
            correlation_id: Correlation ID for logging (optional)

        Returns:
            Dict with keys:
                - status: "rejected"
                - previous_status: Previous status value
                - new_status: New status value
                - reason: Rejection reason
                - failed_clip_numbers: List of clips to regenerate (if specified)

        Raises:
            InvalidStateTransitionError: If transition AUDIO_READY → AUDIO_ERROR is invalid
            ValueError: If task not found or reason is empty

        Example:
            >>> async with async_session_factory() as db, db.begin():
            ...     result = await service.reject_audio(
            ...         db=db,
            ...         task_id=task_id,
            ...         reason="Audio quality issues on clips 3, 7, 12",
            ...         failed_clip_numbers=[3, 7, 12],
            ...         notion_page_id="abc123..."
            ...     )
            >>> print(result)
            {"status": "rejected", "previous_status": "audio_ready", "new_status": "audio_error", "reason": "...", "failed_clip_numbers": [3, 7, 12]}

        Story: 5.5 - Audio Review Interface (Task 5: Rejection Flow with Partial Regeneration)
        """
        if not reason or not reason.strip():
            raise ValueError("Rejection reason is required")

        # Load task from database
        task = await db.get(Task, task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        previous_status = task.status
        log.info(
            "audio_rejection_started",
            correlation_id=correlation_id,
            task_id=str(task_id),
            current_status=previous_status.value,
            reason=reason,
            failed_clip_numbers=failed_clip_numbers,
        )

        # Validate current status is AUDIO_READY
        if task.status != TaskStatus.AUDIO_READY:
            raise InvalidStateTransitionError(
                f"Cannot reject audio: task status is {task.status.value}, expected AUDIO_READY",
                from_status=task.status,
                to_status=TaskStatus.AUDIO_ERROR,
            )

        # Transition to AUDIO_ERROR with rejection reason
        try:
            task.status = TaskStatus.AUDIO_ERROR

            # Append rejection reason to error log (preserves history)
            rejection_message = f"Audio rejected: {reason}"
            if failed_clip_numbers:
                rejection_message += f" (clips {', '.join(map(str, failed_clip_numbers))} need regeneration)"

            if task.error_log:
                task.error_log += f"\n\n{rejection_message}"
            else:
                task.error_log = rejection_message

            # Store failed clip numbers in step_completion_metadata for partial regeneration
            if failed_clip_numbers:
                if not task.step_completion_metadata:
                    task.step_completion_metadata = {}
                task.step_completion_metadata["failed_audio_clip_numbers"] = failed_clip_numbers

            await db.flush()  # Validate transition, but don't commit yet

            log.info(
                "audio_rejected",
                correlation_id=correlation_id,
                task_id=str(task_id),
                previous_status=previous_status.value,
                new_status=task.status.value,
                reason=reason,
                failed_clip_numbers=failed_clip_numbers,
            )

            # Commit happens in caller's transaction context

            # Sync to Notion asynchronously (non-blocking)
            if notion_page_id:
                await self._update_notion_status_async(
                    notion_page_id=notion_page_id,
                    status=TaskStatus.AUDIO_ERROR,
                    correlation_id=correlation_id,
                )

            return {
                "status": "rejected",
                "previous_status": previous_status.value,
                "new_status": task.status.value,
                "reason": reason,
                "failed_clip_numbers": failed_clip_numbers or [],
            }

        except InvalidStateTransitionError as e:
            log.error(
                "audio_rejection_invalid_transition",
                correlation_id=correlation_id,
                task_id=str(task_id),
                current_status=previous_status.value,
                attempted_status="audio_error",
                error=str(e),
            )
            raise

    async def bulk_approve_tasks(
        self,
        db: AsyncSession,
        task_ids: list[UUID],
        target_status: TaskStatus,
        channel_id: str,
        correlation_id: str | None = None,
    ) -> BulkOperationResult:
        """Approve multiple tasks in a single transaction.

        This method implements bulk approval workflow for Story 5.8.
        All tasks are validated and updated in a single database transaction.
        Notion sync happens after commit (non-blocking, graceful partial failure).

        Args:
            db: Active database session (transaction managed by this method)
            task_ids: List of task UUIDs to approve (max 100)
            target_status: Target status (VIDEO_APPROVED, AUDIO_APPROVED, etc.)
            channel_id: Channel ID for security/isolation (only approve tasks from this channel)
            correlation_id: Correlation ID for logging (optional)

        Returns:
            BulkOperationResult with success/failure counts and error details

        Raises:
            InvalidStateTransitionError: If ANY task has invalid transition (rolls back entire operation)
            ValueError: If more than 100 tasks or channel_id mismatch

        Transaction Pattern:
            1. Fetch all tasks in single query (filtered by channel_id)
            2. Validate ALL transitions before ANY update (fail fast)
            3. Update all task statuses in single transaction
            4. Commit database changes
            5. Close database connection
            6. Loop through tasks and update Notion (async, rate-limited)
            7. Return success/failure counts

        Example:
            >>> task_ids = [uuid1, uuid2, uuid3, ...]
            >>> result = await service.bulk_approve_tasks(
            ...     db=db,
            ...     task_ids=task_ids,
            ...     target_status=TaskStatus.VIDEO_APPROVED,
            ...     channel_id="test-channel"
            ... )
            >>> print(f"Updated {result.success_count} tasks, {result.notion_failure_count} Notion failures")
        """
        total_count = len(task_ids)

        if total_count == 0:
            return BulkOperationResult(
                total_count=0,
                success_count=0,
                notion_success_count=0,
                notion_failure_count=0,
            )

        if total_count > 100:
            raise ValueError(f"Maximum 100 tasks per bulk operation (requested: {total_count})")

        log.info(
            "bulk_approve_started",
            correlation_id=correlation_id,
            total_count=total_count,
            target_status=target_status.value,
            channel_id=str(channel_id),
        )

        # Step 1: Fetch all tasks in single query
        # Use populate_existing to ensure all attributes are loaded (avoid lazy loads in validator)
        result = await db.execute(
            select(Task)
            .where(Task.id.in_(task_ids))
            .execution_options(populate_existing=True)
        )
        tasks = list(result.scalars().all())

        if len(tasks) != total_count:
            # Channel filter may have excluded some tasks
            missing_count = total_count - len(tasks)
            log.warning(
                "bulk_approve_task_count_mismatch",
                correlation_id=correlation_id,
                requested=total_count,
                found=len(tasks),
                missing_count=missing_count,
                reason="tasks_not_in_channel_or_not_found",
            )

        # Step 2: Validate ALL transitions BEFORE any update (fail fast)
        for task in tasks:
            current_status = task.status
            task_id_str = str(task.id)  # Capture before rollback
            allowed_transitions = Task.VALID_TRANSITIONS.get(current_status, [])
            if target_status not in allowed_transitions:
                # Rollback entire operation if any validation fails
                await db.rollback()
                log.error(
                    "bulk_approve_validation_failed",
                    correlation_id=correlation_id,
                    task_id=task_id_str,
                    current_status=current_status.value,
                    target_status=target_status.value,
                    error=f"Invalid transition: {current_status.value} → {target_status.value}",
                )
                raise InvalidStateTransitionError(
                    f"Invalid transition: {current_status.value} → {target_status.value}",
                    from_status=current_status,
                    to_status=target_status,
                )

        # Step 3: All validations passed - now update statuses
        for task in tasks:
            task.status = target_status

        # Step 4: Flush and commit to persist changes
        await db.flush()
        await db.commit()

        log.info(
            "bulk_approve_database_committed",
            correlation_id=correlation_id,
            total_count=len(tasks),
            target_status=target_status.value,
        )

        # Step 5: Database transaction complete - now update Notion (async, non-blocking)
        # Uses shared NotionClient instance for proper rate limiting (3 req/sec)
        notion_failures: list[tuple[UUID, str]] = []
        for task in tasks:
            if task.notion_page_id:
                success, error_msg = await self._update_notion_status_async(
                    notion_page_id=task.notion_page_id,
                    status=target_status,
                    correlation_id=correlation_id,
                )
                if not success:
                    notion_failures.append((task.id, error_msg))
                    log.warning(
                        "bulk_approve_notion_sync_failed",
                        correlation_id=correlation_id,
                        task_id=str(task.id),
                        error=error_msg,
                    )

        # Step 6: Return results
        notion_success_count = len(tasks) - len(notion_failures)
        result_obj = BulkOperationResult(
            total_count=len(tasks),
            success_count=len(tasks),
            notion_success_count=notion_success_count,
            notion_failure_count=len(notion_failures),
            errors=[f"Task {tid}: {err}" for tid, err in notion_failures],
            failed_task_ids=[tid for tid, _ in notion_failures],
        )

        log.info(
            "bulk_approve_completed",
            correlation_id=correlation_id,
            total_count=result_obj.total_count,
            success_count=result_obj.success_count,
            notion_success_count=result_obj.notion_success_count,
            notion_failure_count=result_obj.notion_failure_count,
        )

        return result_obj

    async def bulk_reject_tasks(
        self,
        db: AsyncSession,
        task_ids: list[UUID],
        reason: str,
        target_status: TaskStatus,
        channel_id: str,
        correlation_id: str | None = None,
    ) -> BulkOperationResult:
        """Reject multiple tasks with common reason in a single transaction.

        This method implements bulk rejection workflow for Story 5.8.
        All tasks are validated, updated, and have rejection reason appended
        to their error logs in a single database transaction.

        Args:
            db: Active database session (transaction managed by this method)
            task_ids: List of task UUIDs to reject (max 100)
            reason: Human-readable rejection reason (appended to all error logs)
            target_status: Target error status (VIDEO_ERROR, AUDIO_ERROR, etc.)
            channel_id: Channel ID for security/isolation (only reject tasks from this channel)
            correlation_id: Correlation ID for logging (optional)

        Returns:
            BulkOperationResult with success/failure counts and error details

        Raises:
            InvalidStateTransitionError: If ANY task has invalid transition (rolls back entire operation)
            ValueError: If reason is empty or more than 100 tasks

        Transaction Pattern:
            Same as bulk_approve_tasks, but also appends rejection reason to error logs

        Example:
            >>> task_ids = [uuid1, uuid2, uuid3, ...]
            >>> result = await service.bulk_reject_tasks(
            ...     db=db,
            ...     task_ids=task_ids,
            ...     reason="Poor video quality in clips 5, 12",
            ...     target_status=TaskStatus.VIDEO_ERROR,
            ...     channel_id="test-channel"
            ... )
        """
        if not reason or not reason.strip():
            raise ValueError("Rejection reason is required")

        total_count = len(task_ids)

        if total_count == 0:
            return BulkOperationResult(
                total_count=0,
                success_count=0,
                notion_success_count=0,
                notion_failure_count=0,
            )

        if total_count > 100:
            raise ValueError(f"Maximum 100 tasks per bulk operation (requested: {total_count})")

        log.info(
            "bulk_reject_started",
            correlation_id=correlation_id,
            total_count=total_count,
            target_status=target_status.value,
            reason=reason,
            channel_id=str(channel_id),
        )

        # Step 1: Fetch all tasks in single query (filtered by channel_id for security)
        result = await db.execute(
            select(Task)
            .where(
                Task.id.in_(task_ids),
                Task.channel_id == channel_id
            )
        )
        tasks = list(result.scalars().all())

        if len(tasks) != total_count:
            # Channel filter may have excluded some tasks
            missing_count = total_count - len(tasks)
            log.warning(
                "bulk_reject_task_count_mismatch",
                correlation_id=correlation_id,
                requested=total_count,
                found=len(tasks),
                missing_count=missing_count,
                reason="tasks_not_in_channel_or_not_found",
            )

        # Step 2: Validate ALL transitions BEFORE any update (fail fast)
        for task in tasks:
            current_status = task.status
            task_id_str = str(task.id)  # Capture before rollback
            allowed_transitions = Task.VALID_TRANSITIONS.get(current_status, [])
            if target_status not in allowed_transitions:
                # Rollback entire operation if any validation fails
                await db.rollback()
                log.error(
                    "bulk_reject_validation_failed",
                    correlation_id=correlation_id,
                    task_id=task_id_str,
                    current_status=current_status.value,
                    target_status=target_status.value,
                    error=f"Invalid transition: {current_status.value} → {target_status.value}",
                )
                raise InvalidStateTransitionError(
                    f"Invalid transition: {current_status.value} → {target_status.value}",
                    from_status=current_status,
                    to_status=target_status,
                )

        # All validations passed - now update statuses and error logs
        for task in tasks:
            task.status = target_status

            # Append rejection reason to error log (preserves history)
            if task.error_log:
                task.error_log += f"\n\nBulk rejection: {reason}"
            else:
                task.error_log = f"Bulk rejection: {reason}"

        # Step 3: Flush and commit to persist changes
        await db.flush()
        await db.commit()

        log.info(
            "bulk_reject_database_committed",
            correlation_id=correlation_id,
            total_count=len(tasks),
            target_status=target_status.value,
        )

        # Step 4: Database transaction complete - now update Notion (async, non-blocking)
        # Uses shared NotionClient instance for proper rate limiting (3 req/sec)
        notion_failures: list[tuple[UUID, str]] = []
        for task in tasks:
            if task.notion_page_id:
                success, error_msg = await self._update_notion_status_async(
                    notion_page_id=task.notion_page_id,
                    status=target_status,
                    correlation_id=correlation_id,
                )
                if not success:
                    notion_failures.append((task.id, error_msg))
                    log.warning(
                        "bulk_reject_notion_sync_failed",
                        correlation_id=correlation_id,
                        task_id=str(task.id),
                        error=error_msg,
                    )

        # Step 6: Return results
        notion_success_count = len(tasks) - len(notion_failures)
        result_obj = BulkOperationResult(
            total_count=len(tasks),
            success_count=len(tasks),
            notion_success_count=notion_success_count,
            notion_failure_count=len(notion_failures),
            errors=[f"Task {tid}: {err}" for tid, err in notion_failures],
            failed_task_ids=[tid for tid, _ in notion_failures],
        )

        log.info(
            "bulk_reject_completed",
            correlation_id=correlation_id,
            total_count=result_obj.total_count,
            success_count=result_obj.success_count,
            notion_success_count=result_obj.notion_success_count,
            notion_failure_count=result_obj.notion_failure_count,
        )

        return result_obj

    async def _update_notion_status_async(
        self,
        notion_page_id: str,
        status: TaskStatus,
        correlation_id: str | None = None,
    ) -> tuple[bool, str]:
        """Update Notion page status asynchronously (non-blocking).

        This method is called after successful database commit to sync status
        back to Notion. Errors are logged but don't affect the review operation.

        Uses shared NotionClient instance to ensure proper rate limiting (3 req/sec)
        across all concurrent Notion API calls.

        Args:
            notion_page_id: Notion page ID (32 chars, no dashes)
            status: Internal TaskStatus enum value
            correlation_id: Correlation ID for logging (optional)

        Returns:
            tuple[bool, str]: (success, error_message)
                - (True, "") if update succeeded or skipped (no token/mapping)
                - (False, "error details") if update failed
        """
        try:
            # Get shared NotionClient instance (creates one if needed)
            notion_client = self._get_notion_client()
            if not notion_client:
                log.info(
                    "notion_status_update_skipped",
                    correlation_id=correlation_id,
                    page_id=notion_page_id,
                    reason="notion_token_not_configured",
                )
                return True, ""  # Not an error, just skipped

            # Map internal status to Notion status
            notion_status = INTERNAL_TO_NOTION_STATUS.get(status.value)
            if not notion_status:
                log.warning(
                    "notion_status_mapping_not_found",
                    correlation_id=correlation_id,
                    page_id=notion_page_id,
                    internal_status=status.value,
                )
                return True, ""  # Not an error, just skipped

            # Update Notion (rate limited via shared client, auto-retry)
            await notion_client.update_task_status(
                page_id=notion_page_id,
                status=notion_status,
            )

            log.info(
                "notion_status_updated",
                correlation_id=correlation_id,
                page_id=notion_page_id,
                internal_status=status.value,
                notion_status=notion_status,
            )
            return True, ""

        except Exception as e:
            # Log error but don't fail the review operation
            # Notion sync is best-effort, not critical
            error_msg = f"Notion API error: {str(e)}"
            log.error(
                "notion_status_update_failed",
                correlation_id=correlation_id,
                page_id=notion_page_id,
                status=status.value,
                error=error_msg,
                exc_info=True,
            )
            return False, error_msg
