"""OmniSearch backend application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import get_logger, setup_logging
from app.database.initialization import init_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle events."""
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("Starting %s v%s in %s mode", settings.app_name, settings.app_version, settings.environment)
    init_db(settings.resolved_db_path)
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    """FastAPI application factory."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Local-first, AI-powered multifile search backend API",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # Configure CORS for local frontend communication
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Mount API v1 router
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )

