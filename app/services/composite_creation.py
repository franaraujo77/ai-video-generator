"""Composite Creation Service for combining character + environment assets.

This module implements the second stage of the 8-step video generation pipeline.
It orchestrates the creation of 18 composite images (1920x1080, 16:9) by combining
character and environment assets, following the "Smart Agent + Dumb Scripts"
architectural pattern.

Key Responsibilities:
- Map 18 video clips to character + environment asset pairs
- Create 18 composite images (standard + split-screen) via CLI script invocation
- Handle both standard composites (1 char + 1 env) and split-screen (2 char + 2 env)
- Track completed vs. pending composites for partial resume support
- Enforce 1920x1080 (16:9) output dimensions for YouTube compatibility

Architecture Pattern:
    Service (Smart): Maps scenes to assets, determines composite type, manages retry
    CLI Script (Dumb): Receives paths, creates composite, returns success/failure

Dependencies:
    - Story 3.1: CLI wrapper (run_cli_script, CLIScriptError)
    - Story 3.2: Filesystem helpers (get_composite_dir, get_character_dir, get_environment_dir)
    - Story 3.3: Asset generation (22 assets available in assets/ subdirectories)
    - Epic 1: Database models (Task)
    - Epic 2: Notion API client

Usage:
    from app.services.composite_creation import CompositeCreationService

    service = CompositeCreationService("poke1", "vid_abc123")
    manifest = service.create_composite_manifest(
        "Bulbasaur forest documentary",
        "Show evolution through seasons"
    )

    result = await service.generate_composites(manifest, resume=False)
    print(f"Generated {result['generated']} composites")
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image  # type: ignore[import-untyped]

from app.utils.cli_wrapper import CLIScriptError, run_cli_script
from app.utils.filesystem import (
    get_character_dir,
    get_composite_dir,
    get_environment_dir,
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
class SceneComposite:
    """Represents a single composite to generate for one video clip.

    Attributes:
        clip_number: Clip number (1-18)
        character_path: Path to character PNG (transparent background)
        environment_path: Path to environment PNG (background image)
        output_path: Path where composite PNG will be saved
        is_split_screen: True if this is a split-screen composite (clip 15)
        character_b_path: Optional second character for split-screen
        environment_b_path: Optional second environment for split-screen
        character_scale: Scaling factor for character (1.0 = 100%)
    """

    clip_number: int
    character_path: Path
    environment_path: Path
    output_path: Path
    is_split_screen: bool = False
    character_b_path: Path | None = None
    environment_b_path: Path | None = None
    character_scale: float = 1.0


@dataclass
class CompositeManifest:
    """Complete manifest of composites to generate for a project (18 total).

    Attributes:
        composites: List of SceneComposite objects (one per video clip)
    """

    composites: list[SceneComposite]


class CompositeCreationService:
    """Service for creating 1920x1080 composite images from character + environment assets.

    This service orchestrates the composite creation phase of the video pipeline,
    following the "Smart Agent + Dumb Scripts" pattern where the service handles
    business logic and the CLI script handles image composition.

    Responsibilities:
    - Map scene definitions to asset paths (character + environment)
    - Create 18 composite images (one per video clip)
    - Handle both standard composites (1 char + 1 env) and split-screen (2 char + 2 env)
    - Orchestrate CLI script invocation for each composite
    - Track completed vs. pending composites for partial resume

    Architecture Compliance:
    - Uses Story 3.1 CLI wrapper (never calls subprocess directly)
    - Uses Story 3.2 filesystem helpers (never constructs paths manually)
    - Implements short transaction pattern (service is stateless)
    """

    def __init__(self, channel_id: str, project_id: str):
        """Initialize composite creation service for specific project.

        Args:
            channel_id: Channel identifier for path isolation
            project_id: Project/task identifier (UUID from database)

        Raises:
            ValueError: If channel_id or project_id contain invalid characters
        """
        # Validate identifiers to prevent path traversal attacks (Story 3.4 security requirement)
        _validate_identifier(channel_id, "channel_id")
        _validate_identifier(project_id, "project_id")

        self.channel_id = channel_id
        self.project_id = project_id
        self.log = get_logger(__name__)

    def create_composite_manifest(self, topic: str, story_direction: str) -> CompositeManifest:
        """Create composite manifest by mapping 18 scenes to character+environment assets.

        Scene Derivation Strategy:
        1. Parse story_direction to understand narrative structure (18 clips)
        2. Scan available character assets in `assets/characters/`
        3. Scan available environment assets in `assets/environments/`
        4. Map each clip to appropriate character and environment based on:
           - Clip sequence (intro → action → conclusion)
           - Asset filenames (infer usage from naming conventions)
           - Default pairing strategy (cycle through characters/environments)

        Args:
            topic: Video topic from Notion (for context)
            story_direction: Story direction from Notion (narrative guidance)

        Returns:
            CompositeManifest with 18 SceneComposite objects

        Example:
            >>> manifest = service.create_composite_manifest(
            ...     "Bulbasaur forest documentary",
            ...     "Show evolution through seasons: spring growth, summer activity, autumn rest",
            ... )
            >>> print(len(manifest.composites))
            18
            >>> print(manifest.composites[0].clip_number)
            1
            >>> print(manifest.composites[0].character_path.name)
            "bulbasaur_resting.png"
        """
        # Get asset directories using filesystem helpers (Story 3.2)
        char_dir = get_character_dir(self.channel_id, self.project_id)
        env_dir = get_environment_dir(self.channel_id, self.project_id)
        composite_dir = get_composite_dir(self.channel_id, self.project_id)

        # Scan available assets
        character_files = sorted(char_dir.glob("*.png"))
        environment_files = sorted(env_dir.glob("*.png"))

        if not character_files:
            raise FileNotFoundError(f"No character assets found in {char_dir}")
        if not environment_files:
            raise FileNotFoundError(f"No environment assets found in {env_dir}")

        self.log.info(
            "assets_scanned",
            character_count=len(character_files),
            environment_count=len(environment_files),
            character_dir=str(char_dir),
            environment_dir=str(env_dir),
        )

        # Generate 18 composites using round-robin asset pairing
        composites: list[SceneComposite] = []

        for clip_num in range(1, 19):  # 18 clips total
            # Round-robin cycling through assets
            char_idx = (clip_num - 1) % len(character_files)
            env_idx = (clip_num - 1) % len(environment_files)

            character_path = character_files[char_idx]
            environment_path = environment_files[env_idx]

            # Special case: Clip 15 is split-screen
            if clip_num == 15:
                # Split-screen uses two character+environment pairs
                char_b_idx = (clip_num) % len(character_files)  # Next character
                env_b_idx = (clip_num) % len(environment_files)  # Next environment

                character_b_path = character_files[char_b_idx]
                environment_b_path = environment_files[env_b_idx]

                output_path = composite_dir / f"clip_{clip_num:02d}_split.png"

                composite = SceneComposite(
                    clip_number=clip_num,
                    character_path=character_path,
                    environment_path=environment_path,
                    output_path=output_path,
                    is_split_screen=True,
                    character_b_path=character_b_path,
                    environment_b_path=environment_b_path,
                    character_scale=1.0,
                )
            else:
                # Standard composite
                output_path = composite_dir / f"clip_{clip_num:02d}.png"

                composite = SceneComposite(
                    clip_number=clip_num,
                    character_path=character_path,
                    environment_path=environment_path,
                    output_path=output_path,
                    is_split_screen=False,
                    character_scale=1.0,
                )

            composites.append(composite)

        self.log.info(
            "composite_manifest_created",
            total_composites=len(composites),
            standard_count=sum(1 for c in composites if not c.is_split_screen),
            split_screen_count=sum(1 for c in composites if c.is_split_screen),
        )

        return CompositeManifest(composites=composites)

    async def generate_composites(
        self, manifest: CompositeManifest, resume: bool = False
    ) -> dict[str, Any]:
        """Generate all composites in manifest by invoking CLI scripts.

        Orchestration Flow:
        1. For each composite in manifest:
           a. Check if composite exists (if resume=True, skip existing)
           b. Determine composite type (standard vs split-screen)
           c. Invoke appropriate CLI script:
              - Standard: `create_composite.py --character X --environment Y --output Z`
              - Split-screen: Inline PIL composition (generic, not haunter-specific)
           d. Wait for completion (timeout: 30 seconds per composite)
           e. Verify PNG file exists and is 1920x1080
           f. Log success/failure with correlation ID
        2. Return summary (generated count, skipped count, failed count)

        Args:
            manifest: CompositeManifest with 18 scene definitions
            resume: If True, skip composites that already exist on filesystem

        Returns:
            Summary dict with keys:
                - generated: Number of newly generated composites
                - skipped: Number of existing composites (if resume=True)
                - failed: Number of failed composites

        Raises:
            CLIScriptError: If any composite generation fails

        Example:
            >>> result = await service.generate_composites(manifest, resume=False)
            >>> print(result)
            {"generated": 18, "skipped": 0, "failed": 0}
        """
        generated = 0
        skipped = 0
        failed = 0

        self.log.info(
            "composite_generation_start",
            total_composites=len(manifest.composites),
            resume_mode=resume,
        )

        for composite in manifest.composites:
            # Skip existing composites if resume mode enabled
            if resume and self.check_composite_exists(composite.output_path):
                self.log.info(
                    "composite_skipped_exists",
                    clip_number=composite.clip_number,
                    output_path=str(composite.output_path),
                )
                skipped += 1
                continue

            try:
                if composite.is_split_screen:
                    # Split-screen: Use inline PIL composition
                    await self.create_split_screen_composite(
                        composite.character_path,
                        composite.environment_path,
                        composite.character_b_path,  # type: ignore
                        composite.environment_b_path,  # type: ignore
                        composite.output_path,
                    )
                else:
                    # Standard composite: Use CLI script
                    await run_cli_script(
                        "create_composite.py",
                        [
                            "--character",
                            str(composite.character_path),
                            "--environment",
                            str(composite.environment_path),
                            "--output",
                            str(composite.output_path),
                            "--scale",
                            str(composite.character_scale),
                        ],
                        timeout=30,  # 30 seconds per composite
                    )

                # Verify output exists and is correct dimensions
                if not composite.output_path.exists():
                    raise FileNotFoundError(f"Composite not created: {composite.output_path}")

                # Verify dimensions (1920x1080)
                with Image.open(composite.output_path) as img:
                    if img.size != (1920, 1080):
                        raise ValueError(
                            f"Composite has incorrect dimensions: {img.size}, expected (1920, 1080)"
                        )

                self.log.info(
                    "composite_generated",
                    clip_number=composite.clip_number,
                    output_path=str(composite.output_path),
                    is_split_screen=composite.is_split_screen,
                )
                generated += 1

            except CLIScriptError as e:
                self.log.error(
                    "composite_generation_error",
                    clip_number=composite.clip_number,
                    script=e.script,
                    exit_code=e.exit_code,
                    stderr=e.stderr[:500],  # Truncate stderr
                    character_path=str(composite.character_path),
                    environment_path=str(composite.environment_path),
                )
                failed += 1
                # Re-raise to mark task as failed and allow retry
                raise

            except Exception as e:
                self.log.error(
                    "composite_generation_unexpected_error",
                    clip_number=composite.clip_number,
                    error=str(e),
                    output_path=str(composite.output_path),
                )
                failed += 1
                # Re-raise to mark task as failed
                raise

        self.log.info(
            "composite_generation_complete",
            generated=generated,
            skipped=skipped,
            failed=failed,
            total=len(manifest.composites),
        )

        return {"generated": generated, "skipped": skipped, "failed": failed}

    def check_composite_exists(self, composite_path: Path) -> bool:
        """Check if composite file exists on filesystem.

        Used for partial resume (Story 3.4 AC3).

        Args:
            composite_path: Full path to composite PNG file

        Returns:
            True if file exists and is readable, False otherwise
        """
        return composite_path.exists() and composite_path.is_file()

    async def create_split_screen_composite(
        self,
        char_a_path: Path,
        env_a_path: Path,
        char_b_path: Path,
        env_b_path: Path,
        output_path: Path,
    ) -> None:
        """Create split-screen composite inline using PIL (generic, not haunter-specific).

        Composition Strategy:
        1. Load all 4 images (2 characters, 2 environments)
        2. Resize each environment to 960x1080 (half of 1920x1080)
        3. Overlay character A on environment A (left half)
        4. Overlay character B on environment B (right half)
        5. Combine both halves side-by-side on 1920x1080 canvas
        6. Save as PNG

        Args:
            char_a_path: Path to left character PNG
            env_a_path: Path to left environment PNG
            char_b_path: Path to right character PNG
            env_b_path: Path to right environment PNG
            output_path: Path to save split-screen composite PNG

        Raises:
            Exception: If PIL operations fail or dimensions are incorrect

        Note:
            This is a generic implementation that works for ANY project,
            unlike the hardcoded `scripts/create_split_screen.py` which
            only works for the haunter project.
        """
        # Target dimensions: 1920x1080 total, 960x1080 per half
        target_width = 1920
        target_height = 1080
        half_width = 960

        self.log.info(
            "split_screen_composite_start",
            char_a=str(char_a_path.name) if char_a_path else None,
            env_a=str(env_a_path.name) if env_a_path else None,
            char_b=str(char_b_path.name) if char_b_path else None,
            env_b=str(env_b_path.name) if env_b_path else None,
            output=str(output_path.name) if output_path else None,
        )

        # Load images
        env_a = Image.open(env_a_path).convert("RGBA")
        char_a = Image.open(char_a_path).convert("RGBA")
        env_b = Image.open(env_b_path).convert("RGBA")
        char_b = Image.open(char_b_path).convert("RGBA")

        # Resize environments to 960x1080 (half width)
        env_a_resized = env_a.resize((half_width, target_height), Image.Resampling.LANCZOS)
        env_b_resized = env_b.resize((half_width, target_height), Image.Resampling.LANCZOS)

        # Scale characters to fit within 960x1080 half
        def scale_character_to_half(
            char: Image.Image, max_width: int, max_height: int
        ) -> Image.Image:
            """Scale character to fit within half screen while maintaining aspect ratio."""
            char_width, char_height = char.size
            scale_factor = min(max_width / char_width, max_height / char_height)

            # Don't upscale, only downscale
            if scale_factor < 1.0:
                new_width = int(char_width * scale_factor)
                new_height = int(char_height * scale_factor)
                return char.resize((new_width, new_height), Image.Resampling.LANCZOS)
            return char

        char_a_scaled = scale_character_to_half(char_a, half_width, target_height)
        char_b_scaled = scale_character_to_half(char_b, half_width, target_height)

        # Create left half (environment A + character A)
        left_half = env_a_resized.copy()
        char_a_width, char_a_height = char_a_scaled.size
        char_a_x = (half_width - char_a_width) // 2
        char_a_y = (target_height - char_a_height) // 2
        left_half.paste(char_a_scaled, (char_a_x, char_a_y), char_a_scaled)

        # Create right half (environment B + character B)
        right_half = env_b_resized.copy()
        char_b_width, char_b_height = char_b_scaled.size
        char_b_x = (half_width - char_b_width) // 2
        char_b_y = (target_height - char_b_height) // 2
        right_half.paste(char_b_scaled, (char_b_x, char_b_y), char_b_scaled)

        # Combine both halves side-by-side on 1920x1080 canvas
        composite = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 255))
        composite.paste(left_half, (0, 0))
        composite.paste(right_half, (half_width, 0))

        # Convert to RGB for final output
        final = Image.new("RGB", composite.size, (0, 0, 0))
        final.paste(composite, mask=composite.split()[3])  # Use alpha channel as mask

        # Save
        final.save(output_path, "PNG")

        self.log.info(
            "split_screen_composite_complete",
            output_path=str(output_path),
            dimensions=f"{target_width}x{target_height}",
        )
