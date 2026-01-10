"""Tests for app/config.py configuration module.

This module tests:
- Environment variable loading functions
- Default value handling
- Error cases for missing required configuration

Priority: P1 - Configuration is critical for all services.
"""

import os
from unittest.mock import patch

import pytest

from app.config import (
    get_channel_configs_dir,
    get_database_url,
    get_default_voice_id,
    get_fernet_key,
    get_workspace_root,
)


class TestGetDefaultVoiceId:
    """Tests for get_default_voice_id function."""

    def test_p1_returns_voice_id_when_set(self, monkeypatch: pytest.MonkeyPatch):
        """[P1] Should return DEFAULT_VOICE_ID when environment variable is set."""
        # GIVEN: DEFAULT_VOICE_ID is set
        expected_voice_id = "21m00Tcm4TlvDq8ikWAM"
        monkeypatch.setenv("DEFAULT_VOICE_ID", expected_voice_id)

        # WHEN: Calling get_default_voice_id
        result = get_default_voice_id()

        # THEN: Returns the configured voice ID
        assert result == expected_voice_id

    def test_p1_returns_none_when_not_set(self, monkeypatch: pytest.MonkeyPatch):
        """[P1] Should return None when DEFAULT_VOICE_ID is not set."""
        # GIVEN: DEFAULT_VOICE_ID is not set
        monkeypatch.delenv("DEFAULT_VOICE_ID", raising=False)

        # WHEN: Calling get_default_voice_id
        result = get_default_voice_id()

        # THEN: Returns None
        assert result is None

    def test_p2_returns_empty_string_when_set_empty(self, monkeypatch: pytest.MonkeyPatch):
        """[P2] Should return empty string when DEFAULT_VOICE_ID is set to empty."""
        # GIVEN: DEFAULT_VOICE_ID is set to empty string
        monkeypatch.setenv("DEFAULT_VOICE_ID", "")

        # WHEN: Calling get_default_voice_id
        result = get_default_voice_id()

        # THEN: Returns empty string (falsy but not None)
        assert result == ""


class TestGetDatabaseUrl:
    """Tests for get_database_url function."""

    def setup_method(self):
        """Clear LRU cache before each test."""
        get_database_url.cache_clear()

    def test_p1_raises_value_error_when_not_set(self, monkeypatch: pytest.MonkeyPatch):
        """[P1] Should raise ValueError when DATABASE_URL is not set."""
        # GIVEN: DATABASE_URL is not set
        monkeypatch.delenv("DATABASE_URL", raising=False)

        # WHEN/THEN: Calling get_database_url raises ValueError
        with pytest.raises(ValueError) as exc_info:
            get_database_url()

        assert "DATABASE_URL environment variable is required" in str(exc_info.value)

    def test_p1_returns_asyncpg_url_unchanged(self, monkeypatch: pytest.MonkeyPatch):
        """[P1] Should return postgresql+asyncpg URL unchanged."""
        # GIVEN: DATABASE_URL with asyncpg driver
        asyncpg_url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
        monkeypatch.setenv("DATABASE_URL", asyncpg_url)

        # WHEN: Calling get_database_url
        result = get_database_url()

        # THEN: Returns URL unchanged
        assert result == asyncpg_url

    def test_p1_converts_postgresql_to_asyncpg(self, monkeypatch: pytest.MonkeyPatch):
        """[P1] Should convert postgresql:// to postgresql+asyncpg://."""
        # GIVEN: DATABASE_URL with standard postgresql driver
        original_url = "postgresql://user:pass@localhost:5432/testdb"
        monkeypatch.setenv("DATABASE_URL", original_url)

        # WHEN: Calling get_database_url
        result = get_database_url()

        # THEN: Returns URL with asyncpg driver
        expected_url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
        assert result == expected_url

    def test_p2_only_replaces_protocol_prefix(self, monkeypatch: pytest.MonkeyPatch):
        """[P2] Should only replace the protocol prefix, not other occurrences."""
        # GIVEN: URL with postgresql in hostname
        original_url = "postgresql://user@postgresql-host.example.com:5432/db"
        monkeypatch.setenv("DATABASE_URL", original_url)

        # WHEN: Calling get_database_url
        result = get_database_url()

        # THEN: Only protocol is replaced
        expected_url = "postgresql+asyncpg://user@postgresql-host.example.com:5432/db"
        assert result == expected_url

    def test_p2_caches_result(self, monkeypatch: pytest.MonkeyPatch):
        """[P2] Should cache the result (lru_cache behavior)."""
        # GIVEN: DATABASE_URL is set
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")

        # WHEN: Calling get_database_url multiple times
        result1 = get_database_url()
        result2 = get_database_url()

        # THEN: Same result returned (cached)
        assert result1 == result2
        assert result1 is result2  # Same object (from cache)


class TestGetFernetKey:
    """Tests for get_fernet_key function."""

    def setup_method(self):
        """Clear LRU cache before each test."""
        get_fernet_key.cache_clear()

    def test_p1_raises_value_error_when_not_set(self, monkeypatch: pytest.MonkeyPatch):
        """[P1] Should raise ValueError when FERNET_KEY is not set."""
        # GIVEN: FERNET_KEY is not set
        monkeypatch.delenv("FERNET_KEY", raising=False)

        # WHEN/THEN: Calling get_fernet_key raises ValueError
        with pytest.raises(ValueError) as exc_info:
            get_fernet_key()

        assert "FERNET_KEY environment variable is required" in str(exc_info.value)

    def test_p1_returns_key_when_set(self, monkeypatch: pytest.MonkeyPatch):
        """[P1] Should return FERNET_KEY when set."""
        # GIVEN: FERNET_KEY is set
        from cryptography.fernet import Fernet

        expected_key = Fernet.generate_key().decode()
        monkeypatch.setenv("FERNET_KEY", expected_key)

        # WHEN: Calling get_fernet_key
        result = get_fernet_key()

        # THEN: Returns the configured key
        assert result == expected_key

    def test_p2_caches_result(self, monkeypatch: pytest.MonkeyPatch):
        """[P2] Should cache the result (lru_cache behavior)."""
        # GIVEN: FERNET_KEY is set
        from cryptography.fernet import Fernet

        monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())

        # WHEN: Calling get_fernet_key multiple times
        result1 = get_fernet_key()
        result2 = get_fernet_key()

        # THEN: Same result returned (cached)
        assert result1 == result2
        assert result1 is result2  # Same object (from cache)


class TestGetChannelConfigsDir:
    """Tests for get_channel_configs_dir function."""

    def test_p1_returns_env_value_when_set(self, monkeypatch: pytest.MonkeyPatch):
        """[P1] Should return CHANNEL_CONFIGS_DIR when set."""
        # GIVEN: CHANNEL_CONFIGS_DIR is set
        expected_dir = "/custom/configs/path"
        monkeypatch.setenv("CHANNEL_CONFIGS_DIR", expected_dir)

        # WHEN: Calling get_channel_configs_dir
        result = get_channel_configs_dir()

        # THEN: Returns the configured path
        assert result == expected_dir

    def test_p1_returns_default_when_not_set(self, monkeypatch: pytest.MonkeyPatch):
        """[P1] Should return default 'channel_configs' when not set."""
        # GIVEN: CHANNEL_CONFIGS_DIR is not set
        monkeypatch.delenv("CHANNEL_CONFIGS_DIR", raising=False)

        # WHEN: Calling get_channel_configs_dir
        result = get_channel_configs_dir()

        # THEN: Returns default value
        assert result == "channel_configs"


class TestGetWorkspaceRoot:
    """Tests for get_workspace_root function."""

    def test_p1_returns_env_value_when_set(self, monkeypatch: pytest.MonkeyPatch):
        """[P1] Should return WORKSPACE_ROOT when set."""
        # GIVEN: WORKSPACE_ROOT is set
        expected_root = "/custom/workspace"
        monkeypatch.setenv("WORKSPACE_ROOT", expected_root)

        # WHEN: Calling get_workspace_root
        result = get_workspace_root()

        # THEN: Returns the configured path
        assert result == expected_root

    def test_p1_returns_default_when_not_set(self, monkeypatch: pytest.MonkeyPatch):
        """[P1] Should return default '/app/workspace' when not set."""
        # GIVEN: WORKSPACE_ROOT is not set
        monkeypatch.delenv("WORKSPACE_ROOT", raising=False)

        # WHEN: Calling get_workspace_root
        result = get_workspace_root()

        # THEN: Returns default value
        assert result == "/app/workspace"

    def test_p2_returns_empty_string_when_set_empty(self, monkeypatch: pytest.MonkeyPatch):
        """[P2] Should return empty string when WORKSPACE_ROOT is set to empty."""
        # GIVEN: WORKSPACE_ROOT is set to empty string
        monkeypatch.setenv("WORKSPACE_ROOT", "")

        # WHEN: Calling get_workspace_root
        result = get_workspace_root()

        # THEN: Returns empty string (empty overrides default)
        assert result == ""


class TestConfigIntegration:
    """Integration tests for configuration module."""

    def setup_method(self):
        """Clear all LRU caches before each test."""
        get_database_url.cache_clear()
        get_fernet_key.cache_clear()

    def test_p2_all_configs_can_be_loaded_together(self, monkeypatch: pytest.MonkeyPatch):
        """[P2] All configuration values can be loaded without conflicts."""
        # GIVEN: All environment variables are set
        from cryptography.fernet import Fernet

        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())
        monkeypatch.setenv("DEFAULT_VOICE_ID", "voice123")
        monkeypatch.setenv("CHANNEL_CONFIGS_DIR", "/configs")
        monkeypatch.setenv("WORKSPACE_ROOT", "/workspace")

        # WHEN: Loading all configurations
        db_url = get_database_url()
        fernet_key = get_fernet_key()
        voice_id = get_default_voice_id()
        configs_dir = get_channel_configs_dir()
        workspace = get_workspace_root()

        # THEN: All values are returned correctly
        assert db_url == "postgresql+asyncpg://localhost/test"
        assert fernet_key is not None
        assert voice_id == "voice123"
        assert configs_dir == "/configs"
        assert workspace == "/workspace"
