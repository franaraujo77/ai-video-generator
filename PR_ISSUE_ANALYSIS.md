# PR Issue Analysis: notion_page_id Schema Mismatch

## Issue Summary

**Critical Bug:** Database column size mismatch will cause runtime failures when Notion webhooks send UUIDs with dashes.

## Root Cause Analysis

### Current State

**Database Schema:**
```python
# app/models.py:394-395
notion_page_id: Mapped[str] = mapped_column(
    String(32),  # ❌ Only supports 32-char UUIDs without dashes
    unique=True,
    nullable=False,
    index=True,
)
```

**Pydantic Validation:**
```python
# app/schemas/webhook.py:38
page_id: str = Field(..., min_length=32, max_length=36)  # ✅ Allows both formats

# app/schemas/task.py:45-51
notion_page_id: str = Field(
    ...,
    min_length=32,
    max_length=36,
    description="Notion page UUID (32-36 chars, with or without dashes)",
    examples=["9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8", "9afc2f9c05b3486bb2e7a4b2e3c5e5e8"],
)
```

### Evidence from Codebase

**Test Data Shows Both Formats:**
- 32-char (no dashes): `9afc2f9c05b3486bb2e7a4b2e3c5e5e8` (used in task_model tests)
- 36-char (with dashes): `9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8` (used in webhook tests)

**Webhook Test Payload (Line 47):**
```python
def valid_webhook_payload():
    return {
        "page_id": "9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8",  # 36 chars with dashes!
        # ...
    }
```

**NotionClient Comments:**
```python
# app/clients/notion.py
async def get_page(self, page_id: str) -> dict[str, Any]:
    """
    Args:
        page_id: Notion page ID (32 chars, no dashes)
    """
```

### Impact Analysis

**Failure Scenario:**
1. Notion sends webhook with 36-char UUID: `9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8`
2. Pydantic validation passes ✅ (max_length=36)
3. Code attempts database insert
4. PostgreSQL rejects with error ❌: `DataError: value too long for type character varying(32)`
5. Webhook processing fails silently (already acknowledged to Notion)
6. Task never gets enqueued

**Severity:** **HIGH** - Production runtime failure

**Probability:** **HIGH** - Notion's API documentation shows UUIDs are returned with dashes

## Solution Options

### Option 1: Expand Database Column (RECOMMENDED)

**Rationale:**
- Simplest and safest solution
- Matches existing Pydantic validation
- Supports actual Notion API format (UUIDs with dashes)
- No data transformation needed
- Backward compatible (32-char UUIDs still work)

**Implementation:**

1. Update model definition:
```python
# app/models.py
notion_page_id: Mapped[str] = mapped_column(
    String(36),  # Changed from 32 to 36
    unique=True,
    nullable=False,
    index=True,
)
```

2. Create Alembic migration:
```python
# alembic/versions/YYYYMMDD_HHMM_008_expand_notion_page_id.py
def upgrade() -> None:
    op.alter_column(
        'tasks',
        'notion_page_id',
        type_=sa.String(36),
        existing_type=sa.String(32),
        existing_nullable=False,
    )

def downgrade() -> None:
    op.alter_column(
        'tasks',
        'notion_page_id',
        type_=sa.String(32),
        existing_type=sa.String(36),
        existing_nullable=False,
    )
```

**Pros:**
- ✅ Simple, low-risk change
- ✅ No code changes beyond model and migration
- ✅ Matches real Notion API behavior
- ✅ Supports both formats transparently
- ✅ 4-byte storage difference is negligible

**Cons:**
- ❌ Allows inconsistent formats in database (some 32-char, some 36-char)

---

### Option 2: Normalize to 32-char Format

**Rationale:**
- Enforce consistent storage format
- Slightly more efficient storage
- Requires explicit format handling

**Implementation:**

1. Add UUID normalization utility:
```python
# app/utils/notion.py
def normalize_notion_page_id(page_id: str) -> str:
    """Normalize Notion page ID to 32-char format (remove dashes).

    Args:
        page_id: Notion page ID (32 or 36 chars, with or without dashes)

    Returns:
        32-character UUID without dashes

    Examples:
        "9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8" -> "9afc2f9c05b3486bb2e7a4b2e3c5e5e8"
        "9afc2f9c05b3486bb2e7a4b2e3c5e5e8" -> "9afc2f9c05b3486bb2e7a4b2e3c5e5e8"
    """
    return page_id.replace("-", "")
```

2. Update Pydantic schemas with field validator:
```python
# app/schemas/task.py
from pydantic import field_validator

class TaskCreate(BaseModel):
    notion_page_id: str = Field(
        ...,
        min_length=32,
        max_length=32,  # Changed from 36
        description="Notion page UUID (32 chars, normalized without dashes)",
        examples=["9afc2f9c05b3486bb2e7a4b2e3c5e5e8"],
    )

    @field_validator("notion_page_id", mode="before")
    @classmethod
    def normalize_page_id(cls, v: str) -> str:
        """Remove dashes from UUID."""
        return v.replace("-", "")
```

3. Update webhook handler:
```python
# app/services/webhook_handler.py
from app.utils.notion import normalize_notion_page_id

async def process_notion_webhook_event(payload: NotionWebhookPayload) -> None:
    # Normalize page_id before processing
    normalized_page_id = normalize_notion_page_id(payload.page_id)

    # Use normalized_page_id in all database operations
    ...
```

4. Update task service:
```python
# app/services/task_service.py
async def enqueue_task_from_notion_page(...):
    page_id = page.get("id")
    normalized_page_id = normalize_notion_page_id(page_id)

    # Check for existing task
    result = await session.execute(
        select(Task).where(Task.notion_page_id == normalized_page_id)
    )
    ...
```

**Pros:**
- ✅ Consistent database format
- ✅ Slightly smaller storage (4 bytes per row)
- ✅ Explicit format handling is more maintainable

**Cons:**
- ❌ More code changes (multiple files)
- ❌ Requires updating all tests
- ❌ Higher risk of introducing bugs
- ❌ Need to ensure normalization happens everywhere

---

### Option 3: Hybrid Approach

Store 32-char format but accept 36-char input:
- Database: `String(32)`
- Input validation: Accept 32-36 chars
- Automatic normalization at boundaries (Pydantic validators)
- Internal operations use 32-char format

**Same as Option 2 but emphasizes the boundary normalization pattern.**

---

## Recommendation

**Choose Option 1: Expand Database Column to 36 Characters**

### Justification

1. **Matches Real-World API Behavior:**
   - Notion's API returns UUIDs with dashes (36 chars)
   - Webhook test payload already uses 36-char format
   - Current Pydantic schemas already support 36 chars

2. **Minimizes Risk:**
   - Single file change (model + migration)
   - No code logic changes
   - No test updates needed
   - Backward compatible with existing 32-char data

3. **Performance Impact is Negligible:**
   - 4 extra bytes per row (36 vs 32)
   - VARCHAR storage overhead is minimal in PostgreSQL
   - Index performance difference is unmeasurable at this scale

4. **Aligns with Current Architecture:**
   - Pydantic schemas already validate 32-36 chars
   - No need to add normalization logic throughout codebase
   - Reduces cognitive load (one less transformation to track)

5. **Future-Proof:**
   - If Notion changes format, we're already prepared
   - Supports both formats transparently

### Storage Cost Analysis
```
Scenario: 1 million tasks
- String(32): 32 MB
- String(36): 36 MB
Difference: 4 MB (0.0004%)

With indexes and overhead, realistic difference: ~10-20 MB
Cost: Negligible on modern systems
```

---

## Implementation Plan

### Step 1: Update Model Definition
**File:** `app/models.py`
**Change:** Line 395: `String(32)` → `String(36)`

### Step 2: Create Alembic Migration
**Command:** `uv run alembic revision -m "expand notion_page_id to 36 chars"`
**File:** `alembic/versions/YYYYMMDD_HHMM_008_expand_notion_page_id.py`
**Content:**
```python
def upgrade() -> None:
    op.alter_column(
        'tasks',
        'notion_page_id',
        type_=sa.String(36),
        existing_type=sa.String(32),
        existing_nullable=False,
    )

def downgrade() -> None:
    op.alter_column(
        'tasks',
        'notion_page_id',
        type_=sa.String(32),
        existing_type=sa.String(36),
        existing_nullable=False,
    )
```

### Step 3: Run Migration
**Commands:**
```bash
# Check migration
uv run alembic upgrade head --sql

# Apply migration
uv run alembic upgrade head
```

### Step 4: Verify Tests Still Pass
**Command:** `uv run pytest tests/ -v`
**Expected:** All 536 tests pass (no changes to test data needed)

### Step 5: Update Documentation Comments
**Optional:** Update NotionClient docstrings to reflect "32-36 chars, with or without dashes"

---

## Verification Strategy

### Test Coverage
**Existing tests already cover both formats:**
- ✅ `tests/test_schemas/test_webhook.py:42` - Tests 36-char UUID with dashes
- ✅ `tests/test_task_model_26_status.py` - Tests 32-char UUID without dashes

### Integration Test
**Create new test:**
```python
async def test_webhook_with_36_char_uuid(db_session):
    """Verify 36-char UUIDs (with dashes) are stored correctly."""
    page_id = "9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8"  # 36 chars

    task = Task(
        channel_id=uuid4(),
        notion_page_id=page_id,
        title="Test Task",
        status=TaskStatus.PENDING,
        priority=5,
    )

    db_session.add(task)
    await db_session.commit()

    # Verify stored correctly
    result = await db_session.execute(
        select(Task).where(Task.notion_page_id == page_id)
    )
    stored_task = result.scalar_one()
    assert stored_task.notion_page_id == page_id  # Full 36 chars
    assert len(stored_task.notion_page_id) == 36
```

---

## Risk Assessment

**Option 1 (Expand Column):**
- Risk: **LOW**
- Testing: **MINIMAL** (existing tests cover both formats)
- Rollback: **EASY** (downgrade migration available)

**Option 2 (Normalize):**
- Risk: **MEDIUM**
- Testing: **EXTENSIVE** (need to update 20+ test files)
- Rollback: **COMPLEX** (requires code changes across multiple files)

---

## Conclusion

**Expand the database column from String(32) to String(36).**

This is the simplest, safest, and most pragmatic solution that:
- Fixes the bug with minimal code changes
- Aligns with real Notion API behavior
- Maintains backward compatibility
- Requires no test updates
- Has negligible performance impact

**Estimated Time:** 10-15 minutes
**Estimated Risk:** Very Low
**Recommended Approach:** Single PR with model change + migration
