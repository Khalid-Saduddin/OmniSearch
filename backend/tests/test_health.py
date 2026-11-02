"""Tests for health check endpoint."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint_returns_success(async_client: AsyncClient) -> None:
    """Verify that GET /api/v1/health returns 200 OK with expected schema keys."""
    response = await async_client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert data["app_name"] == "OmniSearch Backend"
    assert "version" in data
    assert "environment" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_endpoint_schema_structure(async_client: AsyncClient) -> None:
    """Verify that the payload matches the HealthResponse schema field types."""
    response = await async_client.get("/api/v1/health")
    data = response.json()

    assert isinstance(data["status"], str)
    assert isinstance(data["app_name"], str)
    assert isinstance(data["version"], str)
    assert isinstance(data["environment"], str)
    assert isinstance(data["timestamp"], str)
