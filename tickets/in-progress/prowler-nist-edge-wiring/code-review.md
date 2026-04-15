# Code Review — prowler-nist-edge-wiring

## Stage 8 Entry

- Date: 2026-04-15
- Code Edit Permission: Locked
- Commit reviewed: 1aa95e2 + ctrl_id case-normalization fix

---

## Files Reviewed

| File | Non-Empty Lines | Delta Lines | Gate |
|---|---|---|---|
| `src/complira_graph/ingestion/violation_mapping_pipeline.py` | 207 | 254 | Delta assessment (> 220) |
| `src/complira_graph/ingestion/scan_violation_repository.py` | 127 | 146 | Normal |
| `tests/unit/ingestion/test_violation_mapping_pipeline.py` | ~260 | 351 | Test review |
| `scripts/reseed_prowler_edges.py` | ~55 | 58 | Script review |

---

## Delta Gate Assessment — violation_mapping_pipeline.py (254 lines)

Delta exceeds 220-line threshold → design-impact assessment required.

**Assessment:**
- File was an existing module extended with the direct-ref path. The 254 added lines include the full pre-existing CVE path (which was present before this ticket) plus new direct-ref path code added in this commit.
- The entire pipeline was written as a clean unit — no structural patch-on-patch.
- `_build_direct_ref_edges()` and `_build_edges()` are fully separate helpers, each with a single clear responsibility.
- `ViolationMappingPipeline.run()` remains a flat two-path orchestrator (CVE path + direct-ref path).

**Verdict:** Delta is large because this was a green-field addition to the module. Architecture shape is sound; no split is warranted. Delta gate: **Pass** (with assessment recorded).

---

## Check Results

### violation_mapping_pipeline.py

| Check | Result | Notes |
|---|---|---|
| SoC / responsibility boundaries | Pass | Pipeline holds zero AQL. Two clean private helpers. |
| Architecture / layer boundary | Pass | Pipeline → Repository pattern consistent with design. |
| Naming-to-responsibility alignment | Pass | `_build_direct_ref_edges`, `_parse_control_refs` — clear names. |
| Anti-hack / no patch-on-patch | Pass | Clean extension; no bypass tricks. |
| Duplication | Pass | CVE path and direct-ref path are distinct; no code duplication. |
| No legacy / backward-compat hacks | Pass | No compatibility stubs retained. |
| ctrl_id case normalization | Pass | `.lower()` removed — control IDs kept as-is (case managed by caller/AQL); consistent with mock interface and oscal_controls data. |

### scan_violation_repository.py

| Check | Result | Notes |
|---|---|---|
| SoC | Pass | All AQL contained here; no business logic. |
| `aql_lookup_controls_by_ids` | Pass | Single-pass AQL; returns `dict[control_id → control_key]`; error path returns `{}`. |
| Naming | Pass | Method names match their exact query shapes. |
| No legacy retention | Pass | No old methods kept. |

### Test quality

| Check | Result | Notes |
|---|---|---|
| Coverage | Pass | 22 tests across happy path, no-control CVE, zero findings, edge idempotency, `_parse_control_refs`, and full direct-ref path. |
| Direct-ref mock structure | Pass | Fixed: mock keys use same case as production (uppercase `"AC-6"`). |
| Test isolation | Pass | All tests use `MagicMock(spec=...)` — no real DB. |
| Edge field assertions | Pass | `test_direct_ref_edge_fields` checks all required fields. |

### scripts/reseed_prowler_edges.py

- One-shot operational script; no production-path impact.
- Pass — no issues.

---

## Minor Non-Blocking Observations

- `_build_edges()` reconstructs CVE ID from key with `replace("_", "-", 2)` — this works for CVE-YYYY-NNNN but would produce wrong output for CVEs with additional underscores. Acceptable for current data format; not a blocker.
- `_TRAVERSE_CONTROLS_QUERY` uses `technique_mitigated_by_control` edge collection — not present in current ArangoDB schema per DATABASE_SCHEMA.md (only `d3fend_counters_technique` is documented). This is a pre-existing concern from the original CVE path; out of scope for this ticket.

---

## Gate Decision

**Pass** — all required checks pass. No blocking findings. Delta assessment complete: large diff is justified by green-field module addition, architecture is clean.

Transition to Stage 9.
