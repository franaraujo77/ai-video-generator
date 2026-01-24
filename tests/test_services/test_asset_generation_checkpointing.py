"""Tests for asset generation sub-step checkpointing (Story 6.3, Task 4).

Tests verify:
- Assets already in step_metadata are skipped
- New assets update step_metadata after successful generation
- Safety check: if metadata says complete but file missing, regenerate
- Partial resume: assets 1-10 complete, resume from asset 11
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.models import Channel, Task, TaskStatus
from app.services.asset_generation import (
    AssetGenerationService,
    AssetManifest,
    AssetPrompt,
)


@pytest.mark.asyncio
async def test_skip_completed_assets_from_checkpoint(async_session, tmp_path):
    """Verify assets in step_metadata are skipped (Subtask 4.2)."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with completed assets 1-5 in step_metadata
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_ASSETS,
        completed_steps=[],
        step_metadata={
            "completed_assets": [
                "asset_char_1",
                "asset_char_2",
                "asset_env_1",
                "asset_env_2",
                "asset_prop_1",
            ]
        },
    )
    async_session.add(task)
    await async_session.commit()

    # Create asset generation service
    service = AssetGenerationService("test_ch", str(task.id))

    # Create mock asset files for assets 1-5
    char_dir = tmp_path / "characters"
    env_dir = tmp_path / "environments"
    props_dir = tmp_path / "props"
    char_dir.mkdir(parents=True)
    env_dir.mkdir(parents=True)
    props_dir.mkdir(parents=True)

    # Create existing files
    (char_dir / "asset_char_1.png").write_bytes(b"fake image data" * 100)
    (char_dir / "asset_char_2.png").write_bytes(b"fake image data" * 100)
    (env_dir / "asset_env_1.png").write_bytes(b"fake image data" * 100)
    (env_dir / "asset_env_2.png").write_bytes(b"fake image data" * 100)
    (props_dir / "asset_prop_1.png").write_bytes(b"fake image data" * 100)

    # Create mock manifest with 6 assets
    assets = [
        AssetPrompt(
            asset_type="character",
            name="asset_char_1",
            prompt="Character 1",
            output_path=char_dir / "asset_char_1.png",
        ),
        AssetPrompt(
            asset_type="character",
            name="asset_char_2",
            prompt="Character 2",
            output_path=char_dir / "asset_char_2.png",
        ),
        AssetPrompt(
            asset_type="environment",
            name="asset_env_1",
            prompt="Environment 1",
            output_path=env_dir / "asset_env_1.png",
        ),
        AssetPrompt(
            asset_type="environment",
            name="asset_env_2",
            prompt="Environment 2",
            output_path=env_dir / "asset_env_2.png",
        ),
        AssetPrompt(
            asset_type="prop",
            name="asset_prop_1",
            prompt="Prop 1",
            output_path=props_dir / "asset_prop_1.png",
        ),
        AssetPrompt(
            asset_type="prop",
            name="asset_prop_2",
            prompt="Prop 2",
            output_path=props_dir / "asset_prop_2.png",
        ),
    ]

    manifest = AssetManifest(global_atmosphere="Test atmosphere", assets=assets)

    # Mock the CLI script calls
    with patch("app.services.asset_generation.run_cli_script", new_callable=AsyncMock) as mock_cli:
        # Create fake asset file after "generation"
        async def create_fake_asset(*args, **kwargs):
            output_arg_index = args[1].index("--output")
            output_path = Path(args[1][output_arg_index + 1])
            output_path.write_bytes(b"fake image data" * 100)

        mock_cli.side_effect = create_fake_asset

        # Call generate_assets with resume=True
        result = await service.generate_assets(
            manifest, resume=True, task_id=str(task.id), db=async_session
        )

    # Verify: assets 1-5 skipped, asset 6 generated
    assert result["skipped"] == 5
    assert result["generated"] == 1
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_update_checkpoint_after_asset_generation(async_session, tmp_path):
    """Verify step_metadata updated after successful generation (Subtask 4.3)."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with no completed assets
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_ASSETS,
        completed_steps=[],
        step_metadata={"completed_assets": []},
    )
    async_session.add(task)
    await async_session.commit()

    # Create asset generation service
    service = AssetGenerationService("test_ch", str(task.id))

    # Create asset directories
    char_dir = tmp_path / "characters"
    env_dir = tmp_path / "environments"
    char_dir.mkdir(parents=True)
    env_dir.mkdir(parents=True)

    # Create mock manifest with 3 assets
    assets = [
        AssetPrompt(
            asset_type="character",
            name="asset_char_1",
            prompt="Character 1",
            output_path=char_dir / "asset_char_1.png",
        ),
        AssetPrompt(
            asset_type="character",
            name="asset_char_2",
            prompt="Character 2",
            output_path=char_dir / "asset_char_2.png",
        ),
        AssetPrompt(
            asset_type="environment",
            name="asset_env_1",
            prompt="Environment 1",
            output_path=env_dir / "asset_env_1.png",
        ),
    ]

    manifest = AssetManifest(global_atmosphere="Test atmosphere", assets=assets)

    # Mock the CLI script calls
    with patch("app.services.asset_generation.run_cli_script", new_callable=AsyncMock) as mock_cli:
        # Create fake asset file after "generation"
        async def create_fake_asset(*args, **kwargs):
            output_arg_index = args[1].index("--output")
            output_path = Path(args[1][output_arg_index + 1])
            output_path.write_bytes(b"fake image data" * 100)

        mock_cli.side_effect = create_fake_asset

        # Call generate_assets
        result = await service.generate_assets(
            manifest, resume=True, task_id=str(task.id), db=async_session
        )

    # Verify all 3 assets generated
    assert result["generated"] == 3
    assert result["skipped"] == 0
    assert result["failed"] == 0

    # Verify step_metadata updated with completed asset names
    # Query task fresh from database to see checkpoint updates
    from sqlalchemy import select
    from app.models import Task as TaskModel

    stmt = select(TaskModel).where(TaskModel.id == task.id)
    result_task = (await async_session.execute(stmt)).scalar_one()
    assert result_task.step_metadata["completed_assets"] == [
        "asset_char_1",
        "asset_char_2",
        "asset_env_1",
    ]


@pytest.mark.asyncio
async def test_safety_check_regenerate_if_file_missing(async_session, tmp_path):
    """Verify asset regenerated if checkpoint exists but file missing (Subtask 4.4)."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with asset in checkpoint but file will be missing
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_ASSETS,
        completed_steps=[],
        step_metadata={"completed_assets": ["asset_char_1"]},  # Checkpoint says asset 1 done
    )
    async_session.add(task)
    await async_session.commit()

    # Create asset generation service
    service = AssetGenerationService("test_ch", str(task.id))

    # Create asset directory but NO asset file
    char_dir = tmp_path / "characters"
    char_dir.mkdir(parents=True)

    # Create mock manifest with asset 1
    asset = AssetPrompt(
        asset_type="character",
        name="asset_char_1",
        prompt="Character 1",
        output_path=char_dir / "asset_char_1.png",
    )
    manifest = AssetManifest(global_atmosphere="Test atmosphere", assets=[asset])

    # Mock the CLI script calls
    with patch("app.services.asset_generation.run_cli_script", new_callable=AsyncMock) as mock_cli:
        # Create fake asset file after "generation"
        async def create_fake_asset(*args, **kwargs):
            output_arg_index = args[1].index("--output")
            output_path = Path(args[1][output_arg_index + 1])
            output_path.write_bytes(b"fake image data" * 100)

        mock_cli.side_effect = create_fake_asset

        # Call generate_assets
        result = await service.generate_assets(
            manifest, resume=True, task_id=str(task.id), db=async_session
        )

    # Verify: asset 1 regenerated (not skipped) because file was missing
    assert result["generated"] == 1
    assert result["skipped"] == 0
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_partial_resume_assets_1_to_10_complete(async_session, tmp_path):
    """Verify resume from asset 11 when assets 1-10 complete (Subtask 4.5)."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with assets 1-10 completed in checkpoint
    completed_names = [f"asset_{i}" for i in range(1, 11)]
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_ASSETS,
        completed_steps=[],
        step_metadata={"completed_assets": completed_names},
    )
    async_session.add(task)
    await async_session.commit()

    # Create asset generation service
    service = AssetGenerationService("test_ch", str(task.id))

    # Create asset directory with files for assets 1-10
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir(parents=True)
    for i in range(1, 11):
        (asset_dir / f"asset_{i}.png").write_bytes(b"fake image data" * 100)

    # Create mock manifest with 15 assets
    assets = []
    for i in range(1, 16):
        assets.append(
            AssetPrompt(
                asset_type="character",
                name=f"asset_{i}",
                prompt=f"Asset {i}",
                output_path=asset_dir / f"asset_{i}.png",
            )
        )

    manifest = AssetManifest(global_atmosphere="Test atmosphere", assets=assets)

    # Mock the CLI script calls
    with patch("app.services.asset_generation.run_cli_script", new_callable=AsyncMock) as mock_cli:
        # Create fake asset files for assets 11-15
        async def create_fake_asset(*args, **kwargs):
            output_arg_index = args[1].index("--output")
            output_path = Path(args[1][output_arg_index + 1])
            output_path.write_bytes(b"fake image data" * 100)

        mock_cli.side_effect = create_fake_asset

        # Call generate_assets
        result = await service.generate_assets(
            manifest, resume=True, task_id=str(task.id), db=async_session
        )

    # Verify: assets 1-10 skipped, assets 11-15 generated
    assert result["skipped"] == 10
    assert result["generated"] == 5
    assert result["failed"] == 0

    # Verify step_metadata updated with all 15 assets
    # Query task fresh from database to see checkpoint updates
    from sqlalchemy import select
    from app.models import Task as TaskModel

    stmt = select(TaskModel).where(TaskModel.id == task.id)
    result_task = (await async_session.execute(stmt)).scalar_one()
    assert set(result_task.step_metadata["completed_assets"]) == set(
        [f"asset_{i}" for i in range(1, 16)]
    )
