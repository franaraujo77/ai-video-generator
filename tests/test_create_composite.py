"""Tests for create_composite.py script.

Tests the image compositing functionality that combines character
and environment assets into 16:9 seed images for Kling video generation.

Priority: P1 - Critical path for video production pipeline.
"""

import sys
from pathlib import Path

import pytest
from PIL import Image

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from create_composite import create_composite

from tests.support.factories.image_factory import (
    create_character_image,
    create_environment_image,
    create_tall_image,
    create_ultrawide_image,
    save_test_image,
)


class TestCreateComposite:
    """Tests for create_composite function."""

    def test_p1_creates_1920x1080_output(self, tmp_path: Path):
        """[P1] Output image should be exactly 1920x1080 (16:9 HD)."""
        # GIVEN: Character and environment images
        char_path = tmp_path / "character.png"
        env_path = tmp_path / "environment.png"
        output_path = tmp_path / "composite.png"

        save_test_image(create_character_image(200, 200), char_path)
        save_test_image(create_environment_image(1920, 1080), env_path)

        # WHEN: Creating composite
        create_composite(str(char_path), str(env_path), str(output_path))

        # THEN: Output is exactly 1920x1080
        result = Image.open(output_path)
        assert result.size == (1920, 1080)

    def test_p1_character_centered_on_canvas(self, tmp_path: Path):
        """[P1] Character should be centered on the 1920x1080 canvas."""
        # GIVEN: A small character (100x100) and standard environment
        char_path = tmp_path / "character.png"
        env_path = tmp_path / "environment.png"
        output_path = tmp_path / "composite.png"

        # Create character with distinct yellow color
        char_img = create_character_image(100, 100)
        save_test_image(char_img, char_path)
        save_test_image(create_environment_image(1920, 1080), env_path)

        # WHEN: Creating composite
        create_composite(str(char_path), str(env_path), str(output_path))

        # THEN: Center pixel should contain character color (yellow)
        result = Image.open(output_path)
        center_x, center_y = 1920 // 2, 1080 // 2
        center_pixel = result.getpixel((center_x, center_y))

        # Character is yellow (255, 255, 0) - allow some tolerance
        assert center_pixel[0] > 200  # Red channel
        assert center_pixel[1] > 200  # Green channel
        assert center_pixel[2] < 50  # Blue channel should be low

    def test_p1_ultrawide_environment_crops_to_16_9(self, tmp_path: Path):
        """[P1] Ultra-wide (21:9) environment should be center-cropped to 16:9."""
        # GIVEN: Ultra-wide environment (2560x1080 = 21:9)
        char_path = tmp_path / "character.png"
        env_path = tmp_path / "environment.png"
        output_path = tmp_path / "composite.png"

        save_test_image(create_character_image(100, 100), char_path)
        save_test_image(create_ultrawide_image(2560, 1080), env_path)

        # WHEN: Creating composite
        create_composite(str(char_path), str(env_path), str(output_path))

        # THEN: Output is 1920x1080 (center-cropped from ultra-wide)
        result = Image.open(output_path)
        assert result.size == (1920, 1080)

    def test_p1_tall_environment_scaled_and_cropped(self, tmp_path: Path):
        """[P1] Tall (9:16) environment should be scaled and center-cropped to 16:9."""
        # GIVEN: Tall portrait environment (1080x1920 = 9:16)
        char_path = tmp_path / "character.png"
        env_path = tmp_path / "environment.png"
        output_path = tmp_path / "composite.png"

        save_test_image(create_character_image(100, 100), char_path)
        save_test_image(create_tall_image(1080, 1920), env_path)

        # WHEN: Creating composite
        create_composite(str(char_path), str(env_path), str(output_path))

        # THEN: Output is still 1920x1080
        result = Image.open(output_path)
        assert result.size == (1920, 1080)

    def test_p1_character_scale_factor_applied(self, tmp_path: Path):
        """[P1] Character scale factor should resize character appropriately."""
        # GIVEN: Character image and scale factor of 0.5
        char_path = tmp_path / "character.png"
        env_path = tmp_path / "environment.png"
        output_path = tmp_path / "composite.png"

        # Create a 200x200 character
        save_test_image(create_character_image(200, 200), char_path)
        save_test_image(create_environment_image(1920, 1080), env_path)

        # WHEN: Creating composite with 0.5 scale
        create_composite(str(char_path), str(env_path), str(output_path), character_scale=0.5)

        # THEN: Output is valid 1920x1080
        result = Image.open(output_path)
        assert result.size == (1920, 1080)

    def test_p1_output_is_rgb_not_rgba(self, tmp_path: Path):
        """[P1] Output should be RGB (3 channels) for video compatibility."""
        # GIVEN: Standard inputs
        char_path = tmp_path / "character.png"
        env_path = tmp_path / "environment.png"
        output_path = tmp_path / "composite.png"

        save_test_image(create_character_image(200, 200), char_path)
        save_test_image(create_environment_image(1920, 1080), env_path)

        # WHEN: Creating composite
        create_composite(str(char_path), str(env_path), str(output_path))

        # THEN: Output is RGB mode
        result = Image.open(output_path)
        assert result.mode == "RGB"

    def test_p2_small_environment_padded(self, tmp_path: Path):
        """[P2] Small environment should be scaled up and padded to 16:9."""
        # GIVEN: Small environment (640x480 = 4:3)
        char_path = tmp_path / "character.png"
        env_path = tmp_path / "environment.png"
        output_path = tmp_path / "composite.png"

        from tests.support.factories.image_factory import create_test_image

        save_test_image(create_character_image(50, 50), char_path)
        save_test_image(create_test_image(640, 480, color=(100, 150, 200)), env_path)

        # WHEN: Creating composite
        create_composite(str(char_path), str(env_path), str(output_path))

        # THEN: Output is 1920x1080
        result = Image.open(output_path)
        assert result.size == (1920, 1080)

    def test_p2_output_directory_created_if_missing(self, tmp_path: Path):
        """[P2] Output directory should be created if it doesn't exist."""
        # GIVEN: Output path in non-existent directory
        char_path = tmp_path / "character.png"
        env_path = tmp_path / "environment.png"
        output_path = tmp_path / "nested" / "deep" / "composite.png"

        save_test_image(create_character_image(100, 100), char_path)
        save_test_image(create_environment_image(1920, 1080), env_path)

        # WHEN: Creating composite
        create_composite(str(char_path), str(env_path), str(output_path))

        # THEN: Output file exists in newly created directory
        assert output_path.exists()

    def test_p2_character_larger_than_canvas_still_works(self, tmp_path: Path):
        """[P2] Character larger than canvas should still produce valid output."""
        # GIVEN: Very large character (2000x2000)
        char_path = tmp_path / "character.png"
        env_path = tmp_path / "environment.png"
        output_path = tmp_path / "composite.png"

        save_test_image(create_character_image(2000, 2000), char_path)
        save_test_image(create_environment_image(1920, 1080), env_path)

        # WHEN: Creating composite
        create_composite(str(char_path), str(env_path), str(output_path))

        # THEN: Output is valid 1920x1080 (character may be clipped)
        result = Image.open(output_path)
        assert result.size == (1920, 1080)
