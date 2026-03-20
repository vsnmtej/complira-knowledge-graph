"""
Integration tests for the evidence ingestion pipeline.

These tests require a live ArangoDB instance with the v2.2 schema applied.
Run with: uv run pytest tests/integration/ingestion/ -m integration

All tests are marked @pytest.mark.integration and are excluded from the
default unit/contract test runs.
"""

import json
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def semgrep_payload():
    """Minimal Semgrep JSON output for integration testing."""
    return json.dumps([
        {
            "check_id": "python.flask.security.injection.tainted-sql-string",
            "path": "app/views.py",
            "start": {"line": 42, "col": 8},
            "end": {"line": 42, "col": 60},
            "extra": {
                "message": "Possible SQL injection via string formatting.",
                "severity": "ERROR",
                "metadata": {
                    "cwe": ["CWE-89: Improper Neutralization of Special Elements"],
                },
            },
        }
    ]).encode()


@pytest.fixture
def checkov_payload():
    """Minimal Checkov JSON output for integration testing."""
    return json.dumps({
        "check_type": "terraform",
        "results": {
            "failed_checks": [
                {
                    "check_id": "CKV_AWS_6",
                    "bc_check_id": "BC_AWS_GENERAL_2",
                    "check_result": {"result": "FAILED"},
                    "resource": "aws_s3_bucket.data",
                    "file_path": "main.tf",
                    "file_line_range": [10, 25],
                    "description": "Ensure S3 bucket has access control list (ACL) enabled",
                }
            ],
            "passed_checks": [],
            "skipped_checks": [],
        },
    }).encode()


@pytest.fixture
def cyclonedx_components():
    """Minimal CycloneDX SBOM component list for integration testing."""
    return [
        {
            "purl": "pkg:npm/express@4.18.2",
            "name": "express",
            "version": "4.18.2",
            "type": "library",
        },
        {
            "purl": "pkg:pypi/flask@2.0.3",
            "name": "flask",
            "version": "2.0.3",
            "type": "library",
        },
    ]


# ---------------------------------------------------------------------------
# EvidenceIngestionService — ingest_scan
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestIngestScanIntegration:
    """Integration tests for EvidenceIngestionService.ingest_scan."""

    @pytest.mark.asyncio
    async def test_semgrep_ingest_creates_scan_run(self, ref_db, tenant_id, semgrep_payload):
        """
        AC-001: ingest_scan creates a scan_runs document with status=completed.

        Given: Semgrep JSON payload
        When:  ingest_scan() is called
        Then:  scan_runs document exists with status=completed and findings_count >= 1
        """
        from complira_graph.ingestion.service import EvidenceIngestionService

        svc = EvidenceIngestionService(ref_db)
        result = await svc.ingest_scan(
            tenant_id=tenant_id,
            tool_name="semgrep",
            raw_payload=semgrep_payload,
        )

        assert result.status == "completed"
        assert result.scan_run_id is not None
        assert result.findings_count >= 1

        # Verify the scan_run document exists in the DB
        run_doc = ref_db.collection("scan_runs").get(result.scan_run_id)
        assert run_doc is not None
        assert run_doc["status"] == "completed"
        assert run_doc["tenant_id"] == tenant_id

    @pytest.mark.asyncio
    async def test_semgrep_ingest_creates_scan_findings(self, ref_db, tenant_id, semgrep_payload):
        """
        AC-002: scan_findings documents are created with correct fingerprint _key.

        Given: Semgrep JSON payload
        When:  ingest_scan() is called
        Then:  at least one scan_findings document exists with tenant_id and fingerprint
        """
        from complira_graph.ingestion.service import EvidenceIngestionService

        svc = EvidenceIngestionService(ref_db)
        result = await svc.ingest_scan(
            tenant_id=tenant_id,
            tool_name="semgrep",
            raw_payload=semgrep_payload,
        )

        # Query findings for this scan run
        cursor = ref_db.aql.execute(
            "FOR f IN scan_findings FILTER f.scan_run_id == @run_id RETURN f",
            bind_vars={"run_id": result.scan_run_id},
        )
        findings = list(cursor)
        assert len(findings) >= 1
        f = findings[0]
        assert f["tenant_id"] == tenant_id
        assert f.get("fingerprint") is not None
        assert f["_key"] == f["fingerprint"]

    @pytest.mark.asyncio
    async def test_checkov_failed_routes_to_scan_findings(self, ref_db, tenant_id, checkov_payload):
        """
        AC-003: Checkov FAILED checks are routed to scan_findings.

        Given: Checkov output with one failed check
        When:  ingest_scan() is called
        Then:  one scan_findings document exists
        """
        from complira_graph.ingestion.service import EvidenceIngestionService

        svc = EvidenceIngestionService(ref_db)
        result = await svc.ingest_scan(
            tenant_id=tenant_id,
            tool_name="checkov",
            raw_payload=checkov_payload,
        )

        assert result.status == "completed"
        cursor = ref_db.aql.execute(
            "FOR f IN scan_findings FILTER f.scan_run_id == @run_id RETURN f",
            bind_vars={"run_id": result.scan_run_id},
        )
        findings = list(cursor)
        assert len(findings) == 1
        assert findings[0].get("resource_address") is not None

    @pytest.mark.asyncio
    async def test_ingest_fail_marks_run_failed(self, ref_db, tenant_id):
        """
        AC-004: An unsupported tool_name causes fail_run() to be called.

        Given: An unknown tool name
        When:  ingest_scan() raises ValueError
        Then:  the scan_run document has status=failed
        """
        from complira_graph.ingestion.service import EvidenceIngestionService

        svc = EvidenceIngestionService(ref_db)
        with pytest.raises(ValueError):
            await svc.ingest_scan(
                tenant_id=tenant_id,
                tool_name="nonexistent_tool",
                raw_payload=b"[]",
            )

        # The run should still exist as failed
        cursor = ref_db.aql.execute(
            "FOR r IN scan_runs FILTER r.tenant_id == @tid AND r.status == 'failed' "
            "SORT r.created_at DESC LIMIT 1 RETURN r",
            bind_vars={"tid": tenant_id},
        )
        failed_runs = list(cursor)
        assert len(failed_runs) == 1
        assert failed_runs[0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_re_ingestion_is_idempotent(self, ref_db, tenant_id, semgrep_payload):
        """
        AC-005: Re-ingesting the same payload produces identical _key (idempotent upsert).

        Given: Semgrep payload ingested twice
        When:  ingest_scan() is called a second time with the same payload
        Then:  finding _keys are identical (no duplicates in scan_findings)
        """
        from complira_graph.ingestion.service import EvidenceIngestionService

        svc = EvidenceIngestionService(ref_db)

        result1 = await svc.ingest_scan(
            tenant_id=tenant_id, tool_name="semgrep", raw_payload=semgrep_payload
        )
        cursor1 = ref_db.aql.execute(
            "FOR f IN scan_findings FILTER f.scan_run_id == @run_id RETURN f._key",
            bind_vars={"run_id": result1.scan_run_id},
        )
        keys1 = set(cursor1)

        result2 = await svc.ingest_scan(
            tenant_id=tenant_id, tool_name="semgrep", raw_payload=semgrep_payload
        )
        cursor2 = ref_db.aql.execute(
            "FOR f IN scan_findings FILTER f.scan_run_id == @run_id RETURN f._key",
            bind_vars={"run_id": result2.scan_run_id},
        )
        keys2 = set(cursor2)

        # Same fingerprint _keys — idempotent
        assert keys1 == keys2


# ---------------------------------------------------------------------------
# EvidenceIngestionService — ingest_sbom
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestIngestSbomIntegration:
    """Integration tests for EvidenceIngestionService.ingest_sbom."""

    @pytest.mark.asyncio
    async def test_sbom_ingest_creates_components(
        self, ref_db, tenant_id, cyclonedx_components
    ):
        """
        AC-006: ingest_sbom creates components documents (purl-keyed, global).

        Given: Two CycloneDX components
        When:  ingest_sbom() is called
        Then:  two components documents exist in reference DB with purl-based _key
        """
        from complira_graph.ingestion.service import EvidenceIngestionService

        svc = EvidenceIngestionService(ref_db)
        result = await svc.ingest_sbom(
            tenant_id=tenant_id,
            components_raw=cyclonedx_components,
            sbom_format="cyclonedx",
        )

        assert result.components_count == 2
        # Verify global components (no tenant_id on document)
        cursor = ref_db.aql.execute(
            "FOR c IN components FILTER c.purl IN @purls RETURN c",
            bind_vars={"purls": [c["purl"] for c in cyclonedx_components]},
        )
        docs = list(cursor)
        assert len(docs) == 2
        for d in docs:
            assert "tenant_id" not in d  # components are global

    @pytest.mark.asyncio
    async def test_sbom_ingest_creates_project_uses_component_edges(
        self, ref_db, tenant_id, cyclonedx_components
    ):
        """
        AC-007: project_uses_component edges are created when project_id is provided.

        Given: Two components and a project_id
        When:  ingest_sbom() is called with project_id
        Then:  two project_uses_component edges exist linking project to components
        """
        from complira_graph.ingestion.service import EvidenceIngestionService

        project_id = "test_proj_integration"
        svc = EvidenceIngestionService(ref_db)
        await svc.ingest_sbom(
            tenant_id=tenant_id,
            components_raw=cyclonedx_components,
            sbom_format="cyclonedx",
            project_id=project_id,
        )

        cursor = ref_db.aql.execute(
            "FOR e IN project_uses_component FILTER e._from == @proj RETURN e",
            bind_vars={"proj": f"projects/{project_id}"},
        )
        edges = list(cursor)
        assert len(edges) == 2
        for e in edges:
            assert e["tenant_id"] == tenant_id
            assert e["source"] == "sbom"


# ---------------------------------------------------------------------------
# BackfillAdapter
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestBackfillAdapterIntegration:
    """Integration tests for BackfillAdapter migration."""

    def test_backfill_migrates_scan_sessions_to_scan_runs(
        self, ref_db, tenant_id, mock_customer_db
    ):
        """
        AC-008: BackfillAdapter migrates scan_sessions → scan_runs with field renames.

        Given: A customer DB with one scan_session document
        When:  BackfillAdapter.run() is called
        Then:  one scan_runs document exists in ref DB with tenant_id (not customer_id)
        """
        from complira_graph.ingestion.backfill import BackfillAdapter

        adapter = BackfillAdapter(ref_db)
        result = adapter.run(
            [tenant_id], get_customer_db_fn=lambda cid: mock_customer_db
        )

        assert result["errors"] == 0
        assert result["scan_runs_migrated"] >= 1

    def test_backfill_migrates_components_without_tenant_id(
        self, ref_db, tenant_id, mock_customer_db_with_components
    ):
        """
        AC-009: BackfillAdapter migrates components globally (no tenant_id on doc).

        Given: A customer DB with one component with a purl
        When:  BackfillAdapter.run() is called
        Then:  components document exists in ref DB without tenant_id or customer_id
        """
        from complira_graph.ingestion.backfill import BackfillAdapter

        adapter = BackfillAdapter(ref_db)
        adapter.run(
            [tenant_id], get_customer_db_fn=lambda cid: mock_customer_db_with_components
        )

        cursor = ref_db.aql.execute(
            "FOR c IN components FILTER c.purl == 'pkg:npm/react@18.0.0' RETURN c"
        )
        docs = list(cursor)
        assert len(docs) >= 1
        assert "tenant_id" not in docs[0]
        assert "customer_id" not in docs[0]
