# Requirements: Phase 1 Enhanced Scan Ingestion

**Status:** `Design-ready`
**Ticket:** phase-1-enhanced-scan-ingestion
**Created:** 2026-03-03
**Last Updated:** 2026-03-03
**Version:** v2 (Design-ready - refined after Stage 1 investigation)

---

## Goal / Problem Statement

**Goal:** Adopt Phase 0 models (CustomerProfile, ScanSession, ScanFinding) in the service and repository layers to replace ad-hoc dictionary usage with validated Pydantic models.

**Problem:**
- Phase 0 created schema and models, but existing service/repository layers still use dictionaries
- No validation on scan session creation or finding storage
- Customer profiles exist but not validated against CustomerProfile model
- Risk of data inconsistency and validation gaps

**Expected Outcome:**
- Service layer uses Pydantic models for all scan operations
- Repository layer returns validated model instances
- Existing API endpoints properly use models
- Type safety and validation throughout scan ingestion pipeline

---

## In-Scope Use Cases

### UC-001: Repository Layer Model Adoption
- **Description:** Update `ScanSessionRepository` and `ScanFindingRepository` to work with Pydantic models
- **Current State (Investigation):** Repositories return `Dict[str, Any]`, manually build dicts without validation
- **Files:** `src/api/repositories/scan.py`
- **Primary Path:**
  1. Repository receives ScanSession/ScanFinding model instance
  2. Repository calls `model.model_dump()` to convert to dict for DB storage
  3. After DB fetch, repository instantiates model from dict
  4. Repository returns model instance
- **Expected Outcome:** All repository methods accept/return typed models instead of dicts

### UC-002: Service Layer Model Adoption
- **Description:** Update `ScanIngestionService` to use ScanSession and ScanFinding models
- **Current State (Investigation):** Service works with dicts from repositories, returns dict responses
- **Files:** `src/api/services/scan.py`
- **Primary Path:**
  1. Service creates ScanSession model from parsed data
  2. Service passes model to repository (not dict)
  3. Service receives ScanSession model from repository
  4. Service returns ScanSession model (FastAPI auto-serializes to JSON)
- **Expected Outcome:** Service layer uses typed models throughout, no manual dict construction

### UC-003: Authentication Layer Model Adoption
- **Description:** Replace custom `Customer` class with `CustomerProfile` model in authentication
- **Current State (Investigation):** Uses custom `Customer` class (not Pydantic), manually constructs from dict
- **Files:** `src/api/core/security.py`
- **Primary Path:**
  1. Security layer fetches customer data from `customer_profiles` collection
  2. Instantiate `CustomerProfile` model from fetched dict (validates data)
  3. Return `CustomerProfile` instance instead of `Customer` instance
  4. Update `get_current_customer()` return type to `CustomerProfile`
- **Expected Outcome:** Customer authentication returns validated CustomerProfile model

### UC-004: Parser-to-Model Mapping (Optional Enhancement)
- **Description:** Map `ParsedFinding` (parser output) to `ScanFinding` (DB model) in service layer
- **Current State (Investigation):** Parsers use `ParsedFinding` (different from `ScanFinding`)
- **Files:** `src/api/services/scan.py`
- **Primary Path:**
  1. Parser returns `ParsedFinding` instances (unchanged)
  2. Service maps `ParsedFinding` fields → `ScanFinding` fields
  3. Service creates `ScanFinding` model instances
  4. Repository stores `ScanFinding` models
- **Expected Outcome:** Clear separation between parser output models and DB storage models
- **Note:** Parsers already use Pydantic models - no parser changes needed

---

## Out-of-Scope

**Excluded from Phase 1 (Investigation Findings):**
- **Parser layer changes:** Parsers already use Pydantic models (`ParsedFinding`, `ParsedScanData`) - ✅ No changes needed
- **New API endpoints:** Only updating existing endpoints
- **API contract changes:** Endpoint request/response format stays the same (models auto-serialize)
- **Database schema changes:** Using existing collections, only changing data layer

**Deferred to future phases:**
- VulnCheck integration (separate phase planned)
- CPE matching (`matched_by_cpe`, `affects` edges) - Phase 2+
- Dependency tree parsing (`depends_on` edges) - Phase 2+
- Reference data updater workers - Phase 2+
- `/v1/enrich`, `/v1/compact`, `/v1/map-controls` endpoints - Phase 2+
- Customer onboarding API - Phase 2+
- Database indexes or performance optimization - Production tuning phase

---

## Acceptance Criteria

### AC-001: ScanSessionRepository Returns ScanSession Models
- **ID:** AC-001
- **File:** `src/api/repositories/scan.py`
- **Methods to Update:**
  - `create_session()` → returns `ScanSession` (not `Dict[str, Any]`)
  - `update_session_status()` → returns `ScanSession`
  - `list_customer_sessions()` → returns `List[ScanSession]`
  - `get_session_by_id()` → returns `Optional[ScanSession]` (if exists)
- **Expected Outcome:** All ScanSessionRepository methods accept/return ScanSession model instances
- **Testable:**
  - Unit test: Call `create_session()`, verify return type is `ScanSession` instance
  - Unit test: Verify model has all required fields validated (customer_id, tool_name, etc.)
  - Unit test: Call `list_customer_sessions()`, verify list contains `ScanSession` instances
- **Status:** Not Started

### AC-002: ScanFindingRepository Returns ScanFinding Models
- **ID:** AC-002
- **File:** `src/api/repositories/scan.py`
- **Methods to Update:**
  - `create_finding()` → returns `ScanFinding` (not `Dict[str, Any]`)
  - `list_session_findings()` → returns `List[ScanFinding]`
  - Any other finding-related methods → return `ScanFinding` or `List[ScanFinding]`
- **Expected Outcome:** All ScanFindingRepository methods work with ScanFinding models
- **Testable:**
  - Unit test: Call `create_finding()`, verify return type is `ScanFinding` instance
  - Unit test: Verify ScanFinding model validates severity normalization (high → HIGH)
  - Unit test: Verify CVE ID validation and normalization works
- **Status:** Not Started

### AC-003: ScanIngestionService Uses Models
- **ID:** AC-003
- **File:** `src/api/services/scan.py`
- **Methods to Update:**
  - `ingest_scan()` → returns `ScanSession` (not `Dict[str, Any]`)
  - `_store_findings()` → works with `ScanFinding` models
- **Expected Outcome:** Service layer uses models, no manual dict construction
- **Testable:**
  - Unit test: Call `ingest_scan()`, verify it returns `ScanSession` instance
  - Integration test: POST scan to `/v1/scan/ingest`, verify response uses model serialization
  - Unit test: Verify service maps `ParsedFinding` → `ScanFinding` correctly
- **Status:** Not Started

### AC-004: Authentication Returns CustomerProfile Model
- **ID:** AC-004
- **File:** `src/api/core/security.py`
- **Changes Required:**
  - Remove `Customer` class (lines 22-42)
  - Update `get_customer_from_api_key()` → returns `Optional[CustomerProfile]`
  - Update `get_current_customer()` → returns `CustomerProfile` (not `Customer`)
  - Update all references to `Customer.id` → `CustomerProfile._key`
- **Expected Outcome:** Authentication uses CustomerProfile model, Customer class removed
- **Testable:**
  - Unit test: Call `get_customer_from_api_key()`, verify return type is `CustomerProfile`
  - Unit test: Verify CustomerProfile validates tier, database_name, api_key_hash
  - Integration test: Make authenticated request, verify dependency injects CustomerProfile
- **Status:** Not Started

### AC-005: No Breaking Changes to API Contracts
- **ID:** AC-005
- **Files:** All modified files
- **Expected Outcome:** API endpoint responses have same JSON structure (Pydantic auto-serialization)
- **Testable:**
  - Integration test: POST `/v1/scan/ingest` → compare response JSON before/after (should match)
  - Integration test: GET `/v1/scan/{session_id}` → compare response JSON before/after
  - Verify FastAPI correctly serializes models using `model.model_dump()` (default behavior)
- **Status:** Not Started

---

## Constraints / Dependencies

### Technical Constraints
- Must maintain backward compatibility with existing API contracts
- No breaking changes to endpoint responses
- Must work with existing ArangoDB multi-tenant architecture
- Pydantic models already defined in Phase 0

### Dependencies
- Phase 0 models (CustomerProfile, ScanSession, ScanFinding) - ✅ Complete
- Existing parsers (`src/api/parsers/sarif.py`, `src/api/parsers/cyclonedx.py`)
- Existing service (`src/api/services/scan.py`)
- Existing endpoints (`src/api/v1/endpoints/scan.py`)
- Existing authentication (`src/api/core/security.py`)

---

## Assumptions

1. **Existing API contracts don't change:** Response format stays the same (models serialize to same JSON)
2. **Parsers are functional:** SARIF and CycloneDX parsers work, only need model adoption
3. **No database schema changes:** Using existing collections, only changing data layer
4. **Single customer testing:** Can test with one customer profile for validation

---

## Open Questions / Risks

### Open Questions (Answered in Stage 1 Investigation)
1. **Q1:** Do parsers currently return dictionaries or custom objects?
   - ✅ **ANSWERED:** Parsers already return Pydantic models (`ParsedFinding`, `ParsedScanData`) - no changes needed
2. **Q2:** Does service layer have repository abstraction or direct DB calls?
   - ✅ **ANSWERED:** Service uses repository abstraction - clean architecture already in place
3. **Q3:** Are there existing tests for scan ingestion that need updating?
   - ⏳ **DEFERRED:** Will investigate existing tests in Stage 3 (Design) or Stage 6 (Implementation)
4. **Q4:** Do we need migration for existing scan_sessions/scan_findings data?
   - ✅ **ANSWERED:** No migration needed - Pydantic models are flexible, can parse existing dict structure

### Remaining Open Questions
1. **Q5:** Do endpoints depend on `Customer.id` attribute or can they use `CustomerProfile._key`?
   - **Impact:** May need to add `.id` property alias to CustomerProfile for backward compatibility
   - **Action:** Investigate endpoint code in Stage 3 (Design)
2. **Q6:** Should we keep `ParsedFinding` separate from `ScanFinding` or unify?
   - **Recommendation:** Keep separate (parser output ≠ DB model), map in service layer
   - **Action:** Confirm in Stage 3 (Design)

### Risks
1. **Risk-001:** `Customer` → `CustomerProfile` migration may have breaking changes
   - **Likelihood:** Medium
   - **Impact:** Medium (affects all authenticated endpoints)
   - **Mitigation:**
     - Add `.id` property to CustomerProfile if endpoints depend on it
     - Comprehensive integration testing before merge
     - Gradual rollout: update security.py first, then endpoints
2. **Risk-002:** FastAPI model serialization may produce different JSON structure
   - **Likelihood:** Low (Pydantic serialization matches dict structure)
   - **Impact:** High (breaking change for API consumers)
   - **Mitigation:**
     - AC-005 specifically tests for no breaking changes
     - Compare API responses before/after in integration tests
3. **Risk-003:** Performance impact of Pydantic validation on every DB operation
   - **Likelihood:** Low (Pydantic is fast, ~1-2µs per validation)
   - **Impact:** Low (negligible for typical API workload)
   - **Mitigation:**
     - Pydantic validation overhead is minimal
     - Can use `model_construct()` for trusted data if needed (optimization)

---

## Triage Result

**Scope:** `Medium` (Confirmed in Stage 1 investigation)

**Effort Estimate:** 9-13 hours

**Breakdown:**
| Component | Complexity | Files | Effort |
|-----------|-----------|-------|--------|
| Repositories (ScanSessionRepository, ScanFindingRepository) | Medium | 1 file | 4-6 hours |
| Service (ScanIngestionService) | Medium | 1 file | 3-4 hours |
| Authentication (Customer → CustomerProfile) | Medium | 1 file | 2-3 hours |
| Parsers | None | 0 files | 0 hours (already use Pydantic) |
| Endpoints | TBD | TBD | TBD (may need minor updates) |
| Tests | TBD | TBD | TBD (write new tests) |

**Rationale for Medium:**
- ✅ Parsers already use models (reduced scope from initial estimate)
- ⚠️ 3 files need refactoring (repositories, service, authentication)
- ⚠️ Requires type signature changes across ~10-15 methods
- ⚠️ Customer class replacement may have ripple effects
- ✅ No database schema changes
- ✅ Models already defined and tested (Phase 0)
- ✅ Clean architecture already in place (no major restructuring)

---

## Requirement Coverage Map

| Requirement | Maps to Use Case(s) | Status | Notes |
|-------------|---------------------|--------|-------|
| REQ-001: Repository model adoption | UC-001 | Not Started | `src/api/repositories/scan.py` - Update ScanSessionRepository, ScanFindingRepository |
| REQ-002: Service layer model adoption | UC-002 | Not Started | `src/api/services/scan.py` - Update ScanIngestionService |
| REQ-003: Authentication model adoption | UC-003 | Not Started | `src/api/core/security.py` - Replace Customer with CustomerProfile |
| REQ-004: Parser-to-model mapping | UC-004 | Not Started | `src/api/services/scan.py` - Map ParsedFinding → ScanFinding |
| REQ-005: Parsers | ~~Out of scope~~ | ✅ Complete | Parsers already use Pydantic models (no changes needed) |

---

## Acceptance Criteria Coverage Map

| Acceptance Criteria ID | Maps to Stage 7 Scenario(s) | Test Coverage | Status |
|------------------------|------------------------------|---------------|--------|
| AC-001 | Scenario-001: ScanSessionRepository returns models | Unit tests for create_session(), list_customer_sessions() | Not Started |
| AC-002 | Scenario-002: ScanFindingRepository returns models | Unit tests for create_finding(), validation tests | Not Started |
| AC-003 | Scenario-003: ScanIngestionService uses models | Unit + integration tests for ingest_scan() | Not Started |
| AC-004 | Scenario-004: Auth returns CustomerProfile | Unit tests for get_current_customer(), integration auth tests | Not Started |
| AC-005 | Scenario-005: No breaking changes to API contracts | Integration tests comparing API responses before/after | Not Started |

---

## Change History

| Date | Version | Changes | Status |
|------|---------|---------|--------|
| 2026-03-03 | v1 | Initial draft for Phase 1 Enhanced Scan Ingestion | Draft |
| 2026-03-03 | v2 | Refined after Stage 1 investigation - scope confirmed Medium, use cases updated with specific file changes, ACs updated with method signatures, open questions answered | Design-ready |
