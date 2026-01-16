"""Asset Generation Service for Gemini-powered image generation.

This module implements the first stage of the 8-step video generation pipeline.
It orchestrates the generation of 22 photorealistic images (characters, environments,
props) via Gemini 2.5 Flash Image API, following the "Smart Agent + Dumb Scripts"
architectural pattern.

Key Responsibilities:
- Extract Global Atmosphere Block from Notion Topic/Story Direction
- Generate asset manifests with 22 individual asset prompts
- Orchestrate CLI script invocation via async wrapper (Story 3.1)
- Track completed vs. pending assets for partial resume support
- Calculate and report Gemini API costs for budget monitoring

Architecture Pattern:
    Service (Smart): Reads data, combines prompts, manages retry logic
    CLI Script (Dumb): Receives complete prompt, calls Gemini API, returns success/failure

Dependencies:
    - Story 3.1: CLI wrapper (run_cli_script, CLIScriptError)
    - Story 3.2: Filesystem helpers (get_character_dir, get_environment_dir, get_props_dir)
    - Epic 1: Database models (Task)
    - Epic 2: Notion API client

Usage:
    from app.services.asset_generation import AssetGenerationService

    service = AssetGenerationService("poke1", "vid_abc123")
    manifest = service.create_asset_manifest(
        "Bulbasaur forest documentary",
        "Show evolution through seasons"
    )

    result = await service.generate_assets(manifest, resume=False)
    print(f"Generated {result['generated']} assets, cost: ${result['total_cost_usd']}")
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.cli_wrapper import run_cli_script
from app.utils.filesystem import (
    get_character_dir,
    get_environment_dir,
    get_props_dir,
)
from app.utils.logging import get_logger

log = get_logger(__name__)


def _validate_identifier(value: str, name: str) -> None:
    """Validate channel_id or project_id to prevent path traversal attacks.

    Args:
        value: The identifier value to validate
        name: The name of the identifier (for error messages)

    Raises:
        ValueError: If identifier contains invalid characters or invalid length

    Security:
        Prevents path traversal attacks by enforcing alphanumeric, underscore,
        and hyphen characters only. Matches Story 3.2 security patterns.
    """
    if not re.match(r"^[a-zA-Z0-9_-]+$", value):
        raise ValueError(f"{name} contains invalid characters: {value}")
    if len(value) == 0 or len(value) > 100:
        raise ValueError(f"{name} length must be 1-100 characters")


@dataclass
class AssetPrompt:
    """Represents a single asset to generate.

    Attributes:
        asset_type: Type of asset ("character", "environment", "prop")
        name: Asset filename without extension (e.g., "bulbasaur_forest")
        prompt: Individual asset prompt WITHOUT Global Atmosphere Block
        output_path: Full path where PNG will be saved
    """

    asset_type: str
    name: str
    prompt: str
    output_path: Path


@dataclass
class AssetManifest:
    """Complete manifest of assets to generate for a project.

    Attributes:
        global_atmosphere: Global Atmosphere Block shared across all assets
                          (lighting, weather, style context)
        assets: List of individual assets to generate (22 total)
    """

    global_atmosphere: str
    assets: list[AssetPrompt]


class AssetGenerationService:
    """Service for generating image assets via Gemini API.

    This service orchestrates the asset generation phase of the video pipeline,
    following the "Smart Agent + Dumb Scripts" pattern where the service handles
    business logic and the CLI script handles API calls.

    Responsibilities:
    - Derive Global Atmosphere Block from Topic/Story Direction
    - Generate asset prompts based on story context
    - Combine prompts with atmosphere for complete Gemini inputs
    - Invoke CLI script for each asset with proper error handling
    - Support partial resume (skip existing assets)
    - Track API costs for budget monitoring

    Architecture Compliance:
    - Uses Story 3.1 CLI wrapper (never calls subprocess directly)
    - Uses Story 3.2 filesystem helpers (never constructs paths manually)
    - Implements short transaction pattern (service is stateless)
    """

    def __init__(self, channel_id: str, project_id: str):
        """Initialize asset generation service for specific project.

        Args:
            channel_id: Channel identifier for path isolation
            project_id: Project/task identifier (UUID from database)

        Raises:
            ValueError: If channel_id or project_id contain invalid characters
        """
        # Validate identifiers to prevent path traversal attacks (Story 3.3 security requirement)
        _validate_identifier(channel_id, "channel_id")
        _validate_identifier(project_id, "project_id")

        self.channel_id = channel_id
        self.project_id = project_id
        self.log = get_logger(__name__)

    def create_asset_manifest(self, topic: str, story_direction: str) -> AssetManifest:
        """Create asset manifest from Notion Topic and Story Direction.

        This method performs critical prompt engineering:
        1. Derive Global Atmosphere Block from topic context
        2. Generate 22 individual asset prompts based on story direction
        3. Categorize assets by type (characters, environments, props)
        4. Construct filesystem paths using helpers from Story 3.2

        Args:
            topic: Video topic from Notion (e.g., "Bulbasaur forest documentary")
            story_direction: Story direction from Notion (narrative guidance)

        Returns:
            AssetManifest with global_atmosphere and list of AssetPrompt objects

        Example:
            >>> manifest = service.create_asset_manifest(
            ...     "Bulbasaur forest documentary", "Show evolution through seasons"
            ... )
            >>> print(manifest.global_atmosphere)
            "Natural forest lighting, misty morning atmosphere..."
            >>> print(len(manifest.assets))
            22
            >>> print(manifest.assets[0].asset_type)
            "character"
        """
        # Derive Global Atmosphere Block from topic
        global_atmosphere = self._derive_global_atmosphere(topic)

        # Generate character assets (6-8 images)
        character_dir = get_character_dir(self.channel_id, self.project_id)
        characters = self._generate_character_prompts(topic, story_direction, character_dir)

        # Generate environment assets (8-10 images)
        environment_dir = get_environment_dir(self.channel_id, self.project_id)
        environments = self._generate_environment_prompts(topic, story_direction, environment_dir)

        # Generate prop assets (4-6 images)
        props_dir = get_props_dir(self.channel_id, self.project_id)
        props = self._generate_prop_prompts(topic, story_direction, props_dir)

        assets = characters + environments + props

        self.log.info(
            "asset_manifest_created",
            channel_id=self.channel_id,
            project_id=self.project_id,
            total_assets=len(assets),
            characters=len(characters),
            environments=len(environments),
            props=len(props),
            atmosphere_preview=global_atmosphere[:100],
        )

        return AssetManifest(global_atmosphere=global_atmosphere, assets=assets)

    async def generate_assets(
        self, manifest: AssetManifest, resume: bool = False
    ) -> dict[str, Any]:
        """Generate all assets in manifest by invoking CLI script.

        Orchestration Flow:
        1. For each asset in manifest:
           a. Check if asset exists (if resume=True, skip existing)
           b. Combine asset prompt with global atmosphere
           c. Invoke `scripts/generate_asset.py` with combined prompt
           d. Wait for completion (timeout: 60 seconds per asset)
           e. Verify PNG file exists at output_path
           f. Log success/failure with correlation ID
        2. Calculate total Gemini API costs
        3. Return summary (generated, skipped, failed counts)

        Args:
            manifest: AssetManifest with prompts and paths
            resume: If True, skip assets that already exist on filesystem

        Returns:
            Summary dict with keys:
                - generated: Number of newly generated assets
                - skipped: Number of existing assets (if resume=True)
                - failed: Number of failed assets
                - total_cost_usd: Total Gemini API cost

        Raises:
            CLIScriptError: If any asset generation fails

        Example:
            >>> result = await service.generate_assets(manifest, resume=False)
            >>> print(result)
            {"generated": 22, "skipped": 0, "failed": 0, "total_cost_usd": 1.50}
        """
        generated = 0
        skipped = 0
        failed = 0

        for asset in manifest.assets:
            # Skip if asset exists and resume=True
            if resume and self.check_asset_exists(asset.output_path):
                skipped += 1
                self.log.info(
                    "asset_skipped",
                    name=asset.name,
                    type=asset.asset_type,
                    path=str(asset.output_path),
                )
                continue

            # Combine asset prompt with global atmosphere
            combined_prompt = f"{manifest.global_atmosphere}\n\n{asset.prompt}"

            try:
                # Invoke CLI script via async wrapper (Story 3.1)
                await run_cli_script(
                    "generate_asset.py",
                    ["--prompt", combined_prompt, "--output", str(asset.output_path)],
                    timeout=60,  # Gemini API timeout
                )

                # Verify file was created
                if not asset.output_path.exists():
                    raise FileNotFoundError(
                        f"Asset generation succeeded but file not found: {asset.output_path}"
                    )

                generated += 1
                self.log.info(
                    "asset_generated",
                    name=asset.name,
                    type=asset.asset_type,
                    path=str(asset.output_path),
                )

            except Exception as e:
                failed += 1
                # Sanitize prompt in log (may contain sensitive context)
                self.log.error(
                    "asset_generation_failed",
                    name=asset.name,
                    type=asset.asset_type,
                    error=str(e),
                    prompt_preview=combined_prompt[:100],
                )
                # Re-raise to allow worker to handle (mark task failed, retry, etc.)
                raise

        # Calculate total cost
        total_cost_usd = self.estimate_cost(generated)

        self.log.info(
            "asset_generation_complete",
            channel_id=self.channel_id,
            project_id=self.project_id,
            generated=generated,
            skipped=skipped,
            failed=failed,
            total_cost_usd=total_cost_usd,
        )

        return {
            "generated": generated,
            "skipped": skipped,
            "failed": failed,
            "total_cost_usd": total_cost_usd,
        }

    def check_asset_exists(self, asset_path: Path) -> bool:
        """Check if asset file exists on filesystem.

        Used for partial resume (AC2) to skip regenerating existing assets.

        Args:
            asset_path: Full path to asset PNG file

        Returns:
            True if file exists and is readable, False otherwise
        """
        return asset_path.exists() and asset_path.is_file()

    def estimate_cost(self, asset_count: int) -> float:
        """Estimate Gemini API cost for asset generation.

        Gemini 2.5 Flash Image pricing (as of 2026-01):
        - $0.05-0.10 per image (varies by size/complexity)
        - Average: $0.068 per image

        Args:
            asset_count: Number of assets to generate

        Returns:
            Estimated cost in USD

        Example:
            >>> cost = service.estimate_cost(22)
            >>> print(f"${cost:.2f}")
            $1.50  # 22 * $0.068 = $1.496 ≈ $1.50
        """
        return asset_count * 0.068  # Average cost per asset

    # Private helper methods for prompt generation

    def _derive_global_atmosphere(self, topic: str) -> str:
        """Derive Global Atmosphere Block from topic.

        Analyzes the topic to extract visual style context (lighting, weather,
        atmosphere) that should be consistent across all 22 assets.

        Args:
            topic: Video topic from Notion

        Returns:
            Global Atmosphere Block string
        """
        # Extract keywords for atmosphere derivation
        topic_lower = topic.lower()

        # Lighting conditions
        if "forest" in topic_lower or "jungle" in topic_lower:
            lighting = "Natural forest lighting, dappled sunlight through canopy"
        elif "underwater" in topic_lower or "ocean" in topic_lower:
            lighting = "Soft underwater lighting, filtered sunlight"
        elif "cave" in topic_lower or "dark" in topic_lower:
            lighting = "Dim cave lighting, bioluminescent glow"
        elif "mountain" in topic_lower or "peak" in topic_lower:
            lighting = "Bright mountain lighting, clear alpine atmosphere"
        else:
            lighting = "Natural daylight, soft ambient lighting"

        # Weather/atmosphere
        if "mist" in topic_lower or "fog" in topic_lower:
            atmosphere = "misty morning atmosphere"
        elif "rain" in topic_lower or "storm" in topic_lower:
            atmosphere = "rainy atmosphere, water droplets"
        elif "snow" in topic_lower or "ice" in topic_lower:
            atmosphere = "snowy atmosphere, crisp cold air"
        else:
            atmosphere = "clear atmosphere"

        # Combine into Global Atmosphere Block
        return (
            f"{lighting}, {atmosphere}, "
            f"soft golden hour glow, depth of field effect, "
            f"photorealistic nature documentary style, "
            f"4K resolution, cinematic composition"
        )

    def _generate_character_prompts(
        self, topic: str, story_direction: str, character_dir: Path
    ) -> list[AssetPrompt]:
        """Generate character asset prompts.

        Creates 8 character images with various poses and states based on
        the story direction.

        Args:
            topic: Video topic
            story_direction: Story direction for context
            character_dir: Directory for character assets

        Returns:
            List of AssetPrompt objects for characters (8 total)
        """
        # Extract Pokemon name from topic (simplified extraction)
        # In production, this would use more sophisticated parsing
        words = topic.split()
        pokemon_name = words[0] if words else "Pokemon"

        characters = [
            AssetPrompt(
                asset_type="character",
                name=f"{pokemon_name.lower()}_resting",
                prompt=f"{pokemon_name} resting peacefully, eyes closed, relaxed pose",
                output_path=character_dir / f"{pokemon_name.lower()}_resting.png",
            ),
            AssetPrompt(
                asset_type="character",
                name=f"{pokemon_name.lower()}_walking",
                prompt=f"{pokemon_name} walking forward, natural gait, alert expression",
                output_path=character_dir / f"{pokemon_name.lower()}_walking.png",
            ),
            AssetPrompt(
                asset_type="character",
                name=f"{pokemon_name.lower()}_looking",
                prompt=f"{pokemon_name} looking at camera, curious expression, front view",
                output_path=character_dir / f"{pokemon_name.lower()}_looking.png",
            ),
            AssetPrompt(
                asset_type="character",
                name=f"{pokemon_name.lower()}_side",
                prompt=f"{pokemon_name} side profile view, standing still, detailed features",
                output_path=character_dir / f"{pokemon_name.lower()}_side.png",
            ),
            AssetPrompt(
                asset_type="character",
                name=f"{pokemon_name.lower()}_action",
                prompt=f"{pokemon_name} using signature ability, energy glowing, dynamic pose",
                output_path=character_dir / f"{pokemon_name.lower()}_action.png",
            ),
            AssetPrompt(
                asset_type="character",
                name=f"{pokemon_name.lower()}_eating",
                prompt=f"{pokemon_name} eating berries, content expression, natural behavior",
                output_path=character_dir / f"{pokemon_name.lower()}_eating.png",
            ),
            AssetPrompt(
                asset_type="character",
                name=f"{pokemon_name.lower()}_sleeping",
                prompt=f"{pokemon_name} sleeping curled up, peaceful rest, nighttime behavior",
                output_path=character_dir / f"{pokemon_name.lower()}_sleeping.png",
            ),
            AssetPrompt(
                asset_type="character",
                name=f"{pokemon_name.lower()}_stretching",
                prompt=f"{pokemon_name} stretching after waking, yawning, morning routine",
                output_path=character_dir / f"{pokemon_name.lower()}_stretching.png",
            ),
        ]

        return characters

    def _generate_environment_prompts(
        self, topic: str, story_direction: str, environment_dir: Path
    ) -> list[AssetPrompt]:
        """Generate environment asset prompts.

        Creates 8-10 environment images (forests, caves, water, mountains) based
        on the topic and story direction.

        Args:
            topic: Video topic
            story_direction: Story direction for context
            environment_dir: Directory for environment assets

        Returns:
            List of AssetPrompt objects for environments
        """
        environments = [
            AssetPrompt(
                asset_type="environment",
                name="forest_clearing",
                prompt="Forest clearing with sunlight, lush vegetation, natural habitat",
                output_path=environment_dir / "forest_clearing.png",
            ),
            AssetPrompt(
                asset_type="environment",
                name="forest_stream",
                prompt="Small forest stream with flowing water, rocks, moss-covered stones",
                output_path=environment_dir / "forest_stream.png",
            ),
            AssetPrompt(
                asset_type="environment",
                name="forest_canopy",
                prompt="Dense forest canopy view, tall trees, filtered sunlight",
                output_path=environment_dir / "forest_canopy.png",
            ),
            AssetPrompt(
                asset_type="environment",
                name="forest_path",
                prompt="Winding forest path, dappled sunlight, natural trail",
                output_path=environment_dir / "forest_path.png",
            ),
            AssetPrompt(
                asset_type="environment",
                name="tree_hollow",
                prompt="Large tree hollow entrance, moss and bark texture, den habitat",
                output_path=environment_dir / "tree_hollow.png",
            ),
            AssetPrompt(
                asset_type="environment",
                name="forest_undergrowth",
                prompt="Dense forest undergrowth, ferns and shrubs, ground level view",
                output_path=environment_dir / "forest_undergrowth.png",
            ),
            AssetPrompt(
                asset_type="environment",
                name="forest_pond",
                prompt="Small forest pond with still water, reflection, lily pads",
                output_path=environment_dir / "forest_pond.png",
            ),
            AssetPrompt(
                asset_type="environment",
                name="forest_rocks",
                prompt="Large moss-covered rocks in forest, natural formation",
                output_path=environment_dir / "forest_rocks.png",
            ),
        ]

        return environments

    def _generate_prop_prompts(
        self, topic: str, story_direction: str, props_dir: Path
    ) -> list[AssetPrompt]:
        """Generate prop asset prompts.

        Creates 6 prop images (background elements, effects, flora/fauna) to
        enrich the documentary scenes.

        Args:
            topic: Video topic
            story_direction: Story direction for context
            props_dir: Directory for prop assets

        Returns:
            List of AssetPrompt objects for props (6 total)
        """
        props = [
            AssetPrompt(
                asset_type="prop",
                name="mushroom_cluster",
                prompt="Cluster of forest mushrooms, various sizes, natural grouping",
                output_path=props_dir / "mushroom_cluster.png",
            ),
            AssetPrompt(
                asset_type="prop",
                name="berry_bush",
                prompt="Bush with ripe berries, green leaves, natural food source",
                output_path=props_dir / "berry_bush.png",
            ),
            AssetPrompt(
                asset_type="prop",
                name="fallen_log",
                prompt="Large fallen log with moss and fungi, decomposing wood",
                output_path=props_dir / "fallen_log.png",
            ),
            AssetPrompt(
                asset_type="prop",
                name="forest_flowers",
                prompt="Small forest flowers, delicate petals, natural groundcover",
                output_path=props_dir / "forest_flowers.png",
            ),
            AssetPrompt(
                asset_type="prop",
                name="tree_bark_closeup",
                prompt="Close-up of tree bark texture, moss and lichen details, natural patterns",
                output_path=props_dir / "tree_bark_closeup.png",
            ),
            AssetPrompt(
                asset_type="prop",
                name="forest_ferns",
                prompt="Lush forest ferns, unfurling fronds, undergrowth vegetation",
                output_path=props_dir / "forest_ferns.png",
            ),
        ]

        return props
