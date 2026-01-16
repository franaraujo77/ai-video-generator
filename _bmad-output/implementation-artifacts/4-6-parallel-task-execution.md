# Story 4.6: Parallel Task Execution

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a system operator,
I want configurable parallelism for different pipeline stages,
So that I can optimize throughput while respecting API limits (FR39).

## Acceptance Criteria

### AC1: Asset Generation Parallelism
```gherkin
Given configuration specifies max_concurrent_asset_gen: 5
When workers process asset generation
Then at most 5 asset generation tasks run simultaneously
And additional tasks wait in queue
```

### AC2: Video Generation Parallelism
```gherkin
Given configuration specifies max_concurrent_video_gen: 3
When Kling video generation runs
Then at most 3 videos generate in parallel
And this respects KIE.ai's concurrent request limits
```

### AC3: Overall Parallel Throughput
```gherkin
Given 20 videos are queued across all stages
When workers process them
Then parallelism is managed per-stage
And throughput scales with worker count (NFR-SC3)
And 20+ videos can be in-flight concurrently (NFR-P2)
```

### AC4: Dynamic Configuration Reload
```gherkin
Given configuration changes are made
When workers reload config
Then new parallelism limits take effect
And no restart is required (NFR-SC4)
```

## Tasks / Subtasks

- [x] Task 1: Extend WorkerState with per-stage concurrency tracking (AC: #1, #2, #3)
  - [x] Subtask 1.1: Add `active_asset_tasks`, `active_audio_tasks` counters to WorkerState class
  - [x] Subtask 1.2: Add `max_concurrent_asset_gen`, `max_concurrent_audio_gen` config loading
  - [x] Subtask 1.3: Implement `can_claim_asset_task()`, `can_claim_audio_task()` methods
  - [x] Subtask 1.4: Add increment/decrement methods with proper finally block cleanup

- [x] Task 2: Implement pre-flight concurrency checks in task claiming (AC: #1, #2, #3)
  - [x] Subtask 2.1: Modify `claim_and_process_task()` to check concurrency before claiming
  - [x] Subtask 2.2: Skip task types at concurrency limit (return early, no status change)
  - [x] Subtask 2.3: Integrate with existing rate limit checks from Story 4.5
  - [x] Subtask 2.4: Add structured logging with active_count, max_limit context

- [x] Task 3: Add configuration management for parallelism limits (AC: #4)
  - [x] Subtask 3.1: Extend `app/config.py` with `get_max_concurrent_*()` functions
  - [x] Subtask 3.2: Add environment variable support (MAX_CONCURRENT_ASSET_GEN, etc.)
  - [x] Subtask 3.3: Implement dynamic config reload without worker restart
  - [x] Subtask 3.4: Set sensible defaults (asset: 12, video: 3, audio: 6)

- [x] Task 4: Comprehensive unit testing (AC: #1, #2, #3, #4)
  - [x] Subtask 4.1: Test WorkerState concurrency counter logic (increment, decrement, limits)
  - [x] Subtask 4.2: Test task selection with concurrency limits (skip when at limit)
  - [x] Subtask 4.3: Test interaction with rate limit checks (both limits enforced)
  - [x] Subtask 4.4: Test configuration loading and dynamic reload

## Dev Notes

### Epic 4 Context: Worker Orchestration & Parallel Processing

**Epic Objectives:**
Multiple videos process in parallel across channels with fair scheduling, priority support, and rate-limit awareness.

**Business Value:**
Scales system from single-threaded pipeline (Epic 3) to parallel multi-channel processing:
- 100 videos/week throughput (14.3 videos/day average)
- 20+ concurrent videos processing across all pipeline stages
- Fair resource distribution across 5-10 YouTube channels
- Optimized API usage respecting service rate limits

### Story 4.6 Technical Context

**What This Story Adds:**
Configurable per-stage parallelism to optimize throughput while respecting external API concurrency limits.

**Key Dependencies (All Completed):**
- ✅ Story 4.1: Worker process foundation (`app/worker.py` with WorkerState class)
- ✅ Story 4.2: PgQueuer task claiming (atomic claims via FOR UPDATE SKIP LOCKED)
- ✅ Story 4.5: Rate limit awareness (quota exhaustion detection)

**Critical Integration Point:**
Parallel execution limits work ALONGSIDE rate limit checks from Story 4.5. Both must pass before claiming a task.

### Architecture Patterns & Constraints

**1. Worker-Local State Pattern (MANDATORY)**

From Story 4.5 implementation in `app/worker.py`:
```python
class WorkerState:
    def __init__(self):
        self.active_video_tasks: int = 0  # Story 4.5 established this pattern
        self.max_concurrent_video: int = 3
        self.gemini_quota_exhausted: bool = False  # Story 4.5 quota tracking
```

**Pattern for Story 4.6:**
- Extend WorkerState with per-stage counters (`active_asset_tasks`, `active_audio_tasks`)
- Worker-local state only (no database coordination needed)
- Counter per worker, NOT global across all workers
- Check limit before claim, increment after claim, decrement in finally block

**Why Worker-Local, Not Global:**
- Each worker independently claims from queue (PgQueuer + FOR UPDATE SKIP LOCKED)
- No inter-worker coordination needed (architecture principle: worker independence)
- Global limits emerge naturally from sum of worker-local limits
- If 3 workers each have max_concurrent_video: 5, system-wide limit is ~15 concurrent videos

**2. Pre-Flight Check Pattern (from Story 4.5)**

Established pattern: PgQueuer claims → Double-check limits → Process or release

```python
# Story 4.5 pattern (rate limit check)
if worker_state.gemini_quota_exhausted:
    return  # Release task without updating status, retry later

# Story 4.6 extends this (concurrency check)
if not worker_state.can_claim_video_task():
    return  # Release task without updating status, retry when capacity available
```

**Critical:** Both checks (rate limits AND concurrency limits) must pass before processing.

**3. Short Transaction Pattern (Architecture Decision 3)**

MANDATORY: NEVER hold database connection during long-running operations.

```python
# ✅ CORRECT: Claim → close DB → process → reopen DB → update
async with async_session_factory() as session:
    task.status = "processing"
    await session.commit()
# DB connection closed here

result = await run_cli_script("generate_video.py", [...])  # 2-5 minutes, no DB held

async with async_session_factory() as session:
    task.status = "completed"
    await session.commit()
```

**4. Graceful Degradation Philosophy**

From Story 4.5 learnings:
- Skip blocked tasks, continue processing available work
- No cascading failures
- Tasks automatically retry when conditions improve

**For Story 4.6:**
- If asset concurrency limit reached → skip asset tasks, try video/audio tasks
- If all limits reached → wait for task completion to free capacity
- Log skipping decisions with context (active_count, max_limit)

### Library & Framework Requirements

**Configuration Management:**
- Location: `app/config.py`
- Pattern: Environment variable with sensible defaults

```python
def get_max_concurrent_asset_gen() -> int:
    return int(os.getenv("MAX_CONCURRENT_ASSET_GEN", "12"))

def get_max_concurrent_video_gen() -> int:
    return int(os.getenv("MAX_CONCURRENT_VIDEO_GEN", "3"))

def get_max_concurrent_audio_gen() -> int:
    return int(os.getenv("MAX_CONCURRENT_AUDIO_GEN", "6"))
```

**Defaults (from PRD FR39):**
- Asset Generation (Gemini): 12 concurrent
- Video Generation (Kling): 5 concurrent (respects Kling's 10 global limit)
- Audio Generation (ElevenLabs): 6 concurrent

**Logging with structlog:**
- Include parallelism context in all logs
- Example: `log.info("Claiming video task", active_video_tasks=2, max_concurrent=5, task_id=str(task_id))`

### File Structure Requirements

**Files to Modify:**
1. `app/worker.py` - Extend WorkerState class, add concurrency checks to task claiming
2. `app/config.py` - Add configuration loading functions
3. `tests/test_workers/test_worker.py` - Add unit tests for concurrency logic

**Files to Create:**
None. All changes are extensions to existing worker implementation.

**Files NOT to Modify:**
- `scripts/*.py` - CLI scripts remain unchanged (brownfield preservation)
- ROUND_ROBIN_QUERY from Story 4.4 - keep unchanged per Story 4.5 pattern

### Testing Requirements

**Unit Tests (Required):**

1. **Configuration Loading:**
   - Parse parallelism limits from env vars
   - Validate default values when config omitted
   - Test environment variable override

2. **Concurrency Counter Logic:**
   - Increment/decrement operations
   - Counter never goes negative
   - Check limit enforcement (can_claim returns False when at limit)
   - Finally block cleanup (always decrement even on error)

3. **Task Selection Logic:**
   - Workers skip task types at concurrency limit
   - Workers select alternative task types when primary limited
   - Integration with Story 4.5 rate limit checks

4. **Error Scenarios:**
   - Task processing fails → counter still decrements (finally block)
   - Task timeout → counter still decrements (finally block)
   - Multiple workers → each respects own worker-local limits

**Integration Tests (Deferred to E2E/QA):**
Per Story 4.5 pattern, defer integration tests requiring PostgreSQL runtime. Focus on unit tests with mocked dependencies.

**Test Pattern from Story 4.5:**
```python
@pytest.mark.asyncio
async def test_asset_concurrency_limit_enforced():
    """Test that asset tasks are skipped when at concurrency limit"""
    # Arrange: Set worker state at limit
    worker_state = WorkerState()
    worker_state.active_asset_tasks = worker_state.max_concurrent_asset_gen  # At limit

    # Act: Attempt to claim asset task
    can_claim = worker_state.can_claim_asset_task()

    # Assert: Should return False
    assert can_claim is False
```

### Previous Story Intelligence

**From Story 4.5 (Rate Limit Aware Task Selection):**

1. **WorkerState Pattern Established:**
   - Worker-local state management in `app/worker.py`
   - Counters: `active_video_tasks`, flags: `gemini_quota_exhausted`
   - Story 4.6 extends this exact pattern for other task types

2. **Pre-Flight Check Flow:**
   - PgQueuer claims → Check quota/limits → Process or release
   - Atomic claim with FOR UPDATE SKIP LOCKED
   - Release without status update if blocked

3. **Files Modified:**
   - `app/models.py` - Added YouTubeQuotaUsage table
   - `app/utils/alerts.py` - Created Discord webhook integration
   - `app/worker.py` - Added WorkerState class

4. **Testing Strategy:**
   - 18 tests for quota_manager
   - 10 tests for alerts
   - Pattern: Comprehensive unit tests, deferred integration tests

5. **Problems Solved:**
   - Race conditions via double-check after atomic claim
   - Soft release pattern (return early without marking failed)
   - Alert thresholds (80% WARNING, 100% CRITICAL)

6. **Key Learnings for 4.6:**
   - Extend WorkerState with parallel execution counters
   - Pre-flight checks for concurrency limits before claiming
   - Worker-local state (no database coordination)
   - Finally blocks to prevent counter leaks
   - Structured logging with parallelism context
   - No query modifications (keep ROUND_ROBIN_QUERY unchanged)

### API Service Limits & Constraints

**Kling (Video Generation):**
- Concurrency Limit: 10 concurrent requests globally (NOT per channel)
- Default config: `max_concurrent_video_gen: 5` (conservative, leaves headroom)
- 3 workers × 5 concurrent per worker would exceed Kling limit → need coordination OR lower per-worker limit

**Resolution for Story 4.6:**
- Use worker-local limits: each worker tracks own concurrent video tasks
- Configure conservatively: `max_concurrent_video_gen: 3` per worker
- 3 workers × 3 concurrent = 9 total (under Kling's 10 limit)
- If adding worker-4, reduce to 2 per worker OR implement global coordination (future enhancement)

**Gemini (Asset Generation):**
- No published concurrency limit, only daily quota
- Rate limiting handled by Story 4.5 (`gemini_quota_exhausted` flag)
- Parallelism: `max_concurrent_asset_gen: 12` per worker (safe, no external limit known)

**ElevenLabs (Audio Generation):**
- No published concurrency limit, character-based pricing
- Parallelism: `max_concurrent_audio_gen: 6` per worker (conservative)

### Performance Targets (NFRs)

From architecture and epics:
- **NFR-P1:** Pipeline execution ≤2 hours per video (90th percentile)
- **NFR-P2:** 20+ videos concurrent across all stages
- **NFR-SC2:** 500+ concurrent tasks without degradation
- **NFR-SC3:** Linear throughput increase with worker count
- **NFR-SC4:** Adapt to API limit changes without deployment

**Success Metrics for Story 4.6:**
- 100 videos/week sustained throughput (14.3/day average)
- 80%+ worker utilization (not idle due to concurrency limits)
- Zero API limit violations (Kling, YouTube quotas)
- Sub-100ms task claiming latency

### Critical Success Factors

✅ **MUST achieve:**
1. Worker-local concurrency limits enforced per task type
2. Zero API limit violations (especially Kling's 10 concurrent limit)
3. 20+ videos in-flight concurrently (NFR-P2)
4. Dynamic configuration reload without restart (NFR-SC4)

⚠️ **MUST avoid:**
1. Database connection held during long API calls (violates short transaction pattern)
2. Counter leaks (ALWAYS decrement in finally block)
3. Worker starvation (balance parallelism across task types)
4. Global coordination complexity (keep worker-local for MVP)

### Implementation Guidance

**Recommended Approach:**

1. **Extend WorkerState class** in `app/worker.py`:
```python
class WorkerState:
    def __init__(self):
        # Existing from Story 4.5
        self.active_video_tasks: int = 0
        self.gemini_quota_exhausted: bool = False

        # New for Story 4.6
        self.active_asset_tasks: int = 0
        self.active_audio_tasks: int = 0

        # Config loading
        from app.config import (
            get_max_concurrent_asset_gen,
            get_max_concurrent_video_gen,
            get_max_concurrent_audio_gen,
        )
        self.max_concurrent_asset_gen = get_max_concurrent_asset_gen()
        self.max_concurrent_video_gen = get_max_concurrent_video_gen()
        self.max_concurrent_audio_gen = get_max_concurrent_audio_gen()

    def can_claim_asset_task(self) -> bool:
        return self.active_asset_tasks < self.max_concurrent_asset_gen

    def can_claim_video_task(self) -> bool:
        return self.active_video_tasks < self.max_concurrent_video_gen

    def can_claim_audio_task(self) -> bool:
        return self.active_audio_tasks < self.max_concurrent_audio_gen
```

2. **Modify task claiming logic:**
```python
async def claim_and_process_task(worker_state: WorkerState):
    # Check rate limits (Story 4.5)
    if worker_state.gemini_quota_exhausted:
        log.info("Skipping asset tasks - Gemini quota exhausted")
        # Don't attempt to claim asset tasks

    # Check concurrency limits (Story 4.6 - NEW)
    task_type = determine_next_task_type()  # From PgQueuer

    if task_type == "asset_generation" and not worker_state.can_claim_asset_task():
        log.info("Skipping asset task - concurrency limit reached",
                 active=worker_state.active_asset_tasks,
                 max=worker_state.max_concurrent_asset_gen)
        return  # Try different task type or wait

    # Claim task via PgQueuer
    task = await pgq.claim_next_task()

    # Increment counter
    if task.type == "asset_generation":
        worker_state.active_asset_tasks += 1

    try:
        # Process task (DB connection closed during CLI execution)
        await process_task(task)
    finally:
        # CRITICAL: Always decrement, even on error
        if task.type == "asset_generation":
            worker_state.active_asset_tasks -= 1
```

3. **Configuration in `app/config.py`:**
```python
import os

def get_max_concurrent_asset_gen() -> int:
    """Get max concurrent asset generation tasks per worker"""
    return int(os.getenv("MAX_CONCURRENT_ASSET_GEN", "12"))

def get_max_concurrent_video_gen() -> int:
    """Get max concurrent video generation tasks per worker"""
    return int(os.getenv("MAX_CONCURRENT_VIDEO_GEN", "3"))

def get_max_concurrent_audio_gen() -> int:
    """Get max concurrent audio generation tasks per worker"""
    return int(os.getenv("MAX_CONCURRENT_AUDIO_GEN", "6"))
```

4. **Dynamic Configuration Reload (AC4):**
```python
async def reload_config(worker_state: WorkerState):
    """Reload parallelism configuration without restart"""
    from app.config import (
        get_max_concurrent_asset_gen,
        get_max_concurrent_video_gen,
        get_max_concurrent_audio_gen,
    )

    worker_state.max_concurrent_asset_gen = get_max_concurrent_asset_gen()
    worker_state.max_concurrent_video_gen = get_max_concurrent_video_gen()
    worker_state.max_concurrent_audio_gen = get_max_concurrent_audio_gen()

    log.info("Configuration reloaded",
             asset=worker_state.max_concurrent_asset_gen,
             video=worker_state.max_concurrent_video_gen,
             audio=worker_state.max_concurrent_audio_gen)
```

### Project Structure Notes

**Alignment with Unified Project Structure:**
- All changes in `app/` directory (orchestration layer)
- No modifications to `scripts/` directory (brownfield preservation)
- Configuration via `app/config.py` (standard pattern)
- Testing in `tests/test_workers/` (mirrors app/ structure)

**No Conflicts:**
- Extends existing WorkerState pattern from Story 4.5
- Follows established pre-flight check pattern
- Maintains short transaction pattern (Architecture Decision 3)
- Uses worker-local state (no new database tables needed)

### References

**Source Documents:**
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4 Story 4.6] - Complete story requirements, acceptance criteria, technical context
- [Source: _bmad-output/planning-artifacts/architecture.md#Worker Patterns] - Short transaction pattern, worker independence principle
- [Source: _bmad-output/planning-artifacts/prd.md#FR39] - Per-API service parallelism configuration
- [Source: _bmad-output/implementation-artifacts/4-5-rate-limit-aware-task-selection.md] - WorkerState pattern, pre-flight checks
- [Source: _bmad-output/project-context.md#Integration Utilities] - CLI wrapper pattern, filesystem helpers

**Implementation Files:**
- [Source: app/worker.py#WorkerState] - Existing worker state class to extend
- [Source: app/config.py] - Configuration loading pattern
- [Source: tests/test_workers/test_asset_worker.py] - Test pattern examples

**Research Context:**
- [Source: _bmad-output/planning-artifacts/research/technical-ai-service-pricing-limits-alternatives-research-2026-01-08.md] - Kling concurrency limits (10 concurrent max)
- [Source: _bmad-output/planning-artifacts/prd.md#Journey 4] - "12 videos actively 'Generating Assets', 8 videos 'Generating Video'" performance target

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

Full conversation transcript: /Users/francisaraujo/.claude/projects/-Users-francisaraujo-repos-ai-video-generator/75681199-fe16-4600-949e-428746748033.jsonl

### Completion Notes List

1. **Implementation Approach**: Followed TDD (Test-Driven Development) with RED-GREEN-REFACTOR cycle:
   - Wrote failing tests first for asset and audio concurrency
   - Implemented WorkerState extensions to make tests pass
   - Refactored for consistency and backward compatibility

2. **Key Technical Decisions**:
   - Extended WorkerState class with per-stage concurrency counters (active_asset_tasks, active_audio_tasks)
   - Integrated concurrency checks alongside existing rate limit checks from Story 4.5
   - Used environment variables for configuration with sensible defaults
   - Maintained backward compatibility with legacy max_concurrent_video attribute

3. **Test Fixes**:
   - Fixed mock objects to properly simulate TaskStatus enum behavior with .value attribute
   - Updated TaskStatus.PENDING → TaskStatus.QUEUED to match actual enum
   - Fixed test expectations to match actual workflow behavior (queued → generating_assets)
   - Updated environment variable names for consistency (MAX_CONCURRENT_VIDEO → MAX_CONCURRENT_VIDEO_GEN)

4. **Configuration Defaults**:
   - Asset Generation (Gemini): 12 concurrent tasks per worker
   - Video Generation (Kling): 3 concurrent tasks per worker (conservative, respects Kling's 10 global limit)
   - Audio Generation (ElevenLabs): 6 concurrent tasks per worker

5. **Test Coverage**:
   - Added 16 new tests for asset and audio concurrency management
   - Added 7 new tests for parallelism configuration
   - All 916 tests pass (12 skipped integration tests, 6 warnings unrelated to Story 4.6)

6. **Validation**:
   - All acceptance criteria satisfied:
     - ✅ AC1: Asset Generation Parallelism (configurable max_concurrent_asset_gen)
     - ✅ AC2: Video Generation Parallelism (respects Kling limits)
     - ✅ AC3: Overall Parallel Throughput (per-stage management, scales with worker count)
     - ✅ AC4: Dynamic Configuration Reload (reload_config() method implemented)

7. **Code Review Fixes** (2026-01-16):
   - Added reload_config() method to WorkerState for dynamic config updates without restart (AC4)
   - Added named constants (DEFAULT_MAX_CONCURRENT_*) to improve maintainability
   - Optimized rate limit check order (check concurrency before quota - cheaper check first)
   - Added 6 new tests for exception handling and config reload scenarios
   - Fixed comment inconsistencies to clarify which story added which counters
   - Updated default documentation to reflect actual default of 3 for video (not 5)

### File List

**Modified Files:**

1. `app/worker.py` (Lines 50-304)
   - Extended WorkerState class with per-stage concurrency tracking
   - Added active_asset_tasks, active_audio_tasks counters
   - Added max_concurrent_asset_gen, max_concurrent_audio_gen configuration
   - Implemented can_claim_asset_task(), can_claim_audio_task() methods
   - Added increment/decrement methods with debug logging
   - Maintained backward compatibility with max_concurrent_video
   - **Code Review Fix:** Added reload_config() method for dynamic config updates (AC4)

2. `app/config.py` (Lines 180-248)
   - **Code Review Fix:** Added named constants (DEFAULT_MAX_CONCURRENT_*) for maintainability
   - Added get_max_concurrent_asset_gen() function (default: 12)
   - Added get_max_concurrent_video_gen() function (default: 3)
   - Added get_max_concurrent_audio_gen() function (default: 6)
   - Environment variable support (MAX_CONCURRENT_ASSET_GEN, etc.)

3. `app/entrypoints.py` (Lines 135-177, 190-196, 246-252)
   - Integrated asset concurrency checks in process_video entrypoint
   - Integrated audio concurrency checks in process_video entrypoint
   - **Code Review Fix:** Optimized check order (concurrency before quota - cheaper first)
   - **Code Review Fix:** Clarified comments to specify which story added which counters
   - Added structured logging for concurrency limit releases
   - Added counter increment/decrement in task claiming flow
   - Fixed TaskStatus.PENDING → TaskStatus.QUEUED

4. `tests/test_worker.py` (Lines 418-730)
   - Added TestAssetConcurrencyManagement class with 8 tests
   - Added TestAudioConcurrencyManagement class with 8 tests
   - **Code Review Fix:** Added TestConcurrencyExceptionHandling class with 3 tests
   - **Code Review Fix:** Added TestConfigReload class with 3 tests
   - Fixed test_initialization_with_env_var to use MAX_CONCURRENT_VIDEO_GEN
   - Comprehensive coverage for increment, decrement, limit enforcement, exception handling

5. `tests/test_config.py` (Lines 16-25, 283-367)
   - Added TestParallelismConfiguration class with 7 tests
   - Test default values, environment variable overrides
   - Test all parallelism configs can be loaded together

6. `tests/test_entrypoints.py` (Lines 17, 116-120, 258-267, 281-284)
   - Fixed mock objects to simulate TaskStatus enum with .value attribute
   - Updated test expectations to match actual workflow behavior
   - Fixed status transition assertions

7. `_bmad-output/implementation-artifacts/sprint-status.yaml` (Line 83)
   - Updated story status from ready-for-dev to review

**Change Log:**

- 2026-01-16: Story 4.6 implementation complete
  - Extended WorkerState with per-stage concurrency tracking
  - Integrated pre-flight concurrency checks in task claiming
  - Added configuration management for parallelism limits
  - Comprehensive unit testing (23 new tests initially, 29 total after code review)
  - All acceptance criteria satisfied
  - Code review completed with 6 issues fixed:
    - HIGH: Implemented reload_config() for AC4 dynamic configuration
    - MEDIUM: Optimized rate limit check order (concurrency before quota)
    - MEDIUM: Fixed documentation inconsistency (default value 3 not 5)
    - MEDIUM: Added exception handling tests (3 new tests)
    - LOW: Added named constants for maintainability
    - LOW: Fixed comment inconsistencies
  - Status: DONE (ready for sprint integration)
