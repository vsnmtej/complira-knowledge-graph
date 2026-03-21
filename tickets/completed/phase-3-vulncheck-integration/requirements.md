# Phase 3: VulnCheck Integration - Requirements

**Ticket:** phase-3-vulncheck-integration
**Status:** Design-ready v2 (Updated: Canaries INCLUDED pending verification)
**Date:** 2026-03-03
**Last Updated:** 2026-03-03 (Investigation complete, all open questions resolved, canaries re-added)
**Target Audience:** Medical device manufacturers (FDA 524B), automotive (CRA), ICS/OT

---

## ⚠️ IMPORTANT: Canary Intelligence Assumption

**Canary observations are INCLUDED in Phase 3A scope**, pending verification when VulnCheck API token is available.

**Assumption:** `/v3/index/canaries` endpoint is available in VulnCheck Community tier (free)

**Verification Required:**
- Test canaries endpoint during Stage 6 (Implementation) when API token available
- If 403 Forbidden → Remove `canary_observations` collection, `observed_by_canary` edge, `VulnCheckCanariesAgent`
- If 200 OK → Full canary intelligence included ✅

**Why this matters:**
- Canary observations are **highest-confidence exploitation data** (first-party VulnCheck network)
- Critical for FDA/CRA regulatory submissions (authoritative exploitation evidence)
- Differentiator vs CISA KEV (VulnCheck canaries provide novel exploitation discovery)

---

## Business Context

### Problem Statement

Medical device and automotive manufacturers face a **critical false positive problem** with embedded/Yocto-based systems:

**Current State (Without VulnCheck):**
- NVD-only CVE data lacks exploit intelligence (no exploit maturity, no threat actor attribution)
- No visibility into active exploitation (ransomware, botnets, threat actors)
- No CISA SSVC automation (exploitation status, automatability, technical impact)
- Customers cannot prioritize which CVEs pose actual risk vs theoretical exposure

**Gap: VulnCheck Exploit Intelligence (Layer 2)**
- VulnCheck tracks 14,400+ exploits for 10,480+ unique CVEs
- VulnCheck KEV: 3,700+ actively exploited CVEs (vs CISA's 1,529)
- 28-day average lead time over CISA KEV
- Ransomware attribution: Which CVEs are exploited by LockBit, BlackCat, etc.
- Botnet attribution: Which CVEs are exploited by Mirai, Emotet, etc.
- Canary network: First-party exploitation evidence (highest confidence)
- Exploit maturity: POC vs weaponized vs actively exploited

**Critical Embedded/Yocto Gap (Layers 1, 3, 4 - Complira Differentiator):**
- **Layer 1:** SBOM extraction from Yocto builds, firmware binaries, RTOS systems
- **Layer 3:** False positive elimination via Yocto patch awareness, kernel config filtering, binary reachability analysis
- **Layer 4:** Regulatory intelligence - which actively exploited CVEs trigger FDA 524B §5.2.4, CRA Article 11, ISO 27001 A.12.6.1

**Typical Yocto False Positive Scenario:**
- NVD/VulnCheck reports 500+ CVE matches for a Yocto image
- 300+ are patched via backported `.bbappend` patches (no version bump)
- 100+ affect kernel subsystems excluded by `CONFIG_*` settings
- 50+ affect unreachable code paths
- **Actual relevant CVEs: 30-50**

**This gap is where Complira provides massive value for CRA-facing embedded manufacturers.**

---

## Scope

### Phase 3A: VulnCheck Data Ingestion (This Ticket)

**Primary Goal:** Integrate VulnCheck exploit intelligence (Layer 2) into Complira knowledge graph

**Deliverables:**
1. **6 new document collections** (VulnCheck-specific intelligence, Community tier)
   - `ransomware_families` - Ransomware groups with CVE attribution
   - `botnets` - Botnet campaigns with CVE attribution
   - `exploit_intelligence` - VulnCheck's core exploit maturity + timeline data per CVE
   - `canary_observations` - First-party exploitation evidence from VulnCheck canary network (pending verification)
   - `exploit_chains` - Multi-CVE attack chains for threat modeling
   - `eol_products` - End-of-life data for OS/software (FDA unsupported software documentation)

2. **10 new edge collections** (connecting VulnCheck data to existing graph)
   - `has_exploit_intelligence` - vulnerabilities → exploit_intelligence
   - `exploited_by_ransomware` - vulnerabilities → ransomware_families
   - `exploited_by_botnet` - vulnerabilities → botnets
   - `exploited_by_threat_actor` - vulnerabilities → threat_groups
   - `observed_by_canary` - vulnerabilities → canary_observations (pending verification)
   - `chain_includes_vuln` - exploit_chains → vulnerabilities
   - `component_eol_status` - components → eol_products
   - `ransomware_uses_technique` - ransomware_families → attack_techniques
   - `botnet_uses_technique` - botnets → attack_techniques
   - `vuln_triggers_requirement` - vulnerabilities → regulatory_requirements (COMPLIRA DIFFERENTIATOR)

3. **Enrichment to existing collections**
   - `vulnerabilities` - Add VulnCheck SSVC, CPE, temporal CVSS, CAPEC/ATT&CK mappings, categories
   - `vulncheck_kev_entries` - Populate from VulnCheck KEV (currently 0 docs, expect 3,700+)
   - `threat_groups` - Enrich with VulnCheck CVE attribution
   - `exploit_modules` - Enrich with VulnCheck maturity classification
   - `cpe_entries` - Add VulnCheck-generated CPEs (76.95% coverage vs NVD's 41.35%)

4. **Data ingestion agents**
   - VulnCheck NVD2 agent (daily sync)
   - VulnCheck KEV agent (daily sync)
   - VulnCheck Exploits agent (on-demand per CVE)
   - VulnCheck Ransomware agent (daily sync)
   - VulnCheck Botnets agent (daily sync)
   - VulnCheck Threat Actors agent (daily sync)
   - VulnCheck Exploit Chains agent (daily sync)
   - VulnCheck EOL agent (daily sync)
   - VulnCheck Canaries agent (daily sync, pending verification)

5. **API endpoints (Phase 2 integration)**
   - Extend POST /v1/enrich to include VulnCheck exploit intelligence
   - Add exploit maturity, ransomware/botnet attribution, canary observations (pending verification), exploit chains to enriched findings
   - Add `vuln_triggers_requirement` edges for regulatory impact

### Phase 3B: Embedded/Yocto False Positive Elimination (Future Ticket)

**Out of scope for this ticket, but critical for Complira differentiation:**

1. **Layer 1: SBOM Extraction** (future)
   - Yocto `cve-check` integration
   - EMBA/Binwalk firmware analysis
   - RTOS component extraction

2. **Layer 3: False Positive Elimination** (future)
   - Yocto patch awareness (`.bbappend` backports)
   - Kernel config filtering (`CONFIG_*` exclusions)
   - Binary reachability analysis (unreachable code paths)

3. **Layer 4: Regulatory Intelligence** (partially in scope)
   - `vuln_triggers_requirement` edge creation (THIS TICKET)
   - FDA 524B impact assessment (future)
   - CRA Article 11 notification obligations (future)
   - VEX statements with evidence chains (future)

---

## Acceptance Criteria

### AC-001: VulnCheck Collections Created ✅

**Requirement:**
- All 6 new document collections created in ArangoDB (Community tier)
- All 10 new edge collections created
- Indexes created for query performance
- Collections registered in named graph definition

**Verification:**
```python
# Document collections (6)
db.collection("ransomware_families").count() >= 0
db.collection("botnets").count() >= 0
db.collection("exploit_intelligence").count() >= 0
db.collection("canary_observations").count() >= 0  # Pending verification
db.collection("exploit_chains").count() >= 0
db.collection("eol_products").count() >= 0

# Edge collections (10)
db.collection("has_exploit_intelligence").count() >= 0
db.collection("exploited_by_ransomware").count() >= 0
db.collection("exploited_by_botnet").count() >= 0
db.collection("exploited_by_threat_actor").count() >= 0
db.collection("observed_by_canary").count() >= 0  # Pending verification
db.collection("chain_includes_vuln").count() >= 0
db.collection("component_eol_status").count() >= 0
db.collection("ransomware_uses_technique").count() >= 0
db.collection("botnet_uses_technique").count() >= 0
db.collection("vuln_triggers_requirement").count() >= 0
```

**Exit Criteria:**
- Schema creation script executes without errors
- All indexes created successfully
- Graph definition updated
- **Note:** If canary endpoints are NOT available in Community tier (discovered during Stage 6), remove canary_observations collection and observed_by_canary edge

---

### AC-002: VulnCheck Data Ingestion Agents Implemented ✅

**Requirement:**
- 9 data ingestion agents implemented following Phase 1/2 patterns (Community tier)
- Agents handle VulnCheck API authentication (Bearer token)
- Agents respect rate limits (1,000 req/min community tier)
- Agents support daily bulk sync
- Agents create documents + edges atomically

**Agents:**
1. `VulnCheckNVD2Agent` - Sync `/v3/backup/vulncheck-nvd2` (daily)
2. `VulnCheckKEVAgent` - Sync `/v3/backup/vulncheck-kev` (daily)
3. `VulnCheckExploitsAgent` - Query `/v3/index/exploits?cve={cve_id}` (on-demand)
4. `VulnCheckRansomwareAgent` - Sync `/v3/backup/ransomware` (daily)
5. `VulnCheckBotnetsAgent` - Sync `/v3/backup/botnets` (daily)
6. `VulnCheckThreatActorsAgent` - Sync `/v3/backup/threat-actors` (daily)
7. `VulnCheckExploitChainsAgent` - Sync `/v3/backup/exploit-chains` (daily)
8. `VulnCheckEOLAgent` - Sync `/v3/backup/eol` (daily)
9. `VulnCheckCanariesAgent` - Sync `/v3/index/canaries` (daily, pending verification)

**Verification:**
```bash
# Initial bulk sync
complira seed --sources vulncheck-kev,vulncheck-nvd2,ransomware,botnets,threat-actors,exploit-chains,eol,canaries

# Daily sync (cron job)
complira incremental --sources vulncheck

# On-demand CVE enrichment
complira enrich-cve CVE-2024-4577
```

**Exit Criteria:**
- All 9 agents execute without errors
- Data populates collections correctly
- Edges created with proper `_from`/`_to` references
- Rate limiting respected (no 429 errors)
- **Note:** If canaries endpoint returns 403 Forbidden during testing, disable VulnCheckCanariesAgent

---

### AC-003: VulnCheck KEV Population ✅

**Requirement:**
- `vulncheck_kev_entries` collection populated (currently 0 docs)
- Expected: 3,700+ VulnCheck KEV entries
- Each entry includes exploitation evidence citations
- `in_cisa_kev` flag distinguishes CISA vs VulnCheck-only KEV
- `vulncheck_first` flag tracks VulnCheck's lead time over CISA

**Verification:**
```aql
// Count VulnCheck KEV entries
LET vc_kev_count = LENGTH(FOR k IN vulncheck_kev_entries RETURN 1)

// Count VulnCheck-first discoveries (ahead of CISA)
LET vc_first_count = LENGTH(
    FOR k IN vulncheck_kev_entries
        FILTER k.vulncheck_first == true
        RETURN 1
)

// Average lead time
LET avg_lead_time = AVERAGE(
    FOR k IN vulncheck_kev_entries
        FILTER k.lead_time_days > 0
        RETURN k.lead_time_days
)

RETURN {
    vulncheck_kev_entries: vc_kev_count,
    vulncheck_first_discoveries: vc_first_count,
    average_lead_time_days: avg_lead_time
}

// Expected result:
// {
//   vulncheck_kev_entries: 3700+,
//   vulncheck_first_discoveries: ~2200,
//   average_lead_time_days: 28
// }
```

**Exit Criteria:**
- `vulncheck_kev_entries` count >= 3,700
- All entries have `exploitation_evidence` array populated
- `in_cisa_kev` and `vulncheck_first` flags accurate

---

### AC-004: Exploit Intelligence Per CVE ✅

**Requirement:**
- `exploit_intelligence` collection stores VulnCheck's core product per CVE
- Boolean flags: `public_exploit_found`, `weaponized_exploit_found`, `reported_exploited`, etc.
- Timeline: `nvd_published`, `first_exploit_published`, `first_reported_ransomware`, etc.
- Exploit maturity: `max_exploit_maturity` (unreported, poc, weaponized, actively-exploited)
- Individual exploit references with maturity classification

**Verification:**
```aql
// Get full exploit intelligence for CVE-2024-4577
FOR vuln IN vulnerabilities
    FILTER vuln.cve_id == "CVE-2024-4577"
    FOR intel IN 1..1 OUTBOUND vuln has_exploit_intelligence
        RETURN {
            cve: vuln.cve_id,
            cvss: vuln.cvss_v3_score,
            exploit_intelligence: {
                max_maturity: intel.max_exploit_maturity,
                reported_exploited: intel.reported_exploited,
                weaponized: intel.weaponized_exploit_found,
                ransomware: intel.reported_exploited_by_ransomware,
                botnets: intel.reported_exploited_by_botnets,
                threat_actors: intel.reported_exploited_by_threat_actors,
                in_cisa_kev: intel.in_cisa_kev,
                in_vulncheck_kev: intel.in_vulncheck_kev,
                timeline: intel.timeline,
                exploits: intel.exploits
            }
        }
```

**Exit Criteria:**
- `exploit_intelligence` collection populated for VulnCheck-enriched CVEs
- All boolean flags accurate
- Timeline data populated
- `has_exploit_intelligence` edges created

---

### AC-005: Ransomware and Botnet Attribution ✅

**Requirement:**
- `ransomware_families` collection populated from `/v3/backup/ransomware`
- `botnets` collection populated from `/v3/backup/botnets`
- `exploited_by_ransomware` edges link CVEs to ransomware families
- `exploited_by_botnet` edges link CVEs to botnets
- Evidence citations included (URLs, dates)

**Verification:**
```aql
// Which CVEs are exploited by ransomware?
FOR vuln IN vulnerabilities
    FOR rw IN 1..1 OUTBOUND vuln exploited_by_ransomware
        COLLECT ransomware = rw.family_name WITH COUNT INTO cve_count
        SORT cve_count DESC
        LIMIT 10
        RETURN {ransomware: ransomware, cve_count: cve_count}

// Example: LockBit 3.0 exploits CVE-2023-41266, CVE-2023-48365, ...

// Which CVEs are exploited by botnets?
FOR vuln IN vulnerabilities
    FOR bn IN 1..1 OUTBOUND vuln exploited_by_botnet
        COLLECT botnet = bn.botnet_name WITH COUNT INTO cve_count
        SORT cve_count DESC
        LIMIT 10
        RETURN {botnet: botnet, cve_count: cve_count}

// Example: Mirai exploits CVE-2016-10401, CVE-2017-17215, ...
```

**Exit Criteria:**
- `ransomware_families` count >= 50
- `botnets` count >= 30
- `exploited_by_ransomware` edges created with evidence
- `exploited_by_botnet` edges created with evidence

---

### AC-006: Exploit Chains for Threat Modeling ✅

**Requirement:**
- `exploit_chains` collection populated from `/v3/backup/exploit-chains`
- `chain_includes_vuln` edges link chains to constituent CVEs
- Chain position and role tracked (initial_access, privilege_escalation, lateral_movement, impact)

**Verification:**
```aql
// Find multi-CVE exploit chains
FOR chain IN exploit_chains
    LET cves = (
        FOR vuln IN 1..1 OUTBOUND chain chain_includes_vuln
            SORT vuln.chain_position ASC
            RETURN {
                cve: vuln.cve_id,
                position: vuln.chain_position,
                role: vuln.role
            }
    )
    FILTER LENGTH(cves) >= 2
    RETURN {
        chain_name: chain.chain_name,
        description: chain.description,
        cve_sequence: cves
    }

// Example: ProxyShell chain
// {
//   chain_name: "ProxyShell",
//   description: "Microsoft Exchange RCE chain",
//   cve_sequence: [
//     {cve: "CVE-2021-34473", position: 1, role: "initial_access"},
//     {cve: "CVE-2021-34523", position: 2, role: "privilege_escalation"},
//     {cve: "CVE-2021-31207", position: 3, role: "impact"}
//   ]
// }
```

**Exit Criteria:**
- `exploit_chains` count >= 20
- `chain_includes_vuln` edges track position and role
- Multi-CVE chains queryable

---

### AC-007: Extended Enrichment Endpoint ✅

**Requirement:**
- POST /v1/enrich endpoint (from Phase 2) extended to include VulnCheck intelligence
- `EnrichedFinding` model updated to include exploit intelligence fields
- Response includes:
  - Exploit maturity (`max_exploit_maturity`)
  - Ransomware attribution (family names, evidence)
  - Botnet attribution (botnet names, evidence)
  - Canary observations (if available, pending verification)
  - Exploit chains (if CVE is part of multi-step chain)
  - Regulatory impact (`vuln_triggers_requirement` edges)

**Request:**
```json
POST /v1/enrich
{
  "scan_session_id": "scan_sess_123",
  "include_threat_intel": true,
  "include_kev": true,
  "include_epss": true,
  "include_vulncheck_intelligence": true  // NEW
}
```

**Response (extended `EnrichedFinding`):**
```json
{
  "scan_session_id": "scan_sess_123",
  "total_findings": 100,
  "enriched_findings": [
    {
      "finding": {...},
      "cve_details": {...},
      "epss_score": {...},
      "kev_entry": {...},
      "threat_intelligence": {...},

      // NEW: VulnCheck exploit intelligence
      "exploit_intelligence": {
        "max_exploit_maturity": "weaponized",
        "reported_exploited": true,
        "weaponized_exploit_found": true,
        "reported_exploited_by_ransomware": true,
        "reported_exploited_by_botnets": false,
        "in_vulncheck_kev": true,
        "timeline": {
          "nvd_published": "2024-06-01",
          "first_exploit_published": "2024-06-08",
          "first_reported_ransomware": "2024-06-15"
        },
        "exploits": [
          {"url": "https://github.com/...", "maturity": "weaponized", "date_added": "2024-06-08"}
        ]
      },

      // NEW: Ransomware attribution
      "ransomware_families": [
        {"family_name": "LockBit 3.0", "first_reported": "2024-06-15", "evidence_url": "..."}
      ],

      // NEW: Botnet attribution
      "botnets": [],

      // NEW: Canary observations (pending verification)
      "canary_observations": [
        {
          "observation_date": "2024-06-16T14:23:00Z",
          "source_countries": ["CN", "RU"],
          "is_novel": true,
          "siftrank_score": 9.8
        }
      ],

      // NEW: Exploit chains
      "exploit_chains": [],

      // NEW: Regulatory impact
      "regulatory_impact": [
        {
          "framework": "FDA 524B",
          "requirement": "§5.2.4",
          "trigger_condition": "actively_exploited",
          "urgency": "24h",
          "required_actions": ["update_vex", "notify_authority"]
        },
        {
          "framework": "CRA",
          "requirement": "Article 11",
          "trigger_condition": "ransomware",
          "urgency": "24h",
          "required_actions": ["incident_notification"]
        }
      ]
    }
  ],
  "enrichment_metadata": {
    "cve_enrichment_coverage": 85.0,
    "epss_coverage": 80.0,
    "kev_coverage": 25.0,
    "threat_intel_coverage": 90.0,
    "vulncheck_exploit_intelligence_coverage": 75.0,  // NEW
    "ransomware_attribution_coverage": 15.0,  // NEW
    "botnet_attribution_coverage": 8.0,  // NEW
    "canary_observation_coverage": 2.0  // NEW (pending verification)
  }
}
```

**Exit Criteria:**
- POST /v1/enrich returns VulnCheck intelligence fields
- `EnrichedFinding` model includes exploit intelligence, ransomware, botnets, canary observations (pending verification), chains, regulatory impact
- Enrichment metadata tracks VulnCheck coverage percentages
- **Note:** If canaries unavailable in Community tier, omit canary_observations field from response

---

### AC-008: Regulatory Obligation Triggering ✅

**Requirement:**
- `vuln_triggers_requirement` edge collection created
- Automated edge creation when VulnCheck intelligence meets regulatory trigger conditions
- Trigger conditions:
  - `actively_exploited` → FDA 524B §5.2.4, CRA Article 11, ISO 27001 A.12.6.1
  - `ransomware` → FDA 524B §5.2.4, CRA Article 11
  - `canary_observed` → FDA 524B §5.2.4, CRA Article 11 (highest priority)
  - `zero_day` → FDA 524B §5.2.4, CRA Article 11 (immediate notification)

**Verification:**
```aql
// Which regulatory requirements are triggered by current threats?
FOR vuln IN vulnerabilities
    FOR intel IN 1..1 OUTBOUND vuln has_exploit_intelligence
        FILTER intel.reported_exploited == true OR intel.reported_exploited_by_ransomware == true
        FOR req IN 1..1 OUTBOUND vuln vuln_triggers_requirement
            COLLECT framework = req.framework, requirement = req.requirement_id
                WITH COUNT INTO trigger_count
            SORT trigger_count DESC
            RETURN {
                framework: framework,
                requirement: requirement,
                active_cve_count: trigger_count,
                urgency: FIRST(
                    FOR e IN vuln_triggers_requirement
                        FILTER e._to == req._id
                        RETURN e.urgency
                )
            }

// Example result:
// [
//   {framework: "FDA 524B", requirement: "§5.2.4", active_cve_count: 45, urgency: "24h"},
//   {framework: "CRA", requirement: "Article 11", active_cve_count: 45, urgency: "24h"},
//   {framework: "ISO 27001", requirement: "A.12.6.1", active_cve_count: 45, urgency: "immediate"}
// ]
```

**Exit Criteria:**
- `vuln_triggers_requirement` edges created for actively exploited CVEs
- Trigger conditions accurate (actively_exploited, ransomware, canary_observed, zero_day)
- Urgency classification correct (immediate, 24h, 72h, 30d, next_review)
- Evidence chain populated (source, evidence_type, timestamp, url)

---

## Open Questions

### Q1: VulnCheck API Tier Selection ✅ RESOLVED

**Question:** Which VulnCheck API tier do we target for MVP?

**Decision:** Community Tier (free)
- 1,000 req/min rate limit
- Backup endpoints only
- **Canary intelligence INCLUDED** (pending verification when API token available)

**Rationale:** Start with Community tier for MVP, validate VulnCheck value before upgrading

**Impact:**
- `canary_observations` collection and `observed_by_canary` edge INCLUDED (assumption: available in Community tier)
- **Verification required:** Test `/v3/index/canaries` endpoint when API token available
- If canaries are NOT available in Community tier, remove collection/edge/agent in Stage 6
- All other features (KEV, exploits, ransomware, botnets, exploit chains, EOL) confirmed available in Community tier

---

### Q2: Sync Frequency and Performance ✅ RESOLVED

**Question:** What sync frequency do we target for each VulnCheck index?

**Decision:** Daily bulk sync only (simplify for MVP)

**Sync Schedule:**
- **Daily bulk sync (02:00 UTC):**
  - `/v3/backup/vulncheck-kev`
  - `/v3/backup/vulncheck-nvd2`
  - `/v3/backup/ransomware`
  - `/v3/backup/botnets`
  - `/v3/backup/threat-actors`
  - `/v3/backup/exploit-chains`
  - `/v3/backup/eol`

- **On-demand (triggered per SBOM scan):**
  - `/v3/purl?purl={purl}`
  - `/v3/cpe?cpe={cpe}`
  - `/v3/index/exploits?cve={cve_id}`

**Excluded from MVP:**
- ❌ Hourly incremental sync (add in future phase if needed)
- ❌ Weekly bulk sync (daily is sufficient)

**Acceptable Latency:**
- VulnCheck publishes exploit → visible in Complira within 24 hours (daily sync)
- On-demand enrichment: <500ms per CVE

---

### Q3: VulnCheck CPE Coverage Integration ✅ RESOLVED

**Question:** VulnCheck provides 76.95% CPE coverage vs NVD's 41.35%. How do we handle CPE conflicts?

**Decision:** VulnCheck-preferred strategy

**Implementation:**
- Use VulnCheck `vcVulnerableCPEs` when available (76.95% coverage)
- Fallback to NVD CPEs when VulnCheck has no CPE data
- Store source attribution (`cpe_source: 'nvd' | 'vulncheck'`) in `vulnerabilities` collection

**Rationale:**
- VulnCheck CPEs are more granular and accurate (76.95% vs 41.35% coverage)
- Reduces false negatives (missing CVE matches) vs NVD-only
- Acceptable trade-off: Potential gaps for 23% of CVEs without VulnCheck CPE data (use NVD fallback)

**Schema Impact:**
```python
# vulnerabilities collection
{
  "cve_id": "CVE-2024-1234",
  "vulnerable_cpes": [...],  # Existing NVD CPEs
  "vc_vulnerable_cpes": [...],  # NEW: VulnCheck CPEs (preferred)
  "cpe_source": "vulncheck",  # NEW: 'nvd' | 'vulncheck'
}
```

---

### Q4: False Positive Elimination Scope Boundary ✅ RESOLVED

**Question:** How much of Layer 3 (false positive elimination) do we include in Phase 3A?

**Decision:** Separate Phase 3B ticket for false positive elimination (NOT Yocto-specific)

**Phase 3A (This Ticket) - VulnCheck Data Ingestion:**
- ✅ VulnCheck collections and edges
- ✅ VulnCheck data ingestion agents
- ✅ Extended POST /v1/enrich with VulnCheck intelligence
- ✅ `vuln_triggers_requirement` edge creation (regulatory impact)

**Phase 3B (Future Ticket) - False Positive Elimination (GENERAL, not Yocto-only):**
- ❌ **Backported patch awareness** (Debian, Ubuntu, RHEL, Alpine, Yocto all backport patches without version bumps)
- ❌ **Kernel config filtering** (`CONFIG_*` exclusions for embedded/server kernels)
- ❌ **Binary reachability analysis** (unreachable code paths in any compiled software)
- ❌ **Unused dependency detection** (package installed but never imported/called)
- ❌ **SBOM metadata integration** (Yocto `cve-check`, SPDX external refs, CycloneDX patch tracking)

**Critical Insight (User Feedback):**
False positive elimination is NOT just for Yocto/embedded. The problem exists for:
1. **Linux distros:** Debian, Ubuntu, RHEL, Alpine all backport CVE fixes without version bumps
2. **Container images:** Distro-based containers (debian:bookworm, alpine:3.19, ubuntu:22.04) have backported patches
3. **Language ecosystems:** npm, pip, maven packages with patch versions (e.g., `1.0.0-patch1` vs `1.0.0`)
4. **Compiled binaries:** Version string mismatches, statically linked libraries, unreachable code

**Typical false positive scenario (applies to ALL ecosystems):**
- NVD/VulnCheck reports: "Package X version 1.0.0 has CVE-2024-1234"
- Reality: Package X 1.0.0 in Debian/Ubuntu/RHEL/Alpine has backported patch (CVE-2024-1234.patch applied)
- SBOM shows: `pkg:deb/debian/package-x@1.0.0-1+deb12u1` (version suffix indicates patched)
- Result: False positive (NVD doesn't know about distro patches)

**Phase 3B will address this generically, not just for Yocto.**

---

### Q5: `vuln_triggers_requirement` Edge Auto-Generation ✅ RESOLVED

**Question:** Do we auto-generate `vuln_triggers_requirement` edges, or require manual review?

**Decision:** Hybrid strategy

**Auto-Generate (High Confidence):**
```python
# Rule 1: Canary observed → Immediate notification (highest confidence)
# Pending verification: Only if canaries available in Community tier
if canary_observations.count > 0:
    create_edge(vuln, fda_524b_5_2_4, trigger="canary_observed", urgency="immediate", auto_generated=True)
    create_edge(vuln, cra_article_11, trigger="canary_observed", urgency="immediate", auto_generated=True)
    create_edge(vuln, iso_27001_a_12_6_1, trigger="canary_observed", urgency="immediate", auto_generated=True)

# Rule 2: Actively exploited CVE → FDA 524B §5.2.4, CRA Article 11, ISO 27001 A.12.6.1
if exploit_intelligence.reported_exploited == True:
    create_edge(vuln, fda_524b_5_2_4, trigger="actively_exploited", urgency="24h", auto_generated=True)
    create_edge(vuln, cra_article_11, trigger="actively_exploited", urgency="24h", auto_generated=True)
    create_edge(vuln, iso_27001_a_12_6_1, trigger="actively_exploited", urgency="immediate", auto_generated=True)

# Rule 3: Ransomware CVE → FDA 524B §5.2.4, CRA Article 11 (high priority)
if exploit_intelligence.reported_exploited_by_ransomware == True:
    create_edge(vuln, fda_524b_5_2_4, trigger="ransomware", urgency="24h", auto_generated=True)
    create_edge(vuln, cra_article_11, trigger="ransomware", urgency="24h", auto_generated=True)

# Rule 4: VulnCheck KEV → All regulatory frameworks (KEV is authoritative)
if vulncheck_kev_entry exists:
    create_edge(vuln, fda_524b_5_2_4, trigger="vulncheck_kev", urgency="24h", auto_generated=True)
    create_edge(vuln, cra_article_11, trigger="vulncheck_kev", urgency="24h", auto_generated=True)
    create_edge(vuln, iso_27001_a_12_6_1, trigger="vulncheck_kev", urgency="immediate", auto_generated=True)
```

**Suggest for Review (Lower Confidence):**
```python
# Suggestion 1: Botnet exploitation (lower priority than ransomware)
if exploit_intelligence.reported_exploited_by_botnets == True:
    suggest_edge(vuln, cra_article_11, trigger="botnet", urgency="72h", auto_generated=False)

# Suggestion 2: Weaponized exploit (but not confirmed exploitation)
if exploit_intelligence.max_exploit_maturity == "weaponized" and exploit_intelligence.reported_exploited == False:
    suggest_edge(vuln, iso_27001_a_12_6_1, trigger="weaponized_exploit", urgency="30d", auto_generated=False)

# Suggestion 3: POC exploit (informational only)
if exploit_intelligence.max_exploit_maturity == "poc":
    suggest_edge(vuln, iso_27001_a_12_6_1, trigger="poc_available", urgency="next_review", auto_generated=False)
```

**Rationale:**
- Auto-generate for high-confidence triggers (actively exploited, ransomware, KEV) → compliance obligations are clear
- Suggest for lower-confidence triggers (botnets, weaponized, POC) → user decides if relevant to their threat model
- All edges have `auto_generated` flag for auditability

**Implementation:**
- `vuln_triggers_requirement` edge schema includes `auto_generated: bool`
- Auto-generated edges created during VulnCheck sync
- Suggested edges stored in separate `suggested_regulatory_triggers` collection (user can promote to edges)
- **Note:** Canary observation rule (Rule 1) pending verification of canaries availability in Community tier

---

## Non-Functional Requirements

### Performance

**NFR-001: VulnCheck API Rate Limiting**
- Must respect VulnCheck rate limits (1,000 req/min for Community tier)
- Implement exponential backoff for 429 responses
- Queue on-demand enrichment requests to avoid rate limit exhaustion

**NFR-002: Bulk Sync Performance**
- Daily bulk sync (vulncheck-kev, ransomware, botnets, etc.) completes within 30 minutes
- Incremental sync (vulncheck-nvd2 delta) completes within 5 minutes
- On-demand CVE enrichment (POST /v1/enrich) adds <500ms latency per CVE

**NFR-003: Graph Query Performance**
- Exploit intelligence queries (e.g., "CVEs exploited by ransomware") execute in <2 seconds
- Regulatory obligation queries (`vuln_triggers_requirement` traversal) execute in <3 seconds
- Full CVE intelligence query (AC-004 example) executes in <1 second

### Security

**NFR-004: VulnCheck API Key Management**
- VulnCheck API token stored in environment variable `VULNCHECK_API_TOKEN`
- Never log API tokens
- Rotate tokens quarterly

**NFR-005: Data Integrity**
- Atomic document + edge creation (transaction-safe)
- Validate VulnCheck API responses against expected schema
- Detect and handle duplicate documents (upsert pattern)

### Maintainability

**NFR-006: Agent Pattern Consistency**
- All VulnCheck agents follow Phase 1/2 agent patterns
- Reuse `BaseAgent`, `BaseRepository`, `BaseService` classes
- Consistent error handling and logging

---

## Dependencies

**Upstream (Required Before Implementation):**
- ✅ Phase 1: Enhanced Scan Ingestion (complete)
- ✅ Phase 2: Enrichment Pipeline (complete)
- ✅ ArangoDB graph schema (20 doc collections, 25 edge collections)
- ✅ Pydantic models for API layer

**External:**
- VulnCheck API account (Community or Professional tier)
- VulnCheck API token (`VULNCHECK_API_TOKEN`)

**Downstream (Enabled By This Phase):**
- Phase 3B: Embedded/Yocto False Positive Elimination
- Phase 4: VEX Statement Generation with VulnCheck Evidence
- Phase 5: Regulatory Submission Automation (FDA 524B, CRA)

---

## Success Metrics

**Data Coverage:**
- `vulncheck_kev_entries` count >= 3,700
- `exploit_intelligence` coverage >= 50% of CVEs in `vulnerabilities` collection
- `ransomware_families` count >= 50
- `botnets` count >= 30
- `exploit_chains` count >= 20

**Enrichment Quality:**
- VulnCheck exploit intelligence coverage >= 75% in POST /v1/enrich responses
- Ransomware attribution coverage >= 15%
- Botnet attribution coverage >= 8%
- Canary observation coverage >= 2% (pending verification)

**Performance:**
- Bulk sync completes within 30 minutes
- On-demand enrichment adds <500ms latency per CVE
- Graph queries execute in <3 seconds

**Regulatory Impact:**
- `vuln_triggers_requirement` edges created for >= 90% of actively exploited CVEs
- Regulatory obligation queries return results in <3 seconds

---

## Risks and Mitigations

**Risk 1: VulnCheck API Rate Limits**
- **Impact:** Bulk sync fails, on-demand enrichment slow
- **Mitigation:** Implement request queuing, exponential backoff, batch requests where possible

**Risk 2: VulnCheck Data Quality**
- **Impact:** False positives in ransomware/botnet attribution, incorrect exploit maturity
- **Mitigation:** Validate VulnCheck data against CISA KEV, manual review for high-impact CVEs

**Risk 3: Schema Evolution**
- **Impact:** VulnCheck API changes break ingestion agents
- **Mitigation:** Version VulnCheck API calls, implement schema validation, monitor VulnCheck changelog

**Risk 4: Embedded/Yocto Expectations**
- **Impact:** Customers expect Layer 3 (false positive elimination) in Phase 3A, disappointed when not included
- **Mitigation:** Clearly communicate Phase 3A vs 3B scope, demonstrate VulnCheck value independently

**Risk 5: Regulatory Edge Auto-Generation Accuracy**
- **Impact:** Incorrect `vuln_triggers_requirement` edges create compliance risk
- **Mitigation:** Human-in-the-loop for high-stakes edges (FDA, CRA), auto-generate for informational edges (ISO)

---

## Phase 3A Timeline Estimate

**Scope:** Large (similar to Phase 2)
- **Collections:** 6 new document collections (including canary_observations pending verification), 10 new edge collections, 5 enrichments to existing collections
- **Agents:** 9 data ingestion agents (including VulnCheckCanariesAgent pending verification)
- **API:** Extend POST /v1/enrich (1 endpoint modification)
- **Tests:** ~30 tests (repository + service + endpoint)

**Estimated Duration:** 12-16 days
- Stage 0-2 (Bootstrap, Investigation, Requirements): 1 day
- Stage 3-5 (Design, Runtime Modeling, Review Gate): 2 days
- Stage 6 (Implementation): 5-7 days (9 agents + schema + enrichment)
- Stage 7-10 (Testing, Code Review, Docs, Handoff): 2-4 days

**Dependencies:** VulnCheck API access (Community or Professional tier)

---

## Future Phases

**Phase 3B: Embedded/Yocto False Positive Elimination**
- Yocto `cve-check` integration
- EMBA/Binwalk firmware analysis
- Yocto patch awareness
- Kernel config filtering
- Binary reachability analysis
- **Estimated Duration:** 14-18 days

**Phase 4: VEX Statement Generation**
- Automated VEX generation with VulnCheck evidence chains
- CycloneDX VEX output
- FDA 524B compliance artifacts
- **Estimated Duration:** 7-10 days

**Phase 5: Regulatory Submission Automation**
- FDA 524B §5.2.4 vulnerability reporting
- CRA Article 11 incident notification
- ISO 27001 A.12.6.1 technical vulnerability management
- **Estimated Duration:** 10-14 days

---

## Appendix: VulnCheck Schema Reference

See `vulncheck_schema.py` for full schema definition including:
- 6 new document collections (ransomware_families, botnets, exploit_intelligence, canary_observations, exploit_chains, eol_products)
- 10 new edge collections (has_exploit_intelligence, exploited_by_ransomware, exploited_by_botnet, etc.)
- Enrichments to existing collections (vulnerabilities, vulncheck_kev_entries, threat_groups, exploit_modules, cpe_entries)
- Example AQL queries (sbom_ransomware_exposure, triggered_regulatory_obligations, cve_full_intelligence, enrichment_coverage)
- Sync configuration (daily bulk, hourly incremental, weekly bulk, on-demand)

---

## Design Decisions (From Investigation)

### D1: VulnCheck KEV vs CISA KEV Reconciliation ✅

**Decision:** Dual tracking (both sources)

**Implementation:**
- `vulncheck_kev_entries` collection stores VulnCheck KEV data (3,700+ entries)
- `kev_entries` collection (existing) stores CISA KEV data (1,529 entries)
- `exploited_in_wild` edge has `source` field: `'cisa_kev' | 'vulncheck_kev'`
- `exploit_intelligence` collection has `in_cisa_kev` and `in_vulncheck_kev` boolean flags
- UI shows both flags + lead time if VulnCheck discovered first

**Rationale:**
- No data loss (union of both KEV catalogs)
- Source attribution for auditability
- Highlight VulnCheck's 28-day average lead time over CISA (competitive differentiator)

---

### D2: Regulatory Edge Auto-Generation Validation ✅

**Decision:** High-confidence auto-generation + suggestions for review

**Implementation:**
- Auto-generate `vuln_triggers_requirement` edges for:
  - Actively exploited CVEs (reported_exploited == True)
  - Ransomware CVEs (reported_exploited_by_ransomware == True)
  - VulnCheck KEV CVEs (in_vulncheck_kev == True)
- Create `suggested_regulatory_triggers` collection for lower-confidence triggers:
  - Botnet exploitation
  - Weaponized exploits (not confirmed exploitation)
  - POC exploits (informational only)
- Add `auto_generated: bool` flag to all `vuln_triggers_requirement` edges

**Rationale:**
- Compliance obligations are clear for actively exploited CVEs (FDA 524B §5.2.4, CRA Article 11)
- User review required for lower-confidence triggers (avoid false compliance obligations)
- Auditability via `auto_generated` flag

---

### D3: VulnCheck Backup Endpoint Streaming ✅

**Decision:** Implement streaming JSON parser for large backup endpoints

**Implementation:**
- Use `ijson` (incremental JSON parser) for `/v3/backup/vulncheck-nvd2` (244,866+ CVEs, estimated 500MB-1GB JSON)
- Process documents in batches of 1,000 (avoid memory exhaustion)
- Show progress indicator during bulk sync

**Rationale:**
- `/v3/backup/vulncheck-nvd2` response too large to load into memory at once
- Streaming parser enables memory-efficient processing
- Batch processing prevents database connection timeouts

---

**Requirements Status:** Design-ready v2 ✅
**Next Stage:** Design Basis (Stage 3)
