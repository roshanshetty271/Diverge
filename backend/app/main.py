"""Diverge API — FastAPI application entry point.

Kiro audit fixes applied:
- #11.2: Runtime safety check warns if debug=True in production (Lambda)
- #15.1: API versioning with /api/v1/ prefix
- #8: CORS credentials disabled (JWT uses Authorization header, not cookies)
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes.debate import router as debate_router
from app.routes.general import router as general_router
from app.routes.tts import router as tts_router
from app.security.middleware import (
    SecurityHeadersMiddleware,
    RequestTrackingMiddleware,
    RequestSizeLimitMiddleware,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("diverge")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    settings = get_settings()
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Debate model: {settings.debate_model_id}")
    logger.info(f"Region: {settings.aws_region}")

    # Kiro audit #11.2: Warn loudly if debug is enabled in Lambda (production)
    if settings.debug and os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        logger.critical(
            "⚠️  DEBUG MODE IS ON IN LAMBDA! API docs are publicly exposed. "
            "Set DIVERGE_DEBUG=false in your Lambda environment variables."
        )

    yield
    logger.info("Shutting down Diverge API")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    docs_url = "/api/docs" if settings.debug else None
    redoc_url = "/api/redoc" if settings.debug else None

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Decision intelligence engine — two AI versions of your future self debate your biggest decision.",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url="/api/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # Security middleware (LIFO order: last added = first executed)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestTrackingMiddleware)

    # CORS
    # Kiro audit #8: allow_credentials=False because we use Authorization header (not cookies).
    # JWT in Authorization header is NOT automatically sent by browsers → no CSRF risk.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_all_cors_origins() if not settings.debug else ["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=3600,
    )

    # Register routers
    app.include_router(debate_router)
    app.include_router(general_router)
    app.include_router(tts_router)

    return app


app = create_app()