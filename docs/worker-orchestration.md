# Worker Orchestration Patterns

**Document Status:** APPROVED
**Created:** 2026-01-18
**Authors:** Alice (Architect), Charlie (Senior Dev)
**Epic:** Epic 4 - Worker Orchestration & Parallel Processing
**Context:** These patterns emerged organically during Epic 4 implementation and represent our architectural DNA.

---

## Executive Summary

This document codifies the four core architectural patterns that emerged during Epic 4 (Worker Orchestration & Parallel Processing). These patterns form the foundation of our production-ready multi-channel video generation system and must be followed in all future worker implementations.

**The Four Patterns:**
1. **Short Transaction Pattern** - Never hold DB connection during long-running operations
2. **Worker-Local State** - No inter-worker coordination, each worker makes locally-optimal decisions
3. **Pre-Flight Check Pattern** - Verify preconditions before claiming tasks from queue
4. **Graceful Degradation** - Skip blocked tasks, continue processing available work

**Why These Patterns Matter:**
- Enable horizontal scaling without distributed coordination complexity
- Prevent database connection pool exhaustion
- Ensure system remains partially operational under constraints
- Provide fault tolerance and graceful failure handling

---

## Pattern 1: Short Transaction Pattern

### Problem
Database connections are a limited resource (10 connections in pool). Long-running operations (video generation: 36-90 minutes) that hold database connections cause pool exhaustion, preventing other workers from functioning.

### Solution
**CRITICAL RULE:** Never hold a database connection during long-running operations.

**Pattern Flow:**
1. **Claim Task** (short transaction) - Update task status, commit, close connection
2. **Close DB Connection** - Release connection back to pool
3. **Do Work** (long-running, outside transaction) - Generate videos, assets, etc.
4. **Reopen DB Connection** - Open new connection
5. **Update Task** (short transaction) - Set final status, commit, close connection

### Code Example

```python
async def process_video_generation_task(task_id: str) -> None:
    """Process video generation with Short Transaction Pattern."""

    # === TRANSACTION 1: CLAIM TASK (SHORT) ===
    async with async_session_factory() as db, db.begin():
        task = await db.get(Task, task_id)
        if not task:
            return

        # Store data needed for work
        channel_id = task.channel.channel_id
        project_id = str(task.id)

        # Claim task by updating status
        task.status = TaskStatus.GENERATING_VIDEO
        await db.commit()
        # === CONNECTION CLOSED HERE ===

    # === DO WORK (LONG-RUNNING, NO DB CONNECTION) ===
    try:
        service = VideoGenerationService(channel_id, project_id)
        result = await service.generate_videos()  # 36-90 minutes
        # Database connection is CLOSED during this entire operation

    except Exception as e:
        # Handle error (discussed in error handling section)
        pass

    # === TRANSACTION 2: UPDATE TASK (SHORT) ===
    async with async_session_factory() as db, db.begin():
        task = await db.get(Task, task_id)
        if task:
            task.status = TaskStatus.VIDEO_READY
            task.total_cost_usd += result["total_cost_usd"]
            await db.commit()
        # === CONNECTION CLOSED HERE ===
```

### Key Principles

| ✅ DO | ❌ DON'T |
|------|---------|
| Open connection, do work, close immediately | Hold connection during long operations |
| Store needed data before closing connection | Query database during long operations |
| Reopen connection for each transaction | Keep connection open "just in case" |
| Use `async with` for automatic cleanup | Manual connection management |

### Why This Works

**Connection Pool Math:**
- Pool size: 10 connections
- 3 parallel workers per pipeline stage
- Each worker holds connection for < 1 second per transaction
- **Result:** Pool never exhausts, system scales horizontally

**Without This Pattern:**
- Worker 1 claims task, holds connection for 60 minutes
- Worker 2 claims task, holds connection for 90 minutes
- Worker 3 tries to claim task → **BLOCKS** (no connections available)
- System effectively single-threaded despite parallelism

### Historical Context
**Epic 4 Story 4.2 Discovery:**
> "We initially tried holding the connection during video generation. Pool exhausted after 3 concurrent tasks. Implementing Short Transaction Pattern reduced connection hold time from 60+ minutes to < 1 second." - Charlie

---

## Pattern 2: Worker-Local State

### Problem
Distributed systems require coordination mechanisms (locks, consensus, leader election) that add complexity, introduce failure modes, and limit scalability. How can multiple workers coordinate without explicit coordination?

### Solution
**Each worker maintains its own local state and makes locally-optimal decisions.** No inter-worker coordination, no shared state, no distributed consensus.

### Examples

#### Example 1: Round-Robin Channel Scheduling (Story 4.4)

```python
class WorkerState:
    """Worker-local state (NOT shared between workers)."""

    def __init__(self):
        # Each worker tracks its own last-processed channel
        self.last_channel_processed: str | None = None

    def get_next_channel(self, available_channels: list[str]) -> str:
        """Rotate to next channel (worker-local rotation)."""
        if not self.last_channel_processed:
            # First task: pick first channel alphabetically
            next_channel = sorted(available_channels)[0]
        else:
            # Find next channel after last processed
            sorted_channels = sorted(available_channels)
            try:
                last_idx = sorted_channels.index(self.last_channel_processed)
                next_idx = (last_idx + 1) % len(sorted_channels)
                next_channel = sorted_channels[next_idx]
            except ValueError:
                # Last channel no longer exists, start over
                next_channel = sorted_channels[0]

        self.last_channel_processed = next_channel
        return next_channel
```

**Key Insight:** Each worker's round-robin is independent. Worker 1 might process `[poke1, poke2, poke3]` while Worker 2 processes `[poke2, poke3, poke1]`. **This is acceptable** - overall system distributes work fairly without coordination.

#### Example 2: Concurrency Tracking (Story 4.6)

```python
class WorkerState:
    """Worker-local concurrency tracking."""

    def __init__(self):
        # Each worker tracks its own active tasks
        self.active_tasks = {
            "asset": 0,
            "video": 0,
            "audio": 0,
        }
        self.max_concurrent = {
            "asset": 12,  # Gemini has high rate limit
            "video": 3,   # Kling is slow and expensive
            "audio": 6,   # ElevenLabs is fast
        }

    def can_claim_task(self, task_type: str) -> bool:
        """Check if worker can claim another task (worker-local decision)."""
        return self.active_tasks[task_type] < self.max_concurrent[task_type]

    def task_started(self, task_type: str):
        """Increment worker-local counter."""
        self.active_tasks[task_type] += 1

    def task_completed(self, task_type: str):
        """Decrement worker-local counter."""
        self.active_tasks[task_type] -= 1
```

**Key Insight:** Worker 1 might have 3 active video tasks while Worker 2 has 2. Total system has 5, which may exceed global target of 3. **This is acceptable** - local decisions ensure no single worker overloads, system self-balances naturally.

### Comparison: With vs. Without Coordination

| **With Worker-Local State (Our Approach)** | **With Distributed Coordination (Alternative)** |
|---------------------------------------------|--------------------------------------------------|
| ✅ No coordination overhead | ❌ Redis/ZooKeeper for shared state |
| ✅ Scales horizontally (add workers = more capacity) | ❌ Coordination becomes bottleneck |
| ✅ Failure isolation (worker crash doesn't affect others) | ❌ Coordinator failure blocks all workers |
| ✅ Simple reasoning (each worker independent) | ❌ Complex failure modes (split brain, leader election) |
| ⚠️ Locally-optimal decisions (not globally optimal) | ✅ Globally-optimal decisions possible |
| ⚠️ Eventual fairness (not instant fairness) | ✅ Instant fairness achievable |

### When Worker-Local State Works
✅ **Works well when:**
- Tasks are homogeneous (all video tasks are similar)
- Fairness is eventual (okay if channel A gets 3 tasks before channel B)
- Workers can make good local decisions (enough local information)

❌ **Doesn't work when:**
- Global constraints required (hard limit: only 3 video tasks system-wide)
- Instant fairness critical (channel A must NEVER process twice before channel B)
- Complex dependencies between workers

**Our Use Case:** Video generation is embarrassingly parallel, tasks are homogeneous, eventual fairness is sufficient → **Worker-Local State is perfect**.

### Historical Context
**Epic 4 Story 4.4 Discussion:**
> "We debated using Redis for shared round-robin state. Decided against it - adds dependency, failure mode, complexity. Worker-local rotation achieves same goal with zero coordination." - Alice

---

## Pattern 3: Pre-Flight Check Pattern

### Problem
PgQueuer's atomic claiming (FOR UPDATE SKIP LOCKED) prevents race conditions at the database level. But what if a task passes database checks but fails application-level constraints? Worker claims task, realizes it's blocked (e.g., quota exhausted), must release task. Wasted claim cycle.

### Solution
**Verify preconditions BEFORE claiming tasks from queue.**

PgQueuer provides atomic claiming, but application logic adds safety checks before processing claimed tasks. Think of it as "double-checking" - database ensures atomicity, application ensures business rules.

### Implementation Layers

#### Layer 1: Database-Level Atomic Claiming (PgQueuer)
```sql
-- PgQueuer's FOR UPDATE SKIP LOCKED pattern
SELECT * FROM tasks
WHERE status = 'pending'
ORDER BY priority, channel_id, created_at
FOR UPDATE SKIP LOCKED
LIMIT 1
```
**Guarantees:** No two workers claim same task (race condition prevented)

#### Layer 2: Application-Level Pre-Flight Checks (Our Code)
```python
async def claim_next_task() -> str | None:
    """Claim next task with pre-flight checks."""

    # Step 1: PgQueuer atomic claim (FOR UPDATE SKIP LOCKED)
    task = await pgq.claim_task()

    if not task:
        return None  # No tasks available

    # Step 2: APPLICATION-LEVEL PRE-FLIGHT CHECKS
    # Check 1: Rate limit not exceeded
    if not await check_rate_limits(task):
        await pgq.release_task(task.id)  # Release back to queue
        log.warning("rate_limit_exceeded", task_id=task.id)
        return None

    # Check 2: Quota not exceeded
    if not await check_quotas(task):
        await pgq.release_task(task.id)
        log.warning("quota_exceeded", task_id=task.id)
        return None

    # Check 3: Prerequisites met (previous steps complete)
    if not await check_prerequisites(task):
        await pgq.release_task(task.id)
        log.warning("prerequisites_not_met", task_id=task.id)
        return None

    # All checks passed - safe to process
    return task.id
```

### Pre-Flight Check Examples

#### Check 1: Rate Limit Verification (Story 4.5)
```python
async def check_rate_limits(task: Task) -> bool:
    """Verify API rate limits before claiming task."""

    # Check Kling API rate limit (5 requests per second)
    if task.requires_video_generation():
        current_rate = await get_kling_current_rate()
        if current_rate >= 5:
            log.warning("kling_rate_limit_approaching", current_rate=current_rate)
            return False  # Don't claim, avoid hitting limit

    # Check Gemini API rate limit (10 requests per second)
    if task.requires_asset_generation():
        current_rate = await get_gemini_current_rate()
        if current_rate >= 10:
            return False

    return True  # Safe to proceed
```

#### Check 2: YouTube Quota Verification (Story 4.5)
```python
async def check_quotas(task: Task) -> bool:
    """Verify YouTube API quota before claiming task."""

    channel = await get_channel(task.channel_id)

    # YouTube API quota: 10,000 units per day per channel
    # Video upload costs 1600 units
    quota_used = await get_daily_quota_usage(channel.id)
    quota_remaining = 10000 - quota_used

    if quota_remaining < 1600:
        log.warning(
            "youtube_quota_exhausted",
            channel_id=channel.channel_id,
            quota_remaining=quota_remaining
        )
        return False  # Don't claim, quota exhausted

    # Warn at 80% threshold
    if quota_remaining < 2000:  # 80% used
        log.warning(
            "youtube_quota_warning",
            channel_id=channel.channel_id,
            quota_remaining=quota_remaining
        )

    return True
```

#### Check 3: Pipeline Prerequisites (Epic 6, ADR-001)
```python
async def check_prerequisites(task: Task) -> bool:
    """Verify previous pipeline steps completed before claiming task."""

    # For video generation, verify assets and composites exist
    if task.status == TaskStatus.COMPOSITES_READY:
        metadata = task.step_completion_metadata or {}
        completed_steps = metadata.get("completed_steps", [])

        # Check: Assets must be complete
        if "assets" not in completed_steps:
            log.error("prerequisites_missing", task_id=task.id, missing="assets")
            return False

        # Check: Composites must be complete
        if "composites" not in completed_steps:
            log.error("prerequisites_missing", task_id=task.id, missing="composites")
            return False

        # Check: Files must exist on filesystem
        composite_dir = get_composite_dir(task.channel.channel_id, str(task.id))
        if not composite_dir.exists() or len(list(composite_dir.glob("*.png"))) < 18:
            log.error("composite_files_missing", task_id=task.id)
            return False

    return True  # Prerequisites met
```

### Pattern Benefits

| Benefit | Without Pre-Flight Checks | With Pre-Flight Checks |
|---------|---------------------------|------------------------|
| **Wasted Claims** | Claim task → Realize blocked → Release | Check first → Only claim if can process |
| **User Experience** | Task "claimed" but not processing (confusion) | Task only claimed when processable |
| **System Efficiency** | Claim cycles wasted on blocked tasks | Claim cycles used for processable tasks |
| **Error Handling** | Complex release logic needed | Simple: don't claim if blocked |

### Historical Context
**Epic 4 Story 4.5 Discussion:**
> "We initially claimed tasks then checked quotas. This caused tasks to get 'stuck' in claimed state when quotas exhausted. Moving checks BEFORE claiming solved this elegantly." - Charlie

---

## Pattern 4: Graceful Degradation

### Problem
What happens when constraints prevent processing certain tasks (quota exhausted, rate limit hit, API down)? Should the worker:
- A) Block and wait until constraint clears?
- B) Crash and restart later?
- C) Skip blocked tasks and continue processing others?

### Solution
**Skip blocked tasks, continue processing available work.** System remains partially operational under constraints.

### Implementation

```python
async def worker_loop():
    """Main worker loop with graceful degradation."""

    while not SHUTDOWN_REQUESTED:
        try:
            # Claim next available task
            task_id = await claim_next_task()  # Includes pre-flight checks

            if task_id:
                # Process task
                await process_task(task_id)
            else:
                # No processable tasks available
                # Could be:
                # 1. No tasks in queue (wait and retry)
                # 2. All tasks blocked by constraints (wait and retry)
                # 3. Pre-flight checks failed (wait and retry)

                log.debug("no_processable_tasks")
                await asyncio.sleep(5)  # Wait 5 seconds, try again

                # GRACEFUL DEGRADATION: Worker continues trying
                # - Doesn't crash
                # - Doesn't block indefinitely
                # - Processes new tasks as they arrive
                # - Retries blocked tasks when constraints clear

        except Exception as e:
            log.error("worker_loop_error", error=str(e))
            # GRACEFUL DEGRADATION: Error doesn't stop worker
            await asyncio.sleep(5)  # Brief pause, then continue
```

### Degradation Scenarios

#### Scenario 1: YouTube Quota Exhausted (Story 4.5)

```
Initial State:
- 100 tasks in queue
- Channel A: 50 tasks (quota exhausted)
- Channel B: 50 tasks (quota available)

Without Graceful Degradation:
- Worker claims Channel A task
- Realizes quota exhausted
- Blocks or crashes
- 50 Channel B tasks not processed (SYSTEM BLOCKED)

With Graceful Degradation:
- Worker claims Channel A task
- Pre-flight check: quota exhausted → release task
- Worker claims Channel B task
- Pre-flight check: quota available → process task
- Worker processes all 50 Channel B tasks
- Channel A tasks remain in queue (processed tomorrow when quota resets)
- SYSTEM PARTIALLY OPERATIONAL
```

#### Scenario 2: Kling API Rate Limit (Story 4.5)

```
Situation: Kling API rate limit hit (5 requests/sec)

Without Graceful Degradation:
- Worker hits rate limit
- Crashes or blocks
- No tasks processed until rate limit resets

With Graceful Degradation:
- Worker claims video task
- Pre-flight check: rate limit hit → release task
- Worker sleeps 5 seconds
- Worker claims audio task (different API)
- Pre-flight check: ElevenLabs has capacity → process task
- Worker processes audio tasks while video tasks wait
- SYSTEM PARTIALLY OPERATIONAL
```

#### Scenario 3: Partial API Outage

```
Situation: Kling API down (video generation unavailable)

Without Graceful Degradation:
- Worker tries video generation
- Fails due to API outage
- Crashes or blocks
- All pipeline stages stop

With Graceful Degradation:
- Worker tries video generation
- Fails due to API outage
- Task marked VIDEO_ERROR (for retry later)
- Worker continues processing:
  - Asset generation tasks (Gemini API works)
  - Audio generation tasks (ElevenLabs API works)
  - Assembly tasks (FFmpeg local, works)
- Video tasks accumulate in ERROR state
- When Kling API recovers, retry mechanism (Epic 6) reprocesses failed tasks
- SYSTEM MOSTLY OPERATIONAL
```

### Degradation Principles

| Principle | Description | Example |
|-----------|-------------|---------|
| **Fail Loudly** | Log errors clearly, don't hide problems | `log.error("kling_api_down")` |
| **Fail Gracefully** | Don't crash, continue processing other work | Skip failed task, try next task |
| **Fail Visibly** | Update task status so users see issues | `task.status = VIDEO_ERROR` |
| **Fail Temporarily** | Assume transient failures, enable retry | Mark ERROR not TERMINAL_ERROR |

### Monitoring Graceful Degradation

```python
# Metrics to track degradation
metrics = {
    "tasks_processed_per_minute": 50,  # Healthy: 50 tasks/min
    "tasks_skipped_quota": 10,         # 10 tasks skipped (quota)
    "tasks_skipped_rate_limit": 5,     # 5 tasks skipped (rate limit)
    "tasks_failed_api_down": 2,        # 2 tasks failed (API down)

    # Health indicator: 50 processed / (50 + 10 + 5 + 2) = 74% healthy
    "system_health": 0.74
}

# Alert thresholds
if metrics["system_health"] < 0.5:
    alert("CRITICAL: System health below 50%")
elif metrics["system_health"] < 0.8:
    alert("WARNING: System health below 80%")
```

### Historical Context
**Epic 4 Story 4.5 Retrospective:**
> "The graceful degradation pattern emerged when we added quota tracking. Instead of blocking when quota exhausted, workers just skip those tasks and process others. System stays alive even when one channel is blocked." - Alice

---

## How Patterns Work Together

These four patterns are **synergistic** - they work together to create a robust, scalable system.

### Example: Video Generation Task Processing

```python
async def worker_loop():
    """Complete worker loop demonstrating all 4 patterns."""

    # PATTERN 2: Worker-Local State
    worker_state = WorkerState()

    while not SHUTDOWN_REQUESTED:
        # PATTERN 3: Pre-Flight Check
        # Check rate limits and quotas before claiming
        if not await check_system_constraints():
            await asyncio.sleep(5)
            continue  # PATTERN 4: Graceful Degradation

        # PATTERN 2: Worker-Local State
        # Check worker-local concurrency
        if not worker_state.can_claim_task("video"):
            await asyncio.sleep(1)
            continue  # PATTERN 4: Graceful Degradation

        # Claim task atomically (PgQueuer + Pre-Flight Checks)
        task_id = await claim_next_task()

        if not task_id:
            await asyncio.sleep(5)
            continue  # PATTERN 4: Graceful Degradation

        # PATTERN 1: Short Transaction Pattern
        # === TRANSACTION 1: CLAIM ===
        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            task.status = TaskStatus.GENERATING_VIDEO
            await db.commit()
        # === CONNECTION CLOSED ===

        # PATTERN 2: Worker-Local State
        worker_state.task_started("video")

        try:
            # === LONG-RUNNING WORK (NO DB CONNECTION) ===
            result = await generate_videos(task_id)  # 36-90 minutes

            # PATTERN 1: Short Transaction Pattern
            # === TRANSACTION 2: UPDATE ===
            async with async_session_factory() as db, db.begin():
                task = await db.get(Task, task_id)
                task.status = TaskStatus.VIDEO_READY
                task.total_cost_usd += result["total_cost_usd"]
                await db.commit()
            # === CONNECTION CLOSED ===

        except Exception as e:
            # PATTERN 4: Graceful Degradation
            log.error("video_generation_error", error=str(e))
            async with async_session_factory() as db, db.begin():
                task = await db.get(Task, task_id)
                task.status = TaskStatus.VIDEO_ERROR  # Mark for retry
                await db.commit()
            # Continue processing other tasks (don't crash)

        finally:
            # PATTERN 2: Worker-Local State
            worker_state.task_completed("video")
```

### Pattern Interaction Map

```
┌─────────────────────────────────────────────────────────────┐
│                      Worker Loop                            │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ PATTERN 2: Worker-Local State                        │  │
│  │ - Track concurrency limits                           │  │
│  │ - Round-robin channel selection                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ PATTERN 3: Pre-Flight Check                          │  │
│  │ - Check rate limits                                   │  │
│  │ - Check quotas                                        │  │
│  │ - Check prerequisites                                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ PATTERN 1: Short Transaction (Claim)                 │  │
│  │ - Open connection                                     │  │
│  │ - Claim task                                          │  │
│  │ - Close connection                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Long-Running Work (NO DB CONNECTION)                 │  │
│  │ - Generate videos                                     │  │
│  │ - Generate assets                                     │  │
│  │ - Assemble video                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ PATTERN 1: Short Transaction (Update)                │  │
│  │ - Open connection                                     │  │
│  │ - Update task status                                  │  │
│  │ - Close connection                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↓                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ PATTERN 4: Graceful Degradation                      │  │
│  │ - On error: log, mark task for retry, continue      │  │
│  │ - On constraint: skip task, process others          │  │
│  │ - On empty queue: sleep, retry                       │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Anti-Patterns (What NOT To Do)

### ❌ Anti-Pattern 1: Long Transaction
```python
# BAD: Hold connection during long operation
async with async_session_factory() as db, db.begin():
    task = await db.get(Task, task_id)
    task.status = TaskStatus.GENERATING_VIDEO

    # BAD: Connection held for 60+ minutes
    result = await generate_videos()  # 60 minutes

    task.status = TaskStatus.VIDEO_READY
    await db.commit()  # Connection finally released
```
**Why Bad:** Connection held for 60 minutes → Pool exhausts → System deadlocks

### ❌ Anti-Pattern 2: Distributed Coordination
```python
# BAD: Use Redis for worker coordination
import redis

redis_client = redis.Redis()

# BAD: Global round-robin state in Redis
def get_next_channel():
    # Get last processed channel from Redis
    last_channel = redis_client.get("last_channel_processed")

    # Increment to next channel
    next_channel = calculate_next(last_channel)

    # Update Redis
    redis_client.set("last_channel_processed", next_channel)

    return next_channel
```
**Why Bad:** Redis dependency, coordination overhead, failure mode (Redis down = all workers blocked), doesn't scale

### ❌ Anti-Pattern 3: Post-Claim Checks
```python
# BAD: Check constraints after claiming
async def process_task(task_id):
    # Already claimed task
    task = await claim_task()

    # BAD: Check quotas AFTER claiming
    if not check_quotas(task):
        # Now we have to release - wasted claim cycle
        await release_task(task)
        return

    # Process task
    await do_work(task)
```
**Why Bad:** Wasted claim cycles, task "stuck" in claimed state temporarily, user confusion

### ❌ Anti-Pattern 4: Crash on Constraint
```python
# BAD: Crash when constraint hit
async def worker_loop():
    while True:
        task = await claim_task()

        # BAD: Crash when quota exhausted
        if not check_quotas(task):
            raise Exception("Quota exhausted!")  # Worker dies

        await process_task(task)
```
**Why Bad:** Worker dies, all other work blocked, not fault-tolerant, poor user experience

---

## Checklist for New Workers

When implementing a new worker, verify all four patterns are followed:

### ✅ Pattern 1: Short Transaction
- [ ] Database connection opened only for claim transaction
- [ ] Connection closed before long-running work
- [ ] Connection reopened only for update transaction
- [ ] No queries during long-running work
- [ ] Transaction hold time < 1 second

### ✅ Pattern 2: Worker-Local State
- [ ] No shared state between workers (no Redis, no ZooKeeper)
- [ ] Worker maintains own state (concurrency counters, round-robin rotation)
- [ ] Decisions made locally without coordination
- [ ] Worker state reset on restart (not persisted)

### ✅ Pattern 3: Pre-Flight Check
- [ ] Rate limits checked BEFORE claiming task
- [ ] Quotas checked BEFORE claiming task
- [ ] Prerequisites checked BEFORE claiming task
- [ ] Task released if pre-flight checks fail
- [ ] Clear logging when checks fail

### ✅ Pattern 4: Graceful Degradation
- [ ] Worker loop doesn't crash on individual task failure
- [ ] Errors logged clearly
- [ ] Tasks marked for retry (not terminal failure)
- [ ] Worker continues processing other tasks
- [ ] Sleep between iterations to avoid busy-loop

---

## Migration Guide: Adapting Existing Workers

If you have an existing worker that doesn't follow these patterns, here's how to migrate:

### Step 1: Implement Short Transaction Pattern

**Before:**
```python
async with session.begin():
    task = await session.get(Task, task_id)
    result = await long_operation()  # BAD: Connection held
    task.status = "completed"
    await session.commit()
```

**After:**
```python
# Transaction 1: Claim
async with session.begin():
    task = await session.get(Task, task_id)
    task.status = "processing"
    await session.commit()
# Connection closed

result = await long_operation()  # GOOD: No connection

# Transaction 2: Update
async with session.begin():
    task = await session.get(Task, task_id)
    task.status = "completed"
    await session.commit()
# Connection closed
```

### Step 2: Add Worker-Local State

```python
class WorkerState:
    def __init__(self):
        self.active_tasks = 0
        self.max_concurrent = 5

worker_state = WorkerState()

# Check before claiming
if worker_state.active_tasks >= worker_state.max_concurrent:
    await asyncio.sleep(1)
    continue
```

### Step 3: Add Pre-Flight Checks

```python
async def claim_with_checks():
    task = await pgq.claim_task()
    if not task:
        return None

    # Pre-flight checks
    if not await check_rate_limits(task):
        await pgq.release_task(task)
        return None

    if not await check_quotas(task):
        await pgq.release_task(task)
        return None

    return task
```

### Step 4: Add Graceful Degradation

```python
while not SHUTDOWN_REQUESTED:
    try:
        task = await claim_with_checks()
        if not task:
            await asyncio.sleep(5)  # Graceful: sleep and retry
            continue

        await process_task(task)

    except Exception as e:
        log.error("task_error", error=str(e))
        # Graceful: continue processing other tasks
        await asyncio.sleep(5)
```

---

## Conclusion

These four patterns represent Epic 4's architectural DNA:

1. **Short Transaction Pattern** → Prevents connection pool exhaustion
2. **Worker-Local State** → Enables horizontal scaling without coordination
3. **Pre-Flight Check Pattern** → Prevents wasted claim cycles
4. **Graceful Degradation** → Keeps system partially operational under constraints

**All future workers MUST follow these patterns.**

**Status:** APPROVED ✅ - These patterns are now mandatory for all worker implementations.
