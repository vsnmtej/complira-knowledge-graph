# Architectural Gaps - Remediation Plan

**Date:** 2026-03-06
**Status:** Planning Phase
**Priority:** CRITICAL - Core value proposition at risk

---

## Executive Summary

Comprehensive architectural review identified **critical gaps** in the compliance and supply chain layers that undermine Complira's core differentiation. While the vulnerability intelligence layer (CVE → CWE → ATT&CK → D3FEND) is production-ready, the regulatory compliance layer is dangerously sparse.

**Business Impact:**
- 🔴 **Compliance Passport** feature non-functional (missing `violates_requirement` edge)
- 🔴 **Supply chain analysis** layer completely empty (0 components, 0 CPE matches)
- 🔴 **Regulatory coverage** inadequate (52 requirements vs expected 500+)
- 🟠 **OSS vulnerability coverage** incomplete (no OSV.dev/GHSA data)

---

## Gap Analysis Summary

### 🔴 Critical Gaps (Blocks Core Features)

| Gap | Current State | Target State | Business Impact |
|-----|--------------|--------------|-----------------|
| **violates_requirement edge** | Missing | ~50K edges | Compliance Passport non-functional |
| **Regulatory requirements** | 52 docs | 500+ docs | CRA/FDA/IEC coverage incomplete |
| **Supply chain layer** | 0 components | ~1M components | SBOM analysis broken |
| **CPE matching** | 0 edges | ~100K edges | Product-CVE mapping broken |

### 🟠 High Priority Gaps (Limits Differentiation)

| Gap | Impact |
|-----|--------|
| **OSV.dev/GHSA data** | Missing 8M+ OSS vulnerabilities |
| **VEX storage** | Can't prove FDA 524B compliance |
| **ATT&CK edges** | Attack path analysis incomplete |
| **IEC 62443/WP.29** | Industrial/automotive verticals unsupported |

### 🟡 Medium Priority Gaps (Technical Debt)

| Gap | Impact |
|-----|--------|
| **Schema documentation** | Investor/partner confusion |
| **Edge metadata** | Regulatory defensibility at risk |
| **cross_framework_mapping** | Hidden value not exposed via API |

---

## Remediation Roadmap

### Phase 1: Critical Fixes (Week 1-2)

**Goal:** Restore core Compliance Passport functionality

#### 1.1 Implement `violates_requirement` Edge Collection

**Description:** Dual-path compliance architecture requires both:
- Path A: `maps_to_requirement` (what evidence is needed)
- Path B: `violates_requirement` (what is actively breached)

**Implementation:**
```python
# New edge collection
db.create_collection('violates_requirement', edge=True)

# Schema
{
    "_from": "vulnerabilities/CVE_2024_12345",
    "_to": "regulatory_requirements/CRA_AII_1_1",
    "source": "deterministic",  # Rule-based mapping
    "confidence": 1.0,
    "framework": "CRA",
    "severity": "CRITICAL",  # Based on requirement mandatory_by_date
    "rationale": "Exploitable vulnerability in safety-critical component",
    "evidence_required": ["patch_applied", "security_testing"],
    "remediation_deadline": "2026-09-11"  # CRA enforcement date
}
```

**Data Population:**
1. Query all CVEs with CVSS >= 7.0
2. Join with `components` where `safety_class` in ["critical", "high"]
3. Map to applicable regulatory requirements based on:
   - Product category (medical, automotive, industrial)
   - Safety classification
   - Deployment context (internet-facing, safety-critical)

**Estimated Edges:** ~50,000 (15% of CVEs in regulated contexts)

---

#### 1.2 Populate Regulatory Requirements

**Current:** 52 documents
**Target:** 500+ documents

**Data Sources:**

| Framework | Requirements | Priority | ETA |
|-----------|-------------|----------|-----|
| **EU Cyber Resilience Act (CRA)** | ~150 | 🔴 Critical | Week 1 |
| **FDA 524B (Medical)** | ~80 | 🔴 Critical | Week 1 |
| **IEC 62304 (Medical Software)** | ~120 | 🔴 Critical | Week 2 |
| **ISO 21434 (Automotive)** | ~90 | 🟠 High | Week 2 |
| **UNECE WP.29** | ~60 | 🟠 High | Week 3 |
| **IEC 62443 (Industrial)** | ~200 | 🟡 Medium | Week 4 |

**Schema Enhancement:**
```python
# regulatory_requirements collection
{
    "_key": "CRA_AII_1_1",
    "framework_id": "CRA",
    "framework_version": "2024-12",
    "section": "Annex II, Part I, 1.1",
    "title": "Secure by design development process",
    "description": "...",
    "mandatory": true,
    "mandatory_by_date": "2026-09-11",
    "applicable_product_categories": ["medical", "automotive", "industrial"],
    "applicable_safety_classes": ["critical", "high"],
    "evidence_required": [
        {"type": "sbom", "format": "cyclonedx"},
        {"type": "vex", "format": "csaf"},
        {"type": "security_test_report", "standard": "IEC 62443-4-2"}
    ],
    "cvss_threshold": 7.0,  # Auto-trigger for CVEs above this
    "document_hash": "sha256:...",  # Change detection
    "source_url": "https://eur-lex.europa.eu/..."
}
```

**Implementation:**
1. Parse regulatory framework documents (PDF/XML)
2. Extract structured requirements
3. Map requirements to product categories
4. Define evidence schemas
5. Set criticality levels and deadlines

---

#### 1.3 Implement Supply Chain Layer

**Goal:** Enable SBOM ingestion and component-CVE mapping

**New Collections:**

```python
# components collection
{
    "_key": "pkg:npm/lodash@4.17.20",  # PURL format
    "name": "lodash",
    "version": "4.17.20",
    "type": "npm",
    "namespace": null,
    "purl": "pkg:npm/lodash@4.17.20",
    "cpe": "cpe:2.3:a:lodash:lodash:4.17.20:*:*:*:*:node.js:*:*",
    "supplier": "John-David Dalton",
    "license": "MIT",
    "safety_class": "high",  # User-defined via SBOM metadata
    "deployment_context": "backend_api",  # internet-facing
    "source_sbom": "sbom_12345"
}

# depends_on edge collection
{
    "_from": "components/pkg:npm/app@1.0.0",
    "_to": "components/pkg:npm/lodash@4.17.20",
    "relationship": "depends",
    "scope": "runtime",
    "source": "sbom"
}

# matched_by_cpe edge collection
{
    "_from": "components/pkg:npm/lodash@4.17.20",
    "_to": "vulnerabilities/CVE_2021_23337",
    "source": "cpe_match",
    "confidence": 0.95,
    "match_type": "exact_version",
    "cpe_match_string": "cpe:2.3:a:lodash:lodash:4.17.20"
}
```

**Implementation:**
1. Create PURL↔CPE mapping service
2. Implement SBOM parsers (CycloneDX, SPDX)
3. CPE matching engine
4. Component safety classification
5. Dependency graph builder

**Expected Data:**
- ~1M components (from 10K SBOMs x 100 components/SBOM)
- ~100K matched_by_cpe edges (10% of components have known CVEs)
- ~5M depends_on edges (dependency graph)

---

### Phase 2: High Priority Enhancements (Week 3-4)

#### 2.1 Implement OSV.dev and GHSA Agents

**OSV.dev Coverage:** ~8M vulnerability records for OSS packages
**GHSA Coverage:** ~10K GitHub Security Advisories

**New Agents:**
```python
# src/complira_graph/agents/osv.py
class OSVAgent(BaseIngestionAgent):
    """Ingest OSV.dev vulnerability database."""

    def fetch_data(self):
        # OSV API: https://osv.dev/
        # Ecosystems: npm, PyPI, Go, Maven, NuGet, etc.
        pass

# src/complira_graph/agents/ghsa.py
class GHSAAgent(BaseIngestionAgent):
    """Ingest GitHub Security Advisory database."""

    def fetch_data(self):
        # GitHub API: https://api.github.com/advisories
        pass
```

**Benefits:**
- Better PURL→CVE matching (OSV uses PURLs natively)
- Earlier detection (GHSA often faster than NVD)
- Richer ecosystem metadata

---

#### 2.2 Implement VEX Storage & Generation

**Goal:** FDA 524B compliance requires VEX document generation

**New Collections:**
```python
# vex_documents collection
{
    "_key": "vex_product_v1_2024_03",
    "format": "csaf_vex_2.0",
    "product_id": "acme_pacemaker_v2.1",
    "document_version": "1.0",
    "generated_date": "2024-03-06",
    "generator": "complira_graph",
    "vulnerabilities": [
        {
            "cve_id": "CVE-2024-12345",
            "status": "not_affected",
            "justification": "component_not_present",
            "rationale": "Lodash 4.17.20 not used in production build"
        }
    ],
    "csaf_document": {...}  # Full CSAF 2.0 JSON
}
```

**API Endpoint:**
```python
POST /api/v1/vex/generate
{
    "sbom_id": "sbom_12345",
    "product_id": "pacemaker_v2.1",
    "format": "csaf_vex"
}

→ Returns VEX document showing which CVEs apply/don't apply
```

---

#### 2.3 Complete ATT&CK Edge Population

**Missing Edges:**
- `technique_exploits_weakness`: CWE ← ATT&CK (how techniques exploit weaknesses)
- `technique_mitigated_by_control`: ATT&CK → NIST controls (defensive mappings)

**Data Sources:**
- MITRE ATT&CK STIX data (includes CWE mappings)
- D3FEND → ATT&CK mappings (already have 40K)
- NIST 800-53 → ATT&CK mappings (Center for Internet Security)

**Implementation:**
```python
# Enhance ATT&CKAgent to extract:
# 1. technique.x_mitre_attack_spec_version
# 2. technique.x_mitre_data_sources (detection methods)
# 3. technique → CWE mappings from STIX relationships

# Expected edges:
# - technique_exploits_weakness: ~3K edges (835 techniques × avg 4 CWEs)
# - technique_mitigated_by_control: ~8K edges (835 techniques × avg 10 controls)
```

---

### Phase 3: Medium Priority Improvements (Week 5-6)

#### 3.1 Add Edge Metadata Enforcement

**Goal:** Schema-level validation for `source` + `confidence` on all edges

**Implementation:**
```python
# ArangoDB schema validation
db.create_collection('example_edge', edge=True, schema={
    "rule": {
        "properties": {
            "_from": {"type": "string"},
            "_to": {"type": "string"},
            "source": {
                "type": "string",
                "enum": ["deterministic", "probabilistic", "llm", "manual"]
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0
            }
        },
        "required": ["_from", "_to", "source", "confidence"]
    },
    "level": "strict",
    "message": "Edge must have source and confidence"
})
```

**Backfill Existing Edges:**
- Set `source="deterministic"` for all NVD/CWE/CAPEC/ATT&CK edges
- Set `confidence=1.0` for deterministic, `0.8` for heuristic
- Add migration script to update ~3M existing edges

---

#### 3.2 Document cross_framework_mapping

**Current:** 9,147 edges, zero documentation
**Hypothesis:** Maps CRA ↔ FDA ↔ IEC 62304 ↔ NIST 800-53 ↔ ISO 27001

**Action Items:**
1. Query edge samples to understand mappings
2. Document mapping methodology
3. Expose via API endpoint:
   ```python
   GET /api/v1/compliance/framework-mapping?from=CRA_AII_1_1&to=FDA
   → Returns equivalent FDA 524B requirements
   ```

**Business Value:** This is potentially the **highest-value edge collection** for multi-vertical compliance. Example use case:
- Customer complies with FDA 524B
- Wants to sell in EU (needs CRA compliance)
- API shows: "You already have 60% of CRA evidence from your FDA compliance"

---

#### 3.3 Schema Documentation Accuracy

**Issues:**
1. Doc claims 66 collections, live DB has ~45
2. Edge collections misclassified as document collections
3. Count discrepancies (~6.4M vs ~5.5M)

**Fix:**
- Auto-generate schema doc from live DB
- Add schema versioning
- Include last-updated timestamps
- CI/CD validation: fail build if doc and DB diverge

---

## Implementation Priority Matrix

| Priority | Effort | Business Impact | Timeline |
|----------|--------|-----------------|----------|
| 🔴 1.1 violates_requirement | 3 days | Unblocks Compliance Passport | Week 1 |
| 🔴 1.2 Regulatory reqs (CRA/FDA) | 5 days | Essential for positioning | Week 1-2 |
| 🔴 1.3 Supply chain layer | 7 days | Enables SBOM analysis | Week 2-3 |
| 🟠 2.1 OSV/GHSA agents | 4 days | 10x vulnerability coverage | Week 3 |
| 🟠 2.2 VEX storage | 3 days | FDA compliance proof | Week 4 |
| 🟠 2.3 ATT&CK edges | 2 days | Complete attack paths | Week 4 |
| 🟡 3.1 Edge metadata | 3 days | Regulatory defensibility | Week 5 |
| 🟡 3.2 Framework mapping | 2 days | Unlock hidden value | Week 5 |
| 🟡 3.3 Schema docs | 1 day | Reduce confusion | Week 6 |

**Total Effort:** ~30 days (1.5 person-months)
**Critical Path:** 15 days (Week 1-3)

---

## Success Criteria

### Phase 1 Complete (Week 3):
- ✅ `violates_requirement` collection has >10K edges
- ✅ `regulatory_requirements` has >400 documents (CRA, FDA, IEC 62304, ISO 21434)
- ✅ `components` collection has >1K components (from test SBOMs)
- ✅ `matched_by_cpe` has >500 edges
- ✅ Compliance Passport API endpoint functional

### Phase 2 Complete (Week 5):
- ✅ OSV/GHSA agents ingested
- ✅ VEX generation API working
- ✅ `technique_exploits_weakness` has >2K edges
- ✅ `technique_mitigated_by_control` has >5K edges

### Phase 3 Complete (Week 6):
- ✅ All edges have `source` + `confidence`
- ✅ `cross_framework_mapping` documented and exposed via API
- ✅ Schema doc auto-generated from live DB
- ✅ CI/CD validation in place

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| **Regulatory data quality** | Partner with legal/compliance experts for CRA/FDA mapping |
| **CPE matching accuracy** | Implement confidence scoring + manual review workflow |
| **Schema migration complexity** | Use ArangoDB versioning + rollback procedures |
| **Performance degradation** | Add indexes before bulk edge creation |
| **Data licensing** | Verify OSV/GHSA terms for commercial use |

---

## Next Steps

1. **Immediate (Today):**
   - Review this plan with stakeholders
   - Prioritize Phase 1 tasks
   - Assign owners

2. **Week 1:**
   - Implement `violates_requirement` edge
   - Start CRA/FDA requirement ingestion

3. **Weekly:**
   - Review progress against timeline
   - Adjust priorities based on customer feedback

---

**Owner:** Engineering Lead
**Reviewers:** Product, Legal/Compliance, Architecture
**Status:** ⏳ Awaiting Approval
