# Story 5.3: Asset Review Interface

Status: in-progress

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

---

## Story

As a content creator,
I want to view and approve generated assets in Notion,
So that I can verify image quality before video generation (FR5).

## Acceptance Criteria

### AC1: View Assets at "Assets Ready" Status
```gherkin
Given a task is in "Assets Ready" status
When I open the Notion page
Then I can see all 22 generated asset images (gallery or grid view)
And asset URLs are populated in the Assets property
```

### AC2: Approve Assets
```gherkin
Given I review the assets and they look good
When I change status to "Assets Approved"
Then the task resumes and composite creation begins
```

### AC3: Reject Assets with Feedback
```gherkin
Given I review the assets and find issues
When I change status to "Asset Error" or add notes
Then the task is flagged for regeneration
And Error Log is updated with my feedback
```

## Tasks / Subtasks

- [x] Task 1: Notion Asset Table Schema Definition (AC: #1)
  - [x] Subtask 1.1: Define Asset table schema in Notion workspace
  - [x] Subtask 1.2: Create relation property linking Tasks → Assets
  - [x] Subtask 1.3: Test relation property creates bidirectional link

- [x] Task 2: Asset URL Population Service (AC: #1) **PARTIAL - File upload needs implementation**
  - [x] Subtask 2.1: Implement NotionAssetService.populate_assets() method
  - [x] Subtask 2.2: Create Asset entries after generation (character, environment, prop types)
  - [x] Subtask 2.3: Link assets to task via relation property
  - [ ] Subtask 2.4: Support both Notion and R2 storage strategies **BLOCKED - Needs file upload implementation**

- [x] Task 3: Asset Generation Integration (AC: #1)
  - [x] Subtask 3.1: Update asset generation step to call populate_assets()
  - [x] Subtask 3.2: Set task status to ASSETS_READY after population
  - [x] Subtask 3.3: Set review_started_at timestamp (inherited from Story 5.2)
  - [x] Subtask 3.4: Test with 22 assets (6-8 characters, 8-10 environments, 4-6 props)

- [x] Task 4: Approval Flow Implementation (AC: #2) **MOVED FROM STORY 5.2**
  - [x] Subtask 4.1: Implement webhook handler for "Assets Approved" status detection
  - [x] Subtask 4.2: Task re-queued as QUEUED status on approval
  - [x] Subtask 4.3: Pipeline resumes from composite generation
  - [x] Subtask 4.4: review_completed_at timestamp set on approval

- [x] Task 5: Rejection Flow Implementation (AC: #3) **MOVED FROM STORY 5.2**
  - [x] Subtask 5.1: Implement webhook handler for "Asset Error" status detection
  - [x] Subtask 5.2: Error log extraction from Notion Error Log property
  - [x] Subtask 5.3: Rejection reason appended to task.error_log
  - [x] Subtask 5.4: Manual retry path (Asset Error → Queued)

- [ ] Task 6: End-to-End Testing (AC: #1, #2, #3) **PARTIAL - Unit tests only**
  - [ ] Subtask 6.1: Test complete approval flow (generate → ready → approve → resume) **NEEDS INTEGRATION TEST**
  - [ ] Subtask 6.2: Test complete rejection flow (generate → ready → reject → error state) **NEEDS INTEGRATION TEST**
  - [ ] Subtask 6.3: Test 30-second approval workflow (UX requirement) **NEEDS MANUAL TEST**
  - [ ] Subtask 6.4: Test with both Notion and R2 storage strategies **BLOCKED - File upload needed**

## Review Follow-ups (AI Code Review)

- [ ] [AI-Review][HIGH] Implement Notion file upload - Asset entries created but File URL property not populated [notion_asset_service.py:229-245]
- [ ] [AI-Review][HIGH] Add create_page() method to NotionClient to centralize Notion page creation [clients/notion.py]
- [ ] [AI-Review][MEDIUM] Move hardcoded database IDs to channel configuration [notion_asset_service.py:60-61]
- [ ] [AI-Review][MEDIUM] Add integration tests for complete approval/rejection flows [tests/test_services/]
- [ ] [AI-Review][LOW] Add correlation IDs to logging for distributed tracing [notion_asset_service.py]

## Dev Notes

### Epic 5 Context: Review Gates & Quality Control

**Epic Business Value:**
- **Cost Control:** Review before expensive video generation ($5-10 per video) prevents wasted API spend
- **Quality Assurance:** Human verification ensures content meets standards
- **YouTube Compliance:** Human review evidence required for YouTube Partner Program (July 2025 policy)
- **User Control:** 95% automation with 5% strategic human intervention

**Review Gates Strategy (from UX):**
- Review at expensive steps only (video generation is most critical)
- 30-second approval flow from card click → view → approve
- "Card stuck = problem, moving = success" monitoring principle
- Auto-proceed through low-cost steps when review optional

---

## 🔥 ULTIMATE DEVELOPER CONTEXT ENGINE 🔥

**CRITICAL MISSION:** This story creates the foundation for ALL future review interfaces (video, audio). The implementation patterns established here MUST be reusable and correct.

**WHAT MAKES THIS STORY CRITICAL:**
1. **First Review Interface:** Sets patterns for Stories 5.4 (video) and 5.5 (audio)
2. **Notion Integration Foundation:** First use of Notion relations for file attachments
3. **Storage Strategy Abstraction:** Must work with both Notion and R2 storage
4. **Review Gate Activation:** First time review gates (Story 5.2) are actually used
5. **UX Validation:** 30-second approval flow requirement must be achieved

---

### Story 5.3 Technical Context

**What This Story Adds:**
Implements the **FIRST** user-visible review interface that leverages the review gate enforcement from Story 5.2. This is the foundation for all future review workflows.

**Current State (After Story 5.2):**
- ✅ Pipeline halts at ASSETS_READY status (Story 5.2 complete)
- ✅ Notion webhook detects "Assets Approved" → re-queues task (Story 5.2 complete)
- ✅ Rejection handler detects "Asset Error" → logs reason (Story 5.2 complete)
- ✅ Asset generation creates 22 PNG files in filesystem (Story 3.3 complete)
- ❌ Assets NOT linked to Notion task (no Asset table exists)
- ❌ No way for user to VIEW assets in Notion
- ❌ Manual status change in Notion doesn't show asset context

**Target State (After Story 5.3):**
- ✅ Notion Asset table exists with proper schema
- ✅ Tasks → Assets relation property configured
- ✅ Asset generation automatically populates Asset entries
- ✅ User sees all 22 assets when opening "Assets Ready" task
- ✅ Approval/rejection workflows fully functional with asset context
- ✅ 30-second approval flow achievable (UX requirement)

---

### 📊 COMPREHENSIVE ARTIFACT ANALYSIS

This section contains EXHAUSTIVE context from ALL planning artifacts to prevent implementation mistakes.

#### **From Epic 5 (Epics.md)**

**Story 5.3 Complete Requirements:**

**User Story:**
As a content creator, I want to view and approve generated assets in Notion, so that I can verify image quality before video generation (FR5).

**Technical Requirements from Epics File:**

1. **Notion Schema Requirements:**
   - **Assets Table Schema** (Must Create in Notion):
     ```
     Assets Table:
     - Asset Type (Select): character | environment | prop | composite
     - File URL/Attachment (URL or Files): Link to asset location
     - Task (Relation): Back-reference to parent task
     - Generated Date (Date): Timestamp of asset creation
     - Status (Select): pending | generated | approved | rejected
     - Notes (Rich Text): Optional reviewer feedback
     ```
   - **Tasks Table Extension** (Add to existing Notion database):
     ```
     Tasks Table:
     - Assets (Relation → Assets table): Many-to-many link to asset files
     ```

2. **Task Status Transitions:**
   ```python
   # Already enforced by Story 5.1 state machine
   generating_assets → assets_ready (automatic when all 22 assets generated)
   assets_ready → assets_approved (manual user approval)
   assets_ready → asset_error (manual user rejection)
   assets_approved → generating_composites (automatic resume)
   ```

3. **Asset Storage & URL Population:**
   - **Storage Strategy (FR12):**
     - **Notion Strategy (Default):** Assets stored as Notion file attachments
     - **R2 Strategy (Optional):** Assets uploaded to Cloudflare R2, URLs stored in Notion

   - **Asset Generation Workflow (Epic 3 - Story 3.3):**
     ```python
     # 22 assets generated:
     # - 6-8 character images (transparent PNG)
     # - 8-10 environment images (1920x1080 or ultra-wide)
     # - 4-6 prop images
     # Output: {workspace}/channels/{channel_id}/projects/{task_id}/assets/{type}/{name}.png
     ```

   - **URL Population Logic (FR48):**
     ```
     1. Asset generated → File saved to filesystem
     2. If storage_strategy="notion": Upload to Notion via Files API
     3. If storage_strategy="r2": Upload to R2 bucket, get public URL
     4. Create Asset table entry with file URL/attachment
     5. Link Asset to Task via relation property
     6. Update task status to assets_ready
     ```

4. **Database Schema (PostgreSQL - No Changes Required):**
   - **Current Task Model:** Already has all required fields
     - `status` field supports `assets_ready` and `assets_approved` states
     - `error_log` field available for rejection feedback
     - State machine validation enforces transitions
   - **No Asset Model Required:** Assets table lives in Notion only (not PostgreSQL)
     - Avoids duplication between Notion and database
     - Notion is single source of truth for asset metadata
     - Database only tracks task status progression

5. **Worker Orchestration Logic:**
   ```python
   # Epic 3 - Story 3.3: Asset Generation completes
   async def handle_assets_complete(task_id: UUID):
       # All 22 assets generated successfully
       async with async_session_factory() as session:
           task = await session.get(Task, task_id)
           task.status = TaskStatus.ASSETS_READY  # Trigger review gate
           task.review_started_at = utcnow()  # Start review timer
           await session.commit()

       # Sync status to Notion
       await notion_client.update_page_status(
           page_id=task.notion_page_id,
           status="Assets Ready"
       )
       # Worker STOPS here - waits for user approval (Story 5.2)

   # Story 5.2: Review Gate Enforcement (ALREADY IMPLEMENTED)
   async def check_review_gate(task: Task) -> bool:
       """Check if task can proceed past review gate."""
       if task.status == TaskStatus.ASSETS_READY:
           return False  # Block progression - needs approval
       if task.status == TaskStatus.ASSETS_APPROVED:
           return True   # Approved - resume to composites
       return False

   # User approves in Notion → Webhook triggers resume (ALREADY IMPLEMENTED)
   async def handle_status_change(notion_page_id: str, new_status: str):
       if new_status == "Assets Approved":
           async with async_session_factory() as session:
               task = await session.get(Task, notion_page_id)
               task.status = TaskStatus.ASSETS_APPROVED
               task.review_completed_at = utcnow()  # End review timer
               await session.commit()

           # Re-queue task for composite generation
           await enqueue_task(task.id, step="composites")
   ```

6. **Notion API Integration:**
   ```python
   class NotionClient:
       async def update_page_status(self, page_id: str, status: str):
           """Update task status in Notion (Story 5.6)."""

       async def populate_asset_urls(self, page_id: str, assets: list[dict]):
           """Link generated assets to task via relation property."""
           # Creates Asset table entries
           # Links to task via relation

       async def upload_file_attachment(self, file_path: str) -> str:
           """Upload file to Notion, return attachment URL."""
           # Used when storage_strategy="notion"
   ```
   **Rate Limiting:** Respect 3 req/sec limit (Story 2.2: AsyncLimiter)

7. **Error Handling:**
   ```python
   # Asset Rejection Flow
   async def handle_asset_rejection(task_id: UUID, feedback: str):
       async with async_session_factory() as session:
           task = await session.get(Task, task_id)
           task.status = TaskStatus.ASSET_ERROR

           # Append feedback to error log
           error_entry = f"[{utcnow().isoformat()}] Asset Review: {feedback}"
           task.error_log = f"{task.error_log}\n{error_entry}" if task.error_log else error_entry

           await session.commit()

       # Task must be re-queued manually by user changing status back to "Queued"
   ```

**Dependencies & Related Stories:**

**Upstream Dependencies (Must Complete First):**
1. ✅ **Story 2.2:** Notion API Client with Rate Limiting (COMPLETE)
2. ✅ **Story 3.3:** Asset Generation Step (Gemini) (COMPLETE)
3. ✅ **Story 5.1:** 26-Status Workflow State Machine (COMPLETE)
4. ✅ **Story 5.2:** Review Gate Enforcement (COMPLETE)

**Downstream Dependencies (Blocked by This Story):**
1. 🚧 **Story 5.4:** Video Review Interface (same pattern as 5.3)
2. 🚧 **Story 5.5:** Audio Review Interface (same pattern as 5.3)
3. 🚧 **Story 5.8:** Bulk Approve/Reject Operations (requires individual review interfaces)

**Parallel Work (Can Implement Simultaneously):**
- **Story 5.6:** Real-time Status Updates (partially done, needs testing)
- **Story 5.7:** Progress Visibility Dashboard (Notion schema work)

**PRD References:**
- **FR5 (Lines 1056-1062):** Asset Review Interface specification
- **User Journey 1 (Line 370):** Francis reviews assets - *"He clicks into 'Stoicism and Modern Anxiety' - status is 'Assets Ready'. The system has generated 22 images... He reviews them quickly... changes status to 'Approved - Assets'"*

---

#### **From Architecture (architecture.md)**

**CRITICAL ARCHITECTURAL CONSTRAINTS:**

1. **Use Depends(get_session) for FastAPI routes** (not direct session factory)
2. **Follow 27-status workflow state machine** (Task.VALID_TRANSITIONS from Story 5.1)
3. **Create immutable AuditLog entries** for all review actions (compliance requirement)
4. **Use structured logging (structlog)** with correlation IDs
5. **Return resources directly** (no wrapper objects)
6. **Use HTTPException** for all API errors
7. **Follow snake_case naming** throughout (tables, columns, JSON fields)
8. **Place review routes in `app/routes/reviews.py`** (if API endpoints needed)
9. **Place review business logic in `app/services/review_service.py`** (new service)
10. **Support both API and Notion webhook review flows**

**Short Transaction Pattern (CRITICAL):**
```python
# ✅ CORRECT - Short transactions
@router.post("/{task_id}/approve")
async def approve_review(
    task_id: UUID,
    session: AsyncSession = Depends(get_session)
):
    # Session auto-managed by FastAPI
    task = await session.get(Task, task_id)
    task.status = TaskStatus.ASSETS_APPROVED
    # FastAPI commits on success, rolls back on exception
    return task

# ❌ WRONG - Holding transaction during work
async with session.begin():
    task = await session.get(Task, task_id)
    # DO EXPENSIVE WORK - BLOCKS DB!
    task.status = "completed"
    await session.commit()
```

**Notion Integration Pattern:**
- **Location:** Architecture doc Section 3.2 (Notion API client)
- **Pattern:** Short transactions, rate limiting, bidirectional sync
- **Rate Limit:** 3 requests per second (AsyncLimiter enforcement mandatory)

**Missing Components (Architecture Specifies, Not Yet Implemented):**
1. **Review Model** - Architecture mentions, not in current models.py
2. **Video Model** - Architecture mentions, not in current models.py
3. **AuditLog Model** - Architecture REQUIRES, not in current models.py (COMPLIANCE CRITICAL)
4. **VideoCost Model** - Architecture mentions, not in current models.py

**Recommendation for Developer:**
**Option A (Immediate - RECOMMENDED):** Implement review endpoints operating on Task model only
- Use task_id instead of video_id
- Store review metadata in Task.step_completion_metadata (JSON field)
- Create AuditLog table separately in future story

**Option B (Complete):** Implement full architecture
- Create Review, Video, VideoCost, AuditLog models
- Create Alembic migration
- Implement review endpoints with full model relationships

**For Story 5.3, use Option A** - Focus on Notion workflow, defer full API layer.

---

#### **From UX Design (ux-design-specification.md)**

**MANDATORY UX REQUIREMENTS:**

1. **Review Is Fast:** 30-second flow from card click → view assets → approve → next stage
   - **Desired Emotion:** "Efficient quality control, not a bottleneck"
   - **Visual:** Modal gallery with clear approve/reject options
   - **Target Experience:** Click "Assets Ready" card → See 22 images → Approve → Card moves to "Generating Video"

2. **Asset Display Requirements:**
   - **Display Structure:** Gallery/Grid View - all 22 assets visible simultaneously
   - **Asset Labels:** Type identification (character, environment, prop)
   - **Quality Assessment:** Individual image inspection capability
   - **Quick Actions:** Approve all, flag specific assets for regeneration

3. **Approval/Rejection Interaction Patterns:**
   - **Approval Action:** User changes status to "Assets Approved"
   - **Effect:** Task resumes and composite creation begins
   - **Rejection Action:** User changes status to "Asset Error" or adds notes
   - **Effect:** Task flagged for regeneration, Error Log updated with feedback

4. **Status Display Requirements:**
   - **Color-coded columns:** Green for normal, red for error
   - **Time-in-status prominently displayed:** Updates automatically every minute
   - **Glanceable Health:** Answer "is everything OK?" in 2-second glance at board

5. **Navigation Patterns:**
   - **Board View:** Wide Kanban board with horizontal scroll
   - **Click card → Modal with quick actions + details**
   - **Asset review:** Modal gallery overlay OR dedicated page

6. **Performance Targets:**
   - 30 seconds per review session
   - Support 100 videos/week = 300+ approval points
   - Bulk approve 10 tasks simultaneously (future Story 5.8)
   - Zero friction between viewing and approving

7. **Emotional Design Goals:**
   - **"Review Is Fast"** - 30-second flow feels efficient
   - **"Efficient quality control, not a bottleneck"** - Trust but verify model
   - **Spaciousness** - Not drowning in pipeline management

**Key Files Referenced:**
- `/Users/francisaraujo/repos/ai-video-generator/_bmad-output/planning-artifacts/ux-design-specification.md` (primary source)
- `/Users/francisaraujo/repos/ai-video-generator/_bmad-output/planning-artifacts/prd.md` (FR5-FR7 requirements)

---

#### **From Story 5.2 (5-2-review-gate-enforcement.md)**

**CRITICAL PATTERNS TO FOLLOW FROM PREVIOUS STORY:**

1. **Set-Based Membership Testing (O(1) Performance):**
   ```python
   # Good: O(1) lookup
   REVIEW_GATES = {TaskStatus.ASSETS_READY, TaskStatus.VIDEO_READY, ...}
   return status in REVIEW_GATES

   # Bad: O(n) iteration
   review_gates = [TaskStatus.ASSETS_READY, TaskStatus.VIDEO_READY, ...]
   return status in review_gates
   ```

2. **Tuple-Based Transition Detection:**
   ```python
   # Good: Explicit, clear intent
   approval_transitions = {
       (TaskStatus.ASSETS_READY, TaskStatus.ASSETS_APPROVED),
       (TaskStatus.VIDEO_READY, TaskStatus.VIDEO_APPROVED),
   }
   return (old_status, new_status) in approval_transitions
   ```

3. **Property-Based Computed Fields:**
   ```python
   # Good: Computed property (no data inconsistency risk)
   @property
   def review_duration_seconds(self) -> int | None:
       if self.review_started_at and self.review_completed_at:
           delta = self.review_completed_at - self.review_started_at
           return int(delta.total_seconds())
       return None
   ```

4. **Timezone-Aware Timestamps:**
   ```python
   # Good: Explicit UTC timezone
   task.review_started_at = datetime.now(timezone.utc)

   # Bad: Naive datetime (ambiguous timezone)
   task.review_started_at = datetime.now()
   ```

5. **Append-Only Error Logs:**
   ```python
   # Good: Append with timestamp
   current_log = task.error_log or ""
   timestamp = datetime.now(timezone.utc).isoformat()
   new_entry = f"[{timestamp}] Review Rejection: {reason}"
   task.error_log = f"{current_log}\n{new_entry}".strip()

   # Bad: Overwrite (loses history)
   task.error_log = f"Review Rejection: {reason}"
   ```

6. **Structured Logging with Context:**
   ```python
   # Good: Structured fields for filtering/aggregation
   log.info(
       "task_requeued_after_approval",
       correlation_id=correlation_id,
       task_id=str(task.id),
       approval_status=old_status.value,
       review_duration_seconds=review_duration,
   )
   ```

7. **Short Transaction Pattern:**
   ```python
   # Good: Open connection, update, close immediately
   async with async_session_factory() as db, db.begin():
       task = await db.get(Task, self.task_id)
       task.status = status
       task.review_started_at = datetime.now(timezone.utc)
   # Connection closed here
   ```

**What's Already Built (Story 5.2 Complete):**
1. **Review Gate Detection:** `is_review_gate()` function exists and tested
2. **Approval/Rejection Handlers:** `handle_approval_transition()` and `handle_rejection_transition()` exist
3. **Timestamp Tracking:** `review_started_at` and `review_completed_at` fields exist
4. **State Machine Validation:** Story 5.1 enforces valid transitions
5. **Notion Sync Polling:** 60-second polling loop exists
6. **Re-Enqueue Pattern:** Approval sets status to QUEUED, workers auto-claim

**Testing Strategy to Adopt (From Story 5.2):**
1. **Unit Tests:** Use parametrized tests for detection functions
2. **Integration Tests:** Use real async session for handler functions
3. **Mock Strategy:** Mock pipeline dependencies, use real DB for Notion sync
4. **Coverage Target:** Aim for 90%+ coverage on new code

**State Machine Integration (MUST RESPECT):**
- **Valid Transitions** (already enforced by Story 5.1):
  - `ASSETS_READY → ASSETS_APPROVED` ✅
  - `ASSETS_READY → ASSET_ERROR` ✅
  - `ASSET_ERROR → QUEUED` (manual retry) ✅
- **Invalid Transitions** (will raise `InvalidStateTransitionError`):
  - `ASSETS_READY → VIDEO_READY` ❌ (cannot skip approval)
  - `ASSETS_READY → PUBLISHED` ❌ (cannot skip entire pipeline)

**Notion Integration Points (Already Exists):**
1. **Status Mapping:** Already exists in `app/constants.py`
   - "Assets Ready" → `TaskStatus.ASSETS_READY`
   - "Assets Approved" → `TaskStatus.ASSETS_APPROVED`
   - "Asset Error" → `TaskStatus.ASSET_ERROR`
2. **Polling Frequency:** 60 seconds (sufficient for human-in-the-loop)
3. **Rate Limiting:** Already implemented (AsyncLimiter, 3 req/sec)

**Critical Don'ts (From Story 5.2 Review):**
❌ **Don't** create new timestamp fields (use existing `review_started_at` / `review_completed_at`)
❌ **Don't** overwrite error logs (use append-only pattern)
❌ **Don't** use naive datetimes (always use `datetime.now(timezone.utc)`)
❌ **Don't** hold database connections during long operations (short transaction pattern)
❌ **Don't** bypass state machine validation (let Story 5.1 enforce transitions)
❌ **Don't** skip status mapping in `app/constants.py` (required for Notion sync)

**Critical Do's (From Story 5.2):**
✅ **Do** use set-based membership testing for O(1) performance
✅ **Do** use tuple-based transition detection for clarity
✅ **Do** use property-based computed fields (avoid stored duration)
✅ **Do** use structured logging with correlation IDs
✅ **Do** use append-only error logs with timestamps
✅ **Do** leverage existing `step_completion_metadata` for resume logic
✅ **Do** test with both mocks (unit) and real DB (integration)

**Files to Reference for Implementation:**
- **`app/services/pipeline_orchestrator.py`** (lines 76-116, 378-394, 722-729): Review gate detection, halt logic
- **`app/services/notion_sync.py`** (lines 39-76, 79-115, 307-356, 358-421): Approval/rejection detection, handlers
- **`app/models.py`** (lines 578-588, 666-688): Timestamp fields, computed property pattern
- **`app/constants.py`** (lines 39-42, 86-89): Notion status mapping pattern
- **`tests/test_services/test_pipeline_orchestrator.py`** (lines 694-730, 916-1023): Mock-based unit tests
- **`tests/test_services/test_notion_sync.py`** (lines 863-1354): Integration tests with real DB

---

#### **From Project Context (project-context.md)**

**MANDATORY IMPLEMENTATION RULES:**

1. **CLI Scripts Architecture:**
   - Scripts in `scripts/` are stateless CLI tools invoked via subprocess
   - Orchestration layer (`app/`) invokes scripts via `run_cli_script()`, never import as modules
   - Scripts communicate via command-line arguments, stdout/stderr, exit codes
   - **MUST use subprocess wrapper:** `app/utils/cli_wrapper.py:run_cli_script()`
   - **MUST use filesystem helpers:** `app/utils/filesystem.py:get_asset_dir()`, etc.

2. **Integration Utilities (MANDATORY):**
   ```python
   # CLI Script Wrapper (REQUIRED for all subprocess calls)
   from app.utils.cli_wrapper import run_cli_script, CLIScriptError

   try:
       result = await run_cli_script(
           "generate_asset.py",
           ["--prompt", full_prompt, "--output", str(output_path)],
           timeout=60
       )
       log.info("Asset generated", stdout=result.stdout, path=output_path)
   except CLIScriptError as e:
       log.error("Asset generation failed", script=e.script, stderr=e.stderr)
       raise
   ```

   ```python
   # Filesystem Helpers (REQUIRED for all path construction)
   from app.utils.filesystem import get_asset_dir, get_character_dir

   # ✅ CORRECT
   asset_dir = get_asset_dir(channel_id="poke1", project_id="vid_123")
   char_dir = get_character_dir(channel_id="poke1", project_id="vid_123")
   output_path = char_dir / "bulbasaur.png"

   # ❌ WRONG: Hard-coded paths
   output_path = f"/workspace/poke1/vid_123/assets/bulbasaur.png"
   ```

3. **Notion API Integration (3 req/sec Rate Limiting):**
   ```python
   from aiolimiter import AsyncLimiter

   class NotionClient:
       def __init__(self, auth_token: str):
           self.rate_limiter = AsyncLimiter(max_rate=3, time_period=1)  # CRITICAL

       async def update_task_status(self, page_id: str, status: str):
           async with self.rate_limiter:  # ALWAYS use rate limiter
               response = await self.client.patch(...)
   ```

4. **Project Structure & Organization (MANDATORY):**
   ```
   app/
   ├── routes/          # FastAPI endpoint handlers ONLY
   ├── services/        # Business logic and orchestration
   ├── clients/         # Third-party API wrappers
   └── utils/           # Pure helper functions
   ```

5. **Async/Await Patterns (CRITICAL):**
   - ALL database operations MUST use `async/await`
   - ALL HTTP requests in async code MUST use `httpx` async client (NOT `requests`)
   - FastAPI route handlers MUST be `async def` when accessing database
   - Use `asyncio.create_subprocess_exec()` for subprocess calls in async context

6. **Type Hints (REQUIRED):**
   - ALL functions MUST have type hints for parameters and return values
   - Use Python 3.10+ union syntax: `str | None` (NOT `Optional[str]`)
   - Import types explicitly: `from uuid import UUID`, `from datetime import datetime`

7. **Error Handling Patterns:**
   - Custom exceptions MUST extend `HTTPException` in FastAPI routes
   - Include structured error details
   - Log exceptions with `exc_info=True` for full stack traces
   - NEVER silently catch exceptions without logging or re-raising

8. **Database Session Management:**
   - **FastAPI routes:** Use dependency injection: `db: AsyncSession = Depends(get_db)`
   - **Workers:** Use context managers: `async with AsyncSessionLocal() as db:`
   - **Transactions:** Keep short (claim → close DB → process → new DB → update)

---

### 🎯 IMPLEMENTATION STRATEGY

**Phase 1: Notion Asset Table Setup (Manual - Do First)**
1. Open Notion workspace
2. Create new database: "Assets"
3. Add properties:
   - Asset Type (Select): character, environment, prop, composite
   - File URL/Attachment (Files or URL)
   - Task (Relation → Tasks database)
   - Generated Date (Date)
   - Status (Select): pending, generated, approved, rejected
   - Notes (Rich Text)
4. Add relation property to Tasks database:
   - Assets (Relation → Assets database, many-to-many)

**Phase 2: NotionAssetService Implementation (Backend)**
1. Create `app/services/notion_asset_service.py`
2. Implement `populate_assets(task_id, asset_files)` method:
   - For each asset file: Create Asset entry in Notion
   - Link to task via relation property
   - Handle both Notion file upload and R2 URL storage
3. Add rate limiting (AsyncLimiter, 3 req/sec)
4. Add structured logging with correlation IDs

**Phase 3: Asset Generation Integration**
1. Modify `app/services/pipeline_orchestrator.py`:
   - After asset generation step completes
   - Call `notion_asset_service.populate_assets()`
   - Set task status to ASSETS_READY
   - Set review_started_at timestamp (already exists from Story 5.2)
2. Test with 22 assets (characters, environments, props)

**Phase 4: Verification (No New Code Needed)**
1. Verify existing webhook handler (Story 5.2) detects "Assets Approved"
2. Verify task re-queued as QUEUED status
3. Verify pipeline resumes from composite generation
4. Verify review_completed_at timestamp set

**Phase 5: Testing & Validation**
1. Unit tests: Asset URL population logic
2. Integration tests: Complete approval flow
3. Integration tests: Complete rejection flow
4. UX test: 30-second approval workflow validation

---

### Library & Framework Requirements

**No New Dependencies Required:**
- ✅ SQLAlchemy 2.0 async (already in use)
- ✅ FastAPI (already in use)
- ✅ Notion API client (already in use, Story 2.2)
- ✅ structlog (already in use)
- ✅ aiolimiter (already in use for rate limiting)

**Existing Components to Extend:**
1. `app/services/pipeline_orchestrator.py` - Add asset population after generation
2. `app/services/notion_sync.py` - Verify approval/rejection detection works (already implemented)
3. `app/clients/notion.py` - Add `populate_assets()` and `upload_file_attachment()` methods

**No Migration Required:** Assets live in Notion only, not PostgreSQL

---

### File Structure Requirements

**Files to Create:**
1. `app/services/notion_asset_service.py` - Asset URL population service
2. `tests/test_services/test_notion_asset_service.py` - Service tests

**Files to Modify:**
1. `app/services/pipeline_orchestrator.py` - Call populate_assets() after generation
2. `app/clients/notion.py` - Add asset-related methods

**Files NOT to Modify:**
- `scripts/*.py` - CLI scripts remain unchanged (brownfield preservation)
- `app/models.py` - No new models (Assets in Notion only)
- `app/services/notion_sync.py` - Approval/rejection logic already complete (Story 5.2)

---

### Testing Requirements

**Unit Tests (Required):**
1. **Asset Population Tests:**
   - Test asset entry creation in Notion
   - Test relation property linking
   - Test file upload (Notion strategy)
   - Test URL storage (R2 strategy)
   - Test rate limiting compliance (3 req/sec)

2. **Integration Tests:**
   - Test complete approval flow (generate → populate → ready → approve → resume)
   - Test complete rejection flow (generate → populate → ready → reject → error)
   - Test with 22 assets (6-8 characters, 8-10 environments, 4-6 props)
   - Test both Notion and R2 storage strategies

3. **UX Validation Tests:**
   - Verify 30-second approval workflow achievable
   - Verify all 22 assets visible in Notion
   - Verify status transitions work correctly

**Test Coverage Targets:**
- Asset population logic: 95%+ coverage
- Notion API integration: 90%+ coverage
- End-to-end workflows: 100% coverage

---

### Previous Story Intelligence

**From Story 5.2 (Review Gate Enforcement):**

**Key Learnings:**
1. **Review Gate Detection:** `is_review_gate()` function exists in `pipeline_orchestrator.py`
2. **Approval Handling:** `handle_approval_transition()` exists in `notion_sync.py`
3. **Rejection Handling:** `handle_rejection_transition()` exists in `notion_sync.py`
4. **Timestamp Tracking:** `review_started_at` and `review_completed_at` fields exist
5. **State Machine:** Story 5.1 validation enforces all transitions

**Code Patterns to Follow:**
- Set-based membership testing (O(1) performance)
- Tuple-based transition detection (clean, explicit)
- Property-based computed fields (no data inconsistency)
- Timezone-aware timestamps (`datetime.now(timezone.utc)`)
- Append-only error logs (audit trail)
- Structured logging (correlation IDs)
- Short transaction pattern (no long-held connections)

**Testing Patterns:**
- Mock-based unit tests for orchestrator
- Integration tests with real DB for sync
- Parametrized tests for comprehensive coverage

**Files Modified in Story 5.2 (Reference These):**
- `app/services/pipeline_orchestrator.py` (lines 76-116, 378-394, 722-729)
- `app/services/notion_sync.py` (lines 39-76, 79-115, 307-356, 358-421)
- `app/models.py` (lines 578-588, 666-688)
- `app/constants.py` (lines 39-42, 86-89)

---

### Git Intelligence Summary

**Recent Work Patterns (Last 5 Commits):**
1. **Story 5.2 Just Completed** (commit d03a110): Review gate enforcement complete
2. **Story 5.1 Code Review** (commit 9925790): 27-status state machine fixes applied
3. **Epic 4 Complete:** Worker orchestration, parallel execution, rate limiting all working

**Established Patterns to Follow:**
1. Alembic migrations for schema changes
2. SQLAlchemy async patterns (AsyncSession, async with)
3. Structured logging with correlation IDs (structlog)
4. Comprehensive unit tests (pytest, pytest-asyncio)
5. Code review after initial implementation

---

### Critical Success Factors

✅ **MUST achieve:**
1. All 22 assets visible in Notion when task reaches ASSETS_READY
2. Approval in Notion resumes pipeline to composite generation
3. Rejection in Notion moves to ASSET_ERROR with error log
4. 30-second approval workflow achievable (UX requirement)
5. Both Notion and R2 storage strategies work correctly
6. Rate limiting compliant (3 req/sec max)
7. No breaking changes to existing pipeline

⚠️ **MUST avoid:**
1. Creating Asset model in PostgreSQL (Notion is source of truth)
2. Bypassing rate limiting (Notion API blocks over 3 req/sec)
3. Breaking existing review gate logic (Story 5.2)
4. Long-held database connections (short transaction pattern)
5. Hard-coded paths (use filesystem helpers)
6. Direct subprocess calls (use cli_wrapper)

---

### Project Structure Notes

**Alignment with Unified Project Structure:**
- Asset population logic in `app/services/notion_asset_service.py` (new service)
- Pipeline integration in `app/services/pipeline_orchestrator.py` (extends existing)
- Notion API methods in `app/clients/notion.py` (extends existing)
- Tests in `tests/test_services/test_notion_asset_service.py` (new test file)

**No Conflicts:**
- Extends existing pipeline without breaking changes
- Uses existing review gate infrastructure (Story 5.2)
- Follows established async patterns from Epic 4
- Compatible with brownfield CLI scripts (no changes to scripts/)

---

### References

**Source Documents:**
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 5 Story 5.3] - Complete requirements
- [Source: _bmad-output/planning-artifacts/prd.md#FR5] - Asset Review Interface specification
- [Source: _bmad-output/planning-artifacts/architecture.md#Notion Integration] - Integration patterns
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Review Gates] - UX requirements
- [Source: _bmad-output/implementation-artifacts/5-2-review-gate-enforcement.md] - Previous story patterns
- [Source: _bmad-output/project-context.md] - Critical implementation rules

**Implementation Files:**
- [Source: app/services/pipeline_orchestrator.py] - Pipeline orchestration (extend)
- [Source: app/services/notion_sync.py] - Notion sync service (verify works)
- [Source: app/clients/notion.py] - Notion API client (extend)
- [Source: app/utils/cli_wrapper.py] - CLI script wrapper (use)
- [Source: app/utils/filesystem.py] - Filesystem helpers (use)

---

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

- Asset population logic: `notion_asset_service.py:74-174`
- Pipeline integration: `pipeline_orchestrator.py:376-397, 719-775`
- Webhook handlers: `webhook_handler.py:133-307`

### Completion Notes List

**Implementation Highlights:**
1. ✅ Created NotionAssetService with populate_assets() method
2. ✅ Integrated asset population into pipeline after ASSET_GENERATION step
3. ✅ Implemented approval/rejection webhook handlers (moved from Story 5.2)
4. ✅ Added review gate enforcement with re-queueing logic
5. ⚠️ File upload implementation deferred (TODO placeholders for both strategies)
6. ⚠️ Integration tests pending (unit tests complete)

**Architecture Decisions:**
- Assets stored in Notion only (not PostgreSQL) - reduces duplication
- Rate limiting enforced via AsyncLimiter wrapper around all Notion API calls
- Short transaction pattern maintained (claim → close → work → reopen → update)
- Graceful degradation: Asset population failure logs error but doesn't stop pipeline

**Story Boundary Note:**
Tasks 4 & 5 (webhook handlers) were originally scoped for Story 5.2 but implemented in Story 5.3. Story 5.2 was marked "done" prematurely without webhook implementation. This created technical debt that was resolved by implementing the handlers in this story.

### File List

**Created Files:**
- `app/services/notion_asset_service.py` (261 lines) - Asset URL population service with rate limiting
- `tests/test_services/test_notion_asset_service.py` (205 lines) - Unit tests for asset service (4 tests, all passing)

**Modified Files:**
- `app/services/pipeline_orchestrator.py` (+61 lines)
  - Lines 376-397: Call populate_assets() after ASSET_GENERATION step completes
  - Lines 512-550: Store asset_files in step completion metadata for Notion population
  - Lines 719-775: New _populate_assets_in_notion() method with error handling

- `app/services/webhook_handler.py` (+268 lines)
  - Lines 36-48: Added approval/rejection status mapping constants
  - Lines 133-227: New _handle_approval_status_change() - re-queue tasks on approval
  - Lines 229-307: New _handle_rejection_status_change() - extract feedback and mark error
  - Lines 410-472: Updated process_notion_webhook_event() to route approval/rejection events

**Configuration Files:**
- `.claude/settings.local.json` (modified) - Local development settings
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) - Story status updated

### Change Log

**2026-01-17 - Code Review Fixes:**
1. Updated task checkboxes to reflect actual implementation status
2. Added AI Review Follow-ups section for deferred work items
3. Documented story boundary issue (Tasks 4 & 5 from Story 5.2)
4. Completed Dev Agent Record with comprehensive file list
5. Added this change log for future reference

**Original Implementation:**
- Created NotionAssetService for populating asset entries in Notion
- Integrated asset population into pipeline orchestrator
- Implemented webhook handlers for approval/rejection flows (Note: Should have been in Story 5.2)
- Added unit tests with mock-based testing
- Deferred file upload implementation (both Notion and R2 strategies)
