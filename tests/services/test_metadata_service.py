"""Tests for YouTube metadata generation service (Story 7.3).

Comprehensive test coverage for metadata_service.py including:
- Title generation and truncation
- Description generation with template placeholders
- Tag generation (channel + topic tags, normalization, limits)
- Privacy status configuration
- YouTube Data API v3 field limit validation
- Error handling (permanent vs transient failures)
- Structured logging verification

Test Coverage Requirements (from story Dev Notes):
✅ 1. Title from task (direct mapping)
✅ 2. Title truncation (> 100 chars)
✅ 3. Description from template (placeholders replaced)
✅ 4. Description truncation (> 5000 chars)
✅ 5. Tags include channel defaults
✅ 6. Tags include topic-specific tags
✅ 7. Tags limit to 30 tags
✅ 8. Tags limit to 500 chars total
✅ 9. Validation fails on missing title
✅ 10. Validation fails on invalid privacy
✅ 11. Privacy from channel default
✅ 12. Error on non-APPROVED task
✅ 13. Error on missing channel
✅ 14. Full integration test (E2E metadata generation)
"""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.metadata_service import (
    generate_metadata,
    MetadataGenerationError,
    MetadataDict,
    _generate_description,
    _generate_tags,
    _extract_summary,
    _slugify,
    _validate_metadata,
    _resolve_privacy_status,
)
from app.models import Task, Channel, TaskStatus
from tests.support.factories.task_factory import create_task
from tests.support.factories.channel_factory import create_channel, create_channel_with_metadata


class TestMetadataTitle:
    """Test title generation and truncation."""

    @pytest.mark.asyncio
    async def test_metadata_title_from_task(self, async_session: AsyncSession):
        """Title should come from task.title (AC: direct mapping)."""
        channel = create_channel_with_metadata(channel_name="Test Channel")
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Pikachu: The Electric Mouse Pokémon",
            topic="Pikachu",
            story_direction="Test story direction",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        metadata = await generate_metadata(task, async_session)

        assert metadata["title"] == "Pikachu: The Electric Mouse Pokémon"
        assert metadata["privacy_status"] == "private"  # Story 7.8: Default is "private"
        assert len(metadata["tags"]) >= 0

    @pytest.mark.asyncio
    async def test_metadata_title_truncated(self, async_session: AsyncSession):
        """Title > 100 chars should be truncated with warning (AC: truncate with warning)."""
        channel = create_channel_with_metadata()
        async_session.add(channel)
        await async_session.commit()

        long_title = "A" * 150  # 150 chars, exceeds 100 char limit
        task = create_task(
            title=long_title,
            topic="Test",
            story_direction="Test",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        with patch("app.services.metadata_service.log") as mock_log:
            metadata = await generate_metadata(task, async_session)

            # Verify truncation
            assert len(metadata["title"]) == 100
            assert metadata["title"].endswith("...")
            assert metadata["title"][:97] == "A" * 97

            # Verify warning logged
            mock_log.warning.assert_any_call(
                "title_truncated",
                correlation_id=str(task.id),
                original_length=150,
                truncated_length=100,
            )


class TestMetadataDescription:
    """Test description generation with template placeholders."""

    @pytest.mark.asyncio
    async def test_metadata_description_from_template(self, async_session: AsyncSession):
        """Description should use template with placeholders replaced (AC: placeholders replaced)."""
        channel = create_channel_with_metadata(
            channel_name="Pokemon Channel",
            description_template=(
                "{title}\n\n"
                "Topic: {topic}\n"
                "Channel: {channel_name}\n"
                "Summary: {story_direction_summary}\n"
                "Links: {channel_links}\n"
                "#{topic_slug}"
            ),
        )
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Pikachu Documentary",
            topic="Pikachu",
            story_direction="First paragraph of story.\n\nSecond paragraph.",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        metadata = await generate_metadata(task, async_session)

        # Verify placeholders replaced
        assert "Pikachu Documentary" in metadata["description"]  # {title}
        assert "Topic: Pikachu" in metadata["description"]  # {topic}
        assert "Channel: Pokemon Channel" in metadata["description"]  # {channel_name}
        assert "First paragraph of story." in metadata["description"]  # {story_direction_summary}
        assert "Subscribe to Pokemon Channel" in metadata["description"]  # {channel_links}
        assert "#pikachu" in metadata["description"]  # {topic_slug}

        # Verify no raw placeholders remain
        assert "{" not in metadata["description"]
        assert "}" not in metadata["description"]

    @pytest.mark.asyncio
    async def test_metadata_description_truncated(self, async_session: AsyncSession):
        """Description > 5000 chars should be truncated (AC: truncate with warning)."""
        # Create a template that renders to > 5000 chars
        long_text = "B" * 5500  # Will render to > 5000 chars
        channel = create_channel_with_metadata(
            description_template=f"{{title}}\n\n{long_text}"  # Title + long text
        )
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Test",
            topic="Test",
            story_direction="Test",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        with patch("app.services.metadata_service.log") as mock_log:
            metadata = await generate_metadata(task, async_session)

            # Verify truncation
            assert len(metadata["description"]) == 5000
            assert metadata["description"].endswith("...")

            # Verify warning logged (original > 5000 after template rendering)
            assert mock_log.warning.call_count >= 1
            # Find the description_truncated call
            warning_calls = [
                call for call in mock_log.warning.call_args_list
                if call[0][0] == "description_truncated"
            ]
            assert len(warning_calls) == 1
            assert warning_calls[0][1]["correlation_id"] == str(task.id)

    @pytest.mark.asyncio
    async def test_metadata_description_uses_default_template(self, async_session: AsyncSession):
        """Description should use default template when channel.description_template is None."""
        channel = create_channel_with_metadata(
            channel_name="Test Channel",
            description_template=None,  # Force default template
        )
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Test Video",
            topic="Test Topic",
            story_direction="Test story direction content",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        metadata = await generate_metadata(task, async_session)

        # Verify default template structure
        assert "Test Video" in metadata["description"]
        assert "Welcome to the world of Test Topic" in metadata["description"]
        assert "Test Channel" in metadata["description"]
        assert "#testtopic" in metadata["description"]


class TestMetadataTags:
    """Test tag generation logic."""

    @pytest.mark.asyncio
    async def test_metadata_tags_include_defaults(self, async_session: AsyncSession):
        """Tags should include channel.default_tags (AC: channel default tags)."""
        channel = create_channel_with_metadata(
            default_tags=["pokemon", "nature", "documentary"]
        )
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Test",
            topic="",  # No topic tags
            story_direction="Test",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        metadata = await generate_metadata(task, async_session)

        # Verify channel default tags included
        assert "pokemon" in metadata["tags"]
        assert "nature" in metadata["tags"]
        assert "documentary" in metadata["tags"]

    @pytest.mark.asyncio
    async def test_metadata_tags_topic_specific(self, async_session: AsyncSession):
        """Tags should include topic-specific tags from task.topic (AC: topic tags)."""
        channel = create_channel_with_metadata(
            default_tags=["nature"]  # Only one default tag
        )
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Test",
            topic="Pikachu, Electric Type, Cute",  # Comma-separated topic tags
            story_direction="Test",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        metadata = await generate_metadata(task, async_session)

        # Verify topic tags included and normalized
        assert "pikachu" in metadata["tags"]
        assert "electric type" in metadata["tags"]
        assert "cute" in metadata["tags"]
        assert "nature" in metadata["tags"]  # Channel default

    @pytest.mark.asyncio
    async def test_metadata_tags_limit_30(self, async_session: AsyncSession):
        """Tags should be trimmed to 30 tags max (AC: max 30 tags)."""
        # Create 25 default tags + 10 topic tags = 35 total (should trim to 30)
        channel = create_channel_with_metadata(
            default_tags=[f"tag{i}" for i in range(25)]  # 25 default tags
        )
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Test",
            topic=", ".join([f"topic{i}" for i in range(10)]),  # 10 topic tags
            story_direction="Test",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        metadata = await generate_metadata(task, async_session)

        # Verify trimmed to 30 tags
        assert len(metadata["tags"]) == 30

    @pytest.mark.asyncio
    async def test_metadata_tags_limit_500_chars(self, async_session: AsyncSession):
        """Tags should be trimmed to 500 chars total (AC: max 500 chars)."""
        # Create tags that exceed 500 chars total
        long_tags = [f"verylongtag{i:03d}" for i in range(40)]  # ~560 chars total
        channel = create_channel_with_metadata(default_tags=long_tags)
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Test",
            topic="",
            story_direction="Test",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        metadata = await generate_metadata(task, async_session)

        # Verify total chars <= 500 (including commas)
        total_chars = sum(len(tag) for tag in metadata["tags"]) + max(
            0, len(metadata["tags"]) - 1
        )
        assert total_chars <= 500

    @pytest.mark.asyncio
    async def test_metadata_tags_normalized(self, async_session: AsyncSession):
        """Tags should be lowercase and deduplicated (AC: normalized)."""
        channel = create_channel_with_metadata(
            default_tags=["Pokemon", "Nature", "POKEMON"]  # Mixed case, duplicates
        )
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Test",
            topic="NATURE, nature, Nature",  # More duplicates
            story_direction="Test",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        metadata = await generate_metadata(task, async_session)

        # Verify lowercase
        assert all(tag == tag.lower() for tag in metadata["tags"])

        # Verify deduplicated (should only have "pokemon" and "nature")
        assert "pokemon" in metadata["tags"]
        assert "nature" in metadata["tags"]
        assert len([tag for tag in metadata["tags"] if tag == "pokemon"]) == 1
        assert len([tag for tag in metadata["tags"] if tag == "nature"]) == 1


class TestMetadataValidation:
    """Test metadata validation against YouTube limits."""

    @pytest.mark.asyncio
    async def test_metadata_validation_fails_on_missing_title(self):
        """Validation should fail if title is empty (AC: required field)."""
        metadata = MetadataDict(
            title="",  # Empty title
            description="Test description",
            tags=["test"],
            privacy_status="unlisted",
            category_id="24",
        )

        is_valid, warnings = await _validate_metadata(metadata)

        assert not is_valid
        assert "Title is required" in warnings[0]

    @pytest.mark.asyncio
    async def test_metadata_validation_fails_on_invalid_privacy(self):
        """Validation should fail if privacy_status is invalid (AC: validate privacy)."""
        metadata = MetadataDict(
            title="Test",
            description="Test",
            tags=["test"],
            privacy_status="invalid_value",  # Invalid privacy
            category_id="24",
        )

        is_valid, warnings = await _validate_metadata(metadata)

        assert not is_valid
        assert "Invalid privacy_status" in warnings[0]
        assert "private" in warnings[0]
        assert "unlisted" in warnings[0]
        assert "public" in warnings[0]


class TestMetadataPrivacy:
    """Test privacy status configuration."""

    @pytest.mark.asyncio
    async def test_metadata_privacy_from_channel_default(self, async_session: AsyncSession):
        """Privacy should come from channel.default_privacy (AC: use channel config)."""
        channel = create_channel_with_metadata(default_privacy="private")
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Test",
            topic="Test",
            story_direction="Test",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        metadata = await generate_metadata(task, async_session)

        assert metadata["privacy_status"] == "private"

    @pytest.mark.asyncio
    async def test_metadata_privacy_defaults_to_private(self, async_session: AsyncSession):
        """Privacy should default to 'private' if channel.default_privacy is None (Story 7.8 AC7)."""
        channel = create_channel(channel_name="Test Channel")
        channel.default_privacy = None  # None means use global default
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Test",
            topic="Test",
            story_direction="Test",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        metadata = await generate_metadata(task, async_session)

        # AC7: Global default is "private" (safest option)
        assert metadata["privacy_status"] == "private"

    @pytest.mark.asyncio
    async def test_metadata_privacy_override_takes_precedence(self, async_session: AsyncSession):
        """Per-video privacy override should take precedence over channel default (Story 7.8 AC5)."""
        channel = create_channel_with_metadata(default_privacy="private")
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Test",
            topic="Test",
            story_direction="Test",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        # AC5: Per-video override from Notion (highest priority)
        task.privacy_override = "public"
        async_session.add(task)
        await async_session.commit()

        metadata = await generate_metadata(task, async_session)

        # Should use per-video override, not channel default
        assert metadata["privacy_status"] == "public"

    @pytest.mark.asyncio
    async def test_metadata_privacy_invalid_override_uses_channel_default(self, async_session: AsyncSession):
        """If privacy_override is invalid, should fall back to channel default (Story 7.8 AC6 robustness)."""
        channel = create_channel_with_metadata(default_privacy="unlisted")
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Test",
            topic="Test",
            story_direction="Test",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        # Invalid privacy value (should not happen if Notion validation works, but defensive)
        task.privacy_override = "hidden"  # Invalid - not "public"/"unlisted"/"private"
        async_session.add(task)
        await async_session.commit()

        metadata = await generate_metadata(task, async_session)

        # Should fall back to channel default when override is invalid
        assert metadata["privacy_status"] == "unlisted"

    @pytest.mark.asyncio
    async def test_metadata_privacy_uses_channel_default_when_no_override(self, async_session: AsyncSession):
        """Should use channel default when no per-video override (Story 7.8 AC6)."""
        channel = create_channel_with_metadata(default_privacy="unlisted")
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Test",
            topic="Test",
            story_direction="Test",
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        task.privacy_override = None  # No per-video override
        async_session.add(task)
        await async_session.commit()

        metadata = await generate_metadata(task, async_session)

        # AC6: Should use channel default when no override
        assert metadata["privacy_status"] == "unlisted"


class TestMetadataErrors:
    """Test error handling and error classification."""

    @pytest.mark.asyncio
    async def test_metadata_error_on_non_approved_task(self, async_session: AsyncSession):
        """Should raise MetadataGenerationError if task status != APPROVED (AC: validate status)."""
        channel = create_channel_with_metadata()
        async_session.add(channel)
        await async_session.commit()

        task = create_task(
            title="Test",
            topic="Test",
            story_direction="Test",
            channel_id=channel.id,
            status=TaskStatus.QUEUED,  # Not APPROVED
        )
        async_session.add(task)
        await async_session.commit()

        with pytest.raises(
            MetadataGenerationError, match="Status must be APPROVED"
        ) as exc_info:
            await generate_metadata(task, async_session)

        assert "queued" in str(exc_info.value)  # Lowercase status value

    @pytest.mark.asyncio
    async def test_metadata_error_on_missing_channel(self, async_session: AsyncSession):
        """Should raise MetadataGenerationError if channel not found (AC: validate channel)."""
        import uuid

        fake_channel_id = uuid.uuid4()

        task = create_task(
            title="Test",
            topic="Test",
            story_direction="Test",
            channel_id=fake_channel_id,  # Non-existent channel
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        with pytest.raises(
            MetadataGenerationError, match="Channel .* not found"
        ) as exc_info:
            await generate_metadata(task, async_session)

        assert str(fake_channel_id) in str(exc_info.value)


class TestHelperFunctions:
    """Test helper functions used by metadata service."""

    def test_extract_summary_first_paragraph(self):
        """_extract_summary should return first paragraph."""
        text = "First paragraph content.\n\nSecond paragraph content."
        summary = _extract_summary(text, max_chars=100)

        assert summary == "First paragraph content."

    def test_extract_summary_truncate_long_text(self):
        """_extract_summary should truncate if first paragraph > max_chars."""
        text = "A" * 500  # 500 char paragraph
        summary = _extract_summary(text, max_chars=100)

        assert len(summary) == 100
        assert summary.endswith("...")
        assert summary[:97] == "A" * 97

    def test_slugify_removes_special_chars(self):
        """_slugify should remove special chars and spaces."""
        assert _slugify("Pikachu, Electric Type!") == "pikachuelectrictype"
        assert _slugify("Bulbasaur - Grass Type") == "bulbasaurgrasstype"
        assert _slugify("Charizard (Fire/Flying)") == "charizardfireflying"  # Keeps alphanumeric

    def test_slugify_lowercase(self):
        """_slugify should convert to lowercase."""
        assert _slugify("PIKACHU") == "pikachu"
        assert _slugify("PiKaChU") == "pikachu"


class TestIntegrationEndToEnd:
    """End-to-end integration tests for full metadata generation."""

    @pytest.mark.asyncio
    async def test_metadata_generation_full_integration(self, async_session: AsyncSession):
        """Full E2E test: Generate metadata from Task + Channel config."""
        # Setup channel with full metadata config
        channel = create_channel_with_metadata(
            channel_id="poke1",
            channel_name="Pokemon Nature Documentary",
            default_tags=["pokemon", "nature", "documentary"],
            description_template=(
                "{title}\n\n"
                "Explore the world of {topic}!\n\n"
                "{story_direction_summary}\n\n"
                "Produced by {channel_name}\n\n"
                "#{topic_slug} #nature #shorts"
            ),
            default_privacy="unlisted",
        )
        async_session.add(channel)
        await async_session.commit()

        # Setup task with full data
        task = create_task(
            title="Pikachu: The Electric Mouse Pokémon",
            topic="Pikachu, Electric Type, Kanto",
            story_direction=(
                "Follow Pikachu through its natural habitat in the Viridian Forest.\n\n"
                "Second paragraph with more details."
            ),
            channel_id=channel.id,
            status=TaskStatus.APPROVED,
        )
        async_session.add(task)
        await async_session.commit()

        # Generate metadata
        with patch("app.services.metadata_service.log") as mock_log:
            metadata = await generate_metadata(task, async_session)

            # Verify title
            assert metadata["title"] == "Pikachu: The Electric Mouse Pokémon"

            # Verify description placeholders replaced
            assert "Pikachu: The Electric Mouse Pokémon" in metadata["description"]
            assert "Explore the world of Pikachu" in metadata["description"]
            assert "Pokemon Nature Documentary" in metadata["description"]
            assert "Follow Pikachu through its natural habitat" in metadata["description"]
            assert "#pikachu" in metadata["description"]

            # Verify tags (channel + topic)
            assert "pokemon" in metadata["tags"]
            assert "nature" in metadata["tags"]
            assert "documentary" in metadata["tags"]
            assert "pikachu" in metadata["tags"]
            assert "electric type" in metadata["tags"]
            assert "kanto" in metadata["tags"]

            # Verify privacy
            assert metadata["privacy_status"] == "unlisted"

            # Verify category
            assert metadata["category_id"] == "24"

            # Verify success logging (Story 7.8: Now logs privacy resolution + metadata_generated)
            # Check that log.info was called at least twice (privacy resolution + metadata_generated)
            assert mock_log.info.call_count >= 2

            # Check the final log call is metadata_generated
            final_log_call = mock_log.info.call_args
            assert final_log_call[0][0] == "metadata_generated"
            assert final_log_call[1]["correlation_id"] == str(task.id)
            assert final_log_call[1]["channel_id"] == str(channel.id)
            assert final_log_call[1]["title_length"] == len(metadata["title"])
            assert final_log_call[1]["description_length"] == len(metadata["description"])
            assert final_log_call[1]["tag_count"] == len(metadata["tags"])
            assert final_log_call[1]["privacy_status"] == "unlisted"
