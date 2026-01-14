---
stepsCompleted: [1, 2, 3, 4, 7, 8, 9, 10, 11]
inputDocuments:
  - "_bmad-output/planning-artifacts/research/technical-notion-api-integration-research-2026-01-08.md"
  - "_bmad-output/planning-artifacts/research/technical-ai-service-pricing-limits-alternatives-research-2026-01-08.md"
  - "_bmad-output/planning-artifacts/research/market-ai-video-generation-industry-costs-roi-research-2026-01-09.md"
  - "_bmad-output/planning-artifacts/research/domain-youtube-automation-multi-channel-compliance-research-2026-01-09.md"
  - "_bmad-output/analysis/brainstorming-session-2026-01-04.md"
  - "_bmad-output/analysis/brainstorming-session-2026-01-07.md"
  - "docs/project-structure.md"
  - "docs/existing-documentation-inventory.md"
  - "docs/user-provided-context.md"
  - "docs/technology-stack.md"
  - "docs/architecture-patterns.md"
  - "docs/comprehensive-analysis-main.md"
  - "docs/source-tree-analysis.md"
  - "docs/development-guide.md"
  - "docs/architecture.md"
  - "docs/project-overview.md"
  - "docs/index.md"
workflowType: 'prd'
lastStep: 11
briefCount: 0
researchCount: 4
brainstormingCount: 2
projectDocsCount: 11
---

# Product Requirements Document - ai-video-generator

**Author:** Francis
**Date:** 2026-01-09

## Executive Summary

### Product Vision

The ai-video-generator project currently provides a successful CLI automation pipeline for creating photorealistic AI-generated documentary videos. Individual projects (Pokemon documentaries) are produced through an 8-step workflow that combines Google Gemini (image generation), Kling AI (video animation), and ElevenLabs (audio/SFX), orchestrated by AI agents following the "Smart Agent + Dumb Scripts" architectural pattern.

This PRD defines the evolution from **single-project pipeline** to **multi-channel YouTube automation platform**, enabling content creators to manage video production across multiple YouTube channels through Notion as a centralized content planning hub.

**The Transformation:**

- **From:** Manual, sequential workflow producing one 90-second documentary at a time (~90-120 minutes, $6-13 per video)
- **To:** Automated, parallel content factory producing 10-20 videos/day across multiple YouTube channels, managed through Notion databases

**Target Users:**
- Content creators managing multiple YouTube channels
- Teams producing high-volume AI-generated video content
- Creators seeking to scale production while maintaining quality and YouTube compliance

### What Makes This Special

**Unique Value Proposition:**

Most YouTube automation solutions focus on either content generation OR channel management. This system uniquely combines both by:

1. **Architectural Continuity** - Extends the proven "Smart Agent + Dumb Scripts" pattern with a Notion orchestration layer, rather than rebuilding from scratch

2. **Horizontal Scaling Economics** - Maintains the existing $6-13 per video cost structure while enabling 10-20x throughput through parallel processing

3. **Familiar Creator Interface** - Content teams plan in Notion (a tool they already use), not through CLI commands or custom dashboards

4. **Compliance-First Design** - YouTube's multi-channel policies are strict; this system architecturally enforces compliance rules rather than treating them as an afterthought

5. **Intelligent Orchestration** - The system reads Notion project queues, triggers appropriate pipeline steps, manages dependencies, and updates status—allowing creators to focus on planning rather than execution

**The "Finally!" Moment:**

Content creators will say: *"Finally, I can map out my entire multi-channel content calendar in Notion, and the videos generate automatically while respecting YouTube's rules. I'm not managing file folders or running terminal commands anymore."*

## Project Classification

**Technical Type:** CLI Tool (existing) + SaaS Platform Capabilities (new)
**Domain:** General - Content Automation
**Complexity:** Medium
**Project Context:** Brownfield - Extending existing system

**Classification Rationale:**

The existing project is a **CLI automation toolkit** with 7 Python scripts orchestrated by AI agents. The new features add **SaaS/platform characteristics**:

- Multi-tenant support (multiple YouTube channels)
- External integration (Notion API, YouTube API)
- Queue management and scheduling
- Status tracking and workflow orchestration

**Complexity Assessment: Medium** because:
- Integration complexity (Notion API, YouTube Data API, YouTube Upload API)
- Multi-channel orchestration and state management
- Compliance requirements (YouTube policies, API rate limits)
- NOT high complexity because the domain is not regulated (not healthcare, fintech, etc.)

**Existing Architecture Patterns to Preserve:**

From the project documentation, these patterns must be respected in the new features:

- **"Smart Agent + Dumb Scripts"** - Agents orchestrate, scripts execute single tasks
- **Filesystem as State** - No databases for core pipeline state
- **Complete Inputs** - Scripts receive fully-formed arguments, no file reading
- **Idempotent Operations** - Re-running steps safely overwrites outputs
- **Single Responsibility** - Each script does one thing well

**New Architectural Additions Required:**

- **Notion Integration Layer** - Read project queues, write status updates
- **Channel Configuration Management** - Per-channel settings (voice IDs, branding, parameters)
- **Orchestration Service** - Poll Notion, trigger pipelines, manage queues
- **YouTube Integration** - Upload completed videos, manage channel compliance

## Success Criteria

### User Success

**Primary User:** Francis (content creator managing multiple YouTube channels)

**User Success Definition:** Zero manual intervention after planning phase, with error alerts only when system cannot auto-recover.

**Measurable User Success Metrics:**

1. **Time Investment Per Video:**
   - Planning time: 5-10 minutes (add video details to Notion database)
   - Execution monitoring: 0 minutes (unless error alert received)
   - **Target: 95%+ videos complete without user intervention**

2. **End-to-End Automation:**
   - User adds Notion database entry with video requirements
   - System automatically: generates assets → creates composites → generates videos → produces audio/SFX → assembles final video → uploads to YouTube
   - User only intervenes on error alerts (API failures, compliance violations, auto-retry exhaustion)
   - **Target: Complete automation from Notion entry to published YouTube video**

3. **The "Aha!" Moment:**
   - User plans 10 videos in Notion on Monday morning
   - By Friday, all 10 videos are live on appropriate YouTube channels
   - User never opened terminal, ran scripts, or managed file folders
   - **Target: Week-long autonomous operation without manual pipeline management**

4. **Error Transparency:**
   - When errors occur (API timeouts, rate limits, service failures), system alerts user with context
   - User can see which step failed and why
   - System provides actionable information for intervention
   - **Target: 100% error visibility with clear remediation steps**

### Business Success

**Business Model:** Personal automation tool for scaling YouTube content production

**3-Month Success Metrics:**
- Successfully managing 3-5 YouTube channels through single Notion workspace
- Generating 25-50 videos/week consistently
- Maintaining $6-13 per video cost structure
- 90%+ success rate with auto-retry handling most failures

**12-Month Success Metrics:**
- **Primary Target: 100 videos/week across multiple channels**
- Managing 5-10 YouTube channels with channel-specific configurations
- Total cost: $600-1,300/week in AI service costs (predictable, scalable economics)
- Time savings: 150-200 hours/week compared to manual pipeline execution
- 95%+ success rate with minimal manual intervention

**Key Business Metric:**
- **Videos successfully published per week** - Single number checked weekly to validate system is delivering on scaling promise

### Technical Success

**Reliability Target: 95% success rate with auto-retry**

**Technical Success Metrics:**

1. **Reliability:**
   - 95% of videos complete successfully from Notion entry to YouTube upload
   - Remaining 5% auto-retry with exponential backoff
   - Alerts sent only when auto-retry exhausted or unrecoverable errors occur
   - **Measurement: Track success rate per week, per channel**

2. **Auto-Recovery:**
   - Automatic retry logic for transient failures (API timeouts, rate limits, network issues)
   - Exponential backoff prevents API ban (e.g., retry after 1min, 5min, 15min, 1hr)
   - Persistent state allows resume from failure point (don't regenerate completed assets)
   - **Target: 80%+ of failures auto-recover without user intervention**

3. **Performance:**
   - Parallel video generation (multiple videos processing simultaneously)
   - Respect API rate limits (Gemini, Kling, ElevenLabs, YouTube)
   - Queue management handles priority and sequencing
   - **Target: Process 20+ videos/day (to support 100/week goal with buffer)**

4. **Multi-Channel Management:**
   - Channel-specific configurations (voice IDs, branding, upload settings)
   - Isolated channel state (one channel's failures don't block others)
   - YouTube compliance rules enforced per channel
   - **Target: Support 5-10 channels without configuration conflicts**

5. **System Uptime:**
   - Continuous operation (polling Notion for new entries)
   - Graceful degradation (if Kling is down, queue videos for later)
   - State persistence across restarts
   - **Target: 99% uptime for orchestration service**

### Measurable Outcomes

**Success means achieving these concrete outcomes:**

1. **User Experience:**
   - Francis plans videos in Notion, never touches terminal/CLI
   - Error alerts only (95%+ videos need zero intervention)
   - Multi-channel management from single interface

2. **Business Impact:**
   - 100 videos/week production capacity
   - $600-1,300/week predictable costs
   - 150-200 hours/week time savings vs manual execution

3. **Technical Performance:**
   - 95% success rate with auto-retry
   - 80%+ auto-recovery from transient failures
   - Support 5-10 YouTube channels simultaneously
   - Process 20+ videos/day with parallel execution

4. **Quality Maintenance:**
   - Same output quality as current single-project pipeline (90-second documentaries, 1080p, professional narration)
   - Cost per video stays at $6-13 (no scaling cost increases)
   - YouTube compliance maintained (no policy violations)

**What makes this successful:** The system works when Francis can scale from producing one Pokemon documentary at a time to managing a multi-channel content operation—without changing how videos are made, just how they're orchestrated.

## Product Scope

### MVP - Minimum Viable Product

**What must work for this to be useful:**

1. **Notion Integration:**
   - Read video project entries from Notion database
   - Parse project metadata (channel, topic, status, requirements)
   - Write status updates back to Notion (queued → generating assets → generating video → generating audio → assembling → uploading → published)
   - Track errors and completion states

2. **Multi-Channel Support:**
   - Channel configuration management (voice IDs, branding parameters, YouTube credentials)
   - Channel-specific settings stored in config files
   - Isolated channel operations (failures in one channel don't block others)
   - Support 5-10 YouTube channels from day one

3. **Full Pipeline Automation:**
   - Execute complete 8-step pipeline without manual intervention:
     - Asset generation (Gemini) - respecting existing "Global Atmosphere + Asset Prompt" pattern
     - Composite creation (16:9 for Kling)
     - Video generation (Kling) - with motion prompts
     - Audio generation (ElevenLabs) - with channel-specific voice IDs
     - Sound effects generation (ElevenLabs)
     - Final assembly (FFmpeg) - trim, mix, concatenate
     - YouTube upload - via YouTube Data/Upload API

4. **Auto-Retry with Exponential Backoff:**
   - Detect transient failures (timeouts, rate limits, network errors)
   - Retry with backoff: 1min → 5min → 15min → 1hr
   - Resume from failure point (don't regenerate completed steps)
   - Alert user only after retry exhaustion or unrecoverable errors
   - **Target: 95% success rate, 80%+ auto-recovery**

5. **Error Alerting:**
   - Alert mechanism (Slack webhook, email, Notion status update)
   - Error context (which step failed, why, what was attempted)
   - Actionable information for manual intervention
   - Error logs for debugging

6. **Queue Management:**
   - Process multiple videos in parallel (respect API rate limits)
   - Handle priority/sequencing
   - State persistence (survive restarts without losing queue)
   - Prevent duplicate processing

**MVP Success Criteria:**
- Successfully generate and upload one complete video per channel (5 channels = 5 videos)
- Demonstrate end-to-end Notion → YouTube automation
- Achieve 90%+ success rate (95% is post-MVP tuning target)
- Handle at least one auto-retry scenario successfully

### Growth Features (Post-MVP)

**What makes it scale to 100 videos/week:**

1. **Performance Optimization:**
   - Tune parallel processing limits (how many simultaneous Kling jobs?)
   - Optimize API usage patterns
   - Reduce bottlenecks in asset generation
   - **Target: Scale from 20 videos/day to 100 videos/week capacity**

2. **Advanced Queue Management:**
   - Priority levels (urgent videos jump queue)
   - Deadline-aware scheduling
   - Channel capacity balancing
   - Smart retry scheduling (don't retry all failures simultaneously)

3. **Custom Branding Per Channel:**
   - Channel-specific intro/outro videos
   - Custom overlay templates
   - Brand-specific asset generation styles
   - Thumbnail templates

4. **Analytics & Reporting:**
   - Dashboard showing videos generated per channel
   - Cost tracking (API usage by service, by channel)
   - Success rate monitoring
   - Performance metrics (average generation time, failure patterns)

5. **YouTube Optimization:**
   - Smart scheduling (optimal upload times per channel)
   - Auto-generated descriptions (SEO-optimized)
   - Tag suggestions based on content
   - Playlist management

### Vision (Future)

**Dream features for maximum automation:**

1. **A/B Testing:**
   - Generate multiple video variants (different styles, narration tones)
   - Track performance (views, engagement)
   - Auto-optimize based on results

2. **Automated Thumbnail Generation:**
   - Generate eye-catching thumbnails from video assets
   - A/B test thumbnail variants
   - Auto-select highest-performing style

3. **Cross-Channel Content Repurposing:**
   - Generate short-form content (YouTube Shorts, TikTok) from long-form videos
   - Adapt content style for different channel audiences
   - Maintain consistent branding across formats

4. **Advanced Content Planning:**
   - AI-assisted story generation (reduce manual planning time)
   - Trend detection (suggest timely topics)
   - Series planning (arc multiple videos across weeks)

5. **Monetization Analytics:**
   - Revenue tracking per video, per channel
   - ROI analysis (production cost vs ad revenue)
   - Optimize content strategy based on profitability

## User Journeys

### Journey 1: Francis as Content Planner - The Monday Morning Content Sprint

**Monday, 9:00 AM. Coffee in hand, inspiration flowing.**

Francis opens Notion and navigates to his "Video Production Queue" database. He's been thinking about content all weekend and has 10 solid ideas across three channels: five philosophy videos, three history deep-dives, and two science explainers.

He starts adding entries, typing quickly:

**Row 1:**
- Title: "Stoicism and Modern Anxiety"  
- Channel: Philosophy Matters
- Topic: "Exploring how Marcus Aurelius's teachings on controlling what you can control apply to modern workplace stress"
- Story Direction: "Use Meditations quotes, contrast ancient Rome with modern offices, calming tone"
- Status: Draft

He continues through all 10 videos - each takes about 5 minutes to flesh out the concept. By 9:50 AM, he has his full week mapped out in Notion.

**The moment of activation:** Francis reviews his 10 entries one last time, then batch-selects them all and changes Status from "Draft" to "Queued". He hits save and closes his laptop.

**Tuesday afternoon.** Francis opens Notion to check progress. The status columns are alive:
- 3 videos show "Assets Ready" 
- 4 videos show "Generating Assets"
- 2 videos show "Generating Video" 
- 1 video shows "Video Ready"

He clicks into "Stoicism and Modern Anxiety" - status is "Assets Ready". The system has generated 22 images (Marcus Aurelius character, Roman settings, modern office environments). He reviews them quickly in the linked asset folder. They look great. He changes the status to "Approved - Assets" and the system immediately shifts to "Generating Video".

**Wednesday morning.** More videos hit review points. Francis spends 15 minutes approving assets and videos across multiple entries. Everything is progressing smoothly.

**Thursday, 2:00 PM.** Francis gets a Slack notification: "⚠️ Error: Video Generation Failed - 'Epictetus on Freedom'". He opens Notion, sees the error status, and reads the error log: "Kling API timeout after 3 retries". He clicks a checkbox to retry, and the system requeues the video generation.

**Friday evening.** Francis opens Notion to see his week's work:
- 8 videos show "✅ Published" with YouTube URLs populated
- 1 video shows "Uploading" (will finish in 10 minutes)
- 1 video (the Kling timeout) shows "Video Ready" - he approves it and it moves to assembling

**The breakthrough:** Francis realizes he just produced nearly 10 professional documentaries in one week while only spending about 2 hours total on review and approvals. In the old workflow, this would have consumed 15-20 hours of terminal commands and manual orchestration.

He copies the YouTube URLs, schedules social media posts, and starts planning next week's 10 videos. He's not just keeping up anymore - he's scaling.

### Journey 2: Francis as System Operator - Responding to the Friday Crisis

**Friday, 11:00 AM. Panic notification.**

Francis is in the middle of lunch when his phone buzzes with a Slack alert: "⚠️ CRITICAL: 5 videos stuck in 'Error: Asset Generation Failed' - Gemini API quota exceeded"

He opens his laptop and navigates to Notion. The Production Queue shows a problem:
- 5 videos all failed at asset generation
- Error logs all say: "Gemini API quota exceeded - daily limit reached"

**The investigation:** Francis checks his Gemini API dashboard. He's hit the daily quota earlier than expected because he queued 15 videos this week instead of his usual 10. The quota resets at midnight.

**The decision:** He has two choices:
1. Wait until midnight and let auto-retry handle it
2. Manually bump some videos to "High Priority" so they process first when quota resets

He selects the 3 most time-sensitive videos and changes Priority to "High". The system will process these first when the quota resets.

**Midnight passes.** Francis wakes up Saturday morning to check his phone. Slack notification: "✅ Auto-retry successful - 5 videos resumed asset generation". The high-priority videos are already at "Generating Video" stage.

**The resolution:** By Saturday afternoon, all 5 videos have caught up. Francis learns to stagger his queuing throughout the week to avoid quota issues. He adds a new Notion property: "Queue Date" to better manage API limits.

**What this journey reveals:** Francis needs visibility into API quotas, smart retry logic, clear error messages, and the ability to prioritize when things go wrong. The system handled 80% of the problem (auto-retry), but he needed control over the 20% that required judgment.

### Journey 3: Francis as Channel Manager - Setting Up "Daily Stoic"

**Sunday afternoon. New channel launch.**

Francis has decided to launch a fourth YouTube channel: "Daily Stoic" - short, punchy philosophy videos with a different style than his main Philosophy Matters channel. Different voice, different pacing, different branding.

He opens his terminal and navigates to the project config directory. There's a `channels.yaml` file that defines all channel configurations. He duplicates the "Philosophy Matters" entry and starts editing:

```yaml
- channel_id: "daily-stoic"
  youtube_channel: "UC_DailyStoicXYZ"
  elevenlabs_voice_id: "EXAo8TGb3Xn2kVqGSz8H"  # Different voice - more energetic
  brand_style: "minimalist"
  video_length_target: 60  # Shorter than usual 90s
  intro_template: "assets/branding/daily-stoic-intro.mp4"
  outro_template: "assets/branding/daily-stoic-outro.mp4"
```

He saves the config file. Now he needs to set up YouTube API credentials for this new channel.

**YouTube OAuth dance:** Francis runs a CLI command: `python scripts/youtube_auth.py --channel daily-stoic`

A browser window opens, he logs into his "Daily Stoic" YouTube account, grants permissions, and the system saves the OAuth token. The terminal confirms: "✅ Channel 'daily-stoic' authenticated and ready"

**Testing the setup:** Francis goes to Notion and creates a test video:
- Title: "Marcus Aurelius on Anger - 60 Second Wisdom"
- Channel: Daily Stoic (new option appears in dropdown!)
- Topic: "Quick Stoic lesson on managing anger"
- Status: Queued

He watches the status progress over the next hour. The video generates with the new voice, the shorter format, and uploads to the correct YouTube channel.

**The satisfaction:** Francis now has 4 channels running in parallel. Each has its own voice, style, and branding, but they all share the same efficient automation pipeline. Adding channel #5, #6, and beyond will be just as easy.

**What this journey reveals:** Francis needs a clean channel configuration system, YouTube OAuth management per channel, per-channel settings (voice IDs, branding, video parameters), and easy addition of new channels without touching core code.

### Journey 4: Francis as Scale Master - Managing the 100 Video Week

**Monday morning, ambitious goals.**

Francis has been running the system for 3 months. He's proven the workflow works at 20-30 videos/week. Now he wants to test the 100 video/week goal he set back when designing the system.

He opens Notion and starts planning. Over 2 hours on Monday, he creates 100 video entries across his 5 active channels:
- 30 for Philosophy Matters (his flagship)
- 25 for Daily Stoic (short-form philosophy)
- 20 for History Unfolded
- 15 for Science Explained
- 10 for his new channel, Tech Ethics

He batch-selects all 100 and changes Status to "Queued". He takes a deep breath and hits save.

**Tuesday morning, monitoring at scale.** Francis opens Notion and immediately notices the system is smart:
- 12 videos actively "Generating Assets" (Gemini parallel limit)
- 8 videos "Generating Video" (Kling parallel limit)
- 6 videos "Generating Audio" (ElevenLabs parallel limit)
- 74 videos still "Queued" - waiting their turn

The system is respecting API rate limits and processing in parallel waves. Francis realizes this will take the full week, not 2-3 days.

**Wednesday crisis.** Slack alert: "⚠️ Warning: 15 videos in retry state due to Kling rate limits". Francis checks the dashboard view he built in Notion (filtered by Status = any Error). The Kling API is getting hammered and rate-limiting his requests.

**The adjustment:** Francis realizes he needs to throttle Kling jobs more carefully. He edits the orchestration config:
```yaml
kling_max_parallel: 5  # Down from 8
kling_delay_between_jobs: 30s  # Add breathing room
```

He restarts the orchestration service. The retries start succeeding again.

**Thursday, steady progress.** Francis checks Notion throughout the day:
- 45 videos "Published"
- 30 videos in various generation stages  
- 20 videos still "Queued"
- 5 videos in "Ready" states waiting for his approval

He spends 30 minutes approving the batched reviews and keeps the pipeline moving.

**Friday evening, the count.** Francis opens Notion and filters by Published Date = This Week:
- 87 videos successfully published
- 8 videos still in final stages (will finish by Saturday)
- 5 videos had errors requiring manual intervention (uploaded manually)

**The realization:** He didn't quite hit 100 in one week, but he came close. More importantly, he identified the bottlenecks (Kling rate limits) and knows how to tune the system. Next week, with better throttling settings, he'll hit the goal.

**What this journey reveals:** Francis needs parallel processing with configurable limits, API rate limit awareness and auto-throttling, bulk review workflows (don't approve one at a time), system monitoring dashboards, and the ability to tune orchestration parameters without code changes.

### Journey Requirements Summary

**These four journeys reveal the following capability areas:**

**1. Notion Integration & Content Planning (Journey 1):**
- Notion database structure with comprehensive properties
- Status progression with review points
- Batch operations (queue multiple videos at once)
- Asset/video/audio review interfaces
- Approval workflow (user confirms before next step)
- YouTube URL auto-population after publish

**2. Error Handling & Recovery (Journey 2):**
- Granular error statuses per AI service
- Detailed error logging with actionable context
- Automatic retry with exponential backoff
- Alert system (Slack/email notifications)
- Priority queue management (High/Normal/Low)
- API quota monitoring and visibility
- Manual retry triggers

**3. Multi-Channel Management (Journey 3):**
- Channel configuration system (YAML or similar)
- Per-channel settings: voice IDs, branding, video parameters
- YouTube OAuth management per channel
- Channel-specific assets (intros, outros, templates)
- Easy channel addition without code changes
- Channel isolation (failures don't cross channels)

**4. Scale & Performance (Journey 4):**
- Parallel processing with configurable limits per API service
- API rate limit detection and auto-throttling
- Orchestration service with tunable parameters
- Bulk review workflows (approve batches, not individuals)
- System monitoring dashboard (queue depth, success rates, bottlenecks)
- Performance tuning without code deployment
- State persistence (survive restarts mid-generation)

## CLI Tool + SaaS Platform Specific Requirements

### Project-Type Overview

The ai-video-generator system extends its existing CLI automation toolkit with SaaS/platform capabilities. The architecture preserves the proven "Smart Agent + Dumb Scripts" pattern while adding multi-channel orchestration, Notion integration, and cloud-based workflow management.

**Hybrid Architecture:**
- **Existing:** 7 Python CLI scripts (stateless, single-purpose)
- **New:** FastAPI orchestrator + PostgreSQL queue + Python workers + Notion webhooks
- **Storage:** Configurable per-task (Notion default, R2 optional for scale)
- **Deployment:** Node.js/FastAPI backend on cloud (Vercel/similar), Python workers with persistent compute

### Technical Architecture Considerations

**1. Backend Services Architecture**

**Orchestrator Service (FastAPI):**
- Exposes webhook endpoints for Notion database automations
- Receives task status change events (Draft → Queued)
- Enqueues work requests in PostgreSQL queue
- Returns 200 OK immediately (no timeout issues)
- Reads channel configurations and task details from Notion

**Worker Pool (Python):**
- Background processors pulling from PostgreSQL queue
- Execute existing CLI scripts (generate_asset.py, generate_video.py, etc.)
- Handle long-running AI operations (Kling 2-5 minutes)
- Update Notion task status via API
- Upload assets to storage (Notion or R2)
- Independent scaling from orchestrator

**Database (PostgreSQL):**
- Task queue table (persistent, survives restarts)
- Worker state tracking
- No Redis needed (simpler deployment)

**2. Notion Integration Architecture**

**Database Structure:**
- Hierarchical: Channel pages → Task sub-pages → Assets + Logs as relations
- 26 workflow statuses with review gates (see detailed breakdown in User Journeys)
- Properties: Title, Channel (select), Topic, Story Direction, Status, Priority, Error Log, YouTube URL

**Webhook Flow:**
1. User changes task Status: "Draft" → "Queued" in Notion
2. Notion automation triggers webhook to backend `/webhook/notion`
3. Backend reads full task details from Notion API
4. Backend enqueues task in PostgreSQL
5. Workers process task, update Notion status at each step
6. Workers write asset URLs back to Notion Assets table

**Data Mapping:**
- Webhook payload contains: task ID, status change event
- Backend reads from Notion: channel, title, topic, story direction, current status
- Backend reads from config: channel-specific settings (voice ID, branding, OAuth tokens)

**3. Multi-Channel Management**

**Channel Configuration File (`channels.yaml`):**
```yaml
- channel_id: "philosophy-matters"
  youtube_channel: "UC_PhilosophyXYZ"
  elevenlabs_voice_id: "voice_id_here"
  brand_style: "professional"
  video_length_target: 90
  intro_template: "assets/branding/philosophy-intro.mp4"
  outro_template: "assets/branding/philosophy-outro.mp4"
  storage_strategy: "r2"  # or "notion"
  
- channel_id: "daily-stoic"
  youtube_channel: "UC_DailyStoicXYZ"
  elevenlabs_voice_id: "different_voice_id"
  brand_style: "minimalist"
  video_length_target: 60
  storage_strategy: "notion"
```

**Channel Isolation:**
- Each channel has isolated queue for fairness
- OAuth tokens managed per channel
- Rate limits tracked independently
- One channel's failures don't block others
- Separate filesystem folders per channel

**Global Rate Limiting:**
- Shared worker pool with round-robin scheduling
- Global rate limit tracking (e.g., Kling 10 concurrent max)
- Workers skip tasks that would exceed limits
- Pick from other channels when rate-limited

**4. Storage Strategy**

**Configurable Per-Task:**
- **Pure Notion (default):** Simple onboarding, zero extra services, good for <10 videos/week
- **Hybrid R2 + Notion:** Performance optimization, external sharing, YouTube direct upload, good for scale

**Asset Flow:**
- AI services generate assets (images via Gemini, videos via Kling, audio via ElevenLabs)
- Workers receive asset binary data from APIs
- Workers upload to configured storage (Notion file property or R2 bucket)
- Notion stores thumbnails + R2 URLs (if hybrid mode)
- YouTube uploads pull from R2 (faster) or Notion (simpler)

**Filesystem Structure (Backend):**
```
/workspaces/
  /{channel_id}/
    /{task_id}/
      /assets/
        /characters/
        /environments/
        /composites/
      /videos/
      /audio/
      /sfx/
      /{task_id}_final.mp4
```

**R2 Structure (Optional):**
```
s3://{bucket}/
  /{channel_id}/
    /{task_id}/
      [same structure as filesystem]
```

**5. YouTube Compliance & Integration**

**YouTube API Integration:**
- **Upload API:** Automated video publishing after assembly
- **OAuth 2.0:** Per-channel authentication tokens
- **Metadata:** Auto-generated titles, descriptions from Notion task data
- **Privacy:** Configurable per channel (public/unlisted)

**Compliance Considerations:**
- **Content Uniqueness:** Videos are unique per task (no duplication across channels)
- **Upload Frequency:** No artificial throttling needed (organic creation pace)
- **Channel Affiliation:** Not required (channels independently operated)
- **Automated Content:** AI-generated, properly disclosed in channel about pages

**6. Cost Tracking & Optimization**

**Service-Level Cost Tracking:**
- 7 API Cost entries per video (not 76 individual assets)
- Batch operations: "22 images = $0.44 Gemini"
- Logged to Notion API Costs table
- Fields: Service Name (text), Cost (number), Operation (select), Task (relation)

**Cost Visibility:**
- Task rollups show total cost per video
- Per-service breakdown enables optimization ("Kling = 75% of costs")
- Channel-level dashboards for ROI analysis
- No asset-level detail (too granular, not actionable)

**7. Error Handling & Retry Logic**

**Smart Auto-Retry with Exponential Backoff:**
```python
RetryConfig:
  max_attempts: 3
  backoff: [60s, 300s, 900s]  # 1min, 5min, 15min

Behavior:
├─ Attempt 1 fails (rate limit) → Wait 1min, retry
├─ Attempt 2 fails → Wait 5min, retry
├─ Attempt 3 fails → Wait 15min, retry
└─ Attempt 4 fails → Mark "Failed", alert user
```

**Error Visibility:**
- Task Status field: "Error: Asset Generation Failed"
- Error Log property: Detailed error context, retry history
- Slack/email alerts on terminal failures
- Manual retry trigger: User changes status back to "In Progress"

**8. Workflow Automation (Optional Enhancement)**

**Workflow-as-Config (per Channel):**
```yaml
workflow_config:
  steps:
    - id: asset_generation
      auto_proceed: true       # Skip review gate (cheap step)
      retry_on_failure: true
      max_retries: 3
    
    - id: video_generation
      auto_proceed: false      # Review gate (expensive step)
      clip_count: 18           # Configurable quality
```

**Benefits:**
- Premium channels review everything
- Budget channels auto-proceed through cheap steps
- A/B test strategies without code changes
- Per-channel quality vs speed vs cost optimization

### Implementation Considerations

**Technology Stack:**
- **Backend Orchestrator:** FastAPI (Python) or Express (Node.js)
- **Workers:** Python (reuse existing scripts)
- **Database:** PostgreSQL (queue + state)
- **Deployment:** Vercel/Railway/Render for orchestrator, persistent compute for workers
- **Storage:** Notion (default), Cloudflare R2 (optional scale)

**Development Phases:**
1. **Phase 1:** Notion database setup, webhook infrastructure
2. **Phase 2:** FastAPI orchestrator, PostgreSQL queue
3. **Phase 3:** Python workers, CLI script integration
4. **Phase 4:** Multi-channel orchestration, rate limiting
5. **Phase 5:** R2 storage option, YouTube automation
6. **Phase 6:** Cost tracking, error handling, retry logic

**Key Technical Constraints:**
- FFmpeg requirement → Persistent compute for workers (not serverless)
- Kling timeouts (2-5min) → Need queue-based architecture
- Notion rate limits → Webhook-driven (not polling)
- Multi-channel from day 1 → Can't retrofit later

**Integration Points:**
- Notion API: Webhooks (inbound), REST API (read/write)
- Gemini API: Image generation (existing script)
- Kling API: Video generation (existing script)
- ElevenLabs API: Audio/SFX generation (existing scripts)
- YouTube API: OAuth + Upload
- Cloudflare R2: S3-compatible storage (optional)

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Platform MVP - Complete Foundation for Rapid Scaling

**Strategic Rationale:**

This product requires a Platform MVP rather than a minimal feature set because:

1. **Multi-channel orchestration cannot be retrofitted** - The architecture for managing one channel vs. many channels is fundamentally different (queue management, rate limiting, channel isolation)

2. **Business model depends on rapid experimentation** - Finding profitable content niches requires testing multiple channels simultaneously from day 1

3. **Quality control prevents catastrophic cost waste** - Review gates at every step are non-negotiable to catch bad AI outputs before spending $6-13 per video on downstream processing

4. **Operational feasibility requires automation** - At 100 videos/week scale, manual retry and error handling would consume more time than the automation saves

**Resource Requirements:**

- **Team:** Solo developer (Francis) with AI assistance
- **Timeline:** 6-8 weeks for MVP (6 development phases)
- **Skills:** Python, FastAPI, PostgreSQL, Notion API, YouTube API, FFmpeg
- **Infrastructure:** Cloud hosting (Vercel/Railway), persistent compute for workers, PostgreSQL database

### MVP Feature Set (Phase 1)

**Core User Journey Supported:** All 4 journeys must work in MVP

1. **Journey 1: Content Planner** - Plan videos in Notion, batch queue, review at gates
2. **Journey 2: System Operator** - Receive error alerts, manually retry, prioritize recovery
3. **Journey 3: Channel Manager** - Configure new channels via YAML, YouTube OAuth
4. **Journey 4: Scale Master** - Process 20+ videos/day with parallel execution

**Must-Have Capabilities (From Step 3 MVP Scope):**

**1. Notion Integration:**
- Webhook endpoint for status change events
- Read video project entries from Notion database
- Write status updates back to Notion (26 workflow statuses)
- Track errors and completion states in Notion properties

**2. Multi-Channel Support:**
- Channel configuration file (`channels.yaml`) with voice IDs, branding, OAuth tokens
- Channel-specific settings (video length, intro/outro templates, storage strategy)
- Isolated channel operations (failures don't cross channels)
- Support 5-10 YouTube channels from launch

**3. Full Pipeline Automation:**
- Execute complete 8-step pipeline without manual intervention:
  - Asset generation (Gemini) - 22 images per video
  - Composite creation (16:9 for Kling)
  - Video generation (Kling) - 18 clips per video
  - Audio generation (ElevenLabs) - 18 narration clips
  - Sound effects generation (ElevenLabs) - 18 SFX clips
  - Final assembly (FFmpeg) - trim, mix, concatenate
  - YouTube upload - via YouTube Data/Upload API
- Preserve existing CLI scripts, call from workers

**4. Auto-Retry with Exponential Backoff:**
- Detect transient failures (timeouts, rate limits, network errors)
- Retry with backoff: 1min → 5min → 15min → 1hr
- Resume from failure point (don't regenerate completed steps)
- Alert user only after retry exhaustion or unrecoverable errors
- **Target: 95% success rate, 80%+ auto-recovery**

**5. Error Alerting:**
- Alert mechanism (Slack webhook or email)
- Error context (which step failed, why, what was attempted)
- Actionable information for manual intervention
- Error logs in Notion for debugging

**6. Queue Management:**
- PostgreSQL-based task queue (persistent, survives restarts)
- Process multiple videos in parallel (respect API rate limits)
- Global rate limit tracking (Kling 10 concurrent, Gemini/ElevenLabs limits)
- Round-robin scheduling across channels for fairness
- State persistence (workers can restart without losing queue)

**7. Backend Architecture:**
- FastAPI orchestrator (webhook endpoints, immediate 200 OK responses)
- Python worker pool (background processing, long-running AI operations)
- PostgreSQL database (queue + worker state)
- Deploy orchestrator to cloud (Vercel/Railway)
- Workers on persistent compute (for FFmpeg + long timeouts)

**8. Storage Infrastructure:**
- Default: Pure Notion (simple onboarding, zero extra config)
- Backend filesystem structure: `/workspaces/{channel_id}/{task_id}/`
- Asset organization: characters/, environments/, composites/, videos/, audio/, sfx/

**MVP Success Criteria:**
- Successfully generate and upload one complete video per channel (5 channels = 5 videos minimum)
- Demonstrate end-to-end Notion → YouTube automation
- Achieve 90%+ success rate (95% is tuning target, acceptable to miss initially)
- Handle at least one auto-retry scenario successfully
- Process 10-15 videos in a week (prove multi-channel orchestration works)

**What's Explicitly OUT of MVP:**
- R2 storage (Notion storage sufficient for launch)
- Cost tracking dashboard (manual cost calculation acceptable initially)
- Workflow-as-config automation (manual review gates for all videos)
- Analytics and reporting (YouTube Studio provides basic analytics)
- Advanced queue prioritization (simple FIFO queue sufficient)
- Bulk review workflows (approve videos one at a time)

### Post-MVP Features

**Phase 2: Performance & Scale Optimization (Weeks 9-12)**

**Goal:** Scale from 20 videos/day to 100 videos/week capacity

**Features:**

1. **Cloudflare R2 Storage Integration:**
   - Optional per-channel configuration
   - Faster YouTube uploads from R2
   - External asset sharing capabilities
   - Hybrid mode: Notion thumbnails + R2 URLs

2. **Cost Tracking & Visibility:**
   - Service-level cost logging (7 entries per video)
   - Notion API Costs table with rollups
   - Per-service breakdown (identify Kling = 75% of costs)
   - Task-level cost totals for ROI analysis

3. **Performance Tuning:**
   - Optimize parallel processing limits per API
   - Reduce asset generation bottlenecks
   - Fine-tune rate limit detection
   - Monitor and optimize worker throughput

4. **Advanced Queue Management:**
   - Priority levels (High/Normal/Low)
   - Deadline-aware scheduling
   - Channel capacity balancing
   - Smart retry scheduling (don't retry all failures simultaneously)

5. **Bulk Review Workflows:**
   - Approve multiple videos at once in Notion
   - Batch status changes
   - Filtered views for pending reviews

**Success Metrics:**
- Consistently process 100 videos/week
- 95% success rate achieved
- Average processing time per video documented
- Cost per video stays at $6-13

**Phase 3: Enhancement & Optimization (Month 4+)**

**Goal:** Optimize operations and enable advanced content strategies

**Features:**

1. **Custom Branding Per Channel:**
   - Channel-specific intro/outro videos
   - Custom overlay templates
   - Brand-specific asset generation styles
   - Thumbnail templates

2. **Workflow-as-Config Automation:**
   - Per-channel auto-proceed settings
   - Budget channels skip review gates
   - Premium channels review everything
   - Configurable clip counts per channel

3. **Analytics & Reporting:**
   - Dashboard showing videos generated per channel
   - Success rate monitoring over time
   - Performance metrics (generation time, failure patterns)
   - Channel profitability analysis

4. **YouTube Optimization:**
   - Smart scheduling (optimal upload times per channel)
   - Auto-generated SEO-optimized descriptions
   - Tag suggestions based on content
   - Playlist management

5. **System Monitoring Dashboard:**
   - Queue depth visibility
   - Success rates per channel
   - Bottleneck identification
   - API quota usage tracking

**Success Metrics:**
- Operating at full 100 videos/week capacity consistently
- Profitability achieved (YouTube revenue > production costs)
- Operational overhead < 5 hours/week
- Data-driven optimization decisions based on analytics

**Phase 4: Vision Features (Future)**

**Goal:** Maximum automation and content optimization

**Features:**

1. **A/B Testing:**
   - Generate multiple video variants
   - Track performance (views, engagement)
   - Auto-optimize based on results

2. **Automated Thumbnail Generation:**
   - Generate eye-catching thumbnails from assets
   - A/B test thumbnail variants
   - Auto-select highest-performing style

3. **Cross-Channel Content Repurposing:**
   - Generate YouTube Shorts from long-form videos
   - Adapt content style for different audiences
   - Maintain consistent branding across formats

4. **Advanced Content Planning:**
   - AI-assisted story generation
   - Trend detection and topic suggestions
   - Series planning across multiple videos

5. **Monetization Analytics:**
   - Revenue tracking per video, per channel
   - ROI analysis (production cost vs ad revenue)
   - Content strategy optimization based on profitability

### Risk Mitigation Strategy

**Technical Risks:**

**Risk:** FFmpeg processing or Kling timeouts cause worker failures
- **Mitigation:** Persistent worker compute (not serverless), auto-retry with exponential backoff
- **Fallback:** Manual retry from Notion, direct download from Kling dashboard

**Risk:** Notion webhook rate limits or reliability issues
- **Mitigation:** Immediate 200 OK response, queue-based processing decouples webhook from work
- **Fallback:** Manual status checking in Notion, manual worker triggering if needed

**Risk:** Multi-channel orchestration proves more complex than expected
- **Mitigation:** Isolated channel queues, independent OAuth tokens, separate filesystem folders
- **Fallback:** Temporarily reduce to 3 channels while debugging, scale up after stabilization

**Market Risks:**

**Risk:** Content doesn't generate sufficient YouTube revenue
- **Mitigation:** MVP enables rapid experimentation across 5-10 channels simultaneously
- **Validation:** First 30 videos across 3 channels will prove/disprove business model
- **Pivot:** If unprofitable, system can be repurposed for client work or different content types

**Risk:** AI service costs increase or quality decreases
- **Mitigation:** Generic API wrapper pattern allows provider substitution
- **Validation:** Cost tracking identifies which service is most expensive (Kling = 75%)
- **Pivot:** Can switch video providers or reduce clip counts to control costs

**Resource Risks:**

**Risk:** Development takes longer than 6-8 weeks
- **Mitigation:** Phase 1 focuses on proving core workflow (Notion → YouTube) with 1-2 channels
- **Minimal Viable MVP:** Single channel, manual retries, no cost tracking = 2-3 weeks
- **Fallback:** Launch with reduced feature set, add multi-channel in Phase 1.5

**Risk:** Solo developer bandwidth insufficient for operations
- **Mitigation:** Auto-retry reduces intervention needs to <5% of videos
- **Validation:** If operational burden > 5 hours/week, pause new channels until automation improves
- **Pivot:** Add monitoring/alerting in Phase 2 to reduce manual checking

## Functional Requirements

This section synthesizes all discovery work from previous steps into comprehensive functional requirements organized by capability area. Each requirement is numbered (FR1, FR2, etc.) for traceability and references specific sections from User Journeys, Success Criteria, and Technical Architecture.

### 1. Content Planning & Management

**Capability:** User ability to plan, manage, and track video projects through Notion interface

**FR1: Notion Database Entry Creation**
- User can create new video project entries in Notion database with required properties: Title (text), Channel (select), Topic (text), Story Direction (text), Status (select), Priority (select)
- System validates required fields before accepting entry
- Entry creation does not trigger processing until Status changes to "Queued"
- *Source: Journey 1 - Content Planner, Monday morning planning session*

**FR2: Batch Video Queuing**
- User can select multiple Draft entries in Notion and batch-change Status to "Queued"
- System receives single webhook per status change (not bulk webhook)
- All queued videos enter processing queue in FIFO order within their priority level
- *Source: Journey 1 - "Francis batch-selects them all and changes Status from 'Draft' to 'Queued'"*

**FR3: Channel Selection Management**
- Notion Channel property is single-select dropdown populated from channel configuration file
- User can only assign videos to configured channels
- Channel selection determines voice ID, branding, OAuth tokens, storage strategy
- Invalid channel selections are rejected during processing
- *Source: Journey 3 - Channel Manager setting up "Daily Stoic"*

**FR4: Video Project Metadata Storage**
- Each Notion entry stores: Title, Channel, Topic, Story Direction, Status, Priority, Error Log, YouTube URL, Created Date, Updated Date
- System reads these properties during processing
- System writes back: Status updates, Error Log entries, YouTube URL on completion
- *Source: User Journeys - Notion as single source of truth*

**FR5: Asset Review Interface**
- When Status reaches "Assets Ready", user can view generated assets via Notion relation
- Assets table contains: Asset Type, File URL/Attachment, Task (relation), Generated Date
- User reviews assets and changes Status to "Approved - Assets" to proceed
- System blocks video generation until approval received
- *Source: Journey 1 - "He clicks into 'Stoicism and Modern Anxiety' - status is 'Assets Ready'"*

**FR6: Video Review Interface**
- When Status reaches "Video Ready", user can review 18 generated video clips
- Videos linked via Notion relation to Videos table
- User changes Status to "Approved - Video" to proceed to audio generation
- System blocks audio generation until approval received
- *Source: Journey 1 - Review gates at critical cost points*

**FR7: Audio Review Interface**
- When Status reaches "Audio Ready", user can review narration and SFX
- Audio files linked via Notion relation to Audio table
- User changes Status to "Approved - Audio" to proceed to final assembly
- System blocks assembly until approval received
- *Source: User Journeys - Review gates prevent wasted downstream processing*

### 2. Multi-Channel Orchestration

**Capability:** System supports isolated, parallel operation of 5-10 YouTube channels with channel-specific configurations

**FR8: Channel Configuration File Management**
- System reads channel configurations from `channels.yaml` file
- Configuration includes: channel_id, youtube_channel, elevenlabs_voice_id, brand_style, video_length_target, intro_template, outro_template, storage_strategy
- Changes to config file require orchestrator restart to take effect
- Invalid configurations are detected at startup and prevent system launch
- *Source: Journey 3 - "He opens his terminal and navigates to the project config directory"*

**FR9: Channel Isolation**
- Each channel has isolated task queue
- Failures in one channel do not block processing for other channels
- Channel-specific rate limits are tracked independently
- One channel reaching quota does not pause other channels
- *Source: Success Criteria - "Isolated channel state (one channel's failures don't block others)"*

**FR10: Per-Channel Voice Selection**
- Video generation uses voice_id from channel configuration
- Different channels can use different ElevenLabs voices
- Voice ID validation occurs before audio generation begins
- Invalid voice IDs fail with clear error message
- *Source: Journey 3 - "elevenlabs_voice_id: 'EXAo8TGb3Xn2kVqGSz8H' # Different voice - more energetic"*

**FR11: Channel-Specific Branding**
- System can apply channel-specific intro videos (if configured)
- System can apply channel-specific outro videos (if configured)
- Branding assets are optional (not all channels require them)
- Missing branding files fail gracefully with warning, not error
- *Source: Journey 3 - "intro_template, outro_template configuration"*

**FR12: Channel-Specific Storage Strategy**
- Each channel can configure storage_strategy: "notion" or "r2"
- Notion strategy stores all assets as file attachments
- R2 strategy uploads to Cloudflare R2 and stores URLs in Notion
- Strategy is per-channel, not per-task
- *Source: Technical Architecture - "Configurable per-task (Notion default, R2 optional)"*

**FR13: Multi-Channel Parallel Processing**
- System processes videos from multiple channels simultaneously
- Round-robin scheduling ensures fairness across channels
- High-priority tasks from any channel can jump the queue
- Global rate limits (Kling concurrent max) apply across all channels
- *Source: Journey 4 - "Francis now has 4 channels running in parallel"*

**FR14: YouTube OAuth Per Channel**
- Each channel has independent YouTube OAuth token
- Tokens are stored securely in channel configuration or secrets manager
- Token refresh is handled automatically per channel
- Expired tokens pause that channel's uploads, not entire system
- *Source: Journey 3 - "Francis runs a CLI command: python scripts/youtube_auth.py --channel daily-stoic"*

**FR15: Channel Addition Without Code Changes**
- New channels are added by editing channels.yaml and running OAuth script
- No code deployment required for new channel
- New channel immediately appears in Notion Channel dropdown
- System validates new channel configuration before accepting tasks
- *Source: Journey 3 - "Adding channel #5, #6, and beyond will be just as easy"*

**FR16: Channel Capacity Balancing**
- System tracks queue depth per channel
- Warnings issued if one channel dominates processing
- No hard limits on per-channel task count
- User can manually prioritize channels via Priority field
- *Source: Journey 4 - Scale Master managing 100 videos across 5 channels*

### 3. Video Generation Pipeline

**Capability:** Complete 8-step automation from planning documents to published YouTube video

**FR17: End-to-End Pipeline Execution**
- System executes complete 8-step pipeline without manual intervention:
  1. Asset generation (Gemini) - 22 images
  2. Composite creation (16:9 for Kling)
  3. Video generation (Kling) - 18 clips
  4. Audio generation (ElevenLabs) - 18 narrations
  5. Sound effects (ElevenLabs) - 18 SFX
  6. Final assembly (FFmpeg) - trim, mix, concatenate
  7. YouTube upload
- Pipeline halts at review gates unless auto-proceed configured
- *Source: Success Criteria - "Complete automation from Notion entry to published YouTube video"*

**FR18: Asset Generation from Notion Planning**
- System reads Topic and Story Direction from Notion task
- System generates 22 photorealistic images via Gemini API
- Asset types: Character variations, environment backgrounds, props
- Follows existing "Global Atmosphere + Asset Prompt" pattern
- *Source: Technical Architecture - "Asset Generation Workflow"*

**FR19: 16:9 Composite Creation**
- System combines character PNGs + environment backgrounds into 1920x1080 composites
- Uses existing `create_composite.py` script
- Enforces 16:9 aspect ratio for Kling video generation compatibility
- Generates 18 composite seed images (one per video clip)
- *Source: Technical Architecture - "Composite Images: MUST be 16:9 (1920x1080)"*

**FR20: Video Generation via Kling**
- System uploads composite images to catbox.moe (free public hosting)
- System calls Kling 2.5 API via KIE.ai with motion prompts
- Follows Priority Hierarchy (Core Action FIRST, Camera Movement LAST)
- Generates 10-second clips (trimmed to 6-8s during assembly)
- Polls for completion (2-5 minutes typical, up to 10 minutes)
- *Source: Technical Architecture - "Video Prompt Priority Hierarchy"*

**FR21: Narration Generation**
- System generates 18 narration clips via ElevenLabs v3
- Uses channel-specific voice_id from configuration
- Narration text derived from Story Direction field
- Clips are 6-8 seconds each (match video lengths)
- *Source: Technical Architecture - "Audio generation via ElevenLabs"*

**FR22: Sound Effects Generation**
- System generates 18 sound effect clips via ElevenLabs v3
- SFX prompts derived from Story Direction atmospheric descriptions
- Clips are 5-10 seconds each
- SFX mixed with narration during assembly
- *Source: Technical Architecture - "SFX generation via ElevenLabs"*

**FR23: FFmpeg Video Assembly**
- System trims 10-second video clips to match audio duration (6-8s)
- System mixes narration + SFX on separate audio tracks
- System concatenates 18 clips with hard cuts (no transitions)
- Final output: 90-second documentary, 1920x1080, H.264/AAC
- *Source: Technical Architecture - "Video Assembly Process"*

**FR24: YouTube Upload Automation**
- System uploads assembled video to YouTube via YouTube Data API
- Uses channel-specific OAuth token
- Sets title from Notion Title field
- Sets description from auto-generated template (configurable)
- Sets privacy level from channel configuration (public/unlisted)
- *Source: Technical Architecture - "YouTube Integration"*

**FR25: YouTube URL Population**
- After successful upload, system writes YouTube URL back to Notion
- URL populated in YouTube URL property of task entry
- User can click link to view published video
- Status changes to "Published" after URL written
- *Source: Journey 1 - "8 videos show '✅ Published' with YouTube URLs populated"*

**FR26: Existing CLI Script Preservation**
- System calls existing Python scripts without modification:
  - generate_asset.py
  - create_composite.py
  - generate_video.py
  - generate_audio.py
  - generate_sound_effects.py
  - assemble_video.py
- Scripts remain stateless and single-purpose
- Workers handle all file I/O, data extraction, orchestration
- *Source: Technical Architecture - "Smart Agent + Dumb Scripts pattern preserved"*

### 4. Error Handling & Recovery

**Capability:** Automatic retry with exponential backoff, clear error visibility, manual intervention when needed

**FR27: Transient Failure Detection**
- System detects transient failures: API timeouts, rate limits (429), network errors (5xx)
- Distinguishes from permanent failures: invalid API keys, malformed requests (4xx)
- Transient failures trigger auto-retry
- Permanent failures immediately alert user
- *Source: Success Criteria - "Detect transient failures (timeouts, rate limits, network issues)"*

**FR28: Exponential Backoff Retry**
- Retry schedule: 1 minute → 5 minutes → 15 minutes → 1 hour
- Max 3 retry attempts before marking as failed
- Each retry logs attempt number and wait time
- Backoff prevents API bans from aggressive retrying
- *Source: Technical Architecture - "Auto-Retry with Exponential Backoff"*

**FR29: Resume from Failure Point**
- System resumes from failed step, not from beginning
- Completed assets are reused (not regenerated)
- State persistence allows recovery across worker restarts
- Idempotent operations prevent duplicate processing
- *Source: Success Criteria - "Resume from failure point (don't regenerate completed assets)"*

**FR30: Granular Error Status Updates**
- Notion Status field shows specific error type:
  - "Error: Asset Generation Failed"
  - "Error: Video Generation Failed"
  - "Error: Audio Generation Failed"
  - "Error: Assembly Failed"
  - "Error: Upload Failed"
- User immediately knows which step failed
- *Source: Journey 2 - "Error: Video Generation Failed - 'Epictetus on Freedom'"*

**FR31: Detailed Error Logging**
- Error Log property in Notion contains:
  - Timestamp of failure
  - Which step failed
  - Error message from API/service
  - Retry attempts made
  - Next scheduled retry time (if applicable)
- User has complete context for debugging
- *Source: Journey 2 - "Error logs all say: 'Gemini API quota exceeded - daily limit reached'"*

**FR32: Alert System for Terminal Failures**
- System sends alerts when:
  - Auto-retry exhausted (3 attempts failed)
  - Unrecoverable error detected (invalid credentials, missing files)
  - API quota exceeded
- Alert mechanism: Slack webhook or email
- Alert includes: Task title, channel, error type, link to Notion entry
- *Source: Journey 2 - "Francis is in the middle of lunch when his phone buzzes with a Slack alert"*

**FR33: Manual Retry Trigger**
- User can manually retry failed tasks
- Method: Change Status from "Error: X Failed" back to appropriate retry status
- System requeues task for immediate processing
- Manual retry bypasses exponential backoff wait times
- *Source: Journey 2 - "He clicks a checkbox to retry, and the system requeues the video generation"*

**FR34: API Quota Monitoring**
- System tracks API usage against daily quotas:
  - Gemini image generation quota
  - Kling video generation quota
  - ElevenLabs audio generation quota
- Warns when approaching quota limits (80% threshold)
- Gracefully handles quota exceeded errors
- *Source: Journey 2 - "Gemini API quota exceeded - daily limit reached"*

**FR35: Auto-Recovery Success Rate**
- Target: 80%+ of transient failures auto-recover without user intervention
- Measured: (Auto-recovered failures) / (Total transient failures)
- Reported weekly in system monitoring
- Falls below 70%: Investigate retry configuration tuning
- *Source: Success Criteria - "80%+ auto-recovery from transient failures"*

### 5. Queue & Task Management

**Capability:** PostgreSQL-based persistent queue with parallel processing, state tracking, and restart resilience

**FR36: Webhook Endpoint for Notion Events**
- FastAPI orchestrator exposes `/webhook/notion` endpoint
- Accepts POST requests from Notion automations
- Validates webhook signature (if configured)
- Returns 200 OK immediately (no processing in webhook handler)
- *Source: Technical Architecture - "Notion Integration Architecture - Webhook Flow"*

**FR37: Task Enqueueing**
- Webhook handler enqueues task in PostgreSQL queue table
- Queue entry contains: task_id (Notion page ID), channel_id, priority, status, created_at
- Duplicate detection prevents double-processing
- Queue is persistent (survives orchestrator restarts)
- *Source: Technical Architecture - "Database (PostgreSQL): Task queue table (persistent, survives restarts)"*

**FR38: Worker Pool Management**
- Python workers poll PostgreSQL queue for tasks
- Configurable worker count (default: 3-5 workers)
- Workers are independent processes (can scale separately from orchestrator)
- Worker restarts do not lose queue state
- *Source: Technical Architecture - "Worker Pool (Python): Background processors pulling from PostgreSQL queue"*

**FR39: Parallel Task Execution**
- Multiple videos process simultaneously (respecting API rate limits)
- Configurable parallelism per API service:
  - Gemini: 12 concurrent asset generations
  - Kling: 5-8 concurrent video generations
  - ElevenLabs: 6 concurrent audio generations
- Global rate limit tracking prevents exceeding service caps
- *Source: Journey 4 - "12 videos actively 'Generating Assets', 8 videos 'Generating Video'"*

**FR40: Priority Queue Management**
- Tasks have priority levels: High, Normal, Low
- High-priority tasks jump to front of queue
- Within same priority level, FIFO ordering
- User sets priority in Notion Priority field
- *Source: Journey 2 - "He selects the 3 most time-sensitive videos and changes Priority to 'High'"*

**FR41: Round-Robin Channel Scheduling**
- Workers pick tasks round-robin across channels
- Ensures one channel doesn't monopolize resources
- High-priority tasks override round-robin (any channel)
- Channel with no queued tasks is skipped in rotation
- *Source: Technical Architecture - "Global Rate Limiting: Round-robin scheduling"*

**FR42: Rate Limit Aware Task Selection**
- Workers check global rate limit counters before claiming tasks
- If Kling at 10 concurrent limit, skip video generation tasks
- Pick different task type or different channel
- Prevents workers from sitting idle when rate-limited
- *Source: Journey 4 - "The system is respecting API rate limits and processing in parallel waves"*

**FR43: State Persistence Across Restarts**
- Queue state stored in PostgreSQL (not in-memory)
- Worker restarts do not lose in-progress tasks
- Tasks in "Processing" state revert to "Queued" on worker crash
- Orchestrator restarts preserve entire queue
- *Source: Success Criteria - "State persistence (survive restarts without losing queue)"*

### 6. Asset & Storage Management

**Capability:** Organized filesystem structure with configurable storage strategies (Notion vs R2)

**FR44: Backend Filesystem Structure**
- Assets organized: `/workspaces/{channel_id}/{task_id}/`
- Subdirectories: assets/, videos/, audio/, sfx/
- Final video: `{task_id}_final.mp4`
- Channel isolation: No cross-channel file access
- *Source: Technical Architecture - "Filesystem Structure (Backend)"*

**FR45: Asset Subfolder Organization**
- assets/ contains: characters/, environments/, composites/
- characters/: Transparent PNG character images
- environments/: Background scene images
- composites/: 1920x1080 16:9 seed images for Kling
- Naming convention: `{asset_type}_{index}.png`
- *Source: Technical Architecture - "Asset Flow"*

**FR46: Notion Storage Strategy**
- Default storage option (simplest onboarding)
- Assets uploaded as file attachments to Notion Assets table
- Assets table has relation to parent task
- No external services required (zero extra config)
- Good for <10 videos/week scale
- *Source: Technical Architecture - "Pure Notion (default): Simple onboarding, zero extra services"*

**FR47: Cloudflare R2 Storage Strategy (Post-MVP)**
- Optional per-channel configuration
- Assets uploaded to R2 bucket: `s3://{bucket}/{channel_id}/{task_id}/`
- Notion stores thumbnails + R2 URLs
- Faster YouTube uploads from R2
- External asset sharing capabilities
- Good for >10 videos/week scale
- *Source: Technical Architecture - "Hybrid R2 + Notion: Performance optimization, external sharing"*

**FR48: Asset URL Population in Notion**
- After asset generation, system writes URLs to Notion Assets table
- Notion Assets table entries: Asset Type, File/URL, Task (relation), Generated Date
- User can preview assets directly from Notion
- Supports both Notion file attachments and R2 URLs
- *Source: Technical Architecture - "Workers write asset URLs back to Notion Assets table"*

**FR49: Temporary File Cleanup**
- Backend filesystem serves as working directory
- Files retained until task reaches "Published" or "Error" terminal state
- Cleanup task runs daily to remove old completed task directories
- Configurable retention period (default: 7 days)
- *Source: Technical Architecture - Implicit from filesystem usage pattern*

**FR50: Asset Generation Idempotency**
- Re-running asset generation overwrites existing files
- Prevents duplicate asset accumulation
- Allows manual regeneration of failed steps
- File naming ensures consistent overwrites
- *Source: Existing Architecture - "Idempotent Operations: Re-running overwrites outputs"*

### 7. Status & Progress Monitoring

**Capability:** 26-state workflow with review gates, clear progress visibility, real-time status updates

**FR51: 26 Workflow Status Progression**
- Task progresses through defined states:
  - Draft (initial user creation)
  - Queued (user activates processing)
  - Generating Assets (Gemini in progress)
  - Assets Ready (review gate)
  - Approved - Assets (user approval)
  - Generating Video (Kling in progress)
  - Video Ready (review gate)
  - Approved - Video (user approval)
  - Generating Audio (ElevenLabs in progress)
  - Audio Ready (review gate)
  - Approved - Audio (user approval)
  - Assembling (FFmpeg in progress)
  - Assembly Complete
  - Uploading (YouTube upload in progress)
  - Published (final success state)
  - [11 error states for each step]
- *Source: Technical Architecture - "26 workflow statuses with review gates"*

**FR52: Review Gate Enforcement**
- System pauses at "Assets Ready", "Video Ready", "Audio Ready"
- Processing does not continue until user approves
- Approval method: User changes Status to "Approved - X"
- Prevents wasted cost on downstream processing of bad outputs
- *Source: User Journeys - "Review gates prevent wasted downstream processing"*

**FR53: Real-Time Status Updates in Notion**
- Workers update Notion Status field after each pipeline step
- Status visible to user within seconds of step completion
- Updates via Notion API (not webhooks back to Notion)
- Failed updates logged but do not block processing
- *Source: Journey 1 - "Tuesday afternoon. Francis opens Notion to check progress. The status columns are alive"*

**FR54: Progress Visibility Dashboard**
- User creates Notion database views filtered by Status
- View examples: "In Progress" (all active generation states), "Needs Review" (all Ready states), "Errors" (all Error states)
- Dashboard shows queue depth, success rate, bottlenecks
- No custom UI required (pure Notion database views)
- *Source: Journey 4 - "Francis checks the dashboard view he built in Notion"*

**FR55: Updated Date Auto-Tracking**
- Notion Updated Date property auto-updates on every status change
- Allows sorting by "most recently updated"
- Helps identify stuck tasks (no updates in >1 hour)
- No manual intervention required
- *Source: Notion standard feature leveraged by architecture*

**FR56: Error State Clarity**
- Error statuses indicate exact failure point
- Separate error status per major step (11 total)
- User can filter Notion by any error type
- Bulk error resolution workflows possible
- *Source: Journey 2 - "Francis opens Notion and immediately notices the system is smart: 15 videos in retry state"*

**FR57: Retry State Visibility**
- Tasks in retry show "In Retry - [Step Name]" (if tracked separately)
- Error Log shows retry count and next attempt time
- User knows system is auto-recovering without manual action
- Retry state distinguishes from terminal failure
- *Source: Journey 2 - "Slack alert: 15 videos in retry state due to Kling rate limits"*

**FR58: Bulk Status Operations**
- User can select multiple tasks in Notion and batch-change Status
- Bulk approve all "Assets Ready" tasks at once
- Bulk retry all "Error: X Failed" tasks
- Bulk priority changes for urgent batches
- *Source: Journey 4 - "He spends 30 minutes approving the batched reviews"*

**FR59: Success Rate Tracking**
- System logs task outcomes: Success, Failed (auto-recovered), Failed (manual intervention required)
- Weekly success rate calculated: (Successful tasks) / (Total tasks attempted)
- Target: 95% success rate with auto-retry
- Reported in Notion rollups or external dashboard
- *Source: Success Criteria - "95% success rate with auto-retry"*

### 8. YouTube Integration

**Capability:** Automated video publishing with channel-specific OAuth, metadata generation, compliance enforcement

**FR60: YouTube OAuth Per Channel**
- Each channel has independent OAuth 2.0 token
- Tokens stored securely (environment variables or secrets manager)
- OAuth flow initiated via CLI script: `python scripts/youtube_auth.py --channel {channel_id}`
- Browser-based consent flow opens for user approval
- *Source: Journey 3 - "Francis runs a CLI command: python scripts/youtube_auth.py --channel daily-stoic"*

**FR61: Token Refresh Automation**
- System automatically refreshes expired OAuth tokens
- Refresh happens transparently during upload attempt
- Failed refresh alerts user to re-authenticate
- One channel's expired token does not affect other channels
- *Source: Technical Architecture - "Token refresh is handled automatically per channel"*

**FR62: Video Metadata Generation**
- Title: Pulled from Notion Title field
- Description: Auto-generated from template (configurable per channel)
- Tags: Optional, derived from Topic field keywords
- Privacy: Configurable per channel (public, unlisted, private)
- *Source: Technical Architecture - "Metadata: Auto-generated titles, descriptions from Notion task data"*

**FR63: Upload via YouTube Data API**
- System uses YouTube Data API v3 for uploads
- Resumable upload protocol for large files (>50MB)
- Upload retries on network interruption
- Upload status tracked separately in Notion
- *Source: Technical Architecture - "Upload API: Automated video publishing after assembly"*

**FR64: YouTube URL Retrieval**
- After successful upload, system extracts YouTube video ID
- Constructs full URL: `https://youtube.com/watch?v={video_id}`
- Writes URL back to Notion YouTube URL property
- Link becomes clickable in Notion for quick access
- *Source: Journey 1 - "8 videos show '✅ Published' with YouTube URLs populated"*

**FR65: Upload Error Handling**
- Upload failures trigger retry (same exponential backoff as other steps)
- Common failures: Token expired, quota exceeded, network timeout
- Permanent failures (copyright strike, content violation) alert user immediately
- Upload can be manually retried after fixing underlying issue
- *Source: Journey 2 - Error handling applies to all pipeline steps including upload*

**FR66: YouTube Compliance Enforcement**
- Videos are unique per task (no duplication across channels)
- Upload frequency is organic (no artificial throttling)
- Automated content disclosure in channel About page (manual setup)
- No special channel affiliation required (independent operation)
- *Source: Technical Architecture - "Compliance Considerations"*

**FR67: Channel Privacy Configuration**
- Each channel config specifies default privacy level
- Options: public, unlisted, private
- User can override per-task in Notion (optional Privacy field)
- Privacy setting applied during upload
- *Source: Technical Architecture - "Privacy: Configurable per channel"*

## Non-Functional Requirements

This section defines quality attributes that specify HOW WELL the system must perform. NFRs are selective—we only document categories that matter for this specific product to avoid requirement bloat.

### Performance

**NFR-P1: Pipeline Execution Time**
- **Requirement:** Complete 8-step pipeline execution in ≤2 hours per video (90th percentile)
- **Measurement:** Time from "Queued" status to "Published" status
- **Rationale:** User success requires predictable turnaround times. 2-hour target enables 100 videos/week capacity with buffer.
- **Target:** Average 90 minutes, 90th percentile ≤120 minutes

**NFR-P2: Parallel Processing Throughput**
- **Requirement:** System processes minimum 20 videos concurrently across all pipeline stages
- **Measurement:** Count of videos in active generation states (not Queued, Ready, or terminal states)
- **Rationale:** Achieving 100 videos/week requires 14-15 videos/day, which demands substantial parallelism.
- **Breakdown:**
  - Gemini asset generation: 12 concurrent tasks
  - Kling video generation: 5-8 concurrent tasks
  - ElevenLabs audio generation: 6 concurrent tasks

**NFR-P3: Notion API Response Time**
- **Requirement:** Notion API calls (read/write) complete within 5 seconds (95th percentile)
- **Measurement:** API call duration from request to response
- **Rationale:** Slow Notion updates create perceived system lag. Real-time status updates enhance user confidence.
- **Failure Handling:** Timeouts logged but do not block processing

**NFR-P4: Webhook Response Time**
- **Requirement:** `/webhook/notion` endpoint returns 200 OK within 500ms
- **Measurement:** Time from request received to response sent
- **Rationale:** Webhook timeouts cause Notion automation failures. Immediate response prevents retry storms.
- **Design:** No processing in webhook handler, only enqueueing

**NFR-P5: Worker Startup Time**
- **Requirement:** Workers become operational within 30 seconds of launch
- **Measurement:** Time from process start to first task claim from queue
- **Rationale:** Fast recovery from worker crashes maintains system throughput
- **Target:** <10 second startup preferred, 30 second maximum

### Security

**NFR-S1: API Key Protection**
- **Requirement:** All API keys (Gemini, KIE.ai, ElevenLabs) stored in environment variables or secrets manager, never in code or logs
- **Measurement:** Code review and log inspection confirms no plain-text secrets
- **Rationale:** Leaked API keys enable unauthorized usage and cost theft
- **Implementation:** Use `.env` files (gitignored) or cloud secrets manager (Vercel/Railway)

**NFR-S2: YouTube OAuth Token Security**
- **Requirement:** OAuth tokens encrypted at rest and transmitted only over HTTPS
- **Measurement:** Security audit confirms encrypted storage and TLS enforcement
- **Rationale:** Compromised OAuth tokens enable channel hijacking
- **Implementation:** Tokens stored in encrypted secrets manager with channel-specific access control

**NFR-S3: Webhook Signature Validation**
- **Requirement:** `/webhook/notion` endpoint validates request signatures (if Notion supports)
- **Measurement:** Penetration testing confirms unauthorized webhook requests are rejected
- **Rationale:** Prevents malicious queue injection
- **Fallback:** IP allowlisting if signature validation unavailable

**NFR-S4: Database Access Control**
- **Requirement:** PostgreSQL database accessible only from orchestrator and worker processes, not publicly exposed
- **Measurement:** Network security audit confirms no public access
- **Rationale:** Queue manipulation or data exfiltration would compromise system integrity
- **Implementation:** Database on private network or localhost only

**NFR-S5: Secure Asset Storage**
- **Requirement:** Notion file attachments and R2 buckets have proper access controls (authenticated users only)
- **Measurement:** Unauthorized access attempts fail
- **Rationale:** Generated content is user intellectual property and must be protected
- **Implementation:** Notion workspace access controls + R2 private bucket with signed URLs

### Scalability

**NFR-SC1: Multi-Channel Growth Capacity**
- **Requirement:** System supports 10 channels in MVP, scales to 20 channels without architectural changes
- **Measurement:** Add new channels and verify no performance degradation >10%
- **Rationale:** Business model depends on testing multiple content niches simultaneously
- **Constraint:** Channel configuration file size and parsing time remain <1 second

**NFR-SC2: Queue Depth Handling**
- **Requirement:** PostgreSQL queue handles 500+ concurrent tasks without performance degradation
- **Measurement:** Query performance remains <100ms at 500 tasks
- **Rationale:** 100 videos/week means ~15-20 videos queued daily, with retries and multi-step processing creating queue buildup
- **Target:** 1000 task capacity for future growth

**NFR-SC3: Worker Scaling**
- **Requirement:** Adding workers (horizontal scaling) increases throughput linearly up to 10 workers
- **Measurement:** Doubling worker count doubles task completion rate
- **Rationale:** Performance bottlenecks should be API rate limits, not orchestration
- **Constraint:** Workers must be independently scalable from orchestrator

**NFR-SC4: API Rate Limit Elasticity**
- **Requirement:** System adapts to API rate limit changes without code deployment
- **Measurement:** Update rate limit configuration, verify system respects new limits within 5 minutes
- **Rationale:** API providers change limits unpredictably; code deployment for config changes is unacceptable
- **Implementation:** Rate limits in configuration file, hot-reloaded by workers

**NFR-SC5: Storage Growth Management**
- **Requirement:** System handles 10,000 completed videos without performance impact on new tasks
- **Measurement:** Task processing time remains constant regardless of historical task count
- **Rationale:** Long-term operation accumulates historical data; queries must not degrade
- **Implementation:** Proper database indexing, archived task cleanup after 90 days

### Integration

**NFR-I1: External API Availability Tolerance**
- **Requirement:** System remains operational when 1 of 6 external services is unavailable
- **Measurement:** Simulate service outage, verify other channels/tasks continue processing
- **Rationale:** External service downtime should not cause total system failure
- **Behavior:** Tasks requiring unavailable service enter retry queue, other tasks proceed

**NFR-I2: Notion API Rate Limit Compliance**
- **Requirement:** System never exceeds Notion API rate limits (3 requests/second)
- **Measurement:** API call rate monitoring shows ≤3 req/sec sustained
- **Rationale:** Exceeding Notion rate limits causes 5-minute bans, blocking all operations
- **Implementation:** Request queue with rate limit throttling

**NFR-I3: Kling API Timeout Handling**
- **Requirement:** System tolerates Kling video generation timeouts (up to 10 minutes per clip)
- **Measurement:** 99% of video generations complete within 10 minutes or enter retry
- **Rationale:** Kling is slowest pipeline step (2-5 min typical, up to 10 min possible)
- **Implementation:** 10-minute timeout with exponential backoff retry

**NFR-I4: Gemini API Quota Exhaustion Recovery**
- **Requirement:** When Gemini daily quota exhausted, system pauses affected tasks until midnight UTC reset
- **Measurement:** Quota exceeded errors do not cascade; affected tasks auto-resume after reset
- **Rationale:** Gemini quotas are daily hard limits; graceful handling prevents alert storms
- **Behavior:** Tasks moved to "Quota Exceeded" state, auto-retry at midnight + 5 minutes

**NFR-I5: YouTube OAuth Token Refresh**
- **Requirement:** System automatically refreshes YouTube OAuth tokens before expiration (60-minute validity)
- **Measurement:** Token expiration never causes upload failures
- **Rationale:** OAuth tokens expire predictably; manual refresh is unacceptable for autonomous operation
- **Implementation:** Proactive refresh at 50-minute mark

**NFR-I6: Integration Error Visibility**
- **Requirement:** All external API errors logged with full context (service, endpoint, request ID, error message)
- **Measurement:** Error logs contain sufficient information to reproduce and debug integration issues
- **Rationale:** Debugging external API failures requires detailed context
- **Target:** 100% of API errors logged with request/response details

### Reliability

**NFR-R1: System Uptime**
- **Requirement:** Orchestrator achieves 99% uptime (measured monthly)
- **Measurement:** Uptime monitoring shows ≤7.2 hours downtime per month
- **Rationale:** Continuous Notion webhook processing requires persistent orchestrator availability
- **Target:** 99.5% (3.6 hours/month downtime) aspirational target

**NFR-R2: Auto-Recovery Success Rate**
- **Requirement:** 80% of transient failures auto-recover without manual intervention
- **Measurement:** (Auto-recovered failures) / (Total transient failures) ≥ 0.80
- **Rationale:** User success depends on autonomous operation; manual intervention should be rare
- **Tracking:** Weekly report of failure types and recovery rates

**NFR-R3: State Persistence**
- **Requirement:** Queue state survives orchestrator and worker restarts with zero task loss
- **Measurement:** Crash testing confirms all queued and in-progress tasks resume correctly
- **Rationale:** Infrastructure restarts must not lose user work
- **Implementation:** PostgreSQL provides transactional durability

**NFR-R4: Idempotent Operations**
- **Requirement:** Re-running pipeline steps produces identical outputs without side effects
- **Measurement:** Execute same step twice, verify second execution overwrites cleanly
- **Rationale:** Retry logic depends on safe re-execution
- **Constraint:** Asset generation determinism depends on AI service consistency (not guaranteed)

**NFR-R5: Error Alert Reliability**
- **Requirement:** 100% of terminal failures trigger user alerts (Slack/email) within 5 minutes
- **Measurement:** Failure injection testing confirms alerts delivered
- **Rationale:** User intervention requires timely notification
- **Fallback:** If alert system fails, Notion status update remains as fallback visibility

**NFR-R6: Data Integrity**
- **Requirement:** Notion status updates never desynchronize from actual task state
- **Measurement:** Audit logs confirm status transitions match pipeline execution
- **Rationale:** Incorrect status misleads user about progress and causes inappropriate interventions
- **Implementation:** Status updates only after confirmed pipeline step completion

**NFR-R7: Graceful Degradation**
- **Requirement:** When API rate limits reached, system queues tasks rather than failing them
- **Measurement:** Rate limit scenarios result in "Queued" or "Retry" states, not "Failed"
- **Rationale:** Temporary capacity constraints should not cause permanent task failures
- **Behavior:** Tasks wait in queue until capacity available

### NFR Summary

**Total NFRs Defined:** 28 requirements across 5 categories

**Coverage:**
- Performance: 5 NFRs (pipeline speed, parallelism, API response times)
- Security: 5 NFRs (API key protection, OAuth security, access control)
- Scalability: 5 NFRs (multi-channel growth, queue capacity, worker scaling)
- Integration: 6 NFRs (API availability tolerance, rate limit compliance, error handling)
- Reliability: 7 NFRs (uptime, auto-recovery, state persistence, alerts)

**Key Quality Targets:**
- 95% task success rate with auto-retry
- 99% orchestrator uptime
- 2-hour pipeline execution time (90th percentile)
- 20 concurrent video processing capacity
- 80% auto-recovery from transient failures
- 100% alert delivery for terminal failures

**Categories Excluded:**
- Accessibility: Not applicable (backend automation system, Notion provides UI)
