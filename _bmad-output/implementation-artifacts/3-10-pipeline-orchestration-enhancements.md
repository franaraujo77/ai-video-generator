---
story_key: '3-10-pipeline-orchestration-enhancements'
epic_id: '3'
story_id: '10'
title: 'Pipeline Orchestration Enhancements'
status: 'ready-for-dev'
priority: 'high'
story_points: 5
created_at: '2026-01-16'
assigned_to: 'Claude Sonnet 4.5'
dependencies: ['3-9-end-to-end-pipeline-orchestration']
blocks: ['4-1-worker-process-foundation']
ready_for_dev: true
---

# Story 3.10: Pipeline Orchestration Enhancements

**Epic:** 3 - Video Generation Pipeline
**Priority:** High (Critical Refinements from Code Review)
**Story Points:** 5 (Targeted Enhancements to Existing System)
**Status:** BACKLOG

## Story Description

**As a** content creator,
**I want** partial progress tracking, real-time Notion sync, and consistent status naming in the pipeline orchestration,
**So that** failed tasks resume efficiently, status updates are visible in Notion within 5 seconds, and documentation is accurate.

## Context & Background

This story addresses **3 remaining action items** from Story 3.9 code review that require more extensive implementation work beyond simple bug fixes. Story 3.9 successfully implemented the core pipeline orchestration, but these enhancements are needed to meet all acceptance criteria fully.

**Remaining Action Items from Story 3.9 Code Review:**

1. **[HIGH] Implement partial progress tracking in execute_step** (Issue #4)
   - Current State: Services return `partial_progress=None`, tasks restart from beginning on failure
   - Required: Services must return and consume partial progress (e.g., `{"clips": 5, "total": 18}`)
   - Impact: Without this, failed video generation (5/18 clips complete) regenerates all 5 clips, wasting ~25 minutes and $2-3

2. **[HIGH] Implement Notion status sync after each step** (Issue #9)
   - Current State: Notion sync commented out in `pipeline_orchestrator.py:573-574`
   - Required: Real-time status updates to Notion within 5 seconds (AC 1 & 4)
   - Impact: Users can't see pipeline progress in Notion, breaking visibility requirement

3. **[MEDIUM] Update story documentation for status name consistency**
   - Current State: Story 3.9 ACs reference "awaiting_review" but code correctly uses `TaskStatus.FINAL_REVIEW`
   - Required: Update story docs to match enum values
   - Impact: Documentation inconsistency causes confusion for developers

**Why These Are Critical:**

- **Partial Progress Tracking**: Core idempotency requirement (FR29: Resume from failure point)
  - Without this, $5-10 video generation restarts from scratch on failure
  - Wastes time (up to 90 minutes) and money (up to $10 per retry)
  - Breaks acceptance criteria: "Resume from asset #12 (skip first 11)"

- **Notion Status Sync**: Core visibility requirement (FR53: Real-time status updates)
  - Without this, users don't know what's happening with their videos
  - Breaks acceptance criteria: "Update Notion status within 5 seconds"
  - Critical for user experience and pipeline monitoring

- **Status Name Consistency**: Developer experience and maintainability
  - Inconsistent naming causes confusion when implementing Epic 5 review gates
  - Story documentation should match actual enum values

**Derived from Story 3.9 Analysis:**

- Core orchestration pattern works: 6 steps execute sequentially, status updates to PostgreSQL
- Service layer integration verified: All services (3.3-3.8) callable and functional
- Short transaction pattern validated: DB closed during pipeline execution
- Error classification working: Transient vs permanent errors correctly identified
- Testing infrastructure solid: 36 tests covering orchestrator and worker

**What's Missing:**

1. **Service Layer Enhancement**: Services need to track and return partial progress
2. **Notion Integration**: Async status sync implementation needed
3. **Documentation Update**: Story 3.9 markdown needs enum value corrections

## Acceptance Criteria

### Scenario 1: Partial Progress Tracking in Asset Generation
**Given** asset generation fails after generating 11 of 22 assets (Gemini API timeout)
**When** the task is retried
**Then** the orchestrator should:
- ✅ Load step completion metadata: `{"assets_generated": 11, "total_assets": 22}`
- ✅ Pass partial progress to AssetGenerationService: `resume_from=11`
- ✅ Service generates only assets 12-22 (skips 1-11)
- ✅ Total regeneration time reduced from 15 min to ~7 min (savings: 8 min, ~$0.80)
- ✅ Updated step completion metadata: `{"assets_generated": 22, "total_assets": 22}`
- ✅ Pipeline continues to composite creation automatically

### Scenario 2: Partial Progress Tracking in Video Generation
**Given** video generation fails on clip #7 (clips 1-6 complete, each clip ~5 minutes, ~$0.55)
**When** the task is retried
**Then** the orchestrator should:
- ✅ Load step completion metadata: `{"clips_generated": 6, "total_clips": 18}`
- ✅ Pass partial progress to VideoGenerationService: `start_clip=7`
- ✅ Service generates only clips 7-18 (skips 1-6)
- ✅ Regeneration cost reduced from $10 to ~$7 (savings: $3, 30 min)
- ✅ Updated step completion metadata: `{"clips_generated": 18, "total_clips": 18}`
- ✅ Pipeline continues to narration generation

### Scenario 3: Partial Progress Tracking in Narration Generation
**Given** narration generation fails on clip #13 (clips 1-12 complete)
**When** the task is retried
**Then** the orchestrator should:
- ✅ Load step completion metadata: `{"narrations_generated": 12, "total_narrations": 18}`
- ✅ Pass partial progress to NarrationGenerationService: `start_clip=13`
- ✅ Service generates only clips 13-18
- ✅ Regeneration time reduced from 10 min to ~3 min
- ✅ Updated step completion metadata: `{"narrations_generated": 18, "total_narrations": 18}`

### Scenario 4: Partial Progress Tracking in SFX Generation
**Given** SFX generation fails on clip #9 (clips 1-8 complete)
**When** the task is retried
**Then** the orchestrator should:
- ✅ Load step completion metadata: `{"sfx_generated": 8, "total_sfx": 18}`
- ✅ Pass partial progress to SFXGenerationService: `start_clip=9`
- ✅ Service generates only clips 9-18
- ✅ Regeneration time reduced from 5 min to ~3 min
- ✅ Updated step completion metadata: `{"sfx_generated": 18, "total_sfx": 18}`

### Scenario 5: Notion Status Sync After Asset Generation
**Given** asset generation completes successfully (22 assets generated)
**When** status is updated to "generating_composites"
**Then** the system should:
- ✅ Update PostgreSQL task status to `TaskStatus.GENERATING_COMPOSITES`
- ✅ Commit database transaction
- ✅ Trigger async Notion status update (fire-and-forget with `asyncio.create_task`)
- ✅ Notion API update completes within 5 seconds (NFR-P3)
- ✅ Notion Board View shows task moved to "Generating Composites" column
- ✅ Pipeline continues to composite creation without waiting for Notion update
- ✅ If Notion update fails, log error but don't fail pipeline

### Scenario 6: Notion Status Sync with Rate Limiting
**Given** 3 tasks complete asset generation simultaneously
**When** Notion status updates are triggered for all 3 tasks
**Then** the system should:
- ✅ Queue all 3 updates
- ✅ Apply rate limiting: max 3 requests per second (Notion API limit)
- ✅ Updates complete within 5 seconds total (within NFR-P3 target)
- ✅ All 3 tasks show updated status in Notion
- ✅ No 429 rate limit errors from Notion API

### Scenario 7: Notion Status Sync Error Handling
**Given** Notion API is temporarily unavailable (HTTP 503 error)
**When** a status update is attempted
**Then** the system should:
- ✅ Log error: "Notion status sync failed" with task_id and error details
- ✅ Pipeline continues normally (status in PostgreSQL is updated)
- ✅ Retry Notion update after 5 seconds (exponential backoff)
- ✅ If 3 retries fail, log warning but complete pipeline
- ✅ User can see status in PostgreSQL even if Notion sync fails

### Scenario 8: Story Documentation Update
**Given** Story 3.9 markdown file exists
**When** status name corrections are applied
**Then** the documentation should:
- ✅ Replace all "awaiting_review" references with "FINAL_REVIEW" (lines 154, 157, 210, 213)
- ✅ Update acceptance criteria to use correct enum values
- ✅ Add note: "Status enum: TaskStatus.FINAL_REVIEW (not 'awaiting_review')"
- ✅ No functional code changes (documentation only)

### Scenario 9: End-to-End Validation with Enhancements
**Given** a task fails at video generation clip #7
**When** the task is retried after implementing all enhancements
**Then** the system should:
- ✅ Resume from clip #7 (partial progress tracking)
- ✅ Update Notion status to "Generating Video" within 5 seconds (Notion sync)
- ✅ Complete clips 7-18 successfully
- ✅ Update Notion status to "Generating Audio" within 5 seconds
- ✅ Total regeneration time: ~60 min (vs 90 min without partial progress)
- ✅ Cost savings: ~$3 (vs $10 full regeneration)
- ✅ All status updates visible in Notion Board View

## Technical Specifications

### 1. Service Layer Enhancement: Partial Progress Support

**Update All Services to Return Partial Progress:**

```python
# app/services/asset_generation.py
@dataclass
class AssetGenerationResult:
    """Result from asset generation with partial progress tracking."""
    assets_generated: int
    total_assets: int
    completed: bool
    partial_progress: Dict[str, Any]

async def generate_assets(
    self,
    manifest: AssetManifest,
    resume_from: int | None = None  # NEW: Resume from asset number
) -> AssetGenerationResult:
    """
    Generate assets with partial progress tracking.

    Args:
        manifest: Asset generation manifest
        resume_from: Optional asset number to resume from (1-indexed)

    Returns:
        AssetGenerationResult with partial progress
    """
    start_index = resume_from if resume_from else 1

    for i, asset in enumerate(manifest.assets[start_index-1:], start=start_index):
        try:
            await self.generate_single_asset(asset)
        except Exception as e:
            # Return partial progress on failure
            return AssetGenerationResult(
                assets_generated=i - 1,
                total_assets=len(manifest.assets),
                completed=False,
                partial_progress={"assets_generated": i - 1, "total_assets": len(manifest.assets)}
            )

    # All assets complete
    return AssetGenerationResult(
        assets_generated=len(manifest.assets),
        total_assets=len(manifest.assets),
        completed=True,
        partial_progress={"assets_generated": len(manifest.assets), "total_assets": len(manifest.assets)}
    )
```

**Similar Updates Needed For:**
- `app/services/video_generation.py` - Return `{"clips_generated": N, "total_clips": 18}`
- `app/services/narration_generation.py` - Return `{"narrations_generated": N, "total_narrations": 18}`
- `app/services/sfx_generation.py` - Return `{"sfx_generated": N, "total_sfx": 18}`

**Composite Creation & Video Assembly:**
- These steps are atomic (complete or fail), no partial progress needed
- Return `{"completed": True}` on success, no intermediate state

### 2. Orchestrator Enhancement: Consume Partial Progress

**Update `app/services/pipeline_orchestrator.py`:**

```python
async def execute_step(self, step: PipelineStep) -> StepCompletion:
    """Execute a single pipeline step with partial progress support."""

    # Load completion metadata from database
    metadata = await self.load_step_completion_metadata()

    # Check if step already complete
    if step in metadata and metadata[step].completed:
        self.log.info("step_already_complete", step=step.value)
        return metadata[step]

    # Get partial progress for resume
    partial_progress = metadata.get(step, StepCompletion(step=step, completed=False)).partial_progress

    # Execute step with resume support
    if step == PipelineStep.ASSET_GENERATION:
        service = AssetGenerationService(self.channel_id, self.project_id)
        manifest = service.create_asset_manifest(self.topic, self.story_direction)

        # Resume from partial progress if available
        resume_from = partial_progress.get("assets_generated", 0) + 1 if partial_progress else None
        result = await service.generate_assets(manifest, resume_from=resume_from)

        return StepCompletion(
            step=step,
            completed=result.completed,
            partial_progress=result.partial_progress,
            duration_seconds=time.time() - start_time
        )

    elif step == PipelineStep.VIDEO_GENERATION:
        service = VideoGenerationService(self.channel_id, self.project_id)

        # Resume from partial progress if available
        start_clip = partial_progress.get("clips_generated", 0) + 1 if partial_progress else 1
        result = await service.generate_videos(start_clip=start_clip)

        return StepCompletion(
            step=step,
            completed=result.completed,
            partial_progress=result.partial_progress,
            duration_seconds=time.time() - start_time
        )

    # Similar logic for NARRATION_GENERATION, SFX_GENERATION
    # COMPOSITE_CREATION and VIDEO_ASSEMBLY remain atomic (no partial progress)
```

### 3. Notion Status Sync Implementation

**Add Notion sync method to `app/services/pipeline_orchestrator.py`:**

```python
from app.services.notion_client import NotionClient
from app.utils.rate_limiter import AsyncLimiter

# Initialize Notion client with rate limiter
notion_limiter = AsyncLimiter(rate=3, period=1)  # 3 req/sec max

async def sync_to_notion(self, status: str) -> None:
    """
    Sync task status to Notion (async, non-blocking).

    This method is fire-and-forget - errors are logged but don't fail pipeline.
    Retries transient failures with exponential backoff (1s, 5s, 15s).

    Args:
        status: New task status (e.g., "GENERATING_ASSETS")

    Example:
        >>> asyncio.create_task(self.sync_to_notion("GENERATING_COMPOSITES"))
        # Fires async update, pipeline continues immediately
    """
    try:
        # Load task to get notion_page_id
        async with async_session_factory() as db:
            task = await db.get(Task, self.task_id)
            if not task or not task.notion_page_id:
                self.log.warning("notion_sync_skipped", reason="no_notion_page_id")
                return

            notion_page_id = task.notion_page_id

        # Apply rate limiting (max 3 req/sec)
        async with notion_limiter:
            notion_client = NotionClient()

            # Retry loop with exponential backoff
            for attempt in range(1, 4):  # 3 attempts max
                try:
                    await notion_client.update_page_property(
                        page_id=notion_page_id,
                        property_name="Status",
                        value=status
                    )

                    self.log.info(
                        "notion_status_synced",
                        status=status,
                        page_id=notion_page_id,
                        attempt=attempt
                    )
                    return  # Success

                except HTTPError as e:
                    if e.status_code in (500, 502, 503):  # Transient errors
                        backoff_seconds = 2 ** attempt  # 2s, 4s, 8s
                        self.log.warning(
                            "notion_sync_retry",
                            error=str(e),
                            attempt=attempt,
                            backoff_seconds=backoff_seconds
                        )
                        await asyncio.sleep(backoff_seconds)
                    else:
                        # Permanent error (400, 401, etc.)
                        self.log.error("notion_sync_failed", error=str(e), status_code=e.status_code)
                        return

            # All retries exhausted
            self.log.error("notion_sync_exhausted", status=status, attempts=3)

    except Exception as e:
        # Log error but don't fail pipeline
        self.log.error("notion_sync_error", error=str(e), error_type=type(e).__name__)

async def update_task_status(self, status: TaskStatus, error_message: str | None = None) -> None:
    """Update task status in PostgreSQL and trigger async Notion sync."""

    # Update PostgreSQL (blocking, must complete)
    async with async_session_factory() as db, db.begin():
        task = await db.get(Task, self.task_id)
        if task:
            task.status = status
            if error_message:
                current_log = task.error_log or ""
                task.error_log = f"{current_log}\n[{datetime.now()}] {error_message}".strip()
            await db.commit()

    # Trigger async Notion sync (fire-and-forget)
    asyncio.create_task(self.sync_to_notion(status.value))

    self.log.info("task_status_updated", status=status.value)
```

### 4. Story Documentation Update

**Update `_bmad-output/implementation-artifacts/3-9-end-to-end-pipeline-orchestration.md`:**

```markdown
# Changes Required:

## Line 154:
- BEFORE: - ✅ Set final status to "awaiting_review" (pauses for human review)
+ AFTER: - ✅ Set final status to TaskStatus.FINAL_REVIEW (pauses for human review)

## Line 157:
- BEFORE: - ✅ Complete entire pipeline in ≤2 hours (90th percentile target)
+ AFTER: (no change needed - this line is fine)

## Line 210:
- BEFORE: - ✅ Set task status to "awaiting_review" (NOT "completed")
+ AFTER: - ✅ Set task status to TaskStatus.FINAL_REVIEW (NOT TaskStatus.COMPLETED)

## Line 213:
- BEFORE: - ✅ Update Notion status to "Awaiting Review"
+ AFTER: - ✅ Update Notion status to "Final Review"

## Add Note After Line 215:
**Note:** The status enum value is `TaskStatus.FINAL_REVIEW`, not "awaiting_review".
All code references use the enum value. Notion displays this as "Final Review" to users.
```

### File Structure

**Files to Modify:**
```
app/
├── services/
│   ├── asset_generation.py      # UPDATE: Add resume_from parameter, return partial progress
│   ├── video_generation.py      # UPDATE: Add start_clip parameter, return partial progress
│   ├── narration_generation.py  # UPDATE: Add start_clip parameter, return partial progress
│   ├── sfx_generation.py        # UPDATE: Add start_clip parameter, return partial progress
│   └── pipeline_orchestrator.py # UPDATE: Consume partial progress, implement Notion sync
_bmad-output/implementation-artifacts/
└── 3-9-end-to-end-pipeline-orchestration.md  # UPDATE: Status name corrections
```

**No New Files:**
- All changes are enhancements to existing files from Story 3.9

## Dev Agent Guardrails - CRITICAL REQUIREMENTS

### 🔥 Backward Compatibility (MANDATORY)

**1. Service Method Signatures Must Remain Compatible:**

```python
# ✅ CORRECT: Add optional parameters with defaults
async def generate_assets(
    self,
    manifest: AssetManifest,
    resume_from: int | None = None  # Optional, defaults to None (start from beginning)
) -> AssetGenerationResult:
    pass

# ❌ WRONG: Break existing callers by making resume_from required
async def generate_assets(
    self,
    manifest: AssetManifest,
    resume_from: int  # BREAKS existing code that doesn't pass this
) -> AssetGenerationResult:
    pass
```

**2. Partial Progress Must Be Optional:**

```python
# ✅ CORRECT: If no partial progress, start from beginning
resume_from = partial_progress.get("assets_generated", 0) + 1 if partial_progress else None

# ❌ WRONG: Require partial progress (breaks first-time execution)
resume_from = partial_progress["assets_generated"] + 1  # KeyError if partial_progress is None
```

**3. Notion Sync Must Be Fire-and-Forget:**

```python
# ✅ CORRECT: Don't await, pipeline continues immediately
asyncio.create_task(self.sync_to_notion(status))

# ❌ WRONG: Block pipeline waiting for Notion update
await self.sync_to_notion(status)  # Adds 1-5 seconds to each status update
```

### 🧠 Previous Story Learnings

**From Story 3.9 (Pipeline Orchestration):**
- ✅ Short transaction pattern verified working (DB closed during operations)
- ✅ Service layer integration solid (all services callable)
- ✅ Error classification functional (transient vs permanent)
- ✅ Structured logging with correlation IDs established

**What to Preserve:**
- Don't change transaction patterns (keep short transactions)
- Don't modify error classification logic (already correct)
- Don't alter service instantiation patterns (works as-is)
- Don't change logging structure (JSON format with correlation IDs)

**What to Enhance:**
- Add partial progress tracking to services (new feature)
- Implement Notion sync (missing feature)
- Update documentation (clarity improvement)

### 📚 Library & Framework Requirements

**No New Dependencies:**
- All required libraries already installed from Story 3.9
- Notion client exists from Epic 2 (Story 2.2)
- AsyncLimiter pattern already used for Notion rate limiting

**Reuse Existing:**
- `app/services/notion_client.py` - Already implements rate limiting
- `app/utils/rate_limiter.py` - AsyncLimiter for 3 req/sec limit
- `app/database.py` - async_session_factory for DB access

### 🧪 Testing Requirements

**Minimum Test Coverage:**

1. **Partial Progress Tests (15+ test cases):**
   - Asset generation resume from various points (asset 1, 11, 21)
   - Video generation resume from various clips (clip 1, 7, 17)
   - Narration generation resume from various clips
   - SFX generation resume from various clips
   - Composite creation (atomic, no partial progress)
   - Video assembly (atomic, no partial progress)
   - Edge cases: resume_from=None, resume_from=0, resume_from > total

2. **Notion Sync Tests (10+ test cases):**
   - Successful status sync within 5 seconds
   - Rate limiting (3 req/sec max)
   - Transient error retry (500, 503)
   - Permanent error handling (400, 401)
   - Retry exhaustion (all 3 attempts fail)
   - Fire-and-forget behavior (pipeline doesn't block)
   - Missing notion_page_id handling

3. **Integration Tests (5+ test cases):**
   - End-to-end pipeline with partial resume at each step
   - All status updates sync to Notion
   - Retry after failure resumes from correct position
   - Cost and time savings from partial progress

**Mock Strategy:**
- Mock NotionClient for Notion sync tests
- Mock service methods to return partial progress
- Use tmp_path fixture for filesystem tests
- Mock time.time() for duration tracking

### 🔒 Security Requirements

**Rate Limiting:**
- Notion API: 3 requests per second max (enforced by AsyncLimiter)
- Prevent API quota exhaustion
- Log rate limit violations

**Error Logging Security:**
- Don't log sensitive data (API keys, credentials)
- Truncate long error messages to prevent log flooding
- Sanitize user inputs before logging

**Channel Isolation:**
- Each task has channel_id → operations use channel-specific paths
- No cross-channel file access
- Database queries filter by channel_id

## Dependencies

**Required Before Starting:**

- ✅ Story 3.9: Pipeline orchestration implementation complete
- ✅ Epic 2: Notion API client with rate limiting (Story 2.2)
- ✅ All service layer implementations (Stories 3.3-3.8)

**Blocks These Stories:**

- Story 4.1: Worker process foundation (needs efficient partial resume)
- Epic 6: Error handling & auto-recovery (needs partial progress for retry)

## Definition of Done

- [ ] Service layer updated to return partial progress (AssetGeneration, VideoGeneration, Narration, SFX)
- [ ] Service layer accepts resume parameters (resume_from, start_clip)
- [ ] Orchestrator consumes partial progress and passes to services
- [ ] Notion status sync implemented (fire-and-forget pattern)
- [ ] Notion rate limiting enforced (3 req/sec max)
- [ ] Story 3.9 documentation updated with correct status names
- [ ] All partial progress tests passing (15+ test cases)
- [ ] All Notion sync tests passing (10+ test cases)
- [ ] All integration tests passing (5+ test cases)
- [ ] Backward compatibility verified (existing code still works)
- [ ] Performance improvement validated (time and cost savings from partial resume)
- [ ] Type hints complete (all parameters and return types)
- [ ] Docstrings complete (module, class, function-level with examples)
- [ ] Linting passes (`ruff check --fix .`)
- [ ] Type checking passes (`mypy app/`)
- [ ] Code review approved
- [ ] Merged to `main` branch

## Notes & Implementation Hints

**Implementation Order:**

1. **Phase 1: Service Layer Enhancement (Highest Priority)**
   - Start with AssetGenerationService (simplest case)
   - Add resume_from parameter, test thoroughly
   - Replicate pattern to VideoGenerationService
   - Then Narration and SFX services
   - Keep Composite and Assembly atomic (no changes)

2. **Phase 2: Orchestrator Enhancement**
   - Update execute_step to consume partial progress
   - Test with each service type
   - Verify backward compatibility (works without partial progress)

3. **Phase 3: Notion Sync Implementation**
   - Implement sync_to_notion method
   - Add rate limiting with AsyncLimiter
   - Test transient error retry
   - Verify fire-and-forget behavior

4. **Phase 4: Documentation Update**
   - Update Story 3.9 markdown file
   - Search and replace "awaiting_review" → "FINAL_REVIEW"
   - Add clarification note about enum values

**Cost/Time Savings Examples:**

| Failure Point | Without Partial Progress | With Partial Progress | Savings |
|---------------|--------------------------|----------------------|---------|
| Asset gen (11/22) | 15 min, $1.50 | 7 min, $0.70 | 8 min, $0.80 |
| Video gen (6/18) | 90 min, $10 | 60 min, $7 | 30 min, $3 |
| Narration (12/18) | 10 min, $0.50 | 3 min, $0.15 | 7 min, $0.35 |
| SFX (8/18) | 5 min, $0.25 | 3 min, $0.14 | 2 min, $0.11 |

**Typical Failure Scenario:**
- Video generation fails at clip 7 (most expensive step)
- Without partial progress: Regenerate all 18 clips (~90 min, $10)
- With partial progress: Regenerate clips 7-18 only (~60 min, $7)
- **Savings: 30 minutes, $3 per retry**

## Related Stories

- **Depends On:**
  - 3-9 (End-to-End Pipeline Orchestration) - core implementation
  - 2-2 (Notion API Client) - for status sync

- **Blocks:**
  - 4-1 (Worker Process Foundation) - needs efficient partial resume for production
  - 6-3 (Resume from Failure Point) - depends on partial progress tracking

- **Related:**
  - Epic 6 (Error Handling) - partial progress enables intelligent retry
  - Epic 5 (Review Gates) - Notion sync needed for review interface

## Source References

**PRD Requirements:**

- FR29: Resume from failure point with partial completion
- FR53: Real-time status updates to Notion (within 5 seconds)
- NFR-P3: Notion API response time (≤5 seconds, 95th percentile)
- NFR-R4: Idempotent operations for retry safety

**Architecture Decisions:**

- Short Transaction Pattern: Keep DB closed during operations
- Service Layer Pattern: Services return results, orchestrator manages flow
- Async Patterns: Fire-and-forget for non-critical operations

**Context:**

- Story 3.9: Code review issues #4, #9 (partial progress, Notion sync)
- Story 3.9: Lines 1462-1488 (3 remaining action items)
- epics.md: Epic 3 Story 9 requirements

---

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Implementation Summary

_To be filled in after implementation_

### Debug Log References

_To be filled in after implementation_

### Completion Notes List

_To be filled in after implementation_

### File List

**Files to Modify:**
- `app/services/asset_generation.py` - Add partial progress tracking
- `app/services/video_generation.py` - Add partial progress tracking
- `app/services/narration_generation.py` - Add partial progress tracking
- `app/services/sfx_generation.py` - Add partial progress tracking
- `app/services/pipeline_orchestrator.py` - Consume partial progress, implement Notion sync
- `_bmad-output/implementation-artifacts/3-9-end-to-end-pipeline-orchestration.md` - Status name corrections

**Test Files:**
- `tests/test_services/test_pipeline_orchestrator.py` - Add partial progress tests, Notion sync tests
- `tests/test_services/test_asset_generation.py` - Add resume_from tests
- `tests/test_services/test_video_generation.py` - Add start_clip tests
- `tests/test_services/test_narration_generation.py` - Add start_clip tests
- `tests/test_services/test_sfx_generation.py` - Add start_clip tests

---

## Status

**Status:** backlog
**Created:** 2026-01-16 via BMad Method workflow (create-story for Story 3.10)
**Ready for Implementation:** YES - All context, patterns, and requirements documented from Story 3.9 code review
