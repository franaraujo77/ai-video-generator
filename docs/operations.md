# Operations Manual

This document provides operational procedures for managing the AI Video Generator orchestration platform in production.

## Quota Management

### Automated Daily Quota Resets (Story 7.0)

The system automatically resets YouTube and Gemini API quotas at midnight Pacific Time (America/Los_Angeles timezone).

**Scheduler Configuration:**
- **Timezone:** America/Los_Angeles (handles PDT/PST automatically)
- **Schedule:** Daily at 00:00 (midnight)
- **Misfire Grace Time:** 60 seconds (skips reset if worker down >60s past midnight)
- **Jobs:** `reset_youtube_quotas`, `reset_gemini_quotas`

**What Happens During Reset:**
1. Query all active channels (`WHERE is_active = true`)
2. Create new quota row for today's date (YouTube: units_used=0, Gemini: requests_used=0)
3. Clear `youtube_quota_exhausted` and `gemini_quota_exhausted` flags
4. Log reset completion with channel count

**If Reset Fails:**
- CRITICAL Discord alert sent with error details
- Manual fallback SQL commands included in alert
- See Manual Quota Reset section below

### Manual Quota Reset (Emergency)

If automatic reset fails or quota needs immediate reset, use the admin API endpoint.

**API Endpoint:**
```
POST /api/v1/admin/quota-reset
```

**Authentication:**
Set `ADMIN_API_KEY` environment variable in Railway **before** using the admin endpoint.

**CRITICAL:** The admin endpoint will return HTTP 500 if `ADMIN_API_KEY` is not configured. This is intentional - the endpoint requires authentication to be set up.

**Setup Instructions:**
1. Generate a secure random key: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. In Railway dashboard → Variables → Add `ADMIN_API_KEY=<generated-key>`
3. Restart worker service to apply changes
4. Include key in request header: `X-Admin-Key: <your-admin-api-key>`

**Security Notes:**
- Key comparison uses constant-time algorithm (prevents timing attacks)
- Rate limited to 5 requests/minute (prevents brute-force)
- All admin actions logged with audit trail

**Request Body:**
```json
{
  "channel_id": "12345678-1234-1234-1234-123456789012",
  "service": "youtube",
  "date": "2026-01-25"
}
```

**Parameters:**
- `channel_id` (required): UUID of channel to reset
- `service` (required): `youtube` or `gemini`
- `date` (optional): Date to reset quota for (defaults to today in Pacific timezone)

**Example with curl:**
```bash
curl -X POST https://your-app.railway.app/api/v1/admin/quota-reset \
  -H "X-Admin-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"channel_id": "12345678-1234-1234-1234-123456789012", "service": "youtube"}'
```

**Response:**
```json
{
  "success": true,
  "message": "Successfully reset youtube quota for channel ...",
  "channel_id": "12345678-1234-1234-1234-123456789012",
  "service": "youtube",
  "date": "2026-01-25",
  "new_quota_units": 10000,
  "quota_exhausted_flag_cleared": true
}
```

### Manual Quota Reset via SQL (Last Resort)

If API is unavailable, run SQL directly in Railway PostgreSQL dashboard:

**Reset YouTube Quotas:**
```sql
-- Reset YouTube quotas for all active channels
INSERT INTO youtube_quota_usage (channel_id, date, units_used, daily_limit)
SELECT id, CURRENT_DATE, 0, 10000
FROM channels WHERE is_active = true
ON CONFLICT (channel_id, date) DO NOTHING;

UPDATE channels SET youtube_quota_exhausted = false WHERE is_active = true;
```

**Reset Gemini Quotas:**
```sql
-- Reset Gemini quotas for all active channels
INSERT INTO gemini_quota_usage (channel_id, date, requests_used, daily_limit)
SELECT id, CURRENT_DATE, 0, 1500
FROM channels WHERE is_active = true
ON CONFLICT (channel_id, date) DO NOTHING;

UPDATE channels SET gemini_quota_exhausted = false WHERE is_active = true;
```

### Quota Retention Policy

**Retention Period:** 90 days (minimum)

**Current Implementation (Story 7.0):**
- All quota records are RETAINED indefinitely
- No automatic deletion implemented
- Records allow historical analysis and compliance auditing

**Future Enhancement (Epic 8):**
- Optional cleanup job to delete records >90 days old
- Configurable retention period
- **Table size monitoring:** Automated alerts if quota tables exceed 100k rows (deferred to Epic 8 - Monitoring, Observability & Cost Tracking)
  - Will use PostgreSQL table size queries: `SELECT pg_total_relation_size('youtube_quota_usage')`
  - Alert threshold: 100,000 rows or 50MB table size
  - Cleanup recommendation: Archive records >90 days to cold storage

**Historical Queries:**
Quota tables are indexed by `(channel_id, date)` composite primary key, allowing efficient historical queries:

```sql
-- Get quota history for specific channel (last 30 days)
SELECT date, units_used, daily_limit
FROM youtube_quota_usage
WHERE channel_id = '12345678-1234-1234-1234-123456789012'
  AND date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY date DESC;

-- Analyze quota trends across all channels
SELECT date, SUM(units_used) as total_usage, COUNT(*) as channel_count
FROM youtube_quota_usage
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY date
ORDER BY date DESC;
```

## Railway Deployment Configuration

### Environment Variables

**Required for Quota Resets:**
- `QUOTA_TIMEZONE` (default: `America/Los_Angeles`): Timezone for quota resets
- `ADMIN_API_KEY` (required): Admin API key for manual quota reset endpoint

**Example Railway Configuration:**
```bash
# Railway environment variables (worker service)
QUOTA_TIMEZONE=America/Los_Angeles
ADMIN_API_KEY=your-secure-random-key-here
```

### Scheduler Behavior

**Startup:**
- Scheduler starts automatically when worker process starts
- Jobs re-register on every restart (in-memory scheduler)
- Next run times logged on startup

**Shutdown:**
- Scheduler shuts down gracefully on SIGTERM
- Waits for running jobs to complete
- No pending jobs are lost (will run next midnight)

**Missed Runs:**
- If worker down at midnight, reset is SKIPPED
- No backfill of missed resets
- Manual reset required if quota not reset

**Health Check:**
Verify scheduler is running:
```python
from app.scheduler import is_scheduler_running
print(is_scheduler_running())  # True if running
```

### Monitoring

**Logs to Watch:**
- `quota_reset_scheduler_started`: Scheduler initialization
- `youtube_quota_reset_job_success`: Successful YouTube reset
- `gemini_quota_reset_job_success`: Successful Gemini reset
- `youtube_quota_reset_job_failed`: YouTube reset failure (CRITICAL)
- `gemini_quota_reset_job_failed`: Gemini reset failure (CRITICAL)

**Railway Logs Filter:**
```
quota_reset
```

**Expected Daily Logs:**
- `00:00 PST`: Two success logs (YouTube + Gemini)
- If failures: CRITICAL alerts in Discord with SQL fallback commands

### Troubleshooting

**Problem: Scheduler not starting**
- Check worker logs for `quota_reset_scheduler_started`
- Verify APScheduler dependency installed (`apscheduler>=3.10.0`)
- Check for import errors in scheduler.py

**Problem: Jobs not running at midnight**
- Verify QUOTA_TIMEZONE environment variable
- Check next run times in startup logs
- Ensure worker is running at midnight (Railway deployment timing)

**Problem: Reset jobs failing**
- Check database connectivity
- Verify active channels exist (`SELECT * FROM channels WHERE is_active = true`)
- Review error logs for specific exception

**Problem: Discord alerts not sent**
- Verify DISCORD_WEBHOOK_URL configured
- Check alert_service.py for webhook errors
- Manual reset required if alerts fail

## See Also

- **Architecture Documentation:** `_bmad-output/planning-artifacts/architecture.md`
- **Story 7.0 Details:** `_bmad-output/implementation-artifacts/7-0-automated-quota-reset.md`
- **Project Context:** `_bmad-output/project-context.md`
