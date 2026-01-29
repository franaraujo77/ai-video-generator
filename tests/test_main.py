"""Tests for FastAPI application endpoints.

Tests cover:
- Health check endpoint (/health) - P0 critical for Railway deployment
- Root endpoint (/) - P1 API metadata and discovery
- Response status codes and content validation
- Epic 1: Foundation deployment validation
"""

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from app.main import app


@pytest.fixture
def mock_db_session():
    """Create mock database session for testing endpoints without database."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    return mock_session


@pytest.fixture
def client(mock_db_session) -> TestClient:
    """Create FastAPI test client with mocked database.

    Returns:
        TestClient: Synchronous client for testing FastAPI endpoints.
    """
    # Mock the get_session dependency to avoid database requirement
    from app.database import get_session

    async def mock_get_session():
        yield mock_db_session

    app.dependency_overrides[get_session] = mock_get_session

    yield TestClient(app)

    # Clean up dependency overrides
    app.dependency_overrides.clear()


class TestHealthEndpoint:
    """Tests for /health endpoint (P0 - Critical for deployment)."""

    @pytest.fixture(autouse=True)
    def mock_health_checks(self, monkeypatch):
        """Mock all health check functions to avoid database requirements."""
        from unittest.mock import AsyncMock

        # Mock database connection check
        async def mock_check_db(db):
            return True

        # Mock worker count check
        async def mock_get_workers(db):
            return {"count": 3, "active_timestamp": "2026-01-29T00:00:00Z"}

        # Mock queue depth check
        async def mock_get_queue(db):
            return 0

        # Mock scheduler checks
        def mock_scheduler_running():
            return True

        monkeypatch.setattr("app.main.check_database_connection", mock_check_db)
        monkeypatch.setattr("app.main.get_active_worker_count", mock_get_workers)
        monkeypatch.setattr("app.main.get_queue_depth", mock_get_queue)
        monkeypatch.setattr("app.main.is_scheduler_running", mock_scheduler_running)
        monkeypatch.setattr("app.main.is_cleanup_scheduler_running", mock_scheduler_running)
        monkeypatch.setattr("app.main.is_weekly_metrics_scheduler_running", mock_scheduler_running)

    def test_health_endpoint_returns_200(self, client: TestClient) -> None:
        """[P0] Test health endpoint returns 200 OK status.

        GIVEN: FastAPI application is running
        WHEN: GET request to /health endpoint
        THEN: Returns 200 OK status code
        """
        # WHEN: Requesting health endpoint
        response = client.get("/health")

        # THEN: Returns 200 OK
        assert response.status_code == status.HTTP_200_OK

    def test_health_endpoint_returns_healthy_status(self, client: TestClient) -> None:
        """[P0] Test health endpoint returns healthy status in response body.

        GIVEN: FastAPI application is running
        WHEN: GET request to /health endpoint
        THEN: Response contains status="healthy" or "degraded"
        """
        # WHEN: Requesting health endpoint
        response = client.get("/health")

        # THEN: Response body contains status field
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_health_endpoint_returns_service_name(self, client: TestClient) -> None:
        """[P0] Test health endpoint returns correct service name.

        GIVEN: FastAPI application is running
        WHEN: GET request to /health endpoint
        THEN: Response contains service="ai-video-generator"
        """
        # WHEN: Requesting health endpoint
        response = client.get("/health")

        # THEN: Response contains service name
        data = response.json()
        assert data["service"] == "ai-video-generator"

    def test_health_endpoint_returns_epic_metadata(self, client: TestClient) -> None:
        """[P1] Test health endpoint includes epic metadata.

        GIVEN: FastAPI application is running
        WHEN: GET request to /health endpoint
        THEN: Response contains epic field
        """
        # WHEN: Requesting health endpoint
        response = client.get("/health")

        # THEN: Response includes epic metadata
        data = response.json()
        assert data["epic"] == "epic-8"

    def test_health_endpoint_response_structure(self, client: TestClient) -> None:
        """[P1] Test health endpoint returns all expected fields.

        GIVEN: FastAPI application is running
        WHEN: GET request to /health endpoint
        THEN: Response contains all required fields (status, database, workers, etc.)
        """
        # WHEN: Requesting health endpoint
        response = client.get("/health")

        # THEN: Response has complete structure (Story 8.7 format)
        data = response.json()
        assert "status" in data
        assert "database" in data
        assert "workers" in data
        assert "queue_depth" in data
        assert "schedulers" in data
        assert "service" in data
        assert "epic" in data


class TestRootEndpoint:
    """Tests for / root endpoint (P1 - API discovery)."""

    def test_root_endpoint_returns_200(self, client: TestClient) -> None:
        """[P1] Test root endpoint returns 200 OK status.

        GIVEN: FastAPI application is running
        WHEN: GET request to root endpoint /
        THEN: Returns 200 OK status code
        """
        # WHEN: Requesting root endpoint
        response = client.get("/")

        # THEN: Returns 200 OK
        assert response.status_code == status.HTTP_200_OK

    def test_root_endpoint_returns_service_name(self, client: TestClient) -> None:
        """[P1] Test root endpoint returns service name.

        GIVEN: FastAPI application is running
        WHEN: GET request to root endpoint
        THEN: Response contains full service name
        """
        # WHEN: Requesting root endpoint
        response = client.get("/")

        # THEN: Response contains service name
        data = response.json()
        assert data["service"] == "AI Video Generator - Multi-Channel Orchestration"

    def test_root_endpoint_returns_version(self, client: TestClient) -> None:
        """[P1] Test root endpoint returns API version.

        GIVEN: FastAPI application is running
        WHEN: GET request to root endpoint
        THEN: Response contains version field
        """
        # WHEN: Requesting root endpoint
        response = client.get("/")

        # THEN: Response includes version
        data = response.json()
        assert data["version"] == "0.1.0"

    def test_root_endpoint_returns_epic_status(self, client: TestClient) -> None:
        """[P1] Test root endpoint includes epic and status metadata.

        GIVEN: FastAPI application is running
        WHEN: GET request to root endpoint
        THEN: Response contains epic and deployment status
        """
        # WHEN: Requesting root endpoint
        response = client.get("/")

        # THEN: Response includes epic metadata
        data = response.json()
        assert data["epic"] == "epic-1"
        assert data["status"] == "foundation-deployed"

    def test_root_endpoint_returns_documentation_links(self, client: TestClient) -> None:
        """[P1] Test root endpoint includes API documentation links.

        GIVEN: FastAPI application is running
        WHEN: GET request to root endpoint
        THEN: Response contains links to /docs and /health endpoints
        """
        # WHEN: Requesting root endpoint
        response = client.get("/")

        # THEN: Response includes documentation links
        data = response.json()
        assert data["docs"] == "/docs"
        assert data["health"] == "/health"

    def test_root_endpoint_response_structure(self, client: TestClient) -> None:
        """[P1] Test root endpoint returns all expected fields.

        GIVEN: FastAPI application is running
        WHEN: GET request to root endpoint
        THEN: Response contains all required fields
        """
        # WHEN: Requesting root endpoint
        response = client.get("/")

        # THEN: Response has complete structure
        data = response.json()
        expected_fields = ["service", "version", "epic", "status", "docs", "health"]
        for field in expected_fields:
            assert field in data
        assert len(data) == 6  # Exactly 6 fields
