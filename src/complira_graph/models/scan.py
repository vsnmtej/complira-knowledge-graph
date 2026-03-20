"""
Legacy scan models — removed in v2.2.

ScanSession and ScanFinding have been replaced by the v2.2 evidence layer models:
  - ScanRun       (src/complira_graph/models/evidence.py)
  - V22Finding    (src/complira_graph/models/evidence.py)

This file is retained only because api/repositories/scan.py still references
these classes. That repository is pending deletion (T-DEL-002) once
api/services/enrichment.py and api/services/compaction.py are migrated.
"""
