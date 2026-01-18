# End-to-End Testing Strategy

**Document Status:** DRAFT
**Created:** 2026-01-18
**Authors:** Dana (Test/QA Lead), Charlie (Senior Dev), Elena (Product Manager)
**Epic:** Preparation Sprint (Epic 4 Action Item 3, Epic 5 Retrospective Action 3)

---

## Executive Summary

This document defines the comprehensive testing strategy for the 8-SOP video generation pipeline. It addresses testing gaps identified in Epic 4 and Epic 5 retrospectives, provides reusable test patterns, and establishes infrastructure for Epic 6's complex retry logic.

**Key Goals:**
- Define clear boundaries between unit, integration, and E2E tests
- Provide reusable fixtures for all 8 SOPs
- Establish time-mocking strategy for long-running operations
- Enable confident refactoring through comprehensive test coverage
- Support Epic 6's retry logic testing requirements

---

## Test Types & Boundaries

### Unit Tests
**Scope:** Single function or class in isolation
**Database:** Mocked (`mock_async_session`)
**External APIs:** Mocked
**Duration:** < 100ms per test
**Example:** Test individual SOP business logic

```python
@pytest.mark.asyncio
async def test_asset_manifest_creation_unit(mock_async_session):
    """Unit test: AssetGenerationService creates correct manifest."""
    service = AssetGenerationService("poke1", "project_123")
    manifest = service.create_asset_manifest(
        topic="Pikachu",
        story_direction="Forest adventure"
    )
    assert len(manifest.assets) == 22
    assert manifest.global_atmosphere is not None
```

### Integration Tests
**Scope:** Multiple components working together (e.g., service + database)
**Database:** Real in-memory SQLite (`async_test_session`)
**External APIs:** Mocked
**Duration:** < 1s per test
**Example:** Test worker + service + database integration

```python
@pytest.mark.asyncio
async def test_video_review_approval_integration(async_session, patch_session_factory):
    """Integration test: Approval flow updates task status correctly."""
    # Create test task in VIDEO_READY state
    task = Task(status=TaskStatus.VIDEO_READY, ...)
    async_session.add(task)
    await async_session.commit()

    # Execute approval workflow
    await _handle_approval_status_change(page_id=task.notion_page_id, ...)

    # Verify database state
    await async_session.refresh(task)
    assert task.status == TaskStatus.QUEUED
    assert task.review_completed_at is not None
```

### End-to-End Tests
**Scope:** Full pipeline from QUEUED → FINAL_REVIEW (all 8 SOPs)
**Database:** Real in-memory SQLite (`async_test_session`)
**External APIs:** Mocked with realistic responses
**Duration:** < 10s per test (with time-mocking)
**Example:** Test complete 8-SOP pipeline execution

```python
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_full_pipeline_success_e2e(async_session, patch_all_workers, mock_all_apis):
    """E2E test: Full pipeline from QUEUED to FINAL_REVIEW."""
    # Arrange: Create task in QUEUED state
    task = Task(status=TaskStatus.QUEUED, ...)
    async_session.add(task)
    await async_session.commit()

    # Act: Execute full pipeline (all 8 SOPs)
    await execute_full_pipeline(task.id)

    # Assert: Task reaches FINAL_REVIEW with all outputs
    await async_session.refresh(task)
    assert task.status == TaskStatus.FINAL_REVIEW
    assert task.final_video_path is not None
    assert task.total_cost_usd > 0
```

---

## Test Infrastructure

### Existing Fixtures (from `tests/conftest.py` and `tests/fixtures/database.py`)

| Fixture | Purpose | Test Type |
|---------|---------|-----------|
| `mock_async_session` | Mocked AsyncSession | Unit |
| `async_test_session` | Real SQLite session | Integration, E2E |
| `async_test_engine` | Real SQLite engine | Integration, E2E |
| `test_session_factory` | Real session factory | Integration, E2E |
| `mock_session_factory` | Mocked session factory | Unit |
| `sample_task_data` | Sample task attributes | All |
| `sample_channel_data` | Sample channel attributes | All |
| `encryption_env` | Encryption test setup | Unit, Integration |

### New Fixtures Required for E2E Testing

#### 1. SOP Mocking Fixtures

```python
# tests/fixtures/sop_mocks.py

@pytest.fixture
def mock_gemini_api():
    """Mock Gemini image generation API with realistic responses."""
    with patch("app.services.asset_generation.run_cli_script") as mock:
        mock.return_value = {
            "output_path": "/tmp/asset_1.png",
            "cost_usd": 0.05,
            "duration_seconds": 2.3
        }
        yield mock

@pytest.fixture
def mock_kling_api():
    """Mock Kling video generation API with realistic responses."""
    with patch("app.services.video_generation.run_cli_script") as mock:
        mock.return_value = {
            "output_path": "/tmp/video_1.mp4",
            "cost_usd": 0.50,
            "duration_seconds": 120.5
        }
        yield mock

@pytest.fixture
def mock_elevenlabs_api():
    """Mock ElevenLabs audio generation API."""
    with patch("app.services.narration_generation.run_cli_script") as mock:
        mock.return_value = {
            "output_path": "/tmp/audio_1.mp3",
            "cost_usd": 0.02,
            "duration_seconds": 5.2
        }
        yield mock

@pytest.fixture
def mock_ffmpeg():
    """Mock FFmpeg video assembly."""
    with patch("app.services.video_assembly.run_cli_script") as mock:
        mock.return_value = {
            "output_path": "/tmp/final.mp4",
            "duration": 90.0,
            "file_size_mb": 45.2
        }
        yield mock

@pytest.fixture
def mock_all_apis(mock_gemini_api, mock_kling_api, mock_elevenlabs_api, mock_ffmpeg):
    """Mock all external APIs for E2E tests."""
    return {
        "gemini": mock_gemini_api,
        "kling": mock_kling_api,
        "elevenlabs": mock_elevenlabs_api,
        "ffmpeg": mock_ffmpeg
    }
```

#### 2. Worker Orchestration Fixtures

```python
# tests/fixtures/workers.py

@pytest.fixture
def patch_all_workers(async_session, monkeypatch):
    """Patch all worker session factories to use test database."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_factory():
        yield async_session

    # Patch all worker modules
    worker_modules = [
        "app.workers.asset_worker",
        "app.workers.composite_worker",
        "app.workers.video_generation_worker",
        "app.workers.narration_generation_worker",
        "app.workers.sfx_generation_worker",
        "app.workers.video_assembly_worker",
        "app.workers.pipeline_worker",
    ]

    for module in worker_modules:
        monkeypatch.setattr(f"{module}.async_session_factory", mock_factory)

    return async_session

@pytest.fixture
async def execute_full_pipeline():
    """Helper to execute full 8-SOP pipeline for E2E tests."""
    from app.workers.asset_worker import process_asset_generation_task
    from app.workers.composite_worker import process_composite_creation_task
    from app.workers.video_generation_worker import process_video_generation_task
    from app.workers.narration_generation_worker import process_narration_generation_task
    from app.workers.sfx_generation_worker import process_sfx_generation_task
    from app.workers.video_assembly_worker import process_video_assembly_task

    async def _execute(task_id: str):
        """Execute full pipeline sequentially."""
        # SOP 1: Asset Generation
        await process_asset_generation_task(task_id)

        # SOP 2: Composite Creation
        await process_composite_creation_task(task_id)

        # SOP 3: Video Generation
        await process_video_generation_task(task_id)

        # SOP 4: Narration Generation
        await process_narration_generation_task(task_id)

        # SOP 5: SFX Generation
        await process_sfx_generation_task(task_id)

        # SOP 6: Video Assembly
        await process_video_assembly_task(task_id)

    return _execute
```

#### 3. Time-Mocking Fixtures

```python
# tests/fixtures/time_mocking.py

import pytest
from freezegun import freeze_time
from datetime import datetime, timedelta, timezone

@pytest.fixture
def freeze_pipeline_time():
    """Freeze time for testing time-dependent logic (review durations, retry delays)."""
    # Start at a known timestamp
    start_time = datetime(2026, 1, 18, 10, 0, 0, tzinfo=timezone.utc)
    with freeze_time(start_time) as frozen_time:
        yield frozen_time

@pytest.fixture
def mock_async_sleep(monkeypatch):
    """Mock asyncio.sleep to prevent delays in tests."""
    from unittest.mock import AsyncMock
    mock_sleep = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", mock_sleep)
    return mock_sleep

@pytest.fixture
def accelerated_time():
    """Accelerate time progression for testing retry delays (Epic 6).

    Example:
        with accelerated_time(factor=1000):
            # 1 second in test = 1000 seconds in system
            await retry_with_backoff()  # Completes instantly
    """
    from contextlib import contextmanager

    @contextmanager
    def _accelerate(factor: int = 1000):
        """Accelerate time by factor (e.g., 1000x faster)."""
        # This would patch datetime.now() and time.time() to progress faster
        # Implementation depends on testing framework capabilities
        yield

    return _accelerate
```

---

## Time-Mocking Strategy

### Problem
Long-running operations (video generation: 36-90 min) and time-based logic (exponential backoff: minutes to hours) make tests slow and unreliable without time-mocking.

### Solution: Multi-Level Time Control

#### Level 1: Mock External API Delays
**Target:** Remove actual API call latency
**Tool:** Mock `run_cli_script` to return instantly
**Benefit:** Reduces test time from minutes to milliseconds

```python
@pytest.fixture
def mock_fast_video_generation():
    """Mock video generation to return instantly."""
    with patch("app.services.video_generation.run_cli_script") as mock:
        # Instant return instead of 2-5 minute actual call
        mock.return_value = {"output_path": "/tmp/video.mp4", "cost_usd": 0.50}
        yield mock
```

#### Level 2: Mock asyncio.sleep()
**Target:** Remove intentional delays (rate limiting, retry backoff)
**Tool:** `mock_async_sleep` fixture
**Benefit:** Tests run instantly without waiting for delays

```python
@pytest.mark.asyncio
async def test_retry_with_backoff(mock_async_sleep):
    """Test exponential backoff without waiting."""
    await retry_with_exponential_backoff(max_retries=5)

    # Verify backoff delays were calculated correctly
    assert mock_async_sleep.call_count == 5
    assert mock_async_sleep.call_args_list[0][0][0] == 1  # 1 sec
    assert mock_async_sleep.call_args_list[1][0][0] == 2  # 2 sec
    assert mock_async_sleep.call_args_list[2][0][0] == 4  # 4 sec
```

#### Level 3: Freeze Time for Deterministic Testing
**Target:** Time-dependent logic (review durations, claim timeouts)
**Tool:** `freezegun` library
**Benefit:** Deterministic timestamps for assertions

```python
@pytest.mark.asyncio
async def test_review_duration_calculation(freeze_pipeline_time):
    """Test review duration with frozen time."""
    task = Task(review_started_at=datetime.now(timezone.utc))

    # Advance time by 30 seconds
    freeze_pipeline_time.tick(delta=timedelta(seconds=30))

    task.review_completed_at = datetime.now(timezone.utc)
    duration = (task.review_completed_at - task.review_started_at).total_seconds()

    # Exact assertion possible with frozen time
    assert duration == 30.0
```

#### Level 4: Accelerated Time for Long Operations (Epic 6)
**Target:** Multi-hour retry sequences
**Tool:** Custom time acceleration (future enhancement)
**Benefit:** Test 24-hour retry sequences in seconds

```python
@pytest.mark.asyncio
async def test_24_hour_retry_sequence(accelerated_time):
    """Test retry sequence over 24 hours (runs in 1 second)."""
    with accelerated_time(factor=86400):  # 86400x faster (1 day = 1 sec)
        result = await retry_with_exponential_backoff(
            max_duration_hours=24,
            max_retries=10
        )
        assert result.total_retries == 10
        assert result.total_duration_hours == 24
```

### Time-Mocking Best Practices

1. **Always mock external APIs** - Never make real API calls in tests
2. **Mock asyncio.sleep() in unit tests** - Remove artificial delays
3. **Use freezegun for timestamp assertions** - Deterministic time progression
4. **Document time assumptions** - Clearly state what time behavior is mocked
5. **Test time-dependent edge cases** - Timezone handling, leap seconds, DST

---

## E2E Test Templates

### Template 1: Full Pipeline Success Path

```python
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_full_pipeline_success_e2e(
    async_session,
    patch_all_workers,
    mock_all_apis,
    mock_async_sleep,
    execute_full_pipeline
):
    """E2E test: Full 8-SOP pipeline completes successfully.

    Flow: QUEUED → GENERATING_ASSETS → ASSETS_READY → GENERATING_COMPOSITES →
          COMPOSITES_READY → GENERATING_VIDEO → VIDEO_READY → GENERATING_AUDIO →
          AUDIO_READY → GENERATING_SFX → SFX_READY → ASSEMBLING → FINAL_REVIEW

    Verifies:
    - All SOP status transitions
    - Cost tracking accumulation
    - File outputs exist
    - Review timestamps set correctly
    """
    # Arrange: Create channel and task
    channel = Channel(channel_id="test1", channel_name="Test", storage_strategy="notion")
    async_session.add(channel)
    await async_session.flush()

    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion_abc123",
        title="Pikachu Documentary",
        topic="Pikachu",
        story_direction="Forest adventure",
        status=TaskStatus.QUEUED,
        total_cost_usd=0.0
    )
    async_session.add(task)
    await async_session.commit()

    # Act: Execute full pipeline
    await execute_full_pipeline(str(task.id))

    # Assert: Task completed successfully
    await async_session.refresh(task)
    assert task.status == TaskStatus.FINAL_REVIEW
    assert task.final_video_path is not None
    assert task.final_video_duration > 0
    assert task.total_cost_usd > 0  # Cost accumulated from all SOPs
    assert task.review_started_at is None  # Final review hasn't started yet

    # Assert: No errors logged
    assert task.error_log is None or task.error_log == ""
```

### Template 2: Partial Failure & Recovery (Epic 6)

```python
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_pipeline_video_failure_resume_e2e(
    async_session,
    patch_all_workers,
    mock_all_apis,
    execute_full_pipeline
):
    """E2E test: Pipeline resumes from failure point after retry.

    Scenario:
    1. Assets and composites complete successfully
    2. Video generation fails (simulated API timeout)
    3. Task marked VIDEO_ERROR with step_completion_metadata
    4. Retry resumes from video generation (skips assets & composites)
    5. Pipeline completes successfully

    Tests Epic 6 Story 6.3 (Resume from Failure Point) with
    ADR-001 (Pipeline Resumability Architecture).
    """
    # Arrange: Create task
    channel = Channel(channel_id="test1", ...)
    task = Task(status=TaskStatus.QUEUED, ...)
    async_session.add_all([channel, task])
    await async_session.commit()

    # Act 1: Execute pipeline with simulated video generation failure
    mock_all_apis["kling"].side_effect = Exception("Kling API timeout")

    try:
        await execute_full_pipeline(str(task.id))
    except Exception:
        pass  # Expected failure

    # Assert 1: Task in error state with completed steps tracked
    await async_session.refresh(task)
    assert task.status == TaskStatus.VIDEO_ERROR
    assert task.step_completion_metadata is not None
    assert "assets" in task.step_completion_metadata["completed_steps"]
    assert "composites" in task.step_completion_metadata["completed_steps"]
    assert "videos" not in task.step_completion_metadata["completed_steps"]

    # Act 2: Retry - remove error, execute pipeline
    mock_all_apis["kling"].side_effect = None  # Fix API
    task.status = TaskStatus.QUEUED
    await async_session.commit()

    await execute_full_pipeline(str(task.id))

    # Assert 2: Pipeline completed, skipped already-completed steps
    await async_session.refresh(task)
    assert task.status == TaskStatus.FINAL_REVIEW

    # Verify assets and composites were NOT regenerated (cost saved)
    # This would require tracking API call counts in mock
    assert mock_all_apis["gemini"].call_count == 22  # Only called once (first run)
    assert mock_all_apis["kling"].call_count == 18   # Only called once (second run)
```

### Template 3: Review Gate Enforcement

```python
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_review_gates_halt_pipeline_e2e(
    async_session,
    patch_all_workers,
    mock_all_apis,
    execute_full_pipeline
):
    """E2E test: Review gates halt pipeline until human approval.

    Tests Story 5.2 (Review Gate Enforcement):
    - Pipeline halts at VIDEO_READY (review gate)
    - Pipeline does NOT auto-progress to audio generation
    - Human approval required to proceed

    Critical for YouTube compliance (July 2025 policy).
    """
    # Arrange
    channel = Channel(channel_id="test1", ...)
    task = Task(status=TaskStatus.QUEUED, ...)
    async_session.add_all([channel, task])
    await async_session.commit()

    # Act: Execute pipeline up to video generation
    from app.workers.asset_worker import process_asset_generation_task
    from app.workers.composite_worker import process_composite_creation_task
    from app.workers.video_generation_worker import process_video_generation_task

    await process_asset_generation_task(str(task.id))
    await process_composite_creation_task(str(task.id))
    await process_video_generation_task(str(task.id))

    # Assert: Pipeline HALTED at VIDEO_READY (review gate)
    await async_session.refresh(task)
    assert task.status == TaskStatus.VIDEO_READY
    assert task.review_started_at is not None  # Review timestamp set

    # Assert: Audio generation NOT triggered automatically
    # (would require checking queue or worker state)

    # Act: Simulate human approval
    task.status = TaskStatus.VIDEO_APPROVED
    task.review_completed_at = datetime.now(timezone.utc)
    task.status = TaskStatus.QUEUED  # Re-queue for next SOP
    await async_session.commit()

    # Assert: Pipeline can now proceed to audio generation
    from app.workers.narration_generation_worker import process_narration_generation_task
    await process_narration_generation_task(str(task.id))

    await async_session.refresh(task)
    assert task.status == TaskStatus.AUDIO_READY
```

---

## Test Organization

### Directory Structure

```
tests/
├── unit/                       # Unit tests (< 100ms each)
│   ├── test_services/
│   │   ├── test_asset_generation.py
│   │   ├── test_video_generation.py
│   │   └── ...
│   ├── test_workers/
│   │   ├── test_asset_worker.py
│   │   └── ...
│   └── test_utils/
│       └── ...
├── integration/                # Integration tests (< 1s each)
│   ├── test_video_review_workflow.py  # Story 5.4
│   ├── test_round_robin_behavior.py   # Story 4.4
│   └── test_sop_integration/
│       ├── test_asset_to_composite.py
│       ├── test_video_to_audio.py
│       └── ...
├── e2e/                        # End-to-end tests (< 10s each)
│   ├── test_full_pipeline_success.py
│   ├── test_pipeline_failure_recovery.py
│   ├── test_review_gates.py
│   └── test_retry_logic.py    # Epic 6
├── fixtures/                   # Reusable fixtures
│   ├── __init__.py
│   ├── database.py             # Existing DB fixtures
│   ├── sop_mocks.py            # NEW: API mocks
│   ├── workers.py              # NEW: Worker orchestration
│   └── time_mocking.py         # NEW: Time control
├── conftest.py                 # Global fixtures
└── pytest.ini                  # Pytest configuration
```

### Test Markers

```ini
# pytest.ini

[pytest]
markers =
    unit: Unit tests (fast, isolated, mocked)
    integration: Integration tests (real DB, mocked APIs)
    e2e: End-to-end tests (full pipeline, comprehensive)
    slow: Tests that take > 1 second
    epic6: Tests for Epic 6 retry logic
```

### Running Tests

```bash
# Run all tests
pytest

# Run only unit tests (fast)
pytest -m unit

# Run integration tests
pytest -m integration

# Run E2E tests
pytest -m e2e

# Run Epic 6 tests
pytest -m epic6

# Run tests with coverage
pytest --cov=app --cov-report=html

# Run tests in parallel (requires pytest-xdist)
pytest -n auto
```

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml

name: Test Suite

on:
  push:
    branches: [main, feat/**]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install uv
          uv sync

      - name: Run unit tests
        run: uv run pytest -m unit --cov=app --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install uv
          uv sync

      - name: Run integration tests
        run: uv run pytest -m integration

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install uv
          uv sync

      - name: Run E2E tests
        run: uv run pytest -m e2e --maxfail=1

      - name: Archive failure artifacts
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: test-failures
          path: tests/reports/
```

### Railway Deployment Integration

```yaml
# railway.json (Railway configuration)

{
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "uv sync && uv run pytest -m 'unit or integration'"
  },
  "deploy": {
    "startCommand": "python -m app.workers.pipeline_worker",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 300
  }
}
```

---

## Success Metrics

### Test Coverage Goals

| Component | Unit Test Coverage | Integration Tests | E2E Tests |
|-----------|-------------------|-------------------|-----------|
| Services | ≥ 90% | Key workflows | Happy path |
| Workers | ≥ 85% | All SOPs | Full pipeline |
| Models | ≥ 95% | CRUD operations | State transitions |
| Utils | ≥ 90% | N/A | N/A |
| **Overall** | **≥ 85%** | **≥ 50 tests** | **≥ 5 tests** |

### Quality Gates

- ✅ All tests pass before merge
- ✅ No decrease in coverage (threshold: 85%)
- ✅ E2E tests pass on main branch
- ✅ Performance: Unit tests < 100ms, Integration < 1s, E2E < 10s
- ✅ No flaky tests (tests must pass 3/3 runs)

---

## Epic 6 Testing Requirements

Epic 6 (Error Handling & Auto-Recovery) introduces complex retry logic that requires specialized testing:

### Retry Logic Testing Needs

1. **Transient Failure Detection**
   - Test classification: network timeout vs. invalid input
   - Mock various API error responses
   - Verify correct retry vs. terminal error determination

2. **Exponential Backoff**
   - Test backoff calculation: 1s, 2s, 4s, 8s, 16s
   - Test max retry limits
   - Time-mock to avoid long test duration

3. **Resume from Failure Point**
   - Test SOP-level resumption (covered by ADR-001)
   - Verify `step_completion_metadata` tracking
   - Test partial regeneration (Story 5.4 pattern)

4. **Retry State Visibility**
   - Test retry count tracking
   - Test retry history logging
   - Test Notion status updates during retries

### Epic 6 Test Template

```python
@pytest.mark.asyncio
@pytest.mark.epic6
async def test_exponential_backoff_retry_e2e(
    async_session,
    patch_all_workers,
    mock_all_apis,
    mock_async_sleep,
    freeze_pipeline_time
):
    """E2E test: Exponential backoff retry with time-mocking.

    Scenario:
    - Video generation fails with 429 rate limit (transient)
    - System retries with exponential backoff: 1s, 2s, 4s
    - Succeeds on 3rd attempt
    - Verify backoff delays and retry count tracking
    """
    # Arrange: Create task
    task = Task(status=TaskStatus.QUEUED, ...)
    async_session.add(task)
    await async_session.commit()

    # Mock API: Fail twice, succeed third time
    call_count = 0
    def mock_kling_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("429 Too Many Requests")
        return {"output_path": "/tmp/video.mp4", "cost_usd": 0.50}

    mock_all_apis["kling"].side_effect = mock_kling_side_effect

    # Act: Execute video generation with retry
    from app.workers.video_generation_worker import process_video_generation_task
    await process_video_generation_task(str(task.id))

    # Assert: Retries executed with correct backoff
    assert call_count == 3
    assert mock_async_sleep.call_count == 2  # 2 retries = 2 sleep calls
    assert mock_async_sleep.call_args_list[0][0][0] == 1  # 1 second
    assert mock_async_sleep.call_args_list[1][0][0] == 2  # 2 seconds

    # Assert: Task succeeded after retries
    await async_session.refresh(task)
    assert task.status == TaskStatus.VIDEO_READY

    # Assert: Retry metadata tracked
    assert task.retry_count == 2
    assert task.error_log is not None
    assert "429 Too Many Requests" in task.error_log
```

---

## Action Items

### Immediate (Epic 6 Preparation)

1. **Implement SOP Mock Fixtures** (4 hours)
   - Create `tests/fixtures/sop_mocks.py`
   - Mock Gemini, Kling, ElevenLabs, FFmpeg APIs
   - Ensure realistic response structure

2. **Implement Worker Orchestration Fixtures** (4 hours)
   - Create `tests/fixtures/workers.py`
   - `patch_all_workers` fixture
   - `execute_full_pipeline` helper

3. **Implement Time-Mocking Fixtures** (4 hours)
   - Create `tests/fixtures/time_mocking.py`
   - Install `freezegun` library
   - `freeze_pipeline_time`, `mock_async_sleep` fixtures

4. **Write 3 E2E Test Templates** (8 hours)
   - Create `tests/e2e/test_full_pipeline_success.py`
   - Create `tests/e2e/test_pipeline_failure_recovery.py`
   - Create `tests/e2e/test_review_gates.py`

5. **Configure CI/CD** (4 hours)
   - Create `.github/workflows/test.yml`
   - Configure test markers in `pytest.ini`
   - Set up coverage reporting

**Total Effort:** 24 hours (3 days)

### Medium Priority (During Epic 6)

6. **Write Epic 6 Retry Tests** (12 hours)
   - Create `tests/e2e/test_retry_logic.py`
   - Test exponential backoff
   - Test transient failure detection
   - Test retry state visibility

7. **Performance Testing** (8 hours)
   - Add performance benchmarks
   - Test claim duration under load
   - Test database connection pool behavior

### Low Priority (Post-Epic 6)

8. **Mutation Testing** (16 hours)
   - Install `mutmut` library
   - Run mutation tests on critical paths
   - Improve test quality based on findings

9. **Property-Based Testing** (12 hours)
   - Install `hypothesis` library
   - Write property tests for state machine
   - Test edge cases automatically

---

## Conclusion

This E2E testing strategy provides:
- ✅ Clear boundaries between unit, integration, and E2E tests
- ✅ Reusable fixtures for all 8 SOPs
- ✅ Time-mocking strategy for long-running operations
- ✅ CI/CD integration for automated testing
- ✅ Epic 6 readiness for complex retry logic testing

**Next Steps:**
1. Implement immediate action items (24 hours)
2. Review with team for feedback
3. Begin Epic 6 development with testing infrastructure in place

**Status:** READY FOR IMPLEMENTATION 🚀
