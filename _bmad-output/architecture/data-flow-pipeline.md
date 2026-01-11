# Data Flow Pipeline

1.  **Research (Agent):** Reads `1_research.md` -> Writes `01_research.md` (Text).
2.  **Scripting (Agent):** Reads Research -> Writes `02_story_script.md` (Text).
3.  **Asset Gen (Script):** Reads Prompts -> Calls Gemini -> Writes `assets/*.png`.
4.  **Compositing (Script):** Reads `char.png` + `env.png` -> Writes `composite.png` (16:9).
5.  **Video Gen (Script):** Reads `composite.png` -> Calls Kling -> Writes `video.mp4`.
6.  **Audio Gen (Script):** Reads Script -> Calls ElevenLabs -> Writes `audio.mp3`.
7.  **Assembly (Script):** Reads `manifest.json` -> Calls FFmpeg -> Writes `final.mp4`.
