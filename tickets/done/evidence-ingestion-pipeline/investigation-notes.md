# Investigation Notes: Evidence Data Ingestion Pipeline

## Sources Consulted

- `src/api/services/scan.py` — existing `ScanIngestionService` (customer DB writer)
- `src/api/parsers/base.py` — `ParsedFinding`, `ParsedScanData` models + `IScanParser` / `BaseScanParser`
- `src/api/parsers/factory.py` — `ParserFactory.get_parser()` dispatch
- `src/api/parsers/sarif.py`, `cyclonedx.py`, `grype_analyzer.py` — concrete parsers
- `src/api/repositories/scan.py` — `ScanSessionRepository`, `ScanFindingRepository`, `ScanEdgeRepository`
- `src/api/repositories/component.py` — `ComponentRepository` (customer DB)
- `src/api/v1/endpoints/scan.py` — `POST /v1/scan/ingest` endpoint
- `src/api/core/database.py` — `get_reference_db()`, `get_customer_db()` routing
- `src/complira_graph/models/scan.py` — `ScanSession`, `ScanFinding` Pydantic models (customer DB)
- `src/complira_graph/agents/base.py` — `BaseAgent`, `_ensure_keys()`, `load_data()`
- `src/complira_graph/utils/keys.py` — `generate_edge_key()`, `normalize_purl()`, `normalize_cwe_id()`
- `src/complira_graph/schema/complira_kg_schema_v2_2.py` — `DB_PLACEMENT`, `LEGACY_COLLECTION_MAP`, `FIELD_MAP`, `INGESTION_NORMALISATION`, `SCHEMA_VERSION`
- `src/complira_graph/db.py` — 42 doc + 49 edge collection definitions, indexes

---

## Key Findings

### 1. Two Ingestion Systems Currently Co-Exist (Critical Architecture Decision)

**Existing system (`ScanIngestionService`)**:
- Writes `scan_sessions`, `scan_findings`, `customer_components` → **customer DB** (`complira_customer_<id>`)
- Uses `customer_id` field throughout
- Creates edges: `finding_to_cve`, `component_to_finding` → customer DB
- Called from `POST /v1/scan/ingest` endpoint
- Creates `customer_db = get_customer_db(customer_id)` at ingest time

**v2.2 target system (to be built)**:
- Writes `scan_runs`, `scan_findings`, `detected_controls`, `evidence_packages`, `components` → **reference DB** (`complira_graph`)
- Must use `tenant_id` field (not `customer_id`) — per `FIELD_MAP`
- Creates 9 new edge collections in reference DB
- `DB_PLACEMENT` confirms: all v2.2 evidence collections → reference DB

**Resolution**: The v2.2 pipeline is a **clean replacement** of `ScanIngestionService`. Per Core Modernization Policy (no backward compat), the new `EvidenceIngestionService` replaces the old service. The API endpoint `POST /v1/scan/ingest` will be updated to call the new service.

---

### 2. `ParsedFinding` Model Is Insufficient for v2.2

Current `ParsedFinding` fields: `cve_id`, `severity`, `description`, `location`, `tool_name`, `scan_type`, `raw_data`

v2.2 `scan_findings` collection requires: `fingerprint`, `finding_type`, `cwe_ids`, `rule_id`, `semgrep_vuln_category`, `triage_status`, `tenant_id`, `scan_run_id`

**Decision**: `ParsedFinding` is a **parser output model** — adding v2.2 fields to it conflates parsing with evidence modeling. Instead:
- Keep `ParsedFinding` as-is (parser output)
- Introduce `V22FindingRecord` Pydantic model (ingestion-layer adapter output) that maps `ParsedFinding` + enrichment to v2.2 `scan_findings` schema
- `INGESTION_NORMALISATION` constants drive the `ParsedFinding → V22FindingRecord` transformation

---

### 3. Fingerprint Dedup Strategy

v2.2 deduplication is fingerprint-based for `scan_findings`. `INGESTION_NORMALISATION` defines:
- `semgrep_fingerprint_fields: ["rule_id", "file_path", "line_number"]`

Fingerprint must be deterministic: `hashlib.sha256(f"{rule_id}:{file_path}:{line_number}".encode()).hexdigest()[:32]`

For SCA findings (CVE-based): fingerprint = `hashlib.sha256(f"{cve_id}:{purl}".encode()).hexdigest()[:32]`

The `_key` for `scan_findings` should be the fingerprint itself (enables `on_duplicate="update"` idempotency).

---

### 4. Components Are Global (purl-keyed, No `tenant_id`)

`DB_PLACEMENT["components"] = "reference"` and they are global (Fix 1 in v2.2.1 schema). The component `_key = normalize_purl(purl)`. `tenant_id` is **not** on component documents — it goes on the `project_uses_component` edge instead.

**Implication**: SBOM ingestion must:
1. Upsert component into global `components` collection with `on_duplicate="update"`
2. Create `project_uses_component` edge (`_from=projects/<project_id>`, `_to=components/<purl_key>`) with `tenant_id`

---

### 5. Edge Cross-Reference Pattern (All Intra-Reference-DB)

After Fix 1 (global components in reference DB), all 9 new v2.2 edges are intra-reference-DB. ArangoDB cross-DB edge limitation does not apply.

Edge `_key` generation: `generate_edge_key(from_key, to_key)` from `complira_graph/utils/keys.py`. For edges like `finding_maps_to_weakness` where the from-key is a fingerprint hash and the to-key is a CWE key, the combined string will be short enough to not need hashing.

---

### 6. Reference Lookup Strategy for Edges

**`finding_maps_to_weakness`**: CWE IDs extracted by `re.findall(INGESTION_NORMALISATION["cwe_extract_pattern"], rule_id_or_metadata)`. CWE key = `normalize_cwe_id("CWE-79")` = `"CWE_79"`. Need to verify CWE doc exists in reference DB before creating edge (or tolerate dangling edges — ArangoDB allows them but they won't traverse).

**`finding_triggers_req`**: Requires a CWE → regulatory_requirement lookup in reference DB. The reference DB should have `cwe_to_req` or equivalent traversal path. This is the most complex edge — needs an AQL query against reference DB to resolve CWE → requirement mapping.

**`component_has_vuln`**: CVE key = `normalize_cve_id(cve_id)` = `"CVE_2024_12345"`. Vulnerability must exist in reference DB `vulnerabilities` collection (seeded by NVD agent).

**`detected_control_maps_to`**: Requires OSCAL control ID or SCF control ID — needs AQL lookup to resolve control reference.

---

### 7. Existing `get_reference_db()` Is Available

`src/api/core/database.py` already exports `get_reference_db()` used by `VEXEvidenceService`. The v2.2 ingestion service can use the same function. No new DB connection infrastructure needed.

---

### 8. Detected Controls — Source Is Not Yet Clear

The v2.2 schema defines `detected_controls` for positive security control detections. Current scanners (Semgrep, Grype, CycloneDX) do not emit positive control detection data. This collection is likely populated by:
- Future scanner integrations (tfsec, checkov, OSCAL assessment tools)
- Or manually configured rules

**Scope decision**: Implement the `detected_controls` ingestion model and edge creation skeleton, but leave the scanner-to-detected-control normalisation as a stub for now (no current parser emits this data).

---

### 9. Backfill Strategy

`LEGACY_COLLECTION_MAP = {"scan_sessions": "scan_runs", "customer_components": "components"}`
`FIELD_MAP = {"customer_id": "tenant_id"}`

Backfill reads from each customer DB, applies field mapping, writes to reference DB. This is a one-time administrative migration, not a runtime ingestion path.

The backfill adapter needs access to all customer DB instances — use the existing customer DB discovery pattern from `api/core/database.py`.

---

### 10. `ScanIngestRequest` vs v2.2

The existing `ScanIngestRequest` model has: `format`, `scan_type`, `payload`, `metadata`, `project_id`, `repository_id`. This maps cleanly to v2.2 `scan_runs`. Need to add `tenant_id` (from auth, not request body).

---

## Scope Triage

**Classification: `Large`**

Rationale:
- **DB layer change**: customer DB → reference DB (affects every collection write path)
- **Multi-layer replacement**: Service + Repository + Pydantic models + edge creation + API endpoint update
- **New Pydantic models** for 4 v2.2 doc collections
- **New edge creation logic** for 9 edge collections
- **Backfill adapter** (separate concern, separate module)
- **INGESTION_NORMALISATION** centralisation (`ParsedFinding` → `V22FindingRecord` transformer)
- **Detected controls** skeleton
- Estimated 12–18 new/modified files

---

## Open Unknowns

1. **`finding_triggers_req` resolution strategy**: How to map CWE → regulatory_requirement in reference DB? Need AQL traversal pattern.
2. **`detected_control_maps_to` source**: No current parser produces detected controls — implement as stub or skip?
3. **Deprecation of customer DB scan collections**: Once v2.2 pipeline is live, do we also need to update the existing customer DB scan queries that still reference `scan_sessions`/`customer_components`? Scope risk.
4. **API response model**: `ScanIngestResponse` currently returns `scan_session_id`. In v2.2 it should return `scan_run_id`. Is this a breaking API change?
