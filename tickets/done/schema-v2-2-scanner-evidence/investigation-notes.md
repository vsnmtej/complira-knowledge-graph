# Investigation Notes: Schema v2.2 Scanner Evidence Layer

## Sources Consulted

- `src/complira_graph/db.py` — current schema (38 doc + 40 edge collections)
- `src/complira_graph/models/scan.py` — existing ScanSession/ScanFinding Pydantic models
- `src/complira_graph/models/vex_evidence.py` — VEX evidence models (67KB)
- `src/api/core/database.py` — multi-tenant routing + customer DB schema
- `src/api/parsers/` — SARIF, CycloneDX, Grype parser factory
- `src/api/services/scan.py` — scan ingestion pipeline + VEX generation
- `src/api/repositories/scan.py` — scan data access
- `src/complira_graph/agents/base.py` — base agent with `_ensure_keys()` fix
- `src/complira_graph/utils/keys.py` — `generate_edge_key()` utility
- `scripts/init_phase5_schema.py` — Phase 5 migration script pattern
- `docs/DATABASE_SCHEMA.md`, `docs/GRAPH_ARCHITECTURE.md` — existing docs
- v2.2 schema definition (provided by user in conversation)

## Key Findings

### 1. Two-Database Architecture (Critical Constraint)

The system uses a **reference database** (`complira_graph`) and **customer databases** (`complira_customer_<id>`):

**Reference DB** (shared, read-only intelligence):
- All 38 doc + 40 edge collections from `db.py`
- CVEs, CWEs, ATT&CK, CAPEC, OSCAL, SCF, KEV, EPSS, etc.

**Customer DBs** (isolated per customer):
- `scan_sessions`, `scan_findings`, `customer_components`, `vex_documents`
- `projects`, `repositories`
- Edges: `finding_to_cve`, `component_to_finding`

**Decision needed:** The v2.2 collections (`scan_runs`, `scan_findings`, `detected_controls`, `evidence_packages`) should go in **customer databases** since they contain customer-specific scan data. But the v2.2 schema file assumes a single database. This is the biggest architectural decision.

### 2. Existing Model Overlap

| v2.2 Collection | Existing Equivalent | Location | Gap |
|---|---|---|---|
| `scan_runs` | `scan_sessions` | Customer DB | v2.2 adds: compliance_score, finding_counts, violated_requirements, diff anchoring, tools_invoked |
| `scan_findings` | `scan_findings` | Customer DB | v2.2 adds: fingerprint-based dedup, finding_type enum, cwe_source, semgrep_vuln_category, triage_status, VEX support, firmware fields |
| `detected_controls` | **NEW** | — | Entirely new concept |
| `evidence_packages` | `vex_documents` (partial) | Customer DB | v2.2 is much broader: bundles SBOM+MCP+scan, signing, retention |
| `components` (enriched) | `customer_components` | Customer DB | v2.2 adds: purl_source, firmware_layer, sbom_format, cpe_confidence |

### 3. Edge Architecture Difference

**Current customer DB edges:**
- `finding_to_cve` — scan_findings → vulnerabilities (cross-DB reference)
- `component_to_finding` — customer_components → scan_findings

**v2.2 new edges (8):**
- `component_has_vuln` — components → vulnerabilities
- `finding_maps_to_weakness` — scan_findings → weaknesses
- `finding_triggers_req` — scan_findings → regulatory_requirements
- `detected_control_maps_to` — detected_controls → oscal_controls | scf_controls
- `control_in_component` — detected_controls → components
- `finding_in_component` — scan_findings → components
- `evidence_links_finding` — evidence_packages → scan_findings
- `evidence_for_project` — evidence_packages → projects

**Critical:** Several v2.2 edges cross the customer→reference DB boundary (e.g., `finding_maps_to_weakness` goes from customer `scan_findings` to reference `weaknesses`). ArangoDB doesn't support cross-database edges natively. Current system uses `finding_to_cve` edge in customer DB with `_to` pointing to reference DB document IDs — this works because ArangoDB edges are just documents with `_from`/`_to` string fields.

### 4. Named Graph

- **No named graph exists** in the current system
- All queries use explicit `FOR v, e IN 1..1 OUTBOUND` traversals
- v2.2 defines `GRAPH_EDGE_DEFINITIONS_V2_2` for a named `complira_graph`
- Named graphs are optional in ArangoDB — explicit traversals work fine without them
- **Recommendation:** Skip named graph for now, add later if needed for query optimization

### 5. Schema Validators

- Current `db.py` creates collections **without** JSON Schema validators
- v2.2 defines full JSON Schema validators for all new collections
- ArangoDB supports `schema` parameter on `create_collection()` and `configure()`
- Risk: applying validators to existing collections could reject existing data
- **Recommendation:** Apply validators only to new collections; retrofit existing ones in a follow-up ticket

### 6. Ingestion Pipeline Already Exists

The scan ingestion pipeline (`src/api/services/scan.py` + parsers) already:
- Parses SARIF (Semgrep, CodeQL, Snyk), CycloneDX (SBOMs), Grype (native)
- Normalizes findings to `ParsedFinding` model
- Stores in customer DB `scan_findings`/`scan_sessions`
- Creates cross-DB edges

The v2.2 `INGESTION_NORMALISATION` constants formalize what the parsers already do ad-hoc. These should be centralized.

### 7. Base Agent `_ensure_keys()` Compatibility

The `_ensure_keys()` fix in `base.py` auto-generates deterministic `_key` for edges from `_from`/`_to`. This will work automatically for all new v2.2 edge collections as long as they go through `load_data()`. Customer-DB ingestion uses `ScanIngestionService` which calls ArangoDB directly — it needs its own dedup strategy (fingerprint-based for findings, UUID for scan_runs).

### 8. Tier 1 AQL Templates

The 6 Tier 1 AQL templates in v2.2 are compliance-critical queries:
1. `component_regulatory_blast_radius` — component → CVE → requirement traversal
2. `sast_finding_attack_chain` — finding → CWE → ATT&CK → D3FEND
3. `control_gap_analysis` — violated reqs with no compensating controls
4. `firmware_kev_exposure` — firmware components with KEV CVEs
5. `vex_not_affected_candidates` — auto-derivable VEX candidates
6. `compliance_delta_between_runs` — regression/remediation tracking

These need a home — likely `src/complira_graph/queries/tier1_templates.py`.

## Open Unknowns

1. **Customer vs reference DB placement for v2.2 collections** — Critical architectural decision. The v2.2 schema assumes single-DB but the system is multi-tenant.
2. **Migration strategy for existing `scan_sessions` → `scan_runs`** — Rename? Dual support? Clean break?
3. **Phase 1 ticket overlap** — Phase 1 was about adopting Pydantic models in scan service. V2.2 redefines those models. Need to reconcile or supersede.
4. **Evidence packages vs vex_documents** — Are these the same concept or complementary?

## Scope Triage

**Classification: `Large`**

Rationale:
- **Multi-layer impact:** Schema (db.py) + Models (Pydantic) + Migration script + API service + Repository layer + Queries + Constants
- **Cross-cutting behavior:** Customer DB + reference DB, ingestion pipeline + query layer
- **New public APIs:** Evidence package assembly, control gap analysis queries
- **Schema/storage changes:** 4 new doc collections, 8 new edge collections, schema validators, collection enrichment
- **Architectural decisions:** Customer vs reference DB placement, existing model migration strategy
- Estimated 15-20+ files touched
