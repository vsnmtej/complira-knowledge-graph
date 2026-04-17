# Future-State Runtime Call Stacks — cse-situation-explainability

## Design Basis

- Scope: `Small`
- Call Stack Version: `v1`
- Requirements: `requirements.md` (Design-ready)
- Source Artifact: `proposed-design.md` v1
- Referenced Sections: §1 Architecture Decisions, §2 New Models, §3 AQL Queries, §4 Abstraction Layer, §5 Frontend

---

## Future-State Modeling Rule

All call stacks model target (to-be) behaviour. Existing logic in `compute_ciso()` and
`compute_board()` is unchanged — new code appends new optional fields after existing
computation.

---

## Use Case Index

| UC | Name | Change Items |
|----|------|-------------|
| UC-01 | `compute_ciso()` populates `threat_category_explanations` | C-01, C-02, C-04, C-05 |
| UC-02 | `compute_board()` populates `exposure_derivation` | C-01, C-03, C-06, C-07 |
| UC-03 | `GET /v1/situation/ciso` returns `threat_category_explanations` | C-01, C-02 |
| UC-04 | `GET /v1/situation/board` returns `exposure_derivation` | C-01, C-03 |
| UC-05 | Frontend CISO card renders `what_would_have_helped` | C-08, C-09 |
| UC-06 | Frontend Board card renders `exposure_derivation.narrative` | C-08, C-10 |

---

## Transition Notes

- `CISOSituation` and `BoardSituation` gain new optional fields with default values
  (`= []` / `= None`) — existing callers that don't pass them still work.
- `compute_ciso()` and `compute_board()` have their return constructors extended —
  no other change to their logic.
- New AQL functions added to `situation_abstraction_queries.py` following the same
  pattern as existing functions (single cursor execution, return list).
- Frontend `cisoAlerts()` already maps `ThreatCategory` → `AlertItem`; new code only
  augments `detail_rows` when explanation data is present.
- Frontend Board `boardAlerts()` prepends a new card when `exposure_derivation` is set.

---

## UC-01: `compute_ciso()` populates `threat_category_explanations`

### Goal
`GET /v1/situation/ciso` response includes per-bucket explanations built from chain
narrative data already stored in `attack_chain_findings[].explanation`.

### Preconditions
- `threat_category_rollups` has at least one document for the tenant
- `attack_chain_findings` has `explanation` field populated (set by report agent)
- Both are true after at least one completed simulation run

### Expected Outcome
`CISOSituation.threat_category_explanations` is a non-empty list, each item containing
`what_would_have_helped` sourced from `attack_chain_findings[].explanation.single_countermeasure`.

### Call Stack

```
[ENTRY] SituationAbstractionLayer.compute_ciso(tenant_id)
│
├── [existing] rollups = get_threat_category_rollup(db, tenant_id)
│   → list of {bucket_name, display_name, max_chain_probability, run_id, ...}
│
├── [existing] threat_categories = [ThreatCategory(...) for r in rollups]
│
├── [NEW C-04] threat_category_explanations = []
│   └── for rollup in rollups:
│       ├── narratives = get_chain_narratives_for_bucket(   # new C-05
│       │       db, tenant_id, rollup["bucket_name"]
│       │   )
│       │   └── db.aql.execute(_AQL_CHAIN_NARRATIVES_FOR_BUCKET,
│       │           bind_vars={"tenant_id": tenant_id,
│       │                      "bucket_name": rollup["bucket_name"]}
│       │       )
│       │       # AQL:
│       │       # FOR r IN threat_category_rollups
│       │       #   FILTER r.tenant_id == @tenant_id
│       │       #   FILTER r.bucket_name == @bucket_name
│       │       #   SORT r.computed_at DESC    ← F-001: most recent run, not highest prob
│       │       #   LIMIT 1
│       │       #   FOR f IN attack_chain_findings
│       │       #     FILTER f.run_id == r.run_id
│       │       #     FILTER f.explanation != null
│       │       #     SORT f.confidence DESC
│       │       #     LIMIT 3
│       │       #     RETURN {technique_id, entry_point_reasoning,
│       │       #             success_reasoning, defender_response,
│       │       #             soc_blind_spot, single_countermeasure, confidence}
│       │
│       ├── if not narratives: continue   # no explanation data yet → skip
│       │
│       └── threat_category_explanations.append(
│               _build_category_explanation(rollup, narratives)
│           )
│           # _build_category_explanation():
│           #   driving_events = [n["entry_point_reasoning"] for n in narratives[:2]]
│           #   effective_defender_actions = [n["defender_response"] for n in narratives if n.get("defender_response")]
│           #   what_would_have_helped = narratives[0].get("single_countermeasure", "")
│           #   → ThreatCategoryExplanation(bucket_name, driving_events,
│           #       turning_point_round=None, effective_defender_actions,
│           #       what_would_have_helped)
│
└── situation = CISOSituation(
        ...,                                                # all existing fields
        threat_category_explanations=threat_category_explanations,   # new C-02
    )
```

---

## UC-02: `compute_board()` populates `exposure_derivation`

### Goal
`GET /v1/situation/board` response includes a plain-English explanation of how the
financial exposure figure was calculated.

### Preconditions
- At least one completed simulation run for the tenant with `counterfactuals` populated

### Expected Outcome
`BoardSituation.exposure_derivation.narrative` is a non-empty string. `None` when no
completed simulation exists.

### Call Stack

```
[ENTRY] SituationAbstractionLayer.compute_board(tenant_id)
│
├── [existing] breach_probability_pct, financial_exposure_low/high computed
│
├── [NEW C-06] run_data = get_counterfactuals_for_tenant(db, tenant_id)   # new C-07
│   └── db.aql.execute(_AQL_COUNTERFACTUALS_FOR_RUN,
│           bind_vars={"tenant_id": tenant_id}
│       )
│       # AQL:
│       # FOR r IN simulation_runs
│       #   FILTER r.tenant_id == @tenant_id
│       #   FILTER r.status == "completed"
│       #   SORT r.completed_at DESC
│       #   LIMIT 1
│       #   RETURN {run_id: r._key, counterfactuals: r.counterfactuals,
│       #           chain_count: r.chain_count, audit_trail: r.audit_trail}
│
├── [NEW C-06] exposure_derivation = None
│   └── if run_data:
│       └── exposure_derivation = _build_exposure_derivation(
│               run_data,
│               breach_probability_pct,
│               financial_exposure_low,
│               financial_exposure_high,
│           )
│           # _build_exposure_derivation():
│           #   counterfactuals = run_data.get("counterfactuals") or []
│           #   chain_count     = run_data.get("chain_count") or 0
│           #   top_cf          = counterfactuals[0] if counterfactuals else {}
│           #
│           #   low_m  = (financial_exposure_low  or 0) / 1_000_000
│           #   high_m = (financial_exposure_high or 0) / 1_000_000
│           #
│           #   # F-002: guard trailing space when counterfactuals is empty
│           #   impact = (top_cf.get("impact_if_applied") or "").strip()
│           #   narrative = (
│           #     f"Exposure of ${low_m:.1f}M–${high_m:.1f}M derived from "
│           #     f"{chain_count} confirmed attack chain"
│           #     f"{'s' if chain_count != 1 else ''} "
│           #     f"({breach_probability_pct:.0f}% breach probability)."
│           #     + (f" {impact}" if impact else "")
│           #   )
│           #
│           #   return ExposureDerivation(
│           #     narrative=narrative,
│           #     contributing_chains=chain_count,
│           #     highest_confidence_chain=top_cf.get("current_state", ""),
│           #     investment_recommendation=top_cf.get("intervention_description", ""),
│           #   )
│
└── situation = BoardSituation(
        ...,                              # all existing fields
        exposure_derivation=exposure_derivation,   # new C-03
    )
```

---

## UC-03: `GET /v1/situation/ciso` returns `threat_category_explanations`

### Call Stack

```
[ENTRY] GET /v1/situation/ciso
└── SituationAbstractionLayer(db).compute_ciso(tenant_id)
    → CISOSituation(..., threat_category_explanations=[...])
└── return situation.model_dump()
    # Pydantic serialises threat_category_explanations as JSON array
    # Empty list [] when no simulation data — never null
```

### Response shape (new field only)
```json
{
  "threat_category_explanations": [
    {
      "bucket_name": "remote_code_execution",
      "driving_events": [
        "Unmonitored public-facing service exploited via command injection technique",
        "No active patch deployed after 12 rounds"
      ],
      "turning_point_round": null,
      "effective_defender_actions": [
        "CISO alerted at round 18 after 3 chain steps"
      ],
      "what_would_have_helped": "Enable endpoint monitoring before round 6 to detect the exploitation attempt"
    }
  ]
}
```

---

## UC-04: `GET /v1/situation/board` returns `exposure_derivation`

### Call Stack

```
[ENTRY] GET /v1/situation/board
└── SituationAbstractionLayer(db).compute_board(tenant_id)
    → BoardSituation(..., exposure_derivation=ExposureDerivation(...))
└── return situation.model_dump()
    # Pydantic serialises exposure_derivation as JSON object, or null
```

### Response shape (new field only)
```json
{
  "exposure_derivation": {
    "narrative": "Exposure of $1.2M–$5.1M is derived from 2 confirmed attack chains with 91% breach probability. Deploying endpoint detection on internet-facing devices would reduce the upper bound by ~60%.",
    "contributing_chains": 2,
    "highest_confidence_chain": "Public-facing service exploited at round 6, no prior detection events",
    "investment_recommendation": "Deploy endpoint detection on internet-facing devices"
  }
}
```

---

## UC-05: Frontend CISO card renders `what_would_have_helped`

### Call Stack

```
[BROWSER] situation/page.tsx — cisoAlerts(ciso: CISOSituation)
│
└── for each tc in ciso.threat_categories:
    ├── [existing] build AlertItem with detail_rows
    │
    └── [NEW C-09] find matching explanation:
        ├── explanation = ciso.threat_category_explanations?.find(
        │       e => e.bucket_name === tc.bucket_name
        │   )
        └── if explanation:
            └── detail_rows = [
                    ...existingRows,
                    { key: "What would help",
                      value: explanation.what_would_have_helped },
                ]
            # No UI changes — detail_rows renders in existing AlertCard expanded view
```

---

## UC-06: Frontend Board card renders `exposure_derivation.narrative`

### Call Stack

```
[BROWSER] situation/page.tsx — boardAlerts(board: BoardSituation)
│
├── [existing] regulatory fine risk cards + board priorities
│
└── [NEW C-10] if board.exposure_derivation:
    └── items.unshift({                          # prepend to feed
            id: "board-exposure-derivation",
            title: "Financial Exposure — How We Got Here",
            severity: "high",
            card_type: "compliance",
            summary: board.exposure_derivation.narrative,
            ask_prompt: "Explain the financial exposure derivation in detail...",
            detail_rows: [
              { key: "Contributing Chains",
                value: String(board.exposure_derivation.contributing_chains) },
              { key: "Top Chain",
                value: board.exposure_derivation.highest_confidence_chain },
              { key: "Recommended Investment",
                value: board.exposure_derivation.investment_recommendation },
            ],
        })
```

---

## Graceful-Empty Paths (AC-11)

### No simulation run (rollups empty)

```
compute_ciso():
  rollups = []
  → for rollup in rollups: → loop does not execute
  → threat_category_explanations = []   ✓ empty list, not null

compute_board():
  run_data = get_counterfactuals_for_tenant() → None (no completed runs)
  → exposure_derivation = None           ✓ null, not crash
```

### Simulation run exists but explanation not yet populated

```
get_chain_narratives_for_bucket():
  attack_chain_findings has documents but explanation field is null
  → AQL FILTER f.explanation != null → returns []
  → for rollup: if not narratives: continue
  → threat_category_explanations = []   ✓ graceful empty
```
