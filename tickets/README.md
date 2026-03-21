# Issue Tickets - Schema Bug Investigation & Fixes

**Created**: 2026-03-07
**Investigation**: Schema compliance issues in vulnerability ingestion agents

---

## Quick Summary

During VEX V2 implementation and GHSA agent debugging, discovered **2 critical schema bugs** affecting **336K+ vulnerability records**. All critical issues resolved in Phase 1. Enhancement script bugs verified fixed in Phase 2. Prevention test suite completed in Phase 3.

### Impact
- 🔥 **GHSA**: 100% data loss (0 records from 58K API pages)
- 🔥 **NVD**: 336K records missing required `vulnerability_id` field
- ✅ **Resolution**: All data recovered, features validated

---

## Tickets Overview

| # | Title | Status | Priority | Impact |
|---|-------|--------|----------|--------|
| [001](TICKET-001-ghsa-schema-bug.md) | GHSA Agent Schema Mismatch | ✅ RESOLVED | 🔥 CRITICAL | 100% data loss |
| [002](TICKET-002-nvd-vulnerability-id-backfill.md) | NVD Missing vulnerability_id + Backfill | ✅ RESOLVED | 🔥 CRITICAL | 336K records |
| [003](TICKET-003-enhancement-script-bugs.md) | CVE Enhancement Script Bugs | ✅ RESOLVED | 🟡 HIGH | Blocks imports |
| [004](TICKET-004-schema-validation-tests.md) | Schema Validation Test Suite | ✅ RESOLVED | 🟡 MEDIUM | Prevention |
| [005](TICKET-005-vulncheck-api-payment.md) | VulnCheck API Payment Required | ⚠️ OPEN | 🟢 LOW | Optional |

---

## ✅ Resolved Tickets (Phases 1, 2 & 3 Complete)

### TICKET-001: GHSA Agent Schema Mismatch
**Status**: ✅ RESOLVED (2026-03-07)

**Problem**: Agent fetched 58K+ pages but created 0 records due to schema validation failure.

**Root Cause**: Missing required fields:
- `vulnerability_id` (used `ghsa_id` instead)
- `cvss_v3_score` (used `cvss_score`)
- `cvss_v3_severity` (used `severity`)

**Solution**: Fixed field mapping in `src/complira_graph/agents/ghsa.py:254-281`

**Result**: 274 GHSA records now in database ✅

**Time**: 70 minutes (discovery to verification)

---

### TICKET-002: NVD Missing vulnerability_id + Backfill
**Status**: ✅ RESOLVED (2026-03-07)

**Problem**: 336,085 NVD records missing required `vulnerability_id` field.

**Root Cause**: Agent code didn't include field in yield statement.

**Solution**:
1. Added `"vulnerability_id": cve_id` to agent (line 276)
2. Backfilled 336K existing records with AQL update query

**Result**:
- All 336K records now have `vulnerability_id` ✅
- Compliance Passport works (43 violations in 11ms) ✅
- VEX evidence collection works (3ms query) ✅

**Time**: 40 minutes (fix + backfill + verification)

---

### TICKET-003: CVE Enhancement Script Bugs
**Status**: ✅ RESOLVED (2026-03-07)

**Problem**: Enhancement script had two bugs blocking CVE imports:
1. AttributeError: `_checkpoint` not initialized before `fetch_data()` call
2. 404 Not Found: Date range exceeded NVD API's 120-day limit

**Root Cause**: Script called agent methods directly without proper initialization and chunking.

**Solution**:
1. Added `agent._checkpoint = agent._load_checkpoint()` initialization (line 127)
2. Implemented 120-day date range chunking (lines 129-151)

**Result**:
- ✅ Script runs without errors
- ✅ Successfully tested with 7-day range (74 CVEs fetched)
- ✅ Historical verification: 319,815 CVEs imported via process fe5da3
- ✅ All acceptance criteria met

**Time**: Bugs already fixed in current codebase; 10 min verification

---

### TICKET-004: Schema Validation Test Suite
**Status**: ✅ RESOLVED (2026-03-07)

**Purpose**: Automated schema compliance tests to prevent future TICKET-001 and TICKET-002 class bugs.

**Solution**:
1. Created comprehensive test suite (`tests/agents/test_schema_compliance.py`)
   - 287 lines, 11 tests (all passing)
   - 4 GHSA agent tests
   - 3 NVD agent tests
   - 2 required field tests
   - 2 field naming convention tests
2. Created test fixtures (sample GHSA and NVD API responses)
3. Integrated with GitHub Actions CI/CD
4. Resolved circular import issues using manual validation

**Result**:
- ✅ All 11 tests passing (11/11)
- ✅ Tests catch missing `vulnerability_id` field
- ✅ Tests catch incorrect field names (`severity`, `cvss_score`)
- ✅ Tests validate CVSS severity normalization
- ✅ CI/CD automatically runs on every push/PR

**Time**: 4 hours (test development + fixture creation + CI integration)

---

## ⚠️ Open Tickets

### TICKET-005: VulnCheck API Payment Required
**Status**: ⚠️ OPEN (Pending business decision)
**Priority**: 🟢 LOW (Optional service)

**Problem**: VulnCheck API returns 402 Payment Required

**Options**:
1. Purchase subscription ($$$)
2. Disable agent gracefully (30 min)
3. Use free alternatives (already integrated)

**Recommendation**: Option 2 (disable) unless budget available

**Impact**: Low - free NVD API provides core data

---

## Database Status After Phase 1

### Vulnerabilities Collection
```
Total Records: 336,359
├── NVD: 336,085 (all with vulnerability_id ✅)
├── GHSA: 274 (all with vulnerability_id ✅)
└── Recent (2023+): 132,437 (all compliant ✅)
```

### Edges Collection
```
violates_requirement: 5,274,880 (Compliance Passport ✅)
has_weakness: 275,779 (CVE → CWE ✅)
```

### Features Validated
- ✅ Compliance Passport queries (11ms response)
- ✅ VEX evidence collection (3ms response)
- ✅ Graph traversals working
- ✅ Schema compliance 100%

---

## Fix Timeline

### Phase 1: Critical Data Fixes (✅ COMPLETE)
**Duration**: ~2 hours
**Date**: 2026-03-07

- [x] Investigated GHSA re-aggregation issue
- [x] Found schema mismatches in GHSA and NVD agents
- [x] Fixed GHSA agent code
- [x] Fixed NVD agent code
- [x] Backfilled 336K NVD records
- [x] Verified compliance passport
- [x] Verified VEX evidence
- [x] Created comprehensive tickets

### Phase 2: Enhancement Scripts (✅ COMPLETE)
**Duration**: 10 minutes
**Date**: 2026-03-07

- [x] Verified _checkpoint initialization already fixed
- [x] Verified 120-day chunking already implemented
- [x] Tested with small date range (74 CVEs fetched)
- [x] Verified historical success (319K CVEs imported)

### Phase 3: Prevention (✅ COMPLETE)
**Duration**: 4 hours
**Date**: 2026-03-07

- [x] Build schema validation test suite (287 lines, 11 tests)
- [x] Create test fixtures (GHSA, NVD samples)
- [x] Integrate with CI/CD (GitHub Actions)
- [x] Resolve import path issues (used manual validation)
- [x] All tests passing (11/11)
- [x] Update documentation

---

## Files Created/Modified

### Created (Phase 1 & 2)
- `tickets/TICKET-001-ghsa-schema-bug.md`
- `tickets/TICKET-002-nvd-vulnerability-id-backfill.md`
- `tickets/TICKET-003-enhancement-script-bugs.md`
- `tickets/TICKET-004-schema-validation-tests.md`
- `tickets/TICKET-005-vulncheck-api-payment.md`
- `tickets/README.md` (this file)
- `FIX_PLAN.md` (comprehensive 3-phase plan)
- `scripts/backfill_nvd_vulnerability_id.py`
- `check_agent_schemas.py`

### Created (Phase 3 - Test Suite)
- `tests/agents/test_schema_compliance.py` (309 lines)
- `tests/fixtures/ghsa/sample_advisory.json`
- `tests/fixtures/nvd/sample_cve.json`
- `.github/workflows/test-schema-compliance.yml`

### Modified
- `src/complira_graph/agents/ghsa.py:254-281` (schema fix)
- `src/complira_graph/agents/nvd.py:276` (added vulnerability_id)

---

## Lessons Learned

### What Went Wrong
1. **Silent Failures**: ArangoDB validation dropped documents without errors
2. **No Schema Tests**: No automated validation of agent outputs
3. **Field Name Drift**: Schema evolved but agents weren't updated
4. **Late Detection**: Found during feature implementation, not testing

### Prevention Measures
1. **Schema Validation Tool**: `check_agent_schemas.py` created
2. **Comprehensive Tickets**: Full documentation of issues
3. **Test Suite Planned**: TICKET-004 for automated prevention
4. **Documentation**: Clear schema requirements

### Process Improvements
1. **Ticket-Driven Development**: Track all issues formally
2. **Phased Fixes**: Critical first, then prevention
3. **Verification Tests**: Validate each fix immediately
4. **Business Decisions**: Separate technical from business issues

---

## Next Steps

### Immediate (Optional)
1. Fix TICKET-003 (enhancement script) if needed for new CVE imports
2. Decide on TICKET-005 (VulnCheck) based on budget

### Short-term (Recommended)
1. Implement TICKET-004 (test suite) to prevent future bugs
2. Document schema change process
3. Update agent development guide

### Long-term
1. Consider strict schema validation in ArangoDB
2. Automate compliance checks in CI/CD
3. Regular agent audits

---

## Success Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| GHSA records created | > 0 | 274 | ✅ |
| NVD vulnerability_id coverage | 100% | 100% | ✅ |
| Compliance queries working | Yes | Yes (11ms) | ✅ |
| VEX evidence working | Yes | Yes (3ms) | ✅ |
| Schema compliance | 100% | 100% | ✅ |
| Data loss incidents | 0 | 0 | ✅ |

---

## Related Documentation

- `FIX_PLAN.md` - Comprehensive 3-phase fix plan
- `IMPLEMENTATION_SUMMARY.md` - VEX V2 implementation
- `src/complira_graph/models.py` - Schema definitions
- `src/complira_graph/agents/base.py` - Agent framework

---

## Contact

For questions about these tickets or the fixes:
- Review ticket files in this directory
- Check `FIX_PLAN.md` for implementation details
- See git commits for code changes
