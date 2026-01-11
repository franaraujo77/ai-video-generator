#!/usr/bin/env python3
"""
Create horizontal split-screen composite for clip 15
Left side: Magneton in generator room
Right side: Haunter in poisoned basement
Output: 1920x1080 (16:9) for YouTube
"""

from PIL import Image

# YouTube standard dimensions
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
HALF_WIDTH = TARGET_WIDTH // 2  # 960 pixels per side

# Left side: Magneton in generator room
magneton_env = Image.open("haunter/assets/environments/env_generator_room_lit.png").convert("RGBA")
magneton_char = Image.open("haunter/assets/characters/magneton_hovering_standard_core.png").convert(
    "RGBA"
)

# Right side: Haunter in poisoned basement
haunter_env = Image.open("haunter/assets/environments/env_flooded_basement_poisoned.png").convert(
    "RGBA"
)
haunter_char = Image.open("haunter/assets/characters/haunter_victorious_floating.png").convert(
    "RGBA"
)


# Resize environments to fit half-width while maintaining aspect ratio
def resize_and_crop_to_half(img):
    """Resize image to 960x1080 (half of 16:9 canvas)"""
    # Target is 960x1080 (aspect ratio 0.889:1)
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


# Resize both environments
magneton_env = resize_and_crop_to_half(magneton_env)
haunter_env = resize_and_crop_to_half(haunter_env)

# Overlay characters on their respective environments
# Magneton on left environment
mag_char_width, mag_char_height = magneton_char.size
mag_x = (HALF_WIDTH - mag_char_width) // 2
mag_y = (TARGET_HEIGHT - mag_char_height) // 2
magneton_env.paste(magneton_char, (mag_x, mag_y), magneton_char)

# Haunter on right environment
haunt_char_width, haunt_char_height = haunter_char.size
haunt_x = (HALF_WIDTH - haunt_char_width) // 2
haunt_y = (TARGET_HEIGHT - haunt_char_height) // 2
haunter_env.paste(haunter_char, (haunt_x, haunt_y), haunter_char)

# Create final 1920x1080 canvas
final_canvas = Image.new("RGB", (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0))

# Paste left half (Magneton in generator room)
temp_left = Image.new("RGB", magneton_env.size, (0, 0, 0))
temp_left.paste(magneton_env, mask=magneton_env.split()[3])
final_canvas.paste(temp_left, (0, 0))

# Paste right half (Haunter in poisoned basement)
temp_right = Image.new("RGB", haunter_env.size, (0, 0, 0))
temp_right.paste(haunter_env, mask=haunter_env.split()[3])
final_canvas.paste(temp_right, (HALF_WIDTH, 0))

# Save
output_path = "haunter/assets/composites/clip_15_split.png"
final_canvas.save(output_path, "PNG")
print(f"✅ Horizontal split-screen saved: {output_path} (1920x1080 16:9)")
print(f"   - Left: Magneton in generator room")
print(f"   - Right: Haunter in poisoned basement")
