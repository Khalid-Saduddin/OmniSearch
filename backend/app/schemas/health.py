"""Health check schemas."""

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Structured response schema for service health status."""

    status: str = Field(..., description="Service status indicator, e.g. 'healthy'")
    app_name: str = Field(..., description="Name of the backend application")
    version: str = Field(..., description="Application semantic version")
    environment: str = Field(..., description="Current running environment")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the health check response",
    )
