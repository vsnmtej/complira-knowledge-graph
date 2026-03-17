"""
Unit tests for VEX Justification Validator Module.

Tests post-generation validation including hallucination detection,
evidence gap detection, determinism ratio checks, and regulatory enforcement.

Coverage:
- Hallucination detection (node ID existence)
- Justification support validation
- Deterministic/probabilistic evidence ratio
- Regulatory bar enforcement (FDA 524B, EU CRA)

Author: Complira Development Team
Version: 1.0
Ticket: vex-justification-enforcement
"""

import pytest
from typing import List

from complira_graph.llm_agents.vex_enforcement.validator import (
    VEXJustificationValidator,
    ValidationFailure,
    VEXStatement,
    VEXDocument,
    EvidenceReference,
)
from complira_graph.llm_agents.vex_enforcement.grounding import (
    VEXEvidenceBundle,
    EvidenceNode,
    JustificationCode,
)


class TestValidationFailure:
    """Test ValidationFailure model."""

    def test_validation_failure_creation_block(self):
        """Test ValidationFailure with blocking severity."""
        failure = ValidationFailure(
            cve_id="CVE-2021-44228",
            component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
            reason="Hallucinated evidence reference: 'fake/node123' does not exist",
            severity="block",
            validation_type="node_id_existence"
        )

        assert failure.severity == "block"
        assert "fake/node123" in failure.reason

    def test_validation_failure_creation_warn(self):
        """Test ValidationFailure with warning severity."""
        failure = ValidationFailure(
            cve_id="CVE-2021-44228",
            component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
            reason="Low deterministic evidence ratio",
            severity="warn",
            validation_type="determinism_ratio"
        )

        assert failure.severity == "warn"
        assert failure.validation_type == "determinism_ratio"


class TestVEXJustificationValidator:
    """Test VEXJustificationValidator validation methods."""

    @pytest.fixture
    def sample_bundle_with_evidence(self):
        """Create sample evidence bundle with CWE and KEV evidence."""
        return VEXEvidenceBundle(
            cve_id="CVE-2021-44228",
            component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
            nodes=[
                EvidenceNode(
                    node_id="cwes/CWE_502",
                    node_key="CWE_502",
                    collection="cwes",
                    summary="CWE-502: Deserialization of Untrusted Data",
                    source="has_weakness",
                    deterministic=True,
                ),
                EvidenceNode(
                    node_id="kev/CVE_2021_44228",
                    node_key="CVE_2021_44228",
                    collection="kev",
                    summary="CVE-2021-44228 in CISA KEV catalog",
                    source="kev",
                    deterministic=True,
                ),
                EvidenceNode(
                    node_id="exploit_intelligence/epss_123",
                    node_key="epss_123",
                    collection="exploit_intelligence",
                    summary="EPSS score 0.05",
                    source="epss",
                    deterministic=False,
                    confidence=0.05,
                ),
            ],
        )

    @pytest.fixture
    def valid_vex_statement(self):
        """Create valid VEX statement with real evidence references."""
        return VEXStatement(
            cve_id="CVE-2021-44228",
            component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
            status="not_affected",
            justification=JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE,
            evidence_refs=[
                EvidenceReference(
                    node_id="cwes/CWE_502",
                    relevance_explanation="Deserialization weakness not exploitable in this context"
                ),
                EvidenceReference(
                    node_id="kev/CVE_2021_44228",
                    relevance_explanation="Not in KEV catalog indicates low active exploitation"
                ),
            ],
            detail="This component is not affected because the vulnerable deserialization code path is not accessible in our deployment configuration. Evidence nodes cwes/CWE_502 and kev/CVE_2021_44228 support this assessment.",
            regulatory_context=[],
        )

    def test_validator_initialization(self, sample_bundle_with_evidence):
        """Test validator initialization with evidence bundles."""
        bundles = {"CVE-2021-44228": sample_bundle_with_evidence}
        validator = VEXJustificationValidator(bundles)

        assert "CVE-2021-44228" in validator._all_node_ids
        assert "cwes/CWE_502" in validator._all_node_ids["CVE-2021-44228"]

    def test_validate_all_checks_pass(self, sample_bundle_with_evidence, valid_vex_statement):
        """Test validate() with statement that passes all checks."""
        bundles = {"CVE-2021-44228": sample_bundle_with_evidence}
        validator = VEXJustificationValidator(bundles)

        doc = VEXDocument(statements=[valid_vex_statement])
        failures = validator.validate(doc)

        # Should pass all validation checks
        assert len(failures) == 0

    def test_check_node_ids_exist_success(self, sample_bundle_with_evidence, valid_vex_statement):
        """Test _check_node_ids_exist() with all valid node IDs."""
        bundles = {"CVE-2021-44228": sample_bundle_with_evidence}
        validator = VEXJustificationValidator(bundles)

        failures = validator._check_node_ids_exist(valid_vex_statement, sample_bundle_with_evidence)

        assert len(failures) == 0

    def test_check_node_ids_exist_hallucination(self, sample_bundle_with_evidence):
        """Test _check_node_ids_exist() detects fabricated node IDs (UC-002 ERROR path)."""
        bundles = {"CVE-2021-44228": sample_bundle_with_evidence}
        validator = VEXJustificationValidator(bundles)

        # Statement with fabricated node ID
        stmt = VEXStatement(
            cve_id="CVE-2021-44228",
            component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
            status="not_affected",
            justification=JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE,
            evidence_refs=[
                EvidenceReference(
                    node_id="fake_collection/fake_node_123",  # Fabricated!
                    relevance_explanation="Fake evidence"
                ),
            ],
            detail="Detail mentioning fake_collection/fake_node_123",
            regulatory_context=[],
        )

        failures = validator._check_node_ids_exist(stmt, sample_bundle_with_evidence)

        assert len(failures) == 1
        assert failures[0].severity == "block"
        assert "fake_collection/fake_node_123" in failures[0].reason
        assert failures[0].validation_type == "node_id_existence"

    def test_check_node_ids_exist_multiple_hallucinations(self, sample_bundle_with_evidence):
        """Test _check_node_ids_exist() detects multiple fabricated node IDs."""
        bundles = {"CVE-2021-44228": sample_bundle_with_evidence}
        validator = VEXJustificationValidator(bundles)

        stmt = VEXStatement(
            cve_id="CVE-2021-44228",
            component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
            status="not_affected",
            evidence_refs=[
                EvidenceReference(node_id="fake1/node1", relevance_explanation="Fake 1"),
                EvidenceReference(node_id="fake2/node2", relevance_explanation="Fake 2"),
            ],
            detail="Detail text",
            regulatory_context=[],
        )

        failures = validator._check_node_ids_exist(stmt, sample_bundle_with_evidence)

        assert len(failures) == 2
        assert all(f.severity == "block" for f in failures)

    def test_check_justification_supported_success(self, sample_bundle_with_evidence, valid_vex_statement):
        """Test _check_justification_supported() with sufficient evidence."""
        bundles = {"CVE-2021-44228": sample_bundle_with_evidence}
        validator = VEXJustificationValidator(bundles)

        failures = validator._check_justification_supported(valid_vex_statement, sample_bundle_with_evidence)

        assert len(failures) == 0

    def test_check_justification_supported_insufficient_evidence(self):
        """Test _check_justification_supported() with insufficient evidence (UC-001 ERROR path)."""
        # Bundle with only CWE evidence (missing KEV for VULNERABLE_CODE_NOT_CONTROLLABLE)
        bundle = VEXEvidenceBundle(
            cve_id="CVE-2024-1234",
            component_purl="pkg:maven/test/package@1.0.0",
            nodes=[
                EvidenceNode(
                    node_id="cwes/CWE_79",
                    node_key="CWE_79",
                    collection="cwes",
                    summary="CWE-79: XSS",
                    source="has_weakness",
                    deterministic=True,
                ),
            ],
        )

        bundles = {"CVE-2024-1234": bundle}
        validator = VEXJustificationValidator(bundles)

        stmt = VEXStatement(
            cve_id="CVE-2024-1234",
            component_purl="pkg:maven/test/package@1.0.0",
            status="not_affected",
            justification=JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE,
            evidence_refs=[
                EvidenceReference(node_id="cwes/CWE_79", relevance_explanation="XSS weakness")
            ],
            detail="Detailed justification",
            regulatory_context=[],
        )

        failures = validator._check_justification_supported(stmt, bundle)

        assert len(failures) == 1
        assert failures[0].severity == "block"
        assert "kev_evidence" in failures[0].reason
        assert failures[0].validation_type == "justification_support"

    def test_check_justification_supported_skips_non_not_affected(self, sample_bundle_with_evidence):
        """Test _check_justification_supported() skips affected/under_investigation status."""
        bundles = {"CVE-2021-44228": sample_bundle_with_evidence}
        validator = VEXJustificationValidator(bundles)

        # Statement with affected status (no justification required)
        stmt = VEXStatement(
            cve_id="CVE-2021-44228",
            component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
            status="affected",
            justification=None,
            evidence_refs=[],
            detail="Component is affected",
            regulatory_context=[],
        )

        failures = validator._check_justification_supported(stmt, sample_bundle_with_evidence)

        # Should not validate justification for non-"not_affected" status
        assert len(failures) == 0

    def test_check_determinism_ratio_high_deterministic(self, sample_bundle_with_evidence):
        """Test _check_determinism_ratio() passes with >50% deterministic evidence."""
        bundles = {"CVE-2021-44228": sample_bundle_with_evidence}
        validator = VEXJustificationValidator(bundles)

        # 2 deterministic (CWE + KEV) + 0 probabilistic = 100% deterministic
        stmt = VEXStatement(
            cve_id="CVE-2021-44228",
            component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
            status="not_affected",
            evidence_refs=[
                EvidenceReference(node_id="cwes/CWE_502", relevance_explanation="CWE"),
                EvidenceReference(node_id="kev/CVE_2021_44228", relevance_explanation="KEV"),
            ],
            detail="Detail",
            regulatory_context=[],
        )

        failures = validator._check_determinism_ratio(stmt, sample_bundle_with_evidence)

        assert len(failures) == 0

    def test_check_determinism_ratio_low_deterministic(self, sample_bundle_with_evidence):
        """Test _check_determinism_ratio() warns with ≤50% deterministic evidence (UC-003 WARN path)."""
        bundles = {"CVE-2021-44228": sample_bundle_with_evidence}
        validator = VEXJustificationValidator(bundles)

        # 1 deterministic + 2 probabilistic = 33% deterministic (≤50%)
        bundle_with_prob = VEXEvidenceBundle(
            cve_id="CVE-2021-44228",
            component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
            nodes=[
                EvidenceNode(
                    node_id="cwes/CWE_502",
                    node_key="CWE_502",
                    collection="cwes",
                    summary="CWE-502",
                    source="has_weakness",
                    deterministic=True,
                ),
                EvidenceNode(
                    node_id="llm/prob1",
                    node_key="prob1",
                    collection="llm",
                    summary="LLM evidence 1",
                    source="llm_classifier",
                    deterministic=False,
                ),
                EvidenceNode(
                    node_id="llm/prob2",
                    node_key="prob2",
                    collection="llm",
                    summary="LLM evidence 2",
                    source="llm_classifier",
                    deterministic=False,
                ),
            ],
        )

        stmt = VEXStatement(
            cve_id="CVE-2021-44228",
            component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
            status="not_affected",
            evidence_refs=[
                EvidenceReference(node_id="cwes/CWE_502", relevance_explanation="CWE"),
                EvidenceReference(node_id="llm/prob1", relevance_explanation="LLM 1"),
                EvidenceReference(node_id="llm/prob2", relevance_explanation="LLM 2"),
            ],
            detail="Detail",
            regulatory_context=[],
        )

        failures = validator._check_determinism_ratio(stmt, bundle_with_prob)

        assert len(failures) == 1
        assert failures[0].severity == "warn"  # Warning, not blocking
        assert "1/3" in failures[0].reason
        assert failures[0].validation_type == "determinism_ratio"

    def test_check_regulatory_bar_fda_524b_missing_binary_analysis(self, sample_bundle_with_evidence):
        """Test _check_regulatory_bar() warns for FDA 524B without binary analysis (UC-004 WARN path)."""
        bundles = {"CVE-2021-44228": sample_bundle_with_evidence}
        validator = VEXJustificationValidator(bundles)

        stmt = VEXStatement(
            cve_id="CVE-2021-44228",
            component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
            status="not_affected",
            justification=JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE,
            evidence_refs=[
                EvidenceReference(node_id="cwes/CWE_502", relevance_explanation="CWE"),
            ],
            detail="Detail",
            regulatory_context=["FDA_524B"],  # FDA context requires binary analysis
        )

        failures = validator._check_regulatory_bar(stmt, sample_bundle_with_evidence)

        assert len(failures) == 1
        assert failures[0].severity == "warn"
        assert "FDA 524B" in failures[0].reason
        assert "binary" in failures[0].reason.lower()
        assert failures[0].validation_type == "regulatory_bar"

    def test_check_regulatory_bar_eu_cra_short_detail(self, sample_bundle_with_evidence):
        """Test _check_regulatory_bar() warns for EU CRA with short detail."""
        bundles = {"CVE-2021-44228": sample_bundle_with_evidence}
        validator = VEXJustificationValidator(bundles)

        stmt = VEXStatement(
            cve_id="CVE-2021-44228",
            component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
            status="not_affected",
            evidence_refs=[],
            detail="Short detail",  # Only 12 characters (< 100 required for EU CRA)
            regulatory_context=["EU_CRA"],
        )

        failures = validator._check_regulatory_bar(stmt, sample_bundle_with_evidence)

        assert len(failures) == 1
        assert failures[0].severity == "warn"
        assert "EU CRA" in failures[0].reason
        assert "100 characters" in failures[0].reason
        assert failures[0].validation_type == "regulatory_bar"

    def test_check_regulatory_bar_no_context(self, sample_bundle_with_evidence, valid_vex_statement):
        """Test _check_regulatory_bar() skips validation with no regulatory context."""
        bundles = {"CVE-2021-44228": sample_bundle_with_evidence}
        validator = VEXJustificationValidator(bundles)

        failures = validator._check_regulatory_bar(valid_vex_statement, sample_bundle_with_evidence)

        # No regulatory context = no regulatory validation
        assert len(failures) == 0

    def test_is_submission_ready_no_blocking_failures(self):
        """Test is_submission_ready() returns True with only warnings."""
        failures = [
            ValidationFailure(
                cve_id="CVE-2021-44228",
                component_purl="pkg:maven/test/package@1.0.0",
                reason="Low deterministic ratio",
                severity="warn",
                validation_type="determinism_ratio"
            ),
        ]

        validator = VEXJustificationValidator({})
        ready = validator.is_submission_ready(failures)

        assert ready is True

    def test_is_submission_ready_with_blocking_failures(self):
        """Test is_submission_ready() returns False with blocking failures."""
        failures = [
            ValidationFailure(
                cve_id="CVE-2021-44228",
                component_purl="pkg:maven/test/package@1.0.0",
                reason="Fabricated node ID",
                severity="block",
                validation_type="node_id_existence"
            ),
        ]

        validator = VEXJustificationValidator({})
        ready = validator.is_submission_ready(failures)

        assert ready is False

    def test_get_failures_by_severity(self):
        """Test get_failures_by_severity() groups failures correctly."""
        failures = [
            ValidationFailure(
                cve_id="CVE-1",
                component_purl="pkg:maven/test/pkg1@1.0.0",
                reason="Blocking 1",
                severity="block",
                validation_type="node_id_existence"
            ),
            ValidationFailure(
                cve_id="CVE-2",
                component_purl="pkg:maven/test/pkg2@1.0.0",
                reason="Warning 1",
                severity="warn",
                validation_type="determinism_ratio"
            ),
            ValidationFailure(
                cve_id="CVE-3",
                component_purl="pkg:maven/test/pkg3@1.0.0",
                reason="Blocking 2",
                severity="block",
                validation_type="justification_support"
            ),
        ]

        validator = VEXJustificationValidator({})
        grouped = validator.get_failures_by_severity(failures)

        assert len(grouped["block"]) == 2
        assert len(grouped["warn"]) == 1

    def test_validate_multiple_statements(self, sample_bundle_with_evidence):
        """Test validate() with multiple statements in document."""
        bundle2 = VEXEvidenceBundle(
            cve_id="CVE-2024-5678",
            component_purl="pkg:maven/test/another@1.0.0",
            nodes=[
                EvidenceNode(
                    node_id="cwes/CWE_79",
                    node_key="CWE_79",
                    collection="cwes",
                    summary="XSS",
                    source="has_weakness",
                    deterministic=True,
                ),
            ],
        )

        bundles = {
            "CVE-2021-44228": sample_bundle_with_evidence,
            "CVE-2024-5678": bundle2,
        }
        validator = VEXJustificationValidator(bundles)

        doc = VEXDocument(statements=[
            VEXStatement(
                cve_id="CVE-2021-44228",
                component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
                status="not_affected",
                evidence_refs=[
                    EvidenceReference(node_id="cwes/CWE_502", relevance_explanation="Valid")
                ],
                detail="Valid detail for CVE-2021-44228",
                regulatory_context=[],
            ),
            VEXStatement(
                cve_id="CVE-2024-5678",
                component_purl="pkg:maven/test/another@1.0.0",
                status="not_affected",
                evidence_refs=[
                    EvidenceReference(node_id="fake/node999", relevance_explanation="Fabricated!")
                ],
                detail="Detail with fake evidence",
                regulatory_context=[],
            ),
        ])

        failures = validator.validate(doc)

        # Should detect hallucinated node_id in second statement
        assert len(failures) >= 1
        assert any("fake/node999" in f.reason for f in failures)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
