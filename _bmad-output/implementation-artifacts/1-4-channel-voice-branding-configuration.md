# Story 1.4: Channel Voice & Branding Configuration

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **content creator**,
I want **each channel to have its own ElevenLabs voice ID and branding settings**,
So that **videos on different channels have distinct voices and intro/outro content** (FR10, FR11).

## Acceptance Criteria

1. **Given** a channel YAML includes `voice_id: "abc123"` and `branding.intro_video: "path/to/intro.mp4"`
   **When** video generation runs for that channel
   **Then** narration uses the specified `voice_id` (FR10)
   **And** branding intro/outro paths are available to the assembly step (FR11)

2. **Given** a channel YAML omits `voice_id`
   **When** configuration is loaded
   **Then** the system uses a default voice ID from global config
   **And** a warning is logged about missing channel-specific voice

3. **Given** two channels have different voice IDs configured
   **When** videos generate for each channel
   **Then** each video uses its channel's specific voice (no cross-channel bleed)

## Tasks / Subtasks

- [x] Task 1: Extend ChannelConfigSchema with branding fields (AC: #1)
  - [x] 1.1: Add `BrandingConfig` nested Pydantic model with `intro_video`, `outro_video`, `watermark_image` fields
  - [x] 1.2: Add `branding: BrandingConfig | None` field to `ChannelConfigSchema`
  - [x] 1.3: Add path validation for branding assets (must be relative paths, no absolute paths)
  - [x] 1.4: Add docstrings documenting branding configuration usage
  - [x] 1.5: Update `ChannelConfigSchema.__repr__` to include voice_id presence (not value)

- [x] Task 2: Add voice/branding columns to Channel database model (AC: #1, #3)
  - [x] 2.1: Add `voice_id` column (String(100), nullable) to Channel model in `app/models.py`
  - [x] 2.2: Add `default_voice_id` column (String(100), nullable) - global default when channel voice is None
  - [x] 2.3: Add `branding_intro_path` column (String(255), nullable)
  - [x] 2.4: Add `branding_outro_path` column (String(255), nullable)
  - [x] 2.5: Add `branding_watermark_path` column (String(255), nullable)
  - [x] 2.6: Update Channel docstring to document voice/branding fields
  - [x] 2.7: Update Channel `__repr__` to show voice_id presence (not value) if set

- [x] Task 3: Create Alembic migration for voice/branding columns (AC: #1)
  - [x] 3.1: Generate new migration file: `alembic revision -m "add_voice_branding_columns"`
  - [x] 3.2: Add `voice_id` as String(100) column (nullable)
  - [x] 3.3: Add `default_voice_id` as String(100) column (nullable)
  - [x] 3.4: Add branding path columns as String(255) (nullable)
  - [x] 3.5: Test migration forward and rollback locally
  - [x] 3.6: Review migration manually before committing

- [x] Task 4: Create VoiceBrandingService for voice/branding resolution (AC: #1, #2, #3)
  - [x] 4.1: Create `app/services/voice_branding_service.py` with `VoiceBrandingService` class
  - [x] 4.2: Implement `get_voice_id(channel_id: str, db: AsyncSession) -> str` method
  - [x] 4.3: Implement fallback logic: channel voice_id → default_voice_id → raise error
  - [x] 4.4: Implement `get_branding_paths(channel_id: str, db: AsyncSession) -> BrandingPaths` method
  - [x] 4.5: Add logging for voice/branding resolution with structlog (AC: #2 warning)
  - [x] 4.6: Create `BrandingPaths` dataclass with intro_path, outro_path, watermark_path fields

- [x] Task 5: Update ChannelConfigLoader to persist voice/branding (AC: #1, #3)
  - [x] 5.1: Update `ChannelConfigLoader.load_channel_config()` to parse branding section
  - [x] 5.2: Update `ChannelConfigLoader.sync_to_database()` to persist voice_id to Channel model
  - [x] 5.3: Update sync to persist branding paths to Channel model
  - [x] 5.4: Add validation: log warning if voice_id missing (AC: #2)
  - [x] 5.5: Add validation: verify branding file paths exist (log warning if not)

- [x] Task 6: Create global configuration for default voice ID (AC: #2)
  - [x] 6.1: Add `DEFAULT_VOICE_ID` to `app/config.py` (loaded from environment variable)
  - [x] 6.2: Document `DEFAULT_VOICE_ID` in `.env.example`
  - [x] 6.3: Update VoiceBrandingService to use global default when channel voice_id is None

- [x] Task 7: Write comprehensive tests (AC: #1, #2, #3)
  - [x] 7.1: Create `tests/test_voice_branding_service.py`
  - [x] 7.2: Test get_voice_id returns channel-specific voice when set
  - [x] 7.3: Test get_voice_id falls back to default when channel voice is None (AC: #2)
  - [x] 7.4: Test get_voice_id logs warning when using default (AC: #2)
  - [x] 7.5: Test get_branding_paths returns channel-specific paths
  - [x] 7.6: Test get_branding_paths returns None for missing branding config
  - [x] 7.7: Test two channels return different voice IDs (AC: #3 isolation)
  - [x] 7.8: Create `tests/test_channel_config_branding.py`
  - [x] 7.9: Test YAML with branding section parses correctly
  - [x] 7.10: Test YAML without branding section uses defaults
  - [x] 7.11: Test invalid branding paths are validated
  - [x] 7.12: Test migration forward and rollback

## Dev Notes

### Critical Technical Requirements

**Technology Stack (MANDATORY versions from project-context.md):**
- Python 3.10+ (use `str | None` syntax, NOT `Optional[str]`)
- SQLAlchemy >=2.0.0 (async engine, `Mapped[]` annotations)
- Pydantic >=2.8.0 (v2 syntax: `model_config = ConfigDict(...)`, nested models)
- structlog >=23.2.0 (JSON output, context binding)
- pytest >=7.4.0, pytest-asyncio >=0.21.0

**Voice ID Pattern (from epics.md FR10):**
```python
# ElevenLabs voice ID is a string identifier
# Example: "21m00Tcm4TlvDq8ikWAM" (Rachel voice)
# Stored directly in database (NOT encrypted - not sensitive)
voice_id: str | None = Field(default=None)
```

**Branding Configuration Pattern (from epics.md FR11):**
```yaml
# channel_configs/pokechannel1.yaml
branding:
  intro_video: "channel_assets/intro_v2.mp4"  # Relative to workspace
  outro_video: "channel_assets/outro_v2.mp4"
  watermark_image: "channel_assets/watermark.png"  # Optional
```

**Default Voice Fallback (AC #2):**
```python
async def get_voice_id(self, channel_id: str, db: AsyncSession) -> str:
    """Get voice ID for channel with fallback to default.

    Resolution order:
    1. Channel-specific voice_id
    2. Global DEFAULT_VOICE_ID from environment
    3. Raise ConfigurationError if no default set

    Logs warning when falling back to default (AC #2).
    """
    channel = await self._get_channel(channel_id, db)

    if channel.voice_id:
        return channel.voice_id

    # Fallback to default
    default = get_default_voice_id()
    if default:
        log.warning(
            "using_default_voice_id",
            channel_id=channel_id,
            default_voice_id=default[:8] + "...",  # Truncate for logging
        )
        return default

    raise ConfigurationError(f"No voice_id configured for channel {channel_id} and no DEFAULT_VOICE_ID set")
```

### Anti-Patterns to AVOID

```python
# WRONG: Hardcoded voice IDs
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # NEVER hardcode

# WRONG: Absolute paths for branding
branding:
  intro_video: "/home/user/videos/intro.mp4"  # WRONG - not portable

# WRONG: Encrypted voice IDs (not sensitive)
voice_id_encrypted: Mapped[bytes | None]  # WRONG - voice IDs are public

# WRONG: Sharing voice state between channels
class VoiceManager:
    current_voice_id = None  # WRONG - class-level state causes cross-channel bleed

# CORRECT: Per-channel resolution from database
voice_id = await voice_branding_service.get_voice_id(channel_id, db)
```

### Project Structure Notes

**File Locations (MANDATORY from project-context.md):**
```
app/
├── models.py                    # MODIFY: Add voice_id, branding path columns
├── config.py                    # MODIFY: Add DEFAULT_VOICE_ID
├── schemas/
│   └── channel_config.py        # MODIFY: Add BrandingConfig, voice_id field
├── services/
│   ├── __init__.py             # MODIFY: Export VoiceBrandingService
│   ├── channel_config_loader.py # MODIFY: Sync voice/branding to database
│   └── voice_branding_service.py # NEW: VoiceBrandingService class

alembic/versions/
└── xxx_add_voice_branding_columns.py  # NEW: Migration

tests/
├── test_voice_branding_service.py     # NEW: VoiceBrandingService tests
└── test_channel_config_branding.py    # NEW: Branding schema tests
```

**Naming Conventions:**
- Service classes: `{Domain}Service` (e.g., `VoiceBrandingService`)
- Dataclasses: `{Domain}Paths`, `{Domain}Config` (e.g., `BrandingPaths`)
- Database columns: snake_case (e.g., `voice_id`, `branding_intro_path`)
- Config classes: Nested Pydantic models (e.g., `BrandingConfig` inside `ChannelConfigSchema`)

### Previous Story (1.3) Learnings

**Patterns Established:**
- Use `datetime.now(UTC)` for timezone-aware timestamps
- Use `Mapped[type]` annotations for SQLAlchemy 2.0 models
- Keep `expire_on_commit=False` in session factory
- Use structlog for all logging
- All tests should be async with pytest-asyncio
- Use `asyncio.to_thread()` for blocking I/O in async context

**Code Conventions Applied:**
- Docstrings on all public classes and functions
- Type hints on all parameters and return values
- `__repr__` method on models for debugging (but NOT exposing sensitive data)

**Testing Patterns:**
- Use `aiosqlite` for in-memory SQLite testing
- Create fixtures in `tests/conftest.py`
- Test both success and failure scenarios
- Test edge cases (missing config, fallback behavior)

### Git Intelligence from Stories 1.1-1.3

**Files Created in Previous Stories:**
- `app/__init__.py` - Package with `__all__` exports
- `app/database.py` - Async engine, session factory
- `app/models.py` - Channel model (120 lines - room to add columns)
- `app/schemas/__init__.py`, `app/schemas/channel_config.py` - Pydantic schemas (already has voice_id!)
- `app/services/__init__.py`, `app/services/channel_config_loader.py` - Config loader
- `app/services/credential_service.py` - Credential encryption/decryption
- `app/utils/encryption.py` - EncryptionService
- `alembic/` - Migration infrastructure established
- `tests/conftest.py` - Shared async fixtures

**Important Discovery: voice_id Already Exists in Schema!**
The `ChannelConfigSchema` in `app/schemas/channel_config.py` already has:
```python
voice_id: str | None = Field(default=None)
```
This means:
- YAML parsing for voice_id is already working
- Need to ADD: branding nested model, database columns, sync logic

**Dependencies Already in pyproject.toml:**
- SQLAlchemy, asyncpg, Alembic (database)
- pytest, pytest-asyncio, aiosqlite (testing)
- pydantic, pyyaml, structlog

**This story should ADD (not duplicate):**
- `BrandingConfig` nested model in channel_config.py
- Voice/branding columns to Channel model
- New Alembic migration
- `VoiceBrandingService` for resolution logic
- Sync logic in ChannelConfigLoader
- `DEFAULT_VOICE_ID` environment variable

### Architecture Requirements

**From architecture.md - Per-Channel Voice Selection:**
- Each channel has its own ElevenLabs voice_id
- Voice ID is passed to `generate_audio.py` CLI script
- Workers retrieve voice_id from database before calling script

**From architecture.md - Channel-Specific Branding:**
- Intro/outro videos applied during assembly step
- Paths stored in database per channel
- Assembly step reads branding paths from Channel model

**From epics.md - FR10 & FR11:**
- FR10: Videos use voice_id from channel configuration
- FR11: Intro/outro videos applied per channel

### Environment Variables

**New Required Variable:**
```
DEFAULT_VOICE_ID=<elevenlabs-voice-id>  # Fallback voice ID (optional but recommended)
```

**Documentation in .env.example:**
```bash
# ElevenLabs voice configuration
# Get voice IDs from: https://api.elevenlabs.io/v1/voices
DEFAULT_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # Optional: Default voice when channel voice not set
```

### Channel YAML Format (After This Story)

```yaml
# channel_configs/pokechannel1.yaml
channel_id: pokechannel1
channel_name: "Pokémon Nature Docs"
notion_database_id: "abc123..."
priority: normal
is_active: true

# Voice configuration (FR10)
voice_id: "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs voice ID for narration

# Storage configuration
storage_strategy: notion
max_concurrent: 2

# Branding configuration (FR11)
branding:
  intro_video: "channel_assets/intro_v2.mp4"
  outro_video: "channel_assets/outro_v2.mp4"
  watermark_image: "channel_assets/watermark.png"  # Optional

# Budget (optional)
budget_daily_usd: 50.00
```

### Testing Requirements

**Required Test Coverage:**
- Voice ID resolution with channel-specific voice
- Voice ID resolution with fallback to default (+ warning logging)
- Voice ID isolation between channels (AC #3)
- Branding path resolution
- Branding missing gracefully handled
- YAML branding section parsing
- Migration forward and rollback

**Test File Structure:**
```python
# tests/test_voice_branding_service.py
import pytest
from app.services.voice_branding_service import VoiceBrandingService

class TestVoiceBrandingService:
    @pytest.mark.asyncio
    async def test_get_voice_id_channel_specific(self, db_session): ...

    @pytest.mark.asyncio
    async def test_get_voice_id_fallback_to_default(self, db_session, caplog): ...

    @pytest.mark.asyncio
    async def test_get_voice_id_logs_warning_on_fallback(self, db_session, caplog): ...

    @pytest.mark.asyncio
    async def test_get_branding_paths_returns_paths(self, db_session): ...

    @pytest.mark.asyncio
    async def test_get_branding_paths_returns_none_when_missing(self, db_session): ...

    @pytest.mark.asyncio
    async def test_voice_isolation_between_channels(self, db_session): ...

# tests/test_channel_config_branding.py
import pytest
from app.schemas.channel_config import ChannelConfigSchema, BrandingConfig

class TestBrandingConfig:
    def test_branding_section_parses_correctly(self): ...
    def test_branding_section_optional(self): ...
    def test_branding_paths_validated(self): ...
```

### References

- [Source: _bmad-output/planning-artifacts/epics.md - Story 1.4 Acceptance Criteria]
- [Source: _bmad-output/planning-artifacts/epics.md - FR10: Per-channel voice selection]
- [Source: _bmad-output/planning-artifacts/epics.md - FR11: Channel-specific branding]
- [Source: _bmad-output/planning-artifacts/architecture.md - Per-Channel Configuration]
- [Source: _bmad-output/project-context.md - Technology Stack: SQLAlchemy >=2.0.0, Pydantic >=2.8.0]
- [Source: app/schemas/channel_config.py - Existing ChannelConfigSchema with voice_id field]
- [Source: app/models.py - Existing Channel model structure]
- [Source: _bmad-output/implementation-artifacts/1-3-per-channel-encrypted-credentials-storage.md - Previous story patterns]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

None

### Completion Notes List

- All 7 tasks completed successfully
- All tests pass including 65 new tests for voice/branding (24 VoiceBrandingService + 24 BrandingConfig + 17 config module)
- Migration file created: `alembic/versions/20260110_0003_003_add_voice_branding_columns.py`
- VoiceBrandingService implements fallback logic with warning logging
- BrandingConfig schema validates relative paths only (no absolute paths or path traversal)
- DEFAULT_VOICE_ID documented in `.env.example`
- Code review fixes applied: added migration tests, fixed test assertions

### File List

**New Files:**
- `app/config.py` - Global configuration with DEFAULT_VOICE_ID
- `app/services/voice_branding_service.py` - VoiceBrandingService class with BrandingPaths dataclass
- `alembic/versions/20260110_0003_003_add_voice_branding_columns.py` - Database migration
- `tests/test_voice_branding_service.py` - 24 tests for VoiceBrandingService (includes migration tests)
- `tests/test_channel_config_branding.py` - 24 tests for BrandingConfig schema
- `tests/test_config.py` - 17 tests for configuration module

**Modified Files:**
- `app/schemas/channel_config.py` - Added BrandingConfig nested model, updated voice_id field, updated __repr__
- `app/schemas/__init__.py` - Export BrandingConfig
- `app/models.py` - Added voice_id, default_voice_id, branding_intro_path, branding_outro_path, branding_watermark_path columns
- `app/services/__init__.py` - Export VoiceBrandingService, BrandingPaths, ConfigurationError
- `app/services/channel_config_loader.py` - Added sync_to_database(), validate_branding_files() methods
- `scripts/.env.example` - Added DEFAULT_VOICE_ID, DATABASE_URL, FERNET_KEY documentation
- `scripts/create_composite.py` - Added output directory creation
