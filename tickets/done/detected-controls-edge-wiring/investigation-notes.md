# Investigation Notes

## Sources Consulted

- `src/complira_graph/ingestion/edge_service.py` (lines 538-559): stub body
- `src/complira_graph/ingestion/service.py`: EvidenceIngestionService — `EvidenceEdgeService(db)` takes single `StandardDatabase`
- `src/complira_graph/ingestion/adapter_registry.py`: Checkov adapter config
- `src/complira_graph/ingestion/ingestion_engine.py` (lines 347-370): detected_controls doc fields set by engine
- `src/complira_graph/schema/complira_kg_schema_v2_2.py` (lines 751-797): edge schemas
- `src/complira_graph/db.py` (lines 389-392): `detected_control_maps_to` indexes
- `src/complira_graph/agents/oscal.py` (line 111): `_key = control_id.replace('.', '_')` from OSCAL lowercase IDs
- `src/complira_graph/ingestion/scan_violation_repository.py`: AQL pattern reference
- `src/complira_graph/llm_agents/regulatory_mapper.py` (line 383): key normalization pattern
- `tests/unit/ingestion/test_edge_service.py` (lines 325-344): existing stub tests that must be replaced

## Key Findings

### F-001: EvidenceEdgeService receives a single `db` (reference DB)
`EvidenceIngestionService.__init__` creates `EvidenceEdgeService(db)` — the same `StandardDatabase` instance used for all collections (scan_findings, detected_controls, oscal_controls, etc.). No separate `_ref_db` needed; `self._db` is already the reference DB.

### F-002: detected_controls documents contain `check_id`, `fingerprint`, and optionally `purl`
Engine sets: `fingerprint`, `_key` (= fingerprint), `scan_run_id`, `tenant_id`, `tool`, `triage_status: "compliant"`, `control_type: "iac_check"`.
Checkov field_map adds: `check_id`, `check_name`, `file_path`, `resource_address`, `iac_framework`, `bc_check_id`, `severity`.
No `purl` field for IaC Checkov output (resource_address is not a PURL).

### F-003: Edge schema `additionalProperties: False` is strict
`detected_control_maps_to` only allows: `source`, `confidence`, `embedding_model`, `target_collection` (plus ArangoDB internals `_key`, `_from`, `_to`).
`control_in_component` only allows: `source`, `file_path`.
**No `tenant_id`, `scan_run_id`, `check_id`, `control_id`, `framework` on these edges.**

### F-004: oscal_controls key format
From `agents/oscal.py`: OSCAL JSON uses lowercase IDs (`"ac-1"`, `"si-10"`, `"ac-2.1"`). Key = `control_id.replace('.', '_')` → `"ac-1"`, `"si-10"`, `"ac-2_1"`.
From external sources (Checkov mapping in uppercase): normalize via `control_id.lower().replace('.', '_').replace('(', '').replace(')', '')` (from `regulatory_mapper.py` line 383).

### F-005: Checkov check_id → NIST 800-53 mapping must be bundled statically
No existing codebase artifact provides this mapping. The Checkov open-source project documents compliance mappings per check. A curated static Python dict `CHECKOV_NIST_MAP: dict[str, list[str]]` is the correct approach — deterministic, no runtime API calls, `source: "rule_engine"`, `confidence: 1.0`.

### F-006: Existing test stub (`TestDetectedControlEdgesStub`) asserts `import_bulk.assert_not_called()`
After implementation, these tests will need to be rewritten to test real behavior, not the stub.

### F-007: `generate_edge_key()` is the established pattern for deterministic edge keys
Used by all other edge creation methods. Must use it here too.

### F-008: `control_in_component` is a no-op for current Checkov IaC output
Checkov produces `resource_address` (e.g., `aws_s3_bucket.my_bucket`), not PURLs. The `control_in_component` edge is wired for future scanners that emit a `purl` field. Current implementation: only create if `doc.get("purl")` is truthy.

## Open Questions Resolved

- Q: Does edge_service have a separate `_ref_db`? **A: No — `self._db` is already the reference DB.**
- Q: What fields are on detected_control docs? **A: Fully enumerated in F-002.**
- Q: Does `additionalProperties: False` apply to `_key`, `_from`, `_to`? **A: No — ArangoDB internals are always allowed; constraint applies to user-defined fields.**
- Q: Where does the Checkov→NIST mapping come from? **A: Bundle as static Python dict; no external source needed.**

## Implications for Design

- New file: `src/complira_graph/ingestion/checkov_control_map.py` (curated `CHECKOV_NIST_MAP` dict)
- Modify: `edge_service.py` — replace stub body; add `_normalize_oscal_key()` helper
- Modify: `test_edge_service.py` — replace `TestDetectedControlEdgesStub` with implementation tests
- No schema changes, no service.py changes, no new public APIs
