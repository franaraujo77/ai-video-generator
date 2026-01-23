# Manual Retry Guide (Story 6.7)

This guide explains how to manually retry failed video generation tasks through Notion.

## Overview

When a video generation task fails after exhausting automatic retries (3 attempts with exponential backoff), you can manually trigger a retry by changing the task's status in Notion. The system detects this status change and re-enqueues the task while preserving completed work.

## When to Use Manual Retry

Use manual retry when:
- **Automatic retries exhausted**: Task reached error status (ASSET_ERROR, VIDEO_ERROR, AUDIO_ERROR, UPLOAD_ERROR) after 3 automatic retry attempts
- **Transient failure resolved**: The underlying issue (API timeout, rate limit, network error) is likely resolved
- **Partial progress preserved**: The task has checkpoints from completed steps that should be preserved

**Do NOT use manual retry for**:
- Tasks currently in progress (GENERATING_ASSETS, GENERATING_VIDEO, etc.)
- Terminal failures requiring code changes or configuration updates
- Tasks with corrupted or invalid data

## How to Manually Retry a Task

### Step 1: Identify Failed Tasks

In your Notion database, look for tasks with error statuses:
- **ASSET_ERROR**: Asset generation failed
- **VIDEO_ERROR**: Video generation failed
- **AUDIO_ERROR**: Audio/narration generation failed
- **UPLOAD_ERROR**: YouTube upload failed

### Step 2: Choose Retry Strategy

You have two retry strategies:

#### A. Full Restart (QUEUED)
Retry the entire pipeline from the beginning, preserving completed steps:

1. Open the failed task in Notion
2. Change the **Status** field from error status → **QUEUED**
3. The system will:
   - Reset retry counter to 0
   - Preserve error log with manual retry marker
   - Clear checkpoint for failed step only
   - Preserve checkpoints for completed steps
   - Re-enqueue task for worker claiming

**Example**: VIDEO_ERROR → QUEUED
- Asset generation checkpoint preserved (skip re-generation)
- Video generation checkpoint cleared (re-run from beginning)

#### B. Partial Restart (Resume from Specific Step)
Resume from a specific approval gate:

| Failed Status | Resume From | Next Step |
|---------------|-------------|-----------|
| VIDEO_ERROR | ASSETS_APPROVED | Retry video generation only |
| AUDIO_ERROR | VIDEO_APPROVED | Retry audio generation only |
| UPLOAD_ERROR | APPROVED | Retry YouTube upload only |

**Example**: VIDEO_ERROR → ASSETS_APPROVED
1. Open the failed task in Notion
2. Change **Status** from VIDEO_ERROR → **ASSETS_APPROVED**
3. The system will:
   - Skip asset generation (already approved)
   - Retry video generation from composite creation

### Step 3: Monitor Retry Progress

After triggering manual retry:

1. **Check Status Updates**: The task status will progress through the pipeline stages
2. **Review Error Log**: The error log shows:
   ```
   --- MANUAL RETRY TRIGGERED ---
   Timestamp: 2026-01-23T14:00:00.000000+00:00
   Previous Status: video_error
   New Status: queued
   Retry Attempt: Manual (reset automatic retry counter from 3 to 0)
   ```
3. **Verify Checkpoints**: Completed steps are preserved, failed step checkpoint cleared
4. **Track Metrics**: Check `retry_count` field (reset to 0 after manual retry)

## Status Transition Matrix

| From Status | Valid Retry Transitions | Effect |
|-------------|------------------------|--------|
| ASSET_ERROR | QUEUED, GENERATING_ASSETS | Full restart or retry asset generation |
| VIDEO_ERROR | QUEUED, ASSETS_APPROVED, GENERATING_VIDEO | Full restart, resume from assets, or retry video |
| AUDIO_ERROR | QUEUED, VIDEO_APPROVED, GENERATING_AUDIO | Full restart, resume from video, or retry audio |
| UPLOAD_ERROR | QUEUED, APPROVED, UPLOADING | Full restart, resume from approval, or retry upload |

## What Happens During Manual Retry

When you change the status in Notion, the system automatically:

1. **Detects Manual Retry**: `is_manual_retry_transition()` identifies the status change
2. **Resets Retry Metadata**:
   - `retry_count` → 0 (fresh automatic retry budget)
   - `next_retry_at` → None (immediate re-queuing)
3. **Preserves Error History**:
   - Existing error log preserved
   - Manual retry marker appended with timestamp, old/new status
4. **Smart Checkpoint Clearing**:
   - Failed step checkpoint cleared (re-run from beginning)
   - Completed step checkpoints preserved (skip re-running)
5. **Re-enqueues Task**:
   - Task status updated to new value
   - Worker picks up task on next poll cycle (~30 seconds)
6. **Logs Event**: Structured log entry with correlation ID for debugging

## Error Log Format

After manual retry, the error log includes:

```
[Previous errors and retry attempts...]

--- MANUAL RETRY TRIGGERED ---
Timestamp: 2026-01-23T14:00:00.000000+00:00
Previous Status: video_error
New Status: queued
Retry Attempt: Manual (reset automatic retry counter from 3 to 0)
```

This marker is appended to existing logs, preserving full failure history.

## Checkpoint Preservation

Manual retry uses **smart checkpoint clearing** to avoid re-running completed steps:

### Example: VIDEO_ERROR → QUEUED

**Before Manual Retry**:
- `completed_steps`: [asset_generation, video_generation]
- `step_metadata`: {completed_video_clips: [1, 2, 3, 4, 5]}
- Status: VIDEO_ERROR

**After Manual Retry**:
- `completed_steps`: [asset_generation] (video checkpoint cleared)
- `step_metadata`: {} (sub-step metadata cleared)
- Status: QUEUED

**Result**: Asset generation skipped, video generation retried from clip 1

## Best Practices

### When to Use Full Restart (QUEUED)
- First manual retry attempt
- Multiple steps failed or uncertain which step failed
- Want to verify entire pipeline works

### When to Use Partial Restart (Approval Status)
- Confident the failure is isolated to one step
- Previous steps verified working (assets approved, video approved, etc.)
- Want to save time by skipping completed steps

### Monitoring Tips
1. **Check Worker Logs**: Look for correlation ID in structured logs
2. **Review Checkpoint Data**: Verify completed_steps list matches expectations
3. **Track Retry Patterns**: Multiple manual retries for same task may indicate systemic issue

### Troubleshooting

**Task Stuck After Manual Retry**
- Verify status is in valid retry transition (see matrix above)
- Check worker is running (`docker ps` or Railway logs)
- Review error log for validation errors

**Checkpoints Not Preserving**
- Verify task has `completed_steps` field populated
- Check if failed step checkpoint was properly cleared
- Review `step_metadata` to confirm sub-step data

**Manual Retry Not Detected**
- Ensure status change is from error status to retry status
- Check Notion webhook is firing (may take 30-60 seconds)
- Verify task status in database matches Notion

## Integration with Other Stories

Manual retry integrates with:
- **Story 6.1**: Retry classification (distinguishes manual from automatic retry)
- **Story 6.2**: Exponential backoff (resets retry_count to 0)
- **Story 6.3**: Checkpoint resume (preserves completed steps)
- **Story 6.4**: Granular error status (specific error status → retry mapping)
- **Story 6.5**: Error logging (preserves error history)

## Technical Details

For developers and system administrators:

### Detection Logic
```python
def is_manual_retry_transition(old_status: TaskStatus, new_status: TaskStatus) -> bool:
    """Detect error status → retry status transition."""
    manual_retry_map = {
        TaskStatus.ASSET_ERROR: {TaskStatus.QUEUED, TaskStatus.GENERATING_ASSETS},
        TaskStatus.VIDEO_ERROR: {TaskStatus.QUEUED, TaskStatus.ASSETS_APPROVED, TaskStatus.GENERATING_VIDEO},
        TaskStatus.AUDIO_ERROR: {TaskStatus.QUEUED, TaskStatus.VIDEO_APPROVED, TaskStatus.GENERATING_AUDIO},
        TaskStatus.UPLOAD_ERROR: {TaskStatus.QUEUED, TaskStatus.APPROVED, TaskStatus.UPLOADING},
    }
    return old_status in manual_retry_map and new_status in manual_retry_map[old_status]
```

### Database Changes
- `retry_count` reset to 0
- `next_retry_at` set to None
- `error_log` appended (not replaced)
- `completed_steps` filtered (failed step removed)
- `step_metadata` cleared (sub-step data invalid after retry)
- `status` updated to new value
- `updated_at` timestamp updated

### Logging Event
```json
{
  "event": "manual_retry_triggered",
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "old_status": "video_error",
  "new_status": "queued",
  "failed_step": "video_generation",
  "original_retry_count": 3,
  "is_manual_retry": true,
  "correlation_id": "abc-123-def-456"
}
```

## Related Documentation

- **Error Handling Architecture**: `docs/error-handling-architecture.md`
- **Checkpoint Resume Design**: `docs/checkpoint-resume-design.md`
- **Retry Orchestration**: `docs/retry-orchestration.md`
- **Notion Integration**: `docs/notion-integration.md`

## FAQ

**Q: Can I manually retry a task that's currently running?**
A: No, manual retry only works for tasks in error statuses (ASSET_ERROR, VIDEO_ERROR, AUDIO_ERROR, UPLOAD_ERROR).

**Q: Will manual retry lose my completed work?**
A: No, completed step checkpoints are preserved. Only the failed step checkpoint is cleared.

**Q: How many times can I manually retry?**
A: Unlimited. Each manual retry resets the automatic retry counter to 0, giving you 3 more automatic retries.

**Q: What if manual retry fails again?**
A: The task will go through automatic retries (up to 3 attempts with exponential backoff) before reaching error status again.

**Q: Can I manually retry from the middle of a step?**
A: No, manual retry clears the failed step checkpoint, so the step re-runs from the beginning. However, completed steps are skipped.

**Q: How long does manual retry take to process?**
A: The worker polls every ~30 seconds, so the task should be claimed within 1 minute of status change.

---

**Story**: 6.7 - Manual Retry Trigger
**Last Updated**: 2026-01-23
**Status**: Complete (All 8 tasks implemented, 18 tests passing)
