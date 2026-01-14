---
stepsCompleted: [1, 2, 3, 4, 5, 6, 14]
lastStep: 14
status: complete
completedAt: '2026-01-10'
inputDocuments:
  - "_bmad-output/planning-artifacts/prd.md"
  - "_bmad-output/project-context.md"
  - "docs/index.md"
  - "docs/project-overview.md"
  - "docs/architecture-patterns.md"
skippedSteps: [7, 8, 9, 10, 11, 12, 13]
skippedReason: 'Custom UI design steps deferred - using Notion as primary interface for MVP'
---

# UX Design Specification ai-video-generator

**Author:** Francis
**Date:** 2026-01-10

---

## Executive Summary

### Project Vision

ai-video-generator is evolving from a CLI automation pipeline (producing one video at a time) into a multi-channel YouTube automation platform. The vision is to enable content creators to scale from 1 video/week to 100 videos/week across 5-10 YouTube channels, orchestrated entirely through Notion as a centralized planning hub.

**The Transformation:**
- **From:** Manual terminal commands, sequential processing, one video at a time (~90-120 minutes per video)
- **To:** Notion-based planning → Automated parallel processing → YouTube publishing (zero manual intervention)

**Core Value Proposition:** "Finally, I can map out my entire multi-channel content calendar in Notion, and the videos generate automatically while respecting YouTube's rules. I'm not managing file folders or running terminal commands anymore."

**Success Metric:** 95% of videos complete from Notion entry to YouTube upload without user intervention, with error alerts only when system cannot auto-recover.

### Target Users

**Primary User:** Francis (expert content creator managing multiple YouTube channels)

**User Profile:**
- Managing 3-10 YouTube channels simultaneously
- Expert technical skill level (comfortable with Python, YAML, CLI when necessary)
- Currently producing 10 videos/week, wants to scale to 100 videos/week
- Values autonomous operation and error transparency
- Wants to focus on content planning and creative decisions, not pipeline management

**User Context:**
- **Planning:** Notion (desktop/mobile) - 5-10 minutes per video entry
- **Monitoring:** Notion (desktop) - periodic check-ins on progress
- **Review Gates:** Notion (desktop) - reviewing assets, videos, audio before expensive next steps
- **Error Response:** Mobile (Slack alerts) → Desktop (Notion for investigation and resolution)
- **Configuration:** Terminal (one-time channel setup via YAML and OAuth)

**User in 4 Distinct Roles:**
1. **Content Planner** - Batch planning videos in Notion, queuing for processing
2. **Quality Reviewer** - Approving assets/videos/audio at review gates
3. **System Operator** - Responding to errors, managing retries, adjusting priorities
4. **Channel Manager** - Configuring new YouTube channels, tuning orchestration parameters

### Key Design Challenges

**1. Multi-Modal Workflow Complexity**
Users need different UX patterns for different contexts: fast/intuitive for planning, detailed/diagnostic for troubleshooting, precise/technical for configuration. One-size-fits-all interface design will fail.

**2. Asynchronous Progress Visibility**
Video generation takes 2-5 minutes per clip (18 clips × 20+ videos = hours of async processing). Users need real-time status updates across dozens of videos without information overload or constant monitoring.

**3. Actionable Error Recovery**
When failures occur (API quotas exceeded, rate limits, timeouts), users need immediate answers: which videos are affected? why did it fail? what should I do? when will auto-retry succeed? Critical distinction between "system is handling this" vs. "I need to intervene now."

**4. Review Gate Efficiency at Scale**
At 100 videos/week, reviewing 300+ approval points (assets + videos + audio for each video) becomes a bottleneck. Need bulk review workflows that maintain quality control without creating cognitive overload.

**5. Channel Context Switching**
Managing 5-10 channels with different voices, styles, branding, and audiences requires clear visual/spatial differentiation to prevent operational mistakes (e.g., uploading philosophy video to science channel).

**6. Balance Between Automation and Control**
Users want autonomous operation (95% hands-off) but also need fine-grained control when needed (priority queues, manual retries, channel-specific configurations). The UX must progressively disclose complexity.

### Design Opportunities

**1. Leverage Notion as Familiar Power Tool**
Instead of building custom dashboards, leverage Notion's existing UX strengths (databases, filters, views, relations, formulas). Users already know how to create views, sort by status, filter by channel. Zero learning curve for core operations, infinite customization potential.

**2. Smart Defaults with Expert Overrides**
Auto-proceed through low-cost steps (asset generation $0.50), require approval for expensive steps (video generation $5-10). Configurable per channel (premium channels review everything, budget channels auto-proceed). Users feel "the system makes smart decisions, but I'm always in control."

**3. Progressive Disclosure of Complexity**
- **Daily operations:** Simple Notion interface (add video, check status, approve reviews)
- **Channel setup:** One-time YAML editing + OAuth flow (acceptable for expert users)
- **Error scenarios:** Detailed error logs and retry controls only appear when needed
- **Scale tuning:** Advanced orchestration parameters hidden unless user seeks them

Complexity hidden until needed, revealed at appropriate skill level.

**4. Spatial Memory for Multi-Channel Management**
Each channel gets a dedicated Notion page with visual branding (emoji, color, banner). Video tasks live under their parent channel page as sub-pages. Users leverage spatial memory ("philosophy videos are on the 🧠 blue page, science videos are on the 🔬 green page") to avoid channel confusion at scale.

**5. Proactive Intelligence (Silent Auto-Recovery + Targeted Alerts)**
System auto-retries 80% of failures with exponential backoff (rate limits, timeouts, network errors). Users receive zero alerts for auto-recovered failures. Alerts only fire for the 20% requiring human judgment (quota exceeded, invalid credentials, unrecoverable errors). Reduces alert fatigue, focuses attention on decisions only humans can make.

**UX Philosophy:** "The system works while I sleep, only wakes me when it truly needs help."

---

## Core User Experience

### Defining Experience

**Primary User Action:** Monitoring video production progress across multiple channels via Kanban board interface

**Core Experience Loop:**
1. User opens Notion → Views Kanban board with all video tasks
2. Glances across columns to assess overall progress ("everything moving?")
3. Identifies cards needing attention (stuck in status, errors, ready for review)
4. Takes action (review assets, check error logs, approve, retry)
5. Continues monitoring as tasks flow toward "Published"

**Secondary User Actions:**
- **Reviewing:** Approving generated assets, videos, audio at quality gates
- **Planning:** Creating new video entries in Notion (5-10 min per video)
- **Error Response:** Investigating failures, manually retrying, adjusting priorities

**Frequency Hierarchy:**
- Monitoring: Multiple times per day (glanceable, passive)
- Reviewing: 3 times per video (deliberate, quality control)
- Planning: Weekly batch sessions (creative, strategic)
- Error Response: As-needed (reactive, diagnostic)

### Platform Strategy

**Primary Interface:** Notion Board View (Kanban-style database)

**Platform Rationale:**
- Leverages Notion's native Board view (zero custom development)
- Users already familiar with Notion's UX patterns
- Real-time updates built-in (1-2 minute acceptable lag)
- Mobile app included (horizontal swipe through columns)
- Infinite customization via Notion's database features

**Board Structure:**
- **26 status columns:** Normal workflow states + error-specific states
  - Normal: Queued → Generating Assets → Assets Ready → Generating Video → Video Ready → Generating Audio → Audio Ready → Assembling → Uploading → Published
  - Errors: Error: Assets Failed, Error: Video Failed, Error: Audio Failed, Error: Assembly Failed, Error: Upload Failed (plus others)
- **Card properties:** Title, Channel (emoji/color identifier), Time in Current Status, Priority
- **Relations:** Tasks → Assets, Tasks → Videos, Tasks → Audio (for review workflows)

**Desktop Experience:**
- Wide Kanban board with horizontal scroll
- Click card → Modal with quick actions + details
- Asset review: Modal gallery overlay for quick approval OR dedicated page for detailed inspection

**Mobile Experience:**
- Horizontal swipe through columns (Trello-style)
- Same card click → quick actions pattern
- Optimized for monitoring and quick approvals (detailed work on desktop)

**Platform Constraints Accepted:**
- Cannot add custom quick-action buttons directly on cards (must click card first)
- Limited card visual customization (rely on column position + properties)
- Mobile board view basic but functional

**Future Consideration:**
- If Notion limitations become friction at scale, custom dashboard remains option
- For MVP, Notion Board view provides 90% of needed functionality

### Effortless Interactions

**What Happens Automatically (Zero User Action Required):**

1. **Status Updates:** Tasks move across board columns as pipeline progresses in real-time
2. **Error Detection:** System identifies failures, moves cards to error columns, populates error logs
3. **Auto-Retry:** 80% of transient failures retry automatically with exponential backoff (user sees card stay in column briefly, then continue)
4. **Time Tracking:** "Time in Current Status" updates automatically every minute
5. **Asset Population:** Generated images/videos/audio auto-link to task via Notion relations
6. **Thumbnail Generation:** Asset previews load automatically when user clicks "View Assets"
7. **YouTube URL Population:** Published cards auto-populate with YouTube link after upload

**What Feels Effortless (Minimal User Effort):**

1. **Glanceable Monitoring:** Open Notion → Board view → Instantly see overall progress and bottlenecks
2. **Quick Approvals:** Click card → View assets → Approve → Card moves to next stage (30 seconds)
3. **Batch Operations:** Select multiple cards in "Assets Ready" → Approve all at once
4. **Error Investigation:** Click error card → Error log panel shows exactly what failed and why
5. **Priority Adjustment:** Drag-and-drop card to change priority queue position
6. **Channel Filtering:** Click channel tag → See only tasks for that channel

**Friction We Eliminate:**

- **No terminal commands** for daily monitoring (vs. current CLI workflow)
- **No file system navigation** to check progress (vs. checking folders for output files)
- **No manual status tracking** in spreadsheets or notes
- **No "is it done yet?" checking** of long-running processes (board updates automatically)

### Critical Success Moments

**Visual Success Indicators:**

1. **"Everything Is Moving"**
   - **Experience:** User opens board, sees cards flowing through columns with normal time-in-status values
   - **Feeling:** Confidence, control, system is working
   - **Visual:** Green/normal status across board, no cards stuck

2. **"Card Stuck = Problem"**
   - **Experience:** Card shows "Generating Video - 45m" when typical is 2-5 minutes
   - **Feeling:** Immediate attention signal, something needs investigation
   - **Visual:** Time-in-status value stands out as abnormal
   - **Make-or-Break:** This is THE critical failure indicator for monitoring

3. **"Review Is Fast"**
   - **Experience:** Card reaches "Assets Ready" → Click view → See 22 images → Approve → Card moves to "Generating Video" (30-second flow)
   - **Feeling:** Efficient quality control, not a bottleneck
   - **Visual:** Modal gallery with clear approve/reject options

4. **"Error Is Actionable"**
   - **Experience:** Card in "Error: Video Failed" column → Click → Error log shows "Kling API timeout after 3 retries, will retry at 2:15 PM"
   - **Feeling:** Informed, clear next action (wait for auto-retry or manual intervention)
   - **Visual:** Error log with timestamp, cause, and retry status

5. **"Published Confirms Success"**
   - **Experience:** Card reaches "Published" column with YouTube URL populated
   - **Feeling:** Ultimate success, can share/schedule video
   - **Visual:** Clickable YouTube link in card

**First-Time User Success:**

- **Onboarding Win:** User creates first video entry in Notion, watches it progress through Kanban board columns without touching terminal
- **"Aha!" Moment:** Realizes they can plan 10 videos in one sitting, then monitor all 10 progressing in parallel on the board
- **Confidence Milestone:** First error auto-retries successfully without user intervention (sees card briefly pause, then continue)

### Experience Principles

**Guiding Principles for All UX Decisions:**

1. **"Monitor, Don't Manage"**
   - Users observe progress, not orchestrate it
   - System autonomy is the goal (95% hands-off)
   - Monitoring interface optimized for glanceability, not control
   - UX focuses on visibility, not manipulation

2. **"Stuck = Problem, Moving = Success"**
   - Time-in-status is the universal health metric
   - Cards flowing through columns at expected pace = everything working
   - Abnormal time-in-status = immediate visual indicator
   - No need to dig into logs unless card is stuck

3. **"Review Gates Prevent Waste"**
   - Approvals happen before expensive operations (video generation $5-10)
   - Quality control at critical checkpoints, not continuous oversight
   - Fast review workflows (30 seconds) prevent bottlenecks
   - Trust but verify: auto-proceed on cheap steps, manual approval on expensive steps

4. **"Progressive Complexity"**
   - Daily operations: Simple board view (status, approve, monitor)
   - Error scenarios: Detailed logs and retry controls (only when needed)
   - Channel setup: One-time technical configuration (YAML, OAuth)
   - Scale tuning: Advanced parameters hidden unless user seeks them
   - Complexity revealed at appropriate skill level and context

5. **"Spatial Memory for Channels"**
   - Each channel has visual identity (emoji, color, dedicated page)
   - Channels feel spatially distinct ("philosophy is 🧠 blue, science is 🔬 green")
   - Prevents cross-channel mistakes at scale (wrong video uploaded to wrong channel)
   - Leverages human spatial cognition for multi-channel management

---

## Desired Emotional Response

### Primary Emotional Goals

**Core Emotional State:** Calm, Confident Control Through Trusted Automation

Users should feel like they're **observing a reliable system working for them**, not managing a fragile process that requires constant attention. The primary emotion is **peace of mind** - the system is running, progress is visible, intervention is only needed when the system explicitly signals it.

**Primary Emotional Goal:**
- **Trust & Confidence:** "I trust this system to handle 95% of production autonomously while keeping me informed"

**Supporting Emotional States:**
- **Calm Assurance:** "Everything is moving as expected, I don't need to worry"
- **Spaciousness:** "I have mental and temporal space for creative work, not pipeline babysitting"
- **Clarity:** "When something needs my attention, it's immediately obvious what and why"
- **Quiet Accomplishment:** "Look at the scale I'm achieving while staying focused on content quality"

**NOT These Emotions:**
- NOT "excited hustle" or "productive grind" (leads to burnout at scale)
- NOT "delighted surprise" at every interaction (automation should be reliable, not novel)
- NOT "anxious monitoring" or "constant vigilance" (defeats purpose of automation)

### Emotional Journey Mapping

**Phase 1: Discovery → Intrigued Skepticism**
- **Context:** User reads about Notion → YouTube automation with 95% autonomy
- **Desired Emotion:** "This sounds too good to be true, but I desperately want it to be real"
- **UX Support:** Clear documentation of success metrics, realistic expectations (95% not 100%), transparent limitations

**Phase 2: First Use → Surprised Delight**
- **Context:** User creates first video entry in Notion, watches it progress through Kanban board without touching terminal
- **Desired Emotion:** "Holy shit, it's actually happening. I just watched a card move from 'Queued' to 'Generating Assets' to 'Assets Ready' while I got coffee"
- **UX Support:** Real-time status updates, visible progress, clear "time in status" feedback, first success feels magical

**Phase 3: Daily Monitoring → Calm Assurance**
- **Context:** User opens Kanban board multiple times per day, glances across columns
- **Desired Emotion:** "Everything's moving as expected. Cards are flowing. No red flags. I can get back to creative work."
- **UX Support:** Glanceable status overview, normal time-in-status values, visual "everything is green" feedback, no alerts when system is healthy

**Phase 4: Review Gates → Efficient Quality Control**
- **Context:** User clicks "Assets Ready" card, reviews 22 images, approves in 30 seconds
- **Desired Emotion:** "Quick quality check, everything looks good, approved. Not a bottleneck."
- **UX Support:** Fast modal gallery, clear approve/reject buttons, batch operations, single-click to next stage

**Phase 5: Error Scenario → Informed Confidence**
- **Context:** Card stuck in "Error: Video Failed", user clicks for details
- **Desired Emotion:** "I know exactly what failed (Kling timeout), why (API slow today), and what's happening (auto-retry at 2:15 PM). I trust the system to handle this or will tell me if I need to intervene."
- **UX Support:** Clear error logs with timestamp and cause, auto-retry status visible, distinction between "system handling" vs "needs your action"

**Phase 6: Weekly Review → Quiet Accomplishment**
- **Context:** Friday afternoon, user filters board by "Published" this week, sees 95 videos completed
- **Desired Emotion:** "Look at what got done while I focused on content planning and creative decisions, not pipeline orchestration. I'm scaling without burning out."
- **UX Support:** Week-over-week metrics, success rate visibility (95 of 100 = 95%), cost tracking ($570 for 95 videos = on budget), published video links

**Phase 7: Long-Term Use → Deep Trust**
- **Context:** User has published 500+ videos over 3 months, system autonomy rate remains 94-96%
- **Desired Emotion:** "This is my content production infrastructure. I trust it like I trust electricity - I flip the switch (create Notion entry), it works, I move on."
- **UX Support:** Consistent reliability metrics, predictable behavior, silent auto-recovery, alerts only when truly needed

### Micro-Emotions

**Critical Micro-Emotional Shifts:**

**1. Anxiety → Trust**
- **Before (CLI):** "Did the script finish? Should I check the folder? What if it silently failed 3 hours ago?"
- **After (Kanban):** "System updates me automatically. If there's a problem, the card will be in an error column and I'll see it instantly."
- **Design Support:** Real-time status updates (1-2 min lag acceptable), automatic error detection and notification, no silent failures

**2. Overwhelm → Spaciousness**
- **Before (CLI):** "10 videos = 15-20 hours of terminal orchestration this week. I'm drowning in pipeline management."
- **After (Kanban):** "10 videos = 1 hour of Notion planning + 3 quick review sessions. The rest happens automatically. I have space for creative work."
- **Design Support:** Autonomous operation (95%), batch planning workflows, quick review gates (30 seconds), no daily terminal commands

**3. Stress → Clarity**
- **Before (CLI):** "Something failed. Which step? Which file? Do I re-run from beginning or restart mid-pipeline? Where are the logs?"
- **After (Kanban):** "Card in 'Error: Video Failed' column. Click. 'Kling API timeout after 3 retries, will retry at 2:15 PM.' Clear. Done."
- **Design Support:** Error states by column position, detailed error logs with actionable next steps, auto-retry status visible, manual retry one-click

**4. Confusion → Confidence**
- **Before (CLI):** "Is this video at the asset stage or video generation stage? Let me check folder timestamps..."
- **After (Kanban):** "Card position tells me instantly. 'Generating Video - 3m' means it's 3 minutes into video generation."
- **Design Support:** Visual column position = status, time-in-status property, no need to check filesystem or logs

**5. Fragmented → Focused**
- **Before (CLI):** "Constantly context-switching between terminal windows, folder navigation, checking if processes finished."
- **After (Kanban):** "One Notion board. Glance once per hour. Only drill in when card needs review or error needs attention."
- **Design Support:** Single source of truth (Notion), glanceable monitoring, progressive disclosure (details only when clicked)

### Design Implications

**Emotion-Driven UX Decisions:**

**1. Trust → Reliability Signals**
- **Design Choices:**
  - Show "time in status" automatically updating (system is alive and monitoring)
  - Display auto-retry attempts transparently ("Retry 2 of 5 at 2:15 PM")
  - Expose system health metrics (95% success rate over last 100 videos)
  - Publish error logs in human-readable format with clear cause and resolution
- **What We Avoid:** Silent failures, vague error messages, system state opacity

**2. Calm Assurance → Glanceable Status**
- **Design Choices:**
  - Kanban board optimized for quick scan across columns
  - "Everything is green" visual confirmation (no errors = calm color palette)
  - Cards moving through columns = visible progress
  - Abnormal time-in-status stands out (45 minutes vs. typical 3 minutes)
- **What We Avoid:** Information overload, constant notifications, requiring deep investigation to assess health

**3. Spaciousness → Autonomous Operation**
- **Design Choices:**
  - Auto-proceed through low-cost steps (assets $0.50)
  - Review gates only at expensive steps (video $5-10)
  - 80% of errors auto-retry without user intervention
  - Batch operations (approve 10 asset sets at once)
- **What We Avoid:** Requiring approval for every tiny decision, forcing serial workflows, manual retry for transient failures

**4. Clarity → Actionable Errors**
- **Design Choices:**
  - Error columns group failures by type ("Error: Video Failed", not generic "Error")
  - Error logs show: What failed, Why, What's happening now (auto-retry? needs manual?), When retry will occur
  - Manual retry is one-click action from card
  - Clear distinction: "System handling this (blue badge)" vs "Needs your action (red badge)"
- **What We Avoid:** "Something went wrong" generic errors, requiring log file archaeology, unclear next steps

**5. Quiet Accomplishment → Week-Over-Week Visibility**
- **Design Choices:**
  - Filter board by "Published this week" to see batch accomplishments
  - Show metrics: 95 videos published, $570 spent, 95% success rate
  - Clickable YouTube URLs in published cards (see your work live)
  - No daily "you did it!" celebrations (would get annoying at scale)
- **What We Avoid:** Gamification (badges, streaks, points), over-celebrating routine success, hiding aggregate metrics

### Emotional Design Principles

**Guiding Principles for Emotional UX:**

**1. "Visible Progress, Invisible Complexity"**
- Users see cards flowing through columns (progress)
- Users don't see: async worker queues, database transactions, retry exponential backoff logic (complexity)
- Emotional Goal: Confidence without cognitive overload

**2. "Trust Through Transparency"**
- System shows exactly what it's doing (status updates, error logs, retry attempts)
- System never lies or hides failures
- But: Only surfaces details when user needs them (progressive disclosure)
- Emotional Goal: Deep trust through honest, clear communication

**3. "Alert Fatigue Is Emotional Fatigue"**
- 80% auto-recovery happens silently (user sees card pause briefly, then continue)
- Alerts only fire for 20% requiring human judgment
- Each alert is actionable (not just informative)
- Emotional Goal: Peace of mind, not constant vigilance

**4. "Accomplishment Should Feel Quiet, Not Loud"**
- At 100 videos/week, celebration for each would be noise
- Success = "I glance at board Friday afternoon, see 95 published, feel satisfied, close laptop"
- Metrics visible when sought, not pushed constantly
- Emotional Goal: Sustainable satisfaction, not burnout-inducing hustle

**5. "Spatial Clarity Prevents Channel Chaos"**
- Each channel has visual identity (emoji, color, dedicated page)
- User knows "I'm in the philosophy channel" by visual context
- Cross-channel mistakes feel impossible (spatial memory reinforcement)
- Emotional Goal: Confident multi-channel management without fear of errors

---

## UX Pattern Analysis & Inspiration

### Inspiring Products Analysis

**1. Notion - Database Flexibility & Board Views**

**Strengths:**
- Infinite workspace customization without code (databases, views, relations, formulas)
- Board view provides Kanban-style task management with drag-and-drop
- Same data, multiple perspectives (board, table, calendar, gallery views)
- Progressive disclosure - simple by default, powerful when needed

**Why It Works:** Expert users feel in control - they shape the tool to their workflow, not the reverse. Everything lives in one place, eliminating context switching.

**Key Takeaways for ai-video-generator:**
- Leverage Notion's board view as primary monitoring interface (zero development cost)
- Use database relations to link tasks → assets → videos → audio
- Encourage users to create custom filtered views per channel or priority
- Use formula fields for calculated properties (cost tracking, time-in-status)

---

**2. Linear - Speed & Keyboard-First Design**

**Strengths:**
- Blazingly fast interface - feels instant, no loading spinners
- Keyboard shortcuts everywhere - Cmd+K command palette, hotkeys for all actions
- Smart defaults reduce decision fatigue (auto-assignment, auto-priority)
- Clean, focused UI with crystal-clear information hierarchy

**Why It Works:** Speed compounds at scale. Saving 2 seconds per action × 100 actions/day = significant productivity gain. Keyboard shortcuts make power users feel superhuman.

**Key Takeaways for ai-video-generator:**
- Train users on Notion's Cmd+K for fast navigation (don't build custom, leverage existing)
- Keep card properties minimal - only essential info visible on board
- Consider keyboard shortcuts for approval workflows (if Notion API supports)
- Fast filtering via Notion's native UI (click channel tag → instant filter)

---

**3. Zapier/Make - Visual Workflows & Run History**

**Strengths:**
- Visual workflow builder shows automation pipeline at a glance
- Detailed run history - click any execution to see step-by-step what happened
- Error highlighting makes failures immediately visible (red steps)
- Every run logs inputs, outputs, errors as first-class data

**Why It Works:** Visual pipelines make complex flows comprehensible. Run history provides debugging superpowers - users can trace exactly when and why failures occurred.

**Key Takeaways for ai-video-generator:**
- Kanban board IS the visual workflow (cards flow through columns like Zapier steps)
- Error logs as first-class feature - click error card → detailed execution log
- Task history shows all status transitions with timestamps (audit trail)
- "What happened?" visibility for every task (created when, started when, failed when/why)

---

**4. GitHub Actions / Railway Dashboard - Real-Time Build Monitoring**

**Strengths:**
- Live logs streaming - watch build output in real-time
- Step-by-step progress indicators (which step currently running)
- Green/red status badges - glanceable health checks
- One-click retry from failure point (not re-run entire workflow)
- Commit → deploy pipeline visualization

**Why It Works:** Real-time feedback builds confidence - users see the system working, don't need to worry. Step granularity enables precise debugging.

**Key Takeaways for ai-video-generator:**
- Time-in-status auto-updates provide "live progress" feedback
- Show current substep where valuable (e.g., "Generating Video - Clip 5/18")
- Visual indicators: normal columns (green/blue), error columns (red)
- One-click retry directly from error cards
- Per-channel status badges showing aggregate health (95% success this week)

---

**5. Datadog / Grafana - Observability Dashboards**

**Strengths:**
- Multi-metric dashboards show system health at a glance (10+ graphs on one screen)
- Time-series visualization reveals trends and patterns (error spike at 2 PM?)
- Alert rules with thresholds automate monitoring (system watches, user intervenes only when needed)
- Drill-down from aggregate to detail (click spike → see individual failures)

**Why It Works:** Dashboards surface patterns humans would miss in raw data. Alerts reduce monitoring burden - system only pings when thresholds breached.

**Key Takeaways for ai-video-generator:**
- Per-channel aggregate metrics (success rate, avg time per step, weekly cost)
- Anomaly detection via simple thresholds (video gen normally 2-5 min, alert if >15 min)
- Threshold-based Slack alerts (success rate <90%, quota exceeded)
- Weekly dashboard showing trends (95 videos published this week vs. 87 last week)
- Drill-down: click channel health → see specific failed tasks

---

**6. Jira - Custom Workflows & Bulk Operations**

**Strengths:**
- Customizable workflows per project (define your own statuses and transitions)
- Bulk operations at scale (select 10 issues → change status simultaneously)
- Filters as saved views (complex queries bookmarked for reuse)
- Sprint planning drag-and-drop (visual capacity planning)

**Why It Works:** Workflows match organizational reality, not forced into generic states. Bulk operations save hours when managing 100+ tasks. Saved filters = personalized views for different roles.

**Key Takeaways for ai-video-generator:**
- Notion supports custom statuses (define workflow columns that match your process)
- Bulk operations via Notion multi-select (change status/priority/channel for multiple cards)
- Filtered views as saved pages ("Philosophy Channel Errors", "High Priority Ready for Review")
- Allow manual status changes for expert users (move card back to regenerate assets)

### Transferable UX Patterns

**Navigation Patterns:**

1. **Command Palette Navigation** (Linear Cmd+K, Notion Quick Find)
   - **Application:** Leverage Notion's existing Cmd+K for instant channel/task search
   - **Benefit:** Power users navigate without mouse, zero learning curve

2. **Saved Filtered Views** (Jira filters, Notion database views)
   - **Application:** Create bookmark views like "All Errors", "Ready for Review", "Philosophy Channel This Week"
   - **Benefit:** Personalized perspectives on same data, fast context switching

3. **Hierarchical Navigation** (Notion pages, GitHub repos)
   - **Application:** Channels as parent pages → Tasks as subpages → Assets/videos as relations
   - **Benefit:** Spatial memory reinforcement, clear information architecture

**Monitoring Patterns:**

1. **Glanceable Health Indicators** (GitHub Actions badges, Grafana panels)
   - **Application:** Color-coded columns (green for normal, red for error), time-in-status prominently displayed
   - **Benefit:** Answer "is everything OK?" in 2-second glance at board

2. **Real-Time Status Updates** (Railway deploys, GitHub Actions)
   - **Application:** Time-in-status auto-updates every minute, status transitions push to Notion within 1-2 min
   - **Benefit:** Trust through transparency - users see system is alive and working

3. **Anomaly Highlighting** (Datadog alerts, threshold detection)
   - **Application:** When time-in-status exceeds 3× typical value, visual warning on card
   - **Benefit:** "Stuck card" detection without manual calculation

4. **Aggregate → Detail Drill-Down** (Grafana dashboards)
   - **Application:** Channel page shows weekly metrics → click "5 failures" → see failed tasks
   - **Benefit:** Start with overview, drill in only when needed

**Interaction Patterns:**

1. **One-Click Retry** (GitHub Actions re-run, Zapier replay)
   - **Application:** Error card → Click "Retry" → Task requeues immediately
   - **Benefit:** Fast error recovery, minimal friction

2. **Bulk Operations** (Jira multi-select, Notion bulk edit)
   - **Application:** Select 10 "Assets Ready" cards → Click "Approve All" → All move to next stage
   - **Benefit:** Efficient review gates at scale (100 videos/week)

3. **Modal Overlays for Quick Actions** (Linear issue detail, Notion page modals)
   - **Application:** Click card → Modal with quick actions (view assets, approve, retry, logs)
   - **Benefit:** Fast interactions without full page navigation

4. **Keyboard Shortcuts for Power Users** (Linear shortcuts, Notion hotkeys)
   - **Application:** Leverage Notion's existing hotkeys (Cmd+Enter to open, Escape to close)
   - **Benefit:** Speed for frequent actions, feels powerful

**Error Handling Patterns:**

1. **Step-by-Step Execution Logs** (Zapier run history, GitHub Actions detailed view)
   - **Application:** Error card shows: "Step 3: Generate Video → Kling API timeout after 3 retries"
   - **Benefit:** Precise debugging, clear failure point

2. **Error Context at a Glance** (Zapier red step, Railway failed stage)
   - **Application:** Error cards live in error-specific columns ("Error: Video Failed" not generic "Error")
   - **Benefit:** Card position immediately conveys error type

3. **Auto-Retry with Transparency** (Zapier auto-replay attempts)
   - **Application:** Card shows "Retry 2 of 5, next attempt at 2:15 PM"
   - **Benefit:** User knows system is handling it, sees progress toward resolution

4. **Actionable Error Messages** (GitHub Actions error annotations)
   - **Application:** "Gemini API quota exceeded (1500/day), resets at 12:00 AM PST" not "Error 429"
   - **Benefit:** User knows exactly what happened and when it will resolve

**Trust-Building Patterns:**

1. **Transparent System State** (Notion real-time sync, Datadog live dashboards)
   - **Application:** Time-in-status updates every minute, Notion sync indicator shows connection health
   - **Benefit:** Users see system is working, don't worry about silent failures

2. **Run History / Audit Trail** (Zapier task history, Jira changelog)
   - **Application:** Each task logs all status transitions with timestamps and reasons
   - **Benefit:** Full traceability, can reconstruct what happened when

3. **Predictable Behavior** (Linear consistency, Notion reliability)
   - **Application:** Auto-retry follows exponential backoff rules consistently, status updates reliable
   - **Benefit:** Users learn system's patterns, build deep trust over time

4. **Honest Limitations** (GitHub Actions queue depth, Zapier rate limits)
   - **Application:** Show API quota status ("450/1500 Gemini images today"), realistic ETA for retries
   - **Benefit:** Manage expectations, no surprises, feels honest

### Anti-Patterns to Avoid

**1. Notification Overload**
- **Bad Example:** Jira sending emails for every comment, status change, and mention
- **Why It Fails:** Alert fatigue → users ignore all notifications → miss truly critical ones
- **How We Avoid:** Slack/email alerts ONLY for 20% of errors requiring human judgment (quota exceeded, auth failed). Auto-recoveries (80%) happen silently.

**2. Hidden Complexity (False Simplicity)**
- **Bad Example:** Zapier "simple mode" hiding powerful features behind paywall or hard-to-find settings
- **Why It Fails:** Expert users hit ceiling fast, feel tool underestimates their abilities
- **How We Avoid:** Progressive disclosure with discoverability - simple by default, but advanced features visible and accessible (not hidden behind menus)

**3. Slow Dashboards**
- **Bad Example:** Grafana dashboards taking 10+ seconds to load large time ranges
- **Why It Fails:** Users won't check dashboard if it's slow → defeats purpose of monitoring
- **How We Avoid:** Notion board loads in 1-2 seconds, acceptable 1-2 min lag for status updates (fast enough for monitoring at scale)

**4. Generic Error Messages**
- **Bad Example:** "Something went wrong. Try again later." (no details, timestamp, or cause)
- **Why It Fails:** User can't diagnose, can't fix, loses trust in system competence
- **How We Avoid:** Error logs MUST show: What failed (step name), Why (API error code + message), When (timestamp), What's next (auto-retry schedule or manual action needed)

**5. Forced Linear Workflows**
- **Bad Example:** Tools preventing users from skipping steps even when they know their context
- **Why It Fails:** Expert users understand their domain, forced hand-holding is insulting and frustrating
- **How We Avoid:** Allow manual status changes (move card back to regenerate, jump forward to force progress), allow priority queue adjustments, allow review gate skipping (with confirmation)

**6. Over-Gamification**
- **Bad Example:** "You completed 10 tasks today! 🎉🎊" celebrations after every mundane action
- **Why It Fails:** Novelty wears off immediately, becomes noise at scale (100 videos/week = 300 celebrations)
- **How We Avoid:** Quiet accomplishment model - metrics visible when user seeks them (weekly dashboard), not pushed constantly. Success = calm satisfaction, not confetti explosions.

**7. Inconsistent UI Patterns**
- **Bad Example:** Notion's sometimes-inconsistent modal behavior (Escape key works differently in different contexts)
- **Why It Fails:** Users build muscle memory for patterns, inconsistency breaks flow and frustrates
- **How We Avoid:** Leverage Notion's existing patterns consistently, don't fight the platform's conventions. When adding custom elements, match Notion's interaction paradigms.

**8. Premature Custom Development**
- **Bad Example:** Building custom dashboard before proving Notion limitations at real usage scale
- **Why It Fails:** Wastes development time on features Notion provides for free, creates maintenance burden
- **How We Avoid:** Start with Notion Board view (provides 90% of needed functionality), only build custom dashboard if hitting clear, validated limitations after months of production use

### Design Inspiration Strategy

**What to Adopt Directly:**

1. **Notion Board View as Primary Interface**
   - **Source:** Notion database board view
   - **Reason:** Already familiar to expert users, highly customizable, zero development cost
   - **Application:** 26-column Kanban board for monitoring all video production tasks

2. **Real-Time Status Updates**
   - **Source:** GitHub Actions live logs, Railway deployment tracking
   - **Reason:** Builds trust, reduces anxiety about system health, provides confidence
   - **Application:** Time-in-status auto-updates every minute, status transitions push to Notion within 1-2 min

3. **One-Click Retry from Errors**
   - **Source:** GitHub Actions "Re-run failed jobs", Zapier "Replay task"
   - **Reason:** Fast error recovery with minimal friction, empowers users to fix issues immediately
   - **Application:** Click error card → "Retry" button → Task requeues and processes immediately

4. **Detailed Execution Logs**
   - **Source:** Zapier run history with step-by-step details, GitHub Actions job annotations
   - **Reason:** Debugging superpower, provides actionable information for troubleshooting
   - **Application:** Error cards expose: failed step, error message, retry attempts, next retry timestamp

**What to Adapt for Our Context:**

1. **Command Palette Navigation**
   - **Source:** Linear Cmd+K universal search, Notion Quick Find
   - **Adaptation:** Don't build custom - leverage Notion's existing Cmd+K functionality
   - **Training:** Document keyboard shortcut usage in onboarding, encourage power user workflows

2. **Anomaly Detection Alerts**
   - **Source:** Datadog ML-based anomaly detection, Grafana threshold alerts
   - **Adaptation:** Use simple threshold-based detection (not ML) - if time-in-status > 3× typical, flag as stuck
   - **Rationale:** ML overkill for our use case, simple thresholds sufficient for detecting stuck tasks

3. **Aggregate Metric Dashboards**
   - **Source:** Grafana multi-metric panels, Datadog system overviews
   - **Adaptation:** Per-channel summary pages (not system-wide graphs) showing weekly stats
   - **Application:** Channel pages display: success rate this week, videos published, total cost, error count

4. **Step-by-Step Progress Indicators**
   - **Source:** GitHub Actions showing which step is running, Zapier showing current action
   - **Adaptation:** Show substep progress only where valuable (video generation: "Clip 5/18 completed")
   - **Rationale:** Not all steps benefit from substep visibility, only show when it adds clarity

**What to Avoid (At Least Initially):**

1. **Custom Dashboard Development**
   - **Reason:** Notion Board view provides 90% of functionality, avoid premature optimization
   - **Decision:** Validate Notion limitations at production scale before building custom UI

2. **Complex Workflow Validation Rules**
   - **Source:** Jira transition guards, required fields, approval gates
   - **Reason:** Expert users don't need hand-holding, forced validations add friction without value
   - **Decision:** Allow manual status changes, trust user judgment, provide guardrails through UI hints not enforcement

3. **Real-Time Streaming Logs**
   - **Source:** GitHub Actions live log streaming, Railway build output streams
   - **Reason:** Video generation takes 2-5 minutes (not seconds), streaming adds complexity without value
   - **Decision:** Write logs at end of each step, not streamed during execution (batch updates sufficient)

4. **Complex Notification Customization**
   - **Source:** Jira's extensive notification rule builder, custom alert routing
   - **Reason:** Over-configuration leads to decision paralysis, most users never customize
   - **Decision:** Simple alert rules - Slack/email on unrecoverable errors only, auto-retry happens silently

**Design Philosophy:**

**"Borrow Proven Patterns, Adapt to Context, Avoid Premature Complexity"**

We stand on the shoulders of giants (Notion, Linear, GitHub, Zapier, Datadog). Their UX patterns are battle-tested with millions of expert users. Rather than reinvent, we:
- **Adopt** patterns that transfer directly (Notion board view, one-click retry, detailed logs)
- **Adapt** patterns that need context-specific modification (anomaly thresholds, substep visibility)
- **Avoid** patterns that add complexity without proportional value (custom dashboards, streaming logs, workflow guards)

Our competitive advantage is not novel UX patterns - it's combining proven patterns in service of our specific emotional goals (calm control, trust, spaciousness) for our specific workflow (monitoring 100 videos/week across 5-10 channels).

---

## Design System Foundation

### Design System Choice

**Decision: Defer Custom Design System Selection Until Validated Need**

**Primary Interfaces (MVP):**
1. **Notion Board View** - Main monitoring and task management interface
2. **Notion Database** - Task creation, filtering, configuration
3. **YAML Configuration Files** - Channel setup (voice IDs, auto-proceed settings, priorities)
4. **CLI & Environment Variables** - OAuth setup, deployment configuration
5. **Slack/Email** - Error alerts and notifications

**No Custom UI Development for MVP**

### Rationale for Selection

**Why Defer Design System Choice:**

1. **Notion Provides 90% of UI Needs**
   - Kanban board for monitoring (26-column workflow visualization)
   - Database views for filtering and custom perspectives
   - Relations for linking tasks to assets/videos/audio
   - Formula fields for calculated properties (time-in-status, cost tracking)
   - Real-time collaboration and mobile app built-in
   - Zero development cost, zero maintenance burden

2. **Expert User Comfort with Non-GUI Interfaces**
   - Target user (Francis) comfortable with YAML configuration
   - CLI tools acceptable for one-time setup (OAuth, channel initialization)
   - Terminal-based workflows familiar from current CLI pipeline
   - No need to "simplify" with GUI for expert users

3. **Avoid Premature Optimization**
   - Choosing design system now = planning for hypothetical future UI
   - Custom UI might never be needed (Notion may scale perfectly to 100 videos/week)
   - Design system selection should be driven by validated pain points, not speculation
   - Development resources better spent on backend robustness and automation quality

4. **Backend-First Architecture Alignment**
   - FastAPI orchestrator exposes API, not HTML
   - Workers process tasks, don't serve UI
   - PostgreSQL stores state, Notion surfaces it
   - System designed for API-first integration (Notion API, Slack API, webhook endpoints)

5. **Faster Time to MVP**
   - Zero frontend development = faster deployment
   - No design system learning curve
   - No component library integration
   - No CSS framework setup or theme configuration
   - Focus 100% on pipeline automation and reliability

**When to Revisit This Decision:**

Re-evaluate design system choice if any of these validated limitations emerge:

1. **Performance at Scale:**
   - Notion board with 500+ cards becomes slow to load (>5 seconds)
   - Real-time updates lag significantly (>5 minutes)
   - Database queries timeout on complex filters

2. **Feature Limitations:**
   - Notion can't support required workflow automations (conditional status transitions)
   - Custom visualizations needed (time-series graphs, cost trend analysis)
   - Batch operations too limited (approve 50 assets requires 50 clicks)

3. **User Expansion:**
   - Non-expert users join (need simplified UI, not YAML configuration)
   - Team grows beyond single user (need role-based permissions Notion can't provide)
   - External stakeholders need dashboard access (can't share Notion workspace)

4. **Integration Constraints:**
   - Notion API rate limits hit (5 requests/second, 1000/minute)
   - Notion downtime impacts operations (need backup monitoring interface)
   - Data export requirements for compliance (need custom reporting UI)

**Trigger for Design System Selection:** If 2+ limitations above validated in production after 1-2 months of operation, proceed with design system choice.

### Implementation Approach

**MVP Implementation (No Custom UI):**

**1. Notion as Primary Interface**
- Set up Notion workspace with database for video tasks
- Define database schema:
  - Properties: Title (text), Channel (select), Status (select - 26 options), Priority (select), Time in Status (formula), Created (date), Updated (date)
  - Relations: Tasks → Assets (multi-relation), Tasks → Videos (multi-relation), Tasks → Audio (multi-relation)
- Create Board view (default - Kanban by Status)
- Create saved filter views:
  - "All Errors" (Status starts with "Error:")
  - "Ready for Review" (Status ends with "Ready")
  - "High Priority" (Priority = High)
  - Per-channel views (Channel = "Philosophy", etc.)

**2. Backend API Integration**
- FastAPI orchestrator uses Notion API SDK to:
  - Create tasks when videos queued
  - Update task status as pipeline progresses
  - Update time-in-status property every 60 seconds
  - Populate relations when assets/videos/audio generated
  - Add error logs to task page body when failures occur
- Webhook endpoint receives Notion database changes (manual status overrides, priority changes)

**3. Configuration via Files**
- Channel configuration: `channels/<channel-id>.yaml`
  - Voice ID, auto-proceed flags, priority defaults, review gate settings
- System configuration: `.env` file
  - API keys (Gemini, Kling, ElevenLabs, Notion, Slack)
  - Database connection string (Railway PostgreSQL)
  - Worker concurrency settings

**4. CLI Tools for Setup**
- `setup_channel.py` - Initialize new YouTube channel (OAuth, YAML generation)
- `notion_init.py` - Create Notion database with correct schema
- `test_pipeline.py` - Verify all integrations working

**5. Monitoring & Alerts**
- Slack integration for error notifications (only unrecoverable errors)
- Email fallback if Slack unavailable
- Railway logs for system diagnostics
- Notion activity log for audit trail

**No Frontend Framework, No Build Pipeline, No Component Library**

### Customization Strategy

**Since No Custom UI for MVP, "Customization" Means:**

**1. Notion Workspace Customization**
- **Visual Branding per Channel:**
  - Channel pages use emoji icons (🧠 Philosophy, 🔬 Science, 🎨 Art, etc.)
  - Page covers with channel-appropriate imagery (Notion's cover library)
  - Consistent color-coding via select property colors
- **Board View Optimization:**
  - Column ordering matches workflow sequence
  - Card preview properties limited to essential info (Title, Channel, Time in Status)
  - Hidden properties for internal tracking (created timestamp, retry count)
- **Formula Fields for Calculated Data:**
  - Time in Status: `formatDate(now() - prop("Updated"), "m 'min'")` (live updating)
  - Cost Estimate: Based on status (if "Generating Video", cost = $5-10)
  - Success Rate: Rollup from task history

**2. YAML Configuration Templates**
- Provide `channels/template.yaml` with documented options
- Copy template for new channels, customize values
- Schema validation on startup (fail fast if invalid YAML)

**3. Slack Alert Customization**
- Configurable per channel: which errors trigger alerts
- Message templates with channel context (emoji, name, link)
- Severity levels (warning vs critical)

**4. If Custom UI Eventually Needed (Future):**

**Phase 1: Lightweight Admin Panels Only**
- OAuth setup wizard (guide user through YouTube authentication flow)
- Channel configuration UI (edit YAML via form, avoid syntax errors)
- System health dashboard (aggregate metrics across channels)

**Phase 2: Custom Monitoring Dashboard (If Notion Limitations Hit)**
- Real-time metrics (refresh every 5 seconds, not 1-2 minutes)
- Time-series graphs (error rate trends, throughput over time)
- Advanced filtering (complex queries Notion can't support)

**Recommended Design System When Needed:**
- **Tailwind CSS + Shadcn UI** for admin panels (lightweight, copy-paste components)
- **Recharts** or **Chart.js** for time-series visualizations if needed
- **React** for interactivity, served as static assets from FastAPI

**Philosophy:** Build custom UI only when Notion limitations validated in production. Start minimal (single admin page), expand only as needed. Always prefer Notion-native solutions over custom UI when possible.
