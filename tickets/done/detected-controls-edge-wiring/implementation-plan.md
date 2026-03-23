# Implementation Plan

**Scope:** Small
**Status:** Finalized (post Stage 5 Go Confirmed)

## Solution Sketch (Design Basis)

### Architecture Direction

Target: implement `create_detected_control_edges()` inside the existing `EvidenceEdgeService` layer. No new layer needed; this is a pure edge-creation concern within the existing service boundary.

**New file:** `src/complira_graph/ingestion/checkov_control_map.py`
Responsibility: static curated `CHECKOV_NIST_MAP: dict[str, list[str]]` mapping `check_id` → list of NIST 800-53 control_ids. No logic, no DB calls — data only.

**Modified file:** `src/complira_graph/ingestion/edge_service.py`
Changes:
- Import `CHECKOV_NIST_MAP` from `checkov_control_map`
- Replace stub body of `create_detected_control_edges()` with real implementation
- Add private `_normalize_oscal_key(control_id: str) -> str` helper

**Modified file:** `tests/unit/ingestion/test_edge_service.py`
Changes:
- Replace `TestDetectedControlEdgesStub` with `TestDetectedControlEdges` covering real behavior

### Key normalization
```
_normalize_oscal_key("AC-2")   → "ac-2"
_normalize_oscal_key("AC-2.1") → "ac-2_1"
_normalize_oscal_key("AC-2(1)") → "ac-2_1"
```

### Edge field sets (must match schema `additionalProperties: False`)

`detected_control_maps_to` doc:
```python
{
    "_key": generate_edge_key(fp, control_key, "maps_to"),
    "_from": f"detected_controls/{fp}",
    "_to":   f"oscal_controls/{control_key}",
    "source":            "rule_engine",
    "confidence":        1.0,
    "target_collection": "oscal_controls",
}
```

`control_in_component` doc:
```python
{
    "_key": generate_edge_key(fp, purl_key, "control_in_comp"),
    "_from": f"detected_controls/{fp}",
    "_to":   f"components/{purl_key}",
    "source":    "scanner",
    "file_path": doc.get("file_path"),  # None-safe
}
```

### Implementation logic

```python
def create_detected_control_edges(self, detected_controls, tenant_id):
    maps_to_edges = []
    in_comp_edges = []

    for doc in detected_controls:
        fp = doc.get("fingerprint") or doc.get("_key", "")
        if not fp:
            continue

        check_id = doc.get("check_id", "")
        for ctrl_id in CHECKOV_NIST_MAP.get(check_id, []):
            ctrl_key = _normalize_oscal_key(ctrl_id)
            edge_key = generate_edge_key(fp, ctrl_key, "maps_to")
            maps_to_edges.append({
                "_key": edge_key,
                "_from": f"detected_controls/{fp}",
                "_to":   f"oscal_controls/{ctrl_key}",
                "source": "rule_engine",
                "confidence": 1.0,
                "target_collection": "oscal_controls",
            })

        purl = doc.get("purl")
        if purl:
            purl_key = normalize_purl(purl)
            edge_key = generate_edge_key(fp, purl_key, "control_in_comp")
            in_comp_edges.append({
                "_key": edge_key,
                "_from": f"detected_controls/{fp}",
                "_to":   f"components/{purl_key}",
                "source": "scanner",
                "file_path": doc.get("file_path") or None,
            })

    if maps_to_edges:
        self._db.collection("detected_control_maps_to").import_bulk(
            maps_to_edges, on_duplicate="update"
        )
        log.info("detected_control_maps_to.created", extra={"count": len(maps_to_edges)})

    if in_comp_edges:
        self._db.collection("control_in_component").import_bulk(
            in_comp_edges, on_duplicate="update"
        )
        log.info("control_in_component.created", extra={"count": len(in_comp_edges)})
```

## Change Inventory

| # | File | Change Type | Description |
| --- | --- | --- | --- |
| C-01 | `src/complira_graph/ingestion/checkov_control_map.py` | Add | Static `CHECKOV_NIST_MAP` dict + `_normalize_oscal_key()` helper |
| C-02 | `src/complira_graph/ingestion/edge_service.py` | Modify | Import map; implement `create_detected_control_edges()`; add `_normalize_oscal_key()` call |
| C-03 | `tests/unit/ingestion/test_edge_service.py` | Modify | Replace stub test class with real implementation tests |

## Task Sequence

1. Create `checkov_control_map.py` with `CHECKOV_NIST_MAP` dict and `_normalize_oscal_key()` helper
2. Implement `create_detected_control_edges()` in `edge_service.py`
3. Update `test_edge_service.py`: replace `TestDetectedControlEdgesStub`, add `TestDetectedControlEdges`
4. Run unit tests to verify all pass

## Acceptance Criteria Coverage

| AC | Task |
| --- | --- |
| AC-001 | Task 2 |
| AC-002 | Task 1, 2 |
| AC-003 | Task 2 |
| AC-004 | Task 2 |
| AC-005 | Task 2 |
| AC-006 | Task 1, 2 |
| AC-007 | Task 2 |
| AC-008 | Task 1, 2 |
