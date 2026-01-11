# Project Context Analysis

## Requirements Overview

**Functional Requirements:**

The PRD defines **67 functional requirements** organized into 8 capability areas:

1. **Content Planning & Management (FR1-FR7):** Notion database entry creation, batch video queuing, channel selection, asset/video/audio review gates with approval workflows

2. **Multi-Channel Orchestration (FR8-FR16):** Channel configuration file management, channel isolation, per-channel voice selection, branding, storage strategy, parallel processing across channels, YouTube OAuth per channel, channel addition without code changes

3. **Video Generation Pipeline (FR17-FR26):** End-to-end 8-step automation (asset generation → composites → video → audio → SFX → assembly → YouTube upload), preservation of existing CLI scripts, "Smart Agent + Dumb Scripts" pattern continuity

4. **Error Handling & Recovery (FR27-FR35):** Transient failure detection, exponential backoff retry (1min → 5min → 15min → 1hr), resume from failure point, granular error statuses, detailed error logging, alert system, manual retry triggers, API quota monitoring, 80%+ auto-recovery target

5. **Queue & Task Management (FR36-FR43):** Webhook endpoint for Notion events, PostgreSQL-based persistent queue, worker pool management, parallel task execution (12 Gemini, 5-8 Kling, 6 ElevenLabs concurrent), priority queue management, round-robin channel scheduling, rate limit aware task selection, state persistence across restarts

6. **Asset & Storage Management (FR44-FR50):** Backend filesystem structure (`/workspaces/{channel_id}/{task_id}/`), asset subfolder organization, Notion storage (default), Cloudflare R2 storage (post-MVP optional), asset URL population in Notion, temporary file cleanup, idempotent operations

7. **Status & Progress Monitoring (FR51-FR59):** 26 workflow statuses with review gates, review gate enforcement, real-time Notion status updates, progress visibility dashboard, error state clarity, retry state visibility, bulk status operations, 95% success rate tracking

8. **YouTube Integration (FR60-FR67):** YouTube OAuth per channel, token refresh automation, video metadata generation, upload via YouTube Data API, YouTube URL retrieval and population, upload error handling, YouTube compliance enforcement, channel privacy configuration

**Non-Functional Requirements:**

The PRD defines **28 non-functional requirements** across 5 categories:

- **Performance (5 NFRs):** ≤2 hours per video (90th percentile), 20 videos concurrent processing, Notion API <5s response, webhook <500ms response, worker <30s startup

- **Security (5 NFRs):** API key protection (environment variables/secrets manager), YouTube OAuth token encryption, webhook signature validation, database access control, secure asset storage

- **Scalability (5 NFRs):** 10 channels MVP → 20 channels without architectural changes, 500+ task queue capacity, linear worker scaling up to 10 workers, API rate limit elasticity via configuration, 10,000 completed videos without performance degradation

- **Integration (6 NFRs):** Operational when 1 of 6 external services unavailable, Notion API 3 req/sec compliance, Kling 10-minute timeout tolerance, Gemini quota exhaustion recovery, YouTube OAuth auto-refresh, 100% integration error logging

- **Reliability (7 NFRs):** 99% orchestrator uptime, 80% auto-recovery from transient failures, zero task loss across restarts, idempotent operations, 100% terminal failure alerts within 5 minutes, status/state synchronization, graceful degradation under rate limits

**Scale & Complexity:**

- **Project complexity:** Medium
- **Primary technical domain:** Content Automation / AI Service Orchestration
- **Estimated architectural components:** 15-20 major components
  - FastAPI orchestrator (webhook endpoints, immediate queue)
  - Python worker pool (background processing)
  - PostgreSQL database (persistent queue + state)
  - Notion integration layer (read/write API, webhook handling)
  - Multi-channel configuration system
  - 7 existing CLI scripts (preserved, no modifications)
  - YouTube integration (OAuth, upload API)
  - Storage abstraction (Notion vs R2)
  - Error handling & retry system
  - Alert system (Slack/email)
  - Rate limit tracking (global + per-channel)
  - Asset management (filesystem structure)
  - Status progression state machine (26 states)
  - Cost tracking system (post-MVP)
  - Monitoring/analytics dashboard (post-MVP)

## Technical Constraints & Dependencies

**Architectural Constraints:**

1. **"Smart Agent + Dumb Scripts" Pattern Preservation:**
   - Existing 7 CLI scripts (`generate_asset.py`, `create_composite.py`, `generate_video.py`, `generate_audio.py`, `generate_sound_effects.py`, `assemble_video.py`, `youtube_auth.py`) must remain unchanged
   - Scripts are stateless, single-purpose, receive complete inputs
   - Workers handle all file I/O, data extraction, prompt combination, orchestration
   - Pattern proven successful in current CLI pipeline, must extend to platform scale

2. **Filesystem as State:**
   - No databases for pipeline execution state (only queue management)
   - Assets stored in organized filesystem: `/workspaces/{channel_id}/{task_id}/`
   - Idempotent operations allow safe re-execution
   - Filesystem serves as source of truth for asset existence

3. **Multi-Channel from Day 1:**
   - Architecture cannot be single-channel initially and retrofitted later
   - Channel isolation, rate limiting, OAuth management, queue fairness required from MVP
   - Business model depends on testing multiple niches simultaneously

4. **Review Gates Non-Negotiable:**
   - Quality control prevents catastrophic cost waste
   - System must pause at "Assets Ready", "Video Ready", "Audio Ready"
   - Workflow-as-config automation (skipping gates) is post-MVP enhancement only

**External Service Dependencies:**

1. **Google Gemini 2.5 Flash (Image Generation):**
   - Cost: $0.039/image, ~$0.86 per video (22 images)
   - Rate limits: Daily quota (exact limit from API dashboard)
   - Dependency: Asset generation (Step 1 of pipeline)
   - Risk: Quota exhaustion blocks entire pipeline
   - Mitigation: Quota monitoring, graceful pause until midnight reset

2. **Kling 2.5 via KIE.ai (Video Generation):**
   - Cost: $2.36 per video (18 clips @ ~$0.13 each)
   - Rate limits: Concurrent generation max (10 typical)
   - Timeout: 2-5 minutes typical, up to 10 minutes possible
   - Dependency: Video generation (Step 3 of pipeline)
   - Risk: Slowest pipeline step, highest cost component (75% of total)
   - Mitigation: 10-minute timeout, 5-8 concurrent limit to respect rate limits

3. **ElevenLabs v3 (Audio & SFX):**
   - Cost: $0.05 per video (narration + SFX)
   - Rate limits: Concurrent requests (6 typical)
   - Dependency: Audio generation (Step 4), SFX generation (Step 5)
   - Risk: Low cost but still subject to rate limits
   - Mitigation: 6 concurrent limit, fast execution (<1 minute per clip)

4. **Notion API (Orchestration Hub):**
   - Rate limits: 3 requests/second (hard limit, 5-minute ban if exceeded)
   - Dependency: Task reading, status updates, asset URL population
   - Integration: Webhooks (inbound), REST API (read/write)
   - Risk: Rate limit ban blocks all status updates, user visibility lost
   - Mitigation: Request queue with rate limit throttling, failed updates logged but don't block processing

5. **YouTube Data API (Video Publishing):**
   - Rate limits: 10,000 quota units/day (upload = 1,600 units, ~6 uploads/day per project)
   - OAuth: Per-channel tokens, 60-minute validity
   - Dependency: Video upload (Step 7 of pipeline)
   - Risk: Quota exhaustion prevents publishing, OAuth expiration blocks uploads
   - Mitigation: Token auto-refresh at 50 minutes, quota monitoring, multi-project distribution for scale

6. **catbox.moe (Image Hosting for Kling):**
   - Cost: Free
   - Reliability: Public service, no SLA
   - Dependency: Composite image upload for Kling video generation
   - Risk: Service downtime blocks video generation
   - Mitigation: Retry with backoff, fallback to alternative hosting if persistent failure

7. **Cloudflare R2 (Optional Asset Storage - Post-MVP):**
   - Cost: $0.015/GB storage, $0.36/million Class A operations
   - Dependency: Optional alternative to Notion storage for performance at scale
   - Risk: Additional configuration complexity
   - Benefit: Faster YouTube uploads, external asset sharing

**Technology Stack Dependencies:**

- **Python 3.10+:** Required for AI SDK compatibility, async/await support
- **FastAPI:** Orchestrator framework (webhook endpoints, async request handling)
- **PostgreSQL:** Persistent queue, worker state tracking
- **FFmpeg 8.0.1:** Video trimming, audio mixing, concatenation (requires persistent compute, not serverless)
- **Pillow (PIL):** Image compositing and manipulation
- **python-dotenv:** Environment variable management for API keys
- **pyjwt:** JWT token generation for KIE.ai authentication
- **requests:** HTTP client for API calls and uploads

**Research-Informed Constraints:**

From **Notion API Integration Research:**
- 3 requests/second rate limit (critical constraint)
- Webhook HMAC validation for security
- Hierarchical database structure (Channel pages → Task sub-pages → Assets + Logs)
- Pagination required for bulk operations (max 100 items per response)

From **AI Service Pricing Research:**
- Gemini: $0.039/image → $0.86/video (22 images)
- Kling: $2.36/video (18 clips, 75% of total cost)
- ElevenLabs: $0.05/video (narration + SFX)
- **Total realistic cost: $3-4/video** (not $6-13 as initially estimated in PRD - PRD may include contingency)
- Cost structure enables profitable business model with YouTube ad revenue

From **Market Analysis Research:**
- **AI video generation market: $614.8M (2024) → $2.56B (2032)** - 20.6% CAGR validates market opportunity
- **180% faster growth with human-AI hybrid workflows** - justifies review gate architecture
- **82-93% ROI for AI video automation** - business case for system investment
- **80-90% failure rate for pure automation** - justifies 95% success target as aspirational

From **YouTube Compliance Research:**
- **July 15, 2025 policy update:** Inauthentic content restrictions, human involvement required
- **API quota: 10,000 units/day** - video upload = 1,600 units (~6 uploads/day per project)
- **Multi-channel risk:** Content duplication across channels violates policies
- **Compliance requirement:** Videos must be unique per channel, organic upload pace, human oversight

## Cross-Cutting Concerns Identified

1. **Rate Limiting:** All external APIs have rate limits (Notion 3 req/sec, Kling concurrent max, Gemini daily quotas, YouTube 10k quota/day) - requires global coordination across workers and channels

2. **State Management:** Queue state, task state, worker state, rate limit counters, OAuth tokens, retry history - must survive restarts and be consistent across workers

3. **Error Recovery:** Auto-retry with exponential backoff applies to every pipeline step - shared retry logic needed across all services

4. **Multi-Tenancy:** Channel isolation requires careful design - failures, rate limits, OAuth tokens, storage, queue fairness must all be channel-aware

5. **Observability:** User needs real-time visibility into queue depth, bottlenecks, success rates, errors - requires comprehensive status updates and logging

6. **Cost Management:** $3-4 per video target must be maintained at scale - cost tracking and optimization critical for business viability

7. **Compliance:** YouTube's July 2025 policies require human oversight - review gates architecturally enforced, not optional

8. **Security:** API keys, OAuth tokens, user content - secrets management and access control pervade entire system

## Architectural Challenge Summary

**What Makes This Architecturally Complex:**

1. **Hybrid Architecture:** Preserving CLI simplicity while adding SaaS orchestration complexity
2. **Multi-Channel Orchestration:** Channel isolation, fairness, rate limit coordination, OAuth management from MVP
3. **External Service Coordination:** 6 external APIs with different rate limits, timeouts, quotas, failure modes
4. **Cost Optimization:** $3-4/video target requires careful parallelism tuning (don't waste Kling credits on bad assets)
5. **Autonomous Operation:** 95% success rate, 80% auto-recovery targets demand sophisticated error handling
6. **State Management:** Queue persistence, retry tracking, rate limit counters, OAuth tokens - must survive restarts
7. **Compliance Enforcement:** YouTube policies architecturally enforced, not feature add-ons

**Critical Success Factors:**

1. Multi-channel orchestration works from MVP (cannot retrofit)
2. Review gates prevent cost waste (quality control before expensive steps)
3. Auto-retry achieves 80%+ recovery (reduces manual intervention burden)
4. Rate limit coordination prevents API bans (system-wide coordination)
5. State persistence across restarts (zero task loss, resume from failure)
6. Cost per video stays at $3-4 (no scaling cost increases)

---
