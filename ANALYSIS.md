# Pre-commit vs PR Validation Differences - Analysis

## Problem Summary

PR validation is catching issues that weren't caught locally before commit/push.

## Root Causes

### 1. Pre-commit Hooks Are NOT Installed ❌

**Evidence:**
```bash
$ ls -la .git/hooks/pre-push
No pre-push hook installed
```

**Impact:** Even though `.pre-commit-config.yaml` exists and `pre-commit` is installed, the git hooks haven't been installed, so NO local checks run before push.

**Solution:** Install hooks with:
```bash
uv run pre-commit install --hook-type pre-push
```

---

### 2. Lint Rule Mismatches Between Local and PR

#### Issue A: Print Statements in Tests (T201)

**Current State:**
- `pyproject.toml` per-file-ignores for `tests/*`:
  ```toml
  "tests/*" = ["S101", "S105", "S106", "S110", "D", "B008", "SIM117", "F401", "F841", "I001", "E501", "RUF022"]
  ```

- **Missing:** `T201` (print statements)
- **Found:** 20 violations in `tests/test_performance.py`, 1 in `tests/test_services/test_notion_sync.py`

**Decision Required:**
- **Option A:** Add `T201` to test ignores (allow print for debugging/performance output)
- **Option B:** Remove all print statements from tests

#### Issue B: Nested With Statements (SIM117)

**Current State:**
- Found in `app/services/webhook_handler.py` (lines 152, 222)
- Tests ignore SIM117, but app code does NOT

**Fix:** Refactor nested `with` statements or add to per-file-ignores

#### Issue C: Unused Loop Variable (B007)

**Location:** `tests/test_performance.py:346`
```python
for i in range(5):  # 'i' not used
    # do something
```

**Fix:** Use `for _ in range(5):` or `for i in range(5):` with actual usage

#### Issue D: f-string Without Placeholders (F541)

**Location:** `tests/test_performance.py:419`

**Fix:** Either add placeholders or use regular string

#### Issue E: Suppressible Exception (SIM105)

**Location:** `tests/test_task_model_26_status.py:167`

**Fix:** Use `contextlib.suppress(IntegrityError)` instead of try-except-pass

---

### 3. Configuration Differences

#### Pre-commit Config (.pre-commit-config.yaml)

```yaml
- id: ruff
  args: [--fix, --exit-non-zero-on-fix]
- id: mypy
  files: ^app/  # Only checks app/
```

#### PR Workflow (.github/workflows/pr-checks.yml)

```yaml
- name: Run Ruff linter
  run: uv run ruff check . --output-format=github

- name: Run Mypy on app/
  run: uv run mypy app/ --config-file=pyproject.toml
```

**Differences:**
1. ✅ Both check all files with ruff
2. ✅ Both check only `app/` with mypy
3. ✅ Pre-commit uses `--fix` (auto-fix), PR uses `--output-format=github` (report only)
4. ⚠️ Pre-commit configured for pre-push, but NOT INSTALLED

---

## Complete Solution

### Step 1: Install Pre-commit Hooks

```bash
# Install pre-push hooks
uv run pre-commit install --hook-type pre-push

# Verify installation
ls -la .git/hooks/pre-push  # Should exist now

# Test hooks
uv run pre-commit run --all-files
```

### Step 2: Fix Per-file-ignores in pyproject.toml

**Option A: Allow print in tests (RECOMMENDED for performance tests)**

```toml
[tool.ruff.lint.per-file-ignores]
# Tests: allow print for debugging/performance output
"tests/*" = [
    "S101", "S105", "S106", "S110",  # Security - asserts, hardcoded passwords
    "D",                              # Docstrings
    "B008", "B007",                   # Bugbear - function call defaults, unused loop vars
    "SIM117", "SIM105",               # Simplify - nested with, suppressible exception
    "F401", "F841", "F541",           # Pyflakes - unused imports/vars, empty f-strings
    "I001",                           # Import sorting
    "E501",                           # Line length
    "RUF022",                         # Ruff-specific
    "T201",                           # Print statements (performance tests need this)
]
```

**Option B: Remove all print statements**

```bash
# Auto-remove print statements (use with caution)
uv run ruff check tests/ --select=T201 --fix --unsafe-fixes
```

### Step 3: Fix App Code Issues

#### Fix SIM117 (Nested With Statements)

**File:** `app/services/webhook_handler.py`

**Before:**
```python
# Line 152
async with session.begin():
    async with session.execute(query) as result:
        # ...

# Line 222
async with session.begin():
    async with session.execute(query) as result:
        # ...
```

**After:**
```python
# Combine into single with statement
async with session.begin(), session.execute(query) as result:
    # ...
```

**OR add exception:**
```toml
"app/services/webhook_handler.py" = ["SIM117"]  # Async context requires nested
```

### Step 4: Fix Test Code Issues

**Fix all auto-fixable issues:**
```bash
uv run ruff check . --fix
```

**Manual fixes needed:**
1. `test_performance.py:346` - Change `for i in` to `for _ in`
2. `test_performance.py:419` - Fix f-string or convert to regular string
3. `test_task_model_26_status.py:167` - Use `contextlib.suppress`

### Step 5: Update Pre-commit Config (Optional Enhancement)

Make pre-commit match PR checks exactly:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        name: ruff (lint)
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format
        name: ruff (format)

      # Add: explicit security check (matches PR)
      - id: ruff
        name: ruff (security)
        args: [--select=S, --exit-non-zero-on-fix]
```

---

## Verification Steps

### 1. Local Pre-push Check (should match PR)

```bash
# Run all pre-commit hooks
uv run pre-commit run --all-files

# Should pass with no errors (after fixes applied)
```

### 2. Manual PR Simulation

```bash
# Run exact same checks as PR workflow
uv run ruff check . --output-format=github
uv run ruff format --check --diff .
uv run mypy app/ --config-file=pyproject.toml
uv run pytest --tb=short -q
uv run ruff check . --select=S --output-format=github
```

All should pass with zero errors.

### 3. Test Push

```bash
# Make a trivial change
echo "# Test" >> README.md

# Stage and commit
git add README.md
git commit -m "test: Verify pre-push hooks working"

# Push - hooks should run automatically
git push

# Hooks should catch any issues before push completes
```

---

## Summary

**Issues Found:**
1. ❌ Pre-commit hooks not installed (critical)
2. ❌ 25 lint violations not caught locally
3. ⚠️ Per-file-ignores incomplete for tests

**Fixes Required:**
1. ✅ Install pre-commit hooks: `uv run pre-commit install --hook-type pre-push`
2. ✅ Add `T201`, `B007`, `SIM105`, `F541` to test ignores OR fix violations
3. ✅ Fix 2 SIM117 violations in `app/services/webhook_handler.py`
4. ✅ Run `uv run ruff check . --fix` for auto-fixable issues

**After Fixes:**
- ✅ Local pre-push checks will match PR validation exactly
- ✅ No surprises in PR - issues caught before push
- ✅ Consistent code quality enforcement across all stages
