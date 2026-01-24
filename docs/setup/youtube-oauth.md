# YouTube OAuth Setup Guide

This guide walks through setting up YouTube OAuth authentication for each channel in the AI Video Generator platform.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Google Cloud Console Setup](#google-cloud-console-setup)
- [OAuth Client Configuration](#oauth-client-configuration)
- [Running the Setup Script](#running-the-setup-script)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)
- [Re-Authorization](#re-authorization)
- [Security Considerations](#security-considerations)

## Overview

The YouTube OAuth setup process:

1. **One-time setup**: Create OAuth credentials in Google Cloud Console
2. **Per-channel setup**: Run CLI script to authorize each channel's YouTube account
3. **Token storage**: Refresh tokens are encrypted with Fernet and stored in PostgreSQL
4. **Automatic refresh**: Access tokens (1-hour expiry) are refreshed automatically using stored refresh tokens

**Key Facts:**

- ✅ Refresh tokens are permanent (until revoked)
- ✅ Access tokens expire after 1 hour (automatic refresh)
- ✅ Each channel has independent YouTube account authorization
- ✅ Tokens are encrypted with Fernet before database storage
- ⚠️ OAuth setup requires browser access (run locally, not on Railway)

## Prerequisites

Before starting, ensure you have:

- **Google account** for each YouTube channel
- **Google Cloud Console access** (https://console.cloud.google.com)
- **FERNET_KEY environment variable** (for encryption)
  ```bash
  python scripts/generate_fernet_key.py
  export FERNET_KEY=<generated-key>
  ```
- **Database access** (channels synced via `sync_channels.py`)
- **Local machine with browser** (OAuth requires browser redirect)

## Google Cloud Console Setup

### Step 1: Create or Select Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Click project dropdown in top navigation
3. Click **New Project** or select existing project
4. Name your project (e.g., "AI Video Generator Production")
5. Click **Create**

### Step 2: Enable YouTube Data API v3

1. Navigate to **APIs & Services > Library**
2. Search for "YouTube Data API v3"
3. Click on the result
4. Click **Enable**
5. Wait for API to be enabled (usually instant)

### Step 3: Configure OAuth Consent Screen

1. Navigate to **APIs & Services > OAuth consent screen**
2. Select **External** user type (unless using Google Workspace)
3. Click **Create**
4. Fill in required fields:
   - **App name**: "AI Video Generator" (or your app name)
   - **User support email**: Your email address
   - **Developer contact**: Your email address
5. Click **Save and Continue**
6. **Scopes**: Click **Add or Remove Scopes**
   - Search for and add:
     - `.../auth/youtube.upload` (Upload videos)
     - `.../auth/youtube.force-ssl` (Manage videos)
   - Click **Update**
7. Click **Save and Continue**
8. **Test users** (if app is in testing): Add your YouTube account emails
9. Click **Save and Continue**
10. Review summary and click **Back to Dashboard**

## OAuth Client Configuration

### Step 4: Create OAuth 2.0 Client ID

1. Navigate to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth client ID**
3. Application type: **Desktop app**
4. Name: "OAuth Client for AI Video Generator"
5. Click **Create**

### Step 5: Download client_secret.json

1. In the OAuth 2.0 Client IDs table, find your newly created client
2. Click the **Download** icon (↓) on the right
3. Save the file as `client_secret.json`
4. **CRITICAL**: Place `client_secret.json` in the project root directory
5. **SECURITY**: Verify `client_secret.json` is in `.gitignore` (it should be)

### Step 6: Configure Redirect URI

The script uses `http://localhost` as the redirect URI (with random port).

**Verification:**

1. In Google Cloud Console, go to **Credentials**
2. Click on your OAuth 2.0 Client ID
3. Check "Authorized redirect URIs"
4. Should contain: `http://localhost` (no port, no trailing slash)
5. If missing, click **Add URI** and add `http://localhost`
6. Click **Save**

**Note**: `google-auth-oauthlib` automatically appends the random port during OAuth flow.

## Running the Setup Script

### For Each Channel:

Run the OAuth setup script once per channel to authorize the corresponding YouTube account.

**Example: Setup for "poke1" channel:**

```bash
python scripts/setup_channel_oauth.py --channel poke1
```

**What happens:**

1. Script validates `client_secret.json` exists
2. Script checks channel exists in database
3. Browser opens to Google OAuth consent screen
4. You authorize the YouTube account for this channel
5. Script receives OAuth callback with refresh token
6. Script encrypts token with Fernet
7. Script stores encrypted token in `channels.youtube_token_encrypted`
8. Success message printed

**Expected Output:**

```
Setting up YouTube OAuth for channel: Pokemon Documentary Channel

⏳ Opening browser for OAuth consent...
   Please authorize the application in your browser

✅ OAuth consent granted
⏳ Encrypting and storing refresh token...
✅ OAuth setup complete for channel 'Pokemon Documentary Channel'

Notes:
  - Refresh token stored in database (encrypted)
  - Access token expires after 1 hour (automatic refresh)
  - To re-authorize: Remove app from https://myaccount.google.com/permissions and run again
```

### Multiple Channels:

Repeat for each channel with different Google accounts:

```bash
python scripts/setup_channel_oauth.py --channel poke1
python scripts/setup_channel_oauth.py --channel poke2
python scripts/setup_channel_oauth.py --channel poke3
```

**Important**: Each channel should use a separate YouTube account for independent quota tracking.

## Verification

### Verify Token Storage:

Use Python to verify the token was stored correctly:

```python
import asyncio
from app.database import async_session_factory
from app.services.credential_service import CredentialService

async def verify_token():
    async with async_session_factory() as db:
        service = CredentialService()
        token = await service.get_youtube_token("poke1", db)

        if token:
            print(f"✅ Token found for poke1: {token[:20]}...")
        else:
            print("❌ No token found for poke1")

asyncio.run(verify_token())
```

### Verify in Database:

```sql
-- Check token exists (encrypted bytes, not readable)
SELECT
    channel_id,
    channel_name,
    youtube_token_encrypted IS NOT NULL as has_token,
    LENGTH(youtube_token_encrypted) as token_length
FROM channels;
```

**Expected:**

```
channel_id | channel_name                    | has_token | token_length
-----------+---------------------------------+-----------+--------------
poke1      | Pokemon Documentary Channel     | t         | 156
```

## Troubleshooting

### Browser Doesn't Open

**Problem**: `run_local_server()` fails to open browser

**Solution**:

```bash
# Option 1: Manually open URL printed in console
# Script will print: "Please visit: http://localhost:XXXXX"

# Option 2: Use headless flow (advanced)
# Modify script to use manual authorization flow instead
```

### Redirect URI Mismatch

**Error**: `redirect_uri_mismatch`

**Solution**:

1. Check Google Cloud Console > Credentials > OAuth 2.0 Client ID
2. Authorized redirect URIs must include: `http://localhost`
3. **Do NOT** include port (script uses random port)
4. **Do NOT** include trailing slash
5. Click Save and try again

### No Refresh Token Received

**Error**: "No refresh token received from Google"

**Cause**: User already authorized the app previously

**Solution**:

1. Go to https://myaccount.google.com/permissions
2. Find "AI Video Generator" (or your app name)
3. Click **Remove Access**
4. Run setup script again
5. OAuth will now return a new refresh token

### Channel Not Found

**Error**: `Channel 'poke1' not found in database`

**Solution**:

```bash
# Sync channels from YAML configs to database first
python scripts/sync_channels.py

# Verify channels exist
python -c "
import asyncio
from app.database import async_session_factory
from app.models import Channel
from sqlalchemy import select

async def list_channels():
    async with async_session_factory() as db:
        result = await db.execute(select(Channel))
        for ch in result.scalars():
            print(f'{ch.channel_id}: {ch.channel_name}')

asyncio.run(list_channels())
"
```

### FERNET_KEY Missing

**Error**: `FERNET_KEY environment variable not set`

**Solution**:

```bash
# Generate encryption key
python scripts/generate_fernet_key.py

# Copy the output key
# Add to environment
export FERNET_KEY=<your-44-char-base64-key>

# For Railway: Add to environment variables in dashboard
```

### Network Errors

**Error**: `Network error during OAuth`

**Causes**:

- No internet connection
- Firewall blocking localhost connections
- Port already in use

**Solutions**:

```bash
# Check internet connection
ping google.com

# Check firewall allows localhost connections
# (Usually not an issue, but check if restricted network)

# Try again (script uses random port to avoid conflicts)
python scripts/setup_channel_oauth.py --channel poke1
```

## Re-Authorization

### When to Re-Authorize:

- Token revoked by user in Google Account settings
- Switching to different YouTube account for channel
- Adding new OAuth scopes to app
- Security audit requires token rotation

### How to Re-Authorize:

**Option 1: Revoke and Re-Run (Recommended)**

```bash
# 1. Revoke access in Google Account
# Visit: https://myaccount.google.com/permissions
# Remove: "AI Video Generator"

# 2. Run setup script again
python scripts/setup_channel_oauth.py --channel poke1

# 3. Authorize in browser
# New refresh token will replace old token
```

**Option 2: Direct Re-Run (If Revocation Not Needed)**

```bash
# Just run script again (overwrites existing token)
python scripts/setup_channel_oauth.py --channel poke1
```

### Verify Re-Authorization:

```bash
# Check updated_at timestamp changed
python -c "
import asyncio
from app.database import async_session_factory
from app.models import Channel
from sqlalchemy import select

async def check_token_update():
    async with async_session_factory() as db:
        result = await db.execute(
            select(Channel).where(Channel.channel_id == 'poke1')
        )
        channel = result.scalar_one()
        print(f'Last updated: {channel.updated_at}')

asyncio.run(check_token_update())
"
```

## Security Considerations

### Token Security Best Practices:

1. **Never log plaintext tokens**
   ```python
   # ❌ WRONG
   log.info("token_stored", token=refresh_token)

   # ✅ CORRECT
   log.info("oauth_setup_success", channel_id=channel_id)
   ```

2. **Never commit credentials**
   ```gitignore
   # .gitignore (already configured)
   client_secret.json
   token.pickle
   token.json
   *.pem
   ```

3. **Rotate FERNET_KEY periodically**
   ```bash
   # Generate new key
   python scripts/generate_fernet_key.py

   # Update Railway environment variables
   # Re-run OAuth setup for all channels (tokens encrypted with new key)
   ```

4. **Use separate Google accounts per channel**
   - Independent quota tracking
   - Isolated security boundaries
   - Easier audit trails

5. **Monitor OAuth token usage**
   ```sql
   -- Check which channels have tokens
   SELECT channel_id, updated_at
   FROM channels
   WHERE youtube_token_encrypted IS NOT NULL;
   ```

### Railway Deployment Security:

**Environment Variables (Railway Dashboard):**

```bash
FERNET_KEY=<44-char-base64-key>  # From scripts/generate_fernet_key.py
DATABASE_URL=<railway-provides>   # Auto-configured by Railway
```

**File Upload (Railway CLI or Dashboard):**

- Upload `client_secret.json` as environment variable or secret file
- **Never** commit to git repository

**Access Control:**

- OAuth setup runs locally (not on Railway)
- Refresh tokens stored in database (accessible by workers)
- Railway workers use tokens via CredentialService (automatic decryption)

---

## Railway Deployment Workflow (Issue #6 - Complete Setup Guide)

This section provides a complete Railway deployment workflow for YouTube OAuth.

### Architecture Overview

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│  Local Machine  │────────▶│  PostgreSQL DB   │◀────────│ Railway Worker  │
│  (OAuth Setup)  │         │  (Railway-hosted)│         │  (Production)   │
└─────────────────┘         └──────────────────┘         └─────────────────┘
      │                              │                            │
      │                              │                            │
      ├─ Run CLI script              ├─ Encrypted tokens         ├─ Decrypts tokens
      ├─ Browser OAuth flow          ├─ Accessible from Railway  ├─ Calls YouTube API
      └─ Store encrypted token       └─ Production database      └─ Uploads videos
```

### Step 1: Environment Setup (One-Time)

**1.1 Generate Encryption Key:**

```bash
# On local machine
python scripts/generate_fernet_key.py

# Output: Copy this key for next step
# FERNET_KEY=rA8K...base64-encoded-44-chars...
```

**1.2 Add to Railway Environment Variables:**

```bash
# Via Railway Dashboard:
# 1. Go to project > Variables tab
# 2. Add variable: FERNET_KEY = <your-generated-key>
# 3. Click "Add"
# 4. Deploy to apply changes

# Or via Railway CLI:
railway variables set FERNET_KEY=<your-generated-key>
```

**1.3 Verify DATABASE_URL (Auto-Configured):**

Railway automatically sets `DATABASE_URL` when PostgreSQL plugin is added. Verify:

```bash
# Railway Dashboard: Variables tab
# Should see: DATABASE_URL=postgresql://...

# Or via CLI:
railway variables get DATABASE_URL
```

### Step 2: Google Cloud Console Setup (Per Environment)

**CRITICAL**: Create separate Google Cloud projects for staging and production.

**2.1 Production Project:**

```
Project Name: AI Video Generator - Production
Project ID: ai-video-gen-prod-12345
OAuth App Name: AI Video Generator (Production)
```

**2.2 Staging Project (Optional but Recommended):**

```
Project Name: AI Video Generator - Staging
Project ID: ai-video-gen-staging-67890
OAuth App Name: AI Video Generator (Staging)
```

**Why Separate Projects?**

- Independent quota tracking (10,000 quota units/day per project)
- Isolated security boundaries
- Separate OAuth consent screens
- Easier audit trails

### Step 3: Upload client_secret.json to Railway

**Option A: Environment Variable (Recommended for Single File):**

```bash
# 1. Convert client_secret.json to base64 (for env var)
cat client_secret.json | base64 > client_secret_base64.txt

# 2. Add to Railway variables
railway variables set CLIENT_SECRET_BASE64=$(cat client_secret_base64.txt)

# 3. In Railway app startup, decode:
# echo $CLIENT_SECRET_BASE64 | base64 -d > client_secret.json
```

**Option B: Railway Volume (Recommended for Multiple Environments):**

```bash
# 1. Create Railway volume via dashboard
# 2. Mount volume to /secrets
# 3. Upload client_secret.json via Railway CLI:
railway volume attach <volume-id> /secrets
railway volume upload /secrets/client_secret.json ./client_secret.json
```

**Security Note**: Never commit `client_secret.json` to git. Railway-hosted workers should never expose this file publicly.

### Step 4: Local OAuth Setup for Each Channel

**4.1 Connect to Railway Database Locally:**

```bash
# Install Railway CLI (if not already)
npm i -g @railway/cli

# Login and link project
railway login
railway link

# Get database connection string
railway variables get DATABASE_URL

# Set local environment (use Railway's database)
export DATABASE_URL=$(railway variables get DATABASE_URL)
export FERNET_KEY=$(railway variables get FERNET_KEY)
```

**4.2 Sync Channels to Database:**

```bash
# Ensure channels exist in Railway database
python scripts/sync_channels.py
```

**4.3 Run OAuth Setup for Each Channel:**

```bash
# Channel 1 (poke1)
python scripts/setup_channel_oauth.py --channel poke1

# Browser opens → Authorize with Google account for poke1
# Token encrypted and stored in Railway PostgreSQL

# Channel 2 (poke2)
python scripts/setup_channel_oauth.py --channel poke2

# Repeat for all channels...
```

**CRITICAL**: Each channel should authorize with a **different YouTube/Google account** for independent quota tracking.

### Step 5: Verify Railway Worker Access

**5.1 Test Token Retrieval (Railway CLI):**

```bash
# SSH into Railway container
railway run bash

# Inside container:
python -c "
import asyncio
from app.database import async_session_factory
from app.services.credential_service import CredentialService

async def test():
    async with async_session_factory() as db:
        service = CredentialService()
        token = await service.get_youtube_token('poke1', db)
        print(f'Token retrieved: {token[:20]}...' if token else 'NO TOKEN')

asyncio.run(test())
"

# Expected output: Token retrieved: 1//0gB...
```

**5.2 Test YouTube API Connection:**

```bash
# Inside Railway container:
python -c "
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from app.services.credential_service import CredentialService
# ... (full test code in troubleshooting section below)
"
```

### Step 6: Production Deployment Checklist

**Pre-Deployment:**

- [ ] FERNET_KEY set in Railway environment variables
- [ ] DATABASE_URL verified (Railway auto-config)
- [ ] client_secret.json uploaded to Railway (env var or volume)
- [ ] All channels synced to database (`sync_channels.py`)
- [ ] OAuth setup completed for all channels (local → Railway DB)
- [ ] Token retrieval tested (Step 5.1)
- [ ] YouTube API connection tested (Step 5.2)

**Post-Deployment:**

- [ ] Worker starts successfully (check Railway logs)
- [ ] No encryption errors in logs
- [ ] YouTube upload test successful
- [ ] Quota tracking working (check Google Cloud Console)

### Step 7: Rollback Procedures

**If OAuth Setup Fails Mid-Deployment:**

```bash
# 1. Identify affected channel
SELECT channel_id, updated_at
FROM channels
WHERE youtube_token_encrypted IS NULL;

# 2. Re-run OAuth setup locally
python scripts/setup_channel_oauth.py --channel <channel_id>

# 3. Verify token stored
python -c "
from app.services.credential_service import CredentialService
# ... (verification code)
"
```

**If FERNET_KEY Rotation Required:**

```bash
# CRITICAL: All tokens must be re-authorized after key rotation

# 1. Generate new FERNET_KEY
python scripts/generate_fernet_key.py

# 2. Update Railway environment variable
railway variables set FERNET_KEY=<new-key>

# 3. Redeploy Railway app (restarts workers)
railway up

# 4. Re-authorize ALL channels (tokens encrypted with old key are now invalid)
python scripts/setup_channel_oauth.py --channel poke1
python scripts/setup_channel_oauth.py --channel poke2
# ... repeat for all channels
```

### Multi-Environment Strategy

**Staging Environment:**

```bash
# Separate Railway project for staging
railway link --environment staging

# Use staging Google Cloud project
# - Different client_secret.json
# - Different YouTube accounts
# - Independent quota tracking

# Set staging FERNET_KEY (different from production)
railway variables set FERNET_KEY=<staging-key>

# Run OAuth setup with staging accounts
export DATABASE_URL=$(railway variables get DATABASE_URL --environment staging)
python scripts/setup_channel_oauth.py --channel staging-poke1
```

**Production Environment:**

```bash
# Production Railway project
railway link --environment production

# Use production Google Cloud project
# - Production client_secret.json
# - Production YouTube accounts
# - Isolated quota tracking

railway variables set FERNET_KEY=<production-key>

python scripts/setup_channel_oauth.py --channel poke1
```

### Troubleshooting Railway Deployment

**Error: "Database connection failed"**

```bash
# Verify DATABASE_URL is set
railway variables get DATABASE_URL

# Test connection from local machine
psql $DATABASE_URL -c "SELECT 1;"

# Check Railway PostgreSQL plugin status
railway status
```

**Error: "FERNET_KEY not set"**

```bash
# Verify environment variable exists
railway variables get FERNET_KEY

# Should return 44-character base64 string
# If missing or wrong length, regenerate and set
```

**Error: "client_secret.json not found" (Railway Worker)**

```bash
# If using environment variable approach:
# Verify CLIENT_SECRET_BASE64 is set
railway variables get CLIENT_SECRET_BASE64

# If using volume approach:
railway volumes list
railway volume files <volume-id>  # Should show client_secret.json
```

**Token Retrieval Returns None:**

```bash
# Common causes:
# 1. OAuth setup not run for this channel
# 2. Different FERNET_KEY between local and Railway
# 3. Database not synced

# Solution: Re-run OAuth setup
export DATABASE_URL=$(railway variables get DATABASE_URL)
export FERNET_KEY=$(railway variables get FERNET_KEY)
python scripts/setup_channel_oauth.py --channel <channel_id>
```

### Security Best Practices (Railway)

1. **Never Log DATABASE_URL or FERNET_KEY:**
   ```python
   # ❌ WRONG
   print(f"DATABASE_URL: {os.getenv('DATABASE_URL')}")

   # ✅ CORRECT
   log.info("database_connected", has_url=bool(os.getenv('DATABASE_URL')))
   ```

2. **Rotate FERNET_KEY Quarterly:**
   ```bash
   # Schedule reminder: Every 90 days
   # Generate new key → Update Railway → Re-authorize all channels
   ```

3. **Use Railway Secrets for client_secret.json:**
   - Never store in environment variables (too risky)
   - Use Railway volumes with restricted permissions
   - Consider AWS Secrets Manager integration (advanced)

4. **Monitor OAuth Token Usage:**
   ```sql
   -- Check last token update
   SELECT channel_id, updated_at
   FROM channels
   WHERE youtube_token_encrypted IS NOT NULL
   ORDER BY updated_at DESC;
   ```

5. **Audit Trail:**
   ```bash
   # Check Railway deployment logs for OAuth operations
   railway logs --filter "oauth_setup_success"
   ```

### Audit Logging:

Monitor OAuth operations:

```sql
-- Future: audit_logs table
SELECT
    timestamp,
    action,
    channel_id,
    user_id
FROM audit_logs
WHERE action = 'oauth_setup_success'
ORDER BY timestamp DESC;
```

## Additional Resources

- [YouTube Data API v3 Documentation](https://developers.google.com/youtube/v3)
- [OAuth 2.0 for Installed Apps](https://developers.google.com/youtube/v3/guides/auth/installed-apps)
- [Google OAuth 2.0 Scopes](https://developers.google.com/identity/protocols/oauth2/scopes)
- [google-auth-oauthlib Documentation](https://googleapis.dev/python/google-auth-oauthlib/latest/)
- [YouTube API Quotas](https://developers.google.com/youtube/v3/getting-started#quota)

## Quick Reference

| Task | Command |
|------|---------|
| Setup OAuth for channel | `python scripts/setup_channel_oauth.py --channel <id>` |
| Custom client_secret path | `python scripts/setup_channel_oauth.py --channel <id> --client-secrets /path/to/file.json` |
| Generate FERNET_KEY | `python scripts/generate_fernet_key.py` |
| Sync channels to database | `python scripts/sync_channels.py` |
| Verify token exists | `python -c "from app.services.credential_service import CredentialService; ..."` |

## Support

For issues or questions:

1. Check [Troubleshooting](#troubleshooting) section above
2. Review [Google OAuth troubleshooting](https://developers.google.com/identity/protocols/oauth2/native-app#troubleshooting)
3. Check Railway logs for encryption/database errors
4. Verify FERNET_KEY matches between environments
