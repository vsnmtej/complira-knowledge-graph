# Known Issues

## OpenCRE Agent - API Deprecated (March 2026)

**Status**: Known Issue
**Impact**: Low (agent gracefully returns 0 records)
**Severity**: Non-blocking

### Issue Description

The OpenCRE agent fails to fetch data because the OWASP OpenCRE public API endpoint has been deprecated or restructured.

**Error Message**:
```
OpenCRE API returned invalid JSON (API likely deprecated)
content_type='text/html; charset=utf-8'
```

### Root Cause

- The public API endpoint (`https://www.opencre.org/rest/v1/cre_catalog`) now returns HTML instead of JSON
- CSV export functionality requires running a local OpenCRE Docker instance
- No public API or data dump is currently available

### Current Behavior

- Agent logs error and continues with 0 records
- No `opencre_nodes` or `opencre_links` data in knowledge graph
- **Other agents are unaffected** ✅
- Seed workflow completes successfully

### Impact Assessment

**Low Impact** because:
1. OpenCRE data is **supplementary** (not critical for core vulnerability tracking)
2. Other compliance frameworks are still available:
   - ✅ SCF (Secure Controls Framework) - **Working**
   - ✅ OSCAL (NIST 800-53, CRA, FDA 524B, IEC 62304) - **Working**
3. The knowledge graph has ~40 other data sources functioning normally

---

## Solution Options

### Option 1: Run Local OpenCRE Instance (Recommended for Production)

If you need OpenCRE data, run a local instance:

```bash
# Create database directory
mkdir -p opencre_data

# Run OpenCRE with local database
docker run -d \
  -v $(pwd)/opencre_data:/db:rw \
  -e CRE_ALLOW_IMPORT=1 \
  -e PROD_DATABASE_URL="sqlite:///db/db.sqlite" \
  -p 5000:5000 \
  ghcr.io/owasp/opencre/opencre:latest

# Export CSV data
curl http://localhost:5000/rest/v1/cre_csv > opencre_data.csv

# Update OpenCRE agent to use local instance
# Change OPENCRE_API_URL in src/complira_graph/agents/opencre.py:
#   OPENCRE_API_URL = "http://localhost:5000/rest/v1/cre_csv"
```

Then update the agent to parse CSV instead of JSON (requires code changes).

### Option 2: Use Alternative Data Source

**OpenCRE Explorer** provides a static data export:
- GitHub: https://zeljkoobrenovic.github.io/opencre-explorer/
- Consider scraping or downloading their dataset

### Option 3: Disable OpenCRE Agent

Remove from orchestrator agent registry if not needed:

```python
# In src/complira_graph/orchestrator/seed.py
# Comment out or remove OpenCREAgent from AGENT_REGISTRY
```

### Option 4: Wait for API Restoration

Monitor the OWASP/OpenCRE repository for API updates:
- Repository: https://github.com/OWASP/OpenCRE
- Last updated: 2026-03-02

---

## Recommendation

**For now: Accept the 0 records** ✅

The agent handles the failure gracefully and logs informative errors. Your knowledge graph is still fully functional with 39 other data sources.

**For production deployments**: Consider Option 1 (local instance) if OpenCRE mappings are required for your compliance workflows.

---

## Related Files

- Agent implementation: `src/complira_graph/agents/opencre.py`
- Orchestrator: `src/complira_graph/orchestrator/seed.py`
- OpenCRE docs: https://github.com/OWASP/OpenCRE/blob/main/docs/my-opencre-user-guide.md
