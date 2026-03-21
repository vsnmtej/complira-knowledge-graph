# Requirements: Schema v2.2 — Scanner Evidence Ingestion Layer

**Status:** `Draft`
**Scope Triage:** TBD (expected `Medium` or `Large`)
**Branch:** codex/schema-v2-2-scanner-evidence

---

## Goal / Problem Statement

Integrate the `complira_kg_schema_v2_2.py` scanner evidence ingestion layer into the production codebase. This adds the ability to ingest scanner output (SAST, secrets, DAST, SCA, firmware findings), track scan pipeline runs, detect positive security controls, and produce regulatory evidence packages — all modeled as graph nodes and edges in ArangoDB with full compliance traversal capability.

The v2.2 schema extends the existing v2.1 graph (38 doc + 40 edge collections, just validated) with:
- 4 new document collections: `scan_runs`, `scan_findings`, `detected_controls`, `evidence_packages`
- 8 new edge collections linking findings/controls/evidence to the existing knowledge graph
- Schema validators (JSON Schema) on all new collections
- Activation of 4 previously-empty edge collections with full schemas
- Enrichment of the existing `components` collection with SBOM fields
- 6 Tier 1 AQL query templates for compliance-critical traversals
- Ingestion normalisation constants for scanner data mapping

## In-Scope Use Cases

| ID | Use Case | Description |
| --- | --- | --- |
| UC-001 | Schema migration | Apply v2.2 collections, edges, indexes, and validators to existing DB without breaking v2.1 data |
| UC-002 | Scanner finding ingestion | Ingest SAST/secrets/DAST/SCA/firmware findings into `scan_findings` with deterministic dedup via fingerprint |
| UC-003 | SBOM component ingestion | Ingest CycloneDX/SPDX SBOM components into enriched `components` collection with purl-based dedup |
| UC-004 | Scan run lifecycle | Create/update `scan_runs` tracking pipeline execution metadata, finding counts, compliance snapshots |
| UC-005 | Detected control ingestion | Ingest positive security control detections and map them to OSCAL/SCF controls |
| UC-006 | Evidence package assembly | Create evidence packages linking scan runs, findings, and projects for regulatory submission |
| UC-007 | Component-to-vulnerability linking | Create `component_has_vuln` edges via CPE match and/or direct scanner report |
| UC-008 | Finding-to-CWE-to-ATT&CK traversal | Finding → CWE → ATT&CK → D3FEND traversal via new `finding_maps_to_weakness` edges |
| UC-009 | Compliance gap analysis | Identify violated requirements with no compensating detected controls |
| UC-010 | Compliance delta between runs | Compare requirements violated between two scan runs for regression/remediation tracking |
| UC-011 | VEX not_affected derivation | Identify components with CVE exposure but no matching SAST finding for CWE — VEX candidates |
| UC-012 | Idempotent re-ingestion | Re-running ingestion produces updates not duplicates (leverages base agent `_ensure_keys()`) |

## Acceptance Criteria

| AC ID | Requirement | Measurable Expected Outcome |
| --- | --- | --- |
| AC-001 | v2.2 migration is idempotent | Running migration script twice produces no errors, no duplicate collections, correct collection counts |
| AC-002 | Existing v2.1 data is preserved | All 38+40 existing collections retain their document counts and indexes after migration |
| AC-003 | Schema validators enforce data quality | Inserting a `scan_findings` doc missing required fields (`fingerprint`, `tool`, `severity`) raises validation error |
| AC-004 | New indexes are created | All v2.2 index definitions are present in DB after migration |
| AC-005 | `scan_findings` dedup by fingerprint | Inserting two findings with same fingerprint results in update, not duplicate |
| AC-006 | `components` enriched with SBOM fields | Components support `purl_source`, `sbom_format`, `firmware_layer`, `scan_run_id` fields |
| AC-007 | Tier 1 AQL queries execute | All 6 Tier 1 AQL templates execute without syntax errors against the migrated schema |
| AC-008 | Edge integrity maintained | All new edge `_from`/`_to` references point to valid existing collections |
| AC-009 | Pydantic models validate | New Pydantic models for `scan_runs`, `scan_findings`, `detected_controls`, `evidence_packages` pass unit tests |
| AC-010 | Named graph updated | `complira_graph` named graph includes all v2.2 edge definitions |
| AC-011 | Ingestion normalisation works | Semgrep severity mapping, CWE extraction, CVE validation produce correct outputs |
| AC-012 | Deterministic edge keys | New edge collections generate deterministic `_key` from `_from`/`_to` via `generate_edge_key()` |

## Constraints / Dependencies

- Must not break existing 705-passing test suite
- Must integrate with the base agent `_ensure_keys()` fix for idempotent edges
- ArangoDB schema validators require python-arango >= 7.x
- The v2.2 schema file is a standalone migration script — need to decide integration strategy (merge into `db.py` vs keep separate)
- INGESTION_NORMALISATION constants need a home accessible to future ingestion agents
- Must work with both reference DB (`complira_graph`) and customer DBs

## Assumptions

- ArangoDB 3.11+ is the target (supports JSON Schema validators)
- The `complira_kg_schema_v2_2.py` file is the authoritative source of truth for v2.2 schema additions
- Existing v2.1 collections/indexes should not be modified by v2.2 migration
- Scanner ingestion agents will be built in a follow-up ticket (this ticket focuses on schema + models + migration)

## Open Questions / Risks

1. **Integration strategy**: Merge v2.2 into `db.py` lists vs keep as separate migration file? Trade-offs: single source of truth vs migration history.
2. **Schema validators**: Apply to existing collections too, or only new ones? Risk of rejecting existing data that doesn't conform.
3. **Multi-tenant**: Do `scan_runs`/`scan_findings`/`detected_controls`/`evidence_packages` go in the reference DB or customer DBs?
4. **Named graph**: Do we need the `complira_graph` named graph, or are edge-collection-only traversals sufficient?
5. **Component overlap**: `scan_findings` model exists in `src/complira_graph/models/scan.py` — how does it relate to the v2.2 `scan_findings` schema?
