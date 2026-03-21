# Future-State Runtime Call Stacks (Debug-Trace Style)

## Design Basis

- Scope Classification: `Large`
- Call Stack Version: `v3`
- Requirements: `tickets/in-progress/evidence-ingestion-pipeline/requirements.md` (status `Refined`)
- Source Artifact: `tickets/in-progress/evidence-ingestion-pipeline/proposed-design.md`
- Source Design Version: `v3`
- Referenced Sections: Target State (To-Be), File And Module Breakdown, Change Inventory

## Future-State Modeling Rule

- All stacks model the target `EvidenceIngestionService` writing to reference DB.
- Current `ScanIngestionService` / customer DB paths are not modeled — they are removed.

## Use Case Index

| use_case_id | Source Type | Requirement ID(s) | Design-Risk Objective | Use Case Name | Coverage Target |
| --- | --- | --- | --- | --- | --- |
| UC-001 | Requirement | R-001 | N/A | Scan run lifecycle (create + complete) | Primary/N/A/Yes |
| UC-002 | Requirement | R-002 | N/A | SAST finding ingestion with fingerprint dedup | Primary/N/A/Yes |
| UC-003 | Requirement | R-003 | N/A | SCA finding ingestion + component_has_vuln edge | Primary/Fallback/Yes |
| UC-004 | Requirement | R-004 | N/A | SBOM component upsert (purl-keyed global) | Primary/Fallback/Yes |
| UC-005 | Requirement | R-004 | N/A | project_uses_component edge creation | Primary/N/A/Yes |
| UC-006 | Requirement | R-003 | N/A | component_has_vuln edge (CVE missing → skip) | Primary/Fallback/N/A |
| UC-007 | Requirement | R-005 | N/A | finding_maps_to_weakness edge | Primary/Fallback/N/A |
| UC-008 | Requirement | R-006 | N/A | finding_triggers_req edge via AQL CWE lookup | Primary/Fallback/N/A |
| UC-009 | Requirement | R-007 | N/A | finding_in_component edge | Primary/Fallback/N/A |
| UC-010 | Requirement | R-008 | N/A | detected_controls stub ingestion | Primary/N/A/N/A |
| UC-011 | Requirement | R-008 | N/A | Control mapping edges stub (detected_control_maps_to + control_in_component) | Primary/N/A/N/A |
| UC-012 | Requirement | R-009 | N/A | Evidence package + traceability edges (covers UC-013 inline) | Primary/N/A/Yes |
| UC-013 | Requirement | R-009 | N/A | Evidence-to-finding edge creation (covered inline in UC-012) | Primary/N/A/N/A |
| UC-014 | Requirement | R-002, R-011 | N/A | Idempotent re-ingestion (fingerprint + edge key dedup) | Primary/N/A/N/A |
| UC-015 | Requirement | R-012 | N/A | Backfill legacy customer DB data | Primary/Fallback/Yes |
| UC-016 | Requirement | R-002, R-003 | N/A | Ingestion normalisation (INGESTION_NORMALISATION applied) | Primary/N/A/N/A |
| UC-017 | Requirement | R-013 | N/A | Checkov IaC finding ingestion (IngestionEngine multi_root routing) | Primary/Fallback/Yes |
| UC-018 | Requirement | R-014 | N/A | checkov_native finding_triggers_req edge (bc_check_id present/absent) | Primary/Fallback/N/A |
| UC-019 | Requirement | R-015 | N/A | Checkov PASSED → detected_controls routing | Primary/N/A/N/A |
| DR-001 | Design-Risk | R-010 | tenant_id isolation — verify wrong-tenant query returns empty | Multi-tenant data isolation boundary | Primary/N/A/N/A |
| DR-002 | Design-Risk | R-006 | AQL reference resolution — finding_triggers_req when CWE→req path missing | AQL edge resolution graceful skip | Primary/Fallback/N/A |
| DR-003 | Design-Risk | R-014 | bc_check_id absent fallback — verify llm_reg_mapper source used, no engine error | bc_check_id conditional req mapping | Primary/Fallback/N/A |

---

## Transition Notes

- `ScanIngestionService`, `ScanSessionRepository`, `ScanFindingRepository`, `ComponentRepository` are deleted in the same ticket.
- `ScanSession` / `ScanFinding` models removed from `complira_graph/models/scan.py`.
- Backfill must run before decommission of customer DB scan collections (customer DB data not deleted — only read for migration).

---

## UC-001: Scan Run Lifecycle (Create + Complete)

### Goal
Create a `scan_runs` document before findings are written, update it with counts and status on completion.

### Preconditions
- Valid `ScanIngestRequest` received at `POST /v1/scan/ingest`
- `tenant_id` available from auth context
- Reference DB accessible

### Expected Outcome
`scan_runs` doc exists with `status=running` before findings; updated to `status=completed` with `finding_counts` after.

### Primary Runtime Call Stack

```text
[ENTRY] api/v1/endpoints/scan.py:ingest_scan_endpoint(request, customer)
├── customer.id → tenant_id                              [STATE]
├── complira_graph/ingestion/service.py:EvidenceIngestionService.ingest_scan(tenant_id, request)
│   ├── api/core/database.py:get_reference_db()          [IO] # shared reference DB connection
│   ├── complira_graph/ingestion/repositories.py:EvidenceRunRepository.create_run(
│   │       tenant_id, project_id, repository_id, tools_invoked=[request.format]
│   │   )                                                [IO] # INSERT scan_runs, status=running
│   │   └── returns: scan_run_doc (dict with _key=uuid)  [STATE]
│   │
│   ├── # ... parsing + finding/component ingestion (see UC-002 / UC-004) ...
│   │
│   └── complira_graph/ingestion/repositories.py:EvidenceRunRepository.complete_run(
│           scan_run_key,
│           finding_counts={critical:N, high:N, ...},
│           compliance_score=None,  # computed by Tier 1 AQL later
│           violated_requirements=[],
│           status="completed"
│       )                                                [IO] # UPDATE scan_runs doc
└── api/v1/endpoints/scan.py:→ ScanIngestResponse(scan_run_id=..., findings_count=..., status="completed")
```

### Error Path

```text
[ERROR] if any step between create_run and complete_run raises
complira_graph/ingestion/service.py:EvidenceIngestionService.ingest_scan(...)
└── complira_graph/ingestion/repositories.py:EvidenceRunRepository.fail_run(scan_run_key, error_msg)
    └── [IO] UPDATE scan_runs, status="failed"
        raise  # re-raise to API layer → 500
```

### State And Data Transformations

- `ScanIngestRequest.format + scan_type + project_id + repository_id` → `scan_runs` doc with `tenant_id`

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered`

---

## UC-002: SAST Finding Ingestion With Fingerprint Dedup

### Goal
Ingest SARIF SAST findings into reference DB `scan_findings` with fingerprint-based deduplication.

### Preconditions
- SARIF payload parsed to `ParsedScanData` (findings list)
- `scan_run_doc` created (UC-001)

### Expected Outcome
Each finding stored once (fingerprint `_key`); second ingestion of same finding updates, not duplicates.

### Primary Runtime Call Stack

```text
[ENTRY] complira_graph/ingestion/service.py:EvidenceIngestionService._ingest_findings(
        raw_file, tool_name, scan_run_doc, tenant_id
    )
├── complira_graph/ingestion/ingestion_engine.py:IngestionEngine.process(
│       tool_name=tool_name,  # "semgrep" | "checkov" | etc.
│       raw_file=raw_bytes,
│       scan_run_id=scan_run_doc["_key"],
│       tenant_id=tenant_id
│   )
│   ├── adapter = ADAPTER_REGISTRY["semgrep"]            [STATE]
│   ├── for each raw finding:
│   │   ├── _fingerprint(adapter, raw)
│   │   │   └── sha256(rule_id + "|" + file_path + "|" + line_number)[:32]  [STATE]
│   │   ├── _classify_severity(adapter, raw)
│   │   │   └── adapter["severity_map"].get(raw["severity"])  [STATE]
│   │   │       # ERROR→high, WARNING→medium, INFO→info
│   │   ├── _route(adapter, raw)
│   │   │   └── adapter["result_routing"]["*"] → "scan_findings"  [STATE]
│   │   ├── _map_fields(adapter, raw)
│   │   │   └── rule_id, file_path, line_start, cwe→_cwe_raw, etc.  [STATE]
│   │   ├── _extract_cwe(adapter, raw, doc)
│   │   │   └── re.findall(adapter["cwe_extract_pattern"], combined_text)  [STATE]
│   │   ├── _redact(adapter, doc)  # no-op (no secret_raw_field)  [STATE]
│   │   ├── _validate(doc)                               [STATE]
│   │   └── _plan_edges(adapter, doc) → edges list       [STATE]
│   └── returns: List[{"collection": "scan_findings", "document": dict, "edges": list}]
│
└── complira_graph/ingestion/repositories.py:EvidenceFindingRepository.upsert_batch(bundles)
    └── db.collection("scan_findings").import_bulk(
            [b["document"] for b in bundles],
            on_duplicate="update"   # fingerprint _key → idempotent
        )                                                [IO]
        └── returns: inserted/updated count             [STATE]
```

### Error Path

```text
[ERROR] if import_bulk fails (schema validator rejects doc)
EvidenceFindingRepository.upsert_batch(...)
└── log.error("scan_findings bulk insert failed", error=...)
    raise  # propagates to service → scan_run marked failed
```

### State And Data Transformations

- `ParsedFinding` → `V22FindingRecord` (normaliser applies INGESTION_NORMALISATION)
- `V22FindingRecord.fingerprint` → `scan_findings._key` (enables on_duplicate=update)

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered`

---

## UC-003: SCA Finding Ingestion + component_has_vuln Edge

### Goal
Ingest Grype/SCA findings (CVE-keyed) into `scan_findings` AND create `component_has_vuln` edges.

### Preconditions
- Grype or CycloneDX SCA payload parsed to `ParsedScanData`
- Reference DB `vulnerabilities` collection populated (NVD agent has run)

### Expected Outcome
`scan_findings` docs with `finding_type=sca` + `component_has_vuln` edge pointing to reference DB `vulnerabilities/<CVE_key>`.

### Primary Runtime Call Stack

```text
[ENTRY] complira_graph/ingestion/service.py:EvidenceIngestionService._ingest_findings(...)
├── normaliser.py:IngestionNormaliser.normalise(findings, ...)
│   └── for SCA findings:
│       ├── _generate_fingerprint_sca(cve_id, purl)
│       │   └── sha256(f"{cve_id}:{purl}".encode())[:32]  [STATE]
│       └── V22FindingRecord(finding_type="sca", cve_id=..., purl=..., ...)  [STATE]
├── EvidenceFindingRepository.upsert_batch(v22_findings)  [IO]
│
└── complira_graph/ingestion/edge_service.py:EvidenceEdgeService.create_component_has_vuln_edges(
        findings=v22_findings,    # filter: finding.cve_id is not None
        tenant_id=tenant_id
    )
    ├── for each SCA finding with cve_id and purl:
    │   ├── cve_key = normalize_cve_id(finding.cve_id)         # e.g. "CVE_2024_12345"
    │   ├── comp_key = normalize_purl(finding.purl)            # e.g. "pkg_pypi_django_4_2_0"
    │   ├── edge_key = generate_edge_key(comp_key, cve_key)
    │   └── builds: {_key, _from: "components/<comp_key>", _to: "vulnerabilities/<cve_key>",
    │                tenant_id, vex_status: "unknown", source: "grype"}
    └── db.collection("component_has_vuln").import_bulk(edges, on_duplicate="update")  [IO]
```

### Fallback Path

```text
[FALLBACK] CVE not in reference DB vulnerabilities collection
EvidenceEdgeService.create_component_has_vuln_edges(...)
├── edge built with _to: "vulnerabilities/<CVE_key>"
├── ArangoDB stores edge (dangling _to is allowed)
└── log.warning("CVE not in vulnerabilities, dangling edge created", cve_id=...)
    # not an error — Tier 1 AQL will skip if vertex missing
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `Covered` (via UC-001 error path)

---

## UC-004: SBOM Component Upsert (purl-keyed, Global)

### Goal
Upsert SBOM components into global reference DB `components` collection, keyed by purl.

### Preconditions
- CycloneDX payload parsed to `ParsedScanData` (components list)

### Expected Outcome
Each component stored once globally (purl `_key`); second ingestion updates, not duplicates. No `tenant_id` on component document.

### Primary Runtime Call Stack

```text
[ENTRY] complira_graph/ingestion/service.py:EvidenceIngestionService._ingest_components(
        parsed_data.components, scan_run_doc, tenant_id, project_id
    )
├── for each component dict from parser:
│   ├── purl = component.get("purl") or generate_purl_fallback(component)
│   │   └── [FALLBACK] if no purl: f"pkg:generic/{name}@{version}"
│   ├── comp_key = utils/keys.py:normalize_purl(purl)
│   └── V22Component(
│           _key=comp_key, purl=purl, name=..., version=...,
│           type=..., purl_source="sbom", sbom_format=parsed_data.metadata.get("format"),
│       )                                            [STATE]
│
├── complira_graph/ingestion/repositories.py:EvidenceComponentRepository.upsert_batch(v22_components)
│   └── db.collection("components").import_bulk(
│           [c.model_dump() for c in v22_components],
│           on_duplicate="update"  # purl _key → global dedup
│       )                                            [IO]
│
└── (project_uses_component edges created in UC-005)
```

### Fallback Path (PURL Missing)

```text
[FALLBACK] component has no purl and has name
service.py:generate_purl_fallback(component)
└── returns f"pkg:generic/{name}@{version}" or f"pkg:generic/{name}"
    log.info("Generated fallback purl", name=..., purl=...)
```

```text
[FALLBACK] component has no purl AND no meaningful name
service.py:_ingest_components(...)
└── log.warning("Skipping component with no purl and no meaningful name", ...)
    continue  # skip silently
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `Covered` (bulk insert failure → scan_run failed)

---

## UC-005: project_uses_component Edge Creation

### Goal
Create `project_uses_component` edges from `projects/<project_id>` to each ingested component.

### Preconditions
- `project_id` provided in `ScanIngestRequest`
- Components upserted (UC-004 complete)

### Expected Outcome
`project_uses_component` edges exist in reference DB, keyed deterministically, with `tenant_id`.

### Primary Runtime Call Stack

```text
complira_graph/ingestion/edge_service.py:EvidenceEdgeService.create_project_uses_component_edges(
    v22_components, project_id, tenant_id
)
├── for each component:
│   ├── edge_key = generate_edge_key(project_id, comp_key, edge_type="uses")
│   └── builds: {_key, _from: "projects/<project_id>", _to: "components/<comp_key>",
│                tenant_id, sbom_format=..., source: "sbom"}
└── db.collection("project_uses_component").import_bulk(edges, on_duplicate="update")  [IO]
```

### Error Path

```text
[ERROR] project_id is None (no project context)
EvidenceEdgeService.create_project_uses_component_edges(...)
└── if project_id is None: log.info("No project_id, skipping project_uses_component edges")
    return  # not an error; project context is optional
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered`

---

## UC-006: component_has_vuln Edge (CVE Missing → Skip)

*Covered inline in UC-003 fallback path. See UC-003.*

---

## UC-007: finding_maps_to_weakness Edge

### Goal
Create `finding_maps_to_weakness` edges linking `scan_findings` to `weaknesses` (CWE) documents.

### Preconditions
- `scan_findings` upserted (UC-002/UC-003)
- CWE IDs extracted during normalisation into `V22FindingRecord.cwe_ids`

### Expected Outcome
For each finding with CWE IDs, edges exist from `scan_findings/<fingerprint>` to `weaknesses/CWE_<N>`.

### Primary Runtime Call Stack

```text
complira_graph/ingestion/edge_service.py:EvidenceEdgeService.create_finding_weakness_edges(
    v22_findings, tenant_id
)
├── for each finding with len(finding.cwe_ids) > 0:
│   ├── for each cwe_id in finding.cwe_ids:
│   │   ├── cwe_key = utils/keys.py:normalize_cwe_id(cwe_id)  # "CWE_79"
│   │   ├── edge_key = generate_edge_key(finding.fingerprint, cwe_key, "maps_to_weakness")
│   │   └── builds: {_key, _from: "scan_findings/<fingerprint>",
│   │                _to: "weaknesses/<cwe_key>",
│   │                tenant_id, cwe_source="extracted", source="rule_engine"}
│   └── appends to edges batch
└── db.collection("finding_maps_to_weakness").import_bulk(edges, on_duplicate="update")  [IO]
```

### Fallback Path (CWE Not in Reference DB)

```text
[FALLBACK] CWE doc not in weaknesses collection
→ edge stored with _to: "weaknesses/CWE_<N>" (ArangoDB allows dangling edge)
  log.debug("CWE may not be in reference DB, edge created anyway", cwe_id=...)
  # Tier 1 AQL traversals skip non-existent vertices automatically
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `N/A` (skip-on-empty is handled, not an error)

---

## UC-008: finding_triggers_req Edge via AQL CWE Lookup

### Goal
Create `finding_triggers_req` edges linking findings to regulatory requirements, resolved by CWE traversal in reference DB.

### Preconditions
- `scan_findings` upserted; CWE IDs available on findings
- Reference DB has CWE→regulatory_requirement mapping (via existing graph edges)

### Expected Outcome
For findings with CWEs that map to requirements, `finding_triggers_req` edges exist.

### Primary Runtime Call Stack

```text
complira_graph/ingestion/edge_service.py:EvidenceEdgeService.create_finding_req_edges(
    v22_findings, tenant_id, ref_db
)
├── collect all unique CWE keys from v22_findings
├── ref_db.aql.execute("""
│       FOR cwe_key IN @cwe_keys
│           FOR req IN 1..2 OUTBOUND CONCAT("weaknesses/", cwe_key)
│               weakness_to_requirement, cwe_to_regulation
│               RETURN DISTINCT {cwe_key: cwe_key, req_key: req._key}
│   """, bind_vars={"cwe_keys": [...]})               [IO] # AQL lookup: CWE→req
│   └── returns: List[{cwe_key, req_key}]             [STATE]
│
├── build cwe_to_req_map: {cwe_key: [req_key, ...], ...}
├── for each finding:
│   ├── for each cwe_id in finding.cwe_ids:
│   │   ├── req_keys = cwe_to_req_map.get(normalize_cwe_id(cwe_id), [])
│   │   └── for each req_key:
│   │       ├── edge_key = generate_edge_key(finding.fingerprint, req_key, "triggers_req")
│   │       └── builds: {_key, _from: "scan_findings/<fingerprint>",
│   │                    _to: "regulatory_requirements/<req_key>",
│   │                    tenant_id, source="rule_engine"}
└── db.collection("finding_triggers_req").import_bulk(edges, on_duplicate="update")  [IO]
```

### Fallback Path (No CWE→req Mapping)

```text
[FALLBACK] AQL returns empty for all CWE keys
EvidenceEdgeService.create_finding_req_edges(...)
├── cwe_to_req_map is empty
└── log.info("No CWE→requirement mappings found in reference DB, skipping finding_triggers_req edges")
    return  # not an error
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `N/A`

---

## UC-009: finding_in_component Edge

### Goal
Link `scan_findings` to `components` when the finding has component context (purl).

### Primary Runtime Call Stack

```text
complira_graph/ingestion/edge_service.py:EvidenceEdgeService.create_finding_in_component_edges(
    v22_findings, tenant_id
)
├── for each finding where finding.purl is not None:
│   ├── comp_key = normalize_purl(finding.purl)
│   ├── edge_key = generate_edge_key(finding.fingerprint, comp_key, "in_component")
│   └── builds: {_key, _from: "scan_findings/<fingerprint>",
│                _to: "components/<comp_key>", tenant_id}
└── db.collection("finding_in_component").import_bulk(edges, on_duplicate="update")  [IO]
```

### Fallback Path (No purl on Finding)

```text
[FALLBACK] finding.purl is None (e.g. SAST finding with only file location)
→ skip: no finding_in_component edge created
  log.debug("No purl on finding, skipping finding_in_component edge", fingerprint=...)
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `N/A`

---

## UC-010: Detected Controls Stub Ingestion

### Goal
Provide skeleton `detected_controls` ingestion that can be populated by future scanners.

### Primary Runtime Call Stack

```text
complira_graph/ingestion/service.py:EvidenceIngestionService._ingest_detected_controls(
    parsed_data, scan_run_doc, tenant_id
)
├── detected_controls = parsed_data.metadata.get("detected_controls", [])
├── if not detected_controls:
│   └── log.debug("No detected_controls in parsed data, skipping")
│       return []
└── (future: normalise + upsert to detected_controls collection + create edges)
    # stub returns [] for now
```

### Coverage Status

- Primary Path: `Covered` (stub — returns empty list)
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## UC-011: Control Mapping Edges Stub (detected_control_maps_to + control_in_component)

### Goal
Provide skeleton edge creation for `detected_control_maps_to` and `control_in_component` once a scanner emits positive control detections. No current scanner emits this data — stub returns empty.

### Primary Runtime Call Stack

```text
complira_graph/ingestion/edge_service.py:EvidenceEdgeService.create_detected_control_edges(
    detected_controls, tenant_id
)
├── if not detected_controls:
│   └── log.debug("No detected controls, skipping control mapping edges")
│       return
└── (future: for each detected_control,
     create detected_control_maps_to edge → oscal_controls/<control_key>
     create control_in_component edge → components/<comp_key>)
    # stub returns for now
```

### Coverage Status

- Primary Path: `Covered` (stub — no-op for current scope)
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## UC-012: Evidence Package + Traceability Edges

### Goal
Create `evidence_packages` document + `evidence_links_finding` + `evidence_for_project` edges for regulatory submission.

### Primary Runtime Call Stack

```text
complira_graph/ingestion/service.py:EvidenceIngestionService._assemble_evidence_package(
    scan_run_doc, v22_findings, tenant_id, project_id
)
├── pkg_key = uuid4().hex
├── evidence_pkg = {
│       _key: pkg_key,
│       tenant_id: tenant_id,
│       scan_run_id: scan_run_doc["_key"],
│       project_id: project_id,
│       created_at: now_iso(),
│       package_type: "scan_run_evidence",
│       status: "active"
│   }
├── complira_graph/ingestion/repositories.py:EvidencePackageRepository.insert(evidence_pkg)  [IO]
│
├── complira_graph/ingestion/edge_service.py:EvidenceEdgeService.create_evidence_finding_edges(
│       pkg_key, v22_findings, tenant_id
│   )
│   ├── for each finding:
│   │   ├── edge_key = generate_edge_key(pkg_key, finding.fingerprint, "links_finding")
│   │   └── builds: {_key, _from: "evidence_packages/<pkg_key>",
│   │                _to: "scan_findings/<fingerprint>", tenant_id}
│   └── db.collection("evidence_links_finding").import_bulk(edges, on_duplicate="update")  [IO]
│
└── complira_graph/ingestion/edge_service.py:EvidenceEdgeService.create_evidence_project_edge(
        pkg_key, project_id, tenant_id
    )
    ├── if project_id is None: return
    ├── edge_key = generate_edge_key(pkg_key, project_id, "for_project")
    ├── builds: {_key, _from: "evidence_packages/<pkg_key>",
    │            _to: "projects/<project_id>", tenant_id}
    └── db.collection("evidence_for_project").import_bulk([edge], on_duplicate="update")  [IO]
```

### Error Path

```text
[ERROR] project_id None but evidence_for_project needed
→ log.info("No project_id, skipping evidence_for_project edge")
  evidence_package still created; evidence_links_finding edges still created
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `Covered`

---

## UC-012: Backfill Legacy Customer DB Data

### Goal
Migrate existing `scan_sessions` + `customer_components` from all customer DBs to reference DB `scan_runs` + `components`.

### Primary Runtime Call Stack

```text
[ENTRY] CLI / admin endpoint → BackfillAdapter.run(customer_ids: List[str])
├── for each customer_id in customer_ids:
│   ├── complira_graph/ingestion/backfill.py:BackfillAdapter._migrate_scan_sessions(
│   │       customer_id, ref_db
│   │   )
│   │   ├── cust_db = api/core/database.py:get_customer_db(customer_id)  [IO]
│   │   ├── docs = cust_db.collection("scan_sessions").all()              [IO]
│   │   ├── for each doc:
│   │   │   ├── new_doc = dict(doc)
│   │   │   ├── new_doc["tenant_id"] = new_doc.pop("customer_id")   # FIELD_MAP
│   │   │   ├── new_doc["tools_invoked"] = [new_doc.get("tool_name", "unknown")]
│   │   │   └── new_doc["finding_counts"] = {"total": new_doc.get("findings_count", 0)}
│   │   └── ref_db.collection("scan_runs").import_bulk(
│   │           new_docs, on_duplicate="update"
│   │       )                                                         [IO]
│   │
│   └── BackfillAdapter._migrate_components(customer_id, ref_db)
│       ├── cust_db.collection("customer_components").all()           [IO]
│       ├── for each component:
│       │   ├── new_doc = dict(component)
│       │   ├── purl_key = normalize_purl(new_doc["purl"])
│       │   ├── new_doc["_key"] = purl_key
│       │   └── remove customer_id (components are global — no tenant_id)
│       └── ref_db.collection("components").import_bulk(
│               new_docs, on_duplicate="update"
│           )                                                         [IO]
│
└── log.info("Backfill complete", customer_ids=..., scan_runs_migrated=..., components_migrated=...)
```

### Fallback Path (Customer DB Unreachable)

```text
[FALLBACK] get_customer_db(customer_id) fails
BackfillAdapter._migrate_scan_sessions(...)
└── log.error("Customer DB unreachable, skipping", customer_id=..., error=...)
    continue  # next customer_id
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `Covered`

---

## UC-013: Idempotent Re-Ingestion

### Goal
Re-ingesting the same scan payload produces updates not duplicates across all collections and edge collections.

### Primary Runtime Call Stack

```text
[ENTRY] POST /v1/scan/ingest (second call, same payload)
├── EvidenceIngestionService.ingest_scan(...)
│   ├── EvidenceRunRepository.create_run(...)
│   │   └── new scan_run _key (UUID) — each run gets its own record  [IO]
│   │       # runs are not deduped by design — each invocation is a new pipeline run
│   │
│   ├── EvidenceFindingRepository.upsert_batch(v22_findings)
│   │   └── import_bulk(on_duplicate="update")
│   │       # fingerprint _key already exists → UPDATE (no new doc)  [IO]
│   │
│   ├── EvidenceComponentRepository.upsert_batch(v22_components)
│   │   └── import_bulk(on_duplicate="update")
│   │       # purl _key already exists → UPDATE (no new doc)         [IO]
│   │
│   └── EvidenceEdgeService.create_all_edges(...)
│       └── for each edge collection:
│           └── import_bulk(on_duplicate="update")
│               # generate_edge_key() produces same _key → UPDATE     [IO]
│               # no duplicate edges
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## UC-014: Ingestion Normalisation Applied (IngestionEngine Pipeline)

### Goal
Verify IngestionEngine executes all 9 normalisation steps correctly: severity mapping, CWE extraction, CVE validation, fingerprint generation — driven by adapter configuration (not hard-coded tool branches).

### Primary Runtime Call Stack

```text
complira_graph/ingestion/ingestion_engine.py:IngestionEngine.process(
        tool_name="semgrep", raw_file=..., scan_run_id, project_id, tenant_id
    )
├── adapter = ADAPTER_REGISTRY["semgrep"]                    [STATE]
│   # adapter["severity_map"] = {"ERROR": "high", "WARNING": "medium", ...}
│   # adapter["cwe_extract_pattern"] = r"(CWE-\d+)"
│   # adapter["fingerprint_fields"] = ["rule_id", "file_path", "line_number"]
│
├── for each raw finding:
│   ├── _classify_severity(adapter, raw)
│   │   └── adapter["severity_map"].get(raw["severity"])     [STATE]
│   │       # "ERROR" → "high"
│   │
│   ├── _extract_cwe(adapter, raw, doc)
│   │   └── re.findall(adapter["cwe_extract_pattern"], combined_text)  [STATE]
│   │       # ["CWE-79", "CWE-89"] extracted
│   │
│   ├── _validate(doc)
│   │   ├── CVE regex: re.match(r"^CVE-\d{4}-\d{4,}$", cve_id)  [STATE]
│   │   │   # invalid cve_id → moved to tool_vuln_id
│   │   └── required fields check (fingerprint, tool, finding_type, severity, ...)
│   │
│   └── _fingerprint(adapter, raw)
│       └── sha256(rule_id + "|" + file_path + "|" + line_number)  [STATE]
│           # deterministic, matches on_duplicate=update _key
│
└── returns: List[bundles with normalised documents]          [STATE]
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## UC-017: Checkov IaC Finding Ingestion (IngestionEngine Multi-Root Routing)

### Goal
Ingest Checkov output file with three result arrays (failed_checks → scan_findings, passed_checks → detected_controls, skipped_checks → audit_log) using the Checkov `ToolAdapter` entry in `ADAPTER_REGISTRY`.

### Preconditions
- Checkov JSON output available (single file containing `results.failed_checks`, `results.passed_checks`, `results.skipped_checks`)
- `scan_run_doc` created (UC-001)
- `ADAPTER_REGISTRY["checkov"]` configured with `multi_root`, `result_state_field="check_result.result"`, `result_routing`

### Expected Outcome
FAILED findings → `scan_findings` with IaC-specific fields; PASSED checks → `detected_controls`; SKIPPED checks → `scan_run.audit_log` list.

### Primary Runtime Call Stack

```text
[ENTRY] complira_graph/ingestion/service.py:EvidenceIngestionService._ingest_findings(
        raw_file, tool_name="checkov", scan_run_doc, tenant_id
    )
├── complira_graph/ingestion/ingestion_engine.py:IngestionEngine.process(
│       tool_name="checkov", raw_file=raw_bytes,
│       scan_run_id=scan_run_doc["_key"], project_id, tenant_id
│   )
│   ├── adapter = ADAPTER_REGISTRY["checkov"]             [STATE] # ToolAdapter dict
│   ├── _parse(adapter, raw_file)                         [STATE]
│   │   └── for root in adapter["multi_root"]:            # failed + passed + skipped arrays
│   │       └── jmespath(raw_json, root) → list of findings
│   │       └── total: List[dict] (all three arrays combined)
│   ├── [optionally] adapter["pre_process"](raw_findings) → raw_findings  [STATE]
│   ├── for each raw finding:
│   │   ├── _fingerprint(adapter, raw)                    [STATE]
│   │   │   └── sha256(check_id + "|" + file_path + "|" + resource)[:32]
│   │   ├── _classify_severity(adapter, raw)              [STATE]
│   │   │   └── adapter["severity_map"].get(raw["severity"], None)
│   │   │       # None if severity absent (no --bc-api-key)
│   │   ├── _route(adapter, raw)                          [STATE]
│   │   │   ├── raw_state = _get_field(raw, "check_result.result")
│   │   │   │   # nested: raw["check_result"]["result"] → "FAILED" | "PASSED" | "SKIPPED"
│   │   │   └── adapter["result_routing"][raw_state]
│   │   │       # FAILED → "scan_findings"
│   │   │       # PASSED → "detected_controls"
│   │   │       # SKIPPED → "audit_log"
│   │   ├── _map_fields(adapter, raw)                     [STATE]
│   │   │   └── check_id, check_name, check_result, check_class,
│   │   │       file_path, line_start, line_end,
│   │   │       resource_address (from raw["resource"]),
│   │   │       guideline, bc_check_id, severity,
│   │   │       iac_framework (from "@check_type" injection — adapter caller injects)
│   │   ├── _extract_cwe(adapter, raw, doc)               [STATE]
│   │   │   └── adapter["cwe_source"] = "absent" → cwe_ids=[], source="absent"
│   │   ├── _redact(adapter, doc)                         [STATE]
│   │   │   └── no-op (adapter["secret_raw_field"] is None)
│   │   ├── _validate(doc)                                [STATE]
│   │   └── _plan_edges(adapter, doc) → List[edge_dict]  [STATE]
│   │       # see UC-018 for finding_triggers_req edge planning
│   └── returns: List[{"collection": "scan_findings"|"detected_controls"|"audit_log",
│                       "document": dict, "edges": list}]  [STATE]
│
├── for each bundle where bundle["collection"] == "scan_findings":
│   └── EvidenceFindingRepository.upsert_batch([bundle["document"]])  [IO]
│       └── import_bulk(on_duplicate="update", _key=fingerprint)
│
├── for each bundle where bundle["collection"] == "detected_controls":
│   └── EvidenceDetectedControlRepository.upsert_batch([bundle["document"]])  [IO]
│       └── import_bulk(on_duplicate="update")
│
└── for each bundle where bundle["collection"] == "audit_log":
    └── EvidenceRunRepository.append_audit_log(
            scan_run_key, entries=[bundle["document"]]
        )                                                  [IO]
        └── UPDATE scan_runs, PUSH to audit_log array
```

### Fallback Path

```text
[FALLBACK] Checkov SCA framework detected:
IngestionEngine._route() + IngestionEngine._validate() in caller:
├── adapter["checkov_framework_map"]["sca_package"] → "route_to_component_has_vuln"
│   # Service checks bundle["collection"] for this signal
│   └── EvidenceEdgeService.create_component_has_vuln_edges(bundle["document"])
│       # routes through UC-006 path instead
└── adapter["checkov_framework_map"]["secrets"] → "route_to_secret_findings"
    └── Bundle stored in scan_findings with finding_type="secret"
```

### Error Path

```text
[ERROR] import_bulk fails (schema validator rejects Checkov doc):
└── log.error("Checkov bulk insert failed for collection", collection=..., error=...)
    raise  # propagates to service → scan_run marked failed
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered` (SCA + secrets rerouting)
- Error Path: `Covered`

---

## UC-018: checkov_native finding_triggers_req Edge (bc_check_id Present/Absent)

### Goal
Create `finding_triggers_req` edges for Checkov FAILED findings using `bc_check_id` when available (deterministic `checkov_native` source), falling back to `llm_reg_mapper` when absent (open-source Checkov without `--bc-api-key`).

### Preconditions
- Checkov FAILED findings ingested to `scan_findings` (UC-017)
- Adapter `req_mapping_source="checkov_native"` and `deterministic_req_fields=["bc_check_id"]`

### Expected Outcome
Findings with `bc_check_id` → `finding_triggers_req` edge with `source="checkov_native"`. Findings without `bc_check_id` → `source="llm_reg_mapper"` (or no edge if LLM mapper not invoked).

### Primary Runtime Call Stack

```text
[ENTRY] complira_graph/ingestion/ingestion_engine.py:IngestionEngine._plan_edges(
        adapter, doc
    )
├── req_src = adapter["req_mapping_source"]  # "checkov_native"
├── bc_check_id = doc.get("bc_check_id")
│
├── if bc_check_id:                           # --bc-api-key was used
│   └── edges.append({
│           "collection": "finding_triggers_req",
│           "_from":      f"scan_findings/{doc['fingerprint']}",
│           "_to":        None,  # resolved via bc_check_id lookup in edge_service
│           "source":     "checkov_native",
│           "bc_check_id": bc_check_id,
│           "confidence": None,  # deterministic, no confidence needed
│       })                                    [STATE]
│
├── else:                                     # open-source Checkov, no bc_check_id
│   └── edges.append({
│           "collection": "finding_triggers_req",
│           "_from":      f"scan_findings/{doc['fingerprint']}",
│           "_to":        None,
│           "source":     "llm_reg_mapper",
│           "bc_check_id": None,
│           "confidence": None,  # to be filled by LLM mapper agent
│       })                                    [STATE]
│
└── returns: edges list
    ↓
complira_graph/ingestion/edge_service.py:EvidenceEdgeService._resolve_checkov_req_edge(
        edge_plan, ref_db
    )
├── if edge_plan["source"] == "checkov_native":
│   ├── req_key = ref_db["bc_check_id_to_req"].get(bc_check_id)  [IO]
│   │   # or AQL: FOR r IN regulatory_requirements FILTER r.bc_check_id == @bc_check_id
│   │   ├── if req_key found:
│   │   │   └── edge_plan["_to"] = f"regulatory_requirements/{req_key}"
│   │   │       create edge in finding_triggers_req collection  [IO]
│   │   └── if req_key not found: skip edge, log warning
│
└── if edge_plan["source"] == "llm_reg_mapper":
    └── log.info("Queued for llm_reg_mapper agent")
        # edge deferred — LLM mapper agent handles async
```

### Fallback Path

```text
[FALLBACK] bc_check_id present but not found in reference DB:
EvidenceEdgeService._resolve_checkov_req_edge(...)
└── req_key not found → skip edge, log warning
    # Not an error — reference DB may not have all bc_check_ids indexed
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered` (bc_check_id absent → llm_reg_mapper; bc_check_id present but not in DB → skip)
- Error Path: `N/A`

---

## UC-019: Checkov PASSED → detected_controls Routing

### Goal
Route Checkov checks with `check_result.result == "PASSED"` to `detected_controls` collection, storing positive IaC compliance evidence.

### Preconditions
- Checkov output processed by `IngestionEngine` with Checkov adapter
- `_route()` returns `"detected_controls"` for PASSED results

### Expected Outcome
`detected_controls` doc created with `check_id`, `iac_framework`, `tenant_id`, `scan_run_id`; `detected_control_maps_to` stub edge placeholder.

### Primary Runtime Call Stack

```text
[ENTRY] IngestionEngine.process(...) — handling a PASSED check:
├── _route(adapter, raw):
│   ├── raw_state = _get_field(raw, "check_result.result") → "PASSED"
│   └── adapter["result_routing"]["PASSED"] → "detected_controls"  [STATE]
│
└── bundle = {
        "collection": "detected_controls",
        "document": {
            "_key": fingerprint,
            "check_id": raw["check_id"],
            "check_name": raw["check_name"],
            "iac_framework": iac_framework,   # from @check_type injection
            "file_path": raw["file_path"],
            "resource_address": raw["resource"],
            "tenant_id": tenant_id,
            "scan_run_id": scan_run_id,
            "triage_status": "compliant",
        },
        "edges": []  # stub — detected_control_maps_to deferred
    }
    ↓
EvidenceDetectedControlRepository.upsert_batch([bundle["document"]])  [IO]
└── db.collection("detected_controls").import_bulk(
        [doc], on_duplicate="update", _key=fingerprint
    )
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## DR-003: bc_check_id Absent Fallback (IngestionEngine Dynamic Source Resolution)

### Goal
Verify that when `bc_check_id` is absent from a Checkov finding (open-source without `--bc-api-key`), `IngestionEngine._plan_edges()` correctly falls back to `llm_reg_mapper` source without error.

### Design-Risk Objective
The `ToolAdapter["req_mapping_source"]` declares `"checkov_native"` as the intent, but the engine must dynamically override to `"llm_reg_mapper"` when the `bc_check_id` field is absent. If this logic is missing, findings without `bc_check_id` would attempt a checkov_native lookup that always fails, silently dropping the req edge.

### Expected Observable Outcome
`finding_triggers_req` edge planned with `source="llm_reg_mapper"` (not `"checkov_native"`) when `bc_check_id` is absent. Ingestion completes with `status=completed`. No engine error.

### Primary Runtime Call Stack

```text
IngestionEngine._plan_edges(adapter, doc):
├── req_src = adapter["req_mapping_source"]  # "checkov_native"
├── bc_check_id = doc.get("bc_check_id")     # None (absent)
├── deterministic_fields = adapter["deterministic_req_fields"]  # ["bc_check_id"]
│
├── # Dynamic override: declared source is checkov_native, but trigger field absent
│   effective_src = "llm_reg_mapper" if bc_check_id is None else "checkov_native"
│   # Rule: if all deterministic_req_fields are None/absent → fall back to llm_reg_mapper
│
└── edges.append({"source": "llm_reg_mapper", ...})  [STATE]
    # edge_service defers this to LLM mapper agent queue
→ returns without error
→ ingestion continues → scan_run completed
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered` (absent bc_check_id → llm_reg_mapper without error)
- Error Path: `N/A`

---

## DR-001: Multi-Tenant Data Isolation Boundary

### Goal
Verify that querying reference DB `scan_findings` with a different `tenant_id` returns no data from another tenant.

### Design-Risk Objective
`tenant_id` is stored on all evidence documents and has a composite index. If a query accidentally omits `tenant_id` filter, data leaks across tenants.

### Expected Observable Outcome
AQL query with wrong `tenant_id` returns empty result set. Composite index on `(tenant_id, scan_run_id)` makes this efficient.

### Primary Runtime Call Stack

```text
AQL query (example Tier 1 template execution):
FOR f IN scan_findings
    FILTER f.tenant_id == @tenant_id  # bind var enforced
    FILTER f.scan_run_id == @scan_run_id
    RETURN f
→ returns only records for that tenant  [IO]
# If @tenant_id is wrong, returns []
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `N/A`
- Error Path: `N/A`

---

## DR-002: AQL Edge Resolution Graceful Skip (finding_triggers_req)

### Goal
Verify that when CWE→requirement mapping is absent from reference DB, `finding_triggers_req` edge creation skips gracefully without failing the ingestion.

### Design-Risk Objective
The AQL lookup is the only external-DB-state dependency in the edge creation path. If the AQL returns nothing, the service must not error — it must silently skip.

### Expected Observable Outcome
Ingestion completes with `status=completed` even when no `finding_triggers_req` edges are created. Log entry at INFO level explains skip.

### Primary Runtime Call Stack

```text
EvidenceEdgeService.create_finding_req_edges(v22_findings, tenant_id, ref_db)
├── aql_result = ref_db.aql.execute(CWE→req traversal, bind_vars={"cwe_keys": [...]})  [IO]
├── cwe_to_req_map = {}  # empty — no mappings in reference DB
├── for each finding: req_keys = cwe_to_req_map.get(cwe_key, []) → []
│   └── no edges built
└── import_bulk([]) → no-op                                   [IO]
    log.info("No CWE→requirement mappings found, skipping finding_triggers_req")
    return
```

### Coverage Status

- Primary Path: `Covered`
- Fallback Path: `Covered`
- Error Path: `N/A`
