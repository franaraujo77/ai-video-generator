# Story 2.3: Video Entry Creation in Notion - EXHAUSTIVE TECHNICAL REQUIREMENTS

**Document Purpose:** Extract ALL critical technical requirements, constraints, and patterns relevant to implementing **Story 2.3: Video Entry Creation in Notion** from the architecture document.

**Story 2.3 Context:**
- Create video entries in Notion with required properties
- Sync entries to PostgreSQL Task database
- Enable bidirectional updates between Notion and database
- Enforce validation rules for required fields

---

## 1. NOTION INTEGRATION PATTERNS

### 1.1 Notion Database Structure & Schema

**Database Configuration:**
- **Location in Code:** Reference in `_bmad-output/planning-artifacts/ux-design-specification.md` line 844
- **Schema Definition (EXACT):**

| Property Name | Property Type | Required | Default Value | Constraints |
|---|---|---|---|---|
| Title | Title (text) | YES | None | Unique identifier for the video entry |
| Channel | Select | YES | None | Must match one of configured channels from `channel_configs/` YAML files |
| Topic | Text | YES | None | Topic/theme of the video content |
| Story Direction | Rich Text | YES | None | Narrative direction/script guidance |
| Status | Select | YES | "Draft" | 26 distinct status options (see Section 1.2 below) |
| Priority | Select | YES | "Normal" | Options: Low, Normal, High |
| Time in Status | Formula | NO | Auto-calculated | Formula: `formatDate(now() - prop("Updated"), "m 'min'")` |
| Created | Date | NO | Auto | Auto-populated on creation |
| Updated | Date | NO | Auto | Auto-populated on any update |
| Relations (Optional) | Multi-relation | NO | None | Tasks → Assets, Tasks → Videos, Tasks → Audio |

**CRITICAL VALIDATION RULES:**
- **Required fields for database entry creation:** Title + Topic (Story Direction can be empty initially)
- **Channel property must be populated from configured channels** (no free-form entry)
- **Status field default:** Must be "Draft" when first created (not "Pending" or other)
- **Priority field default:** Must be "Normal" (not "High" or "Low")

### 1.2 Notion Status Property - 26 Column Pipeline

**Source:** Architecture document, line 44 and throughout. Status is Notion's representation of the 9-state Task state machine (mapped to 26 status options for visualization).

**The 26 Status Options (EXACT MAPPING REQUIRED):**

Status options are designed to support the pipeline visualization in the Notion Board View (Kanban columns). Each status reflects task lifecycle:

1. **Draft** - Initial state, incomplete metadata
2. **Ready for Planning** - Metadata complete, ready for queuing
3. **Queued** - Added to processing queue, waiting for worker
4. **Processing** - Worker actively executing pipeline
5. **Assets Generating** - Generating images via Gemini
6. **Assets Ready** - Image generation complete
7. **Composites Creating** - Creating 16:9 composites
8. **Composites Ready** - Composites ready for video generation
9. **Videos Generating** - Animating composites with Kling
10. **Videos Ready** - All video clips generated
11. **Audio Generating** - Generating narration via ElevenLabs
12. **Audio Ready** - Narration complete
13. **SFX Generating** - Generating sound effects
14. **SFX Ready** - Sound effects complete
15. **Assembling Video** - FFmpeg final assembly in progress
16. **Ready for Review** - Complete video ready for human review
17. **Under Review** - Reviewer is examining the video
18. **Review Approved** - Human approved, ready to upload
19. **Review Rejected** - Human rejected, needs manual fixes
20. **Uploading** - YouTube upload in progress
21. **Upload Complete** - Video successfully published to YouTube
22. **Error: Invalid Input** - Non-retriable error in input validation
23. **Error: API Failure** - Non-retriable error from external API
24. **Error: Retriable** - Temporary error, will retry
25. **Error: Manual Review** - Error requiring human investigation
26. **Archived** - Task complete and archived

**IMPLEMENTATION REQUIREMENT:**
- The Task model's 9 states map to these 26 statuses
- Mapping must be defined in code (suggested: `app/models.py` or separate `status_map.py`)
- When reading Notion pages, status string is mapped back to internal Task state

### 1.3 Notion Database Views (Board, Filters, Relations)

**Board View Configuration:**
- **Default View:** Kanban board grouped by Status column
- **Column Order:** Follows the workflow sequence (Draft → Queued → Processing → ... → Upload Complete → Archived)
- **Card Preview Properties:** Title, Channel, Time in Status (minimal display to reduce cognitive load)
- **Hidden Properties:** Internal tracking fields (timestamps, retry counts)

**Saved Filtered Views (Required for MVP):**
- "All Errors" - Filter: Status starts with "Error:"
- "Ready for Review" - Filter: Status ends with "Ready"
- "High Priority" - Filter: Priority = High
- Per-channel views - Filter: Channel = "[Channel Name]"

**Relations Configuration (For Full Pipeline Visibility):**
- Tasks → Assets (multi-relation): Links to generated images
- Tasks → Videos (multi-relation): Links to generated video clips
- Tasks → Audio (multi-relation): Links to generated narration files
- **Implementation Note:** Relations are populated by `notion_sync` service as pipeline progresses

---

## 2. DATA VALIDATION REQUIREMENTS

### 2.1 Entry-Level Validation (When Creating in Notion)

**What MUST be validated when a new Notion entry is created:**

1. **Title Field:**
   - Must not be empty
   - Max length: 255 characters (standard Notion title limit)
   - No special characters restrictions (user-facing text)
   - **Error on violation:** Logged but entry remains in "Draft" status

2. **Channel Field:**
   - Must match EXACTLY one of the channel IDs from `channel_configs/` directory
   - Must not be empty or left as "Select option..."
   - Validation source: List channels from loaded YAML configs at startup
   - **Error on violation:** Logged, entry stays in "Draft" status

3. **Topic Field:**
   - Must not be empty
   - Max length: 1000 characters (text field)
   - Can contain special characters and markdown formatting
   - **Error on violation:** Logged, entry stays in "Draft" status

4. **Story Direction Field:**
   - May be empty initially (optional for drafting)
   - When populated, no length restrictions (rich text)
   - Can contain markdown, formatting, multi-line content
   - **Error on violation:** None (optional field)

5. **Status Field:**
   - Default MUST be "Draft" when created
   - Only specific valid values (the 26 options listed in Section 1.2)
   - User cannot manually create pages with arbitrary status
   - **Error on violation:** Reject invalid status values

6. **Priority Field:**
   - Default MUST be "Normal"
   - Valid values: Low, Normal, High
   - **Error on violation:** Enforce default if invalid

### 2.2 Sync-Time Validation (When Reading from Notion)

**Validation that occurs when `notion_sync` service reads pages:**

**Acceptance Criteria (from Story 2.3):**
```
Given a video entry is missing required fields (Title, Topic)
When it's processed for queuing
Then it remains in "Draft" status
And a validation error is logged (not queued)
```

**Validation Logic:**
```python
def validate_notion_entry(page: NotionPage) -> tuple[bool, Optional[str]]:
    """Validate entry before syncing to database"""

    # Required fields check
    title = page.properties.get("Title")
    topic = page.properties.get("Topic")
    channel = page.properties.get("Channel")

    if not title or not title.strip():
        return False, "Missing Title - cannot queue"

    if not topic or not topic.strip():
        return False, "Missing Topic - cannot queue"

    if not channel or not channel.strip():
        return False, "Invalid Channel - not configured"

    # Channel validation against configured channels
    configured_channels = load_configured_channels()  # From YAML files
    if channel not in configured_channels:
        return False, f"Unknown channel: {channel}"

    # If all required fields present, entry can be queued
    return True, None
```

**Logging Requirement:**
- When validation fails, log with context:
  - Entry: notion_page_id, Title, Channel
  - Failure reason: which fields are missing
  - Timestamp: when validation ran
  - Action: entry remains in Draft status (not queued)

### 2.3 Property Mapping Validation

**From Story 2.3 Acceptance Criteria:**
```
Given a video entry exists in Notion
When the sync service reads it
Then all properties are correctly mapped to Task model fields
And the notion_page_id is stored for bidirectional updates
```

**Required Property Mappings (Notion → Task Model):**

| Notion Property | Task Model Field | Type | Handling |
|---|---|---|---|
| notion_page_id | task.notion_page_id | UUID (Notion format) | Stored as-is for bidirectional sync |
| Title | task.title | str | Mapped directly |
| Channel | task.channel_id | str | Mapped to configured channel ID |
| Topic | task.topic | str | Mapped directly |
| Story Direction | task.story_direction | str/text | Mapped directly |
| Status | task.status | enum (9 states) | Mapped from 26-option to 9 states |
| Priority | task.priority | enum | Mapped to Priority enum |
| Created | task.created_at | datetime | Mapped from Notion date |
| Updated | task.updated_at | datetime | Mapped from Notion date |

**Type Conversion Requirements:**
- **Notion date fields:** Converted to Python `datetime` objects (UTC)
- **Notion status strings:** Mapped to Task state machine using lookup table
- **Notion rich text:** Extracted as plain text OR markdown (implementation choice)
- **Notion select:** String value extracted from select option

---

## 3. SYNC MECHANISMS (Bidirectional Notion ↔ PostgreSQL)

### 3.1 Polling Strategy (Database → Notion Direction)

**Source:** Architecture document, lines 450-456

**Configuration:**
- **Polling Frequency:** Every 60 seconds
- **Direction:** PostgreSQL is source of truth, Notion is view layer
- **Conflict Resolution:** PostgreSQL wins (if manual change in Notion, next poll will overwrite)

**Polling Implementation Pattern:**
```python
# app/services/notion_sync.py
async def sync_database_to_notion_loop():
    """Run every 60 seconds"""
    while True:
        try:
            # 1. Query all tasks with notion_page_id set
            tasks = await get_tasks_with_notion_pages()

            # 2. For each task, push state to Notion
            for task in tasks:
                notion_page_id = task.notion_page_id

                # Map internal status to 26-option Notion status
                notion_status = map_task_status_to_notion(task.status)

                # Push update (rate-limited)
                await notion_client.update_page(
                    page_id=notion_page_id,
                    properties={
                        "Status": notion_status,
                        "Time in Status": task.time_in_status,
                        # Update other fields as needed
                    }
                )

            # 3. Sleep 60 seconds
            await asyncio.sleep(60)

        except Exception as e:
            log.error("notion_sync_error", error=str(e))
            await send_alert("ERROR", "Notion sync failed")
```

**Rate Limiting Enforcement:**
- Notion API client uses AsyncLimiter (3 req/sec)
- Implemented in `app/clients/notion.py` (see Section 3.2)
- Never exceed 3 requests per second across all operations

### 3.2 Notion API Client Design with Rate Limiting

**Source:** Architecture document, lines 430-448

**Client Implementation Location:** `app/clients/notion.py`

**CRITICAL: AsyncLimiter Configuration (EXACT SPECIFICATION):**
```python
from aiolimiter import AsyncLimiter

class NotionClient:
    def __init__(self, auth_token: str):
        # 3 requests per 1 second = 3 req/sec
        self.rate_limiter = AsyncLimiter(3, 1)
        self.auth_token = auth_token
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {auth_token}"}
        )

    async def update_page(self, page_id: str, properties: dict):
        """Update page properties with automatic rate limiting"""
        async with self.rate_limiter:
            # Request is held until rate limit allows
            response = await self.client.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                json={"properties": properties}
            )
            response.raise_for_status()
            return response.json()

    async def get_database(self, database_id: str):
        """Get database schema"""
        async with self.rate_limiter:
            response = await self.client.get(
                f"https://api.notion.com/v1/databases/{database_id}"
            )
            response.raise_for_status()
            return response.json()

    async def query_database(self, database_id: str, filter_: dict = None):
        """Query database with pagination"""
        async with self.rate_limiter:
            response = await self.client.post(
                f"https://api.notion.com/v1/databases/{database_id}/query",
                json={"filter": filter_} if filter_ else {}
            )
            response.raise_for_status()
            return response.json()
```

**Instance Management:**
- Single shared instance across workers (singleton pattern)
- Initialized in `app/main.py` on startup
- Injected into services that need it

**Backoff Strategy:**
- AsyncLimiter automatically queues requests when rate limit approached
- Exponential backoff on 429 (Too Many Requests) responses
- Max retry delay: 60 seconds

### 3.3 Webhook Endpoint for Notion Changes (Notion → Database Direction)

**Source:** Story 2.5 in epics.md

**Endpoint Specification:**
```python
# app/routes/tasks.py (or new app/routes/webhooks.py)

@router.post("/webhook/notion")
async def handle_notion_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    """
    Receives Notion database change events

    Acceptance Criteria (Story 2.5):
    - Return 200 OK within 500ms
    - Validate payload
    - Queue for async processing (don't block)
    - Detect and reject duplicates (idempotency)
    - Validate signature if configured
    """

    # 1. Receive and validate payload
    payload = await request.json()

    # 2. Signature validation (optional if Notion webhook signed)
    if not validate_notion_signature(request.headers, payload):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 3. Extract event type
    event_type = payload.get("type")  # "page.updated", "page.created"

    # 4. Queue for async processing (return 200 immediately)
    # Critical: Don't hold connection during processing

    if event_type == "page.updated":
        # Check for duplicate by event_id
        event_id = payload.get("id")

        # Duplicate detection: Check if we've seen this event_id
        result = await session.execute(
            select(WebhookEvent).where(WebhookEvent.event_id == event_id)
        )
        if result.scalar_one_or_none():
            # Already processed, return 200 to acknowledge
            return {"status": "already_processed"}

        # Record event for idempotency
        webhook_event = WebhookEvent(
            event_id=event_id,
            payload=payload,
            processed=False
        )
        session.add(webhook_event)
        await session.commit()

        # Queue for async processing (don't await here)
        asyncio.create_task(process_notion_webhook(payload))

    # Return 200 immediately
    return {"status": "received"}
```

**Async Processing (Outside Request Lifecycle):**
```python
async def process_notion_webhook(payload: dict):
    """Process webhook asynchronously after returning 200 OK"""

    try:
        # 1. Extract page ID and changed properties
        page = payload.get("object")
        notion_page_id = page.get("id")
        properties = page.get("properties")

        # 2. Determine action based on property change
        if properties.get("Status"):
            new_status = extract_status_value(properties["Status"])

            # 3. Update or create task
            async with async_session_factory() as session:
                # Find existing task by notion_page_id
                result = await session.execute(
                    select(Task).where(Task.notion_page_id == notion_page_id)
                )
                task = result.scalar_one_or_none()

                if task:
                    # Update existing task
                    task.status = notion_status_to_task_status(new_status)
                    await session.commit()
                else:
                    # Create new task (status changed to "Queued" without prior entry)
                    task = Task(
                        notion_page_id=notion_page_id,
                        title=extract_title(properties),
                        channel_id=extract_channel(properties),
                        topic=extract_topic(properties),
                        story_direction=extract_story_direction(properties),
                        status=notion_status_to_task_status(new_status),
                        priority=extract_priority(properties)
                    )
                    session.add(task)
                    await session.commit()

                    # Add to queue if status is "Queued"
                    if new_status == "Queued":
                        await pgqueue.enqueue(task.id)

    except Exception as e:
        log.error("webhook_processing_failed", error=str(e))
        await send_alert("ERROR", "Notion webhook processing failed", {"error": str(e)})
```

**Idempotency Requirement (Story 2.5 Acceptance Criteria):**
```
Given the same webhook is received twice (Notion retry)
When duplicate detection runs
Then the second webhook is acknowledged but not re-processed (idempotency)
```

**Implementation:**
- Store event_id from webhook payload
- Before processing, check if event_id already exists
- If exists, return 200 OK (acknowledge but skip processing)
- Prevents duplicate task creation on Notion retries

### 3.4 Manual Status Updates via Notion UI (Conflict Handling)

**Scenario:** User manually changes Status in Notion, then polling sync happens

**Conflict Resolution Strategy:**
- PostgreSQL is source of truth
- Next polling cycle (60s later) will push PostgreSQL state back to Notion
- **Result:** Manual Notion changes are overwritten by database state
- **Acceptable because:** 95% of status changes should be driven by system (pipeline progression)

**User Communication:**
- Document in setup: "Notion is a view layer, status changes driven by pipeline"
- Provide alternative: Reject/approve workflows via API endpoints (human review gates)

---

## 4. ERROR HANDLING STRATEGIES

### 4.1 Validation Errors (Story 2.3 Acceptance Criteria)

**Scenario:**
```
Given a video entry is missing required fields (Title, Topic)
When it's processed for queuing
Then it remains in "Draft" status
And a validation error is logged (not queued)
```

**Error Handling Pattern:**
```python
async def sync_notion_entry(notion_page_id: str, session: AsyncSession):
    """Sync single Notion entry to database"""

    try:
        # 1. Fetch page from Notion
        page = await notion_client.get_page(notion_page_id)

        # 2. Validate required fields
        is_valid, error_message = validate_notion_entry(page)

        if not is_valid:
            # Log validation error
            log.warning(
                "notion_entry_validation_failed",
                notion_page_id=notion_page_id,
                title=page.properties.get("Title"),
                error=error_message,
                action="entry_remains_in_draft"
            )

            # Update Notion page to mark validation error (optional)
            # Add error comment or update internal status field

            return  # Don't queue

        # 3. Create or update task
        await create_or_update_task_from_notion(page, session)

        log.info(
            "notion_entry_synced",
            notion_page_id=notion_page_id,
            title=page.properties.get("Title")
        )

    except Exception as e:
        log.error(
            "notion_sync_failed",
            notion_page_id=notion_page_id,
            error=str(e)
        )
        await send_alert("ERROR", "Failed to sync Notion entry", {
            "notion_page_id": notion_page_id,
            "error": str(e)
        })
```

**Log Requirements (Structured Logging):**
- Log level: WARNING for validation failures, ERROR for exceptions
- Include context: notion_page_id, Title, Channel, which field failed
- Include action: "entry_remains_in_draft" (tells operator what to expect)
- Include timestamp (automatic from structlog)

### 4.2 API Rate Limit Errors (Notion API 3 req/sec)

**Scenario:** AsyncLimiter queue fills, requests queue up

**Handling:**
- AsyncLimiter automatically throttles requests
- Client-level: Queue requests until rate limit allows
- Server-level: No 429 errors expected if using AsyncLimiter correctly
- If 429 received despite limiter: Exponential backoff with jitter

**Backoff Implementation:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=60)
)
async def notion_api_call_with_retry(...)
    # Will retry up to 3 times with 1s, 2s, 4s delays
```

### 4.3 Notion API Integration Errors (Non-Retriable)

**Non-Retriable Errors (don't retry):**
- 400 Bad Request - Invalid request format (fix code)
- 401 Unauthorized - Invalid token (requires re-auth)
- 403 Forbidden - Permission denied (requires access grant)
- 404 Not Found - Page/database doesn't exist (skip processing)

**Handling Pattern:**
```python
try:
    response = await notion_client.get_page(notion_page_id)
except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        log.warning("notion_page_not_found", page_id=notion_page_id)
        # Skip processing (page was deleted)
    elif e.response.status_code in (401, 403):
        log.error("notion_auth_error", status=e.response.status_code)
        await send_alert("CRITICAL", "Notion authentication failed")
    elif e.response.status_code == 400:
        log.error("notion_bad_request", error=e.response.text)
        # Fix the request, don't retry
    else:
        # Retriable error
        raise
```

### 4.4 Database Sync Errors

**Scenario:** Notion entry is valid but database update fails

**Handling:**
```python
try:
    async with async_session_factory() as session:
        task = Task(
            notion_page_id=notion_page_id,
            title=title,
            channel_id=channel_id,
            status="draft"
        )
        session.add(task)
        await session.commit()
except IntegrityError as e:
    # Duplicate notion_page_id (task already exists)
    log.info("task_already_exists", notion_page_id=notion_page_id)
    # Treat as success (idempotent)
except Exception as e:
    log.error("task_creation_failed", error=str(e))
    await send_alert("ERROR", "Failed to create task from Notion entry", {
        "notion_page_id": notion_page_id,
        "error": str(e)
    })
```

---

## 5. PROPERTY MAPPING (Notion ↔ Task Model)

### 5.1 Task Model Schema (From app/models.py)

**Critical Task Model Fields Relevant to Story 2.3:**

```python
class Task(Base):
    """Task model - represents a video generation job"""

    # Primary key
    id: UUID = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Notion linkage (CRITICAL for Story 2.3)
    notion_page_id: str = mapped_column(String(100), nullable=True, unique=True)
    # Maps to Notion page ID (e.g., "abc123def456...")
    # Used for bidirectional sync - lookup existing task by notion_page_id
    # UNIQUE constraint prevents duplicate syncs

    # Content fields (from Story 2.3 properties)
    title: str = mapped_column(String(255), nullable=False)
    # Maps from: Notion Title property
    # Max length: 255 (standard title field)

    channel_id: str = mapped_column(String(100), nullable=False, index=True)
    # Maps from: Notion Channel property (select option value)
    # Must match configured channel ID from channel_configs/ YAML
    # Indexed for channel filtering

    topic: str = mapped_column(String(1000), nullable=False)
    # Maps from: Notion Topic property (text field)
    # Used to seed asset generation prompts

    story_direction: str = mapped_column(Text, nullable=True)
    # Maps from: Notion Story Direction property (rich text)
    # Optional initially, can be filled in later
    # Stored as plain text (or markdown)

    status: str = mapped_column(String(50), nullable=False, default="draft")
    # Maps from: Notion Status property (26 options)
    # Internal representation: 9 states (draft, pending, processing, etc.)
    # Mapping defined in status lookup table

    priority: str = mapped_column(String(50), nullable=False, default="normal")
    # Maps from: Notion Priority property (select: Low, Normal, High)
    # Used by scheduler for prioritization

    # Metadata fields (auto-populated, not from Notion initially)
    created_at: datetime = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: datetime = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Timestamps synced back to Notion
    # Notion Created/Updated fields read-only, not used as source
```

### 5.2 Mapping Logic (Reading from Notion → Creating/Updating Task)

**Location:** `app/services/notion_sync.py` (or similar)

**Complete Mapping Function:**
```python
async def sync_notion_page_to_task(
    notion_page: dict,
    session: AsyncSession
) -> Task:
    """
    Map Notion page to Task model

    Args:
        notion_page: Page object from Notion API
        session: Database session

    Returns:
        Task object (created or updated)
    """

    # Extract notion_page_id (used for lookups)
    notion_page_id = notion_page["id"]

    # Extract properties
    properties = notion_page["properties"]

    # Map Title
    title = extract_rich_text(properties["Title"])

    # Map Channel (extract select option value)
    channel_option = properties["Channel"]["select"]
    channel_id = channel_option["name"] if channel_option else None

    # Map Topic
    topic = extract_rich_text(properties["Topic"])

    # Map Story Direction (optional)
    story_direction_prop = properties.get("Story Direction")
    story_direction = extract_rich_text(story_direction_prop) if story_direction_prop else None

    # Map Status (from 26-option Notion status to 9-state internal status)
    notion_status = properties["Status"]["select"]
    notion_status_name = notion_status["name"] if notion_status else "Draft"
    internal_status = map_notion_status_to_internal(notion_status_name)

    # Map Priority
    priority_option = properties["Priority"]["select"]
    priority = priority_option["name"].lower() if priority_option else "normal"

    # Map timestamps (from Notion metadata, though these are read-only)
    created_at = properties.get("Created", {}).get("date", {}).get("start")
    if created_at:
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

    # Look up or create task
    result = await session.execute(
        select(Task).where(Task.notion_page_id == notion_page_id)
    )
    task = result.scalar_one_or_none()

    if task:
        # Update existing task
        task.title = title
        task.channel_id = channel_id
        task.topic = topic
        task.story_direction = story_direction
        task.status = internal_status
        task.priority = priority
        task.updated_at = datetime.utcnow()
    else:
        # Create new task
        task = Task(
            notion_page_id=notion_page_id,
            title=title,
            channel_id=channel_id,
            topic=topic,
            story_direction=story_direction,
            status=internal_status,
            priority=priority,
            created_at=created_at or datetime.utcnow()
        )

    session.add(task)
    await session.commit()

    return task


def extract_rich_text(prop: dict) -> str:
    """Extract plain text from Notion rich text property"""
    if not prop or "rich_text" not in prop:
        return ""

    text_parts = []
    for text_obj in prop["rich_text"]:
        if text_obj.get("type") == "text":
            text_parts.append(text_obj["text"]["content"])

    return "".join(text_parts)


def map_notion_status_to_internal(notion_status: str) -> str:
    """Map 26-option Notion status to 9-state internal status"""
    status_map = {
        # Draft states
        "Draft": "draft",
        "Ready for Planning": "draft",

        # Pending/Processing states
        "Queued": "pending",
        "Processing": "processing",
        "Assets Generating": "processing",
        "Composites Creating": "processing",
        "Videos Generating": "processing",
        "Audio Generating": "processing",
        "SFX Generating": "processing",
        "Assembling Video": "processing",

        # Intermediate states
        "Assets Ready": "processing",
        "Composites Ready": "processing",
        "Videos Ready": "processing",
        "Audio Ready": "processing",
        "SFX Ready": "processing",
        "Ready for Review": "awaiting_review",
        "Under Review": "awaiting_review",

        # Approval states
        "Review Approved": "approved",
        "Review Rejected": "rejected",

        # Upload states
        "Uploading": "processing",
        "Upload Complete": "completed",

        # Error states
        "Error: Invalid Input": "failed",
        "Error: API Failure": "failed",
        "Error: Retriable": "retry",
        "Error: Manual Review": "failed",

        # Terminal
        "Archived": "completed",
    }

    return status_map.get(notion_status, "draft")
```

### 5.3 Reverse Mapping (Task → Notion)

**When pushing Task updates back to Notion (from sync service):**

```python
async def push_task_to_notion(task: Task, session: AsyncSession):
    """Push task state back to Notion"""

    notion_page_id = task.notion_page_id

    # Map internal status to Notion 26-option status
    notion_status = map_internal_status_to_notion(task.status)

    # Map priority
    notion_priority = task.priority.title()  # "normal" → "Normal"

    # Prepare properties to update
    properties = {
        "Status": {
            "select": {"name": notion_status}
        },
        "Priority": {
            "select": {"name": notion_priority}
        },
        # Don't overwrite Title, Topic, Story Direction, Channel
        # (user might have edited them in Notion, and we preserve those)
    }

    try:
        await notion_client.update_page(
            page_id=notion_page_id,
            properties=properties
        )

        log.info(
            "task_pushed_to_notion",
            task_id=str(task.id),
            notion_page_id=notion_page_id,
            status=notion_status
        )

    except Exception as e:
        log.error(
            "failed_to_push_task_to_notion",
            task_id=str(task.id),
            error=str(e)
        )


def map_internal_status_to_notion(internal_status: str) -> str:
    """Map 9-state internal status to Notion 26-option status"""
    status_map = {
        "draft": "Draft",
        "pending": "Queued",
        "processing": "Processing",
        "awaiting_review": "Ready for Review",
        "approved": "Review Approved",
        "rejected": "Review Rejected",
        "completed": "Upload Complete",
        "failed": "Error: Manual Review",
        "retry": "Error: Retriable",
    }

    return status_map.get(internal_status, "Draft")
```

---

## 6. TECHNICAL REQUIREMENTS FOR TASK 2.3 IMPLEMENTATION

### 6.1 Code Files That MUST Be Created/Modified

**New Files Required:**
1. `app/clients/notion.py` - NotionClient with rate limiting
   - Implements AsyncLimiter (3 req/sec)
   - Methods: get_page, update_page, query_database, get_database

2. `app/services/notion_sync.py` - Sync service
   - `sync_database_to_notion_loop()` - Polling task (60s interval)
   - `sync_notion_entry()` - Single entry sync
   - Status mapping functions

3. `app/routes/webhooks.py` - Webhook endpoint (OR add to `app/routes/tasks.py`)
   - `POST /webhook/notion` - Receives Notion change events
   - Idempotency handling via WebhookEvent table

4. Database models for tracking webhooks:
   - `WebhookEvent` - Stores event_id for idempotency (in `app/models.py`)

**Modified Files:**
1. `app/models.py` - Add/update:
   - `Task` model with `notion_page_id` field (UNIQUE constraint)
   - `WebhookEvent` model for idempotency
   - Status mapping table (constant or enum)

2. `app/database.py` - Add:
   - Initialization of NotionClient singleton

3. `app/main.py` - Add:
   - Background task: `sync_database_to_notion_loop()` on startup
   - Route registration for webhook endpoint
   - Startup/shutdown handlers for NotionClient

4. `pyproject.toml` - Add dependencies:
   - `aiolimiter` - AsyncLimiter for rate limiting
   - `httpx` - For Notion API calls (if not already present)

### 6.2 AsyncLimiter Configuration (EXACT)

**Package:** `aiolimiter`
**Usage:**
```python
from aiolimiter import AsyncLimiter

# 3 requests per 1 second window
limiter = AsyncLimiter(3, 1)

async with limiter:
    # This request is rate-limited to 3/sec max
    response = await make_request()
```

**Why AsyncLimiter:**
- Non-blocking (doesn't use thread pools)
- Automatically queues requests when rate limit approached
- Works seamlessly with asyncio
- Built-in exponential backoff on 429 responses

### 6.3 Unique Constraints in Database Schema

**Critical Constraint:**
```python
notion_page_id: str = mapped_column(
    String(100),
    nullable=True,
    unique=True,  # CRITICAL: Prevents duplicate syncs
    index=True     # Faster lookups by notion_page_id
)
```

**Why UNIQUE:**
- When webhook arrives with notion_page_id, we query `Task.notion_page_id`
- Must return 0 or 1 result (never multiple tasks for same Notion page)
- UNIQUE constraint enforces this at database level

**Migration:**
```python
# In Alembic migration
sa.Column('notion_page_id', sa.String(100), nullable=True, unique=True)
```

### 6.4 Status Mapping Table (Constant)

**Location:** `app/models.py` or new `app/constants.py`

```python
# Mapping from 26-option Notion status to 9-state internal status
NOTION_TO_INTERNAL_STATUS = {
    "Draft": "draft",
    "Ready for Planning": "draft",
    "Queued": "pending",
    "Processing": "processing",
    "Assets Generating": "processing",
    "Assets Ready": "processing",
    "Composites Creating": "processing",
    "Composites Ready": "processing",
    "Videos Generating": "processing",
    "Videos Ready": "processing",
    "Audio Generating": "processing",
    "Audio Ready": "processing",
    "SFX Generating": "processing",
    "SFX Ready": "processing",
    "Assembling Video": "processing",
    "Ready for Review": "awaiting_review",
    "Under Review": "awaiting_review",
    "Review Approved": "approved",
    "Review Rejected": "rejected",
    "Uploading": "processing",
    "Upload Complete": "completed",
    "Error: Invalid Input": "failed",
    "Error: API Failure": "failed",
    "Error: Retriable": "retry",
    "Error: Manual Review": "failed",
    "Archived": "completed",
}

# Reverse mapping
INTERNAL_TO_NOTION_STATUS = {
    "draft": "Draft",
    "pending": "Queued",
    "processing": "Processing",
    "awaiting_review": "Ready for Review",
    "approved": "Review Approved",
    "rejected": "Review Rejected",
    "completed": "Upload Complete",
    "failed": "Error: Manual Review",
    "retry": "Error: Retriable",
}
```

### 6.5 Environment Variables Required

**For Story 2.3 Implementation:**

```bash
# Notion API Authentication
NOTION_API_TOKEN=secret_...  # Internal integration token

# Database (existing, but required)
DATABASE_URL=postgresql+asyncpg://...

# Optional: Notion webhook signature secret (if using signed webhooks)
NOTION_WEBHOOK_SECRET=...
```

**Storage:**
- Railway environment variables (secrets)
- Or `.env.local` for local development

---

## 7. CRITICAL CONSTRAINTS & PATTERNS

### 7.1 Transaction Pattern (Short Transactions Only)

**MANDATORY from Architecture Document, lines 126-144:**

**❌ WRONG: Holding transaction during Notion API call**
```python
async def bad_sync(task_id: UUID):
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)

        # BLOCKS DB CONNECTION FOR UNKNOWN TIME!
        response = await notion_client.update_page(...)

        task.synced_at = datetime.utcnow()
        await session.commit()
```

**✅ CORRECT: Claim → close → call API → reopen → update**
```python
async def good_sync(task_id: UUID):
    # Step 1: Read from DB (short transaction)
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        notion_page_id = task.notion_page_id
        # Connection closes here

    # Step 2: Call external API (no DB connection held)
    try:
        response = await notion_client.update_page(notion_page_id, {...})
    except Exception as e:
        log.error("notion_update_failed", error=str(e))
        return

    # Step 3: Update DB (short transaction)
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        task.synced_at = datetime.utcnow()
        await session.commit()
```

### 7.2 Rate Limiting Pattern (AsyncLimiter)

**MANDATORY Enforcement:**
```python
# ✅ CORRECT: Rate limiting built into client
class NotionClient:
    def __init__(self, token: str):
        self.rate_limiter = AsyncLimiter(3, 1)  # 3 req/sec

    async def get_page(self, page_id: str):
        async with self.rate_limiter:
            return await self.http_client.get(...)

# ✅ CORRECT: Use client (rate limiting automatic)
result = await notion_client.get_page(page_id)  # Automatically rate-limited

# ❌ WRONG: Bypassing rate limiter by using HTTP client directly
result = await httpx_client.get(...)  # Not rate-limited!
```

### 7.3 Async SQLAlchemy 2.0 Query Pattern

**MANDATORY (from Architecture, lines 1124-1145):**

```python
# ✅ CORRECT: SQLAlchemy 2.0 select() style
from sqlalchemy import select

result = await session.execute(
    select(Task).where(Task.notion_page_id == notion_page_id)
)
task = result.scalar_one_or_none()

# ✅ CORRECT: Get by primary key
task = await session.get(Task, task_id)

# ❌ WRONG: Legacy query() API (not async-compatible)
task = await session.query(Task).filter_by(id=task_id).first()
```

### 7.4 Logging Pattern (Structured Logging)

**MANDATORY Correlation IDs (from Architecture, lines 731-734):**

```python
import structlog
import uuid

log = structlog.get_logger()

# Generate per-task correlation ID
correlation_id = str(uuid.uuid4())

# Include in ALL log statements for that task
log.info(
    "notion_entry_synced",
    correlation_id=correlation_id,
    notion_page_id=notion_page_id,
    task_id=str(task.id),
    channel_id=task.channel_id,
    status=task.status
)
```

### 7.5 Error Handling Pattern (Custom Exceptions)

**From Architecture, lines 1180-1195:**

```python
class NotionIntegrationError(Exception):
    """Base exception for Notion integration errors"""
    pass

class NotionAuthError(NotionIntegrationError):
    """Raised on 401/403 from Notion API"""
    pass

class NotionPageNotFound(NotionIntegrationError):
    """Raised on 404 (page doesn't exist)"""
    pass

# Usage
try:
    page = await notion_client.get_page(notion_page_id)
except NotionPageNotFound:
    log.warning("notion_page_not_found", page_id=notion_page_id)
    # Skip processing
except NotionAuthError:
    log.error("notion_auth_failed")
    await send_alert("CRITICAL", "Notion authentication failed")
```

---

## 8. TESTING REQUIREMENTS

### 8.1 Unit Tests for Validation Logic

**File:** `tests/test_services/test_notion_sync.py`

```python
async def test_validate_notion_entry_missing_title():
    """Entry without Title should fail validation"""
    page = {"properties": {"Title": "", "Topic": "Test"}}
    is_valid, error = validate_notion_entry(page)
    assert is_valid is False
    assert "Title" in error

async def test_validate_notion_entry_invalid_channel():
    """Entry with unknown channel should fail"""
    page = {"properties": {
        "Title": "Test",
        "Topic": "Test",
        "Channel": "unknown_channel"
    }}
    is_valid, error = validate_notion_entry(page)
    assert is_valid is False
    assert "channel" in error.lower()
```

### 8.2 Integration Tests for Sync

```python
async def test_sync_notion_entry_creates_task(db_session):
    """Valid Notion entry should create Task"""
    notion_page = create_mock_notion_page(
        title="Test Video",
        channel="test_channel",
        topic="Test Topic",
        status="Queued"
    )

    task = await sync_notion_page_to_task(notion_page, db_session)

    assert task.title == "Test Video"
    assert task.channel_id == "test_channel"
    assert task.topic == "Test Topic"
    assert task.notion_page_id == notion_page["id"]
    assert task.status == "pending"  # "Queued" maps to "pending"

async def test_sync_preserves_notion_page_id(db_session):
    """Task must store notion_page_id for bidirectional sync"""
    notion_page = create_mock_notion_page()
    task = await sync_notion_page_to_task(notion_page, db_session)

    assert task.notion_page_id == notion_page["id"]

    # Should be findable by notion_page_id
    result = await db_session.execute(
        select(Task).where(Task.notion_page_id == notion_page["id"])
    )
    assert result.scalar_one_or_none() is not None
```

### 8.3 Mock Tests for Notion API Client

```python
async def test_notion_client_rate_limiting():
    """NotionClient should enforce 3 req/sec rate limit"""
    client = NotionClient(token="test_token")

    start_time = time.time()

    # Make 6 requests (should take ~2 seconds)
    # With 3 req/sec limiter: requests 1-3 immediate, 4-6 delayed

    for i in range(6):
        await client.get_page(f"page_{i}")

    elapsed = time.time() - start_time

    # Should take at least 1 second (6 requests / 3 per sec = 2 sec)
    assert elapsed >= 1.0
```

---

## 9. DEPLOYMENT & CONFIGURATION

### 9.1 Notion Token Management

**Setup:**
1. User creates Internal Integration in Notion workspace
2. Copy integration token (starts with `secret_...`)
3. Store in Railway environment variable: `NOTION_API_TOKEN`

**Client Initialization:**
```python
# app/main.py
from app.clients.notion import NotionClient
from app.config import NOTION_API_TOKEN

notion_client = NotionClient(auth_token=NOTION_API_TOKEN)

# Inject into services as needed
```

### 9.2 Database Migration for Notion Fields

**Alembic Migration Required:**
```python
# alembic/versions/[timestamp]_add_notion_fields.py

def upgrade() -> None:
    # Add notion_page_id column
    op.add_column('tasks', sa.Column('notion_page_id', sa.String(100), nullable=True))

    # Create unique constraint
    op.create_unique_constraint('uq_tasks_notion_page_id', 'tasks', ['notion_page_id'])

    # Create index for faster lookups
    op.create_index('ix_tasks_notion_page_id', 'tasks', ['notion_page_id'])

def downgrade() -> None:
    op.drop_index('ix_tasks_notion_page_id', table_name='tasks')
    op.drop_constraint('uq_tasks_notion_page_id', table_name='tasks')
    op.drop_column('tasks', 'notion_page_id')
```

### 9.3 Startup Configuration

**app/main.py:**
```python
from contextlib import asynccontextmanager
from app.services.notion_sync import sync_database_to_notion_loop

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start sync polling task
    sync_task = asyncio.create_task(sync_database_to_notion_loop())
    yield
    # Shutdown: Cancel sync task
    sync_task.cancel()

app = FastAPI(lifespan=lifespan)
```

---

## 10. SUCCESS CRITERIA FOR STORY 2.3

**All of the following MUST be true:**

1. ✅ **Notion Entry Creation**
   - User can create new page in Notion database
   - Page has properties: Title, Channel, Topic, Story Direction, Status (default "Draft"), Priority (default "Normal")

2. ✅ **Entry Validation**
   - Title is required, validated on sync
   - Topic is required, validated on sync
   - Channel must match configured channel ID
   - Invalid entries stay in "Draft" status and log error

3. ✅ **Property Mapping**
   - All Notion properties correctly map to Task model fields
   - `notion_page_id` stored uniquely (UNIQUE constraint)
   - Status mapped from 26-option Notion to 9-state internal
   - Priority mapped correctly

4. ✅ **Sync Service**
   - Polling service runs every 60 seconds
   - Reads all tasks from database
   - Pushes updates to Notion (Status, Priority, timestamps)
   - Respects 3 req/sec rate limit

5. ✅ **Webhook Endpoint**
   - `POST /webhook/notion` accepts Notion change events
   - Returns 200 OK within 500ms
   - Detects and rejects duplicate webhooks (idempotency)
   - Queues valid changes for async processing

6. ✅ **Bidirectional Sync**
   - Changes in Notion → database (via webhook)
   - Changes in database → Notion (via polling)
   - Conflict resolution: PostgreSQL wins (Notion is view layer)

7. ✅ **Testing**
   - Unit tests for validation logic
   - Integration tests for sync
   - Mock tests for Notion API client rate limiting

8. ✅ **Logging & Monitoring**
   - All sync operations logged with correlation IDs
   - Validation failures logged with context
   - API errors logged with appropriate level (ERROR, WARNING)
   - Alerts sent on critical failures (auth, connection loss)

---

## SUMMARY

Story 2.3 implementation requires:

**Key Technical Decisions:**
- AsyncLimiter (3 req/sec) for Notion API rate limiting
- Polling (60s) + webhooks (real-time) for sync
- PostgreSQL as source of truth, Notion as view layer
- Short transactions (claim → close → call API → reopen)
- AsyncSQLAlchemy 2.0 query patterns

**Key Constraints:**
- notion_page_id MUST be UNIQUE in database
- Never hold DB transaction during Notion API calls
- Webhook endpoint must return 200 OK within 500ms
- Validation failures keep entry in "Draft" status (don't queue)
- Conflict resolution: Database wins

**Key Files:**
- `app/clients/notion.py` - NotionClient with AsyncLimiter
- `app/services/notion_sync.py` - Sync service
- `app/routes/webhooks.py` - Webhook endpoint
- `app/models.py` - Task model with notion_page_id + status mapping

This exhaustive analysis covers all technical details needed to prevent developer mistakes during Story 2.3 implementation.
