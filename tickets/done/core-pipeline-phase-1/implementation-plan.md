# Implementation Plan: Core Pipeline Phase 1 — Stage 6

**Ticket:** `core-pipeline-phase-1`
**Stage:** 6 (Implementation)
**Author:** Claude Code (claude-sonnet-4-6)
**Date:** 2026-03-21

---

## Objective

Implement the three-stage post-ingestion intelligence pipeline as specified in
`proposed-design.md`. Pipeline runs as a FastAPI BackgroundTask after scan ingestion
completes, advancing scan_run status through `completed → enriched → compacted → mapped`.

---

## Build Order (Bottom-Up)

| # | File | Type | Purpose |
|---|------|------|---------|
| 1 | `src/complira_graph/ingestion/scan_enrichment_repository.py` | New | Data-access layer for all pipeline reads/writes |
| 2 | `src/complira_graph/ingestion/enrichment_pipeline.py` | New | UC-007: CVE enrichment, edge creation, EPSS/KEV writes |
| 3 | `src/complira_graph/ingestion/compaction_pipeline.py` | New | UC-008: Risk scoring, CWE grouping, cluster ranking |
| 4 | `src/complira_graph/ingestion/control_mapping_pipeline.py` | New | UC-009: Framework coverage computation |
| 5 | `src/complira_graph/ingestion/pipeline_coordinator.py` | New | Orchestrates three stages; error/idempotency handling |
| 6 | `src/api/v1/endpoints/pipeline.py` | New | POST /v1/scans/{scan_run_id}/enrich (202 manual trigger) |
| 7 | `src/api/v1/endpoints/scan.py` | Modify | Add BackgroundTask trigger after ingest_scan |
| 8 | `src/api/v1/router.py` | Modify | Register pipeline router |
| 9 | `src/complira_graph/ingestion/__init__.py` | Modify | Export new pipeline classes |
| 10 | `tests/unit/ingestion/test_scan_enrichment_repository.py` | New | Test bulk_update_findings chunking |
| 11 | `tests/unit/ingestion/test_enrichment_pipeline.py` | New | Test _build_finding_update, _normalize_cve_key, _build_detected_controls |
| 12 | `tests/unit/ingestion/test_compaction_pipeline.py` | New | Test _compute_risk_score, _assign_compaction_groups, _cluster_and_rank |
| 13 | `tests/unit/ingestion/test_control_mapping_pipeline.py` | New | Test _compute_coverage (zero, single, multi-framework) |

---

## Key Design Decisions

### AQL Strategy
- All AQL lives in `ScanEnrichmentRepository` — pipelines contain zero AQL.
- Single round-trip per batch for enrichment traversal (`aql_enrich_findings_batch`).
- Bulk UPDATE by `_key` for all write-back operations.
- All reads include `FILTER tenant_id == @tenant_id` for multi-tenancy.

### Idempotency
- All writes use `import_bulk(on_duplicate="update")` or AQL `UPDATE ... IN`.
- Re-triggering from any retriable status re-runs the full pipeline idempotently.
- Retriable statuses: `{completed, enriched, compacted, pipeline_failed, enrichment_pending}`.

### Error Handling
- PipelineCoordinator wraps each stage in try/except.
- Stage failure → `status="pipeline_failed"` with error message.
- Reference DB unavailable → `status="enrichment_pending"`.
- No rollback — partial writes are idempotent on retry.

### Batch Contract
- `fetch_findings_for_run` yields ≤500 findings per iteration.
- `bulk_update_findings` chunks writes at 500 per AQL call.
- CompactionPipeline accumulates ALL findings before computing ranks (needs global view).

### Risk Score Formula
```
risk_score = (cvss_base/10)*0.4 + epss_score*0.3 + (1.0 if in_kev else 0)*0.2 + (0.1 if d3fend_techniques else 0)*0.1
```

---

## Status Chain

```
running → completed → enriched → compacted → mapped
                         ↘                     ↗
                    pipeline_failed (retriable)
                    enrichment_pending (retriable)
```

---

## Dependencies

- `arango.database.StandardDatabase` — all DB access
- `complira_graph.utils.keys.generate_edge_key` — deterministic edge keys
- `complira_graph.utils.keys.normalize_cve_id` — CVE ID normalization
- `complira_graph.ingestion.repositories.EvidenceRunRepository` — reused for status checks
- `structlog` / stdlib `logging` — following existing ingestion pattern (stdlib logging)
- FastAPI `BackgroundTasks` — async background execution

---

## Test Strategy

- All unit tests use `unittest.mock.MagicMock` for DB (no live ArangoDB required).
- Pure-function helpers (risk score, group assignment, coverage) are tested with plain dicts.
- Repository tests verify chunking behaviour by counting AQL execute calls.
- No integration tests in this stage (scope = unit only).
