# Notion Integration Verification Guide

## Test Entry Created

I've created a test entry in your Notion database to verify the integration is working:

**Test Entry Details:**
- **Title**: "Test Video - Pikachu Forest Adventure"
- **Topic**: "Pikachu exploring forest habitat in search of berries"
- **Channel**: "poke1"
- **Status**: "Queued" ✅ (changed from Draft to trigger sync)
- **Priority**: "Normal"
- **Notion Page ID**: `2e8088e8-988b-81d4-93bd-eeb49e35233e`
- **Notion URL**: https://www.notion.so/2e8088e8988b81d493bdeeb49e35233e

## What Should Happen

Within **60 seconds** (the sync interval), your application should:

1. ✅ Poll the Notion database
2. ✅ Detect the new entry with Status = "Queued"
3. ✅ Validate the entry (Title, Topic, Channel are present)
4. ✅ Create a new task in PostgreSQL with `status='queued'`
5. ✅ Log: `task_enqueued_from_notion`

## How to Verify (3 Methods)

### Method 1: Automated Verification Script (Recommended)

```bash
# Run the verification script
./scripts/verify_notion_sync.sh
```

**Expected Output:**
```
✅ Test entry found in database!
   Notion sync is working correctly ✨
```

**If fails:**
```
⚠️  Test entry NOT found in database
🔧 Troubleshooting: [detailed steps]
```

### Method 2: Manual Database Query

```bash
# Connect to your database
psql $DATABASE_URL

# Or for Railway
railway run psql $DATABASE_URL
```

```sql
-- Check for the test entry
SELECT
    id,
    title,
    status,
    channel_id,
    notion_page_id,
    created_at,
    updated_at
FROM tasks
WHERE notion_page_id = '2e8088e8-988b-81d4-93bd-eeb49e35233e';
```

**Expected Result:**
```
 id                                   | title                                  | status  | channel_id | notion_page_id                       | created_at
--------------------------------------+----------------------------------------+---------+------------+--------------------------------------+---------------------
 <uuid>                               | Test Video - Pikachu Forest Adventure  | queued  | poke1      | 2e8088e8-988b-81d4-93bd-eeb49e35233e | 2026-01-14 ...
```

**What each column means:**
- `id`: Auto-generated task UUID
- `title`: Should match "Test Video - Pikachu Forest Adventure"
- `status`: Should be "queued" (lowercase)
- `channel_id`: Should be "poke1"
- `notion_page_id`: Should be "2e8088e8-988b-81d4-93bd-eeb49e35233e"
- `created_at`: Timestamp when task was created

### Method 3: Check Application Logs

```bash
# For Railway
railway logs --filter "task_enqueued_from_notion" --tail 50

# For local
# Check your console output or log file
```

**Expected Log Entry:**
```json
{
  "event": "task_enqueued_from_notion",
  "notion_page_id": "2e8088e8-988b-81d4-93bd-eeb49e35233e",
  "task_id": "<some-uuid>",
  "title": "Test Video - Pikachu Forest Adventure",
  "channel_id": "poke1",
  "status": "queued",
  "timestamp": "2026-01-14T..."
}
```

## Troubleshooting If Test Fails

### 1. Check Sync Loop Started

```bash
railway logs --filter "notion_sync_loop_started"
```

**Expected:**
```
notion_sync_loop_started database_count=1 interval_seconds=60
```

**If you see:**
```
notion_sync_no_databases_configured
```

**Fix:**
```bash
railway env set NOTION_DATABASE_IDS="6b870ef4134346168f14367291bc89e6"
railway restart
```

### 2. Check for Query Errors

```bash
railway logs --filter "notion_database_query_failed"
```

**If you see 400 error:**
- ❌ Database NOT shared with your integration
- Fix: Go to Notion → Share database with integration

**If you see 401 error:**
- ❌ Invalid NOTION_API_TOKEN
- Fix: Get new token from https://www.notion.so/my-integrations

**If you see 403 error:**
- ❌ Missing capabilities
- Fix: Enable Read/Update/Insert in integration settings

### 3. Check for Validation Errors

```bash
railway logs --filter "notion_entry_validation_failed"
```

**Common validation errors:**
- Missing Title or Topic (required fields)
- Channel doesn't match any channel_id in configs
- Status property missing

### 4. Verify Environment Variables

```bash
# Check both variables are set
railway env get NOTION_API_TOKEN
railway env get NOTION_DATABASE_IDS

# Should return:
# NOTION_API_TOKEN: secret_...
# NOTION_DATABASE_IDS: 6b870ef4134346168f14367291bc89e6
```

### 5. Run Full Diagnostic

```bash
uv run python scripts/test_notion_integration.py
```

This will test:
- ✅ Environment variables
- ✅ API token validity
- ✅ Database access
- ✅ Schema validation

## Timing

⏱️ **Normal sync delay: 0-60 seconds**

The sync loop polls every 60 seconds. Depending on when you triggered the test:
- Best case: 5-10 seconds (if sync happens right away)
- Worst case: 60 seconds (if you just missed the last poll)

💡 **If more than 60 seconds pass with no task created, there's an issue.**

## Success Criteria Checklist

- [ ] Test entry visible in Notion with Status = "Queued"
- [ ] Application logs show `notion_sync_loop_started database_count=1`
- [ ] No `notion_database_query_failed` errors in logs
- [ ] Task found in PostgreSQL with notion_page_id = `2e8088e8-988b-81d4-93bd-eeb49e35233e`
- [ ] Task has `status='queued'`, `channel_id='poke1'`
- [ ] Log entry shows `task_enqueued_from_notion` with correct details

## Next Steps After Verification

### If Test PASSED ✅

Congratulations! Your Notion integration is working. You can now:

1. **Create real video entries:**
   - Open: https://www.notion.so/6b870ef4134346168f14367291bc89e6
   - Click "+ New"
   - Fill in Title, Topic, Channel
   - Set Status to "Queued"

2. **Monitor progress:**
   ```bash
   railway logs --filter "notion" --follow
   ```

3. **Check queue depth:**
   ```sql
   SELECT status, COUNT(*)
   FROM tasks
   GROUP BY status;
   ```

4. **Clean up test entry:**
   ```sql
   DELETE FROM tasks
   WHERE notion_page_id = '2e8088e8-988b-81d4-93bd-eeb49e35233e';
   ```

### If Test FAILED ❌

1. **Wait full 60 seconds** (sync might not have run yet)

2. **Run diagnostic:**
   ```bash
   uv run python scripts/test_notion_integration.py
   ```

3. **Check specific error:**
   - 400 → Database not shared (see QUICK_FIX.md)
   - 401 → Invalid token (get new token)
   - 403 → Missing capabilities (enable in integration settings)
   - No logs → Application not running or crashed

4. **Review troubleshooting guide:**
   - NOTION_TROUBLESHOOTING.md
   - Section matching your error code

5. **Get help:**
   - Collect logs: `railway logs > notion_debug.log`
   - Check database: Run SQL query above
   - Open issue with logs and query results

## Reference Links

- **Test Entry**: https://www.notion.so/2e8088e8988b81d493bdeeb49e35233e
- **Database**: https://www.notion.so/6b870ef4134346168f14367291bc89e6
- **Setup Guide**: NOTION_SETUP.md
- **Quick Fix**: QUICK_FIX.md
- **Troubleshooting**: NOTION_TROUBLESHOOTING.md

## Expected Notion → PostgreSQL Mapping

| Notion Property | PostgreSQL Column | Notes |
|----------------|-------------------|-------|
| Title | title | Required, text |
| Topic | topic | Required, text |
| Channel | channel_id | Required, must match YAML config |
| Status = "Queued" | status = "queued" | Lowercase in DB |
| Priority | priority | Lowercase (high/normal/low) |
| Story Direction | story_direction | Optional |
| notion_page_id | notion_page_id | Auto-populated, 36-char UUID with dashes |

---

**Created:** 2026-01-14
**Test Entry ID:** 2e8088e8-988b-81d4-93bd-eeb49e35233e
**Database ID:** 6b870ef4134346168f14367291bc89e6
