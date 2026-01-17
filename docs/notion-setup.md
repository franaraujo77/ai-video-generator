# Notion Database Setup Guide

**Purpose:** Configure Notion database views for glanceable monitoring of the video generation pipeline.

**Target Audience:** Content creators managing multiple YouTube channels using this platform.

**Time Required:** ~30 minutes for complete setup.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Database Properties Overview](#database-properties-overview)
3. [View 1: Kanban by Status (Primary View)](#view-1-kanban-by-status-primary-view)
4. [View 2: Needs Review (Actionable Items)](#view-2-needs-review-actionable-items)
5. [View 3: All Errors (Troubleshooting)](#view-3-all-errors-troubleshooting)
6. [View 4: Published (Completed Work)](#view-4-published-completed-work)
7. [View 5: High Priority (Optional)](#view-5-high-priority-optional)
8. [View 6: In Progress (Monitoring)](#view-6-in-progress-monitoring)
9. [Per-Channel Views (Optional)](#per-channel-views-optional)
10. [Time in Status Formula](#time-in-status-formula)
11. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before configuring views, ensure your Notion database has these properties:

**Required Properties:**
- **Title** (text) - Video title
- **Channel** (select) - Channel identifier with emoji (🧠 Philosophy, 🔬 Science, etc.)
- **Status** (select) - 27 status values matching the pipeline workflow
- **Priority** (select) - high, normal, low
- **Created** (date) - Auto-populated on task creation
- **Updated** (date) - Auto-updated on every status change
- **Topic** (text) - Video category/subject
- **Story Direction** (rich text) - Detailed video description from Notion
- **Error Log** (text) - Append-only error history (nullable)
- **YouTube URL** (url) - Populated after publish (nullable)

**Calculated Property:**
- **Time in Status** (formula) - See [Time in Status Formula](#time-in-status-formula)

---

## Database Properties Overview

### Status Property (27 Values)

The Status property MUST contain exactly 27 status values in this workflow order:

**Initial States (4):**
1. Draft
2. Queued
3. Claimed
4. Cancelled

**Asset Generation Phase - Step 1 (3):**
5. Generating Assets
6. Assets Ready ⚠️ **MANDATORY REVIEW GATE**
7. Assets Approved

**Composite Creation Phase - Step 2 (2):**
8. Generating Composites
9. Composites Ready *(auto-proceeds)*

**Video Generation Phase - Step 3 (3):**
10. Generating Video
11. Video Ready ⚠️ **MANDATORY REVIEW GATE** *(most expensive: $5-10)*
12. Video Approved

**Audio Generation Phase - Step 4 (3):**
13. Generating Audio
14. Audio Ready ⚠️ **MANDATORY REVIEW GATE**
15. Audio Approved

**Sound Effects Phase - Step 5 (2):**
16. Generating SFX
17. SFX Ready *(auto-proceeds)*

**Assembly Phase - Step 6 (2):**
18. Assembling
19. Assembly Ready *(auto-proceeds)*

**Review and Approval Phase - Step 7 (2):**
20. Final Review ⚠️ **MANDATORY REVIEW GATE** *(YouTube compliance check)*
21. Approved

**YouTube Upload Phase - Step 8 (2):**
22. Uploading
23. Published ✅ **TERMINAL SUCCESS STATE**

**Error States (4):**
24. Asset Error ❌
25. Video Error ❌
26. Audio Error ❌
27. Upload Error ❌

---

## View 1: Kanban by Status (Primary View)

**Purpose:** Visual pipeline health check - "Card stuck = problem, moving = success"

### Configuration Steps

1. **Create New View:**
   - Click "+ Add View" in your Notion database
   - Select **Board** view type
   - Name: "Kanban by Status"

2. **Group By:**
   - Group by: **Status**
   - Column order: Left to right following workflow order (Draft → Queued → ... → Published)

3. **Sort Within Columns:**
   - Primary sort: **Created** (ascending - oldest first)
   - Rationale: FIFO processing within each status

4. **Card Properties Visible:**
   - **Title** (bold, prominent)
   - **Channel** (emoji + name for quick identification)
   - **Time in Status** (health metric - shows duration in current status)
   - **Priority** (only if high/low, hide normal to reduce noise)

5. **Hidden Properties:**
   - notion_page_id (internal)
   - created_at (shown via sort, no need to display)
   - retry_count (future Epic 6 feature)

6. **Column Ordering:**
   - Arrange columns left to right in exact workflow order
   - Expected: 27 columns (requires horizontal scroll)
   - UX trade-off: Horizontal scroll acceptable for complete visibility

### Usage Tips

- **Normal flow:** Cards move left to right through columns at expected pace
- **Stuck cards:** Card not moving = investigate (check Time in Status)
- **Typical durations:**
  - Assets: 5-10 minutes
  - Video: 2-5 minutes per clip (18 clips = 36-90 minutes total)
  - Audio: 1-2 minutes per clip (18 clips = 18-36 minutes total)
  - Assembly: 30-60 seconds
- **Color indicators:** Normal (blue/green), Review gates (yellow), Errors (red)

---

## View 2: Needs Review (Actionable Items)

**Purpose:** Surface tasks requiring immediate user approval at review gates

### Configuration Steps

1. **Create New View:**
   - Click "+ Add View" in your Notion database
   - Select **Table** or **Gallery** view type
   - Name: "Needs Review"

2. **Filter:**
   - Add filter: **Status** → **is one of:**
     - Assets Ready
     - Video Ready
     - Audio Ready
     - Final Review
   - Rationale: These 4 statuses are mandatory review gates

3. **Sort:**
   - Primary sort: **Priority** (descending - high first)
   - Secondary sort: **Created** (ascending - FIFO within same priority)
   - Rationale: Urgent items first, then fair FIFO ordering

4. **Display Columns (Table View):**
   - Title
   - Channel
   - Status (to distinguish which review gate)
   - Time in Status (urgency indicator)
   - Created (shows wait time)

5. **Alternative Gallery View:**
   - Card size: Medium or Large
   - Card preview: Show Title, Channel, Status, Time in Status
   - Useful for visual review of assets/videos

### Usage Tips

- **Review workflow:**
  1. Open this view
  2. Click card to view assets/video/audio
  3. Approve or reject
  4. Card disappears from view (~10 seconds latency)
- **Video Ready priority:** Most critical gate (most expensive step: $5-10 per video)
- **Empty view = good:** No cards = no tasks waiting for approval

---

## View 3: All Errors (Troubleshooting)

**Purpose:** Aggregate error dashboard for debugging and troubleshooting

### Configuration Steps

1. **Create New View:**
   - Click "+ Add View" in your Notion database
   - Select **Table** view type
   - Name: "All Errors"

2. **Filter:**
   - Add filter: **Status** → **is one of:**
     - Asset Error
     - Video Error
     - Audio Error
     - Upload Error

3. **Sort:**
   - Primary sort: **Updated** (descending - recent errors first)
   - Rationale: Latest errors are highest priority for debugging

4. **Display Columns:**
   - Title
   - Channel
   - Status (error type)
   - **Error Log** (prominent, expanded - full error history)
   - Updated (when error occurred)
   - Retry Count (future Epic 6 feature)

5. **Column Width:**
   - Make **Error Log** column wide (~300-400px) for full error text visibility
   - Rationale: Error details are primary information for troubleshooting

### Usage Tips

- **80% auto-retry:** Rate limits and timeouts retry automatically (Epic 6)
- **20% require intervention:** Quota exceeded, auth failures need human action
- **Error format:** Each error shows: What failed, Why (API error), When (timestamp), What's next (retry schedule)
- **Empty view = healthy:** No errors = pipeline running smoothly

---

## View 4: Published (Completed Work)

**Purpose:** Archive of completed videos with YouTube links

### Configuration Steps

1. **Create New View:**
   - Click "+ Add View" in your Notion database
   - Select **Gallery** or **Table** view type
   - Name: "Published"

2. **Filter:**
   - Add filter: **Status** → **is** → **Published**

3. **Sort:**
   - Primary sort: **Updated** (descending - newest first)
   - Rationale: Recent publications on top

4. **Display Columns (Table View):**
   - Title
   - Channel
   - **YouTube URL** (clickable - primary value)
   - Updated (publish date)

5. **Alternative Gallery View:**
   - Card size: Medium or Large
   - Card preview: Show Title, Channel, YouTube URL
   - Useful for visual archive of completed videos

### Usage Tips

- **YouTube URLs:** Populated after successful upload (Epic 7)
- **Click URL:** Opens YouTube video in new tab for verification
- **Archive growth:** View will grow over time (100+ videos per channel)
- **Performance:** Notion handles 1000+ cards efficiently in gallery view

---

## View 5: High Priority (Optional)

**Purpose:** Surface urgent/time-sensitive content across all statuses

### Configuration Steps

1. **Create New View:**
   - Click "+ Add View" in your Notion database
   - Select **Board** view type
   - Name: "High Priority"

2. **Filter:**
   - Add filter: **Priority** → **is** → **High**

3. **Group By:**
   - Group by: **Status**
   - Rationale: See where high-priority tasks are in pipeline

4. **Sort Within Columns:**
   - Primary sort: **Created** (ascending - oldest first)

5. **Card Properties:**
   - Title
   - Channel
   - Time in Status
   - Created

### Usage Tips

- **Use case:** When managing multiple channels, surface urgent content
- **Normal priority:** Default for most videos
- **High priority:** Trending topics, time-sensitive content
- **Low priority:** Evergreen content, backfill videos

---

## View 6: In Progress (Monitoring)

**Purpose:** Identify bottlenecks and stuck tasks currently being processed

### Configuration Steps

1. **Create New View:**
   - Click "+ Add View" in your Notion database
   - Select **Table** view type
   - Name: "In Progress"

2. **Filter:**
   - Add filter: **Status** → **is one of:**
     - Claimed
     - Generating Assets
     - Assets Ready
     - Assets Approved
     - Generating Composites
     - Composites Ready
     - Generating Video
     - Video Ready
     - Video Approved
     - Generating Audio
     - Audio Ready
     - Audio Approved
     - Generating SFX
     - SFX Ready
     - Assembling
     - Assembly Ready
     - Final Review
     - Approved
   - Rationale: 18 statuses representing "in-flight" work

3. **Sort:**
   - Primary sort: **Time in Status** (descending - stuck longest first)
   - Alternative sort: **Updated** (ascending - oldest updates first)
   - Rationale: Surface tasks that may be stuck

4. **Display Columns:**
   - Title
   - Channel
   - Status
   - **Time in Status** (primary metric for bottleneck detection)
   - Created

### Usage Tips

- **Bottleneck detection:** Cards stuck >2x expected duration = investigate
- **Expected durations:**
  - Assets: 5-10 min
  - Video: 2-5 min per clip (36-90 min total)
  - Audio: 1-2 min per clip (18-36 min total)
- **Empty view after hours:** All tasks completed or in terminal states
- **Use with Kanban:** Cross-reference stuck cards between views

---

## Per-Channel Views (Optional)

**Purpose:** Isolate work by channel to prevent cross-channel mistakes

### Configuration Steps

1. **Create New View:**
   - Click "+ Add View" in your Notion database
   - Select **Board** or **Table** view type
   - Name: "{Channel Emoji} {Channel Name} - All Tasks"
   - Example: "🧠 Philosophy - All Tasks"

2. **Filter:**
   - Add filter: **Channel** → **is** → **{specific channel}**

3. **Group By (if Board view):**
   - Group by: **Status**

4. **Sort:**
   - Primary sort: **Created** (ascending - FIFO)
   - Secondary sort: **Status** (workflow order)

5. **Display Properties:**
   - Title
   - Status
   - Time in Status
   - Priority
   - Created

### Usage Tips

- **Multi-channel safety:** Isolate channels to avoid branding/credential mix-ups
- **Channel-specific monitoring:** Track single channel's production pipeline
- **Create one view per channel:** Philosophy, Science, Art, History, etc.
- **Naming convention:** Use channel emoji for quick visual identification

---

## Time in Status Formula

**Purpose:** Calculate duration task has been in current status (health metric)

### Notion Formula Syntax

```javascript
formatDate(now() - prop("Updated"), "m 'min'")
```

### Formula Explanation

- `now()`: Current timestamp (auto-updates)
- `prop("Updated")`: Last status change timestamp (synced from PostgreSQL)
- `now() - prop("Updated")`: Duration in current status
- `formatDate(..., "m 'min'")`: Format as "5 min", "120 min", etc.

### Setup Steps

1. **Create Calculated Property:**
   - In database, click "+ Add Property"
   - Select **Formula** property type
   - Name: "Time in Status"

2. **Enter Formula:**
   - Paste formula: `formatDate(now() - prop("Updated"), "m 'min'")`
   - Click "Done"

3. **Verify Calculation:**
   - Check a few tasks to ensure formula displays minutes correctly
   - Format: "5 min", "120 min", "1440 min" (24 hours)

### Alternative Formats

**Hours instead of minutes:**
```javascript
formatDate(now() - prop("Updated"), "h 'hrs'")
```

**Days for long-running tasks:**
```javascript
formatDate(now() - prop("Updated"), "d 'days'")
```

**Hours and minutes combined:**
```javascript
formatDate(now() - prop("Updated"), "h 'hrs' m 'min'")
```

### Usage Tips

- **Health metric:** Primary indicator of pipeline health
- **Normal range:** Most steps complete within expected duration (see Kanban section)
- **Abnormal duration:** >2x expected = investigate (worker down, API timeout, etc.)
- **Review gates:** Time in Status shows how long awaiting approval
- **Auto-updates:** Formula recalculates automatically every minute in Notion

---

## Troubleshooting

### Issue: Views not updating after status change

**Cause:** Notion API sync latency (~10 seconds)

**Solution:** Wait 10-15 seconds and refresh browser. Real-time updates implemented in Story 5.6.

---

### Issue: "Time in Status" showing wrong duration

**Cause:** Formula references wrong property (using "Created" instead of "Updated")

**Solution:**
1. Edit "Time in Status" formula property
2. Verify formula uses `prop("Updated")` NOT `prop("Created")`
3. Correct formula: `formatDate(now() - prop("Updated"), "m 'min'")`

---

### Issue: Kanban board too wide (27 columns)

**Cause:** 27 statuses = wide board requiring horizontal scroll

**Solution:** This is expected. Use horizontal scroll or create filtered views for specific pipeline phases:
- "Early Pipeline" view: Filter statuses 1-10 (Draft → Video Ready)
- "Late Pipeline" view: Filter statuses 11-23 (Generating Audio → Published)

---

### Issue: "Needs Review" view empty but tasks stuck

**Cause:** Tasks stuck in non-review gate statuses (e.g., "Generating Video" for hours)

**Solution:**
1. Check "In Progress" view (sorted by Time in Status descending)
2. Identify stuck tasks
3. Check Error Log for API failures
4. Retry task via review interface (Epic 5 stories 5.3-5.5)

---

### Issue: Filter not working (wrong statuses showing)

**Cause:** Status select property values don't match exact names (case-sensitive)

**Solution:**
1. Verify Status property has EXACT 27 values (see Database Properties Overview)
2. Check filter uses exact status names: "Assets Ready" NOT "assets ready" or "Assets_Ready"
3. Re-create filter with correct capitalization

---

### Issue: YouTube URL not appearing in Published view

**Cause:** Epic 7 (YouTube Publishing) not yet implemented

**Solution:** YouTube URL population will be implemented in Epic 7. For now, Published view tracks completion without URLs.

---

### Issue: Multiple cards for same video

**Cause:** Duplicate task creation (Epic 2 Story 2.6 handles deduplication)

**Solution:**
1. Check Notion page ID for duplicate tasks
2. If duplicates exist, delete manually in Notion
3. Verify duplicate detection working (contact system admin if recurring)

---

## Next Steps

After configuring all views:

1. **Test workflow:** Create test task, move through statuses, verify views update
2. **Bookmark views:** Pin frequently used views (Needs Review, All Errors, Kanban)
3. **Share with team:** Grant access to collaborators using Notion share settings
4. **Monitor daily:** Check "Needs Review" for approval tasks, "All Errors" for issues
5. **Iterate:** Customize views based on team workflow preferences

---

## Additional Resources

- **Architecture Document:** `_bmad-output/planning-artifacts/architecture.md` - 27-status state machine details
- **PRD:** `_bmad-output/planning-artifacts/prd.md` - FR51 (workflow), FR54 (dashboard requirements)
- **UX Design Spec:** `_bmad-output/planning-artifacts/ux-design-specification.md` - Dashboard UX principles
- **Story 5.6:** Real-time status updates implementation (10-second Notion sync latency)

---

**Last Updated:** 2026-01-17
**Document Version:** 1.0
**Author:** AI Video Generator Platform
**Status:** Complete
