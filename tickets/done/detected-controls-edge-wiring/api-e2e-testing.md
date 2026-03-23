# API/E2E Testing

## Acceptance Criteria Matrix

| AC ID | Criterion | Scenario IDs | Status |
| --- | --- | --- | --- |
| AC-001 | import_bulk called for known check_id | S-001 | Passed ✅ |
| AC-002 | Edge fields: _from, _to, source, confidence, target_collection | S-002 | Passed ✅ |
| AC-003 | Unknown check_id → skip, no error | S-003 | Passed ✅ |
| AC-004 | Empty list → no DB calls | S-004 | Passed ✅ |
| AC-005 | purl present → control_in_component created | S-005 | Passed ✅ |
| AC-006 | Deterministic edge key | S-006 | Passed ✅ |
| AC-007 | import_bulk(on_duplicate="update") | S-007 | Passed ✅ |
| AC-008 | No extra fields (additionalProperties: False) | S-008, S-009 | Passed ✅ |

## Scenarios

### S-001 (AC-001) — Known check_id creates detected_control_maps_to edge

- **Type:** Unit / API
- **Requirement:** AC-001
- **Use case:** UC-1
- **Expected:** `db.collection("detected_control_maps_to").import_bulk(...)` called
- **Command:** `pytest tests/unit/ingestion/test_edge_service.py::TestDetectedControlEdges::test_creates_maps_to_edge_for_known_check_id`
- **Result:** Passed ✅

### S-002 (AC-002) — Edge doc fields are correct

- **Type:** Unit / API
- **Requirement:** AC-002
- **Use case:** UC-1
- **Expected:** `source="rule_engine"`, `confidence=1.0`, `target_collection="oscal_controls"`, `_from=detected_controls/fp`, `_to=oscal_controls/<key>`
- **Command:** `...::test_edge_fields_match_schema`
- **Result:** Passed ✅

### S-003 (AC-003) — Unknown check_id silently skipped

- **Type:** Unit / API
- **Requirement:** AC-003
- **Use case:** UC-2
- **Expected:** No DB calls
- **Command:** `...::test_skips_unknown_check_id_no_error`
- **Result:** Passed ✅

### S-004 (AC-004) — Empty list noop

- **Type:** Unit / API
- **Requirement:** AC-004
- **Use case:** UC-2
- **Expected:** No DB calls
- **Command:** `...::test_noop_on_empty_list`
- **Result:** Passed ✅

### S-005 (AC-005) — control_in_component when purl present

- **Type:** Unit / API
- **Requirement:** AC-005
- **Use case:** UC-3
- **Expected:** `control_in_component` collection written with correct `_from`, `_to`, `source="scanner"`, `file_path`
- **Command:** `...::test_creates_control_in_component_edge_when_purl_present`
- **Result:** Passed ✅

### S-006 (AC-006) — Deterministic keys

- **Type:** Unit / API
- **Requirement:** AC-006
- **Use case:** UC-DR1
- **Expected:** Two runs produce identical `_key` values
- **Command:** `...::test_edge_key_is_deterministic`
- **Result:** Passed ✅

### S-007 (AC-007) — on_duplicate="update"

- **Type:** Unit / API
- **Requirement:** AC-007
- **Use case:** UC-DR1
- **Expected:** `import_bulk` called with `on_duplicate="update"` kwarg
- **Command:** `...::test_import_bulk_uses_on_duplicate_update`
- **Result:** Passed ✅

### S-008 (AC-008) — No extra fields on maps_to edge

- **Type:** Unit / API
- **Requirement:** AC-008
- **Use case:** UC-DR2
- **Expected:** Edge doc keys ⊆ {_key, _from, _to, source, confidence, target_collection, embedding_model}
- **Command:** `...::test_no_extra_fields_on_maps_to_edge`
- **Result:** Passed ✅

### S-009 (AC-008) — No extra fields on control_in_component edge

- **Type:** Unit / API
- **Requirement:** AC-008
- **Use case:** UC-DR2
- **Expected:** Edge doc keys ⊆ {_key, _from, _to, source, file_path}
- **Command:** `...::test_no_extra_fields_on_control_in_component_edge`
- **Result:** Passed ✅

### S-010 — Multi-control per check_id

- **Type:** Unit / API
- **Requirement:** AC-001, AC-002
- **Use case:** UC-1
- **Expected:** check_id mapping to 2 controls creates 2 edges
- **Command:** `...::test_multi_control_per_check_id`
- **Result:** Passed ✅

### S-011 — No control_in_component when purl absent

- **Type:** Unit / API
- **Requirement:** AC-005 (negative)
- **Use case:** UC-3
- **Expected:** `control_in_component` collection not written
- **Command:** `...::test_no_control_in_component_when_no_purl`
- **Result:** Passed ✅

## Stage 7 Gate Decision: Pass ✅

All 8 ACs mapped and passed. All 11 scenarios resolved.
