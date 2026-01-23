# Railway Log Query Guide

This guide provides Railway log query patterns for debugging and monitoring the AI video generator pipeline.

## Quick Reference

```bash
# All logs for a specific task
correlation_id="<task-uuid>"

# All pipeline errors
event="pipeline_step_failed"

# All retry events
event="task_retry_*"

# Specific step errors
step_name="video_generation" AND level="ERROR"

# Terminal failures only
event="task_terminal_failure"

# Channel-specific errors
channel_id="poke1" AND level="ERROR"
```

## Correlation IDs

Every log entry includes a `correlation_id` field (set to `task.id`) for distributed tracing. Use this to view all logs related to a single task execution across retries and steps.

**Example: Trace complete task lifecycle**
```bash
correlation_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

This shows:
- Pipeline start
- Each step started/completed
- Any errors and retry attempts
- Terminal failure or final success

## Error Filtering

### All Pipeline Step Failures

View all errors that occurred during pipeline step execution:

```bash
event="pipeline_step_failed"
```

**Sample output:**
```json
{
  "event": "pipeline_step_failed",
  "task_id": "abc-123",
  "correlation_id": "abc-123",
  "step_name": "video_generation",
  "error_type": "TimeoutError",
  "error_message": "KIE.ai API timeout after 600s",
  "retry_attempt": 1,
  "is_transient": true,
  "error_category": "transient",
  "api_service": "KIE.ai",
  "failure_location": "Video Generation: Item 11 of 18",
  "partial_progress": {"completed_video_clips": [1,2,3,4,5,6,7,8,9,10]}
}
```

### Step-Specific Errors

Filter errors by pipeline step:

```bash
# Video generation errors only
step_name="video_generation" AND level="ERROR"

# Asset generation errors only
step_name="asset_generation" AND level="ERROR"

# Audio generation errors only
step_name="narration_generation" AND level="ERROR"
```

### Error Category Filtering

Filter by error classification (from Story 6.1):

```bash
# Transient errors (retry eligible)
error_category="transient"

# Permanent errors (not retriable)
error_category="permanent"

# Configuration errors (API key issues)
error_category="configuration"

# Quota exceeded errors
error_category="quota_exceeded"
```

### API Service Filtering

Filter errors by external API service:

```bash
# Kling video generation errors
api_service="KIE.ai"

# Gemini image generation errors
api_service="Gemini"

# ElevenLabs audio errors
api_service="ElevenLabs"
```

## Retry Tracking

### All Retry Events

View all retry-related events:

```bash
event="task_retry_*"
```

This matches:
- `task_retry_scheduled`
- `task_retry_claimed`

### Retry Scheduling

When a retry is scheduled after a failure:

```bash
event="task_retry_scheduled"
```

**Sample output:**
```json
{
  "event": "task_retry_scheduled",
  "task_id": "abc-123",
  "correlation_id": "abc-123",
  "retry_attempt": 2,
  "next_retry_at": "2026-01-23T12:05:00+00:00",
  "retry_delay_seconds": 300
}
```

### Retry Claims

When a worker claims a retry task:

```bash
event="task_retry_claimed"
```

**Sample output:**
```json
{
  "event": "task_retry_claimed",
  "task_id": "abc-123",
  "correlation_id": "abc-123",
  "retry_attempt": 2,
  "worker_id": "worker-1"
}
```

### Retry Progression

Track retry attempts for a specific task:

```bash
correlation_id="abc-123" AND (event="task_retry_*" OR event="pipeline_step_failed")
```

This shows:
1. Initial failure → `pipeline_step_failed` (retry_attempt=1)
2. Retry scheduled → `task_retry_scheduled` (next retry in 1 min)
3. Retry claimed → `task_retry_claimed` (worker starts retry)
4. Retry failure (if it fails again) → `pipeline_step_failed` (retry_attempt=2)
5. ... continues until success or terminal failure

## Terminal Failures

When all retry attempts are exhausted:

```bash
event="task_terminal_failure"
```

**Sample output:**
```json
{
  "event": "task_terminal_failure",
  "task_id": "abc-123",
  "correlation_id": "abc-123",
  "channel_id": "poke1",
  "retry_attempts": 3,
  "final_error_type": "KlingAPITimeout",
  "final_error_message": "Video generation timeout after 10 minutes"
}
```

## Pipeline Step Lifecycle

### Step Initiation

When a pipeline step starts:

```bash
event="pipeline_step_started"
```

**Sample output:**
```json
{
  "event": "pipeline_step_started",
  "task_id": "abc-123",
  "correlation_id": "abc-123",
  "channel_id": "poke1",
  "step_name": "video_generation",
  "timestamp": "2026-01-23T12:00:00+00:00"
}
```

### Step Completion

When a pipeline step completes successfully:

```bash
event="pipeline_step_completed"
```

**Sample output:**
```json
{
  "event": "pipeline_step_completed",
  "task_id": "abc-123",
  "correlation_id": "abc-123",
  "channel_id": "poke1",
  "step_name": "video_generation",
  "duration_seconds": 1234.5
}
```

### Complete Step Lifecycle

View start, completion, and any errors for a specific step:

```bash
correlation_id="abc-123" AND step_name="video_generation"
```

## Channel Filtering

Filter logs by YouTube channel:

```bash
# All logs for poke1 channel
channel_id="poke1"

# All errors for poke1 channel
channel_id="poke1" AND level="ERROR"

# All video generation for poke1 channel
channel_id="poke1" AND step_name="video_generation"
```

## Common Debugging Scenarios

### Scenario 1: Task is Stuck

**Query:** Find last log entry for task
```bash
task_id="abc-123"
```

Sort by timestamp (descending) and check:
- Last event type
- Last step_name
- Any error messages

### Scenario 2: Repeated Failures

**Query:** View all failures for a task
```bash
correlation_id="abc-123" AND event="pipeline_step_failed"
```

Check:
- `retry_attempt` progression (should increment: 1, 2, 3...)
- `error_type` consistency (same error repeated?)
- `is_transient` field (should retry be attempted?)
- `error_category` (transient vs permanent)

### Scenario 3: Video Generation Slow

**Query:** Find video generation durations
```bash
step_name="video_generation" AND event="pipeline_step_completed"
```

Check `duration_seconds` field across multiple tasks to identify slow patterns.

### Scenario 4: API Quota Issues

**Query:** Find quota errors
```bash
error_category="quota_exceeded" OR error_message="*quota*" OR error_message="*429*"
```

Check which `api_service` is hitting quotas.

### Scenario 5: Checkpoint Resume

**Query:** Find partial progress before failure
```bash
correlation_id="abc-123" AND event="pipeline_step_failed"
```

Check `partial_progress` field to see which sub-steps completed:
```json
{
  "partial_progress": {
    "completed_video_clips": [1,2,3,4,5,6,7,8,9,10],
    "failed_at_clip": 11
  }
}
```

### Scenario 6: Worker Performance

**Query:** Find which workers are claiming retries
```bash
event="task_retry_claimed"
```

Group by `worker_id` to see retry distribution.

## Log Field Reference

### Common Fields (All Events)

- `event`: Event type identifier (e.g., "pipeline_step_failed")
- `timestamp`: ISO 8601 timestamp (auto-added by structlog)
- `level`: Log level (INFO, WARNING, ERROR, CRITICAL)
- `task_id`: Task UUID
- `correlation_id`: Correlation UUID (typically same as task_id)
- `channel_id`: YouTube channel identifier

### Error Events (`pipeline_step_failed`)

- `step_name`: Pipeline step that failed
- `error_type`: Exception class name
- `error_message`: Human-readable error description
- `retry_attempt`: Current retry attempt number (1-3)
- `is_transient`: Boolean (true if retriable)
- `error_category`: Error classification (transient, permanent, etc.)
- `api_service`: External API that caused error (KIE.ai, Gemini, ElevenLabs)
- `failure_location`: Human-readable failure location
- `partial_progress`: Dict with checkpoint data
- `suggested_action`: Recommended action from error classifier
- `confidence`: Classifier confidence (0.0-1.0)

### Retry Events

**`task_retry_scheduled`:**
- `retry_attempt`: Retry attempt number
- `next_retry_at`: ISO 8601 timestamp of next retry
- `retry_delay_seconds`: Delay in seconds

**`task_retry_claimed`:**
- `retry_attempt`: Retry attempt number
- `worker_id`: Worker process identifier

**`task_terminal_failure`:**
- `retry_attempts`: Total retry attempts made (typically 3)
- `final_error_type`: Last exception type
- `final_error_message`: Last error message

### Pipeline Step Events

**`pipeline_step_started`:**
- `step_name`: Step being started
- `timestamp`: When step started

**`pipeline_step_completed`:**
- `step_name`: Step that completed
- `duration_seconds`: Step execution time

## Tips

1. **Use correlation_id for complete traces**: Always start with `correlation_id` to see the full task lifecycle

2. **Combine filters**: Railway supports boolean operators (AND, OR, NOT)
   ```bash
   channel_id="poke1" AND step_name="video_generation" AND level="ERROR"
   ```

3. **Wildcard matching**: Use `*` for partial matches
   ```bash
   error_message="*timeout*"
   ```

4. **Time-based filtering**: Use Railway's time picker in the UI to narrow results

5. **Export results**: Railway allows exporting filtered logs for offline analysis

6. **Create saved queries**: Save common queries in Railway dashboard for quick access

## Railway Dashboard Setup

Create these saved queries in your Railway dashboard:

1. **Active Errors** (last 1 hour):
   ```bash
   level="ERROR" AND timestamp>="now-1h"
   ```

2. **Terminal Failures** (last 24 hours):
   ```bash
   event="task_terminal_failure" AND timestamp>="now-24h"
   ```

3. **Retry Activity** (last 6 hours):
   ```bash
   event="task_retry_*" AND timestamp>="now-6h"
   ```

4. **Slow Videos** (>30 minutes):
   ```bash
   step_name="video_generation" AND event="pipeline_step_completed" AND duration_seconds>1800
   ```

5. **API Quota Errors** (last 7 days):
   ```bash
   error_category="quota_exceeded" AND timestamp>="now-7d"
   ```

---

**Related Documentation:**
- Story 6.1: Error Classification
- Story 6.2: Exponential Backoff Retry
- Story 6.3: Checkpoint-Based Resume
- Story 6.4: Granular Error Status Updates
- Story 6.5: Detailed Error Logging (this guide)
