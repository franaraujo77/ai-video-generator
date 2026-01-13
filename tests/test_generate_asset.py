"""Tests for generate_asset.py script.

Tests the image compositing functions in generate_asset.py.
API calls to Gemini are NOT tested here (would require integration tests).

Priority: P1 - Critical path for asset generation pipeline.
"""

import sys
from pathlib import Path

import pytest
from PIL import Image

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_asset import create_composite, create_split_vertical

from tests.support.factories.image_factory import (
    create_character_image,
    create_environment_image,
    create_test_image,
    save_test_image,
)


class TestCreateCompositeInGenerateAsset:
    """Tests for create_composite function in generate_asset.py."""

    def test_p1_creates_composite_from_character_and_environment(self, tmp_path: Path):
        """[P1] Should create composite by centering character on environment."""
        # GIVEN: Character and environment images
        char_path = tmp_path / "character.png"
        env_path = tmp_path / "environment.png"
        output_path = tmp_path / "composite.png"

        save_test_image(create_character_image(100, 100), char_path)
        save_test_image(create_environment_image(800, 600), env_path)

        # WHEN: Creating composite
        result = create_composite(str(char_path), str(env_path), str(output_path))

        # THEN: Returns True and file exists
        assert result is True
        assert output_path.exists()

    def test_p1_composite_preserves_environment_dimensions(self, tmp_path: Path):
        """[P1] Composite should match environment dimensions."""
        # GIVEN: Specific environment size
        char_path = tmp_path / "character.png"
        env_path = tmp_path / "environment.png"
        output_path = tmp_path / "composite.png"

        env_width, env_height = 1200, 800
        save_test_image(create_character_image(100, 100), char_path)
        save_test_image(create_test_image(env_width, env_height, color=(50, 100, 150)), env_path)

        # WHEN: Creating composite
        create_composite(str(char_path), str(env_path), str(output_path))

        # THEN: Output dimensions match environment
        result = Image.open(output_path)
        assert result.size == (env_width, env_height)

    def test_p1_composite_output_is_rgb(self, tmp_path: Path):
        """[P1] Composite output should be RGB mode."""
        # GIVEN: Standard inputs
        char_path = tmp_path / "character.png"
        env_path = tmp_path / "environment.png"
        output_path = tmp_path / "composite.png"

        save_test_image(create_character_image(100, 100), char_path)
        save_test_image(create_environment_image(800, 600), env_path)

        # WHEN: Creating composite
        create_composite(str(char_path), str(env_path), str(output_path))

        # THEN: Output is RGB
        result = Image.open(output_path)
        assert result.mode == "RGB"

    def test_p2_returns_false_on_invalid_character_path(self, tmp_path: Path):
        """[P2] Should return False when character file doesn't exist."""
        # GIVEN: Non-existent character file
        char_path = tmp_path / "nonexistent.png"
        env_path = tmp_path / "environment.png"
        output_path = tmp_path / "composite.png"

        save_test_image(create_environment_image(800, 600), env_path)

        # WHEN: Attempting to create composite
        result = create_composite(str(char_path), str(env_path), str(output_path))

        # THEN: Returns False
        assert result is False

    def test_p2_returns_false_on_invalid_environment_path(self, tmp_path: Path):
        """[P2] Should return False when environment file doesn't exist."""
        # GIVEN: Non-existent environment file
        char_path = tmp_path / "character.png"
        env_path = tmp_path / "nonexistent.png"
        output_path = tmp_path / "composite.png"

        save_test_image(create_character_image(100, 100), char_path)

        # WHEN: Attempting to create composite
        result = create_composite(str(char_path), str(env_path), str(output_path))

        # THEN: Returns False
        assert result is False


class TestCreateSplitVertical:
    """Tests for create_split_vertical function."""

    def test_p1_creates_vertical_split_composite(self, tmp_path: Path):
        """[P1] Should stack two images vertically."""
        # GIVEN: Two images
        top_path = tmp_path / "top.png"
        bottom_path = tmp_path / "bottom.png"
        output_path = tmp_path / "split.png"

        save_test_image(create_test_image(800, 400, color=(255, 0, 0)), top_path)
        save_test_image(create_test_image(800, 400, color=(0, 0, 255)), bottom_path)

        # WHEN: Creating vertical split
        result = create_split_vertical(str(top_path), str(bottom_path), str(output_path))

        # THEN: Returns True and file exists
        assert result is True
        assert output_path.exists()

    def test_p1_split_height_is_sum_of_input_heights(self, tmp_path: Path):
        """[P1] Output height should be sum of input heights."""
        # GIVEN: Two images with different heights
        top_path = tmp_path / "top.png"
        bottom_path = tmp_path / "bottom.png"
        output_path = tmp_path / "split.png"

        top_height = 300
        bottom_height = 500
        save_test_image(create_test_image(800, top_height), top_path)
        save_test_image(create_test_image(800, bottom_height), bottom_path)

        # WHEN: Creating vertical split
        create_split_vertical(str(top_path), str(bottom_path), str(output_path))

        # THEN: Height is sum of inputs
        result = Image.open(output_path)
        assert result.size[1] == top_height + bottom_height

    def test_p1_split_width_is_max_of_input_widths(self, tmp_path: Path):
        """[P1] Output width should be max of input widths."""
        # GIVEN: Two images with different widths
        top_path = tmp_path / "top.png"
        bottom_path = tmp_path / "bottom.png"
        output_path = tmp_path / "split.png"

        top_width = 600
        bottom_width = 900
        save_test_image(create_test_image(top_width, 400), top_path)
        save_test_image(create_test_image(bottom_width, 400), bottom_path)

        # WHEN: Creating vertical split
        create_split_vertical(str(top_path), str(bottom_path), str(output_path))

        # THEN: Width is max of inputs
        result = Image.open(output_path)
        assert result.size[0] == max(top_width, bottom_width)

    def test_p1_narrower_images_centered_horizontally(self, tmp_path: Path):
        """[P1] Narrower images should be centered on wider canvas."""
        # GIVEN: Top narrower than bottom
        top_path = tmp_path / "top.png"
        bottom_path = tmp_path / "bottom.png"
        output_path = tmp_path / "split.png"

        # Red top (narrow), blue bottom (wide)
        save_test_image(create_test_image(400, 200, color=(255, 0, 0)), top_path)
        save_test_image(create_test_image(800, 200, color=(0, 0, 255)), bottom_path)

        # WHEN: Creating vertical split
        create_split_vertical(str(top_path), str(bottom_path), str(output_path))

        # THEN: Top image should be centered
        result = Image.open(output_path)

        # Check center of top half has red (from top image)
        top_center_pixel = result.getpixel((400, 100))
        assert top_center_pixel[0] > 200  # Red

        # Check far left of top half is black (padding)
        top_left_pixel = result.getpixel((10, 100))
        assert sum(top_left_pixel) < 50  # Black padding

    def test_p2_returns_false_on_missing_top_image(self, tmp_path: Path):
        """[P2] Should return False when top image doesn't exist."""
        # GIVEN: Non-existent top image
        top_path = tmp_path / "nonexistent.png"
        bottom_path = tmp_path / "bottom.png"
        output_path = tmp_path / "split.png"

        save_test_image(create_test_image(800, 400), bottom_path)

        # WHEN: Attempting split
        result = create_split_vertical(str(top_path), str(bottom_path), str(output_path))

        # THEN: Returns False
        assert result is False

    def test_p2_creates_output_directory_if_missing(self, tmp_path: Path):
        """[P2] Should create output directory if it doesn't exist."""
        # GIVEN: Output in nested non-existent directory
        top_path = tmp_path / "top.png"
        bottom_path = tmp_path / "bottom.png"
        output_path = tmp_path / "nested" / "deep" / "split.png"

        save_test_image(create_test_image(800, 400), top_path)
        save_test_image(create_test_image(800, 400), bottom_path)

        # WHEN: Creating split
        create_split_vertical(str(top_path), str(bottom_path), str(output_path))

        # THEN: Output exists in newly created directory
        assert output_path.exists()
