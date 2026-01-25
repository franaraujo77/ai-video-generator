# YouTube Metadata Generation

**Story:** 7.3 - Video Metadata Generation
**FR:** FR62 (Generate metadata from Notion entry)
**Status:** Implementation complete, ready for Story 7.4 integration

## Overview

The metadata generation service transforms Task and Channel data into YouTube Data API v3 compatible metadata for video uploads. It combines:

- **Task fields** (title, topic, story_direction) synced from Notion
- **Channel configuration** (default_tags, description_template, default_privacy) from YAML config
- **YouTube API limits** (title: 100 chars, description: 5000 chars, tags: 30/500)

## Architecture

```
Task (APPROVED status)
    ↓
generate_metadata(task, db)
    ↓
1. Validate task status (must be APPROVED)
2. Fetch Channel config from database
3. Generate title (task.title → truncate if > 100 chars)
4. Generate description (template + placeholders → truncate if > 5000 chars)
5. Generate tags (channel defaults + topic tags → normalize, trim to 30/500)
6. Set privacy (channel.default_privacy or "unlisted")
7. Validate metadata (YouTube limits enforcement)
8. Log success with metrics
    ↓
MetadataDict (ready for Story 7.4 upload)
```

## MetadataDict Schema

```python
from app.services.metadata_service import MetadataDict

metadata: MetadataDict = {
    "title": str,              # 1-100 chars (truncated with warning)
    "description": str,        # 0-5000 chars (truncated with warning)
    "tags": list[str],        # Max 30 tags, 500 chars total
    "privacy_status": str,    # "private" | "unlisted" | "public"
    "category_id": str,       # "24" (Entertainment) or "15" (Pets & Animals)
}
```

### YouTube Data API v3 Limits

| Field | Limit | Enforcement |
|-------|-------|-------------|
| Title | 100 chars | Truncate to 97 + "..." with WARNING log |
| Description | 5000 chars | Truncate to 4997 + "..." with WARNING log |
| Tags | 30 tags | Trim from end to 30 tags |
| Tags | 500 chars total | Trim from end until total <= 500 chars |
| Privacy | Must be "private", "unlisted", or "public" | Validation error if invalid |

## Channel Configuration

Channels configure metadata generation via YAML files in `config/channels/`.

**Example:** `config/channels/poke1.yaml`

```yaml
channel_id: poke1
channel_name: "Pokemon Nature Documentary"

# Story 7.3: Metadata Configuration
default_tags:
  - pokemon
  - nature
  - documentary
  - wildlife
  - ai-generated

description_template: |
  {title}

  Welcome to the world of {topic}. This nature documentary explores the fascinating life,
  habitat, and behavior of {topic} in their natural environment.

  {story_direction_summary}

  Credits:
  - Produced by {channel_name}
  - Technology: AI-Generated Documentary

  More videos: {channel_links}

  #{topic_slug} #nature #documentary #shorts

default_privacy: "unlisted"  # or "private", "public"
```

### Template Placeholders

| Placeholder | Source | Example |
|------------|--------|---------|
| `{title}` | task.title | "Pikachu: The Electric Mouse Pokémon" |
| `{topic}` | task.topic | "Pikachu" |
| `{channel_name}` | channel.channel_name | "Pokemon Nature Documentary" |
| `{story_direction_summary}` | First paragraph of task.story_direction | "Follow Pikachu through..." |
| `{channel_links}` | Placeholder (future: actual links) | "Subscribe to Pokemon Nature Documentary" |
| `{topic_slug}` | Slugified task.topic | "pikachu" (lowercase, no spaces) |

## Usage

### Basic Usage

```python
from app.services.metadata_service import generate_metadata
from sqlalchemy.ext.asyncio import AsyncSession

async def upload_video(task_id: UUID):
    """Generate metadata and upload to YouTube (Story 7.4)."""
    async with AsyncSession() as db:
        # Fetch task
        task = await db.get(Task, task_id)

        # Generate metadata
        metadata = await generate_metadata(task, db)

        # metadata["title"] = "Pikachu: The Electric Mouse Pokémon"
        # metadata["description"] = "Welcome to the world of Pikachu..."
        # metadata["tags"] = ["pokemon", "nature", "pikachu"]
        # metadata["privacy_status"] = "unlisted"

        # Story 7.4 will use metadata for YouTube upload
        # await youtube_service.upload_video(video_path, metadata)
```

### Error Handling

```python
from app.services.metadata_service import (
    generate_metadata,
    MetadataGenerationError,
    MetadataGenerationRetryError,
)

try:
    metadata = await generate_metadata(task, db)
except MetadataGenerationError as e:
    # Permanent error - requires data correction
    log.error("metadata_generation_failed", error=str(e))
    # Mark task as failed, alert operator
    await mark_task_failed(task, error_message=str(e))

except MetadataGenerationRetryError as e:
    # Transient error - retry with exponential backoff
    log.warning("metadata_generation_retry", error=str(e))
    # Worker retry logic handles this
    raise
```

## Error Classification

### Permanent Errors (MetadataGenerationError)

Will NOT retry - requires data correction:

- Task status != APPROVED (not ready for upload)
- Channel not found in database (invalid channel_id)
- Missing required fields (title empty)
- Invalid privacy_status value (not "private", "unlisted", or "public")
- Template rendering errors (invalid placeholders)

### Transient Errors (MetadataGenerationRetryError)

Will retry with exponential backoff:

- Network timeout during database fetch
- Temporary database connection issues

## Tag Generation Strategy

Tags are generated by combining:

1. **Channel default tags** (`channel.default_tags`)
2. **Topic-specific tags** (`task.topic` split on commas)

Then normalized:

3. **Lowercase** all tags
4. **Deduplicate** (remove duplicates)
5. **Trim to 30 tags** (YouTube limit)
6. **Trim to 500 chars total** (including commas)

**Example:**

```python
# Channel config
default_tags = ["pokemon", "nature", "documentary"]

# Task
task.topic = "Pikachu, Electric Type, Cute"

# Generated tags
tags = [
    "pokemon",        # From channel defaults
    "nature",         # From channel defaults
    "documentary",    # From channel defaults
    "pikachu",        # From task.topic (normalized)
    "electric type",  # From task.topic (normalized)
    "cute",          # From task.topic (normalized)
]
```

## Structured Logging

All metadata generation events use structured logging with correlation_id for traceability.

### Success Event

```python
log.info(
    "metadata_generated",
    correlation_id=str(task.id),
    channel_id=str(task.channel_id),
    title_length=len(metadata["title"]),
    description_length=len(metadata["description"]),
    tag_count=len(metadata["tags"]),
    privacy_status=metadata["privacy_status"],
)
```

### Warning Events

```python
# Title truncated
log.warning(
    "title_truncated",
    correlation_id=str(task.id),
    original_length=150,
    truncated_length=100,
)

# Description truncated
log.warning(
    "description_truncated",
    correlation_id=str(task.id),
    original_length=5500,
    truncated_length=5000,
)
```

### Error Events

```python
# Permanent error
log.error(
    "metadata_generation_permanent_error",
    correlation_id=str(task.id),
    error=str(e),
    error_type=type(e).__name__,
)
```

## Database Schema

### Channel Model Fields (Story 7.3)

```python
class Channel(Base):
    # ... existing fields ...

    # Story 7.3: Video Metadata Generation
    default_tags: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Default tags for all channel videos",
    )

    description_template: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Description template with {placeholders}",
    )

    default_privacy: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="unlisted",
        server_default="unlisted",
        comment="Default privacy: 'private', 'unlisted', 'public'",
    )
```

### Migration

Migration: `alembic/versions/20260124_2200_add_story_7_3_metadata_fields_to_channel.py`

```bash
# Apply migration
uv run alembic upgrade head

# Verify in database
psql $DATABASE_URL -c "\d channels"
```

## Testing

Comprehensive test coverage (21 tests, all passing):

```bash
# Run metadata service tests
uv run pytest tests/services/test_metadata_service.py -v

# Test coverage includes:
# ✅ Title generation and truncation
# ✅ Description template placeholder substitution
# ✅ Description truncation
# ✅ Tag generation (channel + topic)
# ✅ Tag normalization (lowercase, deduplicate)
# ✅ Tag limits (30 tags, 500 chars)
# ✅ Privacy status configuration
# ✅ Validation (missing title, invalid privacy)
# ✅ Error handling (non-APPROVED task, missing channel)
# ✅ Full E2E integration test
```

## Integration Points

### Current (Story 7.3)

- **Input:** Task (APPROVED status) + Channel config
- **Output:** MetadataDict ready for YouTube upload
- **Dependencies:** Database (Channel model), Task model

### Future (Story 7.4+)

- **Story 7.4 (Resumable Upload):** Uses MetadataDict for `youtube.videos().insert()` API call
- **Story 7.5 (URL Retrieval):** Updates Notion with YouTube URL after successful upload
- **Story 7.8 (Privacy Configuration):** Uses `default_privacy` field for privacy settings

## Best Practices

### Template Design

1. **Keep templates simple** - Use {placeholders}, not complex logic
2. **Test with real data** - Verify placeholders render correctly
3. **Include hashtags** - 1-3 relevant hashtags at end (#{topic_slug} #nature #shorts)
4. **First 150 chars matter** - YouTube preview shows ~150 chars
5. **Call-to-action** - Include subscribe link, channel links

### Tag Strategy

1. **Niche tags > broad tags** - "AI Pokemon Documentary" beats "viral video"
2. **Mix trending + evergreen** - #Shorts + #Pokemon + channel-specific
3. **Avoid irrelevant popular tags** - Confuses YouTube algorithm
4. **3-6 highly targeted tags optimal** - Quality over quantity

### Privacy Settings

- **Private:** Only visible to owner (recommended during testing)
- **Unlisted:** Viewable by anyone with link (recommended until YouTube verification)
- **Public:** Visible to everyone (requires YouTube API compliance audit)

**Note:** Videos from unverified API projects (created after July 28, 2020) are restricted to **private viewing** until compliance audit complete.

## Troubleshooting

### "Cannot generate metadata for task in X status"

**Cause:** Task status != APPROVED
**Fix:** Ensure task reaches APPROVED status before metadata generation
**Prevention:** Only call `generate_metadata()` after task approval gates (Story 5.2)

### "Channel not found in database"

**Cause:** Invalid channel_id in Task
**Fix:** Verify channel exists in database
**Prevention:** Validate channel_id during task creation (Story 2.3)

### "Title exceeds 100 chars"

**Cause:** task.title > 100 characters
**Fix:** Automatic truncation with WARNING log
**Action:** Review truncated titles, consider shortening at source (Notion Title field)

### "Description exceeds 5000 chars"

**Cause:** Rendered description > 5000 characters
**Fix:** Automatic truncation with WARNING log
**Action:** Shorten description_template or story_direction summaries

### "Invalid privacy_status"

**Cause:** channel.default_privacy not in ["private", "unlisted", "public"]
**Fix:** Update channel YAML config with valid privacy value
**Prevention:** Validate YAML config on channel creation (Story 1.2)

## References

- **YouTube Data API v3:** https://developers.google.com/youtube/v3/docs/videos
- **YouTube Character Limits:** https://utilhq.com/articles/youtube-character-limits-seo-guide/
- **YouTube SEO Best Practices:** https://www.learningrevolution.net/youtube-seo/
- **Story 7.1:** YouTube OAuth Setup CLI
- **Story 7.2:** OAuth Token Refresh Automation
- **Story 7.4:** Resumable Upload Implementation (future integration)

---

**Last Updated:** 2026-01-24
**Author:** Story 7.3 Implementation
**Status:** Implementation complete, ready for Story 7.4
