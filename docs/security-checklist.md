# Security Checklist for ai-video-generator

**Purpose:** Mandatory security review checklist for all stories before marking "done".
**Last Updated:** January 16, 2026
**Applies To:** All stories in Epic 4+
**Based On:** OWASP Top 10 (2021) + Epic 3 security findings

---

## How to Use This Checklist

1. **Design Phase:** Review relevant sections before implementation
2. **Implementation Phase:** Verify each item as you write code
3. **Testing Phase:** Create security test cases for applicable items
4. **Code Review Phase:** Adversarial reviewer verifies all items
5. **Sign-off:** All items must be ✅ checked or marked N/A before merging

---

## 1. Injection Prevention (OWASP A03:2021)

### Command Injection
- [ ] All subprocess calls use `run_cli_script()` wrapper (never direct `subprocess.run()`)
- [ ] CLI script arguments validated before passing to subprocess
- [ ] Shell metacharacters escaped or rejected: `;`, `|`, `&`, `$`, `` ` ``, `$()`
- [ ] No user input directly concatenated into shell commands
- [ ] Test cases verify rejection of injection attempts

**Test Pattern:**
```python
def test_command_injection_prevention():
    malicious_input = "; rm -rf /"
    with pytest.raises(ValueError):
        validate_input(malicious_input)
```

### SQL Injection
- [ ] All database queries use SQLAlchemy ORM (no raw SQL strings)
- [ ] Query parameters use SQLAlchemy bindparams (never f-strings)
- [ ] User input never directly interpolated into queries
- [ ] ORM methods used: `session.get()`, `session.query().filter()`
- [ ] Test cases verify ORM generates parameterized queries

**Test Pattern:**
```python
async def test_sql_injection_prevention(async_session):
    malicious_id = "123'; DROP TABLE tasks;--"
    result = await async_session.get(Task, malicious_id)  # Safe with ORM
    assert result is None  # Not found, but no injection
```

### Log Injection
- [ ] All log entries use structured logging (JSON format)
- [ ] Newline characters stripped from user input before logging
- [ ] No user-controlled strings in log event names
- [ ] Log values sanitized (see Sensitive Data section)
- [ ] Test cases verify newline injection rejected

**Test Pattern:**
```python
def test_log_injection_prevention(caplog):
    malicious_input = "innocent\nINFO:Injected log entry"
    log.info("user_input", value=malicious_input.replace("\n", ""))
    assert "Injected log entry" not in caplog.text
```

---

## 2. Path Traversal Prevention (Epic 3 Critical Finding)

### Filesystem Operations
- [ ] All file paths constructed using `app/utils/filesystem.py` helpers
- [ ] Never use f-strings or string concatenation for paths
- [ ] User input validated with regex: `^[a-zA-Z0-9_-]+$`
- [ ] Resolved paths verified to be within `/app/workspace/`
- [ ] Test cases verify path traversal attempts rejected

**Validation Pattern:**
```python
import re
from pathlib import Path

def validate_identifier(value: str, name: str):
    """Validate channel_id, project_id, or similar identifier."""
    if not value or len(value) > 100:
        raise ValueError(f"{name} must be 1-100 characters")
    if not re.match(r'^[a-zA-Z0-9_-]+$', value):
        raise ValueError(f"{name} contains invalid characters: {value}")

def validate_path_within_workspace(path: Path, workspace_root: Path):
    """Verify resolved path stays within workspace."""
    resolved = path.resolve()
    if not resolved.is_relative_to(workspace_root):
        raise ValueError(f"Path {path} escapes workspace {workspace_root}")
```

**Test Pattern:**
```python
def test_path_traversal_prevention():
    malicious_ids = ["../../../etc", "poke1/../../etc", "..\\..\\windows"]
    for malicious_id in malicious_ids:
        with pytest.raises(ValueError):
            validate_identifier(malicious_id, "channel_id")
```

### File Upload/Download
- [ ] File paths validated before reading/writing
- [ ] File extensions whitelist enforced: `.png`, `.mp4`, `.mp3`, `.wav`
- [ ] File size limits enforced (prevent DoS)
- [ ] Symlink traversal prevented (use `Path.resolve()`)
- [ ] Test cases verify symlink attacks rejected

---

## 3. Sensitive Data Protection (Epic 3 Critical Finding)

### Logging
- [ ] API keys NEVER logged (Gemini, Kling, ElevenLabs, Notion, YouTube)
- [ ] OAuth tokens NEVER logged (access tokens, refresh tokens)
- [ ] Passwords NEVER logged
- [ ] User email addresses sanitized or truncated
- [ ] Prompts truncated to 100 chars (may contain PII)
- [ ] Error messages don't leak internal paths or config

**Sanitization Pattern:**
```python
SENSITIVE_PATTERNS = ["--api-key", "--token", "--secret", "--password", "api_key=", "token="]

def sanitize_for_logging(value: str) -> str:
    """Redact sensitive data from log values."""
    for pattern in SENSITIVE_PATTERNS:
        if pattern in value.lower():
            return "[REDACTED]"
    if len(value) > 200:
        return value[:100] + "...[TRUNCATED]"
    return value
```

**Test Pattern:**
```python
def test_sensitive_data_sanitization(caplog):
    sensitive_input = "--api-key secret123"
    log.info("cli_execution", args=sanitize_for_logging(sensitive_input))
    assert "secret123" not in caplog.text
    assert "[REDACTED]" in caplog.text
```

### Database Storage
- [ ] API keys encrypted at rest (Fernet encryption)
- [ ] OAuth tokens encrypted at rest
- [ ] Encryption keys stored in environment variables (not code)
- [ ] Decryption only when needed (minimize plaintext lifetime)
- [ ] Test cases verify encrypted values in database

**Encryption Pattern:**
```python
from app.utils.encryption import EncryptionService

# Store
encrypted_key = EncryptionService.get_instance().encrypt(api_key)
channel.api_key_encrypted = encrypted_key

# Retrieve
api_key = EncryptionService.get_instance().decrypt(channel.api_key_encrypted)
```

### Environment Variables
- [ ] Secrets loaded from environment variables (not hardcoded)
- [ ] `.env` files in `.gitignore` (never committed)
- [ ] Railway environment variables used for production
- [ ] No secrets in error messages or stack traces
- [ ] Test cases use mock secrets (not real credentials)

---

## 4. Authentication & Authorization

### API Credentials
- [ ] Each channel has isolated API credentials
- [ ] Credentials validated on first use (fail fast)
- [ ] Expired credentials trigger refresh (OAuth)
- [ ] Invalid credentials logged with channel context
- [ ] Test cases verify credential isolation

### Channel Isolation
- [ ] Multi-tenant isolation enforced at filesystem level
- [ ] Database queries filtered by channel_id
- [ ] No cross-channel data leakage
- [ ] Worker processes respect channel boundaries
- [ ] Test cases verify isolation

**Test Pattern:**
```python
async def test_channel_isolation(async_session):
    # Create tasks for two channels
    task1 = Task(id="1", channel_id="poke1", status="queued")
    task2 = Task(id="2", channel_id="poke2", status="queued")
    async_session.add_all([task1, task2])
    await async_session.commit()

    # Verify channel 1 can't access channel 2's tasks
    result = await async_session.query(Task).filter_by(
        channel_id="poke1"
    ).all()
    assert len(result) == 1
    assert result[0].id == "1"
```

---

## 5. Error Handling & Logging

### Error Messages
- [ ] Error messages don't leak internal paths
- [ ] Error messages don't leak database schema
- [ ] Error messages don't leak API keys
- [ ] Stack traces sanitized before logging
- [ ] User-facing errors vs. internal logs separated

### Logging Best Practices
- [ ] Structured logging (JSON format) for production
- [ ] Correlation IDs (task_id) in all log entries
- [ ] Log levels appropriate (DEBUG vs. INFO vs. ERROR)
- [ ] Performance-sensitive operations logged with duration
- [ ] Test cases verify log format

---

## 6. Input Validation

### User Input
- [ ] All user input validated at entry point
- [ ] Validation uses whitelists (not blacklists)
- [ ] Length limits enforced (prevent buffer overflow)
- [ ] Type checking enforced (e.g., UUID format)
- [ ] Test cases verify validation edge cases

**Validation Patterns:**
```python
# Channel ID validation
def validate_channel_id(channel_id: str):
    if not channel_id or len(channel_id) > 50:
        raise ValueError("Channel ID must be 1-50 characters")
    if not re.match(r'^[a-z0-9_-]+$', channel_id):
        raise ValueError("Channel ID must be lowercase alphanumeric + dash/underscore")

# Topic validation
def validate_topic(topic: str):
    if not topic or len(topic) > 500:
        raise ValueError("Topic must be 1-500 characters")
    if topic.strip() != topic:
        raise ValueError("Topic must not have leading/trailing whitespace")
```

### API Input
- [ ] API request payloads validated with Pydantic schemas
- [ ] Unknown fields rejected (no extra fields allowed)
- [ ] Required fields enforced
- [ ] Default values documented
- [ ] Test cases verify schema validation

---

## 7. External API Security

### Rate Limiting
- [ ] API rate limits documented (Notion: 3 req/sec, etc.)
- [ ] Rate limiting enforced at client level
- [ ] Backoff strategy implemented (exponential with jitter)
- [ ] 429 responses handled gracefully
- [ ] Test cases verify rate limit compliance

### Timeout Configuration
- [ ] All external API calls have timeouts
- [ ] Timeouts configurable per channel
- [ ] Timeout exceeded logged with context
- [ ] Circuit breaker pattern considered for persistent failures
- [ ] Test cases verify timeout handling

### SSL/TLS
- [ ] All external API calls use HTTPS
- [ ] Certificate validation enabled (not disabled for testing)
- [ ] No mixed HTTP/HTTPS content
- [ ] Test cases verify HTTPS enforcement

---

## 8. Cryptography

### Encryption
- [ ] Fernet symmetric encryption for credentials
- [ ] Encryption keys 32 bytes (256 bits)
- [ ] Keys stored in environment variables
- [ ] Keys rotated periodically (manual process documented)
- [ ] Test cases verify encryption/decryption

### Hashing
- [ ] Passwords hashed with bcrypt (if storing user passwords)
- [ ] API keys NOT hashed (need reversible encryption)
- [ ] Hash algorithms modern (no MD5, SHA1)
- [ ] Test cases verify hash uniqueness

---

## 9. Dependency Security

### Package Management
- [ ] Dependencies pinned in `pyproject.toml`
- [ ] Regular dependency updates (monthly)
- [ ] Vulnerability scanning (GitHub Dependabot)
- [ ] No known CVEs in dependencies
- [ ] Test cases run on updated dependencies

### Docker/Railway
- [ ] Base image up-to-date (Python 3.11+)
- [ ] Minimal image (no unnecessary packages)
- [ ] Non-root user in production
- [ ] Secrets via environment variables (not baked into image)
- [ ] Test cases verify deployment security

---

## 10. Testing & Verification

### Security Test Coverage
- [ ] Min 5 security test cases per story
- [ ] Path traversal tests for all file operations
- [ ] Injection tests for all external commands
- [ ] Sensitive data tests for all logging
- [ ] Authorization tests for multi-tenant features
- [ ] Test cases documented in story

### Adversarial Testing
- [ ] Adversarial reviewer assigned (not implementer)
- [ ] Attack scenarios documented
- [ ] OWASP Top 10 checklist completed
- [ ] Security findings logged in story
- [ ] Re-test after fixes applied

---

## Story-Specific Checklists

### For Worker Stories
- [ ] Short transaction pattern enforced (claim → close → execute → update)
- [ ] Database connections don't leak
- [ ] Worker crash doesn't leave tasks locked
- [ ] Correlation IDs tracked throughout pipeline
- [ ] Test cases verify worker isolation

### For Service Stories
- [ ] Business logic isolated from database/worker code
- [ ] No database imports in service layer
- [ ] Input validation at service entry points
- [ ] Service tests don't require database
- [ ] Test cases verify service isolation

### For API Integration Stories
- [ ] API credentials encrypted
- [ ] API rate limits enforced
- [ ] API errors handled gracefully
- [ ] API responses validated before use
- [ ] Test cases mock external APIs

### For Filesystem Stories
- [ ] Path helpers used consistently
- [ ] No hard-coded paths
- [ ] Channel isolation enforced
- [ ] File permissions verified
- [ ] Test cases verify filesystem isolation

---

## Sign-Off Checklist

Before marking story "done", verify:

- [ ] All applicable checklist items completed or marked N/A
- [ ] Min 5 security test cases passing
- [ ] Adversarial review completed and approved
- [ ] Security findings documented in story
- [ ] Code review approved with security focus
- [ ] No known vulnerabilities remaining

**Reviewer Signature:** _____________________
**Date:** _____________________
**Story:** _____________________

---

## Resources

- **OWASP Top 10 (2021):** https://owasp.org/Top10/
- **OWASP Cheat Sheet Series:** https://cheatsheetseries.owasp.org/
- **SQLAlchemy Security:** https://docs.sqlalchemy.org/en/20/faq/security.html
- **Python Security Best Practices:** https://python.readthedocs.io/en/stable/library/security_warnings.html
- **Epic 3 Retrospective:** `_bmad-output/implementation-artifacts/epic-3-retrospective-2026-01-16.md`

---

## Changelog

- **2026-01-16:** Initial version created from Epic 3 retrospective findings
- **Future:** Update after each epic with new patterns and lessons
