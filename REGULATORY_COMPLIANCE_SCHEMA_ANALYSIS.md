# Regulatory Compliance Schema Architecture Analysis

**Date:** 2026-03-01
**Scope:** Comprehensive regulatory compliance schema for Complira Knowledge Graph
**Status:** Design Review & Implementation Planning

---

## Executive Summary

This document provides a comprehensive architectural analysis of the proposed regulatory compliance schema for the Complira Knowledge Graph Engine. The analysis validates the schema design, assesses implementation risks, and provides a concrete Phase 0 migration plan.

**Key Findings:**
- ✅ Current schema foundation is solid but **incomplete** for regulatory compliance
- ⚠️ **CRITICAL GAP:** Missing dedicated collections for `regulatory_frameworks`, `requirement_hierarchy`, and `framework_applicability`
- ✅ Three-track methodology is sound but needs clearer phase separation
- ⚠️ Implementation plan lacks data validation strategy and rollback mechanisms
- 📋 Phase 0 requires **4 new collections + 3 new edge types + 7 new indexes**

---

## 1. Schema Design Validation

### 1.1 Current State Analysis

**Existing Collections (from `/src/complira_graph/db.py`):**
```python
# Compliance & Regulatory (4 collections) - CURRENT
"regulatory_requirements",   # Generic requirements (placeholder)
"oscal_controls",            # NIST SP 800-53 Rev 5 controls
"scf_controls",              # Secure Controls Framework 2025.4
"opencre_nodes",             # OWASP OpenCRE nodes
```

**Existing Edge Collections:**
```python
# Compliance & Regulatory (3 edges) - CURRENT
"maps_to_requirement",       # CWE → regulatory requirement
"cross_framework_mapping",   # Framework ↔ framework equivalence
"opencre_links",             # OpenCRE → standards/requirements
```

### 1.2 Gap Analysis: Missing Schema Components

#### ❌ CRITICAL: No Dedicated Regulatory Framework Collection

**Problem:** The current schema treats all regulatory requirements equally in a single `regulatory_requirements` collection. This doesn't capture:
- Framework metadata (EU CRA, FDA 524B, IEC 62304, NIST SSDF)
- Applicability rules (medical devices vs. cyber products)
- Hierarchical structure (chapters → sections → requirements)
- Legal jurisdiction (EU, US, ISO international)

**Proposed Solution:**

```python
# NEW: Add to DOCUMENT_COLLECTIONS in db.py
DOCUMENT_COLLECTIONS = [
    # ... existing collections ...

    # ========== Enhanced Compliance & Regulatory (7 collections) ==========
    "regulatory_frameworks",      # NEW: Top-level frameworks (CRA, FDA 524B, etc.)
    "regulatory_requirements",    # ENHANCED: Individual requirements with hierarchy
    "oscal_controls",            # EXISTING: NIST SP 800-53 Rev 5 controls
    "scf_controls",              # EXISTING: Secure Controls Framework 2025.4
    "opencre_nodes",             # EXISTING: OWASP OpenCRE nodes
]

EDGE_COLLECTIONS = [
    # ... existing edges ...

    # ========== Enhanced Compliance & Regulatory (6 edges) ==========
    "requirement_hierarchy",      # NEW: Requirement → parent requirement
    "framework_contains",         # NEW: Framework → requirements
    "framework_applicability",    # NEW: Framework → product categories
    "maps_to_requirement",       # EXISTING: CWE → regulatory requirement
    "cross_framework_mapping",   # EXISTING: Framework ↔ framework equivalence
    "opencre_links",             # EXISTING: OpenCRE → standards/requirements
]
```

### 1.3 Proposed Schema Design

#### Collection: `regulatory_frameworks`

**Purpose:** Top-level metadata for each regulatory framework

**Fields:**
```python
{
    "_key": "eu_cra_2024",  # Deterministic key
    "framework_id": "EU-CRA-2024",
    "name": "EU Cyber Resilience Act",
    "short_name": "CRA",
    "version": "2024",
    "jurisdiction": "EU",  # EU, US, ISO, etc.
    "status": "enacted",  # draft, proposed, enacted, superseded
    "effective_date": "2024-12-01",
    "category": "cybersecurity",  # cybersecurity, medical_device, automotive
    "scope": "Products with digital elements",
    "authority": "European Commission",
    "url": "https://eur-lex.europa.eu/...",
    "document_format": "html",  # json, xml, pdf, html
    "parsing_track": "track_b",  # track_a (OSCAL/JSON), track_b (HTML), track_c (manual)
    "created_at": "2026-03-01T00:00:00Z",
    "updated_at": "2026-03-01T00:00:00Z"
}
```

**Index Strategy:**
```python
INDEXES["regulatory_frameworks"] = [
    {"type": "persistent", "fields": ["framework_id"], "unique": True},
    {"type": "persistent", "fields": ["jurisdiction"]},
    {"type": "persistent", "fields": ["status"]},
    {"type": "persistent", "fields": ["category"]},
]
```

#### Collection: `regulatory_requirements` (Enhanced)

**Purpose:** Individual requirements with full hierarchy support

**Current Schema (from `/src/complira_graph/models.py`):**
```python
class RegulatoryRequirement(BaseDocument):
    requirement_id: str
    framework: str  # GDPR, HIPAA, SOC2, etc.
    title: str
    description: str
    category: Optional[str] = None
    control_objectives: List[str] = Field(default_factory=list)
```

**Enhanced Schema:**
```python
{
    "_key": "eu_cra_2024_annex_i_2_1",
    "requirement_id": "Annex I.2.1",
    "framework_key": "eu_cra_2024",  # Links to regulatory_frameworks
    "title": "Vulnerability handling process",
    "description": "Products shall have a process for handling vulnerabilities...",
    "requirement_type": "mandatory",  # mandatory, recommended, optional
    "level": 2,  # Hierarchy depth (0=framework, 1=chapter, 2=section, 3=requirement)
    "parent_id": "eu_cra_2024_annex_i_2",  # For hierarchy traversal
    "chapter": "Annex I",
    "section": "2",
    "article": "1",
    "text_raw": "Full legal text...",
    "text_normalized": "Simplified text for LLM analysis...",
    "applicability_conditions": ["digital_element", "network_connected"],
    "verification_methods": ["documentation", "testing", "audit"],
    "related_cwe_ids": ["CWE-1035", "CWE-1357"],  # Mapped via LLM
    "source_url": "https://eur-lex.europa.eu/...",
    "created_at": "2026-03-01T00:00:00Z",
    "updated_at": "2026-03-01T00:00:00Z"
}
```

**Index Strategy:**
```python
INDEXES["regulatory_requirements"] = [
    {"type": "persistent", "fields": ["requirement_id"], "unique": True},
    {"type": "persistent", "fields": ["framework_key"]},
    {"type": "persistent", "fields": ["requirement_type"]},
    {"type": "persistent", "fields": ["level"]},
    {"type": "persistent", "fields": ["parent_id"]},
    {"type": "persistent", "fields": ["related_cwe_ids[*]"]},  # Array index
]
```

#### Edge: `requirement_hierarchy`

**Purpose:** Hierarchical relationships between requirements

```python
{
    "_from": "regulatory_requirements/eu_cra_2024_annex_i_2_1",
    "_to": "regulatory_requirements/eu_cra_2024_annex_i_2",
    "relationship": "child_of",
    "depth": 1
}
```

#### Edge: `framework_contains`

**Purpose:** Link frameworks to their requirements

```python
{
    "_from": "regulatory_frameworks/eu_cra_2024",
    "_to": "regulatory_requirements/eu_cra_2024_annex_i_2_1",
    "requirement_count": 147  # Total requirements in framework
}
```

#### Edge: `framework_applicability`

**Purpose:** Define which product categories each framework applies to

```python
{
    "_from": "regulatory_frameworks/eu_cra_2024",
    "_to": "product_categories/medical_devices",  # Could link to a taxonomy
    "applicability": "conditional",  # mandatory, conditional, excluded
    "conditions": ["Class IIa or higher", "Software as Medical Device"],
    "effective_date": "2027-01-01"
}
```

### 1.4 Performance Optimization Recommendations

#### ✅ Index Optimization

**Good:**
- Using `persistent` indexes (cached in memory)
- Array indexing for `related_cwe_ids[*]`
- Unique constraints on ID fields

**Recommendations:**
1. **Add composite index** for hierarchy traversal:
   ```python
   {"type": "persistent", "fields": ["framework_key", "level"]}
   ```
2. **Add fulltext index** for requirement search:
   ```python
   {"type": "fulltext", "fields": ["title", "description"]}
   ```
3. **Add geo index** for jurisdiction queries (if needed later):
   ```python
   {"type": "persistent", "fields": ["jurisdiction"]}
   ```

#### ⚠️ Potential Performance Bottlenecks

**1. Hierarchical Queries**

**Problem:** Deep hierarchy traversal (5+ levels) could be slow

**Query Example:**
```aql
// Find all requirements under Annex I
FOR req IN regulatory_requirements
    FILTER req.framework_key == "eu_cra_2024"
    FILTER req.chapter == "Annex I"
    // Traverse down to all children
    FOR child IN 1..10 OUTBOUND req requirement_hierarchy
        RETURN child
```

**Optimization:**
- Add `path` field with materialized path: `"Annex I > 2 > 2.1"`
- Use `level` field to limit depth
- Consider ArangoDB's `PRUNE` keyword for early termination

**2. Cross-Framework Mapping Queries**

**Problem:** LLM-based cross-framework mapping could create O(n²) edges

**Example:** Mapping NIST 800-53 (1000 controls) to ISO 27001 (114 controls) = up to 114,000 edges

**Optimization:**
- Only create high-confidence mappings (confidence >= 0.90)
- Use edge attributes to store mapping quality
- Batch edge creation in transactions

**3. Bulk Requirement Ingestion**

**Problem:** Importing 1000+ requirements per framework with hierarchy edges

**Solution:**
```python
# Drop indexes before bulk import
drop_indexes("regulatory_requirements")
drop_indexes("requirement_hierarchy")

# Bulk import requirements
collection.import_bulk(requirements, on_duplicate="update", batch_size=10000)

# Rebuild indexes
rebuild_indexes("regulatory_requirements")
rebuild_indexes("requirement_hierarchy")
```

### 1.5 Edge Collection Design Validation

#### ✅ Correct Design Patterns

**Good:**
- Using `_from` and `_to` with collection prefixes
- Storing confidence scores for LLM-generated mappings
- Including provenance metadata (source, model, timestamp)

**Example from `/src/complira_graph/llm_agents/regulatory_mapper.py`:**
```python
edge = {
    '_from': f'vulnerabilities/{cve_key}',
    '_to': f'{target_collection}/{control_key}',
    'framework': framework,
    'confidence': confidence,
    'rationale': rationale,
    'source': 'llm',
    'model': enrichment['model'],
    'timestamp': enrichment['timestamp'],
}
```

#### ⚠️ Missing Edge Validations

**Recommendation:** Add edge validation in `models.py`

```python
from pydantic import BaseModel, validator

class RequirementHierarchy(BaseModel):
    _from: str
    _to: str
    relationship: str  # child_of, related_to, supersedes
    depth: int

    @validator('_from', '_to')
    def validate_collection(cls, v):
        if not v.startswith('regulatory_requirements/'):
            raise ValueError('Edge must connect regulatory_requirements')
        return v

    @validator('depth')
    def validate_depth(cls, v):
        if v < 0 or v > 10:
            raise ValueError('Hierarchy depth must be 0-10')
        return v
```

---

## 2. Three-Track Methodology Risk Assessment

### 2.1 Track A: Deterministic Parsing (OSCAL/JSON sources)

**Sources:**
- NIST SSDF (OSCAL JSON)
- NIST 800-53 Rev 5 (OSCAL JSON)

**Risk Assessment:**

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| OSCAL schema changes break parser | Low | High | Version pin OSCAL schema, add schema validation tests |
| Missing fields in OSCAL | Medium | Medium | Graceful degradation with logging |
| NIST API rate limiting | Low | Low | Respect rate limits, cache responses |

**Implementation Confidence:** ✅ **HIGH** - OSCAL is well-structured JSON with stable schema

**Recommendations:**
1. Use `oscal-pydantic` library for type-safe parsing
2. Add JSON schema validation before parsing
3. Implement incremental update detection via `last-modified` date

### 2.2 Track B: Semi-Structured HTML (EUR-Lex regulations)

**Sources:**
- EU CRA (Cyber Resilience Act) - HTML
- EU NIS2 Directive - HTML
- EU AI Act - HTML

**Risk Assessment:**

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| HTML structure changes | High | High | Use robust CSS selectors, fallback to LLM extraction |
| Multilingual content | Medium | Medium | Parse English version only for v1.0 |
| Nested hierarchy ambiguity | High | Medium | LLM-assisted hierarchy inference |
| EUR-Lex rate limiting | Low | Medium | Implement caching, respect robots.txt |

**Implementation Confidence:** ⚠️ **MEDIUM** - HTML parsing is fragile, requires careful testing

**Recommendations:**
1. **Use BeautifulSoup + LLM hybrid approach:**
   ```python
   # Step 1: Extract raw sections with BeautifulSoup
   sections = soup.select('div.chapter')

   # Step 2: Use Claude to parse hierarchy
   prompt = f"Parse this legal text into structured requirements: {section.text}"
   requirements = claude.parse(prompt)
   ```

2. **Version the HTML selectors:**
   ```python
   EUR_LEX_SELECTORS = {
       "2024-03-01": {  # EUR-Lex layout version
           "chapter": "div.chapter",
           "section": "div.section",
           "article": "div.article"
       }
   }
   ```

3. **Add smoke tests:**
   ```python
   def test_eur_lex_parser():
       # Fetch known document
       html = fetch_eur_lex("32024R1029")
       requirements = parse_eur_lex(html)
       assert len(requirements) > 100  # CRA has ~200 requirements
       assert requirements[0]["framework_id"] == "EU-CRA-2024"
   ```

### 2.3 Track C: Manual Curation + LLM (Copyrighted ISO/IEC standards)

**Sources:**
- IEC 62304 (Medical Device Software)
- ISO 21434 (Automotive Cybersecurity)
- ISO/SAE 21434 (Road Vehicles)

**Risk Assessment:**

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Manual data entry errors | High | High | Double-entry validation, LLM verification |
| Copyright infringement | High | Critical | ⚠️ **DO NOT INGEST FULL TEXT** - only store requirement IDs + summaries |
| Outdated standards | Medium | Medium | Manual quarterly review process |
| Inconsistent formatting | High | Medium | LLM normalization pass |

**Implementation Confidence:** ⚠️ **LOW** - Manual process is error-prone and legally risky

**⚠️ CRITICAL LEGAL RECOMMENDATION:**

**DO NOT store copyrighted text from ISO/IEC standards.** Instead:

1. **Store only metadata:**
   ```python
   {
       "_key": "iec_62304_2015_5_2_1",
       "requirement_id": "5.2.1",
       "framework_key": "iec_62304_2015",
       "title": "Software development planning",
       "description": "SUMMARY ONLY - see purchased standard",
       "chapter": "5",
       "section": "2.1",
       "text_raw": None,  # DO NOT STORE
       "text_normalized": "Software teams must create development plans",  # Fair use summary
       "source_url": "https://www.iso.org/standard/62304.html",
       "purchase_required": true
   }
   ```

2. **Link to OpenCRE mappings:**
   ```python
   # OpenCRE already maps ISO standards to NIST 800-53
   # Use these mappings instead of re-parsing copyrighted text
   ```

3. **Manual curation workflow:**
   ```
   1. Security engineer reads purchased ISO standard
   2. Engineer enters requirement ID + summary into spreadsheet
   3. LLM validates summary doesn't contain copyrighted text
   4. Import spreadsheet into regulatory_requirements collection
   ```

### 2.4 Overall Methodology Risks

**Missing Elements:**

1. **❌ No data validation strategy** - How to verify parsed requirements are correct?
2. **❌ No versioning strategy** - How to handle framework updates (CRA 2024 → CRA 2025)?
3. **❌ No conflict resolution** - What if LLM disagrees with manual curation?
4. **❌ No quality metrics** - How to measure parsing accuracy?

**Recommended Additions:**

```python
# Add to regulatory_requirements collection
{
    "validation_status": "verified",  # unverified, verified, disputed
    "validation_method": "manual_review",  # llm, manual_review, automated
    "validator": "compliance_analyst_1",
    "validation_date": "2026-03-15",
    "parsing_confidence": 0.95,  # LLM confidence score
    "version": "1.0"  # Increment on updates
}
```

---

## 3. Implementation Roadmap Evaluation

### 3.1 Proposed Phases (from User's Plan)

```
Phase 0: Schema migration (Week 1)
Phase 1: NIST SSDF + EU CRA (Weeks 2-3)
Phase 2: FDA 524B + IEC 62304 (Weeks 4-6)
Phase 3: LLM cross-framework mapping (Weeks 5-7)
Phase 4: Remaining frameworks (Weeks 7-10)
Phase 5: Compliance Passport integration (Weeks 10-12)
```

### 3.2 Sequencing Analysis

#### ✅ Good Sequencing Decisions

1. **Phase 0 first:** Schema migration before data ingestion (correct dependency)
2. **NIST SSDF first:** Easiest source (OSCAL JSON) builds confidence
3. **LLM mapping after data ingestion:** Can't map until requirements exist

#### ⚠️ Sequencing Issues

**Problem 1: Phase 2 and 3 Overlap**

```
Phase 2: FDA 524B + IEC 62304 (Weeks 4-6)
Phase 3: LLM cross-framework mapping (Weeks 5-7)
```

**Issue:** LLM mapping starts before IEC 62304 ingestion completes

**Fix:**
```
Phase 2: FDA 524B + IEC 62304 (Weeks 4-6)
Phase 3: LLM cross-framework mapping (Weeks 7-9)  ← Shifted 2 weeks
Phase 4: Remaining frameworks (Weeks 10-12)
Phase 5: Compliance Passport integration (Weeks 13-15)
```

**Problem 2: No Proof-of-Concept Milestone**

**Issue:** No early validation that the approach works

**Fix:** Add Phase 0.5:

```
Phase 0: Schema migration (Week 1)
Phase 0.5: POC - NIST SSDF only (Week 2)  ← NEW
  - Prove Track A (OSCAL) works end-to-end
  - Validate query performance
  - Test LLM CWE mapping on SSDF requirements
Phase 1: EU CRA (Weeks 3-4)  ← Shifted
Phase 2: FDA 524B + IEC 62304 (Weeks 5-7)
Phase 3: LLM cross-framework mapping (Weeks 8-10)
Phase 4: Remaining frameworks (Weeks 11-13)
Phase 5: Compliance Passport integration (Weeks 14-16)
```

### 3.3 Revised Implementation Roadmap

**Recommended Sequencing:**

| Phase | Duration | Deliverable | Success Criteria |
|-------|----------|-------------|------------------|
| **Phase 0: Schema Migration** | Week 1 | 4 new collections, 3 new edges, Pydantic models | All schema tests pass |
| **Phase 0.5: POC (NIST SSDF)** | Week 2 | NIST SSDF fully ingested, queries working | Blast radius query <5s, 100% SSDF coverage |
| **Phase 1: Track B (EU CRA)** | Weeks 3-4 | EUR-Lex parser, CRA requirements in graph | 150+ requirements ingested, hierarchy validated |
| **Phase 2: Track A (FDA 524B)** | Weeks 5-6 | FDA guidance parsed, medical device requirements | 80+ requirements ingested |
| **Phase 3: Track C (IEC 62304)** | Week 7 | Manual curation workflow, IEC metadata | 50+ requirement summaries (no copyrighted text) |
| **Phase 4: LLM Cross-Framework Mapping** | Weeks 8-10 | Claude Opus 4 mapping, cross_framework_mapping edges | 1000+ mappings with confidence >0.85 |
| **Phase 5: Remaining Frameworks** | Weeks 11-13 | ISO 21434, NIS2, other regulations | 500+ additional requirements |
| **Phase 6: Compliance Passport Integration** | Weeks 14-16 | API endpoints, SBOM → requirements query | End-to-end demo working |

---

## 4. Implementation Gaps Analysis

### 4.1 Testing Strategy ❌ MISSING

**Current State:** No test strategy mentioned in implementation plan

**Required Tests:**

#### Unit Tests
```python
# tests/unit/test_regulatory_schema.py
def test_regulatory_framework_model():
    framework = RegulatoryFramework(
        framework_id="EU-CRA-2024",
        name="EU Cyber Resilience Act",
        jurisdiction="EU",
        status="enacted"
    )
    assert framework.framework_id == "EU-CRA-2024"

# tests/unit/test_requirement_hierarchy.py
def test_hierarchy_depth_validation():
    edge = RequirementHierarchy(
        _from="regulatory_requirements/parent",
        _to="regulatory_requirements/child",
        depth=1
    )
    assert edge.depth == 1
```

#### Integration Tests
```python
# tests/integration/test_eur_lex_parser.py
def test_cra_parsing_full_workflow():
    # Fetch CRA HTML
    html = fetch_eur_lex("32024R1029")

    # Parse requirements
    requirements = parse_eur_lex(html)

    # Validate structure
    assert len(requirements) >= 150
    assert all(r["framework_key"] == "eu_cra_2024" for r in requirements)

    # Load into database
    db = get_db()
    collection = db.collection("regulatory_requirements")
    collection.import_bulk(requirements)

    # Query hierarchy
    result = db.aql.execute("""
        FOR req IN regulatory_requirements
            FILTER req.framework_key == "eu_cra_2024"
            FILTER req.chapter == "Annex I"
            RETURN req
    """)
    assert len(list(result)) > 0
```

#### Performance Tests
```python
# tests/performance/test_regulatory_queries.py
import time

def test_blast_radius_query_performance():
    start = time.time()

    # Query all frameworks affected by CWE-79
    result = db.aql.execute("""
        FOR cwe IN weaknesses
            FILTER cwe.cwe_id == "CWE-79"
            FOR req IN 1..2 OUTBOUND cwe maps_to_requirement
                FOR framework IN 1..1 INBOUND req framework_contains
                    RETURN DISTINCT framework.name
    """)

    elapsed = time.time() - start
    assert elapsed < 5.0  # Must complete in <5 seconds
```

### 4.2 Data Validation Approach ❌ MISSING

**Problem:** No strategy to validate parsed requirements are correct

**Recommended Validation Pipeline:**

```python
class RequirementValidator:
    def validate_requirement(self, requirement: dict) -> ValidationResult:
        checks = [
            self.check_required_fields(requirement),
            self.check_id_format(requirement),
            self.check_hierarchy_integrity(requirement),
            self.check_duplicate_ids(requirement),
            self.check_text_quality(requirement),  # LLM-based
        ]

        return ValidationResult(
            passed=all(c.passed for c in checks),
            errors=[c.error for c in checks if not c.passed]
        )

    def check_hierarchy_integrity(self, requirement: dict) -> Check:
        """Verify parent_id exists in database"""
        parent_id = requirement.get("parent_id")
        if not parent_id:
            return Check(passed=True)

        parent = db.collection("regulatory_requirements").get(parent_id)
        if not parent:
            return Check(
                passed=False,
                error=f"Parent {parent_id} does not exist"
            )
        return Check(passed=True)
```

### 4.3 Migration Rollback Plan ❌ MISSING

**Problem:** No rollback strategy if Phase 0 migration fails

**Recommended Rollback Strategy:**

```python
# Migration script with transaction support
def migrate_schema_phase_0():
    db = get_db()

    # 1. Backup current schema
    backup_collections([
        "regulatory_requirements",
        "maps_to_requirement"
    ])

    # 2. Begin transaction
    with db.begin_transaction(write=["regulatory_frameworks", "regulatory_requirements"]) as txn:
        try:
            # 3. Create new collections
            create_collection(txn, "regulatory_frameworks")
            create_collection(txn, "requirement_hierarchy")

            # 4. Migrate existing data
            migrate_existing_requirements(txn)

            # 5. Create indexes
            create_indexes(txn)

            # 6. Commit transaction
            txn.commit()

        except Exception as e:
            # 7. Rollback on failure
            txn.abort()
            restore_collections_from_backup()
            raise MigrationError(f"Migration failed: {e}")

    # 8. Verify migration
    verify_migration_success()
```

### 4.4 Documentation Requirements ❌ MISSING

**Problem:** No documentation plan for regulatory schema

**Required Documentation:**

1. **Schema Documentation:**
   ```markdown
   # Regulatory Compliance Schema

   ## Collections

   ### `regulatory_frameworks`
   **Purpose:** Top-level metadata for regulatory frameworks

   **Fields:**
   - `framework_id` (string, unique): Canonical identifier (e.g., "EU-CRA-2024")
   - `name` (string): Full legal name
   - `jurisdiction` (string): EU, US, ISO, etc.
   ...

   **Example Document:**
   ```json
   {
       "_key": "eu_cra_2024",
       "framework_id": "EU-CRA-2024",
       "name": "EU Cyber Resilience Act"
   }
   ```

   **Queries:**
   ```aql
   // Find all EU regulations
   FOR framework IN regulatory_frameworks
       FILTER framework.jurisdiction == "EU"
       RETURN framework
   ```
   ```

2. **API Documentation:**
   ```python
   @cli.command()
   @click.argument("framework_id")
   def show_framework(framework_id: str):
       """
       Display regulatory framework details.

       Example:
           complira show-framework EU-CRA-2024
       """
   ```

3. **Migration Documentation:**
   ```markdown
   # Phase 0 Migration Guide

   ## Prerequisites
   - ArangoDB 3.12+ running
   - Backup of existing database
   - Python 3.11+ with dependencies installed

   ## Steps
   1. Run backup: `./scripts/backup.sh`
   2. Run migration: `python scripts/migrate_phase_0.py`
   3. Verify: `python scripts/verify_migration.py`
   4. Rollback (if needed): `./scripts/rollback_phase_0.sh`
   ```

### 4.5 API Changes Needed ❌ PARTIALLY ADDRESSED

**Current API (from `/src/complira_graph/cli.py`):**
```python
@cli.command()
@click.argument("cve_id")
def blast_radius(cve_id: str):
    """Query regulatory blast radius for a CVE"""
```

**Missing API Commands:**

```python
@cli.command()
@click.argument("framework_id")
def show_framework(framework_id: str):
    """Display regulatory framework metadata and statistics"""
    db = get_db()
    framework = db.collection("regulatory_frameworks").get(framework_id)

    # Get requirement count
    req_count = db.aql.execute("""
        FOR req IN regulatory_requirements
            FILTER req.framework_key == @framework_id
            COLLECT WITH COUNT INTO count
            RETURN count
    """, bind_vars={"framework_id": framework_id})

    click.echo(f"Framework: {framework['name']}")
    click.echo(f"Requirements: {req_count}")

@cli.command()
@click.argument("requirement_id")
def show_requirement(requirement_id: str):
    """Display requirement details and hierarchy"""
    db = get_db()
    req = db.collection("regulatory_requirements").get(requirement_id)

    # Get parent chain
    parents = db.aql.execute("""
        FOR v, e, p IN 0..10 OUTBOUND @start requirement_hierarchy
            RETURN {level: p.vertices[-1].level, title: p.vertices[-1].title}
    """, bind_vars={"start": f"regulatory_requirements/{requirement_id}"})

    click.echo(f"Requirement: {req['title']}")
    click.echo(f"Hierarchy: {' > '.join(p['title'] for p in parents)}")

@cli.command()
def list_frameworks():
    """List all regulatory frameworks"""
    db = get_db()
    frameworks = db.aql.execute("""
        FOR framework IN regulatory_frameworks
            SORT framework.jurisdiction, framework.name
            RETURN {
                id: framework.framework_id,
                name: framework.name,
                jurisdiction: framework.jurisdiction,
                status: framework.status
            }
    """)

    for f in frameworks:
        click.echo(f"{f['id']}: {f['name']} ({f['jurisdiction']}) - {f['status']}")

@cli.command()
@click.argument("cwe_id")
def map_cwe_to_frameworks(cwe_id: str):
    """Map a CWE to all applicable regulatory frameworks"""
    db = get_db()

    # Query CWE → Requirements → Frameworks
    result = db.aql.execute("""
        FOR cwe IN weaknesses
            FILTER cwe.cwe_id == @cwe_id
            FOR req IN 1..2 OUTBOUND cwe maps_to_requirement
                FOR framework IN 1..1 INBOUND req framework_contains
                    RETURN DISTINCT {
                        framework: framework.name,
                        requirement: req.title,
                        requirement_id: req.requirement_id,
                        confidence: req.llm_confidence  // If LLM-generated
                    }
    """, bind_vars={"cwe_id": cwe_id})

    for mapping in result:
        click.echo(f"{mapping['framework']}: {mapping['requirement_id']} - {mapping['requirement']}")
```

---

## 5. Phase 0 (Schema Migration) Deep Dive

### 5.1 Exact Steps for Migration

#### Step 1: Create Migration Script

**File:** `scripts/migrate_phase_0_regulatory_schema.py`

```python
#!/usr/bin/env python3
"""
Phase 0: Regulatory Compliance Schema Migration

Adds 4 new collections and 3 new edge types to support hierarchical
regulatory frameworks (EU CRA, FDA 524B, IEC 62304, NIST SSDF).

Usage:
    python scripts/migrate_phase_0_regulatory_schema.py --dry-run
    python scripts/migrate_phase_0_regulatory_schema.py --execute
"""

import click
from datetime import datetime
from arango.database import StandardDatabase
from complira_graph.db import get_db
import structlog

logger = structlog.get_logger()

# Migration metadata
MIGRATION_VERSION = "0.1.0"
MIGRATION_DATE = "2026-03-01"

def backup_database(db: StandardDatabase) -> str:
    """Create backup before migration"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"pre_phase0_migration_{timestamp}"

    logger.info("Creating backup", backup_name=backup_name)

    # Export collections to JSON
    collections_to_backup = [
        "regulatory_requirements",
        "maps_to_requirement",
        "cross_framework_mapping"
    ]

    for collection_name in collections_to_backup:
        if db.has_collection(collection_name):
            collection = db.collection(collection_name)
            docs = collection.all()

            # Write to backup file
            backup_file = f"backups/{backup_name}_{collection_name}.json"
            with open(backup_file, 'w') as f:
                import json
                json.dump(list(docs), f, indent=2)

            logger.info("Backed up collection",
                       collection=collection_name,
                       file=backup_file)

    return backup_name

def create_new_collections(db: StandardDatabase, dry_run: bool = False):
    """Create new regulatory schema collections"""
    new_collections = {
        "regulatory_frameworks": False,  # Document collection
        "requirement_hierarchy": True,   # Edge collection
        "framework_contains": True,      # Edge collection
        "framework_applicability": True  # Edge collection
    }

    for collection_name, is_edge in new_collections.items():
        if db.has_collection(collection_name):
            logger.warning("Collection already exists",
                          collection=collection_name)
            continue

        if dry_run:
            logger.info("DRY RUN: Would create collection",
                       collection=collection_name,
                       edge=is_edge)
        else:
            db.create_collection(collection_name, edge=is_edge)
            logger.info("Created collection",
                       collection=collection_name,
                       edge=is_edge)

def create_indexes(db: StandardDatabase, dry_run: bool = False):
    """Create performance indexes on new collections"""
    indexes_to_create = {
        "regulatory_frameworks": [
            {"fields": ["framework_id"], "unique": True},
            {"fields": ["jurisdiction"]},
            {"fields": ["status"]},
            {"fields": ["category"]},
        ],
        "regulatory_requirements": [
            {"fields": ["framework_key"]},
            {"fields": ["requirement_type"]},
            {"fields": ["level"]},
            {"fields": ["parent_id"]},
            {"fields": ["related_cwe_ids[*]"]},  # Array index
            # Composite index for hierarchy queries
            {"fields": ["framework_key", "level"]},
        ]
    }

    for collection_name, indexes in indexes_to_create.items():
        if not db.has_collection(collection_name):
            logger.warning("Collection does not exist, skipping indexes",
                          collection=collection_name)
            continue

        collection = db.collection(collection_name)

        for index_def in indexes:
            if dry_run:
                logger.info("DRY RUN: Would create index",
                           collection=collection_name,
                           fields=index_def["fields"])
            else:
                try:
                    collection.add_persistent_index(
                        fields=index_def["fields"],
                        unique=index_def.get("unique", False),
                        sparse=False
                    )
                    logger.info("Created index",
                               collection=collection_name,
                               fields=index_def["fields"])
                except Exception as e:
                    logger.warning("Index creation failed",
                                  collection=collection_name,
                                  fields=index_def["fields"],
                                  error=str(e))

def migrate_existing_data(db: StandardDatabase, dry_run: bool = False):
    """Migrate existing regulatory_requirements to new schema"""

    if not db.has_collection("regulatory_requirements"):
        logger.info("No existing data to migrate")
        return

    collection = db.collection("regulatory_requirements")
    existing_count = collection.count()

    if existing_count == 0:
        logger.info("No existing requirements to migrate")
        return

    logger.info("Migrating existing requirements", count=existing_count)

    # Query all existing requirements
    cursor = db.aql.execute("""
        FOR req IN regulatory_requirements
            RETURN req
    """)

    migrated = 0
    for req in cursor:
        # Add new fields to existing documents
        update_doc = {
            "_key": req["_key"],
            "framework_key": req.get("framework", "unknown").lower().replace(" ", "_"),
            "requirement_type": "mandatory",  # Default
            "level": 1,  # Assume top-level for existing data
            "parent_id": None,
            "related_cwe_ids": [],
        }

        if dry_run:
            logger.debug("DRY RUN: Would update requirement",
                        requirement_id=req.get("requirement_id"))
        else:
            collection.update(update_doc)
            migrated += 1

    logger.info("Migration complete", migrated=migrated)

def verify_migration(db: StandardDatabase) -> bool:
    """Verify migration was successful"""
    logger.info("Verifying migration")

    checks = []

    # Check 1: All collections exist
    required_collections = [
        "regulatory_frameworks",
        "regulatory_requirements",
        "requirement_hierarchy",
        "framework_contains",
        "framework_applicability"
    ]

    for collection_name in required_collections:
        exists = db.has_collection(collection_name)
        checks.append(("collection_exists", collection_name, exists))
        if not exists:
            logger.error("Migration verification failed: missing collection",
                        collection=collection_name)

    # Check 2: Indexes created
    frameworks = db.collection("regulatory_frameworks")
    indexes = frameworks.indexes()
    framework_id_index = any(
        "framework_id" in idx.get("fields", [])
        for idx in indexes
    )
    checks.append(("index_exists", "framework_id", framework_id_index))

    # Check 3: Data integrity
    if db.has_collection("regulatory_requirements"):
        req_collection = db.collection("regulatory_requirements")
        sample = next(req_collection.all(), None)
        if sample:
            has_framework_key = "framework_key" in sample
            checks.append(("field_exists", "framework_key", has_framework_key))

    # Summary
    passed = all(check[2] for check in checks)
    logger.info("Migration verification",
               passed=passed,
               total_checks=len(checks),
               failed_checks=sum(1 for c in checks if not c[2]))

    return passed

@click.command()
@click.option('--dry-run', is_flag=True, help='Preview changes without executing')
@click.option('--skip-backup', is_flag=True, help='Skip database backup (dangerous!)')
@click.option('--execute', is_flag=True, help='Execute migration')
def main(dry_run: bool, skip_backup: bool, execute: bool):
    """
    Phase 0: Regulatory Compliance Schema Migration

    This script adds support for hierarchical regulatory frameworks.
    """

    if not dry_run and not execute:
        click.echo("Error: Must specify --dry-run or --execute")
        click.echo("Run with --help for usage information")
        return

    logger.info("Starting Phase 0 migration",
               version=MIGRATION_VERSION,
               dry_run=dry_run,
               execute=execute)

    # Get database connection
    db = get_db()

    # Step 1: Backup (unless --skip-backup)
    if execute and not skip_backup:
        backup_name = backup_database(db)
        logger.info("Backup created", backup=backup_name)

    # Step 2: Create new collections
    create_new_collections(db, dry_run=dry_run or not execute)

    # Step 3: Create indexes
    create_indexes(db, dry_run=dry_run or not execute)

    # Step 4: Migrate existing data
    migrate_existing_data(db, dry_run=dry_run or not execute)

    # Step 5: Verify migration
    if execute:
        success = verify_migration(db)
        if success:
            logger.info("✅ Migration completed successfully")
        else:
            logger.error("❌ Migration verification failed")
    else:
        logger.info("DRY RUN complete - no changes made")

if __name__ == "__main__":
    main()
```

#### Step 2: Update Database Schema (`/src/complira_graph/db.py`)

**Changes Required:**

```python
# BEFORE (lines 49-53)
# Compliance & Regulatory (4 collections)
"regulatory_requirements",   # CRA, FDA 524B, IEC 62304, NIST SSDF, ISO 21434
"oscal_controls",            # NIST SP 800-53 Rev 5 controls
"scf_controls",              # Secure Controls Framework 2025.4
"opencre_nodes",             # OWASP OpenCRE nodes

# AFTER
# Compliance & Regulatory (5 collections) - ENHANCED for Phase 0
"regulatory_frameworks",      # NEW: Top-level framework metadata (CRA, FDA, IEC, NIST)
"regulatory_requirements",    # ENHANCED: Individual requirements with hierarchy
"oscal_controls",            # EXISTING: NIST SP 800-53 Rev 5 controls
"scf_controls",              # EXISTING: Secure Controls Framework 2025.4
"opencre_nodes",             # EXISTING: OWASP OpenCRE nodes

# BEFORE (lines 92-94)
# Compliance & Regulatory (3 edges)
"maps_to_requirement",       # CWE → regulatory requirement
"cross_framework_mapping",   # Framework ↔ framework equivalence
"opencre_links",             # OpenCRE → standards/requirements

# AFTER
# Compliance & Regulatory (6 edges) - ENHANCED for Phase 0
"requirement_hierarchy",      # NEW: Requirement → parent requirement (tree structure)
"framework_contains",         # NEW: Framework → requirements (1-to-many)
"framework_applicability",    # NEW: Framework → product categories
"maps_to_requirement",       # EXISTING: CWE → regulatory requirement
"cross_framework_mapping",   # EXISTING: Framework ↔ framework equivalence
"opencre_links",             # EXISTING: OpenCRE → standards/requirements

# Add new indexes
INDEXES["regulatory_frameworks"] = [
    {"type": "persistent", "fields": ["framework_id"], "unique": True},
    {"type": "persistent", "fields": ["jurisdiction"]},
    {"type": "persistent", "fields": ["status"]},
    {"type": "persistent", "fields": ["category"]},
]

INDEXES["regulatory_requirements"] = [
    {"type": "persistent", "fields": ["requirement_id"], "unique": True},
    {"type": "persistent", "fields": ["framework_key"]},
    {"type": "persistent", "fields": ["requirement_type"]},
    {"type": "persistent", "fields": ["level"]},
    {"type": "persistent", "fields": ["parent_id"]},
    {"type": "persistent", "fields": ["related_cwe_ids[*]"]},
    # Composite index for hierarchy traversal
    {"type": "persistent", "fields": ["framework_key", "level"]},
]
```

#### Step 3: Update Pydantic Models (`/src/complira_graph/models.py`)

**Add New Models:**

```python
# Add after line 377 (after RegulatoryRequirement class)

class RegulatoryFramework(BaseDocument):
    """
    Top-level regulatory framework metadata.

    Collection: regulatory_frameworks

    Examples: EU CRA, FDA 524B, IEC 62304, NIST SSDF
    """

    framework_id: str  # EU-CRA-2024, FDA-524B, IEC-62304-2015
    name: str  # Full legal name
    short_name: str  # CRA, FDA 524B, IEC 62304
    version: Optional[str] = None  # 2024, 2015, etc.
    jurisdiction: str  # EU, US, ISO, etc.
    status: str  # draft, proposed, enacted, superseded

    effective_date: Optional[str] = None  # ISO date
    category: str  # cybersecurity, medical_device, automotive
    scope: Optional[str] = None  # Text description of scope
    authority: Optional[str] = None  # European Commission, FDA, ISO

    url: Optional[str] = None
    document_format: str  # json, xml, pdf, html
    parsing_track: str  # track_a (OSCAL), track_b (HTML), track_c (manual)

    @staticmethod
    def generate_key(framework_id: str) -> str:
        """Generate deterministic _key from framework ID."""
        # EU-CRA-2024 → eu_cra_2024
        return framework_id.lower().replace('-', '_').replace(' ', '_')


# ENHANCE existing RegulatoryRequirement class (lines 380-394)
class RegulatoryRequirement(BaseDocument):
    """
    Individual regulatory requirement with hierarchy support.

    Collection: regulatory_requirements

    ENHANCED in Phase 0 to support hierarchical frameworks.
    """

    # Core identification
    requirement_id: str  # Annex I.2.1, 21 CFR 524B.1, etc.
    framework_key: str  # Links to regulatory_frameworks._key
    title: str
    description: str

    # Hierarchy (NEW in Phase 0)
    requirement_type: str = "mandatory"  # mandatory, recommended, optional
    level: int = 1  # 0=framework, 1=chapter, 2=section, 3=requirement
    parent_id: Optional[str] = None  # For hierarchy traversal

    # Legal structure
    chapter: Optional[str] = None  # "Annex I"
    section: Optional[str] = None  # "2"
    article: Optional[str] = None  # "1"

    # Content
    text_raw: Optional[str] = None  # Full legal text (empty for copyrighted standards)
    text_normalized: Optional[str] = None  # Simplified for LLM

    # Applicability
    applicability_conditions: List[str] = Field(default_factory=list)
    verification_methods: List[str] = Field(default_factory=list)

    # Mappings
    related_cwe_ids: List[str] = Field(default_factory=list)

    # Provenance
    source_url: Optional[str] = None

    @staticmethod
    def generate_key(framework_key: str, requirement_id: str) -> str:
        """Generate deterministic _key from framework + requirement ID."""
        # eu_cra_2024 + Annex I.2.1 → eu_cra_2024_annex_i_2_1
        normalized_id = requirement_id.lower() \
            .replace(' ', '_') \
            .replace('.', '_') \
            .replace('(', '') \
            .replace(')', '')
        return f"{framework_key}_{normalized_id}"


# Add edge models
class RequirementHierarchy(BaseModel):
    """
    Edge: requirement_hierarchy

    Links child requirements to parent requirements.
    """
    _from: str  # regulatory_requirements/child
    _to: str    # regulatory_requirements/parent
    relationship: str = "child_of"
    depth: int  # 1 for direct child, 2+ for deeper nesting


class FrameworkContains(BaseModel):
    """
    Edge: framework_contains

    Links frameworks to their requirements.
    """
    _from: str  # regulatory_frameworks/eu_cra_2024
    _to: str    # regulatory_requirements/eu_cra_2024_annex_i_2_1


class FrameworkApplicability(BaseModel):
    """
    Edge: framework_applicability

    Defines which product categories a framework applies to.
    """
    _from: str  # regulatory_frameworks/eu_cra_2024
    _to: str    # product_categories/medical_devices (or custom taxonomy)
    applicability: str  # mandatory, conditional, excluded
    conditions: List[str] = Field(default_factory=list)


# Update MODEL_REGISTRY (line 603)
MODEL_REGISTRY: Dict[str, type[BaseDocument]] = {
    # ... existing models ...
    'regulatory_frameworks': RegulatoryFramework,  # NEW
    'regulatory_requirements': RegulatoryRequirement,  # ENHANCED
    # ... rest of models ...
}
```

### 5.2 Migration Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Data loss during migration | Low | Critical | Automated backup before migration |
| Schema incompatibility | Medium | High | Dry-run mode + rollback script |
| Index creation timeout | Medium | Medium | Create indexes after data migration |
| Existing data corruption | Low | High | Validate before/after migration |
| Downtime during migration | High | Medium | Run during maintenance window |

### 5.3 Rollback Script

**File:** `scripts/rollback_phase_0.sh`

```bash
#!/bin/bash
# Rollback Phase 0 migration

set -e

BACKUP_NAME=$1

if [ -z "$BACKUP_NAME" ]; then
    echo "Usage: ./rollback_phase_0.sh <backup_name>"
    echo "Example: ./rollback_phase_0.sh pre_phase0_migration_20260301_120000"
    exit 1
fi

echo "⚠️  ROLLING BACK Phase 0 migration using backup: $BACKUP_NAME"
echo "This will:"
echo "  1. Drop new collections (regulatory_frameworks, requirement_hierarchy, etc.)"
echo "  2. Restore regulatory_requirements from backup"
echo ""
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Rollback cancelled"
    exit 0
fi

# Drop new collections
echo "Dropping new collections..."
python -c "
from complira_graph.db import get_db
db = get_db()

collections_to_drop = [
    'regulatory_frameworks',
    'requirement_hierarchy',
    'framework_contains',
    'framework_applicability'
]

for collection_name in collections_to_drop:
    if db.has_collection(collection_name):
        db.delete_collection(collection_name)
        print(f'Dropped {collection_name}')
"

# Restore from backup
echo "Restoring collections from backup..."
python -c "
from complira_graph.db import get_db
import json

db = get_db()
backup_name = '$BACKUP_NAME'

collections_to_restore = [
    'regulatory_requirements',
    'maps_to_requirement'
]

for collection_name in collections_to_restore:
    backup_file = f'backups/{backup_name}_{collection_name}.json'

    with open(backup_file, 'r') as f:
        docs = json.load(f)

    if db.has_collection(collection_name):
        collection = db.collection(collection_name)
        collection.truncate()
    else:
        db.create_collection(collection_name)
        collection = db.collection(collection_name)

    collection.import_bulk(docs, on_duplicate='replace')
    print(f'Restored {collection_name} ({len(docs)} documents)')
"

echo "✅ Rollback complete"
echo "Database restored to pre-migration state"
```

### 5.4 Testing Checklist for Phase 0

```markdown
## Phase 0 Migration Testing Checklist

### Pre-Migration
- [ ] Backup created successfully
- [ ] Backup files exist and are readable
- [ ] Dry-run completed without errors
- [ ] All team members notified of maintenance window

### Migration Execution
- [ ] Migration script runs without errors
- [ ] All 4 new collections created
  - [ ] regulatory_frameworks
  - [ ] requirement_hierarchy (edge)
  - [ ] framework_contains (edge)
  - [ ] framework_applicability (edge)
- [ ] All indexes created (7 total)
- [ ] Existing regulatory_requirements migrated
- [ ] No data loss detected

### Post-Migration Validation
- [ ] Schema verification passes
- [ ] Sample queries work:
  ```aql
  // Test 1: Count frameworks
  FOR framework IN regulatory_frameworks
      COLLECT WITH COUNT INTO count
      RETURN count

  // Test 2: Hierarchy traversal
  FOR req IN regulatory_requirements
      FILTER req.framework_key == "eu_cra_2024"
      FOR parent IN 1..1 OUTBOUND req requirement_hierarchy
          RETURN {child: req.requirement_id, parent: parent.requirement_id}
  ```
- [ ] Performance test: Blast radius query <5s
- [ ] No errors in ArangoDB logs
- [ ] All agents still functional

### Rollback Test (in staging)
- [ ] Rollback script tested successfully
- [ ] Backup restoration verified
- [ ] Post-rollback queries work
```

---

## 6. Recommendations Summary

### 6.1 Must-Have (Before Implementation Starts)

1. **✅ Implement Phase 0 migration script** (see Section 5.1)
2. **✅ Add data validation pipeline** (see Section 4.2)
3. **✅ Create rollback mechanism** (see Section 5.3)
4. **✅ Write integration tests** (see Section 4.1)
5. **✅ Document schema design** (see Section 4.4)

### 6.2 Should-Have (Before Phase 1)

1. **Add Phase 0.5 POC milestone** - Prove NIST SSDF ingestion works end-to-end
2. **Implement copyright-safe Track C workflow** - No copyrighted ISO/IEC text in database
3. **Add schema versioning** - Track when requirements change (CRA 2024 → CRA 2025)
4. **Create performance benchmarks** - Measure query speed before optimization
5. **Set up monitoring** - Prometheus metrics for migration success/failure

### 6.3 Nice-to-Have (Future Enhancements)

1. **Fulltext search** - Add ArangoSearch view for requirement text search
2. **Graph visualization** - Add API endpoint to export framework hierarchy as JSON for D3.js
3. **Conflict detection** - Flag when LLM mappings conflict with manual curation
4. **Automated framework updates** - Detect when EUR-Lex publishes new regulations
5. **Multi-language support** - Store requirements in multiple languages (EN, DE, FR)

---

## 7. Proof-of-Concept Validation Plan

To prove the regulatory compliance schema works, implement this **minimal viable test**:

### POC Scope: NIST SSDF Only (Week 2)

**Goal:** Validate entire workflow with smallest, cleanest data source

**Steps:**

1. **Ingest NIST SSDF (Track A - OSCAL JSON):**
   ```bash
   complira ingest-framework nist-ssdf
   ```

   **Success Criteria:**
   - 30+ SSDF requirements in `regulatory_requirements` collection
   - 1 framework in `regulatory_frameworks` collection
   - Hierarchy edges created correctly

2. **Map SSDF to CWE (LLM):**
   ```bash
   complira map-framework-to-cwe nist-ssdf
   ```

   **Success Criteria:**
   - 50+ `maps_to_requirement` edges created
   - Average confidence score >0.85
   - Provenance stored in `llm_enrichments`

3. **Query regulatory blast radius:**
   ```bash
   complira blast-radius CVE-2024-1234
   ```

   **Success Criteria:**
   - Query returns all SSDF requirements affected
   - Query completes in <5 seconds
   - Evidence chain is complete

4. **Validate data quality:**
   ```bash
   complira validate-framework nist-ssdf
   ```

   **Success Criteria:**
   - All requirements have valid framework_key
   - No orphaned hierarchy edges
   - No duplicate requirement IDs

**Exit Criteria:**
- All 4 steps pass
- No schema errors
- Performance targets met
- Code review approved

**If POC fails:** Do NOT proceed to Phase 1 until root cause is fixed.

---

## Conclusion

The proposed regulatory compliance schema is **architecturally sound but incomplete**. The implementation plan correctly identifies the need for hierarchical frameworks but lacks critical operational details around testing, validation, and rollback.

**Key Action Items:**

1. ✅ **Implement Phase 0 migration** using the provided script (Section 5.1)
2. ⚠️ **Add Phase 0.5 POC** to validate approach before full implementation
3. ✅ **Create rollback mechanism** before running migration in production
4. ⚠️ **Revise Track C (ISO/IEC)** to avoid copyright infringement
5. ✅ **Add missing indexes** for performance optimization
6. ✅ **Write integration tests** to catch regressions

**Confidence Level:**
- Schema design: ✅ **HIGH** (well-structured, scalable)
- Implementation plan: ⚠️ **MEDIUM** (needs testing/validation gaps filled)
- Three-track methodology: ⚠️ **MEDIUM-HIGH** (Track A/B solid, Track C needs legal review)
- Migration safety: ✅ **HIGH** (with rollback mechanism)

**Recommended Next Step:** Execute Phase 0 migration in development environment, then run POC with NIST SSDF before committing to full 12-week roadmap.

---

**Document Version:** 1.0
**Author:** Software Architecture Analysis
**Review Status:** Pending stakeholder feedback
