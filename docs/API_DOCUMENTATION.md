# Complira API Documentation

**Version:** v1
**Base URL:** `http://localhost:8000` (development) | `https://api.complira.dev` (production)
**Knowledge Graph:** 336,000+ CVEs | 10.3M+ edges | 5.27M regulatory compliance mappings

---

## 🎯 What is Complira?

Complira is a **cybersecurity compliance knowledge graph** that automatically maps CVE vulnerabilities to regulatory requirements, threat intelligence, and defensive controls.

**Core Features:**
- 🔍 **CVE Enrichment**: EPSS scores, KEV status, CWE weaknesses, ATT&CK techniques
- 🛡️ **Compliance Passport**: Automated CVE → Regulatory Requirement mapping (5.27M edges)
- 📊 **Threat Intelligence**: 770+ ATT&CK techniques, 195+ threat groups per CVE
- ⚡ **Fast**: ~13ms average enrichment response time (6-hour cache)

**Use Case:**
GitHub Action finds `CVE-2023-46456` locally → queries Complira API → gets enrichment data → generates compliance report. **Your scan results never leave your CI/CD pipeline.**

---

## 🔐 Authentication

**All API endpoints require authentication** using an API key in the `X-API-Key` header.

```bash
curl https://api.complira.dev/v1/reference/cve/CVE-2024-1234 \
  -H "X-API-Key: your_api_key_here"
```

### Getting Your First API Key

Contact your administrator to provision your first API key, or use the demo customer:

```python
# Create demo customer (development only)
python scripts/create_demo_customer.py

# Demo API Key
API_KEY="demo_api_key_12345678901234567890"
```

### Managing API Keys

Once authenticated, you can create and manage additional API keys:

- **Create new keys** for different environments (prod, staging, dev)
- **Set expiration dates** for temporary access
- **Revoke compromised keys** immediately
- **Track usage** with last_used timestamps

See [API Key Management](#api-key-management) section for details.

---

## Quick Start

### 1. Check API Health

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "database": "connected",
  "reference_database": "complira_graph"
}
```

### 2. Interactive API Documentation

FastAPI provides **automatic interactive documentation**:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

You can test API requests directly from your browser!

---

## Situation Room API

The Situation Room translates raw simulation graph data into persona-appropriate business views
with **zero CVE IDs** in any response. All vulnerability data is aggregated to business metrics
before leaving the abstraction layer.

**Authentication:** Bearer token (web session) or `X-API-Key` header.

### `GET /v1/situation/ciso`

Returns `CISOSituation` — posture score, ATT&CK threat categories, compliance control failures,
simulated MTTD, and prioritised action items. Also writes a `posture_snapshot` for historical
trending.

**Response (200 OK):**
```json
{
  "posture_score": 72,
  "posture_delta": -3,
  "attck_coverage_pct": 58.0,
  "control_failure_count": 2,
  "threat_categories": [
    {
      "bucket_name": "remote_code_execution",
      "display_name": "Remote Code Execution",
      "breach_probability": 0.62,
      "critical_asset_count": 3,
      "trend": null
    }
  ],
  "control_failures": [
    { "framework": "CRA", "failure_count": 1, "coverage_pct": 72.0 }
  ],
  "mttd_hours": 18.0,
  "mttd_target_hours": 24.0,
  "action_priorities": [
    {
      "rank": 1,
      "description": "Remediate Remote Code Execution attack vectors (62% breach probability)",
      "owner": "Security Engineering",
      "due_label": "30 days",
      "urgency": "high"
    }
  ],
  "snapshot_timestamp": "2026-04-14T00:00:00Z",
  "data_staleness_warning": null
}
```

**Posture score formula:**
`100 − round(mean_chain_probability × 40) − (gap_count × 3) − round(soc_miss_rate × 20) + round(attck_coverage × 0.1)` clamped [0, 100].

**Note:** No CVE IDs, CVSS scores, or EPSS data appear in any field of this response.
Trigger a new simulation to refresh stale threat data (`data_staleness_warning` will be set
when rollup data is from a prior run).

---

### `GET /v1/situation/board`

Returns `BoardSituation` — breach probability, financial exposure range, regulatory fine risk
(per framework), reputational risk score, and governance-language board priorities.

**Response (200 OK):**
```json
{
  "breach_probability_pct": 42.0,
  "breach_probability_delta": null,
  "financial_exposure_usd_low": 500000,
  "financial_exposure_usd_high": 2500000,
  "regulatory_fine_risk": [
    {
      "framework": "NIS2",
      "estimated_fine_usd": 5000000,
      "probability": 0.3
    }
  ],
  "reputational_risk_score": 0.35,
  "board_priorities": [],
  "snapshot_timestamp": "2026-04-14T00:00:00Z"
}
```

---

## Simulation API

The simulation layer uses the **Complira Simulation Engine (CSE)** — an in-process,
subprocess-based multi-agent simulation engine. CSE replaced the external MiroFish
HTTP client in Phase 5 Web UI. See `src/complira_graph/cse/` for the implementation.

### `POST /v1/cse/simulations/create`

Prepares and starts a CSE simulation run for the authenticated tenant.
Reads the tenant's attack surface (CVEs + components) from ArangoDB, generates
5 agent profiles (Attacker, SOCAnalyst, DevSecOps, CISO, Regulator), writes
`simulation_config.json`, and launches the simulation subprocess.

**Request body:**
```json
{ "trigger_type": "kev_triggered" }
```

Supported `trigger_type` values:
- `kev_triggered` — focused KEV-triggered run (48 rounds, 1h per round, CRA deadline round 24)
- `monthly_posture_sim` — full monthly posture run (720 rounds, 1h per round)

**Response (200 OK):**
```json
{ "sim_id": "550e8400-e29b-41d4-a716-446655440000", "status": "running", "tenant_id": "tenant_abc" }
```

**Errors:**
- `422 insufficient_attack_surface` — no exploitable CVEs found for tenant
- `422 invalid_trigger_type` — unknown trigger_type value
- `500 simulation_prepare_failed` — internal error during preparation

---

### `GET /v1/cse/simulations/{sim_id}/status`

Polls live CSE run state for the authenticated tenant.
Returns ArangoDB writeback data joined with run_state.json for round progress.
Designed for 3-second polling from `SimulationLivePanel`.

**Response (200 OK):**
```json
{
  "sim_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "tenant_abc",
  "status": "running",
  "trigger_type": "kev_triggered",
  "started_at": "2026-04-14T10:00:00Z",
  "current_round": 12,
  "total_rounds": 48,
  "agent_count": 5,
  "chain_count": null,
  "chain_probability": null,
  "board_narrative": null,
  "top_3_actions": [],
  "recent_events": [
    { "round_no": 12, "agent_type": "Attacker", "action_type": "EXPLOIT_CVE", "outcome": "CVE-2021-44228 exploited" }
  ]
}
```

**Errors:**
- `404` — run not found or belongs to a different tenant

---

### `GET /v1/simulation/{run_id}/status`

Returns Complira-side simulation run metadata (stored in `simulation_runs` collection).

**Response (200 OK):**
```json
{
  "run_id": "run_test_001",
  "cve_id": "CVE-2021-44228",
  "status": "completed",
  "started_at": "2026-04-12T10:00:00Z",
  "completed_at": "2026-04-12T10:05:00Z",
  "agent_count": 12,
  "round_count": 8,
  "chain_count": 2,
  "soc_blind_spot_count": 1,
  "top_playbook_action": "Patch log4j-core immediately",
  "recent_events": []
}
```

---

## Core Endpoints

### 📚 Reference Data (Authentication Required)

#### `GET /v1/reference/cve/{cve_id}`

Get CVE details with **full threat intelligence enrichment**.

**Authentication Required:** `X-API-Key` header

**Path Parameters:**
- `cve_id` (string, required): CVE identifier (e.g., `CVE-2023-46456`)

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "cve_id": "CVE-2023-46456",
    "description": "SQL injection vulnerability in...",
    "cvss_score": 9.8,
    "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
    "severity": "CRITICAL",
    "published_date": "2023-10-15T00:00:00Z",
    "last_modified_date": "2023-10-20T00:00:00Z",

    "epss": {
      "score": 0.00456,
      "percentile": 0.62,
      "date": "2024-03-05"
    },
    "kev": {
      "in_kev": false
    },

    "weaknesses": [
      {
        "cwe_id": "CWE-89",
        "name": "Improper Neutralization of Special Elements used in an SQL Command ('SQL Injection')",
        "description": "The product constructs all or part of an SQL command..."
      }
    ],

    "attack_patterns": [
      {
        "capec_id": "CAPEC-66",
        "name": "SQL Injection",
        "description": "This attack exploits target software that constructs SQL statements..."
      }
    ],

    "attack_techniques": [
      {
        "technique_id": "T1190",
        "name": "Exploit Public-Facing Application",
        "description": "Adversaries may attempt to exploit a weakness in an Internet-facing host...",
        "tactics": ["initial-access"]
      }
    ],

    "nist_controls": [
      {
        "control_id": "SI-2",
        "title": "Flaw Remediation",
        "family": "System and Information Integrity"
      }
    ],

    "regulatory_requirements": [],

    "d3fend_defenses": [
      {
        "technique_id": "d3f:ApplicationHardening",
        "name": "Application Hardening",
        "description": "Hardening an application to make it more resistant to attack."
      }
    ],

    "threat_groups": [],
    "exploits": [],

    "references": [
      {
        "url": "https://nvd.nist.gov/vuln/detail/CVE-2023-46456",
        "source": "nvd.nist.gov",
        "tags": ["Third Party Advisory"]
      }
    ]
  },
  "metadata": {
    "cache_hit": false,
    "api_version": "v1"
  }
}
```

**Example:**
```bash
curl http://localhost:8000/v1/reference/cve/CVE-2023-46456 \
  -H "X-API-Key: your_api_key" | jq
```

**Performance:**
- Average response time: **13ms** (with 6-hour cache)
- Cache TTL: 6 hours (21,600 seconds)

---

#### `GET /v1/reference/enrich`

Batch enrich multiple CVEs with threat intelligence.

**Authentication Required:** `X-API-Key` header

**Query Parameters:**
- `cve_ids` (string, required): Comma-separated CVE IDs (max 100 per request)

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    { /* Full CVE enrichment data (same as /v1/reference/cve/{cve_id}) */ },
    { /* Full CVE enrichment data */ },
    {
      "cve_id": "CVE-9999-0000",
      "error": "CVE not found"
    }
  ],
  "metadata": {
    "cache_hit": false,
    "api_version": "v1"
  }
}
```

**Example:**
```bash
# Enrich multiple CVEs found in your local scan
curl "http://localhost:8000/v1/reference/enrich?cve_ids=CVE-2023-46456,CVE-2024-1234" \
  -H "X-API-Key: your_api_key" | jq
```

**Behavior:**
- Returns partial results if some CVEs not found
- Max 100 CVEs per request
- Missing CVEs return `{"cve_id": "CVE-xxx", "error": "CVE not found"}`

---

#### `GET /v1/reference/cwe/{cwe_id}`

Get CWE weakness details with hierarchy and attack patterns.

**Authentication Required:** `X-API-Key` header

**Path Parameters:**
- `cwe_id` (string, required): CWE identifier (e.g., `CWE-79`)

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "cwe_id": "CWE-79",
    "name": "Improper Neutralization of Input During Web Page Generation ('Cross-site Scripting')",
    "description": "The software does not neutralize or incorrectly neutralizes user-controllable input...",
    "extended_description": "XSS vulnerabilities occur when...",

    "parents": [
      {
        "cwe_id": "CWE-74",
        "name": "Improper Neutralization of Special Elements in Output Used by a Downstream Component ('Injection')"
      }
    ],

    "children": [
      {
        "cwe_id": "CWE-80",
        "name": "Improper Neutralization of Script-Related HTML Tags in a Web Page (Basic XSS)"
      }
    ],

    "attack_patterns": [
      {
        "capec_id": "CAPEC-18",
        "name": "XSS Targeting Non-Script Elements",
        "description": "This type of attack is a form of Cross-Site Scripting..."
      }
    ]
  },
  "metadata": {
    "cache_hit": false,
    "api_version": "v1"
  }
}
```

**Example:**
```bash
curl http://localhost:8000/v1/reference/cwe/CWE-79 \
  -H "X-API-Key: your_api_key" | jq
```

---

#### `GET /v1/reference/controls/{cve_id}`

Get NIST 800-53 controls mapped to a CVE via the **Compliance Passport**.

**Authentication Required:** `X-API-Key` header

**Traversal Path:**
`CVE → CWE → CAPEC → ATT&CK → NIST 800-53 Control`

**Path Parameters:**
- `cve_id` (string, required): CVE identifier

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "cve_id": "CVE-2023-46456",
    "nist_controls": [
      {
        "control_id": "SI-2",
        "title": "Flaw Remediation",
        "family": "System and Information Integrity",
        "description": "Identify, report, and correct system flaws..."
      },
      {
        "control_id": "RA-5",
        "title": "Vulnerability Monitoring and Scanning",
        "family": "Risk Assessment",
        "description": "Monitor and scan for vulnerabilities..."
      }
    ],
    "regulatory_requirements": []
  },
  "metadata": {
    "cache_hit": false,
    "api_version": "v1"
  }
}
```

**Example:**
```bash
curl http://localhost:8000/v1/reference/controls/CVE-2023-46456 \
  -H "X-API-Key: your_api_key" | jq
```

**Use Case:**
Generate compliance report showing which NIST 800-53 controls address vulnerabilities found in your local scan.

---

### 📊 Metadata (Authentication Required)

#### `GET /v1/meta/coverage`

Get data coverage and quality metrics for the knowledge graph.

**Authentication Required:** `X-API-Key` header

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "vertices": {
      "vulnerabilities": 336000,
      "weaknesses": 969,
      "attack_patterns": 615,
      "attack_techniques": 823,
      "oscal_controls": 1196,
      "regulatory_requirements": 523
    },
    "edges": {
      "has_weakness": 290000,
      "capec_relates_to_cwe": 1247,
      "capec_maps_to_attack": 270,
      "technique_mitigated_by_control": 3456,
      "violates_requirement": 5270000
    },
    "enrichment_funnel": {
      "sample_size": 100,
      "sample_year": 2024,
      "cve_to_cwe_percent": 97,
      "cve_to_capec_percent": 72,
      "cve_to_attack_percent": 45
    }
  }
}
```

---

#### `GET /v1/meta/stats`

Get database statistics.

**Authentication Required:** `X-API-Key` header

---

### 🔑 API Key Management

#### `POST /v1/account/api-keys`

Create a new API key for the authenticated customer.

**Authentication Required:** `X-API-Key` header (use existing key to create new ones)

**Request Body:**
```json
{
  "name": "Production Server",
  "description": "API key for production deployment",
  "expires_days": 90
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "key_id": "key_abc123def456",
    "name": "Production Server",
    "api_key": "xY8Qm2KpR7vN3jL9Hs4Fq1Wt6Zc8BmA5Dp2Gn7Kr9Lp3Jv6",
    "created_at": "2026-03-12T10:00:00Z",
    "expires_at": "2026-06-10T10:00:00Z",
    "warning": "⚠️ Save this API key securely. You will not be able to retrieve it again."
  }
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/v1/account/api-keys \
  -H "X-API-Key: your_current_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production Server",
    "description": "API key for production deployment",
    "expires_days": 90
  }' | jq
```

**Important:**
- The API key is **only shown once** at creation time
- Save it securely - you cannot retrieve it later
- You can create multiple API keys for different use cases

---

#### `GET /v1/account/api-keys`

List all API keys for the authenticated customer.

**Authentication Required:** `X-API-Key` header

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "keys": [
      {
        "key_id": "key_abc123",
        "name": "Production Server",
        "description": "API key for production",
        "key_prefix": "xY8Qm2Kp",
        "created_at": "2026-03-12T10:00:00Z",
        "expires_at": "2026-06-10T10:00:00Z",
        "last_used_at": "2026-03-12T14:30:00Z",
        "revoked": false,
        "revoked_at": null,
        "revoked_reason": null
      }
    ],
    "total": 3,
    "active": 2
  }
}
```

**Example:**
```bash
curl http://localhost:8000/v1/account/api-keys \
  -H "X-API-Key: your_api_key" | jq
```

---

#### `DELETE /v1/account/api-keys/{key_id}`

Revoke an API key immediately.

**Authentication Required:** `X-API-Key` header

**Path Parameters:**
- `key_id` (string, required): API key identifier to revoke

**Request Body (optional):**
```json
{
  "reason": "Key compromised"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "key_id": "key_abc123",
    "revoked": true,
    "revoked_at": "2026-03-12T15:00:00Z",
    "message": "API key has been revoked and can no longer be used"
  }
}
```

**Example:**
```bash
curl -X DELETE http://localhost:8000/v1/account/api-keys/key_abc123 \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Key compromised"}' | jq
```

**Important:**
- Revocation is **permanent** and cannot be undone
- Revoked keys can no longer authenticate requests
- You can only revoke keys belonging to your customer account

---

### 📄 VEX Management

#### `POST /v1/vex`

Create a VEX (Vulnerability Exploitability eXchange) document.

**Authentication Required:** `X-API-Key` header

**Request Body:**
```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "version": 1,
  "vulnerabilities": [
    {
      "id": "CVE-2021-44228",
      "analysis": {
        "state": "not_affected",
        "justification": "code_not_reachable",
        "detail": "Log4j is included but logging is disabled in production configuration"
      }
    }
  ],
  "metadata": {
    "component": {
      "type": "application",
      "name": "my-app",
      "version": "1.0.0"
    },
    "timestamp": "2026-03-12T10:00:00Z"
  }
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "vex_id": "vex_abc123",
    "vulnerabilities_count": 2,
    "enriched_count": 2,
    "created_at": "2026-03-12T10:00:00Z"
  }
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/v1/vex \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d @vex_document.json | jq
```

---

#### `GET /v1/vex`

List all VEX documents.

**Authentication Required:** `X-API-Key` header

**Query Parameters:**
- `limit` (integer, optional): Max documents to return (1-1000, default: 100)
- `offset` (integer, optional): Number of documents to skip (default: 0)

---

#### `GET /v1/vex/{vex_id}`

Get a VEX document with full knowledge graph enrichment.

**Authentication Required:** `X-API-Key` header

**Path Parameters:**
- `vex_id` (string, required): VEX document identifier

**Response includes:**
- Client-submitted VEX assessments
- KEV status, EPSS scores, CVSS scores
- CWE weaknesses, ATT&CK techniques
- NIST controls, D3FEND defenses
- Regulatory violations

---

#### `PUT /v1/vex/{vex_id}`

Update entire VEX document (replaces all vulnerabilities).

**Authentication Required:** `X-API-Key` header

---

#### `PATCH /v1/vex/{vex_id}/vulnerability/{cve_id}`

Update single vulnerability assessment in VEX document.

**Authentication Required:** `X-API-Key` header

---

#### `DELETE /v1/vex/{vex_id}`

Delete VEX document.

**Authentication Required:** `X-API-Key` header

---

## 🛡️ Compliance Passport

### Overview

The **Compliance Passport** is Complira's flagship feature: **automated CVE → Regulatory Requirement mapping** via knowledge graph traversal.

**Statistics:**
- **5.27 million** `violates_requirement` edges created
- Traversal path: `CVE → CWE → CAPEC → ATT&CK → Control → Regulatory Requirement`
- Frameworks supported: FDA 524B, EU Cyber Resilience Act, IEC 62304, NIST 800-53

**How It Works:**

1. **Ingestion**: All CVEs (336K) linked to CWE weaknesses
2. **Weakness → Attack Pattern**: CWE linked to CAPEC attack patterns
3. **Attack Pattern → Technique**: CAPEC linked to MITRE ATT&CK techniques
4. **Technique → Control**: ATT&CK techniques mitigated by NIST 800-53 controls
5. **Control → Requirement**: Controls satisfy regulatory requirements
6. **Derived Edge Creation**: `populate_violates_requirement.py` creates direct `CVE → Requirement` edges

**Query Performance:**
```aql
// Find all regulatory requirements violated by CVE-2023-46456
FOR req IN 1..1 OUTBOUND DOCUMENT("vulnerabilities/CVE_2023_46456") violates_requirement
  RETURN req
```

Response time: **< 10ms** (direct edge lookup vs 5-hop traversal)

---

## 🚀 Performance Benchmarks

### Endpoint Performance (March 2026)

| Endpoint | Avg Response Time | Cache TTL | Database Hops |
|----------|------------------|-----------|---------------|
| `/v1/reference/cve/{id}` | **13ms** | 6 hours | 5-hop traversal |
| `/v1/reference/cwe/{id}` | **8ms** | 6 hours | 2-hop traversal |
| `/v1/reference/controls/{id}` | **15ms** | 6 hours | 4-hop traversal |
| `/v1/reference/enrich` | **45ms** (3 CVEs) | 6 hours | Batch processing |
| `/v1/vex` (create) | **500ms** | No cache | VEX + enrichment |
| `/v1/account/api-keys` (create) | **50ms** | No cache | Key generation |
| `/health` | **2ms** | No cache | Database ping |

### Knowledge Graph Statistics

```
Collections:
- vulnerabilities: 336,000 CVEs
- weaknesses: 969 CWE entries
- attack_patterns: 615 CAPEC entries
- attack_techniques: 823 ATT&CK techniques
- oscal_controls: 1,196 NIST 800-53 controls
- regulatory_requirements: 523 requirements (FDA, EU CRA, IEC 62304)

Edges:
- has_weakness: 290,000 (CVE → CWE)
- capec_relates_to_cwe: 1,247 (CAPEC → CWE)
- capec_maps_to_attack: 270 (CAPEC → ATT&CK)
- technique_mitigated_by_control: 3,456 (ATT&CK → Control)
- d3fend_counters_technique: 2,187 (D3FEND → ATT&CK)
- violates_requirement: 5,270,000 (CVE → Regulatory Requirement) ⭐
- has_epss: 336,000 (CVE → EPSS score)

Total Edges: 10.3M+
```

---

## Response Format

All API responses follow a consistent structure:

```json
{
  "success": true,
  "data": { /* Response data */ },
  "metadata": {
    "cache_hit": false,
    "execution_time_ms": 123.45,
    "api_version": "v1"
  }
}
```

**Error Response:**
```json
{
  "detail": "Error message here"
}
```

---

## HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request succeeded |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | Invalid request (validation error) |
| 401 | Unauthorized | Missing or invalid API key |
| 403 | Forbidden | API key valid but lacks permission |
| 404 | Not Found | Resource not found (CVE, CWE, scan session) |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error (contact support) |

---

## Error Examples

### 401 - Missing or Invalid API Key
```json
{
  "detail": "Missing API key. Provide X-API-Key header."
}
```

```json
{
  "detail": "Invalid API key"
}
```

### 404 - CVE Not Found
```json
{
  "detail": "CVE not found: CVE-9999-0000"
}
```

### 404 - CWE Not Found
```json
{
  "detail": "CWE not found: CWE-99999"
}
```

### 500 - Database Connection Error
```json
{
  "detail": "Internal server error"
}
```

---

## CI/CD Integration

### GitHub Actions - CVE Enrichment

```yaml
name: Security Scan + Enrichment

on: [push, pull_request]

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run Semgrep
        run: semgrep --config auto --sarif > semgrep.sarif

      - name: Extract CVEs
        run: |
          cat semgrep.sarif | jq -r '.runs[].results[].ruleId' | grep CVE | sort -u > cves.txt

      - name: Enrich CVEs with Complira
        env:
          COMPLIRA_API_KEY: ${{ secrets.COMPLIRA_API_KEY }}
        run: |
          CVE_IDS=$(cat cves.txt | tr '\n' ',' | sed 's/,$//')
          curl "https://api.complira.dev/v1/reference/enrich?cve_ids=$CVE_IDS" \
            -H "X-API-Key: $COMPLIRA_API_KEY" > enriched.json

      - name: Generate Compliance Report
        run: |
          python scripts/generate_compliance_report.py \
            --enriched enriched.json \
            --output compliance_report.md

      - name: Upload Report
        uses: actions/upload-artifact@v3
        with:
          name: compliance-report
          path: compliance_report.md
```

**Key Benefits:**
- ✅ Secure API key storage in GitHub Secrets
- ✅ Scan results never leave your GitHub runner
- ✅ Compliance report generated locally
- ✅ 6-hour cache = fast CI/CD builds

---

## Support & Development

### Local Development

See [API Local Development Guide](API_LOCAL_DEVELOPMENT.md) for:
- One-command API server startup (`./scripts/run_api_dev.sh`)
- Automated testing (`python scripts/test_api_local.py`)
- Debugging and troubleshooting
- Performance testing

### Documentation

- **API Docs:** http://localhost:8000/docs
- **Knowledge Graph Status:** [KNOWLEDGE_GRAPH_STATUS.md](KNOWLEDGE_GRAPH_STATUS.md)
- **Database Schema:** [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md)
- **Multi-Tenant Architecture:** [MULTI_TENANT_ARCHITECTURE.md](MULTI_TENANT_ARCHITECTURE.md)
- **Graph Architecture:** [GRAPH_ARCHITECTURE.md](GRAPH_ARCHITECTURE.md)
- **Temporal SBOM Analysis:** [TEMPORAL_SBOM_ANALYSIS.md](TEMPORAL_SBOM_ANALYSIS.md)
- **Reference Graph Completeness:** [REFERENCE_GRAPH_COMPLETENESS.md](REFERENCE_GRAPH_COMPLETENESS.md)

### Resources

- **Interactive Docs:** http://localhost:8000/docs (Swagger UI)
- **Alternative Docs:** http://localhost:8000/redoc (ReDoc)
- **Health Check:** http://localhost:8000/health

---

## Changelog

### v1.1.0 (2026-03-12) - API Key Management & VEX Support ✅

**Added:**
- ✅ **API Key Management**: Create, list, and revoke API keys
  - `POST /v1/account/api-keys` - Create new API key
  - `GET /v1/account/api-keys` - List all API keys
  - `DELETE /v1/account/api-keys/{key_id}` - Revoke API key
- ✅ **VEX API**: Complete CRUD for vulnerability assessments
  - `POST /v1/vex` - Create VEX document
  - `GET /v1/vex` - List VEX documents
  - `GET /v1/vex/{vex_id}` - Get enriched VEX
  - `PUT /v1/vex/{vex_id}` - Update VEX document
  - `PATCH /v1/vex/{vex_id}/vulnerability/{cve_id}` - Update single CVE
  - `DELETE /v1/vex/{vex_id}` - Delete VEX
- ✅ **Temporal Data Model**: Track SBOM changes over time
- ✅ **Multi-key authentication**: Support multiple API keys per customer
- ✅ **Key expiration**: Time-limited keys for temporary access
- ✅ **Key revocation**: Instant invalidation of compromised keys

**Changed:**
- 🔒 **All endpoints now require authentication** (X-API-Key header)
- 📚 Reference API endpoints now require API keys

**Documentation:**
- ✅ Added Graph Architecture guide
- ✅ Added Temporal SBOM Analysis guide
- ✅ Added Reference Graph Completeness report
- ✅ Updated API examples with authentication headers

### v1.0.0 (2026-03-09) - Compliance Passport Release ✅

**Added:**
- ✅ **Compliance Passport**: 5.27M `violates_requirement` edges (CVE → Regulatory Requirement)
- ✅ `/v1/reference/cve/{id}` - CVE enrichment with full threat intelligence
- ✅ `/v1/reference/enrich` - Batch CVE enrichment
- ✅ `/v1/reference/cwe/{id}` - CWE weakness details
- ✅ `/v1/reference/controls/{id}` - NIST 800-53 control mapping
- ✅ Knowledge graph: 336K CVEs, 10.3M+ edges
- ✅ Performance: ~13ms average enrichment response time
- ✅ 6-hour cache for reference data

**Fixed:**
- ✅ All edge collection names corrected (`has_weakness`, `capec_relates_to_cwe`, etc.)
- ✅ AQL queries updated to use INBOUND/OUTBOUND correctly
- ✅ Database connection to `complira_graph` reference database

**Coming in Phase 2:**
- 🚧 Threat group intelligence via VulnCheck
- 🚧 Exploit module tracking
- 🚧 EPSS velocity analysis
- 🚧 ATT&CK coverage heatmaps

### v0.1.0 (2026-03-05) - Phase 0 Alpha

**Added:**
- Scan ingestion API (SARIF, CycloneDX)
- Multi-tenant authentication
- Scan session management
- Finding retrieval
- VEX generation
- CPE matching (LLM-powered)
