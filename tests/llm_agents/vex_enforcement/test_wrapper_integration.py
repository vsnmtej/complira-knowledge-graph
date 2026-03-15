"""
Integration tests for EnforcedVEXSynthesizer (wrapper).

Tests wrapper module interactions with mocked synthesizers (grounded + V2).
Validates AC-007 (wrapper uses grounded synthesizer) and AC-008 (V2 fallback).

Test Strategy:
- Mock GroundedVEXSynthesizer and VEXSynthesizerV2
- Test mode tracking ("grounded" vs "v2_fallback")
- Test validation metadata propagation
- Test submission readiness flags

Coverage Target: 70%+ for wrapper.py

Author: Complira Development Team
Ticket: vex-justification-enforcement (Stage 7)
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from typing import List

from complira_graph.llm_agents.vex_enforcement.wrapper import EnforcedVEXSynthesizer
from complira_graph.llm_agents.vex_enforcement.grounding import (
    EvidenceNode,
    VEXEvidenceBundle,
)
from complira_graph.llm_agents.vex_enforcement.synthesizer import VEXDocument, VEXStatement
from complira_graph.llm_agents.vex_enforcement.validator import (
    ValidationFailure,
    EvidenceReference,
)


# ========== Fixtures ==========


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client."""
    return Mock()


@pytest.fixture
def sample_bundle():
    """Sample evidence bundle."""
    cwe_node = EvidenceNode(
        node_id="cwes/CWE_79",
        node_key="CWE_79",
        collection="cwes",
        summary="CWE-79: Cross-site Scripting",
        source="has_weakness",
        deterministic=True,
    )
    kev_node = EvidenceNode(
        node_id="kev/CVE_2023_99999",
        node_key="CVE_2023_99999",
        collection="kev",
        summary="Not in KEV catalog",
        source="kev",
        deterministic=True,
    )
    return VEXEvidenceBundle(
        cve_id="CVE-2023-99999",
        component_purl="pkg:npm/example@1.0.0",
        nodes=[cwe_node, kev_node],
    )


@pytest.fixture
def mock_grounded_vex_document():
    """Mock VEX document from grounded synthesizer."""
    return VEXDocument(
        scan_session_id="test-scan-123",
        statements=[
            VEXStatement(
                cve_id="CVE-2023-99999",
                component_purl="pkg:npm/example@1.0.0",
                status="not_affected",
                justification="vulnerable_code_cannot_be_controlled_by_adversary",
                detail="XSS vulnerability (cwes/CWE_79) is not exploitable due to input sanitization. KEV evidence (kev/CVE_2023_99999) confirms no active exploitation.",
                impact_summary="XSS vector blocked by sanitization layer",
                regulatory_context=["FDA_524B"],
                evidence_refs=[
                    EvidenceReference(
                        node_id="cwes/CWE_79",
                        relevance_explanation="Identifies XSS weakness",
                    ),
                    EvidenceReference(
                        node_id="kev/CVE_2023_99999",
                        relevance_explanation="Not in CISA KEV catalog",
                    ),
                ],
            )
        ],
    )


# ========== Integration Tests ==========


@pytest.mark.asyncio
async def test_wrapper_uses_grounded_synthesizer_success(
    mock_anthropic_client, sample_bundle, mock_grounded_vex_document
):
    """
    AC-007: Wrapper uses enforcement layer when available.

    Given: Valid evidence bundle
    When: Call EnforcedVEXSynthesizer.synthesize()
    Then: Use GroundedVEXSynthesizer and return mode="grounded"
    """
    with patch('complira_graph.llm_agents.vex_enforcement.wrapper.GroundedVEXSynthesizer') as MockGrounded, \
         patch('complira_graph.llm_agents.vex_enforcement.wrapper.VEXSynthesizerV2') as MockV2:
        # Mock grounded synthesizer
        mock_grounded_instance = Mock()
        mock_grounded_instance.generate = AsyncMock(return_value=mock_grounded_vex_document)
        mock_grounded_instance.last_validation_failures = []
        MockGrounded.return_value = mock_grounded_instance

        # Mock V2 synthesizer
        mock_v2_instance = Mock()
        MockV2.return_value = mock_v2_instance

        # Mock V2 synthesizer
        mock_v2_instance = Mock()
        MockV2.return_value = mock_v2_instance

        # Create wrapper
        wrapper = EnforcedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        # Call synthesize
        result = await wrapper.synthesize(
            bundles=[sample_bundle],
            scan_session_id="test-scan-123",
            regulatory_context=["FDA_524B"],
        )

        # Verify grounded synthesizer was called
        mock_grounded_instance.generate.assert_called_once_with(
            bundles=[sample_bundle],
            scan_session_id="test-scan-123",
            regulatory_context=["FDA_524B"],
        )

        # Verify result structure
        assert result is not None
        assert "vex_document" in result
        assert "validation_failures" in result
        assert "submission_ready" in result
        assert "mode" in result

        # Verify mode is "grounded"
        assert result["mode"] == "grounded"

        # Verify VEX document returned
        assert result["vex_document"]["scan_session_id"] == "test-scan-123"
        assert len(result["vex_document"]["statements"]) == 1

        # Verify validation metadata
        assert result["validation_failures"] == []
        assert result["submission_ready"] is True


@pytest.mark.asyncio
async def test_wrapper_fallback_to_v2_on_exception(
    mock_anthropic_client, sample_bundle
):
    """
    AC-008: Wrapper falls back to V2 on enforcement failure.

    Given: Enforcement layer exception
    When: Call EnforcedVEXSynthesizer.synthesize()
    Then: Fallback to VEXSynthesizerV2 and return mode="v2_fallback"
    """
    with patch('complira_graph.llm_agents.vex_enforcement.wrapper.GroundedVEXSynthesizer') as MockGrounded, \
         patch('complira_graph.llm_agents.vex_enforcement.wrapper.VEXSynthesizerV2') as MockV2:

        # Mock grounded synthesizer to raise exception
        mock_grounded_instance = Mock()
        mock_grounded_instance.generate = AsyncMock(side_effect=Exception("Grounded synthesis failed"))
        MockGrounded.return_value = mock_grounded_instance

        # Mock V2 synthesizer
        mock_v2_instance = Mock()
        MockV2.return_value = mock_v2_instance

        # Mock V2 synthesizer (fallback)
        mock_v2_instance = Mock()
        mock_v2_doc = {
            "scan_session_id": "test-scan-123",
            "statements": [
                {
                    "cve_id": "CVE-2023-99999",
                    "component_purl": "pkg:npm/example@1.0.0",
                    "status": "under_investigation",
                    "detail": "V2 fallback: investigation in progress",
                }
            ],
        }
        mock_v2_instance.synthesize = AsyncMock(return_value=mock_v2_doc)
        MockV2.return_value = mock_v2_instance

        # Create wrapper
        wrapper = EnforcedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        # Call synthesize
        result = await wrapper.synthesize(
            bundles=[sample_bundle],
            scan_session_id="test-scan-123",
        )

        # Verify grounded synthesizer was attempted
        mock_grounded_instance.generate.assert_called_once()

        # Note: V2 synthesizer.synthesize() is not called in MVP
        # Instead, wrapper creates fallback response directly

        # Verify result structure
        assert result is not None
        assert "vex_document" in result
        assert "mode" in result
        assert "validation_failures" in result
        assert "submission_ready" in result

        # Verify mode is "v2_fallback"
        assert result["mode"] == "v2_fallback"

        # Verify fallback document returned with under_investigation
        assert result["vex_document"]["scan_session_id"] == "test-scan-123"
        assert len(result["vex_document"]["statements"]) == 1
        assert result["vex_document"]["statements"][0]["status"] == "under_investigation"
        assert "enforcement layer failed" in result["vex_document"]["statements"][0]["detail"]

        # Verify validation failures include enforcement_failure
        assert len(result["validation_failures"]) == 1
        assert result["validation_failures"][0]["validation_type"] == "enforcement_failure"
        assert "Grounded synthesis failed" in result["validation_failures"][0]["reason"]

        # Verify submission not ready after fallback
        assert result["submission_ready"] is False


@pytest.mark.asyncio
async def test_wrapper_validation_failures_with_warnings(
    mock_anthropic_client, sample_bundle, mock_grounded_vex_document
):
    """
    Test wrapper propagates validation failures (warnings) in response.

    Given: Grounded synthesis with validation warnings
    When: Call wrapper
    Then: Return warnings in validation_failures, submission_ready=True
    """
    with patch('complira_graph.llm_agents.vex_enforcement.wrapper.GroundedVEXSynthesizer') as MockGrounded, \
         patch('complira_graph.llm_agents.vex_enforcement.wrapper.VEXSynthesizerV2') as MockV2:
        # Mock grounded synthesizer with warnings
        mock_grounded_instance = Mock()
        mock_grounded_instance.generate = AsyncMock(return_value=mock_grounded_vex_document)
        mock_grounded_instance.last_validation_failures = [
            ValidationFailure(
                cve_id="CVE-2023-99999",
                component_purl="pkg:npm/example@1.0.0",
                reason="Low deterministic evidence ratio (60%)",
                severity="warn",
                validation_type="determinism_ratio",
            )
        ]
        MockGrounded.return_value = mock_grounded_instance

        # Mock V2 synthesizer
        mock_v2_instance = Mock()
        MockV2.return_value = mock_v2_instance

        wrapper = EnforcedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        result = await wrapper.synthesize(
            bundles=[sample_bundle],
            scan_session_id="test-scan-123",
        )

        # Verify validation failures propagated
        assert len(result["validation_failures"]) == 1
        assert result["validation_failures"][0]["severity"] == "warn"
        assert result["validation_failures"][0]["validation_type"] == "determinism_ratio"

        # Warnings don't block submission
        assert result["submission_ready"] is True


@pytest.mark.asyncio
async def test_wrapper_validation_failures_with_blockers(
    mock_anthropic_client, sample_bundle, mock_grounded_vex_document
):
    """
    Test wrapper marks submission_ready=False when blocking failures exist.

    Given: Grounded synthesis with blocking validation failures
    When: Call wrapper
    Then: Return submission_ready=False
    """
    with patch('complira_graph.llm_agents.vex_enforcement.wrapper.GroundedVEXSynthesizer') as MockGrounded, \
         patch('complira_graph.llm_agents.vex_enforcement.wrapper.VEXSynthesizerV2') as MockV2:
        # Mock grounded synthesizer with blocking failure
        mock_grounded_instance = Mock()
        mock_grounded_instance.generate = AsyncMock(return_value=mock_grounded_vex_document)
        mock_grounded_instance.last_validation_failures = [
            ValidationFailure(
                cve_id="CVE-2023-99999",
                component_purl="pkg:npm/example@1.0.0",
                reason="Hallucinated evidence reference: 'fake/node123' does not exist",
                severity="block",
                validation_type="node_id_existence",
            )
        ]
        MockGrounded.return_value = mock_grounded_instance

        # Mock V2 synthesizer
        mock_v2_instance = Mock()
        MockV2.return_value = mock_v2_instance

        wrapper = EnforcedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        result = await wrapper.synthesize(
            bundles=[sample_bundle],
            scan_session_id="test-scan-123",
        )

        # Verify validation failures propagated
        assert len(result["validation_failures"]) == 1
        assert result["validation_failures"][0]["severity"] == "block"

        # Blocking failures prevent submission
        assert result["submission_ready"] is False


@pytest.mark.asyncio
async def test_wrapper_mode_tracking_grounded(
    mock_anthropic_client, sample_bundle, mock_grounded_vex_document
):
    """
    Test wrapper correctly tracks mode="grounded" for successful enforcement.
    """
    with patch('complira_graph.llm_agents.vex_enforcement.wrapper.GroundedVEXSynthesizer') as MockGrounded, \
         patch('complira_graph.llm_agents.vex_enforcement.wrapper.VEXSynthesizerV2') as MockV2:
        mock_grounded_instance = Mock()
        mock_grounded_instance.generate = AsyncMock(return_value=mock_grounded_vex_document)
        mock_grounded_instance.last_validation_failures = []
        MockGrounded.return_value = mock_grounded_instance

        # Mock V2 synthesizer
        mock_v2_instance = Mock()
        MockV2.return_value = mock_v2_instance

        wrapper = EnforcedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        result = await wrapper.synthesize(
            bundles=[sample_bundle],
            scan_session_id="test-scan-123",
        )

        # Verify mode tracking
        assert result["mode"] == "grounded"
        assert "fallback_reason" not in result


@pytest.mark.asyncio
async def test_wrapper_mode_tracking_v2_fallback(
    mock_anthropic_client, sample_bundle
):
    """
    Test wrapper correctly tracks mode="v2_fallback" when enforcement fails.
    """
    with patch('complira_graph.llm_agents.vex_enforcement.wrapper.GroundedVEXSynthesizer') as MockGrounded, \
         patch('complira_graph.llm_agents.vex_enforcement.wrapper.VEXSynthesizerV2') as MockV2:

        # Force grounded to fail
        mock_grounded_instance = Mock()
        mock_grounded_instance.generate = AsyncMock(side_effect=ValueError("Test error"))
        MockGrounded.return_value = mock_grounded_instance

        # Mock V2 synthesizer
        mock_v2_instance = Mock()
        MockV2.return_value = mock_v2_instance

        # Mock V2 fallback
        mock_v2_instance = Mock()
        mock_v2_instance.synthesize = AsyncMock(return_value={
            "scan_session_id": "test-scan-123",
            "statements": [],
        })
        MockV2.return_value = mock_v2_instance

        wrapper = EnforcedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        result = await wrapper.synthesize(
            bundles=[sample_bundle],
            scan_session_id="test-scan-123",
        )

        # Verify mode tracking
        assert result["mode"] == "v2_fallback"

        # Verify fallback behavior (no fallback_reason key in MVP)
        assert "validation_failures" in result
        assert len(result["validation_failures"]) > 0
        assert "Test error" in result["validation_failures"][0]["reason"]


@pytest.mark.asyncio
async def test_wrapper_empty_bundles(mock_anthropic_client):
    """
    Test wrapper handles empty evidence bundles gracefully.

    Given: Empty bundles list
    When: Call synthesize()
    Then: Return grounded mode with empty statements
    """
    with patch('complira_graph.llm_agents.vex_enforcement.wrapper.GroundedVEXSynthesizer') as MockGrounded, \
         patch('complira_graph.llm_agents.vex_enforcement.wrapper.VEXSynthesizerV2') as MockV2:
        mock_grounded_instance = Mock()
        mock_empty_doc = VEXDocument(
            scan_session_id="test-scan-123",
            statements=[],
        )
        mock_grounded_instance.generate = AsyncMock(return_value=mock_empty_doc)
        mock_grounded_instance.last_validation_failures = []
        MockGrounded.return_value = mock_grounded_instance

        # Mock V2 synthesizer
        mock_v2_instance = Mock()
        MockV2.return_value = mock_v2_instance

        wrapper = EnforcedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        result = await wrapper.synthesize(
            bundles=[],
            scan_session_id="test-scan-123",
        )

        # Verify result structure
        assert result["mode"] == "grounded"
        assert result["vex_document"]["scan_session_id"] == "test-scan-123"
        assert len(result["vex_document"]["statements"]) == 0
        assert result["submission_ready"] is True


@pytest.mark.asyncio
async def test_wrapper_preserves_regulatory_context(
    mock_anthropic_client, sample_bundle, mock_grounded_vex_document
):
    """
    Test wrapper passes regulatory context to grounded synthesizer.
    """
    with patch('complira_graph.llm_agents.vex_enforcement.wrapper.GroundedVEXSynthesizer') as MockGrounded, \
         patch('complira_graph.llm_agents.vex_enforcement.wrapper.VEXSynthesizerV2') as MockV2:
        mock_grounded_instance = Mock()
        mock_grounded_instance.generate = AsyncMock(return_value=mock_grounded_vex_document)
        mock_grounded_instance.last_validation_failures = []
        MockGrounded.return_value = mock_grounded_instance

        # Mock V2 synthesizer
        mock_v2_instance = Mock()
        MockV2.return_value = mock_v2_instance

        wrapper = EnforcedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        await wrapper.synthesize(
            bundles=[sample_bundle],
            scan_session_id="test-scan-123",
            regulatory_context=["FDA_524B", "EU_CRA"],
        )

        # Verify regulatory context passed through
        call_kwargs = mock_grounded_instance.generate.call_args.kwargs
        assert call_kwargs["regulatory_context"] == ["FDA_524B", "EU_CRA"]


@pytest.mark.asyncio
async def test_wrapper_observability_metrics(
    mock_anthropic_client, sample_bundle, mock_grounded_vex_document
):
    """
    Test wrapper provides observability metrics in response.

    Validates that response includes:
    - Mode (grounded vs v2_fallback)
    - Validation failure count
    - Submission readiness flag
    """
    with patch('complira_graph.llm_agents.vex_enforcement.wrapper.GroundedVEXSynthesizer') as MockGrounded, \
         patch('complira_graph.llm_agents.vex_enforcement.wrapper.VEXSynthesizerV2') as MockV2:
        mock_grounded_instance = Mock()
        mock_grounded_instance.generate = AsyncMock(return_value=mock_grounded_vex_document)
        mock_grounded_instance.last_validation_failures = [
            ValidationFailure(
                cve_id="CVE-2023-99999",
                component_purl="pkg:npm/example@1.0.0",
                reason="Warning: Low deterministic evidence",
                severity="warn",
                validation_type="determinism_ratio",
            )
        ]
        MockGrounded.return_value = mock_grounded_instance

        # Mock V2 synthesizer
        mock_v2_instance = Mock()
        MockV2.return_value = mock_v2_instance

        wrapper = EnforcedVEXSynthesizer(anthropic_client=mock_anthropic_client)

        result = await wrapper.synthesize(
            bundles=[sample_bundle],
            scan_session_id="test-scan-123",
        )

        # Verify observability fields present
        assert "mode" in result
        assert "validation_failures" in result
        assert "submission_ready" in result

        # Verify values
        assert result["mode"] == "grounded"
        assert len(result["validation_failures"]) == 1
        assert result["submission_ready"] is True  # Warnings don't block
