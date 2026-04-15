# Compliance Violation API Reference

**Status:** Implemented
**Last Updated:** 2026-04-15
**Base Path:** `/v1/compliance`

---

## Overview

The Compliance Violation API exposes per-finding compliance violation data produced by the `ViolationMappingPipeline` post-ingestion stage. The pipeline supports two finding paths and writes `finding_violates_control` edges for both. These endpoints query those edges to surface compliance violations and coverage summaries per scan run.

All endpoints require authentication (`X-API-Key` or JWT). All results are tenant-scoped via `tenant_id` on `finding_violates_control` edges.

**Path 1 — CVE graph traversal (SAST/SCA findings with `cve_id`):**
```
CVE → has_weakness → CWE
    ← capec_relates_to_cwe ← CAPEC
    → capec_maps_to_attack → ATT&CK technique
    → technique_mitigated_by_control → NIST 800-53 control (oscal_controls)
```
- `evidence_path`: `[cve_key, cwe_key, capec_key, attack_key, control_key]`
- `confidence`: `1.0`

**Path 2 — Direct control ref (CSPM/IaC findings with `nist_control_refs` or `hipaa_refs`):**
- Comma-separated control IDs on the finding (e.g. `"AC-6, IA-2"`) are looked up directly in `oscal_controls`.
- No graph traversal; tool-provided mapping is used.
- `framework`: `"NIST-800-53"` for `nist_control_refs`, `"HIPAA"` for `hipaa_refs`
- `evidence_path`: `[finding_key, control_key]`
- `confidence`: `1.0`
- Control IDs not found in `oscal_controls` are silently skipped.

**Edge collection:** `finding_violates_control`
- `_from`: `scan_findings/<fingerprint_key>`
- `_to`: `oscal_controls/<control_key>`
- Fields: `tenant_id`, `scan_run_id`, `cve_id`, `control_id`, `framework`, `confidence`, `evidence_path`, `created_at`

---

## Pipeline Integration

| Stage | Status Before | Status After | Trigger |
| --- | --- | --- | --- |
| `ViolationMappingPipeline` | `mapped` | `violations_mapped` | Auto-triggered by `PipelineCoordinator` after `ControlMappingPipeline` |

The pipeline is idempotent: re-running with the same scan run and findings produces the same edges (deterministic `_key` = `generate_edge_key(finding_key, control_key, "violates_ctrl")`).

---

## Endpoints

### GET /v1/compliance/violations

Returns all `finding_violates_control` edges for a scan run, scoped to the caller's tenant.

#### Query Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scan_run_id` | `string` | Yes | Scan run identifier |

#### Response: `ViolationsResponse`

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "finding_id": "fp_abc123",
        "cve_id": "CVE-2024-1234",
        "control_id": "SI-2",
        "framework": "NIST_800_53",
        "confidence": 1.0,
        "evidence_path": ["CVE_2024_1234", "CWE_79", "CAPEC_86", "T1190", "SI-2"]
      }
    ],
    "total": 1
  },
  "metadata": {"api_version": "v1"}
}
```

**Fields:**
- `finding_id` — scan finding key (`scan_findings/<key>` without collection prefix)
- `cve_id` — CVE identifier in `CVE-YYYY-NNNNN` format
- `control_id` — NIST 800-53 control identifier (e.g. `AC-2`, `SI-2`)
- `framework` — framework identifier (e.g. `NIST_800_53`)
- `confidence` — `1.0` for all deterministic chain traversals
- `evidence_path` — ordered list of vertex `_key` values: `[cve_key, cwe_key, capec_key, attack_key, control_key]`

**Error responses:**
- `404` — scan run not found or does not belong to caller's tenant

---

### GET /v1/compliance/coverage

Returns a per-framework compliance coverage summary for a scan run.

#### Query Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `scan_run_id` | `string` | Yes | Scan run identifier |

#### Response: `CoverageResponse`

```json
{
  "success": true,
  "data": {
    "scan_run_id": "run_abc123",
    "total_findings": 87,
    "findings_with_violations": 23,
    "by_framework": [
      {
        "framework": "NIST_800_53",
        "violated_control_count": 12,
        "control_ids": ["AC-2", "SI-2", "CM-6", "SC-7", "IA-5", "AU-2", "SA-11", "SC-28", "RA-5", "IR-4", "CM-7", "AC-17"]
      }
    ]
  },
  "metadata": {"api_version": "v1"}
}
```

**Fields:**
- `total_findings` — total findings in the scan run
- `findings_with_violations` — count of distinct findings that triggered at least one control violation
- `by_framework` — per-framework breakdown:
  - `framework` — framework identifier
  - `violated_control_count` — number of distinct violated controls in this framework
  - `control_ids` — list of distinct violated control identifiers

**Error responses:**
- `404` — scan run not found or does not belong to caller's tenant

---

## Error Responses

| Status | Scenario |
| --- | --- |
| 401 | Missing or invalid authentication |
| 404 | Scan run not found or not accessible to tenant |
| 500 | Internal server error |

---

## Implementation

| File | Purpose |
| --- | --- |
| `src/complira_graph/db.py` | `finding_violates_control` edge collection schema + indexes |
| `src/complira_graph/ingestion/scan_violation_repository.py` | AQL: control chain traversal, direct control lookup by ID, edge upsert |
| `src/complira_graph/ingestion/violation_mapping_pipeline.py` | Pipeline stage: two-path orchestration (CVE traversal + direct ref) → build edges → upsert → set status |
| `src/complira_graph/ingestion/pipeline_coordinator.py` | Wires `ViolationMappingPipeline` after `ControlMappingPipeline` (`mapped → violations_mapped`) |
| `src/api/models/responses/compliance.py` | Response models |
| `src/api/v1/endpoints/compliance.py` | Endpoint handlers |
| `src/api/v1/router.py` | Router registration under `/compliance` prefix |

---

## Tests

| File | Type | Count |
| --- | --- | --- |
| `tests/unit/ingestion/test_violation_mapping_pipeline.py` | Unit (mocked repo) | 22 |
| `tests/unit/api/test_compliance_api.py` | Unit (TestClient) | 7 |

**AC Coverage:** 15/15 acceptance criteria (AC-CV-001 – AC-CV-015) closed. Direct-ref path adds coverage for Prowler NIST/HIPAA findings (6 additional scenarios).
