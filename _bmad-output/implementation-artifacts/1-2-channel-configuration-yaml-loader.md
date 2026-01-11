# Story 1.2: Channel Configuration YAML Loader

Status: done

## Story

As a **system administrator**,
I want **to add new channels by creating YAML configuration files without code changes**,
So that **I can scale to 10+ channels by simply adding config files** (FR15).

## Acceptance Criteria

1. **Given** a YAML file exists at `channel_configs/{channel_id}.yaml`
   **When** the system starts or reloads configuration
   **Then** the channel configuration is parsed and validated
   **And** required fields are enforced: `channel_id`, `channel_name`, `notion_database_id`
   **And** optional fields have defaults: `priority` (normal), `is_active` (true)

2. **Given** a YAML file has invalid syntax or missing required fields
   **When** configuration loading is attempted
   **Then** the system logs a clear error message with file path and validation failure
   **And** the system continues operating with other valid channels

3. **Given** a new `{channel_id}.yaml` file is added
   **When** configuration is reloaded
   **Then** the new channel becomes available without application restart (FR15)

## Tasks / Subtasks

- [x] Task 1: Create Pydantic schema for channel configuration (AC: #1)
  - [x] 1.1: Create `app/schemas/channel_config.py` with `ChannelConfigSchema` Pydantic model
  - [x] 1.2: Define required fields: `channel_id` (str), `channel_name` (str), `notion_database_id` (str)
  - [x] 1.3: Define optional fields with defaults: `priority` (str, default="normal"), `is_active` (bool, default=True)
  - [x] 1.4: Add additional optional fields from architecture: `voice_id` (str|None), `storage_strategy` (str, default="notion"), `max_concurrent` (int, default=2), `budget_daily_usd` (Decimal|None)
  - [x] 1.5: Use Pydantic v2 syntax: `model_config = ConfigDict(...)`, NOT `class Config:`
  - [x] 1.6: Add field validators for `channel_id` format (alphanumeric + underscore, max 50 chars)
  - [x] 1.7: Add validator for `priority` values: "high", "normal", "low"
  - [x] 1.8: Add validator for `storage_strategy` values: "notion", "r2"

- [x] Task 2: Create YAML loader service (AC: #1, #2)
  - [x] 2.1: Create `app/services/channel_config_loader.py` with `ChannelConfigLoader` class
  - [x] 2.2: Implement `load_channel_config(file_path: Path) -> ChannelConfigSchema | None` method
  - [x] 2.3: Use PyYAML (`yaml.safe_load()`) for parsing YAML files
  - [x] 2.4: Handle YAML syntax errors with structured logging (file path, line number, error message)
  - [x] 2.5: Handle Pydantic validation errors with structured logging (file path, field errors)
  - [x] 2.6: Return `None` and log error on failure (do NOT raise exceptions to caller)

- [x] Task 3: Implement config directory scanner (AC: #1, #2, #3)
  - [x] 3.1: Implement `load_all_configs(config_dir: Path) -> dict[str, ChannelConfigSchema]` method
  - [x] 3.2: Scan `channel_configs/` directory for `*.yaml` files
  - [x] 3.3: Load each YAML file using `load_channel_config()`
  - [x] 3.4: Skip files that fail validation (continue with valid configs)
  - [x] 3.5: Return dictionary mapping `channel_id` to config object
  - [x] 3.6: Log summary: loaded N configs, skipped M invalid files

- [x] Task 4: Implement config reload functionality (AC: #3)
  - [x] 4.1: Create singleton `ConfigManager` class to hold current configs
  - [x] 4.2: Implement `reload()` method that rescans config directory
  - [x] 4.3: Add `get_config(channel_id: str) -> ChannelConfigSchema | None` accessor method
  - [x] 4.4: Add `get_all_configs() -> dict[str, ChannelConfigSchema]` accessor method
  - [x] 4.5: Implement thread-safe reload using `asyncio.Lock`
  - [x] 4.6: Log config changes: new configs added, existing configs updated

- [x] Task 5: Create sample channel config files (AC: #1)
  - [x] 5.1: Create `channel_configs/` directory (if not exists)
  - [x] 5.2: Create `channel_configs/_example.yaml` with full schema documentation as comments
  - [x] 5.3: Include all required and optional fields with descriptions
  - [x] 5.4: Add `.gitkeep` to ensure directory is tracked

- [x] Task 6: Write comprehensive tests (AC: #1, #2, #3)
  - [x] 6.1: Create `tests/test_channel_config.py`
  - [x] 6.2: Test valid YAML loading with all required fields
  - [x] 6.3: Test valid YAML with all optional fields
  - [x] 6.4: Test missing required field (`channel_id`, `channel_name`, `notion_database_id`)
  - [x] 6.5: Test invalid YAML syntax (malformed YAML)
  - [x] 6.6: Test invalid field values (invalid priority, invalid channel_id format)
  - [x] 6.7: Test config directory scanning with mixed valid/invalid files
  - [x] 6.8: Test config reload detects new files
  - [x] 6.9: Test ConfigManager thread-safety
  - [x] 6.10: Test default value application

## Dev Notes

### Critical Technical Requirements

**Technology Stack (MANDATORY versions from project-context.md):**
- Python 3.10+ (match type `|` syntax)
- Pydantic >=2.8.0 (v2 syntax: `model_config = ConfigDict(...)`, NOT `class Config:`)
- PyYAML (use `yaml.safe_load()` for security)
- structlog >=23.2.0 (JSON output, context binding)

**Pydantic v2 Pattern (MANDATORY):**
```python
from pydantic import BaseModel, ConfigDict, Field, field_validator
from decimal import Decimal

class ChannelConfigSchema(BaseModel):
    """Channel configuration loaded from YAML file."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_default=True,
    )

    # Required fields
    channel_id: str = Field(..., min_length=1, max_length=50)
    channel_name: str = Field(..., min_length=1, max_length=100)
    notion_database_id: str = Field(..., min_length=1)

    # Optional fields with defaults
    priority: str = Field(default="normal")
    is_active: bool = Field(default=True)
    voice_id: str | None = Field(default=None)
    storage_strategy: str = Field(default="notion")
    max_concurrent: int = Field(default=2, ge=1, le=10)
    budget_daily_usd: Decimal | None = Field(default=None, ge=0)

    @field_validator("channel_id")
    @classmethod
    def validate_channel_id(cls, v: str) -> str:
        """Channel ID must be alphanumeric with underscores only."""
        import re
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("channel_id must be alphanumeric with underscores only")
        return v.lower()  # Normalize to lowercase

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        """Priority must be high, normal, or low."""
        allowed = {"high", "normal", "low"}
        if v.lower() not in allowed:
            raise ValueError(f"priority must be one of: {allowed}")
        return v.lower()

    @field_validator("storage_strategy")
    @classmethod
    def validate_storage_strategy(cls, v: str) -> str:
        """Storage strategy must be notion or r2."""
        allowed = {"notion", "r2"}
        if v.lower() not in allowed:
            raise ValueError(f"storage_strategy must be one of: {allowed}")
        return v.lower()
```

**YAML Loading Pattern:**
```python
import yaml
from pathlib import Path
import structlog

log = structlog.get_logger()

def load_channel_config(file_path: Path) -> ChannelConfigSchema | None:
    """Load and validate channel config from YAML file.

    Args:
        file_path: Path to YAML configuration file.

    Returns:
        Validated ChannelConfigSchema or None if invalid.
    """
    try:
        with file_path.open("r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)

        if raw_config is None:
            log.warning("config_file_empty", file=str(file_path))
            return None

        config = ChannelConfigSchema.model_validate(raw_config)
        log.info("config_loaded", channel_id=config.channel_id, file=str(file_path))
        return config

    except yaml.YAMLError as e:
        log.error(
            "yaml_parse_error",
            file=str(file_path),
            error=str(e),
            line=getattr(e, "problem_mark", None).line if hasattr(e, "problem_mark") else None,
        )
        return None

    except ValidationError as e:
        log.error(
            "config_validation_error",
            file=str(file_path),
            errors=e.errors(),
        )
        return None
```

**ConfigManager Singleton Pattern:**
```python
import asyncio
from pathlib import Path

class ConfigManager:
    """Thread-safe configuration manager with reload support."""

    _instance: "ConfigManager | None" = None
    _lock: asyncio.Lock

    def __init__(self, config_dir: Path):
        self._config_dir = config_dir
        self._configs: dict[str, ChannelConfigSchema] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls, config_dir: Path | None = None) -> "ConfigManager":
        """Get singleton instance."""
        if cls._instance is None:
            if config_dir is None:
                config_dir = Path("channel_configs")
            cls._instance = cls(config_dir)
        return cls._instance

    async def reload(self) -> None:
        """Reload all configurations from disk."""
        async with self._lock:
            new_configs = load_all_configs(self._config_dir)

            # Log changes
            added = set(new_configs.keys()) - set(self._configs.keys())
            removed = set(self._configs.keys()) - set(new_configs.keys())

            if added:
                log.info("configs_added", channel_ids=list(added))
            if removed:
                log.info("configs_removed", channel_ids=list(removed))

            self._configs = new_configs

    def get_config(self, channel_id: str) -> ChannelConfigSchema | None:
        """Get config for specific channel."""
        return self._configs.get(channel_id)

    def get_all_configs(self) -> dict[str, ChannelConfigSchema]:
        """Get all loaded configs."""
        return self._configs.copy()
```

### Anti-Patterns to AVOID

```python
# WRONG: Pydantic v1 syntax
class ChannelConfigSchema(BaseModel):
    class Config:  # OLD SYNTAX - DO NOT USE
        str_strip_whitespace = True

# WRONG: Using yaml.load() without Loader (security risk)
config = yaml.load(f)  # WRONG - use yaml.safe_load(f)

# WRONG: Raising exceptions on invalid config (breaks other channels)
def load_channel_config(file_path):
    config = yaml.safe_load(...)
    return ChannelConfigSchema(**config)  # Raises on validation error - WRONG

# WRONG: Not using type hints
def load_channel_config(file_path):  # Missing type hints - WRONG
    ...

# WRONG: Blocking I/O in async context
async def reload():
    with open(file_path) as f:  # Blocking I/O in async - WRONG
        ...
# CORRECT: Use asyncio.to_thread() for file I/O or sync context
```

### Project Structure Notes

**File Locations (MANDATORY from project-context.md):**
```
app/
├── schemas/                 # NEW: Pydantic schemas
│   ├── __init__.py
│   └── channel_config.py    # THIS STORY: ChannelConfigSchema
├── services/
│   ├── __init__.py
│   └── channel_config_loader.py  # THIS STORY: ConfigLoader, ConfigManager
└── ...

channel_configs/             # NEW: YAML config files directory
├── _example.yaml            # THIS STORY: Documented example config
└── .gitkeep

tests/
└── test_channel_config_loader.py  # THIS STORY: Config loading tests
```

**Naming Conventions:**
- Schema classes: `{Model}Schema` suffix (e.g., `ChannelConfigSchema`)
- Service classes: `{Domain}{Action}` (e.g., `ChannelConfigLoader`)
- Config files: `{channel_id}.yaml` (lowercase, underscores allowed)
- Test functions: `test_{scenario}` (e.g., `test_load_valid_config`)

### Previous Story (1.1) Learnings

**Patterns Established:**
- Use `datetime.now(UTC)` for timezone-aware timestamps (NOT deprecated `utcnow()`)
- Use `Mapped[type]` annotations for SQLAlchemy 2.0 models
- Keep `expire_on_commit=False` in session factory
- Use structlog for all logging
- All tests should be async with pytest-asyncio

**Code Conventions Applied:**
- Docstrings on all public classes and functions
- Type hints on all parameters and return values
- Import from `collections.abc` for `AsyncGenerator`
- `__repr__` method on models for debugging

**Testing Patterns:**
- Use `aiosqlite` for in-memory SQLite testing
- Create fixtures in `tests/conftest.py`
- Test both success and failure scenarios
- Test edge cases (empty files, invalid data)

### Git Intelligence from Story 1.1

**Files Created:**
- `app/__init__.py` - Package with `__all__` exports
- `app/database.py` - Async engine, session factory
- `app/models.py` - Channel model (77 lines - plenty of room to add more)
- `alembic/` - Migration infrastructure
- `tests/conftest.py` - Shared async fixtures

**Dependencies Added to pyproject.toml:**
- SQLAlchemy, asyncpg, Alembic (database)
- pytest, pytest-asyncio, aiosqlite (testing)

**This story should ADD (not duplicate):**
- PyYAML for config parsing
- New `app/schemas/` directory for Pydantic schemas
- New `channel_configs/` directory

### Architecture Requirements

**From architecture.md - Channel Configuration:**
- YAML files in `channel_configs/{channel_id}.yaml` (version controlled)
- Hot reload support for channel config changes (optional but nice-to-have)
- Configuration validation on startup (prevent runtime config errors)

**Required Config Fields (from epics.md Story 1.2):**
- `channel_id` - Business identifier (e.g., "poke1")
- `channel_name` - Display name
- `notion_database_id` - Notion integration

**Optional Config Fields (from architecture.md - Per-Channel Config):**
- `priority` - Processing priority ("high", "normal", "low")
- `is_active` - Enable/disable channel
- `voice_id` - ElevenLabs voice (for Story 1.4)
- `storage_strategy` - "notion" or "r2" (for Story 1.5)
- `max_concurrent` - Parallel task limit (for Story 1.6)
- `budget_daily_usd` - Daily spending limit

**Example YAML Structure (from architecture.md):**
```yaml
# channel_configs/pokechannel1.yaml
channel_id: pokechannel1
channel_name: "Pokemon Nature Docs"
notion_database_id: "abc123..."
youtube_channel_id: "UC123..."  # For future YouTube integration
priority: normal
is_active: true
schedule: "daily"  # Future: daily, weekly, manual
budget_daily_usd: 50.00
```

### Testing Requirements

**Required Test Coverage:**
- Valid config loading with all fields
- Valid config with only required fields (defaults applied)
- Missing required field validation errors
- Invalid field value validation errors
- YAML syntax errors
- Empty YAML file handling
- Directory scanning with mixed valid/invalid files
- Config reload detecting new/removed files
- Thread-safe reload operations
- Default value application

**Test File Structure:**
```python
# tests/test_channel_config_loader.py
import pytest
from pathlib import Path
from app.schemas.channel_config import ChannelConfigSchema
from app.services.channel_config_loader import load_channel_config, ConfigManager

class TestChannelConfigSchema:
    """Tests for Pydantic schema validation."""

    def test_valid_config_all_fields(self): ...
    def test_valid_config_required_only(self): ...
    def test_missing_channel_id(self): ...
    def test_invalid_priority(self): ...
    def test_channel_id_normalized_lowercase(self): ...

class TestLoadChannelConfig:
    """Tests for YAML file loading."""

    def test_load_valid_yaml(self, tmp_path): ...
    def test_load_invalid_yaml_syntax(self, tmp_path): ...
    def test_load_empty_file(self, tmp_path): ...
    def test_load_missing_file(self, tmp_path): ...

class TestConfigManager:
    """Tests for config manager singleton."""

    @pytest.mark.asyncio
    async def test_reload_detects_new_config(self, tmp_path): ...
    @pytest.mark.asyncio
    async def test_get_config_returns_none_for_unknown(self): ...
```

### Environment Variables

**No new environment variables required for this story.**

Config files are loaded from filesystem (version controlled) per architecture decision.

### Dependencies to Add

```toml
# pyproject.toml - add to dependencies
dependencies = [
    # ... existing ...
    "pyyaml>=6.0",  # YAML parsing
]
```

### References

- [Source: _bmad-output/planning-artifacts/architecture.md - Environment Configuration Strategy]
- [Source: _bmad-output/planning-artifacts/architecture.md - Per-Channel Config YAML]
- [Source: _bmad-output/project-context.md - Technology Stack: Pydantic v2]
- [Source: _bmad-output/planning-artifacts/epics.md - Story 1.2 Acceptance Criteria]
- [Source: Pydantic v2 Documentation - ConfigDict, field_validator]
- [Source: PyYAML Documentation - safe_load]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A - No debugging issues encountered.

### Completion Notes List

- Implemented `ChannelConfigSchema` with Pydantic v2 syntax following the exact pattern from Dev Notes
- All validators (channel_id, priority, storage_strategy) normalize values to lowercase
- Used `str_strip_whitespace=True` in ConfigDict to handle whitespace in YAML values
- `ChannelConfigLoader` class handles YAML parsing with proper error logging using structlog
- Invalid YAML files return `None` instead of raising exceptions (graceful failure)
- `ConfigManager` singleton provides async-safe reload via `asyncio.Lock`
- Files starting with underscore are skipped (e.g., `_example.yaml`)
- Comprehensive test coverage with 38 tests (20 schema + 11 loader + 7 manager)
- All tests pass - no regressions

### Code Review Fixes Applied (2026-01-10)

- **Fixed blocking I/O in async context**: `reload()` now uses `asyncio.to_thread()` for file I/O
- **Added `.yml` extension support**: Config loader now scans for both `*.yaml` and `*.yml` files
- **Added `__repr__` method**: ChannelConfigSchema now has proper string representation for debugging
- **Fixed misleading test name**: Renamed `test_reload_thread_safe` to `test_reload_concurrent_safe`
- **Reverted brownfield violation**: Changes to `scripts/create_composite.py` were reverted (not part of this story)

### File List

**New Files:**
- `app/schemas/__init__.py` - Schema package exports
- `app/schemas/channel_config.py` - ChannelConfigSchema Pydantic model
- `app/services/__init__.py` - Services package exports
- `app/services/channel_config_loader.py` - ChannelConfigLoader and ConfigManager classes
- `channel_configs/_example.yaml` - Documented example configuration template
- `channel_configs/.gitkeep` - Ensures directory is tracked by git
- `tests/test_channel_config.py` - Comprehensive tests (37 tests)

**Modified Files:**
- `pyproject.toml` - Added dependencies: pydantic>=2.8.0, pyyaml>=6.0, structlog>=23.2.0

## Change Log

- 2026-01-10: Implemented Story 1.2 - Channel Configuration YAML Loader (all tasks complete)
- 2026-01-10: Code review fixes applied - async I/O fix, .yml support, __repr__ method, test naming
