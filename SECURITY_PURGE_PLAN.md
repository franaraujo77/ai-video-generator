# Security Purge Plan: Remove Exposed API Keys from Git History

**Date Created:** 2026-01-17
**Status:** Ready for Execution
**Risk Level:** CRITICAL - Repository history will be rewritten
**Estimated Time:** 15-30 minutes

## Executive Summary

This document provides step-by-step instructions to permanently remove `scripts/.env` from the entire git history using `git-filter-repo`. This will rewrite 144 commits dating back to 2025-11-26.

**CRITICAL WARNINGS:**
- ⚠️ This rewrites git history - all commit SHAs will change
- ⚠️ All team members must re-clone after force push
- ⚠️ Any open PRs or branches will need rebasing
- ⚠️ CI/CD pipelines may need reconfiguration
- ⚠️ Backup EVERYTHING before proceeding

---

## Prerequisites

### 1. Install git-filter-repo

**macOS (Homebrew):**
```bash
brew install git-filter-repo
```

**Linux (apt):**
```bash
sudo apt-get install git-filter-repo
```

**Manual Installation:**
```bash
# Download latest release
curl -O https://raw.githubusercontent.com/newren/git-filter-repo/main/git-filter-repo
chmod +x git-filter-repo
sudo mv git-filter-repo /usr/local/bin/
```

**Verify Installation:**
```bash
git-filter-repo --version
# Should output: git-filter-repo 2.x.x
```

### 2. Verify API Keys Have Been Revoked

Before purging history, ensure all exposed keys have been revoked and regenerated:

- [ ] Gemini API key revoked at https://aistudio.google.com/app/apikey
- [ ] KIE.ai API key revoked at https://kie.ai
- [ ] ElevenLabs API key revoked at https://elevenlabs.io
- [ ] New keys generated and stored in local `scripts/.env` (gitignored)
- [ ] No active services using old keys

**WHY:** Purging history is pointless if keys are still valid and usable.

---

## Step 1: Create Complete Backup

**CRITICAL:** Create backup BEFORE starting. This is your safety net if something goes wrong.

```bash
# Navigate to repository
cd /Users/francisaraujo/repos/ai-video-generator

# Create timestamped backup
BACKUP_DIR="$HOME/ai-video-generator-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -R . "$BACKUP_DIR/"

# Verify backup
ls -la "$BACKUP_DIR"
echo "Backup created at: $BACKUP_DIR"
```

**Verification Checklist:**
- [ ] Backup directory exists
- [ ] Backup contains `.git` directory
- [ ] Backup size matches original (use `du -sh`)
- [ ] Can navigate into backup and see all files

---

## Step 2: Clone Fresh Copy (Recommended)

**WHY:** git-filter-repo works best on a fresh clone without working tree changes.

```bash
# Navigate to parent directory
cd /Users/francisaraujo/repos

# Clone fresh copy for history rewrite
git clone ai-video-generator ai-video-generator-purge
cd ai-video-generator-purge

# Verify you're in the purge copy
pwd
# Should output: /Users/francisaraujo/repos/ai-video-generator-purge
```

**Alternative:** If you prefer to work on the original, ensure working tree is clean:
```bash
cd /Users/francisaraujo/repos/ai-video-generator
git status
# Should output: "nothing to commit, working tree clean"
```

---

## Step 3: Verify File to Purge

Confirm that `scripts/.env` exists in git history:

```bash
# Check file history
git log --all --full-history --oneline -- scripts/.env

# Should show commits including:
# af45982 first commit (2025-11-26)
# ... other commits that modified it
```

**If no output:** File may already be purged or never committed. Verify in initial commit:
```bash
git show af45982:scripts/.env
# Should display exposed API keys
```

---

## Step 4: Execute History Purge

**CRITICAL STEP:** This command rewrites ALL commits. There is NO undo.

```bash
# Purge scripts/.env from all branches and history
git filter-repo --path scripts/.env --invert-paths --force

# Expected output:
# Parsed 144 commits
# Rewritten 144 commits
# Completely finished after X seconds
```

**Command Breakdown:**
- `--path scripts/.env` - Target file to remove
- `--invert-paths` - Remove (not keep) the specified path
- `--force` - Required for repositories with remotes configured

**What This Does:**
1. Rewrites all 144 commits to exclude `scripts/.env`
2. Updates all branches and tags
3. Changes all commit SHAs (history rewrite)
4. Removes file from all snapshots

---

## Step 5: Verify Purge Success

**Test 1: Check git history**
```bash
# This should return NOTHING (file no longer in history)
git log --all --full-history --oneline -- scripts/.env

# Expected: No output (empty)
```

**Test 2: Check initial commit**
```bash
# This should fail (file doesn't exist in initial commit)
git show af45982:scripts/.env 2>&1 | grep "does not exist"

# Expected output: "Path 'scripts/.env' does not exist"
```

**Test 3: Search entire history**
```bash
# Search for exposed API key patterns
git log -p --all | grep -i "GEMINI_API_KEY"

# Expected: No matches (or only references in documentation)
```

**Test 4: Verify working tree**
```bash
# Local scripts/.env should still exist (gitignored)
ls -la scripts/.env

# Git should not track it
git status
# Expected: "nothing to commit" (scripts/.env not listed)
```

**Verification Checklist:**
- [ ] `git log -- scripts/.env` returns nothing
- [ ] Cannot retrieve file from any commit
- [ ] No API keys found in `git log -p --all`
- [ ] Local `scripts/.env` still exists for development
- [ ] `.gitignore` prevents future commits

---

## Step 6: Add Remote and Force Push

**CRITICAL:** Coordinate with team BEFORE force pushing.

```bash
# Add remote (if using fresh clone)
git remote add origin https://github.com/YOUR_USERNAME/ai-video-generator.git

# Or verify existing remote
git remote -v

# Fetch latest changes (sanity check)
git fetch origin

# Force push rewritten history (POINT OF NO RETURN)
git push --force --all origin
git push --force --tags origin
```

**Expected Output:**
```
+ af45982...abc1234 main -> main (forced update)
+ def5678...xyz9012 feature-branch -> feature-branch (forced update)
```

**Warnings:**
- All commit SHAs will change
- GitHub/GitLab will show "Force-pushed" in history
- Protected branches may block force push (temporarily disable protection)

---

## Step 7: Team Coordination

**BEFORE Force Push:**

Send this message to all team members:

```
CRITICAL: Git History Rewrite Scheduled

I will be force-pushing a security fix to remove exposed API keys from git history at [SPECIFIC TIME].

After the force push, you MUST:
1. Commit any local changes
2. Delete your local repository
3. Re-clone from origin
4. Restore local configuration (scripts/.env with NEW keys)

All commit SHAs will change. Open PRs will need rebasing.

Do NOT push to the repository until I confirm the purge is complete.

Timeline:
- [TIME]: Force push begins
- [TIME + 5min]: Verification complete
- [TIME + 10min]: Team can resume work

Questions? Contact me before the scheduled time.
```

**AFTER Force Push:**

Send confirmation message:

```
✅ Security purge complete. Repository history has been rewritten.

Next Steps for ALL Team Members:
1. cd ~/repos && rm -rf ai-video-generator
2. git clone https://github.com/YOUR_USERNAME/ai-video-generator.git
3. cd ai-video-generator
4. cp ~/backup/scripts/.env scripts/.env  # Use NEW keys, not old ones
5. Verify: git log --oneline | head -5  # Commit SHAs should match main

DO NOT use your old local clone - it has the old history.

If you have open PRs:
- Rebase them onto the new main branch
- Force push to update PR: git push --force origin your-branch

CI/CD Status: [Check if pipelines need reconfiguration]
```

---

## Step 8: Repository Cleanup

**On GitHub/GitLab:**

1. **Verify Protected Branches:**
   - Repository Settings → Branches → Protected Branches
   - Re-enable force push protection after purge

2. **Check GitHub Secret Scanning:**
   - Repository Settings → Security → Secret scanning alerts
   - Should show no new alerts
   - Old alerts may remain (historical detection)

3. **Update CI/CD Pipelines:**
   - If pipelines reference commit SHAs, update them
   - Re-run failed builds (old SHAs no longer exist)

4. **Archive Old PRs:**
   - Close PRs that can't be rebased
   - Document reason: "Closed due to security history rewrite"

**On Local Machines (All Team Members):**

```bash
# Each team member must:
cd ~/repos
rm -rf ai-video-generator  # Delete old clone
git clone https://github.com/YOUR_USERNAME/ai-video-generator.git
cd ai-video-generator

# Restore local configuration (with NEW keys)
cp ~/backup/scripts/.env scripts/.env

# Verify new history
git log --oneline -5
# Commit SHAs should match GitHub
```

---

## Step 9: Post-Purge Verification

**Comprehensive Security Audit:**

```bash
# 1. Verify file is gone from history
git log --all --full-history -- scripts/.env
# Expected: No output

# 2. Search for API key patterns
git log -p --all | grep -E "(AIzaSy|sk_[a-zA-Z0-9]{48}|[a-f0-9]{32})"
# Expected: No matches (or only in documentation)

# 3. Check repository size reduction
git count-objects -vH
# Expected: size-pack should be smaller than before

# 4. Run git garbage collection
git gc --prune=now --aggressive

# 5. Verify local .env is still present and gitignored
ls -la scripts/.env && git status
# Expected: File exists, not tracked by git
```

**Check API Usage Logs:**

After purge, verify no unauthorized usage of old keys:

- [ ] Google Gemini API logs: https://console.cloud.google.com/apis/dashboard
- [ ] KIE.ai billing dashboard: https://kie.ai/dashboard
- [ ] ElevenLabs usage history: https://elevenlabs.io/usage

**If Unauthorized Usage Detected:**
1. Revoke new keys immediately
2. Generate new keys again
3. Review access logs for IP addresses
4. Contact service providers' abuse teams

---

## Step 10: Prevention Measures

**Implement Pre-commit Hook:**

```bash
# Install detect-secrets
pip install detect-secrets

# Initialize baseline
detect-secrets scan > .secrets.baseline

# Add pre-commit hook
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
detect-secrets scan --baseline .secrets.baseline
if [ $? -ne 0 ]; then
  echo "❌ Secret detected! Commit blocked."
  echo "Run: detect-secrets scan --update .secrets.baseline"
  exit 1
fi
EOF

chmod +x .git/hooks/pre-commit
```

**Enable GitHub Secret Scanning:**

1. Repository Settings → Security & analysis
2. Enable "Secret scanning"
3. Enable "Push protection"

**Document Secrets Management:**

Create `docs/SECRETS_MANAGEMENT.md`:

```markdown
# Secrets Management Policy

## Never Commit Secrets
- Use environment variables ONLY
- Add `.env` to `.gitignore` BEFORE first commit
- Use `.env.example` with placeholder values

## Secure Key Storage
- Local development: `scripts/.env` (gitignored)
- Production: Railway environment variables (encrypted)
- Team sharing: Use secure channels (1Password, not git)

## Incident Response
1. Revoke exposed credentials immediately
2. Generate new keys
3. Purge from git history (see SECURITY_PURGE_PLAN.md)
4. Audit API usage logs

## Pre-commit Hooks
All developers must install:
- detect-secrets (pip install detect-secrets)
- Pre-commit hook (see .git/hooks/pre-commit)
```

---

## Rollback Plan (If Something Goes Wrong)

**If purge fails or causes issues:**

```bash
# Option 1: Restore from backup
cd ~/repos
rm -rf ai-video-generator-purge
cp -R ~/ai-video-generator-backup-TIMESTAMP ai-video-generator
cd ai-video-generator
git remote -v  # Verify remote is correct

# Option 2: Reset to pre-purge state (if you have commit SHA)
git reset --hard ORIGINAL_MAIN_SHA
git push --force origin main
```

**If team members pushed before re-cloning:**

```bash
# Their changes are based on old history - must cherry-pick
git log old-branch --oneline  # Note their commit SHAs
git cherry-pick SHA1 SHA2 SHA3  # Apply their changes to new history
```

---

## Success Criteria

✅ **Purge is successful when:**

1. `git log --all --full-history -- scripts/.env` returns nothing
2. Cannot retrieve `scripts/.env` from any commit
3. API key patterns not found in `git log -p --all`
4. Local `scripts/.env` still exists (gitignored)
5. All team members have re-cloned successfully
6. CI/CD pipelines are green
7. No unauthorized API usage detected

❌ **Abort and rollback if:**

1. git-filter-repo reports errors
2. Cannot verify file removal
3. Local development environment broken
4. Team members cannot re-clone
5. CI/CD pipelines fail unexpectedly

---

## Timeline Estimate

- **Step 1-3 (Backup & Clone):** 5 minutes
- **Step 4 (Purge Execution):** 2-5 minutes (144 commits)
- **Step 5 (Verification):** 3 minutes
- **Step 6 (Force Push):** 2 minutes
- **Step 7 (Team Coordination):** 10-30 minutes (wait for team)
- **Step 8-9 (Cleanup & Verification):** 5 minutes
- **Step 10 (Prevention):** 10 minutes (optional)

**Total:** 15-30 minutes (excluding team coordination wait time)

---

## References

- **git-filter-repo Documentation:** https://github.com/newren/git-filter-repo
- **GitHub: Removing sensitive data:** https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
- **Security Incident Report:** SECURITY_INCIDENT_REPORT.md
- **Original Issue:** Exposed API keys in commit af45982 (2025-11-26)

---

## Contact

For questions or issues during purge execution:
- **Before purge:** Review this plan with team lead
- **During purge:** Do NOT interrupt process (wait for completion)
- **After purge:** Report issues to repository owner immediately

---

**Status:** Ready for Execution
**Last Updated:** 2026-01-17
**Reviewed By:** Claude Code (automated security tools)
