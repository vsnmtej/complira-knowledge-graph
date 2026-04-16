"""
Main API v1 router.

Aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

# Import endpoint routers
# Phase 0
from api.v1.endpoints import scan

# Phase 2: Enrichment Pipeline
from api.v1.endpoints import enrichment

# Future phases:
# from api.v1.endpoints import blast_radius, epss_velocity, portfolio_risk

# Create main v1 router
api_router = APIRouter()

# Include all endpoint routers
# Phase 0: Scan Ingestion
api_router.include_router(scan.router, prefix="/scan", tags=["scan"])

# Phase 2: Enrichment Pipeline
api_router.include_router(enrichment.router, prefix="", tags=["enrichment"])

# Future endpoints (Phase 3+):
# api_router.include_router(blast_radius.router, prefix="/blast-radius", tags=["blast-radius"])
# api_router.include_router(epss_velocity.router, prefix="/epss-velocity", tags=["epss-velocity"])
# api_router.include_router(portfolio_risk.router, prefix="/portfolio-risk", tags=["portfolio-risk"])
