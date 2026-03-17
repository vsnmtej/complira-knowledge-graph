# Proposed Design: Phase 0 Foundation

**Status:** Draft
**Ticket:** phase-0-foundation
**Created:** 2026-03-02
**Scope:** Small

---

## Design Overview

**Purpose:** Complete Phase 0 foundation by adding missing schema definition and data models to formalize the already-implemented infrastructure.

**Scope:** Add 1 collection definition + 3 Pydantic models

**Files Modified:**
1. `src/complira_graph/db.py` - Add `customer_profiles` to `DOCUMENT_COLLECTIONS`
2. `src/complira_graph/models.py` - Add 3 Pydantic models (CustomerProfile, ScanSession, ScanFinding)

---

## Design Decisions

### Decision 1: Schema Definition Location
**Decision:** Add `customer_profiles` to `DOCUMENT_COLLECTIONS` in `src/complira_graph/db.py`

**Rationale:**
- Existing pattern: All document collections are defined in `DOCUMENT_COLLECTIONS` list
- `customer_profiles` is used in reference database (shared across all customers)
- Authentication layer already queries this collection (see `src/api/core/security.py:104-116`)
- Adding to schema makes it official and ensures collection is created during database initialization

**Alternative Considered:** Create collection dynamically like customer-specific collections
**Why Rejected:** `customer_profiles` belongs in reference database, not customer databases

---

### Decision 2: Model Definition Approach
**Decision:** Define Pydantic models in `src/complira_graph/models.py` following existing patterns

**Rationale:**
- Existing pattern: All data models in `models.py` use Pydantic BaseModel
- Models provide validation, documentation, and type safety
- Current implementation uses ad-hoc dictionaries (functional but not ideal)
- Models will be imported by API layer for validation (future enhancement)

**Alternative Considered:** Keep using dictionaries without models
**Why Rejected:** Models improve maintainability and provide self-documentation

---

## Implementation Details

### 1. Schema Addition: customer_profiles Collection

**File:** `src/complira_graph/db.py`

**Change:** Add `"customer_profiles"` to `DOCUMENT_COLLECTIONS` list

**Location:** After existing reference collections (vulnerabilities, weaknesses, etc.)

**Schema (Already Defined by Usage):**
```python
{
    "_key": str,  # customer_id (e.g., "acme", "enterprise_xyz")
    "name": str,  # customer name (e.g., "Acme Corp")
    "api_key_hash": str,  # bcrypt hash of API key
    "database_name": str,  # customer database name (e.g., "complira_customer_acme")
    "tier": str,  # subscription tier (free, pro, enterprise)
    "created_at": str,  # ISO 8601 timestamp
}
```

**Indexes (Future Enhancement):**
```python
INDEXES = {
    # ... existing indexes ...
    "customer_profiles": [
        {"fields": ["created_at"], "unique": False},
    ],
}
```

---

### 2. Model Definitions

**File:** `src/complira_graph/models.py`

#### CustomerProfile Model

```python
class CustomerProfile(BaseGraphModel):
    """
    Customer profile for multi-tenant SaaS.

    Stored in reference database, shared across all customers.
    Used by authentication layer to validate API keys and route to customer databases.
    """
    _key: str = Field(
        ...,
        description="Customer identifier (unique)",
        min_length=1,
        max_length=100,
    )
    name: str = Field(
        ...,
        description="Customer name (e.g., 'Acme Corp')",
        min_length=1,
        max_length=255,
    )
    api_key_hash: str = Field(
        ...,
        description="Bcrypt hash of API key",
        min_length=60,
        max_length=60,  # Bcrypt hashes are always 60 chars
    )
    database_name: str = Field(
        ...,
        description="Customer database name (e.g., 'complira_customer_acme')",
        min_length=1,
        max_length=128,
    )
    tier: str = Field(
        default="free",
        description="Subscription tier",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Profile creation timestamp (ISO 8601)",
    )

    @validator("tier")
    def validate_tier(cls, v):
        """Validate tier is one of allowed values."""
        allowed_tiers = ["free", "pro", "enterprise"]
        if v not in allowed_tiers:
            raise ValueError(f"tier must be one of {allowed_tiers}")
        return v

    @validator("database_name")
    def validate_database_name(cls, v):
        """Validate database name format."""
        if not v.startswith("complira_customer_"):
            raise ValueError("database_name must start with 'complira_customer_'")
        return v
```

#### ScanSession Model

```python
class ScanSession(BaseGraphModel):
    """
    Scan session metadata.

    Stored in customer database. Represents a single scan execution from CI/CD pipeline.
    """
    _key: Optional[str] = Field(
        None,
        description="Session identifier (auto-generated if not provided)",
    )
    customer_id: str = Field(
        ...,
        description="Customer identifier",
        min_length=1,
    )
    tool_name: str = Field(
        ...,
        description="Scanner tool name (e.g., 'Snyk', 'Trivy', 'Semgrep')",
        min_length=1,
    )
    tool_version: str = Field(
        ...,
        description="Scanner tool version",
        min_length=1,
    )
    scan_timestamp: str = Field(
        ...,
        description="Scan execution timestamp (ISO 8601)",
    )
    scan_type: str = Field(
        ...,
        description="Scan format type (sarif, cyclonedx)",
    )
    status: str = Field(
        default="processing",
        description="Scan processing status",
    )
    findings_count: int = Field(
        default=0,
        description="Number of findings in this scan",
        ge=0,
    )
    components_count: int = Field(
        default=0,
        description="Number of SBOM components in this scan",
        ge=0,
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional scan metadata",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Session creation timestamp (ISO 8601)",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Session last update timestamp (ISO 8601)",
    )

    @validator("status")
    def validate_status(cls, v):
        """Validate status is one of allowed values."""
        allowed_statuses = ["pending", "processing", "completed", "failed"]
        if v not in allowed_statuses:
            raise ValueError(f"status must be one of {allowed_statuses}")
        return v

    @validator("scan_type")
    def validate_scan_type(cls, v):
        """Validate scan_type is supported."""
        supported_types = ["sarif", "cyclonedx"]
        if v not in supported_types:
            raise ValueError(f"scan_type must be one of {supported_types}")
        return v
```

#### ScanFinding Model

```python
class ScanFinding(BaseGraphModel):
    """
    Individual scan finding (vulnerability or issue).

    Stored in customer database. Represents a single vulnerability or issue discovered by scanner.
    """
    _key: Optional[str] = Field(
        None,
        description="Finding identifier (auto-generated if not provided)",
    )
    customer_id: str = Field(
        ...,
        description="Customer identifier",
        min_length=1,
    )
    scan_session_id: str = Field(
        ...,
        description="Scan session _key this finding belongs to",
        min_length=1,
    )
    cve_id: Optional[str] = Field(
        None,
        description="CVE identifier (e.g., 'CVE-2021-44228') if applicable",
    )
    severity: str = Field(
        ...,
        description="Normalized severity level",
    )
    description: str = Field(
        ...,
        description="Finding description",
        min_length=1,
    )
    location: str = Field(
        ...,
        description="Finding location (file:line or component@version)",
        min_length=1,
    )
    tool_name: str = Field(
        ...,
        description="Scanner tool that reported this finding",
        min_length=1,
    )
    raw_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Original finding data from scanner",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Finding creation timestamp (ISO 8601)",
    )

    @validator("severity")
    def validate_severity(cls, v):
        """Validate severity is normalized."""
        allowed_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"]
        if v.upper() not in allowed_severities:
            raise ValueError(f"severity must be one of {allowed_severities}")
        return v.upper()

    @validator("cve_id")
    def validate_cve_id(cls, v):
        """Validate CVE ID format if provided."""
        if v and not v.upper().startswith("CVE-"):
            raise ValueError("cve_id must start with 'CVE-' if provided")
        return v.upper() if v else None
```

---

## Implementation Approach

### Step 1: Add customer_profiles to Schema
1. Open `src/complira_graph/db.py`
2. Locate `DOCUMENT_COLLECTIONS` list
3. Add `"customer_profiles"` after existing reference collections
4. Verify list syntax (comma-separated)

### Step 2: Add Models to models.py
1. Open `src/complira_graph/models.py`
2. Import required dependencies (Field, validator, Optional, Dict, Any, datetime)
3. Add three model classes (CustomerProfile, ScanSession, ScanFinding)
4. Follow existing pattern (inherit from BaseGraphModel)
5. Add validators for enum-like fields (tier, status, scan_type, severity)

### Step 3: Verification
1. Import models in Python REPL
2. Test instantiation with valid data
3. Test validation with invalid data
4. Verify collection appears in schema definition

---

## Testing Strategy

### Unit Tests (Stage 6)

**Test File:** `tests/unit/test_phase0_models.py`

**Test Cases:**
1. `test_customer_profile_valid_data()` - Valid CustomerProfile instantiation
2. `test_customer_profile_invalid_tier()` - Reject invalid tier
3. `test_customer_profile_invalid_database_name()` - Reject malformed database_name
4. `test_scan_session_valid_data()` - Valid ScanSession instantiation
5. `test_scan_session_invalid_status()` - Reject invalid status
6. `test_scan_session_negative_counts()` - Reject negative counts
7. `test_scan_finding_valid_data()` - Valid ScanFinding instantiation
8. `test_scan_finding_invalid_severity()` - Reject invalid severity
9. `test_scan_finding_invalid_cve_id()` - Reject malformed CVE ID

### Integration Tests (Stage 7)

**Test File:** `tests/integration/test_phase0_schema.py`

**Test Cases:**
1. `test_customer_profiles_collection_exists()` - Verify collection in reference DB
2. `test_schema_initialization_includes_customer_profiles()` - Verify schema init creates collection

---

## Risks and Mitigations

### Risk 1: Breaking Changes to Existing Code
**Likelihood:** Low
**Impact:** Low
**Mitigation:** Changes are purely additive (no modifications to existing code)

### Risk 2: Model Validation Too Strict
**Likelihood:** Low
**Impact:** Medium (could reject valid data)
**Mitigation:** Validators match existing usage patterns observed in codebase

### Risk 3: Collection Already Exists in Some Environments
**Likelihood:** Medium
**Impact:** Low (collection creation is idempotent)
**Mitigation:** `_init_database_schema()` checks `has_collection()` before creating

---

## Design Approval Checklist

- [ ] Schema addition location confirmed (DOCUMENT_COLLECTIONS)
- [ ] Model field types match existing usage
- [ ] Validators cover all enum-like fields
- [ ] No breaking changes to existing code
- [ ] Testing strategy covers validation edge cases

---

## Change History

| Date | Version | Changes | Status |
|------|---------|---------|--------|
| 2026-03-02 | v1 | Initial design for 1 collection + 3 models | Draft |
