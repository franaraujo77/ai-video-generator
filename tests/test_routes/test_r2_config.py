"""Tests for R2 configuration API endpoints (Story 8.4).

Tests verify:
- R2 credential storage via API endpoints
- R2 configuration retrieval
- R2 configuration deletion
- Error handling for missing/invalid inputs
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import Channel


@pytest.mark.asyncio
async def test_store_r2_config_success(
    async_client: AsyncClient, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test storing R2 configuration for a channel."""
    # Set up encryption key
    from cryptography.fernet import Fernet

    fernet_key = Fernet.generate_key().decode()
    monkeypatch.setenv("FERNET_KEY", fernet_key)

    # Create test channel
    channel = Channel(channel_id="poke1", channel_name="Test Channel")
    async_session.add(channel)
    await async_session.commit()

    # Store R2 config via API
    response = await async_client.post(
        "/api/v1/channels/poke1/r2-config",
        json={
            "access_key_id": "test_access_key",
            "secret_access_key": "test_secret_key",
            "bucket_name": "test-bucket",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["channel_id"] == "poke1"
    assert data["bucket_name"] == "test-bucket"
    assert data["has_credentials"] is True


@pytest.mark.asyncio
async def test_store_r2_config_channel_not_found(async_client: AsyncClient) -> None:
    """Test storing R2 config for nonexistent channel returns 404."""
    response = await async_client.post(
        "/api/v1/channels/nonexistent/r2-config",
        json={
            "access_key_id": "test_access_key",
            "secret_access_key": "test_secret_key",
            "bucket_name": "test-bucket",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_r2_config_success(
    async_client: AsyncClient, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test retrieving R2 configuration for a channel."""
    from cryptography.fernet import Fernet

    from app.services.credential_service import CredentialService

    fernet_key = Fernet.generate_key().decode()
    monkeypatch.setenv("FERNET_KEY", fernet_key)

    # Create test channel and store credentials
    channel = Channel(channel_id="poke1", channel_name="Test Channel")
    async_session.add(channel)
    await async_session.commit()

    credential_service = CredentialService()
    await credential_service.store_r2_credentials(
        "poke1", "access_key", "secret_key", "test-bucket", async_session
    )

    # Get R2 config via API
    response = await async_client.get("/api/v1/channels/poke1/r2-config")

    assert response.status_code == 200
    data = response.json()
    assert data["channel_id"] == "poke1"
    assert data["bucket_name"] == "test-bucket"
    assert data["has_credentials"] is True
    # Verify secrets are NOT returned
    assert "access_key_id" not in data
    assert "secret_access_key" not in data


@pytest.mark.asyncio
async def test_get_r2_config_not_configured(
    async_client: AsyncClient, async_session: AsyncSession
) -> None:
    """Test retrieving R2 config for channel without R2 returns 404."""
    # Create channel without R2 config
    channel = Channel(channel_id="poke1", channel_name="Test Channel")
    async_session.add(channel)
    await async_session.commit()

    response = await async_client.get("/api/v1/channels/poke1/r2-config")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_r2_config_success(
    async_client: AsyncClient, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test deleting R2 configuration for a channel."""
    from cryptography.fernet import Fernet

    from app.services.credential_service import CredentialService

    fernet_key = Fernet.generate_key().decode()
    monkeypatch.setenv("FERNET_KEY", fernet_key)

    # Create channel and store credentials
    channel = Channel(channel_id="poke1", channel_name="Test Channel")
    async_session.add(channel)
    await async_session.commit()

    credential_service = CredentialService()
    await credential_service.store_r2_credentials(
        "poke1", "access_key", "secret_key", "test-bucket", async_session
    )

    # Delete R2 config via API
    response = await async_client.delete("/api/v1/channels/poke1/r2-config")

    assert response.status_code == 204

    # Verify credentials were cleared by trying to GET config
    # Should return 404 because empty strings mean "not configured"
    get_response = await async_client.get("/api/v1/channels/poke1/r2-config")
    # Note: Empty strings stored as deletion marker should result in 404
    # This verifies the deletion worked (config no longer accessible)
    assert get_response.status_code == 404 or (
        get_response.status_code == 200 and get_response.json()["bucket_name"] == ""
    )


@pytest.mark.asyncio
async def test_delete_r2_config_channel_not_found(async_client: AsyncClient) -> None:
    """Test deleting R2 config for nonexistent channel returns 404."""
    response = await async_client.delete("/api/v1/channels/nonexistent/r2-config")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_test_r2_connection_success(
    async_client: AsyncClient, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test R2 connection test endpoint."""
    from cryptography.fernet import Fernet

    from app.services.credential_service import CredentialService

    fernet_key = Fernet.generate_key().decode()
    monkeypatch.setenv("FERNET_KEY", fernet_key)

    # Create channel and store credentials
    channel = Channel(channel_id="poke1", channel_name="Test Channel")
    async_session.add(channel)
    await async_session.commit()

    credential_service = CredentialService()
    await credential_service.store_r2_credentials(
        "poke1", "access_key", "secret_key", "test-bucket", async_session
    )

    # Test connection via API (will succeed because we just need client creation)
    response = await async_client.post("/api/v1/channels/poke1/r2-config/test")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["bucket_name"] == "test-bucket"


@pytest.mark.asyncio
async def test_test_r2_connection_not_configured(
    async_client: AsyncClient, async_session: AsyncSession
) -> None:
    """Test R2 connection test for channel without R2 returns 404."""
    # Create channel without R2 config
    channel = Channel(channel_id="poke1", channel_name="Test Channel")
    async_session.add(channel)
    await async_session.commit()

    response = await async_client.post("/api/v1/channels/poke1/r2-config/test")

    assert response.status_code == 404
