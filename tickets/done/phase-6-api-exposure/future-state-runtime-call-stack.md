# Future-State Runtime Call Stacks: Phase 6 — API Exposure of Phase 2 Intelligence Fields

**Version:** v2 (FINDING-R1-01: 3→2 AQL queries for summary; FINDING-R1-02: sort allow-list)
**Ticket:** `phase-6-api-exposure`
**Scope:** Small
**Date:** 2026-03-22
**Design Basis:** `implementation-plan.md` (solution sketch)

---

## UC-P6-001: GET /v1/scan/{run_id}/findings — Phase 1 + Phase 2 fields returned

**Source:** Requirement (REQ-P6-001)
**Coverage:** Primary ✓ | Fallback ✓ | Error ✓

```
[Client] GET /v1/scan/{run_id}/findings
  ↓ FastAPI router → scan.py:list_scan_findings(run_id, customer, limit, offset)
      ↓ get_current_customer() → [auth] Customer(id=tenant_id)
      ↓ get_reference_db() → ArangoDB connection
      ↓ [DB read] ref_db.collection("scan_runs").get(run_id)
          ↓ [guard] doc is None OR doc["tenant_id"] != customer.id
              → raise HTTPException(404) ← ERROR PATH

      ↓ [DB read] ref_db.aql.execute(
            FOR f IN scan_findings
            FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
            SORT f.severity ASC
            LIMIT @offset, @limit
            RETURN f
        )
          ↓ cursor → list[dict] (ArangoDB documents)
          ↓ [data transformation] for f in findings:
              ScanFindingResponse(
                finding_id=f["_key"],
                cve_id=f.get("cve_id") or f.get("rule_id") or "N/A",
                severity=f.get("severity") or "unknown",
                description=f.get("message") or ...,
                location=f.get("file_path") or ...,
                tool_name=f.get("tool", "unknown"),
                created_at=f.get("ingested_at") or "",
                # Phase 1 fields (new)
                cvss_base=f.get("cvss_base"),
                epss_score=f.get("epss_score"),
                epss_percentile=f.get("epss_percentile"),
                in_kev=f.get("in_kev"),
                cwe_chain=f.get("cwe_chain"),
                d3fend_techniques=f.get("d3fend_techniques"),
                risk_score=f.get("risk_score"),
                compaction_group_id=f.get("compaction_group_id"),
                cluster_rank=f.get("cluster_rank"),
                compacted=f.get("compacted"),
                # Phase 2 fields (new)
                llm_risk_summary=f.get("llm_risk_summary"),
                llm_remediation=f.get("llm_remediation"),
                llm_attack_surface=f.get("llm_attack_surface"),
                llm_enriched_at=f.get("llm_enriched_at"),
                blast_radius_score=f.get("blast_radius_score"),
                affected_components=f.get("affected_components"),
                blast_radius_path=f.get("blast_radius_path"),
                blast_radius_computed_at=f.get("blast_radius_computed_at"),
                epss_velocity=f.get("epss_velocity"),
                epss_trend=f.get("epss_trend"),
                epss_velocity_computed_at=f.get("epss_velocity_computed_at"),
              )
          ↓ [persistence] none — read-only
          ↓ return APIResponse(success=True, data=findings_response)

  FALLBACK: findings = [] → returns APIResponse(data=[]) with 200 OK
  ERROR: DB unreachable → HTTPException(500)
```

---

## UC-P6-002: GET /v1/scan/{run_id} — scan_run returns Phase 2 fields + summary

**Source:** Requirement (REQ-P6-002, REQ-P6-006)
**Coverage:** Primary ✓ | Fallback ✓ | Error ✓

```
[Client] GET /v1/scan/{run_id}
  ↓ FastAPI router → scan.py:get_scan_run(run_id, customer)
      ↓ get_reference_db() → ArangoDB connection
      ↓ [DB read] ref_db.collection("scan_runs").get(run_id)
          ↓ [guard] not found or tenant mismatch → HTTPException(404) ← ERROR PATH

      ↓ [new] [DB aggregate — Query 1] ref_db.aql.execute(
            LET all_findings = (
                FOR f IN scan_findings
                FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
                RETURN {trend: f.epss_trend, br: f.blast_radius_score}
            )
            LET br_scores = (FOR x IN all_findings FILTER x.br != null RETURN x.br)
            LET trend_groups = (
                FOR x IN all_findings
                COLLECT trend = x.trend WITH COUNT INTO cnt
                RETURN {trend: trend, count: cnt}
            )
            RETURN {
                trend_groups: trend_groups,
                avg_blast_radius: LENGTH(br_scores) > 0 ? AVG(br_scores) : null
            }
        )
          ↓ result[0]["trend_groups"] → list[{trend, count}]
          ↓ trend_dict = {row["trend"]: row["count"] for row in trend_groups}
          ↓ rising_count = trend_dict.get("rising", 0)
          ↓ stable_count = trend_dict.get("stable", 0)
          ↓ falling_count = trend_dict.get("falling", 0)
          ↓ avg_blast_radius = result[0]["avg_blast_radius"]  # float | None

      ↓ [new] [DB read — Query 2] ref_db.aql.execute(
            FOR f IN scan_findings
            FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
                   AND f.blast_radius_score != null
            SORT f.blast_radius_score DESC
            LIMIT 5
            RETURN f._key
        )
          ↓ top_5_keys: list[str]

      ↓ [data transformation]
          phase2_summary = Phase2Summary(
              rising_count=rising_count,
              stable_count=stable_count,
              falling_count=falling_count,
              avg_blast_radius=avg_blast_radius,
              top_blast_radius_findings=top_5_keys,
          )
          llm_token_usage_raw = doc.get("llm_token_usage")
          llm_token_usage = LLMTokenUsage(**llm_token_usage_raw) if llm_token_usage_raw else None

          ScanSessionResponse(
              ...existing fields...,
              llm_token_usage=llm_token_usage,
              phase2_summary=phase2_summary,
              coverage_by_framework=doc.get("coverage_by_framework"),
          )
      ↓ return APIResponse(success=True, data=response)

  FALLBACK: No findings → phase2_summary has all zeros; avg_blast_radius=None; top=[])
  ERROR: DB unreachable → HTTPException(500)
```

---

## UC-P6-003: GET .../findings?epss_trend=rising — filter by trend

**Source:** Requirement (REQ-P6-003)
**Coverage:** Primary ✓ | Error ✓

```
[Client] GET /v1/scan/{run_id}/findings?epss_trend=rising
  ↓ FastAPI → list_scan_findings(epss_trend="rising", ...)
      ↓ [Pydantic validation] epss_trend: Optional[Literal["rising","stable","falling"]]
          ↓ "rising" → valid ✓
          ↓ "invalid" → Pydantic raises RequestValidationError → FastAPI → 422 ← ERROR PATH

      ↓ [AQL build] filter_clauses = ["f.scan_run_id == @run_id", "f.tenant_id == @tenant_id"]
          ↓ epss_trend is not None → append "f.epss_trend == @epss_trend"
          ↓ bind_vars["epss_trend"] = "rising"

      ↓ [DB read] aql.execute(
            FOR f IN scan_findings
            FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
                   AND f.epss_trend == @epss_trend
            SORT f.severity ASC
            LIMIT @offset, @limit
            RETURN f
        )
          ↓ Only documents where epss_trend == "rising" returned
      ↓ [data transformation] → list[ScanFindingResponse] (same as UC-P6-001)
      ↓ return APIResponse(data=filtered_findings)
```

---

## UC-P6-004: GET .../findings?min_blast_radius=0.5 — filter by blast radius

**Source:** Requirement (REQ-P6-004)
**Coverage:** Primary ✓ | Error ✓

```
[Client] GET /v1/scan/{run_id}/findings?min_blast_radius=0.5
  ↓ FastAPI → list_scan_findings(min_blast_radius=0.5, ...)
      ↓ [Pydantic/FastAPI validation] min_blast_radius: Optional[float] = Query(None, ge=0.0, le=1.0)
          ↓ 0.5 → valid ✓
          ↓ 1.5 → FastAPI Query validation fails → 422 ← ERROR PATH

      ↓ [AQL build] min_blast_radius is not None
          → append "f.blast_radius_score >= @min_blast_radius"
          → bind_vars["min_blast_radius"] = 0.5

      ↓ [DB read] aql.execute(
            FOR f IN scan_findings
            FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
                   AND f.blast_radius_score >= @min_blast_radius
            SORT f.severity ASC
            LIMIT @offset, @limit
            RETURN f
        )
      ↓ return APIResponse(data=filtered_findings)
```

---

## UC-P6-005: GET .../findings?sort_by=blast_radius_score — sort by Phase 2 field

**Source:** Requirement (REQ-P6-005)
**Coverage:** Primary ✓ | Error ✓

```
[Client] GET /v1/scan/{run_id}/findings?sort_by=blast_radius_score
  ↓ FastAPI → list_scan_findings(sort_by="blast_radius_score", ...)
      ↓ [Pydantic validation] sort_by: Optional[Literal["blast_radius_score","epss_velocity"]]
          ↓ "blast_radius_score" → valid ✓
          ↓ "invalid_field" → 422 ← ERROR PATH

      ↓ [AQL build] sort_by is not None
          → _SORT_FIELD_MAP = {"blast_radius_score": "f.blast_radius_score", "epss_velocity": "f.epss_velocity"}
          → sort_field = _SORT_FIELD_MAP["blast_radius_score"]  # = "f.blast_radius_score"
          → sort_clause = f"SORT {sort_field} DESC"  # only hardcoded strings interpolated
          (nulls sort last in ArangoDB DESC — correct behavior)

      ↓ [DB read] aql.execute(
            FOR f IN scan_findings
            FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
            SORT f.blast_radius_score DESC
            LIMIT @offset, @limit
            RETURN f
        )
      ↓ return APIResponse(data=sorted_findings)
```

---

## UC-P6-006: GET .../findings?epss_trend=rising&min_blast_radius=0.3&sort_by=epss_velocity — combined filters

**Source:** Design-Risk (verify AND-semantics and combined AQL correctness)
**Technical objective:** Confirm filter clauses combine correctly in AQL; bind_vars don't collide; sort_by overrides default severity sort.
**Expected outcome:** AQL with all three filter clauses AND'd, SORT by epss_velocity DESC.
**Coverage:** Primary ✓

```
[Client] GET /v1/scan/{run_id}/findings?epss_trend=rising&min_blast_radius=0.3&sort_by=epss_velocity
  ↓ FastAPI → list_scan_findings(epss_trend="rising", min_blast_radius=0.3, sort_by="epss_velocity")

      ↓ [AQL build]
          base_filter = "f.scan_run_id == @run_id AND f.tenant_id == @tenant_id"
          + " AND f.epss_trend == @epss_trend"
          + " AND f.blast_radius_score >= @min_blast_radius"
          bind_vars: {run_id, tenant_id, epss_trend="rising", min_blast_radius=0.3, offset, limit}
          sort_clause = "SORT f.epss_velocity DESC"   [overrides default severity sort]

      ↓ [DB read] aql.execute(
            FOR f IN scan_findings
            FILTER f.scan_run_id == @run_id AND f.tenant_id == @tenant_id
                   AND f.epss_trend == @epss_trend
                   AND f.blast_radius_score >= @min_blast_radius
            SORT f.epss_velocity DESC
            LIMIT @offset, @limit
            RETURN f
        )
      ↓ Returns findings matching BOTH filters, sorted by epss_velocity DESC, nulls last
```

---

## Use-Case Coverage Matrix

| use_case_id | Source | Primary | Fallback | Error | Notes |
| --- | --- | --- | --- | --- | --- |
| UC-P6-001 | Requirement | ✓ | ✓ (empty list) | ✓ (404, 500) | Full field mapping shown |
| UC-P6-002 | Requirement | ✓ | ✓ (no findings → zeros) | ✓ (404, 500) | 3 AQL queries shown |
| UC-P6-003 | Requirement | ✓ | N/A | ✓ (422 invalid value) | |
| UC-P6-004 | Requirement | ✓ | N/A | ✓ (422 out-of-range) | |
| UC-P6-005 | Requirement | ✓ | N/A | ✓ (422 invalid field) | |
| UC-P6-006 | Design-Risk | ✓ | N/A | N/A | AND-semantics + combined AQL |
