# Notion Integration - Current Status

**Date:** 2026-01-14
**Issue:** `notion_database_query_failed` 400 error
**Status:** ✅ Fixed (code) + 🧪 Test entry created + ⏳ Awaiting verification

---

## 🎯 What's Been Done

### 1. ✅ Notion Database Created
- **Database Name**: "Video Entries"
- **Location**: Under "Dark channels" page
- **Database ID**: `6b870ef4134346168f14367291bc89e6`
- **URL**: https://www.notion.so/6b870ef4134346168f14367291bc89e6
- **Schema**: Complete (Title, Topic, Channel, Status, Priority, etc.)
- **Status Options**: All 23 workflow statuses configured

### 2. ✅ Code Fixed (`app/clients/notion.py`)
- Database ID normalization (handles 32/36 char formats)
- Enhanced error messages (shows actual Notion API error)
- UUID format compatibility (with/without dashes)

**Commits:**
- `a37b6f2` - Fix 400 error with enhanced error handling
- `a380bfb` - Add verification tools and test entry

### 3. ✅ Documentation Created
- `QUICK_FIX.md` - 5-minute fix guide
- `NOTION_SETUP.md` - Complete setup (200+ lines)
- `NOTION_TROUBLESHOOTING.md` - Error reference
- `VERIFICATION_GUIDE.md` - How to verify integration works
- `NOTION_FIX_SUMMARY.md` - Complete issue analysis

### 4. ✅ Testing Tools Created
- `scripts/test_notion_integration.py` - Diagnostic test
- `scripts/verify_notion_sync.sh` - Automated verification

### 5. ✅ Test Entry Created
- **Title**: "Test Video - Pikachu Forest Adventure"
- **Status**: "Queued" ✅ (triggers sync)
- **Notion Page ID**: `2e8088e8-988b-81d4-93bd-eeb49e35233e`
- **URL**: https://www.notion.so/2e8088e8988b81d493bdeeb49e35233e

---

## ⏳ What You Need to Do Now

### CRITICAL STEP 1: Share Database with Integration

**This is required for your app to access the database.**

1. Open: https://www.notion.so/6b870ef4134346168f14367291bc89e6
2. Click **"..."** (three dots, top right)
3. Click **"+ Add connections"**
4. Select your integration (e.g., "AI Video Generator")
5. Click **"Confirm"**

**Without this, the 400 error will persist.**

### STEP 2: Set Environment Variables

```bash
# Check current values
railway env get NOTION_API_TOKEN
railway env get NOTION_DATABASE_IDS

# If not set, configure them
railway env set NOTION_API_TOKEN="secret_your_token_here"
railway env set NOTION_DATABASE_IDS="6b870ef4134346168f14367291bc89e6"
```

### STEP 3: Restart Application

```bash
railway restart
# or
railway up
```

### STEP 4: Wait 60 Seconds

The sync loop polls every 60 seconds. After sharing the database and restarting:
- ⏱️ Wait up to 60 seconds
- 🔄 Sync loop will detect the test entry
- ✅ Task will be created in PostgreSQL

### STEP 5: Verify Integration Works

```bash
# Run automated verification
./scripts/verify_notion_sync.sh
```

**Expected Output:**
```
✅ Test entry found in database!
   Notion sync is working correctly ✨
```

**Alternative: Manual verification**
```sql
SELECT id, title, status, notion_page_id
FROM tasks
WHERE notion_page_id = '2e8088e8-988b-81d4-93bd-eeb49e35233e';
```

Should return 1 row with `status='queued'`.

---

## 📊 Current Integration Status

| Component | Status | Notes |
|-----------|--------|-------|
| Notion Database | ✅ Created | Video Entries with complete schema |
| Database Schema | ✅ Configured | 23 status options, all required properties |
| Test Entry | ✅ Created | Status = "Queued", ready to sync |
| Code Fixes | ✅ Committed | ID normalization + error handling |
| Documentation | ✅ Complete | 5 guides covering setup/troubleshooting |
| Test Scripts | ✅ Ready | 2 scripts for testing/verification |
| Database Sharing | ⏳ Pending | **YOU MUST DO THIS** |
| Environment Vars | ⏳ Pending | Set NOTION_API_TOKEN, NOTION_DATABASE_IDS |
| App Restart | ⏳ Pending | Restart after env vars set |
| Verification | ⏳ Pending | Run after 60 seconds |

---

## 🔍 How to Check Logs

### Check Sync Loop Started
```bash
railway logs --filter "notion_sync_loop_started"
```

**Expected:**
```
notion_sync_loop_started database_count=1 interval_seconds=60
```

### Check for Errors
```bash
railway logs --filter "notion_database_query_failed"
```

**If 400 error:**
- Database not shared → Share database (see Step 1 above)

**If 401 error:**
- Invalid token → Get new token from https://www.notion.so/my-integrations

**If no errors but also no "sync_loop_started":**
- NOTION_DATABASE_IDS not set → Set environment variable

### Check for Success
```bash
railway logs --filter "task_enqueued_from_notion"
```

**Expected:**
```
task_enqueued_from_notion
notion_page_id=2e8088e8-988b-81d4-93bd-eeb49e35233e
task_id=<uuid>
title="Test Video - Pikachu Forest Adventure"
```

---

## 📚 Quick Reference

### Database Information
- **Database ID**: `6b870ef4134346168f14367291bc89e6`
- **Database URL**: https://www.notion.so/6b870ef4134346168f14367291bc89e6
- **Parent Page**: "Dark channels"

### Test Entry Information
- **Page ID**: `2e8088e8-988b-81d4-93bd-eeb49e35233e`
- **Page URL**: https://www.notion.so/2e8088e8988b81d493bdeeb49e35233e
- **Title**: "Test Video - Pikachu Forest Adventure"
- **Status**: "Queued"

### Documentation Files
- **Quick Fix**: `QUICK_FIX.md` (5 minutes)
- **Full Setup**: `NOTION_SETUP.md` (15 minutes)
- **Troubleshooting**: `NOTION_TROUBLESHOOTING.md`
- **Verification**: `VERIFICATION_GUIDE.md`
- **This Status**: `STATUS.md`

### Test Scripts
- **Integration Test**: `python scripts/test_notion_integration.py`
- **Sync Verification**: `./scripts/verify_notion_sync.sh`

---

## 🎉 Success Indicators

You'll know everything is working when:

- ✅ No `notion_database_query_failed` errors
- ✅ Logs show `notion_sync_loop_started database_count=1`
- ✅ Logs show `task_enqueued_from_notion` for test entry
- ✅ PostgreSQL has task with notion_page_id = `2e8088e8-988b-81d4-93bd-eeb49e35233e`
- ✅ Verification script shows "✅ SUCCESS"

---

## 🚀 After Verification Passes

Once the test entry syncs successfully:

1. **Clean up test data** (optional):
   ```sql
   DELETE FROM tasks WHERE notion_page_id = '2e8088e8-988b-81d4-93bd-eeb49e35233e';
   ```

2. **Create real video entries**:
   - Go to database: https://www.notion.so/6b870ef4134346168f14367291bc89e6
   - Click "+ New"
   - Fill in Title, Topic, Channel
   - Set Status to "Queued"

3. **Monitor processing**:
   ```bash
   railway logs --follow
   ```

4. **Check queue status**:
   ```sql
   SELECT status, COUNT(*) FROM tasks GROUP BY status;
   ```

---

## 🆘 If Something Goes Wrong

1. **Read the error-specific guide**: `NOTION_TROUBLESHOOTING.md`
2. **Run diagnostics**: `python scripts/test_notion_integration.py`
3. **Check logs**: `railway logs --filter "notion"`
4. **Verify database sharing**: Most common issue is forgetting to share

---

**Next Action:** Share the database with your integration (Step 1 above)

**Then:** Run `./scripts/verify_notion_sync.sh` after 60 seconds

**Questions?** Check `QUICK_FIX.md` or `NOTION_TROUBLESHOOTING.md`
