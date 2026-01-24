"""Tests for video generation sub-step checkpointing (Story 6.3, Task 3).

Tests verify:
- Clips already in step_metadata are skipped
- New clips update step_metadata after successful generation
- Safety check: if metadata says complete but file missing, regenerate
- Partial resume: clips 1-10 complete, resume from clip 11
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.models import Channel, Task, TaskStatus
from app.services.video_generation import VideoGenerationService, VideoManifest, VideoClip


@pytest.mark.asyncio
async def test_skip_completed_clips_from_checkpoint(async_session, tmp_path):
    """Verify clips in step_metadata are skipped (Subtask 3.2)."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with completed clips 1-5 in step_metadata
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_VIDEO,
        completed_steps=[],
        step_metadata={"completed_video_clips": [1, 2, 3, 4, 5]},
    )
    async_session.add(task)
    await async_session.commit()

    # Create video generation service
    service = VideoGenerationService("test_ch", str(task.id))

    # Create mock video files for clips 1-5
    video_dir = tmp_path / "videos"
    video_dir.mkdir(parents=True)
    for i in range(1, 6):
        video_file = video_dir / f"clip_{i:02d}.mp4"
        video_file.write_bytes(b"fake video data" * 1024 * 100)  # 1.5MB fake video

    # Create mock manifest with 6 clips
    clips = []
    for i in range(1, 7):
        clip = VideoClip(
            clip_number=i,
            composite_path=tmp_path / f"composite_{i:02d}.png",
            motion_prompt=f"Motion prompt {i}",
            output_path=video_dir / f"clip_{i:02d}.mp4",
        )
        clips.append(clip)

    manifest = VideoManifest(clips=clips)

    # Mock the upload and CLI script calls
    with patch.object(service, "upload_to_catbox", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://catbox.moe/fake.png"

        with patch("app.services.video_generation.run_cli_script", new_callable=AsyncMock):
            # Call generate_videos with resume=True
            result = await service.generate_videos(
                manifest, resume=True, max_concurrent=2, task_id=str(task.id), db=async_session
            )

    # Verify: clips 1-5 skipped, clip 6 generated
    assert result["skipped"] == 5
    assert result["generated"] == 1
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_update_checkpoint_after_clip_generation(async_session, tmp_path):
    """Verify step_metadata updated after successful generation (Subtask 3.3)."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with no completed clips
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_VIDEO,
        completed_steps=[],
        step_metadata={"completed_video_clips": []},
    )
    async_session.add(task)
    await async_session.commit()

    # Create video generation service
    service = VideoGenerationService("test_ch", str(task.id))

    # Create video directory
    video_dir = tmp_path / "videos"
    video_dir.mkdir(parents=True)

    # Create mock manifest with 3 clips
    clips = []
    for i in range(1, 4):
        clip = VideoClip(
            clip_number=i,
            composite_path=tmp_path / f"composite_{i:02d}.png",
            motion_prompt=f"Motion prompt {i}",
            output_path=video_dir / f"clip_{i:02d}.mp4",
        )
        clips.append(clip)

    manifest = VideoManifest(clips=clips)

    # Mock the upload and CLI script calls
    with patch.object(service, "upload_to_catbox", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://catbox.moe/fake.png"

        with patch(
            "app.services.video_generation.run_cli_script", new_callable=AsyncMock
        ) as mock_cli:
            # Create fake video files after "generation"
            async def create_fake_video(*args, **kwargs):
                # Extract output path from args
                output_arg_index = args[1].index("--output")
                output_path = Path(args[1][output_arg_index + 1])
                output_path.write_bytes(b"fake video data" * 1024 * 100)

            mock_cli.side_effect = create_fake_video

            # Call generate_videos
            result = await service.generate_videos(
                manifest, resume=True, max_concurrent=2, task_id=str(task.id), db=async_session
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
    assert result_task.step_metadata["completed_video_clips"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_safety_check_regenerate_if_file_missing(async_session, tmp_path):
    """Verify clip regenerated if checkpoint exists but file missing (Subtask 3.4)."""
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
        status=TaskStatus.GENERATING_VIDEO,
        completed_steps=[],
        step_metadata={"completed_video_clips": [1]},  # Checkpoint says clip 1 done
    )
    async_session.add(task)
    await async_session.commit()

    # Create video generation service
    service = VideoGenerationService("test_ch", str(task.id))

    # Create video directory but NO video file for clip 1
    video_dir = tmp_path / "videos"
    video_dir.mkdir(parents=True)

    # Create mock manifest with clip 1
    clip = VideoClip(
        clip_number=1,
        composite_path=tmp_path / "composite_01.png",
        motion_prompt="Motion prompt 1",
        output_path=video_dir / "clip_01.mp4",
    )
    manifest = VideoManifest(clips=[clip])

    # Mock the upload and CLI script calls
    with patch.object(service, "upload_to_catbox", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://catbox.moe/fake.png"

        with patch(
            "app.services.video_generation.run_cli_script", new_callable=AsyncMock
        ) as mock_cli:
            # Create fake video file after "generation"
            async def create_fake_video(*args, **kwargs):
                output_arg_index = args[1].index("--output")
                output_path = Path(args[1][output_arg_index + 1])
                output_path.write_bytes(b"fake video data" * 1024 * 100)

            mock_cli.side_effect = create_fake_video

            # Call generate_videos
            result = await service.generate_videos(
                manifest, resume=True, max_concurrent=2, task_id=str(task.id), db=async_session
            )

    # Verify: clip 1 regenerated (not skipped) because file was missing
    assert result["generated"] == 1
    assert result["skipped"] == 0
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_partial_resume_clips_1_to_10_complete(async_session, tmp_path):
    """Verify resume from clip 11 when clips 1-10 complete (Subtask 3.5)."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with clips 1-10 completed in checkpoint
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_VIDEO,
        completed_steps=[],
        step_metadata={"completed_video_clips": list(range(1, 11))},  # Clips 1-10
    )
    async_session.add(task)
    await async_session.commit()

    # Create video generation service
    service = VideoGenerationService("test_ch", str(task.id))

    # Create video directory with files for clips 1-10
    video_dir = tmp_path / "videos"
    video_dir.mkdir(parents=True)
    for i in range(1, 11):
        video_file = video_dir / f"clip_{i:02d}.mp4"
        video_file.write_bytes(b"fake video data" * 1024 * 100)

    # Create mock manifest with 18 clips
    clips = []
    for i in range(1, 19):
        clip = VideoClip(
            clip_number=i,
            composite_path=tmp_path / f"composite_{i:02d}.png",
            motion_prompt=f"Motion prompt {i}",
            output_path=video_dir / f"clip_{i:02d}.mp4",
        )
        clips.append(clip)

    manifest = VideoManifest(clips=clips)

    # Mock the upload and CLI script calls
    with patch.object(service, "upload_to_catbox", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = "https://catbox.moe/fake.png"

        with patch(
            "app.services.video_generation.run_cli_script", new_callable=AsyncMock
        ) as mock_cli:
            # Create fake video files for clips 11-18
            async def create_fake_video(*args, **kwargs):
                output_arg_index = args[1].index("--output")
                output_path = Path(args[1][output_arg_index + 1])
                output_path.write_bytes(b"fake video data" * 1024 * 100)

            mock_cli.side_effect = create_fake_video

            # Call generate_videos
            result = await service.generate_videos(
                manifest, resume=True, max_concurrent=5, task_id=str(task.id), db=async_session
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
    assert set(result_task.step_metadata["completed_video_clips"]) == set(range(1, 19))
