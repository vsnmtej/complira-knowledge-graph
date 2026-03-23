# Future-State Runtime Call Stacks: SBOM Component Ingestion

**Ticket:** `sbom-component-ingestion`
**Version:** v1
**Date:** 2026-03-22
**Basis:** implementation-plan.md (Draft) — Small scope

---

## Use Case Coverage Matrix

| use_case_id | Source Type | Primary | Fallback | Error | Notes |
| --- | --- | --- | --- | --- | --- |
| UC-SBOM-001 | Requirement | Yes | Yes | Yes | Component document upsert with field extension |
| UC-SBOM-002 | Requirement | Yes | Yes | Yes | `depends_on` edge ingestion from `dependencies[]` |
| UC-SBOM-003 | Requirement | Yes | N/A | N/A | `project_uses_component` — verify no regression |
| UC-SBOM-004 | Requirement | Yes | N/A | N/A | PURL normalization — embedded in UC-001/002 |
| UC-SBOM-005 | Requirement | Yes | N/A | N/A | Idempotency — embedded in UC-001/002 |
| UC-SBOM-006 | Requirement | Yes | N/A | N/A | Fallback PURL for nameless components |
| DR-SBOM-001 | Design-Risk | Yes | N/A | N/A | `dependsOn` ref not matching any component → dangling edge tolerance |

---

## UC-SBOM-001 — Component Document Upsert with Field Extension

**Source:** Requirement (REQ-SBOM-001)
**Objective:** CycloneDX components are parsed with `supplier`, `licenses`, `hashes` and upserted to the `components` collection.

```
POST /v1/scan/ingest  {format="cyclonedx", payload={components:[...], dependencies:[...]}}
  └─ src/api/v1/endpoints/scan.py : ingest_scan_endpoint()
       │  DECISION: request.format == "cyclonedx" → SBOM path
       │  EXTRACT: components_raw = request.payload.get("components", [])
       │  EXTRACT: dependencies_raw = request.payload.get("dependencies", [])  ← NEW
       └─ src/complira_graph/ingestion/service.py : EvidenceIngestionService.ingest_sbom(
              tenant_id, components_raw, sbom_format="cyclonedx",
              dependencies_raw=dependencies_raw,   ← NEW param
              project_id, repository_id
          )
            │  CALL: self._run_repo.create_run(tenant_id, project_id, repository_id, tools_invoked=["sbom"])
            │    └─ src/complira_graph/ingestion/repositories.py : EvidenceRunRepository.create_run()
            │         DB WRITE: scan_runs.insert({_key: uuid, status: "running", ...})
            │
            │  CALL: self._build_component_docs(components_raw, sbom_format="cyclonedx")
            │    └─ src/complira_graph/ingestion/service.py : _build_component_docs()
            │         FOR each raw_component:
            │           purl = raw.get("purl") or raw.get("packageUrl")
            │           name = raw.get("name", "").strip()
            │           version = raw.get("version", "")
            │           DECISION: no purl + no name → SKIP (warning logged)
            │           DECISION: no purl + name → fallback purl = "pkg:generic/{name}@{version}"
            │
            │           supplier_raw = raw.get("supplier") or {}      ← NEW
            │           supplier = supplier_raw.get("name") if dict   ← NEW
            │
            │           licenses_raw = raw.get("licenses") or []      ← NEW
            │           licenses = [lic.license.id for lic in licenses_raw if valid]  ← NEW
            │
            │           hashes_raw = raw.get("hashes") or []          ← NEW
            │           hashes = [{alg, content} for h in hashes_raw] ← NEW
            │
            │           CALL: normalize_purl(purl)
            │             └─ src/complira_graph/utils/keys.py : normalize_purl()
            │                  re.sub(r'[^a-zA-Z0-9_]', '_', purl)
            │                  → _key = "pkg_npm_lodash_4_17_21"
            │
            │           V22Component(key=_key, purl, name, version, type, purl_source="sbom",
            │                        sbom_format, cpe, license, supplier, licenses, hashes)  ← NEW fields
            │           → doc dict (model_dump by_alias)
            │         RETURN: [doc1, doc2, doc3]
            │
            │  DECISION: component_docs non-empty
            │  CALL: self._component_repo.upsert_batch(component_docs)
            │    └─ src/complira_graph/ingestion/repositories.py : EvidenceComponentRepository.upsert_batch()
            │         DB WRITE: components.import_bulk(docs, on_duplicate="update")
            │         → {created: N, updated: M}
            │
            └─ [continue → UC-SBOM-002 if dependencies_raw; UC-SBOM-003 if project_id]

Primary path coverage: Pass
Fallback path (no purl → fallback key): Pass — handled in _build_component_docs()
Error path (no purl, no name → skip): Pass — warning logged, component excluded from batch
```

---

## UC-SBOM-002 — `depends_on` Edge Ingestion from `dependencies[]`

**Source:** Requirement (REQ-SBOM-002)
**Objective:** CycloneDX `dependencies[]` entries are parsed and written as `depends_on` edges.

```
[continuing from UC-SBOM-001 ingest_sbom(), after component upsert]

  src/complira_graph/ingestion/service.py : ingest_sbom()
    │  DECISION: dependencies_raw non-empty
    │  CALL: self._edge_svc.create_depends_on_edges(
    │            dependencies_raw=dependencies_raw,
    │            scan_run_key=scan_run_key,
    │            tenant_id=tenant_id
    │        )
    │    └─ src/complira_graph/ingestion/edge_service.py : EvidenceEdgeService.create_depends_on_edges()
    │         edges = []
    │         FOR each dep in dependencies_raw:
    │           from_purl = dep.get("ref")
    │           DECISION: no "ref" → SKIP (continue)
    │           from_key = normalize_purl(from_purl)
    │           FOR each to_purl in dep.get("dependsOn") or []:
    │             to_key = normalize_purl(to_purl)
    │             edge_key = generate_edge_key(from_key, to_key, "depends_on")
    │             edges.append({
    │               "_key": edge_key,
    │               "_from": "components/{from_key}",
    │               "_to": "components/{to_key}",
    │               "tenant_id": tenant_id,
    │               "scan_run_id": scan_run_key,
    │             })
    │         DECISION: edges non-empty
    │         DB WRITE: depends_on.import_bulk(edges, on_duplicate="update")
    │         LOG: "depends_on.created" count=N
    │
    │  [continues to complete_run below]

Primary path coverage: Pass
Fallback path (dep has no "ref" → skip): Pass — DECISION gate + continue
Fallback path (dependsOn is empty list → no edges for that dep): Pass — inner FOR produces nothing
Error path (depends_on collection missing → arango exception): N/A — collection exists in schema
```

---

## UC-SBOM-003 — `project_uses_component` Edge No Regression

**Source:** Requirement (REQ-SBOM-003)
**Objective:** Existing `project_uses_component` edge creation path continues to work unchanged.

```
[continuing from ingest_sbom(), after component upsert]

  src/complira_graph/ingestion/service.py : ingest_sbom()
    │  DECISION: component_docs non-empty AND project_id set
    │  CALL: self._edge_svc.create_project_uses_component_edges(
    │            component_docs, project_id, tenant_id
    │        )
    │    └─ src/complira_graph/ingestion/edge_service.py : create_project_uses_component_edges()
    │         FOR each comp in component_docs:
    │           purl = comp.get("purl")
    │           DECISION: no purl → skip
    │           comp_key = comp.get("_key") or normalize_purl(purl)
    │           edge_key = generate_edge_key(project_id, comp_key, "uses")
    │           edges.append({_key, _from: "projects/{project_id}",
    │                          _to: "components/{comp_key}", tenant_id, sbom_format, source: "sbom"})
    │         DB WRITE: project_uses_component.import_bulk(edges, on_duplicate="update")

Primary path coverage: Pass
Fallback path (no project_id → no edges): Pass — DECISION gate
```

---

## UC-SBOM-004/005 — PURL Normalization + Idempotency (Cross-Cutting)

**Source:** Requirement (REQ-SBOM-004, REQ-SBOM-005)
**Objective:** PURL normalization is consistent; re-ingestion produces no duplicates.

```
  normalize_purl("pkg:npm/lodash@4.17.21")
    └─ src/complira_graph/utils/keys.py : normalize_purl()
         len("pkg:npm/lodash@4.17.21") = 22 < 254
         re.sub(r'[^a-zA-Z0-9_]', '_', "pkg:npm/lodash@4.17.21")
         → "pkg_npm_lodash_4_17_21"

  Idempotency — component documents:
    import_bulk(on_duplicate="update") → same _key = update in place, no duplicate

  Idempotency — depends_on edges:
    generate_edge_key(from_key, to_key, "depends_on") → deterministic _key
    import_bulk(on_duplicate="update") → same _key = update in place, no duplicate

Primary path coverage: Pass
```

---

## UC-SBOM-006 — Fallback PURL Derivation

**Source:** Requirement (REQ-SBOM-006 / assumption)
**Objective:** Component with no PURL but with name gets a synthetic key.

```
  _build_component_docs() — raw = {"name": "mylib", "version": "1.0.0", "type": "library"}
    purl = raw.get("purl")  → None
    purl = raw.get("packageUrl")  → None
    DECISION: purl is None + name is "mylib"
    → purl = "pkg:generic/mylib@1.0.0"
    LOG: "sbom.generated_fallback_purl" name=mylib purl=pkg:generic/mylib@1.0.0
    normalize_purl("pkg:generic/mylib@1.0.0") → "pkg_generic_mylib_1_0_0"
    V22Component(key="pkg_generic_mylib_1_0_0", purl="pkg:generic/mylib@1.0.0", ...)

Primary path coverage: Pass
Fallback: no name + no purl → SKIP (warning logged)
```

---

## DR-SBOM-001 — Dangling Edge Tolerance

**Source:** Design-Risk
**Technical Objective:** Verify that `dependsOn` refs that point to a PURL not present in the components batch do not cause a DB error or pipeline failure.
**Expected Observable Outcome:** Edge is written with the normalized PURL as `_to`; ArangoDB allows dangling edges (schema permits, as in `component_has_vuln` pattern); no exception raised.

```
  create_depends_on_edges([{"ref": "pkg:npm/lodash@4", "dependsOn": ["pkg:npm/unknown@99"]}], ...)
    from_key = normalize_purl("pkg:npm/lodash@4") → "pkg_npm_lodash_4"
    to_key = normalize_purl("pkg:npm/unknown@99") → "pkg_npm_unknown_99"
    edge_key = generate_edge_key("pkg_npm_lodash_4", "pkg_npm_unknown_99", "depends_on")
    edges = [{"_key": ..., "_from": "components/pkg_npm_lodash_4",
              "_to": "components/pkg_npm_unknown_99",
              "tenant_id": ..., "scan_run_id": ...}]
    DB WRITE: depends_on.import_bulk(edges, on_duplicate="update")
    → ArangoDB writes edge; allows non-existent vertex (_to) per schema design
    → No exception; blast radius traversal skips non-existent vertices automatically

Expected: Pass (ArangoDB tolerates dangling edges per existing schema design — matches component_has_vuln pattern)
```

---

## Scan Run Completion (All UC-SBOM paths)

```
  src/complira_graph/ingestion/service.py : ingest_sbom()
    DECISION: create_new_run is True
    CALL: self._run_repo.complete_run(
            scan_run_key=scan_run_key,
            finding_counts={critical:0, high:0, medium:0, low:0, info:0},
            status="completed",
            components_count=len(component_docs)
          )
      └─ DB WRITE: scan_runs.update({_key, status="completed", components_count=N, completed_at})
    RETURN: ScanIngestResult(scan_run_id, findings_count=0, components_count=N, status="completed")
```
