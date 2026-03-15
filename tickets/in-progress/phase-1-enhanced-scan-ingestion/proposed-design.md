# Proposed Design: Phase 1 Enhanced Scan Ingestion

**Ticket:** phase-1-enhanced-scan-ingestion
**Date:** 2026-03-03
**Stage:** 3 (Design Basis)
**Version:** v1

---

## Design Goal

Refactor service, repository, and authentication layers to adopt Phase 0 Pydantic models (CustomerProfile, ScanSession, ScanFinding), replacing manual dictionary construction with validated model instances.

**Design Principles:**
- Maintain backward compatibility (no API contract changes)
- Minimize code churn (change only what's necessary)
- Preserve existing architecture (no major restructuring)
- Type safety throughout (Pydantic models + type hints)

---

## Architecture Overview

### Current State (Before)
```
┌─────────────────┐
│   FastAPI       │
│   Endpoints     │
└────────┬────────┘
         │ Dict[str, Any]
         ▼
┌─────────────────┐
│   Service       │  ← Works with dicts
│   Layer         │  ← Returns dicts
└────────┬────────┘
         │ Dict[str, Any]
         ▼
┌─────────────────┐
│  Repository     │  ← Builds dicts manually
│   Layer         │  ← Returns dicts
└────────┬────────┘
         │ Dict[str, Any]
         ▼
┌─────────────────┐
│   ArangoDB      │
└─────────────────┘
```

### Future State (After)
```
┌─────────────────┐
│   FastAPI       │
│   Endpoints     │  ← FastAPI auto-serializes models to JSON
└────────┬────────┘
         │ ScanSession / CustomerProfile
         ▼
┌─────────────────┐
│   Service       │  ← Works with typed models
│   Layer         │  ← Returns typed models
└────────┬────────┘
         │ ScanSession / ScanFinding
         ▼
┌─────────────────┐
│  Repository     │  ← model.model_dump() before DB
│   Layer         │  ← Model(**dict) after DB
└────────┬────────┘
         │ Dict[str, Any] (DB layer only)
         ▼
┌─────────────────┐
│   ArangoDB      │
└─────────────────┘
```

**Key Changes:**
- Repositories: Dict/model boundary (convert at DB edge)
- Services: Work entirely with models
- Endpoints: Receive models (FastAPI auto-serializes)
- Authentication: Returns CustomerProfile instead of Customer

---

## Component 1: Repository Layer Refactoring

### Design Pattern: Model-Dict Adapter

**File:** `src/api/repositories/scan.py`

**Pattern:**
```python
# BEFORE (current)
def create_session(...) -> Dict[str, Any]:
    session = {  # Manual dict construction
        "customer_id": customer_id,
        "tool_name": tool_name,
        # ... no validation
    }
    result = self.create(session)
    return result  # Dict

# AFTER (proposed)
def create_session(...) -> ScanSession:
    from complira_graph.models import ScanSession

    # Create validated model instance
    session = ScanSession(
        customer_id=customer_id,
        tool_name=tool_name,
        tool_version=tool_version,
        scan_timestamp=scan_timestamp,
        scan_type=scan_type,
        status="processing",  # Default from model
        findings_count=0,
        components_count=0,
        metadata=metadata or {},
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat(),
    )

    # Convert to dict for DB storage
    session_dict = session.model_dump()

    # Store in DB
    result = self.create(session_dict)

    # Convert DB result back to model
    return ScanSession(**result)
```

### ScanSessionRepository Changes

**Methods to Update:**

#### 1. `create_session()` → returns `ScanSession`
```python
def create_session(
    self,
    customer_id: str,
    tool_name: str,
    tool_version: str,
    scan_timestamp: str,
    scan_type: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> ScanSession:  # ← Changed from Dict[str, Any]
    """
    Create new scan session with validated model.

    Returns:
        ScanSession: Validated scan session model instance
    """
    from complira_graph.models import ScanSession
    from datetime import datetime

    # Step 1: Create validated model
    session = ScanSession(
        customer_id=customer_id,
        tool_name=tool_name,
        tool_version=tool_version,
        scan_timestamp=scan_timestamp,
        scan_type=scan_type,
        status="processing",
        findings_count=0,
        components_count=0,
        metadata=metadata or {},
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat(),
    )

    # Step 2: Convert to dict for DB
    session_dict = session.model_dump()

    # Step 3: Store in DB
    result = self.create(session_dict)

    # Step 4: Return as model
    return ScanSession(**result)
```

#### 2. `update_session_status()` → returns `ScanSession`
```python
def update_session_status(
    self,
    session_key: str,
    status: str,
    findings_count: Optional[int] = None,
    components_count: Optional[int] = None,
) -> ScanSession:  # ← Changed from Dict[str, Any]
    """
    Update scan session status with validation.

    Returns:
        ScanSession: Updated scan session model
    """
    from complira_graph.models import ScanSession
    from datetime import datetime

    update_data = {
        "status": status,
        "updated_at": datetime.utcnow().isoformat(),
    }

    if findings_count is not None:
        update_data["findings_count"] = findings_count

    if components_count is not None:
        update_data["components_count"] = components_count

    result = self.update(session_key, update_data)

    return ScanSession(**result)
```

#### 3. `list_customer_sessions()` → returns `List[ScanSession]`
```python
def list_customer_sessions(
    self,
    customer_id: str,
    limit: int = 100,
    offset: int = 0,
) -> List[ScanSession]:  # ← Changed from List[Dict[str, Any]]
    """
    List all scan sessions for customer.

    Returns:
        list: List of ScanSession model instances
    """
    from complira_graph.models import ScanSession

    query = """
    FOR session IN scan_sessions
        FILTER session.customer_id == @customer_id
        SORT session.created_at DESC
        LIMIT @offset, @limit
        RETURN session
    """

    cursor = self.db.aql.execute(
        query,
        bind_vars={
            "customer_id": customer_id,
            "limit": limit,
            "offset": offset,
        }
    )

    # Convert each dict to model
    sessions = [ScanSession(**session) for session in cursor]

    return sessions
```

#### 4. `get_session_by_id()` → returns `Optional[ScanSession]` (new method if needed)
```python
def get_session_by_id(
    self,
    session_key: str,
) -> Optional[ScanSession]:
    """
    Get scan session by ID.

    Returns:
        ScanSession if found, None otherwise
    """
    from complira_graph.models import ScanSession

    try:
        result = self.get(session_key)
        return ScanSession(**result)
    except Exception:
        return None
```

### ScanFindingRepository Changes

**Methods to Update:**

#### 1. `create_finding()` → returns `ScanFinding`
```python
def create_finding(
    self,
    customer_id: str,
    scan_session_id: str,
    cve_id: Optional[str],
    severity: str,
    description: str,
    location: str,
    tool_name: str,
    raw_data: Dict[str, Any],
) -> ScanFinding:  # ← Changed from Dict[str, Any]
    """
    Create scan finding with validation.

    Returns:
        ScanFinding: Validated finding model instance
    """
    from complira_graph.models import ScanFinding
    from datetime import datetime

    # Step 1: Create validated model (auto-normalizes severity and CVE ID)
    finding = ScanFinding(
        customer_id=customer_id,
        scan_session_id=scan_session_id,
        cve_id=cve_id,  # Model validates format and normalizes to uppercase
        severity=severity,  # Model normalizes to uppercase
        description=description,
        location=location,
        tool_name=tool_name,
        raw_data=raw_data,
        created_at=datetime.utcnow().isoformat(),
    )

    # Step 2: Convert to dict for DB
    finding_dict = finding.model_dump()

    # Step 3: Store in DB
    result = self.create(finding_dict)

    # Step 4: Return as model
    return ScanFinding(**result)
```

#### 2. `list_session_findings()` → returns `List[ScanFinding]`
```python
def list_session_findings(
    self,
    scan_session_id: str,
    limit: int = 1000,
) -> List[ScanFinding]:  # ← Changed from List[Dict[str, Any]]
    """
    List all findings for scan session.

    Returns:
        list: List of ScanFinding model instances
    """
    from complira_graph.models import ScanFinding

    query = """
    FOR finding IN scan_findings
        FILTER finding.scan_session_id == @scan_session_id
        LIMIT @limit
        RETURN finding
    """

    cursor = self.db.aql.execute(
        query,
        bind_vars={
            "scan_session_id": scan_session_id,
            "limit": limit,
        }
    )

    # Convert each dict to model
    findings = [ScanFinding(**finding) for finding in cursor]

    return findings
```

---

## Component 2: Service Layer Refactoring

### Design Pattern: Model-First Service

**File:** `src/api/services/scan.py`

**Pattern:**
```python
# BEFORE (current)
async def ingest_scan(...) -> Dict[str, Any]:  # Returns dict
    scan_session = session_repo.create_session(...)  # Dict
    scan_session_id = scan_session.get("_key")  # Dict access

    return {  # Manual dict construction
        "scan_session_id": scan_session_id,
        "findings_count": len(findings_created),
        # ...
    }

# AFTER (proposed)
async def ingest_scan(...) -> ScanSession:  # Returns model
    scan_session = session_repo.create_session(...)  # ScanSession model
    scan_session_id = scan_session._key  # Model attribute access

    # ... (process findings)

    # Update session with final counts
    updated_session = session_repo.update_session_status(
        session_key=scan_session_id,
        status="completed",
        findings_count=len(findings_created),
        components_count=len(components_created),
    )

    return updated_session  # Return model (FastAPI auto-serializes)
```

### ScanIngestionService Changes

#### 1. `ingest_scan()` → returns `ScanSession`
```python
async def ingest_scan(
    self,
    customer_id: str,
    scan_request: ScanIngestRequest,
) -> ScanSession:  # ← Changed from Dict[str, Any]
    """
    Ingest scan results with model validation.

    Returns:
        ScanSession: Completed scan session model
    """
    # ... (parser logic unchanged - parsers already return models)

    parsed_data = parser.parse(scan_request.payload)

    # Get customer database
    from api.core.database import get_customer_db
    customer_db = get_customer_db(customer_id)

    # Initialize repositories
    session_repo = ScanSessionRepository(customer_db)
    finding_repo = ScanFindingRepository(customer_db)
    component_repo = ComponentRepository(customer_db)

    # Create scan session (returns ScanSession model)
    scan_session = session_repo.create_session(
        customer_id=customer_id,
        tool_name=parsed_data.tool_name,
        tool_version=parsed_data.tool_version,
        scan_timestamp=parsed_data.scan_timestamp,
        scan_type=scan_request.scan_type,
        metadata={
            **scan_request.metadata,
            **parsed_data.metadata,
        },
    )

    scan_session_id = scan_session._key  # ← Changed from .get("_key")

    # Store findings (now returns List[ScanFinding])
    findings_created = []
    if parsed_data.findings:
        findings_created = await self._store_findings(
            customer_id=customer_id,
            scan_session_id=scan_session_id,
            findings=parsed_data.findings,  # List[ParsedFinding]
            finding_repo=finding_repo,
        )

    # Store components
    components_created = []
    if parsed_data.components:
        components_created = await self._store_components(
            customer_id=customer_id,
            scan_session_id=scan_session_id,
            components=parsed_data.components,
            component_repo=component_repo,
        )

    # Create edges
    await self._create_edges(
        customer_db=customer_db,
        scan_session_id=scan_session_id,
        findings=findings_created,
        components=components_created,
    )

    # Update scan session status (returns ScanSession model)
    updated_session = session_repo.update_session_status(
        session_key=scan_session_id,
        status="completed",
        findings_count=len(findings_created),
        components_count=len(components_created),
    )

    self.logger.info(
        "Scan ingestion completed",
        scan_session_id=scan_session_id,
        findings_count=len(findings_created),
        components_count=len(components_created),
    )

    return updated_session  # FastAPI auto-serializes to JSON
```

#### 2. `_store_findings()` → returns `List[ScanFinding]`
```python
async def _store_findings(
    self,
    customer_id: str,
    scan_session_id: str,
    findings: List[ParsedFinding],  # Parser output model
    finding_repo: ScanFindingRepository,
) -> List[ScanFinding]:  # ← Changed from list (now typed)
    """
    Store scan findings with ParsedFinding → ScanFinding mapping.

    Args:
        findings: List of ParsedFinding objects from parser

    Returns:
        List[ScanFinding]: Created finding model instances
    """
    from complira_graph.models import ScanFinding

    findings_created = []

    for parsed_finding in findings:
        # Map ParsedFinding → ScanFinding
        # (ParsedFinding has different fields than ScanFinding)
        finding = finding_repo.create_finding(
            customer_id=customer_id,
            scan_session_id=scan_session_id,
            cve_id=parsed_finding.cve_id,
            severity=parsed_finding.severity,
            description=parsed_finding.description,
            location=parsed_finding.location,
            tool_name=parsed_finding.tool_name,
            raw_data=parsed_finding.raw_data,
        )

        findings_created.append(finding)

    self.logger.debug(
        "Findings stored",
        count=len(findings_created),
        scan_session_id=scan_session_id,
    )

    return findings_created
```

---

## Component 3: Authentication Layer Refactoring

### Design Pattern: Replace Custom Class with Pydantic Model

**File:** `src/api/core/security.py`

**Changes:**

#### 1. Remove `Customer` class (lines 22-42)
```python
# REMOVE THIS CLASS
class Customer:
    def __init__(self, customer_id: str, name: str, database_name: str, tier: str = "free"):
        self.id = customer_id  # ← Used by endpoints
        self.name = name
        self.database_name = database_name
        self.tier = tier
```

#### 2. Add compatibility property to CustomerProfile

**Option A: Add to `src/complira_graph/models.py` (CustomerProfile)**
```python
class CustomerProfile(BaseDocument):
    # ... existing fields ...

    @property
    def id(self) -> str:
        """Alias for _key for backward compatibility with endpoints."""
        return self._key
```

**Rationale:** Endpoints may use `customer.id` - this property ensures backward compatibility

#### 3. Update `get_customer_from_api_key()` → returns `Optional[CustomerProfile]`
```python
async def get_customer_from_api_key(api_key: str) -> Optional[CustomerProfile]:  # ← Changed
    """
    Retrieve customer from API key using CustomerProfile model.

    Returns:
        CustomerProfile: Validated customer profile if valid API key, None otherwise
    """
    from complira_graph.models import CustomerProfile

    if not api_key:
        return None

    try:
        db = get_database()

        query = """
        FOR profile IN customer_profiles
            RETURN profile
        """

        cursor = db.aql.execute(query)
        profiles = list(cursor)

        # Check each profile's API key hash
        for profile_dict in profiles:
            api_key_hash = profile_dict.get('api_key_hash')
            if api_key_hash and verify_api_key(api_key, api_key_hash):
                # Validate and return CustomerProfile model
                customer_profile = CustomerProfile(**profile_dict)

                logger.debug(
                    "API key validated",
                    customer_id=customer_profile._key,
                    customer_name=customer_profile.name,
                )

                return customer_profile

        logger.warning("Invalid API key")
        return None

    except Exception as e:
        logger.error(
            "Customer lookup error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None
```

#### 4. Update `get_current_customer()` → returns `CustomerProfile`
```python
async def get_current_customer(
    api_key: Optional[str] = Depends(api_key_header),
) -> CustomerProfile:  # ← Changed from Customer
    """
    FastAPI dependency for authenticating requests.

    Returns:
        CustomerProfile: Validated customer profile model

    Usage:
        @app.get("/v1/scan/list")
        async def list_scans(
            customer: CustomerProfile = Depends(get_current_customer)
        ):
            # customer._key or customer.id (via property)
            # customer.database_name
            # customer.tier
            ...
    """
    if not api_key:
        logger.warning("Missing API key in request")
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide X-API-Key header.",
        )

    customer = await get_customer_from_api_key(api_key)

    if customer is None:
        logger.warning("Invalid API key attempted")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )

    logger.info(
        "Request authenticated",
        customer_id=customer._key,
        customer_name=customer.name,
    )

    return customer
```

---

## Component 4: Backward Compatibility Strategy

### API Contract Preservation

**Challenge:** Ensure API responses have same JSON structure before/after refactoring

**Solution:** FastAPI automatically serializes Pydantic models to JSON using `model.model_dump()`

#### Before (manual dict)
```python
return {
    "scan_session_id": "session_123",
    "findings_count": 42,
    "components_count": 10,
    "status": "completed"
}
```

#### After (Pydantic model)
```python
# Service returns ScanSession model
# FastAPI automatically calls model.model_dump() and returns:
{
    "_key": "session_123",
    "customer_id": "acme",
    "tool_name": "trivy",
    "tool_version": "0.48.0",
    "scan_timestamp": "2026-03-03T10:00:00Z",
    "scan_type": "sarif",
    "status": "completed",
    "findings_count": 42,
    "components_count": 10,
    "metadata": {},
    "created_at": "2026-03-03T10:00:00Z",
    "updated_at": "2026-03-03T10:05:00Z"
}
```

**Issue:** Response includes more fields (full model)

**Options:**

1. **Option A:** Accept richer response (preferred - not breaking, just more data)
   - Pros: No extra work, clients ignore unknown fields
   - Cons: Larger response payload

2. **Option B:** Create response models with subset of fields
   ```python
   class ScanIngestResponse(BaseModel):
       scan_session_id: str
       findings_count: int
       components_count: int
       status: str

   async def ingest_scan(...) -> ScanIngestResponse:
       # ... work with ScanSession internally
       return ScanIngestResponse(
           scan_session_id=session._key,
           findings_count=session.findings_count,
           components_count=session.components_count,
           status=session.status,
       )
   ```
   - Pros: Exact same response format
   - Cons: Extra mapping code, duplicate models

**Recommendation:** Option A - Return full model (not breaking, clients benefit from extra data)

### Customer Property Compatibility

**Challenge:** Endpoints may use `customer.id` instead of `customer._key`

**Solution:** Add `.id` property to CustomerProfile model

```python
# In src/complira_graph/models.py
class CustomerProfile(BaseDocument):
    # ... existing fields ...

    @property
    def id(self) -> str:
        """Alias for _key for backward compatibility."""
        return self._key
```

**Result:** Endpoints can use either `customer.id` or `customer._key`

---

## Component 5: Test Strategy

### Unit Tests

#### Repository Tests
**File:** `tests/unit/test_scan_repository.py` (new or update existing)

```python
import pytest
from complira_graph.models import ScanSession, ScanFinding

class TestScanSessionRepository:
    def test_create_session_returns_model(self, session_repo):
        """AC-001: Verify create_session returns ScanSession model."""
        session = session_repo.create_session(
            customer_id="test_customer",
            tool_name="trivy",
            tool_version="0.48.0",
            scan_timestamp="2026-03-03T10:00:00Z",
            scan_type="sarif",
        )

        assert isinstance(session, ScanSession)
        assert session.customer_id == "test_customer"
        assert session.tool_name == "trivy"
        assert session.status == "processing"

    def test_list_customer_sessions_returns_models(self, session_repo):
        """AC-001: Verify list_customer_sessions returns List[ScanSession]."""
        sessions = session_repo.list_customer_sessions("test_customer")

        assert isinstance(sessions, list)
        for session in sessions:
            assert isinstance(session, ScanSession)

class TestScanFindingRepository:
    def test_create_finding_returns_model(self, finding_repo):
        """AC-002: Verify create_finding returns ScanFinding model."""
        finding = finding_repo.create_finding(
            customer_id="test_customer",
            scan_session_id="session_123",
            cve_id="cve-2021-44228",  # lowercase
            severity="high",  # lowercase
            description="Log4Shell vulnerability",
            location="org.apache.logging.log4j:log4j-core:2.14.1",
            tool_name="trivy",
            raw_data={},
        )

        assert isinstance(finding, ScanFinding)
        assert finding.cve_id == "CVE-2021-44228"  # normalized to uppercase
        assert finding.severity == "HIGH"  # normalized to uppercase
```

#### Service Tests
**File:** `tests/unit/test_scan_service.py` (new or update existing)

```python
class TestScanIngestionService:
    async def test_ingest_scan_returns_model(self, service):
        """AC-003: Verify ingest_scan returns ScanSession model."""
        result = await service.ingest_scan(
            customer_id="test_customer",
            scan_request=ScanIngestRequest(...),
        )

        assert isinstance(result, ScanSession)
        assert result.status == "completed"
        assert result.findings_count > 0
```

#### Authentication Tests
**File:** `tests/unit/test_security.py` (new or update existing)

```python
class TestAuthentication:
    async def test_get_current_customer_returns_profile(self):
        """AC-004: Verify get_current_customer returns CustomerProfile."""
        customer = await get_current_customer(api_key="valid_key")

        assert isinstance(customer, CustomerProfile)
        assert customer._key is not None
        assert customer.id == customer._key  # Property works
```

### Integration Tests

**File:** `tests/integration/test_scan_api.py` (new or update existing)

```python
class TestScanAPI:
    def test_ingest_scan_response_format(self, client):
        """AC-005: Verify API response format unchanged."""
        response = client.post(
            "/v1/scan/ingest",
            headers={"X-API-Key": "test_key"},
            json={
                "format": "sarif",
                "scan_type": "sarif",
                "payload": {...},
                "metadata": {},
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response contains expected fields
        assert "_key" in data or "scan_session_id" in data
        assert "findings_count" in data
        assert "status" in data
```

---

## Implementation Order

### Phase 1: Repository Layer (AC-001, AC-002)
1. Update `ScanSessionRepository.create_session()` → returns `ScanSession`
2. Update `ScanSessionRepository.update_session_status()` → returns `ScanSession`
3. Update `ScanSessionRepository.list_customer_sessions()` → returns `List[ScanSession]`
4. Update `ScanFindingRepository.create_finding()` → returns `ScanFinding`
5. Update `ScanFindingRepository.list_session_findings()` → returns `List[ScanFinding]`
6. Write unit tests for repository changes

### Phase 2: Authentication Layer (AC-004)
1. Add `.id` property to `CustomerProfile` model in `src/complira_graph/models.py`
2. Update `get_customer_from_api_key()` → returns `Optional[CustomerProfile]`
3. Update `get_current_customer()` → returns `CustomerProfile`
4. Remove `Customer` class from `src/api/core/security.py`
5. Write unit tests for authentication changes

### Phase 3: Service Layer (AC-003)
1. Update `ScanIngestionService.ingest_scan()` → returns `ScanSession`
2. Update `ScanIngestionService._store_findings()` → returns `List[ScanFinding]`
3. Update service to use model attributes instead of dict access
4. Write unit tests for service changes

### Phase 4: Integration Testing (AC-005)
1. Write integration tests for `/v1/scan/ingest` endpoint
2. Write integration tests for `/v1/scan/{session_id}` endpoint
3. Verify no breaking changes to API responses

---

## Risk Mitigation

### Risk 1: Customer.id → CustomerProfile._key Breaking Changes
**Mitigation:** Add `.id` property to CustomerProfile (backward compatible)

### Risk 2: API Response Format Changes
**Mitigation:**
- Return full model (richer response, not breaking)
- AC-005 integration tests verify response format

### Risk 3: Model Validation Rejecting Existing Data
**Mitigation:**
- Pydantic models use optional fields where appropriate
- Models are flexible (can parse existing dict structure)
- Test with existing data during integration tests

---

## Design Complete

**Stage 3 Exit Condition:** ✅ Design basis current for scope

**Design Artifacts:**
- ✅ Repository refactoring pattern documented
- ✅ Service layer changes documented
- ✅ Authentication migration documented
- ✅ Backward compatibility strategy documented
- ✅ Test strategy documented
- ✅ Implementation order defined

**Ready for Stage 4:** Runtime modeling (call stacks)
