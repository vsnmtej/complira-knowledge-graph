# Requirements: VEX Justification Enforcement Layer

**Status**: `Design-ready`
**Ticket**: `vex-justification-enforcement`
**Date Created**: 2026-03-07
**Last Updated**: 2026-03-07
**Version**: v2 (Refined after Stage 1 investigation)

---

## Problem Statement

The current VEX Synthesizer V2 implementation (`src/complira_graph/llm_agents/vex_synthesizer_v2.py`) provides evidence-first VEX generation with Pydantic validation and graph provenance tracking. However, it has critical gaps compared to State of the Art (SOTA) regulatory-grade VEX generation requirements:

### Critical SOTA Gaps

1. **Evidence-to-Justification Mapping Gap**
   - Current: LLM can claim any justification code without enforcement
   - SOTA Required: Justification codes must be grounded in deterministic evidence
   - Impact: FDA 524B/EU CRA reviewers will reject "not_affected" claims without binary-level evidence

2. **Deterministic vs Probabilistic Evidence Tracking Gap**
   - Current: All evidence treated equally regardless of source
   - SOTA Required: Distinguish scanner-sourced (deterministic) vs LLM-sourced (probabilistic) evidence
   - Impact: Regulatory submissions require deterministic evidence chains

3. **Pre-LLM Evidence Validation Gap**
   - Current: Evidence collected but not validated before LLM synthesis
   - SOTA Required: Validate evidence sufficiency before calling LLM
   - Impact: Wasted LLM calls when evidence insufficient

4. **Post-LLM Hallucination Detection Gap**
   - Current: Schema validation only (field presence/format)
   - SOTA Required: Validate that cited evidence node IDs actually exist in knowledge graph
   - Impact: LLM can fabricate plausible-looking but fake evidence references

5. **Regulatory Bar Enforcement Gap**
   - Current: Documents regulatory context but doesn't enforce requirements
   - SOTA Required: FDA 524B requires binary analysis, CRA requires detailed justification narratives
   - Impact: Submissions fail regulatory review

6. **Validation Severity Levels Gap**
   - Current: Binary pass/fail
   - SOTA Required: Blocking failures (can't submit) vs warnings (review recommended)
   - Impact: No guidance on submission readiness

---

## Goal

Implement a VEX Justification Enforcement Layer that:
1. **Grounds** every VEX justification in traceable knowledge graph evidence **before** LLM runs
2. **Validates** LLM outputs cite real evidence node IDs (hallucination detection)
3. **Enforces** regulatory-context-specific evidence requirements
4. **Maintains** backward compatibility with existing VEX V2 implementation

---

## In-Scope Use Cases

### UC-001: Pre-LLM Evidence Sufficiency Check
**Source**: Requirement - REQ-001
**Priority**: Critical

**Primary Path**:
1. System collects evidence bundle for CVE from knowledge graph
2. User requests VEX generation with justification code "component_not_present"
3. System checks if evidence bundle contains required deterministic evidence (sbom_component OR binary_analysis_result)
4. IF evidence present: Allow LLM synthesis
5. IF evidence missing: Block synthesis, return status "under_investigation"

**Acceptance Criteria**: AC-001, AC-002

---

### UC-002: Post-LLM Hallucination Detection
**Source**: Requirement - REQ-002
**Priority**: Critical

**Primary Path**:
1. LLM generates VEX statement with evidence_refs containing node IDs
2. System extracts all cited node_id values
3. System validates each node_id exists in pre-fetched evidence bundle
4. IF all node IDs exist: Mark statement valid
5. IF any node ID missing/fabricated: Block statement, severity="block"

**Error Path**:
- Invalid node ID format: Reject at Pydantic schema level before post-validation

**Acceptance Criteria**: AC-003, AC-004

---

### UC-003: Deterministic Evidence Ratio Check
**Source**: Requirement - REQ-003
**Priority**: High

**Primary Path**:
1. VEX statement cites N evidence nodes
2. System counts deterministic vs probabilistic nodes among cited evidence
3. IF >50% deterministic: Pass
4. IF ≤50% deterministic: Warn (severity="warn")

**Acceptance Criteria**: AC-005

---

### UC-004: Regulatory Bar Enforcement - FDA 524B
**Source**: Requirement - REQ-004
**Priority**: High

**Primary Path**:
1. VEX statement has status="not_affected" and regulatory_context contains "FDA_524B"
2. System checks evidence bundle for binary_analysis_result evidence
3. IF binary evidence present: Pass
4. IF binary evidence missing: Warn (severity="warn") with rationale

**Acceptance Criteria**: AC-006

---

### UC-005: Wrapper Pattern Integration
**Source**: Design-Risk - Maintain backward compatibility
**Priority**: Critical

**Primary Path**:
1. User calls EnforcedVEXSynthesizer.synthesize()
2. System attempts GroundedVEXSynthesizer.generate() (enforcement layer)
3. IF enforcement succeeds: Return {vex_document, validation_failures, submission_ready, mode="grounded"}
4. IF enforcement fails: Fallback to VEXSynthesizerV2.synthesize() (existing V2)

**Fallback Path**:
- Enforcement layer exception: Log warning, use V2 fallback, return mode="v2_fallback"

**Acceptance Criteria**: AC-007, AC-008

---

## Acceptance Criteria

| ID | Criterion | Testable Outcome | Mapped Use Case | Priority |
|----|-----------|------------------|-----------------|----------|
| AC-001 | Evidence sufficiency check blocks synthesis when required evidence missing | Given CVE with no SBOM evidence, when request justification="component_not_present", then return status="under_investigation" with reason | UC-001 | Critical |
| AC-002 | Evidence sufficiency check allows synthesis when required evidence present | Given CVE with SBOM evidence (deterministic), when request justification="component_not_present", then allow LLM synthesis | UC-001 | Critical |
| AC-003 | Hallucination detection rejects fabricated node IDs | Given LLM output with node_id="fake_collection/fake123", when validate against bundle, then return ValidationFailure(severity="block") | UC-002 | Critical |
| AC-004 | Hallucination detection passes real node IDs | Given LLM output with node_id from pre-fetched bundle, when validate, then pass validation | UC-002 | Critical |
| AC-005 | Deterministic ratio warning triggers correctly | Given VEX statement citing 3 probabilistic + 1 deterministic node, when validate, then return ValidationFailure(severity="warn") about LLM-heavy evidence | UC-003 | High |
| AC-006 | FDA 524B binary analysis requirement enforced | Given status="not_affected", regulatory_context=["FDA_524B"], no binary_analysis evidence, when validate, then return ValidationFailure(severity="warn") requiring binary analysis | UC-004 | High |
| AC-007 | Wrapper pattern uses enforcement layer when available | Given valid evidence bundle, when call EnforcedVEXSynthesizer, then use GroundedVEXSynthesizer and return mode="grounded" | UC-005 | Critical |
| AC-008 | Wrapper pattern falls back to V2 on enforcement failure | Given enforcement layer exception, when call EnforcedVEXSynthesizer, then fallback to VEXSynthesizerV2 and return mode="v2_fallback" | UC-005 | Critical |
| AC-009 | Pydantic schema validation rejects invalid node ID format | Given node_id="invalid format no slash", when instantiate VEXStatement, then raise ValidationError before post-validation | UC-002 | Critical |
| AC-010 | Function calling prevents prose escape hatch | Given Claude function-calling mode with tool_choice="any", when call LLM, then receive only tool_use blocks (no text content blocks) | - | High |

---

## Out of Scope

- **VEX V2 Refactoring**: Do not modify existing VEXSynthesizerV2 internal implementation
- **New Evidence Collection**: Do not implement new scanners/agents (use existing evidence)
- **CSAF-specific validation**: Covered by existing V2 export methods
- **VEX lifecycle management**: Partially handled by existing assessment_version/timestamp fields
- **Multi-CVE batch processing**: Single CVE-component pair processing only

---

## Constraints

1. **Python Version**: Must work with Python 3.11+ (project requirement)
2. **Anthropic API**: Requires `anthropic>=0.18.0` for function calling
3. **Pydantic**: Must use Pydantic V2 (existing project dependency)
4. **ArangoDB**: Evidence node IDs follow ArangoDB format: `collection_name/document_key`
5. **Backward Compatibility**: Existing V2 callers must continue working without changes
6. **No Breaking Changes**: New enforcement layer is opt-in via wrapper pattern

---

## Assumptions (Updated After Investigation)

### ✅ Validated Assumptions

1. **Evidence Provenance Exists**: ✅ CONFIRMED
   - Evidence already has `graph_id` and `edge_id` fields
   - Source: `vex_evidence.py` CWEEvidence model (lines ~200-250)

2. **Backward Compatibility Feasible**: ✅ CONFIRMED
   - Wrapper pattern maintains compatibility
   - No breaking changes to existing V2 API

3. **Pydantic V2 Available**: ✅ CONFIRMED
   - Project uses Pydantic V2
   - Validation features compatible

### ⚠️ Refined Assumptions

1. **Evidence Collections - MVP SCOPE CHANGE**:
   - **Original Assumption**: All proposed collections exist
   - **Investigation Finding**: Many collections may not exist (static_analysis_findings_edges, binary_analysis_edges, etc.)
   - **Refined Assumption (MVP)**: Use only **existing** evidence types:
     - ✅ `has_weakness` (CVE → CWE edges) - EXISTS
     - ✅ `vulnerabilities` collection - EXISTS
     - ✅ `cwe` collection - EXISTS
     - ✅ `kev` collection (CISA KEV) - EXISTS
     - ✅ `violates_requirement` edges - EXISTS
   - **Future Enhancement**: Add SBOM/static analysis collections in separate ticket

2. **Deterministic Source Classification - INFERENCE-BASED**:
   - **Original Assumption**: All evidence has `source` field populated
   - **Investigation Finding**: Source field not consistently populated
   - **Refined Assumption**: Infer deterministic classification from evidence type:
     ```python
     # Deterministic (curated/official data)
     - CWEEvidence → Deterministic (curated graph)
     - KEVEvidence → Deterministic (CISA official)

     # Probabilistic (ML/prediction)
     - ExploitabilityEvidence (EPSS) → Probabilistic (ML model)
     - LLM-sourced evidence → Probabilistic
     ```

3. **Supported Justification Codes - MVP SCOPE**:
   - **Original Assumption**: All CycloneDX justification codes supported
   - **Investigation Finding**: Limited evidence types available
   - **Refined Assumption (MVP)**: Support only justification codes backed by existing evidence:
     - ❌ `component_not_present` - Requires SBOM (not available in MVP)
     - ❌ `vulnerable_code_not_present` - Requires static analysis (not available in MVP)
     - ❌ `vulnerable_code_not_in_execute_path` - Requires reachability analysis (not available)
     - ✅ `vulnerable_code_cannot_be_controlled_by_adversary` - Use KEV + CWE evidence
     - ✅ `inline_mitigations_already_exist` - Use KEV absence + low EPSS as signal
   - **Future Enhancement**: Add full justification code support with SBOM/SAST collections

4. **Instructor Compatibility - DEFERRED TO STAGE 7**:
   - **Assumption**: Test in Stage 7 integration testing
   - **Fallback**: Use raw Anthropic client if instructor incompatible
   - **Recommendation**: Use instructor for consistency with existing V2

---

## Dependencies

### Internal Dependencies
- `src/complira_graph/llm_agents/vex_synthesizer_v2.py` - Existing VEX V2 synthesizer
- `src/complira_graph/models/vex_evidence.py` - Evidence and assessment Pydantic models
- `src/api/services/vex_evidence.py` - Evidence collection service
- `src/complira_graph/queries/vex_evidence_queries.py` - Graph evidence queries

### External Dependencies
- `anthropic>=0.18.0` - Claude Sonnet 4.5 with function calling
- `pydantic>=2.0` - Schema validation
- `python-arango` - ArangoDB client

---

## Open Questions

1. **Q1**: Do all evidence edges currently have `source` field populated?
   - **Risk**: If not, deterministic classification will fail
   - **Mitigation**: Add to investigation stage

2. **Q2**: Which edge collections are missing from current schema?
   - **Risk**: AQL traversal will fail if collections don't exist
   - **Mitigation**: Database schema audit in investigation stage

3. **Q3**: Does `instructor` package conflict with Anthropic function calling?
   - **Risk**: Runtime errors during LLM calls
   - **Mitigation**: Integration test in Stage 7

4. **Q4**: Should enforcement layer be mandatory or opt-in for FDA/CRA customers?
   - **Decision**: Start opt-in (wrapper pattern), plan future mandatory migration
   - **Impact**: Affects implementation strategy

---

## Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Hallucination Detection Rate | 100% | Unit tests with fabricated node IDs |
| Evidence Sufficiency Blocking | 100% | Unit tests with insufficient evidence bundles |
| Backward Compatibility | 0 breaking changes | Integration tests with existing V2 callers |
| Regulatory Validation Coverage | 100% FDA/CRA rules | Unit tests for regulatory bar enforcement |
| Wrapper Fallback Success | 100% | Integration tests with forced enforcement failures |

---

## Risks

| Risk ID | Risk | Probability | Impact | Mitigation |
|---------|------|-------------|--------|------------|
| R-001 | Missing evidence edge collections | High | High | Database schema audit in Stage 1 investigation |
| R-002 | Evidence source field not populated | Medium | High | Schema validation in Stage 1 investigation |
| R-003 | Instructor/Anthropic conflict | Low | Medium | Early integration test in Stage 7 |
| R-004 | LLM finds escape hatch around function calling | Low | High | Post-validation catches any non-tool-use responses |
| R-005 | Performance degradation from double-validation | Low | Low | Validation is fast (in-memory set lookups) |

---

## Requirements-to-Use-Case Coverage Matrix

| Requirement ID | Description | Mapped Use Cases | Coverage Status |
|----------------|-------------|------------------|-----------------|
| REQ-001 | Pre-LLM evidence sufficiency validation | UC-001 | Covered |
| REQ-002 | Post-LLM hallucination detection | UC-002 | Covered |
| REQ-003 | Deterministic vs probabilistic tracking | UC-003 | Covered |
| REQ-004 | Regulatory bar enforcement | UC-004 | Covered |
| REQ-005 | Wrapper pattern integration | UC-005 | Covered |

---

## Notes

- **Original Proposal**: Based on VEX justification enforcement layer provided by user
- **SOTA Analysis**: Gaps identified from comparison with V2 implementation
- **Implementation Strategy**: Wrapper pattern preferred for low-risk rollout
- **Future Work**: Consider mandatory enforcement for FDA/CRA contexts after validation

---

## Triage Result

**Scope**: `Medium`

**Rationale**:
- **Estimated Files Touched**: 4-6 files (new enforcement layer + wrapper + integration + tests)
- **Cross-Layer Impact**: Touches LLM agent layer, service layer, and validation layer
- **New Public APIs**: Yes (EnforcedVEXSynthesizer wrapper class)
- **Schema Changes**: No (uses existing Pydantic models, extends with new validation models)
- **Architectural Impact**: Medium (adds new validation layer but no changes to existing layers)

**Workflow Depth**:
- Requires proposed design document
- Requires future-state runtime call stacks per use case
- Requires iterative deep-review rounds
- Requires comprehensive API/E2E testing for regulatory compliance scenarios
