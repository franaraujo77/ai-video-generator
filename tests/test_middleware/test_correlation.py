"""Tests for FastAPI correlation ID middleware.

Tests middleware to ensure:
- Generates UUID4 correlation_id when not provided in header
- Extracts correlation_id from X-Correlation-ID request header
- Binds correlation_id to async context during request
- Adds X-Correlation-ID to response headers
- Context is isolated per request

Story: 8.1 - Structured Logging with Correlation IDs (Task 3)
"""

from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.correlation import CorrelationMiddleware
from app.utils.context import get_correlation_id


# Test FastAPI app
app = FastAPI()
app.add_middleware(CorrelationMiddleware)


@app.get("/test")
async def test_endpoint(request: Request):
    """Test endpoint that returns correlation_id from context."""
    correlation_id = get_correlation_id()
    return {"correlation_id": correlation_id}


client = TestClient(app)


class TestCorrelationMiddleware:
    """Test correlation ID middleware for FastAPI."""

    def test_generates_correlation_id_when_no_header(self):
        """Test middleware generates UUID4 correlation_id when no header provided."""
        # WHEN we make a request without X-Correlation-ID header
        response = client.get("/test")

        # THEN response has X-Correlation-ID header
        assert "X-Correlation-ID" in response.headers

        # AND it's a valid UUID4
        correlation_id = response.headers["X-Correlation-ID"]
        uuid_obj = UUID(correlation_id)  # Will raise if invalid
        assert uuid_obj.version == 4

    def test_extracts_correlation_id_from_header(self):
        """Test middleware extracts correlation_id from X-Correlation-ID header."""
        # GIVEN a correlation_id in request header
        test_id = "12345678-1234-5678-1234-567812345678"

        # WHEN we make a request with X-Correlation-ID header
        response = client.get("/test", headers={"X-Correlation-ID": test_id})

        # THEN response has the same correlation_id
        assert response.headers["X-Correlation-ID"] == test_id

        # AND the endpoint receives it from context
        assert response.json()["correlation_id"] == test_id

    def test_correlation_id_in_response_header(self):
        """Test middleware adds X-Correlation-ID to response headers."""
        # WHEN we make a request
        response = client.get("/test")

        # THEN response has X-Correlation-ID header
        assert "X-Correlation-ID" in response.headers

        # AND it's not empty
        correlation_id = response.headers["X-Correlation-ID"]
        assert correlation_id is not None
        assert len(correlation_id) > 0

    def test_correlation_id_bound_to_async_context(self):
        """Test middleware binds correlation_id to async context for request."""
        # GIVEN a specific correlation_id
        test_id = "87654321-4321-8765-4321-876543218765"

        # WHEN we make a request with that correlation_id
        response = client.get("/test", headers={"X-Correlation-ID": test_id})

        # THEN the endpoint can retrieve it from context
        assert response.json()["correlation_id"] == test_id

    def test_generated_correlation_id_matches_response_header(self):
        """Test generated correlation_id is same in context and response header."""
        # WHEN we make a request without correlation_id header
        response = client.get("/test")

        # THEN correlation_id in response header matches what endpoint received
        header_id = response.headers["X-Correlation-ID"]
        context_id = response.json()["correlation_id"]

        assert header_id == context_id

    def test_multiple_requests_get_different_correlation_ids(self):
        """Test each request gets its own correlation_id (context isolation)."""
        # WHEN we make two requests
        response1 = client.get("/test")
        response2 = client.get("/test")

        # THEN they have different correlation_ids
        id1 = response1.headers["X-Correlation-ID"]
        id2 = response2.headers["X-Correlation-ID"]

        assert id1 != id2

    def test_correlation_id_accepts_non_uuid_strings(self):
        """Test middleware accepts any string as correlation_id (for flexibility)."""
        # GIVEN a non-UUID correlation_id
        custom_id = "custom-trace-id-12345"

        # WHEN we make a request with custom correlation_id
        response = client.get("/test", headers={"X-Correlation-ID": custom_id})

        # THEN it's accepted and propagated
        assert response.headers["X-Correlation-ID"] == custom_id
        assert response.json()["correlation_id"] == custom_id
