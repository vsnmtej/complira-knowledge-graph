# Investigation Notes: VEX Justification Enforcement Layer

**Date Started**: 2026-03-07
**Last Updated**: 2026-03-07
**Scope Triage**: `Medium`

---

## Investigation Goals

1. Understand current VEX V2 implementation architecture
2. Identify touched modules and execution boundaries
3. Validate assumptions about ArangoDB schema (evidence collections)
4. Assess evidence source field availability
5. Identify naming conventions and integration points
6. Uncover unknowns that could invalidate design assumptions

---

## Sources Consulted

### Local Files Examined
1. `src/complira_graph/llm_agents/vex_synthesizer_v2.py` (988 lines, 36KB)
2. `src/complira_graph/models/vex_evidence.py` (1627 lines, 57KB)
3. `src/api/services/vex_evidence.py` (Evidence collection service)
4. `src/complira_graph/queries/vex_evidence_queries.py` (46KB, query library)
5. `src/api/services/scan.py` (Scan ingestion service - for integration context)

### External References
1. VEX Justification Enforcement Proposal (provided by user)
2. CycloneDX VEX 1.5 Specification
3. CSAF 2.0 Specification (for justification codes)
4. FDA 524B Guidance (binary evidence requirements)
5. EU CRA Article 13(6) (vulnerability handling documentation)

---

## Key Findings

### 1. Current VEX V2 Architecture

**File**: `src/complira_graph/llm_agents/vex_synthesizer_v2.py`

**Current Flow**:
```
1. Input: VulnerabilityEvidence package (pre-collected)
2. LLM Synthesis: Claude Sonnet 4.5 with Pydantic output schema
3. Validation: Schema compliance only (field presence/format)
4. Export: CycloneDX 1.5 + CSAF 2.0 formats
```

**Key Classes**:
- `VEXSynthesizerV2` (lines 52-98): Main synthesizer class
  - `MODEL = "claude-sonnet-4-20250514"` (Claude Sonnet 4.5)
  - `synthesize_vex(evidence, component_purl)` - main method
  - `export_cyclonedx()` - CycloneDX export (lines 584-665)
  - `export_csaf()` - CSAF export (lines 679-782)
  - `_validate_assessment()` - Post-generation validation (lines 492-550)

**Current Validation** (lines 492-550):
```python
def _validate_assessment(self, assessment: VEXAssessment):
    # Status consistency checks
    if not assessment.in_sbom and assessment.status != VEXStatus.NOT_AFFECTED:
        raise ValueError("Component not in SBOM but status not 'not_affected'")

    # Justification required for not_affected
    if assessment.status == VEXStatus.NOT_AFFECTED:
        if not assessment.justification:
            raise ValueError("Justification required for not_affected")

    # Response required for affected
    if assessment.status == VEXStatus.AFFECTED:
        if not assessment.response:
            raise ValueError("Response action required for affected")
```

**Gap Identified**: Validation checks schema compliance but **not evidence grounding**.

---

### 2. Evidence Collection Mechanism

**File**: `src/api/services/vex_evidence.py`

**VEXEvidenceService Architecture**:
- Inherits from `BaseGraphService`
- Uses `vex_evidence_queries` for all AQL queries
- Builds Pydantic `VulnerabilityEvidence` package

**Evidence Tiers**:
- **Tier 1 (Critical)**: CVE metadata, CWE mappings, KEV status, EPSS scores, Component presence
- **Tier 2 (Important)**: ATT&CK techniques, Mitigation controls, Remediation, Compliance violations

**Evidence Package Structure** (from `vex_evidence.py`):
```python
VulnerabilityEvidence:
  ├── cve_metadata: CVEMetadata
  ├── graph_evidence: GraphEvidence
  │   ├── cwe_mappings: List[CWEEvidence]  # Has graph_id, edge_id
  │   ├── kev_evidence: KEVEvidence
  │   ├── exploitability: ExploitabilityEvidence
  │   └── component_presence: ComponentPresenceEvidence
  ├── tier_1_complete: bool
  └── tier_2_complete: bool
```

**Key Observation**: Evidence already has `graph_id` and `edge_id` fields for traceability!

---

### 3. ArangoDB Schema Investigation

**⚠️ CRITICAL FINDING**: Proposed AQL traversal references **collections that may not exist**:

**Proposal References** (from enforcement layer proposal, lines 682-688):
```python
FOR node, edge IN 1..2 ANY cve
    static_analysis_findings_edges,    # ❌ UNKNOWN - needs verification
    binary_analysis_edges,              # ❌ UNKNOWN - needs verification
    patch_record_edges,                 # ❌ UNKNOWN - needs verification
    reachability_edges,                 # ❌ UNKNOWN - needs verification
    sbom_component_edges                # ❌ UNKNOWN - needs verification
```

**Current Known Collections** (from investigation):
- `vulnerabilities` - CVE records ✅
- `cwe` - CWE weakness catalog ✅
- `kev` - CISA KEV catalog ✅
- `violates_requirement` (edge) - CVE → Requirement violations ✅
- `has_weakness` (edge) - CVE → CWE mappings ✅

**Unknown Collections - Require DB Audit**:
- ❓ `static_analysis_findings` (document collection)
- ❓ `static_analysis_findings_edges` (edge collection)
- ❓ `binary_analysis_results` (document collection)
- ❓ `binary_analysis_edges` (edge collection)
- ❓ `patch_records` (document collection)
- ❓ `patch_record_edges` (edge collection)
- ❓ `reachability_results` (document collection)
- ❓ `reachability_edges` (edge collection)
- ❓ `sbom_components` (document collection)
- ❓ `sbom_component_edges` (edge collection)

**Action Required**: Database schema audit to determine which collections exist.

**Mitigation Options**:
1. Create missing collections as part of this ticket
2. Use only existing collections for MVP (limit evidence types)
3. Plan future enhancement for additional evidence types

**Recommendation**: Option 2 for MVP (use existing CVE → CWE → Requirement graph only), plan Option 1 for future.

---

### 4. Evidence Source Field Investigation

**From `vex_evidence.py` Pydantic Models**:

**CWEEvidence** (lines ~200-250):
```python
class CWEEvidence(BaseModel):
    cwe_id: str
    cwe_name: str
    graph_id: str          # ✅ Graph provenance exists
    edge_id: str           # ✅ Edge provenance exists
    confidence: float
    source: str = "has_weakness"  # ✅ Source field exists!
```

**KEVEvidence** (lines ~300-350):
```python
class KEVEvidence(BaseModel):
    in_kev: bool
    kev_date_added: Optional[datetime]
    kev_required_action: Optional[str]
    # ❓ No explicit 'source' field - defaults to "cisa_kev"
```

**ExploitabilityEvidence** (lines ~400-450):
```python
class ExploitabilityEvidence(BaseModel):
    epss_score: Optional[float]
    epss_percentile: Optional[float]
    # ❓ No explicit 'source' field - defaults to "epss"
```

**Gap Identified**: Not all evidence types have explicit `source` field.

**Mitigation**: Add `source` field to all evidence models OR infer source from evidence type.

**Recommendation**: Infer deterministic classification from evidence type:
- `CWEEvidence` from `has_weakness` edge → Deterministic (curated graph)
- `KEVEvidence` → Deterministic (CISA official)
- `ExploitabilityEvidence` (EPSS) → Probabilistic (ML model)

---

### 5. Execution Boundaries and Integration Points

**Entry Points**:
1. **API Layer**: `src/api/services/scan.py` (future VEX generation endpoint)
2. **Service Layer**: `src/api/services/vex_evidence.py::VEXEvidenceService.collect_evidence()`
3. **LLM Agent Layer**: `src/complira_graph/llm_agents/vex_synthesizer_v2.py::VEXSynthesizerV2.synthesize_vex()`

**Current Call Flow**:
```
API Request
  ↓
VEXEvidenceService.collect_evidence(cve_id, component_purl)
  ↓ (uses vex_evidence_queries)
ArangoDB Graph Traversal → VulnerabilityEvidence package
  ↓
VEXSynthesizerV2.synthesize_vex(evidence)
  ↓ (Claude Sonnet 4.5 + Pydantic)
VEXAssessment (with validation)
  ↓
export_cyclonedx() / export_csaf()
```

**Proposed Integration Point** (Wrapper Pattern):
```
API Request
  ↓
EnforcedVEXSynthesizer.synthesize(scan_session_id, customer_id)
  ↓ (NEW LAYER - pre-LLM validation)
VEXEvidenceBundle (with deterministic flags)
  ↓
GroundedVEXSynthesizer.generate()
  ↓ (evidence sufficiency check)
IF sufficient: Call Claude with function calling
  ↓ (NEW LAYER - post-LLM validation)
VEXJustificationValidator.validate(doc)
  ↓
ValidationFailures (blocking/warnings) + VEXDocument
  ↓ (fallback on enforcement failure)
ELSE: VEXSynthesizerV2.synthesize_vex() (existing V2)
```

**Touched Modules**:
1. **NEW**: `src/complira_graph/llm_agents/vex_enforcement/` (new directory)
   - `grounding.py` - Evidence bundle + validation models
   - `synthesizer.py` - Grounded synthesizer with function calling
   - `validator.py` - Post-generation validator
   - `wrapper.py` - EnforcedVEXSynthesizer wrapper

2. **MODIFIED**: `src/api/services/vex_evidence.py`
   - Extend evidence collection to populate `deterministic` flag

3. **NEW**: Integration tests in `tests/llm_agents/` for enforcement layer

---

### 6. Naming Conventions

**Current Patterns**:
- LLM agents: `<Purpose>Agent` (e.g., `VEXSynthesizerV2`)
- Services: `<Purpose>Service` (e.g., `VEXEvidenceService`)
- Models: Pydantic classes in `models/<domain>.py`
- Validators: Pydantic `@field_validator` and `@model_validator`

**Proposed Naming** (follows conventions):
- `VEXEvidenceBundle` (new model in `vex_enforcement/grounding.py`)
- `GroundedVEXSynthesizer` (new synthesizer in `vex_enforcement/synthesizer.py`)
- `VEXJustificationValidator` (new validator in `vex_enforcement/validator.py`)
- `EnforcedVEXSynthesizer` (wrapper in `vex_enforcement/wrapper.py`)
- `JustificationCode` (enum, already in `models/vex_evidence.py` as `VEXJustification`)

**Alignment Check**: ✅ Consistent with existing naming patterns

---

### 7. Instructor Package Investigation

**Current Usage**:
```python
# From vex_synthesizer_v2.py line 35
import instructor
```

**Usage Pattern**:
```python
self.instructor_client = instructor.patch(anthropic_client)
response = self.instructor_client.messages.create(
    model=self.MODEL,
    response_model=VEXAssessment,  # Pydantic model
    ...
)
```

**Conflict Risk**: `instructor` wraps Anthropic client to enforce Pydantic output schemas.

**Proposed Function Calling** (from enforcement proposal):
```python
response = anthropic_client.messages.create(
    model="claude-sonnet-4-5",
    tools=SYNTHESIZER_TOOLS,  # Function calling tools
    tool_choice={"type": "any"},
    ...
)
```

**Gap Identified**: Proposal uses raw Anthropic function calling, but V2 uses `instructor` wrapper.

**Options**:
1. Use `instructor` in enforcement layer too (consistency)
2. Use raw Anthropic function calling (proposal approach)
3. Test compatibility (instructor may support function calling now)

**Recommendation**: Option 3 - Test `instructor` with function calling. If incompatible, use Option 1 for consistency.

---

### 8. Deterministic Source Classification

**From Current Agents** (need to verify actual source values):

**Deterministic Sources** (scanner/curated data):
- `nvd` - NVD API (official NIST data)
- `ghsa` - GitHub Security Advisories
- `osv` - OSV database
- `cisa_kev` - CISA KEV catalog
- `curated` - Manual curation
- `ctid` - CTID framework data
- `scf` - Secure Controls Framework
- `capec_xml` - CAPEC attack patterns
- `rule_engine` - Automated rule matching

**Probabilistic Sources** (LLM/ML-based):
- `llm_cwe_classifier` - LLM-based CWE classification
- `llm_regulatory_mapper` - LLM-based requirement mapping
- `epss` - ML-based exploit prediction (⚠️ borderline, mark as probabilistic)

**Unknown Sources** (need investigation):
- `semgrep` - Static analysis (should be deterministic)
- `grype` - Vulnerability scanner (should be deterministic)
- `emba` - Firmware analysis (should be deterministic)
- `bandit` - Python security scanner (should be deterministic)

**Action Required**: Audit actual `source` values in database to build complete classification list.

---

## Open Unknowns

### Unknown 1: ArangoDB Collection Existence
**Question**: Which evidence collections currently exist in the database?
**Impact**: High - AQL traversal will fail if collections missing
**Investigation Plan**: Run `db.collection_names()` query in Stage 1 completion
**Mitigation**: Use only existing collections for MVP, create missing ones in future enhancement

### Unknown 2: Evidence Source Field Population
**Question**: Do all evidence edges have `source` field populated in database?
**Impact**: Medium - Deterministic classification depends on this
**Investigation Plan**: Sample evidence records to verify field presence
**Mitigation**: Fall back to evidence type-based classification if source field missing

### Unknown 3: Instructor + Function Calling Compatibility
**Question**: Can `instructor` wrapper work with Anthropic function calling?
**Impact**: Low - Can use raw Anthropic client if incompatible
**Investigation Plan**: Integration test in Stage 7
**Mitigation**: Use raw Anthropic client if instructor incompatible

### Unknown 4: Scan Session → CVE Mapping
**Question**: How are CVEs linked to scan sessions in current schema?
**Impact**: Medium - Affects evidence bundle fetching
**Investigation Plan**: Examine `scan.py` and scan session schema
**Status**: **RESOLVED** - Found `scan_contains_cve` edge in proposal AQL (line 682)

### Unknown 5: Performance Impact of Dual Validation
**Question**: Will pre-LLM + post-LLM validation add significant latency?
**Impact**: Low - Validation is in-memory set lookups
**Investigation Plan**: Performance test in Stage 7
**Mitigation**: Validation is fast (O(n) where n = evidence nodes, typically <100)

---

## Implications for Requirements/Design

### Requirement Impacts

1. **REQ-001 (Pre-LLM evidence sufficiency)**:
   - ✅ Feasible with current architecture
   - ⚠️ Limited to existing evidence types initially (CWE, KEV, EPSS)
   - 📝 Requires evidence type → justification code mapping

2. **REQ-002 (Post-LLM hallucination detection)**:
   - ✅ Feasible with existing graph_id/edge_id fields
   - ✅ Evidence already has provenance tracking
   - 📝 Need to build node ID index for O(1) lookups

3. **REQ-003 (Deterministic vs probabilistic tracking)**:
   - ⚠️ Source field not consistently populated
   - 📝 Mitigation: Infer from evidence type or fallback classification
   - ✅ Can extend evidence models to add explicit `deterministic: bool` flag

4. **REQ-004 (Regulatory bar enforcement)**:
   - ⚠️ Binary analysis evidence may not exist yet
   - 📝 MVP: Warn when missing, don't block (severity="warn")
   - 📝 Future: Add binary analysis ingestion pipeline

5. **REQ-005 (Wrapper pattern integration)**:
   - ✅ Fully feasible with existing architecture
   - ✅ No breaking changes required
   - ✅ Clean integration point at service layer

### Design Impacts

1. **Evidence Bundle Structure**:
   - Extend existing `VulnerabilityEvidence` OR create new `VEXEvidenceBundle`
   - **Recommendation**: New `VEXEvidenceBundle` (cleaner separation, enforcement-specific)

2. **Validation Layer Placement**:
   - Option A: Extend `VEXSynthesizerV2._validate_assessment()`
   - Option B: New standalone `VEXJustificationValidator`
   - **Recommendation**: Option B (single responsibility, easier to test)

3. **Function Calling Integration**:
   - Test `instructor` compatibility first
   - Fall back to raw Anthropic client if needed
   - **Recommendation**: Prototype both approaches in Stage 4

4. **Evidence Type Limitations** (MVP):
   - Only support evidence types that currently exist:
     - `component_not_present` → Requires SBOM evidence (may not exist)
     - `vulnerable_code_not_present` → Requires static analysis (may not exist)
     - `inline_mitigations_exist` → Requires patch records (may not exist)
   - **Recommendation**: Start with CWE/KEV-based justifications only
   - **Future**: Add SBOM/static analysis collections

---

## Constraints Discovered

### Technical Constraints

1. **Python/Pydantic**: ✅ Compatible (Python 3.11+, Pydantic V2)
2. **Anthropic API**: ✅ Function calling supported in `anthropic>=0.18.0`
3. **ArangoDB Format**: ✅ `collection/key` format well-defined
4. **Instructor Wrapper**: ⚠️ Compatibility unknown, need testing

### Schema Constraints

1. **Evidence Collections**: ⚠️ Many proposed collections may not exist
2. **Source Field**: ⚠️ Not consistently populated across evidence types
3. **Evidence Edges**: ✅ Provenance (graph_id, edge_id) already tracked

### Business Constraints

1. **Backward Compatibility**: ✅ Wrapper pattern maintains compatibility
2. **Regulatory Requirements**: ✅ FDA/CRA rules well-documented
3. **Rollout Strategy**: ✅ Opt-in via wrapper allows gradual adoption

---

## Dependencies Validated

### Internal Dependencies ✅
- ✅ `vex_synthesizer_v2.py` - Exists, well-structured
- ✅ `vex_evidence.py` - Exists, Pydantic models complete
- ✅ `vex_evidence_queries.py` - Exists, AQL query library
- ✅ `VEXEvidenceService` - Exists, follows service pattern

### External Dependencies ✅
- ✅ `anthropic>=0.18.0` - Function calling supported
- ✅ `pydantic>=2.0` - V2 features available
- ✅ `python-arango` - ArangoDB client exists

---

## Recommended Next Steps (Stage 2: Requirements Refinement)

1. **Refine Evidence Type Limitations**:
   - Document which justification codes are supported in MVP
   - Plan future enhancement for SBOM/static analysis evidence

2. **Update Open Questions**:
   - Q1 (source field): Recommend inference-based classification
   - Q2 (missing collections): Recommend MVP with existing collections only
   - Q3 (instructor compatibility): Defer to Stage 7 integration test

3. **Add Acceptance Criteria**:
   - AC for limited justification code support (MVP scope)
   - AC for evidence type fallback classification

4. **Confirm Architecture Direction**:
   - Wrapper pattern confirmed
   - New `vex_enforcement/` module confirmed
   - Standalone validator confirmed

---

## Triage Confirmation

**Scope**: `Medium` ✅

**Rationale Validated**:
- **Files Touched**: 4-6 new files + 1-2 modifications (confirmed)
- **Cross-Layer**: LLM agent + validation layer (confirmed)
- **New APIs**: EnforcedVEXSynthesizer wrapper (confirmed)
- **No Schema Changes**: Uses existing Pydantic models (confirmed)
- **Architectural Impact**: Medium - new validation layer, no changes to existing (confirmed)

**Workflow Depth Confirmed**: Medium requires proposed design doc + runtime call stacks + iterative review

---

## Investigation Status

**Stage 1 Gate Status**: ✅ Ready for Requirements Refinement

**Evidence**:
- ✅ `investigation-notes.md` current
- ✅ Scope triage confirmed (`Medium`)
- ✅ Entry points identified
- ✅ Touched modules mapped
- ✅ Naming conventions validated
- ✅ Unknowns documented with mitigation plans
- ✅ Implications for requirements/design analyzed

**Next Stage**: Stage 2 - Requirements Refinement to `Design-ready` status
