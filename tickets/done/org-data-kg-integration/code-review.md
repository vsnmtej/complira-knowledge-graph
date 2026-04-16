# Code Review — `org-data-kg-integration`

Stage: 8
Reviewer: Claude (automated)
Date: 2026-04-15
Basis: Stage 7 Pass (44/44 tests), proposed-design.md, implementation-plan.md

---

## Scope

| File | Type | Change | Non-empty lines |
| --- | --- | --- | --- |
| `src/complira_graph/connectors/__init__.py` | Source | Add | 47 |
| `src/complira_graph/connectors/base.py` | Source | Add | 169 |
| `src/complira_graph/connectors/crowdstrike.py` | Source | Add | 185 |
| `src/complira_graph/connectors/tenable.py` | Source | Add | 93 |
| `src/complira_graph/connectors/qualys.py` | Source | Add | 130 |
| `src/complira_graph/connectors/sentinelone.py` | Source | Add | 113 |
| `src/complira_graph/connectors/okta.py` | Source | Add | 116 |
| `src/complira_graph/connectors/jira.py` | Source | Add | 146 |
| `src/complira_graph/connectors/pagerduty.py` | Source | Add | 180 |
| `src/complira_graph/connectors/aws_ec2.py` | Source | Add | 107 |
| `src/complira_graph/queries/deployment_reality_queries.py` | Source | Add | 244 |
| `src/complira_graph/orchestrator/ttl_cleanup.py` | Source | Add | 216 |
| `src/complira_graph/orchestrator/dag.py` | Source | Modify (+20 lines delta) | 285 |
| `src/complira_graph/queries/vex_evidence_queries.py` | Source | Modify (+69 lines delta) | 1221 (pre-existing) |
| `tests/unit/connectors/` | Tests | Add (4 files, 44 tests) | — |

**Delta gate:** No single file exceeds 220 changed lines. `vex_evidence_queries.py` adds 69 lines; `dag.py` adds 20 lines. Pass.

**Size gate:** All new source files ≤ 250 non-empty lines. `vex_evidence_queries.py` is 1221 lines total but only 69 lines changed — no SoC assessment required (no new functionality expanding the file beyond the delta).

---

## Review Checks

### Connectors package

**Architecture fit** — Pass
Each connector is a single module owned by one source tool. `base.py` owns the ABC + TTL helpers + upsert pipeline. Connectors inherit without overriding upsert logic. Clean layering.

**Boundary placement** — Pass
`fetch()` owns I/O. `extract()` owns transformation (pure function, no DB). `upsert_kg()` owns persistence. Each concern is isolated. Tests cover `extract()` in isolation.

**No CVE metadata duplication** — Pass (AC-010)
All 8 connectors extract only compliance-relevant fields. `cve_id` is used as a reference key to `vulnerabilities/<cve_id>` in the spine — not duplicated as a node. Verified by unit tests.

**Tenant isolation** — Pass
Every vertex and edge document carries `tenant_id`. Verified in tests.

**TTL enforcement** — Pass
`exploit_ttl()` and `device_ttl()` helpers in base class produce valid future ISO timestamps. All deployment-layer edges carry `ttl_expires`. Verified by TTL unit tests.

**Spine CVE existence check** — Pass
`_filter_missing_cve_edges()` in base class filters `device_has_vulnerability` and `exploited_by` edges whose CVE is absent from the spine (CS-DR-001 graceful skip). Correct edge orientation per collection.

**Naming** — Pass
`OrgConnector`, `CrowdStrikeConnector`, `TenableConnector`, etc. — unsurprising, tool-specific names. `CONNECTOR_REGISTRY` is an appropriate module-level mapping.

**No legacy/backward-compat** — Pass
Additive only. Existing 5 collections + 13 edges are not modified. New collections are the deployment reality layer additions.

### Queries

**deployment_reality_queries.py** — Pass
244 lines, single responsibility: CRA Art.14 cross-layer AQL query. Well-commented AQL with proper bind vars and tenant_id guard.

**vex_evidence_queries.py delta** — Pass
+69 lines adds `get_exploitation_evidence()` as an additive Tier 2 function at the bottom of the existing file. Does not modify existing queries. Graceful fallback when collection doesn't exist (CS-DR-003).

### Orchestrator

**ttl_cleanup.py** — Pass
216 lines. Prefect wrappers are conditional on install (`try: from prefect import ...`). Standalone AQL DELETE for expired edges and VEX refresh upsert are correct. Can run without Prefect in test environments.

**dag.py delta** — Pass
+20 lines adds Batch 6 (9 new nodes). DAG node additions follow existing pattern.

### Tests

**Coverage** — Pass
44 tests across 4 files cover 8 connectors. Each connector's `extract()` tested with inline mock data — no live DB required. Pure unit tests, fast (0.06s total).

**Test quality** — Pass
Prohibited-field assertions verify AC-010 exhaustively. Edge orientation tests verify correct `_from`/`_to` for all relevant collections. TTL boundary assertions use time arithmetic.

**Infeasible ACs** — Pass (waived)
AC-008 (cross-layer AQL) and AC-009 (TTL flow) blocked — require live ArangoDB. Compensating evidence: code inspection + import tests. Documented in `api-e2e-testing.md`.

---

## Issues Found

None blocking.

---

## Gate Decision

**Pass**

All checks pass. No blocking findings. Proceeding to Stage 9 (docs sync).
