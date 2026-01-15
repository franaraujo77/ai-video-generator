"""Tests for Composite Creation Service.

This module tests the CompositeCreationService class which orchestrates
composite image creation from character + environment assets.

Test Coverage:
- Composite manifest creation (18 scenes with standard + split-screen)
- Composite generation orchestration (CLI script invocation)
- Partial resume functionality (skip existing composites)
- Split-screen composite creation (inline PIL composition)
- Error handling (CLIScriptError, timeout, FileNotFoundError)
- Dimension verification (1920x1080 enforcement)
- Security (path traversal, validation)

Architecture Compliance:
- Uses Story 3.1 CLI wrapper (never subprocess directly)
- Uses Story 3.2 filesystem helpers (never manual paths)
- Mocks CLI script to avoid actual PIL operations
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from PIL import Image

from app.services.composite_creation import (
    CompositeCreationService,
    CompositeManifest,
    SceneComposite,
)
from app.utils.cli_wrapper import CLIScriptError


class TestSceneCompositeDataclass:
    """Test SceneComposite dataclass."""

    def test_scene_composite_creation_standard(self, tmp_path: Path):
        """Test creating standard SceneComposite with required fields."""
        char_path = tmp_path / "char.png"
        env_path = tmp_path / "env.png"
        output_path = tmp_path / "clip_01.png"

        composite = SceneComposite(
            clip_number=1,
            character_path=char_path,
            environment_path=env_path,
            output_path=output_path,
            is_split_screen=False,
            character_scale=1.0
        )

        assert composite.clip_number == 1
        assert composite.character_path == char_path
        assert composite.environment_path == env_path
        assert composite.output_path == output_path
        assert composite.is_split_screen is False
        assert composite.character_b_path is None
        assert composite.environment_b_path is None
        assert composite.character_scale == 1.0

    def test_scene_composite_creation_split_screen(self, tmp_path: Path):
        """Test creating split-screen SceneComposite with all fields."""
        char_a_path = tmp_path / "char_a.png"
        env_a_path = tmp_path / "env_a.png"
        char_b_path = tmp_path / "char_b.png"
        env_b_path = tmp_path / "env_b.png"
        output_path = tmp_path / "clip_15_split.png"

        composite = SceneComposite(
            clip_number=15,
            character_path=char_a_path,
            environment_path=env_a_path,
            output_path=output_path,
            is_split_screen=True,
            character_b_path=char_b_path,
            environment_b_path=env_b_path,
            character_scale=1.0
        )

        assert composite.clip_number == 15
        assert composite.is_split_screen is True
        assert composite.character_b_path == char_b_path
        assert composite.environment_b_path == env_b_path


class TestCompositeManifestDataclass:
    """Test CompositeManifest dataclass."""

    def test_composite_manifest_creation(self, tmp_path: Path):
        """Test creating CompositeManifest with composites list."""
        composite1 = SceneComposite(
            clip_number=1,
            character_path=tmp_path / "char1.png",
            environment_path=tmp_path / "env1.png",
            output_path=tmp_path / "clip_01.png"
        )
        composite2 = SceneComposite(
            clip_number=2,
            character_path=tmp_path / "char2.png",
            environment_path=tmp_path / "env2.png",
            output_path=tmp_path / "clip_02.png"
        )

        manifest = CompositeManifest(composites=[composite1, composite2])

        assert len(manifest.composites) == 2
        assert manifest.composites[0].clip_number == 1
        assert manifest.composites[1].clip_number == 2


class TestCompositeCreationServiceInit:
    """Test CompositeCreationService initialization."""

    def test_service_initialization(self):
        """Test service initializes with channel_id and project_id."""
        service = CompositeCreationService("poke1", "vid_abc123")

        assert service.channel_id == "poke1"
        assert service.project_id == "vid_abc123"
        assert service.log is not None

    def test_service_initialization_invalid_channel_id(self):
        """Test service rejects invalid channel_id."""
        with pytest.raises(ValueError, match="channel_id contains invalid characters"):
            CompositeCreationService("../../../etc", "vid_abc123")

    def test_service_initialization_invalid_project_id(self):
        """Test service rejects invalid project_id."""
        with pytest.raises(ValueError, match="project_id contains invalid characters"):
            CompositeCreationService("poke1", "vid;rm -rf /")


class TestCreateCompositeManifest:
    """Test create_composite_manifest method."""

    @patch('app.services.composite_creation.get_composite_dir')
    @patch('app.services.composite_creation.get_environment_dir')
    @patch('app.services.composite_creation.get_character_dir')
    def test_create_manifest_generates_18_scenes(
        self,
        mock_char_dir,
        mock_env_dir,
        mock_composite_dir,
        tmp_path: Path
    ):
        """Test manifest contains exactly 18 SceneComposite objects."""
        # Setup mocked directories with assets
        char_dir = tmp_path / "characters"
        env_dir = tmp_path / "environments"
        composite_dir = tmp_path / "composites"
        char_dir.mkdir()
        env_dir.mkdir()
        composite_dir.mkdir()

        # Create 8 character assets
        for i in range(1, 9):
            (char_dir / f"char_{i}.png").touch()

        # Create 8 environment assets
        for i in range(1, 9):
            (env_dir / f"env_{i}.png").touch()

        mock_char_dir.return_value = char_dir
        mock_env_dir.return_value = env_dir
        mock_composite_dir.return_value = composite_dir

        service = CompositeCreationService("poke1", "vid_abc123")
        manifest = service.create_composite_manifest(
            "Bulbasaur forest documentary",
            "18-scene narrative showing evolution"
        )

        # Verify exactly 18 composites
        assert len(manifest.composites) == 18

        # Verify clip numbers are 1-18
        clip_numbers = [c.clip_number for c in manifest.composites]
        assert clip_numbers == list(range(1, 19))

    @patch('app.services.composite_creation.get_composite_dir')
    @patch('app.services.composite_creation.get_environment_dir')
    @patch('app.services.composite_creation.get_character_dir')
    def test_create_manifest_maps_assets_correctly(
        self,
        mock_char_dir,
        mock_env_dir,
        mock_composite_dir,
        tmp_path: Path
    ):
        """Test each clip maps to valid character and environment paths."""
        char_dir = tmp_path / "characters"
        env_dir = tmp_path / "environments"
        composite_dir = tmp_path / "composites"
        char_dir.mkdir()
        env_dir.mkdir()
        composite_dir.mkdir()

        # Create assets
        for i in range(1, 9):
            (char_dir / f"char_{i}.png").touch()
            (env_dir / f"env_{i}.png").touch()

        mock_char_dir.return_value = char_dir
        mock_env_dir.return_value = env_dir
        mock_composite_dir.return_value = composite_dir

        service = CompositeCreationService("poke1", "vid_abc123")
        manifest = service.create_composite_manifest("Topic", "Story")

        # Verify all composites have valid paths
        for composite in manifest.composites:
            assert composite.character_path.exists()
            assert composite.environment_path.exists()
            assert composite.character_path.parent == char_dir
            assert composite.environment_path.parent == env_dir
            assert composite.output_path.parent == composite_dir

    @patch('app.services.composite_creation.get_composite_dir')
    @patch('app.services.composite_creation.get_environment_dir')
    @patch('app.services.composite_creation.get_character_dir')
    def test_create_manifest_handles_split_screen_clip_15(
        self,
        mock_char_dir,
        mock_env_dir,
        mock_composite_dir,
        tmp_path: Path
    ):
        """Test clip 15 has is_split_screen=True with character_b and environment_b."""
        char_dir = tmp_path / "characters"
        env_dir = tmp_path / "environments"
        composite_dir = tmp_path / "composites"
        char_dir.mkdir()
        env_dir.mkdir()
        composite_dir.mkdir()

        for i in range(1, 9):
            (char_dir / f"char_{i}.png").touch()
            (env_dir / f"env_{i}.png").touch()

        mock_char_dir.return_value = char_dir
        mock_env_dir.return_value = env_dir
        mock_composite_dir.return_value = composite_dir

        service = CompositeCreationService("poke1", "vid_abc123")
        manifest = service.create_composite_manifest("Topic", "Story")

        # Find clip 15
        clip_15 = next(c for c in manifest.composites if c.clip_number == 15)

        # Verify split-screen properties
        assert clip_15.is_split_screen is True
        assert clip_15.character_b_path is not None
        assert clip_15.environment_b_path is not None
        assert clip_15.character_b_path.exists()
        assert clip_15.environment_b_path.exists()
        assert "split" in clip_15.output_path.name.lower()

        # Verify other clips are not split-screen
        other_clips = [c for c in manifest.composites if c.clip_number != 15]
        assert all(c.is_split_screen is False for c in other_clips)
        assert all(c.character_b_path is None for c in other_clips)
        assert all(c.environment_b_path is None for c in other_clips)

    @patch('app.services.composite_creation.get_composite_dir')
    @patch('app.services.composite_creation.get_environment_dir')
    @patch('app.services.composite_creation.get_character_dir')
    def test_create_manifest_missing_character_assets(
        self,
        mock_char_dir,
        mock_env_dir,
        mock_composite_dir,
        tmp_path: Path
    ):
        """Test manifest creation fails when no character assets exist."""
        char_dir = tmp_path / "characters"
        env_dir = tmp_path / "environments"
        char_dir.mkdir()
        env_dir.mkdir()

        # Create environments but NO characters
        for i in range(1, 9):
            (env_dir / f"env_{i}.png").touch()

        mock_char_dir.return_value = char_dir
        mock_env_dir.return_value = env_dir
        mock_composite_dir.return_value = tmp_path / "composites"

        service = CompositeCreationService("poke1", "vid_abc123")

        with pytest.raises(FileNotFoundError, match="No character assets found"):
            service.create_composite_manifest("Topic", "Story")

    @patch('app.services.composite_creation.get_composite_dir')
    @patch('app.services.composite_creation.get_environment_dir')
    @patch('app.services.composite_creation.get_character_dir')
    def test_create_manifest_missing_environment_assets(
        self,
        mock_char_dir,
        mock_env_dir,
        mock_composite_dir,
        tmp_path: Path
    ):
        """Test manifest creation fails when no environment assets exist."""
        char_dir = tmp_path / "characters"
        env_dir = tmp_path / "environments"
        char_dir.mkdir()
        env_dir.mkdir()

        # Create characters but NO environments
        for i in range(1, 9):
            (char_dir / f"char_{i}.png").touch()

        mock_char_dir.return_value = char_dir
        mock_env_dir.return_value = env_dir
        mock_composite_dir.return_value = tmp_path / "composites"

        service = CompositeCreationService("poke1", "vid_abc123")

        with pytest.raises(FileNotFoundError, match="No environment assets found"):
            service.create_composite_manifest("Topic", "Story")


class TestGenerateComposites:
    """Test generate_composites method."""

    @pytest.mark.asyncio
    @patch('app.services.composite_creation.run_cli_script')
    @patch('app.services.composite_creation.Image')
    async def test_generate_composites_success_all_18_composites(
        self,
        mock_image,
        mock_run_cli_script,
        tmp_path: Path
    ):
        """Test all 18 composites generated successfully."""
        # Create manifest with 18 composites
        composites = []
        for i in range(1, 19):
            if i == 15:
                output_path = tmp_path / f"clip_{i:02d}_split.png"
                # Split-screen composite needs character_b and environment_b
                composite = SceneComposite(
                    clip_number=i,
                    character_path=tmp_path / "char_a.png",
                    environment_path=tmp_path / "env_a.png",
                    output_path=output_path,
                    is_split_screen=True,
                    character_b_path=tmp_path / "char_b.png",
                    environment_b_path=tmp_path / "env_b.png"
                )
            else:
                output_path = tmp_path / f"clip_{i:02d}.png"
                composite = SceneComposite(
                    clip_number=i,
                    character_path=tmp_path / "char.png",
                    environment_path=tmp_path / "env.png",
                    output_path=output_path,
                    is_split_screen=False
                )
            composites.append(composite)

        manifest = CompositeManifest(composites=composites)

        # Mock CLI script success - make it create the output file
        async def mock_run_cli(script_name, args_list, **kwargs):
            # Extract output path from args_list
            if "--output" in args_list:
                output_idx = args_list.index("--output")
                output_path = Path(args_list[output_idx + 1])
                output_path.touch()  # Create the file
            return None

        mock_run_cli_script.side_effect = mock_run_cli

        # Mock PIL Image.open to simulate valid composites AND split-screen image loading
        mock_img = MagicMock()
        mock_img.size = (1920, 1080)  # Correct dimensions
        mock_img.convert.return_value = mock_img
        mock_img.resize.return_value = mock_img
        mock_img.copy.return_value = mock_img
        mock_img.paste = MagicMock()
        mock_img.split.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        mock_img.__enter__ = Mock(return_value=mock_img)
        mock_img.__exit__ = Mock(return_value=False)
        mock_image.open.return_value = mock_img
        mock_image.new.return_value = mock_img

        # Mock save to create files
        def mock_save(path, *args, **kwargs):
            Path(path).touch()

        mock_img.save = mock_save

        # Create dummy composite files (they get created after generation completes)
        service = CompositeCreationService("poke1", "vid_abc123")

        # Run generation
        result = await service.generate_composites(manifest, resume=False)

        # Verify results (17 standard + 1 split-screen = 18 total)
        assert result["generated"] == 18
        assert result["skipped"] == 0
        assert result["failed"] == 0

        # Verify CLI script called for standard composites (17 times, clip 15 uses inline PIL)
        assert mock_run_cli_script.call_count == 17

    @pytest.mark.asyncio
    @patch('app.services.composite_creation.run_cli_script')
    @patch('app.services.composite_creation.Image')
    async def test_generate_composites_with_partial_resume(
        self,
        mock_image,
        mock_run_cli_script,
        tmp_path: Path
    ):
        """Test partial resume skips existing composites."""
        # Create manifest with 18 composites
        composites = []
        for i in range(1, 19):
            if i == 15:
                # Split-screen composite needs character_b and environment_b
                output_path = tmp_path / f"clip_{i:02d}_split.png"
                composite = SceneComposite(
                    clip_number=i,
                    character_path=tmp_path / "char_a.png",
                    environment_path=tmp_path / "env_a.png",
                    output_path=output_path,
                    is_split_screen=True,
                    character_b_path=tmp_path / "char_b.png",
                    environment_b_path=tmp_path / "env_b.png"
                )
            else:
                output_path = tmp_path / f"clip_{i:02d}.png"
                composite = SceneComposite(
                    clip_number=i,
                    character_path=tmp_path / "char.png",
                    environment_path=tmp_path / "env.png",
                    output_path=output_path,
                    is_split_screen=False
                )
            composites.append(composite)

            # Simulate first 10 composites already exist
            if i <= 10:
                output_path.touch()

        manifest = CompositeManifest(composites=composites)

        # Mock CLI script success - make it create the output file
        async def mock_run_cli(script_name, args_list, **kwargs):
            # Extract output path from args_list
            if "--output" in args_list:
                output_idx = args_list.index("--output")
                output_path = Path(args_list[output_idx + 1])
                output_path.touch()  # Create the file
            return None

        mock_run_cli_script.side_effect = mock_run_cli

        # Mock PIL Image.open for validation and split-screen creation
        mock_img = MagicMock()
        mock_img.size = (1920, 1080)
        mock_img.convert.return_value = mock_img
        mock_img.resize.return_value = mock_img
        mock_img.copy.return_value = mock_img
        mock_img.paste = MagicMock()
        mock_img.split.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        mock_img.__enter__ = Mock(return_value=mock_img)
        mock_img.__exit__ = Mock(return_value=False)
        mock_image.open.return_value = mock_img
        mock_image.new.return_value = mock_img

        # Mock save to create files
        def mock_save(path, *args, **kwargs):
            Path(path).touch()

        mock_img.save = mock_save

        service = CompositeCreationService("poke1", "vid_abc123")

        # Run generation with resume=True
        result = await service.generate_composites(manifest, resume=True)

        # Verify only 8 composites generated (10 skipped)
        assert result["generated"] == 8
        assert result["skipped"] == 10
        assert result["failed"] == 0

    @pytest.mark.asyncio
    @patch('app.services.composite_creation.run_cli_script')
    async def test_generate_composites_failure_raises_cli_script_error(
        self,
        mock_run_cli_script,
        tmp_path: Path
    ):
        """Test CLI script error propagates with correct details."""
        composite = SceneComposite(
            clip_number=5,
            character_path=tmp_path / "char.png",
            environment_path=tmp_path / "env.png",
            output_path=tmp_path / "clip_05.png"
        )
        manifest = CompositeManifest(composites=[composite])

        # Mock CLI script failure
        mock_run_cli_script.side_effect = CLIScriptError(
            "create_composite.py",
            1,
            "FileNotFoundError: char.png not found"
        )

        service = CompositeCreationService("poke1", "vid_abc123")

        with pytest.raises(CLIScriptError) as exc_info:
            await service.generate_composites(manifest, resume=False)

        assert exc_info.value.script == "create_composite.py"
        assert exc_info.value.exit_code == 1
        assert "not found" in exc_info.value.stderr

    @pytest.mark.asyncio
    @patch('app.services.composite_creation.run_cli_script')
    @patch('app.services.composite_creation.Image')
    async def test_generate_composites_incorrect_dimensions(
        self,
        mock_image,
        mock_run_cli_script,
        tmp_path: Path
    ):
        """Test composite generation fails if dimensions are not 1920x1080."""
        composite = SceneComposite(
            clip_number=1,
            character_path=tmp_path / "char.png",
            environment_path=tmp_path / "env.png",
            output_path=tmp_path / "clip_01.png"
        )
        manifest = CompositeManifest(composites=[composite])

        # Mock CLI script success but wrong dimensions
        mock_run_cli_script.return_value = AsyncMock()

        # Mock PIL Image.open with WRONG dimensions
        mock_img = MagicMock()
        mock_img.size = (1280, 720)  # Wrong dimensions!
        mock_img.__enter__ = Mock(return_value=mock_img)
        mock_img.__exit__ = Mock(return_value=False)
        mock_image.open.return_value = mock_img

        # Create composite file
        composite.output_path.touch()

        service = CompositeCreationService("poke1", "vid_abc123")

        with pytest.raises(ValueError, match="incorrect dimensions"):
            await service.generate_composites(manifest, resume=False)


class TestCheckCompositeExists:
    """Test check_composite_exists method."""

    def test_composite_exists_returns_true_for_existing_file(self, tmp_path: Path):
        """Test returns True when composite file exists."""
        composite_path = tmp_path / "clip_01.png"
        composite_path.touch()

        service = CompositeCreationService("poke1", "vid_abc123")
        result = service.check_composite_exists(composite_path)

        assert result is True

    def test_composite_exists_returns_false_for_missing_file(self, tmp_path: Path):
        """Test returns False when composite file doesn't exist."""
        composite_path = tmp_path / "nonexistent.png"

        service = CompositeCreationService("poke1", "vid_abc123")
        result = service.check_composite_exists(composite_path)

        assert result is False


class TestCreateSplitScreenComposite:
    """Test create_split_screen_composite method."""

    @pytest.mark.asyncio
    @patch('app.services.composite_creation.Image')
    async def test_split_screen_composite_generic_implementation(
        self,
        mock_image,
        tmp_path: Path
    ):
        """Test split-screen composite creates 1920x1080 image."""
        # Create mock paths
        char_a_path = tmp_path / "char_a.png"
        env_a_path = tmp_path / "env_a.png"
        char_b_path = tmp_path / "char_b.png"
        env_b_path = tmp_path / "env_b.png"
        output_path = tmp_path / "clip_15_split.png"

        # Mock PIL Image.open to return mock images
        mock_img_char_a = MagicMock()
        mock_img_char_a.size = (400, 400)
        mock_img_char_a.resize.return_value = mock_img_char_a
        mock_img_char_a.convert.return_value = mock_img_char_a

        mock_img_env_a = MagicMock()
        mock_img_env_a.size = (1920, 1080)
        mock_img_env_a.resize.return_value = mock_img_env_a
        mock_img_env_a.convert.return_value = mock_img_env_a

        mock_img_char_b = MagicMock()
        mock_img_char_b.size = (400, 400)
        mock_img_char_b.resize.return_value = mock_img_char_b
        mock_img_char_b.convert.return_value = mock_img_char_b

        mock_img_env_b = MagicMock()
        mock_img_env_b.size = (1920, 1080)
        mock_img_env_b.resize.return_value = mock_img_env_b
        mock_img_env_b.convert.return_value = mock_img_env_b

        # Mock composite image
        mock_composite = MagicMock()
        mock_composite.size = (1920, 1080)
        mock_composite.split.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]

        # Configure open to return different mocks based on path
        def open_side_effect(path):
            if "char_a" in str(path):
                return mock_img_char_a
            elif "env_a" in str(path):
                return mock_img_env_a
            elif "char_b" in str(path):
                return mock_img_char_b
            elif "env_b" in str(path):
                return mock_img_env_b
            return MagicMock()

        mock_image.open.side_effect = open_side_effect
        mock_image.new.return_value = mock_composite

        service = CompositeCreationService("poke1", "vid_abc123")

        # Run split-screen composition
        await service.create_split_screen_composite(
            char_a_path, env_a_path, char_b_path, env_b_path, output_path
        )

        # Verify Image.new called with 1920x1080 dimensions
        mock_image.new.assert_called()
        new_call_args = mock_image.new.call_args_list[0]
        assert new_call_args[0][1] == (1920, 1080)

        # Verify composite.save() called
        assert mock_composite.save.called


class TestMultiChannelIsolation:
    """Test multi-channel isolation."""

    @patch('app.services.composite_creation.get_composite_dir')
    @patch('app.services.composite_creation.get_environment_dir')
    @patch('app.services.composite_creation.get_character_dir')
    def test_multi_channel_isolation_paths(
        self,
        mock_char_dir,
        mock_env_dir,
        mock_composite_dir,
        tmp_path: Path
    ):
        """Test composite paths are completely isolated per channel."""
        # Setup channel 1 directories
        poke1_char = tmp_path / "poke1" / "characters"
        poke1_env = tmp_path / "poke1" / "environments"
        poke1_comp = tmp_path / "poke1" / "composites"
        poke1_char.mkdir(parents=True)
        poke1_env.mkdir(parents=True)
        poke1_comp.mkdir(parents=True)

        # Setup channel 2 directories
        poke2_char = tmp_path / "poke2" / "characters"
        poke2_env = tmp_path / "poke2" / "environments"
        poke2_comp = tmp_path / "poke2" / "composites"
        poke2_char.mkdir(parents=True)
        poke2_env.mkdir(parents=True)
        poke2_comp.mkdir(parents=True)

        # Create assets for both channels
        for i in range(1, 9):
            (poke1_char / f"char_{i}.png").touch()
            (poke1_env / f"env_{i}.png").touch()
            (poke2_char / f"char_{i}.png").touch()
            (poke2_env / f"env_{i}.png").touch()

        # Create service for channel 1
        def mock_char_dir_side_effect(channel_id, project_id):
            return tmp_path / channel_id / "characters"

        def mock_env_dir_side_effect(channel_id, project_id):
            return tmp_path / channel_id / "environments"

        def mock_composite_dir_side_effect(channel_id, project_id):
            return tmp_path / channel_id / "composites"

        mock_char_dir.side_effect = mock_char_dir_side_effect
        mock_env_dir.side_effect = mock_env_dir_side_effect
        mock_composite_dir.side_effect = mock_composite_dir_side_effect

        service1 = CompositeCreationService("poke1", "vid_abc123")
        service2 = CompositeCreationService("poke2", "vid_abc123")

        manifest1 = service1.create_composite_manifest("Topic1", "Story1")
        manifest2 = service2.create_composite_manifest("Topic2", "Story2")

        # Verify paths are completely isolated
        for composite in manifest1.composites:
            assert "poke1" in str(composite.output_path)
            assert "poke2" not in str(composite.output_path)

        for composite in manifest2.composites:
            assert "poke2" in str(composite.output_path)
            assert "poke1" not in str(composite.output_path)


class TestIdempotentRegeneration:
    """Test idempotent regeneration."""

    @pytest.mark.asyncio
    @patch('app.services.composite_creation.run_cli_script')
    @patch('app.services.composite_creation.Image')
    async def test_idempotent_regeneration_overwrites_existing(
        self,
        mock_image,
        mock_run_cli_script,
        tmp_path: Path
    ):
        """Test regeneration overwrites existing files (resume=False)."""
        # Create composites
        composites = []
        for i in range(1, 4):  # 3 composites for faster test
            output_path = tmp_path / f"clip_{i:02d}.png"
            output_path.touch()  # Simulate existing composite

            composite = SceneComposite(
                clip_number=i,
                character_path=tmp_path / "char.png",
                environment_path=tmp_path / "env.png",
                output_path=output_path
            )
            composites.append(composite)

        manifest = CompositeManifest(composites=composites)

        # Mock CLI script and PIL
        mock_run_cli_script.return_value = AsyncMock()
        mock_img = MagicMock()
        mock_img.size = (1920, 1080)
        mock_img.__enter__ = Mock(return_value=mock_img)
        mock_img.__exit__ = Mock(return_value=False)
        mock_image.open.return_value = mock_img

        service = CompositeCreationService("poke1", "vid_abc123")

        # Run with resume=False (idempotent regeneration)
        result = await service.generate_composites(manifest, resume=False)

        # Verify all composites regenerated (none skipped)
        assert result["generated"] == 3
        assert result["skipped"] == 0
        assert result["failed"] == 0

        # Verify CLI script called for each composite
        assert mock_run_cli_script.call_count == 3
