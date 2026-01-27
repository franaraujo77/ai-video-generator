"""FastAPI middleware for correlation ID propagation.

This middleware:
- Generates UUID4 correlation_id for each request (if not provided)
- Extracts correlation_id from X-Correlation-ID request header
- Binds correlation_id to async context for automatic propagation
- Adds X-Correlation-ID to response headers for client tracing

Usage:
    from app.middleware.correlation import CorrelationMiddleware

    app.add_middleware(CorrelationMiddleware)

Story: 8.1 - Structured Logging with Correlation IDs (Task 3, AC: 4)
"""

import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.context import clear_correlation_context, set_correlation_id


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware for correlation ID generation and propagation.

    Automatically generates or extracts correlation IDs for distributed tracing
    across FastAPI requests. Binds correlation_id to async context so it's
    available to all downstream code without manual parameter passing.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and inject correlation ID.

        Args:
            request: FastAPI request object
            call_next: Next middleware or endpoint handler

        Returns:
            Response with X-Correlation-ID header added
        """
        # Step 1: Extract correlation_id from header or generate new UUID4
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

        # Step 2: Bind to async context (automatically propagates to all async calls)
        set_correlation_id(correlation_id)

        try:
            # Step 3: Process request (correlation_id is now in context)
            response = await call_next(request)

            # Step 4: Add correlation_id to response headers for client tracing
            response.headers["X-Correlation-ID"] = correlation_id

            return response
        finally:
            # Step 5: Clear context after request (good hygiene)
            # Note: ContextVar is request-scoped, but explicit clear prevents leakage
            clear_correlation_context()
