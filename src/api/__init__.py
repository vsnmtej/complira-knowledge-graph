"""
Complira Knowledge Graph Cloud API.

Multi-tenant SaaS REST API for cybersecurity compliance intelligence.

Architecture:
    - FastAPI application with DRY/SOLID principles
    - Multi-tenant database-per-customer
    - Redis caching with per-endpoint TTL
    - API key authentication
    - Independent API and worker scaling
"""

__version__ = "0.1.0"
