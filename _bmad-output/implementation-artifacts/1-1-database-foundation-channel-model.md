# Story 1.1: Database Foundation & Channel Model

Status: done

## Story

As a **system administrator**,
I want **a PostgreSQL database with the Channel model and async session management**,
So that **the system has persistent storage with proper isolation between channels**.

## Acceptance Criteria

1. **Given** the system is starting up for the first time
   **When** Alembic migrations run
   **Then** the `channels` table is created with columns: `id` (UUID PK), `channel_id` (str unique), `channel_name` (str), `created_at` (datetime), `updated_at` (datetime), `is_active` (bool)
   **And** the async SQLAlchemy engine is configured with `pool_size=10`, `max_overflow=5`, `pool_pre_ping=True`
   **And** `async_session_factory` is available for dependency injection

2. **Given** a channel record exists in the database
   **When** a query filters by `channel_id`
   **Then** only data for that specific channel is returned (FR9: isolation)

## Tasks / Subtasks

- [x] Task 1: Create SQLAlchemy async database module (AC: #1)
  - [x] 1.1: Create `app/database.py` with `create_async_engine` configuration
  - [x] 1.2: Configure connection pool: `pool_size=10`, `max_overflow=5`, `pool_pre_ping=True`
  - [x] 1.3: Create `async_sessionmaker` factory with `expire_on_commit=False`
  - [x] 1.4: Implement `get_session()` async generator for FastAPI dependency injection
  - [x] 1.5: Load DATABASE_URL from environment variable

- [x] Task 2: Create Channel SQLAlchemy model (AC: #1, #2)
  - [x] 2.1: Create `app/models.py` with SQLAlchemy 2.0 declarative base
  - [x] 2.2: Define `Channel` model with `Mapped[type]` annotations (NOT old Column syntax)
  - [x] 2.3: Implement UUID primary key with `uuid.uuid4` default
  - [x] 2.4: Add `channel_id` as unique string field (business identifier)
  - [x] 2.5: Add `channel_name`, `created_at`, `updated_at`, `is_active` fields
  - [x] 2.6: Add `__tablename__ = "channels"` (plural snake_case)

- [x] Task 3: Set up Alembic for async migrations (AC: #1)
  - [x] 3.1: Initialize Alembic with `alembic init alembic`
  - [x] 3.2: Configure `alembic.ini` with PostgreSQL+asyncpg URL template
  - [x] 3.3: Update `env.py` for async migrations using `run_sync` pattern
  - [x] 3.4: Import models metadata in `env.py` for autogenerate
  - [x] 3.5: Create initial migration: `alembic revision --autogenerate -m "001_initial_channels_table"`
  - [x] 3.6: Review and manually verify generated migration

- [x] Task 4: Write tests for database layer (AC: #1, #2)
  - [x] 4.1: Create `tests/conftest.py` with async test database fixtures
  - [x] 4.2: Create `tests/test_database.py` for connection tests
  - [x] 4.3: Create `tests/test_models.py` for Channel model tests
  - [x] 4.4: Test channel creation with all fields
  - [x] 4.5: Test channel isolation query by `channel_id`
  - [x] 4.6: Test unique constraint on `channel_id`

## Dev Notes

### Critical Technical Requirements

**Technology Stack (MANDATORY versions):**
- Python 3.10+ (match type `|` syntax)
- SQLAlchemy >=2.0.0 (MUST use async patterns - 1.x incompatible)
- asyncpg >=0.29.0 (NOT psycopg2 - async only)
- Alembic >=1.13.0 (async migrations)

**Database Connection Pattern:**
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

DATABASE_URL = os.getenv("DATABASE_URL")  # postgresql+asyncpg://...
# Railway provides DATABASE_URL - ensure +asyncpg protocol

engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,  # Railway connection recycling
    echo=False,  # Set True only for debugging
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # CRITICAL: prevents attribute expiration
)
```

**FastAPI Dependency Injection Pattern:**
```python
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

**SQLAlchemy 2.0 Model Pattern (MANDATORY):**
```python
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

class Base(DeclarativeBase):
    pass

class Channel(Base):
    __tablename__ = "channels"

    # CORRECT: Use Mapped[type] annotations
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    channel_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

**Alembic Async env.py Pattern:**
```python
import asyncio
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online():
    asyncio.run(run_async_migrations())
```

### Anti-Patterns to AVOID

```python
# WRONG: Legacy SQLAlchemy 1.x Column syntax
class Channel(Base):
    id = Column(UUID, primary_key=True)  # OLD SYNTAX - DO NOT USE

# WRONG: Synchronous engine
from sqlalchemy import create_engine  # WRONG - use create_async_engine

# WRONG: psycopg2 driver
"postgresql://..."  # WRONG - use "postgresql+asyncpg://..."

# WRONG: Blocking database calls in async code
session.execute(...)  # WRONG - use await session.execute(...)

# WRONG: Holding transactions during long operations
async with session.begin():
    await long_running_operation()  # NEVER hold transaction during this
```

### Project Structure Notes

**File Locations (MANDATORY):**
```
app/
├── __init__.py
├── database.py          # THIS STORY: Async engine, session factory, get_session()
├── models.py            # THIS STORY: Channel model (add more models here until 500 lines)
└── ...

alembic/
├── env.py               # THIS STORY: Configure for async
├── versions/
│   └── 001_initial_channels_table.py
└── alembic.ini

tests/
├── conftest.py          # THIS STORY: Async test fixtures
├── test_database.py     # THIS STORY: Connection tests
└── test_models.py       # THIS STORY: Model tests
```

**Naming Conventions:**
- Tables: plural snake_case (`channels`, NOT `channel`)
- Columns: snake_case (`channel_id`, NOT `channelId`)
- Primary keys: Always `id` (UUID), NEVER `{table}_id`
- Foreign keys: `{table_singular}_id` (e.g., `channel_id` referencing `channels.id`)
- Indexes: `ix_{table}_{column}` (e.g., `ix_channels_channel_id`)

### Testing Requirements

**Async Test Setup:**
```python
# tests/conftest.py
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

@pytest_asyncio.fixture
async def async_session():
    # Use in-memory SQLite for fast tests
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session_factory() as session:
        yield session

    await engine.dispose()
```

**Required Test Coverage:**
- Channel CRUD operations (create, read by id, read by channel_id)
- Unique constraint violation on duplicate `channel_id`
- `is_active` default value
- `created_at`/`updated_at` auto-population
- Session commit/rollback behavior

### Environment Variables

**Required:**
- `DATABASE_URL`: PostgreSQL connection string with asyncpg driver
  - Format: `postgresql+asyncpg://user:pass@host:5432/dbname`
  - Railway provides this; ensure `+asyncpg` is added

**Optional (for local dev):**
- `DATABASE_ECHO`: Set to "true" for SQL query logging

### References

- [Source: _bmad-output/planning-artifacts/architecture.md - SQLAlchemy Models Organization]
- [Source: _bmad-output/planning-artifacts/architecture.md - Transaction Patterns]
- [Source: _bmad-output/project-context.md - Technology Stack & Versions]
- [Source: _bmad-output/project-context.md - Database Session Management]
- [Source: _bmad-output/planning-artifacts/epics.md - Story 1.1 Acceptance Criteria]
- [Source: SQLAlchemy 2.0 Async Documentation - create_async_engine, async_sessionmaker]
- [Source: Alembic Cookbook - Using Asyncio with Alembic]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- All 30 tests pass: `uv run pytest tests/ -v` (13 initial → 27 after automation → 30 after code review)

### Completion Notes List

- Created async SQLAlchemy 2.0 database layer with proper pool configuration
- Implemented Channel model with Mapped[type] annotations (SQLAlchemy 2.0 pattern)
- Used timezone-aware datetime (Python 3.11+ compatible) instead of deprecated utcnow()
- Set up Alembic for async migrations with asyncpg driver
- Created comprehensive test suite with 13 passing tests covering:
  - Database connection and session management
  - Channel CRUD operations
  - Unique constraint enforcement
  - Default value behavior
  - Channel isolation queries (FR9)
- Added required dependencies to pyproject.toml
- Configured pytest with asyncio_mode="auto"

### File List

**New Files:**
- `app/__init__.py` - Package initialization
- `app/database.py` - Async engine, session factory, get_session() dependency
- `app/models.py` - Channel model with SQLAlchemy 2.0 patterns
- `alembic.ini` - Alembic configuration
- `alembic/env.py` - Async migration environment
- `alembic/script.py.mako` - Migration template
- `alembic/versions/20260110_0001_001_initial_channels_table.py` - Initial migration
- `tests/__init__.py` - Test package initialization
- `tests/conftest.py` - Shared async test fixtures
- `tests/test_database.py` - Database connection tests
- `tests/test_models.py` - Channel model tests

**Modified Files:**
- `pyproject.toml` - Added SQLAlchemy, asyncpg, Alembic, pytest dependencies and configuration

## Change Log

- 2026-01-10: Initial implementation complete - all 4 tasks with 22 subtasks implemented and tested
- 2026-01-10: Test automation expanded - 14 new tests added (27 total), covering:
  - `_get_database_url()` error handling and URL conversion (4 tests)
  - Session rollback and isolation behavior (2 tests)
  - Channel CRUD operations (delete, update, count, bulk create) (4 tests)
  - Active/inactive filtering, UUID uniqueness (4 tests)
- 2026-01-10: Code review completed - 7 issues fixed (2 High, 3 Medium, 2 Low):
  - H1: Fixed migration DateTime columns to use `timezone=True` (PostgreSQL compatibility)
  - H2: Removed duplicate index on channel_id, kept UniqueConstraint with explicit name
  - M1: Added `__all__` exports to `app/__init__.py` for clear public API
  - M2: Updated `pyproject.toml` to use `dependency-groups.dev` (deprecated `tool.uv.dev-dependencies`)
  - M3: Added 3 tests for `get_session()` FastAPI dependency (RuntimeError, commit, rollback)
  - L1: Clarified `alembic.ini` database URL is overridden at runtime
  - L2: Added `index=True` to `is_active` column for query optimization
  - Final test count: 30 tests passing
