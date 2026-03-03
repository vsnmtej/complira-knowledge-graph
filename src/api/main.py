"""
FastAPI Application Entry Point.

Creates and configures the FastAPI application with:
- CORS middleware
- Exception handlers
- API versioning (v1 router)
- Health check endpoints
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import structlog

logger = structlog.get_logger()


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        FastAPI: Configured application instance
    """
    app = FastAPI(
        title="Complira Knowledge Graph API",
        description="Multi-tenant cybersecurity compliance intelligence platform",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware (configure allowed origins based on environment)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint for load balancers."""
        return {
            "status": "healthy",
            "version": "0.1.0",
        }

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
