# Implementation Plan: SBOM Component Ingestion

**Ticket:** `sbom-component-ingestion`
**Scope:** Small
**Date:** 2026-03-22
**Status:** Draft (design basis for runtime call stacks)

---

## Architecture Sketch

Target layers and change boundaries:

```
API Endpoint (scan.py)
  └─ Extract dependencies_raw from payload         [C1 — Modify]
     └─ Pass to ingest_sbom(dependencies_raw=...)

Service (service.py)
  └─ ingest_sbom() accepts dependencies_raw        [C2 — Modify]
     └─ Calls edge_svc.create_depends_on_edges()

Edge Service (edge_service.py)
  └─ create_depends_on_edges()                     [C3 — Add]
     └─ PURL → normalize_purl() → _key
     └─ generate_edge_key() → deterministic _key
     └─ import_bulk(on_duplicate="update")

Model (evidence.py)
  └─ V22Component extended with supplier,          [C4 — Modify]
     licenses (list), hashes (list)

Service (service.py)
  └─ _build_component_docs() extraction updated    [C2 also]
     for supplier, licenses, hashes
```

**No new layers.** All changes extend existing patterns.

---

## Change Inventory

| ID | File | Change Type | Description |
| --- | --- | --- | --- |
| C1 | `src/api/v1/endpoints/scan.py` | Modify | Extract `dependencies_raw` from CycloneDX payload; pass to `ingest_sbom()` |
| C2 | `src/complira_graph/ingestion/service.py` | Modify | Add `dependencies_raw` param to `ingest_sbom()`; call `create_depends_on_edges()` after component upsert; extend `_build_component_docs()` for supplier/licenses/hashes |
| C3 | `src/complira_graph/ingestion/edge_service.py` | Modify (Add method) | Add `create_depends_on_edges(dependencies_raw, scan_run_key, tenant_id)` |
| C4 | `src/complira_graph/models/evidence.py` | Modify | Extend `V22Component` with `supplier: Optional[str]`, `licenses: Optional[list[str]]`, `hashes: Optional[list[dict]]` |
| C5 | `tests/unit/ingestion/test_sbom_ingestion.py` | Add | Unit tests covering all 14 ACs |

---

## Solution Sketch

### C1 — Endpoint (`scan.py`)

```python
if request.format == "cyclonedx" or request.scan_type == "sbom":
    components_raw = request.payload.get("components", [])
    dependencies_raw = request.payload.get("dependencies", [])   # NEW
    result = await svc.ingest_sbom(
        tenant_id=customer.id,
        components_raw=components_raw,
        dependencies_raw=dependencies_raw,                        # NEW
        sbom_format="cyclonedx",
        project_id=request.project_id,
        repository_id=request.repository_id,
    )
```

### C2 — Service (`service.py`)

```python
async def ingest_sbom(
    self,
    tenant_id: str,
    components_raw: list[dict],
    sbom_format: Optional[str] = None,
    dependencies_raw: list[dict] = [],    # NEW
    project_id: Optional[str] = None,
    repository_id: Optional[str] = None,
    scan_run_key: Optional[str] = None,
) -> ScanIngestResult:
    ...
    if component_docs and project_id:
        self._edge_svc.create_project_uses_component_edges(...)

    if dependencies_raw:                  # NEW
        self._edge_svc.create_depends_on_edges(
            dependencies_raw=dependencies_raw,
            scan_run_key=scan_run_key,
            tenant_id=tenant_id,
        )
    ...
```

**`_build_component_docs()` supplier/licenses/hashes extraction:**

```python
supplier_raw = raw.get("supplier") or {}
supplier = supplier_raw.get("name") if isinstance(supplier_raw, dict) else None

licenses_raw = raw.get("licenses") or []
licenses = [
    lic.get("license", {}).get("id") or lic.get("license", {}).get("name")
    for lic in licenses_raw
    if isinstance(lic, dict) and lic.get("license")
]

hashes_raw = raw.get("hashes") or []
hashes = [
    {"alg": h.get("alg"), "content": h.get("content")}
    for h in hashes_raw
    if isinstance(h, dict)
]
```

### C3 — Edge Service (`edge_service.py`)

```python
def create_depends_on_edges(
    self,
    dependencies_raw: list[dict],
    scan_run_key: str,
    tenant_id: str,
) -> None:
    edges: list[dict] = []
    for dep in dependencies_raw:
        from_purl = dep.get("ref")
        if not from_purl:
            continue
        from_key = normalize_purl(from_purl)
        for to_purl in dep.get("dependsOn") or []:
            to_key = normalize_purl(to_purl)
            edge_key = generate_edge_key(from_key, to_key, "depends_on")
            edges.append({
                "_key": edge_key,
                "_from": f"components/{from_key}",
                "_to": f"components/{to_key}",
                "tenant_id": tenant_id,
                "scan_run_id": scan_run_key,
            })
    if edges:
        self._db.collection("depends_on").import_bulk(edges, on_duplicate="update")
        log.info("depends_on.created", extra={"count": len(edges)})
```

### C4 — Model (`evidence.py`)

```python
class V22Component(BaseModel):
    ...
    supplier: Optional[str] = Field(None)
    licenses: Optional[list[str]] = Field(None)
    hashes: Optional[list[dict]] = Field(None)
```

---

## Requirement Traceability

| Requirement | Design Section | Use Case | Implementation |
| --- | --- | --- | --- |
| REQ-SBOM-001 | C4 + C2 | UC-SBOM-001 | V22Component extension + `_build_component_docs()` |
| REQ-SBOM-002 | C1 + C2 + C3 | UC-SBOM-002 | Endpoint extraction + service call + edge method |
| REQ-SBOM-003 | — | UC-SBOM-003 | No change; verified by test |
| REQ-SBOM-004 | C3 | UC-SBOM-004 | `normalize_purl()` used in C3 |
| REQ-SBOM-005 | C3 | UC-SBOM-005 | `import_bulk(on_duplicate="update")` + `generate_edge_key()` |
| REQ-SBOM-006 | C2 | UC-SBOM-001 | `len(component_docs)` already returned |
