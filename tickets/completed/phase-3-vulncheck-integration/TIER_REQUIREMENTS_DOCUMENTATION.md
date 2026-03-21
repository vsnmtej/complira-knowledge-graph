# VulnCheck API Tier Requirements

**Date:** 2026-03-05
**Stage:** 7 (API/E2E Testing)
**Solution:** Document tier requirements, keep all agents (disabled for Community tier)

---

## Overview

Phase 3A VulnCheck Integration implemented 9 agents, but manual integration testing revealed that **8 of 9 agents require a paid VulnCheck subscription**. Rather than removing this code, we document the tier requirements and keep all agents ready for future use.

**This approach:**
- ✅ Keeps all professionally designed and tested code
- ✅ No re-entry or code removal needed
- ✅ Clear documentation of tier requirements
- ✅ Agents gracefully handle 402 errors
- ✅ Ready if user upgrades to paid tier
- ✅ Stage 7 can complete and transition to Stage 8

---

## Agent Tier Matrix

| # | Agent | Endpoint | Community Tier | Paid Tier | Status |
|---|-------|----------|----------------|-----------|--------|
| 1 | **VulnCheckKEVAgent** | `/v3/backup/vulncheck-kev` | ✅ **Available** | ✅ Available | **FUNCTIONAL** |
| 2 | VulnCheckNVD2Agent | `/v3/backup/vulncheck-nvd2` | ❌ 402 | ✅ Available | Disabled (requires paid) |
| 3 | VulnCheckExploitsAgent | `/v3/index/exploits` | ❌ 402 | ✅ Available | Disabled (requires paid) |
| 4 | VulnCheckRansomwareAgent | `/v3/backup/ransomware` | ❌ 402 | ✅ Available | Disabled (requires paid) |
| 5 | VulnCheckBotnetsAgent | `/v3/backup/botnets` | ❌ 402 | ✅ Available | Disabled (requires paid) |
| 6 | VulnCheckThreatActorsAgent | `/v3/backup/threat-actors` | ❌ 402 | ✅ Available | Disabled (requires paid) |
| 7 | VulnCheckExploitChainsAgent | `/v3/backup/exploit-chains` | ❌ 402 | ✅ Available | Disabled (requires paid) |
| 8 | VulnCheckEOLAgent | `/v3/backup/eol` | ❌ 402 | ✅ Available | Disabled (requires paid) |
| 9 | VulnCheckCanariesAgent | `/v3/index/canaries` | ❌ 402 | ✅ Available | Removed (Stage 7 re-entry T-008) |

**Community Tier:** 1/9 agents functional (11%)
**Paid Tier:** 8/9 agents functional (89%)

---

## Subscription Requirements

### VulnCheck Community Tier (FREE)

**Included Endpoints:**
- ✅ `/v3/backup/vulncheck-kev` - CISA KEV catalog with lead time analysis

**Not Included:**
- ❌ All other `/v3/backup` endpoints (requires "Exploit & Vulnerability Intelligence" subscription)
- ❌ All `/v3/index` endpoints (requires "Exploit & Vulnerability Intelligence" subscription)

### VulnCheck Exploit & Vulnerability Intelligence (PAID)

**Included Endpoints:**
- ✅ All Community tier endpoints
- ✅ `/v3/backup/vulncheck-nvd2` - 244K CVEs with exploit maturity data
- ✅ `/v3/index/exploits` - On-demand CVE enrichment
- ✅ `/v3/backup/ransomware` - Ransomware family CVE attribution
- ✅ `/v3/backup/botnets` - Botnet campaign CVE attribution
- ✅ `/v3/backup/threat-actors` - Threat actor groups
- ✅ `/v3/backup/exploit-chains` - Multi-CVE attack sequences
- ✅ `/v3/backup/eol` - End-of-life product tracking
- ✅ `/v3/index/canaries` - Canary network exploitation evidence

**Pricing:** Contact VulnCheck sales (https://vulncheck.com/pricing)

---

## Database Impact

### Functional with Community Tier

**Document Collections (1):**
- ✅ `vulncheck_kev_entries` - Populated by VulnCheckKEVAgent

**Edge Collections (2):**
- ✅ `has_exploit_intelligence` - KEV → exploit_intelligence
- ✅ `exploited_in_wild` - Vulnerability → KEV entry

**Database Records:** 4,609 KEV entries (as of 2026-03-05)

### Disabled with Community Tier

**Document Collections (5):**
- ⏸️ `exploit_intelligence` - Requires NVD2 agent (paid) OR alternative free NVD API
- ⏸️ `ransomware_families` - Requires ransomware agent (paid)
- ⏸️ `botnets` - Requires botnets agent (paid)
- ⏸️ `exploit_chains` - Requires exploit chains agent (paid)
- ⏸️ `eol_products` - Requires EOL agent (paid)

**Edge Collections (8):**
- ⏸️ `exploited_by_ransomware` - Requires ransomware agent
- ⏸️ `exploited_by_botnet` - Requires botnets agent
- ⏸️ `exploited_by_threat_actor` - Requires threat actors agent
- ⏸️ `chain_includes_vuln` - Requires exploit chains agent
- ⏸️ `component_eol_status` - Requires EOL agent
- ⏸️ `ransomware_uses_technique` - Requires ransomware agent
- ⏸️ `botnet_uses_technique` - Requires botnets agent
- ⏸️ `vuln_triggers_requirement` - Requires exploit/ransomware data

**Note:** Schema exists and is ready; collections are simply empty until agents can populate them.

---

## Error Handling

All VulnCheck agents include built-in 402 error handling:

```python
except httpx.HTTPStatusError as e:
    if e.response.status_code == 402:
        logger.warning(
            "VulnCheck endpoint requires paid subscription",
            agent=self.__class__.__name__,
            endpoint=url,
            tier_required="Exploit & Vulnerability Intelligence"
        )
        return {
            "status": "skipped",
            "reason": "endpoint_requires_paid_tier",
            "documents_created": 0,
            "edges_created": 0
        }
```

**Behavior:**
- Agents log a clear warning message
- Return gracefully with `status: "skipped"`
- No exceptions raised (fail gracefully)
- Unit tests still pass (use mocked responses)

---

## Alternative Data Sources

### For `exploit_intelligence` Collection

The `exploit_intelligence` collection can be populated from **free alternative sources**:

**Option 1: NVD API (FREE)**
- Endpoint: `https://services.nvd.nist.gov/rest/json/cves/2.0`
- Data: CVE records with CVSS scores, CWE mappings
- Rate Limit: 50 requests/30s (no API key) or 500/30s (with free API key)
- Coverage: All CVEs (same as VulnCheck NVD2)

**Option 2: GHSA API (FREE)**
- Endpoint: `https://api.github.com/graphql`
- Data: GitHub Security Advisories with exploit/PoC links
- Rate Limit: 5,000 requests/hour (with GitHub token)
- Coverage: ~100K+ advisories

**Option 3: ExploitDB API (FREE)**
- Endpoint: `https://www.exploit-db.com/search`
- Data: Public exploits with CVE mappings
- Rate Limit: Unknown (scraping-based)
- Coverage: ~50K+ exploits

**Implementation Note:** Phase 2 already includes NVD and GHSA agents. The `exploit_intelligence` collection can be populated by merging data from these free sources rather than requiring VulnCheck NVD2.

---

## Acceptance Criteria Impact

### AC1: Unit Tests - All VulnCheck Agents
**Status:** ✅ **PASS**
- 23/23 tests passing
- All agents tested with mocked responses
- Tier requirements do not affect unit tests

### AC2: VulnCheck KEV Agent - Performance
**Status:** ✅ **PASS**
- Fully functional with Community tier
- Performance: 0.57s (target: < 30s)
- Database: 4,609 KEV entries

### AC3: VulnCheck NVD2 Agent - Streaming Parser
**Status:** ⚠️ **DEFERRED** (requires paid tier)
- Agent implementation complete and tested (unit tests pass)
- Cannot test with Community tier API key
- Requires user waiver or paid subscription upgrade

### AC4: VulnCheck Exploits Agent - On-Demand Enrichment
**Status:** ⚠️ **DEFERRED** (requires paid tier)
- Agent implementation complete and tested (unit tests pass)
- Cannot test with Community tier API key
- Requires user waiver or paid subscription upgrade

### AC5-AC7: Database Schema
**Status:** ✅ **PASS**
- All 6 collections created
- All 10 edges created
- All 7 indexes created
- Schema ready for use when agents are enabled

### AC8: Edge Relationships - Ransomware Attribution
**Status:** ⚠️ **DEFERRED** (requires paid tier)
- Agent implementation complete and tested (unit tests pass)
- Cannot test with Community tier API key
- Requires user waiver or paid subscription upgrade

### AC9: Canary Endpoint Tier Verification
**Status:** ✅ **PASS** (scope reduction complete)
- Verified 402 Payment Required
- Canary components removed in re-entry T-008

### AC10: API Endpoint Integration - POST /v1/enrich
**Status:** ⚠️ **DEFERRED** (Phase 3A-B)
- Deferred to Phase 3A-B (RegulatoryTriggerService)
- Requires user waiver

**Summary:** 4/10 AC Pass, 4/10 AC Deferred (tier), 2/10 AC Deferred (future phase)

---

## User Waiver Required

To complete Stage 7 and transition to Stage 8 (Code Review), user must provide **explicit waiver** for:

1. **AC3, AC4, AC8** - VulnCheck paid tier agents
   - **Rationale:** Agents are implemented, tested (unit tests), and ready to use
   - **Workaround:** User can upgrade to paid tier at any time
   - **Impact:** 5 of 6 collections will remain empty until upgraded

2. **AC10** - API endpoint integration
   - **Rationale:** Deferred to Phase 3A-B (RegulatoryTriggerService implementation)
   - **Workaround:** Phase 3A-B will complete this functionality
   - **Impact:** POST /v1/enrich will not include VulnCheck data until Phase 3A-B

**User Confirmation:**
> "I acknowledge that 8 of 9 VulnCheck agents require a paid subscription and cannot be tested with the Community tier API key. I waive AC3, AC4, and AC8 and approve transition to Stage 8 (Code Review) with the understanding that these agents are implemented and will function when a paid subscription is obtained."

---

## Documentation Updates Required

### 1. README.md
Add section:
```markdown
### VulnCheck Integration (Phase 3A)

**Community Tier (FREE):**
- ✅ VulnCheckKEVAgent - CISA KEV catalog with lead time analysis

**Paid Tier Required:**
- ⏸️ VulnCheckNVD2Agent - 244K CVEs with exploit maturity (requires subscription)
- ⏸️ VulnCheckExploitsAgent - On-demand CVE enrichment (requires subscription)
- ⏸️ VulnCheckRansomwareAgent - Ransomware CVE attribution (requires subscription)
- ⏸️ VulnCheckBotnetsAgent - Botnet CVE attribution (requires subscription)
- ⏸️ VulnCheckThreatActorsAgent - Threat actor groups (requires subscription)
- ⏸️ VulnCheckExploitChainsAgent - Multi-CVE attack sequences (requires subscription)
- ⏸️ VulnCheckEOLAgent - End-of-life product tracking (requires subscription)

**Alternative:** Use free NVD/GHSA APIs to populate exploit_intelligence collection.
```

### 2. Agent Docstrings
Add tier requirement to each agent:
```python
"""
VulnCheck Ransomware Agent.

**Tier Requirement:** Exploit & Vulnerability Intelligence subscription
**Status:** Disabled for Community tier (returns 402 Payment Required)

Syncs VulnCheck ransomware catalog...
"""
```

### 3. acceptance-criteria-checklist.md
Update AC3, AC4, AC8 status to "⚠️ Deferred (Paid Tier Required)"

### 4. PHASE_3A_IMPLEMENTATION_SUMMARY.md
Add tier requirements section

---

## Benefits of This Approach

✅ **No Code Removal** - All agents stay in codebase
✅ **No Re-Entry** - Stay in Stage 7, no need to go back to Stage 6
✅ **Future-Proof** - Ready when user upgrades to paid tier
✅ **Transparent** - Clear documentation of tier requirements
✅ **Graceful Degradation** - Agents fail gracefully on 402
✅ **Unit Tests Pass** - All 23 unit tests still pass (mocked)
✅ **Professional** - Demonstrates proper API integration patterns
✅ **Educational** - Code serves as reference for similar integrations

---

## Next Steps

1. ✅ Document tier requirements (this file)
2. ⏳ Update agent docstrings with tier requirements
3. ⏳ Update README.md with tier matrix
4. ⏳ Update acceptance-criteria-checklist.md with waivers
5. ⏳ Request user waiver for AC3, AC4, AC8, AC10
6. ⏳ Transition to Stage 8 (Code Review)

---

**Document Version:** 1.0
**Created:** 2026-03-05
**Author:** Claude Code (Anthropic)
**Status:** Tier requirements documented, awaiting user waiver
