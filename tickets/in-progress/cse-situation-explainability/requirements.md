# Requirements — cse-situation-explainability

**Status:** Design-ready  
**Scope:** Small  
**Branch:** codex/cse-situation-explainability  
**Parent ticket:** cse-engine-accuracy-explainability (C-19, C-20 deferred items)

---

## Goal / Problem Statement

The `cse-engine-accuracy-explainability` ticket writes chain narratives, counterfactuals,
and audit trails to ArangoDB after every simulation run. However, the Situation Room CISO
and Board personas do not yet surface this data — they still show raw numeric metrics with
no explanation of what drove them.

Two deferred change items need wiring:

**C-19:** `threat_category_explanations` in CISO Situation view  
For each threat category (e.g. "Remote code execution, 85% breach probability"), explain:
- Which simulation events drove this probability
- What round was the turning point
- Which defender actions were effective vs. ineffective
- What one change would reduce this category's risk

**C-20:** `exposure_derivation` in Board Situation view  
For the financial exposure figure ($1.2M–$5.1M), explain:
- Plain-English derivation narrative (no CVE IDs)
- How many chains contributed to the TEF estimate
- Which chain type had highest confidence
- What investment in which control would reduce exposure most

---

## In-Scope Use Cases

| ID | Use Case |
|----|----------|
| UC-01 | `compute_ciso()` returns `threat_category_explanations` populated from `attack_chain_findings.explanation` |
| UC-02 | `compute_board()` returns `exposure_derivation` populated from `simulation_runs.counterfactuals` |
| UC-03 | `GET /v1/situation/ciso` response includes `threat_category_explanations` (optional, not null when data exists) |
| UC-04 | `GET /v1/situation/board` response includes `exposure_derivation` (optional, not null when data exists) |
| UC-05 | Situation Room frontend renders explanation text under each threat category card |
| UC-06 | Situation Room frontend renders exposure derivation narrative in Board persona |

---

## Acceptance Criteria

| ID | Criterion | Verifiable Outcome |
|----|-----------|-------------------|
| AC-01 | `CISOSituation.threat_category_explanations` field exists in model | `situation/models.py` has `threat_category_explanations: list[ThreatCategoryExplanation]` |
| AC-02 | `ThreatCategoryExplanation` has required fields | Model has: `bucket_name`, `driving_events`, `turning_point_round`, `effective_defender_actions`, `what_would_have_helped` |
| AC-03 | `BoardSituation.exposure_derivation` field exists in model | `situation/models.py` has `exposure_derivation: ExposureDerivation \| None` |
| AC-04 | `ExposureDerivation` has required fields | Model has: `narrative`, `contributing_chains`, `highest_confidence_chain`, `investment_recommendation` |
| AC-05 | `compute_ciso()` populates explanations from graph data | Unit test: mock AQL returns chain narratives → `threat_category_explanations` non-empty |
| AC-06 | `compute_board()` populates derivation from counterfactuals | Unit test: mock AQL returns counterfactuals → `exposure_derivation.narrative` non-empty |
| AC-07 | `GET /v1/situation/ciso` returns `threat_category_explanations` array | API returns field (empty list when no simulation run, populated after run) |
| AC-08 | `GET /v1/situation/board` returns `exposure_derivation` object | API returns field (null when no simulation run, populated after run) |
| AC-09 | Frontend CISO card renders `what_would_have_helped` text | Situation Room shows explanation under each threat category |
| AC-10 | Frontend Board card renders `exposure_derivation.narrative` | Situation Room shows plain-English exposure explanation |
| AC-11 | Empty/null when no simulation has run | Both fields gracefully absent when `threat_category_rollups` is empty |
| AC-12 | No CVE IDs in any explanation text | Existing SituationAbstractionLayer persona boundary enforced |

---

## Change Items

| ID | File | Change |
|----|------|--------|
| C-01 | `situation/models.py` | Add `ThreatCategoryExplanation` dataclass + `ExposureDerivation` dataclass |
| C-02 | `situation/models.py` | Add `threat_category_explanations: list[ThreatCategoryExplanation]` to `CISOSituation` |
| C-03 | `situation/models.py` | Add `exposure_derivation: ExposureDerivation \| None` to `BoardSituation` |
| C-04 | `situation/abstraction_layer.py` | `compute_ciso()`: call `_build_category_explanations()` from chain narrative data |
| C-05 | `queries/situation_abstraction_queries.py` | Add `_AQL_CHAIN_NARRATIVES_FOR_BUCKET` query |
| C-06 | `situation/abstraction_layer.py` | `compute_board()`: call `_build_exposure_derivation()` from counterfactual data |
| C-07 | `queries/situation_abstraction_queries.py` | Add `_AQL_COUNTERFACTUALS_FOR_RUN` query |
| C-08 | `frontend/lib/types/situation.ts` | Add `ThreatCategoryExplanation` and `ExposureDerivation` interfaces |
| C-09 | `frontend/app/dashboard/situation/page.tsx` | Render `what_would_have_helped` under CISO threat category cards |
| C-10 | `frontend/app/dashboard/situation/page.tsx` | Render `exposure_derivation.narrative` in Board persona |

---

## Constraints

- Must not break existing 146 CSE unit tests
- No CVE IDs in any output (existing persona boundary)
- New model fields are optional (`= None` / `= field(default_factory=list)`) — backward-compatible
- AQL queries must use `run_id` from `threat_category_rollups` to join to `attack_chain_findings`
- Frontend changes are additive only — existing alert cards unchanged
