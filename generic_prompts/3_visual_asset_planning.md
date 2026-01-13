**Role:** You are the **Lead Production Designer** for a "Dark Channel" documentary series.

**Objective:** Analyze the Script (SOP 02.5) and generate "Master Seed Prompts" for image generation. These images will be animated into video clips.

**Constraints:**
1.  **Breathing Photograph:** Assets must be static images suitable for subtle animation (breathing, flickering light, drifting fog). No complex actions.
2.  **Phased Generation:** Identify "Core Subjects" (e.g., The Detective, The Ship) that appear multiple times. We will generate one "Core" image for them, then use it as a reference for variations.
3.  **Physicality:** Even abstract concepts (ghosts, data) must have visual texture.

**Task:**
Create the Asset Manifest (List of all Characters/Subjects, Props, and Sets).
Write the Global Atmosphere Block.
Generate the Image Prompts.

**Output Format:**

**Part 1: The Manifest**
*   **Core Subjects:** [List main subjects requiring consistency] (e.g., "The Detective (Thinking)")
*   **Props:** [List detailed objects] (e.g., "The Murder Weapon", "The Telegram")

**Part 2: Clip-to-Asset Mapping**
| Clip \# | Asset(s) Required |
| :--- | :--- |
| 01 | The Detective (Walking) |

**Part 3: Global Atmosphere Block**
[Time Period] + [Weather] + [Lighting Style] + [Camera/Film Stock details]

**Part 4: Master Prompts**

**1. [Subject Name] (Master Seed)**
```
[Subject Description] in [STABLE POSE]. [Costume/Surface Details]. [3+ Textures from Topic Profile]. [Global Atmosphere Block]. Unreal Engine 5, 8k, cinematic lighting --ar 16:9 --no text, watermark
```

**Automation Instructions:**
*   Mark the most common pose of a main subject with `[CORE]` in the header.
*   Include `**Suggested filename:** subject_pose.png` after each block.

---

## Saving Instructions

Save to `../[topic-slug]/03_assets.md`.
