# Requirements: Phase 4 - Regulatory Framework Integration

**Status:** `Design-ready` (v2)
**Last Updated:** 2026-03-05
**Ticket:** phase-4-regulatory-framework-integration
**Scope:** SMALL (1-2 days, 2-4 files, 600-800 LOC)

---

## Goal / Problem Statement

Ingest remaining FDA 524B and EU CRA regulatory requirements into the Complira Knowledge Graph to enable comprehensive regulatory compliance assessment.

**Business Problem:**
- Current database has 32 regulatory requirements (27 IEC 62304, 3 CRA, 2 FDA 524B)
- **FDA 524B incomplete:** Only 2 placeholders exist, 12 requirements defined in YAML (10 missing)
- **CRA incomplete:** Only 3 requirements exist, 8 requirements defined in YAML (5 missing)
- **IEC 62304:** ✅ COMPLETE (27 requirements already ingested)
- **NIST 800-53:** ✅ COMPLETE (1,196 controls in oscal_controls collection)

**Solution:**
Use existing YAMLRegulatoryAgent to ingest FDA 524B and CRA requirements from pre-existing YAML files.

**Key Discovery (from Stage 1 investigation):**
- ✅ YAMLRegulatoryAgent already exists and is production-ready (src/complira_graph/agents/yaml_regulatory.py)
- ✅ FDA 524B and CRA requirements already manually curated in YAML files (data/regulations/*.yaml)
- ✅ Database schema compatible with all frameworks (regulatory_requirements collection)
- ✅ IEC 62304 and NIST 800-53 already complete (no Phase 4 work needed)

**Actual Work:** Run existing agent on existing YAML files (simple data ingestion, not infrastructure build)

**Business Value:**
- Enables automated FDA 524B compliance assessment for medical device manufacturers
- Enables automated EU CRA compliance assessment for software vendors
- Provides defensible audit trail for regulatory submissions (FDA, EU MDR)
- Supports proactive identification of regulatory obligations triggered by vulnerabilities

---

## In-Scope Use Cases

### UC-1: FDA 524B Requirements Ingestion
**Actor:** Platform Operator
**Flow:**
1. Operator runs `YAMLRegulatoryAgent(db, framework_key="FDA_524B").run()`
2. Agent reads `data/regulations/fda_524b.yaml` (12 requirements, 272 lines, manually curated)
3. Agent validates YAML schema
4. Agent inserts requirements into `regulatory_requirements` collection with deterministic keys
5. Database updated: 32 + 12 = 44 total requirements

**Success Criteria:**
- All 12 FDA 524B requirements ingested:
  - V.A.1: SBOM submission
  - V.A.2: SBOM maintenance
  - V.C.1: Vulnerability monitoring
  - V.C.2: KEV response (24h)
  - V.C.3: CVSS high severity response
  - Plus 7 more requirements
- Requirements include metadata: framework, requirement_id, title, description, urgency, evidence_types
- No errors during ingestion

**Priority:** High (medical device compliance is critical)

---

### UC-2: EU CRA Requirements Ingestion
**Actor:** Platform Operator
**Flow:**
1. Operator runs `YAMLRegulatoryAgent(db, framework_key="CRA").run()`
2. Agent reads `data/regulations/cra.yaml` (8 Annex I requirements, 409 lines, manually curated)
3. Agent validates YAML schema
4. Agent inserts requirements into `regulatory_requirements` collection
5. Database updated: 44 + 8 = 52 total requirements

**Success Criteria:**
- All 8 CRA Annex I essential requirements ingested:
  - Annex I.1: Security by design and default
  - Annex I.2: Vulnerability handling
  - Annex I.3: Secure update mechanisms
  - Annex I.4: Incident reporting
  - Plus 4 more requirements
- Requirements include metadata: framework, annex, section, title, obligation_level, evidence_types
- No errors during ingestion

**Priority:** High (EU market access requirement)

---

### UC-3: Ingestion Script Creation
**Actor:** Platform Operator
**Flow:**
1. Create `scripts/ingest_regulatory_frameworks.py` script
2. Script invokes YAMLRegulatoryAgent for both FDA 524B and CRA
3. Script reports ingestion statistics (requirements added, errors, execution time)
4. Script provides CLI interface for easy execution

**Success Criteria:**
- Script successfully ingests both FDA and CRA requirements
- Execution time < 10 seconds
- Clear success/error reporting

**Priority:** Medium (automation convenience)

---

### UC-4: Database Verification
**Actor:** Platform Operator
**Flow:**
1. Query `regulatory_requirements` collection after ingestion
2. Verify total count: 52 requirements (27 IEC + 3 CRA + 2 FDA placeholders + 12 FDA + 8 CRA)
3. Verify requirements by framework:
   - IEC_62304: 27
   - FDA_524B: 14 (2 placeholders + 12 new)
   - CRA: 11 (3 existing + 8 new)
4. Sample-check requirement metadata completeness

**Success Criteria:**
- Database contains 52 total requirements
- All FDA and CRA requirements have complete metadata
- No duplicate keys

**Priority:** High (validation is critical)

---

## Acceptance Criteria

### Functional Requirements

**AC1: FDA 524B Requirements Ingested** ✅
- **Pass:** All 12 FDA 524B requirements in database (V.A.1, V.A.2, V.C.1-V.C.10)
- **Fail:** Fewer than 12 requirements ingested or any ingestion errors

**AC2: EU CRA Requirements Ingested** ✅
- **Pass:** All 8 CRA Annex I requirements in database (sections 1-8)
- **Fail:** Fewer than 8 requirements ingested or any ingestion errors

**AC3: IEC 62304 Requirements Verified** ✅
- **Pass:** All 27 IEC 62304 requirements still in database (no regression)
- **Fail:** Any IEC requirements missing or corrupted

**AC4: NIST 800-53 Controls Verified** ✅
- **Pass:** All 1,196 NIST controls still in oscal_controls collection (no regression)
- **Fail:** Any NIST controls missing or corrupted

**AC5: Database State Validated** ✅
- **Pass:** Database contains exactly 52 requirements (27 IEC + 14 FDA + 11 CRA)
- **Fail:** Incorrect total count or missing requirements

**AC6: Regulatory Blast Radius Query Works** ✅
- **Pass:** Query returns FDA, CRA, and IEC requirements for test CVE (e.g., CVE-2021-44228)
- **Fail:** Query returns no frameworks or incomplete results

**AC7: Ingestion Script Functional** ✅
- **Pass:** Script successfully ingests FDA + CRA requirements with no errors
- **Fail:** Script fails or produces errors

**AC8: Unit Tests Pass** ✅
- **Pass:** All new unit tests pass (ingestion script tests, YAML validation tests)
- **Fail:** Any test fails

### Non-Functional Requirements

**AC9: Performance** ✅
- **Pass:** Total ingestion time < 10 seconds for FDA + CRA (20 requirements)
- **Fail:** Ingestion takes > 30 seconds

**AC10: Documentation Complete** ✅
- **Pass:** All agents documented, Phase 4 summary created in docs/
- **Fail:** Documentation incomplete or missing

---

## Out-of-Scope (Deferred to Future Phases)

### Deferred to Phase 5+

**OUT-1: CWE-to-Requirement Mapping**
- LLM-based agent to infer CWE → requirement relationships
- New edge collection: `cwe_triggers_requirement`
- **Rationale:** Phase 3A-B already provides vuln → requirement mappings (43 edges via vuln_triggers_requirement). CWE mapping is additive but not critical for v1.0.

**OUT-2: Placeholder Requirement Migration**
- Update Phase 3A-B trigger rules to use comprehensive FDA/CRA requirements instead of placeholders
- Migrate 43 vuln_triggers_requirement edges from placeholders to new requirements
- **Rationale:** Placeholders work correctly. Migration can be done in Phase 5 without breaking functionality.

**OUT-3: Additional Frameworks**
- ISO/IEC 27001, PCI DSS, HIPAA Security Rule, ISO 21434, DORA, NIS2
- **Rationale:** FDA 524B, CRA, IEC 62304, NIST 800-53 cover highest-priority use cases. Additional frameworks can be added incrementally.

**OUT-4: Compliance Gap Analysis Report**
- Web-based compliance dashboard
- Automated report generation (PDF export)
- **Rationale:** Requires frontend development. Defer to Phase 6 or later.

**OUT-5: Control-to-Control Mappings**
- NIST 800-53 → CIS Controls
- Cross-framework equivalency mappings
- **Rationale:** Useful but not critical for compliance assessment. Defer to Phase 7 or later.

---

## Resolved Design Decisions (from Stage 1 investigation)

### D1: Data Source Strategy
**Decision:** ✅ Use existing YAML files (Option B: Manually curated)

**Rationale:**
- FDA 524B, CRA, IEC 62304 requirements already manually curated in data/regulations/*.yaml
- YAMLs are high-quality, comprehensive, and production-ready
- No additional curation needed

**Alternatives Considered:**
- Option A: Download official machine-readable formats (OSCAL, JSON) → Not available for FDA/CRA
- Option C: Web scraping regulatory documents → Too complex, error-prone

---

### D2: CWE Mapping Strategy
**Decision:** ❌ Defer to Phase 5 (no CWE mapping in Phase 4)

**Rationale:**
- Phase 3A-B RegulatoryTriggerService already creates vuln → requirement edges (43 edges)
- CWE → requirement mapping would be additive, not foundational
- LLM-based mapping requires new agent + validation workflow (out of scope for SMALL phase)

**Alternatives Considered:**
- Option A: Fully automated (LLM with confidence ≥0.85) → Requires new agent
- Option B: Hybrid (LLM proposes, analyst reviews) → Requires approval workflow
- Option C: Manual (analyst creates all mappings in YAML) → Too time-consuming

---

### D3: NIST 800-53 Scope
**Decision:** ✅ All controls already ingested (Option A)

**Rationale:**
- NIST 800-53 Rev 5 fully ingested in Phase 0 or earlier (1,196 controls in oscal_controls collection)
- maps_to_requirement edges already exist (458 edges: vulnerabilities → oscal_controls)
- No additional work needed for NIST in Phase 4

**Alternatives Considered:**
- Option B: Vulnerability-specific controls only (SI, RA, CM families) → Unnecessary, all already done
- Option C: Denormalize oscal_controls → regulatory_requirements → Breaks existing architecture

---

### D4: Placeholder Requirement Migration
**Decision:** ✅ Keep placeholders, defer edge migration to Phase 5 (Option C)

**Rationale:**
- Deleting placeholders would break 43 vuln_triggers_requirement edges from Phase 3A-B
- New FDA/CRA requirements will coexist with placeholders (no conflicts)
- Edge migration is low-priority enhancement (Phase 5)

**Migration Strategy (Phase 5):**
1. Keep 5 placeholders in database (no deletion)
2. Ingest 12 FDA + 8 CRA requirements (20 total)
3. Database will have: 5 placeholders + 20 new requirements = 25 FDA/CRA requirements
4. Phase 3A-B trigger rules continue using placeholders (no breaking changes)
5. **Phase 5:** Update trigger rules to point to new comprehensive requirements

**Alternatives Considered:**
- Option A: Replace all placeholders → Would break Phase 3A-B edges
- Option B: Keep placeholders, add new requirements alongside → ✅ CHOSEN (low risk)

---

### D5: Regulatory Framework Versioning
**Decision:** ✅ Store only latest version (Option A)

**Rationale:**
- All frameworks have single authoritative version:
  - FDA 524B: Draft Guidance 2023 (effective 2024-01-01)
  - CRA: Regulation (EU) 2024/2847 (enforcement 2027-12-11)
  - IEC 62304: ISO/IEC 62304:2006+AMD1:2015
- No historical version tracking needed for v1.0
- YAML files include version field for future-proofing

**Alternatives Considered:**
- Option B: Store all versions with version field → Unnecessary complexity for v1.0
- Option C: Store only versions relevant to users → Same as Option A

---

## Dependencies

### Upstream Dependencies (All Satisfied ✅)
- ✅ Phase 0: Foundation (database, schema) - **COMPLETE**
- ✅ Phase 2: Enrichment Pipeline (NVD, GHSA, CWE data) - **COMPLETE**
- ✅ Phase 3A: VulnCheck Integration (KEV, exploit intelligence) - **COMPLETE**
- ✅ Phase 3A-B: RegulatoryTriggerService (vuln_triggers_requirement edges) - **COMPLETE**

### Internal Dependencies (All Satisfied ✅)
- ✅ YAMLRegulatoryAgent exists (src/complira_graph/agents/yaml_regulatory.py)
- ✅ FDA 524B YAML exists (data/regulations/fda_524b.yaml, 12 requirements)
- ✅ CRA YAML exists (data/regulations/cra.yaml, 8 requirements)
- ✅ Database schema compatible (regulatory_requirements collection)

### Downstream Dependencies (Blocked Until Phase 4 Complete)
- ⏸️ Phase 5: CWE Mapping Agent (requires comprehensive regulatory requirements)
- ⏸️ Phase 6: Compliance Reporting UI (requires regulatory data)

### External Dependencies (None)
- No external API dependencies
- No third-party library dependencies beyond existing stack

---

## Scope Estimate

### Effort Breakdown

| Task | Estimated Effort | Estimated LOC | Files |
|------|------------------|---------------|-------|
| Create ingestion script (scripts/ingest_regulatory_frameworks.py) | 2 hours | 150-200 | 1 |
| Test ingestion (FDA + CRA) | 1 hour | 0 | 0 |
| Create unit tests (tests/test_regulatory_ingestion.py) | 2-3 hours | 150-200 | 1 |
| Verify database state (manual queries) | 1 hour | 0 | 0 |
| Update documentation (docs/PHASE_4_REGULATORY_FRAMEWORK_INTEGRATION.md) | 2-3 hours | 300-400 | 1 |
| Update README.md | 30 min | 10-20 | 1 |
| **TOTAL** | **8-10 hours (1-2 days)** | **610-820 LOC** | **4 files** |

### Scope Classification
- **Size:** SMALL
- **Duration:** 1-2 days
- **Complexity:** Low (run existing agent on existing data)
- **Risk:** Low (all infrastructure exists, YAMLs validated)
- **Files:** 2-4 (ingestion script, test file, 1-2 documentation files)
- **LOC:** 600-800 lines

### Confidence Level
- **High Confidence** (95%+)
- All infrastructure already exists ✅
- YAMLs are ready for ingestion ✅
- No unknown dependencies ✅
- Low technical risk ✅

---

## Success Metrics

### Data Coverage
- **Target:** 52 regulatory requirements ingested (27 IEC + 14 FDA + 11 CRA)
- **Baseline:** 32 requirements (current database)
- **Goal:** 63% increase in regulatory coverage (20 new requirements / 32 baseline)

### Framework Coverage
- **Target:** 3 frameworks fully covered (FDA 524B, CRA, IEC 62304)
- **Baseline:** 1 framework fully covered (IEC 62304)
- **Goal:** 200% increase in framework coverage

### Ingestion Performance
- **Target:** Total ingestion time < 10 seconds for FDA + CRA (20 requirements)
- **Baseline:** Not yet measured
- **Goal:** Real-time ingestion performance

### Automation Rate
- **Target:** 100% automated ingestion (zero manual data entry)
- **Baseline:** 0% (no ingestion automation)
- **Goal:** Full automation via YAMLRegulatoryAgent

---

## Risks and Mitigations

### Risk 1: YAML Schema Compatibility (LOW)
- **Risk:** YAMLs may not match YAMLRegulatoryAgent expected schema
- **Likelihood:** Low (YAMLs likely created for this agent)
- **Impact:** Low (validation errors caught immediately)
- **Mitigation:** Test ingestion in Stage 6, fix any schema mismatches

### Risk 2: Duplicate Requirements (LOW)
- **Risk:** Some FDA/CRA requirements may already exist beyond placeholders
- **Likelihood:** Low (only 5 placeholders exist currently)
- **Impact:** Low (agent uses upsert with deterministic keys)
- **Mitigation:** Agent handles duplicates via deterministic key generation

### Risk 3: Placeholder Edge Conflicts (NONE)
- **Risk:** New FDA/CRA requirements may conflict with placeholder edges
- **Likelihood:** None (placeholders remain in database)
- **Impact:** None (edges continue working)
- **Mitigation:** No action needed (migration deferred to Phase 5)

### Risk 4: NIST 800-53 Confusion (MEDIUM)
- **Risk:** Users may expect NIST 800-53 in regulatory_requirements but it's in oscal_controls
- **Likelihood:** Medium (separate collections may cause confusion)
- **Impact:** Low (documentation will clarify)
- **Mitigation:** Document architecture clearly in Phase 4 docs, explain dual-collection design

---

## Document Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| v1 Draft | 2026-03-05 | Claude Code | Initial requirements draft for Stage 0 bootstrap |
| v2 Design-ready | 2026-03-05 | Claude Code | Refined based on Stage 1 investigation findings: scope reduced to SMALL (1-2 days, 600-800 LOC), all open questions resolved, design decisions documented, IEC/NIST work scope removed (already complete) |

---

**Status:** `Design-ready` (v2) - Ready for Stage 2 → Stage 3 transition
**Next Step:** Stage 3 (Design Basis) to create implementation plan based on revised SMALL scope
