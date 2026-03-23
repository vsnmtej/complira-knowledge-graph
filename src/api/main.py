"""
FastAPI Application Entry Point.

Creates and configures the FastAPI application with:
- CORS middleware
- Exception handlers
- API versioning (v1 router)
- Health check endpoints
"""

import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import structlog

logger = structlog.get_logger()


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        FastAPI: Configured application instance
    """
    from api.core.config import get_cloud_settings
    settings = get_cloud_settings()

    is_production = os.environ.get("ENVIRONMENT", "development") == "production"

    app = FastAPI(
        title="Complira Knowledge Graph API",
        description="Multi-tenant cybersecurity compliance intelligence platform",
        version="0.1.0",
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
    )

    # GZip compression for responses > 500 bytes
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # Trusted host validation in production
    if is_production:
        allowed_hosts = os.environ.get("ALLOWED_HOSTS", "").split(",")
        if allowed_hosts and allowed_hosts[0]:
            app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    # CORS middleware — always include all localhost dev ports
    cors_origins = list(settings.CORS_ALLOW_ORIGINS)
    for dev_origin in [
        "http://localhost:3000", "http://localhost:3001",
        "http://127.0.0.1:3000", "http://127.0.0.1:3001",
    ]:
        if dev_origin not in cors_origins:
            cors_origins.append(dev_origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # Rate limiting
    if settings.RATE_LIMIT_ENABLED:
        try:
            from slowapi import Limiter, _rate_limit_exceeded_handler
            from slowapi.util import get_remote_address
            from slowapi.errors import RateLimitExceeded

            limiter = Limiter(
                key_func=get_remote_address,
                default_limits=[f"{settings.RATE_LIMIT_REQUESTS_PER_MINUTE}/minute"],
            )
            app.state.limiter = limiter
            app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        except ImportError:
            logger.warning("slowapi not installed, rate limiting disabled")

    # Security headers middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # Exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Catch-all exception handler for unhandled errors."""
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=exc,
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Internal server error",
                "metadata": {
                    "api_version": "v1",
                    "cache_hit": False,
                }
            }
        )

    # Health check endpoint with DB connectivity
    @app.get("/health")
    async def health_check():
        """Health check endpoint for load balancers."""
        health = {"status": "healthy", "version": "0.1.0"}
        try:
            from api.core.database import get_database
            db = get_database()
            db.version()
            health["database"] = "connected"
        except Exception:
            health["database"] = "disconnected"
            health["status"] = "degraded"
        return health

    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "Complira Knowledge Graph API",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/health",
        }

    # Register API v1 router
    from api.v1.router import api_router
    app.include_router(api_router, prefix="/v1")

    logger.info("FastAPI application initialized", version="0.1.0")

    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Development mode
        log_level="info",
    )
