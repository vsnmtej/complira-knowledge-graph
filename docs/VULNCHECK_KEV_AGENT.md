# VulnCheck KEV Agent

## Overview

The **VulnCheckKEVAgent** ingests the VulnCheck KEV (Known Exploited Vulnerabilities) catalog, providing **extended vulnerability intelligence beyond CISA KEV**.

VulnCheck KEV offers:
- **Broader coverage** - More CVEs than CISA's catalog
- **Exploit database cross-references** - Links to exploit code (XDB)
- **Reported exploitation evidence** - Real-world exploitation reports
- **Ransomware campaign tracking** - Known ransomware usage
- **Canary detection** - VulnCheck honeypot detections

## Data Source

- **API**: https://api.vulncheck.com/v3/backup/vulncheck-kev
- **Documentation**: https://docs.vulncheck.com/community/vulncheck-kev
- **Schema**: https://docs.vulncheck.com/community/vulncheck-kev/schema

## Requirements

### API Key (Required)

VulnCheck provides a **free community tier** with generous rate limits (1,000 requests/min).

1. **Register** for free at: https://vulncheck.com/
2. **Get your API key** from the dashboard
3. **Add to `.env` file**:
   ```bash
   VULNCHECK_API_KEY=your_api_key_here
   ```

## What Data Does It Provide?

### Core KEV Fields
- `cve_ids` - Array of CVE identifiers (can be multiple)
- `vendor_project` - Affected vendor/project
- `product` - Affected product
- `vulnerability_name` - Vulnerability name
- `short_description` - Brief description
- `required_action` - Remediation guidance
- `known_ransomware_campaign_use` - Ransomware usage tracking
- `date_added` - Date added to VulnCheck KEV
- `cisa_date_added` - Date added to CISA KEV (if applicable)

### VulnCheck Enrichment (Unique Value)
- `vulncheck_xdb` - **Exploit database references**
  - XDB ID, URL, date added
  - Cross-references to exploit code
- `vulncheck_reported_exploitation` - **Exploitation evidence**
  - URLs of exploitation reports
  - Dates of observed exploitation
- `reported_exploited_by_canaries` - **Honeypot detection**
  - Boolean flag for VulnCheck canary detections
  - Indicates exploitation observed in honeypots

## Database Schema

### Collection: `vulncheck_kev_entries`

```python
{
    "_key": "CVE_2024_1234_vulncheck",  # CVE key + _vulncheck suffix
    "cve_ids": ["CVE-2024-1234"],       # Array (can have multiple)
    "primary_cve_id": "CVE-2024-1234",
    "vendor_project": "Apache",
    "product": "Log4j",
    "vulnerability_name": "Log4Shell",
    "short_description": "Remote code execution in Log4j",
    "required_action": "Apply updates per vendor instructions",
    "known_ransomware_campaign_use": "Known",
    "date_added": "2024-01-15T00:00:00",
    "cisa_date_added": "2024-01-16T00:00:00",  # If also in CISA KEV

    # VulnCheck enrichment
    "vulncheck_xdb": [
        {
            "xdb_id": "xdb-12345",
            "xdb_url": "https://vulncheck.com/xdb/xdb-12345",
            "date_added": "2024-01-15"
        }
    ],
    "vulncheck_reported_exploitation": [
        {
            "url": "https://example.com/incident-report",
            "date_added": "2024-01-14"
        }
    ],
    "reported_exploited_by_canaries": true,
    "source": "vulncheck"
}
```

### Edges: `exploited_in_wild`

Edges from `vulnerabilities` → `vulncheck_kev_entries`:

```python
{
    "_from": "vulnerabilities/CVE_2024_1234",
    "_to": "vulncheck_kev_entries/CVE_2024_1234_vulncheck",
    "date_added": "2024-01-15T00:00:00",
    "source": "vulncheck",
    "has_exploit_db_reference": true,
    "has_reported_exploitation": true,
    "canary_detected": true
}
```

## Usage

### Standalone Execution

```bash
# Run test script
python test_vulncheck_kev.py
```

### Via Orchestrator

```bash
# Full seed workflow (if VULNCHECK_API_KEY is set)
complira seed

# Incremental update
complira incremental VulnCheckKEVAgent
```

### Via Python API

```python
from complira_graph.db import get_db
from complira_graph.agents.vulncheck_kev import VulnCheckKEVAgent

db = get_db()
agent = VulnCheckKEVAgent(db)
result = agent.run()

print(f"Loaded {result['total_created']} VulnCheck KEV entries")
```

## Queries

### Find VulnCheck KEV entries with exploit code

```aql
FOR kev IN vulncheck_kev_entries
    FILTER LENGTH(kev.vulncheck_xdb) > 0
    RETURN {
        cve: kev.primary_cve_id,
        vulnerability: kev.vulnerability_name,
        exploit_count: LENGTH(kev.vulncheck_xdb),
        xdb_links: kev.vulncheck_xdb[*].xdb_url
    }
```

### Find CVEs with both CISA and VulnCheck KEV entries

```aql
FOR vulncheck_kev IN vulncheck_kev_entries
    FILTER vulncheck_kev.cisa_date_added != null
    LET cisa_kev = FIRST(
        FOR kev IN kev_entries
            FILTER kev.cve_id == vulncheck_kev.primary_cve_id
            RETURN kev
    )
    RETURN {
        cve: vulncheck_kev.primary_cve_id,
        vulnerability: vulncheck_kev.vulnerability_name,
        cisa_date: cisa_kev.date_added,
        vulncheck_date: vulncheck_kev.date_added,
        has_xdb: LENGTH(vulncheck_kev.vulncheck_xdb) > 0,
        canary_detected: vulncheck_kev.reported_exploited_by_canaries
    }
```

### Find ransomware-related vulnerabilities

```aql
FOR kev IN vulncheck_kev_entries
    FILTER kev.known_ransomware_campaign_use == "Known"
    RETURN {
        cve: kev.primary_cve_id,
        vulnerability: kev.vulnerability_name,
        vendor: kev.vendor_project,
        product: kev.product,
        date_added: kev.date_added
    }
```

### Find vulnerabilities detected by canaries

```aql
FOR kev IN vulncheck_kev_entries
    FILTER kev.reported_exploited_by_canaries == true
    RETURN {
        cve: kev.primary_cve_id,
        vulnerability: kev.vulnerability_name,
        xdb_count: LENGTH(kev.vulncheck_xdb),
        exploitation_reports: LENGTH(kev.vulncheck_reported_exploitation)
    }
```

## Coverage Comparison

### CISA KEV vs VulnCheck KEV

| Feature | CISA KEV | VulnCheck KEV |
|---------|----------|---------------|
| **CVE Count** | ~1,500 | **Broader** (typically more) |
| **Update Frequency** | Weekly | **Daily** |
| **Exploit Code Links** | ❌ No | ✅ **Yes (XDB)** |
| **Exploitation Reports** | ❌ No | ✅ **Yes** |
| **Honeypot Detection** | ❌ No | ✅ **Yes (Canaries)** |
| **Ransomware Tracking** | ✅ Yes | ✅ **Yes** |
| **API Access** | ✅ Free | ✅ **Free (Community)** |
| **Rate Limit** | Unlimited | 1,000 req/min |

### Recommendation

**Use both**:
- **CISA KEV** (KEVAgent) - Authoritative US government catalog
- **VulnCheck KEV** (VulnCheckKEVAgent) - Extended coverage with enrichment

Together they provide:
- Maximum CVE coverage
- Exploit code cross-references
- Real-world exploitation evidence
- Honeypot detections

## Integration with Existing Data

### Edges to Vulnerabilities

VulnCheck KEV entries create edges to existing `vulnerabilities` via `exploited_in_wild` collection:

```aql
# Find vulnerability with all exploitation intelligence
FOR vuln IN vulnerabilities
    FILTER vuln._key == "CVE_2024_1234"

    # Get CISA KEV entry
    LET cisa_kev = FIRST(
        FOR edge IN exploited_in_wild
            FILTER edge._from == vuln._id AND edge.source == "cisa_kev"
            FOR kev IN kev_entries
                FILTER kev._id == edge._to
                RETURN kev
    )

    # Get VulnCheck KEV entry
    LET vulncheck_kev = FIRST(
        FOR edge IN exploited_in_wild
            FILTER edge._from == vuln._id AND edge.source == "vulncheck"
            FOR kev IN vulncheck_kev_entries
                FILTER kev._id == edge._to
                RETURN kev
    )

    RETURN {
        cve: vuln.cve_id,
        in_cisa_kev: cisa_kev != null,
        in_vulncheck_kev: vulncheck_kev != null,
        has_exploit_code: vulncheck_kev.vulncheck_xdb != null,
        canary_detected: vulncheck_kev.reported_exploited_by_canaries
    }
```

## Error Handling

### Missing API Key

If `VULNCHECK_API_KEY` is not set:

```
ValueError: VulnCheck API key required. Set VULNCHECK_API_KEY environment variable
or pass api_key parameter. Get your free API key at: https://vulncheck.com/
```

**Solution**: Add API key to `.env` file.

### Invalid API Key

If API key is invalid:

```
ValueError: Invalid VulnCheck API key. Get your API key at: https://vulncheck.com/
```

**Solution**: Verify API key in VulnCheck dashboard.

### Rate Limiting

Community tier: 1,000 requests/min

The agent uses the backup endpoint which returns the full dataset in a single request, so rate limiting is typically not an issue.

## Performance

- **Single request** - Uses `/backup/vulncheck-kev` endpoint
- **Full dataset** - All KEV entries in one response
- **Typical size** - ~2-5 MB JSON
- **Execution time** - 1-2 minutes (fetch + transform + load)

## File Location

- **Agent**: `src/complira_graph/agents/vulncheck_kev.py`
- **Model**: `src/complira_graph/models.py` (VulnCheckKEVEntry)
- **Test Script**: `test_vulncheck_kev.py`
- **Orchestrator**: `src/complira_graph/orchestrator/seed.py` (registered)

## Next Steps

After populating VulnCheck KEV:

1. **Compare coverage** with CISA KEV
2. **Query exploit code** via XDB references
3. **Track ransomware** vulnerabilities
4. **Monitor canary detections** for early warnings
5. **Integrate with alerting** for new KEV additions

## Additional Resources

- **VulnCheck Website**: https://vulncheck.com/
- **API Documentation**: https://docs.vulncheck.com/api
- **KEV Schema**: https://docs.vulncheck.com/community/vulncheck-kev/schema
- **Community KEV Page**: https://www.vulncheck.com/kev
- **Free API Registration**: https://vulncheck.com/
