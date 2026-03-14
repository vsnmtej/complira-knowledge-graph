"""
Main API v1 router.

Aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

# Import endpoint routers
# Phase 0
from api.v1.endpoints import scan
from api.v1.endpoints import reference
from api.v1.endpoints import meta
from api.v1.endpoints import vex
from api.v1.endpoints import account
from api.v1.endpoints import projects
from api.v1.endpoints import repositories

# Phase 1: LLM-powered enrichment (enabled)
from api.v1.endpoints import enrichment

# Phase 2+: Temporarily disabled until models are implemented
# from api.v1.endpoints import enrich

# Future phases:
# from api.v1.endpoints import blast_radius, epss_velocity, portfolio_risk

# Create main v1 router
api_router = APIRouter()

# Include all endpoint routers
# Phase 0: Scan Ingestion
api_router.include_router(scan.router, prefix="/scan", tags=["scan"])

# Phase 0: VEX Management (auth required)
api_router.include_router(vex.router, prefix="/vex", tags=["vex"])

# Phase 0: Reference Data (auth required)
api_router.include_router(reference.router, prefix="/reference", tags=["reference"])

# Phase 0: Metadata and Data Quality (auth required)
api_router.include_router(meta.router, prefix="/meta", tags=["metadata"])

# Phase 0: Account Management (auth required)
api_router.include_router(account.router, prefix="/account", tags=["account"])

# Phase 0: Project & Repository Management (auth required)
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(repositories.router, prefix="/repositories", tags=["repositories"])

# Phase 1: LLM-powered enrichment (enabled)
api_router.include_router(enrichment.router, prefix="", tags=["enrichment"])

# Phase 2+: Enrichment Pipeline (temporarily disabled)
# (scan session-based enrichment will be re-added in Phase 2)

# Phase 3A-B: Regulatory Trigger Service (temporarily disabled)
# api_router.include_router(enrich.router, prefix="", tags=["regulatory-triggers"])

# Future endpoints (Phase 3+):
# api_router.include_router(blast_radius.router, prefix="/blast-radius", tags=["blast-radius"])
# api_router.include_router(epss_velocity.router, prefix="/epss-velocity", tags=["epss-velocity"])
# api_router.include_router(portfolio_risk.router, prefix="/portfolio-risk", tags=["portfolio-risk"])
