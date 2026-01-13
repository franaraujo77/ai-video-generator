# Generic "Dark Channel" Video Pipeline

This is a generalized version of the Pokémon pipeline, designed for creating faceless niche content (History, True Crime, Science, Horror).

## How to Use

1.  **Topic Research:**
    *   Open `generic_prompts/1_topic_research.md`.
    *   Provide your topic (e.g., "The Dyatlov Pass Incident").
    *   Save output to `dyatlov-pass/01_topic_research.md`.

2.  **Scripting:**
    *   Open `generic_prompts/2_script_development.md`.
    *   Paste the Research content.
    *   Select a story concept.
    *   Save output to `dyatlov-pass/02_script.md`.

3.  **Asset Planning:**
    *   Open `generic_prompts/3_visual_asset_planning.md`.
    *   Paste the Script.
    *   Save output to `dyatlov-pass/03_assets.md`.

4.  **Asset Generation (Automated):**
    *   Open `generic_prompts/3.5_automated_asset_generation.md`.
    *   Provide the topic slug ("dyatlov-pass").
    *   The agent will generate images using the scripts.

5.  **Video & Audio:**
    *   Use the existing `prompts/4.5_generate_videos_agent.md` and `prompts/5.5_generate_audio_agent.md`.
    *   Just replace `{pokemon}` with your topic slug when instructing the agent.

## Folder Structure
Instead of `{pokemon}/`, you will have `{topic-slug}/` (e.g., `titanic/`, `black-holes/`).
The scripts (`generate_asset.py`, etc.) work with any path, so they don't need modification.
