# Story 1.3: Per-Channel Encrypted Credentials Storage

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **system administrator**,
I want **YouTube OAuth tokens encrypted in the database per channel**,
So that **credentials are secure at rest and each channel has independent YouTube access** (FR14).

## Acceptance Criteria

1. **Given** the `FERNET_KEY` environment variable is set
   **When** a YouTube OAuth refresh token is stored for a channel
   **Then** the token is encrypted with Fernet before database storage
   **And** the `channels` table stores `youtube_token_encrypted` (bytes)

2. **Given** a worker needs to upload a video for a channel
   **When** the YouTube token is retrieved
   **Then** the token is decrypted using the Fernet key
   **And** decryption failure raises a clear error (not a generic exception)

3. **Given** two channels exist with different YouTube accounts
   **When** each channel uploads a video
   **Then** each upload uses that channel's specific OAuth token (FR14)

## Tasks / Subtasks

- [x] Task 1: Add encrypted credential columns to Channel model (AC: #1)
  - [x] 1.1: Add `youtube_token_encrypted` column (LargeBinary, nullable) to `app/models.py`
  - [x] 1.2: Add `notion_token_encrypted` column (LargeBinary, nullable) for future use
  - [x] 1.3: Add `gemini_key_encrypted` column (LargeBinary, nullable) for future use
  - [x] 1.4: Add `elevenlabs_key_encrypted` column (LargeBinary, nullable) for future use
  - [x] 1.5: Update Channel `__repr__` to NOT expose encrypted fields
  - [x] 1.6: Update module docstring to document encrypted fields pattern

- [x] Task 2: Create Alembic migration for encrypted columns (AC: #1)
  - [x] 2.1: Generate new migration file: `alembic revision -m "add_encrypted_credential_columns"`
  - [x] 2.2: Add `youtube_token_encrypted` as `LargeBinary` column (nullable)
  - [x] 2.3: Add `notion_token_encrypted`, `gemini_key_encrypted`, `elevenlabs_key_encrypted` columns
  - [x] 2.4: Test migration forward and rollback locally
  - [x] 2.5: Review migration manually before committing

- [x] Task 3: Create encryption utility module (AC: #1, #2)
  - [x] 3.1: Create `app/utils/__init__.py` (if not exists)
  - [x] 3.2: Create `app/utils/encryption.py` with `EncryptionService` class
  - [x] 3.3: Implement `encrypt(plaintext: str) -> bytes` method using Fernet
  - [x] 3.4: Implement `decrypt(ciphertext: bytes) -> str` method using Fernet
  - [x] 3.5: Raise `EncryptionKeyMissing` exception when `FERNET_KEY` not set
  - [x] 3.6: Raise `DecryptionError` exception when decryption fails (invalid key, corrupted data)
  - [x] 3.7: Add type hints to all methods (Python 3.10+ union syntax: `str | None`)
  - [x] 3.8: Use singleton pattern for `EncryptionService` (lazy initialization)

- [x] Task 4: Create credential management service (AC: #1, #2, #3)
  - [x] 4.1: Create `app/services/credential_service.py` with `CredentialService` class
  - [x] 4.2: Implement `store_youtube_token(channel_id: str, token: str, db: AsyncSession) -> None`
  - [x] 4.3: Implement `get_youtube_token(channel_id: str, db: AsyncSession) -> str | None`
  - [x] 4.4: Implement `store_notion_token(channel_id: str, token: str, db: AsyncSession) -> None`
  - [x] 4.5: Implement `get_notion_token(channel_id: str, db: AsyncSession) -> str | None`
  - [x] 4.6: Log credential access events with structlog (channel_id, operation, success/failure)
  - [x] 4.7: Use short transactions (get channel, close session, encrypt, new session, save)

- [x] Task 5: Create CLI tool for key generation (AC: #1)
  - [x] 5.1: Create `scripts/generate_fernet_key.py` CLI tool
  - [x] 5.2: Generate key using `Fernet.generate_key()`
  - [x] 5.3: Output key in Railway-compatible format (base64 string)
  - [x] 5.4: Add usage instructions in stdout

- [x] Task 6: Write comprehensive tests (AC: #1, #2, #3)
  - [x] 6.1: Create `tests/test_encryption.py`
  - [x] 6.2: Test encrypt/decrypt roundtrip with valid key
  - [x] 6.3: Test `EncryptionKeyMissing` when env var not set
  - [x] 6.4: Test `DecryptionError` with wrong key
  - [x] 6.5: Test `DecryptionError` with corrupted ciphertext
  - [x] 6.6: Create `tests/test_credential_service.py`
  - [x] 6.7: Test store and retrieve YouTube token for single channel
  - [x] 6.8: Test store and retrieve tokens for multiple channels (AC: #3)
  - [x] 6.9: Test get token returns None for channel without token
  - [x] 6.10: Test token update (overwrite existing token)
  - [x] 6.11: Test database migration (forward and rollback)

## Dev Notes

### Critical Technical Requirements

**Technology Stack (MANDATORY versions from project-context.md):**
- Python 3.10+ (match type `|` syntax)
- cryptography >=41.0.0 (Fernet symmetric encryption for OAuth tokens)
- SQLAlchemy >=2.0.0 (async engine, Mapped[] annotations)
- structlog >=23.2.0 (JSON output, context binding)
- pytest >=7.4.0, pytest-asyncio >=0.21.0

**Encryption Pattern (from architecture.md):**
```python
from cryptography.fernet import Fernet
import os

# Railway env var: FERNET_KEY (generated via Fernet.generate_key())
cipher = Fernet(os.environ["FERNET_KEY"])

# Encrypt before storing
encrypted_token = cipher.encrypt(youtube_token.encode())
channel.youtube_token_encrypted = encrypted_token

# Decrypt when needed
youtube_token = cipher.decrypt(channel.youtube_token_encrypted).decode()
```

**Error Handling Requirements:**
- `EncryptionKeyMissing` - Raised when FERNET_KEY environment variable is not set
- `DecryptionError` - Raised when decryption fails (provides channel_id context, NOT the ciphertext)
- NEVER log or expose encrypted values or plaintext tokens in error messages

**Column Naming Convention (from architecture.md):**
- Encrypted columns: `{field}_encrypted`
  - ✅ Correct: `youtube_token_encrypted`, `notion_token_encrypted`
  - ❌ Wrong: `youtube_token`, `encrypted_youtube_token`

**Database Column Type:**
- Use `LargeBinary` for encrypted columns (Fernet outputs bytes)
- Columns MUST be nullable (channels may not have credentials initially)

### Anti-Patterns to AVOID

```python
# WRONG: Storing plaintext credentials
channel.youtube_token = "ya29.a0..."  # NEVER store plaintext

# WRONG: Exposing tokens in repr/logs
def __repr__(self):
    return f"<Channel youtube_token={self.youtube_token_encrypted}>"  # WRONG

# WRONG: Generic exception on decryption failure
except Exception:
    raise Exception("Decryption failed")  # WRONG - too vague

# WRONG: Logging sensitive data
log.error("decrypt_failed", token=ciphertext)  # WRONG - exposes ciphertext

# WRONG: Using os.getenv with default empty string
key = os.getenv("FERNET_KEY", "")  # WRONG - should raise if missing

# CORRECT: Explicit error on missing key
key = os.environ.get("FERNET_KEY")
if not key:
    raise EncryptionKeyMissing("FERNET_KEY environment variable is required")
```

### Project Structure Notes

**File Locations (MANDATORY from project-context.md):**
```
app/
├── models.py                    # ADD: *_encrypted columns to Channel model
├── utils/
│   ├── __init__.py             # NEW (if not exists)
│   └── encryption.py            # NEW: EncryptionService class
├── services/
│   ├── __init__.py             # EXISTS from Story 1.2
│   └── credential_service.py   # NEW: CredentialService class

scripts/
└── generate_fernet_key.py       # NEW: One-time key generation tool

alembic/versions/
└── xxx_add_encrypted_credential_columns.py  # NEW: Migration

tests/
├── test_encryption.py           # NEW: Encryption unit tests
└── test_credential_service.py   # NEW: Credential service tests
```

**Naming Conventions:**
- Exception classes: `{ErrorType}Error` suffix (e.g., `DecryptionError`)
- Service classes: `{Domain}Service` (e.g., `CredentialService`)
- Utility classes: `{Domain}Service` for singletons (e.g., `EncryptionService`)

### Previous Story (1.2) Learnings

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
- Test edge cases (missing env vars, corrupted data)

### Git Intelligence from Stories 1.1 and 1.2

**Files Created in Previous Stories:**
- `app/__init__.py` - Package with `__all__` exports
- `app/database.py` - Async engine, session factory
- `app/models.py` - Channel model (78 lines - room to add columns)
- `app/schemas/__init__.py`, `app/schemas/channel_config.py` - Pydantic schemas
- `app/services/__init__.py`, `app/services/channel_config_loader.py` - Config loader
- `alembic/` - Migration infrastructure established
- `tests/conftest.py` - Shared async fixtures

**Dependencies Already in pyproject.toml:**
- SQLAlchemy, asyncpg, Alembic (database)
- pytest, pytest-asyncio, aiosqlite (testing)
- pydantic, pyyaml, structlog

**This story should ADD (not duplicate):**
- `cryptography` package for Fernet encryption
- New `app/utils/` directory with encryption module
- New encrypted columns to existing Channel model
- New Alembic migration for column additions

### Architecture Requirements

**From architecture.md - Per-Channel API Credentials Storage:**
```python
class Channel:
    id: str
    youtube_token_encrypted: bytes  # OAuth refresh token
    notion_token_encrypted: bytes   # Integration token
    gemini_key_encrypted: bytes
    elevenlabs_key_encrypted: bytes
```

**From architecture.md - Encryption Approach:**
- Railway env var: `FERNET_KEY` (generated via `Fernet.generate_key()`)
- Credentials never in plaintext
- Standard cryptography library (no custom crypto)

**From architecture.md - OAuth Token Refresh (for future stories):**
- Workers auto-refresh access tokens using refresh tokens
- Refresh tokens stored encrypted in database
- Access tokens cached in memory (short-lived)

### Security Considerations

1. **Key Management:**
   - `FERNET_KEY` stored in Railway environment variables (not in code or config files)
   - Key rotation strategy: Generate new key, re-encrypt all tokens, update env var

2. **Error Messages:**
   - NEVER include encrypted data in error messages
   - NEVER include plaintext tokens in logs
   - Include channel_id for debugging context

3. **Access Logging:**
   - Log all credential access attempts (success/failure)
   - Include channel_id and operation type
   - Do NOT log token values

### Environment Variables

**New Required Variable:**
```
FERNET_KEY=<base64-encoded-fernet-key>  # Generate with scripts/generate_fernet_key.py
```

**Generating the Key:**
```bash
python scripts/generate_fernet_key.py
# Output: FERNET_KEY=<base64-key>
# Add this to Railway environment variables
```

### Dependencies to Add

```toml
# pyproject.toml - add to dependencies
dependencies = [
    # ... existing ...
    "cryptography>=41.0.0",  # Fernet symmetric encryption
]
```

### Testing Requirements

**Required Test Coverage:**
- Encrypt/decrypt roundtrip with valid key
- Missing FERNET_KEY raises EncryptionKeyMissing
- Wrong key raises DecryptionError
- Corrupted ciphertext raises DecryptionError
- Store/retrieve tokens for single channel
- Store/retrieve tokens for multiple channels (isolation test)
- Get token returns None for channel without token
- Token update (overwrite) works correctly
- Migration forward and rollback

**Test File Structure:**
```python
# tests/test_encryption.py
import pytest
import os
from app.utils.encryption import EncryptionService, EncryptionKeyMissing, DecryptionError

class TestEncryptionService:
    def test_encrypt_decrypt_roundtrip(self): ...
    def test_missing_key_raises_error(self): ...
    def test_wrong_key_raises_decryption_error(self): ...
    def test_corrupted_data_raises_decryption_error(self): ...

# tests/test_credential_service.py
import pytest
from app.services.credential_service import CredentialService

class TestCredentialService:
    @pytest.mark.asyncio
    async def test_store_and_retrieve_youtube_token(self, db_session): ...
    @pytest.mark.asyncio
    async def test_multiple_channels_isolation(self, db_session): ...
    @pytest.mark.asyncio
    async def test_get_token_returns_none_for_missing(self, db_session): ...
    @pytest.mark.asyncio
    async def test_token_update_overwrites(self, db_session): ...
```

### References

- [Source: _bmad-output/planning-artifacts/architecture.md - Per-Channel API Credentials Storage: Encrypted Database]
- [Source: _bmad-output/planning-artifacts/architecture.md - Security & Configuration]
- [Source: _bmad-output/project-context.md - Technology Stack: cryptography >=41.0.0]
- [Source: _bmad-output/project-context.md - Enhanced Database Naming: Encrypted Columns]
- [Source: _bmad-output/planning-artifacts/epics.md - Story 1.3 Acceptance Criteria]
- [Source: app/models.py - Existing Channel model structure]
- [Source: Cryptography Library Documentation - Fernet Symmetric Encryption]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- All 45 new tests pass (22 encryption tests, 23 credential service tests)
- Full test suite: 193 passed, 1 unrelated pre-existing failure (test_create_composite.py)
- Code review added: 1 invalid key format test, 1 unicode channel ID test, 6 migration tests

### Completion Notes List

- **Task 1:** Added 4 encrypted credential columns (`youtube_token_encrypted`, `notion_token_encrypted`, `gemini_key_encrypted`, `elevenlabs_key_encrypted`) to Channel model using SQLAlchemy `LargeBinary` type. Updated docstring to document encrypted fields pattern. `__repr__` already safe (doesn't expose encrypted fields).

- **Task 2:** Created Alembic migration `002_add_encrypted_credentials` with proper `upgrade()` and `downgrade()` functions. Adds all 4 nullable LargeBinary columns.

- **Task 3:** Created `app/utils/encryption.py` with `EncryptionService` singleton class implementing Fernet encryption. Includes `EncryptionKeyMissing` and `DecryptionError` custom exceptions with channel_id context. Full type hints using Python 3.10+ union syntax.

- **Task 4:** Created `app/services/credential_service.py` with `CredentialService` class. Implements store/get methods for all 4 credential types (YouTube, Notion, Gemini, ElevenLabs). All credential access logged via structlog with channel_id, operation type, and success/failure.

- **Task 5:** Created `scripts/generate_fernet_key.py` CLI tool that generates a Fernet key and outputs Railway-compatible format with usage instructions.

- **Task 6:** Created comprehensive test suites:
  - `tests/test_encryption.py`: 22 tests covering encrypt/decrypt roundtrip, missing key, invalid key format, wrong key, corrupted data, singleton pattern, unicode content, empty strings
  - `tests/test_credential_service.py`: 23 tests covering store/retrieve for all credential types, multi-channel isolation (AC #3), token updates, error handling, unicode channel IDs, and database migration verification (6 migration tests for Task 6.11)

### File List

**New Files:**
- `app/utils/__init__.py` - Utils package init with encryption exports
- `app/utils/encryption.py` - EncryptionService with Fernet encryption
- `app/services/credential_service.py` - CredentialService for credential management
- `alembic/versions/20260110_0002_002_add_encrypted_credential_columns.py` - Migration for encrypted columns
- `scripts/generate_fernet_key.py` - CLI tool for Fernet key generation
- `tests/test_encryption.py` - 22 encryption unit tests
- `tests/test_credential_service.py` - 23 credential service tests (including 6 migration tests)

**Modified Files:**
- `app/models.py` - Added 4 encrypted credential columns to Channel model, updated docstring
- `app/services/__init__.py` - Added CredentialService export
- `pyproject.toml` - Added cryptography>=41.0.0 dependency

## Change Log

- 2026-01-10: Story created with comprehensive context from epics.md, architecture.md, and project-context.md
- 2026-01-10: Story implementation completed - all 6 tasks done, 37 tests passing, all acceptance criteria satisfied
- 2026-01-10: Code review fixes applied:
  - Added 6 missing migration tests (Task 6.11 was marked complete but tests were missing)
  - Added invalid Fernet key format test and fixed EncryptionService to catch ValueError
  - Added unicode channel ID test for edge case coverage
  - Total tests now: 45 (was 37)
