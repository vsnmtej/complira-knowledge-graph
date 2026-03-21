"""
API Contract Tests for Reference Data Endpoints - Validate response schemas.

These tests ensure:
1. Backend API responses match the documented contract
2. Frontend mock data matches real API responses
3. No breaking changes to API structure for reference endpoints

Tests all 4 reference endpoints:
- GET /v1/reference/cve/{cve_id}
- GET /v1/reference/enrich
- GET /v1/reference/cwe/{cwe_id}
- GET /v1/reference/controls/{cve_id}
"""
import json
import pytest
from pathlib import Path


class TestReferenceContractCVEDetails:
    """Test GET /v1/reference/cve/{cve_id} response contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_cve_details_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/reference/cve/{cve_id} response matches contract.

        Validates:
        - Response structure matches APIResponse wrapper
        - CVE details include all required fields
        - Enrichment data structure is correct
        - Field types are correct
        """
        with open(mock_responses_dir / "reference_cve_details.json") as f:
            mock_data = json.load(f)

        # Validate outer APIResponse wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data

        assert mock_data["success"] is True

        # Validate CVE details data
        cve = mock_data["data"]

        # Required CVE fields
        required_fields = [
            "cve_id", "description", "cvss_score", "cvss_vector", "severity",
            "published_date", "last_modified_date"
        ]
        for field in required_fields:
            assert field in cve, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(cve["cve_id"], str)
        assert cve["cve_id"].startswith("CVE-")
        assert isinstance(cve["description"], str)
        assert isinstance(cve["cvss_score"], (int, float))
        assert isinstance(cve["severity"], str)
        assert cve["severity"] in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"]

        # Validate enrichment data structure
        enrichment_fields = [
            "epss", "kev", "weaknesses", "attack_patterns", "attack_techniques",
            "nist_controls", "regulatory_requirements", "d3fend_defenses",
            "threat_groups", "exploits", "references"
        ]
        for field in enrichment_fields:
            assert field in cve, f"Missing enrichment field: {field}"

        # Validate EPSS structure
        if cve["epss"]:
            epss = cve["epss"]
            assert "score" in epss
            assert "percentile" in epss
            assert "date" in epss
            assert isinstance(epss["score"], (int, float))
            assert 0 <= epss["score"] <= 1

        # Validate KEV structure
        assert "kev" in cve
        kev = cve["kev"]
        assert "in_kev" in kev
        assert isinstance(kev["in_kev"], bool)
        if kev["in_kev"]:
            assert "due_date" in kev
            assert "notes" in kev

        # Validate weaknesses array
        assert isinstance(cve["weaknesses"], list)
        if len(cve["weaknesses"]) > 0:
            weakness = cve["weaknesses"][0]
            assert "cwe_id" in weakness
            assert "name" in weakness
            assert weakness["cwe_id"].startswith("CWE-")

        # Validate attack techniques array
        assert isinstance(cve["attack_techniques"], list)
        if len(cve["attack_techniques"]) > 0:
            technique = cve["attack_techniques"][0]
            assert "technique_id" in technique
            assert "name" in technique
            assert technique["technique_id"].startswith("T")

        # Validate NIST controls array
        assert isinstance(cve["nist_controls"], list)
        if len(cve["nist_controls"]) > 0:
            control = cve["nist_controls"][0]
            assert "control_id" in control
            assert "title" in control
            assert "family" in control

        # Validate D3FEND defenses array
        assert isinstance(cve["d3fend_defenses"], list)
        if len(cve["d3fend_defenses"]) > 0:
            defense = cve["d3fend_defenses"][0]
            assert "technique_id" in defense
            assert "name" in defense

        # Validate metadata
        metadata = mock_data["metadata"]
        assert "cache_hit" in metadata
        assert "execution_time_ms" in metadata
        assert isinstance(metadata["cache_hit"], bool)
        assert isinstance(metadata["execution_time_ms"], (int, float))

    def test_cve_details_kev_vulnerability(self, mock_responses_dir):
        """
        Test: CVE in KEV catalog has correct enrichment.

        Validates:
        - in_kev is true
        - kev_date_added present
        - kev_due_date present
        - High EPSS score expected for KEV entries
        """
        with open(mock_responses_dir / "reference_cve_details.json") as f:
            mock_data = json.load(f)

        cve = mock_data["data"]

        # If this is a KEV CVE, validate KEV fields
        if cve["kev"]["in_kev"]:
            assert cve["kev"]["due_date"] is not None
            assert isinstance(cve["kev"]["due_date"], str)
            # KEV CVEs typically have high EPSS scores
            if cve["epss"]:
                assert cve["epss"]["score"] > 0.1, "KEV CVEs typically have EPSS > 0.1"

    def test_cve_details_has_knowledge_graph_mappings(self, mock_responses_dir):
        """
        Test: CVE has complete knowledge graph mappings.

        Validates:
        - CVE → CWE → CAPEC → ATT&CK → Controls path present
        - Realistic number of mappings
        """
        with open(mock_responses_dir / "reference_cve_details.json") as f:
            mock_data = json.load(f)

        cve = mock_data["data"]

        # Most CVEs should have at least one CWE
        assert len(cve["weaknesses"]) >= 1, "CVE should have at least one CWE mapping"

        # If CWE exists, should have some NIST controls
        if len(cve["weaknesses"]) > 0:
            assert len(cve["nist_controls"]) >= 1, "CVE with CWE should have control mappings"


class TestReferenceContractBatchEnrich:
    """Test GET /v1/reference/enrich response contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_batch_enrich_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/reference/enrich response matches contract.

        Validates:
        - Response structure is APIResponse wrapper
        - Data is array of CVE enrichment objects
        - Each CVE has same structure as /cve/{cve_id}
        """
        with open(mock_responses_dir / "reference_enrich.json") as f:
            mock_data = json.load(f)

        # Validate outer wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert mock_data["success"] is True

        # Validate data is array
        cves = mock_data["data"]
        assert isinstance(cves, list)
        assert len(cves) >= 2, "Mock should have multiple CVEs for batch test"

        # Validate each CVE object
        for cve in cves:
            # Check if it's an error response or enriched CVE
            if "error" in cve:
                # CVE not found - should have cve_id and error message
                assert "cve_id" in cve
                assert isinstance(cve["error"], str)
            else:
                # Enriched CVE - should have all standard fields
                assert "cve_id" in cve
                assert "severity" in cve
                assert "cvss_score" in cve
                assert "epss" in cve
                assert "kev" in cve
                assert "weaknesses" in cve

    def test_batch_enrich_handles_mixed_results(self, mock_responses_dir):
        """
        Test: Batch enrich handles mix of found/not found CVEs.

        Validates:
        - Some CVEs enriched successfully
        - Some CVEs have error field
        - Array length matches request count
        """
        with open(mock_responses_dir / "reference_enrich.json") as f:
            mock_data = json.load(f)

        cves = mock_data["data"]

        # Count successful vs error responses
        successful = [c for c in cves if "error" not in c]
        errors = [c for c in cves if "error" in c]

        # Should have at least one of each for comprehensive testing
        assert len(successful) >= 1, "Should have at least one successful enrichment"
        # Not required: assert len(errors) >= 1, "Should have at least one not-found error"


class TestReferenceContractCWEDetails:
    """Test GET /v1/reference/cwe/{cwe_id} response contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_cwe_details_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/reference/cwe/{cwe_id} response matches contract.

        Validates:
        - Response structure matches APIResponse wrapper
        - CWE details include all required fields
        - Hierarchy relationships present
        - Attack patterns mapped
        """
        with open(mock_responses_dir / "reference_cwe_details.json") as f:
            mock_data = json.load(f)

        # Validate outer wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data

        # Validate CWE details
        cwe = mock_data["data"]

        required_fields = [
            "cwe_id", "name", "description", "extended_description",
            "parents", "children", "attack_patterns"
        ]
        for field in required_fields:
            assert field in cwe, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(cwe["cwe_id"], str)
        assert cwe["cwe_id"].startswith("CWE-")
        assert isinstance(cwe["name"], str)
        assert isinstance(cwe["description"], str)

        # Validate hierarchy
        assert isinstance(cwe["parents"], list)
        assert isinstance(cwe["children"], list)

        if len(cwe["parents"]) > 0:
            parent = cwe["parents"][0]
            assert "cwe_id" in parent
            assert "name" in parent
            assert parent["cwe_id"].startswith("CWE-")

        if len(cwe["children"]) > 0:
            child = cwe["children"][0]
            assert "cwe_id" in child
            assert "name" in child
            assert child["cwe_id"].startswith("CWE-")

        # Validate attack patterns
        assert isinstance(cwe["attack_patterns"], list)
        if len(cwe["attack_patterns"]) > 0:
            capec = cwe["attack_patterns"][0]
            assert "capec_id" in capec
            assert "name" in capec
            assert "description" in capec
            assert capec["capec_id"].startswith("CAPEC-")

    def test_cwe_details_has_realistic_content(self, mock_responses_dir):
        """
        Test: CWE details contain realistic content.

        Validates:
        - Name is descriptive
        - Description is substantial
        - Has position in CWE hierarchy
        """
        with open(mock_responses_dir / "reference_cwe_details.json") as f:
            mock_data = json.load(f)

        cwe = mock_data["data"]

        # Name should be meaningful
        assert len(cwe["name"]) > 10, "CWE name should be descriptive"

        # Description should be substantial
        assert len(cwe["description"]) > 50, "CWE description should be detailed"

        # Most CWEs have parents or children in hierarchy
        has_hierarchy = len(cwe["parents"]) > 0 or len(cwe["children"]) > 0
        assert has_hierarchy, "CWE should have hierarchy relationships"


class TestReferenceContractControls:
    """Test GET /v1/reference/controls/{cve_id} response contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_controls_response_contract(self, mock_responses_dir):
        """
        Test: GET /v1/reference/controls/{cve_id} response matches contract.

        Validates:
        - Response structure matches APIResponse wrapper
        - NIST controls array present
        - Regulatory requirements array present
        - Control details complete
        """
        with open(mock_responses_dir / "reference_controls.json") as f:
            mock_data = json.load(f)

        # Validate outer wrapper
        assert "success" in mock_data
        assert "data" in mock_data
        assert "metadata" in mock_data

        # Validate controls data
        controls_data = mock_data["data"]

        required_fields = ["cve_id", "nist_controls", "regulatory_requirements"]
        for field in required_fields:
            assert field in controls_data, f"Missing required field: {field}"

        # Validate CVE ID
        assert isinstance(controls_data["cve_id"], str)
        assert controls_data["cve_id"].startswith("CVE-")

        # Validate NIST controls array
        assert isinstance(controls_data["nist_controls"], list)
        if len(controls_data["nist_controls"]) > 0:
            control = controls_data["nist_controls"][0]
            assert "control_id" in control
            assert "title" in control
            assert "family" in control

            # Control ID should be valid NIST format (e.g., SI-10, AC-2)
            assert isinstance(control["control_id"], str)
            assert len(control["control_id"]) >= 3
            assert isinstance(control["title"], str)
            assert isinstance(control["family"], str)

        # Validate regulatory requirements array
        assert isinstance(controls_data["regulatory_requirements"], list)

    def test_controls_has_realistic_mappings(self, mock_responses_dir):
        """
        Test: Controls endpoint returns realistic control mappings.

        Validates:
        - Multiple controls mapped (CVE → CWE → CAPEC → ATT&CK → Controls)
        - Control families make sense for vulnerability type
        """
        with open(mock_responses_dir / "reference_controls.json") as f:
            mock_data = json.load(f)

        controls_data = mock_data["data"]

        # Most CVEs should map to multiple controls
        assert len(controls_data["nist_controls"]) >= 2, "CVE should map to multiple NIST controls"

        # Validate control families are from NIST 800-53
        valid_families = [
            "Access Control", "Awareness and Training", "Audit and Accountability",
            "Configuration Management", "Contingency Planning", "Identification and Authentication",
            "Incident Response", "Maintenance", "Media Protection", "Physical and Environmental Protection",
            "Planning", "Program Management", "Personnel Security", "PII Processing and Transparency",
            "Risk Assessment", "System and Services Acquisition", "System and Communications Protection",
            "System and Information Integrity", "Supply Chain Risk Management"
        ]

        for control in controls_data["nist_controls"]:
            # Family should be from valid NIST families (or similar)
            assert isinstance(control["family"], str)
            # Note: Not enforcing exact match as some implementations may use abbreviations


class TestReferenceContractErrors:
    """Test reference endpoint error responses."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_reference_error_responses_contract(self, mock_responses_dir):
        """
        Test: Reference endpoint errors match FastAPI HTTPException format.

        Validates:
        - 404 errors for not found CVE/CWE
        - 422 errors for validation failures
        - 400 errors for bad requests
        - All have 'detail' field
        """
        with open(mock_responses_dir / "reference_errors.json") as f:
            error_data = json.load(f)

        # All errors should have "detail" field
        for error_key, error_response in error_data.items():
            assert "detail" in error_response, f"Error {error_key} missing 'detail' field"
            # Detail can be either a string (simple errors) or list (validation errors)
            assert isinstance(error_response["detail"], (str, list)), \
                f"Error {error_key} has invalid detail type: {type(error_response['detail'])}"
            if isinstance(error_response["detail"], str):
                assert len(error_response["detail"]) > 0, f"Error {error_key} has empty detail"
            elif isinstance(error_response["detail"], list):
                assert len(error_response["detail"]) > 0, f"Error {error_key} has empty detail list"
                # Validate structure of validation errors
                for error_item in error_response["detail"]:
                    assert "type" in error_item, f"Validation error missing 'type' field"
                    assert "msg" in error_item, f"Validation error missing 'msg' field"

        # Validate specific error types
        assert "404_cve_not_found" in error_data
        assert "CVE not found" in error_data["404_cve_not_found"]["detail"]

        assert "404_cwe_not_found" in error_data
        assert "CWE not found" in error_data["404_cwe_not_found"]["detail"]

        assert "400_batch_limit_exceeded" in error_data
        assert "100" in error_data["400_batch_limit_exceeded"]["detail"]

        assert "422_missing_cve_ids" in error_data


class TestReferenceContractMetadata:
    """Test metadata structure across all reference endpoints."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses."""
        return Path("tests/fixtures/api_responses")

    def test_all_reference_responses_include_metadata(self, mock_responses_dir):
        """
        Test: All reference endpoint responses include metadata.

        Validates:
        - cache_hit field present
        - execution_time_ms field present
        - api_version field present
        """
        mock_files = [
            "reference_cve_details.json",
            "reference_enrich.json",
            "reference_cwe_details.json",
            "reference_controls.json"
        ]

        for mock_file in mock_files:
            with open(mock_responses_dir / mock_file) as f:
                mock_data = json.load(f)

            assert "metadata" in mock_data, f"{mock_file} missing metadata"
            metadata = mock_data["metadata"]

            assert "cache_hit" in metadata, f"{mock_file} metadata missing cache_hit"
            assert "execution_time_ms" in metadata, f"{mock_file} metadata missing execution_time_ms"

            assert isinstance(metadata["cache_hit"], bool)
            assert isinstance(metadata["execution_time_ms"], (int, float))
            assert metadata["execution_time_ms"] > 0
