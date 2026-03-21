# VEX Evidence Schema - Design Documentation Index

**Version:** 1.0
**Date:** 2026-03-06
**Status:** Complete Design Specification

## Documentation Overview

This regulatory-grade VEX (Vulnerability Exploitability eXchange) evidence system design is documented across 5 comprehensive files totaling **163 KB** of specifications.

## Document Structure

### 1. Design Summary (START HERE)
**File:** `VEX_EVIDENCE_DESIGN_SUMMARY.md` (18 KB)

**Purpose:** Executive overview and quick reference

**Contains:**
- Architecture overview
- Evidence tier system
- Key features and innovations
- Regulatory compliance matrix
- Performance benchmarks
- Implementation checklist
- Success metrics

**Audience:** Technical leads, architects, compliance officers

**Read Time:** 10-15 minutes

---

### 2. Part 1: Evidence Models & Collection Service
**File:** `vex_evidence_schema_design.md` (46 KB)

**Purpose:** Core Pydantic models and evidence collection

**Contains:**
- Complete Pydantic model specifications (600+ lines)
  - `VulnerabilityEvidence`
  - `CVEMetadata`, `CWEEvidence`, `KEVEvidence`
  - `ExploitabilityEvidence`
  - `AttackTechniqueEvidence`, `MitigationControlEvidence`
  - `VEXAssessment`
- Evidence collection service specification (600+ lines)
  - `VEXEvidenceCollectionService`
  - Parallel graph query patterns
  - Evidence aggregation logic
- Field-by-field documentation
- Validation rules

**Audience:** Backend developers, data engineers

**Implementation:** Create `/src/complira_graph/models/vex_evidence.py` and `/src/api/services/vex_evidence.py`

---

### 3. Part 2: LLM Synthesis & CSAF Formatting
**File:** `vex_evidence_schema_design_part2.md` (35 KB)

**Purpose:** Enhanced VEX synthesizer and CSAF output

**Contains:**
- `VEXSynthesizerV2` specification (400+ lines)
  - Evidence-first LLM prompting
  - Structured output enforcement
  - Evidence citation validation
- `VEXBatchGenerator` for SBOM processing
- `CSAFFormatter` implementation (400+ lines)
  - CSAF 2.0 compliant output
  - Evidence embedding in notes
  - Product tree generation
- LLM prompt templates

**Audience:** AI/ML engineers, security analysts

**Implementation:** Create `/src/complira_graph/llm_agents/vex_synthesizer_v2.py` and `/src/complira_graph/formatters/csaf.py`

---

### 4. Part 3: Validation & CycloneDX
**File:** `vex_evidence_schema_design_part3.md` (34 KB)

**Purpose:** Evidence validation and CycloneDX output

**Contains:**
- `CycloneDXFormatter` specification (300+ lines)
  - CycloneDX 1.5 compliant output
  - SBOM-native VEX format
  - Complira extensions for evidence
- `VEXValidator` implementation (350+ lines)
  - Tier 1 completeness checks
  - Tier 2 completeness checks
  - Graph reference validation
  - Consistency checks
  - Regulatory compliance validation
- `VEXEvidenceQueries` AQL library (200+ lines)
  - Reusable query templates
  - Batch query patterns
  - Custom traversal builders

**Audience:** QA engineers, compliance validators

**Implementation:** Create `/src/complira_graph/formatters/cyclonedx.py`, `/src/complira_graph/validators/vex_validator.py`, and `/src/complira_graph/queries/vex_evidence_queries.py`

---

### 5. Implementation Guide (PRACTICAL REFERENCE)
**File:** `VEX_EVIDENCE_IMPLEMENTATION_GUIDE.md` (30 KB)

**Purpose:** Practical implementation guide with examples

**Contains:**
- Quick start guide
- Complete usage examples
- API integration patterns
  - FastAPI endpoint specifications
  - Request/response models
- Output format examples
  - CycloneDX VEX JSON
  - CSAF 2.0 JSON
- Graph query examples with expected output
- Testing strategy
  - Unit test templates
  - Integration test patterns
- Performance optimization
- Deployment checklist
- Regulatory compliance mapping

**Audience:** All developers, DevOps, compliance teams

**Read Time:** 30-45 minutes

---

## Quick Navigation

### By Role

**Technical Lead / Architect:**
1. Read: `VEX_EVIDENCE_DESIGN_SUMMARY.md`
2. Review: `VEX_EVIDENCE_IMPLEMENTATION_GUIDE.md` (API Integration section)
3. Reference: Individual parts as needed

**Backend Developer:**
1. Read: `VEX_EVIDENCE_DESIGN_SUMMARY.md` (Architecture)
2. Implement: `vex_evidence_schema_design.md` (Part 1)
3. Implement: `vex_evidence_schema_design_part2.md` (Part 2)
4. Implement: `vex_evidence_schema_design_part3.md` (Part 3)
5. Reference: `VEX_EVIDENCE_IMPLEMENTATION_GUIDE.md` (Examples)

**AI/ML Engineer:**
1. Read: `VEX_EVIDENCE_DESIGN_SUMMARY.md` (Evidence System)
2. Focus: `vex_evidence_schema_design_part2.md` (LLM Synthesis)
3. Reference: `VEX_EVIDENCE_IMPLEMENTATION_GUIDE.md` (Prompt Engineering)

**QA / Test Engineer:**
1. Read: `VEX_EVIDENCE_DESIGN_SUMMARY.md` (Success Metrics)
2. Focus: `vex_evidence_schema_design_part3.md` (Validation)
3. Reference: `VEX_EVIDENCE_IMPLEMENTATION_GUIDE.md` (Testing Strategy)

**Compliance Officer:**
1. Read: `VEX_EVIDENCE_DESIGN_SUMMARY.md` (Regulatory Matrix)
2. Review: `VEX_EVIDENCE_IMPLEMENTATION_GUIDE.md` (Compliance Mapping)
3. Verify: Output examples in Part 2 & Part 3

### By Task

**Understanding the Architecture:**
- `VEX_EVIDENCE_DESIGN_SUMMARY.md` → Architecture section

**Implementing Models:**
- `vex_evidence_schema_design.md` → Complete Pydantic specifications

**Implementing Evidence Collection:**
- `vex_evidence_schema_design.md` → Evidence Collection Service
- `vex_evidence_schema_design_part3.md` → AQL Query Library

**Implementing LLM Integration:**
- `vex_evidence_schema_design_part2.md` → VEX Synthesizer V2

**Implementing Validation:**
- `vex_evidence_schema_design_part3.md` → VEX Validator

**Implementing Output Formats:**
- `vex_evidence_schema_design_part2.md` → CSAF Formatter
- `vex_evidence_schema_design_part3.md` → CycloneDX Formatter

**Writing Tests:**
- `VEX_EVIDENCE_IMPLEMENTATION_GUIDE.md` → Testing Strategy

**Deploying to Production:**
- `VEX_EVIDENCE_IMPLEMENTATION_GUIDE.md` → Deployment Checklist

## Files to Create

Based on these specifications, create the following files:

### Models
```
/src/complira_graph/models/vex_evidence.py  (600+ lines)
```

### Services
```
/src/api/services/vex_evidence.py  (600+ lines)
```

### LLM Agents
```
/src/complira_graph/llm_agents/vex_synthesizer_v2.py  (400+ lines)
```

### Formatters
```
/src/complira_graph/formatters/cyclonedx.py  (300+ lines)
/src/complira_graph/formatters/csaf.py       (400+ lines)
```

### Validators
```
/src/complira_graph/validators/vex_validator.py  (350+ lines)
```

### Query Libraries
```
/src/complira_graph/queries/vex_evidence_queries.py  (200+ lines)
```

**Total Implementation:** ~3,500+ lines of production-ready code

## Key Design Principles

### 1. Evidence-First Architecture
All evidence collected from graph **before** LLM involvement. Eliminates hallucinations.

### 2. Tiered Evidence System
- **Tier 1 (Critical):** Required for compliance (CVE, CWE, KEV, EPSS, Component)
- **Tier 2 (Important):** Strengthens compliance (ATT&CK, Controls, Violations)
- **Tier 3 (Future):** Advanced analysis (Reachability, Binary analysis)

### 3. Graph Provenance
Every evidence item includes `graph_id` (ArangoDB document ID) for auditability.

### 4. Structured Output
Pydantic models enforce structure - no free-form JSON strings.

### 5. Multi-Format Support
Single evidence package generates both CycloneDX VEX 1.5 and CSAF 2.0.

### 6. Regulatory Compliance
Built-in validation for FDA 524B, EU CRA, and IEC 62304 requirements.

## Graph Query Patterns

### Core Traversals

1. **CVE → CWE** (Tier 1)
   ```aql
   FOR cwe IN 1..1 OUTBOUND vuln has_weakness
   ```

2. **CVE → KEV** (Tier 1)
   ```aql
   FOR kev IN 1..1 OUTBOUND vuln exploited_in_wild
   ```

3. **CVE → EPSS** (Tier 1)
   ```aql
   FOR epss IN 1..1 OUTBOUND vuln has_epss
   ```

4. **CVE → CWE → CAPEC → ATT&CK** (Tier 2)
   ```aql
   FOR cwe IN 1..1 OUTBOUND vuln has_weakness
     FOR capec IN 1..1 INBOUND cwe capec_relates_to_cwe
       FOR attack IN 1..1 OUTBOUND capec capec_maps_to_attack
   ```

5. **ATT&CK → Controls** (Tier 2)
   ```aql
   FOR control IN 1..1 OUTBOUND attack technique_mitigated_by_control
   ```

6. **CVE → Requirements** (Tier 2)
   ```aql
   FOR req IN 1..1 OUTBOUND vuln violates_requirement
   ```

## Evidence Model Hierarchy

```
VEXAssessment
├── vulnerability_id: str
├── component_purl: str
├── status: VEXStatus
├── evidence: VulnerabilityEvidence
│   ├── cve_metadata: CVEMetadata
│   │   ├── cve_id
│   │   ├── cvss_v3_score
│   │   ├── cvss_v3_severity
│   │   └── graph_id
│   └── graph_evidence: GraphEvidence
│       ├── cwe_mappings: List[CWEEvidence]
│       │   └── [cwe_id, name, graph_id, edge_id]
│       ├── kev_evidence: KEVEvidence
│       │   └── [in_kev, due_date, required_action]
│       ├── component_presence: ComponentPresenceEvidence
│       │   └── [purl, in_sbom, deployment_scope]
│       ├── exploitability: ExploitabilityEvidence
│       │   └── [epss_score, exploit_available]
│       ├── attack_techniques: List[AttackTechniqueEvidence]
│       │   └── [technique_id, tactic, graph_path]
│       ├── mitigation_controls: List[MitigationControlEvidence]
│       │   └── [control_id, framework, graph_path]
│       └── compliance_violations: List[ComplianceViolationEvidence]
│           └── [requirement_id, framework, deadline]
└── evidence_citations: List[str]
```

## Regulatory Compliance Quick Reference

| Framework | Key Requirement | Evidence Model | Tier |
|-----------|----------------|----------------|------|
| FDA 524B | CVSS Scoring | `CVEMetadata.cvss_v3_score` | 1 |
| FDA 524B | KEV Prioritization | `KEVEvidence.in_kev` | 1 |
| FDA 524B | Remediation Plan | `RemediationEvidence` | 2 |
| EU CRA | Weakness Classification | `CWEEvidence` | 1 |
| EU CRA | Attack Correlation | `AttackTechniqueEvidence` | 2 |
| EU CRA | Control Mapping | `MitigationControlEvidence` | 2 |
| IEC 62304 | Risk Assessment | CVSS + EPSS + KEV | 1 |
| IEC 62304 | Traceability | All `graph_id` fields | All |

## Performance Targets

| Operation | Target | Optimization |
|-----------|--------|--------------|
| Evidence Collection | <500ms | Parallel queries |
| Evidence Validation | <50ms | In-memory checks |
| LLM Synthesis | 2-5s | Optimized prompts |
| Format Conversion | <100ms | Efficient serialization |
| **Full Pipeline** | **<8s** | **End-to-end** |

## Success Criteria

### Technical
- [ ] All Tier 1 evidence collected for >95% of CVEs
- [ ] Response time <5s for 90th percentile
- [ ] Error rate <1%
- [ ] Graph query efficiency: <100ms per traversal

### Compliance
- [ ] FDA 524B: 100% evidence requirements met
- [ ] EU CRA: 100% essential requirements met
- [ ] IEC 62304: 100% traceability maintained
- [ ] Audit pass rate: >99%

### Business
- [ ] Customer satisfaction: >90%
- [ ] Time to VEX: <10s per CVE
- [ ] Cost per VEX: <$0.10
- [ ] Regulatory acceptance: 100%

## Implementation Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Phase 1: Models | 1 week | `vex_evidence.py` |
| Phase 2: Evidence Collection | 1 week | `vex_evidence.py` (service) |
| Phase 3: Validation | 1 week | `vex_validator.py` |
| Phase 4: LLM Integration | 1 week | `vex_synthesizer_v2.py` |
| Phase 5: Formatters | 1 week | `cyclonedx.py`, `csaf.py` |
| Phase 6: API & Testing | 1 week | FastAPI endpoints, tests |
| Phase 7: Deployment | 1 week | Production deployment |

**Total:** 6-8 weeks for complete implementation

## Support

### Questions?
- Review the relevant design document (Parts 1-3)
- Check the Implementation Guide for examples
- Reference this index for navigation

### Implementation Issues?
- Verify all dependencies installed
- Check graph schema matches specifications
- Review AQL query syntax
- Validate Pydantic model instantiation

### Performance Issues?
- Enable graph indexes on all traversal paths
- Use parallel evidence collection
- Cache static evidence (CVE metadata, CWE chains)
- Profile AQL query execution times

## Document Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-06 | Initial complete design specification |

---

**Design Complete:** 2026-03-06
**Total Documentation:** 163 KB across 5 files
**Estimated Implementation:** 6-8 weeks
**Status:** Ready for Development
