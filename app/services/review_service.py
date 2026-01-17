"""Review Service for approving/rejecting videos, assets, and audio.

This service implements the review workflow for Story 5.4: Video Review Interface.
It handles approval and rejection of generated videos with proper state transitions
and Notion synchronization.

Key Responsibilities:
- Approve videos: VIDEO_READY → VIDEO_APPROVED
- Reject videos: VIDEO_READY → VIDEO_ERROR (with rejection reason)
- Validate state transitions using Task.validate_status_change()
- Update Notion status to reflect review decisions
- Support batch operations for future enhancements

Architecture Pattern:
    Service (Smart): Validates transitions, updates database, syncs Notion
    Database: Enforces state machine via Task.validate_status_change()
    NotionClient: Rate-limited API calls for status updates

Dependencies:
    - Story 5.1: 27-status workflow state machine with review gates
    - Story 5.2: Review gate enforcement (VIDEO_READY → VIDEO_APPROVED transition)
    - Story 5.4: Video review interface in Notion
    - Epic 2: NotionClient for status synchronization

Usage:
    from app.services.review_service import ReviewService

    service = ReviewService()
    await service.approve_videos(task_id=task_id, notion_page_id=page_id)
    await service.reject_videos(task_id=task_id, reason="Quality issues", notion_page_id=page_id)
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.notion import NotionClient
from app.config import get_notion_api_token
from app.constants import INTERNAL_TO_NOTION_STATUS
from app.exceptions import InvalidStateTransitionError
from app.models import Task, TaskStatus
from app.utils.logging import get_logger

log = get_logger(__name__)


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

    async def _update_notion_status_async(
        self,
        notion_page_id: str,
        status: TaskStatus,
        correlation_id: str | None = None,
    ) -> None:
        """Update Notion page status asynchronously (non-blocking).

        This method is called after successful database commit to sync status
        back to Notion. Errors are logged but don't affect the review operation.

        Args:
            notion_page_id: Notion page ID (32 chars, no dashes)
            status: Internal TaskStatus enum value
            correlation_id: Correlation ID for logging (optional)
        """
        try:
            notion_token = get_notion_api_token()
            if not notion_token:
                log.info(
                    "notion_status_update_skipped",
                    correlation_id=correlation_id,
                    page_id=notion_page_id,
                    reason="notion_token_not_configured",
                )
                return

            # Map internal status to Notion status
            notion_status = INTERNAL_TO_NOTION_STATUS.get(status.value)
            if not notion_status:
                log.warning(
                    "notion_status_mapping_not_found",
                    correlation_id=correlation_id,
                    page_id=notion_page_id,
                    internal_status=status.value,
                )
                return

            # Update Notion (rate limited, auto-retry)
            notion_client = NotionClient(auth_token=notion_token)
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

        except Exception as e:
            # Log error but don't fail the review operation
            # Notion sync is best-effort, not critical
            log.error(
                "notion_status_update_failed",
                correlation_id=correlation_id,
                page_id=notion_page_id,
                status=status.value,
                error=str(e),
                exc_info=True,
            )
