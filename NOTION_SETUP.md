# Notion Integration Setup Guide

This guide walks you through setting up Notion integration for the AI Video Generator orchestration platform.

## Overview

The Notion integration allows you to:
- Create video entries in Notion databases
- Batch-queue videos by changing their status to "Queued"
- Monitor video generation progress through a Kanban board interface
- Review and approve assets/videos/audio at gate checkpoints
- Track errors and retry failed generations

## Prerequisites

- A Notion workspace with edit access
- The ability to create Internal Integrations in your workspace

## Step 1: Create Notion Internal Integration

1. Go to https://www.notion.so/my-integrations
2. Click **"+ New integration"**
3. Fill in the integration details:
   - **Name**: "AI Video Generator" (or any name you prefer)
   - **Associated workspace**: Select your workspace
   - **Capabilities**: Ensure these are enabled:
     - ✅ Read content
     - ✅ Update content
     - ✅ Insert content
4. Click **"Submit"**
5. Copy the **Internal Integration Token** (starts with `secret_...`)
6. Save this token securely - you'll need it for the `NOTION_API_TOKEN` environment variable

## Step 2: Create Video Entries Database (Option A: Use Existing)

If you already have a "Video Entries" database created under "Dark channels", skip to Step 3.

**Database URL**: https://www.notion.so/6b870ef4134346168f14367291bc89e6

This database has been pre-configured with:
- ✅ Title (title property)
- ✅ Topic (rich text)
- ✅ Channel (select: poke1, poke2, poke3)
- ✅ Status (select: 23 workflow statuses)
- ✅ Priority (select: High, Normal, Low)
- ✅ Story Direction (rich text)
- ✅ Error Log (rich text)
- ✅ YouTube URL (url)

## Step 2: Create Video Entries Database (Option B: Manual Setup)

If you need to create a new database:

1. In your Notion workspace, create a new database (full page or inline)
2. Add the following properties:

### Required Properties

| Property Name | Type | Description |
|--------------|------|-------------|
| **Title** | Title | Video title (required for validation) |
| **Topic** | Rich Text | Video subject/topic (required for validation) |
| **Channel** | Select | Which channel (must match `channel_id` from YAML config) |
| **Status** | Select | Current workflow status (see status options below) |
| **Priority** | Select | Task priority: High, Normal, Low |

### Optional Properties

| Property Name | Type | Description |
|--------------|------|-------------|
| Story Direction | Rich Text | Narrative guidance for AI generation |
| Error Log | Rich Text | System error messages (auto-populated) |
| YouTube URL | URL | Published video URL (auto-populated) |

### Status Select Options (23 total)

Add these as options to your **Status** select property:

**Workflow Progression:**
- Draft (gray) - Initial state, not yet queued
- Queued (yellow) - Ready for processing
- Generating Assets (blue) - Creating images via Gemini
- Assets Ready (blue) - Awaiting review
- Assets Approved (green) - Approved, proceeding
- Generating Video (blue) - Creating videos via Kling
- Video Ready (blue) - Awaiting review
- Video Approved (green) - Approved, proceeding
- Generating Audio (blue) - Creating narration/SFX
- Audio Ready (blue) - Awaiting review
- Audio Approved (green) - Approved, proceeding
- Assembling Final (blue) - FFmpeg assembly
- Final Ready (blue) - Awaiting review
- Final Approved (green) - Approved, proceeding
- Uploading to YouTube (blue) - Uploading to channel
- Published (green) - Live on YouTube

**Error States:**
- Asset Error (red) - Image generation failed
- Video Error (red) - Video generation failed
- Audio Error (red) - Audio generation failed
- Assembly Error (red) - FFmpeg assembly failed
- Upload Error (red) - YouTube upload failed

**Recovery States:**
- Retry Scheduled (orange) - Auto-retry in progress
- User Cancelled (gray) - Manually cancelled

### Channel Select Options

Add channel IDs that match your `channel_configs/*.yaml` files. Example:
- poke1 (blue)
- poke2 (green)
- poke3 (purple)

You can customize colors and add more channels as needed.

## Step 3: Share Database with Integration

**Critical Step:** Notion integrations can only access databases explicitly shared with them.

1. Open your Video Entries database in Notion
2. Click the **"..."** menu (top right)
3. Click **"+ Add connections"**
4. Select your integration (e.g., "AI Video Generator")
5. Confirm the connection

**Without this step, the sync service will fail with "object not found" errors.**

## Step 4: Get Database ID

1. Open your Video Entries database in Notion
2. Look at the URL in your browser:
   ```
   https://www.notion.so/workspace/6b870ef4134346168f14367291bc89e6?v=viewid
                                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                   This is your database ID (32 chars)
   ```
3. Copy the database ID (32-character hexadecimal string)

## Step 5: Configure Environment Variables

### For Local Development (.env file)

```bash
# Notion API token from Step 1
NOTION_API_TOKEN=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Database ID from Step 4
NOTION_DATABASE_IDS=6b870ef4134346168f14367291bc89e6

# Optional: Adjust sync interval (default: 60 seconds)
NOTION_SYNC_INTERVAL_SECONDS=60
```

### For Railway Deployment

```bash
# Set environment variables in Railway dashboard or via CLI
railway env set NOTION_API_TOKEN="secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
railway env set NOTION_DATABASE_IDS="6b870ef4134346168f14367291bc89e6"
railway env set NOTION_SYNC_INTERVAL_SECONDS=60
```

## Step 6: Configure Channel YAML

Update your channel configuration to reference the Notion database:

```yaml
# channel_configs/poke1.yaml
channel_id: poke1
channel_name: "Pokemon Nature Documentaries"
notion_database_id: "6b870ef4134346168f14367291bc89e6"  # From Step 4
is_active: true
priority: normal
voice_id: "your_elevenlabs_voice_id"
storage_strategy: notion
max_concurrent: 2
```

**Important:** The `notion_database_id` in the YAML must match one of the IDs in `NOTION_DATABASE_IDS`.

## Step 7: Verify Setup

### Start the Application

```bash
# Local development
uvicorn app.main:app --reload

# Check logs for successful startup
# Expected log: notion_sync_loop_started database_count=1
```

### Test Video Creation

1. In Notion, create a new page in your Video Entries database
2. Fill in required fields:
   - **Title**: "Test Video - Pikachu in Forest"
   - **Topic**: "Pikachu exploring forest habitat"
   - **Channel**: "poke1"
   - **Status**: "Draft"
   - **Priority**: "Normal"
3. Change **Status** from "Draft" to "Queued"
4. Within 60 seconds, check your PostgreSQL database:
   ```sql
   SELECT id, title, status, channel_id FROM tasks;
   ```
5. You should see a new task with `status='queued'`

### Check Logs

Monitor Railway logs for:

✅ **Successful startup:**
```
notion_sync_loop_started database_count=1 interval_seconds=60
```

✅ **Successful sync:**
```
task_enqueued_from_notion notion_page_id=xxx task_id=xxx title="Test Video - Pikachu in Forest"
```

❌ **Common errors:**
```
# Missing database ID
notion_sync_no_databases_configured message='NOTION_DATABASE_IDS not set'

# Database not shared with integration
NotionAPIError: object not found (ensure database is shared with integration)

# Missing required fields
notion_entry_validation_failed notion_page_id=xxx error='Missing required field: Title'
```

## Multi-Database Setup

For multiple channels with separate databases:

```bash
# Create multiple databases in Notion (repeat Step 2 for each channel)
# Then configure environment variable with comma-separated IDs:

NOTION_DATABASE_IDS=6b870ef4134346168f14367291bc89e6,abc123def456789,xyz789abc012345
```

Each database should have the same schema (Title, Topic, Channel, Status, Priority, etc.).

## Troubleshooting

### "object not found" Error

**Cause:** Database not shared with integration

**Solution:**
1. Open database in Notion
2. Click "..." → "+ Add connections"
3. Select your integration
4. Restart the application

### "NOTION_DATABASE_IDS not set" Warning

**Cause:** Environment variable is empty or not set

**Solution:**
```bash
# Check current value
echo $NOTION_DATABASE_IDS

# Set the variable
export NOTION_DATABASE_IDS=6b870ef4134346168f14367291bc89e6

# For Railway
railway env set NOTION_DATABASE_IDS="6b870ef4134346168f14367291bc89e6"
```

### Tasks Not Appearing in Database

**Possible causes:**
1. **Status not set to "Queued"** - Only "Queued" status triggers task creation
2. **Missing required fields** - Title and Topic are required
3. **Channel mismatch** - Channel select value must match a `channel_id` in `channel_configs/`
4. **Sync interval** - Wait up to 60 seconds for polling to detect changes

**Debug steps:**
```bash
# Check Railway logs for validation errors
railway logs --filter "notion_entry_validation_failed"

# Check sync loop is running
railway logs --filter "notion_sync_loop_started"

# Verify database count
railway logs --filter "database_count"
```

### Rate Limit Errors

**Cause:** Exceeding Notion's 3 requests/second limit

**Solution:** The NotionClient has built-in rate limiting (AsyncLimiter). If you see rate limit errors:
1. Check for duplicate sync loops running
2. Reduce `NOTION_SYNC_INTERVAL_SECONDS` to avoid bursts
3. Verify only one instance of the app is running

## Best Practices

1. **Start with Draft Status** - Create entries as "Draft" first, batch-select later to queue
2. **Use Kanban Board View** - Create a Board view grouped by Status for visual monitoring
3. **Set Up Filters** - Create database views for "In Progress", "Needs Review", "Errors"
4. **Batch Operations** - Select 10-20 videos and change Status to "Queued" simultaneously
5. **Monitor Time in Status** - Add a "Last Edited" property to track stuck videos

## Additional Resources

- [Notion API Documentation](https://developers.notion.com/reference)
- [Epic 2 Implementation Story](https://github.com/your-repo/ai-video-generator/blob/main/_bmad-output/planning-artifacts/epics.md#epic-2-notion-integration--video-planning)
- [Architecture Documentation](https://github.com/your-repo/ai-video-generator/blob/main/_bmad-output/planning-artifacts/architecture.md)

## Support

If you encounter issues not covered here:
1. Check Railway logs for structured error messages
2. Review `app/services/notion_sync.py` for validation logic
3. Open a GitHub issue with logs and database schema details
