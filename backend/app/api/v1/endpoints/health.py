"""Health check endpoint definition."""

from fastapi import APIRouter, Depends
from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service Health Check",
    description="Returns the operational status, application name, version, and environment.",
)
async def get_health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Return current service health and metadata."""
    return HealthResponse(
        status="healthy",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )

