"""
Centralized graph traversal queries.

Provides DRY, reusable query implementations for:
- Compliance scoring (Path A + Path B)
- Blast radius analysis
- Evidence validation
- Cross-framework mapping
"""

from .compliance import ComplianceQueries

__all__ = ["ComplianceQueries"]
