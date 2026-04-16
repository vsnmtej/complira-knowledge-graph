# Proposed Design: VEX Justification Enforcement Layer

**Version**: v1
**Date**: 2026-03-07
**Status**: Draft (for Stage 4 runtime modeling)
**Scope**: Medium
**Ticket**: `vex-justification-enforcement`

---

## Executive Summary

Add a VEX Justification Enforcement Layer that grounds every VEX statement in traceable knowledge graph evidence before LLM synthesis and validates outputs to prevent hallucination. Implementation uses **wrapper pattern** to maintain backward compatibility with existing VEX Synthesizer V2.

**Key Design Decision**: New enforcement layer as **opt-in wrapper**, not modification of existing V2 core.

---

## Current State (As-Is)

### Existing Architecture

```
API Request
  ↓
VEXEvidenceService.collect_evidence(cve_id, component_purl)
  ↓ (AQL queries via vex_evidence_queries)
ArangoDB Graph Traversal → VulnerabilityEvidence package
  ↓
VEXSynthesizerV2.synthesize_vex(evidence)
  ↓ (Claude Sonnet 4.5 + instructor wrapper + Pydantic)
VEXAssessment (with schema validation only)
  ↓
export_cyclonedx() / export_csaf()
```

### Existing Modules

| Module | Responsibility | Lines | Layer |
|--------|---------------|-------|-------|
| `llm_agents/vex_synthesizer_v2.py` | VEX generation via LLM | 988 | LLM Agent |
| `models/vex_evidence.py` | Pydantic evidence/assessment models | 1627 | Model |
| `api/services/vex_evidence.py` | Evidence collection orchestration | ~500 | Service |
| `queries/vex_evidence_queries.py` | AQL query library | ~1000 | Query |

### Current Validation (VEXSynthesizerV2._validate_assessment, lines 492-550)

**What V2 Validates**:
- ✅ Status consistency (not in SBOM → must be "not_affected")
- ✅ Justification required for "not_affected" status
- ✅ Response action required for "affected" status
- ✅ Pydantic schema compliance (field types, formats)

**What V2 Does NOT Validate** (gaps):
- ❌ Evidence sufficiency before LLM call
- ❌ Justification code backed by deterministic evidence
- ❌ Cited evidence node IDs actually exist in graph
- ❌ Deterministic vs probabilistic evidence ratio
- ❌ Regulatory-context-specific requirements

---

## Target State (To-Be)

### Proposed Architecture

```
API Request
  ↓
EnforcedVEXSynthesizer.synthesize(scan_session_id, customer_id, regulatory_context)
  ↓
[NEW LAYER 1: Pre-LLM Evidence Validation]
  VEXEvidenceBundle (with deterministic flags, node ID index)
  ├─ validate evidence sufficiency for requested justification
  └─ IF insufficient → return status="under_investigation", block LLM call
  ↓ (IF sufficient)
GroundedVEXSynthesizer.generate()
  ├─ Build function-calling prompt (inject only real node IDs)
  ├─ Call Claude with tools (not free-form text)
  └─ Parse tool_use outputs → VEXStatement objects
  ↓
[NEW LAYER 2: Post-LLM Validation]
  VEXJustificationValidator.validate(doc, bundles)
  ├─ Check cited node IDs exist in bundle
  ├─ Check justification supported by deterministic evidence
  ├─ Check deterministic/probabilistic ratio
  ├─ Check regulatory bar (FDA binary analysis, CRA detail length)
  └─ Return ValidationFailures (blocking/warnings)
  ↓
IF blocking failures → Filter out failed statements
ELSE → Return validated VEXDocument
  ↓
[FALLBACK PATH on enforcement failure]
VEXSynthesizerV2.synthesize_vex(evidence)  # Existing V2
```

### Target Modules

| Module | Responsibility | Change Type | Layer |
|--------|---------------|-------------|-------|
| `llm_agents/vex_enforcement/__init__.py` | Package init | **Add** | LLM Agent |
| `llm_agents/vex_enforcement/grounding.py` | Evidence bundle + validation models | **Add** | LLM Agent |
| `llm_agents/vex_enforcement/synthesizer.py` | Grounded VEX synthesizer with function calling | **Add** | LLM Agent |
| `llm_agents/vex_enforcement/validator.py` | Post-generation validation | **Add** | LLM Agent |
| `llm_agents/vex_enforcement/wrapper.py` | EnforcedVEXSynthesizer wrapper with fallback | **Add** | LLM Agent |
| `api/services/vex_evidence.py` | (Optional) Add deterministic flag to evidence | **Modify** (optional) | Service |
| `tests/llm_agents/vex_enforcement/` | Unit tests for enforcement layer | **Add** | Test |

---

## Architecture Direction Decision

### Decision: **Add New Layer (Wrapper Pattern)**

### Rationale

**Complexity**: Medium
- New validation layer adds modest complexity
- Wrapper pattern isolates changes from existing V2

**Testability**: High
- Enforcement layer independently testable
- V2 remains untouched, existing tests unchanged
- New tests target only enforcement logic

**Operability**: High
- Opt-in deployment (feature flag or explicit wrapper use)
- Gradual rollout to high-risk customers first
- Easy rollback (remove wrapper, revert to V2)

**Evolution Cost**: Low
- Future enhancements contained to enforcement layer
- V2 can evolve independently
- Clear separation of concerns

### Alternatives Considered

**Alternative 1: Modify VEXSynthesizerV2 Directly**
- **Pros**: Single code path, no wrapper overhead
- **Cons**: High risk (breaks existing V2), harder to rollback, mixing concerns
- **Rejected**: Too risky for existing deployments

**Alternative 2: Fork VEXSynthesizerV2 to V3**
- **Pros**: Clean separation, both versions available
- **Cons**: Code duplication, maintenance burden, unclear migration path
- **Rejected**: Violates DRY principle

---

## Change Inventory

### Add (New Files)

| File | Purpose | Public APIs | Estimated Lines |
|------|---------|-------------|-----------------|
| `src/complira_graph/llm_agents/vex_enforcement/__init__.py` | Package exports | `EnforcedVEXSynthesizer`, `GroundedVEXSynthesizer`, `VEXJustificationValidator` | ~20 |
| `src/complira_graph/llm_agents/vex_enforcement/grounding.py` | Evidence models + mapping logic | `VEXEvidenceBundle`, `EvidenceNode`, `JustificationCode`, `REQUIRED_EVIDENCE_FOR_JUSTIFICATION` | ~250 |
| `src/complira_graph/llm_agents/vex_enforcement/synthesizer.py` | Grounded LLM synthesis | `GroundedVEXSynthesizer.generate()`, `build_synthesizer_prompt()`, `SYNTHESIZER_TOOLS` | ~300 |
| `src/complira_graph/llm_agents/vex_enforcement/validator.py` | Post-generation validation | `VEXJustificationValidator.validate()`, `ValidationFailure` model | ~250 |
| `src/complira_graph/llm_agents/vex_enforcement/wrapper.py` | Wrapper with fallback | `EnforcedVEXSynthesizer.synthesize()` | ~150 |
| `tests/llm_agents/vex_enforcement/test_grounding.py` | Grounding logic tests | N/A (test file) | ~200 |
| `tests/llm_agents/vex_enforcement/test_validator.py` | Validator tests | N/A (test file) | ~300 |
| `tests/llm_agents/vex_enforcement/test_integration.py` | End-to-end tests | N/A (test file) | ~250 |
| `tests/fixtures/vex_enforcement/sample_evidence_bundle.json` | Test fixture | N/A (data file) | ~100 |

**Total New Code**: ~1,170 lines (implementation) + ~750 lines (tests) = **~1,920 lines**

### Modify (Existing Files - Optional)

| File | Change | Reason | Risk |
|------|--------|--------|------|
| `src/api/services/vex_evidence.py` | Add `deterministic: bool` flag to evidence collection | Enable deterministic/probabilistic classification | **Low** - additive change, backward compatible |

**Note**: This modification is **optional for MVP**. Can infer deterministic classification from evidence type instead.

### Rename/Move

None. Existing V2 files remain unchanged.

### Remove

None. No deprecated code (new layer only).

---

## Module Specifications

### Module 1: `vex_enforcement/grounding.py`

**Layer**: LLM Agent / Validation
**Responsibility**: Define evidence models and justification-to-evidence mapping rules

**Public APIs**:
```python
class EvidenceNode(BaseModel):
    """Single knowledge graph node with deterministic flag."""
    node_id: str  # ArangoDB _id (collection/key format)
    node_key: str
    collection: str
    summary: str
    source: str
    deterministic: bool  # True if scanner/curated, False if LLM-sourced
    confidence: Optional[float]

    @property
    def evidence_type(self) -> str:
        """Infer evidence type from collection name."""

class VEXEvidenceBundle(BaseModel):
    """Pre-fetched evidence for one CVE with validation methods."""
    cve_id: str
    component_purl: str
    component_cpe: Optional[str]
    nodes: List[EvidenceNode]

    def available_evidence_types(self) -> Set[str]: ...
    def deterministic_nodes(self) -> List[EvidenceNode]: ...
    def can_support_justification(self, code: JustificationCode) -> bool: ...

class JustificationCode(str, Enum):
    """CycloneDX/CSAF justification codes (MVP subset)."""
    VULNERABLE_CODE_NOT_CONTROLLABLE = "vulnerable_code_cannot_be_controlled_by_adversary"
    INLINE_MITIGATIONS_EXIST = "inline_mitigations_already_exist"

# Justification-to-evidence mapping (enforcement rules)
REQUIRED_EVIDENCE_FOR_JUSTIFICATION: Dict[JustificationCode, List[str]] = {
    JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE: ["kev_evidence", "cwe_evidence"],
    JustificationCode.INLINE_MITIGATIONS_EXIST: ["kev_evidence", "exploitability_evidence"],
}
```

**Inputs**: Evidence from graph traversal
**Outputs**: VEXEvidenceBundle with validation methods
**Dependencies**: `pydantic`, `models/vex_evidence.py` (for evidence type inference)

**Key Design Notes**:
- **Deterministic inference**: If `source` field missing, infer from evidence type
  - CWEEvidence → Deterministic (curated graph)
  - KEVEvidence → Deterministic (CISA official)
  - ExploitabilityEvidence (EPSS) → Probabilistic (ML model)

---

### Module 2: `vex_enforcement/synthesizer.py`

**Layer**: LLM Agent
**Responsibility**: Grounded VEX synthesis with Anthropic function calling

**Public APIs**:
```python
class GroundedVEXSynthesizer:
    """VEX synthesizer with pre-LLM validation and function calling enforcement."""

    def __init__(self, anthropic_client, kg_client): ...

    async def generate(
        self,
        scan_session_id: str,
        customer_id: str,
        regulatory_context: List[str]
    ) -> VEXDocument:
        """Generate VEX document with evidence grounding."""
        # 1. Fetch evidence bundles from KG
        bundles = await self._fetch_evidence_bundles(...)

        # 2. Build grounded prompt (inject only real node IDs)
        prompt = build_synthesizer_prompt(bundles)

        # 3. Call Claude with function calling
        response = self.client.messages.create(
            model="claude-sonnet-4-5",
            tools=SYNTHESIZER_TOOLS,
            tool_choice={"type": "any"},  # Force tool use
            messages=[{"role": "user", "content": prompt}]
        )

        # 4. Parse tool_use outputs → VEXStatement objects
        statements = self._parse_tool_outputs(response)

        # 5. Post-validation
        validator = VEXJustificationValidator(bundles_by_cve)
        self.last_validation_failures = validator.validate(doc)

        # 6. Filter blocking failures
        return self._filter_blocked_statements(doc)

    async def _fetch_evidence_bundles(...) -> List[VEXEvidenceBundle]: ...

def build_synthesizer_prompt(bundles: List[VEXEvidenceBundle]) -> str:
    """Inject evidence bundles as structured context."""
```

**Inputs**: scan_session_id, customer_id, regulatory_context
**Outputs**: VEXDocument with validation_failures
**Dependencies**: `anthropic`, `vex_enforcement/grounding.py`, `vex_enforcement/validator.py`

**Key Design Notes**:
- **Function calling vs instructor**: Test instructor compatibility first (Stage 7)
- **Prompt injection**: Only inject node IDs that exist in bundle → prevents fabrication

---

### Module 3: `vex_enforcement/validator.py`

**Layer**: Validation
**Responsibility**: Post-generation validation with blocking/warning severity

**Public APIs**:
```python
class ValidationFailure(BaseModel):
    """Single validation failure with severity."""
    cve_id: str
    component_purl: str
    reason: str
    severity: Literal["block", "warn"]  # block = can't submit; warn = review

class VEXJustificationValidator:
    """Post-generation validator for hallucination and evidence gaps."""

    def __init__(self, bundles: Dict[str, VEXEvidenceBundle]): ...

    def validate(self, doc: VEXDocument) -> List[ValidationFailure]:
        """Run all validation checks."""
        failures = []
        for stmt in doc.statements:
            failures.extend(self._check_node_ids_exist(stmt))
            failures.extend(self._check_justification_supported(stmt, bundle))
            failures.extend(self._check_determinism_ratio(stmt, bundle))
            failures.extend(self._check_regulatory_bar(stmt, bundle))
        return failures

    def _check_node_ids_exist(self, stmt: VEXStatement) -> List[ValidationFailure]:
        """Reject fabricated node IDs."""

    def _check_justification_supported(self, stmt, bundle) -> List[ValidationFailure]:
        """Ensure justification code backed by deterministic evidence."""

    def _check_determinism_ratio(self, stmt, bundle) -> List[ValidationFailure]:
        """Warn if >50% cited evidence is probabilistic."""

    def _check_regulatory_bar(self, stmt, bundle) -> List[ValidationFailure]:
        """FDA 524B: require binary analysis; CRA: require detailed narratives."""
```

**Inputs**: VEXDocument, VEXEvidenceBundle dict
**Outputs**: List[ValidationFailure]
**Dependencies**: `vex_enforcement/grounding.py`, `models/vex_evidence.py`

**Key Design Notes**:
- **Severity levels**: `block` prevents submission, `warn` allows with review
- **Regulatory rules**: FDA 524B requires `binary_analysis_result` evidence for "not_affected"

---

### Module 4: `vex_enforcement/wrapper.py`

**Layer**: LLM Agent / Integration
**Responsibility**: Wrapper with fallback to V2 on enforcement failure

**Public APIs**:
```python
class EnforcedVEXSynthesizer:
    """Drop-in replacement for VEXSynthesizerAgent with enforcement."""

    def __init__(self, anthropic_client, kg_client): ...

    async def synthesize(
        self,
        scan_session_id: str,
        customer_id: str,
        regulatory_context: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Generate VEX with enforcement, fallback to V2 on failure."""
        try:
            # Try grounded synthesis
            doc = await self.grounded_synth.generate(...)

            # Return with validation metadata
            return {
                "vex_document": doc.model_dump(),
                "validation_failures": [f.model_dump() for f in self.grounded_synth.last_validation_failures],
                "submission_ready": all(f.severity != "block" for f in ...),
                "mode": "grounded"  # Indicates enforcement used
            }
        except Exception as e:
            # Fallback to V2
            logger.warning(f"Enforcement failed, using V2 fallback: {e}")
            return await self.v2_synth.synthesize_vex(evidence)
```

**Inputs**: scan_session_id, customer_id, regulatory_context
**Outputs**: Dict with vex_document, validation_failures, submission_ready, mode
**Dependencies**: `vex_enforcement/synthesizer.py`, `llm_agents/vex_synthesizer_v2.py`

**Key Design Notes**:
- **Graceful degradation**: Enforcement failure → V2 fallback → user still gets VEX
- **Observability**: `mode` field indicates which path was used

---

## Dependency Flow

### Layer Dependencies (Top to Bottom)

```
┌─────────────────────────────────────────┐
│ API Layer (Future)                      │
│ - ScanService.generate_vex()            │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│ Integration Layer (NEW)                 │
│ - EnforcedVEXSynthesizer (wrapper.py)   │
└──────┬───────────────────────┬──────────┘
       ↓                       ↓
┌──────────────────┐   ┌──────────────────┐
│ Enforcement      │   │ Existing V2      │
│ (synthesizer.py) │   │ (vex_synth_v2)   │
└────┬─────────────┘   └──────────────────┘
     ↓
┌──────────────────────────────────────────┐
│ Validation Layer (NEW)                   │
│ - validator.py, grounding.py             │
└──────┬───────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│ Model Layer (Existing)                   │
│ - vex_evidence.py, VulnerabilityEvidence │
└──────┬───────────────────────────────────┘
       ↓
┌──────────────────────────────────────────┐
│ Query Layer (Existing)                   │
│ - vex_evidence_queries.py                │
└──────────────────────────────────────────┘
```

### Module Dependencies

| Module | Depends On | Type |
|--------|-----------|------|
| `wrapper.py` | `synthesizer.py`, `vex_synthesizer_v2.py` | Direct import |
| `synthesizer.py` | `grounding.py`, `validator.py`, `anthropic` | Direct import |
| `validator.py` | `grounding.py`, `models/vex_evidence.py` | Direct import |
| `grounding.py` | `models/vex_evidence.py`, `pydantic` | Direct import |

**Dependency Direction**: Enforcement layer → Existing models (one-way, no cycles)

**Allowed Violations**: None. Clean one-way dependencies.

---

## Naming Decisions

### File Naming

| Name | Rationale | Alternatives Considered |
|------|-----------|------------------------|
| `vex_enforcement/` | Clear purpose, matches "enforcement layer" terminology | `vex_validation/` (rejected: too narrow) |
| `grounding.py` | Reflects "evidence grounding" core concept | `evidence_bundle.py` (rejected: too generic) |
| `synthesizer.py` | Parallels existing `vex_synthesizer_v2.py` | `grounded_synthesizer.py` (rejected: too verbose) |
| `validator.py` | Clear validation purpose | `post_validator.py` (rejected: "post" is impl detail) |
| `wrapper.py` | Describes integration pattern | `enforced_synthesizer.py` (rejected: confuses with synthesizer.py) |

### Class Naming

| Class | Rationale | Alignment with Conventions |
|-------|-----------|---------------------------|
| `EnforcedVEXSynthesizer` | Wrapper that adds enforcement | ✅ Follows `<Purpose>Synthesizer` pattern |
| `GroundedVEXSynthesizer` | Synthesizer with grounding | ✅ Descriptive, distinct from V2 |
| `VEXJustificationValidator` | Validates justifications | ✅ Follows `<Purpose>Validator` pattern |
| `VEXEvidenceBundle` | Bundle of evidence nodes | ✅ Follows `<Purpose>Bundle` pattern |
| `EvidenceNode` | Single graph node | ✅ Simple, clear |
| `ValidationFailure` | Single validation failure | ✅ Pydantic model convention |

**No Naming Drift**: All new names align with their responsibilities.

---

## Use-Case Coverage Matrix

| Use Case ID | Primary Path Covered | Fallback Path Covered | Error Path Covered | Mapped Sections in Runtime Call Stack |
|-------------|---------------------|----------------------|-------------------|--------------------------------------|
| UC-001 (Pre-LLM check) | Yes | N/A | Yes (insufficient evidence) | UC-001-PRIMARY, UC-001-ERROR |
| UC-002 (Hallucination detection) | Yes | N/A | Yes (fabricated node ID) | UC-002-PRIMARY, UC-002-ERROR |
| UC-003 (Determinism ratio) | Yes | N/A | Yes (warning issued) | UC-003-PRIMARY, UC-003-WARN |
| UC-004 (Regulatory bar) | Yes | N/A | Yes (warning issued) | UC-004-PRIMARY, UC-004-WARN |
| UC-005 (Wrapper fallback) | Yes | Yes (enforcement exception) | Yes (V2 fallback) | UC-005-PRIMARY, UC-005-FALLBACK |

**Coverage Status**: 100% (all primary, fallback, and error paths covered)

---

## Data Models

### New Models (in `grounding.py`)

```python
class EvidenceNode(BaseModel):
    node_id: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*/[a-zA-Z0-9_\-]+$")
    node_key: str
    collection: str
    summary: str
    source: str
    deterministic: bool
    confidence: Optional[float] = None

class VEXEvidenceBundle(BaseModel):
    cve_id: str
    component_purl: str
    component_cpe: Optional[str]
    nodes: List[EvidenceNode]

class EvidenceReference(BaseModel):
    node_id: str = Field(description="ArangoDB _id from evidence bundle")
    relevance_explanation: str

class VEXStatement(BaseModel):
    cve_id: str
    component_purl: str
    status: Literal["not_affected", "affected", "fixed", "under_investigation"]
    justification: Optional[JustificationCode]
    evidence_refs: List[EvidenceReference] = Field(min_items=2)  # Min 2 for not_affected
    detail: str  # Must mention at least one node_id inline
    regulatory_context: List[str] = Field(default_factory=list)

class VEXDocument(BaseModel):
    bom_format: Literal["CycloneDX"] = "CycloneDX"
    spec_version: Literal["1.5"] = "1.5"
    scan_session_id: str
    statements: List[VEXStatement]
    evidence_coverage: Dict[str, int] = Field(default_factory=dict)
```

### Extended Models (in `validator.py`)

```python
class ValidationFailure(BaseModel):
    cve_id: str
    component_purl: str
    reason: str
    severity: Literal["block", "warn"]
```

---

## Error Handling

| Error Scenario | Handling Strategy | User Impact |
|----------------|------------------|-------------|
| Evidence bundle fetch fails | Fallback to V2 synthesizer | VEX generated without enforcement |
| LLM function calling fails | Fallback to V2 synthesizer | VEX generated without enforcement |
| Node ID validation fails | Block statement (severity="block") | Statement excluded from VEX document |
| Justification unsupported | Block statement (severity="block") | Statement excluded from VEX document |
| Determinism ratio low | Warn (severity="warn") | Statement included with warning |
| Regulatory bar not met | Warn (severity="warn") | Statement included with warning |

**Principle**: Fail safe (fallback to V2) for infrastructure errors, fail secure (block) for validation errors.

---

## Testing Strategy

### Unit Tests

| Test File | Coverage Target | Test Count Estimate |
|-----------|----------------|-------------------|
| `test_grounding.py` | Evidence bundle creation, justification mapping | ~15 tests |
| `test_validator.py` | All validation rules (node IDs, justification, determinism, regulatory) | ~20 tests |
| `test_synthesizer.py` | Grounded synthesis, function calling parsing | ~10 tests |
| `test_wrapper.py` | Wrapper logic, fallback behavior | ~8 tests |

### Integration Tests

| Test File | Scenario | Dependencies |
|-----------|----------|--------------|
| `test_integration.py` | End-to-end VEX generation with enforcement | Requires test ArangoDB instance |
| `test_fallback.py` | Enforcement failure → V2 fallback | Mock Anthropic client to force errors |

---

## Migration/Rollout Plan

### Phase 1: MVP Deployment (Week 1-2)

1. Deploy enforcement layer with **feature flag disabled**
2. Integration tests in staging environment
3. Validate no impact to existing V2 users

### Phase 2: Opt-In Rollout (Week 3-4)

1. Enable enforcement for **internal testing**
2. Enable for **1-2 pilot customers** (FDA/CRA context)
3. Monitor validation failure rates, adjust rules if needed

### Phase 3: Broader Adoption (Week 5-6)

1. Enable for all **FDA/CRA regulatory context** customers
2. Add feature flag to API for customer selection
3. Plan mandatory migration timeline

### Decommission Plan

**None**. V2 remains available indefinitely as fallback path.

---

## Open Design Questions

### Q1: Instructor vs Raw Anthropic Function Calling?
**Status**: Deferred to Stage 7 integration testing
**Options**:
- A) Use `instructor` for consistency with V2
- B) Use raw Anthropic function calling per proposal
**Decision Criteria**: Compatibility test results in Stage 7

### Q2: Should deterministic flag be added to existing evidence models?
**Status**: Optional for MVP
**Options**:
- A) Add `deterministic: bool` field to `CWEEvidence`, `KEVEvidence`, etc.
- B) Infer deterministic classification from evidence type in enforcement layer
**Recommendation**: Option B for MVP (no model changes), Option A for future enhancement

### Q3: Should enforcement be mandatory for FDA/CRA contexts?
**Status**: Deferred to post-MVP
**Options**:
- A) Mandatory enforcement for regulatory contexts (block V2 fallback)
- B) Keep opt-in indefinitely
**Recommendation**: Start with Option B, evaluate after pilot customer feedback

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| v1 | 2026-03-07 | Initial design based on investigation findings | System |

---

## Approval Status

- [ ] Architecture review
- [ ] Stage 4: Runtime modeling
- [ ] Stage 5: Review gate passed
- [ ] Ready for implementation (Stage 6)
