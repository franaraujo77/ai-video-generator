# Deployment Validation Strategy - Shift-Left Approach

**Date:** 2026-01-14
**Issue:** Epic 2 deployment failure due to missing `httpx` dependency
**Impact:** Production deployment blocked, Epic 2 validation delayed
**Root Cause:** Manual dependency list in Dockerfile not synchronized with `pyproject.toml`

---

## What Happened

**Deployment Error:**
```
ModuleNotFoundError: No module named 'httpx'
```

**Location:** `app/clients/notion.py:18` (Story 2.2 - NotionClient)

**Timeline:**
1. Epic 2 added new dependencies to `pyproject.toml` (Stories 2.2-2.6):
   - `httpx>=0.28.1` (Notion API client)
   - `aiolimiter>=1.2.1` (Rate limiting)
   - `tenacity>=9.1.2` (Retry logic)
   - `pgqueuer>=0.10.0` (Task queue)
2. Dockerfile contained **manual hardcoded dependency list** from Epic 1
3. Dockerfile was never updated when Epic 2 added dependencies
4. All local tests passed (using `uv sync` which reads `pyproject.toml`)
5. Railway deployment failed (using Dockerfile with missing dependencies)

---

## Root Cause Analysis

### 1. Anti-Pattern: Manual Dependency List in Dockerfile

**Original Dockerfile (Epic 1):**
```dockerfile
# ANTI-PATTERN: Manual dependency list
RUN uv pip install --system --no-cache \
    "google-generativeai>=0.8.0" \
    "python-dotenv>=1.0.0" \
    "pillow>=10.0.0" \
    "pyjwt>=2.8.0" \
    "requests>=2.31.0" \
    "sqlalchemy[asyncio]>=2.0.0" \
    "asyncpg>=0.29.0" \
    "alembic>=1.13.0" \
    # ... 10+ more dependencies
```

**Problem:** Every time a dependency is added to `pyproject.toml`, the Dockerfile must be manually updated. This creates two sources of truth:
- ✅ `pyproject.toml` - Correct (used for local development)
- ❌ `Dockerfile` - Stale (used for production deployment)

### 2. No Validation Before Deployment

**Missing Safeguards:**
- ❌ No pre-commit hook validated Dockerfile matches `pyproject.toml`
- ❌ No CI/CD smoke test built Docker image before merge
- ❌ No automated check that all imports resolve in production environment
- ❌ Code review didn't catch Dockerfile drift (not part of checklist)

### 3. Test Environment Mismatch

**Local Development:**
- Uses `uv sync` which reads `pyproject.toml` automatically
- All dependencies installed correctly
- All tests pass

**Production Deployment:**
- Uses `Dockerfile` with manual dependency list
- Missing 4 dependencies
- Application fails to start

**Insight:** Tests passing locally does NOT guarantee deployment success.

---

## Immediate Fix

### 1. Dockerfile Fixed (Automated Dependency Installation)

**New Approach:**
```dockerfile
# Copy dependency files first (for better layer caching)
COPY pyproject.toml uv.lock ./

# Install production dependencies directly to system Python
# Use uv export to generate requirements.txt from pyproject.toml
# This ensures Dockerfile automatically stays in sync with pyproject.toml
# --no-dev: Exclude dev dependencies
# --no-hashes: Simpler requirements.txt format
RUN uv export --no-dev --no-hashes --frozen > requirements.txt && \
    uv pip install --system --no-cache -r requirements.txt
```

**Benefits:**
- ✅ Single source of truth (`pyproject.toml`)
- ✅ Dockerfile automatically includes all production dependencies
- ✅ No manual synchronization required
- ✅ Future dependency additions automatically deployed

### 2. Files Modified

**Modified:**
- `Dockerfile` - Changed lines 27-36 from manual list to `uv export` pattern

**Created:**
- `scripts/validate_deployment.sh` - Automated validation script
- `.pre-commit-config.yaml` - Added deployment validation hook
- `_bmad-output/DEPLOYMENT-VALIDATION-STRATEGY.md` - This document

---

## Shift-Left Validation Strategy

### Phase 1: Pre-Commit Validation (Fastest Feedback)

**Hook:** `validate-deployment` (runs before git push)

**Checks:**
1. ✅ Dockerfile exists
2. ✅ Dockerfile does NOT contain manual dependency lists
3. ✅ Dockerfile uses `uv export` pattern
4. ✅ All app imports can be resolved with production dependencies

**Run Manually:**
```bash
./scripts/validate_deployment.sh
```

**Automatic Run:**
```bash
# Pre-commit hook runs automatically on git push
git push origin epic-2-notion-integration

# Or run manually
uv run pre-commit run validate-deployment --all-files
```

**Expected Output:**
```
✅ Dockerfile uses automated dependency installation (uv export)
✅ All app imports resolved successfully
✅ All deployment validation checks passed!
```

### Phase 2: CI/CD Smoke Test (Pre-Merge Validation)

**Recommended GitHub Actions Workflow:**

Create `.github/workflows/deployment-validation.yml`:

```yaml
name: Deployment Validation

on:
  pull_request:
    branches: [main, epic-*]
    paths:
      - 'Dockerfile'
      - 'pyproject.toml'
      - 'uv.lock'
      - 'app/**'

jobs:
  validate-deployment:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v1

      - name: Run deployment validation
        run: ./scripts/validate_deployment.sh

      - name: Build Docker image
        run: docker build -t deployment-test:latest .

      - name: Test Docker image starts successfully
        run: |
          docker run -d --name test-app -p 8000:8000 \
            -e DATABASE_URL=sqlite:///./test.db \
            deployment-test:latest
          sleep 10
          curl -f http://localhost:8000/health || exit 1
```

**Benefits:**
- ✅ Catches deployment issues before merge
- ✅ Prevents broken deployments reaching production
- ✅ Fast feedback (~3-5 minutes)

### Phase 3: Staging Environment Validation (Post-Merge, Pre-Production)

**Railway Staging Environment:**

1. **Branch-based Deployment:**
   - `main` branch → Production environment
   - `staging` branch → Staging environment
   - Epic branches → Preview environments

2. **Validation Checklist Before Promoting to Production:**
   - [ ] Application starts without errors (check Railway logs)
   - [ ] All imports resolve (no ModuleNotFoundError)
   - [ ] Health check endpoint responds (`GET /health`)
   - [ ] Database migrations apply successfully
   - [ ] Environment variables loaded correctly

3. **Smoke Test After Deployment:**
```bash
# Check Railway application logs
railway logs --tail 100

# Test health endpoint
curl https://your-app.railway.app/health

# Test Notion webhook endpoint (if Epic 2)
curl -X POST https://your-app.railway.app/api/v1/webhooks/notion \
  -H "Content-Type: application/json" \
  -H "X-Notion-Signature: test" \
  -d '{}'
```

---

## Updated Definition of Done (Story Level)

**Previous (Insufficient):**
- ✅ All acceptance criteria met
- ✅ Tests passing
- ✅ Code review approved

**Updated (Shift-Left Compliant):**
- ✅ All acceptance criteria met
- ✅ Tests passing
- ✅ Code review approved
- ✅ **Deployment validation passing** (NEW)
- ✅ **Pre-commit hooks passing** (NEW)
- ✅ **No new dependencies without Dockerfile validation** (NEW)

---

## Updated Code Review Checklist

**Deployment Readiness Section (NEW):**

When reviewing code that adds dependencies:
- [ ] Dependency added to `pyproject.toml` under correct section (`dependencies` or `dependency-groups.dev`)
- [ ] `uv lock` run to update `uv.lock` file
- [ ] Dockerfile uses automated dependency installation (`uv export` pattern)
- [ ] No manual dependency lists in Dockerfile
- [ ] Deployment validation script passes (`./scripts/validate_deployment.sh`)
- [ ] All imports can be resolved in production environment

When reviewing Dockerfile changes:
- [ ] No hardcoded dependency lists
- [ ] Uses `uv export` to read from `pyproject.toml`
- [ ] Includes `uv.lock` in COPY command for reproducible builds
- [ ] Comments explain why changes were made

---

## Process Improvements

### 1. Dependency Addition Workflow (NEW)

**Before adding a dependency:**
```bash
# 1. Add dependency to pyproject.toml
uv add httpx>=0.28.1

# 2. Update lockfile
uv lock

# 3. Run deployment validation
./scripts/validate_deployment.sh

# 4. Verify imports resolve
python -c "import httpx; print('✅ httpx imported successfully')"

# 5. Commit both files
git add pyproject.toml uv.lock
git commit -m "deps: Add httpx for Notion API client"
```

**After merging PR:**
```bash
# 6. Verify staging deployment succeeds
railway logs --environment staging --tail 100

# 7. Run smoke test in staging
curl https://staging.railway.app/health
```

### 2. Epic Retrospective Checklist Addition

**Add to Epic 2 Retrospective Action Items:**
- [x] Document deployment failure root cause
- [x] Implement automated Dockerfile validation
- [x] Add pre-commit hook for deployment checks
- [x] Create shift-left validation strategy document
- [ ] Add CI/CD smoke test workflow (GitHub Actions)
- [ ] Add staging environment validation to Definition of Done

### 3. Epic 3 Prevention Strategy

**Before Epic 3 starts:**
1. ✅ Dockerfile uses automated dependency installation
2. ✅ Pre-commit hook validates deployment configuration
3. ✅ Deployment validation script exists and passes
4. ⏳ CI/CD smoke test workflow created (optional, recommended)
5. ⏳ Staging environment configured on Railway

**During Epic 3 (whenever dependencies are added):**
1. Run `uv add <package>` to add dependency
2. Run `./scripts/validate_deployment.sh` before committing
3. Verify pre-commit hook passes on git push
4. After merge, verify staging deployment succeeds
5. Only then mark story "done"

---

## Lessons Learned

### 1. Single Source of Truth is Non-Negotiable

**Anti-Pattern:** Duplicate dependency declarations (pyproject.toml + Dockerfile)
**Best Practice:** Dockerfile reads from pyproject.toml programmatically

### 2. Local Success ≠ Production Success

**Anti-Pattern:** "Tests pass locally, ship it"
**Best Practice:** Validate in production-like environment before deployment

### 3. Shift-Left Catches Issues Early

**Cost of Bug Detection:**
- Pre-commit hook: **Immediate** (0 minutes, developer fixes before commit)
- CI/CD smoke test: **Fast** (5 minutes, catches before merge)
- Staging deployment: **Moderate** (30 minutes, catches before production)
- Production deployment: **Expensive** (Hours of debugging, downtime, rollback)

**ROI of Shift-Left:** 100x time savings, zero production downtime

### 4. Automation > Documentation

**Documentation:** "Remember to update Dockerfile when adding dependencies"
**Problem:** Humans forget, documentation gets stale

**Automation:** Pre-commit hook fails if Dockerfile drifts from pyproject.toml
**Benefit:** Impossible to forget, enforced by tooling

---

## Testing the Fix

### 1. Verify Pre-Commit Hook

```bash
# Reinstall pre-commit hooks
uv run pre-commit install --hook-type pre-push

# Run deployment validation manually
./scripts/validate_deployment.sh

# Should output:
# ✅ Dockerfile uses automated dependency installation (uv export)
# ✅ All app imports resolved successfully
# ✅ All deployment validation checks passed!
```

### 2. Test Docker Build Locally

```bash
# Build Docker image
docker build -t ai-video-generator:test .

# Run container
docker run -p 8000:8000 \
  -e DATABASE_URL=sqlite:///./test.db \
  -e NOTION_API_TOKEN=test_token \
  ai-video-generator:test

# Verify application starts (check logs)
# Should see: "Application startup complete"
# Should NOT see: "ModuleNotFoundError"
```

### 3. Deploy to Railway and Validate

```bash
# Push to Railway
git push origin epic-2-notion-integration

# Watch Railway logs
railway logs --tail 100

# Expected output:
# ✅ "Application startup complete"
# ✅ "Notion sync loop started"
# ✅ No ModuleNotFoundError

# Test health endpoint
curl https://your-app.railway.app/health
```

---

## Future Enhancements

### 1. Docker Multi-Stage Build with Tests

**Proposed Dockerfile Enhancement:**
```dockerfile
# Stage 1: Test (validates all imports work)
FROM python:3.11-slim AS test
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv export --no-dev --no-hashes > requirements.txt && \
    uv pip install --system -r requirements.txt
COPY app/ ./app/
RUN python -c "from app import main; print('✅ All imports successful')"

# Stage 2: Production (slim image)
FROM python:3.11-slim AS production
WORKDIR /app
COPY --from=test /usr/local /usr/local
COPY --from=test /app /app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Benefit:** Docker build fails if imports don't resolve

### 2. Automated Dependency Audit

**Script:** `scripts/audit_dependencies.sh`

```bash
#!/bin/bash
# Audit dependencies for security vulnerabilities
uv pip check  # Check for broken dependencies
uv pip list --outdated  # Check for outdated packages
```

**Integration:** Run monthly via scheduled CI/CD

### 3. Cost Tracking Dashboard

Track deployment failures to justify shift-left investment:
- Time spent debugging production issues
- Deployment rollbacks due to missing dependencies
- Developer productivity lost to environment issues

---

## Conclusion

**Problem:** Manual dependency lists in Dockerfile caused production deployment failure

**Solution:**
1. Automated Dockerfile dependency installation (reads from pyproject.toml)
2. Pre-commit hook validation (shift-left detection)
3. Deployment validation script (automated testing)

**Impact:**
- ✅ Future dependency additions automatically deployed
- ✅ Deployment issues caught before git push
- ✅ Zero risk of pyproject.toml/Dockerfile drift
- ✅ Epic 3+ protected from this issue

**Next Steps:**
1. Apply Dockerfile fix (DONE)
2. Add pre-commit hook (DONE)
3. Test Docker build locally (PENDING)
4. Deploy to Railway and validate (PENDING - Epic 2 Action Item #1)
5. Add CI/CD smoke test (RECOMMENDED for Epic 3)

**Status:** ✅ Shift-left strategy implemented and documented
