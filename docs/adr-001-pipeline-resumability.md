# ADR-001: Pipeline Resumability Architecture

**Status:** Accepted
**Date:** 2026-01-18
**Decision Makers:** Alice (Architect), Charlie (Senior Dev), Dana (Test/QA), Francis (Project Lead)
**Context:** Epic 5 Retrospective - Action Item 1 (CRITICAL blocker for Epic 6 Story 6.3)

---

## Context and Problem Statement

The 8-step video generation pipeline (Research → Story → Assets → Composites → Video → Audio → SFX → Assembly) can fail at any step due to transient errors (API rate limits, network timeouts, service degradation). When a task fails mid-pipeline, we need to decide:

**Option A:** Restart from scratch (simple, idempotent, but wasteful)
**Option B:** Resume from last successful step (efficient, but requires state tracking)

Epic 6 Story 6.3 "Resume from Failure Point" has acceptance criteria that assumes Option B:
> "asset generation completes but video generation fails → retry skips asset generation"

This ADR resolves the architectural decision deferred from Epic 4 and now blocking Epic 6.

---

## Decision Drivers

1. **Cost Efficiency:** Video generation costs $5-10 per task - regenerating all 18 clips is wasteful
2. **Time Efficiency:** Asset generation takes 10-20 minutes - re-running wastes time
3. **API Quota Conservation:** Gemini, Kling, ElevenLabs have rate limits and daily quotas
4. **Epic 6 Requirements:** Story 6.3 acceptance criteria explicitly requires resumability
5. **Existing Infrastructure:** Task model already has `step_completion_metadata` JSON field (line 589)
6. **Complexity vs. Benefit:** Must balance implementation complexity against efficiency gains

---

## Considered Options

### Option A: Restart from Scratch

**Approach:**
- On retry, always start from step 1 (Research)
- Ignore any previously completed work
- Overwrite all existing files

**Pros:**
- ✅ **Simple implementation:** No state tracking required
- ✅ **Idempotent:** Always produces same result
- ✅ **No partial state corruption:** Fresh start every time
- ✅ **Easy to reason about:** No complex resumption logic

**Cons:**
- ❌ **Wasteful:** Re-runs expensive operations (asset gen, video gen)
- ❌ **Slow:** 10-20+ minutes wasted on asset regeneration
- ❌ **Cost inefficient:** $5-10 per video wasted on full regeneration
- ❌ **Quota consumption:** Burns API quotas unnecessarily
- ❌ **Doesn't meet Epic 6 requirements:** Story 6.3 explicitly requires resumability

**Verdict:** ❌ Rejected - Wasteful and doesn't meet requirements

---

### Option B: Resume from Last Successful Step (RECOMMENDED)

**Approach:**
- Track completed steps in `step_completion_metadata` JSON field (already exists)
- On retry, check which steps are complete
- Skip completed steps, resume from first incomplete/failed step
- Each SOP verifies its outputs exist before declaring completion

**Pros:**
- ✅ **Cost efficient:** Only regenerates failed portions
- ✅ **Time efficient:** Skips completed work (10-20+ minutes saved)
- ✅ **Quota conserving:** Doesn't burn API quotas on completed work
- ✅ **Meets Epic 6 requirements:** Story 6.3 explicitly requires this
- ✅ **Infrastructure exists:** `step_completion_metadata` field already in Task model
- ✅ **Reasonable complexity:** SOP-level granularity is manageable

**Cons:**
- ⚠️ **More complex:** Requires state tracking and verification logic
- ⚠️ **Potential partial state:** Must handle missing files gracefully
- ⚠️ **Idempotency requirements:** Each SOP must be idempotent

**Verdict:** ✅ **ACCEPTED** - Efficient, meets requirements, infrastructure exists

---

## Decision

**We will implement Option B: Resume from Last Successful Step**

### Resumability Granularity

**SOP-level tracking (NOT clip-level)**
- Track completion of entire SOPs: assets, composites, videos, audio, sfx, assembly
- Do NOT track individual clip completion (e.g., "clip 5 of 18") - too fine-grained
- Exception: Partial video regeneration (Story 5.4) handles clip-level failures separately

### State Management Design

**Use existing `step_completion_metadata` JSON field on Task model:**

```python
# Example structure
{
  "completed_steps": [
    "research",
    "story",
    "assets",
    "composites"
  ],
  "last_completed_at": "2026-01-18T14:30:00Z",
  "asset_count": 22,
  "composite_count": 18
}
```

**Schema:**
- `completed_steps`: List of completed SOP names
- `last_completed_at`: ISO 8601 timestamp of last successful step
- Additional metadata: counts, paths, verification checksums (optional)

### Resumption Logic

**Each SOP handler follows this pattern:**

```python
async def execute_sop(task: Task, sop_name: str) -> None:
    """Execute a pipeline SOP with resumability support."""

    # 1. Check if step already completed
    if is_step_complete(task, sop_name):
        logger.info(f"Skipping {sop_name} - already complete")
        return

    # 2. Verify prerequisites (previous steps complete)
    if not prerequisites_met(task, sop_name):
        raise PipelineError(f"Prerequisites not met for {sop_name}")

    # 3. Execute the SOP
    await perform_sop_work(task, sop_name)

    # 4. Verify outputs exist
    if not verify_sop_outputs(task, sop_name):
        raise PipelineError(f"{sop_name} outputs missing after execution")

    # 5. Mark step as complete
    mark_step_complete(task, sop_name)
    await session.commit()
```

**Key Functions:**

```python
def is_step_complete(task: Task, sop_name: str) -> bool:
    """Check if SOP already completed."""
    metadata = task.step_completion_metadata or {}
    return sop_name in metadata.get("completed_steps", [])

def mark_step_complete(task: Task, sop_name: str) -> None:
    """Mark SOP as completed in metadata."""
    metadata = task.step_completion_metadata or {"completed_steps": []}
    if sop_name not in metadata["completed_steps"]:
        metadata["completed_steps"].append(sop_name)
        metadata["last_completed_at"] = datetime.utcnow().isoformat()
    task.step_completion_metadata = metadata

def verify_sop_outputs(task: Task, sop_name: str) -> bool:
    """Verify SOP outputs exist on filesystem."""
    # Check expected files exist
    # Examples:
    # - assets: Check 22 PNG files in assets/characters/ and assets/environments/
    # - composites: Check 18 composite PNGs in assets/composites/
    # - videos: Check 18 MP4 files in videos/
    # - audio: Check 18 MP3 files in audio/
    # - sfx: Check 18 WAV files in sfx/
    # - assembly: Check final_video_path file exists
    pass
```

### Idempotency Guarantees

**Each SOP must be idempotent (safe to re-run on existing files):**

1. **Research & Story:** Markdown files - overwrite is idempotent
2. **Assets:** Images - overwrite with same dimensions/format is idempotent
3. **Composites:** Images - overwrite with same dimensions/format is idempotent
4. **Videos:** MP4 files - overwrite is idempotent (same duration/codec)
5. **Audio:** MP3 files - overwrite is idempotent (same duration)
6. **SFX:** WAV files - overwrite is idempotent (same duration)
7. **Assembly:** Final MP4 - overwrite is idempotent

**Rule:** If a file exists and a SOP re-runs, it overwrites (does NOT duplicate or append).

### Error Recovery Behavior

**When a task moves to error status (ASSET_ERROR, VIDEO_ERROR, AUDIO_ERROR):**

1. **Preserve completed_steps:** Do NOT clear step_completion_metadata
2. **On retry (status → QUEUED):** Resume from first incomplete step
3. **User can force full restart:** Manually clear step_completion_metadata via API (future feature)

**Example:**
```
Initial run:
  - Assets: ✅ (22 images generated)
  - Composites: ✅ (18 composites created)
  - Videos: ❌ (Kling API timeout at clip 12)
  - Status: VIDEO_ERROR
  - completed_steps: ["research", "story", "assets", "composites"]

Retry run:
  - Check completed_steps: ["research", "story", "assets", "composites"]
  - Skip research (✅ complete)
  - Skip story (✅ complete)
  - Skip assets (✅ complete)
  - Skip composites (✅ complete)
  - Resume from videos (❌ incomplete)
  - Videos: Re-attempt all 18 clips (or use partial regeneration from Story 5.4)
```

### Database Schema Changes

**No migration required** - `step_completion_metadata` field already exists (Task model line 589).

**Optional enhancement (Epic 6):** Add indexes for performance if querying by completed steps becomes common.

---

## Consequences

### Positive

- ✅ **Cost savings:** $5-10 saved per video retry (no asset/composite regeneration)
- ✅ **Time savings:** 10-20+ minutes saved per retry
- ✅ **API quota conservation:** Reduced Gemini/Kling/ElevenLabs API calls
- ✅ **Epic 6 Story 6.3 implementable:** Meets acceptance criteria
- ✅ **Infrastructure ready:** `step_completion_metadata` field exists
- ✅ **Scales to future SOPs:** Pattern extends to additional pipeline steps

### Negative

- ⚠️ **Increased complexity:** Each SOP needs verification logic
- ⚠️ **Partial state risk:** If filesystem and DB diverge, must handle gracefully
- ⚠️ **Testing overhead:** Must test resumption at every possible failure point

### Mitigation Strategies

**For partial state risk:**
1. **Verification before completion:** `verify_sop_outputs()` checks files exist before marking complete
2. **Graceful degradation:** If files missing but step marked complete, log warning and regenerate
3. **Manual recovery:** Provide admin API to clear step_completion_metadata and force full restart

**For testing overhead:**
1. **Test fixtures:** Create tasks with various completed_steps configurations
2. **Failure injection:** Simulate failures at each SOP to test resumption
3. **End-to-end tests:** Verify full pipeline + retry with partial completion

---

## Implementation Plan

**Epic 6 Story 6.3: Resume from Failure Point**

**Phase 1: Core Resumability (Story 6.3)**
1. Implement `is_step_complete()`, `mark_step_complete()`, `verify_sop_outputs()` helper functions
2. Update each SOP handler to check `completed_steps` before executing
3. Add verification logic for each SOP's expected outputs
4. Ensure idempotency: all SOPs overwrite (not append) existing files

**Phase 2: Error Recovery Integration (Story 6.2)**
1. On ERROR → QUEUED transition, preserve `step_completion_metadata`
2. Pipeline orchestrator resumes from first incomplete step
3. Log resumption: "Resuming from {first_incomplete_step}, skipping {completed_steps}"

**Phase 3: Testing (Epic 6)**
1. Unit tests: Test each SOP's resumption logic in isolation
2. Integration tests: Test full pipeline + failure + retry with partial completion
3. End-to-end tests: Verify cost/time savings from resumption

**Phase 4: Observability (Epic 8)**
1. Metrics: Track resumption frequency, steps skipped, time/cost saved
2. Logging: Log which steps skipped vs. executed on each run
3. Notion sync: Show completed_steps in task detail view

---

## Alternatives Considered

### Clip-Level Granularity

**Approach:** Track completion of individual clips (e.g., "video_clip_5", "audio_clip_12")

**Rejected because:**
- Too fine-grained - 18 clips × 3 types (video, audio, sfx) = 54 individual units to track
- Complex state management - partial completion within a single SOP
- Limited benefit - if 17/18 clips succeed, regenerating 1 clip is fast
- Story 5.4 already handles partial video regeneration separately

### Filesystem Markers

**Approach:** Use marker files (`.complete`) to track SOP completion instead of database

**Rejected because:**
- Filesystem and database can diverge
- No centralized query capability
- Harder to observe completion status
- Database is already source of truth for task state

### Checkpointing at Sub-SOP Level

**Approach:** Track completion at sub-SOP operations (e.g., "asset_1", "asset_2", ..., "asset_22")

**Rejected because:**
- Excessive state tracking overhead
- Minimal benefit - asset generation is fast enough to regenerate all 22 if needed
- Adds complexity without proportional efficiency gain

---

## References

- **Epic 4 Retrospective (2026-01-18):** Pipeline resumability deferred, now blocking Epic 6
- **Epic 5 Retrospective (2026-01-18):** Action Item 1 - resolve resumability before Epic 6
- **Epic 6 Story 6.3:** Resume from Failure Point - acceptance criteria requires SOP-level resumability
- **Task Model (app/models.py:589):** `step_completion_metadata` JSON field exists
- **CLAUDE.md:** 8-step pipeline description (Research → Story → Assets → Composites → Video → Audio → SFX → Assembly)
- **Story 5.4:** Partial video regeneration (clip-level retry for videos specifically)

---

## Decision Record

**Decision:** Option B (Resume from Last Successful Step) - ACCEPTED
**Granularity:** SOP-level (8 steps: research, story, assets, composites, videos, audio, sfx, assembly)
**State Management:** Use existing `step_completion_metadata` JSON field on Task model
**Idempotency:** All SOPs overwrite existing files (not append)
**Verification:** Each SOP verifies outputs exist before marking complete
**Error Recovery:** Preserve completed_steps on error, resume from first incomplete step on retry

**Approved by:**
- Alice (Architect) - Author
- Charlie (Senior Dev) - Reviewed and approved
- Dana (Test/QA) - Reviewed and approved
- Francis (Project Lead) - Approved

**Date:** 2026-01-18
