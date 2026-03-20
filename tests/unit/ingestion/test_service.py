"""
Unit tests for ingestion/service.py.

Covers: EvidenceIngestionService.ingest_scan (finding pipeline path),
ingest_sbom (SBOM component path), fail_run on exception,
_count_by_severity, _build_component_docs.
All repo + engine + edge service calls are mocked.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call

from complira_graph.ingestion.service import EvidenceIngestionService, ScanIngestResult
from complira_graph.ingestion.ingestion_engine import IngestionBundle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_svc_with_mocks():
    """Build an EvidenceIngestionService with all sub-components mocked."""
    db = MagicMock()

    with patch("complira_graph.ingestion.service.IngestionEngine") as MockEngine, \
         patch("complira_graph.ingestion.service.EvidenceRunRepository") as MockRunRepo, \
         patch("complira_graph.ingestion.service.EvidenceFindingRepository") as MockFindRepo, \
         patch("complira_graph.ingestion.service.EvidenceComponentRepository") as MockCompRepo, \
         patch("complira_graph.ingestion.service.EvidenceDetectedControlRepository") as MockCtrlRepo, \
         patch("complira_graph.ingestion.service.EvidenceEdgeService") as MockEdgeSvc:

        svc = EvidenceIngestionService(db)
        return svc, {
            "engine": MockEngine.return_value,
            "run_repo": MockRunRepo.return_value,
            "finding_repo": MockFindRepo.return_value,
            "comp_repo": MockCompRepo.return_value,
            "ctrl_repo": MockCtrlRepo.return_value,
            "edge_svc": MockEdgeSvc.return_value,
        }


SEMGREP_PAYLOAD = b'[{"check_id":"sqli","path":"app.py","start":{"line":10},"extra":{"message":"SQL injection","severity":"ERROR","metadata":{}}}]'


# ---------------------------------------------------------------------------
# _count_by_severity (static helper)
# ---------------------------------------------------------------------------

class TestCountBySeverity:
    def test_counts_each_severity_level(self):
        findings = [
            {"severity": "critical"},
            {"severity": "high"},
            {"severity": "high"},
            {"severity": "medium"},
            {"severity": "low"},
            {"severity": "info"},
        ]
        counts = EvidenceIngestionService._count_by_severity(findings)
        assert counts == {"critical": 1, "high": 2, "medium": 1, "low": 1, "info": 1}

    def test_empty_list_returns_zeros(self):
        counts = EvidenceIngestionService._count_by_severity([])
        assert counts == {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}

    def test_unknown_severity_not_counted(self):
        findings = [{"severity": "blocker"}, {"severity": "high"}]
        counts = EvidenceIngestionService._count_by_severity(findings)
        assert counts["high"] == 1
        assert sum(counts.values()) == 1

    def test_case_insensitive(self):
        findings = [{"severity": "HIGH"}, {"severity": "Medium"}]
        counts = EvidenceIngestionService._count_by_severity(findings)
        assert counts["high"] == 1
        assert counts["medium"] == 1

    def test_none_severity_not_counted(self):
        findings = [{"severity": None}]
        counts = EvidenceIngestionService._count_by_severity(findings)
        assert sum(counts.values()) == 0


# ---------------------------------------------------------------------------
# _build_component_docs
# ---------------------------------------------------------------------------

class TestBuildComponentDocs:
    def setup_method(self):
        db = MagicMock()
        # create a real service instance for testing the static-ish helper
        with patch("complira_graph.ingestion.service.IngestionEngine"), \
             patch("complira_graph.ingestion.service.EvidenceRunRepository"), \
             patch("complira_graph.ingestion.service.EvidenceFindingRepository"), \
             patch("complira_graph.ingestion.service.EvidenceComponentRepository"), \
             patch("complira_graph.ingestion.service.EvidenceDetectedControlRepository"), \
             patch("complira_graph.ingestion.service.EvidenceEdgeService"):
            self.svc = EvidenceIngestionService(db)

    def test_converts_raw_component_with_purl(self):
        raw = [{"purl": "pkg:npm/express@4.18.2", "name": "express", "version": "4.18.2"}]
        docs = self.svc._build_component_docs(raw, "cyclonedx")
        assert len(docs) == 1
        assert docs[0]["purl"] == "pkg:npm/express@4.18.2"

    def test_generates_fallback_purl_when_missing(self):
        raw = [{"name": "my-lib", "version": "1.0.0"}]
        docs = self.svc._build_component_docs(raw, "cyclonedx")
        assert len(docs) == 1
        assert "pkg:generic/my-lib@1.0.0" in docs[0]["purl"]

    def test_skips_component_with_no_purl_no_name(self):
        raw = [{"version": "1.0.0", "type": "library"}]
        docs = self.svc._build_component_docs(raw, "cyclonedx")
        assert len(docs) == 0

    def test_sbom_format_stored_on_doc(self):
        raw = [{"purl": "pkg:pypi/flask@2.0.0", "name": "flask"}]
        docs = self.svc._build_component_docs(raw, "cyclonedx")
        assert docs[0]["sbom_format"] == "cyclonedx"

    def test_packageUrl_field_accepted(self):
        """CycloneDX uses packageUrl instead of purl in some formats."""
        raw = [{"packageUrl": "pkg:npm/react@18.0.0", "name": "react"}]
        docs = self.svc._build_component_docs(raw, "cyclonedx")
        assert len(docs) == 1
        assert "react" in docs[0]["purl"]

    def test_empty_licenses_list_does_not_raise(self):
        """F-001: licenses=[] must not raise IndexError; license field absent."""
        raw = [{"purl": "pkg:pypi/foo@1.0.0", "name": "foo", "licenses": []}]
        docs = self.svc._build_component_docs(raw, "cyclonedx")
        assert len(docs) == 1
        assert "license" not in docs[0]

    def test_none_licenses_does_not_raise(self):
        """F-001: licenses=None must not raise; license field absent."""
        raw = [{"purl": "pkg:pypi/bar@2.0.0", "name": "bar", "licenses": None}]
        docs = self.svc._build_component_docs(raw, "cyclonedx")
        assert len(docs) == 1
        assert "license" not in docs[0]

    def test_licenses_list_extracts_id(self):
        """F-001: licenses=[{...}] must correctly extract SPDX id."""
        raw = [{"purl": "pkg:pypi/baz@3.0.0", "name": "baz",
                "licenses": [{"license": {"id": "MIT"}}]}]
        docs = self.svc._build_component_docs(raw, "cyclonedx")
        assert len(docs) == 1
        assert docs[0]["license"] == "MIT"


# ---------------------------------------------------------------------------
# ingest_scan — happy path
# ---------------------------------------------------------------------------

class TestIngestScan:
    def _make_bundles(self, n_findings=2, n_controls=0):
        findings = [
            IngestionBundle(
                collection="scan_findings",
                document={"_key": f"fp{i}", "fingerprint": f"fp{i}", "severity": "high"},
                edges=[],
            )
            for i in range(n_findings)
        ]
        controls = [
            IngestionBundle(
                collection="detected_controls",
                document={"_key": f"ctrl{i}"},
                edges=[],
            )
            for i in range(n_controls)
        ]
        return findings + controls

    def test_returns_scan_ingest_result(self):
        db = MagicMock()
        with patch("complira_graph.ingestion.service.IngestionEngine") as MockEngine, \
             patch("complira_graph.ingestion.service.EvidenceRunRepository") as MockRunRepo, \
             patch("complira_graph.ingestion.service.EvidenceFindingRepository"), \
             patch("complira_graph.ingestion.service.EvidenceComponentRepository"), \
             patch("complira_graph.ingestion.service.EvidenceDetectedControlRepository"), \
             patch("complira_graph.ingestion.service.EvidenceEdgeService"):

            run_repo = MockRunRepo.return_value
            run_repo.create_run.return_value = {"_key": "run123"}

            engine = MockEngine.return_value
            engine.process.return_value = self._make_bundles(n_findings=3)

            db.collection.return_value = MagicMock()

            svc = EvidenceIngestionService(db)
            result = asyncio.get_event_loop().run_until_complete(
                svc.ingest_scan(
                    tenant_id="t1",
                    tool_name="semgrep",
                    raw_payload=SEMGREP_PAYLOAD,
                )
            )

        assert isinstance(result, ScanIngestResult)
        assert result.scan_run_id == "run123"
        assert result.findings_count == 3
        assert result.status == "completed"

    def test_complete_run_called_on_success(self):
        db = MagicMock()
        with patch("complira_graph.ingestion.service.IngestionEngine") as MockEngine, \
             patch("complira_graph.ingestion.service.EvidenceRunRepository") as MockRunRepo, \
             patch("complira_graph.ingestion.service.EvidenceFindingRepository"), \
             patch("complira_graph.ingestion.service.EvidenceComponentRepository"), \
             patch("complira_graph.ingestion.service.EvidenceDetectedControlRepository"), \
             patch("complira_graph.ingestion.service.EvidenceEdgeService"):

            run_repo = MockRunRepo.return_value
            run_repo.create_run.return_value = {"_key": "run456"}

            engine = MockEngine.return_value
            engine.process.return_value = self._make_bundles(n_findings=1)

            db.collection.return_value = MagicMock()

            svc = EvidenceIngestionService(db)
            asyncio.get_event_loop().run_until_complete(
                svc.ingest_scan(tenant_id="t1", tool_name="semgrep", raw_payload=b"[]")
            )

            run_repo.complete_run.assert_called_once()
            run_repo.fail_run.assert_not_called()


# ---------------------------------------------------------------------------
# ingest_scan — fail path
# ---------------------------------------------------------------------------

class TestIngestScanFailPath:
    def test_fail_run_called_on_engine_exception(self):
        db = MagicMock()
        with patch("complira_graph.ingestion.service.IngestionEngine") as MockEngine, \
             patch("complira_graph.ingestion.service.EvidenceRunRepository") as MockRunRepo, \
             patch("complira_graph.ingestion.service.EvidenceFindingRepository"), \
             patch("complira_graph.ingestion.service.EvidenceComponentRepository"), \
             patch("complira_graph.ingestion.service.EvidenceDetectedControlRepository"), \
             patch("complira_graph.ingestion.service.EvidenceEdgeService"):

            run_repo = MockRunRepo.return_value
            run_repo.create_run.return_value = {"_key": "run789"}

            engine = MockEngine.return_value
            engine.process.side_effect = ValueError("unsupported tool")

            svc = EvidenceIngestionService(db)
            with pytest.raises(ValueError, match="unsupported tool"):
                asyncio.get_event_loop().run_until_complete(
                    svc.ingest_scan(tenant_id="t1", tool_name="badtool", raw_payload=b"[]")
                )

            run_repo.fail_run.assert_called_once_with("run789", "unsupported tool")
            run_repo.complete_run.assert_not_called()

    def test_exception_is_reraised_after_fail_run(self):
        db = MagicMock()
        with patch("complira_graph.ingestion.service.IngestionEngine") as MockEngine, \
             patch("complira_graph.ingestion.service.EvidenceRunRepository") as MockRunRepo, \
             patch("complira_graph.ingestion.service.EvidenceFindingRepository"), \
             patch("complira_graph.ingestion.service.EvidenceComponentRepository"), \
             patch("complira_graph.ingestion.service.EvidenceDetectedControlRepository"), \
             patch("complira_graph.ingestion.service.EvidenceEdgeService"):

            run_repo = MockRunRepo.return_value
            run_repo.create_run.return_value = {"_key": "run_fail"}
            MockEngine.return_value.process.side_effect = RuntimeError("db error")

            svc = EvidenceIngestionService(db)
            with pytest.raises(RuntimeError, match="db error"):
                asyncio.get_event_loop().run_until_complete(
                    svc.ingest_scan(tenant_id="t1", tool_name="semgrep", raw_payload=b"[]")
                )


# ---------------------------------------------------------------------------
# ingest_sbom
# ---------------------------------------------------------------------------

class TestIngestSbom:
    def test_returns_components_count(self):
        db = MagicMock()
        with patch("complira_graph.ingestion.service.IngestionEngine"), \
             patch("complira_graph.ingestion.service.EvidenceRunRepository") as MockRunRepo, \
             patch("complira_graph.ingestion.service.EvidenceFindingRepository"), \
             patch("complira_graph.ingestion.service.EvidenceComponentRepository") as MockCompRepo, \
             patch("complira_graph.ingestion.service.EvidenceDetectedControlRepository"), \
             patch("complira_graph.ingestion.service.EvidenceEdgeService"):

            run_repo = MockRunRepo.return_value
            run_repo.create_run.return_value = {"_key": "sbom_run"}

            comp_repo = MockCompRepo.return_value
            comp_repo.upsert_batch.return_value = {"created": 3}

            svc = EvidenceIngestionService(db)
            raw_comps = [
                {"purl": "pkg:npm/react@18.0.0", "name": "react", "version": "18.0.0"},
                {"purl": "pkg:npm/axios@1.0.0", "name": "axios", "version": "1.0.0"},
                {"purl": "pkg:pypi/flask@2.0.0", "name": "flask", "version": "2.0.0"},
            ]
            result = asyncio.get_event_loop().run_until_complete(
                svc.ingest_sbom(tenant_id="t1", components_raw=raw_comps)
            )

        assert result.components_count == 3
        assert result.status == "completed"

    def test_skips_component_without_purl_or_name(self):
        db = MagicMock()
        with patch("complira_graph.ingestion.service.IngestionEngine"), \
             patch("complira_graph.ingestion.service.EvidenceRunRepository") as MockRunRepo, \
             patch("complira_graph.ingestion.service.EvidenceFindingRepository"), \
             patch("complira_graph.ingestion.service.EvidenceComponentRepository") as MockCompRepo, \
             patch("complira_graph.ingestion.service.EvidenceDetectedControlRepository"), \
             patch("complira_graph.ingestion.service.EvidenceEdgeService"):

            run_repo = MockRunRepo.return_value
            run_repo.create_run.return_value = {"_key": "sbom_run2"}

            comp_repo = MockCompRepo.return_value
            comp_repo.upsert_batch.return_value = {"created": 0}

            svc = EvidenceIngestionService(db)
            raw_comps = [{"version": "1.0", "type": "library"}]  # no purl, no name
            result = asyncio.get_event_loop().run_until_complete(
                svc.ingest_sbom(tenant_id="t1", components_raw=raw_comps)
            )

        assert result.components_count == 0

    def test_fail_run_called_on_sbom_exception(self):
        db = MagicMock()
        with patch("complira_graph.ingestion.service.IngestionEngine"), \
             patch("complira_graph.ingestion.service.EvidenceRunRepository") as MockRunRepo, \
             patch("complira_graph.ingestion.service.EvidenceFindingRepository"), \
             patch("complira_graph.ingestion.service.EvidenceComponentRepository") as MockCompRepo, \
             patch("complira_graph.ingestion.service.EvidenceDetectedControlRepository"), \
             patch("complira_graph.ingestion.service.EvidenceEdgeService"):

            run_repo = MockRunRepo.return_value
            run_repo.create_run.return_value = {"_key": "sbom_fail"}

            comp_repo = MockCompRepo.return_value
            comp_repo.upsert_batch.side_effect = RuntimeError("db write error")

            svc = EvidenceIngestionService(db)
            with pytest.raises(RuntimeError):
                asyncio.get_event_loop().run_until_complete(
                    svc.ingest_sbom(
                        tenant_id="t1",
                        components_raw=[{"purl": "pkg:npm/x@1.0", "name": "x"}],
                    )
                )

            run_repo.fail_run.assert_called_once_with("sbom_fail", "db write error")
