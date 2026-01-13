"""Image data factories for test data generation.

Generates PIL Image objects for testing image manipulation scripts.
Uses deterministic data for reproducible tests.
"""

from pathlib import Path

from PIL import Image


def create_test_image(
    width: int = 100,
    height: int = 100,
    color: tuple[int, int, int] = (255, 0, 0),
    mode: str = "RGB",
) -> Image.Image:
    """Create a solid color test image.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.
        color: RGB tuple for fill color.
        mode: PIL image mode (RGB, RGBA, etc.).

    Returns:
        PIL Image object.
    """
    return Image.new(mode, (width, height), color)


def create_transparent_image(
    width: int = 100,
    height: int = 100,
    color: tuple[int, int, int, int] = (0, 255, 0, 200),
) -> Image.Image:
    """Create an RGBA image with transparency.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.
        color: RGBA tuple (R, G, B, Alpha).

    Returns:
        PIL Image object with alpha channel.
    """
    return Image.new("RGBA", (width, height), color)


def create_environment_image(
    width: int = 1920,
    height: int = 1080,
) -> Image.Image:
    """Create a 16:9 environment background for testing.

    Args:
        width: Image width (default 1920 for HD).
        height: Image height (default 1080 for HD).

    Returns:
        PIL Image object representing environment background.
    """
    # Create gradient-like environment (blue sky -> green ground)
    img = Image.new("RGB", (width, height))
    for y in range(height):
        ratio = y / height
        r = int(135 * (1 - ratio) + 34 * ratio)
        g = int(206 * (1 - ratio) + 139 * ratio)
        b = int(235 * (1 - ratio) + 34 * ratio)
        for x in range(width):
            img.putpixel((x, y), (r, g, b))
    return img


def create_character_image(
    width: int = 200,
    height: int = 200,
) -> Image.Image:
    """Create a character image with transparent background.

    Args:
        width: Image width in pixels.
        height: Image height in pixels.

    Returns:
        PIL RGBA Image with circular character and transparent background.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    # Draw a simple circle as "character"
    center_x, center_y = width // 2, height // 2
    radius = min(width, height) // 3

    for x in range(width):
        for y in range(height):
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            if distance <= radius:
                # Yellow character
                img.putpixel((x, y), (255, 255, 0, 255))

    return img


def create_ultrawide_image(
    width: int = 2560,
    height: int = 1080,
) -> Image.Image:
    """Create an ultra-wide (21:9) image for testing aspect ratio handling.

    Args:
        width: Image width (default 2560 for 21:9).
        height: Image height (default 1080).

    Returns:
        PIL Image object.
    """
    return create_test_image(width, height, color=(100, 100, 200))


def create_tall_image(
    width: int = 1080,
    height: int = 1920,
) -> Image.Image:
    """Create a tall (9:16) image for testing vertical aspect ratio handling.

    Args:
        width: Image width.
        height: Image height.

    Returns:
        PIL Image object.
    """
    return create_test_image(width, height, color=(200, 100, 100))


def save_test_image(image: Image.Image, path: Path) -> Path:
    """Save a test image to disk.

    Args:
        image: PIL Image to save.
        path: Path to save to.

    Returns:
        Path to saved file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG")
    return path
