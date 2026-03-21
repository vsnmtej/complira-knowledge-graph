# Implementation Progress: Core Pipeline Phase 1 — Stage 6

**Ticket:** `core-pipeline-phase-1`
**Stage:** 6 (Implementation)
**Started:** 2026-03-21
**Completed:** 2026-03-21
**Author:** Claude Code (claude-sonnet-4-6)

---

## Progress Tracker

| # | File | Status | Notes |
|---|------|--------|-------|
| 1 | `scan_enrichment_repository.py` | DONE | All AQL, bulk writes, status transitions |
| 2 | `enrichment_pipeline.py` | DONE | UC-007: CVE enrichment, edge creation |
| 3 | `compaction_pipeline.py` | DONE | UC-008: Risk scoring, compaction groups, cluster ranks |
| 4 | `control_mapping_pipeline.py` | DONE | UC-009: Framework coverage computation |
| 5 | `pipeline_coordinator.py` | DONE | Orchestration, error handling, idempotency |
| 6 | `endpoints/pipeline.py` | DONE | POST /v1/scans/{scan_run_id}/enrich (202) |
| 7 | `endpoints/scan.py` (modify) | DONE | BackgroundTask trigger added after ingest_scan |
| 8 | `router.py` (modify) | DONE | Pipeline router registered |
| 9 | `ingestion/__init__.py` (modify) | DONE | All new pipeline classes exported |
| 10 | `test_scan_enrichment_repository.py` | DONE | 29 tests — chunking, status updates, upserts, pagination |
| 11 | `test_enrichment_pipeline.py` | DONE | 22 tests — normalize_cve_key, build_updates, detected_controls, edges |
| 12 | `test_compaction_pipeline.py` | DONE | 26 tests — risk_score formula, groups, ranks, integration |
| 13 | `test_control_mapping_pipeline.py` | DONE | 13 tests — coverage (zero/single/multi-framework) |

**Total: 95/95 unit tests pass**

---

## Log

- 2026-03-21: Implementation plan written. Context files read. Started bottom-up implementation.
- 2026-03-21: All source files written (scan_enrichment_repository, enrichment_pipeline, compaction_pipeline, control_mapping_pipeline, pipeline_coordinator, endpoints/pipeline).
- 2026-03-21: scan.py modified to add BackgroundTask trigger; router.py updated; __init__.py updated.
- 2026-03-21: All 4 unit test files written.
- 2026-03-21: Fixed pyproject.toml filterwarnings to suppress macOS LibreSSL/urllib3 warning (pre-existing env issue affecting all ingestion tests).
- 2026-03-21: Fixed test_compaction_pipeline.py helper to correctly handle cwe_chain=[] (empty list).
- 2026-03-21: **95/95 tests pass — stage complete.**

---

## Key Decisions Made During Implementation

1. `ScanEnrichmentRepository.aql_enrich_batch` renamed from `aql_enrich_findings_batch` in design — both names accepted (alias).
2. `bulk_upsert_detected_controls` is an alias of `upsert_detected_controls` for call-stack doc compatibility.
3. `EnrichmentPipeline._build_detected_controls` takes `scan_run_id` as first param (not in pipeline classes as per design) — follows call stack doc.
4. `CompactionPipeline._cluster_and_rank` alias added pointing to `_compute_cluster_ranks` for test compatibility.
5. pyproject.toml `filterwarnings` updated: `"ignore:urllib3 v2 only supports OpenSSL"` added AFTER `"error"` so it has higher priority (Python warning filters: last inserted = highest priority). This resolves a pre-existing test infrastructure issue on macOS Python 3.9 + LibreSSL.
6. `tests/unit/ingestion/conftest.py` created with additional early warning suppression.
7. `tests/conftest.py` updated with early `warnings.filterwarnings` call for the same reason.
