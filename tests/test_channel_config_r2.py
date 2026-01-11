"""Tests for R2 configuration in channel config schema.

This module tests the R2Config nested model and storage strategy validation
in ChannelConfigSchema.
"""

import pytest
from pydantic import ValidationError

from app.schemas.channel_config import ChannelConfigSchema, R2Config


class TestR2ConfigValidation:
    """Test suite for R2Config model validation."""

    def test_valid_r2_config(self) -> None:
        """Test that valid R2 config passes validation."""
        r2_config = R2Config(
            account_id="test_account_id",
            access_key_id="test_access_key_id",
            secret_access_key="test_secret_access_key",
            bucket_name="valid-bucket-name",
        )

        assert r2_config.account_id == "test_account_id"
        assert r2_config.access_key_id == "test_access_key_id"
        assert r2_config.secret_access_key == "test_secret_access_key"
        assert r2_config.bucket_name == "valid-bucket-name"

    def test_bucket_name_lowercase_normalization(self) -> None:
        """Test that bucket name is normalized to lowercase."""
        r2_config = R2Config(
            account_id="acc",
            access_key_id="key",
            secret_access_key="secret",
            bucket_name="My-Bucket-Name",
        )

        assert r2_config.bucket_name == "my-bucket-name"

    def test_bucket_name_minimum_length(self) -> None:
        """Test that bucket name must be at least 3 characters."""
        with pytest.raises(ValidationError) as exc_info:
            R2Config(
                account_id="acc",
                access_key_id="key",
                secret_access_key="secret",
                bucket_name="ab",  # Too short
            )

        assert "bucket_name" in str(exc_info.value)

    def test_bucket_name_maximum_length(self) -> None:
        """Test that bucket name must not exceed 63 characters."""
        with pytest.raises(ValidationError) as exc_info:
            R2Config(
                account_id="acc",
                access_key_id="key",
                secret_access_key="secret",
                bucket_name="a" * 64,  # Too long
            )

        assert "bucket_name" in str(exc_info.value)

    def test_bucket_name_invalid_start_hyphen(self) -> None:
        """Test that bucket name cannot start with hyphen."""
        with pytest.raises(ValidationError) as exc_info:
            R2Config(
                account_id="acc",
                access_key_id="key",
                secret_access_key="secret",
                bucket_name="-invalid-bucket",
            )

        assert "bucket_name" in str(exc_info.value).lower()

    def test_bucket_name_invalid_end_hyphen(self) -> None:
        """Test that bucket name cannot end with hyphen."""
        with pytest.raises(ValidationError) as exc_info:
            R2Config(
                account_id="acc",
                access_key_id="key",
                secret_access_key="secret",
                bucket_name="invalid-bucket-",
            )

        assert "bucket_name" in str(exc_info.value).lower()

    def test_bucket_name_invalid_characters(self) -> None:
        """Test that bucket name cannot contain invalid characters."""
        with pytest.raises(ValidationError) as exc_info:
            R2Config(
                account_id="acc",
                access_key_id="key",
                secret_access_key="secret",
                bucket_name="invalid_bucket",  # Underscore not allowed
            )

        assert "bucket_name" in str(exc_info.value).lower()

    def test_bucket_name_valid_with_hyphens(self) -> None:
        """Test that bucket name can contain hyphens."""
        r2_config = R2Config(
            account_id="acc",
            access_key_id="key",
            secret_access_key="secret",
            bucket_name="my-valid-bucket-name",
        )

        assert r2_config.bucket_name == "my-valid-bucket-name"

    def test_bucket_name_valid_numeric(self) -> None:
        """Test that bucket name can be all numeric."""
        r2_config = R2Config(
            account_id="acc",
            access_key_id="key",
            secret_access_key="secret",
            bucket_name="123456789",
        )

        assert r2_config.bucket_name == "123456789"

    def test_r2_config_repr_masks_credentials(self) -> None:
        """Test that R2Config repr masks sensitive credentials."""
        r2_config = R2Config(
            account_id="secret_account_id",
            access_key_id="secret_access_key_id",
            secret_access_key="super_secret_key",
            bucket_name="my-bucket",
        )

        repr_str = repr(r2_config)

        # Bucket name should be visible
        assert "my-bucket" in repr_str
        # Credentials should not be visible
        assert "secret_account_id" not in repr_str
        assert "secret_access_key_id" not in repr_str
        assert "super_secret_key" not in repr_str

    def test_missing_required_fields(self) -> None:
        """Test that all R2 config fields are required."""
        with pytest.raises(ValidationError) as exc_info:
            R2Config(
                account_id="acc",
                # Missing access_key_id, secret_access_key, bucket_name
            )

        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        assert "access_key_id" in missing_fields
        assert "secret_access_key" in missing_fields
        assert "bucket_name" in missing_fields


class TestChannelConfigSchemaStorageStrategy:
    """Test suite for storage strategy validation in ChannelConfigSchema."""

    def test_default_storage_strategy_is_notion(self) -> None:
        """Test that default storage strategy is 'notion'."""
        config = ChannelConfigSchema(
            channel_id="test_channel",
            channel_name="Test Channel",
            notion_database_id="abc123",
        )

        assert config.storage_strategy == "notion"

    def test_explicit_notion_storage_strategy(self) -> None:
        """Test that 'notion' storage strategy is valid."""
        config = ChannelConfigSchema(
            channel_id="test_channel",
            channel_name="Test Channel",
            notion_database_id="abc123",
            storage_strategy="notion",
        )

        assert config.storage_strategy == "notion"
        assert config.r2_config is None

    def test_r2_storage_strategy_with_config(self) -> None:
        """Test that 'r2' storage strategy with r2_config is valid."""
        config = ChannelConfigSchema(
            channel_id="test_channel",
            channel_name="Test Channel",
            notion_database_id="abc123",
            storage_strategy="r2",
            r2_config=R2Config(
                account_id="acc",
                access_key_id="key",
                secret_access_key="secret",
                bucket_name="my-bucket",
            ),
        )

        assert config.storage_strategy == "r2"
        assert config.r2_config is not None
        assert config.r2_config.bucket_name == "my-bucket"

    def test_r2_storage_strategy_without_config_raises_error(self) -> None:
        """Test that 'r2' storage strategy without r2_config raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="test_channel",
                channel_name="Test Channel",
                notion_database_id="abc123",
                storage_strategy="r2",
                # Missing r2_config
            )

        assert "r2_config is required" in str(exc_info.value)

    def test_notion_storage_strategy_with_r2_config_is_ignored(self) -> None:
        """Test that r2_config is ignored when storage_strategy is 'notion'."""
        # This should not raise an error - r2_config is just ignored
        config = ChannelConfigSchema(
            channel_id="test_channel",
            channel_name="Test Channel",
            notion_database_id="abc123",
            storage_strategy="notion",
            r2_config=R2Config(
                account_id="acc",
                access_key_id="key",
                secret_access_key="secret",
                bucket_name="my-bucket",
            ),
        )

        assert config.storage_strategy == "notion"
        # r2_config is present but won't be used
        assert config.r2_config is not None

    def test_invalid_storage_strategy_raises_error(self) -> None:
        """Test that invalid storage strategy raises error."""
        with pytest.raises(ValidationError) as exc_info:
            ChannelConfigSchema(
                channel_id="test_channel",
                channel_name="Test Channel",
                notion_database_id="abc123",
                storage_strategy="invalid",
            )

        assert "storage_strategy" in str(exc_info.value)

    def test_storage_strategy_case_insensitive(self) -> None:
        """Test that storage strategy is case-insensitive."""
        config = ChannelConfigSchema(
            channel_id="test_channel",
            channel_name="Test Channel",
            notion_database_id="abc123",
            storage_strategy="R2",
            r2_config=R2Config(
                account_id="acc",
                access_key_id="key",
                secret_access_key="secret",
                bucket_name="my-bucket",
            ),
        )

        # Should be normalized to lowercase
        assert config.storage_strategy == "r2"

    def test_channel_config_repr_shows_storage_strategy(self) -> None:
        """Test that ChannelConfigSchema repr shows storage strategy."""
        config = ChannelConfigSchema(
            channel_id="test_channel",
            channel_name="Test Channel",
            notion_database_id="abc123",
            storage_strategy="r2",
            r2_config=R2Config(
                account_id="acc",
                access_key_id="key",
                secret_access_key="secret",
                bucket_name="my-bucket",
            ),
        )

        repr_str = repr(config)

        assert "storage_strategy='r2'" in repr_str
        assert "r2_config=configured" in repr_str

    def test_channel_config_repr_shows_not_configured_r2(self) -> None:
        """Test that ChannelConfigSchema repr shows r2_config not configured."""
        config = ChannelConfigSchema(
            channel_id="test_channel",
            channel_name="Test Channel",
            notion_database_id="abc123",
            storage_strategy="notion",
        )

        repr_str = repr(config)

        assert "storage_strategy='notion'" in repr_str
        assert "r2_config=not_configured" in repr_str


class TestChannelConfigSchemaFromYAML:
    """Test suite for parsing YAML config with R2 settings."""

    def test_parse_yaml_with_notion_storage(self) -> None:
        """Test parsing YAML config with notion storage."""
        yaml_data = {
            "channel_id": "poke1",
            "channel_name": "Pokemon Channel",
            "notion_database_id": "abc123",
            "storage_strategy": "notion",
        }

        config = ChannelConfigSchema.model_validate(yaml_data)

        assert config.channel_id == "poke1"
        assert config.storage_strategy == "notion"
        assert config.r2_config is None

    def test_parse_yaml_with_r2_storage(self) -> None:
        """Test parsing YAML config with R2 storage."""
        yaml_data = {
            "channel_id": "poke1",
            "channel_name": "Pokemon Channel",
            "notion_database_id": "abc123",
            "storage_strategy": "r2",
            "r2_config": {
                "account_id": "cloudflare_account",
                "access_key_id": "r2_key",
                "secret_access_key": "r2_secret",
                "bucket_name": "pokemon-assets",
            },
        }

        config = ChannelConfigSchema.model_validate(yaml_data)

        assert config.channel_id == "poke1"
        assert config.storage_strategy == "r2"
        assert config.r2_config is not None
        assert config.r2_config.account_id == "cloudflare_account"
        assert config.r2_config.bucket_name == "pokemon-assets"

    def test_parse_yaml_without_storage_defaults_to_notion(self) -> None:
        """Test that parsing YAML without storage_strategy defaults to notion."""
        yaml_data = {
            "channel_id": "poke1",
            "channel_name": "Pokemon Channel",
            "notion_database_id": "abc123",
        }

        config = ChannelConfigSchema.model_validate(yaml_data)

        assert config.storage_strategy == "notion"

    def test_parse_yaml_r2_without_config_raises(self) -> None:
        """Test that parsing YAML with r2 but no config raises error."""
        yaml_data = {
            "channel_id": "poke1",
            "channel_name": "Pokemon Channel",
            "notion_database_id": "abc123",
            "storage_strategy": "r2",
        }

        with pytest.raises(ValidationError):
            ChannelConfigSchema.model_validate(yaml_data)

    def test_parse_yaml_r2_with_partial_config_raises(self) -> None:
        """Test that parsing YAML with partial r2_config raises error."""
        yaml_data = {
            "channel_id": "poke1",
            "channel_name": "Pokemon Channel",
            "notion_database_id": "abc123",
            "storage_strategy": "r2",
            "r2_config": {
                "account_id": "acc",
                # Missing other required fields
            },
        }

        with pytest.raises(ValidationError):
            ChannelConfigSchema.model_validate(yaml_data)


class TestR2ConfigExport:
    """Test suite for R2Config export from schemas package."""

    def test_r2_config_exported_from_schemas(self) -> None:
        """Test that R2Config is exported from app.schemas."""
        from app.schemas import R2Config as ExportedR2Config

        assert ExportedR2Config is R2Config

    def test_r2_config_in_schemas_all(self) -> None:
        """Test that R2Config is in __all__ of app.schemas."""
        from app import schemas

        assert "R2Config" in schemas.__all__
