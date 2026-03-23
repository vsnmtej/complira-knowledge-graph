# Future-State Runtime Call Stack

**Version:** v1
**Design basis:** `implementation-plan.md` (Small scope solution sketch)

---

## UC-1: Create detected_control_maps_to edges for known check_id

**Source type:** Requirement
**Use case:** Checkov PASSED checks with check_id in CHECKOV_NIST_MAP → detected_control_maps_to edges created

```
[Entry] EvidenceIngestionService._run_pipeline()
  ↓ Step 6: create all edges after detected_control_docs persisted
  → edge_service.py: EvidenceEdgeService.create_all_edges(detected_control_docs=[...], ...)
      ↓ if detected_control_docs is non-empty
      → edge_service.py: EvidenceEdgeService.create_detected_control_edges(
            detected_controls=[{"_key":"fp1","check_id":"CKV_AWS_19","fingerprint":"fp1",...}],
            tenant_id="t1"
        )
          ↓ for doc in detected_controls:
              fp = doc["fingerprint"]  # "fp1"
              check_id = doc["check_id"]  # "CKV_AWS_19"

              ↓ look up CHECKOV_NIST_MAP["CKV_AWS_19"] → ["SC-28"]
              checkov_control_map.py: CHECKOV_NIST_MAP.get("CKV_AWS_19") → ["SC-28"]

              ↓ for ctrl_id "SC-28":
                  ctrl_key = _normalize_oscal_key("SC-28")
                  → "sc-28"  [decision: lower + replace('.','_') + strip parens]

                  edge_key = generate_edge_key("fp1", "sc-28", "maps_to")
                  → deterministic sha256-based key

                  maps_to_edges.append({
                      "_key": edge_key,
                      "_from": "detected_controls/fp1",
                      "_to":   "oscal_controls/sc-28",
                      "source": "rule_engine",
                      "confidence": 1.0,
                      "target_collection": "oscal_controls",
                  })

          ↓ maps_to_edges is non-empty → write
          self._db.collection("detected_control_maps_to").import_bulk(
              maps_to_edges, on_duplicate="update"
          )
          ✓ state mutation: detected_control_maps_to edge persisted
          log.info("detected_control_maps_to.created", count=1)

[Exit] create_detected_control_edges returns None
```

**Primary path:** ✓
**Fallback path:** N/A (handled in UC-2)
**Error path:** N/A (graceful skip on missing check_id)

---

## UC-2: Skip detected controls with no mapping

**Source type:** Requirement
**Use case:** check_id not in CHECKOV_NIST_MAP → no edge created, no error

```
[Entry] EvidenceEdgeService.create_detected_control_edges(
    detected_controls=[{"_key":"fp2","check_id":"CKV_CUSTOM_99","fingerprint":"fp2"}],
    tenant_id="t1"
)
  ↓ for doc in detected_controls:
      check_id = "CKV_CUSTOM_99"

      ↓ CHECKOV_NIST_MAP.get("CKV_CUSTOM_99") → []  (empty list)
      ↓ for loop over [] → no iterations → no edge appended

  ↓ maps_to_edges is empty → no import_bulk call
  ↓ in_comp_edges is empty → no import_bulk call

[Exit] returns None — no error, no DB call
  [Decision gate] if not detected_controls → early return (AC-004)
  [Decision gate] CHECKOV_NIST_MAP.get(check_id, []) → empty list → skip silently
```

**Primary path:** ✓ (empty list path)
**Fallback path:** ✓ (empty detected_controls → early return)
**Error path:** N/A

---

## UC-3: Create control_in_component edge when purl present

**Source type:** Requirement
**Use case:** detected_control doc has purl field → control_in_component edge created

```
[Entry] EvidenceEdgeService.create_detected_control_edges(
    detected_controls=[{
        "_key": "fp3",
        "fingerprint": "fp3",
        "check_id": "CKV_AWS_19",
        "purl": "pkg:npm/express@4.18.2",
        "file_path": "terraform/main.tf",
    }],
    tenant_id="t1"
)
  ↓ for doc in detected_controls:
      fp = "fp3"
      check_id = "CKV_AWS_19"

      ↓ CHECKOV_NIST_MAP["CKV_AWS_19"] → ["SC-28"]
          ctrl_key = "sc-28"
          maps_to_edges.append({...detected_control_maps_to edge...})

      ↓ purl = doc.get("purl") → "pkg:npm/express@4.18.2"  [truthy]
          purl_key = normalize_purl("pkg:npm/express@4.18.2")
          edge_key = generate_edge_key("fp3", purl_key, "control_in_comp")
          in_comp_edges.append({
              "_key": edge_key,
              "_from": "detected_controls/fp3",
              "_to":   f"components/{purl_key}",
              "source": "scanner",
              "file_path": "terraform/main.tf",
          })

  ↓ maps_to_edges non-empty → import_bulk on detected_control_maps_to
  ✓ state mutation: detected_control_maps_to edge persisted

  ↓ in_comp_edges non-empty → import_bulk on control_in_component
  ✓ state mutation: control_in_component edge persisted
  log.info("control_in_component.created", count=1)

[Exit] returns None
```

**Primary path:** ✓
**Fallback path:** purl absent → in_comp_edges empty → no import_bulk call (AC-004 equivalent for purl)
**Error path:** N/A

---

## UC-DR1: Batch multiple detected_controls — no N+1 DB calls

**Source type:** Design-Risk
**Risk:** Looping over detected_controls docs and making per-doc DB calls would be O(N) write calls
**Expected outcome:** All maps_to_edges from all docs are collected first, then a single `import_bulk` call; same for in_comp_edges

```
[Entry] EvidenceEdgeService.create_detected_control_edges(
    detected_controls=[doc1, doc2, ..., docN],
    tenant_id="t1"
)
  ↓ maps_to_edges = []   ← accumulator
  ↓ in_comp_edges = []   ← accumulator

  ↓ for doc in detected_controls [N iterations]:
      ↓ accumulate into maps_to_edges (no DB call inside loop)
      ↓ accumulate into in_comp_edges (no DB call inside loop)

  ↓ [after loop] if maps_to_edges: ONE import_bulk call
  ↓ [after loop] if in_comp_edges: ONE import_bulk call

[Exit] at most 2 DB calls regardless of N
```

**Primary path:** ✓ (accumulator pattern ensures batch behavior)
**Error path:** Any import_bulk failure propagates to caller (let exception bubble — consistent with other edge methods)

---

## UC-DR2: Schema compliance — no extra fields on edge docs

**Source type:** Design-Risk
**Risk:** Including `tenant_id`, `scan_run_id`, etc. on edge docs would fail schema validation (`additionalProperties: False`)
**Expected outcome:** Edge docs contain ONLY fields allowed by schema

```
detected_control_maps_to allowed user fields:
  source, confidence, embedding_model (opt), target_collection (opt)

control_in_component allowed user fields:
  source, file_path (opt)

[Verify] maps_to edge doc keys = {_key, _from, _to, source, confidence, target_collection}
  → no tenant_id ✓
  → no scan_run_id ✓
  → no check_id ✓
  → no control_id ✓

[Verify] in_comp edge doc keys = {_key, _from, _to, source, file_path}
  → no tenant_id ✓
  → no scan_run_id ✓
```

**Primary path:** ✓ (static doc construction contains only schema-compliant fields)
**Error path:** N/A (compile-time/test-time verification)
