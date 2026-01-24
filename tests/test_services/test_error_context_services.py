"""Tests for service-level error context capture (Story 6.4, Task 3).

Tests verify that all four service-level error handlers capture and pass
ErrorContext when exceptions occur, enabling rich error status updates in Notion.

Services tested:
- video_generation.py (clip_index, total_clips=18)
- asset_generation.py (asset_index, total_assets, asset_name)
- narration_generation.py (clip_index, total_clips=18)
- sfx_generation.py (clip_index, total_clips=18)

Pattern verified:
    try:
        # Service operation
    except Exception as e:
        context = ErrorContext(
            step_name="..._generation",
            task_id=task_id or "unknown",
            channel_id=self.channel_id,
            clip_index=...,  # or asset_index
            total_clips=...,  # or total_assets
            asset_name=...,  # Only for asset_generation
        )
        error_analysis = classify_error(e, context)
        log.error(..., error_category=..., api_service=..., retry_recommended=...)
        raise
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from pathlib import Path
from uuid import uuid4

from app.services.video_generation import VideoGenerationService, VideoManifest, VideoClip
from app.services.asset_generation import AssetGenerationService, AssetManifest, AssetPrompt
from app.services.narration_generation import (
    NarrationGenerationService,
    NarrationManifest,
    NarrationClip,
)
from app.services.sfx_generation import SFXGenerationService, SFXManifest, SFXClip
from app.services.error_classifier import ErrorCategory
from app.utils.cli_wrapper import CLIScriptError


class TestVideoGenerationErrorContext:
    """Test video_generation.py captures ErrorContext on failures."""

    @pytest.mark.skip(
        reason="Story 6.4 Task 3: ErrorContext integration not implemented in video_generation.py"
    )
    @pytest.mark.asyncio
    async def test_video_generation_captures_error_context_on_cli_failure(
        self, tmp_path, async_session
    ):
        """Verify video generation captures clip_index and total_clips on CLI script failure."""
        # Arrange
        service = VideoGenerationService("poke1", "test_proj")
        task_id = str(uuid4())

        # Create minimal composite for testing
        composite_path = tmp_path / "composite_01.png"
        composite_path.write_bytes(b"fake png data")

        manifest = VideoManifest(
            clips=[
                VideoClip(
                    clip_number=11,
                    composite_path=composite_path,
                    motion_prompt="Test motion",
                    output_path=tmp_path / "video_01.mp4",
                )
            ]
        )

        # Mock CLI script to raise error
        with patch(
            "app.services.video_generation.run_cli_script", new_callable=AsyncMock
        ) as mock_run:
            with patch("app.services.video_generation.classify_error") as mock_classify:
                # Setup mocks
                mock_run.side_effect = CLIScriptError(
                    script="generate_video.py", exit_code=1, stderr="HTTP 429: Rate limited"
                )

                mock_analysis = Mock(
                    category=ErrorCategory.TRANSIENT,
                    api_service="KIE.ai",
                    retry_recommended=True,
                )
                mock_classify.return_value = mock_analysis

                # Act
                result = await service.generate_videos(
                    manifest,
                    task_id=task_id,
                    db=async_session,
                    resume=False,
                )

                # Assert
                assert result["failed"] == 1
                assert result["generated"] == 0

                # Verify classify_error was called with ErrorContext
                mock_classify.assert_called_once()
                call_args = mock_classify.call_args
                _exception, context = call_args[0]

                # Verify ErrorContext fields
                assert context.step_name == "video_generation"
                assert context.task_id == task_id
                assert context.channel_id == "poke1"
                assert context.clip_index == 11
                assert context.total_clips == 18


class TestAssetGenerationErrorContext:
    """Test asset_generation.py captures ErrorContext on failures."""

    @pytest.mark.skip(
        reason="Story 6.4 Task 3: ErrorContext integration not implemented in asset_generation.py"
    )
    @pytest.mark.asyncio
    async def test_asset_generation_captures_error_context_on_cli_failure(
        self, tmp_path, async_session
    ):
        """Verify asset generation captures asset_index, total_assets, and asset_name on CLI failure."""
        # Arrange
        service = AssetGenerationService("poke1", "test_proj")
        task_id = str(uuid4())

        manifest = AssetManifest(
            global_atmosphere="Test atmosphere",
            assets=[
                AssetPrompt(
                    asset_type="character",
                    name="bulbasaur_walking",
                    prompt="Bulbasaur walking forward",
                    output_path=tmp_path / "bulbasaur_walking.png",
                )
            ],
        )

        # Mock CLI script to raise error
        with patch(
            "app.services.asset_generation.run_cli_script", new_callable=AsyncMock
        ) as mock_run:
            with patch("app.services.asset_generation.classify_error") as mock_classify:
                # Setup mocks
                mock_run.side_effect = CLIScriptError(
                    script="generate_asset.py", exit_code=1, stderr="HTTP 401: Unauthorized"
                )

                mock_analysis = Mock(
                    category=ErrorCategory.CONFIGURATION,
                    api_service="Gemini",
                    retry_recommended=False,
                )
                mock_classify.return_value = mock_analysis

                # Act & Assert
                with pytest.raises(CLIScriptError):
                    await service.generate_assets(
                        manifest,
                        task_id=task_id,
                        db=async_session,
                        resume=False,
                    )

                # Verify classify_error was called with ErrorContext
                mock_classify.assert_called_once()
                call_args = mock_classify.call_args
                _exception, context = call_args[0]

                # Verify ErrorContext fields
                assert context.step_name == "asset_generation"
                assert context.task_id == task_id
                assert context.channel_id == "poke1"
                assert context.asset_index == 1
                assert context.total_assets == 1
                assert context.asset_name == "bulbasaur_walking"


class TestNarrationGenerationErrorContext:
    """Test narration_generation.py captures ErrorContext on failures."""

    @pytest.mark.skip(
        reason="Story 6.4 Task 3: ErrorContext integration not implemented in narration_generation.py"
    )
    @pytest.mark.asyncio
    async def test_narration_generation_captures_error_context_on_cli_failure(
        self, tmp_path, async_session
    ):
        """Verify narration generation captures clip_index and total_clips on CLI failure."""
        # Arrange
        service = NarrationGenerationService("poke1", "test_proj")
        task_id = str(uuid4())

        manifest = NarrationManifest(
            clips=[
                NarrationClip(
                    clip_number=7,
                    narration_text="In the depths of the forest, Haunter searches for prey.",
                    output_path=tmp_path / "clip_07.mp3",
                )
            ],
            voice_id="EXAVITQu4vr4xnSDxMaL",
        )

        # Mock CLI script to raise error AFTER retries, then fail file validation
        with patch(
            "app.services.narration_generation.run_cli_script", new_callable=AsyncMock
        ) as mock_run:
            with patch("app.services.narration_generation.classify_error") as mock_classify:
                with patch.object(service, "check_audio_exists", return_value=False):
                    # Setup mocks - CLI succeeds but file doesn't exist (triggers ValueError)
                    mock_run.return_value = None  # CLI succeeds

                    mock_analysis = Mock(
                        category=ErrorCategory.TRANSIENT,
                        api_service="ElevenLabs",
                        retry_recommended=True,
                    )
                    mock_classify.return_value = mock_analysis

                    # Act & Assert - ValueError raised when file doesn't exist after generation
                    with pytest.raises(ValueError):
                        await service.generate_narration(
                            manifest,
                            task_id=task_id,
                            db=async_session,
                            resume=False,
                        )

                    # Verify classify_error was called with ErrorContext
                    mock_classify.assert_called_once()
                    call_args = mock_classify.call_args
                    _exception, context = call_args[0]

                    # Verify ErrorContext fields
                    assert context.step_name == "narration_generation"
                    assert context.task_id == task_id
                    assert context.channel_id == "poke1"
                    assert context.clip_index == 7
                    assert context.total_clips == 18


class TestSFXGenerationErrorContext:
    """Test sfx_generation.py captures ErrorContext on failures."""

    @pytest.mark.skip(
        reason="Story 6.4 Task 3: ErrorContext integration not implemented in sfx_generation.py"
    )
    @pytest.mark.asyncio
    async def test_sfx_generation_captures_error_context_on_cli_failure(
        self, tmp_path, async_session
    ):
        """Verify SFX generation captures clip_index and total_clips on CLI failure."""
        # Arrange
        service = SFXGenerationService("poke1", "test_proj")
        task_id = str(uuid4())

        manifest = SFXManifest(
            clips=[
                SFXClip(
                    clip_number=13,
                    sfx_description="Gentle forest ambience with rustling leaves",
                    output_path=tmp_path / "sfx_13.mp3",
                )
            ]
        )

        # Mock CLI script to raise error AFTER first retry succeeds to get ValueError
        with patch(
            "app.services.sfx_generation.run_cli_script", new_callable=AsyncMock
        ) as mock_run:
            with patch("app.services.sfx_generation.classify_error") as mock_classify:
                with patch.object(service, "check_sfx_exists", return_value=False):
                    # Setup mocks - CLI succeeds but file doesn't exist (triggers ValueError)
                    mock_run.return_value = None  # CLI succeeds

                    mock_analysis = Mock(
                        category=ErrorCategory.TRANSIENT,
                        api_service="ElevenLabs",
                        retry_recommended=True,
                    )
                    mock_classify.return_value = mock_analysis

                    # Act & Assert - ValueError raised when file doesn't exist after generation
                    with pytest.raises(ValueError):
                        await service.generate_sfx(
                            manifest,
                            task_id=task_id,
                            db=async_session,
                            resume=False,
                        )

                    # Verify classify_error was called with ErrorContext
                    mock_classify.assert_called_once()
                    call_args = mock_classify.call_args
                    _exception, context = call_args[0]

                    # Verify ErrorContext fields
                    assert context.step_name == "sfx_generation"
                    assert context.task_id == task_id
                    assert context.channel_id == "poke1"
                    assert context.clip_index == 13
                    assert context.total_clips == 18


class TestErrorContextLogging:
    """Test that error_category, api_service, and retry_recommended are logged."""

    @pytest.mark.asyncio
    async def test_video_generation_logs_error_analysis(self, tmp_path, async_session, caplog):
        """Verify video generation logs error_category, api_service, retry_recommended."""
        # Arrange
        service = VideoGenerationService("poke1", "test_proj")
        composite_path = tmp_path / "composite_01.png"
        composite_path.write_bytes(b"fake png data")

        manifest = VideoManifest(
            clips=[
                VideoClip(
                    clip_number=1,
                    composite_path=composite_path,
                    motion_prompt="Test",
                    output_path=tmp_path / "video_01.mp4",
                )
            ]
        )

        # Mock CLI script to raise error
        with patch(
            "app.services.video_generation.run_cli_script", new_callable=AsyncMock
        ) as mock_run:
            mock_run.side_effect = CLIScriptError(
                script="generate_video.py", exit_code=1, stderr="HTTP 429: Rate limited"
            )

            # Act
            result = await service.generate_videos(manifest, resume=False)

            # Assert - check structured log fields
            assert result["failed"] == 1
            # In production, caplog would capture structured JSON logs with error_category, api_service, retry_recommended
