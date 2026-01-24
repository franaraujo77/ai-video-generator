# Lint Error Prevention Strategy

**Document Status:** COMPLETED
**Created:** 2026-01-24
**Action Item:** epic6-ai-2 - Lint Error Leakage Investigation
**Owner:** Charlie

---

## Executive Summary

Investigation completed into lint errors "slipping through to push" identified by Francis. **Result: System is now correctly configured with multi-layer protection.**

## Root Cause Analysis

### Historical Issue
Early in the project (pre-Epic 6), lint errors were making it to pushed commits due to:
1. Pre-commit hooks not initially installed
2. Hooks configured for pre-push (not pre-commit), allowing local commits with errors
3. Developers potentially bypassing hooks with `git push --no-verify`

### Recent Fixes
Multiple commits between Jan 13-24, 2026 resolved all outstanding lint errors:
```bash
6c6b0d5 fix: Resolve all remaining linting and type errors
0bcbc4d fix: Continue resolving linting and type errors
30dafc0 fix: Resolve all remaining linting and type errors
e678398 fix: Resolve all remaining linting and type errors
```

## Current Protection Layers

### Layer 1: Pre-Push Hooks (Primary Defense)

**Configuration:** `.pre-commit-config.yaml`

**Hooks Configured:**
1. **Ruff Linter** - Fast Python linting with auto-fix
2. **Ruff Formatter** - Code formatting enforcement
3. **Mypy** - Static type checking
4. **General Checks** - Trailing whitespace, YAML/TOML syntax, large files, merge conflicts, private keys

**Installation:**
```bash
# Install hooks (run once per clone)
uv run pre-commit install --hook-type pre-push

# Run manually on all files
uv run pre-commit run --all-files
```

**Hook Stage:** Pre-push (configured in `.pre-commit-config.yaml:74`)
- **Rationale:** Faster local development (commit without running full checks)
- **Trade-off:** Local commits can have errors, but push is blocked

### Layer 2: GitHub Actions CI (Safety Net)

**Workflow:** `.github/workflows/pr-checks.yml`

**Checks on Every PR and Push to Main:**
1. **Lint Job** - Ruff linter + formatter check
2. **Type Check Job** - Mypy static type analysis
3. **Test Job** - Full pytest suite
4. **Security Job** - Ruff security rules (S category)
5. **Gate Job** - All checks must pass (enforced by branch protection)

**CI Advantages:**
- Catches hook bypasses (`--no-verify`)
- Runs in clean environment (no local config issues)
- Required for PR merge (branch protection enforced)
- Immutable record of check results

## Verification Test Results

**Test Date:** 2026-01-24

**Test Scenario:** Created intentional lint errors in `app/test_lint_check.py`

**Pre-Push Hook Result:** ✅ PASSED
```
ruff (lint)..............................................................Failed
ruff (format)............................................................Failed
mypy (type check)........................................................Failed
```
Hook correctly blocked push with failing checks.

**Current Lint Status:**
```bash
$ uv run ruff check app/
All checks passed!

$ uv run mypy app/
Success: no issues found in 65 source files
```

## Developer Workflow

### Daily Development

1. **Commit Frequently** - No lint checks on commit (fast iteration)
```bash
git add .
git commit -m "WIP: implementing feature"
```

2. **Push to Remote** - Pre-push hooks run automatically
```bash
git push origin feature-branch
# Hooks run automatically, fix any errors before continuing
```

3. **Create PR** - CI runs all checks
- Lint, type check, tests, security checks
- All must pass before merge approval

### Bypassing Hooks (DISCOURAGED)

**Never bypass hooks in normal workflow:**
```bash
# ❌ DON'T DO THIS
git push --no-verify  # Bypasses pre-push hooks
```

**When bypass is acceptable:**
- Emergency hotfixes (with team lead approval)
- CI will still catch errors before merge
- Document reason in commit message

### Fixing Lint Errors

**Auto-fix with Ruff:**
```bash
# Fix most lint errors automatically
uv run ruff check . --fix

# Format code
uv run ruff format .
```

**Type errors require manual fixes:**
```bash
# Check type errors
uv run mypy app/

# Add type annotations where needed
def my_function(arg: str) -> int:
    return len(arg)
```

## Configuration Details

### Pre-Commit Hook Types

**Pre-commit** (not used) - Runs on `git commit`
- Pros: Catches errors immediately
- Cons: Slows down commit workflow
- Our choice: Use pre-push instead

**Pre-push** (current setup) - Runs on `git push`
- Pros: Fast local commits, catches errors before remote push
- Cons: Allows local commits with errors
- Our choice: Balanced for productivity

### Ruff Configuration

**pyproject.toml:**
```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "A", "C4", "SIM", "RET", "ARG"]
ignore = []

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["ARG001"]  # Unused function arguments in tests
```

### Mypy Configuration

**pyproject.toml:**
```toml
[tool.mypy]
python_version = "3.10"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

## Monitoring and Maintenance

### Weekly Checks

**Review CI Failures:**
- Monitor PR check failures in GitHub Actions
- Track common error patterns
- Update `.pre-commit-config.yaml` versions monthly

**Hook Health:**
```bash
# Update hook repositories to latest versions
uv run pre-commit autoupdate

# Run hooks on all files (catches config drift)
uv run pre-commit run --all-files
```

### Common Issues and Solutions

**Issue 1: "pre-commit not found"**
```bash
# Solution: Install pre-commit in virtualenv
uv sync --dev
uv run pre-commit install --hook-type pre-push
```

**Issue 2: "Hook failed but no errors shown"**
```bash
# Solution: Run hook directly with verbose output
uv run pre-commit run ruff --verbose --all-files
```

**Issue 3: "Mypy can't find imports"**
```bash
# Solution: Add dependencies to mypy additional_dependencies in .pre-commit-config.yaml
# Already configured for: pydantic, sqlalchemy, fastapi, pgqueuer, asyncpg
```

## Recommendations

### Immediate Actions (Completed)
- [x] Verify pre-push hooks installed and working
- [x] Verify CI runs on all PRs
- [x] Document lint error prevention strategy
- [x] Test hook behavior with intentional errors

### Future Enhancements (Optional)
- [ ] Add pre-commit hook for commit message format (conventional commits)
- [ ] Add ruff-format to git diff for review-time formatting
- [ ] Configure Dependabot for pre-commit hook version updates
- [ ] Add lint error metrics to weekly sprint reports

## Conclusion

**Status:** ✅ RESOLVED

The lint error leakage issue has been addressed through:
1. Comprehensive pre-push hooks (ruff + mypy + general checks)
2. GitHub Actions CI safety net (required for PR merge)
3. All existing lint errors fixed (65 files passing)
4. Documentation and verification completed

**No further action required** - System is production-ready with multi-layer protection against lint errors reaching main branch.

---

**References:**
- `.pre-commit-config.yaml` - Hook configuration
- `.github/workflows/pr-checks.yml` - CI workflow
- `pyproject.toml` - Ruff and Mypy settings
- Action Item: epic6-ai-2 in `action-items.yaml`
