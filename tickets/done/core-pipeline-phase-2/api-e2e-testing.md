# API/E2E Testing: Core Pipeline Phase 2

**Ticket:** `core-pipeline-phase-2`
**Stage:** 7 — API/E2E Test Implementation + Gate
**Date:** 2026-03-22

---

## Environment Feasibility Notes

The Phase 2 pipeline is a backend ingestion pipeline, not an HTTP API layer. External boundaries:

- **Anthropic Claude API** — requires `ANTHROPIC_API_KEY` secret; not available in CI/unit context
- **ArangoDB** — requires live ArangoDB; not available in CI/unit context

**Compensating evidence strategy:** All scenarios are implemented as component-level integration tests with realistic mock data injected at the external boundary (`PipelineLLMClient._client`, `db.aql.execute`, `db.collection`). This provides contract-level validation of:

- Input → processing → output field shapes
- Status transitions (written calls, payloads verified)
- Error isolation and failure propagation
- Idempotency guards (skip logic verified)
- Cross-stage chain behavior

No scenario is marked Waived. All 26 ACs are directly exercised by the scenarios below.

**Test file:** `tests/e2e/ingestion/test_phase2_pipeline_e2e.py`

---

## Acceptance Criteria Matrix

| AC-ID | Criterion | Mapped Scenario(s) | Execution Status |
|---|---|---|---|
| AC-029 | Risk summary populated | S-UC010-01 | Passed |
| AC-030 | Remediation populated | S-UC010-01 | Passed |
| AC-031 | Attack surface classified | S-UC010-01, S-UC010-07 | Passed |
| AC-032 | Non-CVE findings handled | S-UC010-02 | Passed |
| AC-033 | Status → `llm_enriched` | S-UC010-01 | Passed |
| AC-034 | LLM failure isolation | S-UC010-03, S-UC010-04 | Passed |
| AC-035 | Haiku model + token usage | S-UC010-05 | Passed |
| AC-036 | LLM enrichment idempotent | S-UC010-06 | Passed |
| AC-037 | Blast radius for SCA findings | S-UC011-01 | Passed |
| AC-038 | No-purl findings: zero score | S-UC011-02 | Passed |
| AC-039 | Affected components list | S-UC011-01 | Passed |
| AC-040 | Propagation path returned | S-UC011-01 | Passed |
| AC-041 | Score formula + clamp | S-UC011-03, S-UC011-04 | Passed |
| AC-042 | Status → `blast_radius_computed` | S-UC011-01 | Passed |
| AC-043 | Blast radius idempotent | S-UC011-05 | Passed |
| AC-044 | Velocity for CVE findings | S-UC012-01 | Passed |
| AC-045 | No-CVE findings: zero velocity | S-UC012-02 | Passed |
| AC-046 | Rising threshold | S-UC012-03 | Passed |
| AC-047 | Falling threshold | S-UC012-04 | Passed |
| AC-048 | Insufficient history | S-UC012-05 | Passed |
| AC-049 | Status → `velocity_computed` | S-UC012-01 | Passed |
| AC-050 | Velocity idempotent | S-UC012-06 | Passed |
| AC-051 | Full pipeline chain | S-CROSS-01 | Passed |
| AC-052 | Manual re-trigger | S-CROSS-02 | Passed |
| AC-053 | Stage failure isolation | S-CROSS-03 | Passed |
| AC-054 | tenant_id scoping | S-CROSS-04 | Passed |

---

## Scenario Registry

### UC-010 LLM Enrichment Scenarios

| Scenario ID | AC IDs | Requirement | Use Case | Source | Level | Expected Outcome | Result |
|---|---|---|---|---|---|---|---|
| S-UC010-01 | AC-029, AC-030, AC-031, AC-033 | REQ-004 | UC-010-MAIN | Requirement | Component-Integration | All CVE findings receive llm_risk_summary, llm_remediation, llm_attack_surface; status=llm_enriched | Passed |
| S-UC010-02 | AC-032 | REQ-004 | UC-010-NONCVE | Requirement | Component-Integration | Non-CVE finding (no cve_id) receives LLM output using rule_id+severity; no skip | Passed |
| S-UC010-03 | AC-034 | REQ-004 | UC-010-PARTIAL-FAIL | Requirement | Component-Integration | One batch fails; other batches succeed; partial writes retained; no RuntimeError | Passed |
| S-UC010-04 | AC-034 | REQ-004 | UC-010-ALL-FAIL | Requirement | Component-Integration | All batches fail; RuntimeError("all_llm_batches_failed") raised; coordinator sets pipeline_failed | Passed |
| S-UC010-05 | AC-035 | REQ-004 | UC-010-MAIN | Requirement | Component-Integration | Token usage written to scan_run; model field = haiku model name | Passed |
| S-UC010-06 | AC-036 | REQ-004 | UC-010-IDEMPOTENT | Requirement | Component-Integration | bulk_write uses UPDATE semantics (upsert); second run writes over first without duplication | Passed |
| S-UC010-07 | AC-031 | REQ-004 | UC-010-MAIN | Design-Risk | Component-Integration | attack_surface uppercase normalized; invalid value defaults to "network" | Passed |

### UC-011 Blast Radius Scenarios

| Scenario ID | AC IDs | Requirement | Use Case | Source | Level | Expected Outcome | Result |
|---|---|---|---|---|---|---|---|
| S-UC011-01 | AC-037, AC-039, AC-040, AC-042 | REQ-005 | UC-011-MAIN | Requirement | Component-Integration | SCA finding with purl: blast_radius_score computed, affected_components list populated, blast_radius_path populated, status=blast_radius_computed | Passed |
| S-UC011-02 | AC-038 | REQ-005 | UC-011-NO-PURL | Requirement | Component-Integration | Findings with no purl: blast_radius_score=0.0, affected_components=[], blast_radius_path=[] | Passed |
| S-UC011-03 | AC-041 | REQ-005 | UC-011-MAIN | Requirement | Component-Integration | Score = len(affected_purls) / max(total_components, 1) | Passed |
| S-UC011-04 | AC-041 | REQ-005 | UC-011-MAIN | Design-Risk | Component-Integration | Score clamped to 1.0 when affected > total | Passed |
| S-UC011-05 | AC-043 | REQ-005 | UC-011-IDEMPOTENT | Requirement | Component-Integration | Re-run produces identical update payloads (same purl → same traversal result) | Passed |

### UC-012 EPSS Velocity Scenarios

| Scenario ID | AC IDs | Requirement | Use Case | Source | Level | Expected Outcome | Result |
|---|---|---|---|---|---|---|---|
| S-UC012-01 | AC-044, AC-049 | REQ-006 | UC-012-MAIN | Requirement | Component-Integration | CVE findings get epss_velocity (float), epss_trend, epss_velocity_computed_at; status=velocity_computed | Passed |
| S-UC012-02 | AC-045 | REQ-006 | UC-012-NO-CVE | Requirement | Component-Integration | Findings with no cve_id: epss_velocity=0.0, epss_trend="stable" | Passed |
| S-UC012-03 | AC-046 | REQ-006 | UC-012-MAIN | Requirement | Component-Integration | Rising history (slope*7 > 0.05): epss_trend="rising" | Passed |
| S-UC012-04 | AC-047 | REQ-006 | UC-012-MAIN | Requirement | Component-Integration | Falling history (slope*7 < -0.05): epss_trend="falling" | Passed |
| S-UC012-05 | AC-048 | REQ-006 | UC-012-INSUFFICIENT | Requirement | Component-Integration | Fewer than 2 data points: epss_velocity=0.0, epss_trend="stable" | Passed |
| S-UC012-06 | AC-050 | REQ-006 | UC-012-IDEMPOTENT | Requirement | Component-Integration | Same epss_history → same velocity + trend on re-run | Passed |

### Cross-Cutting Scenarios

| Scenario ID | AC IDs | Requirement | Use Case | Source | Level | Expected Outcome | Result |
|---|---|---|---|---|---|---|---|
| S-CROSS-01 | AC-051 | REQ-004/005/006 | UC-CROSS-CHAIN | Requirement | Component-Integration | Coordinator from status="mapped" runs all three Phase 2 stages in sequence; final status="velocity_computed" | Passed |
| S-CROSS-02 | AC-052 | REQ-004/005/006 | UC-CROSS-RETRIGGER | Requirement | Component-Integration | status="llm_enriched": skips LLM, runs blast+velocity; status="blast_radius_computed": skips LLM+blast, runs velocity only | Passed |
| S-CROSS-03 | AC-053 | REQ-004/005/006 | UC-CROSS-PARTIAL-FAIL | Requirement | Component-Integration | LLM stage exception: status=pipeline_failed; downstream stages not called | Passed |
| S-CROSS-04 | AC-054 | REQ-004/005/006 | UC-TENANT | Requirement | Component-Integration | tenant_id passed through to fetch_findings_for_run on every stage | Passed |

---

## Feasibility / Infeasibility Notes

No scenarios are blocked. All 26 ACs exercised through component-integration testing. Live ArangoDB and Anthropic API are not available; boundary mocks provide contract validation. No user waiver required.

**Residual risk:** Full integration with live ArangoDB + Anthropic API is not covered here. This should be addressed in a future integration test environment.

---

## Stage 7 Gate Decision

All 26 acceptance criteria mapped to at least one executable scenario. All scenarios **Passed**.

**Stage 7 Gate: PASS**
