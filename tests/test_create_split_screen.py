"""Tests for create_split_screen.py script.

Tests the horizontal split-screen composite logic. Since create_split_screen.py
has module-level code with hardcoded paths, we test the core algorithm
by reimplementing and testing the resize_and_crop_to_half logic.

Priority: P2 - Supporting functionality for split-screen clips.
"""

from pathlib import Path

import pytest
from PIL import Image

from tests.support.factories.image_factory import (
    create_environment_image,
    create_test_image,
    save_test_image,
)


# Constants matching the script
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
HALF_WIDTH = TARGET_WIDTH // 2  # 960 pixels per side


def resize_and_crop_to_half(img: Image.Image) -> Image.Image:
    """Resize image to 960x1080 (half of 16:9 canvas).

    This is a copy of the function from create_split_screen.py for testing.
    """
    img_width, img_height = img.size
    img_aspect = img_width / img_height
    target_aspect = HALF_WIDTH / TARGET_HEIGHT

    if img_aspect > target_aspect:
        # Image is wider - scale to height and crop width
        new_height = TARGET_HEIGHT
        new_width = int(img_width * TARGET_HEIGHT / img_height)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        # Center crop to half width
        left = (new_width - HALF_WIDTH) // 2
        img = img.crop((left, 0, left + HALF_WIDTH, TARGET_HEIGHT))
    else:
        # Image is taller - scale to width and crop height
        new_width = HALF_WIDTH
        new_height = int(img_height * HALF_WIDTH / img_width)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        # Center crop to target height
        top = (new_height - TARGET_HEIGHT) // 2
        img = img.crop((0, top, HALF_WIDTH, top + TARGET_HEIGHT))

    return img


class TestResizeAndCropToHalf:
    """Tests for resize_and_crop_to_half function."""

    def test_p1_output_is_960x1080(self):
        """[P1] Output should always be 960x1080 (half of 16:9)."""
        # GIVEN: Various input sizes
        test_cases = [
            (1920, 1080),  # Standard 16:9
            (2560, 1080),  # Ultra-wide
            (1080, 1920),  # Tall/portrait
            (800, 600),  # 4:3
            (640, 480),  # Small 4:3
        ]

        for width, height in test_cases:
            img = create_test_image(width, height, color=(100, 150, 200))

            # WHEN: Resizing and cropping
            result = resize_and_crop_to_half(img)

            # THEN: Output is exactly 960x1080
            assert result.size == (HALF_WIDTH, TARGET_HEIGHT), f"Failed for input {width}x{height}"

    def test_p1_wide_image_center_cropped_horizontally(self):
        """[P1] Wide images should be center-cropped horizontally."""
        # GIVEN: Ultra-wide image (wider than 960:1080 ratio)
        # Create image with distinct left/center/right sections
        width, height = 2560, 1080
        img = Image.new("RGB", (width, height))
        # Left third: red
        for x in range(width // 3):
            for y in range(height):
                img.putpixel((x, y), (255, 0, 0))
        # Middle third: green
        for x in range(width // 3, 2 * width // 3):
            for y in range(height):
                img.putpixel((x, y), (0, 255, 0))
        # Right third: blue
        for x in range(2 * width // 3, width):
            for y in range(height):
                img.putpixel((x, y), (0, 0, 255))

        # WHEN: Resizing and cropping
        result = resize_and_crop_to_half(img)

        # THEN: Center pixel should be green (from middle section)
        center_pixel = result.getpixel((HALF_WIDTH // 2, TARGET_HEIGHT // 2))
        assert center_pixel[1] > 200, "Center should be green (from middle)"

    def test_p1_tall_image_center_cropped_vertically(self):
        """[P1] Tall images should be center-cropped vertically."""
        # GIVEN: Tall/portrait image (9:16 ratio)
        width, height = 1080, 1920
        img = Image.new("RGB", (width, height))
        # Top third: red
        for x in range(width):
            for y in range(height // 3):
                img.putpixel((x, y), (255, 0, 0))
        # Middle third: green
        for x in range(width):
            for y in range(height // 3, 2 * height // 3):
                img.putpixel((x, y), (0, 255, 0))
        # Bottom third: blue
        for x in range(width):
            for y in range(2 * height // 3, height):
                img.putpixel((x, y), (0, 0, 255))

        # WHEN: Resizing and cropping
        result = resize_and_crop_to_half(img)

        # THEN: Center pixel should be green (from middle section)
        center_pixel = result.getpixel((HALF_WIDTH // 2, TARGET_HEIGHT // 2))
        assert center_pixel[1] > 200, "Center should be green (from middle)"

    def test_p1_standard_16_9_scales_correctly(self):
        """[P1] Standard 16:9 image should scale to half width."""
        # GIVEN: Standard 1920x1080 image
        img = create_test_image(1920, 1080, color=(128, 128, 128))

        # WHEN: Resizing and cropping
        result = resize_and_crop_to_half(img)

        # THEN: Output is 960x1080
        assert result.size == (HALF_WIDTH, TARGET_HEIGHT)

    def test_p2_small_image_upscaled(self):
        """[P2] Small images should be upscaled to fit."""
        # GIVEN: Small 320x240 image
        img = create_test_image(320, 240, color=(100, 200, 150))

        # WHEN: Resizing and cropping
        result = resize_and_crop_to_half(img)

        # THEN: Output is exactly 960x1080
        assert result.size == (HALF_WIDTH, TARGET_HEIGHT)

    def test_p2_square_image_handled(self):
        """[P2] Square images should be handled correctly."""
        # GIVEN: Square image
        img = create_test_image(1000, 1000, color=(200, 100, 50))

        # WHEN: Resizing and cropping
        result = resize_and_crop_to_half(img)

        # THEN: Output is 960x1080
        assert result.size == (HALF_WIDTH, TARGET_HEIGHT)


class TestSplitScreenCompositeLogic:
    """Tests for the overall split-screen composite logic."""

    def test_p1_final_canvas_is_1920x1080(self, tmp_path: Path):
        """[P1] Final split-screen canvas should be 1920x1080."""
        # GIVEN: Two half-width images
        left_img = create_test_image(HALF_WIDTH, TARGET_HEIGHT, color=(255, 0, 0))
        right_img = create_test_image(HALF_WIDTH, TARGET_HEIGHT, color=(0, 0, 255))

        # WHEN: Creating split-screen canvas
        final_canvas = Image.new("RGB", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0))
        final_canvas.paste(left_img, (0, 0))
        final_canvas.paste(right_img, (HALF_WIDTH, 0))

        # THEN: Final canvas is 1920x1080
        assert final_canvas.size == (TARGET_WIDTH, TARGET_HEIGHT)

    def test_p1_left_half_starts_at_x_0(self, tmp_path: Path):
        """[P1] Left half should start at x=0."""
        # GIVEN: Red left image
        left_img = create_test_image(HALF_WIDTH, TARGET_HEIGHT, color=(255, 0, 0))
        right_img = create_test_image(HALF_WIDTH, TARGET_HEIGHT, color=(0, 0, 255))

        # WHEN: Creating split-screen canvas
        final_canvas = Image.new("RGB", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0))
        final_canvas.paste(left_img, (0, 0))
        final_canvas.paste(right_img, (HALF_WIDTH, 0))

        # THEN: Left edge pixel is red
        left_pixel = final_canvas.getpixel((10, TARGET_HEIGHT // 2))
        assert left_pixel[0] > 200  # Red

    def test_p1_right_half_starts_at_x_960(self, tmp_path: Path):
        """[P1] Right half should start at x=960."""
        # GIVEN: Red left, blue right
        left_img = create_test_image(HALF_WIDTH, TARGET_HEIGHT, color=(255, 0, 0))
        right_img = create_test_image(HALF_WIDTH, TARGET_HEIGHT, color=(0, 0, 255))

        # WHEN: Creating split-screen canvas
        final_canvas = Image.new("RGB", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0))
        final_canvas.paste(left_img, (0, 0))
        final_canvas.paste(right_img, (HALF_WIDTH, 0))

        # THEN: Right side pixel is blue
        right_pixel = final_canvas.getpixel((HALF_WIDTH + 10, TARGET_HEIGHT // 2))
        assert right_pixel[2] > 200  # Blue

    def test_p2_boundary_between_halves(self, tmp_path: Path):
        """[P2] Boundary at x=960 should be clean (no overlap)."""
        # GIVEN: Distinct colors for each half
        left_img = create_test_image(HALF_WIDTH, TARGET_HEIGHT, color=(255, 0, 0))
        right_img = create_test_image(HALF_WIDTH, TARGET_HEIGHT, color=(0, 255, 0))

        # WHEN: Creating split-screen canvas
        final_canvas = Image.new("RGB", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0))
        final_canvas.paste(left_img, (0, 0))
        final_canvas.paste(right_img, (HALF_WIDTH, 0))

        # THEN: Pixel at x=959 is red (left), pixel at x=960 is green (right)
        left_edge = final_canvas.getpixel((HALF_WIDTH - 1, TARGET_HEIGHT // 2))
        right_edge = final_canvas.getpixel((HALF_WIDTH, TARGET_HEIGHT // 2))

        assert left_edge[0] > 200, "Left edge should be red"
        assert right_edge[1] > 200, "Right edge should be green"

    def test_p2_character_overlay_centered_on_half(self):
        """[P2] Character should be centered within each half."""
        # GIVEN: Environment and small character
        env = create_test_image(HALF_WIDTH, TARGET_HEIGHT, color=(50, 50, 50))
        char = create_test_image(100, 100, color=(255, 255, 0))

        # WHEN: Calculating center position for half-width canvas
        char_width, char_height = char.size
        x_offset = (HALF_WIDTH - char_width) // 2
        y_offset = (TARGET_HEIGHT - char_height) // 2

        # THEN: Offsets center the character
        assert x_offset == (960 - 100) // 2  # 430
        assert y_offset == (1080 - 100) // 2  # 490
