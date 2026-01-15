# Notion Integration Troubleshooting

## Error: 400 Bad Request when querying database

```
notion_database_query_failed
correlation_id=291407cf-ae3a-494b-b0e1-62aa492b2b81
database_id=6b870ef4134346168f14367291bc89e6
error='Non-retriable error: 400 - Status: 400'
status_code=400
```

### Root Cause

This error occurs when the Notion database hasn't been shared with your integration. Even though the database exists and the ID is correct, your integration cannot access it without explicit permission.

### Solution

**Share the database with your integration:**

1. Open the database in Notion: https://www.notion.so/6b870ef4134346168f14367291bc89e6
2. Click the **"..."** (three dots) menu in the top right
3. Click **"+ Add connections"**
4. Select your integration (e.g., "AI Video Generator")
5. Click **"Confirm"**

**Without this step, you'll continue getting 400 errors.**

### Verification

After sharing the database:

1. Restart the application
2. Check logs for successful startup:
   ```
   notion_sync_loop_started database_count=1 interval_seconds=60
   ```
3. No more `notion_database_query_failed` errors

## Error: NOTION_DATABASE_IDS not set

```
notion_sync_no_databases_configured
message='NOTION_DATABASE_IDS not set - sync loop will run but skip Notion → DB sync'
```

### Root Cause

The `NOTION_DATABASE_IDS` environment variable is empty or not configured.

### Solution

```bash
# For Railway
railway env set NOTION_DATABASE_IDS="6b870ef4134346168f14367291bc89e6"

# For local development (.env file)
NOTION_DATABASE_IDS=6b870ef4134346168f14367291bc89e6

# For multiple databases (comma-separated)
NOTION_DATABASE_IDS=6b870ef4134346168f14367291bc89e6,abc123def456789
```

## Error: 401 Unauthorized

```
notion_database_query_failed
error='Non-retriable error: 401 - Unauthorized'
status_code=401
```

### Root Cause

The `NOTION_API_TOKEN` is invalid, expired, or not set.

### Solution

1. Go to https://www.notion.so/my-integrations
2. Find your integration (e.g., "AI Video Generator")
3. Copy the **Internal Integration Token** (starts with `secret_...`)
4. Update environment variable:
   ```bash
   railway env set NOTION_API_TOKEN="secret_your_actual_token_here"
   ```

## Error: 403 Forbidden

```
notion_database_query_failed
error='Non-retriable error: 403 - Forbidden'
status_code=403
```

### Root Cause

Your integration doesn't have the required capabilities (Read content, Update content, Insert content).

### Solution

1. Go to https://www.notion.so/my-integrations
2. Click on your integration
3. Ensure these capabilities are enabled:
   - ✅ Read content
   - ✅ Update content
   - ✅ Insert content
4. Save changes
5. Restart the application

## Database ID Format Issues

### Invalid Database ID Length Error

```
ValueError: Invalid database ID length: 28 chars (expected 32)
```

**Cause:** The database ID format is incorrect.

**Solution:** Notion database IDs should be:
- **32 characters without dashes**: `6b870ef4134346168f14367291bc89e6`
- **36 characters with dashes**: `6b870ef4-1343-4616-8f14-367291bc89e6`

The code now automatically normalizes both formats.

**How to get database ID:**
1. Open database in Notion
2. Look at URL: `https://www.notion.so/workspace/{DATABASE_ID}?v=view_id`
3. Copy the 32-character hex string (the part between `/workspace/` and `?v=`)

## Testing the Integration

### Manual Test

1. Create a test entry in Notion:
   - **Title**: "Test - Pikachu Forest"
   - **Topic**: "Pikachu exploring forest"
   - **Channel**: "poke1"
   - **Status**: "Draft"
   - **Priority**: "Normal"

2. Change **Status** from "Draft" to "Queued"

3. Wait 60 seconds (polling interval)

4. Check PostgreSQL database:
   ```sql
   SELECT id, title, status, channel_id, notion_page_id
   FROM tasks
   WHERE title LIKE '%Test%';
   ```

5. Expected result: New task with `status='queued'`

### Check Logs

**Successful sync:**
```
task_enqueued_from_notion
notion_page_id=9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8
task_id=123e4567-e89b-12d3-a456-426614174000
title="Test - Pikachu Forest"
```

**Failed sync:**
```
notion_database_query_failed
correlation_id=xxx
database_id=6b870ef4134346168f14367291bc89e6
error='...'
status_code=400/401/403
```

## Common Issues & Fixes

### Issue: Database created but integration can't see it

**Fix:** Share the database with your integration (see top of this document)

### Issue: Environment variables not loading

**Fix:**
```bash
# Verify variables are set
railway env get NOTION_API_TOKEN
railway env get NOTION_DATABASE_IDS

# If empty, set them
railway env set NOTION_API_TOKEN="secret_..."
railway env set NOTION_DATABASE_IDS="6b870ef4134346168f14367291bc89e6"

# Restart the app
railway up
```

### Issue: Tasks not appearing after 60 seconds

**Possible causes:**
1. Status must be exactly "Queued" (case-sensitive)
2. Title and Topic are required fields
3. Channel must match a `channel_id` in `channel_configs/`
4. Check logs for validation errors:
   ```
   notion_entry_validation_failed
   notion_page_id=xxx
   error='Missing required field: Title'
   ```

### Issue: Multiple databases not syncing

**Fix:** Ensure all database IDs are comma-separated with no spaces:
```bash
# Correct
NOTION_DATABASE_IDS=6b870ef4134346168f14367291bc89e6,abc123def456789,xyz789abc012345

# Incorrect (has spaces)
NOTION_DATABASE_IDS=6b870ef4134346168f14367291bc89e6, abc123def456789
```

## Debug Checklist

When troubleshooting Notion integration issues:

- [ ] `NOTION_API_TOKEN` is set and starts with `secret_`
- [ ] `NOTION_DATABASE_IDS` is set with correct database ID(s)
- [ ] Database is shared with your integration (in Notion UI)
- [ ] Integration has Read/Update/Insert capabilities
- [ ] Database schema matches required properties (Title, Topic, Channel, Status, Priority)
- [ ] Channel select options match `channel_id` values in YAML configs
- [ ] Status select has "Queued" option (case-sensitive)
- [ ] Application has been restarted after environment variable changes
- [ ] Logs show `notion_sync_loop_started` with `database_count > 0`

## Getting Help

If the issue persists after checking all the above:

1. Collect logs with:
   ```bash
   railway logs --filter "notion" > notion_logs.txt
   ```

2. Check for error patterns:
   - `notion_database_query_failed` - API access issue
   - `notion_entry_validation_failed` - Data validation issue
   - `notion_sync_no_databases_configured` - Configuration issue

3. Open a GitHub issue with:
   - Full error log (with sensitive data redacted)
   - Database schema screenshot
   - Environment variable configuration (tokens redacted)
   - Steps to reproduce

## Additional Resources

- [Notion API Documentation](https://developers.notion.com/reference)
- [Notion Setup Guide](./NOTION_SETUP.md)
- [Architecture Documentation](./_bmad-output/planning-artifacts/architecture.md)
