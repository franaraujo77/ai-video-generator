# Architecture Pattern
**Agentic Pipeline / Orchestration**
- **Orchestrator:** AI Agents (following SOPs in `prompts/`).
- **Executors:** Stateless Python CLI scripts (in `scripts/`).
- **State Store:** The File System (Markdown files for text, distinct folders for media).
