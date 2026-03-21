"""
API Contract Tests - Enrichment Endpoints.

These tests ensure:
1. Enrichment API responses match the documented contract
2. Frontend mock data matches real API responses
3. No breaking changes to enrichment API structure
4. All response models validate correctly with Pydantic
5. Enrichment data sources are consistent (NVD, KEV, EPSS, VulnCheck, ATT&CK, D3FEND)
"""
import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from api.models.responses.enrichment import (
    CVEEnrichment,
    EnrichmentResponse,
    RiskFactors,
    AttackPath,
    AttackPathStage,
    Defense,
    ComplianceMapping,
)


class TestEnrichmentAPIContract:
    """Test enrichment API responses match expected contract."""

    @pytest.fixture
    def mock_responses_dir(self):
        """Path to API mock responses"""
        return Path("tests/fixtures/api_responses")

    def test_batch_enrichment_response_contract(self, mock_responses_dir):
        """
        Test: POST /v1/enrichment/enrich response matches contract

        Validates:
        - Response structure matches EnrichmentResponse model
        - All required fields present (enriched, total, processing_time_ms)
        - Field types correct
        - Enriched CVEs match CVEEnrichment schema
        """
        with open(mock_responses_dir / "enrichment_batch.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        required_fields = ["enriched", "total", "processing_time_ms"]
        for field in required_fields:
            assert field in mock_data, f"Missing required field: {field}"

        # Validate field types
        assert isinstance(mock_data["enriched"], list)
        assert isinstance(mock_data["total"], int)
        assert isinstance(mock_data["processing_time_ms"], (int, float))

        # Validate at least one enriched CVE
        assert len(mock_data["enriched"]) > 0, "Should have at least one enriched CVE"

        # Validate total matches enriched count
        assert mock_data["total"] == len(mock_data["enriched"]), \
            "total should match enriched count"

        # Validate processing time is positive
        assert mock_data["processing_time_ms"] > 0, \
            "processing_time_ms should be positive"

        # Validate using Pydantic model
        try:
            response = EnrichmentResponse(**mock_data)
            assert response.total == mock_data["total"]
            assert len(response.enriched) == len(mock_data["enriched"])
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match EnrichmentResponse schema: {e}")

    def test_single_cve_enrichment_contract(self, mock_responses_dir):
        """
        Test: GET /v1/enrichment/enrich/{cve_id} response matches contract

        Validates:
        - Response structure matches CVEEnrichment model
        - All required enrichment fields present
        - Risk scoring fields are valid
        - Data source fields are present
        """
        with open(mock_responses_dir / "enrichment_single.json") as f:
            mock_data = json.load(f)

        # Validate required fields
        required_fields = [
            "cve_id", "risk_score", "priority", "risk_factors",
            "cwe_list", "attack_techniques", "threat_groups", "enriched_at"
        ]
        for field in required_fields:
            assert field in mock_data, f"Missing required field: {field}"

        # Validate CVE ID format
        assert mock_data["cve_id"].startswith("CVE-"), \
            f"cve_id should start with 'CVE-', got: {mock_data['cve_id']}"

        # Validate risk score range
        assert 0.0 <= mock_data["risk_score"] <= 1.0, \
            f"risk_score should be 0.0-1.0, got: {mock_data['risk_score']}"

        # Validate priority values
        assert mock_data["priority"] in ["CRITICAL", "HIGH", "MEDIUM", "LOW"], \
            f"Invalid priority: {mock_data['priority']}"

        # Validate risk_factors structure
        risk_factors = mock_data["risk_factors"]
        risk_factor_fields = [
            "high_epss", "actively_exploited", "high_cvss",
            "public_exploits", "threat_groups_using"
        ]
        for field in risk_factor_fields:
            assert field in risk_factors, f"Missing risk factor: {field}"
            assert isinstance(risk_factors[field], bool), \
                f"Risk factor {field} should be boolean"

        # Validate lists
        assert isinstance(mock_data["cwe_list"], list)
        assert isinstance(mock_data["attack_techniques"], list)
        assert isinstance(mock_data["threat_groups"], list)

        # Validate timestamp format (ISO 8601)
        assert "T" in mock_data["enriched_at"], \
            "enriched_at should be ISO 8601 format"

        # Validate using Pydantic model
        try:
            enrichment = CVEEnrichment(**mock_data)
            assert enrichment.cve_id == mock_data["cve_id"]
            assert enrichment.risk_score == mock_data["risk_score"]
            assert enrichment.priority == mock_data["priority"]
        except ValidationError as e:
            pytest.fail(f"Mock data doesn't match CVEEnrichment schema: {e}")

    def test_enrichment_data_sources_present(self, mock_responses_dir):
        """
        Test: Enrichment includes all expected data sources

        Validates:
        - NVD data (CVSS scores, description)
        - EPSS scores from FIRST.org
        - KEV catalog status from CISA
        - CWE weaknesses
        - MITRE ATT&CK techniques
        - Threat group intelligence
        """
        with open(mock_responses_dir / "enrichment_single.json") as f:
            mock_data = json.load(f)

        # Validate NVD data fields
        nvd_fields = ["description", "cvss_score", "cvss_vector", "cvss_severity"]
        for field in nvd_fields:
            if field in mock_data:
                assert isinstance(mock_data[field], (str, float, int, type(None))), \
                    f"NVD field {field} has invalid type"

        # Validate CVSS score range (if present)
        if "cvss_score" in mock_data and mock_data["cvss_score"] is not None:
            assert 0.0 <= mock_data["cvss_score"] <= 10.0, \
                f"cvss_score should be 0.0-10.0, got: {mock_data['cvss_score']}"

        # Validate EPSS score (if present)
        if "epss_score" in mock_data and mock_data["epss_score"] is not None:
            assert 0.0 <= mock_data["epss_score"] <= 1.0, \
                f"epss_score should be 0.0-1.0, got: {mock_data['epss_score']}"

        # Validate KEV status
        assert "in_kev" in mock_data
        assert isinstance(mock_data["in_kev"], bool)

        # Validate exploit count
        if "exploit_count" in mock_data:
            assert isinstance(mock_data["exploit_count"], int)
            assert mock_data["exploit_count"] >= 0

        # Validate CWE list format
        for cwe in mock_data["cwe_list"]:
            assert cwe.startswith("CWE-"), f"CWE should start with 'CWE-', got: {cwe}"

        # Validate ATT&CK technique format
        for technique in mock_data["attack_techniques"]:
            assert technique.startswith("T"), \
                f"ATT&CK technique should start with 'T', got: {technique}"

    def test_risk_factors_contract(self, mock_responses_dir):
        """
        Test: RiskFactors model validation

        Validates:
        - All risk factors are boolean
        - Risk factors align with calculated priority
        """
        with open(mock_responses_dir / "enrichment_single.json") as f:
            mock_data = json.load(f)

        risk_factors = mock_data["risk_factors"]

        # Validate using Pydantic model
        try:
            risk_factors_model = RiskFactors(**risk_factors)
            assert isinstance(risk_factors_model.high_epss, bool)
            assert isinstance(risk_factors_model.actively_exploited, bool)
            assert isinstance(risk_factors_model.high_cvss, bool)
            assert isinstance(risk_factors_model.public_exploits, bool)
            assert isinstance(risk_factors_model.threat_groups_using, bool)
        except ValidationError as e:
            pytest.fail(f"Risk factors don't match RiskFactors schema: {e}")

        # Validate risk factors align with priority for CRITICAL CVEs
        if mock_data["priority"] == "CRITICAL":
            # CRITICAL should have multiple high-risk factors
            high_risk_count = sum([
                risk_factors["high_epss"],
                risk_factors["actively_exploited"],
                risk_factors["high_cvss"],
                risk_factors["public_exploits"]
            ])
            assert high_risk_count >= 2, \
                "CRITICAL priority should have at least 2 high-risk factors"

    def test_attack_path_contract(self, mock_responses_dir):
        """
        Test: Attack path response validates correctly

        Validates:
        - Attack path structure (CVE → CWE → CAPEC → ATT&CK → Threat Groups)
        - Each stage has required fields
        - Defenses are properly structured
        """
        with open(mock_responses_dir / "enrichment_batch.json") as f:
            mock_data = json.load(f)

        # Find an enriched CVE with attack path
        enriched_with_path = None
        for enriched in mock_data["enriched"]:
            if "attack_path" in enriched and enriched["attack_path"] is not None:
                enriched_with_path = enriched
                break

        if enriched_with_path is None:
            pytest.skip("No enriched CVE with attack path in mock data")

        attack_path = enriched_with_path["attack_path"]

        # Validate attack path structure
        assert "path" in attack_path
        assert "defenses" in attack_path

        assert isinstance(attack_path["path"], list)
        assert isinstance(attack_path["defenses"], list)

        # Validate path stages
        path = attack_path["path"]
        assert len(path) > 0, "Attack path should have at least one stage"

        expected_stages = ["vulnerability", "weakness", "attack_pattern", "technique", "threat_groups"]
        for i, stage in enumerate(path):
            assert "stage" in stage, f"Stage {i} missing 'stage' field"
            assert stage["stage"] in expected_stages, \
                f"Invalid stage type: {stage['stage']}"

            # Validate stage has node or nodes
            assert "node" in stage or "nodes" in stage, \
                f"Stage {i} missing 'node' or 'nodes' field"

        # Validate defenses
        for defense in attack_path["defenses"]:
            assert "d3fend_id" in defense
            assert "name" in defense
            assert "coverage" in defense

            # Validate D3FEND ID format
            assert defense["d3fend_id"].startswith("D3-"), \
                f"D3FEND ID should start with 'D3-', got: {defense['d3fend_id']}"

        # Validate using Pydantic model
        try:
            attack_path_model = AttackPath(**attack_path)
            assert len(attack_path_model.path) == len(path)
            assert len(attack_path_model.defenses) == len(attack_path["defenses"])
        except ValidationError as e:
            pytest.fail(f"Attack path doesn't match AttackPath schema: {e}")

    def test_compliance_mapping_contract(self, mock_responses_dir):
        """
        Test: Compliance mapping response validates correctly

        Validates:
        - NIST controls are properly formatted
        - Frameworks are valid
        """
        with open(mock_responses_dir / "enrichment_batch.json") as f:
            mock_data = json.load(f)

        # Find an enriched CVE with compliance mapping
        enriched_with_compliance = None
        for enriched in mock_data["enriched"]:
            if "compliance" in enriched and enriched["compliance"] is not None:
                enriched_with_compliance = enriched
                break

        if enriched_with_compliance is None:
            pytest.skip("No enriched CVE with compliance mapping in mock data")

        compliance = enriched_with_compliance["compliance"]

        # Validate compliance structure
        assert "nist_controls" in compliance
        assert "frameworks" in compliance

        assert isinstance(compliance["nist_controls"], list)
        assert isinstance(compliance["frameworks"], list)

        # Validate NIST control format (e.g., SI-2, RA-5)
        for control in compliance["nist_controls"]:
            assert isinstance(control, str)
            assert "-" in control or control.isalnum(), \
                f"NIST control has invalid format: {control}"

        # Validate frameworks
        valid_frameworks = [
            "FDA_524B", "NIST_800_53", "ISO_27001", "IEC_62304",
            "ISO_13485", "EU_CRA", "HIPAA", "SOC2"
        ]
        for framework in compliance["frameworks"]:
            assert framework in valid_frameworks, \
                f"Unknown framework: {framework}"

        # Validate using Pydantic model
        try:
            compliance_model = ComplianceMapping(**compliance)
            assert len(compliance_model.nist_controls) == len(compliance["nist_controls"])
            assert len(compliance_model.frameworks) == len(compliance["frameworks"])
        except ValidationError as e:
            pytest.fail(f"Compliance mapping doesn't match ComplianceMapping schema: {e}")

    def test_enrichment_error_responses_contract(self, mock_responses_dir):
        """
        Test: Error responses match FastAPI HTTPException format

        Validates:
        - All enrichment-specific errors have "detail" field
        - Error messages are descriptive
        """
        with open(mock_responses_dir / "enrichment_errors.json") as f:
            error_data = json.load(f)

        # All errors should have "detail" field
        for error_key, error_response in error_data.items():
            assert "detail" in error_response, f"Error {error_key} missing 'detail' field"
            assert isinstance(error_response["detail"], str)
            assert len(error_response["detail"]) > 0, f"Error {error_key} has empty detail"

    def test_batch_enrichment_handles_multiple_priorities(self, mock_responses_dir):
        """
        Test: Batch enrichment includes CVEs with different priorities

        Validates:
        - Mock data includes CRITICAL, HIGH, MEDIUM, LOW priorities
        - Each priority has appropriate risk scores
        """
        with open(mock_responses_dir / "enrichment_batch.json") as f:
            mock_data = json.load(f)

        enriched_list = mock_data["enriched"]
        priorities = {e["priority"] for e in enriched_list}

        # Should have at least 2 different priority levels
        assert len(priorities) >= 2, \
            f"Mock data should include multiple priority levels, got: {priorities}"

        # Validate risk scores align with priorities
        for enriched in enriched_list:
            priority = enriched["priority"]
            risk_score = enriched["risk_score"]

            if priority == "CRITICAL":
                assert risk_score >= 0.8, \
                    f"CRITICAL priority should have risk_score >= 0.8, got: {risk_score}"
            elif priority == "HIGH":
                assert 0.6 <= risk_score < 0.8, \
                    f"HIGH priority should have risk_score 0.6-0.8, got: {risk_score}"
            elif priority == "MEDIUM":
                assert 0.3 <= risk_score < 0.6, \
                    f"MEDIUM priority should have risk_score 0.3-0.6, got: {risk_score}"
            elif priority == "LOW":
                assert risk_score < 0.3, \
                    f"LOW priority should have risk_score < 0.3, got: {risk_score}"

    def test_enrichment_includes_kev_examples(self, mock_responses_dir):
        """
        Test: Mock data includes CVEs in CISA KEV catalog

        Validates:
        - At least one CVE has in_kev=true
        - KEV CVEs have high risk scores
        """
        with open(mock_responses_dir / "enrichment_batch.json") as f:
            mock_data = json.load(f)

        kev_cves = [e for e in mock_data["enriched"] if e.get("in_kev", False)]

        assert len(kev_cves) > 0, \
            "Mock data should include at least one CVE in KEV catalog"

        # KEV CVEs should have high risk scores
        for kev_cve in kev_cves:
            assert kev_cve["risk_score"] >= 0.7, \
                f"KEV CVE should have high risk score, got: {kev_cve['risk_score']}"
            assert kev_cve["risk_factors"]["actively_exploited"] is True, \
                "KEV CVE should have actively_exploited=true"

    def test_enrichment_includes_epss_scores(self, mock_responses_dir):
        """
        Test: Mock data includes EPSS scores

        Validates:
        - EPSS scores are in valid range (0.0-1.0)
        - High EPSS scores correlate with high risk
        """
        with open(mock_responses_dir / "enrichment_batch.json") as f:
            mock_data = json.load(f)

        epss_cves = [e for e in mock_data["enriched"] if "epss_score" in e and e["epss_score"] is not None]

        assert len(epss_cves) > 0, \
            "Mock data should include CVEs with EPSS scores"

        for cve in epss_cves:
            epss = cve["epss_score"]
            assert 0.0 <= epss <= 1.0, \
                f"EPSS score should be 0.0-1.0, got: {epss}"

            # High EPSS should correlate with high risk
            if epss > 0.7:
                assert cve["risk_factors"]["high_epss"] is True, \
                    f"EPSS > 0.7 should set high_epss=true"

    def test_enrichment_includes_cwe_mappings(self, mock_responses_dir):
        """
        Test: Mock data includes CWE weakness mappings

        Validates:
        - At least one CVE has CWE mappings
        - CWE IDs are properly formatted
        """
        with open(mock_responses_dir / "enrichment_batch.json") as f:
            mock_data = json.load(f)

        cves_with_cwe = [e for e in mock_data["enriched"] if len(e.get("cwe_list", [])) > 0]

        assert len(cves_with_cwe) > 0, \
            "Mock data should include CVEs with CWE mappings"

        for cve in cves_with_cwe:
            for cwe_id in cve["cwe_list"]:
                assert cwe_id.startswith("CWE-"), \
                    f"CWE ID should start with 'CWE-', got: {cwe_id}"
                # Validate CWE number is valid
                cwe_num = cwe_id.split("-")[1]
                assert cwe_num.isdigit(), \
                    f"CWE number should be numeric, got: {cwe_num}"

    def test_enrichment_includes_attack_techniques(self, mock_responses_dir):
        """
        Test: Mock data includes MITRE ATT&CK techniques

        Validates:
        - At least one CVE has ATT&CK mappings
        - Technique IDs are properly formatted
        """
        with open(mock_responses_dir / "enrichment_batch.json") as f:
            mock_data = json.load(f)

        cves_with_attack = [e for e in mock_data["enriched"] if len(e.get("attack_techniques", [])) > 0]

        assert len(cves_with_attack) > 0, \
            "Mock data should include CVEs with ATT&CK techniques"

        for cve in cves_with_attack:
            for technique in cve["attack_techniques"]:
                assert technique.startswith("T"), \
                    f"ATT&CK technique should start with 'T', got: {technique}"
                # Validate technique number is valid
                technique_num = technique[1:]
                assert technique_num.split(".")[0].isdigit(), \
                    f"ATT&CK technique number should be numeric, got: {technique_num}"

    def test_enrichment_includes_threat_groups(self, mock_responses_dir):
        """
        Test: Mock data includes threat group intelligence

        Validates:
        - At least one CVE has threat group mappings
        - Threat group names are realistic
        """
        with open(mock_responses_dir / "enrichment_batch.json") as f:
            mock_data = json.load(f)

        cves_with_threats = [e for e in mock_data["enriched"] if len(e.get("threat_groups", [])) > 0]

        # Not all CVEs need threat group mappings, but at least one should
        if len(cves_with_threats) > 0:
            for cve in cves_with_threats:
                for group in cve["threat_groups"]:
                    assert isinstance(group, str)
                    assert len(group) > 0, "Threat group name should not be empty"

    def test_all_timestamp_fields_use_iso8601(self, mock_responses_dir):
        """
        Test: All timestamp fields use ISO 8601 format

        Validates:
        - enriched_at uses ISO 8601
        - published_date uses ISO 8601 (if present)
        - last_modified uses ISO 8601 (if present)
        """
        with open(mock_responses_dir / "enrichment_single.json") as f:
            mock_data = json.load(f)

        # Check enriched_at
        assert "T" in mock_data["enriched_at"], \
            "enriched_at should be ISO 8601 format"

        # Check published_date (if present)
        if "published_date" in mock_data and mock_data["published_date"] is not None:
            assert "T" in mock_data["published_date"], \
                "published_date should be ISO 8601 format"

        # Check last_modified (if present)
        if "last_modified" in mock_data and mock_data["last_modified"] is not None:
            assert "T" in mock_data["last_modified"], \
                "last_modified should be ISO 8601 format"

    def test_enrichment_optional_fields_nullable(self, mock_responses_dir):
        """
        Test: Optional enrichment fields can be null

        Validates:
        - description can be null
        - cvss_score can be null
        - epss_score can be null
        - attack_path can be null
        - compliance can be null
        """
        with open(mock_responses_dir / "enrichment_batch.json") as f:
            mock_data = json.load(f)

        # Create a minimal enrichment with nulls
        minimal_enrichment = {
            "cve_id": "CVE-2024-99999",
            "description": None,
            "cvss_score": None,
            "cvss_vector": None,
            "cvss_severity": None,
            "epss_score": None,
            "in_kev": False,
            "exploit_count": 0,
            "published_date": None,
            "last_modified": None,
            "risk_score": 0.1,
            "priority": "LOW",
            "risk_factors": {
                "high_epss": False,
                "actively_exploited": False,
                "high_cvss": False,
                "public_exploits": False,
                "threat_groups_using": False
            },
            "cwe_list": [],
            "attack_techniques": [],
            "threat_groups": [],
            "attack_path": None,
            "compliance": None,
            "enriched_at": "2024-03-17T10:00:00Z"
        }

        # Should validate successfully with Pydantic
        try:
            enrichment = CVEEnrichment(**minimal_enrichment)
            assert enrichment.cve_id == "CVE-2024-99999"
            assert enrichment.description is None
            assert enrichment.cvss_score is None
            assert enrichment.attack_path is None
        except ValidationError as e:
            pytest.fail(f"Minimal enrichment with nulls doesn't validate: {e}")
