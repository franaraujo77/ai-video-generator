---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - "_bmad-output/planning-artifacts/prd.md"
  - "_bmad-output/planning-artifacts/architecture.md"
  - "_bmad-output/planning-artifacts/ux-design-specification.md"
---

# ai-video-generator - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for ai-video-generator, decomposing the requirements from the PRD, UX Design, and Architecture documents into implementable stories.

## Requirements Inventory

### Functional Requirements

**1. Content Planning & Management (FR1-FR7)**

- FR1: Notion Database Entry Creation - User creates video entries with required properties (Title, Channel, Topic, Story Direction, Status, Priority)
- FR2: Batch Video Queuing - User batch-changes multiple Draft entries to "Queued" status
- FR3: Channel Selection Management - Notion Channel property populated from channel configuration file
- FR4: Video Project Metadata Storage - Each entry stores Title, Channel, Topic, Story Direction, Status, Priority, Error Log, YouTube URL
- FR5: Asset Review Interface - User views and approves generated assets at "Assets Ready" status
- FR6: Video Review Interface - User reviews 18 video clips at "Video Ready" status
- FR7: Audio Review Interface - User reviews narration and SFX at "Audio Ready" status

**2. Multi-Channel Orchestration (FR8-FR16)**

- FR8: Channel Configuration File Management - System reads `channels.yaml` with voice IDs, branding, OAuth tokens
- FR9: Channel Isolation - Each channel has isolated task queue, failures don't affect other channels
- FR10: Per-Channel Voice Selection - Videos use voice_id from channel configuration
- FR11: Channel-Specific Branding - Intro/outro videos applied per channel
- FR12: Channel-Specific Storage Strategy - Each channel configures "notion" or "r2" storage
- FR13: Multi-Channel Parallel Processing - Round-robin scheduling across channels
- FR14: YouTube OAuth Per Channel - Independent OAuth tokens per channel
- FR15: Channel Addition Without Code Changes - New channels via YAML + OAuth script
- FR16: Channel Capacity Balancing - System tracks queue depth per channel

**3. Video Generation Pipeline (FR17-FR26)**

- FR17: End-to-End Pipeline Execution - 8-step automation without manual intervention
- FR18: Asset Generation from Notion Planning - Generate 22 images via Gemini from Topic/Story Direction
- FR19: 16:9 Composite Creation - Combine characters + environments into 1920x1080 composites
- FR20: Video Generation via Kling - Upload composites, call Kling 2.5 API with motion prompts
- FR21: Narration Generation - Generate 18 clips via ElevenLabs with channel voice
- FR22: Sound Effects Generation - Generate 18 SFX clips via ElevenLabs
- FR23: FFmpeg Video Assembly - Trim, mix, concatenate with hard cuts
- FR24: YouTube Upload Automation - Upload via YouTube Data API with channel OAuth
- FR25: YouTube URL Population - Write YouTube URL back to Notion after upload
- FR26: Existing CLI Script Preservation - Call scripts without modification

**4. Error Handling & Recovery (FR27-FR35)**

- FR27: Transient Failure Detection - Detect timeouts, rate limits, network errors
- FR28: Exponential Backoff Retry - Retry schedule: 1min → 5min → 15min → 1hr
- FR29: Resume from Failure Point - Resume from failed step, reuse completed assets
- FR30: Granular Error Status Updates - Status shows specific error type per step
- FR31: Detailed Error Logging - Error Log contains timestamp, step, message, retry attempts
- FR32: Alert System for Terminal Failures - Slack/email alerts on retry exhaustion
- FR33: Manual Retry Trigger - User changes status back to retry
- FR34: API Quota Monitoring - Track usage against daily quotas
- FR35: Auto-Recovery Success Rate - Target 80%+ auto-recovery

**5. Queue & Task Management (FR36-FR43)**

- FR36: Webhook Endpoint for Notion Events - FastAPI `/webhook/notion` endpoint
- FR37: Task Enqueueing - PostgreSQL queue with duplicate detection
- FR38: Worker Pool Management - Python workers poll PostgreSQL queue
- FR39: Parallel Task Execution - Configurable parallelism per API service
- FR40: Priority Queue Management - High/Normal/Low priority levels
- FR41: Round-Robin Channel Scheduling - Fair distribution across channels
- FR42: Rate Limit Aware Task Selection - Workers check limits before claiming
- FR43: State Persistence Across Restarts - PostgreSQL queue survives restarts

**6. Asset & Storage Management (FR44-FR50)**

- FR44: Backend Filesystem Structure - `/workspaces/{channel_id}/{task_id}/`
- FR45: Asset Subfolder Organization - characters/, environments/, composites/
- FR46: Notion Storage Strategy - Assets as file attachments (default)
- FR47: Cloudflare R2 Storage Strategy - Optional per-channel (post-MVP)
- FR48: Asset URL Population in Notion - Write URLs to Notion Assets table
- FR49: Temporary File Cleanup - Daily cleanup of completed task directories
- FR50: Asset Generation Idempotency - Re-running overwrites existing files

**7. Status & Progress Monitoring (FR51-FR59)**

- FR51: 26 Workflow Status Progression - Draft → Queued → Generating → Ready → Approved → Published
- FR52: Review Gate Enforcement - Pause at "Assets Ready", "Video Ready", "Audio Ready"
- FR53: Real-Time Status Updates in Notion - Updates within seconds of step completion
- FR54: Progress Visibility Dashboard - Notion database views filtered by Status
- FR55: Updated Date Auto-Tracking - Auto-updates on every status change
- FR56: Error State Clarity - Separate error status per major step
- FR57: Retry State Visibility - Shows retry count and next attempt time
- FR58: Bulk Status Operations - Batch approve/retry multiple tasks
- FR59: Success Rate Tracking - Weekly success rate calculation

**8. YouTube Integration (FR60-FR67)**

- FR60: YouTube OAuth Per Channel - Independent OAuth 2.0 tokens per channel
- FR61: Token Refresh Automation - Auto-refresh before expiration
- FR62: Video Metadata Generation - Title, Description, Tags, Privacy from Notion
- FR63: Upload via YouTube Data API - Resumable upload protocol
- FR64: YouTube URL Retrieval - Extract video ID, construct URL, write to Notion
- FR65: Upload Error Handling - Retry with exponential backoff
- FR66: YouTube Compliance Enforcement - Unique videos, organic frequency
- FR67: Channel Privacy Configuration - Per-channel default privacy level

### NonFunctional Requirements

**Performance (NFR-P1 to NFR-P5)**

- NFR-P1: Pipeline Execution Time - Complete pipeline in ≤2 hours per video (90th percentile)
- NFR-P2: Parallel Processing Throughput - 20+ videos concurrent across all stages
- NFR-P3: Notion API Response Time - API calls complete within 5 seconds (95th percentile)
- NFR-P4: Webhook Response Time - Endpoint returns 200 OK within 500ms
- NFR-P5: Worker Startup Time - Workers operational within 30 seconds

**Security (NFR-S1 to NFR-S5)**

- NFR-S1: API Key Protection - Keys in env vars or secrets manager, never in code/logs
- NFR-S2: YouTube OAuth Token Security - Encrypted at rest, HTTPS transmission
- NFR-S3: Webhook Signature Validation - Validate request signatures
- NFR-S4: Database Access Control - PostgreSQL not publicly exposed
- NFR-S5: Secure Asset Storage - Proper access controls on storage

**Scalability (NFR-SC1 to NFR-SC5)**

- NFR-SC1: Multi-Channel Growth Capacity - 10 channels MVP, 20 channels without architectural changes
- NFR-SC2: Queue Depth Handling - 500+ concurrent tasks without degradation
- NFR-SC3: Worker Scaling - Linear throughput increase with worker count
- NFR-SC4: API Rate Limit Elasticity - Adapt to limit changes without deployment
- NFR-SC5: Storage Growth Management - 10,000 videos without performance impact

**Integration (NFR-I1 to NFR-I6)**

- NFR-I1: External API Availability Tolerance - Operational when 1 of 6 services unavailable
- NFR-I2: Notion API Rate Limit Compliance - Never exceed 3 requests/second
- NFR-I3: Kling API Timeout Handling - Tolerate up to 10 minutes per clip
- NFR-I4: Gemini API Quota Exhaustion Recovery - Pause until midnight reset
- NFR-I5: YouTube OAuth Token Refresh - Automatic refresh before expiration
- NFR-I6: Integration Error Visibility - Full context logging for all API errors

**Reliability (NFR-R1 to NFR-R7)**

- NFR-R1: System Uptime - 99% orchestrator uptime monthly
- NFR-R2: Auto-Recovery Success Rate - 80%+ transient failures auto-recover
- NFR-R3: State Persistence - Queue survives restarts with zero task loss
- NFR-R4: Idempotent Operations - Re-running produces identical outputs
- NFR-R5: Error Alert Reliability - 100% terminal failures trigger alerts within 5 minutes
- NFR-R6: Data Integrity - Notion status never desynchronized from actual state
- NFR-R7: Graceful Degradation - Rate limits queue tasks, not fail them

### Additional Requirements

**From Architecture Document:**

- **Starter Template:** Manual Foundation - No starter template, explicit brownfield architecture
- PostgreSQL schema with Alembic migrations for all database tables
- SQLAlchemy 2.0 async models in single `app/models.py` file
- PgQueuer for task queue with FOR UPDATE SKIP LOCKED claiming
- 3 separate worker processes (worker-1, worker-2, worker-3)
- CLI script invocation via `asyncio.to_thread` subprocess wrapper
- 9-state task lifecycle: pending, claimed, processing, awaiting_review, approved, rejected, completed, failed, retry
- Notion API client with AsyncLimiter (3 req/sec)
- YouTube quota tracking with 80%/100% alert thresholds
- Fernet encryption for per-channel credentials storage
- CLI-based OAuth setup for YouTube and Notion
- Audit logging for all human review actions (immutable, 2-year retention)
- Railway deployment with separate web service and 3 worker services
- Structured logging with correlation IDs (structlog, JSON format)
- Cost tracking per video/component in `video_costs` table
- Discord webhook alerts for CRITICAL/ERROR/WARNING events

**From UX Design Document:**

- Notion Board View as primary interface (26-column Kanban)
- "Card stuck = problem, moving = success" monitoring principle
- Review gates at expensive steps only (video generation $5-10)
- Auto-proceed through low-cost steps (asset generation $0.50)
- 80% auto-recovery happens silently (no user alerts)
- Alerts only for 20% requiring human judgment
- Channel visual identity via emoji/color/banner
- Time-in-status auto-updating for live progress
- Bulk operations for approving/retrying multiple tasks
- Progressive disclosure of complexity

**YouTube Compliance Requirements (Critical):**

- Human review gates before YouTube upload (July 2025 policy compliance)
- Evidence storage for all review actions (reviewer ID, timestamp, notes)
- Content authenticity metadata for YouTube Partner Program
- 95% autonomous operation target (5% human intervention at review gates)

### FR Coverage Map

| FR | Epic | Description |
|----|------|-------------|
| FR1 | Epic 2 | Notion database entry creation |
| FR2 | Epic 2 | Batch video queuing |
| FR3 | Epic 2 | Channel selection management |
| FR4 | Epic 2 | Video project metadata storage |
| FR5 | Epic 5 | Asset review interface |
| FR6 | Epic 5 | Video review interface |
| FR7 | Epic 5 | Audio review interface |
| FR8 | Epic 1 | Channel configuration file management |
| FR9 | Epic 1 | Channel isolation |
| FR10 | Epic 1 | Per-channel voice selection |
| FR11 | Epic 1 | Channel-specific branding |
| FR12 | Epic 1 | Channel-specific storage strategy |
| FR13 | Epic 1 | Multi-channel parallel processing |
| FR14 | Epic 1 | YouTube OAuth per channel |
| FR15 | Epic 1 | Channel addition without code changes |
| FR16 | Epic 1 | Channel capacity balancing |
| FR17 | Epic 3 | End-to-end pipeline execution |
| FR18 | Epic 3 | Asset generation from Notion planning |
| FR19 | Epic 3 | 16:9 composite creation |
| FR20 | Epic 3 | Video generation via Kling |
| FR21 | Epic 3 | Narration generation |
| FR22 | Epic 3 | Sound effects generation |
| FR23 | Epic 3 | FFmpeg video assembly |
| FR24 | Epic 7 | YouTube upload automation |
| FR25 | Epic 7 | YouTube URL population |
| FR26 | Epic 3 | Existing CLI script preservation |
| FR27 | Epic 6 | Transient failure detection |
| FR28 | Epic 6 | Exponential backoff retry |
| FR29 | Epic 6 | Resume from failure point |
| FR30 | Epic 6 | Granular error status updates |
| FR31 | Epic 6 | Detailed error logging |
| FR32 | Epic 6 | Alert system for terminal failures |
| FR33 | Epic 6 | Manual retry trigger |
| FR34 | Epic 6 | API quota monitoring |
| FR35 | Epic 6 | Auto-recovery success rate |
| FR36 | Epic 2 | Webhook endpoint for Notion events |
| FR37 | Epic 2 | Task enqueueing |
| FR38 | Epic 4 | Worker pool management |
| FR39 | Epic 4 | Parallel task execution |
| FR40 | Epic 4 | Priority queue management |
| FR41 | Epic 4 | Round-robin channel scheduling |
| FR42 | Epic 4 | Rate limit aware task selection |
| FR43 | Epic 4 | State persistence across restarts |
| FR44 | Epic 3 | Backend filesystem structure |
| FR45 | Epic 3 | Asset subfolder organization |
| FR46 | Epic 8 | Notion storage strategy |
| FR47 | Epic 8 | Cloudflare R2 storage strategy |
| FR48 | Epic 8 | Asset URL population in Notion |
| FR49 | Epic 8 | Temporary file cleanup |
| FR50 | Epic 3 | Asset generation idempotency |
| FR51 | Epic 5 | 26 workflow status progression |
| FR52 | Epic 5 | Review gate enforcement |
| FR53 | Epic 5 | Real-time status updates in Notion |
| FR54 | Epic 5 | Progress visibility dashboard |
| FR55 | Epic 5 | Updated date auto-tracking |
| FR56 | Epic 6 | Error state clarity |
| FR57 | Epic 6 | Retry state visibility |
| FR58 | Epic 5 | Bulk status operations |
| FR59 | Epic 8 | Success rate tracking |
| FR60 | Epic 7 | YouTube OAuth per channel |
| FR61 | Epic 7 | Token refresh automation |
| FR62 | Epic 7 | Video metadata generation |
| FR63 | Epic 7 | Upload via YouTube Data API |
| FR64 | Epic 7 | YouTube URL retrieval |
| FR65 | Epic 7 | Upload error handling |
| FR66 | Epic 7 | YouTube compliance enforcement |
| FR67 | Epic 7 | Channel privacy configuration |

---

## Epic List

### Epic 1: Foundation & Channel Management
**User Outcome:** Users can configure and manage multiple YouTube channels, each with isolated settings, credentials, and storage.

**FRs covered:** FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15, FR16
**NFRs addressed:** NFR-S1, NFR-S2, NFR-SC1

**Why Standalone:** Establishes the multi-channel infrastructure that all other epics build upon. Users can add/configure channels without any video processing capability yet.

---

### Epic 2: Notion Integration & Video Planning
**User Outcome:** Users can create video entries in Notion, batch-queue videos for processing, and see their content calendar.

**FRs covered:** FR1, FR2, FR3, FR4, FR36, FR37
**NFRs addressed:** NFR-I2, NFR-P3, NFR-P4

**Why Standalone:** Users can plan content in Notion. Queue system receives tasks. No generation yet, but planning is complete.

---

### Epic 3: Video Generation Pipeline
**User Outcome:** Videos automatically generate through the 8-step pipeline (assets → composites → video clips → audio → SFX → assembly) without manual intervention.

**FRs covered:** FR17, FR18, FR19, FR20, FR21, FR22, FR23, FR26, FR44, FR45, FR50
**NFRs addressed:** NFR-P1, NFR-P2, NFR-R4

**Why Standalone:** Complete generation pipeline. Users queue a video, it generates end-to-end. No upload yet, but all media is created.

---

### Epic 4: Worker Orchestration & Parallel Processing
**User Outcome:** Multiple videos process in parallel across channels with fair scheduling, priority support, and rate-limit awareness.

**FRs covered:** FR38, FR39, FR40, FR41, FR42, FR43
**NFRs addressed:** NFR-SC2, NFR-SC3, NFR-SC4, NFR-R3

**Why Standalone:** Scales the system. Single-threaded pipeline from Epic 3 becomes parallel multi-channel processing.

---

### Epic 5: Review Gates & Quality Control
**User Outcome:** Users can review and approve generated assets, videos, and audio at strategic checkpoints before expensive operations proceed.

**FRs covered:** FR5, FR6, FR7, FR51, FR52, FR53, FR54, FR55, FR58
**NFRs addressed:** NFR-R6

**Why Standalone:** Complete review workflow. Users control quality gates. Videos pause for approval, then proceed.

---

### Epic 6: Error Handling & Auto-Recovery
**User Outcome:** System automatically recovers from transient failures (80%+), provides clear error visibility, and allows manual retry triggers.

**FRs covered:** FR27, FR28, FR29, FR30, FR31, FR32, FR33, FR34, FR35, FR56, FR57
**NFRs addressed:** NFR-R2, NFR-R5, NFR-R7, NFR-I1, NFR-I3, NFR-I4, NFR-I6

**Why Standalone:** Robust error handling. System resilient to API failures. Users informed of issues and can intervene.

---

### Epic 7: YouTube Publishing & Compliance
**User Outcome:** Approved videos upload to YouTube automatically with proper metadata, OAuth, quota management, and compliance evidence for YouTube Partner Program.

**FRs covered:** FR24, FR25, FR60, FR61, FR62, FR63, FR64, FR65, FR66, FR67
**NFRs addressed:** NFR-S2, NFR-I5

**Why Standalone:** Complete YouTube integration. Videos go from "approved" to "published" with URL in Notion.

---

### Epic 8: Monitoring, Observability & Cost Tracking
**User Outcome:** Users have full visibility into system health, per-video costs, success rates, and receive alerts only when human intervention is truly needed.

**FRs covered:** FR46, FR47, FR48, FR49, FR59
**NFRs addressed:** NFR-R1, NFR-P5, NFR-SC5

**Why Standalone:** Complete observability layer. Users monitor at scale with confidence.

---

## Epic 1: Foundation & Channel Management

**Goal:** Users can configure and manage multiple YouTube channels, each with isolated settings, credentials, and storage.

### Story 1.1: Database Foundation & Channel Model

As a **system administrator**,
I want **a PostgreSQL database with the Channel model and async session management**,
So that **the system has persistent storage with proper isolation between channels**.

**Acceptance Criteria:**

**Given** the system is starting up for the first time
**When** Alembic migrations run
**Then** the `channels` table is created with columns: `id` (UUID PK), `channel_id` (str unique), `channel_name` (str), `created_at` (datetime), `updated_at` (datetime), `is_active` (bool)
**And** the async SQLAlchemy engine is configured with `pool_size=10`, `max_overflow=5`, `pool_pre_ping=True`
**And** `async_session_factory` is available for dependency injection

**Given** a channel record exists in the database
**When** a query filters by `channel_id`
**Then** only data for that specific channel is returned (FR9: isolation)

---

### Story 1.2: Channel Configuration YAML Loader

As a **system administrator**,
I want **to add new channels by creating YAML configuration files without code changes**,
So that **I can scale to 10+ channels by simply adding config files** (FR15).

**Acceptance Criteria:**

**Given** a YAML file exists at `channel_configs/{channel_id}.yaml`
**When** the system starts or reloads configuration
**Then** the channel configuration is parsed and validated
**And** required fields are enforced: `channel_id`, `channel_name`, `notion_database_id`
**And** optional fields have defaults: `priority` (normal), `is_active` (true)

**Given** a YAML file has invalid syntax or missing required fields
**When** configuration loading is attempted
**Then** the system logs a clear error message with file path and validation failure
**And** the system continues operating with other valid channels

**Given** a new `{channel_id}.yaml` file is added
**When** configuration is reloaded
**Then** the new channel becomes available without application restart (FR15)

---

### Story 1.3: Per-Channel Encrypted Credentials Storage

As a **system administrator**,
I want **YouTube OAuth tokens encrypted in the database per channel**,
So that **credentials are secure at rest and each channel has independent YouTube access** (FR14).

**Acceptance Criteria:**

**Given** the `FERNET_KEY` environment variable is set
**When** a YouTube OAuth refresh token is stored for a channel
**Then** the token is encrypted with Fernet before database storage
**And** the `channels` table stores `youtube_token_encrypted` (bytes)

**Given** a worker needs to upload a video for a channel
**When** the YouTube token is retrieved
**Then** the token is decrypted using the Fernet key
**And** decryption failure raises a clear error (not a generic exception)

**Given** two channels exist with different YouTube accounts
**When** each channel uploads a video
**Then** each upload uses that channel's specific OAuth token (FR14)

---

### Story 1.4: Channel Voice & Branding Configuration

As a **content creator**,
I want **each channel to have its own ElevenLabs voice ID and branding settings**,
So that **videos on different channels have distinct voices and intro/outro content** (FR10, FR11).

**Acceptance Criteria:**

**Given** a channel YAML includes `voice_id: "abc123"` and `branding.intro_video: "path/to/intro.mp4"`
**When** video generation runs for that channel
**Then** narration uses the specified `voice_id` (FR10)
**And** branding intro/outro paths are available to the assembly step (FR11)

**Given** a channel YAML omits `voice_id`
**When** configuration is loaded
**Then** the system uses a default voice ID from global config
**And** a warning is logged about missing channel-specific voice

**Given** two channels have different voice IDs configured
**When** videos generate for each channel
**Then** each video uses its channel's specific voice (no cross-channel bleed)

---

### Story 1.5: Channel Storage Strategy Configuration

As a **system administrator**,
I want **each channel to configure where generated assets are stored (Notion or R2)**,
So that **I can optimize storage costs and access patterns per channel** (FR12).

**Acceptance Criteria:**

**Given** a channel YAML includes `storage_strategy: "notion"`
**When** assets are generated for that channel
**Then** assets are stored as Notion file attachments (default behavior)

**Given** a channel YAML includes `storage_strategy: "r2"` with R2 credentials
**When** assets are generated for that channel
**Then** assets are uploaded to Cloudflare R2
**And** R2 URLs are stored in the database

**Given** a channel YAML omits `storage_strategy`
**When** configuration is loaded
**Then** the default `"notion"` strategy is applied
**And** the system operates normally with Notion storage

---

### Story 1.6: Channel Capacity Tracking

As a **system operator**,
I want **the system to track queue depth and processing capacity per channel**,
So that **I can monitor channel load and ensure fair scheduling** (FR13, FR16).

**Acceptance Criteria:**

**Given** multiple videos are queued for different channels
**When** the queue status is queried
**Then** queue depth is reported per channel (count of pending tasks)
**And** channels are displayed with their current load

**Given** workers are processing tasks
**When** channel capacity is calculated
**Then** in-progress tasks are counted per channel
**And** the system can determine which channel has capacity for new work (FR16)

**Given** a channel has reached its configured `max_concurrent` limit
**When** a worker looks for tasks
**Then** tasks from that channel are skipped temporarily
**And** workers pick up tasks from other channels with capacity (FR13)

---

## Epic 2: Notion Integration & Video Planning

**Goal:** Users can create video entries in Notion, batch-queue videos for processing, and see their content calendar.

### Story 2.1: Task Model & Database Schema

As a **system administrator**,
I want **a Task model that stores video project metadata**,
So that **each video has persistent state tracking throughout the pipeline** (FR4).

**Acceptance Criteria:**

**Given** Alembic migrations run
**When** the database is initialized
**Then** the `tasks` table is created with columns:
- `id` (UUID PK)
- `channel_id` (FK to channels)
- `notion_page_id` (str, unique)
- `title` (str)
- `topic` (str)
- `story_direction` (text)
- `status` (enum: 26 statuses)
- `priority` (enum: high/normal/low)
- `error_log` (text, nullable)
- `youtube_url` (str, nullable)
- `created_at`, `updated_at` (datetime)

**Given** a task is created
**When** it references a channel_id
**Then** the foreign key relationship to channels is enforced
**And** cascade delete is NOT enabled (tasks preserved if channel deactivated)

---

### Story 2.2: Notion API Client with Rate Limiting

As a **system developer**,
I want **a Notion API client that respects the 3 req/sec rate limit**,
So that **the system never exceeds Notion's API limits** (NFR-I2).

**Acceptance Criteria:**

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

---

### Story 2.3: Video Entry Creation in Notion

As a **content creator**,
I want **to create video entries in Notion with required properties**,
So that **I can plan my content calendar with all necessary metadata** (FR1).

**Acceptance Criteria:**

**Given** a Notion database is configured for a channel
**When** I create a new page in that database
**Then** I can set properties: Title (title), Channel (select), Topic (text), Story Direction (rich text), Status (select, default "Draft"), Priority (select, default "Normal")

**Given** a video entry exists in Notion
**When** the sync service reads it
**Then** all properties are correctly mapped to Task model fields (FR4)
**And** the `notion_page_id` is stored for bidirectional updates

**Given** a video entry is missing required fields (Title, Topic)
**When** it's processed for queuing
**Then** it remains in "Draft" status
**And** a validation error is logged (not queued)

---

### Story 2.4: Batch Video Queuing

As a **content creator**,
I want **to batch-change multiple Draft videos to "Queued" status**,
So that **I can efficiently queue an entire week's content at once** (FR2).

**Acceptance Criteria:**

**Given** multiple video entries exist with Status = "Draft"
**When** I select multiple entries in Notion and change Status to "Queued"
**Then** all selected entries update to "Queued" status

**Given** Notion triggers webhook for status change to "Queued"
**When** the webhook is received for each video
**Then** each video is added to the processing queue
**And** the batch operation doesn't exceed rate limits

**Given** 20 videos are batch-queued simultaneously
**When** webhooks arrive in rapid succession
**Then** the system processes all 20 without rate limit errors
**And** all 20 appear in the task queue within 60 seconds

---

### Story 2.5: Webhook Endpoint for Notion Events

As a **system developer**,
I want **a FastAPI webhook endpoint that receives Notion database change events**,
So that **video status changes trigger pipeline actions** (FR36).

**Acceptance Criteria:**

**Given** the FastAPI application is running
**When** a POST request arrives at `/webhook/notion`
**Then** the endpoint returns 200 OK within 500ms (NFR-P4)
**And** the payload is validated and queued for async processing

**Given** a webhook payload indicates Status changed to "Queued"
**When** the payload is processed
**Then** a task is created or updated in the database
**And** the task is added to the PgQueuer queue

**Given** a webhook payload has an invalid signature (if configured)
**When** signature validation fails
**Then** the endpoint returns 401 Unauthorized
**And** the payload is not processed

**Given** the same webhook is received twice (Notion retry)
**When** duplicate detection runs
**Then** the second webhook is acknowledged but not re-processed (idempotency)

---

### Story 2.6: Task Enqueueing with Duplicate Detection

As a **system developer**,
I want **tasks enqueued to PostgreSQL with duplicate detection**,
So that **the same video is never processed twice simultaneously** (FR37).

**Acceptance Criteria:**

**Given** a video's status changes to "Queued" in Notion
**When** the webhook triggers task creation
**Then** a new row is inserted into the `tasks` table with status "pending"
**And** the task is visible in the PgQueuer queue

**Given** a task with the same `notion_page_id` already exists and is "pending" or "processing"
**When** a duplicate enqueue is attempted
**Then** the duplicate is rejected
**And** no new task row is created
**And** a log entry records the duplicate attempt

**Given** a task previously completed or failed
**When** a re-queue is triggered (manual retry)
**Then** a new task version is created
**And** the previous task's history is preserved

---

## Epic 3: Video Generation Pipeline

**Goal:** Videos automatically generate through the 8-step pipeline (assets → composites → video clips → audio → SFX → assembly) without manual intervention.

### Story 3.1: CLI Script Wrapper & Async Execution

As a **system developer**,
I want **an async wrapper that invokes existing CLI scripts without blocking the event loop**,
So that **workers can execute long-running scripts while remaining responsive** (FR26).

**Acceptance Criteria:**

**Given** a CLI script exists in `scripts/` directory
**When** `run_cli_script("generate_asset.py", args)` is called
**Then** the script executes via `asyncio.to_thread(subprocess.run, ...)`
**And** the event loop is not blocked during execution
**And** stdout/stderr are captured for logging

**Given** a CLI script exits with non-zero code
**When** the wrapper detects the failure
**Then** `CLIScriptError` is raised with script name, exit code, and stderr
**And** the error is structured for logging and retry decisions

**Given** a CLI script exceeds the timeout (default 600s)
**When** the timeout triggers
**Then** `asyncio.TimeoutError` is raised
**And** the subprocess is terminated
**And** partial outputs are preserved if possible

**Given** any CLI script in `scripts/`
**When** it is invoked by the orchestrator
**Then** the script code remains UNCHANGED (FR26: brownfield preservation)

---

### Story 3.2: Filesystem Organization & Path Helpers

As a **system developer**,
I want **helper functions that manage the channel-organized directory structure**,
So that **assets are stored in predictable locations per channel and project** (FR44, FR45).

**Acceptance Criteria:**

**Given** a channel_id and project_id
**When** `get_project_dir(channel_id, project_id)` is called
**Then** the path `/workspace/channels/{channel_id}/projects/{project_id}/` is returned
**And** the directory is created if it doesn't exist

**Given** a project directory
**When** `get_asset_dir()` is called
**Then** subdirectories are available: `characters/`, `environments/`, `props/`, `composites/` (FR45)
**And** each subdirectory is created on first access

**Given** assets are generated for a project
**When** stored using path helpers
**Then** the filesystem structure matches: `/workspace/channels/{channel_id}/projects/{project_id}/assets/{type}/` (FR44)

**Given** a video, audio, or sfx file is generated
**When** stored using path helpers
**Then** files go to `videos/`, `audio/`, `sfx/` subdirectories respectively

---

### Story 3.3: Asset Generation Step (Gemini)

As a **content creator**,
I want **22 images generated automatically from my Topic and Story Direction**,
So that **I have all visual assets needed for video production** (FR18).

**Acceptance Criteria:**

**Given** a task is in "Generating Assets" status
**When** the asset generation step runs
**Then** the Topic and Story Direction are combined into prompts
**And** `generate_asset.py` is called for each of 22 assets (characters, environments, props)
**And** images are saved to `assets/{type}/{name}.png`

**Given** Gemini API successfully generates an image
**When** the download completes
**Then** the PNG is saved to the correct asset subdirectory
**And** the task's asset manifest is updated

**Given** an asset already exists at the target path (FR50: idempotency)
**When** regeneration is triggered
**Then** the existing file is overwritten
**And** no duplicate files are created

**Given** Gemini API fails for one asset
**When** the error is caught
**Then** the specific asset failure is logged
**And** the step can be retried from the failed asset (partial resume)

---

### Story 3.4: Composite Creation Step

As a **content creator**,
I want **character and environment images combined into 16:9 composites**,
So that **I have properly formatted seed images for video generation** (FR19).

**Acceptance Criteria:**

**Given** character and environment assets exist
**When** the composite creation step runs
**Then** `create_composite.py` is called with character + environment paths
**And** output is a 1920x1080 (16:9) PNG in `assets/composites/`

**Given** 18 scenes are defined in the story
**When** composites are created
**Then** 18 composite images are generated (one per video clip)
**And** each composite is named by scene number

**Given** a scene requires split-screen composition
**When** `create_split_screen.py` is detected as needed
**Then** the correct script is invoked for horizontal split
**And** the output maintains 1920x1080 dimensions

**Given** composite creation fails
**When** the error is logged
**Then** the specific scene number and input files are recorded
**And** retry can target the failed composite

---

### Story 3.5: Video Clip Generation Step (Kling)

As a **content creator**,
I want **composite images animated into 10-second video clips via Kling AI**,
So that **each scene becomes a moving video segment** (FR20).

**Acceptance Criteria:**

**Given** composite images exist in `assets/composites/`
**When** the video generation step runs
**Then** each composite is uploaded to catbox.moe for hosting
**And** `generate_video.py` is called with the hosted URL and motion prompt
**And** output is a 10-second MP4 in `videos/`

**Given** Kling API takes 2-5 minutes per clip (NFR-I3)
**When** generation is in progress
**Then** the system waits up to 10 minutes per clip
**And** timeout is handled gracefully with retry

**Given** 18 video clips need generation
**When** all clips complete successfully
**Then** 18 MP4 files exist in `videos/clip_01.mp4` through `videos/clip_18.mp4`

**Given** Kling API fails for a clip
**When** the error is caught
**Then** the clip number, prompt, and error are logged
**And** retry can target only the failed clip (partial resume)

---

### Story 3.6: Narration Generation Step (ElevenLabs)

As a **content creator**,
I want **18 narration audio clips generated using my channel's voice**,
So that **each scene has matching Attenborough-style narration** (FR21).

**Acceptance Criteria:**

**Given** narration scripts exist for 18 scenes
**When** the audio generation step runs
**Then** `generate_audio.py` is called with text and channel's `voice_id`
**And** output is MP3 files in `audio/`

**Given** the channel has a configured `voice_id`
**When** narration is generated
**Then** the channel-specific voice is used (FR21)
**And** voice consistency is maintained across all 18 clips

**Given** all 18 narration clips complete
**When** files are saved
**Then** 18 MP3 files exist: `audio/narration_01.mp3` through `audio/narration_18.mp3`

**Given** ElevenLabs API fails for a narration clip
**When** the error is caught
**Then** the clip number and text are logged
**And** retry targets only the failed clip

---

### Story 3.7: Sound Effects Generation Step

As a **content creator**,
I want **18 ambient sound effect clips generated for each scene**,
So that **the final video has immersive environmental audio** (FR22).

**Acceptance Criteria:**

**Given** SFX descriptions exist for 18 scenes
**When** the SFX generation step runs
**Then** `generate_sound_effects.py` is called with each description
**And** output is WAV files in `sfx/`

**Given** all 18 SFX clips complete
**When** files are saved
**Then** 18 WAV files exist: `sfx/sfx_01.wav` through `sfx/sfx_18.wav`

**Given** SFX generation fails for a clip
**When** the error is caught
**Then** the clip number and description are logged
**And** retry targets only the failed clip

---

### Story 3.8: Video Assembly Step (FFmpeg)

As a **content creator**,
I want **all video clips, narration, and SFX assembled into a final documentary**,
So that **I have a complete 90-second video ready for upload** (FR23).

**Acceptance Criteria:**

**Given** 18 video clips, 18 narration files, and 18 SFX files exist
**When** the assembly step runs
**Then** `assemble_video.py` is called with a manifest JSON
**And** each video clip is trimmed to match its narration duration
**And** narration and SFX are mixed on separate audio tracks

**Given** FFmpeg processes all clips
**When** assembly completes
**Then** a single `{project_id}_final.mp4` is created
**And** the video uses H.264 codec, AAC audio (YouTube-compatible)
**And** hard cuts are used between clips (no transitions)

**Given** assembly fails
**When** the error is caught
**Then** FFmpeg stderr is logged
**And** the specific failing clip (if identifiable) is recorded

---

### Story 3.9: End-to-End Pipeline Orchestration

As a **content creator**,
I want **the entire 8-step pipeline to execute automatically from queue to final video**,
So that **I don't need to manually trigger each step** (FR17).

**Acceptance Criteria:**

**Given** a task is claimed by a worker
**When** the pipeline orchestrator runs
**Then** steps execute in order: Assets → Composites → Videos → Narration → SFX → Assembly
**And** status updates after each step (Generating Assets → Assets Ready → Generating Video → etc.)
**And** Notion is updated within seconds of each status change

**Given** all steps complete successfully
**When** the final video exists
**Then** task status is "Awaiting Review" (before YouTube upload)
**And** total duration is ≤2 hours (NFR-P1: 90th percentile)

**Given** any step fails
**When** the failure is detected
**Then** the task moves to the appropriate error status
**And** the pipeline halts (no subsequent steps run)
**And** completed assets are preserved for retry

---

## Epic 4: Worker Orchestration & Parallel Processing

**Goal:** Multiple videos process in parallel across channels with fair scheduling, priority support, and rate-limit awareness.

### Story 4.1: Worker Process Foundation

As a **system administrator**,
I want **independent worker processes that can be scaled horizontally**,
So that **I can add processing capacity by launching more workers** (FR38).

**Acceptance Criteria:**

**Given** the worker module exists at `app/worker.py`
**When** `python -m app.worker` is executed
**Then** a worker process starts and connects to PostgreSQL
**And** the worker enters a polling loop for available tasks
**And** startup completes within 30 seconds (NFR-P5)

**Given** multiple worker instances run simultaneously
**When** they poll for tasks
**Then** each worker operates independently
**And** no shared state exists between workers (stateless design)

**Given** a worker process crashes
**When** it restarts
**Then** it resumes polling without manual intervention
**And** tasks it was processing are released for retry (via timeout)

**Given** Railway configuration
**When** services are deployed
**Then** worker-1, worker-2, worker-3 run as separate Railway services
**And** each uses the same Docker image with worker entrypoint

---

### Story 4.2: Task Claiming with PgQueuer

As a **system developer**,
I want **workers to claim tasks atomically using FOR UPDATE SKIP LOCKED**,
So that **no two workers process the same task** (FR38, FR43).

**Acceptance Criteria:**

**Given** tasks exist with status "pending" in the queue
**When** a worker polls for work
**Then** a single task is claimed using `SELECT ... FOR UPDATE SKIP LOCKED`
**And** the task status changes to "claimed" atomically
**And** a `claimed_at` timestamp is recorded

**Given** two workers poll simultaneously
**When** both attempt to claim the same task
**Then** only one worker succeeds
**And** the other worker receives no task (skipped)
**And** no deadlock or race condition occurs

**Given** a worker claims a task
**When** the worker crashes before completing
**Then** the task remains "claimed" with a timestamp
**And** after timeout (30 minutes), the task is eligible for reclaim

**Given** the system restarts
**When** workers reconnect
**Then** the PostgreSQL queue retains all pending tasks (FR43: state persistence)
**And** no tasks are lost

---

### Story 4.3: Priority Queue Management

As a **content creator**,
I want **high-priority videos processed before normal and low-priority ones**,
So that **urgent content gets uploaded faster** (FR40).

**Acceptance Criteria:**

**Given** tasks exist with different priorities (high, normal, low)
**When** a worker claims a task
**Then** high-priority tasks are selected before normal
**And** normal-priority tasks are selected before low
**And** within same priority, FIFO order is maintained

**Given** a high-priority task is queued
**When** normal-priority tasks are already pending
**Then** the high-priority task is processed next
**And** normal-priority tasks wait

**Given** no high-priority tasks exist
**When** a worker polls
**Then** normal-priority tasks are processed
**And** low-priority tasks are processed only when no normal tasks exist

**Given** a task's priority is changed in Notion
**When** the change syncs to PostgreSQL
**Then** the task's queue position reflects the new priority

---

### Story 4.4: Round-Robin Channel Scheduling

As a **system operator**,
I want **fair distribution of processing across all active channels**,
So that **one busy channel doesn't starve others** (FR41).

**Acceptance Criteria:**

**Given** multiple channels have pending tasks
**When** workers claim tasks
**Then** tasks are distributed round-robin across channels
**And** no channel monopolizes all workers

**Given** Channel A has 10 pending tasks, Channel B has 2 pending tasks
**When** 6 tasks are claimed in sequence
**Then** approximately 3 from A and 3 from B are processed (fair share)
**And** Channel B is not starved despite having fewer tasks

**Given** a channel has no pending tasks
**When** workers poll
**Then** that channel is skipped
**And** other channels' tasks are processed normally

**Given** a new channel with pending tasks becomes active
**When** workers poll next
**Then** the new channel is included in round-robin
**And** tasks from the new channel are processed fairly

---

### Story 4.5: Rate Limit Aware Task Selection

As a **system developer**,
I want **workers to check API rate limits before claiming tasks**,
So that **tasks aren't claimed only to fail immediately on rate limits** (FR42).

**Acceptance Criteria:**

**Given** Gemini API quota is exhausted for today
**When** a worker attempts to claim an asset generation task
**Then** the task is skipped (not claimed)
**And** the worker logs "Gemini quota exhausted, skipping asset tasks"
**And** tasks for other steps (that don't need Gemini) can still be claimed

**Given** Kling API is rate-limited (too many concurrent requests)
**When** a worker attempts to claim a video generation task
**Then** the task is deferred
**And** a backoff period is applied before retry

**Given** YouTube quota is at 80% of daily limit
**When** upload tasks are claimed
**Then** a warning is logged
**And** uploads proceed but are monitored

**Given** YouTube quota is exhausted (100%)
**When** upload tasks exist
**Then** upload tasks are skipped until midnight reset
**And** an alert is triggered (NFR-I4)

---

### Story 4.6: Parallel Task Execution

As a **system operator**,
I want **configurable parallelism for different pipeline stages**,
So that **I can optimize throughput while respecting API limits** (FR39).

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
**And** throughput scales with worker count (NFR-SC3)
**And** 20+ videos can be in-flight concurrently (NFR-P2)

**Given** configuration changes are made
**When** workers reload config
**Then** new parallelism limits take effect
**And** no restart is required (NFR-SC4)

---

## Epic 5: Review Gates & Quality Control

**Goal:** Users can review and approve generated assets, videos, and audio at strategic checkpoints before expensive operations proceed.

### Story 5.1: 26-Status Workflow State Machine

As a **system developer**,
I want **a well-defined state machine with 26 workflow statuses**,
So that **every task has a clear, unambiguous state throughout its lifecycle** (FR51).

**Acceptance Criteria:**

**Given** the task status enum
**When** defined in the database model
**Then** exactly 26 statuses exist matching the UX specification:
- Draft, Queued, Claimed
- Generating Assets, Assets Ready, Assets Approved
- Generating Composites, Composites Ready
- Generating Video, Video Ready, Video Approved
- Generating Audio, Audio Ready, Audio Approved
- Generating SFX, SFX Ready
- Assembling, Assembly Ready, Final Review
- Approved, Uploading, Published
- Error states: Asset Error, Video Error, Audio Error, Upload Error

**Given** a task is in status X
**When** a transition is attempted
**Then** only valid next statuses are allowed
**And** invalid transitions raise `InvalidStateTransitionError`

**Given** the UX design specifies status progression
**When** the state machine is implemented
**Then** transitions match: Draft → Queued → Claimed → Generating Assets → ...

---

### Story 5.2: Review Gate Enforcement

As a **content creator**,
I want **the pipeline to pause at review gates and wait for my approval**,
So that **I can verify quality before expensive operations proceed** (FR52).

**Acceptance Criteria:**

**Given** asset generation completes successfully
**When** status changes to "Assets Ready"
**Then** the pipeline halts
**And** no video generation starts until user approves

**Given** video generation completes successfully
**When** status changes to "Video Ready"
**Then** the pipeline halts (most expensive step: $5-10)
**And** no audio generation starts until user approves

**Given** audio generation completes successfully
**When** status changes to "Audio Ready"
**Then** the pipeline halts
**And** no assembly starts until user approves

**Given** final assembly completes
**When** status changes to "Final Review"
**Then** the pipeline halts before YouTube upload
**And** human review evidence is required for YouTube compliance

---

### Story 5.3: Asset Review Interface

As a **content creator**,
I want **to view and approve generated assets in Notion**,
So that **I can verify image quality before video generation** (FR5).

**Acceptance Criteria:**

**Given** a task is in "Assets Ready" status
**When** I open the Notion page
**Then** I can see all 22 generated asset images (gallery or grid view)
**And** asset URLs are populated in the Assets property

**Given** I review the assets and they look good
**When** I change status to "Assets Approved"
**Then** the task resumes and composite creation begins

**Given** I review the assets and find issues
**When** I change status to "Asset Error" or add notes
**Then** the task is flagged for regeneration
**And** Error Log is updated with my feedback

---

### Story 5.4: Video Review Interface

As a **content creator**,
I want **to review all 18 video clips before audio generation**,
So that **I can verify motion quality before committing to the full video** (FR6).

**Acceptance Criteria:**

**Given** a task is in "Video Ready" status
**When** I open the Notion page
**Then** I can access all 18 video clips (links or embedded)
**And** each clip is playable for review

**Given** I review the videos and they look good
**When** I change status to "Video Approved"
**Then** the task resumes and narration generation begins

**Given** one or more clips have issues
**When** I note which clips need regeneration
**Then** the Error Log records specific clip numbers
**And** partial regeneration can target only failed clips

---

### Story 5.5: Audio Review Interface

As a **content creator**,
I want **to review narration and SFX before final assembly**,
So that **I can verify voice quality and sound design** (FR7).

**Acceptance Criteria:**

**Given** a task is in "Audio Ready" status
**When** I open the Notion page
**Then** I can listen to all 18 narration clips
**And** I can listen to all 18 SFX clips

**Given** I review the audio and it sounds good
**When** I change status to "Audio Approved"
**Then** the task resumes and assembly begins

**Given** narration or SFX has issues
**When** I note specific problems
**Then** the Error Log records which clips need regeneration
**And** the task can be retried for specific audio clips

---

### Story 5.6: Real-Time Status Updates to Notion

As a **content creator**,
I want **Notion to reflect the current task status within seconds**,
So that **I always know what's happening with my videos** (FR53, FR55).

**Acceptance Criteria:**

**Given** a task's status changes in PostgreSQL
**When** the change is committed
**Then** Notion is updated within 5 seconds (NFR-P3)
**And** the Status property reflects the new value

**Given** any status change occurs
**When** Notion is updated
**Then** the "Updated" date property is also refreshed (FR55)
**And** the Notion page shows accurate "last modified" time

**Given** multiple status changes happen rapidly
**When** updates are sent to Notion
**Then** rate limiting (3 req/sec) is respected
**And** the final status is always accurate (eventual consistency)

---

### Story 5.7: Progress Visibility Dashboard

As a **content creator**,
I want **Notion database views filtered by status**,
So that **I can see what's in progress, what needs review, and what's done** (FR54).

**Acceptance Criteria:**

**Given** the Notion database is configured
**When** I view the "Kanban" view
**Then** tasks are organized in 26 columns by status
**And** I can see at a glance: "Card stuck = problem, moving = success"

**Given** I want to see only tasks needing my attention
**When** I open the "Needs Review" filtered view
**Then** only tasks in "Assets Ready", "Video Ready", "Audio Ready", "Final Review" appear

**Given** I want to see all errors
**When** I open the "Errors" filtered view
**Then** only tasks in error states appear
**And** I can see Error Log details

**Given** I want to see completed work
**When** I open the "Published" filtered view
**Then** only tasks with status "Published" appear
**And** YouTube URLs are visible

---

### Story 5.8: Bulk Approve/Reject Operations

As a **content creator**,
I want **to approve or reject multiple tasks at once**,
So that **I can efficiently process a batch of reviews** (FR58).

**Acceptance Criteria:**

**Given** multiple tasks are in "Video Ready" status
**When** I select all of them in Notion
**Then** I can bulk-change status to "Video Approved"
**And** all selected tasks resume processing

**Given** multiple tasks are in error states
**When** I select them and change status to retry
**Then** all selected tasks are re-queued for processing
**And** each task retries from its failure point

**Given** 10 tasks are bulk-approved
**When** the status changes sync
**Then** all 10 are updated in PostgreSQL
**And** workers begin processing all 10 (subject to parallelism limits)

---

## Epic 6: Error Handling & Auto-Recovery

**Goal:** System automatically recovers from transient failures (80%+), provides clear error visibility, and allows manual retry triggers.

### Story 6.1: Transient Failure Detection

As a **system developer**,
I want **the system to distinguish transient failures from permanent ones**,
So that **retryable errors are automatically retried while permanent errors alert humans** (FR27).

**Acceptance Criteria:**

**Given** an API call fails with HTTP 429 (rate limit)
**When** the failure is categorized
**Then** it's marked as "transient" and eligible for retry

**Given** an API call fails with HTTP 500/502/503 (server error)
**When** the failure is categorized
**Then** it's marked as "transient" and eligible for retry

**Given** an API call times out
**When** the failure is categorized
**Then** it's marked as "transient" (network issue likely temporary)

**Given** an API call fails with HTTP 400 (bad request) or 401 (unauthorized)
**When** the failure is categorized
**Then** it's marked as "permanent" (won't succeed on retry)
**And** human intervention is required

**Given** a transient failure occurs
**When** logging the error
**Then** the error includes: error_type, is_transient flag, suggested_action

---

### Story 6.2: Exponential Backoff Retry Logic

As a **system developer**,
I want **failed operations to retry with exponential backoff**,
So that **transient failures have time to resolve without overwhelming APIs** (FR28).

**Acceptance Criteria:**

**Given** a transient failure occurs on attempt 1
**When** retry is scheduled
**Then** retry waits 1 minute before attempt 2

**Given** attempt 2 fails
**When** retry is scheduled
**Then** retry waits 5 minutes before attempt 3

**Given** attempt 3 fails
**When** retry is scheduled
**Then** retry waits 15 minutes before attempt 4

**Given** attempt 4 fails
**When** retry is scheduled
**Then** retry waits 1 hour before final attempt 5

**Given** all 5 attempts fail
**When** retry is exhausted
**Then** the task moves to terminal error state
**And** an alert is triggered (FR32)

---

### Story 6.3: Resume from Failure Point

As a **content creator**,
I want **failed tasks to resume from where they failed, not restart from scratch**,
So that **completed work isn't wasted** (FR29).

**Acceptance Criteria:**

**Given** asset generation completes but video generation fails
**When** the task is retried
**Then** asset generation is skipped (already complete)
**And** video generation resumes from the failed clip

**Given** 10 of 18 video clips generated successfully
**When** clip 11 fails and is retried
**Then** clips 1-10 are not regenerated
**And** generation continues from clip 11

**Given** a task has partial completion metadata
**When** retry begins
**Then** the task reads `completed_steps` from database
**And** only incomplete steps execute

**Given** an idempotent retry occurs (FR50)
**When** a step re-runs on existing files
**Then** files are overwritten (not duplicated)
**And** the result is identical

---

### Story 6.4: Granular Error Status Updates

As a **content creator**,
I want **specific error statuses for each pipeline stage**,
So that **I know exactly what failed without reading logs** (FR30, FR56).

**Acceptance Criteria:**

**Given** asset generation fails
**When** status is updated
**Then** status becomes "Asset Error" (not generic "Error")
**And** the Notion card appears in the error column

**Given** video generation fails
**When** status is updated
**Then** status becomes "Video Error"

**Given** audio generation fails
**When** status is updated
**Then** status becomes "Audio Error"

**Given** YouTube upload fails
**When** status is updated
**Then** status becomes "Upload Error"

**Given** any error status is set
**When** viewing Notion
**Then** the error type is immediately visible (FR56: clarity)

---

### Story 6.5: Detailed Error Logging

As a **system operator**,
I want **comprehensive error logs with timestamp, step, message, and retry count**,
So that **I can diagnose failures quickly** (FR31).

**Acceptance Criteria:**

**Given** an error occurs during processing
**When** the error is logged
**Then** the log entry includes:
- `timestamp` (ISO 8601)
- `task_id` and `channel_id`
- `step` (e.g., "video_generation")
- `error_message` (human-readable)
- `error_type` (e.g., "KlingAPITimeout")
- `retry_attempt` (1-5)
- `is_transient` (bool)

**Given** the task's Error Log property in Notion
**When** an error occurs
**Then** the Error Log is appended with a summary
**And** the summary includes step, message, and retry count

**Given** structured logging is configured (structlog)
**When** errors are logged
**Then** output is JSON format for Railway log aggregation
**And** correlation IDs link related log entries

---

### Story 6.6: Alert System for Terminal Failures

As a **system operator**,
I want **alerts sent to Discord when retries are exhausted**,
So that **I'm notified of failures requiring human intervention** (FR32).

**Acceptance Criteria:**

**Given** a task exhausts all retry attempts
**When** the terminal failure is recorded
**Then** a Discord webhook is triggered within 5 minutes (NFR-R5)
**And** the alert includes: task_id, channel, step, error summary

**Given** YouTube quota is exhausted
**When** the 100% threshold is reached
**Then** an alert is sent immediately
**And** the alert includes quota usage details

**Given** multiple failures occur rapidly
**When** alerts are sent
**Then** alerts are batched (not spammed) - max 1 per minute per error type

**Given** the system is configured with `DISCORD_WEBHOOK_URL`
**When** an alert is triggered
**Then** the `send_alert()` function posts to Discord
**And** alert delivery is logged

---

### Story 6.7: Manual Retry Trigger

As a **content creator**,
I want **to manually trigger retries by changing status in Notion**,
So that **I can re-attempt failed tasks after fixing issues** (FR33).

**Acceptance Criteria:**

**Given** a task is in "Asset Error" status
**When** I change status to "Queued" in Notion
**Then** the task is re-enqueued for processing
**And** retry begins from the failed step

**Given** a task is in "Video Error" status
**When** I change status to "Video Approved" (to retry video gen)
**Then** the task retries video generation only
**And** previously completed steps are skipped

**Given** I add notes to Error Log before retrying
**When** retry runs
**Then** the notes are preserved
**And** new errors are appended (not replaced)

---

### Story 6.8: API Quota Monitoring

As a **system operator**,
I want **real-time tracking of API quota usage**,
So that **I can predict and prevent quota exhaustion** (FR34).

**Acceptance Criteria:**

**Given** a YouTube API call is made
**When** the call completes
**Then** quota units used are recorded in `youtube_quota_usage` table
**And** daily total is updated

**Given** YouTube quota reaches 80% of daily limit
**When** the threshold is crossed
**Then** a WARNING alert is sent
**And** uploads continue but are flagged

**Given** YouTube quota reaches 100%
**When** the threshold is crossed
**Then** an ERROR alert is sent
**And** upload tasks are paused until midnight reset (NFR-I4)

**Given** Gemini API quota is exhausted
**When** asset generation is attempted
**Then** tasks are paused (not failed)
**And** an alert indicates "waiting for quota reset"

---

### Story 6.9: Retry State Visibility

As a **content creator**,
I want **to see retry count and next attempt time for failing tasks**,
So that **I know the system is working on recovery** (FR57).

**Acceptance Criteria:**

**Given** a task is in retry mode
**When** I view the Notion page
**Then** I can see: current retry attempt (e.g., "Attempt 3/5")
**And** I can see: next retry time (e.g., "Retrying in 15 min")

**Given** retry is in progress
**When** the next attempt starts
**Then** the retry count increments
**And** Notion reflects the updated count

**Given** a task is waiting for retry
**When** the wait period is active
**Then** status shows "Retrying" (not stuck in error)
**And** the countdown is visible

---

### Story 6.10: Auto-Recovery Success Rate Tracking

As a **system operator**,
I want **weekly metrics on auto-recovery success rate**,
So that **I can verify the system meets the 80% target** (FR35).

**Acceptance Criteria:**

**Given** transient failures occur throughout the week
**When** the weekly report is generated
**Then** metrics include:
- Total transient failures
- Successfully auto-recovered count
- Auto-recovery rate (target: 80%+)
- Average retries before success

**Given** auto-recovery rate falls below 80%
**When** the weekly report runs
**Then** an alert is triggered
**And** the alert includes failure patterns for investigation

**Given** a task successfully recovers after retry
**When** the recovery is logged
**Then** `auto_recovered: true` is recorded
**And** retry_count is preserved for metrics

---

## Epic 7: YouTube Publishing & Compliance

**Goal:** Approved videos upload to YouTube automatically with proper metadata, OAuth, quota management, and compliance evidence for YouTube Partner Program.

### Story 7.1: YouTube OAuth Setup CLI

As a **system administrator**,
I want **a CLI tool to set up YouTube OAuth for each channel**,
So that **I can authorize YouTube access without exposing credentials** (FR60).

**Acceptance Criteria:**

**Given** a new channel needs YouTube access
**When** I run `python scripts/setup_channel_oauth.py --channel pokechannel1`
**Then** a browser opens for Google OAuth consent
**And** I can authorize the channel's YouTube account

**Given** OAuth consent is granted
**When** the callback is received
**Then** the refresh token is encrypted with Fernet
**And** the encrypted token is stored in the database
**And** the access token is NOT stored (only refresh token)

**Given** I need to re-authorize a channel
**When** I run the setup script again
**Then** the old token is replaced
**And** the new token is encrypted and stored

**Given** two channels have different YouTube accounts
**When** both are set up
**Then** each channel has its own OAuth token (FR60: independent tokens)

---

### Story 7.2: OAuth Token Refresh Automation

As a **system developer**,
I want **OAuth tokens to refresh automatically before expiration**,
So that **uploads never fail due to expired tokens** (FR61, NFR-I5).

**Acceptance Criteria:**

**Given** an access token is needed for YouTube upload
**When** the current access token is expired or missing
**Then** the refresh token is used to obtain a new access token
**And** the new access token is cached in memory (not database)

**Given** an access token expires in less than 5 minutes
**When** a YouTube operation is about to start
**Then** the token is proactively refreshed
**And** the operation uses the fresh token

**Given** a refresh token is invalid or revoked
**When** refresh is attempted
**Then** an alert is sent with "YouTube re-authorization required for {channel}"
**And** upload tasks for that channel are paused

**Given** token refresh succeeds
**When** the new access token is obtained
**Then** no database write occurs (memory only)
**And** logging records the refresh timestamp

---

### Story 7.3: Video Metadata Generation

As a **content creator**,
I want **YouTube video metadata generated from my Notion entry**,
So that **uploads have proper titles, descriptions, and tags** (FR62).

**Acceptance Criteria:**

**Given** a task is ready for YouTube upload
**When** metadata is generated
**Then** Title is taken from Notion Title property
**And** Description includes: summary from Story Direction, credits, channel links

**Given** the channel has configured tags
**When** metadata is generated
**Then** default channel tags are included
**And** topic-specific tags are added based on the Topic property

**Given** the description template exists
**When** description is generated
**Then** placeholders are replaced: {title}, {topic}, {channel_name}
**And** the description follows YouTube best practices (hashtags, links)

**Given** metadata exceeds YouTube limits
**When** validation runs
**Then** title is truncated to 100 characters
**And** description is truncated to 5000 characters
**And** a warning is logged

---

### Story 7.4: Resumable Upload Implementation

As a **system developer**,
I want **YouTube uploads to use resumable upload protocol**,
So that **large files upload reliably even with network interruptions** (FR63).

**Acceptance Criteria:**

**Given** a video file is ready for upload
**When** upload begins
**Then** YouTube's resumable upload API is used
**And** an upload URI is obtained first

**Given** upload is interrupted (network error)
**When** retry is attempted
**Then** upload resumes from the last successful byte position
**And** already-uploaded data is not re-sent

**Given** a 90-second video (approximately 50-100MB)
**When** upload completes
**Then** the video is successfully created on YouTube
**And** a video ID is returned

**Given** upload exceeds 10 minutes
**When** timeout is approached
**Then** progress is logged every 30 seconds
**And** the upload continues (no artificial timeout)

---

### Story 7.5: YouTube URL Retrieval & Notion Update

As a **content creator**,
I want **the YouTube URL written back to Notion after upload**,
So that **I can access my published video directly from the planning database** (FR24, FR25, FR64).

**Acceptance Criteria:**

**Given** YouTube upload completes successfully
**When** the response is received
**Then** the video ID is extracted (e.g., "dQw4w9WgXcQ")
**And** the full URL is constructed: `https://youtube.com/watch?v={video_id}`

**Given** the YouTube URL is available
**When** Notion is updated
**Then** the YouTube URL property is populated (FR25)
**And** the task status changes to "Published"

**Given** the video was uploaded as unlisted or private
**When** the URL is recorded
**Then** the URL is still valid (works with direct link)
**And** the privacy status is noted in Notion

**Given** upload succeeds but Notion update fails
**When** the failure is detected
**Then** the YouTube URL is logged for manual recovery
**And** an alert is sent

---

### Story 7.6: Upload Error Handling

As a **system developer**,
I want **upload failures to retry with exponential backoff**,
So that **transient YouTube API issues don't cause permanent failures** (FR65).

**Acceptance Criteria:**

**Given** YouTube API returns 500/503 error
**When** the error is caught
**Then** retry is scheduled with exponential backoff
**And** the task status shows "Upload Error (Retrying)"

**Given** YouTube API returns 403 (quota exceeded)
**When** the error is caught
**Then** retry is paused until midnight PST (quota reset)
**And** an alert is sent with quota status

**Given** YouTube API returns 400 (bad request)
**When** the error is caught
**Then** the error is marked as permanent
**And** the Error Log includes the API error message
**And** human intervention is required

**Given** upload fails 5 times with transient errors
**When** retries are exhausted
**Then** status becomes "Upload Error" (terminal)
**And** an alert is sent

---

### Story 7.7: YouTube Compliance Enforcement

As a **content creator**,
I want **the system to enforce YouTube Partner Program compliance**,
So that **my channel remains in good standing** (FR66).

**Acceptance Criteria:**

**Given** a video is queued for upload
**When** compliance checks run
**Then** the video is verified as unique (not duplicate content)
**And** upload frequency is checked against channel limits

**Given** two identical videos are attempted for the same channel
**When** the duplicate is detected
**Then** the second upload is blocked
**And** an error is logged: "Duplicate content detected"

**Given** upload frequency exceeds organic patterns (e.g., >3/day)
**When** the threshold is crossed
**Then** a warning is logged
**And** uploads are throttled to maintain natural appearance

**Given** human review was completed before upload
**When** the upload runs
**Then** evidence of human review is attached to audit log
**And** content authenticity metadata is included (July 2025 compliance)

---

### Story 7.8: Channel Privacy Configuration

As a **content creator**,
I want **each channel to have a default privacy setting for uploads**,
So that **I can control whether videos are public, unlisted, or private** (FR67).

**Acceptance Criteria:**

**Given** a channel YAML includes `default_privacy: "unlisted"`
**When** videos are uploaded for that channel
**Then** they're uploaded with privacy status "unlisted"

**Given** a channel YAML includes `default_privacy: "public"`
**When** videos are uploaded
**Then** they're immediately public on YouTube

**Given** a channel YAML omits `default_privacy`
**When** configuration is loaded
**Then** the default is "private" (safest option)
**And** a warning suggests setting explicit privacy

**Given** a specific video needs different privacy
**When** the Notion entry has a Privacy property set
**Then** the per-video privacy overrides channel default

---

### Story 7.9: Human Review Audit Logging

As a **system administrator**,
I want **immutable audit logs for all human review actions**,
So that **I have evidence of human oversight for YouTube compliance** (YouTube Compliance).

**Acceptance Criteria:**

**Given** a user approves a video for upload
**When** the approval action occurs
**Then** an audit log entry is created with:
- `timestamp` (ISO 8601)
- `reviewer_id` (Notion user ID or email)
- `action` ("approved" | "rejected")
- `task_id` and `video_id`
- `notes` (if provided)

**Given** audit log entries exist
**When** modification is attempted
**Then** modifications are blocked (append-only)
**And** the audit table has no UPDATE/DELETE permissions

**Given** audit retention policy is 2 years
**When** logs are older than 2 years
**Then** they're archived (not deleted) for compliance

**Given** a YouTube Partner Program audit is requested
**When** evidence is needed
**Then** audit logs can be exported with complete review history
**And** each video shows: who reviewed, when, and decision

---

## Epic 8: Monitoring, Observability & Cost Tracking

**Goal:** Users have full visibility into system health, per-video costs, success rates, and receive alerts only when human intervention is truly needed.

### Story 8.1: Structured Logging with Correlation IDs

As a **system operator**,
I want **all log entries to use structured JSON format with correlation IDs**,
So that **I can trace a video's journey through the entire pipeline and aggregate logs in Railway**.

**Acceptance Criteria:**

**Given** a task begins processing
**When** log entries are generated
**Then** each entry includes:
- `timestamp` (ISO 8601)
- `correlation_id` (task_id)
- `channel_id`
- `step` (current pipeline step)
- `level` (DEBUG/INFO/WARNING/ERROR/CRITICAL)
- `message` (human-readable)

**Given** structlog is configured
**When** logs are emitted
**Then** output is valid JSON (one object per line)
**And** Railway log aggregation can parse them

**Given** multiple workers process different tasks
**When** logs are reviewed
**Then** filtering by `correlation_id` shows all entries for one video
**And** no log entries are missing the correlation ID

---

### Story 8.2: Per-Video Cost Tracking

As a **content creator**,
I want **the cost of each video tracked by component (Gemini, Kling, ElevenLabs)**,
So that **I understand my production costs and can optimize spending**.

**Acceptance Criteria:**

**Given** an API call is made to Gemini/Kling/ElevenLabs
**When** the call completes
**Then** the cost is recorded in the `video_costs` table:
- `task_id` (FK)
- `component` (gemini_assets, kling_video, elevenlabs_narration, elevenlabs_sfx)
- `cost_usd` (decimal)
- `units_used` (API-specific: tokens, seconds, characters)
- `timestamp`

**Given** a video completes processing
**When** costs are summed
**Then** total cost per video is available
**And** cost breakdown by component is visible

**Given** cost data exists for completed videos
**When** reports are generated
**Then** average cost per video can be calculated
**And** cost trends over time are visible

---

### Story 8.3: Asset URL Population in Notion

As a **content creator**,
I want **asset URLs written to Notion for each generated image, video, and audio file**,
So that **I can access all generated content directly from Notion** (FR48).

**Acceptance Criteria:**

**Given** an asset is generated and saved
**When** storage completes
**Then** the asset URL is recorded in the database
**And** a background job updates the Notion Assets property

**Given** all 22 image assets are generated
**When** the asset URLs are populated
**Then** the Notion page shows all 22 image links
**And** each link is accessible (valid URL)

**Given** video clips and audio files are generated
**When** the assets are stored
**Then** video clip URLs (18) and audio URLs (18+18) are recorded
**And** these are accessible from the Notion page

---

### Story 8.4: Cloudflare R2 Storage Integration

As a **system administrator**,
I want **channels configured for R2 storage to upload assets to Cloudflare R2**,
So that **large asset libraries don't consume Notion storage limits** (FR47).

**Acceptance Criteria:**

**Given** a channel YAML includes `storage_strategy: "r2"` with R2 credentials
**When** assets are generated for that channel
**Then** assets are uploaded to the configured R2 bucket
**And** public URLs are stored in the database

**Given** R2 upload fails
**When** the error is caught
**Then** retry logic applies (same as other API failures)
**And** the task doesn't fail permanently on transient R2 errors

**Given** R2 storage is used
**When** assets are accessed
**Then** URLs are publicly accessible (or signed if private bucket)
**And** Notion displays the R2-hosted content

---

### Story 8.5: Temporary File Cleanup

As a **system administrator**,
I want **completed task directories cleaned up daily**,
So that **disk space doesn't grow unbounded** (FR49).

**Acceptance Criteria:**

**Given** a task has been "Published" for more than 7 days
**When** the daily cleanup job runs
**Then** the task's workspace directory is deleted
**And** only the database records and URLs remain

**Given** a task is still in progress or recently completed
**When** cleanup runs
**Then** the task's files are NOT deleted
**And** files remain available for review

**Given** a task is in error state
**When** cleanup runs
**Then** error task files are preserved (for debugging)
**And** cleanup skips tasks with status in error states

**Given** cleanup runs
**When** files are deleted
**Then** a log entry records what was deleted
**And** the count of cleaned directories is reported

---

### Story 8.6: Weekly Success Rate Calculation

As a **system operator**,
I want **weekly metrics on pipeline success, auto-recovery, and failure patterns**,
So that **I can monitor system health and identify issues** (FR59).

**Acceptance Criteria:**

**Given** video processing occurs throughout the week
**When** the weekly report is generated (Sunday midnight)
**Then** metrics include:
- Total videos processed
- Success rate (Published / Total)
- Average processing time
- Auto-recovery rate
- Failure breakdown by step

**Given** success rate falls below 90%
**When** the weekly report runs
**Then** an alert is triggered
**And** the alert includes failure patterns

**Given** metrics are calculated
**When** data is stored
**Then** historical weekly metrics are preserved
**And** trends can be analyzed over time

---

### Story 8.7: Health Check Endpoint

As a **system operator**,
I want **a health check endpoint that reports system status**,
So that **Railway and external monitors can verify the system is operational** (NFR-R1).

**Acceptance Criteria:**

**Given** the FastAPI application is running
**When** GET `/health` is called
**Then** a 200 OK response is returned within 500ms
**And** the response includes:
- `status`: "healthy" | "degraded" | "unhealthy"
- `database`: "connected" | "error"
- `workers`: count of active workers
- `queue_depth`: pending task count

**Given** the database is unreachable
**When** health check runs
**Then** status is "unhealthy"
**And** `database` field shows "error"

**Given** no workers have checked in for 5 minutes
**When** health check runs
**Then** status is "degraded"
**And** an alert is triggered

**Given** all systems are operational
**When** health check runs
**Then** status is "healthy"
**And** the endpoint completes within 500ms (no expensive queries)

---

### Story 8.8: Cost Dashboard & Reporting

As a **content creator**,
I want **a summary view of costs per channel and per time period**,
So that **I can track spending and budget appropriately**.

**Acceptance Criteria:**

**Given** cost data exists in the database
**When** I view the cost summary (via API or Notion rollup)
**Then** I can see:
- Total cost this week/month
- Cost breakdown by channel
- Cost breakdown by component
- Average cost per video

**Given** I want to see cost trends
**When** historical data is queried
**Then** weekly and monthly cost totals are available
**And** trends show whether costs are increasing/decreasing

**Given** a specific channel's costs
**When** I filter the view
**Then** only that channel's costs are shown
**And** I can compare channels' efficiency

**Given** cost data is available
**When** the weekly report runs
**Then** cost summary is included in the report
**And** alerts trigger if costs exceed configured thresholds
