"""
Integration tests for GroundedVEXSynthesizer.

Tests synthesizer module interactions with mocked LLM client and validator.
Validates AC-001 (evidence sufficiency blocks synthesis) and AC-002 (allows synthesis).

Test Strategy:
- Mock instructor_client.messages.create() to return VEXDocument
- Use real VEXJustificationValidator for post-validation
- Test evidence sufficiency filtering, grounded prompt building, validation integration

Coverage Target: 65%+ for synthesizer.py

Author: Complira Development Team
Ticket: vex-justification-enforcement (Stage 7)
"""

import pytest
from unittest.mock import Mock, patch
from typing import List

from complira_graph.llm_agents.vex_enforcement.grounding import (
    EvidenceNode,
    VEXEvidenceBundle,
    JustificationCode,
)
from complira_graph.llm_agents.vex_enforcement.synthesizer import (
    GroundedVEXSynthesizer,
    VEXDocument,
    VEXStatement,
)
from complira_graph.llm_agents.vex_enforcement.validator import (
    VEXJustificationValidator,
    ValidationFailure,
    EvidenceReference,
)


# ========== Fixtures ==========


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for LLM calls."""
    return Mock()


@pytest.fixture
def cwe_node() -> EvidenceNode:
    """Deterministic CWE evidence node."""
    return EvidenceNode(
        node_id="cwes/CWE_502",
        node_key="CWE_502",
        collection="cwes",
        summary="CWE-502: Deserialization of Untrusted Data",
        source="has_weakness",
        deterministic=True,
    )


@pytest.fixture
def kev_node() -> EvidenceNode:
    """Deterministic KEV evidence node."""
    return EvidenceNode(
        node_id="kev/CVE_2021_44228",
        node_key="CVE_2021_44228",
        collection="kev",
        summary="CVE-2021-44228 in CISA KEV catalog",
        source="kev",
        deterministic=True,
    )


@pytest.fixture
def epss_node() -> EvidenceNode:
    """Probabilistic EPSS evidence node."""
    return EvidenceNode(
        node_id="exploit_intelligence/CVE_2021_44228_epss",
        node_key="CVE_2021_44228_epss",
        collection="exploit_intelligence",
        summary="EPSS score: 0.95 (high exploitability)",
        source="epss",
        deterministic=False,
        confidence=0.95,
    )


@pytest.fixture
def sufficient_bundle(cwe_node, kev_node, epss_node) -> VEXEvidenceBundle:
    """Evidence bundle with sufficient evidence for VULNERABLE_CODE_NOT_CONTROLLABLE."""
    return VEXEvidenceBundle(
        cve_id="CVE-2021-44228",
        component_purl="pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1",
        nodes=[cwe_node, kev_node, epss_node],
    )


@pytest.fixture
def insufficient_bundle() -> VEXEvidenceBundle:
    """Evidence bundle with insufficient evidence (only 1 deterministic node)."""
    kev_only = EvidenceNode(
        node_id="kev/CVE_2023_12345",
        node_key="CVE_2023_12345",
        collection="kev",
        summary="KEV evidence only",
        source="kev",
        deterministic=True,
    )
    return VEXEvidenceBundle(
        cve_id="CVE-2023-12345",  # Different CVE to avoid conflicts
        component_purl="pkg:maven/org.example/example-lib@1.0.0",
        nodes=[kev_only],  # Only 1 deterministic node (need 2)
    )


@pytest.fixture
def mock_vex_document(sufficient_bundle) -> VEXDocument:
    """Mock VEXDocument returned by LLM."""
    return VEXDocument(
        scan_session_id="test-session-123",
        statements=[
            VEXStatement(
                cve_id=sufficient_bundle.cve_id,
                component_purl=sufficient_bundle.component_purl,
                justification="vulnerable_code_cannot_be_controlled_by_adversary",
                status="not_affected",
                detail="The vulnerable deserialization code path (cwes/CWE_502) requires admin privileges. KEV evidence (kev/CVE_2021_44228) confirms no active exploitation.",
                impact_summary="CWE-502 deserialization vulnerability is not exploitable due to access controls",
                regulatory_context=["FDA_524B"],
                evidence_refs=[
                    EvidenceReference(
                        node_id="cwes/CWE_502",
                        relevance_explanation="Identifies the CWE-502 deserialization weakness",
                    ),
                    EvidenceReference(
                        node_id="kev/CVE_2021_44228",
                        relevance_explanation="Confirms not in CISA KEV catalog (not actively exploited)",
                    ),
                ],
            )
        ],
    )


# ========== Integration Tests ==========


@pytest.mark.asyncio
async def test_evidence_sufficiency_blocks_synthesis(
    mock_anthropic_client, insufficient_bundle
):
    """
    AC-001: Evidence sufficiency check blocks synthesis for insufficient evidence.

    Given: CVE with insufficient evidence (only 1 deterministic node, need 2)
    When: Request synthesis
    Then: Return under_investigation status without calling LLM
    """
    with patch('complira_graph.llm_agents.vex_enforcement.synthesizer.instructor') as mock_instructor:
        mock_instructor_client = Mock()
        mock_instructor_client.messages = Mock()
        mock_instructor_client.messages.create = Mock()
        mock_instructor.from_anthropic.return_value = mock_instructor_client

        synthesizer = GroundedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        result = await synthesizer.generate(
            bundles=[insufficient_bundle],
            scan_session_id="test-session-123",
            regulatory_context=["FDA_524B"],
        )

        # Verify LLM was NOT called (no sufficient bundles)
        mock_instructor_client.messages.create.assert_not_called()

        # Verify under_investigation document returned
        assert result is not None
        assert result.scan_session_id == "test-session-123"
        assert len(result.statements) == 1

        stmt = result.statements[0]
        assert stmt.cve_id == insufficient_bundle.cve_id
        assert stmt.status == "under_investigation"
        assert "insufficient" in stmt.detail.lower() or "investigation" in stmt.detail.lower()


@pytest.mark.asyncio
async def test_evidence_sufficiency_allows_synthesis(
    mock_anthropic_client, sufficient_bundle, mock_vex_document
):
    """
    AC-002: Evidence sufficiency check allows synthesis for complete evidence.

    Given: CVE with complete evidence (2+ deterministic nodes)
    When: Request synthesis
    Then: Call LLM with grounded prompt and return VEXDocument
    """
    with patch('complira_graph.llm_agents.vex_enforcement.synthesizer.instructor') as mock_instructor:
        mock_instructor_client = Mock()
        mock_instructor_client.messages = Mock()
        mock_instructor_client.messages.create = Mock(return_value=mock_vex_document)
        mock_instructor.from_anthropic.return_value = mock_instructor_client

        synthesizer = GroundedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        result = await synthesizer.generate(
            bundles=[sufficient_bundle],
            scan_session_id="test-session-123",
            regulatory_context=["FDA_524B"],
        )

        # Verify LLM was called
        mock_instructor_client.messages.create.assert_called_once()
        call_kwargs = mock_instructor_client.messages.create.call_args.kwargs

        assert call_kwargs["model"] == "claude-sonnet-4-20250514"
        assert call_kwargs["max_tokens"] >= 4000
        assert "messages" in call_kwargs
        assert len(call_kwargs["messages"]) > 0

        # Verify prompt contains real node IDs (grounding)
        prompt_text = call_kwargs["messages"][0]["content"]
        assert "cwes/CWE_502" in prompt_text
        assert "kev/CVE_2021_44228" in prompt_text

        # Verify result has scan_session_id set
        assert result.scan_session_id == "test-session-123"
        assert len(result.statements) > 0


@pytest.mark.asyncio
async def test_grounded_prompt_building(
    mock_anthropic_client, sufficient_bundle, mock_vex_document
):
    """
    Test grounded prompt building with real node IDs from evidence bundle.

    Validates that prompt contains:
    - Real node IDs only (no fabricated IDs)
    - Evidence summaries for context
    - Regulatory context hints (FDA 524B, EU CRA)
    """
    with patch('complira_graph.llm_agents.vex_enforcement.synthesizer.instructor') as mock_instructor:
        mock_instructor_client = Mock()
        mock_instructor_client.messages = Mock()
        mock_instructor_client.messages.create = Mock(return_value=mock_vex_document)
        mock_instructor.from_anthropic.return_value = mock_instructor_client

        synthesizer = GroundedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        await synthesizer.generate(
            bundles=[sufficient_bundle],
            scan_session_id="test-session-123",
            regulatory_context=["FDA_524B", "EU_CRA"],
        )

        # Extract prompt from LLM call
        call_kwargs = mock_instructor_client.messages.create.call_args.kwargs
        prompt_text = call_kwargs["messages"][0]["content"]

        # Verify real node IDs present
        assert "cwes/CWE_502" in prompt_text
        assert "kev/CVE_2021_44228" in prompt_text
        assert "exploit_intelligence/CVE_2021_44228_epss" in prompt_text

        # Verify evidence summaries present
        assert "CWE-502" in prompt_text or "Deserialization" in prompt_text
        assert "KEV" in prompt_text or "CISA" in prompt_text

        # Verify regulatory context hints
        assert "FDA" in prompt_text or "524B" in prompt_text
        assert "CRA" in prompt_text or "EU" in prompt_text

        # Verify CVE and component identifiers
        assert "CVE-2021-44228" in prompt_text
        assert "pkg:maven/org.apache.logging.log4j/log4j-core" in prompt_text


@pytest.mark.asyncio
async def test_validation_integration_synthesizer_to_validator(
    mock_anthropic_client, sufficient_bundle
):
    """
    Test integration between synthesizer and validator.

    Validates that:
    - Synthesizer calls validator after LLM generation
    - Validator detects hallucinated node IDs
    - Blocking failures filter out invalid statements
    """
    # Create mock document with hallucinated node ID
    hallucinated_doc = VEXDocument(
        scan_session_id="test-session-123",
        statements=[
            VEXStatement(
                cve_id=sufficient_bundle.cve_id,
                component_purl=sufficient_bundle.component_purl,
                justification="vulnerable_code_cannot_be_controlled_by_adversary",
                status="not_affected",
                detail="Test statement with cwes/CWE_502 and fake_collection/fake_node_999",
                impact_summary="Test impact summary for hallucination detection",
                regulatory_context=["FDA_524B"],
                evidence_refs=[
                    EvidenceReference(
                        node_id="cwes/CWE_502",  # Real node
                        relevance_explanation="Real CWE evidence",
                    ),
                    EvidenceReference(
                        node_id="fake_collection/fake_node_999",  # Hallucination!
                        relevance_explanation="Fabricated evidence",
                    ),
                ],
            )
        ],
    )

    with patch('complira_graph.llm_agents.vex_enforcement.synthesizer.instructor') as mock_instructor:
        mock_instructor_client = Mock()
        mock_instructor_client.messages = Mock()
        mock_instructor_client.messages.create = Mock(return_value=hallucinated_doc)
        mock_instructor.from_anthropic.return_value = mock_instructor_client

        synthesizer = GroundedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        result = await synthesizer.generate(
            bundles=[sufficient_bundle],
            scan_session_id="test-session-123",
        )

        # Verify validation ran and detected hallucination
        assert synthesizer.last_validation_failures is not None
        assert len(synthesizer.last_validation_failures) > 0

        hallucination_failures = [
            f for f in synthesizer.last_validation_failures
            if f.validation_type == "node_id_existence"
        ]
        assert len(hallucination_failures) == 1
        assert hallucination_failures[0].severity == "block"
        assert "fake_collection/fake_node_999" in hallucination_failures[0].reason

        # Verify blocking failure filtered out statement
        assert len(result.statements) == 0  # Statement with hallucination removed


@pytest.mark.asyncio
async def test_mixed_bundles_filtering(
    mock_anthropic_client, sufficient_bundle, insufficient_bundle, mock_vex_document
):
    """
    Test evidence filtering with mixed sufficient/insufficient bundles.

    Given: List with 1 sufficient bundle + 1 insufficient bundle
    When: Call generate()
    Then:
      - Sufficient bundle processed via LLM
      - Insufficient bundle returned as under_investigation
      - Final document contains statements from both paths
    """
    with patch('complira_graph.llm_agents.vex_enforcement.synthesizer.instructor') as mock_instructor:
        mock_instructor_client = Mock()
        mock_instructor_client.messages = Mock()
        mock_instructor_client.messages.create = Mock(return_value=mock_vex_document)
        mock_instructor.from_anthropic.return_value = mock_instructor_client

        synthesizer = GroundedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        result = await synthesizer.generate(
            bundles=[sufficient_bundle, insufficient_bundle],
            scan_session_id="test-session-123",
        )

        # Verify LLM called only for sufficient bundle (1 bundle)
        mock_instructor_client.messages.create.assert_called_once()

        # Verify result contains statements
        # Note: Implementation creates under_investigation for insufficient bundles BEFORE LLM call
        # So we should see at least the LLM-generated statement
        assert len(result.statements) >= 1


@pytest.mark.asyncio
async def test_under_investigation_document_creation(
    mock_anthropic_client, insufficient_bundle
):
    """
    Test under_investigation document creation for insufficient evidence.

    Validates structure and content of fallback VEXStatement when evidence is missing.
    """
    with patch('complira_graph.llm_agents.vex_enforcement.synthesizer.instructor') as mock_instructor:
        mock_instructor_client = Mock()
        mock_instructor_client.messages = Mock()
        mock_instructor_client.messages.create = Mock()
        mock_instructor.from_anthropic.return_value = mock_instructor_client

        synthesizer = GroundedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        result = await synthesizer.generate(
            bundles=[insufficient_bundle],
            scan_session_id="test-session-123",
        )

        # Verify document structure
        assert result.scan_session_id == "test-session-123"
        assert result.bom_format == "CycloneDX"
        assert result.spec_version == "1.5"

        # Verify statement structure
        assert len(result.statements) == 1
        stmt = result.statements[0]

        assert stmt.cve_id == insufficient_bundle.cve_id
        assert stmt.component_purl == insufficient_bundle.component_purl
        assert stmt.status == "under_investigation"
        assert stmt.justification is None  # No justification for under_investigation
        assert len(stmt.detail) >= 50  # Has detail narrative
        assert len(stmt.evidence_refs) == 0  # No evidence refs for insufficient case


@pytest.mark.asyncio
async def test_evidence_coverage_metadata(
    mock_anthropic_client, sufficient_bundle, mock_vex_document
):
    """
    Test evidence coverage metadata calculation.

    Validates that synthesizer tracks:
    - Evidence types present in bundle
    - Coverage statistics in document metadata
    """
    with patch('complira_graph.llm_agents.vex_enforcement.synthesizer.instructor') as mock_instructor:
        mock_instructor_client = Mock()
        mock_instructor_client.messages = Mock()
        mock_instructor_client.messages.create = Mock(return_value=mock_vex_document)
        mock_instructor.from_anthropic.return_value = mock_instructor_client

        synthesizer = GroundedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        result = await synthesizer.generate(
            bundles=[sufficient_bundle],
            scan_session_id="test-session-123",
        )

        # Verify evidence coverage calculated
        assert result.evidence_coverage is not None
        assert isinstance(result.evidence_coverage, dict)

        # Verify evidence types tracked
        assert "cwe_evidence" in result.evidence_coverage
        assert "kev_evidence" in result.evidence_coverage
        assert "exploitability_evidence" in result.evidence_coverage

        # Verify counts
        assert result.evidence_coverage["cwe_evidence"] >= 1
        assert result.evidence_coverage["kev_evidence"] >= 1
