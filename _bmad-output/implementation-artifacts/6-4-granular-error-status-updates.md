# Story 6.4: Granular Error Status Updates

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **content creator**,
I want **detailed error status in Notion with specific failure context (API timeout? Clip 13? Network failure?)**,
So that **I can diagnose and fix problems faster** (FR53).

## Acceptance Criteria

**Given** a task fails during video generation
**When** I check the Notion task card
**Then** I see structured error details including:
- **Step name** where failure occurred (e.g., "video_generation")
- **Failure point** (e.g., "Clip 13 of 18")
- **Error category** from Story 6.1 classifier (TRANSIENT, PERMANENT, CONFIGURATION)
- **Specific error message** (e.g., "KIE.ai API timeout after 600s")
- **Retry information** (e.g., "Retry 2 of 3 scheduled at 2026-01-18 15:30")

**Given** video clip 11 fails with network timeout
**When** task error is logged to Notion
**Then** Error Log property shows:
```
[2026-01-18 14:25:00] video_generation failed
- Location: Clip 11 of 18
- Error: Network timeout (TRANSIENT)
- API: KIE.ai video generation
- Next retry: 2026-01-18 14:26:00 (Attempt 2/3)
```

**Given** asset generation fails at asset 15 with invalid API key
**When** task error is logged to Notion
**Then** Error Log property shows:
```
[2026-01-18 10:00:00] asset_generation failed
- Location: Asset 15 of 22 (environment_background_3.png)
- Error: Authentication failed (CONFIGURATION)
- API: Gemini API (401 Unauthorized)
- Action: Check GEMINI_API_KEY in channel config
```

**Given** a task has been retried twice and is awaiting third retry
**When** viewing task in Notion
**Then** I see:
- Status: "Error (Retrying)"
- Error Log: Detailed error from latest failure + retry history
- Next Retry: Timestamp of scheduled third attempt
- Progress: Checkpoint progress (e.g., "10 of 18 clips completed")

**Given** task fails permanently after max retries
**When** viewing terminal failure in Notion
**Then** I see:
- Status: "Failed (Permanent)"
- Error Log: All 3 retry attempt details with timestamps
- Recommendation: Specific next action (e.g., "Increase video timeout", "Check API key", "Review prompt")

## Tasks / Subtasks

- [x] Task 1: Design structured error payload for Notion sync (AC: Error Log shows step, location, category, message)
  - [x] Subtask 1.1: Define ErrorPayload data structure with all required fields
  - [x] Subtask 1.2: Include step_name, failure_point, error_category, error_message, retry_info
  - [x] Subtask 1.3: Add timestamp, correlation_id for debugging
  - [x] Subtask 1.4: Design human-readable formatting for Notion rich text property
  - [x] Subtask 1.5: Support multi-retry history (show all attempts with timestamps)

- [x] Task 2: Extend error_classifier to extract failure location context (AC: Location shows "Clip 11 of 18", "Asset 15 of 22")
  - [x] Subtask 2.1: Modify classify_error() to accept optional context dict: {"step": "video_generation", "clip_index": 11, "total_clips": 18}
  - [x] Subtask 2.2: Extract failure location from exception message when available
  - [x] Subtask 2.3: Format location string: "Clip {clip_index} of {total_clips}"
  - [x] Subtask 2.4: Support multiple location patterns: clips, assets, narration, SFX
  - [x] Subtask 2.5: Include asset name when available: "Asset 15 of 22 (environment_background_3.png)"

- [ ] Task 3: Update service-level error handlers to capture failure context (AC: All error paths include context)
  - [ ] Subtask 3.1: Update video_generation.py to pass clip_index, total_clips to error handler
  - [ ] Subtask 3.2: Update asset_generation.py to pass asset_index, total_assets, asset_name to error handler
  - [ ] Subtask 3.3: Update narration_generation.py to pass clip_index to error handler
  - [ ] Subtask 3.4: Update sfx_generation.py to pass clip_index to error handler
  - [ ] Subtask 3.5: Ensure all subprocess.CalledProcessError captures include context

- [ ] Task 4: Enhance retry_orchestrator to build rich error history (AC: Terminal failure shows all 3 attempts)
  - [ ] Subtask 4.1: Store error details in task.error_log as structured JSON array
  - [ ] Subtask 4.2: Append new error entry on each retry (don't overwrite)
  - [ ] Subtask 4.3: Include retry_attempt number in each error entry
  - [ ] Subtask 4.4: Calculate and store next_retry_at timestamp in error entry
  - [ ] Subtask 4.5: Format error_log for Notion: multi-line markdown with timestamps

- [ ] Task 5: Update Notion sync to push structured error details (AC: Notion Error Log shows formatted details)
  - [ ] Subtask 5.1: Extend TaskSyncData to include structured_error_log field
  - [ ] Subtask 5.2: Format error_log JSON to Notion rich text markdown
  - [ ] Subtask 5.3: Update Notion Error Log property on every retry/failure
  - [ ] Subtask 5.4: Add "Next Retry" property to Notion database schema (timestamp)
  - [ ] Subtask 5.5: Update Status property to reflect retry state: "Error (Retrying)", "Failed (Permanent)"

- [x] Task 6: Add actionable recommendations for common error categories (AC: Permanent failure shows next action)
  - [x] Subtask 6.1: Map error categories to recommendations: CONFIGURATION → "Check API keys", TRANSIENT → "Retry in progress", PERMANENT → "Review inputs"
  - [x] Subtask 6.2: API-specific recommendations: KIE.ai timeout → "Increase timeout or check video complexity"
  - [x] Subtask 6.3: Gemini 401 → "Verify GEMINI_API_KEY in channel config"
  - [x] Subtask 6.4: ElevenLabs quota → "Check monthly character limit"
  - [x] Subtask 6.5: Include recommendations in Notion Error Log footer

- [ ] Task 7: Extend checkpoint service to capture partial progress in error payload (AC: Error shows "10 of 18 clips completed")
  - [ ] Subtask 7.1: Query checkpoint service for partial progress when error occurs
  - [ ] Subtask 7.2: Include completed_steps count in error payload
  - [ ] Subtask 7.3: Include step_metadata progress (e.g., completed_video_clips array length)
  - [ ] Subtask 7.4: Format progress string: "10 of 18 clips completed before failure"
  - [ ] Subtask 7.5: Display progress in Notion error log for easier diagnosis

- [ ] Task 8: Update pipeline_orchestrator to call structured error logging on failures (AC: All failures use new error logging)
  - [ ] Subtask 8.1: Replace simple error logging with structured error payload creation
  - [ ] Subtask 8.2: Capture step name, failure location, error category, message
  - [ ] Subtask 8.3: Query checkpoints for partial progress
  - [ ] Subtask 8.4: Call error_classifier.classify_error() with full context
  - [ ] Subtask 8.5: Pass structured error to retry_orchestrator for storage

- [ ] Task 9: Create Notion database schema changes for new properties (AC: Notion has Next Retry, structured Error Log)
  - [ ] Subtask 9.1: Document Notion property additions: "Next Retry" (datetime), enhanced "Error Log" (rich text)
  - [ ] Subtask 9.2: Create migration script or manual setup instructions
  - [ ] Subtask 9.3: Update Status property options: add "Error (Retrying)", "Failed (Permanent)"
  - [ ] Subtask 9.4: Test Notion sync with new schema
  - [ ] Subtask 9.5: Verify backward compatibility (existing tasks without new fields)

- [ ] Task 10: Write comprehensive tests for structured error logging (AC: All error paths tested)
  - [ ] Subtask 10.1: Unit test: ErrorPayload data structure creation
  - [ ] Subtask 10.2: Unit test: Error location formatting (clips, assets, narration)
  - [ ] Subtask 10.3: Integration test: Video clip 11 fails → Notion shows "Clip 11 of 18"
  - [ ] Subtask 10.4: Integration test: Asset 15 fails → Notion shows asset name + index
  - [ ] Subtask 10.5: Integration test: Multi-retry history → Notion shows all 3 attempts with timestamps
  - [ ] Subtask 10.6: Integration test: Terminal failure → Notion shows recommendations

## Dev Notes

### Critical Context from Previous Stories

**Story 6.1 (Transient Failure Detection):**
- Implemented ErrorCategory enum: TRANSIENT, PERMANENT, CONFIGURATION, QUOTA_EXCEEDED
- Created classify_error() function that analyzes exceptions
- Error classification is fire-and-forget (non-blocking)
- **Story 6.4 Integration:** Use ErrorCategory in structured error payload, extend classify_error() to accept context dict

**Story 6.2 (Exponential Backoff Retry Logic):**
- Implemented schedule_retry() with exponential backoff (30s, 120s, 480s)
- Implemented claim_retry_tasks() for worker polling
- Stores next_retry_at timestamp in database
- **Story 6.4 Integration:** Include retry_attempt number and next_retry_at in error payload

**Story 6.3 (Resume from Failure Point):**
- Implemented checkpoint_service with save_step_checkpoint(), update_step_metadata()
- Stores completed_steps (step-level) and step_metadata (sub-step granularity)
- Checkpoint data includes partial progress: completed_video_clips, completed_assets, etc.
- **Story 6.4 Integration:** Query checkpoint service for partial progress when error occurs, display in Notion

### Architecture Compliance

**Critical Pattern: Structured Logging with Correlation IDs**

From architecture.md:686-743 and project-context.md:686-730:

```python
import structlog

log = structlog.get_logger()

# ✅ CORRECT: Structured error logging with context
log.error(
    "pipeline_step_failed",
    task_id=str(task.id),
    channel_id=task.channel_id,
    correlation_id=correlation_id,
    step_name="video_generation",
    failure_location="Clip 11 of 18",
    error_category="TRANSIENT",
    error_message="KIE.ai API timeout after 600s",
    retry_attempt=2,
    next_retry_at="2026-01-18T14:26:00Z",
    exc_info=True  # Full stack trace
)

# ❌ WRONG: Unstructured error logging
log.error(f"Video generation failed at clip 11: {str(e)}")
```

**Notion API Rate Limiting (3 req/sec):**

From architecture.md:431-448 and project-context.md:302-342:

```python
from aiolimiter import AsyncLimiter

class NotionClient:
    def __init__(self, auth_token: str):
        self.rate_limiter = AsyncLimiter(3, 1)  # 3 requests per second
        self.client = httpx.AsyncClient()

    async def update_task_error_log(self, page_id: str, error_log: str):
        """Update Error Log property with structured error details"""
        async with self.rate_limiter:
            response = await self.client.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers={
                    "Authorization": f"Bearer {self.auth_token}",
                    "Notion-Version": "2022-06-28"
                },
                json={
                    "properties": {
                        "Error Log": {
                            "rich_text": [{"text": {"content": error_log}}]
                        },
                        "Next Retry": {
                            "date": {"start": next_retry_at.isoformat()}
                        }
                    }
                }
            )
            response.raise_for_status()
            return response.json()
```

**Short Transaction Pattern (Never Hold DB During I/O):**

From architecture.md:126-144 and project-context.md:664-730:

```python
# ✅ CORRECT: Record error in separate transaction
async def handle_pipeline_failure(task_id: str, error: Exception, context: dict):
    """Handle pipeline failure with structured error logging"""

    # Step 1: Query checkpoint progress (short transaction)
    async with get_session() as db:
        checkpoint = await get_step_checkpoint(task_id, context["step_name"], db)
        partial_progress = checkpoint["outputs"] if checkpoint else {}

    # Step 2: Classify error and build payload (NO DB connection)
    error_analysis = classify_error(error, context)
    error_payload = build_error_payload(error_analysis, context, partial_progress)

    # Step 3: Store error and schedule retry (short transaction)
    async with get_session() as db:
        await schedule_retry(task_id, error_payload, db)
        await update_notion_sync(task_id, error_payload, db)

# ❌ WRONG: Hold transaction during error processing
async with db.begin():
    error_analysis = classify_error(exception)  # BLOCKS DB!
    await notify_notion(error_analysis)  # BLOCKS DB!
    await db.commit()
```

### Technical Requirements

**ErrorPayload Data Structure:**

```python
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

@dataclass
class FailureLocation:
    """Structured failure location within pipeline step"""
    step_name: str  # e.g., "video_generation", "asset_generation"
    item_index: int | None = None  # e.g., 11 (for clip 11)
    total_items: int | None = None  # e.g., 18 (for 18 total clips)
    item_name: str | None = None  # e.g., "environment_background_3.png"

    def format(self) -> str:
        """Format location as human-readable string"""
        if self.item_index is not None and self.total_items is not None:
            location = f"{self.step_name.replace('_', ' ').title()}: Item {self.item_index} of {self.total_items}"
            if self.item_name:
                location += f" ({self.item_name})"
            return location
        return self.step_name.replace('_', ' ').title()

@dataclass
class ErrorPayload:
    """Structured error information for Notion sync and debugging"""
    timestamp: datetime
    correlation_id: UUID
    step_name: str
    failure_location: FailureLocation
    error_category: str  # TRANSIENT, PERMANENT, CONFIGURATION, QUOTA_EXCEEDED
    error_message: str
    api_service: str  # e.g., "KIE.ai", "Gemini", "ElevenLabs"
    retry_attempt: int  # 1, 2, or 3
    next_retry_at: datetime | None  # None if terminal failure
    partial_progress: dict  # Checkpoint data
    recommendation: str | None  # Actionable next step

    def format_for_notion(self) -> str:
        """Format error payload as Notion rich text markdown"""
        lines = [
            f"**[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}]** {self.step_name} failed",
            f"**Location:** {self.failure_location.format()}",
            f"**Error:** {self.error_message} ({self.error_category})",
            f"**API:** {self.api_service}",
        ]

        # Add retry information
        if self.next_retry_at:
            lines.append(f"**Next retry:** {self.next_retry_at.strftime('%Y-%m-%d %H:%M:%S')} (Attempt {self.retry_attempt + 1}/3)")
        else:
            lines.append(f"**Status:** Terminal failure after {self.retry_attempt} attempts")

        # Add partial progress if available
        if self.partial_progress:
            progress_str = self._format_progress(self.partial_progress)
            if progress_str:
                lines.append(f"**Progress:** {progress_str}")

        # Add recommendation
        if self.recommendation:
            lines.append(f"**Action:** {self.recommendation}")

        return "\n".join(lines)

    def _format_progress(self, progress: dict) -> str:
        """Format checkpoint progress as human-readable string"""
        if "completed_video_clips" in progress:
            count = len(progress["completed_video_clips"])
            total = progress.get("total_clips", 18)
            return f"{count} of {total} clips completed"
        elif "completed_assets" in progress:
            count = len(progress["completed_assets"])
            total = progress.get("total_assets", 22)
            return f"{count} of {total} assets completed"
        elif "completed_narration_clips" in progress:
            count = len(progress["completed_narration_clips"])
            total = progress.get("total_clips", 18)
            return f"{count} of {total} narration clips completed"
        return ""
```

**Extended Error Classifier with Context:**

```python
# app/services/error_classifier.py (EXTEND, don't replace)

from dataclasses import dataclass

@dataclass
class ErrorContext:
    """Context information for error classification"""
    step_name: str
    task_id: str
    channel_id: str
    clip_index: int | None = None
    total_clips: int | None = None
    asset_index: int | None = None
    total_assets: int | None = None
    asset_name: str | None = None

class ErrorAnalysis:
    """Error classification result (from Story 6.1)"""
    category: ErrorCategory
    confidence: float
    reasoning: str
    api_service: str | None  # NEW: Extract API service from exception

def classify_error(exception: Exception, context: ErrorContext | None = None) -> ErrorAnalysis:
    """
    Classify error with optional context for richer analysis.

    Args:
        exception: The exception that occurred
        context: Optional context about where/when error occurred

    Returns:
        ErrorAnalysis with category, confidence, reasoning, and API service
    """
    # Existing classification logic from Story 6.1...

    # NEW: Extract API service from exception message or stack trace
    api_service = _extract_api_service(exception)

    return ErrorAnalysis(
        category=category,
        confidence=confidence,
        reasoning=reasoning,
        api_service=api_service
    )

def _extract_api_service(exception: Exception) -> str | None:
    """Extract API service name from exception message"""
    error_msg = str(exception).lower()

    if "kie.ai" in error_msg or "kling" in error_msg:
        return "KIE.ai"
    elif "gemini" in error_msg or "google.generativeai" in error_msg:
        return "Gemini"
    elif "elevenlabs" in error_msg:
        return "ElevenLabs"
    elif "notion" in error_msg:
        return "Notion"
    elif "youtube" in error_msg:
        return "YouTube"

    return "Unknown"
```

**Service-Level Error Handlers with Context:**

```python
# app/services/video_generation.py (EXTEND)

async def generate_videos_resumable(task_id: str, db: AsyncSession) -> int:
    """Generate 18 video clips with sub-step checkpointing (from Story 6.3)"""
    task = await db.get(Task, task_id)
    step_metadata = task.step_metadata or {}
    completed_clips = step_metadata.get("completed_video_clips", [])

    clips_generated = len(completed_clips)

    for clip_num in range(1, 19):  # Clips 1-18
        if clip_num in completed_clips:
            continue

        try:
            await _generate_single_clip(task_id, clip_num)

            # Update checkpoint
            completed_clips.append(clip_num)
            await update_step_metadata(task_id, "completed_video_clips", completed_clips, db)
            clips_generated += 1

        except Exception as e:
            # NEW: Build error context with clip location
            error_context = ErrorContext(
                step_name="video_generation",
                task_id=task_id,
                channel_id=task.channel_id,
                clip_index=clip_num,
                total_clips=18
            )

            # Classify error with context
            error_analysis = classify_error(e, error_context)

            # Build structured error payload
            error_payload = await build_error_payload(
                error_analysis,
                error_context,
                {"completed_video_clips": completed_clips, "total_clips": 18}
            )

            # Schedule retry with structured error
            await schedule_retry_with_structured_error(task_id, error_payload, db)

            raise  # Re-raise for worker to handle

    return clips_generated
```

**Notion Sync Service Updates:**

```python
# app/services/notion_sync.py (EXTEND)

from app.models import Task
from app.clients.notion import NotionClient

async def sync_task_error_to_notion(task: Task, error_payload: ErrorPayload) -> None:
    """
    Push structured error details to Notion task card.

    Updates:
    - Error Log property (rich text with formatted error payload)
    - Next Retry property (datetime of scheduled retry)
    - Status property (Error (Retrying) or Failed (Permanent))
    """
    notion_client = NotionClient(auth_token=task.channel.notion_token_encrypted)

    # Format error for Notion
    error_log_text = error_payload.format_for_notion()

    # Determine status
    if error_payload.next_retry_at:
        status = "Error (Retrying)"
    else:
        status = "Failed (Permanent)"

    # Update Notion properties (rate-limited)
    await notion_client.update_task_properties(
        page_id=task.notion_page_id,
        properties={
            "Error Log": {"rich_text": [{"text": {"content": error_log_text}}]},
            "Next Retry": {"date": {"start": error_payload.next_retry_at.isoformat()}} if error_payload.next_retry_at else None,
            "Status": {"status": {"name": status}}
        }
    )
```

**Recommendation Mapping:**

```python
# app/services/error_recommendations.py (NEW FILE)

from app.services.error_classifier import ErrorCategory

def get_error_recommendation(error_analysis: ErrorAnalysis, api_service: str) -> str:
    """Generate actionable recommendation based on error category and API service"""

    # Configuration errors
    if error_analysis.category == ErrorCategory.CONFIGURATION:
        if api_service == "Gemini":
            return "Check GEMINI_API_KEY in channel config (Railway environment variables)"
        elif api_service == "KIE.ai":
            return "Verify KIE_API_KEY and ensure API subscription is active"
        elif api_service == "ElevenLabs":
            return "Check ELEVENLABS_API_KEY and verify API subscription status"
        elif api_service == "YouTube":
            return "Verify YouTube OAuth tokens are valid (re-run setup_channel_oauth.py)"
        else:
            return "Check API credentials in channel configuration"

    # Transient errors (retry in progress)
    elif error_analysis.category == ErrorCategory.TRANSIENT:
        if "timeout" in error_analysis.reasoning.lower():
            if api_service == "KIE.ai":
                return "Video generation timeout - retry in progress (consider simpler prompts if recurring)"
            else:
                return f"{api_service} timeout - retry scheduled with exponential backoff"
        else:
            return "Transient network error - automatic retry in progress"

    # Quota exceeded
    elif error_analysis.category == ErrorCategory.QUOTA_EXCEEDED:
        if api_service == "YouTube":
            return "YouTube daily quota exceeded (10,000 units) - uploads paused until tomorrow"
        elif api_service == "ElevenLabs":
            return "ElevenLabs character limit reached - check monthly quota in dashboard"
        else:
            return f"{api_service} quota exceeded - check usage limits and upgrade plan if needed"

    # Permanent errors
    elif error_analysis.category == ErrorCategory.PERMANENT:
        if "prompt" in error_analysis.reasoning.lower():
            return "Invalid prompt detected - review task inputs and regenerate"
        elif "file" in error_analysis.reasoning.lower():
            return "File operation failed - check filesystem permissions and disk space"
        else:
            return "Permanent error - manual investigation required (see error log)"

    return "Check error details and logs for more information"
```

### Library & Framework Requirements

**No new dependencies required - all functionality uses existing packages:**
- `structlog>=23.2.0` - Structured error logging (already in use from Story 6.1)
- `httpx>=0.25.0` - Notion API HTTP client (already in use)
- `aiolimiter` - Notion API rate limiting (already in use)
- `sqlalchemy>=2.0.0` - Database operations (already in use)
- `pydantic>=2.8.0` - Data validation for ErrorPayload (already in use)

### File Structure Requirements

**New Files:**
1. `app/services/error_recommendations.py` - Get actionable recommendations for errors
2. `app/schemas/error_payload.py` - ErrorPayload and FailureLocation dataclasses (Pydantic models)

**Modified Files:**
1. `app/services/error_classifier.py` - Extend classify_error() to accept context, extract API service
2. `app/services/video_generation.py` - Add error context with clip location
3. `app/services/asset_generation.py` - Add error context with asset location
4. `app/services/narration_generation.py` - Add error context with narration clip location
5. `app/services/sfx_generation.py` - Add error context with SFX clip location
6. `app/services/retry_orchestrator.py` - Store structured error payloads in error_log
7. `app/services/notion_sync.py` - Push structured errors to Notion with new properties
8. `app/services/pipeline_orchestrator.py` - Replace simple error logging with structured error payload creation

**Notion Database Schema Changes (Manual):**
1. Add "Next Retry" property (type: Date, optional)
2. Enhance "Error Log" property (type: Rich Text, multi-line)
3. Add Status options: "Error (Retrying)", "Failed (Permanent)"

### Testing Requirements

**Unit Tests (`tests/test_services/test_error_payloads.py`):**

1. **ErrorPayload Formatting:**
   - Test format_for_notion() generates expected markdown
   - Test format() for FailureLocation with clips, assets, narration
   - Test partial progress formatting (completed_video_clips, completed_assets)
   - Test recommendation inclusion in formatted output

2. **Error Context Extraction:**
   - Test ErrorContext creation with clip_index, total_clips
   - Test ErrorContext creation with asset_index, asset_name
   - Test _extract_api_service() identifies correct API from exception message

3. **Recommendation Generation:**
   - Test get_error_recommendation() for CONFIGURATION + Gemini → "Check GEMINI_API_KEY"
   - Test get_error_recommendation() for TRANSIENT + timeout → "retry in progress"
   - Test get_error_recommendation() for QUOTA_EXCEEDED + YouTube → "quota exceeded"
   - Test get_error_recommendation() for PERMANENT + prompt → "review inputs"

**Integration Tests (`tests/test_services/test_structured_error_notion_sync.py`):**

1. **Video Clip Failure:**
   - Generate 10 clips successfully, FAIL at clip 11 with network timeout
   - Verify ErrorPayload: location="Clip 11 of 18", category=TRANSIENT, api_service="KIE.ai"
   - Verify Notion sync: Error Log shows "Clip 11 of 18", Status="Error (Retrying)", Next Retry set
   - Verify partial progress: "10 of 18 clips completed"

2. **Asset Generation Failure:**
   - Generate 14 assets, FAIL at asset 15 with 401 Unauthorized (Gemini)
   - Verify ErrorPayload: location="Asset 15 of 22 (environment_background_3.png)", category=CONFIGURATION
   - Verify Notion sync: Error Log shows asset name, recommendation="Check GEMINI_API_KEY"
   - Verify Status="Failed (Permanent)" (config errors not retriable without fix)

3. **Multi-Retry History:**
   - Task fails, retries 3 times (each with different transient error)
   - Verify error_log contains 3 entries with timestamps
   - Verify Notion shows all 3 attempts in Error Log
   - Verify terminal failure: Status="Failed (Permanent)", Next Retry=None

4. **Narration Failure with Quota:**
   - Generate 10 narration clips, FAIL at clip 11 with ElevenLabs quota exceeded
   - Verify ErrorPayload: category=QUOTA_EXCEEDED, api_service="ElevenLabs"
   - Verify recommendation: "check monthly quota in dashboard"
   - Verify Notion sync: Status="Failed (Permanent)" (quota errors require manual action)

**Test Pattern Example:**

```python
import pytest
from app.schemas.error_payload import ErrorPayload, FailureLocation
from app.services.error_classifier import ErrorContext, classify_error
from app.services.error_recommendations import get_error_recommendation
from datetime import datetime, timezone

def test_error_payload_formats_clip_failure():
    """Verify ErrorPayload formats video clip failure correctly"""
    location = FailureLocation(
        step_name="video_generation",
        item_index=11,
        total_items=18
    )

    payload = ErrorPayload(
        timestamp=datetime(2026, 1, 18, 14, 25, 0, tzinfo=timezone.utc),
        correlation_id=UUID("12345678-1234-1234-1234-123456789abc"),
        step_name="video_generation",
        failure_location=location,
        error_category="TRANSIENT",
        error_message="KIE.ai API timeout after 600s",
        api_service="KIE.ai",
        retry_attempt=2,
        next_retry_at=datetime(2026, 1, 18, 14, 26, 0, tzinfo=timezone.utc),
        partial_progress={"completed_video_clips": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], "total_clips": 18},
        recommendation="Video generation timeout - retry in progress"
    )

    formatted = payload.format_for_notion()

    assert "Clip 11 of 18" in formatted
    assert "KIE.ai API timeout" in formatted
    assert "TRANSIENT" in formatted
    assert "Next retry: 2026-01-18 14:26:00" in formatted
    assert "10 of 18 clips completed" in formatted
    assert "retry in progress" in formatted

@pytest.mark.asyncio
async def test_video_generation_failure_syncs_to_notion(db_session, mock_notion_client):
    """Integration test: Video clip failure syncs structured error to Notion"""
    # Setup: Task with 10 completed clips
    task = create_task(
        channel_id="poke1",
        step_metadata={"completed_video_clips": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}
    )
    db_session.add(task)
    await db_session.commit()

    # Simulate: Clip 11 fails with network timeout
    with pytest.raises(TimeoutError):
        await generate_videos_resumable(str(task.id), db_session)

    # Verify: Notion sync called with structured error
    await db_session.refresh(task)

    # Check error_log structure
    error_log = task.error_log
    assert len(error_log) == 1
    assert error_log[0]["location"] == "Clip 11 of 18"
    assert error_log[0]["category"] == "TRANSIENT"

    # Verify Notion API call
    notion_calls = mock_notion_client.update_task_properties.call_args_list
    assert len(notion_calls) == 1

    properties = notion_calls[0][1]["properties"]
    assert "Clip 11 of 18" in properties["Error Log"]["rich_text"][0]["text"]["content"]
    assert properties["Status"]["status"]["name"] == "Error (Retrying)"
    assert properties["Next Retry"]["date"]["start"] is not None
```

### Project Structure Notes

**Alignment with Story 6.1, 6.2, 6.3 Patterns:**

Story 6.4 builds on all three previous stories in Epic 6:

1. **Error Classification (Story 6.1):**
   - Extends classify_error() to accept ErrorContext for richer analysis
   - Uses ErrorCategory enum in structured error payload
   - Adds API service extraction for targeted recommendations

2. **Retry Orchestration (Story 6.2):**
   - Stores structured error payloads in task.error_log (append-only)
   - Includes retry_attempt number and next_retry_at timestamp
   - Builds multi-retry history for terminal failure visibility

3. **Checkpoint Integration (Story 6.3):**
   - Queries checkpoint service for partial progress when error occurs
   - Displays checkpoint data in Notion ("10 of 18 clips completed")
   - Combines error context with checkpoint data for complete picture

**Transaction Pattern Consistency:**
- Error payload creation OUTSIDE transaction (classify_error, build payload)
- Checkpoint query in separate short transaction
- Error storage and Notion sync in separate short transactions
- Never hold DB during error classification or Notion API calls

**Testing Pattern:**
- Mock time for retry delay tests (from Story 6.2)
- Mock Notion client for error sync tests (new for Story 6.4)
- Mock CLI scripts for error simulation (from Story 6.3)
- Use async SQLite fixtures (consistent across all Epic 6 stories)

**File Modification Patterns:**
- Story 6.1: Created error_classifier.py
- Story 6.2: Created retry_orchestrator.py
- Story 6.3: Created checkpoint_service.py
- Story 6.4: Creates error_recommendations.py, extends all service error handlers

### Previous Story Intelligence

**From Story 6.1 (Transient Failure Detection):**

**Key Learnings Applied:**
1. **Error Category Reuse:** Story 6.4 uses ErrorCategory enum in structured payloads
2. **API Service Extraction:** Extend classify_error() to identify API service for recommendations
3. **Context-Aware Classification:** ErrorContext enables location-specific error messages

**From Story 6.2 (Exponential Backoff Retry Logic):**

**Key Learnings Applied:**
1. **Retry Metadata:** Include retry_attempt and next_retry_at in error payload
2. **Multi-Retry History:** Append errors to task.error_log (don't overwrite)
3. **Terminal Failure Display:** Show all 3 retry attempts with timestamps in Notion

**From Story 6.3 (Resume from Failure Point):**

**Key Learnings Applied:**
1. **Checkpoint Progress:** Query checkpoint service for partial progress display
2. **Step Metadata Integration:** Show "10 of 18 clips completed" from step_metadata
3. **Combined Context:** Merge checkpoint data with error details for complete picture

**Integration Pattern:**
```python
# Story 6.1: Classify error with context
error_analysis = classify_error(exception, context)

# Story 6.2: Get retry information
retry_info = {"attempt": retry_attempt, "next_retry_at": next_retry_at}

# Story 6.3: Get checkpoint progress
checkpoint = await get_step_checkpoint(task_id, step_name, db)
partial_progress = checkpoint["outputs"] if checkpoint else {}

# Story 6.4: Build structured payload combining all
error_payload = ErrorPayload(
    error_category=error_analysis.category,
    api_service=error_analysis.api_service,
    retry_attempt=retry_info["attempt"],
    next_retry_at=retry_info["next_retry_at"],
    partial_progress=partial_progress,
    ...
)

# Push to Notion with all context
await sync_task_error_to_notion(task, error_payload)
```

**From Git Commits:**

Last 5 commits show progression through Epic 6:
1. `0b285f5` - Story 6.3 completed (checkpoint/resume with Notion visibility)
2. `0d0702f` - Story 6.1 completed (transient failure detection)
3. `1749fd9` - Code quality fixes (whitespace, EOF)
4. `13589c4` - Security incident documentation
5. `3bed083` - API key security hardening

**Pattern Consistency:**
- All Epic 6 stories use short transaction pattern (query → process → update)
- All use structlog for JSON logging
- All integrate with Notion sync for user visibility
- All include comprehensive test coverage (45+ tests in Story 6.3 alone)

**File Modification Patterns:**
- Story 6.1: Created `error_classifier.py`, modified service error handlers
- Story 6.2: Created `retry_orchestrator.py`, modified `notion_sync.py`
- Story 6.3: Created `checkpoint_service.py`, modified `pipeline_orchestrator.py`, modified services
- Story 6.4: Creates `error_recommendations.py`, extends `error_classifier.py`, modifies all service error handlers, extends `notion_sync.py`

### References

**Epic & Requirements:**
- PRD: `/Users/francisaraujo/repos/ai-video-generator/_bmad-output/planning-artifacts/prd.md`
- Epic 6 Story 6.4: `/Users/francisaraujo/repos/ai-video-generator/_bmad-output/planning-artifacts/epics.md#story-64-granular-error-status-updates` (lines 1423-1450)
- FR53: Detailed error status in Notion (API timeout? Clip 13? Network failure?)

**Architecture:**
- Structured logging: architecture.md:686-743 (JSON format, correlation IDs, context binding)
- Notion API integration: architecture.md:431-448 (rate limiting, polling strategy)
- Short transaction pattern: architecture.md:126-144 (never hold DB during I/O)
- Error recovery patterns: architecture.md:486-520 (retry logic, exponential backoff)

**Code References:**
- Story 6.1 classifier: `app/services/error_classifier.py` (ErrorCategory, classify_error)
- Story 6.2 retry orchestrator: `app/services/retry_orchestrator.py` (schedule_retry, claim_retry_tasks)
- Story 6.3 checkpoint service: `app/services/checkpoint_service.py` (get_step_checkpoint, step_metadata)
- Notion sync: `app/services/notion_sync.py` (TaskSyncData, push updates)
- Pipeline orchestrator: `app/services/pipeline_orchestrator.py` (8-step pipeline execution)
- Service error handlers: `app/services/video_generation.py`, `app/services/asset_generation.py`, etc.
- Previous stories:
  - `_bmad-output/implementation-artifacts/6-1-transient-failure-detection.md`
  - `_bmad-output/implementation-artifacts/6-2-exponential-backoff-retry-logic.md`
  - `_bmad-output/implementation-artifacts/6-3-resume-from-failure-point.md`

**Latest Best Practices (2026):**
- Structured logging: https://www.structlog.org/ (context binding, JSON output)
- Notion API: https://developers.notion.com/ (rate limits, rich text format, property types)
- Error observability: https://sentry.io/for/python/ (error context, breadcrumbs, user feedback)
- Pydantic dataclasses: https://docs.pydantic.dev/latest/concepts/dataclasses/ (validation, serialization)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

N/A

### Completion Notes List

**Task 1 - Structured Error Payload Design (Completed)**
- Created `app/schemas/error_payload.py` with ErrorPayload and FailureLocation Pydantic models
- Implemented format_for_notion() for Notion-compatible rich text markdown generation
- Added progress formatting for video clips, assets, narration, and SFX
- All 14 tests passing in tests/test_schemas/test_error_payload.py

**Task 2 - Error Classifier Context Extension (Completed)**
- Extended classify_error() to accept optional ErrorContext parameter (backwards compatible)
- Added ErrorContext dataclass with step_name, clip_index, asset_index fields
- Implemented _extract_api_service() to identify API from context or exception message
- Added api_service field to ErrorAnalysis (Story 6.4)
- Split ErrorCategory: 401/403 now CONFIGURATION (was PERMANENT), added QUOTA_EXCEEDED
- Updated existing tests to reflect CONFIGURATION category for 401/403
- All 48 tests passing (26 original + 22 new context tests)

**Task 6 - Actionable Recommendations (Completed)**
- Created `app/services/error_recommendations.py` with get_error_recommendation()
- Implemented configuration recommendations (API keys per service)
- Implemented transient recommendations (retry strategies, timeouts)
- Implemented quota recommendations (YouTube, ElevenLabs, Gemini, KIE.ai)
- Implemented permanent recommendations (validation errors, file errors)
- All 15 tests passing in tests/test_services/test_error_recommendations.py

### File List

**New Files:**
- app/schemas/error_payload.py - ErrorPayload and FailureLocation dataclasses
- app/services/error_recommendations.py - Actionable recommendations for error categories
- tests/test_schemas/test_error_payload.py - Error payload formatting tests (14 tests)
- tests/test_services/test_error_classifier_context.py - Context and API service extraction tests (22 tests)
- tests/test_services/test_error_recommendations.py - Recommendation generation tests (15 tests)

**Modified Files:**
- app/services/error_classifier.py - Added ErrorContext, api_service field, _extract_api_service(), CONFIGURATION/QUOTA_EXCEEDED categories
- tests/test_services/test_error_classifier.py - Updated 401/403 tests to expect CONFIGURATION category
- _bmad-output/implementation-artifacts/sprint-status.yaml - Updated story status to in-progress
