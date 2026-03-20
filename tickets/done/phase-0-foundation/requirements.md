# Requirements: Phase 0 Foundation

**Status:** `Design-ready`
**Ticket:** phase-0-foundation
**Created:** 2026-03-02
**Last Updated:** 2026-03-02
**Version:** v2 (Refined after Stage 1 investigation)

---

## Goal / Problem Statement

**SCOPE REFINEMENT:** Investigation revealed that Phase 0 infrastructure is already fully implemented. Only missing pieces are schema definition and data models.

**Original Goal:** Implement foundational infrastructure for cloud service
**Refined Goal:** Complete Phase 0 foundation by adding missing schema definition and data models

**Investigation Findings:**
- ✅ Multi-tenant database architecture already implemented
- ✅ API service with authentication already implemented
- ✅ Scan ingestion pipeline already implemented (SARIF, CycloneDX parsers complete)
- ❌ `customer_profiles` collection definition missing from schema
- ❌ Pydantic models missing (CustomerProfile, ScanSession, ScanFinding)

**Actual Problem:** Schema and models are not formally defined, making the implementation incomplete for documentation and validation purposes.

---

## In-Scope Use Cases

### UC-001: Customer Profile Schema Definition (New Requirement)
- **Description:** Define `customer_profiles` collection in database schema
- **Primary Path:** Add collection to `DOCUMENT_COLLECTIONS` in `src/complira_graph/db.py`
- **Expected Outcome:** Collection is formally defined for reference database initialization
- **Note:** Collection is already used by authentication layer but not formally defined

### UC-002: Customer Profile Data Model (New Requirement)
- **Description:** Define `CustomerProfile` Pydantic model for validation
- **Primary Path:** Add model to `src/complira_graph/models.py` with field validation
- **Expected Outcome:** Model provides validation and documentation for customer profile data
- **Fields:** _key (customer_id), name, api_key_hash, database_name, tier, created_at

### UC-003: Scan Session Data Model (New Requirement)
- **Description:** Define `ScanSession` Pydantic model for validation
- **Primary Path:** Add model to `src/complira_graph/models.py` with field validation
- **Expected Outcome:** Model provides validation and documentation for scan session data
- **Fields:** _key, customer_id, tool_name, tool_version, scan_timestamp, scan_type, status, findings_count, components_count, metadata, created_at, updated_at

### UC-004: Scan Finding Data Model (New Requirement)
- **Description:** Define `ScanFinding` Pydantic model for validation
- **Primary Path:** Add model to `src/complira_graph/models.py` with field validation
- **Expected Outcome:** Model provides validation and documentation for scan finding data
- **Fields:** _key, customer_id, scan_session_id, cve_id, severity, description, location, tool_name, raw_data, created_at

---

## Out-of-Scope (Already Implemented)

The following use cases were in the original Phase 0 plan but are **already implemented**:

- ~~UC: Scan Session Ingestion~~ - ✅ Complete (`ScanIngestionService`)
- ~~UC: SARIF Parsing~~ - ✅ Complete (`SARIFParser`)
- ~~UC: CycloneDX Parsing~~ - ✅ Complete (`CycloneDXParser`)
- ~~UC: Multi-Tenant Database Isolation~~ - ✅ Complete (`get_customer_db()`)
- ~~UC: Scan Session Retrieval~~ - ✅ Complete (scan endpoints)
- ~~UC: Authentication~~ - ✅ Complete (`get_current_customer()`)

---

## Acceptance Criteria

### AC-001: customer_profiles Collection Defined in Schema ✅
- **ID:** AC-001
- **Expected Outcome:** `customer_profiles` added to `DOCUMENT_COLLECTIONS` in `src/complira_graph/db.py`
- **Testable:** Verify collection appears in `DOCUMENT_COLLECTIONS` list
- **Status:** ✅ **Passed** (db.py:68)
- **Test:** `tests/unit/test_phase0_models.py::TestSchemaDefinition::test_customer_profiles_in_document_collections`

### AC-002: CustomerProfile Model Defined ✅
- **ID:** AC-002
- **Expected Outcome:** `CustomerProfile` Pydantic model defined in `src/complira_graph/models.py` with all required fields and validation
- **Testable:** Import `CustomerProfile`, instantiate with valid/invalid data, verify validation works
- **Status:** ✅ **Passed** (models.py:624)
- **Tests:** `tests/unit/test_phase0_models.py::TestCustomerProfileModel` (7 tests)

### AC-003: ScanSession Model Defined ✅
- **ID:** AC-003
- **Expected Outcome:** `ScanSession` Pydantic model defined in `src/complira_graph/models.py` with all required fields and validation
- **Testable:** Import `ScanSession`, instantiate with valid/invalid data, verify validation works
- **Status:** ✅ **Passed** (models.py:690)
- **Tests:** `tests/unit/test_phase0_models.py::TestScanSessionModel` (5 tests)

### AC-004: ScanFinding Model Defined ✅
- **ID:** AC-004
- **Expected Outcome:** `ScanFinding` Pydantic model defined in `src/complira_graph/models.py` with all required fields and validation
- **Testable:** Import `ScanFinding`, instantiate with valid/invalid data, verify validation works
- **Status:** ✅ **Passed** (models.py:773)
- **Tests:** `tests/unit/test_phase0_models.py::TestScanFindingModel` (7 tests)

---

## Acceptance Criteria (Already Met - Out of Scope)

These acceptance criteria were in the original plan but are **already met** by existing implementation:

- ~~AC: SARIF Parser Functional~~ - ✅ Complete (verified in investigation)
- ~~AC: CycloneDX Parser Functional~~ - ✅ Complete (verified in investigation)
- ~~AC: Scan Ingest Endpoint Works~~ - ✅ Complete (endpoint exists and functional)
- ~~AC: Scan Session Retrieval Works~~ - ✅ Complete (endpoint exists and functional)
- ~~AC: Customer Isolation Enforced~~ - ✅ Complete (multi-tenant DB routing implemented)
- ~~AC: Edge Collections Created~~ - ✅ Complete (created dynamically per customer DB)

---

## Constraints / Dependencies

### Technical Constraints
- **Database:** ArangoDB 3.11+ for graph capabilities
- **Python:** 3.11+ for FastAPI and type hints
- **API Framework:** FastAPI for async support and OpenAPI docs
- **Format Standards:** SARIF 2.1.0, CycloneDX 1.4/1.5

### Dependencies
- Existing reference database collections (vulnerabilities, weaknesses, attack_techniques, etc.)
- Existing API structure in `src/api/` (already partially implemented)
- Existing parsers in `src/api/parsers/` (may be incomplete)

### Operational Constraints
- No cloud deployment in Phase 0 (local development first)
- Redis cache not required for Phase 0 (can be mocked/skipped)
- API gateway not required for Phase 0 (direct FastAPI access)

---

## Assumptions

1. **Existing API Structure:** The `src/api/` directory contains partial implementation that can be extended
2. **Database Access:** ArangoDB is running locally on `localhost:8529`
3. **No Authentication:** Phase 0 uses mock authentication (real auth in later phase)
4. **Single Customer:** Phase 0 can use a single test customer for validation
5. **Local Testing Only:** No production deployment or cloud infrastructure in Phase 0

---

## Open Questions / Risks

### Open Questions
1. **Q1:** Should we implement Redis caching in Phase 0 or stub it out?
   - **Recommendation:** Stub it out, implement in Phase 1
2. **Q2:** Do we need API key authentication in Phase 0 or mock it?
   - **Recommendation:** Mock authentication with hardcoded customer ID for testing
3. **Q3:** Should Phase 0 include SBOM dependency tree parsing (`depends_on` edges)?
   - **Recommendation:** Yes if simple, defer to Phase 1 if complex

### Risks
1. **Risk-001:** Existing parsers may be incomplete or untested
   - **Mitigation:** Review and test parsers in Stage 1 investigation
2. **Risk-002:** Database schema may conflict with existing collections
   - **Mitigation:** Use non-destructive schema updates, verify no data loss
3. **Risk-003:** Multi-tenant database routing may be complex
   - **Mitigation:** Start with single-customer implementation, generalize later

---

## Triage Result

**Scope:** `Small` (Revised from `Medium` after Stage 1 investigation)

**Original Assessment:** Medium (assumed implementation of all Phase 0 components)
**Revised Assessment:** Small (only schema definition + models needed)

**Rationale:**
- Only 1 collection definition to add (`customer_profiles`)
- Only 3 Pydantic models to add (CustomerProfile, ScanSession, ScanFinding)
- No implementation of services, repositories, endpoints, or parsers (all already exist)
- No integration testing needed (existing implementation is functional)
- No design decisions required (schema and model fields are already defined by existing usage)
- Changes are isolated to two files: `db.py` and `models.py`

---

## Requirement Coverage Map

| Requirement | Maps to Use Case(s) | Status | Notes |
|-------------|---------------------|--------|-------|
| REQ-001: customer_profiles schema definition | UC-001 | Not Started | Add to DOCUMENT_COLLECTIONS |
| REQ-002: CustomerProfile model | UC-002 | Not Started | Pydantic model with validation |
| REQ-003: ScanSession model | UC-003 | Not Started | Pydantic model with validation |
| REQ-004: ScanFinding model | UC-004 | Not Started | Pydantic model with validation |

## Requirements Already Met (Out of Scope)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| ~~SARIF parsing~~ | ✅ Complete | `src/api/parsers/sarif.py` |
| ~~CycloneDX parsing~~ | ✅ Complete | `src/api/parsers/cyclonedx.py` |
| ~~Scan ingestion API~~ | ✅ Complete | `src/api/services/scan.py` |
| ~~Scan retrieval API~~ | ✅ Complete | `src/api/v1/endpoints/scan.py` |
| ~~Multi-tenant isolation~~ | ✅ Complete | `src/api/core/database.py` |

---

## Acceptance Criteria Coverage Map

| Acceptance Criteria ID | Maps to Stage 7 Scenario(s) | Status |
|------------------------|------------------------------|--------|
| AC-001 | Scenario-001: Verify customer_profiles in schema | ✅ **Passed** (2 tests) |
| AC-002 | Scenario-002: CustomerProfile model validation | ✅ **Passed** (7 tests) |
| AC-003 | Scenario-003: ScanSession model validation | ✅ **Passed** (5 tests) |
| AC-004 | Scenario-004: ScanFinding model validation | ✅ **Passed** (7 tests) |

**Total Test Coverage:** 21 unit tests covering all acceptance criteria

---

## Change History

| Date | Version | Changes | Status |
|------|---------|---------|--------|
| 2026-03-02 | v1 | Initial draft from cloud implementation plan Phase 0 | Draft |
| 2026-03-02 | v2 | Refined after Stage 1 investigation - scope reduced to Small (1 collection + 3 models) | Design-ready |
