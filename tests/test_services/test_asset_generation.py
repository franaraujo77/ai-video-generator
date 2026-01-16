"""Tests for Asset Generation Service.

This module tests the AssetGenerationService class which orchestrates
image generation via Gemini API for the video generation pipeline.

Test Coverage:
- Asset manifest creation (global atmosphere, individual prompts)
- Asset generation orchestration (CLI script invocation)
- Partial resume functionality (skip existing assets)
- Error handling (CLIScriptError, timeout)
- Cost estimation
- Security (path traversal, sensitive data)

Architecture Compliance:
- Uses Story 3.1 CLI wrapper (never subprocess directly)
- Uses Story 3.2 filesystem helpers (never manual paths)
- Mocks CLI script to avoid actual Gemini API calls
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.asset_generation import (
    AssetGenerationService,
    AssetManifest,
    AssetPrompt,
)
from app.utils.cli_wrapper import CLIScriptError


class TestAssetPromptDataclass:
    """Test AssetPrompt dataclass."""

    def test_asset_prompt_creation(self, tmp_path: Path):
        """Test creating AssetPrompt with all fields."""
        output_path = tmp_path / "test.png"

        asset = AssetPrompt(
            asset_type="character",
            name="bulbasaur_resting",
            prompt="Bulbasaur resting peacefully",
            output_path=output_path,
        )

        assert asset.asset_type == "character"
        assert asset.name == "bulbasaur_resting"
        assert asset.prompt == "Bulbasaur resting peacefully"
        assert asset.output_path == output_path


class TestAssetManifestDataclass:
    """Test AssetManifest dataclass."""

    def test_asset_manifest_creation(self, tmp_path: Path):
        """Test creating AssetManifest with assets list."""
        asset1 = AssetPrompt(
            asset_type="character",
            name="char1",
            prompt="Character 1",
            output_path=tmp_path / "char1.png",
        )
        asset2 = AssetPrompt(
            asset_type="environment",
            name="env1",
            prompt="Environment 1",
            output_path=tmp_path / "env1.png",
        )

        manifest = AssetManifest(
            global_atmosphere="Natural lighting, misty atmosphere", assets=[asset1, asset2]
        )

        assert manifest.global_atmosphere == "Natural lighting, misty atmosphere"
        assert len(manifest.assets) == 2
        assert manifest.assets[0].asset_type == "character"
        assert manifest.assets[1].asset_type == "environment"


class TestAssetGenerationServiceInit:
    """Test AssetGenerationService initialization."""

    def test_service_initialization(self):
        """Test service initializes with channel_id and project_id."""
        service = AssetGenerationService("poke1", "vid_abc123")

        assert service.channel_id == "poke1"
        assert service.project_id == "vid_abc123"
        assert service.log is not None


class TestCreateAssetManifest:
    """Test create_asset_manifest method."""

    @patch("app.services.asset_generation.get_character_dir")
    @patch("app.services.asset_generation.get_environment_dir")
    @patch("app.services.asset_generation.get_props_dir")
    def test_create_manifest_from_topic_and_story(
        self, mock_props_dir, mock_env_dir, mock_char_dir, tmp_path: Path
    ):
        """Test creating asset manifest with topic and story direction."""
        # Setup mocked directories
        char_dir = tmp_path / "characters"
        env_dir = tmp_path / "environments"
        props_dir = tmp_path / "props"
        char_dir.mkdir()
        env_dir.mkdir()
        props_dir.mkdir()

        mock_char_dir.return_value = char_dir
        mock_env_dir.return_value = env_dir
        mock_props_dir.return_value = props_dir

        service = AssetGenerationService("poke1", "vid_abc123")
        manifest = service.create_asset_manifest(
            "Bulbasaur forest documentary", "Show evolution through seasons"
        )

        # Verify global atmosphere derived
        assert isinstance(manifest.global_atmosphere, str)
        assert len(manifest.global_atmosphere) > 0
        assert "lighting" in manifest.global_atmosphere.lower()

        # Verify assets generated (8 char + 8 env + 6 props = 22 total)
        assert len(manifest.assets) == 22

        # Verify asset types
        character_assets = [a for a in manifest.assets if a.asset_type == "character"]
        environment_assets = [a for a in manifest.assets if a.asset_type == "environment"]
        prop_assets = [a for a in manifest.assets if a.asset_type == "prop"]

        assert len(character_assets) == 8
        assert len(environment_assets) == 8
        assert len(prop_assets) == 6

        # Verify paths use correct directories
        assert all(a.output_path.parent == char_dir for a in character_assets)
        assert all(a.output_path.parent == env_dir for a in environment_assets)
        assert all(a.output_path.parent == props_dir for a in prop_assets)

    @patch("app.services.asset_generation.get_character_dir")
    @patch("app.services.asset_generation.get_environment_dir")
    @patch("app.services.asset_generation.get_props_dir")
    def test_global_atmosphere_forest_topic(
        self, mock_props_dir, mock_env_dir, mock_char_dir, tmp_path: Path
    ):
        """Test global atmosphere derivation for forest topic."""
        # Setup mocks
        mock_char_dir.return_value = tmp_path / "characters"
        mock_env_dir.return_value = tmp_path / "environments"
        mock_props_dir.return_value = tmp_path / "props"

        service = AssetGenerationService("poke1", "vid_abc123")
        manifest = service.create_asset_manifest("Forest documentary", "Nature exploration")

        # Verify forest-specific atmosphere
        atmosphere = manifest.global_atmosphere.lower()
        assert "forest" in atmosphere or "canopy" in atmosphere
        assert "lighting" in atmosphere

    @patch("app.services.asset_generation.get_character_dir")
    @patch("app.services.asset_generation.get_environment_dir")
    @patch("app.services.asset_generation.get_props_dir")
    def test_global_atmosphere_underwater_topic(
        self, mock_props_dir, mock_env_dir, mock_char_dir, tmp_path: Path
    ):
        """Test global atmosphere derivation for underwater topic."""
        mock_char_dir.return_value = tmp_path / "characters"
        mock_env_dir.return_value = tmp_path / "environments"
        mock_props_dir.return_value = tmp_path / "props"

        service = AssetGenerationService("poke1", "vid_abc123")
        manifest = service.create_asset_manifest(
            "Underwater ocean documentary", "Deep sea exploration"
        )

        atmosphere = manifest.global_atmosphere.lower()
        assert "underwater" in atmosphere
        assert "lighting" in atmosphere


class TestGenerateAssets:
    """Test generate_assets method."""

    @pytest.mark.asyncio
    @patch("app.services.asset_generation.run_cli_script")
    @patch("app.services.asset_generation.get_character_dir")
    @patch("app.services.asset_generation.get_environment_dir")
    @patch("app.services.asset_generation.get_props_dir")
    async def test_generate_all_assets_success(
        self, mock_props_dir, mock_env_dir, mock_char_dir, mock_run_cli, tmp_path: Path
    ):
        """Test generating all assets successfully."""
        # Setup mocked directories
        char_dir = tmp_path / "characters"
        env_dir = tmp_path / "environments"
        props_dir = tmp_path / "props"
        char_dir.mkdir(parents=True)
        env_dir.mkdir(parents=True)
        props_dir.mkdir(parents=True)

        mock_char_dir.return_value = char_dir
        mock_env_dir.return_value = env_dir
        mock_props_dir.return_value = props_dir

        # Mock CLI script success and create files
        async def create_asset_file(*args, **kwargs):
            # Extract output path from args
            output_flag_index = args[1].index("--output")
            output_path = Path(args[1][output_flag_index + 1])
            output_path.touch()  # Create the file
            return MagicMock(returncode=0, stdout="Success", stderr="")

        mock_run_cli.side_effect = create_asset_file

        service = AssetGenerationService("poke1", "vid_abc123")
        manifest = service.create_asset_manifest("Bulbasaur forest", "Nature documentary")

        result = await service.generate_assets(manifest, resume=False)

        # Verify all 22 assets generated
        assert result["generated"] == 22
        assert result["skipped"] == 0
        assert result["failed"] == 0
        assert result["total_cost_usd"] == pytest.approx(22 * 0.068, abs=0.01)

        # Verify CLI script called for each asset
        assert mock_run_cli.call_count == 22

    @pytest.mark.asyncio
    @patch("app.services.asset_generation.run_cli_script")
    @patch("app.services.asset_generation.get_character_dir")
    @patch("app.services.asset_generation.get_environment_dir")
    @patch("app.services.asset_generation.get_props_dir")
    async def test_generate_assets_with_resume_skip_existing(
        self, mock_props_dir, mock_env_dir, mock_char_dir, mock_run_cli, tmp_path: Path
    ):
        """Test partial resume skips existing assets."""
        # Setup directories
        char_dir = tmp_path / "characters"
        env_dir = tmp_path / "environments"
        props_dir = tmp_path / "props"
        char_dir.mkdir(parents=True)
        env_dir.mkdir(parents=True)
        props_dir.mkdir(parents=True)

        mock_char_dir.return_value = char_dir
        mock_env_dir.return_value = env_dir
        mock_props_dir.return_value = props_dir

        # Create 12 assets already existing
        service = AssetGenerationService("poke1", "vid_abc123")
        manifest = service.create_asset_manifest("Bulbasaur forest", "Nature documentary")

        # Create first 12 assets
        for i in range(12):
            manifest.assets[i].output_path.touch()

        # Mock CLI script for remaining assets
        async def create_remaining_assets(*args, **kwargs):
            output_flag_index = args[1].index("--output")
            output_path = Path(args[1][output_flag_index + 1])
            output_path.touch()
            return MagicMock(returncode=0, stdout="Success", stderr="")

        mock_run_cli.side_effect = create_remaining_assets

        result = await service.generate_assets(manifest, resume=True)

        # Verify only 10 assets generated (22 - 12 existing)
        assert result["generated"] == 10
        assert result["skipped"] == 12
        assert result["failed"] == 0
        assert mock_run_cli.call_count == 10

    @pytest.mark.asyncio
    @patch("app.services.asset_generation.run_cli_script")
    @patch("app.services.asset_generation.get_character_dir")
    @patch("app.services.asset_generation.get_environment_dir")
    @patch("app.services.asset_generation.get_props_dir")
    async def test_generate_assets_cli_script_error(
        self, mock_props_dir, mock_env_dir, mock_char_dir, mock_run_cli, tmp_path: Path
    ):
        """Test CLI script error handling."""
        mock_char_dir.return_value = tmp_path / "characters"
        mock_env_dir.return_value = tmp_path / "environments"
        mock_props_dir.return_value = tmp_path / "props"

        # Mock CLI script to raise error
        mock_run_cli.side_effect = CLIScriptError(
            "generate_asset.py", 1, "Gemini API error: HTTP 500"
        )

        service = AssetGenerationService("poke1", "vid_abc123")
        manifest = service.create_asset_manifest("Bulbasaur forest", "Nature documentary")

        # Verify CLIScriptError propagates
        with pytest.raises(CLIScriptError) as exc_info:
            await service.generate_assets(manifest, resume=False)

        assert exc_info.value.script == "generate_asset.py"
        assert exc_info.value.exit_code == 1
        assert "HTTP 500" in exc_info.value.stderr

    @pytest.mark.asyncio
    @patch("app.services.asset_generation.run_cli_script")
    @patch("app.services.asset_generation.get_character_dir")
    @patch("app.services.asset_generation.get_environment_dir")
    @patch("app.services.asset_generation.get_props_dir")
    async def test_generate_assets_prompt_combination(
        self, mock_props_dir, mock_env_dir, mock_char_dir, mock_run_cli, tmp_path: Path
    ):
        """Test asset prompt combined with global atmosphere."""
        char_dir = tmp_path / "characters"
        env_dir = tmp_path / "environments"
        props_dir = tmp_path / "props"
        char_dir.mkdir(parents=True)
        env_dir.mkdir(parents=True)
        props_dir.mkdir(parents=True)

        mock_char_dir.return_value = char_dir
        mock_env_dir.return_value = env_dir
        mock_props_dir.return_value = props_dir

        # Capture CLI script arguments
        captured_prompts = []

        async def capture_prompt(*args, **kwargs):
            prompt = args[1][args[1].index("--prompt") + 1]
            captured_prompts.append(prompt)
            output_path = Path(args[1][args[1].index("--output") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.touch()
            return MagicMock(returncode=0)

        mock_run_cli.side_effect = capture_prompt

        service = AssetGenerationService("poke1", "vid_abc123")
        manifest = service.create_asset_manifest("Bulbasaur forest", "Nature documentary")

        await service.generate_assets(manifest, resume=False)

        # Verify all prompts start with global atmosphere
        global_atmosphere = manifest.global_atmosphere
        for prompt in captured_prompts:
            assert prompt.startswith(global_atmosphere)
            assert "\n\n" in prompt  # Separator between atmosphere and asset prompt


class TestCheckAssetExists:
    """Test check_asset_exists method."""

    def test_asset_exists_returns_true(self, tmp_path: Path):
        """Test returns True for existing file."""
        asset_path = tmp_path / "test.png"
        asset_path.touch()

        service = AssetGenerationService("poke1", "vid_abc123")
        assert service.check_asset_exists(asset_path) is True

    def test_asset_exists_returns_false_missing_file(self, tmp_path: Path):
        """Test returns False for non-existent file."""
        asset_path = tmp_path / "missing.png"

        service = AssetGenerationService("poke1", "vid_abc123")
        assert service.check_asset_exists(asset_path) is False

    def test_asset_exists_returns_false_directory(self, tmp_path: Path):
        """Test returns False for directory."""
        service = AssetGenerationService("poke1", "vid_abc123")
        assert service.check_asset_exists(tmp_path) is False


class TestEstimateCost:
    """Test estimate_cost method."""

    def test_cost_calculation_22_assets(self):
        """Test cost calculation for 22 assets."""
        service = AssetGenerationService("poke1", "vid_abc123")
        cost = service.estimate_cost(22)

        # 22 assets x $0.068/asset = $1.496
        assert cost == pytest.approx(1.496, abs=0.01)

    def test_cost_calculation_zero_assets(self):
        """Test cost calculation for zero assets."""
        service = AssetGenerationService("poke1", "vid_abc123")
        cost = service.estimate_cost(0)

        assert cost == 0.0

    def test_cost_calculation_10_assets(self):
        """Test cost calculation for partial generation."""
        service = AssetGenerationService("poke1", "vid_abc123")
        cost = service.estimate_cost(10)

        # 10 assets x $0.068/asset = $0.68
        assert cost == pytest.approx(0.68, abs=0.01)


class TestSecurityValidation:
    """Test security validations in asset generation service."""

    def test_path_traversal_prevention_channel_id(self):
        """Test channel_id validation prevents path traversal."""
        # Try to create service with path traversal in channel_id
        with pytest.raises(ValueError) as exc_info:
            AssetGenerationService("../../../etc", "vid_abc123")

        assert "channel_id contains invalid characters" in str(exc_info.value)

    def test_path_traversal_prevention_project_id(self):
        """Test project_id validation prevents path traversal."""
        # Try to create service with path traversal in project_id
        with pytest.raises(ValueError) as exc_info:
            AssetGenerationService("poke1", "../secrets")

        assert "project_id contains invalid characters" in str(exc_info.value)

    def test_identifier_validation_special_characters(self):
        """Test identifier validation rejects shell metacharacters."""
        # Test various shell metacharacters that could be dangerous
        dangerous_chars = [";", "|", "$", "`", "&", "\n", "\r"]

        for char in dangerous_chars:
            with pytest.raises(ValueError):
                AssetGenerationService(f"poke{char}1", "vid_abc123")

            with pytest.raises(ValueError):
                AssetGenerationService("poke1", f"vid{char}abc123")

    def test_identifier_validation_valid_characters(self):
        """Test valid identifiers are accepted."""
        # These should all succeed
        valid_ids = [
            ("poke1", "vid_abc123"),
            ("test-channel", "project-123"),
            ("Channel_1", "Project_ABC"),
            ("a1", "b2"),
        ]

        for channel_id, project_id in valid_ids:
            service = AssetGenerationService(channel_id, project_id)
            assert service.channel_id == channel_id
            assert service.project_id == project_id

    @pytest.mark.asyncio
    @patch("app.services.asset_generation.run_cli_script")
    @patch("app.services.asset_generation.get_character_dir")
    @patch("app.services.asset_generation.get_environment_dir")
    @patch("app.services.asset_generation.get_props_dir")
    async def test_sensitive_data_sanitization_in_logs(
        self, mock_props_dir, mock_env_dir, mock_char_dir, mock_run_cli, tmp_path: Path, caplog
    ):
        """Test prompts are truncated in logs to prevent leaking sensitive data."""
        char_dir = tmp_path / "characters"
        char_dir.mkdir(parents=True)

        mock_char_dir.return_value = char_dir
        mock_env_dir.return_value = tmp_path / "environments"
        mock_props_dir.return_value = tmp_path / "props"

        # Mock CLI script to fail
        mock_run_cli.side_effect = CLIScriptError(
            "generate_asset.py", 1, "API error with API_KEY=secret123"
        )

        service = AssetGenerationService("poke1", "vid_abc123")
        manifest = service.create_asset_manifest(
            "Bulbasaur API_KEY=secret123", "Story with sensitive data"
        )

        # Try to generate (will fail)
        with pytest.raises(CLIScriptError):
            await service.generate_assets(manifest, resume=False)

        # Verify logs contain truncated prompt, not full prompt
        # Log should show prompt_preview with max 100 chars
        assert any(
            "prompt_preview" in record.message
            for record in caplog.records
            if record.levelname == "ERROR"
        )
