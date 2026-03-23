"""
Unit tests for SBOM component ingestion.

Covers all 14 ACs (AC-SBOM-001 through AC-SBOM-014):
  - AC-SBOM-001: 3 components → 3 upsert docs
  - AC-SBOM-002: component fields (purl, name, version, type)
  - AC-SBOM-003: supplier extracted from supplier.name
  - AC-SBOM-004: licenses extracted as full list
  - AC-SBOM-005: hashes extracted as list of {alg, content}
  - AC-SBOM-006: 2 dependency entries → 2 depends_on edges
  - AC-SBOM-007: depends_on edge fields (_from, _to, tenant_id, scan_run_id)
  - AC-SBOM-008: empty dependsOn list → no edges for that ref
  - AC-SBOM-009: project_id → project_uses_component edges created
  - AC-SBOM-010: no project_id → no project_uses_component edges
  - AC-SBOM-011: PURL normalization (npm/lodash → key)
  - AC-SBOM-012: fallback PURL from name@version
  - AC-SBOM-013: idempotent re-ingest (import_bulk called with on_duplicate="update")
  - AC-SBOM-014: components_count returned correctly
"""

import asyncio
import pytest
from unittest.mock import MagicMock, call

from complira_graph.ingestion.service import EvidenceIngestionService, ScanIngestResult
from complira_graph.ingestion.edge_service import EvidenceEdgeService
from complira_graph.utils.keys import normalize_purl, generate_edge_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_svc():
    """Build EvidenceIngestionService with mocked sub-components."""
    from unittest.mock import patch

    db = MagicMock()

    with patch("complira_graph.ingestion.service.IngestionEngine"), \
         patch("complira_graph.ingestion.service.EvidenceRunRepository") as MockRunRepo, \
         patch("complira_graph.ingestion.service.EvidenceFindingRepository"), \
         patch("complira_graph.ingestion.service.EvidenceComponentRepository") as MockCompRepo, \
         patch("complira_graph.ingestion.service.EvidenceDetectedControlRepository"), \
         patch("complira_graph.ingestion.service.EvidenceEdgeService") as MockEdgeSvc:

        run_repo = MockRunRepo.return_value
        run_repo.create_run.return_value = {"_key": "run-001"}
        run_repo.complete_run.return_value = None

        comp_repo = MockCompRepo.return_value
        comp_repo.upsert_batch.return_value = {"created": 3, "updated": 0}

        edge_svc = MockEdgeSvc.return_value

        svc = EvidenceIngestionService(db)
        return svc, run_repo, comp_repo, edge_svc


def _make_edge_svc():
    """Build EvidenceEdgeService with mocked DB."""
    db = MagicMock()
    col = MagicMock()
    col.import_bulk.return_value = {"created": 1}
    db.collection.return_value = col
    return EvidenceEdgeService(db), db, col


_THREE_COMPONENTS = [
    {
        "purl": "pkg:npm/lodash@4.17.21",
        "name": "lodash",
        "version": "4.17.21",
        "type": "library",
        "supplier": {"name": "Lodash Contributors"},
        "licenses": [{"license": {"id": "MIT"}}],
        "hashes": [{"alg": "SHA-256", "content": "abc123"}],
    },
    {
        "purl": "pkg:npm/express@4.18.0",
        "name": "express",
        "version": "4.18.0",
        "type": "library",
    },
    {
        "purl": "pkg:npm/axios@1.3.0",
        "name": "axios",
        "version": "1.3.0",
        "type": "library",
    },
]

_TWO_DEPENDENCIES = [
    {
        "ref": "pkg:npm/lodash@4.17.21",
        "dependsOn": ["pkg:npm/express@4.18.0"],
    },
    {
        "ref": "pkg:npm/express@4.18.0",
        "dependsOn": ["pkg:npm/axios@1.3.0"],
    },
]


# ---------------------------------------------------------------------------
# AC-SBOM-001: 3 components → 3 docs in upsert batch
# ---------------------------------------------------------------------------

class TestComponentCount:
    def test_three_components_produces_three_docs(self):
        """AC-SBOM-001"""
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        result = _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=_THREE_COMPONENTS,
            sbom_format="cyclonedx",
        ))
        call_args = comp_repo.upsert_batch.call_args[0][0]
        assert len(call_args) == 3

    def test_components_count_returned(self):
        """AC-SBOM-014"""
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        result = _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=_THREE_COMPONENTS,
            sbom_format="cyclonedx",
        ))
        assert result.components_count == 3
        assert isinstance(result, ScanIngestResult)


# ---------------------------------------------------------------------------
# AC-SBOM-002: component fields purl, name, version, type
# ---------------------------------------------------------------------------

class TestComponentFields:
    def _get_docs(self):
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=_THREE_COMPONENTS,
            sbom_format="cyclonedx",
        ))
        return comp_repo.upsert_batch.call_args[0][0]

    def test_component_has_purl(self):
        """AC-SBOM-002"""
        docs = self._get_docs()
        assert docs[0]["purl"] == "pkg:npm/lodash@4.17.21"

    def test_component_has_name(self):
        """AC-SBOM-002"""
        docs = self._get_docs()
        assert docs[0]["name"] == "lodash"

    def test_component_has_version(self):
        """AC-SBOM-002"""
        docs = self._get_docs()
        assert docs[0]["version"] == "4.17.21"

    def test_component_has_type(self):
        """AC-SBOM-002"""
        docs = self._get_docs()
        assert docs[0]["type"] == "library"


# ---------------------------------------------------------------------------
# AC-SBOM-003: supplier from supplier.name
# ---------------------------------------------------------------------------

class TestSupplierExtraction:
    def test_supplier_extracted_from_supplier_name(self):
        """AC-SBOM-003"""
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=[_THREE_COMPONENTS[0]],
            sbom_format="cyclonedx",
        ))
        docs = comp_repo.upsert_batch.call_args[0][0]
        assert docs[0]["supplier"] == "Lodash Contributors"

    def test_supplier_absent_when_not_set(self):
        """AC-SBOM-003 — no supplier field"""
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=[_THREE_COMPONENTS[1]],
            sbom_format="cyclonedx",
        ))
        docs = comp_repo.upsert_batch.call_args[0][0]
        assert "supplier" not in docs[0]


# ---------------------------------------------------------------------------
# AC-SBOM-004: licenses extracted as full list
# ---------------------------------------------------------------------------

class TestLicensesExtraction:
    def test_licenses_extracted_as_list(self):
        """AC-SBOM-004"""
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=[_THREE_COMPONENTS[0]],
            sbom_format="cyclonedx",
        ))
        docs = comp_repo.upsert_batch.call_args[0][0]
        assert docs[0]["licenses"] == ["MIT"]

    def test_multiple_licenses_extracted(self):
        """AC-SBOM-004 — multiple licenses"""
        raw = {
            "purl": "pkg:npm/dual@1.0.0",
            "name": "dual",
            "version": "1.0.0",
            "type": "library",
            "licenses": [
                {"license": {"id": "MIT"}},
                {"license": {"name": "Apache-2.0"}},
            ],
        }
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(tenant_id="t1", components_raw=[raw], sbom_format="cyclonedx"))
        docs = comp_repo.upsert_batch.call_args[0][0]
        assert docs[0]["licenses"] == ["MIT", "Apache-2.0"]

    def test_licenses_absent_when_not_set(self):
        """AC-SBOM-004 — no licenses"""
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=[_THREE_COMPONENTS[1]],
            sbom_format="cyclonedx",
        ))
        docs = comp_repo.upsert_batch.call_args[0][0]
        assert "licenses" not in docs[0]


# ---------------------------------------------------------------------------
# AC-SBOM-005: hashes extracted as {alg, content} list
# ---------------------------------------------------------------------------

class TestHashesExtraction:
    def test_hashes_extracted_as_list(self):
        """AC-SBOM-005"""
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=[_THREE_COMPONENTS[0]],
            sbom_format="cyclonedx",
        ))
        docs = comp_repo.upsert_batch.call_args[0][0]
        assert docs[0]["hashes"] == [{"alg": "SHA-256", "content": "abc123"}]

    def test_hashes_absent_when_not_set(self):
        """AC-SBOM-005 — no hashes"""
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=[_THREE_COMPONENTS[1]],
            sbom_format="cyclonedx",
        ))
        docs = comp_repo.upsert_batch.call_args[0][0]
        assert "hashes" not in docs[0]


# ---------------------------------------------------------------------------
# AC-SBOM-006/007: 2 dependency entries → 2 depends_on edges with correct fields
# ---------------------------------------------------------------------------

class TestDependsOnEdges:
    def test_two_dependencies_produce_two_edges(self):
        """AC-SBOM-006"""
        svc_obj, db, col = _make_edge_svc()
        svc_obj.create_depends_on_edges(
            dependencies_raw=_TWO_DEPENDENCIES,
            scan_run_key="run-001",
            tenant_id="t1",
        )
        col.import_bulk.assert_called_once()
        edges = col.import_bulk.call_args[0][0]
        assert len(edges) == 2

    def test_depends_on_edge_fields(self):
        """AC-SBOM-007"""
        svc_obj, db, col = _make_edge_svc()
        svc_obj.create_depends_on_edges(
            dependencies_raw=[_TWO_DEPENDENCIES[0]],
            scan_run_key="run-001",
            tenant_id="t1",
        )
        edges = col.import_bulk.call_args[0][0]
        edge = edges[0]
        from_key = normalize_purl("pkg:npm/lodash@4.17.21")
        to_key = normalize_purl("pkg:npm/express@4.18.0")
        assert edge["_from"] == f"components/{from_key}"
        assert edge["_to"] == f"components/{to_key}"
        assert edge["tenant_id"] == "t1"
        assert edge["scan_run_id"] == "run-001"

    def test_empty_depends_on_list_produces_no_edges(self):
        """AC-SBOM-008"""
        svc_obj, db, col = _make_edge_svc()
        svc_obj.create_depends_on_edges(
            dependencies_raw=[{"ref": "pkg:npm/lodash@4.17.21", "dependsOn": []}],
            scan_run_key="run-001",
            tenant_id="t1",
        )
        col.import_bulk.assert_not_called()

    def test_missing_ref_is_skipped(self):
        """AC-SBOM-007 — malformed dep without ref"""
        svc_obj, db, col = _make_edge_svc()
        svc_obj.create_depends_on_edges(
            dependencies_raw=[{"dependsOn": ["pkg:npm/express@4.18.0"]}],
            scan_run_key="run-001",
            tenant_id="t1",
        )
        col.import_bulk.assert_not_called()

    def test_depends_on_uses_correct_collection(self):
        """AC-SBOM-007 — writes to 'depends_on' collection"""
        svc_obj, db, col = _make_edge_svc()
        svc_obj.create_depends_on_edges(
            dependencies_raw=_TWO_DEPENDENCIES,
            scan_run_key="run-001",
            tenant_id="t1",
        )
        db.collection.assert_called_with("depends_on")

    def test_idempotent_depends_on_uses_on_duplicate_update(self):
        """AC-SBOM-013 — edges use on_duplicate=update"""
        svc_obj, db, col = _make_edge_svc()
        svc_obj.create_depends_on_edges(
            dependencies_raw=_TWO_DEPENDENCIES,
            scan_run_key="run-001",
            tenant_id="t1",
        )
        _, kwargs = col.import_bulk.call_args
        assert kwargs.get("on_duplicate") == "update"


# ---------------------------------------------------------------------------
# AC-SBOM-009/010: project_uses_component edges
# ---------------------------------------------------------------------------

class TestProjectUsesComponentEdges:
    def test_project_uses_component_edges_with_project_id(self):
        """AC-SBOM-009"""
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=_THREE_COMPONENTS,
            sbom_format="cyclonedx",
            project_id="proj-001",
        ))
        edge_svc.create_project_uses_component_edges.assert_called_once()

    def test_no_project_uses_component_without_project_id(self):
        """AC-SBOM-010"""
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=_THREE_COMPONENTS,
            sbom_format="cyclonedx",
        ))
        edge_svc.create_project_uses_component_edges.assert_not_called()


# ---------------------------------------------------------------------------
# AC-SBOM-011: PURL normalization
# ---------------------------------------------------------------------------

class TestPurlNormalization:
    def test_purl_normalization_npm_lodash(self):
        """AC-SBOM-011"""
        key = normalize_purl("pkg:npm/lodash@4.17.21")
        assert key == "pkg_npm_lodash_4_17_21"

    def test_purl_normalization_as_component_key(self):
        """AC-SBOM-011 — component _key matches normalize_purl output"""
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=[_THREE_COMPONENTS[0]],
            sbom_format="cyclonedx",
        ))
        docs = comp_repo.upsert_batch.call_args[0][0]
        assert docs[0]["_key"] == normalize_purl("pkg:npm/lodash@4.17.21")


# ---------------------------------------------------------------------------
# AC-SBOM-012: fallback PURL from name@version
# ---------------------------------------------------------------------------

class TestFallbackPurl:
    def test_fallback_purl_from_name_version(self):
        """AC-SBOM-012"""
        raw = {"name": "mylib", "version": "1.0.0", "type": "library"}
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=[raw],
            sbom_format="cyclonedx",
        ))
        docs = comp_repo.upsert_batch.call_args[0][0]
        assert docs[0]["purl"] == "pkg:generic/mylib@1.0.0"
        assert docs[0]["_key"] == normalize_purl("pkg:generic/mylib@1.0.0")

    def test_component_no_purl_no_name_is_skipped(self):
        """AC-SBOM-012 — skip if no purl and no name"""
        raw = {"version": "1.0.0", "type": "library"}
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        result = _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=[raw],
            sbom_format="cyclonedx",
        ))
        assert result.components_count == 0
        comp_repo.upsert_batch.assert_not_called()


# ---------------------------------------------------------------------------
# AC-SBOM-013: idempotency (component upsert uses on_duplicate)
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_component_upsert_uses_on_duplicate(self):
        """AC-SBOM-013 — component docs use import_bulk with on_duplicate=update"""
        from complira_graph.ingestion.repositories import EvidenceComponentRepository
        db = MagicMock()
        col = MagicMock()
        col.import_bulk.return_value = {"created": 1, "updated": 0}
        db.collection.return_value = col
        repo = EvidenceComponentRepository(db)
        repo.upsert_batch([{"_key": "pkg_npm_lodash_4_17_21", "purl": "pkg:npm/lodash@4.17.21", "name": "lodash"}])
        _, kwargs = col.import_bulk.call_args
        assert kwargs.get("on_duplicate") == "update"


# ---------------------------------------------------------------------------
# Depends-on edge key determinism (idempotency via generate_edge_key)
# ---------------------------------------------------------------------------

class TestEdgeKeyDeterminism:
    def test_same_purl_pair_produces_same_edge_key(self):
        """AC-SBOM-013 — edge key is deterministic"""
        from_key = normalize_purl("pkg:npm/lodash@4.17.21")
        to_key = normalize_purl("pkg:npm/express@4.18.0")
        key1 = generate_edge_key(from_key, to_key, "depends_on")
        key2 = generate_edge_key(from_key, to_key, "depends_on")
        assert key1 == key2

    def test_different_purl_pairs_produce_different_keys(self):
        from_key = normalize_purl("pkg:npm/lodash@4.17.21")
        to_key_a = normalize_purl("pkg:npm/express@4.18.0")
        to_key_b = normalize_purl("pkg:npm/axios@1.3.0")
        key_a = generate_edge_key(from_key, to_key_a, "depends_on")
        key_b = generate_edge_key(from_key, to_key_b, "depends_on")
        assert key_a != key_b


# ---------------------------------------------------------------------------
# ingest_sbom dispatches depends_on edges when dependencies_raw provided
# ---------------------------------------------------------------------------

class TestIngestSbomDependsOnDispatch:
    def test_create_depends_on_edges_called_when_dependencies_provided(self):
        """AC-SBOM-006 via service layer"""
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=_THREE_COMPONENTS,
            dependencies_raw=_TWO_DEPENDENCIES,
            sbom_format="cyclonedx",
        ))
        edge_svc.create_depends_on_edges.assert_called_once_with(
            dependencies_raw=_TWO_DEPENDENCIES,
            scan_run_key="run-001",
            tenant_id="t1",
        )

    def test_create_depends_on_edges_not_called_when_no_dependencies(self):
        """AC-SBOM-006 — None dependencies → no edge call"""
        svc, run_repo, comp_repo, edge_svc = _make_svc()
        _run(svc.ingest_sbom(
            tenant_id="t1",
            components_raw=_THREE_COMPONENTS,
            sbom_format="cyclonedx",
        ))
        edge_svc.create_depends_on_edges.assert_not_called()
