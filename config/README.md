# Channel Configuration

This directory contains YAML configuration files for each YouTube channel.

## Directory Structure

```
config/
└── channels/
    ├── example.yaml    # Template/example configuration
    ├── poke1.yaml      # Pokemon Channel 1
    ├── poke2.yaml      # Pokemon Channel 2
    └── ...
```

## Creating a New Channel

1. Copy `example.yaml` to a new file named `{channel_id}.yaml`
2. Edit the configuration with your channel's settings
3. Run `uv run alembic upgrade head` to ensure database is ready
4. Load config: The `ChannelConfigLoader` will sync YAML to database

## Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `channel_id` | Yes | Unique identifier (must match filename) |
| `channel_name` | Yes | Human-readable display name |
| `is_active` | No | Enable/disable channel (default: true) |
| `voice_id` | No | ElevenLabs voice ID for narration |
| `default_voice_id` | No | Fallback voice ID |
| `branding.intro_path` | No | Relative path to intro video |
| `branding.outro_path` | No | Relative path to outro video |
| `branding.watermark_path` | No | Relative path to watermark image |
| `storage_strategy` | No | "notion" (default) or "r2" |
| `r2_config.*` | No | Cloudflare R2 credentials (if r2) |
| `max_concurrent` | No | Max parallel tasks (default: 2) |

## Credentials

**Do NOT put sensitive credentials in YAML files.**

Credentials (OAuth tokens, API keys) are stored encrypted in the database
and managed via CLI tools:

```bash
# Set YouTube OAuth token (run OAuth flow)
python scripts/setup_channel_oauth.py --channel poke1 --service youtube

# Set API keys
python scripts/setup_channel_credentials.py --channel poke1
```

## Environment Variables

Required environment variables (set in Railway or `.env`):

- `DATABASE_URL` - PostgreSQL connection string
- `FERNET_KEY` - Encryption key for credentials

See `/.env.example` for full list.
