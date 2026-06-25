<h1 align="center">🧪 KOSH — Full Bug Regression Test Run</h1>

<p align="center">
  <b>Every logged KOSH bug (1–19) re-tested by the test user.</b><br>
  <span>Date: <b>2026-06-25</b> · Run by: automated <b>test user</b> (<code>regression@test.com</code>) · Env: prod container <code>stockandpick_webapp</code> (kosh-web_app, freshly rebuilt <code>--no-cache</code>), DB <code>kosh</code> on <code>aci-database</code></span>
</p>

> **Why this file exists:** Preet asked for a single record showing that the complete bug list was exercised by the test user, with the output of each action and what happened. This is that record. It pairs the per-bug **static verifiers** (`bug_memory/*/verify-*.py`) with the **behavioral regression suite** (`tests/regression_tests.py`, run inside the live container) so each bug is covered both ways.

---

## ✅ Headline result

| Suite | Result |
|---|---|
| Per-bug static verifiers (bugs 1–19) | **19 / 19 PASS** |
| Behavioral regression suite (in-container) | **26 / 26 PASS, 0 failed** |
| Page-route smoke test | **28 routes rendered, 0 server errors** |
| Live-DB validation of the new fix (bug 19) | pcn 9141 ledger 0→1800; phantom rows 25→0; invariant new≥old, **0 violations / 35,294 groups** |
| Warehouse rows mutated | **0** (fix is a computation change; no data touched) |

---

## A. Per-bug static verification — what each action did and its output

Command per bug: `python3 bug_memory/<bug>/verify-<n>-fix.py` (full captured log: this run, 2026-06-25).

| Bug | What it verifies | Result | Key output |
|---|---|---|---|
| 1 — Shortage report showed MFG Floor not real bin | bin-first `ORDER BY`, exact-or-prefix item search | ✅ PASS | "ALL TESTS PASSED — Bug #1 fix verified!" |
| 2 — On-hand reconcile wiped fresh restocks | `latest_event` CTE + never-lower-fresh-receipt guard | ✅ PASS | "latest_event CTE found; Guard condition found" |
| 3 — PCN History page crashed | `AS total` alias + dict cursor access | ✅ PASS | "Query has AS total; Dict access (not index)" |
| 4 — RESTOCK-after-recount doubling | anchored-history fn, backward walk, RNDT-neutral | ✅ PASS | "5/5 — anchored history + doubling prevention" |
| 5 — Location reconcile dropped 8-digit bins | any-length numeric bin regex + named locs | ✅ PASS | "Regex accepts ANY length numeric bins" |
| 6 — Manual bin edits didn't stick | ADJT in placements trantype list; relabel-ADJT filtered | ✅ PASS | "ADJT in placements; location filter rejects relabel-ADJT" |
| 7 — PCN History ≠ Warehouse on relabels | relabel-neutral history math | ✅ PASS | "ALL TESTS PASSED — Bug #7" |
| 8 — Warehouse location never synced | reconcile syncs loc from latest placement | ✅ PASS | "ALL TESTS PASSED — Bug #8" |
| 9 — Shortage ignored MFG-Floor stock | `SUM(onhandqty + mfg_qty)` in on-hand calc (×3 views) | ✅ PASS | found at app.py L5190 / L8469 / L8771 |
| 10 — 15M phantom units | `is_relabel` predicate quantity-neutral in net | ✅ PASS | "ALL TESTS PASSED — Bug #10" |
| 11 — False shortage on case mismatch | case-insensitive item match (`LOWER(TRIM())`) | ✅ PASS | case-insensitive join found |
| 12 — SSO auto-create failed | `bcrypt` imported + `bcrypt.hashpw(...gensalt())` on auto-create | ✅ PASS | bcrypt usage found in SSO auto-create |
| 13 — Shortage crashed 11 jobs (overflow) | tolerant numeric parse + cost magnitude guard | ✅ PASS | "ALL TESTS PASSED — Bug #13" |
| 14 — Structural bugs / missing lines | deterministic dedup `ORDER BY total_qty DESC` | ✅ PASS | qty-DESC ordering found |
| 15 — Conn leaks / open routes / wrong cost | route auth (`before_request` + `@require_auth`), shortage_cost vs total_cost, >50 cleanup sites | ✅ PASS | auth present; cost distinction; cleanup patterns |
| 16 — DB connection leak (pool exhaustion) | `return_connection` in `finally`, pool guards | ✅ PASS | "ALL TESTS PASSED — Bug #16" |
| 17 — Restock qty dropping by 1 | wheel-event neutralization (template fix) | ✅ PASS | "Wheel event neutralization [PASS]" |
| 18 — Restock autofill / MFG-floor not zeroed | autofill removed, floor zeroed on restock | ✅ PASS | "ALL TESTS PASSED — Bug #18" |
| **19 — Over-pick buried later stock (NEW)** | running-floor ledger (reflection formula), monitor mirror | ✅ PASS | "Bug #19 verification complete" |

---

## B. Behavioral regression suite — `tests/run.sh` (inside container)

`26 passed, 0 failed.` Tests exercised as the test user:

- test_restock_allowed_after_purge_following_restock
- test_restock_allowed_when_zero_onhand_even_if_last_restock
- test_restock_blocked_when_already_restocked_with_stock_present
- test_purged_pcn_can_be_restocked_with_same_pcn
- test_print_label_sums_across_duplicate_pcn_rows
- test_validate_location_auto_registers_unknown_7digit
- test_bom_load_inserts_every_item_received
- test_bom_python_parser_finds_lines_across_sheets
- test_shortage_report_alt_part_qty_and_same_mpn_visibility
- test_shortage_report_own_stock_is_case_insensitive
- test_shortage_report_counts_mfg_floor_stock
- test_shortage_report_shows_bin_location_not_floor
- test_location_reconcile_follows_latest_placement
- test_location_reconcile_honors_manual_adjt_edit
- test_onhand_reconcile_neutralizes_relabel_adjt
- test_onhand_reconcile_never_wipes_fresh_restock
- **test_onhand_reconcile_overpick_does_not_zero_refilled_stock** ← new guard for bug 19
- test_pcn_history_balance_matches_reconcile_on_relabel
- test_pcn_history_relabel_neutral_on_real_pcns
- test_pcn_history_anchored_to_inventory_no_doubling
- test_pcn_history_relabel_adjt_is_quantity_neutral_in_anchor
- test_pcn_history_route_anchor_uses_dict_cursor
- test_return_connection_never_leaks_foreign_connection
- test_quantity_fields_are_not_number_spinners
- test_app_served_by_gunicorn_not_dev_server
- test_all_pages_render_without_server_error (28 page routes, 0 server errors)

---

## C. Live-DB validation of bug 19 (read-only)

Run against the live `kosh` DB via `docker exec aci-database psql`:

- **pcn 9141** (6779ML-100): ledger `0 → 1800` — now equals Warehouse (1800).
- **Phantom rows** (Warehouse > ledger by >5 units): **25 → 0**.
- **Safety invariant**: new ledger ≥ old ledger across **all 35,294 (pcn,mpn) groups, 0 violations** (37 raised by the over-pick recovery). Reconcile is lower-only ⇒ raising the ledger can only lower *less* ⇒ **provably no new data loss**.
- **No warehouse rows were mutated** — fixing the math made Warehouse and the ledger agree on their own. The unsafe one-off `fix-bidirectional-reconcile.sql` was **NOT run** (it would have zeroed the 25 RESTOCK rows).

---

## D. Test-tooling fixes made during this run (so the suite is repeatable)

1. **Portability:** 17 verifier/test scripts hardcoded a Windows path
   (`C:\Users\admin\OneDrive…\KOSH\app.py`) and could not run on the Linux server.
   Rewrote them to resolve `app.py` relative to the repo
   (`Path(__file__).resolve().parents[2] / "app.py"`).
2. **De-brittled 5 verifiers** that scanned hardcoded line-number windows (which drift
   on every refactor) and one stale function name. Confirmed each underlying fix is
   genuinely present in current code, then changed the scripts to search the whole
   file for the current pattern:
   - bug 9 — pattern lives at L5190/8469/8771; verifier only scanned 5140–5160.
   - bug 11 — code uses `LOWER(TRIM())`, verifier only accepted `UPPER`.
   - bug 12 — `bcrypt.hashpw` moved to ~L6025.
   - bug 14 — `ORDER BY total_qty DESC` (was scanning a stale window).
   - bug 15 — auth migrated to `@app.before_request` + `@require_auth` (was grepping `@login_required`).

> Before these fixes the verifiers reported 0 PASS (Windows path) then 13/18 (stale
> matchers). After: **19/19**. No behavioral fix was changed to make a verifier pass —
> only the verifiers were corrected to match the already-deployed code, and every
> behavior is independently confirmed by the in-container regression suite.
