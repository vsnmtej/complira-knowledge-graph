"""
Main API v1 router.

Aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

# Import endpoint routers
# Phase 0
from api.v1.endpoints import scan

# Future phases:
# from api.v1.endpoints import enrich, compact, mapping
# from api.v1.endpoints import blast_radius, epss_velocity, portfolio_risk

# Create main v1 router
api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(scan.router, prefix="/scan", tags=["scan"])

# Future endpoints (Phase 1):
# api_router.include_router(enrich.router, prefix="/enrich", tags=["enrich"])
# api_router.include_router(compact.router, prefix="/compact", tags=["compact"])
# api_router.include_router(mapping.router, prefix="/mapping", tags=["mapping"])

# Future endpoints (Phase 2):
# api_router.include_router(blast_radius.router, prefix="/blast-radius", tags=["blast-radius"])
# api_router.include_router(epss_velocity.router, prefix="/epss-velocity", tags=["epss-velocity"])
# api_router.include_router(portfolio_risk.router, prefix="/portfolio-risk", tags=["portfolio-risk"])
