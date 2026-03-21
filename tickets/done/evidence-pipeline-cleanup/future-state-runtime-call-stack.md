# Future-State Runtime Call Stack

## Ticket: evidence-pipeline-cleanup
## Version: v1
## Date: 2026-03-19

---

## UC-001: SBOM component with empty licenses list — no IndexError

**Type**: Requirement
**Source**: AC-001
**Expected Outcome**: `license` field is absent (None → excluded by `exclude_none=True`); no exception raised.

```
[API layer]
  POST /v1/scan/ingest (payload: cyclonedx SBOM with component.licenses=[])

[EvidenceIngestionService.ingest_scan]
  src/complira_graph/ingestion/service.py:ingest_scan(...)
  → calls self._build_component_docs(raw_components, sbom_format)

[EvidenceIngestionService._build_component_docs]
  src/complira_graph/ingestion/service.py:_build_component_docs(raw, sbom_format)
  for each raw component:
    purl = raw.get("purl") or raw.get("packageUrl") or ...
    name = raw.get("name") or ...
    license = raw.get("license") or (
        raw.get("licenses")[0].get("license", {}).get("id")   # <-- NEVER reached
        if isinstance(raw.get("licenses"), list) and raw.get("licenses")  # <-- [] is falsy → False
        else None
    )
    # license = None ✓ (no IndexError)
    comp = EvidenceComponent(purl=purl, ..., license=None)
    docs.append(comp.model_dump(by_alias=True, exclude_none=True))
    # "license" key absent from dict ✓
  return docs

[Decision gate: `and raw.get("licenses")`]
  licenses = []  →  isinstance([], list) = True  AND  bool([]) = False  →  branch = None
  licenses = None →  isinstance(None, list) = False  →  branch = None (already handled)
  licenses = [{"license":{"id":"MIT"}}] →  isinstance = True  AND  bool([...]) = True  →  index [0] → "MIT"
```

**Coverage**: Primary ✓ | Fallback (None) ✓ | Error (empty list) ✓

---

## UC-002: SBOM component with licenses=None — no IndexError

**Type**: Requirement
**Source**: AC-002
**Expected Outcome**: `license` field is None; no exception.

```
[EvidenceIngestionService._build_component_docs]
  raw.get("licenses") = None
  isinstance(None, list) = False  → else branch → license = None ✓
```

**Coverage**: Primary ✓

---

## UC-003: SBOM component with valid licenses list — correct extraction

**Type**: Requirement
**Source**: AC-003
**Expected Outcome**: `license = "MIT"`.

```
[EvidenceIngestionService._build_component_docs]
  raw.get("licenses") = [{"license": {"id": "MIT"}}]
  isinstance([...], list) = True  AND  bool([...]) = True
  → [0].get("license", {}).get("id") = "MIT"
  license = "MIT" ✓
```

**Coverage**: Primary ✓

---

## UC-004: Dead service file deletion — no import errors

**Type**: Requirement
**Source**: AC-004–AC-007
**Expected Outcome**: All active modules import cleanly after deletion.

```
[Python module import graph — post-deletion]
  api.core.dependencies  (modified: get_enrichment_service + get_compaction_service removed)
    → no longer references api.services.enrichment (deleted)
    → no longer references api.services.compaction (deleted)
  api.v1.endpoints.enrichment  (active endpoint)
    → imports api.services.enrichment_service.EnrichmentService  ✓ (not deleted)
  api.services.control_mapping (deleted)
    → was only called by api.services.compaction (also deleted)
    → no active importer remains

[Test suite import scan]
  pytest collection: no test imports api.services.enrichment (old dead file)
                     no test imports api.services.compaction
                     no test imports api.services.control_mapping (as ControlMappingService)
  → 0 import errors ✓
```

**Coverage**: Primary ✓ | Error path (import fail) ✓ (confirmed by grep: no importers)

---

## UC-005: api/repositories/scan.py deletion — no import errors

**Type**: Requirement
**Source**: AC-008
**Expected Outcome**: After deleting dead services, `scan.py` has zero importers; deletion is safe.

```
[Import chain — post service deletion]
  api.services.enrichment   (deleted) — was only importer via ScanFindingRepository
  api.services.compaction   (deleted) — was only importer via ScanFindingRepository
  api.services.control_mapping (deleted) — conditional import of ScanFindingRepository

  api.repositories.scan — zero active importers after above deletions → safe to delete

[EvidenceIngestionService] (active, `complira_graph.ingestion.service`)
  → uses EvidenceFindingRepository, EvidenceRunRepository (from ingestion/repositories.py)
  → does NOT import api.repositories.scan ✓
```

**Coverage**: Primary ✓

---

## UC-006: api/repositories/component.py deletion — no import errors

**Type**: Requirement
**Source**: AC-009
**Expected Outcome**: ComponentRepository has zero importers; deletion is safe.

```
[Import graph]
  api.repositories.__init__ — empty, no re-exports
  Grep across src/: ComponentRepository → only defined in component.py, never imported
  Grep across tests/: ComponentRepository → not present

  api.repositories.component → zero importers → safe to delete ✓
```

**Coverage**: Primary ✓
