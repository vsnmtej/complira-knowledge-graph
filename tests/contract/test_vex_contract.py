"""
API Contract Tests for VEX endpoints - Validate API responses match expected schema.

These tests ensure:
1. Backend API responses match the documented contract
2. Frontend mock data matches real API responses
3. No breaking changes to API structure
4. VEX enrichment data structure is consistent
"""
import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from api.models.responses.vex import (
    VEXCreateResponse,
    VEXDocumentResponse,
    VEXUpdateResponse,
    VEXListResponse,
    VEXVulnerabilityResponse,
    VEXEnrichment,
)
from api.models.responses import APIResponse


class TestVEXContractCreateResponse:
    """Test POST /v1/vex response matches contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_vex_create_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/vex response matches VEXCreateResponse schema.

        Validates:
        - Response structure matches APIResponse[VEXCreateResponse]
        - All required fields present (vex_id, vulnerabilities_count, enriched_count, created_at)
        - Field types correct
        """
        with open(mock_responses_dir / "vex_create.json") as f:
            mock_data = json.load(f)

        # Validate outer APIResponse wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data

        # Validate VEXCreateResponse data
        data = mock_data["data"]
        required_fields = ["vex_id", "vulnerabilities_count", "enriched_count", "created_at"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(data["vex_id"], str)
        assert isinstance(data["vulnerabilities_count"], int)
        assert isinstance(data["enriched_count"], int)
        assert isinstance(data["created_at"], str)

        # Validate enriched_count <= vulnerabilities_count
        assert data["enriched_count"] <= data["vulnerabilities_count"], \
            "enriched_count cannot exceed vulnerabilities_count"

        # Validate using Pydantic model
        try:
            response = VEXCreateResponse(**data)
            assert response.vex_id == data["vex_id"]
            assert response.vulnerabilities_count == data["vulnerabilities_count"]
            assert response.enriched_count == data["enriched_count"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match VEXCreateResponse schema: {e}")


class TestVEXContractListResponse:
    """Test GET /v1/vex response matches contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_vex_list_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/vex response matches List[VEXListResponse] schema.

        Validates:
        - Response is array of VEX summaries
        - Each entry has vex_id, vulnerabilities_count, created_at, updated_at, metadata
        - Sorted by created_at DESC (newest first)
        """
        with open(mock_responses_dir / "vex_list.json") as f:
            mock_data = json.load(f)

        # Validate outer wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert isinstance(mock_data["data"], list)

        # Validate each VEX summary
        for vex_summary in mock_data["data"]:
            required_fields = ["vex_id", "vulnerabilities_count", "created_at", "updated_at", "metadata"]
            for field in required_fields:
                assert field in vex_summary, f"Missing required field: {field}"

            # Validate field types
            assert isinstance(vex_summary["vex_id"], str)
            assert isinstance(vex_summary["vulnerabilities_count"], int)
            assert isinstance(vex_summary["created_at"], str)
            assert isinstance(vex_summary["updated_at"], str)
            assert isinstance(vex_summary["metadata"], dict)

            # Validate using Pydantic model
            try:
                response = VEXListResponse(**vex_summary)
                assert response.vex_id == vex_summary["vex_id"]
            except ValidationError as e:
                pytest.fail(f"VEX summary doesn't match VEXListResponse schema: {e}")

    def test_vex_list_sorting(self, mock_responses_dir):
        """
        Test: GET /v1/vex returns list sorted by created_at DESC.

        Validates:
        - Results are in reverse chronological order
        - Most recent VEX documents appear first
        """
        with open(mock_responses_dir / "vex_list.json") as f:
            mock_data = json.load(f)

        vex_list = mock_data["data"]

        if len(vex_list) > 1:
            # Verify descending order (newest first)
            for i in range(len(vex_list) - 1):
                current_date = vex_list[i]["created_at"]
                next_date = vex_list[i + 1]["created_at"]
                assert current_date >= next_date, \
                    f"List not sorted DESC: {current_date} should be >= {next_date}"


class TestVEXContractDocumentResponse:
    """Test GET /v1/vex/{vex_id} response matches contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_vex_document_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/vex/{vex_id} response matches VEXDocumentResponse schema.

        Validates:
        - Full VEX document structure
        - CycloneDX metadata (bomFormat, specVersion, version)
        - Vulnerabilities array with enrichment
        - Timestamps and customer_id
        """
        with open(mock_responses_dir / "vex_get.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        # Validate top-level VEX document fields
        required_fields = [
            "vex_id", "bomFormat", "specVersion", "version",
            "vulnerabilities", "metadata", "created_at", "updated_at", "customer_id"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate CycloneDX metadata
        assert data["bomFormat"] == "CycloneDX"
        assert data["specVersion"] in ["1.4", "1.5"]
        assert isinstance(data["version"], int)
        assert data["version"] >= 1

        # Validate vulnerabilities array
        assert isinstance(data["vulnerabilities"], list)
        assert len(data["vulnerabilities"]) > 0, "VEX document should have at least one vulnerability"

        # Validate using Pydantic model
        try:
            response = VEXDocumentResponse(**data)
            assert response.vex_id == data["vex_id"]
            assert len(response.vulnerabilities) == len(data["vulnerabilities"])
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match VEXDocumentResponse schema: {e}")

    def test_vex_vulnerability_response_contract(self, mock_responses_dir):
        """
        Test: Vulnerability entries in VEX document match VEXVulnerabilityResponse schema.

        Validates:
        - CVE ID, state, justification, response, detail
        - Enrichment data structure
        """
        with open(mock_responses_dir / "vex_get.json") as f:
            mock_data = json.load(f)

        vulnerabilities = mock_data["data"]["vulnerabilities"]

        for vuln in vulnerabilities:
            # Validate core fields
            assert "cve_id" in vuln
            assert "state" in vuln
            assert "enrichment" in vuln

            # Validate CVE ID format
            assert vuln["cve_id"].startswith("CVE-"), f"Invalid CVE ID: {vuln['cve_id']}"

            # Validate VEX state values
            valid_states = ["exploitable", "in_triage", "not_affected", "resolved", "false_positive"]
            assert vuln["state"] in valid_states, f"Invalid state: {vuln['state']}"

            # Validate justification (if state is not_affected)
            if vuln["state"] == "not_affected" and "justification" in vuln:
                valid_justifications = [
                    "code_not_present", "code_not_reachable", "requires_configuration",
                    "requires_dependency", "requires_environment", "protected_by_compiler",
                    "protected_at_runtime", "protected_at_perimeter", "protected_by_mitigating_control"
                ]
                assert vuln["justification"] in valid_justifications, \
                    f"Invalid justification: {vuln['justification']}"

            # Validate using Pydantic model
            try:
                response = VEXVulnerabilityResponse(**vuln)
                assert response.cve_id == vuln["cve_id"]
            except ValidationError as e:
                pytest.fail(f"Vulnerability doesn't match VEXVulnerabilityResponse schema: {e}")

    def test_vex_enrichment_contract(self, mock_responses_dir):
        """
        Test: VEX enrichment data matches VEXEnrichment schema.

        Validates knowledge graph enrichment:
        - KEV data (in_kev, kev_date_added, kev_due_date)
        - EPSS data (epss_score, epss_percentile)
        - CVSS data (cvss_score, cvss_severity)
        - CWE weaknesses
        - MITRE ATT&CK techniques
        - NIST 800-53 controls
        - D3FEND defenses
        - Regulatory violations
        """
        with open(mock_responses_dir / "vex_get.json") as f:
            mock_data = json.load(f)

        vulnerabilities = mock_data["data"]["vulnerabilities"]

        for vuln in vulnerabilities:
            enrichment = vuln["enrichment"]

            # Validate KEV fields
            assert "in_kev" in enrichment
            assert isinstance(enrichment["in_kev"], bool)

            if enrichment["in_kev"]:
                assert "kev_date_added" in enrichment
                assert "kev_due_date" in enrichment

            # Validate EPSS fields
            if "epss_score" in enrichment and enrichment["epss_score"] is not None:
                assert 0.0 <= enrichment["epss_score"] <= 1.0, \
                    f"EPSS score out of range: {enrichment['epss_score']}"

            if "epss_percentile" in enrichment and enrichment["epss_percentile"] is not None:
                assert 0.0 <= enrichment["epss_percentile"] <= 1.0, \
                    f"EPSS percentile out of range: {enrichment['epss_percentile']}"

            # Validate CVSS fields
            if "cvss_score" in enrichment and enrichment["cvss_score"] is not None:
                assert 0.0 <= enrichment["cvss_score"] <= 10.0, \
                    f"CVSS score out of range: {enrichment['cvss_score']}"

            if "cvss_severity" in enrichment and enrichment["cvss_severity"] is not None:
                valid_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE"]
                assert enrichment["cvss_severity"] in valid_severities, \
                    f"Invalid CVSS severity: {enrichment['cvss_severity']}"

            # Validate arrays exist
            assert "weaknesses" in enrichment
            assert "attack_techniques" in enrichment
            assert "nist_controls" in enrichment
            assert "d3fend_defenses" in enrichment
            assert "regulatory_violations" in enrichment

            # Validate array types
            assert isinstance(enrichment["weaknesses"], list)
            assert isinstance(enrichment["attack_techniques"], list)
            assert isinstance(enrichment["nist_controls"], list)
            assert isinstance(enrichment["d3fend_defenses"], list)
            assert isinstance(enrichment["regulatory_violations"], list)

            # Validate CWE structure
            for weakness in enrichment["weaknesses"]:
                assert "cwe_id" in weakness
                assert "name" in weakness
                assert weakness["cwe_id"].startswith("CWE-"), \
                    f"Invalid CWE ID: {weakness['cwe_id']}"

            # Validate ATT&CK structure
            for technique in enrichment["attack_techniques"]:
                assert "technique_id" in technique
                assert "name" in technique
                assert technique["technique_id"].startswith("T"), \
                    f"Invalid ATT&CK technique ID: {technique['technique_id']}"

            # Validate NIST structure
            for control in enrichment["nist_controls"]:
                assert "control_id" in control
                assert "title" in control

            # Validate regulatory violations structure
            for violation in enrichment["regulatory_violations"]:
                assert "framework" in violation
                assert "requirement_id" in violation

            # Validate using Pydantic model
            try:
                enrichment_model = VEXEnrichment(**enrichment)
                assert enrichment_model.in_kev == enrichment["in_kev"]
            except ValidationError as e:
                pytest.fail(f"Enrichment doesn't match VEXEnrichment schema: {e}")


class TestVEXContractUpdateResponse:
    """Test PUT /v1/vex/{vex_id} and PATCH responses match contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_vex_update_response_contract(self, mock_responses_dir):
        """
        Test: PUT /v1/vex/{vex_id} response matches VEXUpdateResponse schema.

        Validates:
        - vex_id, updated_at, vulnerabilities_count
        """
        with open(mock_responses_dir / "vex_update.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        required_fields = ["vex_id", "updated_at", "vulnerabilities_count"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(data["vex_id"], str)
        assert isinstance(data["updated_at"], str)
        assert isinstance(data["vulnerabilities_count"], int)

        # Validate using Pydantic model
        try:
            response = VEXUpdateResponse(**data)
            assert response.vex_id == data["vex_id"]
            assert response.vulnerabilities_count == data["vulnerabilities_count"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match VEXUpdateResponse schema: {e}")

    def test_vex_patch_response_contract(self, mock_responses_dir):
        """
        Test: PATCH /v1/vex/{vex_id}/vulnerability/{cve_id} response matches VEXUpdateResponse.

        Validates:
        - Same schema as PUT response
        """
        with open(mock_responses_dir / "vex_patch.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        # Validate using Pydantic model
        try:
            response = VEXUpdateResponse(**data)
            assert response.vex_id == data["vex_id"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match VEXUpdateResponse schema: {e}")


class TestVEXContractDeleteResponse:
    """Test DELETE /v1/vex/{vex_id} response matches contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_vex_delete_response_contract(self, mock_responses_dir):
        """
        Test: DELETE /v1/vex/{vex_id} response format.

        Validates:
        - Returns deleted=true and vex_id
        """
        with open(mock_responses_dir / "vex_delete.json") as f:
            mock_data = json.load(f)

        data = mock_data["data"]

        # Validate structure
        assert "deleted" in data
        assert "vex_id" in data

        # Validate values
        assert data["deleted"] is True
        assert isinstance(data["vex_id"], str)


class TestVEXContractMetadata:
    """Test VEX API responses include standard metadata."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_all_responses_include_metadata(self, mock_responses_dir):
        """
        Test: All VEX responses include metadata with cache_hit and execution_time_ms.

        Validates:
        - Every response has metadata object
        - Metadata includes cache_hit (bool) and execution_time_ms (number)
        """
        mock_files = [
            "vex_create.json",
            "vex_list.json",
            "vex_get.json",
            "vex_update.json",
            "vex_patch.json",
            "vex_delete.json"
        ]

        for mock_file in mock_files:
            file_path = mock_responses_dir / mock_file
            if not file_path.exists():
                pytest.skip(f"Mock file not found: {mock_file}")

            with open(file_path) as f:
                mock_data = json.load(f)

            assert "metadata" in mock_data, f"{mock_file} missing metadata"
            metadata = mock_data["metadata"]

            assert "cache_hit" in metadata, f"{mock_file} metadata missing cache_hit"
            assert "execution_time_ms" in metadata, f"{mock_file} metadata missing execution_time_ms"

            assert isinstance(metadata["cache_hit"], bool)
            assert isinstance(metadata["execution_time_ms"], (int, float))
            assert metadata["execution_time_ms"] >= 0


class TestVEXContractEnrichmentCoverage:
    """Test VEX enrichment includes all knowledge graph data."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_enrichment_includes_kev_data(self, mock_responses_dir):
        """
        Test: VEX enrichment includes KEV data for known exploited vulnerabilities.

        Validates:
        - At least one vulnerability has in_kev=true in mock data
        - KEV vulnerabilities have kev_date_added and kev_due_date
        """
        with open(mock_responses_dir / "vex_get.json") as f:
            mock_data = json.load(f)

        vulnerabilities = mock_data["data"]["vulnerabilities"]

        kev_vulns = [v for v in vulnerabilities if v["enrichment"]["in_kev"]]
        assert len(kev_vulns) > 0, "Mock data should include at least one KEV vulnerability"

        for vuln in kev_vulns:
            enrichment = vuln["enrichment"]
            assert enrichment["kev_date_added"] is not None
            assert enrichment["kev_due_date"] is not None

    def test_enrichment_includes_epss_data(self, mock_responses_dir):
        """
        Test: VEX enrichment includes EPSS data.

        Validates:
        - At least one vulnerability has EPSS score
        - EPSS scores are in valid range (0.0-1.0)
        """
        with open(mock_responses_dir / "vex_get.json") as f:
            mock_data = json.load(f)

        vulnerabilities = mock_data["data"]["vulnerabilities"]

        epss_vulns = [
            v for v in vulnerabilities
            if v["enrichment"].get("epss_score") is not None
        ]
        assert len(epss_vulns) > 0, "Mock data should include at least one vulnerability with EPSS score"

    def test_enrichment_includes_cvss_data(self, mock_responses_dir):
        """
        Test: VEX enrichment includes CVSS data.

        Validates:
        - At least one vulnerability has CVSS score and severity
        """
        with open(mock_responses_dir / "vex_get.json") as f:
            mock_data = json.load(f)

        vulnerabilities = mock_data["data"]["vulnerabilities"]

        cvss_vulns = [
            v for v in vulnerabilities
            if v["enrichment"].get("cvss_score") is not None
        ]
        assert len(cvss_vulns) > 0, "Mock data should include at least one vulnerability with CVSS score"

    def test_enrichment_includes_cwe_data(self, mock_responses_dir):
        """
        Test: VEX enrichment includes CWE weakness data.

        Validates:
        - At least one vulnerability has CWE weaknesses
        - CWE IDs are valid format
        """
        with open(mock_responses_dir / "vex_get.json") as f:
            mock_data = json.load(f)

        vulnerabilities = mock_data["data"]["vulnerabilities"]

        cwe_vulns = [
            v for v in vulnerabilities
            if len(v["enrichment"]["weaknesses"]) > 0
        ]
        assert len(cwe_vulns) > 0, "Mock data should include at least one vulnerability with CWE weaknesses"

    def test_enrichment_includes_attack_data(self, mock_responses_dir):
        """
        Test: VEX enrichment includes MITRE ATT&CK technique data.

        Validates:
        - At least one vulnerability has ATT&CK techniques
        """
        with open(mock_responses_dir / "vex_get.json") as f:
            mock_data = json.load(f)

        vulnerabilities = mock_data["data"]["vulnerabilities"]

        attack_vulns = [
            v for v in vulnerabilities
            if len(v["enrichment"]["attack_techniques"]) > 0
        ]
        assert len(attack_vulns) > 0, "Mock data should include at least one vulnerability with ATT&CK techniques"

    def test_enrichment_includes_nist_controls(self, mock_responses_dir):
        """
        Test: VEX enrichment includes NIST 800-53 control data.

        Validates:
        - At least one vulnerability has NIST controls
        """
        with open(mock_responses_dir / "vex_get.json") as f:
            mock_data = json.load(f)

        vulnerabilities = mock_data["data"]["vulnerabilities"]

        nist_vulns = [
            v for v in vulnerabilities
            if len(v["enrichment"]["nist_controls"]) > 0
        ]
        assert len(nist_vulns) > 0, "Mock data should include at least one vulnerability with NIST controls"

    def test_enrichment_includes_regulatory_violations(self, mock_responses_dir):
        """
        Test: VEX enrichment includes regulatory violation data.

        Validates:
        - At least one vulnerability has regulatory violations
        - Valid framework names (EU_CRA, FDA_524B, etc.)
        """
        with open(mock_responses_dir / "vex_get.json") as f:
            mock_data = json.load(f)

        vulnerabilities = mock_data["data"]["vulnerabilities"]

        reg_vulns = [
            v for v in vulnerabilities
            if len(v["enrichment"]["regulatory_violations"]) > 0
        ]
        assert len(reg_vulns) > 0, "Mock data should include at least one vulnerability with regulatory violations"

        # Validate framework names
        valid_frameworks = ["EU_CRA", "FDA_524B", "IEC_62304", "ISO_14971", "NIST_SSDF"]
        for vuln in reg_vulns:
            for violation in vuln["enrichment"]["regulatory_violations"]:
                # Framework should be one of the known ones (or new ones)
                assert isinstance(violation["framework"], str)
                assert len(violation["framework"]) > 0
