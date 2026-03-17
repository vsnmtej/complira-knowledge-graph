# Knowledge Graph Status Report

**Last Updated**: March 5, 2026

---

## Overview

The Complira Knowledge Graph contains **699,824 documents** and **4,035,126 edges** representing cybersecurity vulnerabilities, threats, compliance requirements, and their relationships.

**Recent Updates**:
- ✅ **Phase 4 (March 5, 2026)**: Ingested 20 additional regulatory requirements (12 FDA 524B + 8 EU CRA)

---

## Document Collections (20 total)

### ✅ Fully Populated Collections

| Collection | Count | Source | Status |
|------------|-------|--------|--------|
| **epss_history** | 635,744 | EPSS API | ✅ Working |
| **exploit_modules** | 46,491 | Exploit-DB | ✅ Working |
| **vulnerabilities** | 3,238 | NVD, GHSA, CISA ADP | ✅ Working (802 CISA-enriched) |
| **kev_entries** | 1,529 | CISA KEV Catalog | ✅ Working |
| **package_health** | 7,593 | Package metadata | ✅ Working |
| **oscal_controls** | 1,196 | NIST OSCAL | ✅ Working |
| **weaknesses** | 969 | CWE | ✅ Working |
| **attack_techniques** | 835 | MITRE ATT&CK | ✅ Working |
| **licenses** | 727 | SPDX | ✅ Working |
| **attack_patterns** | 615 | CAPEC | ✅ Working |
| **d3fend_techniques** | 493 | D3FEND | ✅ Working |
| **threat_groups** | 187 | ATT&CK Groups | ✅ Working |
| **atlas_techniques** | 155 | MITRE ATLAS | ✅ Working |
| **regulatory_requirements** | 52 | IEC 62304, FDA 524B, EU CRA | ✅ Working |

**Total Working**: 699,824 documents across 14 collections

**Regulatory Requirements Breakdown**:
- IEC 62304: 27 requirements (medical device software lifecycle)
- FDA Section 524B: 14 requirements (medical device cybersecurity - **Phase 4**)
- EU Cyber Resilience Act (CRA): 11 requirements (Annex I & II - **Phase 4**)
- Ingestion: `python scripts/ingest_regulatory_frameworks.py`

---

### ⚠️ Empty Collections (Expected)

| Collection | Count | Reason | Priority |
|------------|-------|--------|----------|
| **scf_controls** | 0 | Requires manual SCF data download | Priority 2 |
| **vulncheck_kev_entries** | 0 | Replaced by CISA ADP enrichment | N/A (deprecated) |
| **opencre_nodes** | 0 | OpenCRE API deprecated | Known issue |
| **components** | 0 | Requires SBOM ingestion | Future |
| **cpe_entries** | 0 | Optional CPE dictionary | Future |
| **scorecard_results** | 0 | Requires Scorecard integration | Future |

**Details**:

#### scf_controls (0 records)
- **Status**: Placeholder for Secure Controls Framework
- **Why Empty**: Requires manual download from SCF website
- **Priority**: Medium (Priority 2 from previous session)
- **Effort**: Medium (needs SCF agent implementation)
- **Impact**: Compliance mapping enhancements

#### vulncheck_kev_entries (0 records)
- **Status**: ~~Deprecated~~ Replaced by CISA ADP enrichment
- **Why Empty**: We now use CISA ADP data embedded in CVE records (via CISAADPAgent)
- **Action**: ✅ No action needed - KEV data available via `cisa_kev` field in vulnerabilities
- **Query**: `FOR v IN vulnerabilities FILTER v.in_cisa_kev == true RETURN v`

#### opencre_nodes (0 records)
- **Status**: Known issue (API deprecated)
- **Why Empty**: OpenCRE API is no longer functional
- **Documented**: `docs/KNOWN_ISSUES.md`
- **Action**: Monitor for OpenCRE v2 API availability

#### components (0 records)
- **Status**: Future enhancement
- **Why Empty**: Requires SBOM ingestion workflow
- **Use Case**: Map vulnerabilities to actual software components
- **Priority**: Low (not critical for current functionality)

#### cpe_entries (0 records)
- **Status**: Optional enhancement
- **Why Empty**: CPE dictionary not required (NVD provides CPE matches inline)
- **Priority**: Low (optimization, not required)

#### scorecard_results (0 records)
- **Status**: Future enhancement
- **Why Empty**: OpenSSF Scorecard integration not implemented
- **Use Case**: Package health and security posture scoring
- **Priority**: Low

---

## Edge Collections (26 total)

### ✅ Populated Edge Collections

| Edge Type | Count | Description | Status |
|-----------|-------|-------------|--------|
| **has_weakness** | 1,875,317 | CVE → CWE mappings | ✅ Working |
| **aliases** | 1,177,665 | CVE ↔ GHSA aliases | ✅ Working |
| **has_epss** | 953,602 | CVE → EPSS scores | ✅ Working |
| **capec_relates_to_cwe** | 10,926 | CAPEC → CWE mappings | ✅ Working |
| **child_of** | 6,585 | CWE hierarchy | ✅ Working |
| **exploited_in_wild** | 4,587 | CVE → KEV entries | ✅ Working |
| **capec_child_of** | 4,264 | CAPEC hierarchy | ✅ Working |
| **can_precede** | 715 | ATT&CK technique sequences | ✅ Working |
| **peer_of** | 490 | CWE peer relationships | ✅ Working |
| **maps_to_requirement** | 458 | Controls → Requirements | ✅ Working |
| **capec_maps_to_attack** | 272 | CAPEC → ATT&CK | ✅ **FIXED** (was 0) |
| **atlas_maps_to_attack** | 170 | ATLAS → ATT&CK | ✅ Working |
| **requires** | 65 | ATT&CK prerequisites | ✅ Working |
| **has_exploit** | 10 | CVE → Exploit modules | ✅ Working |

**Total Working Edges**: 4,035,126 across 14 edge collections

---

### ⚠️ Empty Edge Collections (Expected)

| Edge Type | Count | Reason | Priority |
|-----------|-------|--------|----------|
| **d3fend_counters_technique** | 0 | Data not in D3FEND ontology | N/A (not a bug) |
| **technique_exploits_weakness** | 0 | LLM-generated (future) | Low |
| **technique_mitigated_by_control** | 0 | LLM-generated (future) | Low |
| **affects** | 0 | Requires CPE matching | Future |
| **matched_by_cpe** | 0 | Requires CPE dictionary | Future |
| **cross_framework_mapping** | 0 | Future enhancement | Low |
| **depends_on** | 0 | Package dependency graph | Future |
| **licensed_under** | 0 | Package license mapping | Future |
| **opencre_links** | 0 | OpenCRE API deprecated | Known issue |
| **same_as** | 0 | Entity deduplication | Future |
| **scored_by** | 0 | Scorecard integration | Future |

**Details**:

#### d3fend_counters_technique (0 edges)
- **Status**: Data unavailable (not a bug)
- **Why Empty**: D3FEND public ontology doesn't include ATT&CK counter mappings
- **Investigated**: Confirmed 0 of 493 techniques have `d3f:counters` fields
- **Documented**: `docs/BUG_FIXES.md`
- **Workaround**: Use indirect paths (D3FEND ← NIST → ATT&CK Mitigations)

#### technique_exploits_weakness (0 edges)
- **Status**: Future LLM enrichment
- **Why Empty**: Requires cross-referencing ATT&CK techniques with CWEs
- **Approach**: LLM agent to infer relationships from descriptions
- **Priority**: Low (can use indirect paths: ATT&CK ← CAPEC → CWE)

#### technique_mitigated_by_control (0 edges)
- **Status**: Future LLM enrichment
- **Why Empty**: Requires mapping ATT&CK techniques to defensive controls
- **Approach**: LLM agent to infer from control descriptions
- **Priority**: Low (can use indirect paths)

#### Other Empty Edges
- Most are **future enhancements** requiring additional data sources or integrations
- Not critical for current functionality
- Can be implemented as needed based on use cases

---

## Recent Improvements (March 2, 2026)

### ✅ Bugs Fixed

1. **capec_maps_to_attack** edges created
   - **Before**: 0 edges
   - **After**: 272 edges ✅
   - **Fix**: Taxonomy name matching bug (was checking `ATT&CK`, should be `ATTACK`)
   - **File**: `src/complira_graph/agents/capec.py`

2. **EPSS schema cleanup**
   - **Before**: Unused `has_epss_history` collection in schema
   - **After**: Removed from schema, `has_epss` working correctly (953,602 edges) ✅
   - **Files**: `src/complira_graph/db.py`, `src/complira_graph/cli.py`

### ✅ Features Added

3. **CISA ADP Enrichment**
   - **New Agent**: `CISAADPAgent`
   - **Data**: SSVC scores, KEV status, enhanced CWEs, CISA CVSS
   - **Status**: 802 vulnerabilities enriched (24.8% of 3,238 total) ✅
   - **KEV Count**: 8 vulnerabilities in CISA KEV catalog
   - **File**: `src/complira_graph/agents/cisa_adp.py`
   - **Command**: `complira incremental CISAADPAgent`

4. **Analysis Agents (Agentic Architecture)**
   - **New Agent**: `CISAReportAgent` - Prioritized patching reports
   - **New Agent**: `VulnerabilityAnalysisAgent` - CISA data exploration
   - **Commands**: `complira report`, `complira analyze`
   - **Formats**: text, JSON, markdown
   - **Files**: `src/complira_graph/agents/analysis/`

---

## CISA Enrichment Statistics

From the 802 CISA-enriched vulnerabilities:

| Category | Count | Percentage |
|----------|-------|------------|
| **Total CISA Enriched** | 802 | 24.8% of all CVEs |
| **KEV Catalog** | 8 | 1.0% (CRITICAL) |
| **Active Exploitation** | 8 | 1.0% |
| **PoC Available** | 401 | 50.0% |
| **Automatable** | 258 | 32.2% |
| **Total Technical Impact** | 231 | 28.8% |
| **CVSS >= 9.0** | 65 | 8.1% |

**Priority Distribution**:
- **High Priority (50-110)**: 8 vulnerabilities (1.0%) - **Immediate action required**
- **Medium Priority (25-49)**: 233 vulnerabilities (29.1%)
- **Low Priority (0-24)**: 561 vulnerabilities (70.0%)

---

## Current Capabilities

### ✅ Vulnerability Intelligence
- **3,238 vulnerabilities** from NVD, GHSA, CISA
- **802 CISA-enriched** with SSVC scores and KEV status
- **953,602 EPSS scores** for exploitation probability
- **46,491 exploit modules** for weaponization tracking
- **1,529 KEV entries** for known exploited vulnerabilities

### ✅ Threat Intelligence
- **835 ATT&CK techniques** for adversary tactics
- **615 CAPEC attack patterns** for attack methodologies
- **187 threat groups** for attribution
- **155 ATLAS techniques** for ML-specific threats

### ✅ Weakness Analysis
- **969 CWE entries** for weakness categorization
- **1,875,317 CVE → CWE mappings** for root cause analysis
- **10,926 CAPEC → CWE mappings** for attack pattern weaknesses

### ✅ Defensive Controls
- **493 D3FEND techniques** for countermeasures
- **1,196 NIST OSCAL controls** for compliance
- **27 regulatory requirements** for governance

### ✅ Reporting & Analysis
- **Prioritized patching reports** (`complira report`)
- **CISA enrichment analysis** (`complira analyze`)
- **Multiple output formats** (text, JSON, markdown)
- **Agentic architecture** for extensibility

---

## Available Commands

### Data Ingestion
```bash
# Full seed (populate entire graph)
complira seed

# Incremental updates
complira incremental CISAADPAgent        # Enrich vulnerabilities with CISA data
complira incremental NVDAgent            # Update vulnerabilities
complira incremental KEVAgent            # Update KEV catalog
complira incremental EPSSAgent           # Update EPSS scores
```

### Analysis & Reporting
```bash
# Generate prioritized patching report
complira report                          # Text format
complira report --format json            # JSON format
complira report --format markdown        # Markdown format

# Analyze CISA enrichment data
complira analyze                         # Text format
complira analyze --format json           # JSON format
complira analyze --format markdown       # Markdown format
```

### Query & Status
```bash
# Check system health
complira status

# Execute custom AQL queries
complira query "FOR v IN vulnerabilities FILTER v.in_cisa_kev == true RETURN v"
```

---

## Recommended Next Steps

### Immediate Actions
1. ✅ **Patch KEV vulnerabilities** - 8 CVEs require immediate action per CISA directive
   - Run `complira report` to see prioritized list
   - Focus on KEV vulnerabilities first (priority score 95-110)

2. ✅ **Weekly CISA enrichment** - Keep vulnerability intelligence up to date
   ```bash
   complira incremental CISAADPAgent
   ```

3. ✅ **Generate reports** - Share with security teams
   ```bash
   complira report --format markdown > weekly_report.md
   ```

### Short-Term (Next 30 Days)
4. **Review automatable + total impact vulnerabilities** - 61 CVEs can be exploited at scale
   - Run `complira analyze` to see dangerous combinations
   - Prioritize by CVSS score and business impact

5. **Monitor PoC-available vulnerabilities** - 401 CVEs have public exploit code
   - Track for signs of weaponization
   - Prioritize if exploitation moves from PoC → active

### Long-Term Enhancements
6. **Implement SCF Agent** (Priority 2)
   - Download SCF data from official source
   - Create `SCFAgent` for Secure Controls Framework
   - Populate `scf_controls` collection

7. **LLM Enrichment Agents** (Future)
   - `TechniqueToWeaknessAgent` - Map ATT&CK → CWE relationships
   - `TechniqueToControlAgent` - Map ATT&CK → defensive controls
   - Populate `technique_exploits_weakness` and `technique_mitigated_by_control` edges

8. **SBOM Integration** (Future)
   - Ingest SBOMs to populate `components` collection
   - Link components to vulnerabilities via `affects` edges
   - Enable software composition analysis

---

## Known Issues

### 1. OpenCRE API Deprecated
- **Collection**: `opencre_nodes` (0 records)
- **Edge**: `opencre_links` (0 edges)
- **Status**: API no longer functional
- **Documented**: `docs/KNOWN_ISSUES.md`
- **Action**: Monitor for OpenCRE v2 API

### 2. D3FEND Mappings Unavailable
- **Edge**: `d3fend_counters_technique` (0 edges)
- **Status**: Data not in public D3FEND ontology
- **Investigated**: Confirmed in `docs/BUG_FIXES.md`
- **Workaround**: Use indirect paths via NIST controls

---

## Documentation

### User Guides
- `README.md` - Project overview and setup
- `docs/ANALYSIS_AGENTS.md` - Analysis agents guide
- `docs/CISA_ADP_AGENT.md` - CISA enrichment implementation

### Session Summaries
- `docs/SESSION_SUMMARY_2026_03_02.md` - Recent bug fixes and features
- `docs/AGENTIC_ARCHITECTURE_SUMMARY.md` - Analysis agent implementation

### Technical Documentation
- `docs/BUG_FIXES.md` - Detailed bug investigation and fixes
- `docs/ZERO_COUNTS_EXPLAINED.md` - Comprehensive zero-count analysis
- `docs/KNOWN_ISSUES.md` - Known limitations and workarounds

---

## Summary

**Working Well** ✅:
- 699,799 documents across 14 collections
- 4,035,126 edges across 14 edge types
- CISA ADP enrichment (802 CVEs with SSVC scores, KEV status)
- Prioritized patching reports (8 KEV vulnerabilities identified)
- Agentic analysis architecture (report and analyze commands)

**Known Gaps** ⚠️:
- SCF controls (requires manual download - Priority 2)
- OpenCRE nodes (API deprecated - known issue)
- LLM-generated edges (future enhancement)
- SBOM components (future enhancement)

**Next Actions** 🎯:
1. Patch 8 KEV vulnerabilities (immediate)
2. Run weekly CISA enrichment (ongoing)
3. Generate patching reports (as needed)
4. Consider implementing SCF agent (Priority 2)

---

**Knowledge Graph Status**: ✅ **Healthy and Operational**

All critical data sources are ingesting correctly, CISA enrichment is working, and analysis capabilities are fully functional.
