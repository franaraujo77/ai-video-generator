# Notion Integration Completion Checklist

Use this checklist to track your progress through the manual setup steps.

---

## ✅ Automated Steps (Complete)

- [x] Code fixes implemented in `app/clients/notion.py`
- [x] Database ID normalization added
- [x] Enhanced error logging implemented
- [x] Documentation created (5 guides)
- [x] Test scripts created
- [x] Notion database created ("Video Entries")
- [x] Test entry created in Notion
- [x] All changes committed to git

---

## ⏳ Manual Steps (Your Action Required)

### Step 1: Share Database with Integration ⚠️ CRITICAL

- [ ] Open: https://www.notion.so/6b870ef4134346168f14367291bc89e6
- [ ] Click the **"..."** button (three dots, top right corner)
- [ ] Click **"+ Add connections"**
- [ ] Select your integration (created at notion.so/my-integrations)
- [ ] Click **"Confirm"**

**Why:** This is the root cause of the 400 error. Without this, your integration cannot access the database.

---

### Step 2: Configure Environment Variables

Run these commands in your terminal:

```bash
# Check current values
railway env get NOTION_API_TOKEN
railway env get NOTION_DATABASE_IDS

# Set the values (replace with your actual token)
railway env set NOTION_API_TOKEN="secret_your_actual_token_here"
railway env set NOTION_DATABASE_IDS="6b870ef4134346168f14367291bc89e6"
```

**Checklist:**
- [ ] `NOTION_API_TOKEN` is set
- [ ] `NOTION_DATABASE_IDS` is set to `6b870ef4134346168f14367291bc89e6`

---

### Step 3: Restart Application

```bash
railway restart
```

**Checklist:**
- [ ] Application restarted successfully
- [ ] No startup errors in logs

---

### Step 4: Wait for Sync Loop

The sync loop polls every 60 seconds. After restarting, you need to wait for the first sync cycle.

**Checklist:**
- [ ] Waited at least 60 seconds
- [ ] Checked logs for sync activity

---

### Step 5: Verify Integration Works

Run the automated verification script:

```bash
./scripts/verify_notion_sync.sh
```

**Expected output:**
```
✅ SUCCESS: Test entry found in database!
   Notion sync is working correctly ✨
```

**Checklist:**
- [ ] Verification script ran successfully
- [ ] Test entry found in PostgreSQL
- [ ] Task has `notion_page_id = 2e8088e8-988b-81d4-93bd-eeb49e35233e`
- [ ] Task has `status = 'queued'`
- [ ] Task has `channel_id = 'poke1'`

---

## 🔍 Verification Commands

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

**Expected:** No results (or old errors before sharing database)

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

### Manual Database Query

```sql
SELECT id, title, status, channel_id, notion_page_id, created_at
FROM tasks
WHERE notion_page_id = '2e8088e8-988b-81d4-93bd-eeb49e35233e';
```

**Expected:** 1 row returned with status = 'queued'

---

## 🆘 Troubleshooting

If Step 5 verification fails:

1. **Wait the full 60 seconds** - The sync might not have run yet
2. **Check you completed Step 1** - Most common issue is forgetting to share database
3. **Run diagnostic:** `python scripts/test_notion_integration.py`
4. **Check specific error in logs:** `railway logs --filter "notion"`
5. **Review guides:** See `NOTION_TROUBLESHOOTING.md` for error-specific solutions

---

## 📚 Reference Information

### Database Details
- **Database ID:** `6b870ef4134346168f14367291bc89e6`
- **Database URL:** https://www.notion.so/6b870ef4134346168f14367291bc89e6
- **Parent Page:** "Dark channels"

### Test Entry Details
- **Page ID:** `2e8088e8-988b-81d4-93bd-eeb49e35233e`
- **Page URL:** https://www.notion.so/2e8088e8988b81d493bdeeb49e35233e
- **Title:** "Test Video - Pikachu Forest Adventure"
- **Status:** "Queued"

### Documentation Files
- **Quick Fix:** `QUICK_FIX.md` (5-minute guide)
- **Full Setup:** `NOTION_SETUP.md` (comprehensive)
- **Troubleshooting:** `NOTION_TROUBLESHOOTING.md` (error reference)
- **Verification:** `VERIFICATION_GUIDE.md` (verification methods)
- **Status:** `STATUS.md` (complete overview)

---

## 🎉 Success Indicators

You'll know everything is working when ALL of these are true:

- [x] All checklist items above are complete
- [ ] Logs show `notion_sync_loop_started database_count=1`
- [ ] No `notion_database_query_failed` errors in logs
- [ ] Verification script shows "✅ SUCCESS"
- [ ] PostgreSQL has task with `notion_page_id = 2e8088e8-988b-81d4-93bd-eeb49e35233e`
- [ ] Task has correct status, channel_id, and title

---

**Once all steps are complete, you can start creating real video entries in Notion and they'll automatically sync to your task queue!**

**Next:** Open `STATUS.md` for detailed instructions or `QUICK_FIX.md` for fast execution.
