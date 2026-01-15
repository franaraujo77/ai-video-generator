---
story_key: '3-1-cli-script-wrapper-async-execution'
epic_id: '3'
story_id: '1'
title: 'CLI Script Wrapper & Async Execution'
status: 'done'
priority: 'critical'
story_points: 3
created_at: '2026-01-15'
completed_at: '2026-01-15'
assigned_to: ''
dependencies: []
blocks: ['3-2', '3-3', '3-4']
ready_for_dev: true
---

# Story 3.1: CLI Script Wrapper & Async Execution

**Epic:** 3 - Video Generation Pipeline
**Priority:** Critical
**Story Points:** 3
**Status:** Done ✅

## Story Description

**As a** worker process orchestrating video generation,
**I want to** invoke CLI scripts via a non-blocking async subprocess wrapper,
**So that** I can execute long-running operations (video generation, audio synthesis) without blocking the Python event loop or holding database connections.

## Context & Background

The video generation pipeline requires invoking 7 existing CLI scripts (`generate_asset.py`, `create_composite.py`, `generate_video.py`, etc.) from worker processes. These CLI scripts:
- Are stateless and communicate via command-line arguments, stdout/stderr, and exit codes
- Can run for extended periods (video generation: 2-5 minutes per clip)
- Must NOT be imported as Python modules (architectural constraint: "Smart Agent + Dumb Scripts")
- Must be invoked via subprocess to maintain separation of concerns

**Key Architectural Requirements:**
1. **Async Execution:** Use `asyncio.to_thread()` to wrap blocking `subprocess.run()` calls
2. **Transaction Management:** Never hold database transactions during CLI script execution
3. **Error Handling:** Capture stdout/stderr, parse exit codes, raise structured exceptions
4. **Timeout Management:** Configure per-script timeouts (Gemini: 60s, Kling: 600s, ElevenLabs: 120s)
5. **Logging Integration:** Log script execution with correlation IDs for traceability

**Referenced Architecture Decisions:**
- Architecture Decision 3: Short transaction pattern (claim → close DB → execute → reopen DB → update)
- project-context.md: CLI Scripts Architecture section (lines 59-116)
- project-context.md: Integration Utilities (MANDATORY) section (lines 117-278)

## Acceptance Criteria

### Scenario 1: Successful CLI Script Execution
**Given** a worker process needs to invoke `generate_asset.py`
**When** the script is called with valid arguments and completes successfully
**Then** the wrapper should:
- ✅ Execute the script without blocking the async event loop
- ✅ Return a `CompletedProcess` with stdout, stderr, and returncode
- ✅ Not raise any exceptions
- ✅ Log execution start/completion with correlation IDs

### Scenario 2: CLI Script Failure Handling
**Given** a worker process invokes a CLI script that fails (exit code 1)
**When** the script exits with a non-zero exit code
**Then** the wrapper should:
- ✅ Raise a `CLIScriptError` exception with script name, exit code, and stderr
- ✅ Capture and log stderr output for debugging
- ✅ NOT retry automatically (retry logic handled by worker layer)

### Scenario 3: Timeout Handling
**Given** a worker process invokes `generate_video.py` with a 600-second timeout
**When** the script execution exceeds the timeout
**Then** the wrapper should:
- ✅ Terminate the subprocess after timeout period
- ✅ Raise `asyncio.TimeoutError`
- ✅ Log timeout event with script name and duration

### Scenario 4: Event Loop Non-Blocking Behavior
**Given** 3 worker processes are executing long-running CLI scripts concurrently
**When** each worker invokes a script via the async wrapper
**Then** the wrapper should:
- ✅ NOT block other async operations in the same process
- ✅ Allow concurrent execution of other async tasks (database queries, API calls)
- ✅ Use `asyncio.to_thread()` to offload blocking `subprocess.run()` to thread pool

## Technical Specifications

### File Structure
```
app/
└── utils/
    └── cli_wrapper.py       # New file
```

### Core Implementation: `app/utils/cli_wrapper.py`

**Required Classes and Functions:**

```python
class CLIScriptError(Exception):
    """
    Raised when CLI script fails with non-zero exit code.

    Attributes:
        script (str): Script name (e.g., "generate_asset.py")
        exit_code (int): Process exit code
        stderr (str): Captured stderr output
    """
    def __init__(self, script: str, exit_code: int, stderr: str):
        self.script = script
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(f"{script} failed with exit code {exit_code}: {stderr}")

async def run_cli_script(
    script: str,
    args: List[str],
    timeout: int = 600
) -> subprocess.CompletedProcess:
    """
    Run CLI script without blocking async event loop.

    This function wraps `subprocess.run()` with `asyncio.to_thread()` to prevent
    blocking the event loop during long-running CLI operations (video generation,
    audio synthesis, etc.).

    Args:
        script: Script name (e.g., "generate_asset.py")
        args: List of command-line arguments
        timeout: Timeout in seconds (default: 600 = 10 min for Kling videos)

    Returns:
        CompletedProcess with stdout, stderr, returncode

    Raises:
        CLIScriptError: If script exits with non-zero code
        asyncio.TimeoutError: If script exceeds timeout

    Example:
        >>> result = await run_cli_script(
        ...     "generate_asset.py",
        ...     ["--prompt", "A forest scene", "--output", "/path/to/asset.png"],
        ...     timeout=60
        ... )
        >>> print(result.stdout)
        "✅ Asset generated: /path/to/asset.png"
    """
```

### Implementation Requirements

**1. Path Construction:**
- Scripts directory: `Path("scripts")`
- Script path: `script_path = Path("scripts") / script`
- Full command: `["python", str(script_path)] + args`

**2. Async Execution Pattern:**
```python
result = await asyncio.to_thread(
    subprocess.run,
    command,
    capture_output=True,  # Capture stdout/stderr
    text=True,            # Decode as UTF-8 strings
    timeout=timeout       # Enforce timeout
)
```

**3. Error Classification:**
- Exit code 0: Success, return `CompletedProcess`
- Exit code 1-255: Failure, raise `CLIScriptError(script, returncode, stderr)`
- Timeout exceeded: Raise `asyncio.TimeoutError`

**4. Logging Integration:**
- Import: `from app.utils.logging import get_logger`
- Log format: Structured JSON with correlation IDs
- Log events:
  - `"cli_script_start"` - Script execution started
  - `"cli_script_success"` - Script completed successfully
  - `"cli_script_error"` - Script failed with non-zero exit code
  - `"cli_script_timeout"` - Script exceeded timeout

**Example Logging:**
```python
log = get_logger(__name__)

log.info("cli_script_start", script=script, args=args, timeout=timeout)
# Execute script...
if result.returncode != 0:
    log.error("cli_script_error", script=script, exit_code=result.returncode, stderr=result.stderr)
    raise CLIScriptError(script, result.returncode, result.stderr)
log.info("cli_script_success", script=script, stdout=result.stdout)
```

### Usage Pattern (Worker Example)

```python
from app.utils.cli_wrapper import run_cli_script, CLIScriptError

# ✅ CORRECT: Use wrapper, handle errors, log appropriately
try:
    result = await run_cli_script(
        "generate_asset.py",
        ["--prompt", full_prompt, "--output", str(output_path)],
        timeout=60
    )
    log.info("Asset generated", stdout=result.stdout, path=output_path)
except CLIScriptError as e:
    log.error("Asset generation failed", script=e.script, stderr=e.stderr, exit_code=e.exit_code)
    raise  # Re-raise for worker to handle (mark task failed, retry, etc.)
except asyncio.TimeoutError:
    log.error("Asset generation timeout", script="generate_asset.py", timeout=60)
    raise

# ❌ WRONG: Direct subprocess call (blocks event loop)
result = subprocess.run(["python", "scripts/generate_asset.py", "--prompt", prompt], ...)
```

## Dependencies

**Required Before Starting:**
- ✅ Python 3.10+ with async/await support
- ✅ Existing CLI scripts in `scripts/` directory (`generate_asset.py`, `generate_video.py`, etc.)

**Must Be Created Alongside This Story:**
- `app/utils/logging.py` - Structured logging configuration (can be stubbed for testing)

**Blocks These Stories:**
- Story 3.2: Asset generation worker
- Story 3.3: Video generation worker
- Story 3.4: Audio generation worker

## Testing Requirements

### Unit Tests: `tests/test_utils/test_cli_wrapper.py`

**Test Cases:**

1. **test_run_cli_script_success()**
   - Mock successful script execution (exit code 0)
   - Verify `CompletedProcess` returned with stdout/stderr
   - Verify no exceptions raised

2. **test_run_cli_script_failure()**
   - Mock script failure (exit code 1)
   - Verify `CLIScriptError` raised with correct attributes
   - Verify stderr captured in exception

3. **test_run_cli_script_timeout()**
   - Mock long-running script that exceeds timeout
   - Verify `asyncio.TimeoutError` raised
   - Verify subprocess terminated

4. **test_run_cli_script_event_loop_non_blocking()**
   - Start 3 concurrent script executions
   - Verify all complete successfully without blocking each other
   - Verify execution time ≈ max(script times), not sum(script times)

5. **test_cli_script_error_attributes()**
   - Raise `CLIScriptError` and verify script, exit_code, stderr attributes
   - Verify exception message format

**Mocking Strategy:**
- Mock `subprocess.run()` to avoid executing real CLI scripts
- Mock `asyncio.to_thread()` if needed for timing tests
- Use `pytest-asyncio` for async test support

**Example Test:**
```python
import pytest
from app.utils.cli_wrapper import run_cli_script, CLIScriptError

@pytest.mark.asyncio
async def test_run_cli_script_success(mocker):
    """Test successful script execution returns CompletedProcess"""
    mock_result = mocker.Mock(returncode=0, stdout="✅ Success", stderr="")
    mocker.patch("asyncio.to_thread", return_value=mock_result)

    result = await run_cli_script("generate_asset.py", ["--output", "/tmp/test.png"])

    assert result.returncode == 0
    assert result.stdout == "✅ Success"

@pytest.mark.asyncio
async def test_run_cli_script_failure(mocker):
    """Test script failure raises CLIScriptError"""
    mock_result = mocker.Mock(returncode=1, stdout="", stderr="❌ API key missing")
    mocker.patch("asyncio.to_thread", return_value=mock_result)

    with pytest.raises(CLIScriptError) as exc_info:
        await run_cli_script("generate_asset.py", ["--output", "/tmp/test.png"])

    assert exc_info.value.script == "generate_asset.py"
    assert exc_info.value.exit_code == 1
    assert "API key missing" in exc_info.value.stderr
```

### Integration Tests (Optional - Mark with `@pytest.mark.integration`)

**test_run_actual_cli_script()**
- Execute a simple test script in `scripts/` that echoes input
- Verify stdout captured correctly
- Mark with `@pytest.mark.integration` (requires actual filesystem)

## Edge Cases & Error Scenarios

1. **Missing Script File:**
   - If `scripts/{script}` doesn't exist, `subprocess.run()` will raise `FileNotFoundError`
   - Let exception propagate (indicates developer error)

2. **Invalid Arguments:**
   - If CLI script receives invalid args, it will exit with code 1
   - `CLIScriptError` raised with stderr containing argparse error message

3. **Script Hangs Indefinitely:**
   - Timeout mechanism terminates subprocess after configured duration
   - `asyncio.TimeoutError` raised

4. **UTF-8 Decode Errors:**
   - If script outputs non-UTF-8 bytes, `text=True` will raise `UnicodeDecodeError`
   - Consider adding error handling or using `errors='replace'` if needed

5. **Concurrent Execution:**
   - Multiple workers can invoke same script simultaneously (each creates separate subprocess)
   - No shared state between invocations (stateless CLI scripts)

## Documentation Requirements

**1. Inline Docstrings:**
- Module docstring explaining purpose of CLI wrapper
- Function docstring with Args/Returns/Raises/Example
- Class docstring for `CLIScriptError`

**2. Architecture Documentation:**
- Update `docs/architecture.md` (if exists) with CLI invocation pattern
- Reference this story in architecture decision log

**3. Usage Examples:**
- Add example to `app/utils/cli_wrapper.py` module docstring
- Document timeout recommendations for each CLI script type

## Definition of Done

- [x] `app/utils/cli_wrapper.py` implemented with `CLIScriptError` and `run_cli_script()`
- [x] All unit tests passing (17 test cases, includes security and edge case tests)
- [x] Async execution verified (uses `asyncio.to_thread()`, non-blocking)
- [x] Error handling complete (exit codes, timeouts, exceptions, UTF-8 errors)
- [x] Logging integration added (structured JSON logs with sanitized sensitive data)
- [x] Type hints complete (all parameters and return types annotated)
- [x] Docstrings complete (module, class, function-level)
- [x] Linting passes (`ruff check --fix .`)
- [x] Type checking passes (`mypy app/`)
- [x] Code review approved (all 11 issues fixed)
- [x] Security validated (path traversal and sensitive data logging fixed)
- [ ] Merged to `main` branch

## Notes & Implementation Hints

**From Architecture (project-context.md):**
- This utility is MANDATORY for all subprocess calls (lines 117-198)
- Part of required integration utilities (alongside filesystem helpers)
- Enforces "Smart Agent + Dumb Scripts" architectural pattern
- Prevents blocking async event loop during long-running operations

**Transaction Management Pattern:**
```python
# Step 1: Claim task (short transaction)
async with AsyncSessionLocal() as db:
    async with db.begin():
        task.status = "processing"
        await db.commit()

# Step 2: Execute CLI script (OUTSIDE transaction)
result = await run_cli_script("generate_video.py", [...], timeout=600)

# Step 3: Update task (short transaction)
async with AsyncSessionLocal() as db:
    async with db.begin():
        task.status = "completed"
        await db.commit()
```

**Timeout Recommendations (from Architecture):**
- Asset generation (Gemini): 60 seconds
- Video generation (Kling): 600 seconds (10 minutes)
- Audio generation (ElevenLabs): 120 seconds
- SFX generation (ElevenLabs): 120 seconds
- Video assembly (FFmpeg): 300 seconds

**Security Considerations:**
- Validate `script` parameter is in `scripts/` directory (prevent path traversal)
- DO NOT pass user input directly to `args` without validation
- Capture stderr to prevent sensitive info leakage (API keys in error messages)

## Related Stories

- **Depends On:** None (foundation story)
- **Blocks:** 3-2 (Asset Worker), 3-3 (Video Worker), 3-4 (Audio Worker)
- **Related:** 2-3 (Async Database Session Management) - both stories implement async patterns

## Source References

**PRD Requirements:**
- FR-VGO-001: Queue-based task management (worker orchestration)
- FR-VGO-002: Preserve existing CLI scripts as workers
- NFR-PER-001: Async I/O throughout backend

**Architecture Decisions:**
- Decision 3: Short transaction pattern (don't hold DB during CLI execution)
- CLI Script Invocation Pattern: subprocess with async wrapper (lines 384-401 in architecture.md)

**Context:**
- project-context.md: CLI Scripts Architecture (lines 59-116)
- project-context.md: Integration Utilities (lines 117-278)
- CLAUDE.md: "Smart Agent + Dumb Scripts" pattern explanation

---

## Dev Agent Record

### Implementation Plan
- **Approach:** Created async CLI wrapper using `asyncio.to_thread()` to prevent blocking event loop
- **Key Design Decisions:**
  - Used StructuredLogger wrapper instead of monkey-patching Logger class to avoid breaking SQLAlchemy/asyncio internals
  - Implemented CLIScriptError exception with script, exit_code, and stderr attributes
  - Used Python 3.10+ type hints (`list[str]`, `subprocess.CompletedProcess[str]`)
  - Structured logging with event-based format: `log.info("event_name", key=value, ...)`

### Completion Notes
- ✅ Implemented `app/utils/cli_wrapper.py` with `CLIScriptError` and `run_cli_script()`
- ✅ Created `app/utils/logging.py` with StructuredLogger wrapper (required dependency)
- ✅ Wrote 17 comprehensive unit tests covering all scenarios including security (exceeds 5 minimum)
- ✅ All tests pass (17/17) including security, edge cases, and integration tests
- ✅ Linting passes with ruff (auto-fixed docstrings, type hints, list concatenation)
- ✅ Type checking passes with mypy (strict mode, no errors)
- ✅ Added pytest-mock dependency for test mocking support
- ✅ Code review completed with all 11 issues fixed

**Test Coverage:**
- Exception class attributes and message format
- Successful script execution with stdout/stderr capture
- Script failure with non-zero exit code
- Timeout handling with asyncio.TimeoutError and exception chain verification
- Non-blocking event loop behavior (concurrent execution test)
- Command construction with proper arguments
- Timeout parameter passing to subprocess
- Logging events on success, failure, and timeout
- **NEW:** Path traversal security validation
- **NEW:** Missing script file handling (FileNotFoundError)
- **NEW:** Sensitive args sanitization in logs (API keys redacted)
- **NEW:** UTF-8 decode error handling with replacement characters
- **NEW:** Integration test with real subprocess execution

**Key Implementation Details:**
- Uses `asyncio.to_thread()` to offload blocking `subprocess.run()` to thread pool
- Enforces timeout management with configurable per-script timeouts
- Captures stdout/stderr for debugging and error reporting
- **NEW:** Structured JSON logging (production-ready for CloudWatch, Datadog, Splunk)
- **NEW:** Security: Validates scripts are within scripts/ directory (prevents path traversal)
- **NEW:** Security: Sanitizes sensitive arguments in logs (API keys, tokens, secrets)
- **NEW:** UTF-8 error handling: Uses errors='replace' to handle non-UTF-8 output
- Type-safe with full type hints including exception attributes

### Code Review Fixes Applied (2026-01-15)

**Adversarial code review identified and fixed 11 issues:**

**HIGH SEVERITY (8 issues fixed):**
1. ✅ **Path Traversal Vulnerability** - Added script path validation with `is_relative_to()` check
2. ✅ **Command Injection Risk** - Added args sanitization for logging (redacts --api-key, --token, --secret, --password)
3. ✅ **Missing FileNotFoundError Handling** - Added explicit script existence check before execution
4. ✅ **Missing UTF-8 Decode Test** - Added `errors='replace'` to subprocess.run() and test for replacement chars
5. ✅ **Logging Exposes Sensitive Data** - Implemented comprehensive args sanitization (redacts keys, truncates long args)
6. ✅ **Type Hint Incompleteness** - Added type annotations to exception instance attributes
7. ✅ **Timeout Exception Chain** - Verified exception chain preserves subprocess.TimeoutExpired with test
8. ✅ **Structured Logging NOT JSON** - Converted StructuredLogger to output actual JSON format with json.dumps()

**MEDIUM SEVERITY (2 issues fixed):**
9. ✅ **Missing Integration Test** - Added real subprocess execution test with temporary script
10. ✅ **Untracked Test Package** - Created tests/test_utils/__init__.py

**LOW SEVERITY (1 issue fixed):**
11. ✅ **Linting Issues** - Fixed unused loop variable, broke long lines for readability

**Security Improvements:**
- Path traversal protection prevents execution of scripts outside scripts/ directory
- Sensitive data redaction in logs prevents API key/token leakage
- Stdout/stderr truncation prevents log bloat from large outputs
- UTF-8 error handling prevents crashes on non-UTF-8 subprocess output

**Test Suite Enhanced:**
- Test count: 11 → 17 (55% increase)
- Added path traversal security test
- Added missing script FileNotFoundError test
- Added sensitive args sanitization test
- Added timeout exception chain verification test
- Added UTF-8 replacement character handling test
- Added real subprocess integration test

**Production Readiness:**
- Logging now outputs JSON for production log aggregation (CloudWatch, Datadog, Splunk)
- All security vulnerabilities addressed
- All documented edge cases have tests
- Architecture compliance validated

---

## File List

### New Files Created
- `app/utils/cli_wrapper.py` - CLI script async wrapper with security (CLIScriptError, run_cli_script)
- `app/utils/logging.py` - Structured JSON logging utility (StructuredLogger, get_logger)
- `tests/test_utils/__init__.py` - Test package marker
- `tests/test_utils/test_cli_wrapper.py` - Comprehensive unit tests (17 test cases including security)

### Modified Files
- `pyproject.toml` - Added pytest-mock>=3.15.1 dev dependency

---

## Change Log

- **2026-01-15 (Initial Implementation):** Story 3.1 implementation complete
  - Created CLI script async wrapper with non-blocking execution
  - Implemented StructuredLogger to avoid breaking internal logging
  - Wrote 11 unit tests with 100% pass rate
  - All linting and type checking passes
  - Ready for code review

- **2026-01-15 (Code Review Fixes):** All 11 review issues addressed
  - Fixed 8 HIGH severity issues (security, architecture compliance)
  - Fixed 2 MEDIUM severity issues (test coverage gaps)
  - Fixed 1 LOW severity issue (linting)
  - Enhanced test suite: 11 → 17 tests (55% increase)
  - Added security validations: path traversal protection, sensitive data sanitization
  - Converted logging to actual JSON output (production-ready)
  - All tests passing (17/17), linting clean, type checking passes
  - Story status: review → done

---

## Status

**Status:** done
**Completed:** 2026-01-15
**Code Review:** Approved (all 11 issues fixed)
**Security:** Validated (path traversal, sensitive logging addressed)
**Ready for:** Merge to main branch
