# KOSH — PHASE 1: PROVE THE 25 BUGS ARE STILL FIXED

**Date:** 2026-07-09 · **Mode:** read-only (regression suite is rollback-isolated; verify scripts are static/DB-read; no committed writes).
**Result:** ✅ **All 25 bugs verified still fixed.** 31/31 regression tests, BOM parser suite, 23/23 verify scripts (3 via container/behavioral confirmation), 6/6 live key-PCN spot checks.

---

## 1. Full regression suite — `tests/regression_tests.py`
Ran inside `stockandpick_webapp` (real Postgres, SAVEPOINT/ROLLBACK, test PCNs ≥99000).
**31 passed, 0 failed.** Covers the shipped SQL for bugs 1,2,4,5,6,7,9,10,11,13,14,16,17,18,19,20,21,22,23,25.

## 2. BOM parser regression — `tests/test_bom_parser.js`
**PASS, 0 failures** (bloat/tightRange, only-BOM-to-Load, line-drop rescue). Real sample files not in repo are skipped (expected). Covers bug 22.

## 3. Per-bug verify scripts (23)
| Bug | Script | Result | Note |
|---|---|:--:|---|
| 1–9 | verify-bug-0X-fix.py | ✅ PASS | static checks green |
| **10** | verify-bug-10-fix.py | ⚠️→✅ | Static checks 2&3 use **hardcoded line ranges** (`range(3130,3145)`, `range(3170,3180)`); `is_relabel` moved to app.py L3144-3148 / L3185, so the scan misses it. Logic **is present** (read in Phase 0) and behavior is green via `test_onhand_reconcile_neutralizes_relabel_adjt`. **Not a regression — stale harness.** |
| 11–20 | verify-bug-XX-fix.py | ✅ PASS | incl. bug 19 running-floor, bug 20 floor-dedupe |
| **21** | verify-bug-21-fix.py | ⚠️→✅ | `import app` fails on host (ModuleNotFoundError); **PASS when run inside container** (`docker exec -w /app`). Env-only. |
| 22 | verify-bug-22-fix.js | ✅ PASS | |
| **23** | verify-bug-23-fix.py | ⚠️→✅ | same `import app` path issue; **PASS inside container** (`other_mpn_onhand=7`, exact-only, longer variant absent). |

**Net: 23/23 bugs verified.** The 3 "failures" are harness artifacts (hardcoded line numbers, host import path), each independently reconfirmed — none is a code regression.

## 4. Live-data spot check (read-only) — key PCNs match documented post-fix values
| PCN | Item | Bin | Floor | On-hand | Expected (bug) | ✓ |
|---|---|--:|--:|--:|---|:--:|
| 1247 | 7686-43 | 9000 | 0 | 9000 | 9000 (bug 7 — was History 18000) | ✅ |
| 41664 | 6590L-A-30 | 2000 | 0 | 2000 | 2000 (bug 4 — was History 4000) | ✅ |
| 9141 | 6779ML-100 | 1800 | 0 | 1800 | 1800 (bug 19 over-pick — not 0) | ✅ |
| 13959 | 8095-195 | 9 | 0 | 9 @1604009 | 9 (bug 24) | ✅ |
| 29862 | 8461L-75 | 0 | 140 | 140 | 140 (bug 20 — was double 280) | ✅ |
| 30314 | 8525ML-1-640 | 0 | 10000 | 10000 | 10000 single (bug 10 — was 10000 bin **and** floor) | ✅ |

- Bug-24 phantom row `tblTransaction.id=178831` still `reversed=true` (hidden from History) ✅.
- **Reconcile thread liveness (resolves the Phase 0 flag):** `_sync_onhand_from_transactions` (app.py L3532) is a daemon started at import, loops every 300s calling `reconcile_onhand_from_ledger` + `reconcile_warehouse_locations` + `reconcile_floor_onhand`. Container up & healthy. The June-22 `auto_reconcile` timestamp just means nothing has needed lowering since — the loop only logs on change. Nightly integrity monitor last ran today 14:51. ✅
- **Users are live right now** (restocks at 15:25–15:40 UTC during this check) — confirms the read-only spot check did not disturb anyone.

---

## Two minor NEW observations (not Phase-1 regressions; logged for the rebuild)
1. **Negative `mfg_qty` seen live:** restock of PCN 14926 (8847L-90) left `new_mfg_qty = -5`. Floor qty can go negative — a dirty-data instance the new model's `qty >= 0` CHECK would forbid. Add to catalog (extends P5/floor handling).
2. **Stale verify harness:** bug-10's verify script should be made line-agnostic (grep, not hardcoded ranges); bug-21/23 scripts should set `sys.path`/run in-container. Cosmetic; behavior fully covered by the regression suite. (Per rule 7, worth a small follow-up when we next touch bug_memory.)

**STOP — Phase 1 complete. Awaiting approval before Phase 2 (design doc, document-only).** No writes, no deploys.
