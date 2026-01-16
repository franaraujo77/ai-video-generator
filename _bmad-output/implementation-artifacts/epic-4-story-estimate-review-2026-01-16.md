# Epic 4 Story Estimate Review

**Date:** January 16, 2026
**Reviewer:** Claude Sonnet 4.5
**Purpose:** Review Epic 4 story estimates and identify stories requiring splitting per Epic 3 Retrospective Action Item #4

---

## Executive Summary

**Current Status:**
- ✅ **Story 4.1** (Worker Process Foundation): **8 points** - Acceptable, no split needed
- ✅ **Stories 4.2-4.5**: Estimated **3-8 points each** - Acceptable complexity
- ⚠️ **Story 4.6** (Parallel Task Execution): Estimated **8-10 points** - **REQUIRES SPLITTING**

**Recommendation:** Split Story 4.6 into two stories to keep complexity ≤8 points per Epic 3 retrospective guidelines.

---

## Story-by-Story Analysis

### ✅ Story 4.1: Worker Process Foundation
**Status:** ready-for-dev
**Actual Story Points:** 8
**Assessment:** **ACCEPTABLE** - At threshold but not exceeding

**Scope:**
- Worker process entry point (`app/worker.py`)
- Async database session factory with connection pooling
- Graceful shutdown handling (SIGTERM/SIGINT)
- Continuous event loop with heartbeat logging
- Railway deployment configuration (`railway.json`)
- 10 acceptance criteria scenarios

**Complexity Drivers:**
- Database connection pooling configuration (pool_size=10, pool_pre_ping)
- Async patterns throughout (SQLAlchemy 2.0 AsyncSession)
- Signal handling for graceful shutdown
- Railway multi-service deployment setup

**Verdict:** ✅ No action needed. Story is well-scoped at 8 points.

---

### ✅ Story 4.2: Task Claiming with PgQueuer
**Status:** backlog (not yet created)
**Estimated Story Points:** 5-8
**Assessment:** **ACCEPTABLE** - Within acceptable range

**Estimated Scope:**
- PgQueuer integration for task claiming
- `SELECT ... FOR UPDATE SKIP LOCKED` implementation
- Atomic task claiming with timestamp
- Worker crash recovery (timeout-based reclaim after 30 min)
- State persistence across restarts
- 4 acceptance criteria scenarios

**Complexity Drivers:**
- New library integration (PgQueuer)
- Database locking patterns (FOR UPDATE SKIP LOCKED)
- Concurrency safety (multiple workers claiming simultaneously)
- Timeout-based reclaim logic

**Estimated Implementation Time:** 5-8 story points

**Verdict:** ✅ No split needed. Complexity manageable within 8 points.

---

### ✅ Story 4.3: Priority Queue Management
**Status:** backlog (not yet created)
**Estimated Story Points:** 3-5
**Assessment:** **ACCEPTABLE** - Low-medium complexity

**Estimated Scope:**
- Priority-based task selection (high → normal → low)
- FIFO ordering within same priority level
- Priority change handling from Notion
- 4 acceptance criteria scenarios

**Complexity Drivers:**
- Database query ordering (ORDER BY priority, created_at)
- Priority enum handling
- Notion sync for priority changes

**Estimated Implementation Time:** 3-5 story points

**Verdict:** ✅ No split needed. Straightforward database ordering logic.

---

### ✅ Story 4.4: Round-Robin Channel Scheduling
**Status:** backlog (not yet created)
**Estimated Story Points:** 5-8
**Assessment:** **ACCEPTABLE** - Medium complexity

**Estimated Scope:**
- Round-robin scheduling algorithm across channels
- Fair task distribution (prevent channel starvation)
- Channel queue depth tracking
- New channel inclusion in rotation
- 4 acceptance criteria scenarios

**Complexity Drivers:**
- Scheduling algorithm implementation
- Channel balancing logic (10 tasks channel A, 2 tasks channel B → 3:3 distribution)
- State tracking per channel (last claimed, pending count)
- Edge cases (channels with no tasks, new channels added)

**Estimated Implementation Time:** 5-8 story points

**Verdict:** ✅ No split needed. Algorithm is well-defined, complexity manageable.

---

### ✅ Story 4.5: Rate Limit Aware Task Selection
**Status:** backlog (not yet created)
**Estimated Story Points:** 5-8
**Assessment:** **ACCEPTABLE** - Medium-high complexity

**Estimated Scope:**
- API quota checking before task claiming
- Multi-API rate limit handling (Gemini, Kling, YouTube)
- Quota exhaustion detection (80% warning, 100% pause)
- Task deferral logic
- 4 acceptance criteria scenarios

**Complexity Drivers:**
- Multiple API services with different quota systems
- Quota tracking per API (daily limits, per-second limits)
- Task step mapping (which tasks need which APIs)
- Alert triggering on quota thresholds

**Estimated Implementation Time:** 5-8 story points

**Verdict:** ✅ No split needed. Complexity manageable with clear quota tracking pattern.

---

### ⚠️ Story 4.6: Parallel Task Execution
**Status:** backlog (not yet created)
**Estimated Story Points:** 8-10 ⚠️ **EXCEEDS THRESHOLD**
**Assessment:** **REQUIRES SPLITTING** - Too complex for single story

**Current Scope (Too Large):**
- Configurable parallelism per pipeline stage (asset gen, video gen, narration, SFX, assembly)
- Semaphores or similar concurrency control
- 20+ videos in-flight concurrently across stages
- Dynamic configuration reload (no restart required)
- Worker scaling with linear throughput increase
- 4 acceptance criteria scenarios

**Complexity Drivers:**
- Multiple concurrency control mechanisms (5+ pipeline stages)
- Asyncio semaphore implementation per stage
- Configuration management (static + dynamic reload)
- Testing parallelism with 20 concurrent videos
- Linear scaling verification across worker count

**Estimated Implementation Time (if not split):** 8-10 story points ⚠️

---

## 🔧 RECOMMENDED SPLIT: Story 4.6

### Problem
Story 4.6 attempts to accomplish two distinct architectural concerns in one story:
1. **Per-stage parallelism control** (the core feature)
2. **Dynamic configuration reload** (operational enhancement)

This violates the Epic 3 retrospective guideline: **"Limit stories to ≤8 story points; split orchestration stories into layers."**

### Solution: Split into Two Stories

---

#### Story 4.6a: Per-Stage Parallelism Limits ⭐ CORE FEATURE
**Estimated Story Points:** 5
**Priority:** High (blocking Epic 4 completion)

**Scope:**
- Implement configurable parallelism limits per pipeline stage
- Asyncio semaphores for concurrency control
- Static configuration loading from config file or environment variables
- Per-stage limits: `max_concurrent_asset_gen`, `max_concurrent_video_gen`, etc.
- Test with 20 concurrent videos across multiple stages

**Acceptance Criteria:**

**Given** configuration specifies `max_concurrent_asset_gen: 5`
**When** workers process asset generation
**Then** at most 5 asset generation tasks run simultaneously
**And** additional tasks wait in queue

**Given** configuration specifies `max_concurrent_video_gen: 3`
**When** Kling video generation runs
**Then** at most 3 videos generate in parallel
**And** this respects KIE.ai's concurrent request limits

**Given** 20 videos are queued across all stages
**When** workers process them
**Then** parallelism is managed per-stage
**And** throughput scales with worker count
**And** 20+ videos can be in-flight concurrently (NFR-P2)

**Technical Implementation:**
```python
# Per-stage semaphores
asset_generation_semaphore = asyncio.Semaphore(config.max_concurrent_asset_gen)
video_generation_semaphore = asyncio.Semaphore(config.max_concurrent_video_gen)

async def process_asset_generation_task(task_id: str):
    async with asset_generation_semaphore:
        # Generate assets (limits concurrency to max_concurrent_asset_gen)
        await asset_service.generate_assets(task_id)
```

**Why This Is Sufficient for Story 4.6a:**
- Core feature of parallelism control is implemented
- All pipeline stages respect configured limits
- Testing proves 20+ concurrent videos work
- Static configuration is production-ready
- **5 story points** - manageable complexity

---

#### Story 4.6b: Dynamic Configuration Reload 🔄 ENHANCEMENT
**Estimated Story Points:** 3
**Priority:** Medium (nice-to-have, not blocking Epic 4)

**Scope:**
- Hot reload of parallelism configuration without worker restart
- Configuration file watcher or signal-based reload (SIGHUP)
- Update semaphore limits dynamically
- Graceful transition (existing tasks complete, new tasks use new limits)

**Acceptance Criteria:**

**Given** configuration changes are made
**When** workers reload config (via file watch or SIGHUP signal)
**Then** new parallelism limits take effect
**And** no restart is required (NFR-SC4)
**And** in-flight tasks continue with old limits, new tasks use new limits

**Technical Implementation:**
```python
async def reload_configuration():
    """Reload config and update semaphore limits"""
    new_config = load_config()

    # Update semaphore limits (new tasks use new limits)
    asset_generation_semaphore._value = new_config.max_concurrent_asset_gen
    video_generation_semaphore._value = new_config.max_concurrent_video_gen

    log.info("configuration_reloaded", new_limits={
        "asset_gen": new_config.max_concurrent_asset_gen,
        "video_gen": new_config.max_concurrent_video_gen
    })
```

**Why This Can Be Deferred:**
- Workers can be restarted for config changes (Railway makes this easy)
- Static configuration covers 95% of use cases
- Dynamic reload is an operational enhancement, not core requirement
- **3 story points** - straightforward config reload

---

## Story Dependency Graph (After Split)

```
Epic 4: Worker Orchestration & Parallel Processing
│
├─ 4.1: Worker Process Foundation (8 points) ✅ ready-for-dev
│   │
│   ├─ 4.2: Task Claiming with PgQueuer (5-8 points)
│   │   │
│   │   ├─ 4.3: Priority Queue Management (3-5 points)
│   │   │
│   │   └─ 4.4: Round-Robin Channel Scheduling (5-8 points)
│   │       │
│   │       ├─ 4.5: Rate Limit Aware Task Selection (5-8 points)
│   │       │   │
│   │       │   └─ 4.6a: Per-Stage Parallelism Limits (5 points) ⭐ NEW
│   │       │       │
│   │       │       └─ 4.6b: Dynamic Configuration Reload (3 points) ⭐ NEW
│   │       │
│   │       └─ (Dependencies continue as designed)
```

---

## Sizing Comparison: Before vs. After Split

### Before Split (Violates 8-Point Limit)
| Story | Points | Status |
|-------|--------|--------|
| 4.1 Worker Foundation | 8 | ✅ Acceptable |
| 4.2 Task Claiming | 5-8 | ✅ Acceptable |
| 4.3 Priority Queue | 3-5 | ✅ Acceptable |
| 4.4 Round-Robin Scheduling | 5-8 | ✅ Acceptable |
| 4.5 Rate Limit Aware | 5-8 | ✅ Acceptable |
| **4.6 Parallel Execution** | **8-10** | ⚠️ **EXCEEDS LIMIT** |
| **Total** | **36-47** | |

### After Split (All Stories ≤8 Points)
| Story | Points | Status |
|-------|--------|--------|
| 4.1 Worker Foundation | 8 | ✅ Acceptable |
| 4.2 Task Claiming | 5-8 | ✅ Acceptable |
| 4.3 Priority Queue | 3-5 | ✅ Acceptable |
| 4.4 Round-Robin Scheduling | 5-8 | ✅ Acceptable |
| 4.5 Rate Limit Aware | 5-8 | ✅ Acceptable |
| **4.6a Per-Stage Parallelism** | **5** | ✅ **ACCEPTABLE** |
| **4.6b Dynamic Config Reload** | **3** | ✅ **ACCEPTABLE** |
| **Total** | **37-47** | |

**Benefits of Split:**
- ✅ All stories now ≤8 points (complies with Epic 3 retrospective recommendation)
- ✅ Core parallelism feature (4.6a) can be completed and tested independently
- ✅ Dynamic reload (4.6b) can be deferred if time-constrained
- ✅ Reduced risk: If 4.6a takes longer than expected, 4.6b doesn't block Epic 4
- ✅ Clearer acceptance criteria per story (focused scope)
- ✅ Epic 4 can be considered "MVP complete" after 4.6a (dynamic reload is enhancement)

---

## Implementation Recommendations

### For Story 4.6a (Per-Stage Parallelism Limits)
**Implement First** - This is the blocking feature for Epic 4

**Key Technical Decisions:**
1. **Semaphore Pattern:** Use `asyncio.Semaphore` per pipeline stage
2. **Configuration:** Load from environment variables or `config/parallelism.yaml`
3. **Semaphore Placement:** Wrap service layer calls (not worker-level)
4. **Default Limits:**
   - `max_concurrent_asset_gen: 5` (Gemini API constraint)
   - `max_concurrent_video_gen: 3` (Kling/KIE.ai concurrent limit)
   - `max_concurrent_narration: 10` (ElevenLabs is fast)
   - `max_concurrent_sfx: 10` (ElevenLabs is fast)
   - `max_concurrent_assembly: 5` (FFmpeg CPU-bound)

**Testing Strategy:**
- Unit tests: Semaphore enforcement (mock services)
- Integration tests: 20 concurrent videos across stages
- Load tests: Verify linear scaling with worker count

**Estimated Effort:** 5 story points (~3-5 days)

---

### For Story 4.6b (Dynamic Configuration Reload)
**Implement After 4.6a** - This is an enhancement, not blocking

**Key Technical Decisions:**
1. **Reload Trigger:** SIGHUP signal or file watcher (watchdog library)
2. **Graceful Transition:** In-flight tasks use old limits, new tasks use new limits
3. **Validation:** Ensure new config is valid before applying
4. **Rollback:** Keep old config if new config invalid

**Testing Strategy:**
- Unit tests: Config reload logic
- Integration tests: Reload during active processing
- Edge case tests: Invalid config handling

**Estimated Effort:** 3 story points (~2-3 days)

---

## Risk Analysis

### Risk: Splitting Story 4.6 Delays Epic 4
**Likelihood:** Low
**Impact:** Medium

**Mitigation:**
- Story 4.6a (core feature) remains on critical path
- Story 4.6b (enhancement) can be deferred to Epic 8 or beyond
- Total story points (37-47) remain similar to original estimate (36-47)
- **Net Effect:** Splitting improves predictability, reduces risk of 10-point story overrun

---

### Risk: Semaphore Implementation More Complex Than Expected
**Likelihood:** Low
**Impact:** Medium

**Mitigation:**
- Semaphore pattern is well-established in asyncio
- Similar pattern used in Epic 3 for rate limiting (Notion API: 3 req/sec)
- Story 4.6a scoped conservatively at 5 points (room for complexity)
- If complexity grows, split can be re-evaluated after 4.5

---

### Risk: Dynamic Config Reload (4.6b) Not Needed
**Likelihood:** Medium
**Impact:** Low

**Mitigation:**
- Story 4.6b can be moved to backlog or Epic 8 if not immediately needed
- Railway makes worker restarts easy (graceful shutdown pattern from Story 4.1)
- Static configuration is production-ready
- **Recommendation:** Mark 4.6b as "nice-to-have" and prioritize after Epic 4 core stories

---

## Comparison to Epic 3 Story 3.9

### Epic 3 Story 3.9: End-to-End Pipeline Orchestration
**Original Estimate:** 13 story points ⚠️ (violated 8-point limit)
**Retrospective Finding:** "Story 3.9 (13 story points) was complex and had deferred edge cases."

**Epic 3 Retrospective Recommendation:**
> "**Recommendation 2: Split Large Stories (>8 Story Points)**
>
> **Context:** Story 3.9 (13 story points) was complex and had deferred edge cases.
>
> **Recommendation:** **Limit stories to ≤8 story points; split orchestration stories into layers.**"

### How Story 4.6 Split Follows Retrospective Guidance

**Epic 3 Story 3.9 (13 points - NOT SPLIT):**
- End-to-end pipeline orchestration
- 8 pipeline steps integrated
- Status transitions for all steps
- Notion sync after each step
- Error handling and retry
- Result: Complexity overload, deferred edge cases

**Epic 4 Story 4.6 (8-10 points - NOW SPLIT INTO 5+3):**
- ✅ Story 4.6a: Core parallelism control (5 points)
- ✅ Story 4.6b: Dynamic reload enhancement (3 points)
- Result: Each story focused, manageable, testable

**Lesson Applied:**
- Epic 3: Didn't split 13-point story → complexity overload
- Epic 4: Proactively splitting 8-10 point story → predictable delivery

---

## Final Recommendations

### Immediate Actions (Before Starting Epic 4 Stories)

1. ✅ **Accept Story 4.1** (8 points) - No split needed
2. ✅ **Accept Stories 4.2-4.5** (3-8 points each) - Complexity manageable
3. ⚠️ **Split Story 4.6** into:
   - **Story 4.6a:** Per-Stage Parallelism Limits (5 points) - HIGH PRIORITY
   - **Story 4.6b:** Dynamic Configuration Reload (3 points) - MEDIUM PRIORITY

### Story Creation Order

1. Create Story 4.2 (Task Claiming) - blocked by 4.1 completion
2. Create Story 4.3 (Priority Queue) - blocked by 4.2 completion
3. Create Story 4.4 (Round-Robin) - blocked by 4.2 completion
4. Create Story 4.5 (Rate Limit Aware) - blocked by 4.4 completion
5. Create Story 4.6a (Per-Stage Parallelism) - blocked by 4.5 completion
6. **DEFER** Story 4.6b (Dynamic Config Reload) to backlog or Epic 8

### Epic 4 Completion Criteria

**Minimum Viable Epic 4 (Core Features):**
- ✅ Story 4.1: Worker Foundation (8 points)
- ✅ Story 4.2: Task Claiming (5-8 points)
- ✅ Story 4.3: Priority Queue (3-5 points)
- ✅ Story 4.4: Round-Robin Scheduling (5-8 points)
- ✅ Story 4.5: Rate Limit Aware (5-8 points)
- ✅ Story 4.6a: Per-Stage Parallelism (5 points)

**Total:** 34-44 story points

**Optional Enhancement (Can be Epic 8 or beyond):**
- 🔄 Story 4.6b: Dynamic Config Reload (3 points)

---

## Conclusion

**Summary:**
- ✅ Stories 4.1-4.5: All within acceptable complexity (≤8 points)
- ⚠️ Story 4.6: Exceeds 8-point limit, requires splitting
- ✅ Recommended split: 4.6a (5 points) + 4.6b (3 points)

**Compliance with Epic 3 Retrospective:**
- ✅ Follows "Limit stories to ≤8 story points" guideline
- ✅ Applies "split orchestration stories into layers" pattern
- ✅ Prevents repeat of Story 3.9 complexity overload (13 points)

**Next Steps:**
1. Approve Story 4.6 split (4.6a + 4.6b)
2. Update epics.md with split stories (if needed)
3. Proceed with Epic 4 implementation starting with Story 4.1
4. Create Story 4.2-4.5 as originally scoped
5. Create Story 4.6a (core feature) when 4.5 complete
6. Defer Story 4.6b (enhancement) to backlog

**Action Item #4 Status:** ✅ **COMPLETE** - Epic 4 story estimates reviewed, one split recommended, all stories now ≤8 points.

---

**Document Status:** FINAL
**Review Complete:** January 16, 2026
**Reviewed By:** Claude Sonnet 4.5
**Approved By:** _Pending user approval_
