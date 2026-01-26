"""YouTube video metadata generation service.

This service generates YouTube Data API v3 compatible metadata from Task and Channel
configuration. It combines Task fields (title, topic, story_direction) with Channel
metadata configuration (default_tags, description_template, default_privacy).

Story: 7.3 - Video Metadata Generation
FR: FR62 (Generate metadata from Notion entry)

Key Features:
- Title extraction with YouTube 100-char limit enforcement
- Description generation from templates with placeholder substitution
- Tag generation combining channel defaults + topic-specific tags
- Privacy status configuration per-channel
- Validation against YouTube Data API v3 limits
- Structured logging with correlation_id for traceability

Usage:
    from app.services.metadata_service import generate_metadata

    async with AsyncSession() as db:
        task = await db.get(Task, task_id)
        metadata = await generate_metadata(task, db)

        # metadata is MetadataDict ready for YouTube upload
        # Story 7.4 will use this for resumable upload
"""

import re
from typing import TypedDict

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Task, TaskStatus

log = structlog.get_logger(__name__)


class MetadataDict(TypedDict):
    """YouTube video metadata for upload (YouTube Data API v3).

    This TypedDict matches the YouTube videos.insert API schema.
    All fields are validated against YouTube limits before return.

    Fields:
        title: Video title (1-100 chars, truncated with warning)
        description: Video description (0-5000 chars, truncated with warning)
        tags: List of tags (max 30 tags, 500 chars total)
        privacy_status: Privacy setting ("private" | "unlisted" | "public")
        category_id: YouTube category ("24" = Entertainment, "15" = Pets & Animals)

    Reference:
        https://developers.google.com/youtube/v3/docs/videos#resource
    """

    title: str
    description: str
    tags: list[str]
    privacy_status: str
    category_id: str


class MetadataGenerationError(Exception):
    """Permanent metadata generation failure (fix required).

    Raised when metadata generation fails due to:
    - Task status != APPROVED (not ready for upload)
    - Channel not found in database (invalid channel_id)
    - Missing required fields (title, topic)
    - Invalid privacy_status value
    - Template rendering errors (invalid placeholders)

    These errors are not retriable - they require data correction.
    """

    pass


class MetadataGenerationRetryError(Exception):
    """Transient metadata generation failure (will retry).

    Raised when metadata generation fails due to:
    - Network timeout during database fetch
    - Temporary database connection issues

    Worker should retry these errors with exponential backoff.
    """

    pass


# Default description template (used when channel.description_template is None)
DEFAULT_DESCRIPTION_TEMPLATE = """{title}

Welcome to the world of {topic}. This nature documentary explores the fascinating life,
habitat, and behavior of {topic} in their natural environment.

{story_direction_summary}

Credits:
- Produced by {channel_name}
- Technology: AI-Generated Documentary

More videos: {channel_links}

#{topic_slug} #nature #documentary #shorts
"""


async def generate_metadata(task: Task, db: AsyncSession) -> MetadataDict:
    """Generate YouTube metadata from Task and Channel configuration.

    This is the main entry point for Story 7.3. It combines Task data (title, topic,
    story_direction) with Channel metadata configuration (default_tags, description_template,
    default_privacy) to produce a MetadataDict ready for YouTube upload.

    Args:
        task: Task in APPROVED status with title, topic, story_direction populated.
        db: Async database session for fetching Channel configuration.

    Returns:
        MetadataDict with validated YouTube metadata ready for upload.

    Raises:
        MetadataGenerationError: Permanent failure (invalid status, missing channel, bad data).
        MetadataGenerationRetryError: Transient failure (network, DB timeout).

    Example:
        >>> async with AsyncSession() as db:
        ...     task = await db.get(Task, task_id)
        ...     metadata = await generate_metadata(task, db)
        ...     # metadata["title"] = "Pikachu: The Electric Mouse Pokémon"
        ...     # metadata["description"] = "Welcome to the world of Pikachu..."
        ...     # metadata["tags"] = ["pokemon", "nature", "pikachu"]
        ...     # metadata["privacy_status"] = "unlisted"
    """
    try:
        # Step 1: Validate task status (AC: task must be APPROVED)
        if task.status != TaskStatus.APPROVED:
            raise MetadataGenerationError(
                f"Cannot generate metadata for task in {task.status.value} status. "
                f"Status must be APPROVED (current: {task.status.value})."
            )

        # Validate required task fields are non-empty
        # Title is always required (YouTube requirement)
        if not task.title or len(task.title.strip()) == 0:
            raise MetadataGenerationError(f"Task title is required but empty (task_id: {task.id})")
        # Topic and story_direction are optional (graceful degradation)
        # - If topic is empty, tags will come from channel defaults only
        # - If story_direction is empty, description summary will be empty string

        # Step 2: Fetch channel configuration from database
        result = await db.execute(select(Channel).where(Channel.id == task.channel_id))
        channel = result.scalar_one_or_none()

        if not channel:
            raise MetadataGenerationError(
                f"Channel {task.channel_id} not found in database. "
                f"Cannot generate metadata without channel configuration."
            )

        # Step 3: Generate title from task.title (AC: direct mapping)
        title = task.title
        if len(title) > 100:
            # Truncate to 97 chars + "..." (AC: truncate with warning)
            title = title[:97] + "..."
            log.warning(
                "title_truncated",
                correlation_id=str(task.id),
                original_length=len(task.title),
                truncated_length=len(title),
            )

        # Step 4: Generate description from template (AC: template placeholders replaced)
        description = _generate_description(task, channel)
        if len(description) > 5000:
            # Capture original length BEFORE truncation
            original_length = len(description)
            # Truncate to 4997 chars + "..." (AC: truncate with warning)
            description = description[:4997] + "..."
            log.warning(
                "description_truncated",
                correlation_id=str(task.id),
                original_length=original_length,
                truncated_length=5000,
            )

        # Step 5: Generate tags from channel + topic (AC: channel + topic tags combined)
        tags = _generate_tags(task, channel)

        # Step 6: Resolve privacy status with priority hierarchy (Story 7.8 AC5-7)
        # Priority: per-video override > channel default > global default ("private")
        privacy_status = _resolve_privacy_status(task, channel)

        # Step 7: Build metadata dict
        metadata = MetadataDict(
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status,
            # TODO (Story 7.8+): Make category_id configurable per-channel
            # Current: Hard-coded to "24" (Entertainment)
            # Future: Add default_category_id field to Channel model
            # Options: "24" (Entertainment), "15" (Pets & Animals), "28" (Science & Tech)
            category_id="24",
        )

        # Step 8: Validate metadata against YouTube limits (AC: validation enforced)
        is_valid, warnings = await _validate_metadata(metadata)
        if not is_valid:
            raise MetadataGenerationError(f"Metadata validation failed: {warnings}")

        # Log warnings for operators
        for warning in warnings:
            log.warning(
                "metadata_validation_warning",
                correlation_id=str(task.id),
                message=warning,
            )

        # Step 9: Log success with metrics
        log.info(
            "metadata_generated",
            correlation_id=str(task.id),
            channel_id=str(task.channel_id),
            title_length=len(metadata["title"]),
            description_length=len(metadata["description"]),
            tag_count=len(metadata["tags"]),
            privacy_status=metadata["privacy_status"],
        )

        return metadata

    except MetadataGenerationError:
        # Permanent error - re-raise
        raise

    except Exception as e:
        # Unexpected error - log and convert to permanent error
        log.error(
            "metadata_generation_unexpected_error",
            correlation_id=str(task.id),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise MetadataGenerationError(f"Unexpected error: {e!s}") from e


def _resolve_privacy_status(
    task: Task, channel: Channel
) -> str:  # "public" | "unlisted" | "private"
    """Resolve YouTube privacy status using priority hierarchy (Story 7.8 AC5-7).

    Privacy resolution follows this priority:
    1. Per-video override from Notion (task.privacy_override) - highest priority
    2. Channel default privacy (channel.default_privacy)
    3. Global default ("private") - lowest priority, safest option

    Args:
        task: Task with optional privacy_override from Notion.
        channel: Channel with default_privacy configuration.

    Returns:
        Privacy status string: "public" | "unlisted" | "private"

    Example:
        >>> # Per-video override takes precedence
        >>> task.privacy_override = "public"
        >>> channel.default_privacy = "private"
        >>> _resolve_privacy_status(task, channel)
        "public"

        >>> # Channel default used when no override
        >>> task.privacy_override = None
        >>> channel.default_privacy = "unlisted"
        >>> _resolve_privacy_status(task, channel)
        "unlisted"

        >>> # Global default when both None
        >>> task.privacy_override = None
        >>> channel.default_privacy = None
        >>> _resolve_privacy_status(task, channel)
        "private"
    """
    # AC5: If task has per-video privacy override from Notion, use it (highest priority)
    if task.privacy_override:
        # Validate privacy override value (defensive: should be caught at Notion sync)
        if task.privacy_override in {"public", "unlisted", "private"}:
            log.info(
                "privacy_override_applied",
                correlation_id=str(task.id),
                privacy_override=task.privacy_override,
                channel_default=channel.default_privacy,
                source="per_video_override",
            )
            return task.privacy_override
        else:
            # Invalid privacy override - log warning and fall through to channel default
            log.warning(
                "invalid_privacy_override_ignored",
                correlation_id=str(task.id),
                invalid_value=task.privacy_override,
                message="Privacy override must be 'public', 'unlisted', or 'private'. Using channel default.",  # noqa: E501
            )

    # AC6: Use channel default_privacy if set
    if channel.default_privacy:
        log.info(
            "privacy_from_channel_default",
            correlation_id=str(task.id),
            privacy=channel.default_privacy,
            source="channel_default",
        )
        return channel.default_privacy

    # AC7: Global default is "private" (safest option)
    log.info(
        "privacy_using_global_default",
        correlation_id=str(task.id),
        privacy="private",
        source="global_default",
    )
    return "private"


def _escape_format_braces(text: str) -> str:
    """Escape curly braces in text to prevent format string injection.

    Converts single braces to double braces so they're treated as literals
    in Python's str.format() calls.

    Args:
        text: User-controlled text that might contain {braces}.

    Returns:
        Text with braces escaped (e.g., "foo{bar}" -> "foo{{bar}}").

    Example:
        >>> _escape_format_braces("Title with {braces}")
        'Title with {{braces}}'
    """
    if not text:
        return ""
    return text.replace("{", "{{").replace("}", "}}")


def _sanitize_html_chars(text: str) -> str:
    """Sanitize HTML special characters for YouTube descriptions.

    YouTube descriptions are rendered as plain text, but special HTML characters
    like <, >, & should be escaped to prevent rendering issues or API rejection.

    Args:
        text: Text that might contain HTML special characters.

    Returns:
        Text with HTML characters escaped.

    Example:
        >>> _sanitize_html_chars("Title <with> HTML & chars")
        'Title &lt;with&gt; HTML &amp; chars'
    """
    if not text:
        return ""
    # Escape HTML special characters
    text = text.replace("&", "&amp;")  # Must be first to avoid double-escaping
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&#x27;")
    return text


def _generate_description(task: Task, channel: Channel) -> str:
    r"""Generate description from template with placeholder substitution.

    Uses channel.description_template if available, otherwise DEFAULT_DESCRIPTION_TEMPLATE.

    Placeholders:
        {title}: task.title
        {topic}: task.topic
        {channel_name}: channel.channel_name
        {story_direction_summary}: First paragraph or 300 chars from task.story_direction
        {channel_links}: Placeholder channel link string (future: actual links)
        {topic_slug}: Slugified topic for hashtags (lowercase, no spaces)

    Args:
        task: Task with title, topic, story_direction.
        channel: Channel with description_template, channel_name.

    Returns:
        Rendered description string with placeholders replaced.

    Example:
        >>> task = Task(title="Pikachu Video", topic="Pikachu", story_direction="Story here")
        >>> channel = Channel(
        ...     channel_name="Pokemon Channel", description_template="{title}\\n\\n{topic}"
        ... )
        >>> desc = _generate_description(task, channel)
        >>> assert "Pikachu Video" in desc
        >>> assert "{title}" not in desc  # Placeholders replaced
    """
    # Extract summary from story_direction (first paragraph or 300 chars)
    # Handle None gracefully - _extract_summary returns "" for None/empty
    story_summary = _extract_summary(task.story_direction or "", max_chars=300)

    # Build channel links (placeholder for now - Story 7.5 will implement)
    channel_links = _build_channel_links(channel)

    # Slugify topic for hashtags
    # Handle None gracefully - _slugify returns "" for None/empty
    topic_slug = _slugify(task.topic or "")

    # Use template or default
    template = channel.description_template or DEFAULT_DESCRIPTION_TEMPLATE

    # Sanitize and escape user-controlled data
    # 1. Escape HTML special characters to prevent rendering issues
    # 2. Escape format string braces to prevent injection
    safe_title = _escape_format_braces(_sanitize_html_chars(task.title))
    safe_topic = _escape_format_braces(_sanitize_html_chars(task.topic or ""))
    safe_story_summary = _escape_format_braces(_sanitize_html_chars(story_summary))

    # Render template with placeholders
    try:
        description = template.format(
            title=safe_title,
            topic=safe_topic,
            channel_name=channel.channel_name,  # Channel name is trusted (from DB config)
            story_direction_summary=safe_story_summary,
            channel_links=channel_links,  # Internal placeholder, trusted
            topic_slug=topic_slug,  # Slugified, safe (alphanumeric only)
        )
    except KeyError as e:
        # Invalid placeholder in template
        raise MetadataGenerationError(
            f"Template rendering failed: Invalid placeholder {e}. "
            f"Valid placeholders: title, topic, channel_name, story_direction_summary, "
            f"channel_links, topic_slug"
        ) from e

    return description


def _generate_tags(task: Task, channel: Channel) -> list[str]:
    """Generate tags from channel defaults + topic-specific tags.

    Combines channel.default_tags with tags extracted from task.topic.
    Tags are normalized (lowercase, deduplicated) and trimmed to YouTube limits.

    AC: Channel + topic tags combined
    AC: Tags normalized (lowercase, no duplicates)
    AC: Limit to 30 tags max
    AC: Limit to 500 chars total
    AC: Individual tags max 30 chars (YouTube best practice)

    Args:
        task: Task with topic field (comma-separated tags).
        channel: Channel with default_tags (list of strings).

    Returns:
        List of normalized tags (lowercase, deduplicated, limited).

    Example:
        >>> task = Task(topic="Pikachu, Electric Type")
        >>> channel = Channel(default_tags=["pokemon", "nature"])
        >>> tags = _generate_tags(task, channel)
        >>> assert "pokemon" in tags and "pikachu" in tags
        >>> assert len(tags) <= 30
        >>> assert all(tag == tag.lower() for tag in tags)
        >>> assert all(len(tag) <= 30 for tag in tags)
    """
    tags = []

    # Step 1: Channel default tags
    if channel.default_tags:
        tags.extend(channel.default_tags)

    # Step 2: Topic-specific tags (split on commas)
    if task.topic:
        # Split on commas, strip whitespace, filter empty
        topic_tags = [tag.strip() for tag in task.topic.split(",") if tag.strip()]
        tags.extend(topic_tags)

    # Step 3: Normalize - lowercase, remove duplicates, filter too-long tags
    # YouTube best practice: individual tags should be <= 30 chars
    MAX_TAG_LENGTH = 30  # noqa: N806
    tags = list({tag.lower() for tag in tags if tag and len(tag) <= MAX_TAG_LENGTH})

    # Step 4: Trim to 30 tags max (YouTube limit)
    tags = tags[:30]

    # Step 5: Trim to 500 chars total (YouTube limit)
    # Calculate total chars including commas (tag1,tag2,tag3)
    total_chars = sum(len(tag) for tag in tags) + max(0, len(tags) - 1)
    while tags and total_chars > 500:
        # Remove last tag and recalculate
        removed = tags.pop()
        total_chars -= len(removed)
        if tags:  # Account for comma removal
            total_chars -= 1

    return tags


def _extract_summary(text: str, max_chars: int) -> str:
    r"""Extract summary from text (first paragraph or max_chars).

    Args:
        text: Full text to summarize.
        max_chars: Maximum characters to return.

    Returns:
        First paragraph or truncated text (with "..." if truncated).

    Example:
        >>> summary = _extract_summary("First paragraph.\\n\\nSecond paragraph.", 50)
        >>> assert len(summary) <= 50
    """
    if not text:
        return ""

    # Split on double newlines (paragraph break)
    paragraphs = text.split("\n\n")
    first_para = paragraphs[0] if paragraphs else text

    # Truncate to max_chars
    if len(first_para) > max_chars:
        return first_para[: max_chars - 3] + "..."

    return first_para


def _build_channel_links(channel: Channel) -> str:
    """Build channel links for description.

    Placeholder implementation for Story 7.3.
    Future: Story 7.5 will implement actual YouTube channel links.

    Args:
        channel: Channel with channel_name.

    Returns:
        Placeholder channel link string.
    """
    return f"Subscribe to {channel.channel_name}"


def _slugify(text: str) -> str:
    """Convert text to hashtag-friendly slug (lowercase, no spaces).

    Removes special characters, converts to lowercase, removes spaces.

    Args:
        text: Text to slugify (e.g., "Pikachu, Electric Type").

    Returns:
        Slugified text (e.g., "pikachuelectrictype").

    Example:
        >>> _slugify("Pikachu, Electric Type")
        'pikachuelectrictype'
    """
    if not text:
        return ""
    # Remove special chars (keep alphanumeric and spaces)
    slug = re.sub(r"[^\w\s]", "", text)
    # Lowercase and remove spaces
    slug = slug.lower().replace(" ", "")
    return slug


async def _validate_metadata(metadata: MetadataDict) -> tuple[bool, list[str]]:
    """Validate metadata against YouTube limits.

    Checks:
    - Title: Required, max 100 chars
    - Description: Max 5000 chars
    - Tags: Max 30 tags, 500 chars total
    - Privacy: Must be "private", "unlisted", or "public"

    Args:
        metadata: MetadataDict to validate.

    Returns:
        Tuple of (is_valid, list of warnings).
        is_valid=False means validation failed (errors, not warnings).
        warnings are informational (e.g., "Title truncated").

    Example:
        >>> is_valid, warnings = await _validate_metadata(metadata)
        >>> if not is_valid:
        ...     raise MetadataGenerationError(f"Validation failed: {warnings}")
    """
    warnings = []

    # Title validation (REQUIRED)
    if not metadata["title"] or len(metadata["title"]) == 0:
        return False, ["Title is required and cannot be empty"]

    if len(metadata["title"]) > 100:
        warnings.append(
            f"Title exceeds 100 chars ({len(metadata['title'])} chars) - should have been truncated"
        )

    # Description validation
    if len(metadata["description"]) > 5000:
        warnings.append(
            f"Description exceeds 5000 chars ({len(metadata['description'])} chars) - "
            f"should have been truncated"
        )

    # Tags validation
    if len(metadata["tags"]) > 30:
        warnings.append(
            f"Tag count exceeds 30 ({len(metadata['tags'])} tags) - should have been trimmed"
        )

    total_tag_chars = sum(len(tag) for tag in metadata["tags"]) + max(0, len(metadata["tags"]) - 1)
    if total_tag_chars > 500:
        warnings.append(
            f"Tag total characters exceed 500 limit ({total_tag_chars} chars) - "
            f"should have been trimmed"
        )

    # Privacy validation (REQUIRED)
    valid_privacy = ["private", "unlisted", "public"]
    if metadata["privacy_status"] not in valid_privacy:
        return False, [
            f"Invalid privacy_status: {metadata['privacy_status']}. Must be one of: {valid_privacy}"
        ]

    return True, warnings
