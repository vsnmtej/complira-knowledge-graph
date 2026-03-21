# CISA ADP Agent - Implementation Guide

**Status**: ✅ **Implemented and Working** (2026-03-02)

## Overview

The **CISAADPAgent** enriches vulnerability data with CISA's authoritative assessments as a CVE Authorized Data Publisher (ADP). This provides:

- **SSVC Decision Points** (Exploitation, Automatable, Technical Impact)
- **KEV Catalog Status** (Known Exploited Vulnerabilities)
- **Enhanced CWE Mappings** (CISA analyst-verified)
- **CISA CVSS Scores** (Independent assessment)

---

## Data Source

**API**: `https://cveawg.mitre.org/api/cve/{CVE-ID}`

**Format**: CVE JSON 5.0 with ADP containers

**CISA as ADP**: CISA acts as an Authorized Data Publisher, adding enrichment data to the official CVE record without overwriting the original CNA (CVE Numbering Authority) data.

---

## Data Extracted

### 1. SSVC Scores (Stakeholder-Specific Vulnerability Categorization)

CISA evaluates each CVE on three decision points:

```json
{
  "cisa_ssvc": {
    "exploitation": "active" | "poc" | "none",
    "automatable": "yes" | "no",
    "technical_impact": "total" | "partial",
    "timestamp": "2024-05-23T20:01:07.846921Z"
  }
}
```

**Use Cases**:
- **Exploitation = "active"**: CVE is being actively exploited in the wild
- **Automatable = "yes"**: Can be exploited at scale without human interaction
- **Technical Impact = "total"**: Gives attacker total control

### 2. KEV Status (Known Exploited Vulnerabilities)

If a CVE is in CISA's KEV catalog:

```json
{
  "cisa_kev": {
    "date_added": "2024-05-20",
    "reference": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog?field_cve=CVE-2024-4947"
  },
  "in_cisa_kev": true
}
```

**Use Cases**:
- Prioritize patching KEV vulnerabilities
- Query: `FOR vuln IN vulnerabilities FILTER vuln.in_cisa_kev == true RETURN vuln`

### 3. Enhanced CWE Mappings

CISA analysts verify/add CWE classifications:

```json
{
  "cisa_cwe_ids": ["CWE-843", "CWE-787"]
}
```

**Use Cases**:
- More accurate weakness categorization
- Compare original CNA CWEs vs CISA-verified CWEs

### 4. CISA CVSS Assessment

CISA's independent CVSS scoring:

```json
{
  "cisa_cvss": {
    "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:H/I:H/A:H",
    "base_score": 9.6,
    "base_severity": "CRITICAL"
  }
}
```

---

## Usage

### Run Agent with Sample CVEs

```bash
python run_cisa_adp.py
```

This tests with 5 sample CVEs that have CISA enrichment.

### Run Agent in Production

```python
from complira_graph.db import get_db
from complira_graph.agents.cisa_adp import CISAADPAgent

# Initialize
db = get_db()
agent = CISAADPAgent(db, rate_limit=30)  # 30 req/min

# Option 1: Enrich all recent CVEs (auto-query from DB)
result = agent.run()

# Option 2: Enrich specific CVEs
result = agent.run(cve_ids=["CVE-2024-1234", "CVE-2024-5678"])
```

### Query Enriched Data

```python
# Find KEV vulnerabilities
query = """
FOR vuln IN vulnerabilities
    FILTER vuln.in_cisa_kev == true
    RETURN {
        cve_id: vuln.cve_id,
        kev_date: vuln.cisa_kev.date_added,
        ssvc: vuln.cisa_ssvc
    }
"""

# Find actively exploited vulnerabilities
query = """
FOR vuln IN vulnerabilities
    FILTER vuln.cisa_ssvc.exploitation == "active"
    SORT vuln.cisa_cvss.base_score DESC
    RETURN vuln
"""

# Find automatable high-impact vulnerabilities
query = """
FOR vuln IN vulnerabilities
    FILTER vuln.cisa_ssvc.automatable == "yes"
    FILTER vuln.cisa_ssvc.technical_impact == "total"
    RETURN vuln
"""
```

---

## Performance Considerations

### Rate Limiting

CVE.org API has undocumented rate limits. The agent defaults to **30 requests/minute** (conservative).

**For large datasets**:
```python
# Fetch only recent CVEs (last 2 years)
agent = CISAADPAgent(db)
result = agent.run()  # Auto-queries only un-enriched CVEs from last 2 years

# Or fetch in batches
batch_size = 1000
for batch in chunks(all_cve_ids, batch_size):
    result = agent.run(cve_ids=batch)
    time.sleep(60)  # Pause between batches
```

### Filtering

The agent automatically skips:
- CVEs already enriched (`cisa_enriched == true`)
- CVEs without ADP containers
- CVEs older than 2 years (default)

---

## Integration with Seed Workflow

The agent is registered in the orchestrator:

**File**: `src/complira_graph/orchestrator/seed.py`

```python
AGENT_REGISTRY = {
    ...
    'CISAADPAgent': CISAADPAgent,
    ...
}
```

**Execution Order**: Runs AFTER NVD/GHSA agents populate vulnerabilities.

---

## Example Output

```
CVE ID: CVE-2024-4947
  SSVC Scores:
    - Exploitation: active        ← Being exploited in the wild!
    - Automatable: no             ← Requires human interaction
    - Technical Impact: total     ← Full system compromise
  KEV Status: ⚠️ IN KEV
    - Date Added: 2024-05-20      ← Added to KEV catalog
  Enhanced CWEs: CWE-843          ← Type confusion vulnerability
  CISA CVSS: 9.6 (CRITICAL)       ← CISA's severity assessment
```

---

## Schema Updates

### New Fields in `vulnerabilities` Collection

```json
{
  "_key": "CVE_2024_4947",
  "cve_id": "CVE-2024-4947",
  "cisa_enriched": true,
  "cisa_enrichment_date": "2026-03-02T15:36:55.000Z",

  "cisa_ssvc": {
    "exploitation": "active",
    "automatable": "no",
    "technical_impact": "total",
    "timestamp": "2024-05-23T20:01:07.846921Z"
  },

  "cisa_kev": {
    "date_added": "2024-05-20",
    "reference": "https://www.cisa.gov/..."
  },

  "in_cisa_kev": true,

  "cisa_cwe_ids": ["CWE-843"],

  "cisa_cvss": {
    "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:H/I:H/A:H",
    "base_score": 9.6,
    "base_severity": "CRITICAL"
  }
}
```

---

## Related Files

- **Agent**: `src/complira_graph/agents/cisa_adp.py`
- **Test Script**: `run_cisa_adp.py`
- **Registry**: `src/complira_graph/orchestrator/seed.py`

---

## References

- **CISA Vulnrichment**: https://www.cisa.gov/news-events/news/unlocking-vulnrichment-enriching-cve-data
- **CISA KEV Catalog**: https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- **SSVC Guide**: https://www.cisa.gov/stakeholder-specific-vulnerability-categorization-ssvc
- **CVE.org ADP Program**: https://www.cve.org/Media/News/item/blog/2024/06/04/CISA-Added-as-CVE-Authorized-Data-Publisher

---

## Testing Results

**Test Run**: 2026-03-02

| Metric | Result |
|--------|--------|
| CVEs Tested | 5 |
| ADP Containers Found | 5/5 (100%) |
| SSVC Scores Extracted | 5 |
| KEV Flags Found | 1 |
| Enhanced CWEs | 5 |
| CISA CVSS Scores | 5 |
| Load Errors | 0 |
| **Success Rate** | **100%** ✅ |

---

## Future Enhancements

1. **Incremental Updates**: Auto-fetch new ADP data daily
2. **SSVC Dashboards**: Grafana dashboards for SSVC trends
3. **KEV Alerts**: Notify when new CVEs added to KEV
4. **Bulk Import**: Optimize for initial load of 100K+ CVEs
5. **ADP History**: Track changes to CISA assessments over time
