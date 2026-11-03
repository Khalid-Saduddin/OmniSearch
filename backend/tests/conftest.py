"""Pytest fixtures for backend tests."""

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import create_app


@pytest.fixture
def app():
    """Create a fresh FastAPI test application instance."""
    return create_app()


@pytest.fixture
async def async_client(app):
    """Provide an asynchronous HTTP client bound to the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

