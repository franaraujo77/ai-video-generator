"""Tests for SFX generation sub-step checkpointing (Story 6.3, Task 5).

Tests verify:
- SFX clips already in step_metadata are skipped
- New SFX clips update step_metadata after successful generation
- Safety check: if metadata says complete but file missing, regenerate
- Partial resume: SFX clips 1-10 complete, resume from clip 11
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.models import Channel, Task, TaskStatus
from app.services.sfx_generation import SFXGenerationService, SFXManifest, SFXClip


@pytest.mark.asyncio
async def test_skip_completed_sfx_clips_from_checkpoint(async_session, tmp_path):
    """Verify SFX clips in step_metadata are skipped (Subtask 5.2)."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with completed SFX clips 1-5 in step_metadata
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_SFX,
        completed_steps=[],
        step_metadata={"completed_sfx_clips": [1, 2, 3, 4, 5]},
    )
    async_session.add(task)
    await async_session.commit()

    # Create SFX generation service
    service = SFXGenerationService("test_ch", str(task.id))

    # Create mock SFX files for clips 1-5
    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir(parents=True)
    for i in range(1, 6):
        sfx_file = sfx_dir / f"sfx_{i:02d}.wav"
        sfx_file.write_bytes(b"fake audio data" * 1024 * 10)  # 100KB fake audio

    # Create mock manifest with 6 clips
    clips = []
    for i in range(1, 7):
        clip = SFXClip(
            clip_number=i,
            sfx_description=f"Environmental sound effect {i}",
            output_path=sfx_dir / f"sfx_{i:02d}.wav",
        )
        clips.append(clip)

    manifest = SFXManifest(clips=clips)

    # Mock the CLI script call - need to create file for validation
    async def create_sfx_file(*args, **kwargs):
        output_file = sfx_dir / "sfx_06.wav"
        output_file.write_bytes(b"generated audio")
        return {"success": True, "output_path": str(output_file)}

    # Mock async_session_factory for checkpoint service
    mock_db = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock()

    with patch("app.services.sfx_generation.run_cli_script", new_callable=AsyncMock) as mock_cli:
        with patch("app.database.async_session_factory", return_value=mock_session_ctx):
            mock_cli.side_effect = create_sfx_file

            # Call generate_sfx with resume=True
            result = await service.generate_sfx(
                manifest,
                resume=True,
                max_concurrent=2,
                task_id=str(task.id),
                db=async_session,
            )

    # Verify only clip 6 was generated (clips 1-5 skipped from checkpoint)
    assert result["skipped"] == 5
    assert result["generated"] == 1
    assert result["total"] == 6

    # Verify CLI script only called once (for clip 6)
    assert mock_cli.call_count == 1


@pytest.mark.asyncio
async def test_update_checkpoint_after_sfx_clip_generation(async_session, tmp_path):
    """Verify step_metadata updated after each SFX clip generation (Subtask 5.3)."""
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with no checkpoints
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_SFX,
        completed_steps=[],
        step_metadata={},
    )
    async_session.add(task)
    await async_session.commit()

    service = SFXGenerationService("test_ch", str(task.id))

    # Create mock SFX directory
    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir(parents=True)

    # Create manifest with 2 clips
    clips = [
        SFXClip(
            clip_number=1,
            sfx_description="Wind through trees",
            output_path=sfx_dir / "sfx_01.wav",
        ),
        SFXClip(
            clip_number=2,
            sfx_description="Water flowing",
            output_path=sfx_dir / "sfx_02.wav",
        ),
    ]
    manifest = SFXManifest(clips=clips)

    # Mock CLI script to create files
    async def mock_cli_side_effect(*args, **kwargs):
        # Extract output path from args: args[1] is the argument list
        arg_list = args[1]
        output_index = arg_list.index("--output") + 1
        output_path = Path(arg_list[output_index])
        output_path.write_bytes(b"fake audio")

    # Mock async_session_factory for checkpoint service
    mock_db = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock()

    with patch("app.services.sfx_generation.run_cli_script", new_callable=AsyncMock) as mock_cli:
        with patch("app.database.async_session_factory", return_value=mock_session_ctx):
            mock_cli.side_effect = mock_cli_side_effect

            # Generate SFX clips
            result = await service.generate_sfx(
                manifest,
                resume=True,
                max_concurrent=1,  # Sequential for deterministic testing
                task_id=str(task.id),
                db=async_session,
            )

    # Verify both clips generated
    assert result["generated"] == 2
    assert result["skipped"] == 0

    # Verify step_metadata updated with both clip numbers
    await async_session.refresh(task)
    assert "completed_sfx_clips" in task.step_metadata
    assert set(task.step_metadata["completed_sfx_clips"]) == {1, 2}


@pytest.mark.asyncio
async def test_safety_check_regenerate_if_sfx_file_missing(async_session, tmp_path):
    """Verify SFX clip regenerated if checkpoint says complete but file missing (Subtask 5.4)."""
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with checkpoint saying clip 1 complete
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_SFX,
        completed_steps=[],
        step_metadata={"completed_sfx_clips": [1]},  # Checkpoint says clip 1 done
    )
    async_session.add(task)
    await async_session.commit()

    service = SFXGenerationService("test_ch", str(task.id))

    # Create SFX directory but DON'T create clip 1 file (simulating file loss)
    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir(parents=True)

    clip = SFXClip(
        clip_number=1,
        sfx_description="Thunder rumble",
        output_path=sfx_dir / "sfx_01.wav",
    )
    manifest = SFXManifest(clips=[clip])

    # Mock CLI to regenerate the file
    def mock_cli_side_effect(*args, **kwargs):
        output = sfx_dir / "sfx_01.wav"
        output.write_bytes(b"regenerated audio")
        return {"success": True, "output_path": str(output)}

    # Mock async_session_factory for checkpoint service
    mock_db = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock()

    with patch("app.services.sfx_generation.run_cli_script", new_callable=AsyncMock) as mock_cli:
        with patch("app.database.async_session_factory", return_value=mock_session_ctx):
            mock_cli.side_effect = mock_cli_side_effect

            result = await service.generate_sfx(
                manifest,
                resume=True,
                task_id=str(task.id),
                db=async_session,
            )

    # Verify clip was regenerated despite checkpoint (file was missing)
    assert result["generated"] == 1
    assert result["skipped"] == 0
    assert mock_cli.call_count == 1


@pytest.mark.asyncio
async def test_partial_resume_sfx_clips_1_to_10_complete(async_session, tmp_path):
    """Test partial resume: SFX clips 1-10 complete, clip 11 fails, retry resumes at 11 (Subtask 10.4)."""
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with clips 1-10 complete in checkpoint
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_SFX,
        completed_steps=[],
        step_metadata={"completed_sfx_clips": list(range(1, 11))},  # 1-10 complete
    )
    async_session.add(task)
    await async_session.commit()

    service = SFXGenerationService("test_ch", str(task.id))

    # Create mock files for clips 1-10
    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir(parents=True)
    for i in range(1, 11):
        sfx_file = sfx_dir / f"sfx_{i:02d}.wav"
        sfx_file.write_bytes(b"existing audio")

    # Create manifest for clips 1-12
    clips = []
    for i in range(1, 13):
        clip = SFXClip(
            clip_number=i,
            sfx_description=f"SFX effect {i}",
            output_path=sfx_dir / f"sfx_{i:02d}.wav",
        )
        clips.append(clip)

    manifest = SFXManifest(clips=clips)

    # Mock CLI to generate clips 11-12
    call_count = 0

    def mock_cli_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        clip_num = call_count + 10  # First call is clip 11, second is clip 12
        output = sfx_dir / f"sfx_{clip_num:02d}.wav"
        output.write_bytes(b"new audio")
        return {"success": True, "output_path": str(output)}

    # Mock async_session_factory for checkpoint service
    mock_db = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock()

    with patch("app.services.sfx_generation.run_cli_script", new_callable=AsyncMock) as mock_cli:
        with patch("app.database.async_session_factory", return_value=mock_session_ctx):
            mock_cli.side_effect = mock_cli_side_effect

            result = await service.generate_sfx(
                manifest,
                resume=True,
                max_concurrent=1,
                task_id=str(task.id),
                db=async_session,
            )

    # Verify only clips 11-12 generated (1-10 skipped from checkpoint)
    assert result["skipped"] == 10
    assert result["generated"] == 2
    assert result["total"] == 12
    assert mock_cli.call_count == 2

    # Verify checkpoint updated with clips 11-12
    await async_session.refresh(task)
    assert set(task.step_metadata["completed_sfx_clips"]) == set(range(1, 13))


@pytest.mark.asyncio
async def test_narration_complete_sfx_fails_retry_only_sfx(async_session, tmp_path):
    """Test narration succeeds but SFX fails, retry only runs SFX (Subtask 10.4)."""
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with narration complete (all 18 clips)
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_SFX,
        completed_steps=[
            {
                "step_name": "narration_generation",
                "completed_at": "2026-01-18T10:00:00Z",
                "outputs": {"total_clips": 18, "clips_generated": 18},
            }
        ],
        step_metadata={
            "completed_narration_clips": list(range(1, 19)),  # All narration done
            "completed_sfx_clips": [1, 2, 3],  # Only 3 SFX clips done before failure
        },
    )
    async_session.add(task)
    await async_session.commit()

    service = SFXGenerationService("test_ch", str(task.id))

    # Create mock SFX files for clips 1-3
    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir(parents=True)
    for i in range(1, 4):
        sfx_file = sfx_dir / f"sfx_{i:02d}.wav"
        sfx_file.write_bytes(b"existing sfx")

    # Create manifest for 6 SFX clips
    clips = []
    for i in range(1, 7):
        clip = SFXClip(
            clip_number=i,
            sfx_description=f"SFX {i}",
            output_path=sfx_dir / f"sfx_{i:02d}.wav",
        )
        clips.append(clip)

    manifest = SFXManifest(clips=clips)

    # Mock CLI to generate clips 4-6
    call_count = 0

    def mock_cli_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        clip_num = call_count + 3  # First call is clip 4
        output = sfx_dir / f"sfx_{clip_num:02d}.wav"
        output.write_bytes(b"new sfx")
        return {"success": True, "output_path": str(output)}

    # Mock async_session_factory for checkpoint service
    mock_db = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_ctx.__aexit__ = AsyncMock()

    with patch("app.services.sfx_generation.run_cli_script", new_callable=AsyncMock) as mock_cli:
        with patch("app.database.async_session_factory", return_value=mock_session_ctx):
            mock_cli.side_effect = mock_cli_side_effect

            result = await service.generate_sfx(
                manifest,
                resume=True,
                max_concurrent=1,
                task_id=str(task.id),
                db=async_session,
            )

    # Verify only clips 4-6 generated (1-3 skipped, narration not regenerated)
    assert result["skipped"] == 3
    assert result["generated"] == 3
    assert result["total"] == 6

    # Verify narration checkpoint still intact
    await async_session.refresh(task)
    assert len(task.completed_steps) == 1
    assert task.completed_steps[0]["step_name"] == "narration_generation"
    assert task.step_metadata["completed_narration_clips"] == list(range(1, 19))
