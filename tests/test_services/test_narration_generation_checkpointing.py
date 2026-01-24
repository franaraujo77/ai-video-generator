"""Tests for narration generation sub-step checkpointing (Story 6.3, Task 5).

Tests verify:
- Narration clips already in step_metadata are skipped
- New clips update step_metadata after successful generation
- Safety check: if metadata says complete but file missing, regenerate
- Partial resume: clips 1-10 complete, resume from clip 11
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.models import Channel, Task, TaskStatus
from app.services.narration_generation import (
    NarrationGenerationService,
    NarrationManifest,
    NarrationClip,
)


@pytest.mark.asyncio
async def test_skip_completed_narration_clips_from_checkpoint(async_session, tmp_path):
    """Verify narration clips in step_metadata are skipped (Subtask 5.2)."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with completed narration clips 1-5 in step_metadata
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_AUDIO,
        completed_steps=[],
        step_metadata={"completed_narration_clips": [1, 2, 3, 4, 5]},
    )
    async_session.add(task)
    await async_session.commit()

    # Create narration generation service
    service = NarrationGenerationService("test_ch", str(task.id))

    # Create mock audio files for clips 1-5
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True)
    for i in range(1, 6):
        audio_file = audio_dir / f"clip_{i:02d}.mp3"
        audio_file.write_bytes(b"fake audio data" * 1024 * 10)  # 10KB fake audio

    # Create mock manifest with 6 clips
    clips = []
    for i in range(1, 7):
        clip = NarrationClip(
            clip_number=i,
            narration_text=f"Narration text for clip {i}",
            output_path=audio_dir / f"clip_{i:02d}.mp3",
        )
        clips.append(clip)

    manifest = NarrationManifest(clips=clips, voice_id="testvoiceid1234567890")

    # Mock the CLI script calls and audio duration validation
    with patch(
        "app.services.narration_generation.run_cli_script", new_callable=AsyncMock
    ) as mock_cli:
        with patch.object(
            service, "validate_audio_duration", new_callable=AsyncMock
        ) as mock_duration:
            # Create fake audio file after "generation"
            async def create_fake_audio(*args, **kwargs):
                # Extract output path from args
                output_arg_index = args[1].index("--output")
                output_path = Path(args[1][output_arg_index + 1])
                output_path.write_bytes(b"fake audio data" * 1024 * 10)

            mock_cli.side_effect = create_fake_audio
            mock_duration.return_value = 7.5  # Mock valid audio duration

            # Call generate_narration with resume=True
            result = await service.generate_narration(
                manifest,
                resume=True,
                task_id=str(task.id),
                db=async_session,
            )

    # Verify: clips 1-5 skipped, clip 6 generated
    assert result["skipped"] == 5
    assert result["generated"] == 1
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_update_checkpoint_after_narration_clip_generation(async_session, tmp_path):
    """Verify step_metadata updated after successful generation (Subtask 5.3)."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with no completed narration clips
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_AUDIO,
        completed_steps=[],
        step_metadata={"completed_narration_clips": []},
    )
    async_session.add(task)
    await async_session.commit()

    # Create narration generation service
    service = NarrationGenerationService("test_ch", str(task.id))

    # Create audio directory
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True)

    # Create mock manifest with 3 clips
    clips = []
    for i in range(1, 4):
        clip = NarrationClip(
            clip_number=i,
            narration_text=f"Narration text for clip {i}",
            output_path=audio_dir / f"clip_{i:02d}.mp3",
        )
        clips.append(clip)

    manifest = NarrationManifest(clips=clips, voice_id="testvoiceid1234567890")

    # Mock the CLI script calls and audio duration validation
    with patch(
        "app.services.narration_generation.run_cli_script", new_callable=AsyncMock
    ) as mock_cli:
        with patch.object(
            service, "validate_audio_duration", new_callable=AsyncMock
        ) as mock_duration:
            # Create fake audio file after "generation"
            async def create_fake_audio(*args, **kwargs):
                # Extract output path from args
                output_arg_index = args[1].index("--output")
                output_path = Path(args[1][output_arg_index + 1])
                output_path.write_bytes(b"fake audio data" * 1024 * 10)

            mock_cli.side_effect = create_fake_audio
            mock_duration.return_value = 7.5  # Mock valid audio duration

            # Call generate_narration
            result = await service.generate_narration(
                manifest,
                resume=True,
                task_id=str(task.id),
                db=async_session,
            )

    # Verify all 3 clips generated
    assert result["generated"] == 3
    assert result["skipped"] == 0
    assert result["failed"] == 0

    # Verify step_metadata updated with completed clip numbers
    # Query task fresh from database to see checkpoint updates
    from sqlalchemy import select
    from app.models import Task as TaskModel

    stmt = select(TaskModel).where(TaskModel.id == task.id)
    result_task = (await async_session.execute(stmt)).scalar_one()
    assert result_task.step_metadata["completed_narration_clips"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_safety_check_regenerate_if_audio_file_missing(async_session, tmp_path):
    """Verify narration clip regenerated if checkpoint exists but file missing (Subtask 5.4)."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with clip 1 in checkpoint but file will be missing
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_AUDIO,
        completed_steps=[],
        step_metadata={"completed_narration_clips": [1]},  # Checkpoint says clip 1 done
    )
    async_session.add(task)
    await async_session.commit()

    # Create narration generation service
    service = NarrationGenerationService("test_ch", str(task.id))

    # Create audio directory but NO audio file for clip 1
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True)

    # Create mock manifest with clip 1
    clip = NarrationClip(
        clip_number=1,
        narration_text="Narration text for clip 1",
        output_path=audio_dir / "clip_01.mp3",
    )
    manifest = NarrationManifest(clips=[clip], voice_id="testvoiceid1234567890")

    # Mock the CLI script calls and audio duration validation
    with patch(
        "app.services.narration_generation.run_cli_script", new_callable=AsyncMock
    ) as mock_cli:
        with patch.object(
            service, "validate_audio_duration", new_callable=AsyncMock
        ) as mock_duration:
            # Create fake audio file after "generation"
            async def create_fake_audio(*args, **kwargs):
                # Extract output path from args
                output_arg_index = args[1].index("--output")
                output_path = Path(args[1][output_arg_index + 1])
                output_path.write_bytes(b"fake audio data" * 1024 * 10)

            mock_cli.side_effect = create_fake_audio
            mock_duration.return_value = 7.5  # Mock valid audio duration

            # Call generate_narration
            result = await service.generate_narration(
                manifest,
                resume=True,
                task_id=str(task.id),
                db=async_session,
            )

    # Verify: clip 1 regenerated (not skipped) because file was missing
    assert result["generated"] == 1
    assert result["skipped"] == 0
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_partial_resume_narration_clips_1_to_10_complete(async_session, tmp_path):
    """Verify resume from narration clip 11 when clips 1-10 complete (Subtask 5.5)."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with narration clips 1-10 completed in checkpoint
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_AUDIO,
        completed_steps=[],
        step_metadata={"completed_narration_clips": list(range(1, 11))},  # Clips 1-10
    )
    async_session.add(task)
    await async_session.commit()

    # Create narration generation service
    service = NarrationGenerationService("test_ch", str(task.id))

    # Create audio directory with files for clips 1-10
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True)
    for i in range(1, 11):
        audio_file = audio_dir / f"clip_{i:02d}.mp3"
        audio_file.write_bytes(b"fake audio data" * 1024 * 10)

    # Create mock manifest with 18 clips
    clips = []
    for i in range(1, 19):
        clip = NarrationClip(
            clip_number=i,
            narration_text=f"Narration text for clip {i}",
            output_path=audio_dir / f"clip_{i:02d}.mp3",
        )
        clips.append(clip)

    manifest = NarrationManifest(clips=clips, voice_id="testvoiceid1234567890")

    # Mock the CLI script calls and audio duration validation
    with patch(
        "app.services.narration_generation.run_cli_script", new_callable=AsyncMock
    ) as mock_cli:
        with patch.object(
            service, "validate_audio_duration", new_callable=AsyncMock
        ) as mock_duration:
            # Create fake audio files for clips 11-18
            async def create_fake_audio(*args, **kwargs):
                # Extract output path from args
                output_arg_index = args[1].index("--output")
                output_path = Path(args[1][output_arg_index + 1])
                output_path.write_bytes(b"fake audio data" * 1024 * 10)

            mock_cli.side_effect = create_fake_audio
            mock_duration.return_value = 7.5  # Mock valid audio duration

            # Call generate_narration
            result = await service.generate_narration(
                manifest,
                resume=True,
                task_id=str(task.id),
                db=async_session,
            )

    # Verify: clips 1-10 skipped, clips 11-18 generated
    assert result["skipped"] == 10
    assert result["generated"] == 8
    assert result["failed"] == 0

    # Verify step_metadata updated with all 18 clips
    # Query task fresh from database to see checkpoint updates
    from sqlalchemy import select
    from app.models import Task as TaskModel

    stmt = select(TaskModel).where(TaskModel.id == task.id)
    result_task = (await async_session.execute(stmt)).scalar_one()
    assert set(result_task.step_metadata["completed_narration_clips"]) == set(range(1, 19))
