# Stage 7: API/E2E Testing Plan

**Ticket**: `vex-justification-enforcement`
**Stage**: 7 (API/E2E Testing)
**Status**: In Progress
**Date**: 2026-03-07

---

## Test Strategy

### Testing Approach
Stage 7 focuses on **integration and acceptance criteria validation** using:
1. **Integration Tests**: Test module interactions with mocked LLM/database
2. **AC Scenario Tests**: Validate each acceptance criterion with realistic scenarios
3. **E2E Documentation**: Document live integration requirements for production validation

### Scope

**In Scope for Stage 7**:
- ✅ Integration tests for synthesizer.py (with LLM mocking)
- ✅ Integration tests for wrapper.py (with fallback scenarios)
- ✅ AC scenario validation tests
- ✅ Module interaction testing
- ✅ Error path and fallback testing

**Out of Scope for Stage 7** (requires live services):
- ⏸️ Live LLM integration (requires Anthropic API key + costs)
- ⏸️ Live ArangoDB integration (requires database setup)
- ⏸️ Performance testing under load
- ⏸️ Production deployment validation

---

## Acceptance Criteria Test Plan

### AC-001: Evidence Sufficiency Check Blocks Synthesis
**Status**: ⏸️ Deferred to integration test with mocking
**Test Scenario**:
```python
# Given: CVE with no SBOM evidence
# When: Request justification="component_not_present"
# Then: Return status="under_investigation" with reason
```
**Implementation**: Integration test with mocked evidence bundle
**Priority**: High

### AC-002: Evidence Sufficiency Check Allows Synthesis
**Status**: ⏸️ Deferred to integration test with mocking
**Test Scenario**:
```python
# Given: CVE with SBOM evidence (deterministic)
# When: Request justification="component_not_present"
# Then: Allow LLM synthesis
```
**Implementation**: Integration test with mocked LLM
**Priority**: High

### AC-003: Hallucination Detection Rejects Fabricated Node IDs
**Status**: ✅ **VALIDATED** in unit tests
**Test**: `test_validator.py:test_check_node_ids_exist_hallucination`
**Result**: PASS - Blocks statements with fabricated node IDs

### AC-004: Hallucination Detection Passes Real Node IDs
**Status**: ✅ **VALIDATED** in unit tests
**Test**: `test_validator.py:test_check_node_ids_exist_success`
**Result**: PASS - Allows statements with valid node IDs

### AC-005: Deterministic Ratio Warning Triggers Correctly
**Status**: ✅ **VALIDATED** in unit tests
**Test**: `test_validator.py:test_check_determinism_ratio_low_deterministic`
**Result**: PASS - Warns when >50% evidence is probabilistic

### AC-006: FDA 524B Binary Analysis Requirement Enforced
**Status**: ✅ **VALIDATED** in unit tests
**Test**: `test_validator.py:test_check_regulatory_bar_fda_524b_missing_binary_analysis`
**Result**: PASS - Warns when binary analysis missing for FDA context

### AC-007: Wrapper Uses Enforcement Layer When Available
**Status**: ⏸️ Pending integration test
**Test Scenario**:
```python
# Given: Valid evidence bundle
# When: Call EnforcedVEXSynthesizer.synthesize()
# Then: Use GroundedVEXSynthesizer and return mode="grounded"
```
**Implementation**: Integration test with mocked synthesizer
**Priority**: High

### AC-008: Wrapper Falls Back to V2 on Enforcement Failure
**Status**: ⏸️ Pending integration test
**Test Scenario**:
```python
# Given: Enforcement layer exception
# When: Call EnforcedVEXSynthesizer.synthesize()
# Then: Fallback to VEXSynthesizerV2 and return mode="v2_fallback"
```
**Implementation**: Integration test with forced exception
**Priority**: High

### AC-009: Pydantic Schema Rejects Invalid Node ID Format
**Status**: ✅ **VALIDATED** in unit tests
**Test**: `test_grounding.py:test_evidence_node_invalid_node_id_format`
**Result**: PASS - Raises ValidationError for invalid format

### AC-010: Function Calling Prevents Prose Escape Hatch
**Status**: ⏸️ Deferred to live LLM integration
**Test Scenario**:
```python
# Given: Claude function-calling mode with tool_choice="any"
# When: Call LLM
# Then: Receive only tool_use blocks (no text content blocks)
```
**Implementation**: Requires live Anthropic API integration
**Priority**: Medium (design enforces this via instructor)

---

## Integration Test Implementation Plan

### Test Suite 1: Synthesizer Integration Tests
**File**: `tests/llm_agents/vex_enforcement/test_synthesizer_integration.py`

**Tests to Implement**:
1. ✅ Test evidence sufficiency filtering (AC-001, AC-002)
2. ✅ Test grounded prompt building with real node IDs
3. ✅ Test under_investigation document creation
4. ✅ Test validation integration (synthesizer → validator)
5. ✅ Test evidence coverage calculation

**Mocking Strategy**: Mock `instructor_client.messages.create()` to return VEXDocument

### Test Suite 2: Wrapper Integration Tests
**File**: `tests/llm_agents/vex_enforcement/test_wrapper_integration.py`

**Tests to Implement**:
1. ✅ Test wrapper uses grounded synthesizer (AC-007)
2. ✅ Test wrapper fallback to V2 on exception (AC-008)
3. ✅ Test mode tracking ("grounded" vs "v2_fallback")
4. ✅ Test validation metadata in response
5. ✅ Test submission readiness flag

**Mocking Strategy**: Mock GroundedVEXSynthesizer and VEXSynthesizerV2

### Test Suite 3: AC Scenario Validation
**File**: `tests/llm_agents/vex_enforcement/test_ac_scenarios.py`

**Tests to Implement**:
1. ✅ AC-001 + AC-002: Evidence sufficiency scenarios
2. ✅ AC-007 + AC-008: Wrapper pattern scenarios
3. ✅ Combined workflow: Evidence → Synthesis → Validation → Filter

**Approach**: End-to-end scenarios with full mocking

---

## Test Coverage Goals

### Target Coverage
- **Integration Tests**: 60-70% coverage for synthesizer.py and wrapper.py
- **Overall Enforcement Layer**: >80% combined coverage
- **AC Validation**: 10/10 AC either validated or documented for live testing

### Current Coverage Status
- grounding.py: 70.80% ✅
- validator.py: 94.83% ✅
- synthesizer.py: 29.77% ⏸️ (pending integration tests)
- wrapper.py: 31.71% ⏸️ (pending integration tests)

### Post-Stage 7 Target
- grounding.py: 70%+ ✅
- validator.py: 94%+ ✅
- synthesizer.py: 65%+ 🎯
- wrapper.py: 70%+ 🎯
- **Overall**: 75%+

---

## Live Integration Testing Requirements

### Prerequisites for Production Validation
1. **Anthropic API Access**
   - API key with Claude Sonnet 4.5 access
   - Budget for LLM calls (~$0.50-$1.00 per test run)

2. **ArangoDB Instance**
   - Test database with sample evidence data
   - Collections: vulnerabilities, cwes, kev, exploit_intelligence
   - Sample CVEs with evidence graph traversal

3. **Evidence Data**
   - At least 3-5 CVEs with complete evidence
   - Mix of deterministic and probabilistic evidence
   - FDA/CRA regulatory context examples

### Live Test Scenarios
**Scenario 1**: Happy Path
- CVE with complete evidence → grounded synthesis → all validations pass

**Scenario 2**: Insufficient Evidence
- CVE with minimal evidence → blocked synthesis → under_investigation status

**Scenario 3**: Hallucination Detection
- Force LLM to cite evidence → validate all node IDs → catch any hallucinations

**Scenario 4**: Regulatory Enforcement
- CVE with FDA context → validate binary analysis requirement → warning if missing

**Scenario 5**: Fallback Path
- Force enforcement failure → V2 fallback → verify mode="v2_fallback"

---

## Implementation Timeline

### Phase 1: Integration Test Implementation (Current)
- **Duration**: 1-2 hours
- **Deliverables**:
  - `test_synthesizer_integration.py` (~150 lines)
  - `test_wrapper_integration.py` (~100 lines)
  - `test_ac_scenarios.py` (~150 lines)

### Phase 2: Test Execution and Coverage Analysis
- **Duration**: 30 minutes
- **Deliverables**:
  - Run all tests (unit + integration)
  - Generate coverage report
  - Identify gaps

### Phase 3: AC Gate Closure
- **Duration**: 30 minutes
- **Deliverables**:
  - AC validation matrix
  - Live testing documentation
  - Stage 7 completion summary

---

## Success Criteria

### Stage 7 Exit Conditions
- ✅ Integration tests implemented for synthesizer.py
- ✅ Integration tests implemented for wrapper.py
- ✅ AC scenario validation tests complete
- ✅ Test suite passes (all integration tests green)
- ✅ Coverage >65% for synthesizer.py
- ✅ Coverage >70% for wrapper.py
- ✅ AC validation matrix complete (10/10 AC addressed)
- ✅ Live testing requirements documented

### Acceptable Outcomes
**Option A**: All integration tests pass with mocking
- Move to Stage 8 (Code Review)
- Document live testing for production validation

**Option B**: Integration tests reveal design issues
- Classified re-entry (Design Impact / Local Fix)
- Fix issues, re-run tests
- Move to Stage 8 after fixes

---

## Risk Mitigation

### Risk 1: Mocking Complexity
**Mitigation**: Use pytest-mock for clean mocking, focus on interface contracts

### Risk 2: Coverage Gaps
**Mitigation**: Prioritize critical paths (happy path + error paths), defer edge cases

### Risk 3: Time Constraints
**Mitigation**: Implement high-priority ACs first (AC-001, AC-002, AC-007, AC-008)

---

## Next Actions

1. ✅ Transition to Stage 7 (workflow-state.md updated)
2. ⏭️ Implement `test_synthesizer_integration.py`
3. ⏭️ Implement `test_wrapper_integration.py`
4. ⏭️ Implement `test_ac_scenarios.py`
5. ⏭️ Run full test suite and generate coverage report
6. ⏭️ Create AC validation matrix
7. ⏭️ Create Stage 7 completion summary
8. ⏭️ Transition to Stage 8 (Code Review)
