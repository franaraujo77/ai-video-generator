# Notion Database Schema Changes - Story 6.4

**Story:** 6.4 - Granular Error Status Updates
**Epic:** 6 - Reliability & Error Recovery
**Date:** 2026-01-22
**Status:** Implementation Complete

---

## Overview

Story 6.4 introduces rich error context visibility in Notion by populating two properties with structured error information and checkpoint progress data:

1. **Error Log** (existing property, enhanced functionality)
2. **Progress** (new property added in Story 6.3, Task 9)

These properties provide users with immediate visibility into:
- What failed and where (failure location)
- Why it failed (error classification and API service)
- What's happening next (retry schedule)
- How much progress was saved (checkpoint data)
- What action to take (recommendations)

---

## Property Requirements

### 1. Error Log Property

**Property Type:** `rich_text`
**Required:** No (nullable)
**Auto-populated:** Yes (by `push_error_payload_to_notion`)
**User Editable:** No (append-only from system)

**Purpose:** Display structured error details with failure context, retry scheduling, and actionable recommendations.

**Format:** Markdown with sections:
```markdown
## 🚨 Error Details

**Step:** asset_generation
**Location:** Asset 6/22 - Character portrait of Pikachu
**Error Category:** TRANSIENT
**Service:** Gemini API
**Message:** HTTP 429: Rate limited

## 🔄 Retry Information

**Attempt:** 2/5
**Next Retry:** 2026-01-22T15:45:30Z (in 5 minutes)

## 💾 Checkpoint Progress

**Completed Assets:** [1, 2, 3, 4, 5]
**Total Assets:** 22

## 💡 Recommendation

Retry with exponential backoff. The API rate limit will reset shortly.
```

**Implementation:** `app/schemas/error_payload.py:113-156` (`ErrorPayload.format_for_notion()`)

**Data Source:** `ErrorPayload` schema built by `retry_orchestrator.schedule_retry()`

**Notion Schema Requirements:**
- Property name: `Error Log` (case-sensitive)
- Property type: `rich_text`
- Maximum length: 2000 characters per text block (Notion API limit)
- Supports markdown formatting: bold (`**text**`), code (`` `text` ``), emojis

**Example Values:**

*Transient error with retry scheduled:*
```
## 🚨 Error Details

**Step:** video_generation
**Location:** Video Clip 12/18
**Error Category:** TRANSIENT
**Service:** KIE.ai (Kling)
**Message:** HTTP 503: Service temporarily unavailable

## 🔄 Retry Information

**Attempt:** 1/5
**Next Retry:** 2026-01-22T15:35:00Z (in 1 minute)

## 💾 Checkpoint Progress

**Completed Video Clips:** [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
**Total Clips:** 18

## 💡 Recommendation

Retry automatically. Service outage detected.
```

*Permanent error with no retry:*
```
## 🚨 Error Details

**Step:** asset_generation
**Location:** Asset 8/22 - Environment background forest
**Error Category:** CONFIGURATION
**Service:** Gemini API
**Message:** HTTP 401: Unauthorized

## 🔄 Retry Information

**Attempt:** Terminal (no retry)
**Reason:** Configuration error - requires manual intervention

## 💡 Recommendation

Check API key configuration in Railway environment variables.
```

### 2. Progress Property (NEW)

**Property Type:** `rich_text`
**Required:** No (nullable)
**Auto-populated:** Yes (by `push_task_to_notion` via `format_checkpoint_progress`)
**User Editable:** No (system-managed)

**Purpose:** Display checkpoint progress for resumability during step execution.

**Format:** Markdown with step-specific progress indicators:

**Video Generation:**
```markdown
**Video Generation Progress:**
Completed: 10/18 clips
Clips: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
```

**Asset Generation:**
```markdown
**Asset Generation Progress:**
Completed: 15/22 assets
Assets: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
```

**Narration Generation:**
```markdown
**Narration Generation Progress:**
Completed: 7/18 clips
Clips: [1, 2, 3, 4, 5, 6, 7]
```

**SFX Generation:**
```markdown
**SFX Generation Progress:**
Completed: 12/18 clips
Clips: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
```

**Implementation:** `app/services/notion_sync.py:633-673` (`format_checkpoint_progress()`)

**Data Source:** `Task.step_metadata` JSON field containing:
- `completed_video_clips`: list of integers
- `completed_assets`: list of integers
- `total_assets`: integer (variable, determined during story generation)
- `completed_narration_clips`: list of integers
- `completed_sfx_clips`: list of integers

**Notion Schema Requirements:**
- Property name: `Progress` (case-sensitive)
- Property type: `rich_text`
- Maximum length: 2000 characters per text block
- Supports markdown formatting: bold (`**text**`)

**Example Values:**

*Mid-step video generation:*
```
**Video Generation Progress:**
Completed: 8/18 clips
Clips: [1, 2, 3, 4, 5, 6, 7, 8]
```

*Completed asset generation:*
```
**Asset Generation Progress:**
Completed: 22/22 assets
Assets: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]
```

*No checkpoint data (step not started or completed):*
```
(empty - property not populated)
```

---

## Database Setup Instructions

### For Existing Databases

If your Notion database already has these properties from earlier epics, verify they match the specifications above:

1. **Verify Error Log Property:**
   ```
   - Name: "Error Log"
   - Type: rich_text (NOT text or long text)
   - Nullable: Yes
   ```

2. **Add Progress Property (if missing):**
   ```
   - Click "+ Add Property"
   - Name: "Progress"
   - Type: rich_text
   - Click "Done"
   ```

### For New Databases

Follow these steps when creating a new Video Entries database:

1. **Error Log Property:**
   - Property Name: `Error Log`
   - Property Type: `Rich Text`
   - Leave empty by default
   - System will populate on errors

2. **Progress Property:**
   - Property Name: `Progress`
   - Property Type: `Rich Text`
   - Leave empty by default
   - System will populate during step execution

### Verification Steps

After setup, verify properties are correctly configured:

1. **Test Error Log Population:**
   - Create a test task with invalid API credentials
   - Trigger error (e.g., set status to "Queued")
   - Wait for error to occur
   - Check Notion - Error Log should populate with formatted error details

2. **Test Progress Population:**
   - Create a valid test task
   - Monitor task as it progresses through video/asset generation
   - Check Notion - Progress should update showing completed items

3. **Check Markdown Rendering:**
   - Error Log should show bold text, emojis, code blocks
   - Progress should show bold headers and lists
   - If formatting appears as raw markdown, property type is wrong (change to `rich_text`)

---

## Integration Points

### Code Locations

**Error Log Population:**
- **Entry Point:** `app/services/pipeline_orchestrator.py:437-488` (step-level error handler)
- **ErrorPayload Builder:** `app/services/retry_orchestrator.py:schedule_retry()`
- **Notion Push:** `app/services/notion_sync.py:push_error_payload_to_notion()`
- **Formatter:** `app/schemas/error_payload.py:ErrorPayload.format_for_notion()`

**Progress Population:**
- **Checkpoint Capture:**
  - `app/services/video_generation.py:124-142` (video clips)
  - `app/services/asset_generation.py:110-128` (assets)
  - `app/services/narration_generation.py:95-113` (narration)
  - `app/services/sfx_generation.py:95-113` (SFX)
- **Progress Extractor:** `app/services/checkpoint_service.py:extract_partial_progress_for_error()`
- **Notion Formatter:** `app/services/notion_sync.py:633-673` (`format_checkpoint_progress()`)
- **Notion Push:** `app/services/notion_sync.py:726-766` (`_build_notion_properties()`)

### Data Flow

**Error Log Data Flow:**
```
1. Service raises exception with ErrorContext
2. pipeline_orchestrator catches exception
3. Calls retry_orchestrator.schedule_retry()
4. schedule_retry() builds ErrorPayload with:
   - error_classifier.classify_error() → error_category, api_service
   - error_classifier.extract_failure_location() → FailureLocation
   - error_classifier.get_recommendation() → recommendation
   - checkpoint_service.extract_partial_progress_for_error() → partial_progress
   - Calculates exponential backoff → next_retry_at
5. Returns ErrorPayload to pipeline_orchestrator
6. pipeline_orchestrator calls push_error_payload_to_notion()
7. ErrorPayload.format_for_notion() generates markdown
8. Notion API updates Error Log property
```

**Progress Data Flow:**
```
1. Service completes sub-step (e.g., video clip 5/18)
2. Service calls checkpoint_service.checkpoint_step()
3. checkpoint_step() updates task.step_metadata JSON:
   - Appends to completed_video_clips: [1,2,3,4,5]
   - Commits to database
4. Regular Notion sync loop runs (every 60s)
5. notion_sync.push_task_to_notion() reads task
6. Calls format_checkpoint_progress(task.step_metadata, task.status)
7. format_checkpoint_progress() extracts relevant progress for current step
8. Formats as markdown (e.g., "Completed: 5/18 clips")
9. Notion API updates Progress property
```

---

## Property Behavior

### Error Log

**When Populated:**
- Any exception during pipeline execution
- Transient errors (rate limits, timeouts)
- Permanent errors (auth failures, quota exceeded)
- Configuration errors (missing API keys)

**When Cleared:**
- Never cleared automatically
- Manual user edit can clear
- Overwrites on new error (not appended)

**Fire-and-Forget Pattern:**
- If Notion push fails, error is logged but not re-raised
- Database retains error state even if Notion sync fails
- See `pipeline_orchestrator.py:477-483` for exception handling

### Progress

**When Populated:**
- During step execution with checkpoint support
- Steps with checkpoints:
  - asset_generation (variable total_assets)
  - video_generation (18 clips)
  - narration_generation (18 clips)
  - sfx_generation (18 clips)

**When Cleared:**
- Step completes successfully → step_metadata cleared → Progress becomes empty
- Step errors → Progress preserves last checkpoint for resume

**When NOT Populated:**
- Steps without checkpoints (composite_creation, assembling_final)
- Task in terminal states (Published, Cancelled)
- Task not yet started (Draft, Queued)

---

## Testing

### Test Coverage

**Error Log Tests:**
- ✅ `test_pipeline_error_integration_simplified.py::test_error_handler_pushes_to_notion` - Verifies ErrorPayload pushed to Notion
- ✅ `test_retry_orchestrator.py::test_schedule_retry_transient_error` - Verifies ErrorPayload built correctly
- ✅ `test_error_payload.py::test_format_for_notion_complete_payload` - Verifies markdown formatting

**Progress Tests:**
- ✅ `test_checkpoint_error_progress.py` - All 7 tests for extract_partial_progress_for_error()
- ✅ `test_notion_checkpoint_progress.py` - Tests format_checkpoint_progress() markdown generation
- ✅ `test_video_generation_checkpointing.py` - Tests checkpoint capture in video service
- ✅ `test_asset_generation_checkpointing.py` - Tests checkpoint capture in asset service

### Manual Verification

**Error Log:**
1. Deploy to Railway with invalid Gemini API key
2. Create test task in Notion (status: "Queued")
3. Task will fail with "HTTP 401: Unauthorized"
4. Check Notion Error Log property - should show formatted error with:
   - ✅ Error category: CONFIGURATION
   - ✅ Service: Gemini API
   - ✅ Recommendation: "Check API key configuration"
   - ✅ No retry scheduled (terminal error)

**Progress:**
1. Deploy to Railway with valid credentials
2. Create test task in Notion (status: "Queued")
3. Monitor task as it generates videos
4. Check Notion Progress property - should update showing:
   - ✅ "Completed: 5/18 clips" (increases over time)
   - ✅ Clips list: [1, 2, 3, 4, 5]
5. Verify Progress clears when step completes

---

## Migration Notes

### Backward Compatibility

**Error Log:**
- Property existed before Story 6.4
- Previously populated with simple retry messages (Story 6.2)
- Now enhanced with rich ErrorPayload markdown (Story 6.4)
- Old format: "Retry 2/5 scheduled for 2026-01-22T15:35:00Z"
- New format: Full markdown with sections (see examples above)
- **No migration required** - property type unchanged (rich_text)

**Progress:**
- NEW property added in Story 6.3, Task 9
- Did not exist before Epic 6
- **Migration required for existing databases:**
  1. Add "Progress" property (type: rich_text)
  2. Share database with Notion integration (if not already shared)
  3. Restart application to enable Progress sync

### Schema Version

This document describes schema version **6.4.0** (Epic 6, Story 6.4).

**Previous versions:**
- 6.2.0: Error Log with simple retry messages
- 6.3.0: Progress property added for checkpoint visibility

**Next version:**
- TBD (Epic 7 may add YouTube metadata properties)

---

## Troubleshooting

### Error Log Not Populating

**Symptom:** Task fails but Error Log stays empty

**Possible Causes:**
1. Property name mismatch (case-sensitive: must be "Error Log")
2. Property type wrong (must be `rich_text`, not `text`)
3. Database not shared with Notion integration
4. Notion API rate limit exceeded (3 requests/second)

**Debug Steps:**
```bash
# Check Railway logs for Notion push errors
railway logs --filter "notion_error_push_failed"

# Verify property name
railway logs --filter "Error Log"

# Check for rate limit errors
railway logs --filter "rate_limit"
```

**Solution:**
1. Verify property name: Exactly "Error Log" (capital E, capital L)
2. Verify property type: rich_text (click property → "Edit property" → check type)
3. Re-share database: Database → "..." → "+ Add connections" → Select integration
4. Check app logs for specific error messages

### Progress Not Updating

**Symptom:** Task progresses but Progress property stays empty

**Possible Causes:**
1. Property missing (not added to database)
2. Property name mismatch (case-sensitive: must be "Progress")
3. Step doesn't support checkpoints (e.g., composite_creation)
4. Sync interval delay (up to 60 seconds)

**Debug Steps:**
```bash
# Check if checkpoints are being saved to DB
railway logs --filter "checkpoint_saved"

# Check if Progress is being formatted
railway logs --filter "format_checkpoint_progress"

# Verify Notion sync running
railway logs --filter "notion_sync_loop_started"
```

**Solution:**
1. Add Progress property if missing (type: rich_text)
2. Wait 60 seconds for next sync interval
3. Verify task is in a checkpoint-supported step (Generating Assets, Generating Video, Generating Audio, Generating SFX)
4. Check step_metadata in database: `SELECT step_metadata FROM tasks WHERE id='<task_id>';`

### Markdown Not Rendering

**Symptom:** Notion shows raw markdown text instead of formatted output

**Cause:** Property type is `text` instead of `rich_text`

**Solution:**
1. Click property name in database
2. Click "Edit property"
3. Change type from "Text" to "Rich text"
4. Notion will preserve existing content and render markdown

---

## References

- **Story 6.4 Specification:** `_bmad-output/implementation-artifacts/6-4-granular-error-status-updates.md`
- **ErrorPayload Schema:** `app/schemas/error_payload.py`
- **Checkpoint Service:** `app/services/checkpoint_service.py`
- **Notion Sync Service:** `app/services/notion_sync.py`
- **Retry Orchestrator:** `app/services/retry_orchestrator.py`
- **Pipeline Orchestrator:** `app/services/pipeline_orchestrator.py`

---

**Document Status:** Complete
**Last Updated:** 2026-01-22
**Implementation Status:** Code Complete, Tests Passing ✅
