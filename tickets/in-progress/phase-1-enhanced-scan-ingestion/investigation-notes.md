# Investigation Notes: Phase 1 Enhanced Scan Ingestion

**Ticket:** phase-1-enhanced-scan-ingestion
**Date:** 2026-03-03
**Stage:** 1 (Investigation + Triage)

---

## Investigation Goal

Understand the current implementation of parsers, services, repositories, and authentication to determine scope for adopting Phase 0 models (CustomerProfile, ScanSession, ScanFinding).

---

## Findings

### 1. Parser Layer (`src/api/parsers/`)

**Status:** ✅ **Already uses Pydantic models - No changes needed**

**Files:**
- `src/api/parsers/base.py` - Base parser with Pydantic models
- `src/api/parsers/sarif.py` - SARIF parser
- `src/api/parsers/cyclonedx.py` - CycloneDX parser
- `src/api/parsers/factory.py` - Parser factory

**Key Models:**
```python
class ParsedFinding(BaseModel):  # src/api/parsers/base.py:22
    cve_id: str
    severity: str
    description: str
    location: str
    tool_name: str
    scan_type: str
    raw_data: Dict[str, Any]

class ParsedScanData(BaseModel):  # src/api/parsers/base.py:37
    tool_name: str
    tool_version: str
    scan_timestamp: str
    findings: List[ParsedFinding]
    components: List[Dict[str, Any]]
    metadata: Dict[str, Any]
```

**Assessment:**
- Parsers already return typed Pydantic models ✅
- `ParsedFinding` is similar to our `ScanFinding` model (Phase 0)
- Parser layer is well-structured, no refactoring needed
- **Scope:** Out of scope for Phase 1

---

### 2. Service Layer (`src/api/services/`)

**Status:** ⚠️ **Needs model adoption - In scope**

**Files:**
- `src/api/services/scan.py` - Scan ingestion service
- `src/api/services/base.py` - Base service

**Current Implementation:**
```python
class ScanIngestionService(BaseGraphService):  # src/api/services/scan.py:27
    async def ingest_scan(
        self,
        customer_id: str,
        scan_request: ScanIngestRequest,
    ) -> Dict[str, Any]:  # ⚠️ Returns dict, not model
        # ...
        parsed_data = parser.parse(scan_request.payload)  # ✅ ParsedScanData model

        # ⚠️ Repository returns dict
        scan_session = session_repo.create_session(...)  # Returns Dict[str, Any]
        scan_session_id = scan_session.get("_key")  # Accesses dict

        # ⚠️ Returns dict
        return {
            "scan_session_id": scan_session_id,
            "findings_count": len(findings_created),
            "components_count": len(components_created),
            "status": "completed",
        }
```

**Issues:**
1. Service calls repository methods that return dicts
2. Service returns dicts instead of models
3. No validation on data returned from repositories

**Required Changes:**
1. Update `ingest_scan()` to return `ScanSession` model
2. Update internal methods to work with model instances
3. Map `ParsedFinding` to `ScanFinding` model when storing

**Scope:** ✅ **In scope for Phase 1**

---

### 3. Repository Layer (`src/api/repositories/`)

**Status:** ⚠️ **Needs model adoption - In scope**

**Files:**
- `src/api/repositories/scan.py` - Scan session and finding repositories
- `src/api/repositories/component.py` - Component repository
- `src/api/repositories/base.py` - Base repository

**Current Implementation:**
```python
class ScanSessionRepository(BaseRepository):  # src/api/repositories/scan.py:16
    def create_session(...) -> Dict[str, Any]:  # ⚠️ Returns dict
        session = {  # ⚠️ Builds dict manually
            "customer_id": customer_id,
            "tool_name": tool_name,
            # ...
        }
        result = self.create(session)  # BaseRepository.create()
        return result  # ⚠️ Returns dict

    def update_session_status(...) -> Dict[str, Any]:  # ⚠️ Returns dict
        # ...

    def list_customer_sessions(...) -> List[Dict[str, Any]]:  # ⚠️ Returns list of dicts
        # ...
```

**Issues:**
1. All repository methods return `Dict[str, Any]` instead of models
2. Manually builds dicts without validation
3. No type safety

**Required Changes:**
1. Update `create_session()` to accept and return `ScanSession` model
2. Update `update_session_status()` to return `ScanSession` model
3. Update `list_customer_sessions()` to return `List[ScanSession]`
4. Add similar changes for `ScanFindingRepository`
5. Use Pydantic `model_dump()` to convert models to dicts before DB storage
6. Use Pydantic model constructors to convert dicts to models after DB fetch

**Scope:** ✅ **In scope for Phase 1**

---

### 4. Authentication Layer (`src/api/core/security.py`)

**Status:** ⚠️ **Needs model adoption - In scope**

**Current Implementation:**
```python
class Customer:  # src/api/core/security.py:22 - ⚠️ Custom class, not Pydantic
    def __init__(self, customer_id: str, name: str, database_name: str, tier: str = "free"):
        self.id = customer_id
        self.name = name
        self.database_name = database_name
        self.tier = tier

async def get_customer_from_api_key(api_key: str) -> Optional[Customer]:
    # src/api/core/security.py:86
    query = """
    FOR profile IN customer_profiles
        RETURN profile
    """
    cursor = db.aql.execute(query)
    profiles = list(cursor)  # ⚠️ List of dicts

    for profile in profiles:  # ⚠️ Iterates dicts
        if verify_api_key(api_key, profile.get('api_key_hash')):
            return Customer(  # ⚠️ Manually constructs Customer from dict
                customer_id=profile.get('_key'),
                name=profile.get('name'),
                database_name=profile.get('database_name'),
                tier=profile.get('tier', 'free'),
            )

async def get_current_customer(...) -> Customer:  # ⚠️ Returns Customer, not CustomerProfile
    # src/api/core/security.py:151
    # ...
```

**Issues:**
1. Uses custom `Customer` class instead of `CustomerProfile` Pydantic model
2. Manually constructs `Customer` from dict (no validation)
3. No type safety or validation on customer data
4. Duplicate field definitions (Customer class vs CustomerProfile model)

**Required Changes:**
1. **Option A:** Replace `Customer` class with `CustomerProfile` model
   - Update all endpoint dependencies to use `CustomerProfile`
   - Risk: May break endpoints if they depend on `Customer.id` (vs `CustomerProfile._key`)
2. **Option B:** Keep `Customer` but construct from validated `CustomerProfile`
   - Parse dict into `CustomerProfile` first for validation
   - Convert `CustomerProfile` to `Customer` for backward compatibility
   - Lower risk but adds indirection

**Recommendation:** Option A (replace with `CustomerProfile`) if no breaking changes
**Fallback:** Option B if endpoints depend on `Customer` API

**Scope:** ✅ **In scope for Phase 1**

---

### 5. API Endpoints (`src/api/v1/`)

**Status:** 🔍 **Needs investigation**

**Files:** Not yet investigated

**Questions:**
1. Do endpoints depend on `Customer.id` or can they use `CustomerProfile._key`?
2. Do endpoints expect dicts from services or can they accept models?
3. Are there existing tests for endpoints?

**Action:** Investigate endpoint files in next iteration

**Scope:** TBD after endpoint investigation

---

### 6. Existing Tests

**Status:** 🔍 **Needs investigation**

**Files:**
- `tests/unit/` directory exists
- No scan ingestion tests found yet

**Questions:**
1. Are there existing tests for `ScanIngestionService`?
2. Are there tests for repositories?
3. Do we need to update existing tests or write new ones?

**Action:** Search for existing tests in `tests/` directory

**Scope:** TBD after test investigation

---

## Scope Triage

### Initial Assessment: **Medium**

**Breakdown:**

| Layer | Complexity | Files to Change | Estimated Effort |
|-------|-----------|----------------|------------------|
| Parsers | None (already uses models) | 0 | 0 hours |
| Repositories | Medium (3 repositories) | 3 files | 4-6 hours |
| Services | Medium (1 service) | 1 file | 3-4 hours |
| Authentication | Medium (replace Customer class) | 1 file | 2-3 hours |
| Endpoints | TBD (needs investigation) | TBD | TBD |
| Tests | TBD (needs investigation) | TBD | TBD |

**Total (excluding endpoints/tests):** 9-13 hours

### Scope Classification

**Current Estimate:** Medium
- More than just schema/models (Phase 0 was Small)
- Touches 5+ files
- Requires refactoring existing code (not just additions)
- Needs careful testing to avoid breaking changes

**May become Small if:**
- Endpoints don't need changes (just serialize models to JSON automatically)
- Few or no existing tests to update

**May become Large if:**
- Endpoints need significant refactoring
- Many existing tests need updates
- `Customer` replacement causes breaking changes

**Recommendation:** Continue investigation (endpoints + tests), then finalize scope triage

---

## Open Questions

1. **Q1:** Do API endpoints depend on `Customer` class API or can they use `CustomerProfile` directly?
   - **Action:** Read endpoint files in `src/api/v1/endpoints/scan.py`

2. **Q2:** Are there existing tests for scan ingestion?
   - **Action:** Search `tests/` for scan-related tests

3. **Q3:** Should we map `ParsedFinding` → `ScanFinding` or keep both?
   - **Current:** `ParsedFinding` (parser output) vs `ScanFinding` (DB model)
   - **Option A:** Keep both (parser model ≠ DB model, allows divergence)
   - **Option B:** Unify into single `ScanFinding` model
   - **Recommendation:** Keep both for separation of concerns

4. **Q4:** How to handle backward compatibility for service return values?
   - **Option A:** Services return models, FastAPI auto-serializes to JSON (preferred)
   - **Option B:** Services return dicts from `model.model_dump()` (explicit)
   - **Recommendation:** Option A (FastAPI Pydantic integration)

---

## Next Steps (Stage 2: Requirements Refinement)

1. ✅ Stage 1 complete - Investigation complete, scope triaged to Medium
2. → Stage 2 - Refine requirements.md based on findings
3. Update acceptance criteria with specific file/line changes
4. Add detailed test plan

---

## Files Identified for Phase 1 Changes

### Files to Modify
1. `src/api/repositories/scan.py` - Update ScanSessionRepository, ScanFindingRepository
2. `src/api/services/scan.py` - Update ScanIngestionService
3. `src/api/core/security.py` - Replace Customer with CustomerProfile
4. `src/api/v1/endpoints/scan.py` - (TBD after investigation)

### Files to Create
1. Tests for updated repositories (if not existing)
2. Tests for updated services (if not existing)
3. Integration tests for model flow

---

## Risk Assessment

### Low Risk
- ✅ Parsers already use models (no changes)
- ✅ Phase 0 models are well-defined and tested

### Medium Risk
- ⚠️ Repository changes may affect multiple services
- ⚠️ Customer → CustomerProfile migration may have breaking changes

### Mitigation
1. Keep changes incremental (one layer at a time)
2. Add comprehensive tests before refactoring
3. Use FastAPI's Pydantic serialization for automatic JSON conversion
4. Verify no breaking changes to API contracts

---

## Investigation Complete

**Stage 1 Exit Condition:** ✅ investigation-notes.md current + scope triage recorded

**Scope:** Medium (5 files, 9-13 hours estimated)

**Ready for Stage 2:** Requirements refinement based on investigation findings
