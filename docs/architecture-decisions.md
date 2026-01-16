# Architecture Decision Record (ADR)

**Project:** ai-video-generator
**Last Updated:** January 16, 2026
**Status:** Living Document (updated each epic)

---

## Table of Contents

1. [ADR-001: Short Transaction Pattern](#adr-001-short-transaction-pattern)
2. [ADR-002: Filesystem Asset Storage](#adr-002-filesystem-asset-storage)
3. [ADR-003: Service/Worker Separation](#adr-003-serviceworker-separation)
4. [ADR-004: Async Execution Throughout](#adr-004-async-execution-throughout)
5. [ADR-005: "Smart Agent + Dumb Scripts" Pattern](#adr-005-smart-agent--dumb-scripts-pattern)

---

## ADR-001: Short Transaction Pattern

**Status:** ✅ Accepted (Implemented in Epic 3 Story 3.1)

**Date:** January 15, 2026

**Decision Makers:** Dev Agent (Claude Sonnet 4.5), Francis (Stakeholder)

### Context

Video generation pipeline executes long-running operations (asset generation: 5-15 min, video generation: 36-90 min) that must not hold database connections. Holding database transactions during CLI script execution causes:

- Database connection pool exhaustion (only 10-15 connections available)
- Worker blocking (other workers can't claim tasks)
- Transaction timeouts (PostgreSQL kills long transactions)
- Cascading failures (one slow worker blocks entire system)

**Problem Statement:** How to manage database state for long-running operations without holding connections?

### Decision

**Implement short transaction pattern:** Claim task → **close database connection** → execute long operation → reopen connection → update task.

**Pattern Implementation:**

```python
# Step 1: Claim task (SHORT transaction)
async with AsyncSessionLocal() as db:
    async with db.begin():
        task = await db.get(Task, task_id)
        task.status = "processing"
        await db.commit()
# DB connection CLOSED here

# Step 2: Execute long operation (NO database connection held)
result = await service.generate_assets(manifest)  # 5-15 minutes

# Step 3: Update task (SHORT transaction)
async with AsyncSessionLocal() as db:
    async with db.begin():
        task = await db.get(Task, task_id)
        task.status = "completed"
        task.total_cost_usd += result["total_cost_usd"]
        await db.commit()
# DB connection CLOSED here
```

### Rationale

**Prevents Connection Pool Exhaustion:**
- 3 workers × 2-hour pipeline = 6 hours of connection time if held
- With short transactions: 3 workers × 1 second per transaction = ~20 seconds total
- Connection pool remains available for other operations

**Enables Horizontal Scaling:**
- Can add more workers without increasing connection pool size
- Workers are stateless (don't hold resources)
- Railway can scale workers independently

**Survives Worker Crashes:**
- Task state in database persists across crashes
- Worker restart reclaims task and resumes
- No in-memory state lost (everything in PostgreSQL)

### Consequences

**Positive:**
- ✅ Connection pool never exhausted (connections released immediately)
- ✅ Workers can scale horizontally (stateless design)
- ✅ Worker crashes don't leave transactions open
- ✅ Database monitoring shows short transaction durations

**Negative:**
- ❌ Task state must be idempotent (can resume after crash)
- ❌ Worker must handle "already processing" race condition
- ❌ Metrics harder (can't track full duration in single transaction)
- ❌ Two round-trips to database per operation (claim + update)

**Mitigation:**
- Idempotency: Design operations to be safely resumable (Story 3.3+ implement this)
- Race condition: Use `FOR UPDATE SKIP LOCKED` (Epic 4 will implement)
- Metrics: Log start/end times separately, correlate with task_id
- Round-trips: Acceptable overhead (~20ms each) vs. connection exhaustion

### Alternatives Considered

**Alternative 1: Hold Transaction Throughout (REJECTED)**
- Pro: Simple code (one transaction)
- Con: Connection pool exhaustion
- Con: Can't scale beyond 10-15 workers
- **Rejected:** Doesn't scale to production workload

**Alternative 2: Use Job Queue (Celery, RQ) (REJECTED)**
- Pro: Built-in task management
- Con: Additional infrastructure (Redis/RabbitMQ)
- Con: Doesn't solve long-running operation problem
- **Rejected:** Over-engineering for current needs, PgQueuer sufficient

**Alternative 3: Polling with Status Updates (REJECTED)**
- Pro: No connection held
- Con: Polling overhead
- Con: Eventual consistency issues
- **Rejected:** Short transaction pattern simpler and more reliable

### Verification

**Test Cases:**
- Story 3.1: Unit tests verify transaction lifecycle
- Story 3.3: Integration tests verify short transactions with real operations
- Story 3.9: End-to-end tests verify full pipeline with proper connection management

**Production Validation:**
- Railway connection pool monitoring (check no exhaustion)
- PostgreSQL slow query log (check no long transactions)
- Worker crash recovery (verify tasks resume correctly)

### Related ADRs

- [ADR-004](#adr-004-async-execution-throughout) - Async patterns enable non-blocking operations
- [ADR-003](#adr-003-serviceworker-separation) - Service layer called outside transactions

### References

- Architecture document: `_bmad-output/planning-artifacts/architecture.md` (lines 375-401)
- Epic 3 Story 3.1: `_bmad-output/implementation-artifacts/3-1-cli-script-wrapper-async-execution.md`
- Epic 3 Retrospective: `_bmad-output/implementation-artifacts/epic-3-retrospective-2026-01-16.md`

---

## ADR-002: Filesystem Asset Storage

**Status:** ✅ Accepted (Implemented in Epic 3 Story 3.2)

**Date:** January 15, 2026

**Decision Makers:** Dev Agent (Claude Sonnet 4.5), Francis (Stakeholder)

### Context

Video generation pipeline produces large binary files:
- 22 image assets per video (PNG, ~500KB-2MB each)
- 18 video clips per video (MP4, ~10-50MB each)
- 18 audio clips per video (MP3, ~200KB-1MB each)
- 18 sound effects per video (WAV, ~100KB-500KB each)
- 1 final video per video (MP4, ~50-150MB)

**Total:** ~500MB-1GB per video × 100 videos/week = 50-100GB/week

**Problem Statement:** Where to store video/audio/image assets?

### Decision

**Store assets on filesystem in channel-isolated directories, database stores file paths only.**

**Directory Structure:**
```
/app/workspace/                                 # Railway persistent volume
└── channels/
    ├── poke1/                                 # Channel 1 workspace
    │   └── projects/
    │       ├── vid_abc123/                    # Project 1
    │       │   ├── assets/
    │       │   │   ├── characters/            # Character images
    │       │   │   ├── environments/          # Environment backgrounds
    │       │   │   ├── props/                 # Prop images
    │       │   │   └── composites/            # 16:9 composite images
    │       │   ├── videos/                    # Generated video clips
    │       │   ├── audio/                     # Narration MP3s
    │       │   └── sfx/                       # Sound effect WAVs
    │       └── vid_def456/                    # Project 2
    └── poke2/                                 # Channel 2 workspace (isolated)
```

**Database Schema:**
```sql
-- Tasks table stores FILE PATHS, not file contents
tasks (
    id UUID PRIMARY KEY,
    channel_id VARCHAR,
    project_id VARCHAR,
    final_video_path VARCHAR,  -- e.g., "/app/workspace/channels/poke1/projects/vid_123/final.mp4"
    ...
)
```

### Rationale

**Preserves Brownfield CLI Script Interfaces:**
- Existing scripts expect filesystem paths: `--output /path/to/asset.png`
- Scripts are stateless, communicate via files
- No need to modify 7 existing CLI scripts (1,599 LOC)

**Natural Fit for Large Binary Files:**
- Database blob storage inefficient for 50-150MB video files
- Filesystem read/write faster than database for large files
- Can stream files directly to YouTube without database round-trip

**Easy Debugging and Inspection:**
- Can inspect assets directly via Railway shell (`railway shell`)
- Can download files for manual review
- ffprobe, ffplay work directly on filesystem files

**Proven Pattern:**
- Single-project implementation already uses filesystem
- 4 complete example projects validate approach
- No known issues with filesystem-based workflow

### Consequences

**Positive:**
- ✅ CLI scripts unchanged (brownfield constraint satisfied)
- ✅ Fast large file operations (no database overhead)
- ✅ Easy manual inspection (Railway shell access)
- ✅ Proven pattern (existing implementation validates)

**Negative:**
- ❌ Must keep filesystem and database in sync
- ❌ Cleanup requires filesystem + database operations
- ❌ Cannot query asset metadata without reading files
- ❌ Filesystem size limits (Railway volume size)

**Mitigation:**
- Sync: Atomic operations (write file → commit DB path) prevent orphans
- Cleanup: Periodic cleanup job (Epic 8) removes old projects
- Metadata: Store essential metadata in database (duration, size, cost)
- Size limits: Monitor Railway volume usage, implement cleanup policy

### Alternatives Considered

**Alternative 1: Database Blob Storage (REJECTED)**
- Pro: Single source of truth
- Con: 50-150MB video files bloat database
- Con: Slow read/write for large files
- **Rejected:** Inefficient for large binary files

**Alternative 2: S3/Object Storage (REJECTED)**
- Pro: Unlimited storage
- Pro: Built-in redundancy
- Con: Additional infrastructure cost
- Con: Latency for file access
- Con: CLI scripts need modification
- **Rejected:** Over-engineering for MVP, Railway volume sufficient

**Alternative 3: Hybrid (Small in DB, Large on Filesystem) (REJECTED)**
- Pro: Best of both worlds
- Con: Complex implementation (two storage layers)
- Con: Inconsistent patterns
- **Rejected:** Adds complexity without clear benefit

### Verification

**Test Cases:**
- Story 3.2: 32 tests verify path helpers and isolation
- Story 3.3: Service tests verify asset creation on filesystem
- Story 3.9: Integration tests verify full pipeline file management

**Production Validation:**
- Railway volume usage monitoring
- Filesystem cleanup job effectiveness
- Database/filesystem consistency checks

### Security Considerations

**Path Traversal Prevention:**
- Story 3.2 implements regex validation: `^[a-zA-Z0-9_-]+$`
- Resolved path verification ensures paths stay within `/app/workspace/`
- Malicious identifiers like `"../../../etc"` rejected
- See [ADR-002 Security Analysis](#adr-002-security)

### Related ADRs

- [ADR-005](#adr-005-smart-agent--dumb-scripts-pattern) - CLI scripts operate on filesystem
- [ADR-003](#adr-003-serviceworker-separation) - Service layer handles path construction

### References

- Architecture document: `_bmad-output/planning-artifacts/architecture.md` (lines 361-366)
- Epic 3 Story 3.2: `_bmad-output/implementation-artifacts/3-2-filesystem-organization-path-helpers.md`
- Epic 3 Retrospective: Path helpers prevent bug classes

---

## ADR-003: Service/Worker Separation

**Status:** ✅ Accepted (Implemented in Epic 3 Stories 3.3-3.9)

**Date:** January 15, 2026

**Decision Makers:** Dev Agent (Claude Sonnet 4.5), Francis (Stakeholder)

### Context

Worker processes orchestrate pipeline execution: claim tasks, execute operations, update database. This mixes business logic (what to do) with orchestration (when/how to do it), making testing difficult.

**Problem:** How to structure code for testability without sacrificing clarity?

### Decision

**Separate service layer (business logic) from worker layer (orchestration).**

**Layer Responsibilities:**

**Service Layer** (`app/services/`)
- **What:** Business logic, validation, calculations
- **Dependencies:** Utils only (no database, no models)
- **Testing:** Pure unit tests (no database mocking)
- **Example:** `AssetGenerationService.create_asset_manifest()`

**Worker Layer** (`app/workers/`)
- **What:** Orchestration, database transactions, error handling
- **Dependencies:** Services + Database + Models
- **Testing:** Integration tests (real database)
- **Example:** `process_asset_generation_task()`

**Code Structure:**
```
app/
├── services/              # Business logic (pure, no DB)
│   ├── asset_generation.py
│   ├── video_generation.py
│   └── ...
├── workers/               # Orchestration (DB-aware)
│   ├── asset_worker.py
│   ├── video_worker.py
│   └── ...
└── models.py              # Database models
```

### Rationale

**Testability:**
- **Service tests are fast:** No database setup, pure function mocks
- **Service tests are pure:** Business logic isolated from orchestration complexity
- **Worker tests verify integration:** Real database behavior without service complexity

**Example: Story 3.3 Test Results:**
- Service layer: 17 tests in ~0.5 seconds (no database I/O)
- Worker layer: 3 tests in ~5 seconds (database setup overhead)
- **Total:** 20 tests, 90% are fast unit tests (test pyramid)

**Maintainability:**
- **Clear boundaries:** Service = business logic, Worker = orchestration
- **Independent evolution:** Can change worker orchestration without breaking service tests
- **Refactoring safety:** Service tests catch business logic regressions

**Reusability:**
- Services used by multiple workers (asset generation, video generation, etc.)
- Services used by CLI tools (manual operations)
- Services used by API endpoints (Epic 5+)

### Consequences

**Positive:**
- ✅ Fast test feedback loop (service tests in milliseconds)
- ✅ Clear responsibility boundaries (service vs. worker)
- ✅ Refactoring safety (service tests unchanged when worker changes)
- ✅ Test pyramid: Many fast unit tests, few slow integration tests

**Negative:**
- ❌ More files (service + worker per feature)
- ❌ Pass-through methods in worker layer (boilerplate)
- ❌ Need conventions to prevent logic leaking into worker

**Mitigation:**
- More files: Acceptable tradeoff for testability and clarity
- Pass-through: Minimal boilerplate, clear orchestration patterns
- Conventions: Code reviews enforce service/worker separation

### Pattern Enforcement

**Service Layer Rules:**
```python
# ✅ CORRECT: Service has NO database imports
from app.utils.cli_wrapper import run_cli_script
from app.utils.filesystem import get_asset_dir

class AssetGenerationService:
    def __init__(self, channel_id: str, project_id: str):
        # No database, no models
        pass

# ❌ WRONG: Service imports database/models
from app.database import AsyncSessionLocal  # FORBIDDEN
from app.models import Task  # FORBIDDEN
```

**Worker Layer Rules:**
```python
# ✅ CORRECT: Worker orchestrates, delegates logic to service
async def process_asset_generation_task(task_id: str):
    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)  # Database operation
        task.status = "processing"
        await db.commit()

    # Delegate to service (no DB)
    service = AssetGenerationService(task.channel_id, task.project_id)
    result = await service.generate_assets(manifest)

    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        task.status = "completed"
        await db.commit()

# ❌ WRONG: Worker has business logic
async def process_asset_generation_task(task_id: str):
    # DON'T implement business logic here
    for asset in assets:
        combined_prompt = f"{atmosphere}\n\n{asset.prompt}"  # Business logic in worker
```

### Alternatives Considered

**Alternative 1: Monolithic Worker (REJECTED)**
- Pro: Single file per feature
- Con: Business logic mixed with orchestration
- Con: Tests require database for everything
- **Rejected:** Poor testability

**Alternative 2: Repository Pattern (REJECTED)**
- Pro: Standard enterprise pattern
- Con: Over-engineering for current needs
- Con: Extra abstraction layer without clear benefit
- **Rejected:** Service/Worker separation simpler

**Alternative 3: Domain-Driven Design (REJECTED)**
- Pro: Rich domain models
- Con: Complex for current domain
- Con: Overkill for orchestration layer
- **Rejected:** DDD better for complex business domains

### Verification

**Test Coverage:**
- Story 3.3: 17 service tests (100% pass, no DB)
- Story 3.9: Integration tests verify service/worker integration
- All stories follow pattern consistently

**Code Review:**
- Verify services don't import database/models
- Verify workers delegate business logic to services
- Verify test pyramid: 80%+ unit tests, 20%- integration tests

### Related ADRs

- [ADR-001](#adr-001-short-transaction-pattern) - Worker calls service outside transaction
- [ADR-004](#adr-004-async-execution-throughout) - Both layers use async patterns

### References

- Epic 3 Retrospective: "Service/Worker Separation Improves Testability"
- Story 3.3: First implementation of service/worker pattern
- All Epic 3 stories: Consistent application of pattern

---

## ADR-004: Async Execution Throughout

**Status:** ✅ Accepted (Implemented in Epic 3 Story 3.1+)

**Date:** January 15, 2026

**Decision Makers:** Dev Agent (Claude Sonnet 4.5), Francis (Stakeholder)

### Context

Video generation pipeline has I/O-bound operations:
- External API calls (Gemini, Kling, ElevenLabs)
- Database operations (PostgreSQL queries)
- File system operations (read/write large files)
- Subprocess execution (CLI scripts)

Synchronous code blocks event loop, preventing concurrent execution.

**Problem:** How to enable 3 concurrent workers without blocking?

### Decision

**Use async/await throughout application: database, CLI scripts, API clients, all async.**

**Implementation Patterns:**

**Database (SQLAlchemy 2.0 Async):**
```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

engine = create_async_engine("postgresql+asyncpg://...")

async with AsyncSession(engine) as session:
    task = await session.get(Task, task_id)
    await session.commit()
```

**CLI Scripts (asyncio.to_thread):**
```python
import asyncio
import subprocess

async def run_cli_script(script: str, args: list[str], timeout: int):
    return await asyncio.to_thread(
        subprocess.run,
        ["python", f"scripts/{script}"] + args,
        capture_output=True,
        timeout=timeout
    )
```

**External APIs (aiohttp/httpx):**
```python
import httpx

async def call_gemini_api(prompt: str) -> bytes:
    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.gemini.com/...", json={"prompt": prompt})
        return response.content
```

### Rationale

**Enables Concurrent Execution:**
- 3 workers can process tasks in parallel
- While one worker waits for Kling API, others progress
- Event loop remains responsive for status updates

**Example Concurrency:**
```
Worker 1: Asset generation (waiting for Gemini API)
Worker 2: Video generation (waiting for Kling API)
Worker 3: Database query (waiting for PostgreSQL)
```

With sync code: Total time = Sum of all operations
With async code: Total time ≈ Max of all operations

**Railway Platform Requirement:**
- Railway supports async Python (asyncio)
- FastAPI (async by default) for web service
- PgQueuer (async task queue) for worker coordination

**Future Scalability:**
- Can add more workers without changing code
- Can use Railway horizontal scaling
- Can optimize bottlenecks with async profiling

### Consequences

**Positive:**
- ✅ 3 concurrent workers without blocking
- ✅ Better resource utilization (CPU while waiting for I/O)
- ✅ Event loop responsive for monitoring/status
- ✅ Railway scaling-friendly architecture

**Negative:**
- ❌ Async complexity (must use async/await consistently)
- ❌ Testing complexity (pytest-asyncio required)
- ❌ Debugging harder (async stack traces)
- ❌ Cannot use synchronous libraries without wrappers

**Mitigation:**
- Complexity: Type hints catch async/await mistakes
- Testing: pytest-asyncio patterns established (conftest.py)
- Debugging: Structured logging with correlation IDs
- Sync libraries: `asyncio.to_thread()` wrapper pattern

### Pattern Consistency

**All layers use async:**
- ✅ Database: SQLAlchemy async engine + AsyncSession
- ✅ CLI scripts: `asyncio.to_thread(subprocess.run)`
- ✅ API clients: httpx AsyncClient
- ✅ Workers: async def functions
- ✅ Services: async def functions

**No mixing sync/async:**
```python
# ❌ WRONG: Sync function in async codebase
def generate_asset(prompt: str):
    result = subprocess.run(...)  # BLOCKS event loop
    return result

# ✅ CORRECT: Async wrapper
async def generate_asset(prompt: str):
    result = await asyncio.to_thread(subprocess.run, ...)
    return result
```

### Alternatives Considered

**Alternative 1: Threading (REJECTED)**
- Pro: Simpler than async
- Con: GIL limits parallelism
- Con: Thread overhead (stack memory)
- **Rejected:** Async better for I/O-bound workload

**Alternative 2: Multiprocessing (REJECTED)**
- Pro: True parallelism
- Con: Expensive process creation
- Con: Inter-process communication overhead
- **Rejected:** Over-engineering for I/O-bound work

**Alternative 3: Celery Workers (REJECTED)**
- Pro: Mature task queue
- Con: Requires Redis/RabbitMQ
- Con: Doesn't solve async database problem
- **Rejected:** PgQueuer + async simpler

### Verification

**Test Cases:**
- Story 3.1: Async execution verified (non-blocking tests)
- Story 3.9: Concurrent workers verified (3 workers in parallel)
- All tests use pytest-asyncio

**Production Validation:**
- Railway metrics: CPU utilization while I/O operations in progress
- Worker concurrency: 3 tasks processing simultaneously
- No event loop blocking (response time remains low)

### Related ADRs

- [ADR-001](#adr-001-short-transaction-pattern) - Async database sessions enable short transactions
- [ADR-003](#adr-003-serviceworker-separation) - Both layers use async patterns

### References

- Architecture document: Async execution required (NFR-PER-001)
- Story 3.1: CLI wrapper implements `asyncio.to_thread()`
- SQLAlchemy 2.0 docs: Async patterns

---

## ADR-005: "Smart Agent + Dumb Scripts" Pattern

**Status:** ✅ Accepted (Implemented in Epic 3, preserving brownfield architecture)

**Date:** January 15, 2026

**Decision Makers:** Dev Agent (Claude Sonnet 4.5), Francis (Stakeholder)

### Context

Existing single-project implementation has 7 CLI scripts (1,599 LOC) that work well:
- `generate_asset.py` (Gemini API)
- `create_composite.py` (FFmpeg compositing)
- `generate_video.py` (Kling API)
- `generate_audio.py` (ElevenLabs narration)
- `generate_sound_effects.py` (ElevenLabs SFX)
- `assemble_video.py` (FFmpeg assembly)

Scripts are **stateless**: Take complete inputs via CLI args, execute single API call, return success/failure.

**Problem:** How to add orchestration layer without rewriting proven scripts?

### Decision

**Preserve "Smart Agent + Dumb Scripts" pattern: Orchestrator reads files, combines prompts, retries failures. Scripts execute single API calls.**

**Pattern Responsibilities:**

**Orchestrator (Smart):**
- Read Notion project data (Topic, Story Direction)
- Extract Global Atmosphere Block from context
- Combine atmosphere + individual prompts
- Construct filesystem paths
- Invoke CLI scripts with complete arguments
- Retry failures with exponential backoff
- Update database state and Notion status

**Scripts (Dumb):**
- Receive complete prompt via `--prompt` argument
- Call external API (Gemini, Kling, ElevenLabs)
- Download result
- Save to file at `--output` path
- Exit with code 0 (success) or 1 (failure)
- Log to stdout/stderr (captured by orchestrator)

**Example:**
```python
# Orchestrator (Smart) - Story 3.3
global_atmosphere = "Natural forest lighting, misty morning atmosphere"
asset_prompt = "Bulbasaur resting under oak tree"
combined_prompt = f"{global_atmosphere}\n\n{asset_prompt}"

output_path = get_character_dir(channel_id, project_id) / "bulbasaur_resting.png"

result = await run_cli_script(
    "generate_asset.py",
    ["--prompt", combined_prompt, "--output", str(output_path)],
    timeout=60
)

# Script (Dumb) - scripts/generate_asset.py (unchanged)
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    # Call Gemini API
    response = genai.ImageGenerationModel("gemini-2.5-flash-image").generate_images(args.prompt)

    # Save PNG
    with open(args.output, "wb") as f:
        f.write(response.images[0].data)

    sys.exit(0)  # Success
```

### Rationale

**Brownfield Constraint Satisfied:**
- 7 existing scripts remain 100% unchanged (1,599 LOC preserved)
- Proven functionality continues working
- Zero regression risk from script modifications

**Clear Separation of Concerns:**
- **Orchestrator:** State management, retry logic, error handling, status updates
- **Scripts:** Single API call, no state, no retry logic, no file reading

**Easy Debugging:**
- Can run scripts manually: `python scripts/generate_asset.py --prompt "..." --output "..."`
- Scripts are self-contained (no orchestrator dependencies)
- Stdout/stderr captured by orchestrator for troubleshooting

**Testability:**
- Orchestrator tested via service/worker patterns
- Scripts tested independently (existing test suite)
- Integration tests verify orchestrator → script communication

### Consequences

**Positive:**
- ✅ Zero script modifications (brownfield preserved)
- ✅ Proven functionality unchanged (no regression)
- ✅ Clear boundaries (orchestrator vs. script)
- ✅ Easy manual testing (can run scripts standalone)

**Negative:**
- ❌ Cannot share code between orchestrator and scripts (different processes)
- ❌ CLI argument passing overhead (JSON serialization for complex data)
- ❌ Stdout/stderr parsing if structured data needed
- ❌ Process creation overhead (spawn new Python interpreter per script)

**Mitigation:**
- Code sharing: Not needed (scripts are simple API wrappers)
- Argument passing: CLI args sufficient (prompts, file paths)
- Stdout/stderr: Structured logging in orchestrator captures context
- Process overhead: Acceptable for I/O-bound operations (network API calls dominate time)

### Anti-Patterns to Avoid

**❌ DON'T import scripts as modules:**
```python
# ❌ WRONG: Importing script breaks brownfield pattern
from scripts import generate_asset
generate_asset.main(["--prompt", prompt, "--output", output])
```

**❌ DON'T add orchestrator dependencies to scripts:**
```python
# ❌ WRONG: Script imports orchestrator code
from app.database import AsyncSessionLocal  # Scripts must be stateless
```

**❌ DON'T put business logic in scripts:**
```python
# ❌ WRONG: Script reads files and combines prompts
with open("atmosphere.txt") as f:
    atmosphere = f.read()
combined = f"{atmosphere}\n\n{prompt}"  # Orchestrator's job
```

### Pattern Verification

**Enforcement:**
- Scripts directory (`scripts/`) is immutable (no modifications in Epic 3+)
- Code reviews verify scripts not imported as modules
- Integration tests verify subprocess invocation pattern
- Orchestrator owns all file reading, prompt combination, state management

**Red Flags:**
- Script imports from `app/` package → Violation
- Script reads Notion data → Violation
- Script reads filesystem to combine prompts → Violation
- Orchestrator imports from `scripts/` → Violation

### Alternatives Considered

**Alternative 1: Rewrite Scripts as Python Modules (REJECTED)**
- Pro: Can share code between orchestrator and scripts
- Con: Rewrites 1,599 LOC of working code
- Con: High regression risk
- **Rejected:** Violates brownfield constraint, unnecessary risk

**Alternative 2: Shared Library for Common Code (REJECTED)**
- Pro: Reduces duplication
- Con: Couples orchestrator and scripts
- Con: Scripts lose standalone capability
- **Rejected:** Pattern works well with clear separation

**Alternative 3: RPC/API Instead of CLI (REJECTED)**
- Pro: Structured data passing
- Con: Requires script modifications (HTTP server)
- Con: More complex than subprocess
- **Rejected:** Over-engineering, subprocess sufficient

### Verification

**Test Cases:**
- Story 3.3: Integration tests verify subprocess invocation
- Story 3.9: End-to-end tests verify full pipeline
- Scripts unchanged: `git diff scripts/` shows no changes in Epic 3

**Production Validation:**
- Scripts run successfully via subprocess
- Stdout/stderr captured correctly
- Exit codes handled properly (0 = success, 1 = failure)

### Related ADRs

- [ADR-002](#adr-002-filesystem-asset-storage) - Scripts operate on filesystem
- [ADR-004](#adr-004-async-execution-throughout) - Orchestrator uses async subprocess wrapper

### References

- CLAUDE.md: "Smart Agent + Dumb Scripts" pattern explanation
- Epic 3 Retrospective: Brownfield integration success
- Story 3.1: CLI wrapper implements pattern

---

## Appendix: Decision Summary Table

| ADR | Title | Status | Epic | Key Trade-off |
|-----|-------|--------|------|--------------|
| 001 | Short Transaction Pattern | ✅ Accepted | 3 | Scalability vs. Simplicity |
| 002 | Filesystem Asset Storage | ✅ Accepted | 3 | Performance vs. Consistency |
| 003 | Service/Worker Separation | ✅ Accepted | 3 | Testability vs. File Count |
| 004 | Async Execution Throughout | ✅ Accepted | 3 | Concurrency vs. Complexity |
| 005 | "Smart Agent + Dumb Scripts" | ✅ Accepted | 3 | Brownfield Preservation vs. Optimization |

---

## Change Log

- **2026-01-16:** Initial ADR document created from Epic 3 retrospective
  - ADR-001 through ADR-005 documented
  - Template established for future ADRs
  - Cross-references added between related ADRs

---

## Future ADRs

Epic 4 and beyond will add:
- ADR-006: Queue Fairness Strategy (round-robin vs. weighted)
- ADR-007: Retry Backoff Algorithm (exponential with jitter)
- ADR-008: Configuration Management (YAML vs. database)
- ADR-009: Monitoring & Observability Strategy
- ADR-010: YouTube Quota Allocation Strategy

---

## References

- **Epic 3 Retrospective:** `_bmad-output/implementation-artifacts/epic-3-retrospective-2026-01-16.md`
- **Architecture Document:** `_bmad-output/planning-artifacts/architecture.md`
- **Project Context:** `_bmad-output/project-context.md`
- **CLAUDE.md:** Project instructions and patterns

---

*This document is a living record of architectural decisions. Update after each epic with new ADRs and lessons learned.*
