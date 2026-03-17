# Temporal SBOM Analysis

## Overview

The Complira platform handles multiple SBOMs from the same customer over time using a **scan session-based temporal data model**. Each SBOM upload creates a new scan session with a timestamp, enabling historical tracking and drift analysis.

## Architecture

### Scan Session Model

Each scan creates a timestamped session:

```python
{
    "_key": "session_2024_03_10_001",
    "customer_id": "customer_123",
    "tool_name": "Trivy",
    "scan_timestamp": "2024-03-10T14:30:00Z",
    "scan_type": "cyclonedx",
    "findings_count": 42,
    "components_count": 156
}
```

### Temporal Data Linking

All findings and components link to their specific scan session:

```python
# Scan Finding
{
    "_key": "finding_001",
    "scan_session_id": "session_2024_03_10_001",
    "cve_id": "CVE-2021-44228",
    "severity": "critical",
    "state": "exploitable"
}

# Customer Component
{
    "_key": "component_001",
    "scan_session_id": "session_2024_03_10_001",
    "name": "log4j",
    "version": "2.14.1",
    "purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1"
}
```

## Temporal Query Patterns

### 1. Component Version Drift

Track components that changed versions between two scans:

```aql
// Find components with version changes
LET session1 = @scan_session_id_old
LET session2 = @scan_session_id_new

FOR c1 IN customer_components
    FILTER c1.scan_session_id == session1

    FOR c2 IN customer_components
        FILTER c2.scan_session_id == session2
        FILTER c1.name == c2.name
        FILTER c1.version != c2.version

        RETURN {
            component: c1.name,
            old_version: c1.version,
            new_version: c2.version,
            upgrade: c2.version > c1.version,
            old_purl: c1.purl,
            new_purl: c2.purl
        }
```

### 2. New Vulnerabilities Over Time

Find CVEs that appeared in newer scans (regression detection):

```aql
// Find new vulnerabilities introduced since last scan
LET session1 = @scan_session_id_old
LET session2 = @scan_session_id_new

LET old_cves = (
    FOR f IN scan_findings
        FILTER f.scan_session_id == session1
        RETURN DISTINCT f.cve_id
)

FOR f IN scan_findings
    FILTER f.scan_session_id == session2
    FILTER f.cve_id NOT IN old_cves

    // Enrich with CVE details
    LET cve = DOCUMENT("vulnerabilities", f.cve_id)

    RETURN {
        cve_id: f.cve_id,
        severity: f.severity,
        state: f.state,
        cvss_score: cve.cvss_v3_score,
        description: cve.description,
        component: f.component_name,
        version: f.component_version
    }
```

### 3. Resolved Vulnerabilities

Track CVEs that were fixed between scans:

```aql
// Find vulnerabilities that disappeared (patched components)
LET session1 = @scan_session_id_old
LET session2 = @scan_session_id_new

LET old_cves = (
    FOR f IN scan_findings
        FILTER f.scan_session_id == session1
        RETURN DISTINCT f.cve_id
)

LET new_cves = (
    FOR f IN scan_findings
        FILTER f.scan_session_id == session2
        RETURN DISTINCT f.cve_id
)

FOR cve_id IN old_cves
    FILTER cve_id NOT IN new_cves

    LET cve = DOCUMENT("vulnerabilities", cve_id)
    LET finding = FIRST(
        FOR f IN scan_findings
            FILTER f.scan_session_id == session1
            FILTER f.cve_id == cve_id
            RETURN f
    )

    RETURN {
        cve_id: cve_id,
        resolved: true,
        severity: finding.severity,
        cvss_score: cve.cvss_v3_score,
        component: finding.component_name,
        old_version: finding.component_version
    }
```

### 4. Component Churn Analysis

Identify components added/removed over time:

```aql
// Find components added in recent scan
LET session1 = @scan_session_id_old
LET session2 = @scan_session_id_new

LET old_components = (
    FOR c IN customer_components
        FILTER c.scan_session_id == session1
        RETURN c.purl
)

FOR c IN customer_components
    FILTER c.scan_session_id == session2
    FILTER c.purl NOT IN old_components

    RETURN {
        added: true,
        name: c.name,
        version: c.version,
        purl: c.purl,
        type: c.type
    }
```

```aql
// Find components removed since last scan
LET session1 = @scan_session_id_old
LET session2 = @scan_session_id_new

LET new_components = (
    FOR c IN customer_components
        FILTER c.scan_session_id == session2
        RETURN c.purl
)

FOR c IN customer_components
    FILTER c.scan_session_id == session1
    FILTER c.purl NOT IN new_components

    RETURN {
        removed: true,
        name: c.name,
        version: c.version,
        purl: c.purl,
        type: c.type
    }
```

### 5. Vulnerability Trend Analysis

Track total vulnerability count over time:

```aql
// Get vulnerability counts per scan session (last 30 days)
FOR session IN scan_sessions
    FILTER session.customer_id == @customer_id
    FILTER DATE_TIMESTAMP(session.scan_timestamp) > DATE_NOW() - 30*24*60*60*1000
    SORT session.scan_timestamp ASC

    LET findings = (
        FOR f IN scan_findings
            FILTER f.scan_session_id == session._key
            COLLECT severity = f.severity WITH COUNT INTO count
            RETURN {severity, count}
    )

    RETURN {
        scan_timestamp: session.scan_timestamp,
        tool_name: session.tool_name,
        total_findings: session.findings_count,
        by_severity: findings
    }
```

### 6. Critical CVE Tracking

Monitor specific high-priority CVEs across scans:

```aql
// Track specific CVE across all scans
LET cve_id = @cve_id

FOR session IN scan_sessions
    FILTER session.customer_id == @customer_id
    SORT session.scan_timestamp ASC

    LET finding = FIRST(
        FOR f IN scan_findings
            FILTER f.scan_session_id == session._key
            FILTER f.cve_id == cve_id
            RETURN f
    )

    RETURN {
        scan_timestamp: session.scan_timestamp,
        present: finding != null,
        state: finding.state,
        component: finding.component_name,
        version: finding.component_version
    }
```

### 7. Time-to-Patch Metrics

Calculate how long it takes to remediate vulnerabilities:

```aql
// Find when critical CVEs were first detected and when resolved
FOR cve_id IN (
    FOR f IN scan_findings
        FILTER f.severity == "critical"
        RETURN DISTINCT f.cve_id
)
    // First appearance
    LET first_seen = FIRST(
        FOR f IN scan_findings
            FILTER f.cve_id == cve_id
            LET session = DOCUMENT("scan_sessions", f.scan_session_id)
            SORT session.scan_timestamp ASC
            RETURN session.scan_timestamp
    )

    // Last appearance (if resolved)
    LET last_seen = LAST(
        FOR f IN scan_findings
            FILTER f.cve_id == cve_id
            LET session = DOCUMENT("scan_sessions", f.scan_session_id)
            SORT session.scan_timestamp ASC
            RETURN session.scan_timestamp
    )

    // Check if still present in latest scan
    LET latest_session = FIRST(
        FOR s IN scan_sessions
            FILTER s.customer_id == @customer_id
            SORT s.scan_timestamp DESC
            LIMIT 1
            RETURN s._key
    )

    LET still_present = LENGTH(
        FOR f IN scan_findings
            FILTER f.scan_session_id == latest_session
            FILTER f.cve_id == cve_id
            RETURN 1
    ) > 0

    LET days_to_patch = still_present ? null :
        DATE_DIFF(first_seen, last_seen, "d", true)

    RETURN {
        cve_id,
        first_detected: first_seen,
        resolved_date: still_present ? null : last_seen,
        days_to_patch,
        status: still_present ? "open" : "resolved"
    }
```

## API Integration Examples

### Scan Comparison Endpoint (Future)

```python
GET /v1/scan/compare?from={session_id_1}&to={session_id_2}

Response:
{
    "comparison": {
        "from_session": "session_2024_03_01_001",
        "to_session": "session_2024_03_10_001",
        "from_timestamp": "2024-03-01T10:00:00Z",
        "to_timestamp": "2024-03-10T14:30:00Z",

        "vulnerabilities": {
            "new": 5,
            "resolved": 12,
            "total_change": -7
        },

        "components": {
            "added": 3,
            "removed": 1,
            "version_changes": 8
        },

        "severity_changes": {
            "critical": {"from": 4, "to": 2},
            "high": {"from": 15, "to": 18},
            "medium": {"from": 23, "to": 20}
        }
    }
}
```

### Drift Detection Endpoint (Future)

```python
GET /v1/scan/{session_id}/drift

Response:
{
    "drift_analysis": {
        "session_id": "session_2024_03_10_001",
        "comparison_baseline": "session_2024_03_01_001",

        "version_drift": [
            {
                "component": "log4j",
                "old_version": "2.14.1",
                "new_version": "2.17.1",
                "upgrade": true,
                "vulnerabilities_fixed": ["CVE-2021-44228", "CVE-2021-45046"]
            }
        ],

        "dependency_churn": {
            "added_components": [...],
            "removed_components": [...]
        }
    }
}
```

## Benefits of Temporal Design

1. **Historical Analysis** - Track vulnerability trends over weeks/months
2. **Regression Detection** - Identify when new CVEs are introduced
3. **Patch Verification** - Confirm vulnerabilities were actually fixed
4. **Compliance Audit Trail** - Prove when issues were discovered and resolved
5. **Version Drift Monitoring** - Track component upgrades/downgrades
6. **No Data Loss** - Complete historical record without data duplication

## Storage Considerations

- **Session Metadata**: ~1KB per scan
- **Findings**: ~500 bytes per CVE finding
- **Components**: ~300 bytes per component

**Example**: 100 scans/month with 150 components and 40 findings each:
- Findings: 100 × 40 × 500 bytes = 2MB/month
- Components: 100 × 150 × 300 bytes = 4.5MB/month
- Total: ~6.5MB/month (~78MB/year)

**Retention Policy Options**:
- Keep all data indefinitely (recommended for compliance)
- Archive scans older than 2 years to cold storage
- Aggregate older scan metrics into summary statistics

## Query Performance

- **Index on scan_session_id**: O(log n) lookup for specific scan data
- **Index on scan_timestamp**: Efficient time-range queries
- **Index on (customer_id, scan_timestamp)**: Fast customer history queries
- **Estimated Query Times**:
  - Single session data: 10-50ms
  - Drift comparison (2 sessions): 50-200ms
  - Trend analysis (30 days): 100-500ms

## Best Practices

1. **Always filter by customer_id first** - Ensures data isolation and uses indexes
2. **Use LIMIT clauses** - Prevent unbounded result sets for large historical data
3. **Cache recent comparisons** - Common drift queries (last scan vs. previous)
4. **Pre-aggregate trends** - Daily/weekly vulnerability count summaries
5. **Partition old data** - Move scans >1 year old to archive collections if needed
