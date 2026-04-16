# Future-State Runtime Call Stacks: VEX Justification Enforcement Layer

**Version**: v1
**Date**: 2026-03-07
**Design Basis**: `proposed-design.md` v1
**Ticket**: `vex-justification-enforcement`

---

## Overview

This document models the **future-state (to-be)** execution behavior for all use cases, derived from the proposed design architecture. Each call stack shows:
- File and function paths at every frame (`path/to/file.py:functionName()`)
- Architectural boundaries (API → Service → LLM Agent → Validation)
- Decision gates and conditions
- State mutations and persistence points
- Async boundaries
- Error/fallback paths

**Note**: This models the TARGET design behavior, not current code behavior.

---

## Use Case Coverage Matrix

| Use Case ID | Source | Primary Path | Fallback Path | Error Path | Coverage Status |
|-------------|--------|-------------|---------------|-----------|----------------|
| UC-001 | Requirement REQ-001 | ✅ | N/A | ✅ | Complete |
| UC-002 | Requirement REQ-002 | ✅ | N/A | ✅ | Complete |
| UC-003 | Requirement REQ-003 | ✅ | N/A | ✅ | Complete |
| UC-004 | Requirement REQ-004 | ✅ | N/A | ✅ | Complete |
| UC-005 | Design-Risk | ✅ | ✅ | ✅ | Complete |

---

## UC-001: Pre-LLM Evidence Sufficiency Check

**Use Case ID**: `UC-001`
**Source**: Requirement REQ-001
**Description**: System validates evidence bundle contains required deterministic evidence before allowing LLM synthesis
**Objective**: Prevent wasted LLM calls when evidence insufficient for requested justification

### UC-001-PRIMARY: Sufficient Evidence Path

**Trigger**: User requests VEX generation, evidence bundle contains required deterministic evidence

**Call Stack**:

```
[ENTRY POINT - Service Layer]
src/api/services/scan.py:ScanService.generate_vex(scan_session_id, customer_id, regulatory_context)
  ↓
  DECISION: Use enforcement wrapper (feature flag enabled)
  ↓
src/complira_graph/llm_agents/vex_enforcement/wrapper.py:EnforcedVEXSynthesizer.synthesize(scan_session_id, customer_id, regulatory_context)
  ↓
  [NEW - Grounded Synthesis Path]
  ↓
src/complira_graph/llm_agents/vex_enforcement/synthesizer.py:GroundedVEXSynthesizer.generate(scan_session_id, customer_id, regulatory_context)
  ↓
  [ASYNC BOUNDARY - Database Query]
  ↓
src/complira_graph/llm_agents/vex_enforcement/synthesizer.py:GroundedVEXSynthesizer._fetch_evidence_bundles(scan_session_id, customer_id)
  ↓
  AQL Query: Traverse CVE → CWE → KEV → EPSS edges
  ↓
  [DATA TRANSFORMATION: AQL result → List[EvidenceNode]]
  for row in cursor:
    nodes = [
      EvidenceNode(
        node_id=n["node_id"],
        collection=n["collection"],
        source=n["source"],
        deterministic=(n["source"] in DETERMINISTIC_SOURCES)  # Classification logic
      )
      for n in row["nodes"]
    ]
  ↓
  [STATE MUTATION: Build VEXEvidenceBundle]
  bundle = VEXEvidenceBundle(
    cve_id=row["cve_id"],
    component_purl=row["component_purl"],
    nodes=nodes
  )
  ↓
  bundles.append(bundle)
  return bundles
  ↓
  [BACK TO generate()]
  ↓
src/complira_graph/llm_agents/vex_enforcement/synthesizer.py:GroundedVEXSynthesizer.generate()
  bundles = await _fetch_evidence_bundles(...)
  ↓
  [DECISION GATE - Evidence Sufficiency Check]
  ↓
src/complira_graph/llm_agents/vex_enforcement/grounding.py:VEXEvidenceBundle.can_support_justification(JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE)
  ↓
  required_types = REQUIRED_EVIDENCE_FOR_JUSTIFICATION[code]  # ["kev_evidence", "cwe_evidence"]
  available_types = self.available_evidence_types()  # From bundle.nodes
  deterministic_types = {n.evidence_type for n in self.deterministic_nodes()}
  ↓
  [DECISION: Check overlap]
  IF any(req in available_types and req in deterministic_types for req in required_types):
    return True  # ✅ Evidence sufficient
  ELSE:
    return False  # ❌ Evidence insufficient
  ↓
  [BRANCH: Sufficient Evidence]
  can_support_justification() returns True
  ↓
  [CONTINUE TO LLM SYNTHESIS]
  ↓
src/complira_graph/llm_agents/vex_enforcement/synthesizer.py:GroundedVEXSynthesizer.generate()
  prompt = build_synthesizer_prompt(bundles)
  ↓
src/complira_graph/llm_agents/vex_enforcement/synthesizer.py:build_synthesizer_prompt(bundles)
  ↓
  [DATA TRANSFORMATION: Bundle → Prompt Context]
  parts = []
  for bundle in bundles:
    parts.append(f"## CVE: {bundle.cve_id}")
    for node in bundle.nodes:
      parts.append(f"  - node_id: {node.node_id} | type: {node.evidence_type} | DETERMINISTIC" if node.deterministic else "PROBABILISTIC")
  ↓
  return "\n".join(parts)  # Prompt injecting ONLY real node IDs
  ↓
  [ASYNC BOUNDARY - LLM Call]
  ↓
  response = self.client.messages.create(
    model="claude-sonnet-4-5",
    tools=SYNTHESIZER_TOOLS,  # Function calling schema
    tool_choice={"type": "any"},  # Force tool use, no prose escape
    messages=[{"role": "user", "content": prompt}]
  )
  ↓
  [LLM generates VEXStatement objects via function calling]
  ↓
  [RETURN to wrapper]
  return VEXDocument(statements=statements)

[EXIT POINT]
Return: {"vex_document": doc, "mode": "grounded", "submission_ready": True}
```

**State Mutations**:
1. AQL cursor → List[EvidenceNode] (in-memory)
2. Evidence nodes → VEXEvidenceBundle (in-memory)
3. Bundle → Prompt string (in-memory)
4. LLM response → VEXDocument (in-memory)

**Observed Outcome**: VEX document generated with evidence-grounded justifications

---

### UC-001-ERROR: Insufficient Evidence Path

**Trigger**: User requests VEX generation, evidence bundle lacks required deterministic evidence

**Call Stack** (same until decision gate):

```
[... Same as PRIMARY until can_support_justification() ...]

src/complira_graph/llm_agents/vex_enforcement/grounding.py:VEXEvidenceBundle.can_support_justification(JustificationCode.VULNERABLE_CODE_NOT_CONTROLLABLE)
  ↓
  [DECISION: No deterministic evidence overlap]
  return False  # ❌ Evidence insufficient
  ↓
  [BRANCH: Insufficient Evidence]
  ↓
src/complira_graph/llm_agents/vex_enforcement/synthesizer.py:GroundedVEXSynthesizer.generate()
  ↓
  [DECISION GATE: Block LLM synthesis]
  IF not bundle.can_support_justification(requested_justification):
    ↓
    [EARLY RETURN - Create under_investigation statement]
    ↓
    statement = VEXStatement(
      cve_id=bundle.cve_id,
      status="under_investigation",  # ❌ Not enough evidence to claim "not_affected"
      justification=None,
      detail="Insufficient deterministic evidence for justification. Required: kev_evidence, cwe_evidence. Available: exploitability_evidence only."
    )
    ↓
    return VEXDocument(statements=[statement])

[EXIT POINT]
Return: {"vex_document": doc, "mode": "grounded", "submission_ready": False, "validation_failures": [...]}
```

**State Mutations**:
- No LLM call (blocked by evidence check)
- VEXStatement created with "under_investigation" status

**Observed Outcome**: VEX document returned with status="under_investigation", no LLM call made

---

## UC-002: Post-LLM Hallucination Detection

**Use Case ID**: `UC-002`
**Source**: Requirement REQ-002
**Description**: System validates cited evidence node IDs actually exist in knowledge graph
**Objective**: Prevent LLM from fabricating plausible-looking but fake evidence references

### UC-002-PRIMARY: Valid Node IDs Path

**Trigger**: LLM generates VEX statement, all cited node_ids exist in pre-fetched bundle

**Call Stack** (continues from UC-001 LLM synthesis):

```
[... LLM synthesis complete ...]

src/complira_graph/llm_agents/vex_enforcement/synthesizer.py:GroundedVEXSynthesizer.generate()
  ↓
  [LLM returned tool_use outputs]
  raw_statements = [block.input for block in response.content if block.type == "tool_use"]
  ↓
  [DATA TRANSFORMATION: Parse Pydantic models]
  statements = [VEXStatement(**raw) for raw in raw_statements]
  ↓
  doc = VEXDocument(
    scan_session_id=scan_session_id,
    statements=statements
  )
  ↓
  [POST-GENERATION VALIDATION]
  ↓
  bundles_by_cve = {b.cve_id: b for b in bundles}
  ↓
src/complira_graph/llm_agents/vex_enforcement/validator.py:VEXJustificationValidator(bundles_by_cve).__init__()
  ↓
  [STATE MUTATION: Build node ID index for O(1) lookup]
  self._all_node_ids = {
    node.node_id
    for bundle in bundles.values()
    for node in bundle.nodes
  }  # Set of all valid node IDs from KG
  ↓
src/complira_graph/llm_agents/vex_enforcement/validator.py:VEXJustificationValidator.validate(doc)
  ↓
  failures = []
  ↓
  for stmt in doc.statements:
    ↓
    failures.extend(self._check_node_ids_exist(stmt))
    ↓
src/complira_graph/llm_agents/vex_enforcement/validator.py:VEXJustificationValidator._check_node_ids_exist(stmt)
  ↓
  failures = []
  ↓
  for ref in stmt.evidence_refs:  # List[EvidenceReference]
    ↓
    [DECISION GATE: Node ID existence check]
    IF ref.node_id not in self._all_node_ids:  # O(1) set lookup
      ↓
      [BRANCH: Hallucinated node ID]
      failures.append(ValidationFailure(
        cve_id=stmt.cve_id,
        reason=f"Hallucinated evidence reference: '{ref.node_id}' does not exist in KG",
        severity="block"  # ❌ Cannot submit
      ))
    ELSE:
      ↓
      [BRANCH: Valid node ID]
      # No failure, continue
  ↓
  return failures  # Empty list = all node IDs valid
  ↓
  [BACK TO validate()]
  ↓
src/complira_graph/llm_agents/vex_enforcement/validator.py:VEXJustificationValidator.validate(doc)
  ↓
  self.last_validation_failures = failures  # Store for wrapper
  ↓
  return failures  # Empty list = validation passed

[EXIT POINT]
Return: {"vex_document": doc, "validation_failures": [], "submission_ready": True, "mode": "grounded"}
```

**State Mutations**:
1. Build `_all_node_ids` set (in-memory index)
2. Validate each evidence_ref.node_id against index
3. Collect validation failures

**Observed Outcome**: VEX document passes validation, all cited node IDs verified real

---

### UC-002-ERROR: Fabricated Node ID Path

**Trigger**: LLM generates VEX statement with fabricated node_id

**Call Stack** (diverges at decision gate):

```
[... Same as PRIMARY until _check_node_ids_exist() ...]

src/complira_graph/llm_agents/vex_enforcement/validator.py:VEXJustificationValidator._check_node_ids_exist(stmt)
  ↓
  for ref in stmt.evidence_refs:
    ↓
    [DECISION: Node ID fabricated]
    IF ref.node_id == "fake_collection/fake_key_123" not in self._all_node_ids:
      ↓
      [BRANCH: Hallucination detected]
      failures.append(ValidationFailure(
        cve_id=stmt.cve_id,
        component_purl=stmt.component_purl,
        reason=f"Hallucinated evidence reference: 'fake_collection/fake_key_123' does not exist in knowledge graph. This statement cannot be submitted.",
        severity="block"  # ❌ Blocking failure
      ))
  ↓
  return failures  # Contains blocking failure
  ↓
src/complira_graph/llm_agents/vex_enforcement/validator.py:VEXJustificationValidator.validate(doc)
  ↓
  [COLLECT all failures across all statements]
  ↓
  self.last_validation_failures = failures
  ↓
  return failures  # Contains blocking failures
  ↓
src/complira_graph/llm_agents/vex_enforcement/synthesizer.py:GroundedVEXSynthesizer.generate()
  ↓
  [FILTER BLOCKED STATEMENTS]
  blocking_cves = {f.cve_id for f in validation_failures if f.severity == "block"}
  ↓
  doc.statements = [s for s in doc.statements if s.cve_id not in blocking_cves]
  ↓
  return doc  # Blocked statements removed

[EXIT POINT]
Return: {"vex_document": doc (filtered), "validation_failures": [{"severity": "block", ...}], "submission_ready": False, "mode": "grounded"}
```

**State Mutations**:
- Fabricated statement filtered out from VEXDocument
- ValidationFailure recorded with severity="block"

**Observed Outcome**: Statement with fabricated node ID removed from VEX document, validation failure returned

---

## UC-003: Deterministic Evidence Ratio Check

**Use Case ID**: `UC-003`
**Source**: Requirement REQ-003
**Description**: System warns when >50% of cited evidence is probabilistic (LLM-sourced)
**Objective**: Flag VEX statements that rely heavily on non-deterministic evidence

### UC-003-PRIMARY: High Deterministic Ratio (Pass)

**Trigger**: VEX statement cites majority deterministic evidence

**Call Stack**:

```
[... After node ID validation ...]

src/complira_graph/llm_agents/vex_enforcement/validator.py:VEXJustificationValidator.validate(doc)
  ↓
  for stmt in doc.statements:
    ↓
    failures.extend(self._check_determinism_ratio(stmt, bundle))
    ↓
src/complira_graph/llm_agents/vex_enforcement/validator.py:VEXJustificationValidator._check_determinism_ratio(stmt, bundle)
  ↓
  IF not stmt.evidence_refs:
    return []  # No evidence, skip check
  ↓
  [GATHER cited nodes]
  cited_ids = {ref.node_id for ref in stmt.evidence_refs}
  ↓
  cited_nodes = [n for n in bundle.nodes if n.node_id in cited_ids]
  ↓
  [COUNT deterministic vs probabilistic]
  prob_count = sum(1 for n in cited_nodes if not n.deterministic)
  total_count = len(cited_nodes)
  ↓
  [DECISION GATE: Ratio check]
  IF prob_count > total_count / 2:  # >50% probabilistic
    ↓
    [BRANCH: Warning threshold exceeded]
    return [ValidationFailure(
      cve_id=stmt.cve_id,
      reason=f"{prob_count}/{total_count} cited evidence nodes are probabilistic (LLM-sourced). Regulatory reviewers may challenge this.",
      severity="warn"  # ⚠️ Warning, not blocking
    )]
  ELSE:
    ↓
    [BRANCH: Acceptable ratio]
    return []  # No warning

[EXIT POINT]
Return: validation_failures = [] (or warnings only, submission_ready=True)
```

**State Mutations**:
- Count deterministic/probabilistic nodes from cited evidence
- Generate warning if ratio exceeds threshold

**Observed Outcome**: Statement passes with no warnings (3 deterministic + 1 probabilistic = 75% deterministic)

---

### UC-003-WARN: Low Deterministic Ratio (Warning)

**Trigger**: VEX statement cites >50% probabilistic evidence

**Call Stack** (diverges at decision gate):

```
[... Same as PRIMARY until ratio check ...]

src/complira_graph/llm_agents/vex_enforcement/validator.py:VEXJustificationValidator._check_determinism_ratio(stmt, bundle)
  ↓
  prob_count = 3  # 3 probabilistic nodes
  total_count = 4  # 4 total cited nodes
  ↓
  [DECISION: 3/4 = 75% > 50%]
  IF 3 > 4 / 2:  # True
    ↓
    [BRANCH: Issue warning]
    return [ValidationFailure(
      cve_id=stmt.cve_id,
      component_purl=stmt.component_purl,
      reason="3/4 cited evidence nodes are probabilistic (LLM-sourced). Regulatory reviewers may challenge this. Run additional deterministic scanners before submission.",
      severity="warn"  # ⚠️ Warning, allows submission with review
    )]
  ↓
  return failures  # Contains warning

[EXIT POINT]
Return: {"vex_document": doc, "validation_failures": [{"severity": "warn", ...}], "submission_ready": True, "mode": "grounded"}
```

**State Mutations**:
- ValidationFailure created with severity="warn"
- Statement remains in document (warning doesn't block)

**Observed Outcome**: Warning issued, statement included in VEX document, submission_ready=True (warnings don't block)

---

## UC-004: Regulatory Bar Enforcement - FDA 524B

**Use Case ID**: `UC-004`
**Source**: Requirement REQ-004
**Description**: System enforces FDA 524B requirement for binary analysis evidence when status="not_affected"
**Objective**: Ensure VEX statements meet regulatory evidence requirements

### UC-004-PRIMARY: Binary Analysis Present (Pass)

**Trigger**: status="not_affected", regulatory_context=["FDA_524B"], binary analysis evidence exists

**Call Stack**:

```
[... After determinism ratio check ...]

src/complira_graph/llm_agents/vex_enforcement/validator.py:VEXJustificationValidator.validate(doc)
  ↓
  for stmt in doc.statements:
    ↓
    failures.extend(self._check_regulatory_bar(stmt, bundle))
    ↓
src/complira_graph/llm_agents/vex_enforcement/validator.py:VEXJustificationValidator._check_regulatory_bar(stmt, bundle)
  ↓
  failures = []
  ↓
  [DECISION GATE: FDA 524B context check]
  IF "FDA_524B" in stmt.regulatory_context and stmt.status == "not_affected":
    ↓
    [CHECK: Binary analysis evidence requirement]
    has_binary = any(
      n.evidence_type == "binary_analysis_result"
      for n in bundle.deterministic_nodes()
    )
    ↓
    IF not has_binary:
      ↓
      [BRANCH: Binary evidence missing]
      failures.append(ValidationFailure(
        cve_id=stmt.cve_id,
        reason="FDA 524B context: 'not_affected' requires binary analysis evidence (e.g. EMBA firmware scan). Static analysis alone is insufficient for premarket submission. Add binary_analysis_result evidence.",
        severity="warn"  # ⚠️ Warning (not blocking for MVP)
      ))
    ELSE:
      ↓
      [BRANCH: Binary evidence present]
      # Pass, no failure
  ↓
  return failures

[EXIT POINT]
Return: validation_failures = [] (binary evidence verified)
```

**State Mutations**:
- Check bundle for binary_analysis_result evidence type
- Generate warning if missing

**Observed Outcome**: Statement passes FDA 524B validation (binary evidence present)

---

### UC-004-WARN: Binary Analysis Missing (Warning)

**Trigger**: status="not_affected", regulatory_context=["FDA_524B"], no binary analysis evidence

**Call Stack** (diverges at has_binary check):

```
[... Same as PRIMARY until has_binary check ...]

src/complira_graph/llm_agents/vex_enforcement/validator.py:VEXJustificationValidator._check_regulatory_bar(stmt, bundle)
  ↓
  [CHECK binary evidence]
  has_binary = any(n.evidence_type == "binary_analysis_result" for n in bundle.deterministic_nodes())
  # Returns False - no binary evidence in bundle
  ↓
  [BRANCH: Missing binary analysis]
  IF not has_binary:
    ↓
    failures.append(ValidationFailure(
      cve_id=stmt.cve_id,
      component_purl=stmt.component_purl,
      reason="FDA 524B context: 'not_affected' requires binary analysis evidence (e.g. EMBA firmware scan). Static analysis alone is insufficient for premarket submission. Add binary_analysis_result evidence.",
      severity="warn"  # ⚠️ MVP uses warning, future may block
    ))
  ↓
  return failures  # Contains FDA warning

[EXIT POINT]
Return: {"vex_document": doc, "validation_failures": [{"severity": "warn", "reason": "FDA 524B binary analysis required"}], "submission_ready": True}
```

**State Mutations**:
- ValidationFailure created with FDA-specific warning message
- Statement remains in document (warning only in MVP)

**Observed Outcome**: Warning issued for FDA 524B compliance gap, statement included but flagged for review

---

## UC-005: Wrapper Pattern Integration with Fallback

**Use Case ID**: `UC-005`
**Source**: Design-Risk (backward compatibility)
**Description**: Wrapper attempts grounded synthesis, falls back to V2 on enforcement failure
**Objective**: Ensure VEX generation continues even if enforcement layer fails

### UC-005-PRIMARY: Enforcement Success Path

**Trigger**: Enforcement layer completes successfully

**Call Stack**:

```
[ENTRY POINT - Service Layer]
src/api/services/scan.py:ScanService.generate_vex(scan_session_id, customer_id, regulatory_context)
  ↓
  [DECISION: Feature flag enabled for enforcement]
  ↓
src/complira_graph/llm_agents/vex_enforcement/wrapper.py:EnforcedVEXSynthesizer.synthesize(scan_session_id, customer_id, regulatory_context)
  ↓
  [TRY BLOCK - Enforcement path]
  try:
    ↓
    doc = await self.grounded_synth.generate(scan_session_id, customer_id, regulatory_context)
    ↓
    [... Full enforcement flow from UC-001 to UC-004 ...]
    ↓
    [SUCCESS - Enforcement completed]
    ↓
    [BUILD RESPONSE with validation metadata]
    return {
      "vex_document": doc.model_dump(),
      "validation_failures": [f.model_dump() for f in self.grounded_synth.last_validation_failures],
      "submission_ready": all(f.severity != "block" for f in self.grounded_synth.last_validation_failures),
      "mode": "grounded"  # ✅ Indicates enforcement layer used
    }

[EXIT POINT]
Return: {"mode": "grounded", "submission_ready": True}
```

**State Mutations**:
- Full enforcement validation complete
- Response includes validation_failures metadata

**Observed Outcome**: VEX generated via enforcement layer, validation metadata returned

---

### UC-005-FALLBACK: Enforcement Exception Path

**Trigger**: Enforcement layer raises exception (e.g., database unavailable, LLM timeout)

**Call Stack**:

```
[ENTRY POINT]
src/complira_graph/llm_agents/vex_enforcement/wrapper.py:EnforcedVEXSynthesizer.synthesize(...)
  ↓
  [TRY BLOCK]
  try:
    ↓
    doc = await self.grounded_synth.generate(...)
    ↓
    [EXCEPTION RAISED - e.g., ArangoDB connection timeout]
    ↓
  [EXCEPT BLOCK - Catch all exceptions]
  except Exception as e:
    ↓
    [LOG WARNING]
    logger.warning(f"Enforcement layer failed, using V2 fallback: {e}")
    ↓
    [FALLBACK TO V2]
    ↓
src/complira_graph/llm_agents/vex_synthesizer_v2.py:VEXSynthesizerV2.synthesize_vex(evidence)
    ↓
    [EXISTING V2 FLOW - No enforcement]
    ↓
    evidence = VEXEvidenceService.collect_evidence(cve_id, component_purl)
    ↓
    [LLM Call via instructor wrapper]
    assessment = self.instructor_client.messages.create(
      response_model=VEXAssessment,
      ...
    )
    ↓
    [V2 VALIDATION ONLY]
    self._validate_assessment(assessment)  # Schema compliance only, no evidence grounding
    ↓
    return VEXDocument(statements=[assessment])
    ↓
  [BACK TO WRAPPER]
  ↓
src/complira_graph/llm_agents/vex_enforcement/wrapper.py:EnforcedVEXSynthesizer.synthesize(...)
    ↓
    [RETURN V2 result with fallback mode indicator]
    return {
      "vex_document": v2_doc.model_dump(),
      "validation_failures": [],  # V2 doesn't provide this
      "submission_ready": True,  # V2 assumes ready
      "mode": "v2_fallback"  # ⚠️ Indicates fallback was used
    }

[EXIT POINT]
Return: {"mode": "v2_fallback", "submission_ready": True}
```

**State Mutations**:
- Exception logged
- V2 synthesizer invoked (stateless call)
- Response includes "v2_fallback" mode indicator

**Observed Outcome**: VEX generated via V2 fallback, mode="v2_fallback" allows monitoring

---

### UC-005-ERROR: V2 Also Fails

**Trigger**: Both enforcement layer AND V2 fail

**Call Stack**:

```
[ENTRY POINT]
src/complira_graph/llm_agents/vex_enforcement/wrapper.py:EnforcedVEXSynthesizer.synthesize(...)
  ↓
  [TRY BLOCK]
  try:
    doc = await self.grounded_synth.generate(...)
    [EXCEPTION: Database unavailable]
  except Exception as e:
    ↓
    logger.warning(f"Enforcement failed: {e}")
    ↓
    [TRY V2 FALLBACK]
    try:
      return await self.v2_synth.synthesize_vex(evidence)
      ↓
      [V2 ALSO FAILS - e.g., Anthropic API down]
      ↓
    except Exception as v2_error:
      ↓
      [LOG ERROR]
      logger.error(f"Both enforcement and V2 fallback failed. Enforcement error: {e}, V2 error: {v2_error}")
      ↓
      [RE-RAISE to API layer for error handling]
      raise RuntimeError(f"VEX generation completely failed: {v2_error}") from e

[EXIT POINT - API Error Response]
Return: HTTP 500 {"error": "VEX generation failed", "details": "..."}
```

**State Mutations**:
- Both enforcement and V2 errors logged
- Exception propagated to API layer

**Observed Outcome**: API returns error response, monitoring alerted

---

## Cross-Use-Case Decision Gates Summary

| Decision Gate | Location | Condition | Outcome |
|---------------|----------|-----------|---------|
| Feature flag check | `wrapper.py:synthesize()` | Enforcement enabled? | Use enforcement OR use V2 directly |
| Evidence sufficiency | `grounding.py:can_support_justification()` | Required evidence present? | Allow LLM call OR return "under_investigation" |
| Node ID existence | `validator.py:_check_node_ids_exist()` | All cited IDs in bundle? | Pass OR block statement |
| Determinism ratio | `validator.py:_check_determinism_ratio()` | >50% probabilistic? | Warn OR pass |
| FDA binary analysis | `validator.py:_check_regulatory_bar()` | Binary evidence present? | Warn OR pass |
| Enforcement exception | `wrapper.py:synthesize()` | Enforcement succeeded? | Use result OR fallback to V2 |

---

## Async Boundaries

| Boundary | Location | Type | Awaited Result |
|----------|----------|------|----------------|
| Evidence bundle fetch | `synthesizer.py:_fetch_evidence_bundles()` | ArangoDB AQL query | `await cursor.execute()` → List[VEXEvidenceBundle] |
| LLM function calling | `synthesizer.py:generate()` | Anthropic API call | `await client.messages.create()` → LLM response |
| V2 fallback | `wrapper.py:synthesize()` | V2 synthesis | `await v2_synth.synthesize_vex()` → VEXDocument |

---

## State Mutation Summary

| State Change | Location | Scope | Persistence |
|--------------|----------|-------|-------------|
| AQL result → EvidenceNode list | `synthesizer.py:_fetch_evidence_bundles()` | In-memory | Temporary (request scope) |
| Build node ID index | `validator.py:__init__()` | In-memory | Temporary (validation scope) |
| Filter blocked statements | `synthesizer.py:generate()` | In-memory | Temporary (document mutation) |
| Validation failures collection | `validator.py:validate()` | In-memory | Returned to caller |
| VEXDocument creation | `synthesizer.py:generate()` | In-memory | Returned to API |

**No Database Writes**: Enforcement layer is read-only (validation only, no persistence)

---

## Performance Characteristics

| Operation | Estimated Latency | Scalability |
|-----------|------------------|-------------|
| Evidence bundle fetch (AQL) | ~50-100ms | O(n) where n = CVE count in scan session |
| Node ID index build | ~1-5ms | O(n) where n = evidence nodes per CVE (~10-50) |
| Node ID validation | ~1ms per statement | O(1) set lookup per evidence_ref |
| Determinism ratio calc | <1ms per statement | O(n) where n = cited evidence nodes (~2-10) |
| Regulatory bar check | <1ms per statement | O(n) where n = bundle nodes |
| **Total enforcement overhead** | **~60-120ms** | Negligible compared to LLM call (~2-5 seconds) |

---

## Error Propagation

```
Enforcement Exception
  ↓
Caught in wrapper.py:synthesize()
  ↓
Logged with logger.warning()
  ↓
Fallback to V2
  ↓
IF V2 succeeds: Return with mode="v2_fallback"
IF V2 fails: Raise to API layer → HTTP 500
```

---

## Version History

| Version | Date | Changes | Review Status |
|---------|------|---------|---------------|
| v1 | 2026-03-07 | Initial call stacks for all 5 use cases | Ready for Stage 5 review |

---

## Coverage Verification

| Requirement | Use Cases Covering | Call Stack Sections |
|-------------|-------------------|-------------------|
| REQ-001 (Pre-LLM validation) | UC-001 | UC-001-PRIMARY, UC-001-ERROR |
| REQ-002 (Hallucination detection) | UC-002 | UC-002-PRIMARY, UC-002-ERROR |
| REQ-003 (Determinism tracking) | UC-003 | UC-003-PRIMARY, UC-003-WARN |
| REQ-004 (Regulatory bar) | UC-004 | UC-004-PRIMARY, UC-004-WARN |
| REQ-005 (Wrapper pattern) | UC-005 | UC-005-PRIMARY, UC-005-FALLBACK, UC-005-ERROR |

**Coverage Status**: ✅ 100% (all requirements mapped to use cases with call stacks)
