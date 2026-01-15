---
story_key: '3-2-filesystem-organization-path-helpers'
epic_id: '3'
story_id: '2'
title: 'Filesystem Organization & Path Helpers'
status: 'ready-for-dev'
priority: 'critical'
story_points: 2
created_at: '2026-01-15'
completed_at: ''
assigned_to: ''
dependencies: ['3-1-cli-script-wrapper-async-execution']
blocks: ['3-3', '3-4', '3-5', '3-6', '3-7', '3-8']
ready_for_dev: true
---

# Story 3.2: Filesystem Organization & Path Helpers

**Epic:** 3 - Video Generation Pipeline
**Priority:** Critical
**Story Points:** 2
**Status:** Ready for Development ⚙️

## Story Description

**As a** worker process orchestrating video generation,
**I want to** have standardized filesystem path helpers that enforce channel-organized directory structure,
**So that** CLI scripts receive consistent file paths, assets are isolated per channel, and storage cleanup is predictable.

## Context & Background

The video generation pipeline generates numerous assets per video project:
- 22 image assets (characters, environments, props)
- 18 composite images (16:9 format for video generation)
- 18 video clips (10-second MP4 files)
- 18 narration audio files (MP3)
- 18 sound effect files (WAV)
- 1 final assembled video (MP4)

**Critical Storage Requirements:**
1. **Channel Isolation:** Each channel's assets must be completely isolated (multi-channel system)
2. **CLI Script Compatibility:** Filesystem paths expected by existing CLI scripts (brownfield constraint)
3. **Predictable Structure:** Standardized paths for cleanup, debugging, and manual inspection
4. **Auto-Creation:** Directories must be created automatically when accessed
5. **Railway Persistence:** Must use Railway's persistent volume (`/app/workspace/`)

**Referenced Architecture:**
- Architecture Decision: Asset Storage Strategy (Filesystem with Channel Organization) - lines 361-366
- project-context.md: Filesystem Helpers (Required Implementation) - lines 200-277
- project-context.md: Integration Utilities (MANDATORY) - lines 117-198

**Rationale for Filesystem Storage:**
- Preserves brownfield CLI script interfaces (scripts expect filesystem paths, not database blobs)
- Proven pattern from existing single-project implementation
- Simplifies debugging (can inspect assets directly on Railway via shell)
- Natural fit for video/audio files (database blob storage inefficient for large files)

## Acceptance Criteria

### Scenario 1: Channel-Organized Directory Structure
**Given** a channel_id "poke1" and project_id "vid_abc123"
**When** path helpers are used to construct directories
**Then** the directory structure should be:
- ✅ `/app/workspace/channels/poke1/projects/vid_abc123/`
- ✅ Subdirectories: `assets/`, `videos/`, `audio/`, `sfx/`
- ✅ Asset subdirectories: `assets/characters/`, `assets/environments/`, `assets/props/`, `assets/composites/`
- ✅ All directories created automatically with `mkdir(parents=True, exist_ok=True)`

### Scenario 2: Path Helpers Return Path Objects
**Given** a worker needs to construct an asset path
**When** `get_asset_dir(channel_id, project_id)` is called
**Then** the helper should:
- ✅ Return a `pathlib.Path` object (not string)
- ✅ Auto-create the directory if it doesn't exist
- ✅ Return consistent paths across multiple calls (idempotent)

### Scenario 3: Subdirectory Specialization
**Given** a worker needs specific asset subdirectories
**When** specialized helpers are called
**Then** the correct subdirectories should be created:
- ✅ `get_character_dir()` → `assets/characters/`
- ✅ `get_environment_dir()` → `assets/environments/`
- ✅ `get_props_dir()` → `assets/props/`
- ✅ `get_composite_dir()` → `assets/composites/`

### Scenario 4: String Conversion for CLI Scripts
**Given** a Path object from a helper function
**When** passing to CLI script wrapper
**Then** the path should:
- ✅ Convert cleanly to string: `str(path)`
- ✅ Work correctly with CLI script arguments
- ✅ Maintain compatibility with existing CLI script interfaces

### Scenario 5: Multi-Channel Isolation with Security
**Given** two channels "poke1" and "poke2" with same project_id "vid_123"
**When** path helpers are used for both channels
**Then** the paths should be:
- ✅ Channel 1: `/app/workspace/channels/poke1/projects/vid_123/`
- ✅ Channel 2: `/app/workspace/channels/poke2/projects/vid_123/`
- ✅ No cross-channel interference (completely isolated storage)
- ✅ Path traversal attacks prevented (malicious IDs like "../../../etc" rejected)
- ✅ Input validation enforces alphanumeric + underscore/dash only

## Technical Specifications

### File Structure
```
app/
└── utils/
    └── filesystem.py       # New file (MANDATORY utility)
```

### Core Implementation: `app/utils/filesystem.py`

**Required Constants:**
```python
from pathlib import Path

# Railway persistent volume mount point
WORKSPACE_ROOT = Path("/app/workspace")

# Subdirectory names (constants for consistency)
CHANNEL_DIR_NAME = "channels"
PROJECT_DIR_NAME = "projects"
ASSET_DIR_NAME = "assets"
VIDEO_DIR_NAME = "videos"
AUDIO_DIR_NAME = "audio"
SFX_DIR_NAME = "sfx"

# Asset subdirectory names
CHARACTER_DIR_NAME = "characters"
ENVIRONMENT_DIR_NAME = "environments"
PROPS_DIR_NAME = "props"
COMPOSITE_DIR_NAME = "composites"
```

**Required Functions:**

```python
def get_channel_workspace(channel_id: str) -> Path:
    """
    Get workspace directory for a specific channel.

    Creates the directory if it doesn't exist.

    Args:
        channel_id: Channel identifier (e.g., "poke1", "poke2")

    Returns:
        Path to channel workspace: /app/workspace/channels/{channel_id}/

    Example:
        >>> path = get_channel_workspace("poke1")
        >>> print(path)
        /app/workspace/channels/poke1
        >>> assert path.exists()
    """
    path = WORKSPACE_ROOT / CHANNEL_DIR_NAME / channel_id
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_project_dir(channel_id: str, project_id: str) -> Path:
    """
    Get project directory within channel workspace.

    Creates the directory if it doesn't exist.

    Args:
        channel_id: Channel identifier
        project_id: Project/task identifier (e.g., UUID from database)

    Returns:
        Path to project directory: /app/workspace/channels/{channel_id}/projects/{project_id}/

    Example:
        >>> path = get_project_dir("poke1", "vid_abc123")
        >>> print(path)
        /app/workspace/channels/poke1/projects/vid_abc123
    """
    path = get_channel_workspace(channel_id) / PROJECT_DIR_NAME / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_asset_dir(channel_id: str, project_id: str) -> Path:
    """
    Get assets directory for a project.

    Creates the directory if it doesn't exist.

    Args:
        channel_id: Channel identifier
        project_id: Project/task identifier

    Returns:
        Path to assets directory: .../projects/{project_id}/assets/

    Example:
        >>> path = get_asset_dir("poke1", "vid_abc123")
        >>> print(path)
        /app/workspace/channels/poke1/projects/vid_abc123/assets
    """
    path = get_project_dir(channel_id, project_id) / ASSET_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_character_dir(channel_id: str, project_id: str) -> Path:
    """Get character assets subdirectory: .../assets/characters/"""
    path = get_asset_dir(channel_id, project_id) / CHARACTER_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_environment_dir(channel_id: str, project_id: str) -> Path:
    """Get environment assets subdirectory: .../assets/environments/"""
    path = get_asset_dir(channel_id, project_id) / ENVIRONMENT_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_props_dir(channel_id: str, project_id: str) -> Path:
    """Get props assets subdirectory: .../assets/props/"""
    path = get_asset_dir(channel_id, project_id) / PROPS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_composite_dir(channel_id: str, project_id: str) -> Path:
    """Get composite images subdirectory: .../assets/composites/"""
    path = get_asset_dir(channel_id, project_id) / COMPOSITE_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_video_dir(channel_id: str, project_id: str) -> Path:
    """Get videos directory: .../projects/{project_id}/videos/"""
    path = get_project_dir(channel_id, project_id) / VIDEO_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_audio_dir(channel_id: str, project_id: str) -> Path:
    """Get audio directory: .../projects/{project_id}/audio/"""
    path = get_project_dir(channel_id, project_id) / AUDIO_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_sfx_dir(channel_id: str, project_id: str) -> Path:
    """Get sound effects directory: .../projects/{project_id}/sfx/"""
    path = get_project_dir(channel_id, project_id) / SFX_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path
```

### Usage Pattern (Worker Example)

```python
from app.utils.filesystem import get_asset_dir, get_composite_dir, get_video_dir
from app.utils.cli_wrapper import run_cli_script

# ✅ CORRECT: Use filesystem helpers + pathlib + string conversion for CLI
channel_id = "poke1"
project_id = "vid_abc123"

# Get asset directory (auto-creates)
asset_dir = get_asset_dir(channel_id, project_id)
character_path = asset_dir / "characters" / "bulbasaur.png"

# Pass string path to CLI script
result = await run_cli_script(
    "generate_asset.py",
    ["--prompt", prompt, "--output", str(character_path)],
    timeout=60
)

# Get composite directory for video generation seed images
composite_dir = get_composite_dir(channel_id, project_id)
composite_path = composite_dir / "scene_01.png"

await run_cli_script(
    "create_composite.py",
    ["--character", str(char_path), "--environment", str(env_path), "--output", str(composite_path)]
)

# Get video directory for generated clips
video_dir = get_video_dir(channel_id, project_id)
video_path = video_dir / "clip_01.mp4"

await run_cli_script(
    "generate_video.py",
    ["--image", str(composite_path), "--prompt", motion_prompt, "--output", str(video_path)],
    timeout=600
)

# ❌ WRONG: Hard-coded paths with f-strings
output_path = f"/workspace/poke1/vid_abc123/assets/bulbasaur.png"

# ❌ WRONG: String concatenation
output_path = "/workspace/" + channel_id + "/" + project_id + "/assets/bulbasaur.png"
```

## Dependencies

**Required Before Starting:**
- ✅ Story 3.1 complete: CLI script wrapper (`app/utils/cli_wrapper.py`)
- ✅ Python 3.10+ with pathlib support

**No External Dependencies:**
- Uses only Python standard library (pathlib, no third-party packages)

**Blocks These Stories:**
- Story 3.3: Asset generation (needs path helpers)
- Story 3.4: Composite creation (needs path helpers)
- Story 3.5: Video generation (needs path helpers)
- Story 3.6: Narration generation (needs path helpers)
- Story 3.7: SFX generation (needs path helpers)
- Story 3.8: Video assembly (needs path helpers)

## Testing Requirements

### Unit Tests: `tests/test_utils/test_filesystem.py`

**Test Cases:**

1. **test_get_channel_workspace_creates_directory()**
   - Verify directory is created when it doesn't exist
   - Verify path format: `/app/workspace/channels/{channel_id}/`
   - Verify idempotent (multiple calls return same path)

2. **test_get_project_dir_creates_nested_structure()**
   - Verify nested directory creation: `channels/{channel_id}/projects/{project_id}/`
   - Verify parent directories created automatically

3. **test_get_asset_dir_returns_path_object()**
   - Verify return type is `pathlib.Path`
   - Verify path exists after call
   - Verify path can be used with `/` operator for file paths

4. **test_specialized_asset_subdirectories()**
   - Verify `get_character_dir()` creates `assets/characters/`
   - Verify `get_environment_dir()` creates `assets/environments/`
   - Verify `get_props_dir()` creates `assets/props/`
   - Verify `get_composite_dir()` creates `assets/composites/`

5. **test_get_video_audio_sfx_dirs()**
   - Verify video directory: `.../projects/{project_id}/videos/`
   - Verify audio directory: `.../projects/{project_id}/audio/`
   - Verify sfx directory: `.../projects/{project_id}/sfx/`

6. **test_multi_channel_isolation()**
   - Create paths for two different channels with same project_id
   - Verify paths are different: `channels/poke1/` vs `channels/poke2/`
   - Verify no cross-channel interference

7. **test_path_string_conversion_for_cli()**
   - Get path from helper
   - Convert to string with `str(path)`
   - Verify string format is valid for CLI script arguments

8. **test_idempotent_directory_creation()**
   - Call helper twice with same arguments
   - Verify second call doesn't raise error
   - Verify directory exists and is accessible

9. **test_path_object_slash_operator()**
   - Get base path from helper
   - Use `/` operator to construct file path: `path / "file.png"`
   - Verify resulting path is correct

10. **test_constants_match_expected_names()**
    - Verify `CHANNEL_DIR_NAME == "channels"`
    - Verify `ASSET_DIR_NAME == "assets"`
    - Verify subdirectory constants are correct

**Mocking Strategy:**
- Use `tmp_path` fixture from pytest for temporary directory testing
- Mock `WORKSPACE_ROOT` to point to temporary directory (avoid writing to `/app/workspace/` in tests)

**Example Test:**
```python
import pytest
from pathlib import Path
from app.utils.filesystem import get_asset_dir, get_character_dir, WORKSPACE_ROOT

@pytest.fixture
def mock_workspace_root(tmp_path, monkeypatch):
    """Mock WORKSPACE_ROOT to use temporary directory for testing"""
    monkeypatch.setattr("app.utils.filesystem.WORKSPACE_ROOT", tmp_path)
    return tmp_path

def test_get_asset_dir_creates_directory(mock_workspace_root):
    """Test asset directory is created with correct structure"""
    channel_id = "poke1"
    project_id = "vid_abc123"

    asset_dir = get_asset_dir(channel_id, project_id)

    assert asset_dir.exists()
    assert asset_dir.is_dir()
    assert str(asset_dir) == f"{mock_workspace_root}/channels/poke1/projects/vid_abc123/assets"

def test_get_character_dir_creates_subdirectory(mock_workspace_root):
    """Test character subdirectory is created under assets"""
    channel_id = "poke1"
    project_id = "vid_abc123"

    character_dir = get_character_dir(channel_id, project_id)

    assert character_dir.exists()
    assert character_dir.is_dir()
    assert character_dir.name == "characters"
    assert character_dir.parent.name == "assets"

def test_multi_channel_isolation(mock_workspace_root):
    """Test paths for different channels are completely isolated"""
    project_id = "vid_123"

    path1 = get_asset_dir("poke1", project_id)
    path2 = get_asset_dir("poke2", project_id)

    assert path1 != path2
    assert "poke1" in str(path1)
    assert "poke2" in str(path2)
    assert path1.exists()
    assert path2.exists()
```

### Integration Tests (Optional)
- Mark with `@pytest.mark.integration`
- Test actual filesystem writes to temporary directory
- Verify permissions and access patterns

## Edge Cases & Error Scenarios

1. **Invalid Channel/Project IDs:**
   - Handle special characters in IDs (spaces, slashes, etc.)
   - Path sanitization if needed (e.g., strip whitespace, replace unsafe chars)
   - Consider if validation should happen in helper or at caller

2. **Permission Errors:**
   - If `/app/workspace/` is not writable, mkdir will raise `PermissionError`
   - Let exception propagate (indicates configuration error)
   - Railway volume should be writable by default

3. **Disk Space Exhaustion:**
   - If disk is full, mkdir will succeed but file writes will fail
   - Directory creation doesn't reserve space (writes to disk lazily)
   - Error handling in CLI script layer (not filesystem helpers)

4. **Concurrent Directory Creation:**
   - Multiple workers may call helpers simultaneously for same path
   - `mkdir(exist_ok=True)` handles race condition safely
   - No locking needed (mkdir is atomic)

5. **Symlink Handling:**
   - If channel_id or project_id contains `..` or symlink components
   - Path traversal risk (security concern)
   - Consider validation: `Path.resolve()` and check it's under WORKSPACE_ROOT

6. **Long Path Names:**
   - OS limits on path length (255 chars per component, ~4096 total)
   - UUID project IDs are safe (36 chars)
   - Channel IDs should be validated at config level

## Documentation Requirements

**1. Inline Docstrings:**
- Module docstring explaining filesystem organization strategy
- Function docstrings with Args/Returns/Examples
- Constants documentation explaining Railway volume structure

**2. Architecture Documentation:**
- Update project-context.md if path patterns change
- Reference this story in architecture decisions

**3. Usage Examples:**
- Add comprehensive examples in module docstring
- Document common patterns (asset generation, video storage, cleanup)

## Definition of Done

- [x] `app/utils/filesystem.py` implemented with all required functions
- [x] All constants defined (WORKSPACE_ROOT, subdirectory names)
- [x] All unit tests passing (22 test cases, exceeds 10 minimum)
- [x] Path helpers return `pathlib.Path` objects (not strings)
- [x] Auto-creation verified (directories created on first access)
- [x] Multi-channel isolation verified (no cross-channel interference)
- [x] Type hints complete (all parameters and return types annotated)
- [x] Docstrings complete (module, function-level with examples)
- [x] Linting passes (`ruff check --fix .`)
- [x] Type checking passes (`mypy app/`)
- [x] Integration with Story 3.1 CLI wrapper verified
- [ ] Code review approved (ready for review)
- [ ] Merged to `main` branch (awaiting review)

## Notes & Implementation Hints

**From Architecture (architecture.md lines 361-366):**
- Path Pattern: `{workspace_root}/channels/{channel_id}/projects/{project_id}/assets/`
- Database stores file paths (not file contents)
- Preserves brownfield CLI script interfaces (scripts expect filesystem paths)
- Proven pattern from existing implementation

**From project-context.md (lines 200-277):**
- These helpers are MANDATORY for all path construction
- Never use hard-coded paths or f-string concatenation
- Ensures consistent path structure for cleanup, debugging, manual inspection
- Supports multi-channel isolation

**Filesystem Layout (Complete Structure):**
```
/app/workspace/                                 # Railway persistent volume
└── channels/
    ├── poke1/                                 # Channel 1 workspace
    │   └── projects/
    │       ├── vid_abc123/                    # Project 1
    │       │   ├── assets/
    │       │   │   ├── characters/            # Character images
    │       │   │   ├── environments/          # Environment backgrounds
    │       │   │   ├── props/                 # Prop images
    │       │   │   └── composites/            # 16:9 composite images
    │       │   ├── videos/                    # Generated video clips
    │       │   ├── audio/                     # Narration MP3s
    │       │   └── sfx/                       # Sound effect WAVs
    │       └── vid_def456/                    # Project 2
    │           └── ...
    └── poke2/                                 # Channel 2 workspace (isolated)
        └── projects/
            └── ...
```

**Security Considerations:**
- Validate channel_id and project_id don't contain path traversal sequences (`..`, `/`, etc.)
- Use `Path.resolve()` to normalize paths and verify they're under WORKSPACE_ROOT
- Consider whitelist validation for channel_id format (alphanumeric + underscore)

**Performance Considerations:**
- `mkdir(parents=True, exist_ok=True)` is fast (no-op if directory exists)
- Path construction is cheap (string operations only)
- No disk I/O unless directory doesn't exist

**Railway Volume Configuration:**
- Railway persistent volume mounted at `/app/workspace/`
- Volume persists across deployments (not ephemeral)
- Shared across web service and 3 worker processes
- Must be configured in Railway dashboard

## Related Stories

- **Depends On:** 3-1 (CLI Script Wrapper) - provides `run_cli_script()` that uses these paths
- **Blocks:** 3-3, 3-4, 3-5, 3-6, 3-7, 3-8 (all pipeline steps need path helpers)
- **Related:** Epic 8 Story on cleanup (will use these paths to identify old projects)

## Source References

**PRD Requirements:**
- FR44: Backend Filesystem Structure - `/workspaces/{channel_id}/{task_id}/`
- FR45: Asset Subfolder Organization - characters/, environments/, composites/
- FR50: Asset Generation Idempotency - Re-running overwrites existing files

**Architecture Decisions:**
- Asset Storage Strategy (lines 361-366): Filesystem with channel organization
- Path pattern documented explicitly

**Context:**
- project-context.md: Filesystem Helpers (Required Implementation) - lines 200-277
- project-context.md: Integration Utilities (MANDATORY) - lines 117-198
- CLAUDE.md: Filesystem organization principles

---

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Implementation Plan

**Approach:** Red-Green-Refactor TDD cycle following story specifications

**Implementation Strategy:**
1. Create `app/utils/filesystem.py` with all required path helper functions
2. Implement constants for directory names (WORKSPACE_ROOT, subdirectory names)
3. Implement base path helpers (get_channel_workspace, get_project_dir)
4. Implement specialized helpers for all subdirectories
5. Create comprehensive test suite with 22 test cases
6. Verify all tests pass (100% pass rate achieved)
7. Run code quality checks (linting, type checking)

**Key Design Decisions:**
- Used Python 3.10+ pathlib.Path for type safety and path operations
- Auto-creation with `mkdir(parents=True, exist_ok=True)` ensures idempotent behavior
- Monkeypatch pattern in tests (mock WORKSPACE_ROOT to tmp_path) for safe testing
- Complete test coverage: constants, directory creation, multi-channel isolation, path conversions

**Architecture Compliance:**
- Followed project-context.md lines 200-277 (MANDATORY utility designation)
- Implements Architecture Decision: Asset Storage Strategy with channel organization
- Railway persistent volume pattern: `/app/workspace/` as WORKSPACE_ROOT
- Full multi-channel isolation verified

### Completion Notes

**Implementation Summary:**
✅ Created `app/utils/filesystem.py` (389 lines) with 10 path helper functions + 2 security validators
✅ All required constants defined (11 directory name constants)
✅ Comprehensive test suite: 32 test cases covering all scenarios + security validation
✅ All acceptance criteria satisfied (5/5 scenarios validated with security)
✅ Test results: 32 filesystem tests pass (22 functional + 10 security)
✅ Code quality: Ruff linting passed, Mypy type checking passed (strict mode)
✅ Security: Path traversal attacks prevented with input validation
✅ Multi-channel isolation verified with security boundary tests
✅ Integration with Story 3.1 CLI wrapper ready (Path-to-string conversion tested)

**Test Coverage Achieved:**
- Constants validation (11 constants)
- Directory auto-creation and idempotency
- Path object return types (pathlib.Path)
- Multi-channel isolation (no cross-channel interference)
- **Security validation: Path traversal prevention (10 test cases)**
- **Input validation: Alphanumeric + underscore/dash enforcement**
- **Empty identifier rejection**
- **Special character blocking (/, ;, |, etc.)**
- String conversion for CLI scripts
- Complete directory structure creation
- Edge cases: repeated calls, nested structures, resolved path verification

**Technical Implementation:**
- Python standard library only (pathlib, no dependencies)
- Type hints complete (all functions annotated)
- Docstrings with Args/Returns/Examples (Google style)
- Auto-creation prevents "directory not found" errors
- Safe concurrent access (mkdir atomic operation)

**Integration Points:**
- Ready for Story 3.3+ (asset generation, video processing)
- Compatible with Story 3.1 CLI wrapper pattern
- Implements architecture patterns from project-context.md

### File List

**New Files Created:**
- `app/utils/filesystem.py` - Path helper functions with security validation (389 lines, 10 public functions, 2 security validators, 11 constants, __all__ export list)
- `tests/test_utils/test_filesystem.py` - Comprehensive unit tests (32 test cases, 9 test classes including security validation)

**Modified Files:**
- `_bmad-output/project-context.md` - Updated filesystem helpers documentation to include all 10 functions and security notes

---

## Change Log

- **2026-01-15 (Story Creation):** Story 3.2 ready for development
  - Comprehensive context analysis from previous story 3.1
  - Architecture and project-context.md integration
  - Detailed implementation specifications
  - MANDATORY utility designation emphasized
  - All acceptance criteria and test cases defined

- **2026-01-15 (Implementation Complete):** Filesystem path helpers implemented and tested
  - Created `app/utils/filesystem.py` with 11 path helper functions
  - Implemented all required constants and directory structure
  - Created comprehensive test suite (22 test cases, 100% pass rate)
  - All acceptance criteria validated and satisfied
  - Code quality checks passed (ruff linting, mypy type checking)
  - Multi-channel isolation verified with test scenarios
  - Integration ready for Stories 3.3-3.8 (all pipeline steps)
  - Zero regressions (575 total tests pass)

- **2026-01-15 (Security Review & Fixes):** CRITICAL security vulnerability patched
  - **CRITICAL FIX:** Added path traversal attack prevention (regex validation + resolved path verification)
  - Added 10 comprehensive security test cases (path traversal, special characters, empty identifiers)
  - Added `__all__` export list for explicit public API definition
  - Added Example sections to all specialized helper docstrings
  - Fixed documentation metrics (line counts, function counts, constant counts)
  - Updated project-context.md with complete function list and security notes
  - Updated AC5 to reflect security validation implementation
  - All 32 tests pass (22 functional + 10 security)
  - Code quality verified: Mypy strict mode passed, Ruff linting passed
  - Security validated: Malicious identifiers ("../../../etc", "poke1/malicious", etc.) properly rejected
  - **File metrics:** 389 lines (was 234 before security), 506 test lines (was 362)

---

## Status

**Status:** done
**Created:** 2026-01-15
**Completed:** 2026-01-15
**Ready for:** Merge to main branch (security patched, all tests pass, code review complete)
