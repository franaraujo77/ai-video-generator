# Security Incident Report: Exposed API Keys

**Date Discovered:** 2026-01-17
**Severity:** CRITICAL
**Status:** Partially Mitigated (keys removed from working tree, still in git history)

## Summary

Real API keys were committed to the git repository and have been exposed since the initial commit on 2025-11-26. The keys were stored in `scripts/.env` and tracked by git for approximately **52 days**.

## Exposed Credentials

### 1. Google Gemini API Key
- **Key:** `AIzaSyDMDcrgns9X0DHH4n7UGiurJnoK8CwzCIg`
- **Service:** Google AI Studio (Gemini)
- **First Exposed:** 2025-11-26 13:14:12 -0500 (commit af45982)
- **Revoke at:** https://aistudio.google.com/app/apikey
- **Risk:** Full access to Gemini API with this key. Potential for:
  - Unauthorized usage charges
  - API quota exhaustion
  - Data exfiltration from API responses

### 2. KIE.ai API Key
- **Key:** `7d3951aaa207f64eaff23d04934a1702`
- **Service:** KIE.ai (Kling 2.5 video generation wrapper)
- **First Exposed:** 2025-11-26 13:14:12 -0500 (commit af45982)
- **Revoke at:** https://kie.ai
- **Risk:** Access to video generation API with potential for:
  - High-cost API abuse (video generation is expensive)
  - Account quota exhaustion
  - Service disruption

### 3. ElevenLabs API Key
- **Key:** `sk_6746bc4d00a5a922e46960b5f4280c927cdbcdd0abb0140f`
- **Service:** ElevenLabs (Text-to-Speech)
- **First Exposed:** 2025-11-26 13:14:12 -0500 (commit af45982)
- **Revoke at:** https://elevenlabs.io
- **Risk:** Access to TTS API with potential for:
  - Character/credit consumption
  - Voice cloning abuse
  - Account quota exhaustion

### 4. ElevenLabs Voice ID
- **ID:** `jvcMcno3QtjOzGtfpjoI`
- **Type:** Voice identifier (not a secret, but exposed)
- **Risk:** Low (voice IDs are not sensitive)

## Timeline

- **2025-11-26 13:14:12 -0500:** Keys committed in initial commit (af45982) by Brandon Hancock
- **2025-11-26 to 2026-01-17:** Keys exposed in git history (52 days)
- **2026-01-17:** Keys discovered during FERNET_KEY security audit
- **2026-01-17:** Keys removed from working tree (commit 1e79fbe)
- **2026-01-17:** .gitignore enhanced to prevent future exposure

## How Keys Were Created

Based on the git history analysis:

1. **Origin:** Keys were part of the initial Pokemon Pipeline project
2. **Created by:** Brandon Hancock
3. **Purpose:** Development/production API keys for:
   - Pokemon documentary video generation (Gemini for images)
   - Video generation via Kling 2.5 (KIE.ai wrapper)
   - Narration generation (ElevenLabs TTS)
4. **Mistake:** Real production keys committed instead of using:
   - Environment variables only
   - `.env.example` with placeholder values
   - Proper secrets management

## Repository Exposure

- **Repository:** ai-video-generator
- **Visibility:** Assumed private (verify with `gh repo view`)
- **Total commits:** 144
- **Branches affected:** All branches (keys in initial commit)
- **Clone risk:** Anyone with repository access has access to keys via git history

## Immediate Actions Taken (2026-01-17)

✅ **Working Tree Cleanup**
- Removed `scripts/.env` from git tracking (`git rm --cached`)
- File remains locally for development use
- Enhanced `.gitignore` with comprehensive patterns:
  ```gitignore
  .env
  .env.*
  **/.env
  **/.env.*
  !.env.example
  scripts/.env
  *_credentials.json
  *_secrets.json
  *.pem
  *.key
  ```

✅ **Documentation**
- Created SECURITY_INCIDENT_REPORT.md (this file)
- Created SECURITY_PURGE_PLAN.md with git-filter-repo instructions

## Actions Required

### CRITICAL (Do Immediately)

1. **Revoke ALL exposed API keys:**
   - [ ] Revoke Gemini key at https://aistudio.google.com/app/apikey
   - [ ] Revoke KIE.ai key at https://kie.ai
   - [ ] Revoke ElevenLabs key at https://elevenlabs.io

2. **Generate NEW API keys:**
   - [ ] Generate new Gemini API key
   - [ ] Generate new KIE.ai API key
   - [ ] Generate new ElevenLabs API key
   - [ ] Update local `scripts/.env` with new keys (file is gitignored)

3. **Check for unauthorized usage:**
   - [ ] Review Gemini API usage logs for suspicious activity
   - [ ] Review KIE.ai billing/usage for unexpected charges
   - [ ] Review ElevenLabs character usage for anomalies

### HIGH PRIORITY (Do within 24 hours)

4. **Purge keys from git history:**
   - [ ] Follow SECURITY_PURGE_PLAN.md instructions
   - [ ] Use git-filter-repo to remove `scripts/.env` from all 144 commits
   - [ ] Force push to remote (coordinate with team)

5. **Verify repository visibility:**
   ```bash
   gh repo view --json visibility
   ```
   - [ ] If public, assess exposure risk
   - [ ] If private, assess who had access

6. **Audit other secrets:**
   - [ ] Search for other exposed credentials: `git log -p | grep -E "API|KEY|SECRET"`
   - [ ] Review all `.env.example` files for accidentally committed real values
   - [ ] Check for exposed FERNET_KEY (already verified: not exposed ✅)

### MEDIUM PRIORITY (Do within 1 week)

7. **Implement secrets detection:**
   - [ ] Add pre-commit hook for secrets detection (e.g., detect-secrets)
   - [ ] Configure GitHub secret scanning (if using GitHub)
   - [ ] Document secrets management policy

8. **Team notification:**
   - [ ] Notify team about key revocation
   - [ ] Share new keys via secure channel (not git)
   - [ ] Update Railway/production environment variables

## Lessons Learned

1. **Never commit real API keys** - Use environment variables only
2. **`.env` should always be gitignored** - Verify .gitignore before initial commit
3. **Use `.env.example`** - Commit placeholder examples only
4. **Pre-commit hooks** - Implement secrets detection before first commit
5. **Initial commit review** - First commits are easy to get wrong; review carefully

## Prevention Measures

Going forward:

1. ✅ Enhanced `.gitignore` with comprehensive secret patterns
2. 🔲 Add pre-commit hook for secrets detection (recommended: `detect-secrets`)
3. 🔲 Document secrets management in CONTRIBUTING.md
4. 🔲 Use secret scanning tools (GitHub secret scanning, truffleHog)
5. 🔲 Regular security audits of repository

## References

- **Git history analysis:** `git log --all --full-history -- scripts/.env`
- **Initial commit:** af45982 (2025-11-26 13:14:12 -0500)
- **Removal commit:** 1e79fbe (2026-01-17)
- **Purge instructions:** SECURITY_PURGE_PLAN.md

## Contact

For questions about this incident, contact the repository owner or security team.

---

**Report Status:** ACTIVE - Keys still in git history, purge pending
**Last Updated:** 2026-01-17
**Audited By:** Claude Code (automated security scan)
