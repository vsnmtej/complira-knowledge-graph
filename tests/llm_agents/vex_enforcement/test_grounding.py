"""
Unit tests for VEX Evidence Grounding Module.

Tests evidence bundle creation, justification-to-evidence mapping,
and deterministic classification logic.

Coverage:
- EvidenceNode creation and properties
- VEXEvidenceBundle validation methods
- Justification support checking
- Deterministic/probabilistic classification

Author: Complira Development Team
Version: 1.0
Ticket: vex-justification-enforcement
"""

import pytest
from pydantic import ValidationError

from complira_graph.llm_agents.vex_enforcement.grounding import (
    EvidenceNode,
    VEXEvidenceBundle,
    JustificationCode,
    REQUIRED_EVIDENCE_FOR_JUSTIFICATION,
)


class TestEvidenceNode:
    """Test EvidenceNode model and methods."""

    def test_evidence_node_creation(self):
        """Test basic EvidenceNode creation."""
        node = EvidenceNode(
            node_id="cwes/CWE_502",
            node_key="CWE_502",
            collection="cwes",
            summary="CWE-502: Deserialization of Untrusted Data",
            source="has_weakness",
            deterministic=True,
        )

        assert node.node_id == "cwes/CWE_502"
        assert node.deterministic is True
        assert node.evidence_type == "cwe_evidence"

    def test_evidence_node_with_confidence(self):
        """Test EvidenceNode with confidence score."""
        node = EvidenceNode(
            node_id="exploit_intelligence/epss_123",
            node_key="epss_123",
            collection="exploit_intelligence",
            summary="EPSS score 0.92 for CVE-2021-44228",
            source="epss",
            deterministic=False,
            confidence=0.92,
        )

        assert node.deterministic is False
        assert node.confidence == 0.92
        assert node.evidence_type == "exploitability_evidence"

    def test_evidence_node_invalid_node_id_format(self):
        """Test that invalid node_id format raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            EvidenceNode(
                node_id="invalid_format_no_slash",  # Missing collection/key format
                node_key="invalid",
                collection="test",
                summary="Test",
                source="test",
                deterministic=True,
            )

        assert "node_id" in str(exc_info.value)

    def test_evidence_type_inference(self):
        """Test evidence_type property inference from collection."""
        test_cases = [
            ("cwes", "cwe_evidence"),
            ("kev", "kev_evidence"),
            ("vulnerabilities", "cve_metadata"),
            ("exploit_intelligence", "exploitability_evidence"),
            ("unknown_collection", "unknown_collection_evidence"),
        ]

        for collection, expected_type in test_cases:
            node = EvidenceNode(
                node_id=f"{collection}/test_123",
                node_key="test_123",
                collection=collection,
                summary="Test summary",
                source="test",
                deterministic=True,
            )
            assert node.evidence_type == expected_type

    def test_deterministic_inference_from_collection(self):
        """Test _infer_deterministic_from_collection static method."""
        # Deterministic collections
        assert EvidenceNode._infer_deterministic_from_collection("cwes", "has_weakness") is True
        assert EvidenceNode._infer_deterministic_from_collection("kev", "kev") is True
        assert EvidenceNode._infer_deterministic_from_collection("vulnerabilities", "nvd") is True

        # Probabilistic collections
        assert EvidenceNode._infer_deterministic_from_collection("exploit_intelligence", "epss") is False

        # Probabilistic sources
        assert EvidenceNode._infer_deterministic_from_collection("unknown", "llm_classifier") is False
        assert EvidenceNode._infer_deterministic_from_collection("unknown", "epss") is False

        # Unknown defaults to deterministic
        assert EvidenceNode._infer_deterministic_from_collection("unknown", "unknown") is True


class TestVEXEvidenceBundle:
    """Test VEXEvidenceBundle model and validation methods."""

    @pytest.fixture
    def sample_cwe_node(self):
        """Create sample CWE evidence node."""
        return EvidenceNode(
            node_id="cwes/CWE_502",
            node_key="CWE_502",
            collection="cwes",
            summary="CWE-502: Deserialization of Untrusted Data",
            source="has_weakness",
            deterministic=True,
        )

    @pytest.fixture
    def sample_kev_node(self):
        """Create sample KEV evidence node."""
        return EvidenceNode(
            node_id="kev/CVE_2021_44228",
            node_key="CVE_2021_44228",
            collection="kev",
            summary="CVE-2021-44228 in CISA KEV catalog",
            source="kev",
            deterministic=True,
        )

    @pytest.fixture
    def sample_epss_node(self):
        """Create sample EPSS evidence node."""
        return EvidenceNode(
            node_id="exploit_intelligence/epss_123",
            node_key="epss_123",
            collection="exploit_intelligence",
            summary="EPSS score 0.05 for CVE-2021-44228",
            source="epss",
            deterministic=False,
            confidence=0.05,
        )

    @pytest.fixture
    def sample_bundle(self, sample_cwe_node, sample_kev_node, sample_epss_node):
        """Create sample evidence bundle with mixed evidence."""
        return VEXEvidenceBundle(
            cve_id="CVE-2021-44228",
            component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
            nodes=[sample_cwe_node, sample_kev_node, sample_epss_node],
        )

    def test_bundle_creation(self, sample_bundle):
        """Test basic evidence bundle creation."""
        assert sample_bundle.cve_id == "CVE-2021-44228"
        assert len(sample_bundle.nodes) == 3

    def test_available_evidence_types(self, sample_bundle):
        """Test available_evidence_types() method."""
        types = sample_bundle.available_evidence_types()

        assert "cwe_evidence" in types
        assert "kev_evidence" in types
        assert "exploitability_evidence" in types
        assert len(types) == 3

    def test_deterministic_nodes(self, sample_bundle):
        """Test deterministic_nodes() filtering."""
        det_nodes = sample_bundle.deterministic_nodes()

        assert len(det_nodes) == 2  # CWE + KEV
        assert all(node.deterministic for node in det_nodes)

    def test_probabilistic_nodes(self, sample_bundle):
        """Test probabilistic_nodes() filtering."""
        prob_nodes = sample_bundle.probabilistic_nodes()

        assert len(prob_nodes) == 1  # EPSS only
        assert all(not node.deterministic for node in prob_nodes)

    def test_can_support_justification_success(self, sample_bundle):
        """Test can_support_justification() with sufficient evidence."""
        # VULNERABLE_CODE_NOT_CONTROLLABLE requires: kev_evidence + cwe_evidence
        can_support = sample_bundle.can_support_justification(
            JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE
        )

        assert can_support is True

    def test_can_support_justification_success_inline_mitigations(self, sample_bundle):
        """Test can_support_justification() for INLINE_MITIGATIONS_EXIST."""
        # INLINE_MITIGATIONS_EXIST requires: kev_evidence + exploitability_evidence
        can_support = sample_bundle.can_support_justification(
            JustificationCode.INLINE_MITIGATIONS_EXIST
        )

        assert can_support is True

    def test_can_support_justification_missing_evidence(self):
        """Test can_support_justification() with insufficient evidence."""
        # Bundle with only CWE evidence (missing KEV)
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
                )
            ],
        )

        # VULNERABLE_CODE_NOT_CONTROLLABLE requires both KEV and CWE
        can_support = bundle.can_support_justification(
            JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE
        )

        assert can_support is False

    def test_can_support_justification_only_probabilistic_evidence(self, sample_cwe_node):
        """Test can_support_justification() rejects probabilistic-only evidence."""
        # Create bundle with CWE (deterministic) and probabilistic KEV
        prob_kev_node = EvidenceNode(
            node_id="kev/llm_generated",
            node_key="llm_generated",
            collection="kev",
            summary="LLM-classified KEV",
            source="llm_classifier",
            deterministic=False,  # Probabilistic KEV
        )

        bundle = VEXEvidenceBundle(
            cve_id="CVE-2024-5678",
            component_purl="pkg:maven/test/package@1.0.0",
            nodes=[sample_cwe_node, prob_kev_node],
        )

        # Should fail because KEV evidence is probabilistic
        can_support = bundle.can_support_justification(
            JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE
        )

        assert can_support is False

    def test_get_nodes_by_type(self, sample_bundle):
        """Test get_nodes_by_type() filtering."""
        cwe_nodes = sample_bundle.get_nodes_by_type("cwe_evidence")

        assert len(cwe_nodes) == 1
        assert cwe_nodes[0].collection == "cwes"

    def test_node_id_index(self, sample_bundle):
        """Test node_id_index() set generation."""
        index = sample_bundle.node_id_index()

        assert "cwes/CWE_502" in index
        assert "kev/CVE_2021_44228" in index
        assert "exploit_intelligence/epss_123" in index
        assert len(index) == 3

        # Test fast lookup (O(1))
        assert "cwes/CWE_502" in index
        assert "fake/node_123" not in index

    def test_invalid_cve_id_format(self):
        """Test that invalid CVE ID format raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            VEXEvidenceBundle(
                cve_id="INVALID-2021-1234",  # Wrong format
                component_purl="pkg:maven/test/package@1.0.0",
                nodes=[],
            )

        assert "cve_id" in str(exc_info.value)


class TestJustificationCode:
    """Test JustificationCode enum."""

    def test_justification_code_values(self):
        """Test justification code enum values."""
        assert JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE == "vulnerable_code_cannot_be_controlled_by_adversary"
        assert JustificationCode.INLINE_MITIGATIONS_EXIST == "inline_mitigations_already_exist"

    def test_justification_code_mvp_scope(self):
        """Test that only MVP-scope justification codes are defined."""
        # MVP scope: 2 codes only (no SBOM/SAST-dependent codes)
        all_codes = list(JustificationCode)
        assert len(all_codes) == 2


class TestRequiredEvidenceMapping:
    """Test REQUIRED_EVIDENCE_FOR_JUSTIFICATION mapping."""

    def test_required_evidence_mapping_completeness(self):
        """Test that all justification codes have evidence requirements."""
        for code in JustificationCode:
            assert code in REQUIRED_EVIDENCE_FOR_JUSTIFICATION

    def test_required_evidence_for_vulnerable_code_not_controllable(self):
        """Test evidence requirements for VULNERABLE_CODE_NOT_CONTROLLABLE."""
        required = REQUIRED_EVIDENCE_FOR_JUSTIFICATION[
            JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE
        ]

        assert "kev_evidence" in required
        assert "cwe_evidence" in required

    def test_required_evidence_for_inline_mitigations_exist(self):
        """Test evidence requirements for INLINE_MITIGATIONS_EXIST."""
        required = REQUIRED_EVIDENCE_FOR_JUSTIFICATION[
            JustificationCode.INLINE_MITIGATIONS_EXIST
        ]

        assert "kev_evidence" in required
        assert "exploitability_evidence" in required


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
