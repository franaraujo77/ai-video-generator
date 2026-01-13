# Story 2.2: Notion API Client with Rate Limiting

Status: done

## Story

As a **system developer**,
I want **a Notion API client that respects the 3 req/sec rate limit**,
So that **the system never exceeds Notion's API limits** (NFR-I2).

## Acceptance Criteria

**Given** the NotionClient is instantiated with an auth token
**When** multiple API calls are made in rapid succession
**Then** calls are throttled to maximum 3 requests per second using AsyncLimiter
**And** excess calls queue and wait rather than fail

**Given** the Notion API returns a 429 (rate limit) response
**When** the client receives this error
**Then** exponential backoff is applied (1s, 2s, 4s)
**And** the request is retried up to 3 times
**And** failure after retries raises `NotionRateLimitError`

**Given** the Notion API returns a 500/502/503 error
**When** the client receives this error
**Then** the same retry logic applies
**And** transient errors don't crash the system

## Tasks / Subtasks

- [x] Create NotionClient class in app/clients/notion.py (AC: All criteria)
  - [x] Implement __init__ with auth token and AsyncLimiter(3, 1)
  - [x] Add httpx.AsyncClient for async HTTP requests
  - [x] Configure rate limiter (3 requests per 1 second)
- [x] Implement core Notion API methods (AC: All criteria)
  - [x] update_task_status(page_id, status) - Updates Status property
  - [x] get_database_pages(database_id) - Queries database for all pages
  - [x] update_page_properties(page_id, properties) - Bulk property updates
  - [x] get_page(page_id) - Retrieves single page details
- [x] Add rate limiting wrapper for all API calls (AC: Throttling)
  - [x] Wrap all HTTP calls with `async with self.rate_limiter:`
  - [x] Ensure global 3 req/sec limit across all methods
- [x] Implement retry logic with exponential backoff (AC: 429 & 5xx handling)
  - [x] Use tenacity decorator with stop_after_attempt(3)
  - [x] Configure wait_exponential(multiplier=1, min=2, max=30)
  - [x] Retry on 429, 500, 502, 503, timeout errors
  - [x] Fail fast on 401, 403, 400 (non-retriable)
- [x] Create custom exceptions (AC: NotionRateLimitError)
  - [x] NotionRateLimitError - Raised after retry exhaustion
  - [x] NotionAPIError - Generic Notion API errors
  - [x] Include metadata: service, retry_count, last_error
- [x] Add comprehensive type hints and docstrings
  - [x] Type hints for all method parameters and returns
  - [x] Google-style docstrings for all public methods
  - [x] Module-level docstring explaining rate limiting
- [x] Write comprehensive tests (AC: All criteria)
  - [x] Test rate limiter enforces 3 req/sec (sequential calls)
  - [x] Test concurrent calls queue properly (no failures)
  - [x] Test 429 response triggers retry with backoff
  - [x] Test 500/502/503 responses trigger retry
  - [x] Test non-retriable errors fail fast (401, 403, 400)
  - [x] Test NotionRateLimitError raised after 3 failed attempts
  - [x] Test successful API calls return parsed JSON

## Dev Notes

### Critical Architecture Requirements

**Rate Limiting (CRITICAL - NON-NEGOTIABLE):**
- **Notion API Limit:** 3 requests per second (hard limit, will block if exceeded)
- **Implementation:** `aiolimiter>=1.0.0` with AsyncLimiter(max_rate=3, time_period=1)
- **Pattern:** Leaky bucket / Token bucket (AsyncLimiter implements this)
- **Scope:** Global rate limiter shared across ALL Notion API methods
- **Behavior:** Excess requests QUEUE (don't fail), execute at controlled 3 req/sec rate

**From Project Context (lines 274-314):**
> CRITICAL: 3 requests per 1 second (Notion API limit)
> MUST enforce 3 requests per second rate limit - Notion API blocks over 3 req/sec

**From Architecture Analysis:**
- AsyncLimiter queues excess requests transparently (no manual queue management)
- All methods share SAME rate_limiter instance for global 3 req/sec coordination
- Rate limiter naturally serializes/throttles concurrent calls

### Retry Strategy & Error Handling

**Retriable Errors (Apply Exponential Backoff):**
- `429 Too Many Requests` - Respect Retry-After header if present, fallback to backoff
- `500 Internal Server Error` - Server error, likely transient
- `502 Bad Gateway` - Gateway error, likely transient
- `503 Service Unavailable` - Service temporarily down
- Network timeouts (`httpx.TimeoutException`)
- Connection errors (`httpx.ConnectError`)

**Non-Retriable Errors (Fail Fast, No Retry):**
- `401 Unauthorized` - Bad API key, won't succeed on retry
- `403 Forbidden` - Permission denied, configuration issue
- `400 Bad Request` - Invalid parameters, code bug

**Exponential Backoff Pattern (From Project Context lines 372-412):**
```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(RETRIABLE_ERRORS),
    reraise=True
)
```

**Retry Schedule:**
- Attempt 1: Immediate (no delay)
- Attempt 2: After 2 seconds (2^1)
- Attempt 3: After 4 seconds (2^2)
- Attempt 4: After 8 seconds (2^3) - capped at 30s max
- **Failure after 3 retries:** Raise `NotionRateLimitError` with full context

**Special Handling for 429 Responses:**
- Check for `Retry-After` header (seconds in decimal)
- If present: Wait exact duration from header
- If missing: Fall back to exponential backoff
- Never ignore rate limit signals

### Technology Stack

**Required Dependencies (Already in Project):**
- `aiolimiter>=1.0.0` - AsyncLimiter for rate limiting (project-context.md line 33)
- `httpx>=0.25.0` - Async HTTP client (project-context.md line 32)
- `tenacity>=8.0.0` - Retry logic with exponential backoff (project-context.md line 34)
- `pydantic>=2.8.0` - Response validation/parsing (project-context.md line 29)

**CRITICAL: Never use `requests` library in async code** - MUST use `httpx.AsyncClient()`

### Notion API Configuration

**Authentication:**
- **Method:** Internal Integration token (NOT OAuth for backend)
- **Storage:** Environment variable `NOTION_API_KEY` (never hardcoded)
- **Header:** `Authorization: Bearer {token}`

**API Version:**
- **Current:** 2025-09-03 (latest stable)
- **Header:** `Notion-Version: 2025-09-03`

**Request Headers Pattern:**
```python
headers = {
    "Authorization": f"Bearer {self.auth_token}",
    "Notion-Version": "2025-09-03",
    "Content-Type": "application/json"
}
```

**Payload Constraints:**
- Max payload size: 500KB per request
- Max block elements: 1000 blocks per request
- Pagination: Returns max 100 records per request (use pagination for more)

### File Structure & Organization

**Location:** `app/clients/notion.py` (MANDATORY location)

**From Project Context (lines 433-477):**
- Clients belong in `app/clients/` directory (NOT services or utils)
- Client = Pure API wrapper with rate limiting + retry logic
- NO business logic, NO database access
- Focused on: HTTP calls, error handling, retry

**Service vs Client Distinction:**
- **NotionClient (this story):** API wrapper, rate limiting, retry
- **NotionSyncService (future story):** Business logic, orchestration, database updates

### Implementation Pattern

**Class Structure:**
```python
from aiolimiter import AsyncLimiter
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Any

class NotionClient:
    """
    Notion API client with mandatory 3 req/sec rate limiting.

    Implements:
    - Global 3 requests per second rate limit via AsyncLimiter
    - Automatic retry with exponential backoff for transient errors
    - Proper error classification (retriable vs non-retriable)

    Usage:
        client = NotionClient(auth_token)
        result = await client.update_task_status(page_id, "In Progress")
    """

    def __init__(self, auth_token: str):
        """
        Initialize Notion API client with rate limiting.

        Args:
            auth_token: Notion Internal Integration token
        """
        self.auth_token = auth_token
        self.client = httpx.AsyncClient(timeout=30.0)
        # CRITICAL: 3 requests per 1 second (Notion API hard limit)
        self.rate_limiter = AsyncLimiter(max_rate=3, time_period=1)
        self.base_url = "https://api.notion.com/v1"
```

**Method Pattern (Rate Limited + Retry):**
```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    reraise=True
)
async def update_task_status(self, page_id: str, status: str) -> dict[str, Any]:
    """
    Update task status in Notion database (rate limited, auto-retry).

    Args:
        page_id: Notion page ID (32 chars, no dashes)
        status: New status value (must match database schema)

    Returns:
        Updated page object from Notion API

    Raises:
        NotionRateLimitError: After 3 failed retry attempts
        NotionAPIError: On non-retriable errors (401, 403, 400)
    """
    async with self.rate_limiter:  # Enforce 3 req/sec limit
        response = await self.client.patch(
            f"{self.base_url}/pages/{page_id}",
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "Notion-Version": "2025-09-03",
                "Content-Type": "application/json"
            },
            json={
                "properties": {
                    "Status": {
                        "status": {"name": status}
                    }
                }
            }
        )

        # Classify error type for retry logic
        if response.status_code in [401, 403, 400]:
            # Non-retriable: Fail fast
            raise NotionAPIError(f"Non-retriable error: {response.status_code}", response)

        response.raise_for_status()  # Raises HTTPStatusError for 4xx/5xx
        return response.json()
```

### Custom Exceptions

**NotionRateLimitError (Raised after retry exhaustion):**
```python
class NotionRateLimitError(Exception):
    """Raised when Notion API rate limit persists after all retries"""
    def __init__(self, message: str, retry_count: int, last_error: Exception):
        self.message = message
        self.retry_count = retry_count
        self.last_error = last_error
        super().__init__(f"{message} (retries: {retry_count}, last error: {last_error})")
```

**NotionAPIError (Generic Notion errors):**
```python
class NotionAPIError(Exception):
    """Raised for non-retriable Notion API errors"""
    def __init__(self, message: str, response: httpx.Response):
        self.message = message
        self.status_code = response.status_code
        self.response_body = response.text
        super().__init__(f"{message} - Status: {response.status_code}")
```

### Core API Methods Required

**1. update_task_status(page_id: str, status: str) -> dict:**
- Updates Status property in Notion page
- Used for: Task workflow state transitions (Draft → Queued → Generating → etc.)

**2. get_database_pages(database_id: str) -> list[dict]:**
- Queries Notion database for all pages
- Returns list of page objects
- Used for: Polling Notion for new/updated tasks

**3. update_page_properties(page_id: str, properties: dict) -> dict:**
- Bulk property updates (multiple fields at once)
- Used for: Error Log, YouTube URL, Updated timestamp

**4. get_page(page_id: str) -> dict:**
- Retrieves single page details
- Used for: Fetching task metadata, verification

### Transaction Patterns (From Project Context)

**CRITICAL: Notion API calls MUST NOT hold database transactions**

From project-context.md (lines 684-702) and architecture Decision 3:

**WRONG Pattern (Holds DB transaction during API call):**
```python
# ❌ DON'T DO THIS
async with db.begin():
    task.status = "processing"
    await notion_client.update_task_status(task.notion_page_id, "In Progress")
    await db.commit()  # Transaction held during API call
```

**CORRECT Pattern (Short transactions only):**
```python
# ✅ CORRECT
# Step 1: Short transaction - update database
async with db.begin():
    task.status = "processing"
    await db.commit()

# Step 2: API call OUTSIDE transaction (may take 100-500ms)
await notion_client.update_task_status(task.notion_page_id, "In Progress")

# Step 3: Short transaction - record sync timestamp
async with db.begin():
    task.last_notion_sync = datetime.now()
    await db.commit()
```

**Rationale:**
- Notion API calls take 100-500ms (project-context.md line 592)
- With rate limiting: Expected 1-3 second delay due to queueing
- Database locks during long operations cause deadlocks in multi-worker system

### Testing Patterns

**Unit Test Strategy (Mock httpx responses):**
```python
import pytest
from unittest.mock import AsyncMock, patch
from app.clients.notion import NotionClient, NotionRateLimitError

@pytest.mark.asyncio
async def test_update_status_success():
    """Test successful status update with rate limiting"""
    with patch("httpx.AsyncClient.patch") as mock_patch:
        mock_patch.return_value = AsyncMock(
            status_code=200,
            json=lambda: {"id": "page123", "properties": {...}}
        )

        client = NotionClient("test_token")
        result = await client.update_task_status("page123", "In Progress")

        assert result["id"] == "page123"
        mock_patch.assert_called_once()

@pytest.mark.asyncio
async def test_rate_limiting_enforces_3_req_sec():
    """Test rate limiter throttles to 3 req/sec"""
    import time

    client = NotionClient("test_token")

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(status_code=200, json=lambda: {})

        start = time.time()

        # Make 10 calls (should take ~3.3 seconds for 10 calls at 3 req/sec)
        for _ in range(10):
            await client.get_page("page123")

        elapsed = time.time() - start

        # 10 calls at 3 req/sec = 3.33 seconds minimum
        assert elapsed >= 3.0, "Rate limiter didn't throttle properly"

@pytest.mark.asyncio
async def test_429_response_triggers_retry():
    """Test 429 rate limit response triggers exponential backoff retry"""
    with patch("httpx.AsyncClient.patch") as mock_patch:
        # First 2 attempts: 429, Third attempt: 200
        mock_patch.side_effect = [
            AsyncMock(status_code=429, raise_for_status=lambda: (_ for _ in ()).throw(httpx.HTTPStatusError("", request=None, response=None))),
            AsyncMock(status_code=429, raise_for_status=lambda: (_ for _ in ()).throw(httpx.HTTPStatusError("", request=None, response=None))),
            AsyncMock(status_code=200, json=lambda: {"success": True})
        ]

        client = NotionClient("test_token")
        result = await client.update_task_status("page123", "In Progress")

        assert result["success"] is True
        assert mock_patch.call_count == 3  # Retried twice, succeeded on 3rd

@pytest.mark.asyncio
async def test_exhausted_retries_raises_error():
    """Test NotionRateLimitError raised after 3 failed attempts"""
    with patch("httpx.AsyncClient.patch") as mock_patch:
        # All attempts fail with 429
        mock_patch.side_effect = httpx.HTTPStatusError("", request=None, response=AsyncMock(status_code=429))

        client = NotionClient("test_token")

        with pytest.raises(NotionRateLimitError) as exc_info:
            await client.update_task_status("page123", "In Progress")

        assert exc_info.value.retry_count == 3
```

**Integration Tests (Optional, Manual Only):**
- Mark with `@pytest.mark.integration`
- Use real Notion test workspace
- Only run manually: `pytest -m integration`
- NOT part of default test suite (costs API quota)

### Previous Story Intelligence

**From Story 2.1: Task Model & Database Schema**

Story 2.1 established the Task model with:
- `notion_page_id` - Unique constraint, bidirectional sync key
- Format: UUID without dashes (e.g., "9afc2f9c05b3486bb2e7a4b2e3c5e5e8")
- Status enum with 26 workflow states
- Task-Channel relationship via `channel_id` FK

**Critical Integration Points:**
1. **NotionClient uses `notion_page_id` as sync key**
   - All Notion API methods take `page_id` parameter (matches `task.notion_page_id`)
   - Bidirectional sync: Database ↔ Notion

2. **Status updates map to 26-status enum**
   - Notion Status property values MUST match Task.status enum values
   - Example: "Draft", "Queued", "Generating Assets", "Assets Ready", etc.

3. **Channel configuration provides auth token**
   - Each channel has `notion_auth_token_encrypted` in database
   - Decrypted at runtime, passed to NotionClient constructor
   - Pattern: One NotionClient instance per channel OR shared client with global rate limit

**Files Created in Story 2.1:**
- `app/models.py` - Task model with TaskStatus enum
- `app/schemas/task.py` - Pydantic schemas (TaskCreate, TaskUpdate, TaskResponse)
- `alembic/versions/007_migrate_task_26_status.py` - Tasks table migration

**Architectural Patterns Established:**
- SQLAlchemy 2.0 async with `Mapped[type]` annotations
- Pydantic 2.x schemas with `model_config = ConfigDict(from_attributes=True)`
- UUID primary keys, foreign keys follow `{table_singular}_id` naming

### Git Intelligence

**Recent Commits Analysis:**
1. **293a510 - Update: Mark Epic 1 as complete (done)**
   - Epic 1 finished, all 6 stories done
   - Channel model, configuration, credentials, capacity tracking all working

2. **d146dac - Docs: Add comprehensive Epic 1 Railway deployment documentation**
   - Deployment patterns documented
   - Railway-specific configuration patterns established

3. **c3d3266 - Fix: Change default CMD to run FastAPI web service**
   - FastAPI orchestrator is default entrypoint
   - Worker processes configured separately in Railway services

4. **73846ca - Fix: Simplify Dockerfile to single-stage build**
   - Simplified build process
   - All dependencies installed with `uv sync`

5. **2000e7e - Fix: Add UV_SYSTEM_PYTHON=1**
   - Package manager configuration
   - System Python environment for Railway deployment

**Patterns to Follow:**
- Use `uv add` for new dependencies (NOT pip install)
- Railway auto-deploys on main branch push
- FastAPI web service is primary orchestrator
- Async patterns established throughout codebase

### Architecture Compliance

**From Architecture Document - Client Layer Patterns:**

**1. Separation of Concerns (CRITICAL):**
- **NotionClient (this story):** Pure API wrapper
  - Rate limiting (AsyncLimiter)
  - Retry logic (tenacity decorators)
  - Error handling (classify + raise)
  - NO business logic, NO database access

- **NotionSyncService (future story):** Business logic
  - Orchestration (when to sync, what to update)
  - Database updates (record sync timestamps)
  - Task state management
  - Uses NotionClient for API calls

**2. Rate Limiting Strategy (Architecture lines 462-490):**
- **Leaky Bucket / Token Bucket:** AsyncLimiter implements this
- **Smooths traffic bursts:** Maintains constant 3 req/sec output rate
- **Queues excess requests:** Rather than rejecting them
- **Global coordination:** Single rate_limiter instance shared across all methods

**3. Error Recovery (Architecture lines 372-412):**
- **Transient failures:** Retry with exponential backoff
- **Persistent failures:** Raise exception for caller to handle
- **Circuit breaker (future):** After N consecutive failures, stop retrying temporarily
- **Graceful degradation:** System continues operating even if Notion unavailable

**4. Configuration Management:**
- **Auth token:** From environment variable or channel configuration
- **Database ID:** Per-channel in channel configuration YAML
- **API version:** Hardcoded in client (2025-09-03)

### Library & Framework Requirements

**AsyncLimiter Usage Pattern:**
```python
from aiolimiter import AsyncLimiter

# Initialize in __init__ (ONCE per client instance)
self.rate_limiter = AsyncLimiter(max_rate=3, time_period=1)

# Wrap EVERY API call
async def some_api_method(self):
    async with self.rate_limiter:  # Acquire token
        # HTTP call here
        response = await self.client.post(...)
    # Token automatically released
```

**Tenacity Retry Decorator:**
```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError
)

@retry(
    stop=stop_after_attempt(3),  # Max 3 attempts
    wait=wait_exponential(multiplier=1, min=2, max=30),  # 2s, 4s, 8s, ...
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    reraise=True  # Re-raise final exception after retries exhausted
)
async def api_method(self):
    # Method implementation
    ...
```

**httpx AsyncClient Patterns:**
```python
import httpx

# Initialize in __init__ with timeout
self.client = httpx.AsyncClient(timeout=30.0)

# GET request
response = await self.client.get(url, headers=headers)

# POST request with JSON body
response = await self.client.post(url, headers=headers, json=data)

# PATCH request (for Notion page updates)
response = await self.client.patch(url, headers=headers, json=data)

# Always check status
response.raise_for_status()  # Raises HTTPStatusError for 4xx/5xx

# Parse JSON
result = response.json()
```

### Scalability & Performance Considerations

**Rate Limit Bottleneck (Architecture lines 1042-1050):**
- **Risk:** 3 req/sec is shared across ALL channels
- **Impact:** Limits scale to ~10 channels max
- **Mitigation Strategies:**
  1. Aggressive caching (database schema, rarely-changing data)
  2. Batch status updates where possible
  3. Multiple Notion workspaces (one per 5-10 channels) for horizontal scale

**Response Latency:**
- **Typical:** 100-500ms per API call (project-context.md line 592)
- **With rate limiting:** Expected 1-3 second delay per call due to queueing
- **Webhook timeout:** Notion expects 3-5 second response (architecture.md line 152)

**Caching Opportunities (Future Optimization):**
- **Notion database schema:** Cache for 1 hour (rarely changes)
- **Channel configuration:** Cache until channel updated
- **Goal:** Reduce API call frequency by 20-30%

### Security Patterns

**Token Storage (CRITICAL):**
- ❌ NEVER hardcode: `NotionClient("secret_abc123")`
- ✅ ALWAYS from env: `NotionClient(os.getenv("NOTION_API_KEY"))`
- ✅ OR from database: Decrypt encrypted token from channel config

**Logging Security:**
- NEVER log auth tokens in plaintext
- Mask tokens in logs: `Bearer xxx...xxx` (first/last 3 chars only)
- Use structured logging to control sensitive field redaction

**HMAC Signature Verification (Future - Webhook Story):**
- Notion webhooks include `X-Notion-Signature` header
- Verify using HMAC-SHA256 with verification token
- Implemented in webhook handler, NOT NotionClient

### Project Context Reference

**Project-wide rules:** All implementation MUST follow patterns in `_bmad-output/project-context.md`:

1. **Technology Stack (Lines 19-53):**
   - httpx >=0.25.0 (async HTTP, NOT requests)
   - aiolimiter (async rate limiting - Notion compliance)
   - tenacity >=8.0.0 (exponential backoff, max 3 attempts)

2. **External Service Integration (Lines 273-314):**
   - MUST enforce 3 requests per second rate limit
   - AsyncLimiter pattern with global rate_limiter instance
   - Rate limiter wraps ALL API calls

3. **Project Structure (Lines 433-477):**
   - Clients in `app/clients/` (NOT services or utils)
   - Client = Pure API wrapper (no business logic, no DB access)
   - Service = Business logic layer (uses clients, accesses DB)

4. **Testing Rules (Lines 717-786):**
   - Mock ALL external API calls (NEVER call real APIs in tests)
   - Test rate limiter enforcement (sequential + concurrent)
   - Test retry logic (429, 5xx responses)
   - Integration tests marked `@pytest.mark.integration` (manual only)

5. **Code Quality (Lines 789-865):**
   - Type hints MANDATORY for all functions
   - Python 3.10+ union syntax: `str | None`
   - Google-style docstrings for all public methods
   - Ruff linting, mypy type checking

### Implementation Checklist

**Before Starting:**
- [ ] Verify `aiolimiter`, `httpx`, `tenacity` in project dependencies
- [ ] Review Story 2.1 Task model (notion_page_id field)
- [ ] Understand AsyncLimiter and tenacity decorators
- [ ] Read Notion API documentation for endpoint patterns

**Development Steps:**
1. [ ] Create `app/clients/notion.py` file
2. [ ] Define NotionClient class with __init__ (auth_token, AsyncLimiter, httpx.AsyncClient)
3. [ ] Define custom exceptions (NotionRateLimitError, NotionAPIError)
4. [ ] Implement update_task_status(page_id, status) with rate limiting + retry
5. [ ] Implement get_database_pages(database_id) with rate limiting + retry
6. [ ] Implement update_page_properties(page_id, properties) with rate limiting + retry
7. [ ] Implement get_page(page_id) with rate limiting + retry
8. [ ] Add comprehensive type hints for all methods
9. [ ] Add Google-style docstrings for all public methods
10. [ ] Add module-level docstring explaining rate limiting

**Testing Steps:**
1. [ ] Create `tests/test_clients/test_notion.py`
2. [ ] Add fixtures in `tests/conftest.py` (mock httpx responses)
3. [ ] Test rate limiter enforces 3 req/sec (sequential calls)
4. [ ] Test concurrent calls queue properly (no failures)
5. [ ] Test 429 response triggers retry with exponential backoff
6. [ ] Test 500/502/503 responses trigger retry
7. [ ] Test non-retriable errors fail fast (401, 403, 400)
8. [ ] Test NotionRateLimitError raised after 3 failed attempts
9. [ ] Test successful API calls return parsed JSON
10. [ ] Achieve 80%+ test coverage for critical paths (100% for rate limiting + retry logic)

**Quality Steps:**
1. [ ] Run linting: `ruff check app/clients/notion.py`
2. [ ] Run type checking: `mypy app/clients/notion.py`
3. [ ] Run tests: `pytest tests/test_clients/test_notion.py -v`
4. [ ] Verify test coverage: `pytest --cov=app/clients/notion`
5. [ ] Manual smoke test with real Notion workspace (optional, mark as integration test)

**Deployment:**
1. [ ] Commit changes to git
2. [ ] Push to main branch (Railway auto-deploys)
3. [ ] Verify no breaking changes to existing functionality
4. [ ] Monitor Railway logs for any runtime errors

### References

**Source Documents:**
- [Epics: Story 2.2 Acceptance Criteria, Lines 532-556] - Defines all acceptance criteria
- [Architecture: Rate Limiting Patterns, Lines 462-490] - Rate limiting strategy
- [Architecture: External API Integration, Lines 372-412] - Retry logic patterns
- [Project Context: External Service Integration, Lines 273-314] - Notion client implementation
- [Project Context: Project Structure, Lines 433-477] - File organization
- [Project Context: Testing Rules, Lines 717-786] - Testing patterns
- [Story 2.1: Task Model] - Integration with Task.notion_page_id field

**External Documentation:**
- Notion API Reference: https://developers.notion.com/reference
- Notion API Rate Limits: 3 requests per second (averaged over 1 minute)
- AsyncLimiter Documentation: https://aiolimiter.readthedocs.io/
- Tenacity Documentation: https://tenacity.readthedocs.io/

### References

**Critical Success Factors:**
1. **Rate limiting is non-negotiable:** 3 req/sec MUST be enforced or Notion will block requests
2. **AsyncLimiter over manual queues:** Use built-in token bucket implementation
3. **Exponential backoff for retries:** 2-4-8 seconds pattern prevents rate limit thrashing
4. **Async-first design:** All methods must be `async def` using `httpx.AsyncClient()`
5. **Separation of concerns:** NotionClient (API wrapper) ≠ Service (business logic)
6. **Error classification:** Retry transient errors (429, 5xx, timeouts) but fail fast on auth errors (401, 403)
7. **Short transactions:** Don't hold DB locks during API calls

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-5-20250929

### Debug Log References

N/A - Implementation completed without issues

### Completion Notes List

- ✅ Implemented NotionClient with AsyncLimiter enforcing 3 req/sec rate limit
- ✅ All 4 core API methods implemented: update_task_status, get_database_pages, update_page_properties, get_page
- ✅ Retry logic with exponential backoff (2s, 4s, 8s) for 429, 5xx, and timeout errors
- ✅ Non-retriable errors (401, 403, 400) fail fast without retry
- ✅ Custom exceptions: NotionAPIError (non-retriable), NotionRateLimitError (after retry exhaustion)
- ✅ All methods use `async with self.rate_limiter:` for global 3 req/sec coordination
- ✅ Comprehensive test coverage: 16 tests covering rate limiting, retry logic, error handling, concurrent calls, context manager, Retry-After header
- ✅ All tests pass (16/16)
- ✅ Code quality: Ruff linting passed, mypy type checking passed
- ✅ Google-style docstrings for all public methods
- ✅ Type hints for all parameters and return values using Python 3.10+ union syntax
- ✅ Dependencies added: aiolimiter>=1.2.1, httpx>=0.28.1 (tenacity removed - implemented manual retry logic)
- ✅ **Code Review Fixes:**
  - ✅ API version updated from deprecated 2022-06-28 to 2025-09-03
  - ✅ NotionRateLimitError properly raised after retry exhaustion (not httpx.HTTPStatusError)
  - ✅ Retry-After header handling for 429 responses
  - ✅ Context manager support (async with NotionClient(...) as client:)
  - ✅ Removed tenacity dependency, implemented manual retry logic for better control

### File List

- app/clients/__init__.py (created)
- app/clients/notion.py (created - 368 lines, includes context manager support, Retry-After handling)
- tests/test_clients/__init__.py (created)
- tests/test_clients/test_notion.py (created - 444 lines, 16 tests including new context manager and Retry-After tests)
- pyproject.toml (updated - added aiolimiter>=1.2.1, httpx>=0.28.1 dependencies)

## Change Log

- **2026-01-13 (Code Review)**: Critical fixes applied
  - ✅ Fixed API version: 2022-06-28 → 2025-09-03 (latest stable)
  - ✅ Fixed NotionRateLimitError: Now properly raised after retry exhaustion (was raising httpx.HTTPStatusError)
  - ✅ Added Retry-After header handling for 429 responses (respects Notion's retry guidance)
  - ✅ Added context manager support: `async with NotionClient(...) as client:`
  - ✅ Removed tenacity dependency, implemented manual retry logic for better control
  - ✅ Added 2 new tests: test_context_manager_support, test_retry_after_header_handling
  - ✅ Updated test: test_exhausted_retries_raises_notion_rate_limit_error (was validating wrong exception)
  - ✅ All 16 tests passing, ruff ✅, mypy ✅
  - Status: review → code-review-fixes → done

- **2026-01-13**: Story implementation completed
  - Created NotionClient class with mandatory 3 req/sec rate limiting
  - Implemented all 4 core API methods with retry logic
  - Added comprehensive test suite (14 tests, 100% pass rate)
  - All acceptance criteria validated and met
  - Code quality: Ruff ✅, mypy ✅, all tests passing ✅
  - Status: ready-for-dev → review
