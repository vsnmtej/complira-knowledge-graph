# Scan API Reference

**Status:** Implemented
**Last Updated:** 2026-03-22
**Base Path:** `/v1/scan`

---

## Overview

The Scan API ingests scanner findings, triggers the Phase 1 + Phase 2 enrichment pipeline, and exposes enriched intelligence through query endpoints. All Phase 1 enrichment fields (EPSS, KEV, CWE, risk score, compaction) and Phase 2 intelligence fields (LLM risk summaries, blast radius, EPSS velocity) are returned in API responses.

---

## Endpoints

### POST /v1/scan/ingest

Ingest scan results from SAST, DAST, SCA, IaC, or SBOM tools. Automatically triggers the Phase 1 + Phase 2 enrichment pipeline as a background task.

**Supported formats:** SARIF 2.1.0, JSON native (Grype, Checkov, Semgrep), CycloneDX 1.4/1.5

**CycloneDX SBOM path** (`format=cyclonedx` or `scan_type=sbom`): ingests `components[]` and `dependencies[]` from the payload. Components are upserted to the `components` collection; `depends_on` edges and `project_uses_component` edges are written to ArangoDB, providing real dependency graph data for Phase 2 blast radius computation (UC-011).

**CycloneDX component fields stored:** `purl`, `name`, `version`, `type`, `supplier`, `licenses` (full list), `hashes`, `cpe`, `sbom_format`.

**Response: `ScanIngestResponse`**

```json
{
  "scan_run_id": "scan_abc123",
  "findings_count": 42,
  "components_count": 12,
  "status": "completed"
}
```

---

### GET /v1/scan/{run_id}

Get scan run details including Phase 2 summary statistics.

**Response: `ScanSessionResponse`**

```json
{
  "session_id": "scan_abc123",
  "status": "velocity_computed",
  "findings_count": 42,
  "coverage_by_framework": {"NIST 800-53": 42.7, "ISO 27001": 31.2},
  "llm_token_usage": {
    "input_tokens": 3500,
    "output_tokens": 800,
    "total_tokens": 4300,
    "model": "claude-haiku-4-5-20251001"
  },
  "phase2_summary": {
    "rising_count": 5,
    "stable_count": 30,
    "falling_count": 7,
    "avg_blast_radius": 0.23,
    "top_blast_radius_findings": ["fp1", "fp2", "fp3", "fp4", "fp5"]
  }
}
```

**Pipeline status values (full chain):**

| Status | Stage |
| --- | --- |
| `running` | Ingestion in progress |
| `completed` | Ingestion complete; enrichment queued |
| `enriched` | UC-007 complete |
| `compacted` | UC-008 complete |
| `mapped` | UC-009 complete |
| `llm_enriched` | UC-010 complete |
| `blast_radius_computed` | UC-011 complete |
| `velocity_computed` | UC-012 complete (full pipeline) |
| `enrichment_pending` | Reference DB unavailable at pipeline start |
| `pipeline_failed` | A pipeline stage failed |

**`phase2_summary` fields:**
- `rising_count` / `stable_count` / `falling_count` — count of findings by EPSS trend
- `avg_blast_radius` — mean blast radius score across findings with score; `null` if none
- `top_blast_radius_findings` — top 5 finding `_key` values by blast radius score DESC

**`llm_token_usage`** — null until UC-010 (LLM enrichment) completes.

---

### GET /v1/scan/{run_id}/findings

List findings for a scan run. Supports filtering and sorting by Phase 2 fields.

#### Query Parameters

| Parameter | Type | Description |
| --- | --- | --- |
| `limit` | `int` (1–1000, default 100) | Maximum findings to return |
| `offset` | `int` (default 0) | Pagination offset |
| `epss_trend` | `"rising" \| "stable" \| "falling"` | Filter findings by EPSS trend |
| `min_blast_radius` | `float` [0, 1] | Filter findings with blast_radius_score >= value |
| `sort_by` | `"blast_radius_score" \| "epss_velocity"` | Sort findings by field DESC (default: severity ASC) |

Multiple filters are AND'd together.

#### Examples

```bash
# Rising-trend findings sorted by blast radius
GET /v1/scan/{id}/findings?epss_trend=rising&sort_by=blast_radius_score

# High blast radius findings
GET /v1/scan/{id}/findings?min_blast_radius=0.5&sort_by=blast_radius_score

# Combined filter
GET /v1/scan/{id}/findings?epss_trend=rising&min_blast_radius=0.3&sort_by=epss_velocity
```

#### Response: `ScanFindingResponse`

```json
{
  "finding_id": "fp_xyz789",
  "cve_id": "CVE-2021-44228",
  "severity": "CRITICAL",
  "description": "Log4Shell remote code execution",
  "location": "src/main/java/App.java:42",
  "tool_name": "Grype",
  "created_at": "2026-03-22T00:00:00Z",

  // Phase 1 enrichment fields (UC-007/UC-008) — null until pipeline runs
  "cvss_base": 10.0,
  "epss_score": 0.974,
  "epss_percentile": 0.999,
  "in_kev": true,
  "cwe_chain": ["CWE-917"],
  "d3fend_techniques": ["D3-NTF"],
  "risk_score": 0.89,
  "compaction_group_id": "cg_cwe917",
  "cluster_rank": 1,
  "compacted": false,

  // Phase 2 LLM enrichment fields (UC-010) — null until llm_enriched
  "llm_risk_summary": "This Log4Shell vulnerability allows unauthenticated RCE.",
  "llm_remediation": "Upgrade log4j to 2.17.1 or later.",
  "llm_attack_surface": "network",
  "llm_enriched_at": "2026-03-22T01:00:00Z",

  // Phase 2 blast radius fields (UC-011) — null until blast_radius_computed
  "blast_radius_score": 0.42,
  "affected_components": ["pkg:maven/org.example/service@1.0"],
  "blast_radius_path": ["log4j-core", "service"],
  "blast_radius_computed_at": "2026-03-22T01:01:00Z",

  // Phase 2 EPSS velocity fields (UC-012) — null until velocity_computed
  "epss_velocity": 0.009,
  "epss_trend": "rising",
  "epss_velocity_computed_at": "2026-03-22T01:02:00Z"
}
```

**Field nullability:** All enrichment fields are `Optional` (null if the pipeline stage has not yet completed). The scan run `status` indicates which stages are done.

---

### GET /v1/scans

List all scan runs for the current tenant, newest first. Supports optional `project_id` and `repository_id` filters.

---

## Error Responses

| Status | Scenario |
| --- | --- |
| 422 | Invalid filter value (e.g., `epss_trend=plateau`, `min_blast_radius=1.5`, `sort_by=bad`) |
| 404 | Scan run not found or not owned by caller |
| 500 | Internal server error |

---

## Tests

| File | Type | Count |
| --- | --- | --- |
| `tests/unit/api/test_scan_findings_api.py` | Unit (TestClient) | 23 |

**AC Coverage:** 17/17 acceptance criteria (AC-P6-001 – AC-P6-017) closed.
