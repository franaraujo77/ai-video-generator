# Quick Fix for 400 Bad Request Error

## The Problem
```
notion_database_query_failed
error='Non-retriable error: 400 - Status: 400'
database_id=6b870ef4134346168f14367291bc89e6
```

## The Solution (5 minutes)

### Step 1: Share Database with Integration ⚠️ CRITICAL

**This is the #1 cause of 400 errors.**

1. Open this link: https://www.notion.so/6b870ef4134346168f14367291bc89e6
2. Click the **"..."** button (three dots, top right corner)
3. Click **"+ Add connections"**
4. Select your integration from the list (e.g., "AI Video Generator")
5. Click **"Confirm"**

**Without this step, your integration cannot access the database, no matter what.**

### Step 2: Set Environment Variables

```bash
# Check if variables are set
railway env get NOTION_API_TOKEN
railway env get NOTION_DATABASE_IDS

# If not set or incorrect, update them
railway env set NOTION_API_TOKEN="secret_your_actual_token_here"
railway env set NOTION_DATABASE_IDS="6b870ef4134346168f14367291bc89e6"
```

### Step 3: Test the Integration

Run the test script to verify everything works:

```bash
# Make sure environment variables are loaded
export NOTION_API_TOKEN="secret_your_token_here"
export NOTION_DATABASE_IDS="6b870ef4134346168f14367291bc89e6"

# Run the test
uv run python scripts/test_notion_integration.py
```

**Expected output if working:**
```
✅ NOTION_API_TOKEN is set
✅ NOTION_DATABASE_IDS is set (1 database(s))
✅ NotionClient initialized successfully
✅ Successfully queried database (X page(s) found)
✅ All tests passed!
```

**If you still see 400 error:**
- Database is NOT shared with your integration (repeat Step 1)
- Wrong database ID (verify the ID in Notion URL)

### Step 4: Restart Application

```bash
# If using Railway
railway up

# If running locally
# Kill the process (Ctrl+C) and restart
uvicorn app.main:app --reload
```

### Step 5: Verify in Logs

Check logs for successful startup:

```bash
railway logs --filter "notion_sync_loop_started"
```

**Expected log:**
```
notion_sync_loop_started database_count=1 interval_seconds=60
```

**NOT this:**
```
notion_sync_no_databases_configured
```

**NOT this:**
```
notion_database_query_failed error='400'
```

### Step 6: Create Test Entry

1. Go to database: https://www.notion.so/6b870ef4134346168f14367291bc89e6
2. Click "+ New" to create a page
3. Fill in:
   - **Title**: "Test Video - Pikachu"
   - **Topic**: "Pikachu in forest"
   - **Channel**: "poke1"
   - **Status**: "Draft"
   - **Priority**: "Normal"
4. Change **Status** from "Draft" to "Queued"
5. Wait 60 seconds
6. Check logs:
   ```bash
   railway logs --filter "task_enqueued_from_notion"
   ```

**Expected log:**
```
task_enqueued_from_notion
notion_page_id=xxx
task_id=xxx
title="Test Video - Pikachu"
```

### Step 7: Verify in Database

```sql
-- Check if task was created
SELECT id, title, status, channel_id, notion_page_id
FROM tasks
WHERE title LIKE '%Test%';
```

**Expected result:** One row with `status='queued'`

## Still Not Working?

### Run full diagnostic:
```bash
uv run python scripts/test_notion_integration.py
```

This will tell you EXACTLY what's wrong and how to fix it.

### Common Issues:

**Issue 1: Database not shared**
- Error: `400 Bad Request`
- Fix: Repeat Step 1 above - SHARE THE DATABASE

**Issue 2: Wrong token**
- Error: `401 Unauthorized`
- Fix: Get new token from https://www.notion.so/my-integrations

**Issue 3: Missing capabilities**
- Error: `403 Forbidden`
- Fix: Go to https://www.notion.so/my-integrations → Enable Read/Update/Insert

**Issue 4: Wrong database ID**
- Error: `Invalid database ID length`
- Fix: Get ID from Notion URL (32 hex characters between `/` and `?v=`)

## Success Indicators

✅ Test script shows all green checkmarks
✅ Logs show `notion_sync_loop_started database_count=1`
✅ No `notion_database_query_failed` errors
✅ Test entry creates task in PostgreSQL within 60 seconds
✅ Task has correct `title`, `status='queued'`, `notion_page_id`

## Resources

- **Full Setup Guide:** `NOTION_SETUP.md`
- **Detailed Troubleshooting:** `NOTION_TROUBLESHOOTING.md`
- **Environment Config:** `.env.example`
