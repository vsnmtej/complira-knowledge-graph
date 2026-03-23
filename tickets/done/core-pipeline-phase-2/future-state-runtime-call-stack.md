# Future-State Runtime Call Stack: Core Pipeline Phase 2

**Document Version:** v2
**Status:** Draft — Pending Review
**Ticket:** `core-pipeline-phase-2`
**Scope:** `LARGE`
**Design Basis:** `tickets/in-progress/core-pipeline-phase-2/proposed-design.md` (v1.0)
**Requirements Ref:** `tickets/in-progress/core-pipeline-phase-2/requirements.md`
**Last Updated:** 2026-03-22

---

## Use-Case Index

| Use Case ID | Type | Description | Primary Path | Fallback Path | Error Path |
|---|---|---|---|---|---|
| UC-010-MAIN | Requirement | LLM enrichment — all findings with CVE context | Yes | N/A | Yes |
| UC-010-NONCVE | Requirement | LLM enrichment — non-CVE findings (rule_id + severity fallback) | Yes | N/A | N/A |
| UC-010-PARTIAL-FAIL | Requirement | LLM enrichment — partial batch failure; surviving findings written | N/A | Yes | N/A |
| UC-010-ALL-FAIL | Requirement | LLM enrichment — all batches fail; pipeline_failed recorded | N/A | N/A | Yes |
| UC-010-IDEMPOTENT | Requirement | LLM enrichment — re-run same scan_run_id; no duplicate writes | Yes | N/A | N/A |
| UC-011-MAIN | Requirement | Blast radius — SCA finding with purl; INBOUND traversal returns dependents | Yes | N/A | N/A |
| UC-011-NO-PURL | Requirement | Blast radius — SAST/IaC finding with no purl; score=0 applied | N/A | Yes | N/A |
| UC-011-NO-EDGES | Requirement | Blast radius — purl resolves to component but no depends_on edges | Yes | N/A | N/A |
| UC-011-IDEMPOTENT | Requirement | Blast radius — re-run same scan_run_id; identical scores produced | Yes | N/A | N/A |
| UC-012-MAIN | Requirement | EPSS velocity — CVE with sufficient history; trend classified | Yes | N/A | N/A |
| UC-012-INSUFFICIENT | Requirement | EPSS velocity — fewer than 2 data points; stable returned | N/A | Yes | N/A |
| UC-012-EMPTY-HISTORY | Requirement | EPSS velocity — epss_history collection empty (agents not run) | N/A | Yes | N/A |
| UC-012-NO-CVE | Requirement | EPSS velocity — no cve_id on finding; velocity=0.0, trend=stable | N/A | Yes | N/A |
| UC-012-IDEMPOTENT | Requirement | EPSS velocity — re-run same scan_run_id; same results | Yes | N/A | N/A |
| UC-CROSS-CHAIN | Requirement | Full Phase 2 chain: mapped → llm_enriched → blast_radius_computed → velocity_computed | Yes | N/A | N/A |
| UC-CROSS-RETRIGGER | Requirement | Manual re-trigger from intermediate Phase 2 status via POST /enrich | Yes | N/A | N/A |
| UC-CROSS-PARTIAL-FAIL-ISO | Requirement | Phase 2 stage fails; pipeline_failed set; partial writes retained | N/A | N/A | Yes |
| UC-CROSS-TENANT | Requirement | All Phase 2 reads/writes include tenant_id scoping | Yes | N/A | N/A |
| UC-DR-LLM-PROMPT | Design-Risk | LLM prompt: non-CVE finding context construction correctness | Yes | N/A | N/A |
| UC-DR-BLAST-DEDUP | Design-Risk | Blast radius: purl deduplication reduces AQL round-trips for large scan runs | Yes | N/A | N/A |

---

## UC-010-MAIN: LLM Enrichment — CVE Finding Batch (Primary Path + Error Path)

**Type:** Requirement
**Source:** REQ-004 (UC-010)
**Trigger:** `scan_run.status == "mapped"`
**Expected Outcome:** Every finding receives `llm_risk_summary`, `llm_remediation`, `llm_attack_surface`, `llm_enriched_at`; `scan_run.status = "llm_enriched"`
**Coverage:** AC-029, AC-030, AC-031, AC-033, AC-035

### Primary Path

```
[ENTRY: BackgroundTask / POST /v1/scans/{id}/enrich]
│
src/api/routes/pipeline.py:trigger_enrich()  OR  src/complira_graph/ingestion/scan.py:ingest()
│   BackgroundTask: coordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
│
└─► src/complira_graph/ingestion/pipeline_coordinator.py:PipelineCoordinator.run_post_ingest_pipeline()
        # Phase 1 stages complete; scan_run.status == "mapped"
        # Re-read status: current_status = self._get_run_status(scan_run_id)
        # Guard: current_status not in _LLM_DONE  → proceed
        │
        └─► src/complira_graph/ingestion/llm_enrichment_pipeline.py:LLMEnrichmentPipeline.run(scan_run_id, tenant_id)
                │
                ├─ Initialize accumulators:
                │   total_input_tokens = 0
                │   total_output_tokens = 0
                │   llm_failure_count = 0
                │
                ├─► src/complira_graph/ingestion/scan_enrichment_repository.py:ScanEnrichmentRepository.fetch_findings_for_run(scan_run_id, tenant_id, batch_size=500)
                │       AQL: FOR f IN scan_findings FILTER f.scan_run_id == @scan_run_id AND f.tenant_id == @tenant_id
                │       SORT f._key LIMIT @offset, @batch_size RETURN f
                │       [DB WRITE: none — read-only]
                │       Yields: list[dict] (batch of 500 findings)
                │
                ├─ Split batch into sub-batches of 10:
                │   for i in range(0, len(batch), 10):
                │       sub_batch = batch[i:i+10]
                │       [DATA TRANSFORM: extract context fields per finding]
                │       context_batch = [self._context_for_finding(f) for f in sub_batch]
                │
                ├─► src/complira_graph/ingestion/llm_enrichment_pipeline.py:LLMEnrichmentPipeline._context_for_finding(finding)
                │       If finding["cve_id"]:
                │           return {"finding_key": _key, "cve_id": cve_id, "severity": ..., "package_name": ..., "cvss_base": ...}
                │       Else (non-CVE fallback):
                │           return {"finding_key": _key, "rule_id": rule_id, "severity": ..., "cve_id": null}
                │       [IN-MEMORY TRANSFORM: no DB]
                │
                ├─► src/complira_graph/ingestion/pipeline_llm_client.py:PipelineLLMClient.call_batch(context_batch)
                │       ├─► self._build_system_prompt()  → str
                │       ├─► self._build_user_prompt(findings=context_batch)  → str
                │       │       Serializes each finding as JSON line
                │       ├─► anthropic.Anthropic().messages.create(
                │       │       model="claude-haiku-4-5-20251001",
                │       │       max_tokens=2048,
                │       │       messages=[{"role":"user","content": user_prompt}],
                │       │       system=system_prompt
                │       │   )
                │       │   [EXTERNAL API CALL: Anthropic Claude Haiku — sync]
                │       ├─► self._parse_response(raw_text, finding_keys)
                │       │       json.loads(raw_text)  →  list[dict]
                │       │       Matches results to input order by finding_key
                │       │       Missing entries → empty dict
                │       └─► Returns: LLMBatchResult(results, input_tokens, output_tokens)
                │
                ├─► src/complira_graph/ingestion/llm_enrichment_pipeline.py:LLMEnrichmentPipeline._build_llm_updates(sub_batch, result.results)
                │       For each (finding, llm_result) pair:
                │           if llm_result is not None:
                │               normalize attack_surface to lowercase; default "network" if invalid
                │               update_dict = {"_key": finding["_key"],
                │                              "llm_risk_summary": ..., "llm_remediation": ...,
                │                              "llm_attack_surface": ..., "llm_enriched_at": utcnow()}
                │           else:
                │               update_dict = {"_key": finding["_key"], "llm_enriched_at": utcnow()}
                │       [IN-MEMORY TRANSFORM]
                │
                ├─► src/complira_graph/ingestion/scan_llm_enrichment_repository.py:ScanLLMEnrichmentRepository.bulk_write_llm_fields(updates)
                │       Chunks updates at 500 per AQL call
                │       FOR u IN @updates
                │           UPDATE u._key WITH u IN scan_findings
                │           OPTIONS {keepNull: false}
                │       [DB WRITE: scan_findings — LLM fields per finding]
                │
                ├─ Accumulate tokens:
                │   total_input_tokens  += result.input_tokens
                │   total_output_tokens += result.output_tokens
                │
                ├─ (after all batches processed)
                │
                ├─► src/complira_graph/ingestion/scan_llm_enrichment_repository.py:ScanLLMEnrichmentRepository.write_token_usage(scan_run_id, {input_tokens, output_tokens, total_tokens, model})
                │       self._db.collection("scan_runs").update({"_key": scan_run_id, "llm_token_usage": token_usage, "updated_at": utcnow()})
                │       [DB WRITE: scan_runs — llm_token_usage field]
                │
                └─► src/complira_graph/ingestion/scan_llm_enrichment_repository.py:ScanLLMEnrichmentRepository.update_scan_run_status(scan_run_id, "llm_enriched", extra_fields={"llm_enriched_at": utcnow()})
                        self._db.collection("scan_runs").update({"_key": scan_run_id, "status": "llm_enriched", "llm_enriched_at": utcnow()})
                        [DB WRITE: scan_runs.status = "llm_enriched"]
                        [STATE MUTATION: scan_run transitions to llm_enriched]
```

### Error Path — `anthropic.APIError` on a sub-batch

```
PipelineLLMClient.call_batch(sub_batch)
│   anthropic.Anthropic().messages.create(...)
│   raises anthropic.APIError  →  log error
│   re-raise to caller
│
LLMEnrichmentPipeline.run():
│   except Exception:
│       log.warning("llm_enrichment_pipeline.batch_failed", ...)
│       llm_failure_count += 1
│       continue to next sub-batch  (isolation: AC-034)
│
After all sub-batches:
│   if llm_failure_count == total_sub_batches:   # all failed
│       raise RuntimeError("all_llm_batches_failed")
│       → PipelineCoordinator catches
│       → self._mark_failed(scan_run_id, str(exc))
│       [DB WRITE: scan_runs.status = "pipeline_failed"]
│       return  (pipeline stops; partial writes retained per AC-053)
│
│   else:   # partial failure → surviving writes committed above
│       continue to write_token_usage + update_scan_run_status("llm_enriched")
│       [AC-034: pipeline_failed only if ALL findings fail]
```

---

## UC-010-NONCVE: LLM Enrichment — Non-CVE Finding Context Fallback

**Type:** Requirement
**Source:** REQ-004 (UC-010)
**Coverage:** AC-032
**Note:** Embedded within UC-010-MAIN call stack; isolated here to clarify the non-CVE path.

```
LLMEnrichmentPipeline._context_for_finding(finding)
│
│   Decision gate: finding["cve_id"] is None (or empty string)
│       → return {"finding_key": finding["_key"],
│                 "rule_id":     finding.get("rule_id"),   # e.g. "CWE-89" or Semgrep rule ID
│                 "severity":    finding["severity"],
│                 "cve_id":      null}
│
│   (No skip — non-CVE findings are always submitted to LLM, AC-032)
│
PipelineLLMClient._build_user_prompt(context_batch)
│   Serializes finding as:
│   {"finding_key": "abc", "rule_id": "semgrep.detect-sql-injection", "severity": "HIGH", "cve_id": null}
│   [LLM uses rule_id + severity as context in absence of CVE]
│
PipelineLLMClient.call_batch(...)
│   Claude Haiku receives rule_id + severity in prompt
│   Returns: risk_summary, remediation, attack_surface derived from rule semantics
│   [EXTERNAL API CALL: Anthropic]
│
LLMEnrichmentPipeline._build_llm_updates(...)
│   llm_attack_surface normalized; default "network" if LLM returns unexpected value
│   [IN-MEMORY TRANSFORM]
│
ScanLLMEnrichmentRepository.bulk_write_llm_fields(updates)
│   [DB WRITE: scan_findings — llm fields for non-CVE finding]
```

---

## UC-010-PARTIAL-FAIL: LLM Enrichment — One Batch Fails, Rest Succeed

**Type:** Requirement
**Source:** REQ-004 (UC-010)
**Coverage:** AC-034, AC-053

```
LLMEnrichmentPipeline.run(scan_run_id, tenant_id)
│
│   sub_batch[0] → PipelineLLMClient.call_batch()  → success
│       ScanLLMEnrichmentRepository.bulk_write_llm_fields(updates_0)
│       [DB WRITE: partial — findings 0-9 enriched]
│
│   sub_batch[1] → PipelineLLMClient.call_batch()  → raises APIError
│       except: log.warning; llm_failure_count += 1; continue
│       [No DB write for sub_batch[1] — those findings will have llm_enriched_at but no summary]
│
│   sub_batch[2] → PipelineLLMClient.call_batch()  → success
│       ScanLLMEnrichmentRepository.bulk_write_llm_fields(updates_2)
│       [DB WRITE: partial — findings 20-29 enriched]
│
│   # After all sub-batches:
│   # llm_failure_count = 1, total_sub_batches = 3 → not all failed
│   # Continue to token usage write + status transition
│
│   ScanLLMEnrichmentRepository.write_token_usage(...)
│   ScanLLMEnrichmentRepository.update_scan_run_status(scan_run_id, "llm_enriched")
│   [DB WRITE: scan_runs.status = "llm_enriched"]
│   [PARTIAL WRITES RETAINED — findings 10-19 have no LLM fields except llm_enriched_at]
```

---

## UC-010-IDEMPOTENT: LLM Enrichment — Re-run Same scan_run_id

**Type:** Requirement
**Source:** REQ-004 (UC-010)
**Coverage:** AC-036

```
PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id, force=True)
│   # force=True bypasses _LLM_DONE guard
│   # OR: status == "llm_enriched" but force requested via POST /enrich
│
LLMEnrichmentPipeline.run(scan_run_id, tenant_id)
│   All findings fetched again
│   All LLM calls made again (no caching in pipeline layer)
│   ScanLLMEnrichmentRepository.bulk_write_llm_fields(updates)
│       AQL: UPDATE u._key WITH u IN scan_findings OPTIONS {keepNull: false}
│       on_duplicate semantics: existing LLM fields OVERWRITTEN with new values (upsert)
│       [DB WRITE: scan_findings — idempotent upsert, no duplicates — AC-036]
│
│   ScanLLMEnrichmentRepository.write_token_usage(...)
│       [DB WRITE: scan_runs.llm_token_usage overwritten with new counts]
│
│   ScanLLMEnrichmentRepository.update_scan_run_status(scan_run_id, "llm_enriched")
│       [DB WRITE: scan_runs.status remains "llm_enriched"]
```

---

## UC-011-MAIN: Blast Radius — SCA Finding with purl, Dependents Found

**Type:** Requirement
**Source:** REQ-005 (UC-011)
**Trigger:** `scan_run.status == "llm_enriched"`
**Expected Outcome:** blast_radius_score, affected_components, blast_radius_path set; status = "blast_radius_computed"
**Coverage:** AC-037, AC-039, AC-040, AC-041, AC-042

```
[ENTRY: PipelineCoordinator after LLMEnrichmentPipeline completes]
│
PipelineCoordinator.run_post_ingest_pipeline()
│   current_status = self._get_run_status(scan_run_id)  # "llm_enriched"
│   current_status not in _BLAST_DONE → proceed
│
└─► src/complira_graph/ingestion/blast_radius_pipeline.py:BlastRadiusPipeline.run(scan_run_id, tenant_id)
        │
        ├─► ScanEnrichmentRepository.fetch_findings_for_run(scan_run_id, tenant_id, batch_size=500)
        │       [DB READ: scan_findings — all findings for run]
        │       Yields batches
        │
        ├─ Accumulate all findings in memory:
        │   purl_to_fingerprints: dict[str, list[str]] = {}
        │   no_purl_fingerprints: list[str] = []
        │   for finding in all_findings:
        │       purl = finding.get("purl")
        │       if purl:
        │           purl_to_fingerprints[purl].append(finding["_key"])
        │       else:
        │           no_purl_fingerprints.append(finding["_key"])
        │   [IN-MEMORY: group by unique purl]
        │
        ├─► ScanBlastRadiusRepository.aql_total_project_components(project_id=None)
        │       AQL: RETURN LENGTH(FOR c IN components FILTER LENGTH(FOR e IN 1..1 INBOUND c project_uses_component LIMIT 1 RETURN 1) > 0 RETURN 1)
        │       [DB READ: reference DB — components + project_uses_component]
        │       Returns: int (e.g. 120 total components)
        │       [STATE: total_components = 120]
        │
        ├─ For each unique purl (e.g. "pkg:npm/lodash@4.17.21"):
        │
        ├─► ScanBlastRadiusRepository.aql_blast_radius_for_purl("pkg:npm/lodash@4.17.21", depth_max=5)
        │       AQL:
        │           LET start = FIRST(FOR c IN components FILTER c.purl == @purl LIMIT 1 RETURN c)
        │           LET traversal = (
        │               start != null
        │               ? (FOR v, e, p IN 1..5 INBOUND start depends_on
        │                      RETURN DISTINCT {purl: v.purl, name: v.name, depth: LENGTH(p.edges)})
        │               : []
        │           )
        │           LET max_depth_row = FIRST(FOR row IN traversal SORT row.depth DESC LIMIT 1 RETURN row)
        │           RETURN {affected_purls: traversal[*].purl, affected_names: traversal[*].name,
        │                   max_depth: max_depth_row != null ? max_depth_row.depth : 0, found: start != null}
        │       [DB READ: reference DB — components + depends_on edges, INBOUND depth 1..5]
        │       Returns: {"affected_purls": ["pkg:npm/app@1.0.0", "pkg:npm/api@2.1.0"],
        │                  "affected_names": ["app", "api"], "max_depth": 2, "found": true}
        │
        ├─ Compute score:
        │   len_affected = len(traversal_result["affected_purls"])   # e.g. 2
        │   score = min(1.0, len_affected / max(total_components, 1))  # 2 / 120 = 0.0167
        │   [AC-041: formula confirmed]
        │
        ├─► BlastRadiusPipeline._build_blast_updates_for_purl(fingerprints, traversal_result, score)
        │       for fp in purl_to_fingerprints["pkg:npm/lodash@4.17.21"]:
        │           update_dict = {"_key": fp,
        │                          "blast_radius_score": 0.0167,
        │                          "affected_components": ["pkg:npm/app@1.0.0", "pkg:npm/api@2.1.0"],
        │                          "blast_radius_path": ["app", "api"],
        │                          "blast_radius_computed_at": utcnow()}
        │       [IN-MEMORY: one update per finding sharing this purl]
        │
        ├─ (after all purls processed, add zero-value updates for no-purl findings):
        │
        ├─► BlastRadiusPipeline._build_zero_blast_updates(no_purl_fingerprints)
        │       for fp in no_purl_fingerprints:
        │           update_dict = {"_key": fp, "blast_radius_score": 0.0,
        │                          "affected_components": [], "blast_radius_path": [],
        │                          "blast_radius_computed_at": utcnow()}
        │       [IN-MEMORY: AC-038 confirmed — SAST/IaC findings get score=0]
        │
        ├─► ScanBlastRadiusRepository.bulk_write_blast_radius(all_updates)
        │       Chunks at 500
        │       FOR u IN @updates
        │           UPDATE u._key WITH u IN scan_findings
        │           OPTIONS {keepNull: false}
        │       [DB WRITE: scan_findings — blast radius fields]
        │
        └─► ScanBlastRadiusRepository.update_scan_run_status(scan_run_id, "blast_radius_computed")
                self._db.collection("scan_runs").update({"_key": scan_run_id, "status": "blast_radius_computed", "blast_radius_computed_at": utcnow()})
                [DB WRITE: scan_runs.status = "blast_radius_computed"]
                [STATE MUTATION: scan_run transitions to blast_radius_computed]
```

---

## UC-011-NO-PURL: Blast Radius — SAST/IaC Finding with No purl

**Type:** Requirement
**Source:** REQ-005 (UC-011)
**Coverage:** AC-038

```
BlastRadiusPipeline.run(scan_run_id, tenant_id)
│
│   finding = {"_key": "abc123", "purl": null, "rule_id": "CWE-89", ...}
│   purl = finding.get("purl")   → None
│   no_purl_fingerprints.append("abc123")
│   [No AQL traversal for this finding — optimization: zero AQL round-trip]
│
BlastRadiusPipeline._build_zero_blast_updates(["abc123"])
│   update_dict = {"_key": "abc123", "blast_radius_score": 0.0,
│                  "affected_components": [], "blast_radius_path": [],
│                  "blast_radius_computed_at": utcnow()}
│   [IN-MEMORY TRANSFORM]
│
ScanBlastRadiusRepository.bulk_write_blast_radius([update_dict])
│   [DB WRITE: scan_findings — zeros written, no traversal needed — AC-038]
```

---

## UC-011-NO-EDGES: Blast Radius — purl Resolves but No depends_on Edges

**Type:** Requirement
**Source:** REQ-005 (UC-011)
**Coverage:** AC-037, AC-041 (denominator behavior when no dependents)

```
ScanBlastRadiusRepository.aql_blast_radius_for_purl("pkg:pypi/requests@2.28.0", depth_max=5)
│   AQL: start = FIRST(... FILTER c.purl == @purl ...) → returns component vertex (found=true)
│   traversal = (FOR v,e,p IN 1..5 INBOUND start depends_on ...) → empty list (no edges)
│   max_depth_row = null → max_depth = 0
│   Returns: {"affected_purls": [], "affected_names": [], "max_depth": 0, "found": true}
│
BlastRadiusPipeline.run():
│   len_affected = 0
│   score = min(1.0, 0 / max(total_components, 1)) = 0.0
│   [DECISION: score = 0.0 even though component is in DB — no dependents means no blast radius]
│
BlastRadiusPipeline._build_blast_updates_for_purl(fingerprints, traversal_result, score=0.0)
│   update_dict = {"_key": fp, "blast_radius_score": 0.0,
│                  "affected_components": [], "blast_radius_path": [],
│                  "blast_radius_computed_at": utcnow()}
│   [CORRECT BEHAVIOR: purl found but no edges → score=0, empty lists — not an error]
│
ScanBlastRadiusRepository.bulk_write_blast_radius(updates)
│   [DB WRITE: scan_findings — blast radius = 0]
```

---

## UC-011-IDEMPOTENT: Blast Radius — Re-run Same scan_run_id

**Type:** Requirement
**Source:** REQ-005 (UC-011)
**Coverage:** AC-043

```
PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id, force=True)
│   force=True bypasses _BLAST_DONE guard
│
BlastRadiusPipeline.run(scan_run_id, tenant_id)
│   Fetches same findings; same purls; same dependency graph state
│   aql_blast_radius_for_purl() → same traversal results (deterministic AQL, static graph)
│   score computation → identical values
│   ScanBlastRadiusRepository.bulk_write_blast_radius(updates)
│       AQL: UPDATE u._key WITH u IN scan_findings OPTIONS {keepNull: false}
│       Overwrites existing blast_radius_score with identical values
│       [DB WRITE: idempotent upsert — AC-043]
```

---

## UC-012-MAIN: EPSS Velocity — CVE with 30-day History, Trend Classified

**Type:** Requirement
**Source:** REQ-006 (UC-012)
**Trigger:** `scan_run.status == "blast_radius_computed"`
**Expected Outcome:** `epss_velocity` (slope), `epss_trend` ∈ {rising, stable, falling}; status = "velocity_computed"
**Coverage:** AC-044, AC-046, AC-047, AC-049

```
[ENTRY: PipelineCoordinator after BlastRadiusPipeline completes]
│
PipelineCoordinator.run_post_ingest_pipeline()
│   current_status = self._get_run_status(scan_run_id)  # "blast_radius_computed"
│   current_status not in _VELOCITY_DONE → proceed
│
└─► src/complira_graph/ingestion/epss_velocity_pipeline.py:EPSSVelocityPipeline.run(scan_run_id, tenant_id)
        │
        ├─► ScanEnrichmentRepository.fetch_findings_for_run(scan_run_id, tenant_id, batch_size=500)
        │       [DB READ: scan_findings — all findings for run]
        │
        ├─ Build mappings:
        │   cve_key_to_fingerprints: dict[str, list[str]] = {}
        │   no_cve_fingerprints: list[str] = []
        │   for finding in all_findings:
        │       cve_id = finding.get("cve_id")
        │       if cve_id:
        │           cve_key = normalize_cve_key(cve_id)   # "CVE-2024-1234" → "CVE_2024_1234"
        │           cve_key_to_fingerprints[cve_key].append(finding["_key"])
        │       else:
        │           no_cve_fingerprints.append(finding["_key"])
        │   [IN-MEMORY: group by unique CVE key]
        │
        ├─ Compute cutoff:
        │   cutoff_date = (datetime.now(utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        │   [IN-MEMORY: e.g. "2026-02-20"]
        │
        ├─► ScanEnrichmentRepository.aql_get_epss_history_batch(
        │       cve_keys=list(cve_key_to_fingerprints.keys()),
        │       cutoff_date="2026-02-20"
        │   )
        │       AQL:
        │           FOR cve_key IN @cve_keys
        │               LET cve_doc = DOCUMENT(CONCAT("vulnerabilities/", cve_key))
        │               LET history = (
        │                   cve_doc != null
        │                   ? (FOR e IN has_epss FILTER e._from == cve_doc._id
        │                          LET point = DOCUMENT(e._to)
        │                          FILTER point != null AND point.score_date >= @cutoff_date
        │                          SORT point.score_date ASC
        │                          RETURN {score: point.epss_score, date: point.score_date})
        │                   : []
        │               )
        │               RETURN {cve_key: cve_key, history: history}
        │       [DB READ: reference DB — vulnerabilities + has_epss edges + epss_history]
        │       Returns: {"CVE_2024_1234": [{"score": 0.042, "date": "2026-02-20"}, ..., {"score": 0.089, "date": "2026-03-22"}],
        │                  "CVE_2024_5678": [...]}
        │       [history_map: dict[cve_key, list[{"score", "date"}]]]
        │
        ├─ For each CVE key (e.g. "CVE_2024_1234"):
        │   history = history_map.get("CVE_2024_1234", [])  # 30 data points
        │
        ├─► EPSSVelocityPipeline._compute_slope(history)
        │       n = 30
        │       xs = [0, 1, 2, ..., 29]
        │       ys = [0.042, 0.043, ..., 0.089]
        │       mean_x = 14.5
        │       mean_y = ~0.065
        │       numerator   = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
        │       denominator = sum((xs[i] - mean_x) ** 2 for i in range(n))
        │       slope = numerator / denominator  → e.g. 0.0085 per day
        │       Returns: 0.0085
        │       [IN-MEMORY: pure Python, no numpy]
        │
        ├─► EPSSVelocityPipeline._classify_trend(slope=0.0085)
        │       weekly_delta = 0.0085 * 7 = 0.0595
        │       0.0595 > 0.05 → return "rising"
        │       [DECISION GATE: AC-046 — rising threshold confirmed]
        │
        ├─► EPSSVelocityPipeline._build_velocity_updates(fingerprints, slope=0.0085, trend="rising")
        │       for fp in cve_key_to_fingerprints["CVE_2024_1234"]:
        │           update_dict = {"_key": fp, "epss_velocity": 0.0085,
        │                          "epss_trend": "rising", "epss_velocity_computed_at": utcnow()}
        │       [IN-MEMORY TRANSFORM]
        │
        ├─ (after all CVEs processed, build zero updates for no-CVE findings):
        │
        ├─► EPSSVelocityPipeline._build_zero_velocity_updates(no_cve_fingerprints)
        │       for fp in no_cve_fingerprints:
        │           update_dict = {"_key": fp, "epss_velocity": 0.0, "epss_trend": "stable",
        │                          "epss_velocity_computed_at": utcnow()}
        │       [IN-MEMORY: AC-045 confirmed]
        │
        ├─► ScanEnrichmentRepository.bulk_update_findings(all_updates)
        │       AQL: FOR u IN @updates UPDATE u._key WITH u IN scan_findings OPTIONS {keepNull: false}
        │       Chunks at 500
        │       [DB WRITE: scan_findings — epss_velocity, epss_trend, epss_velocity_computed_at]
        │
        └─► ScanEnrichmentRepository.update_scan_run_status(scan_run_id, "velocity_computed")
                self._db.collection("scan_runs").update({"_key": scan_run_id, "status": "velocity_computed", ...})
                [DB WRITE: scan_runs.status = "velocity_computed"]
                [STATE MUTATION: Phase 2 pipeline complete]
```

---

## UC-012-INSUFFICIENT: EPSS Velocity — Fewer Than 2 Data Points

**Type:** Requirement
**Source:** REQ-006 (UC-012)
**Coverage:** AC-048

```
ScanEnrichmentRepository.aql_get_epss_history_batch(["CVE_2024_9999"], "2026-02-20")
│   Returns: {"CVE_2024_9999": [{"score": 0.031, "date": "2026-03-15"}]}
│   [Only 1 data point in 30-day window]
│
EPSSVelocityPipeline._compute_slope([{"score": 0.031, "date": "2026-03-15"}])
│   n = 1  →  n < 2  →  return 0.0
│   [DECISION GATE: insufficient history → slope = 0.0 — AC-048]
│
EPSSVelocityPipeline._classify_trend(0.0)
│   weekly_delta = 0.0 * 7 = 0.0
│   not > 0.05, not < -0.05  →  return "stable"
│
EPSSVelocityPipeline._build_velocity_updates(fingerprints, slope=0.0, trend="stable")
│   update_dict = {"_key": fp, "epss_velocity": 0.0, "epss_trend": "stable", ...}
│
ScanEnrichmentRepository.bulk_update_findings(updates)
│   [DB WRITE: scan_findings — stable trend with zero velocity — AC-048]
```

---

## UC-012-EMPTY-HISTORY: EPSS Velocity — epss_history Collection Empty

**Type:** Requirement
**Source:** REQ-006 (UC-012), Risk-3
**Coverage:** AC-048 (edge case: 0 data points)

```
ScanEnrichmentRepository.aql_get_epss_history_batch(cve_keys, cutoff_date)
│   AQL executes; cve_doc found, but has_epss edges return empty list (no EPSS agent run)
│   Returns: {"CVE_2024_1234": [], "CVE_2024_5678": []}
│   [No exception — empty history is valid, not an error]
│
EPSSVelocityPipeline.run():
│   for cve_key in cve_key_to_fingerprints:
│       history = history_map.get(cve_key, [])   # → []
│       slope = self._compute_slope([])
│           n = 0  →  n < 2  →  return 0.0
│       trend = self._classify_trend(0.0) → "stable"
│       updates → {"epss_velocity": 0.0, "epss_trend": "stable"}
│   [ALL FINDINGS GET stable — Risk-3 handled gracefully, not an error — AC-048]
│
ScanEnrichmentRepository.bulk_update_findings(all_updates)
│   [DB WRITE: scan_findings — all findings: velocity=0.0, trend=stable]
│
ScanEnrichmentRepository.update_scan_run_status(scan_run_id, "velocity_computed")
│   [DB WRITE: scan_runs.status = "velocity_computed" — pipeline completes normally]
```

---

## UC-012-NO-CVE: EPSS Velocity — Finding with No cve_id

**Type:** Requirement
**Source:** REQ-006 (UC-012)
**Coverage:** AC-045

```
EPSSVelocityPipeline.run(scan_run_id, tenant_id)
│
│   finding = {"_key": "def456", "cve_id": null, "rule_id": "CWE-79", ...}
│   cve_id = finding.get("cve_id") → None
│   no_cve_fingerprints.append("def456")
│   [No EPSS lookup for this finding — no AQL round-trip needed]
│
EPSSVelocityPipeline._build_zero_velocity_updates(["def456"])
│   update_dict = {"_key": "def456", "epss_velocity": 0.0, "epss_trend": "stable",
│                  "epss_velocity_computed_at": utcnow()}
│   [AC-045: velocity=0.0, trend=stable for non-CVE findings]
│
ScanEnrichmentRepository.bulk_update_findings([update_dict])
│   [DB WRITE: scan_findings — zero velocity + stable for non-CVE finding]
```

---

## UC-012-IDEMPOTENT: EPSS Velocity — Re-run Same scan_run_id

**Type:** Requirement
**Source:** REQ-006 (UC-012)
**Coverage:** AC-050

```
PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id, force=True)
│   force=True bypasses _VELOCITY_DONE guard
│
EPSSVelocityPipeline.run(scan_run_id, tenant_id)
│   Fetches same findings; same CVE keys; same epss_history data (deterministic)
│   aql_get_epss_history_batch() → identical time series
│   _compute_slope() → identical slope (deterministic algorithm)
│   _classify_trend() → identical trend
│   ScanEnrichmentRepository.bulk_update_findings(updates)
│       AQL: UPDATE u._key WITH u IN scan_findings OPTIONS {keepNull: false}
│       Overwrites existing values with identical values
│       [DB WRITE: idempotent — AC-050]
```

---

## UC-CROSS-CHAIN: Full Phase 2 Chain — mapped → velocity_computed

**Type:** Requirement
**Source:** REQ-004, REQ-005, REQ-006 (AC-051)
**Coverage:** AC-051

```
[ENTRY: scan ingest completes; scan_run.status = "mapped"]
│
PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
│
│   ─── Phase 1 stages already complete ─────────────────────────────────
│   current_status = "mapped"
│   _ENRICHMENT_DONE check → skip EnrichmentPipeline
│   _COMPACTION_DONE check → skip CompactionPipeline
│   _MAPPING_DONE check    → skip ControlMappingPipeline
│   ─────────────────────────────────────────────────────────────────────
│
│   ─── Phase 2 Stage 4: LLM Enrichment ──────────────────────────────────
│   # current_status = "completed" (single read at top — Phase 1 pattern)
│   # "completed" not in _LLM_DONE → proceed
│   LLMEnrichmentPipeline.run(scan_run_id, tenant_id)
│   → scan_run.status = "llm_enriched"
│   ─────────────────────────────────────────────────────────────────────
│
│   ─── Phase 2 Stage 5: Blast Radius ─────────────────────────────────────
│   # current_status still = "completed" (no re-read — same single-read pattern)
│   # "completed" not in _BLAST_DONE → proceed
│   BlastRadiusPipeline.run(scan_run_id, tenant_id)
│   → scan_run.status = "blast_radius_computed"
│   ─────────────────────────────────────────────────────────────────────
│
│   ─── Phase 2 Stage 6: EPSS Velocity ────────────────────────────────────
│   # current_status still = "completed" (no re-read)
│   # "completed" not in _VELOCITY_DONE → proceed
│   EPSSVelocityPipeline.run(scan_run_id, tenant_id)
│   → scan_run.status = "velocity_computed"
│   ─────────────────────────────────────────────────────────────────────
│
│   Pipeline complete. No return value (fire-and-forget BackgroundTask).
│   [STATE MUTATION: scan_run chain complete: mapped → llm_enriched → blast_radius_computed → velocity_computed]
│   [AC-051: automatic chain, no manual intervention required]
```

---

## UC-CROSS-RETRIGGER: Manual Re-trigger from Intermediate Phase 2 Status

**Type:** Requirement
**Source:** REQ-004–006 (AC-052)
**Coverage:** AC-052

```
[ENTRY: POST /v1/scans/{scan_run_id}/enrich]
│
src/api/routes/pipeline.py:trigger_enrich(scan_run_id, tenant_id)
│   Validates scan_run exists and belongs to tenant
│   Checks: scan_run.status ∈ _RETRIABLE_STATUSES
│   "blast_radius_computed" ∈ _RETRIABLE_STATUSES (AC-052 + Risk-4 covered)
│   BackgroundTask: coordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
│
PipelineCoordinator.run_post_ingest_pipeline(scan_run_id, tenant_id)
│   current_status = self._get_run_status(scan_run_id)   # single read at top → "blast_radius_computed"
│   "blast_radius_computed" ∈ _RETRIABLE_STATUSES → proceed
│
│   Phase 1 guards (use initial current_status = "blast_radius_computed"):
│       _ENRICHMENT_DONE includes "blast_radius_computed" → skip EnrichmentPipeline
│       _COMPACTION_DONE includes "blast_radius_computed" → skip CompactionPipeline
│       _MAPPING_DONE includes "blast_radius_computed" → skip ControlMappingPipeline
│   Phase 2 Stage 4 guard (same current_status): "blast_radius_computed" ∈ _LLM_DONE → skip LLMEnrichmentPipeline
│   Phase 2 Stage 5 guard (same current_status): "blast_radius_computed" ∈ _BLAST_DONE → skip BlastRadiusPipeline
│   Phase 2 Stage 6 guard (same current_status): "blast_radius_computed" ∉ _VELOCITY_DONE → RUN EPSSVelocityPipeline
│
│   EPSSVelocityPipeline.run(scan_run_id, tenant_id)
│   → scan_run.status = "velocity_computed"
│   [PARTIAL RE-TRIGGER: only missing stage runs — AC-052 confirmed]
│
│   [ALSO VALID for status = "mapped" → runs all 3 Phase 2 stages]
│   [ALSO VALID for status = "llm_enriched" → runs blast radius + velocity stages]
│   [ALSO VALID for status = "pipeline_failed" → re-runs from Phase 1 beginning with force]
```

---

## UC-CROSS-PARTIAL-FAIL-ISO: Phase 2 Stage Fails; Partial Writes Retained

**Type:** Requirement
**Source:** REQ-004–006 (AC-053)
**Coverage:** AC-053

```
PipelineCoordinator.run_post_ingest_pipeline()
│
│   LLMEnrichmentPipeline.run() → raises RuntimeError("all_llm_batches_failed")
│   except Exception as exc:
│       log.exception("pipeline_coordinator.llm_enrichment_failed")
│       self._mark_failed(scan_run_id, str(exc))
│           [DB WRITE: scan_runs.status = "pipeline_failed", error_message = "all_llm_batches_failed"]
│       return   ← pipeline stops here
│
│   [ISOLATION: BlastRadiusPipeline and EPSSVelocityPipeline NOT called]
│   [PARTIAL WRITES RETAINED:
│       - scan_findings documents already written by LLMEnrichmentPipeline (for successful sub-batches)
│         are retained in DB — AC-053
│       - blast_radius fields: not yet written (no partial blast radius in this failure)
│       - velocity fields: not yet written]
│
│   [RECOVERY: POST /enrich with status "pipeline_failed" ∈ _RETRIABLE_STATUSES
│       → coordinator re-runs with force=True; starts from Phase 1 checks
│       → Phase 1 all done; Phase 2 LLM re-runs with idempotent writes]
```

---

## UC-CROSS-TENANT: All Phase 2 Reads and Writes Include tenant_id Scoping

**Type:** Requirement
**Source:** REQ-004–006 (AC-054)
**Coverage:** AC-054

```
All three Phase 2 pipeline stages receive (scan_run_id, tenant_id) as parameters.

ScanEnrichmentRepository.fetch_findings_for_run(scan_run_id, tenant_id, batch_size)
│   AQL: FOR f IN scan_findings FILTER f.scan_run_id == @scan_run_id AND f.tenant_id == @tenant_id
│   [tenant_id in FILTER: AC-054 confirmed for all Phase 2 reads]

ScanLLMEnrichmentRepository.bulk_write_llm_fields(updates)
│   updates[i]["_key"] is fingerprint = hash(tenant_id, cve_id, file_path, ...)
│   AQL: UPDATE u._key WITH u IN scan_findings
│   [_key is tenant-scoped via fingerprint derivation — AC-054]

ScanLLMEnrichmentRepository.write_token_usage(scan_run_id, ...)
│   Updates scan_runs by _key = scan_run_id (UUID scoped to one tenant's run)
│   [tenant isolation: scan_run_id is unique per run, not shared across tenants]

ScanBlastRadiusRepository.aql_blast_radius_for_purl(purl)
│   Reference DB traversal (components, depends_on) is cross-tenant but component data
│   is global (purl-keyed). Score normalization uses project_uses_component which is
│   filtered by project_id (tenant-scoped edge). No cross-tenant data bleed.
│   [AC-054: traversal uses shared graph but score computation is tenant-scoped]

ScanBlastRadiusRepository.bulk_write_blast_radius(updates)
│   _key is tenant-scoped fingerprint  →  no cross-tenant writes
│   [AC-054 confirmed]

ScanEnrichmentRepository.aql_get_epss_history_batch(cve_keys, cutoff_date)
│   Reference DB read (vulnerabilities, epss_history) — shared but read-only, no PII.
│   [AC-054: EPSS data is public, cross-CVE, not per-tenant — no tenant isolation needed here]

ScanEnrichmentRepository.bulk_update_findings(velocity_updates)
│   _key is tenant-scoped fingerprint  →  writes go to correct tenant's scan_findings only
│   [AC-054 confirmed]
```

---

## UC-DR-LLM-PROMPT: LLM Prompt — Non-CVE Context Construction

**Type:** Design-Risk
**Technical Objective:** Verify that `_context_for_finding()` and `_build_user_prompt()` correctly distinguish CVE vs non-CVE findings and that the LLM receives a valid, well-formed prompt in both cases. Risk: incorrect key mapping or missing fallback could cause LLM to receive insufficient context, producing low-quality outputs for SAST/IaC findings.
**Expected Observable Outcome:** For CVE findings, prompt includes `cve_id + severity + package_name`. For non-CVE, prompt includes `rule_id + severity` with `cve_id=null`. Claude Haiku returns a coherent attack surface classification and risk summary in both cases.

```
LLMEnrichmentPipeline.run(scan_run_id, tenant_id)
│
│   sub_batch = [
│       {"_key": "f1", "cve_id": "CVE-2024-1234", "severity": "HIGH", "package_name": "log4j", "cvss_base": 9.8},
│       {"_key": "f2", "cve_id": null, "rule_id": "semgrep.sql-injection", "severity": "MEDIUM"}
│   ]
│
│   for f in sub_batch:
│       context = self._context_for_finding(f)
│
│   f1 → _context_for_finding:
│       cve_id is not None → return {"finding_key": "f1", "cve_id": "CVE-2024-1234",
│                                     "severity": "HIGH", "package_name": "log4j", "cvss_base": 9.8}
│
│   f2 → _context_for_finding:
│       cve_id is None → return {"finding_key": "f2", "rule_id": "semgrep.sql-injection",
│                                 "severity": "MEDIUM", "cve_id": null}
│
│   PipelineLLMClient._build_user_prompt(context_batch)
│       Serializes as JSON array:
│       [
│           {"finding_key":"f1","cve_id":"CVE-2024-1234","severity":"HIGH","package_name":"log4j","cvss_base":9.8},
│           {"finding_key":"f2","rule_id":"semgrep.sql-injection","severity":"MEDIUM","cve_id":null}
│       ]
│       [DESIGN RISK CHECK: both findings have enough context — CVE or rule_id path complete]
│
│   PipelineLLMClient.call_batch(context_batch)
│       system_prompt → instructs Claude to return JSON array with finding_key, risk_summary, remediation, attack_surface
│       user_prompt   → the serialized batch above
│       Anthropic API call → response
│       _parse_response() → [{"finding_key":"f1",...}, {"finding_key":"f2",...}]
│       [EXPECTED OUTCOME: both entries have attack_surface ∈ {network,local,adjacent} and non-empty summaries]
│
│   _build_llm_updates:
│       f1 → llm_attack_surface from CVSS AV vector (Claude derives from cvss_base context)
│       f2 → llm_attack_surface inferred from rule semantics (SQL injection → "local" or "network")
│       [DESIGN RISK RESOLVED: non-CVE findings receive coherent LLM output via rule_id fallback]
```

---

## UC-DR-BLAST-DEDUP: Blast Radius — purl Deduplication Optimization

**Type:** Design-Risk
**Technical Objective:** Verify that BlastRadiusPipeline deduplicates findings by purl before issuing AQL traversals. A scan run of 2000 findings may have only 50 unique purls. Without deduplication, 2000 AQL round-trips would be issued. Design requires grouping by purl before traversal.
**Expected Observable Outcome:** For N findings sharing the same purl, exactly 1 AQL traversal call is issued. Score and path are applied to all N findings from the single traversal result.

```
BlastRadiusPipeline.run(scan_run_id, tenant_id)
│
│   all_findings = [
│       {"_key": "f1", "purl": "pkg:npm/lodash@4.17.21", ...},
│       {"_key": "f2", "purl": "pkg:npm/lodash@4.17.21", ...},   # same purl
│       {"_key": "f3", "purl": "pkg:npm/lodash@4.17.21", ...},   # same purl
│       {"_key": "f4", "purl": "pkg:pypi/requests@2.28.0", ...},
│       {"_key": "f5", "purl": null, ...},                         # SAST
│   ]
│
│   Build purl_to_fingerprints:
│       "pkg:npm/lodash@4.17.21" → ["f1", "f2", "f3"]
│       "pkg:pypi/requests@2.28.0" → ["f4"]
│   no_purl_fingerprints: ["f5"]
│
│   unique_purls = list(purl_to_fingerprints.keys())  # 2 purls
│
│   Loop: for purl in unique_purls:   # 2 iterations only (not 4 or 5)
│
│       Iteration 1: purl = "pkg:npm/lodash@4.17.21"
│           aql_blast_radius_for_purl("pkg:npm/lodash@4.17.21") → 1 AQL round-trip
│           traversal_result = {"affected_purls": [...], ...}
│           score = computed
│           _build_blast_updates_for_purl(["f1","f2","f3"], traversal_result, score)
│               → 3 update dicts (f1, f2, f3 all get identical blast_radius_score/path)
│           [OPTIMIZATION: 1 AQL call for 3 findings — Design-Risk confirmed resolved]
│
│       Iteration 2: purl = "pkg:pypi/requests@2.28.0"
│           aql_blast_radius_for_purl("pkg:pypi/requests@2.28.0") → 1 AQL round-trip
│           → 1 update dict (f4)
│
│   _build_zero_blast_updates(["f5"]) → 1 zero update dict
│
│   Total AQL traversal calls: 2  (not 4)
│   Total DB write: 1 bulk call with 5 update dicts
│   [EXPECTED OUTCOME: O(unique_purls) AQL calls, not O(findings)]
```

---

## Requirement Coverage Summary

| Requirement | Use Cases Covering | Primary ✓ | Fallback ✓ | Error ✓ |
|---|---|---|---|---|
| REQ-004 (UC-010) | UC-010-MAIN, UC-010-NONCVE, UC-010-PARTIAL-FAIL, UC-010-ALL-FAIL, UC-010-IDEMPOTENT | ✓ | ✓ | ✓ |
| REQ-005 (UC-011) | UC-011-MAIN, UC-011-NO-PURL, UC-011-NO-EDGES, UC-011-IDEMPOTENT | ✓ | ✓ | N/A |
| REQ-006 (UC-012) | UC-012-MAIN, UC-012-INSUFFICIENT, UC-012-EMPTY-HISTORY, UC-012-NO-CVE, UC-012-IDEMPOTENT | ✓ | ✓ | N/A |
| Cross-cutting | UC-CROSS-CHAIN, UC-CROSS-RETRIGGER, UC-CROSS-PARTIAL-FAIL-ISO, UC-CROSS-TENANT | ✓ | N/A | ✓ |

---

## AC Coverage Summary

| AC Range | Covered by Use Cases |
|---|---|
| AC-029–AC-036 (UC-010) | UC-010-MAIN (AC-029,030,031,033,035), UC-010-NONCVE (AC-032), UC-010-PARTIAL-FAIL (AC-034), UC-010-IDEMPOTENT (AC-036) |
| AC-037–AC-043 (UC-011) | UC-011-MAIN (AC-037,039,040,041,042), UC-011-NO-PURL (AC-038), UC-011-IDEMPOTENT (AC-043) |
| AC-044–AC-050 (UC-012) | UC-012-MAIN (AC-044,046,047,049), UC-012-INSUFFICIENT (AC-048), UC-012-NO-CVE (AC-045), UC-012-IDEMPOTENT (AC-050) |
| AC-051–AC-054 (Cross) | UC-CROSS-CHAIN (AC-051), UC-CROSS-RETRIGGER (AC-052), UC-CROSS-PARTIAL-FAIL-ISO (AC-053), UC-CROSS-TENANT (AC-054) |

**All 26 ACs (AC-029–AC-054) are covered.**
