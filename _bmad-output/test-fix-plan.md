# Test Fix Plan - Pre-existing Failures
**Date:** 2026-01-17
**Target:** 2 failing tests in `test_task_service.py`

---

## Failure Summary

### Test 1: `test_enqueue_task_allows_requeue_after_completion`
**Error:** `InvalidStateTransitionError: Invalid transition: published → queued`
**Location:** `tests/test_services/test_task_service.py:198`
**Root Cause:** State machine validator blocks terminal → queued transitions

### Test 2: `test_all_task_statuses_categorized`
**Error:** `AssertionError: Status cancelled not categorized`
**Location:** `tests/test_services/test_task_service.py:573`
**Root Cause:** `TaskStatus.CANCELLED` not in ACTIVE or TERMINAL status sets

---

## Issue 1: Re-queueing Terminal Tasks

### Problem Analysis

**Current Behavior:**
```python
# app/models.py:425
TaskStatus.PUBLISHED: [],  # Terminal state - no transitions allowed
TaskStatus.CANCELLED: [],  # Terminal state - no transitions allowed
```

**Expected Behavior (from test):**
```python
# Test expects: PUBLISHED → QUEUED (for manual retry)
requeued = await enqueue_task(notion_page_id="...", ...)
# Should update existing terminal task to QUEUED status
```

**Service Layer Intent:**
```python
# app/services/task_service.py:237
# Comment: "Re-queue allowed for terminal tasks"
existing_terminal.status = TaskStatus.QUEUED  # ❌ Blocked by validator
```

### Root Cause

The state machine has **two conflicting requirements**:

1. **State Machine Purity** (Story 5.1): Terminal states have no valid transitions
   - `VALID_TRANSITIONS[TaskStatus.PUBLISHED] = []`
   - Prevents accidental status corruption

2. **Manual Retry Feature** (FR requirement): Allow operators to re-queue failed/completed tasks
   - Service layer tries to set `status = QUEUED` directly
   - Validator blocks this as invalid transition

### Solution Options

#### Option A: Add Explicit "Requeue" Transitions (RECOMMENDED)

**Approach:** Extend VALID_TRANSITIONS to allow terminal → QUEUED transitions

**Changes Required:**

1. **Update `app/models.py` VALID_TRANSITIONS:**
```python
# Before (line 425)
TaskStatus.PUBLISHED: [],  # Terminal state - no transitions allowed

# After
TaskStatus.PUBLISHED: [TaskStatus.QUEUED],  # Allow manual re-queue
TaskStatus.CANCELLED: [TaskStatus.QUEUED],  # Allow manual re-queue
TaskStatus.ASSET_ERROR: [TaskStatus.QUEUED],  # Already allows retry
TaskStatus.VIDEO_ERROR: [TaskStatus.QUEUED],  # Already allows retry
TaskStatus.AUDIO_ERROR: [TaskStatus.QUEUED],  # Already allows retry
TaskStatus.UPLOAD_ERROR: [TaskStatus.QUEUED],  # Already allows retry
```

2. **Update docstring to document re-queue pattern:**
```python
"""
27-Status Workflow State Machine.

Terminal State Re-queueing:
    - PUBLISHED can be re-queued for content updates (e.g., re-publish with new audio)
    - ERROR states can be re-queued for manual retry after fixing issues
    - CANCELLED can be re-queued if task is un-cancelled

This allows operators to manually retry tasks without creating new tasks.
"""
```

**Pros:**
- ✅ Maintains state machine integrity (all transitions explicit)
- ✅ Self-documenting (re-queue intent clear in state machine)
- ✅ No special cases or bypass logic
- ✅ Easy to validate and test

**Cons:**
- ⚠️ Slightly looser than "terminal means terminal"
- ⚠️ Could allow accidental re-queues (mitigated by service layer logic)

**Impact:**
- Low risk - only allows QUEUED as next state for terminals
- Aligns with business requirement for manual retries
- Test passes without modification

---

#### Option B: Bypass Validator for Re-queue Operations

**Approach:** Add special handling in validator to allow terminal → queued transitions

**Changes Required:**

1. **Update `app/models.py` validate_status_change:**
```python
@validates("status")
def validate_status_change(self, key: str, value: TaskStatus) -> TaskStatus:
    # Skip validation on initial task creation
    if self.status is None:
        return value

    # Allow terminal → QUEUED transition for manual re-queue
    if self.status in TERMINAL_TASK_STATUSES and value == TaskStatus.QUEUED:
        return value  # Bypass validator for re-queue

    # Check if transition is valid
    allowed_transitions = self.VALID_TRANSITIONS.get(self.status, [])
    if value not in allowed_transitions:
        raise InvalidStateTransitionError(...)

    return value
```

2. **Import TERMINAL_TASK_STATUSES from task_service.py:**
```python
# app/models.py (top of file)
# NOTE: This creates circular dependency - need to refactor
```

**Pros:**
- ✅ Keeps VALID_TRANSITIONS "pure" (terminal = no transitions)
- ✅ Centralizes re-queue logic in validator

**Cons:**
- ❌ Creates circular dependency (models.py ← task_service.py)
- ❌ Hidden magic (bypass not visible in state machine)
- ❌ Harder to test and validate
- ❌ Requires refactoring to avoid circular import

**Impact:**
- Medium risk - adds implicit behavior
- Requires architectural refactoring (move TERMINAL_TASK_STATUSES to constants.py)

---

#### Option C: Disable Validator for Service Layer Operations

**Approach:** Use SQLAlchemy `flag_modified` to bypass validator

**Changes Required:**

1. **Update `app/services/task_service.py`:**
```python
from sqlalchemy.orm import flag_modified

# Re-queue terminal task (line 237)
existing_terminal.status = TaskStatus.QUEUED  # Still blocked

# Instead, use raw attribute update
existing_terminal.__dict__['status'] = TaskStatus.QUEUED
flag_modified(existing_terminal, 'status')
```

**Pros:**
- ✅ No changes to state machine
- ✅ No circular dependencies

**Cons:**
- ❌ Bypasses all validation (dangerous)
- ❌ Violates SQLAlchemy best practices
- ❌ Fragile (breaks on SQLAlchemy upgrades)
- ❌ Hidden magic (not obvious from code)

**Impact:**
- High risk - defeats purpose of state machine
- NOT RECOMMENDED

---

### Recommended Solution: Option A

**Rationale:**
1. **Business Requirement:** Manual re-queue is a valid use case (retry failed tasks, re-publish content)
2. **State Machine Clarity:** Explicit transitions are better than hidden bypasses
3. **Low Risk:** Only allows QUEUED (not arbitrary states)
4. **Maintainability:** Self-documenting and easy to test

**Implementation Steps:**

1. Update `app/models.py` VALID_TRANSITIONS (5 lines)
2. Update docstring to document re-queue pattern (10 lines)
3. Run test to verify fix
4. Update state machine diagram if needed (documentation)

**Estimated Time:** 15 minutes

---

## Issue 2: TaskStatus.CANCELLED Not Categorized

### Problem Analysis

**Current State:**
```python
# app/services/task_service.py:32-54
ACTIVE_TASK_STATUSES = {
    TaskStatus.QUEUED,
    TaskStatus.CLAIMED,
    # ... (does not include CANCELLED)
}

# app/services/task_service.py:57-64
TERMINAL_TASK_STATUSES = {
    TaskStatus.DRAFT,
    TaskStatus.PUBLISHED,
    # ... (does not include CANCELLED)
}
```

**TaskStatus.CANCELLED Exists:**
```python
# app/models.py:81
CANCELLED = "cancelled"
```

**Test Expectation:**
```python
# tests/test_services/test_task_service.py:573
# Every status must be in ACTIVE or TERMINAL (not both, not neither)
assert is_active or is_terminal, f"Status {status.value} not categorized"
```

### Root Cause

`TaskStatus.CANCELLED` was added to the enum but never categorized in the status grouping constants. This is an oversight, not a design decision.

### Solution

**Add CANCELLED to TERMINAL_TASK_STATUSES**

**Rationale:**
- CANCELLED is a terminal state (task is abandoned, not in progress)
- Cannot proceed to next workflow steps
- Should allow re-queue (user un-cancels task)

**Changes Required:**

1. **Update `app/services/task_service.py` TERMINAL_TASK_STATUSES:**
```python
# Before (line 57-64)
TERMINAL_TASK_STATUSES = {
    TaskStatus.DRAFT,
    TaskStatus.PUBLISHED,
    TaskStatus.ASSET_ERROR,
    TaskStatus.VIDEO_ERROR,
    TaskStatus.AUDIO_ERROR,
    TaskStatus.UPLOAD_ERROR,
}

# After
TERMINAL_TASK_STATUSES = {
    TaskStatus.DRAFT,
    TaskStatus.PUBLISHED,
    TaskStatus.CANCELLED,  # ← ADD THIS
    TaskStatus.ASSET_ERROR,
    TaskStatus.VIDEO_ERROR,
    TaskStatus.AUDIO_ERROR,
    TaskStatus.UPLOAD_ERROR,
}
```

2. **Update comment to clarify CANCELLED semantics:**
```python
# Terminal states: Allow re-queue (manual retry)
# - DRAFT: Notion-only state, not in DB (for completeness)
# - PUBLISHED: Successfully completed (allow re-queue for updates)
# - CANCELLED: User cancelled task (allow re-queue if un-cancelled)
# - *_ERROR: Failed states (recoverable via re-queue)
```

**Impact:**
- Low risk - aligns CANCELLED with other terminal states
- Test passes immediately
- Enables re-queue for cancelled tasks (consistent with other terminals)

**Estimated Time:** 5 minutes

---

## Combined Implementation Plan

### Step 1: Fix Issue 2 (CANCELLED Categorization) ✅ QUICK WIN

**File:** `app/services/task_service.py`
**Lines:** 57-64

```python
TERMINAL_TASK_STATUSES = {
    TaskStatus.DRAFT,
    TaskStatus.PUBLISHED,
    TaskStatus.CANCELLED,  # ← ADD THIS LINE
    TaskStatus.ASSET_ERROR,
    TaskStatus.VIDEO_ERROR,
    TaskStatus.AUDIO_ERROR,
    TaskStatus.UPLOAD_ERROR,
}
```

**Verification:**
```bash
uv run pytest tests/test_services/test_task_service.py::test_all_task_statuses_categorized -v
```

**Expected Result:** ✅ Test passes

---

### Step 2: Fix Issue 1 (Terminal → Queued Transitions)

**File:** `app/models.py`
**Lines:** 425-426 (VALID_TRANSITIONS)

```python
# Update terminal state transitions
TaskStatus.PUBLISHED: [TaskStatus.QUEUED],  # Allow manual re-queue for content updates
TaskStatus.CANCELLED: [TaskStatus.QUEUED],  # Allow manual re-queue after un-cancel
```

**Also Update (if needed):**
```python
# Lines 428-430 - Error states (verify these already allow QUEUED)
TaskStatus.ASSET_ERROR: [TaskStatus.QUEUED],  # ✅ Should already exist
TaskStatus.VIDEO_ERROR: [TaskStatus.QUEUED],  # ✅ Should already exist
TaskStatus.AUDIO_ERROR: [TaskStatus.QUEUED],  # ✅ Should already exist
TaskStatus.UPLOAD_ERROR: [TaskStatus.QUEUED], # ✅ Should already exist
```

**Verification:**
```bash
uv run pytest tests/test_services/test_task_service.py::test_enqueue_task_allows_requeue_after_completion -v
```

**Expected Result:** ✅ Test passes for all terminal states (PUBLISHED, CANCELLED, *_ERROR)

---

### Step 3: Run Full Test Suite

**Verification:**
```bash
uv run pytest tests/test_services/test_task_service.py -v
```

**Expected Result:** ✅ All tests pass (including the 2 previously failing)

---

### Step 4: Update Documentation (Optional)

**Files to Update:**
1. `_bmad-output/architecture/state-machine-diagram.md` (if exists)
2. `app/models.py` docstring for VALID_TRANSITIONS
3. Add comment in task_service.py explaining re-queue semantics

**Example Docstring Update:**
```python
class Task(Base):
    """
    ...

    Terminal State Re-queueing:
        Terminal states (PUBLISHED, CANCELLED, *_ERROR) allow transition to QUEUED
        to enable manual retry/re-publish operations. This is the ONLY allowed
        transition from terminal states.

        Use Case Examples:
        - PUBLISHED → QUEUED: User wants to re-publish with updated audio
        - CANCELLED → QUEUED: User un-cancels a task
        - VIDEO_ERROR → QUEUED: Operator fixes video generation issue, retries
    """
```

---

## Risk Assessment

### Low Risk ✅
- Adding CANCELLED to TERMINAL_TASK_STATUSES (categorization fix)
- Adding QUEUED to terminal state transitions (aligns with business requirements)

### No Breaking Changes ✅
- Existing state machine transitions unchanged
- Only adds new terminal → QUEUED transitions (more permissive)
- Service layer code already expects these transitions to work

### Test Coverage ✅
- Both fixes directly target failing tests
- Existing integration tests validate state machine enforcement
- No new edge cases introduced

---

## Success Criteria

✅ Test `test_all_task_statuses_categorized` passes
✅ Test `test_enqueue_task_allows_requeue_after_completion` passes
✅ All other tests in `test_task_service.py` remain passing
✅ No regressions in full test suite (331 tests)
✅ State machine documentation updated (optional)

---

## Estimated Implementation Time

| Task | Time | Complexity |
|------|------|------------|
| Fix Issue 2 (CANCELLED) | 5 min | Trivial |
| Fix Issue 1 (Re-queue) | 10 min | Simple |
| Test validation | 5 min | Simple |
| Documentation update | 10 min | Simple |
| **Total** | **30 min** | **Low** |

---

## Alternative: If Re-queue is NOT a Business Requirement

If allowing terminal → QUEUED transitions is NOT desired:

### Option: Update Test to Match State Machine

**Change:** Modify test to expect failure for PUBLISHED/CANCELLED re-queue

```python
# tests/test_services/test_task_service.py:173
def test_enqueue_task_allows_requeue_after_completion():
    """Error states can be re-queued, but PUBLISHED/CANCELLED cannot."""

    # These CAN be re-queued (error recovery)
    recoverable_states = [
        TaskStatus.ASSET_ERROR,
        TaskStatus.VIDEO_ERROR,
        TaskStatus.AUDIO_ERROR,
        TaskStatus.UPLOAD_ERROR,
    ]

    # These CANNOT be re-queued (truly terminal)
    non_recoverable_states = [
        TaskStatus.PUBLISHED,
        TaskStatus.CANCELLED,
    ]

    for status in recoverable_states:
        # Assert re-queue succeeds
        ...

    for status in non_recoverable_states:
        # Assert re-queue raises InvalidStateTransitionError
        with pytest.raises(InvalidStateTransitionError):
            await enqueue_task(...)
```

**Cons:**
- Loses ability to re-publish content or un-cancel tasks
- Requires creating new tasks instead of updating existing ones
- Less flexible for operators

**NOT RECOMMENDED** - Business requirement likely allows manual retry

---

## Conclusion

**Recommended Approach:**
1. Add `TaskStatus.CANCELLED` to `TERMINAL_TASK_STATUSES` (Issue 2)
2. Add `TaskStatus.QUEUED` to terminal state transitions in `VALID_TRANSITIONS` (Issue 1)
3. Update documentation to clarify re-queue semantics

**Total Changes:** 3 lines of code + documentation
**Risk Level:** Low
**Implementation Time:** 30 minutes
**Business Value:** Enables manual retry for failed/completed tasks

Both fixes are straightforward and align with business requirements for operator flexibility in task management.
