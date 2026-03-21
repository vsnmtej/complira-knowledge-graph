# Future-State Runtime Call Stack Review

- Ticket: fix-scanner-adapter-field-mappings
- Date: 2026-03-19

---

## Round 1

**Design basis**: implementation-plan.md v1 + future-state-runtime-call-stack.md v1

### Per-Use-Case Review

#### UC-001 Native Semgrep

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | Config-only change in adapter_registry.py; engine logic unchanged |
| Layering fitness | Pass | Adapter config is data layer; no upward deps introduced |
| Boundary placement | Pass | `semgrep` adapter correctly owns native CLI format; `semgrep_custom` owns pre-processed format |
| Existing-structure bias | Pass | Fix moves away from custom format toward the canonical tool output |
| Anti-hack | Pass | No workarounds; clean field_map update |
| Local-fix degradation | Pass | No SoC degradation |
| Terminology/vocabulary | Pass | `semgrep` = native CLI; `semgrep_custom` = pre-processed categories format — distinction is clear |
| File/API naming | Pass | No new public APIs |
| Name-to-responsibility alignment | Pass | `semgrep` adapter now correctly represents native Semgrep output |
| Future-state alignment | Pass | Call stack matches target field_map and parse_root |
| Use-case coverage completeness | Pass | Primary path + CWE extraction + fallback (empty results) covered |
| Use-case source traceability | Pass | AC-001–AC-009 mapped |
| Requirement coverage closure | Pass | All 6 UCs mapped to at least one requirement |
| Design-risk justification | N/A | No design-risk UCs |
| Business flow completeness | Pass | Ingestion → DB write flow complete |
| SoC check | Pass | adapter_registry.py = config only; no business logic |
| Dependency flow smells | Pass | None |
| Redundancy/duplication | Pass | semgrep_custom is a deliberate copy for backward compat — not duplication smell |
| Simplification | Pass | parse_root = "results" is simpler than "categories.*[]" |
| Decommission/cleanup | Pass | No legacy paths retained in engine; semgrep_custom preserves old format without touching semgrep adapter |
| No-legacy | Pass | semgrep adapter is clean; semgrep_custom is an explicit preserved-compat entry |
| Overall | Pass | |

#### UC-002 Native Checkov

| Check | Result | Notes |
| --- | --- | --- |
| Architecture fit | Pass | Removing `results.` prefix restores alignment with real tool output |
| Layering fitness | Pass | Config-only |
| Boundary placement | Pass | |
| Anti-hack | Pass | |
| Use-case coverage completeness | Pass | All 3 routing branches + DR-003 covered |
| Overall | Pass | |

#### UC-003, UC-004, UC-005, UC-006

All Pass — config changes only, call stacks correctly model the `_extract_cwe` str() behavior and fingerprint fields.

### Missing Use-Case Discovery Sweep

- Boundary crossings: endpoint → service → engine → adapter — no new boundaries introduced
- Error paths: empty `results` array → 0 bundles → run completes normally — modeled in UC-001 fallback
- Design risks: `str(list)` for CWE extraction — confirmed safe by reading `ingestion_engine.py:425`
- New use cases discovered: **None**

### Round 1 Verdict

No blockers. No required artifact updates. No new use cases discovered.

**Clean-review streak: 1 (Candidate Go)**

---

## Round 2

**Design basis**: same (no updates from Round 1)

### Per-Use-Case Review (deep challenge pass)

#### Challenge: Does `_get_field(raw, "start.line")` correctly traverse `{"start": {"line": 42}}`?

Confirmed: `_get_field` splits on `.` and recursively descends. `"start.line"` → `raw["start"]["line"]` → `42`. Pass.

#### Challenge: Does `semgrep_custom` registration break `test_all_expected_tools_present`?

Current test checks: `expected = {"semgrep", "checkov", "gitleaks", "grype", "trufflehog", "zap", "sarif"}`. Adding `semgrep_custom` does NOT break this test because it checks `issubset` not equality. However, the test should add `"semgrep_custom"` to the expected set to prevent future accidental removal. **Note**: this is a test improvement, not a required pre-implementation blocker — can be handled in C-004 test update. Not a blocking finding.

#### Challenge: Does `_extract_list(payload, "results")` handle the case where `results` is absent?

Confirmed: `_extract_list` returns `[]` when key is missing. Silent zero-findings, no exception. Acceptable behavior — consistent with how all other adapters handle missing roots.

#### Challenge: After C-003 (Checkov multi_root fix), does `@check_type` document-level injection still work?

`@check_type` in the field_map is an injection from the document-level key (the root JSON object's `check_type` field). This is applied in `_map_fields` at the document level, not per-finding-root. Removing `results.` prefix does not change where `check_type` lives (it's always at top level). Confirmed: still `Pass`.

#### Challenge: Are there any other adapters with `results.` prefixes that should also be checked?

Reviewed all adapters: gitleaks (`parse_root=None`, json_array), grype (`parse_root="matches"`), trufflehog (`parse_root=None`, json_lines), zap (`parse_root="site[*].alerts[*]"`), sarif (`parse_root="runs[*].results[*]"`). None have `results.` wrapper issues. Scope confirmed correctly limited to semgrep + checkov.

### Missing Use-Case Discovery Sweep (Round 2)

- No new UCs discovered
- All AC coverage confirmed
- No boundary/layering issues surfaced under deep challenge

### Round 2 Verdict

No blockers. No required artifact updates. No new use cases discovered.

**Clean-review streak: 2 — Go Confirmed**

---

## Gate Decision

**Result: Go Confirmed**

Two consecutive clean rounds. All use cases Pass. No required artifact updates. No new use cases. Implementation is unlocked pending Stage 6 pre-edit checklist.
