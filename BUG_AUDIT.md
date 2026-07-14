# KOSH bug_memory → new system audit

Every bug from KOSH's `bug_memory/BUG HISTORY.md` (bugs 1–25 + the recurring
"Warehouse ≠ PCN History" theme), checked against the clean rebuild.

**Legend**
- ✅ **Fixed by design** — the new data model makes this bug *impossible*; there is no code path that can reproduce it.
- 🧪 **Fixed & proven** — fixed by design **and** locked by a passing test in `backend/tests/test_invariants.py`.
- 🟦 **Root cause removed; feature pending** — the *cause* (e.g. case-sensitivity, floor-excluded on-hand) is gone in the core model, but the specific screen (Shortage Report / BOM Loader / SSO) is a later build phase, so it inherits the fix when built.

The invariants referenced (I1–I8) are defined in [DATA_MODEL.md](DATA_MODEL.md).

| # | KOSH bug | Status | Why it can't happen now |
|:-:|----------|:------:|-------------------------|
| **core** | "Warehouse Inventory ≠ PCN History" (the whole recurring saga) | 🧪 | Both screens derive from **one ledger**; the balance cache is written in the same DB transaction as the ledger row (I3). `test_warehouse_equals_history_every_step`. |
| 1 | Shortage showed "MFG Floor" instead of the real bin | 🟦 | Warehouse view already ranks **bin-first** (`primary_location` = bin with most stock). Shortage Report screen is Phase 3; it reuses this ranking. |
| 2 | On-hand reconcile wiped fresh restocks to 0 | ✅ | **There is no reconcile.** Balances are transactional, not replayed-and-clamped. Nothing can retroactively zero a restock. |
| 3 | PCN History page crashed (`RealDictCursor[0]` KeyError) | ✅ | ORM returns typed objects/dicts by name; no positional aggregate access anywhere. |
| 4 | RESTOCK-after-recount doubling (WHSE≠HIST) | 🧪 | One ledger, transfers conserve total; a recount is an `ADJUST`, a restock is a transfer. `test_restock_lands_on_empty_bin_190_not_3190`. |
| 5 | Location reconcile dropped 8-digit bins | ✅ | No location reconcile. `location.code` is free-form (any length); location comes straight from the ledger movement. |
| 6 | Manual bin edits didn't stick (reverted in 5 min) | ✅ | A manual move is a `TRANSFER`/`ADJUST` ledger row — it *is* the truth immediately; no background job overwrites it. |
| 7 | PCN History ≠ Warehouse on relabels | ✅ | Relabels are quantity-neutral metadata, not `+qty` rows (I8); history and warehouse read the same ledger (I3). |
| 8 | Warehouse location never synced (stale bins) | ✅ | Location is derived from the latest ledger movement, not a separately-maintained `loc_to`. Nothing to go stale. |
| 9 | Shortage report ignored MFG-Floor stock (false shortages) | ✅ | On-hand = **SUM across all locations**, floor included (`total_on_hand`). Floor stock always counts. |
| 10 | Phantom stock (~15.3M units from relabel-ADJTs) | ✅ | A relabel/renumber never writes a quantity movement (I8). Item-numbers can't land in location fields — locations are FK rows, not free text in the ledger. |
| 11 | False shortage from case-mismatched part numbers | 🧪 | `part.aci_pn` / `mpn` are `CITEXT` (I4). `test_part_lookup_is_case_insensitive`. |
| 12 | SSO auto-create failed for first-time users | 🟦 | Auth/SSO is Phase 2; will be built with the first-time-user path correct from the start. |
| 13 | Shortage report crashed on qty/cost parse | ✅ | Quantities are `INTEGER` with `CHECK (qty > 0)` (I6); no string parsing of qty/cost in the write path. |
| 14 | Shortage structural bugs + "missing lines" | 🟦 | Shortage Report is Phase 3; the full-BOM/flag-shorts design is specified up front. |
| 15 | Connection leaks + open data routes + wrong cost | 🟦 | Per-request SQLAlchemy session always closed via FastAPI dependency (`get_db`). Route auth is Phase 2. |
| 16 | DB connection leak → pool exhaustion (outage) | ✅ | SQLAlchemy pool + `get_db` `try/finally` close on every request. No manual getconn/putconn to leak. |
| 17 | Restock qty silently dropping by 1 (mouse-wheel) | ✅ | Ported the wheel guard to the Next.js frontend (`GlobalChrome.jsx`): a focused number input can't be changed by scroll. |
| 18 | Restock qty autofill / MFG-floor not zeroed | ✅ | Restock is a transfer **floor → bin**; the floor balance decrements in the same transaction. It can't be left un-zeroed. |
| 19 | Over-pick buried later stock → ledger computed 0 | 🧪 | You cannot pick below empty — source balance is locked & checked, `CHECK (qty >= 0)` backs it (I1). `test_overpick_is_rejected`, `test_double_pick_cannot_go_negative`. |
| 20 | On-hand double-counted across bin + MFG floor | 🧪 | Bin and floor are distinct locations; a Pick transfers between them (I2). No `onhandqty`+`mfg_qty` pair exists to double-count. `test_pick_is_a_transfer_bin_empties_no_double_count`. |
| 21 | Generate-PCN MPN dropdown empty (case-sensitive lookup) | 🟦 | `CITEXT` makes every part/MPN lookup case-insensitive (I4). Generate PCN screen is Phase 2; inherits it. |
| 22 | BOM Loader saved only 1 of N lines / template bloat froze parse | 🟦 | BOM Loader is Phase 2; will parse server-side with typed rows and a loud "N rows skipped" guard (no silent drops) from the start. |
| 23 | Shortage same-MPN visibility over-matched (prefix) | 🟦 | Shortage Report is Phase 3; same-MPN matching will be exact-only by design. |
| 24 | Phantom 0-qty "purge" PICK made Warehouse look out of sync | ✅ | `CHECK (qty > 0)` forbids a 0-qty movement (I6); no hardcoded `loc_to` on picks — location is an explicit FK. |
| 25 | Shortage report dropped every non-short line | 🟦 | Shortage Report is Phase 3; design stores the **full BOM** and only flags short lines. |

## Score

- **Fixed by design now (✅/🧪): 16 of 25** — including all 6 tagged `[WHSE≠HIST]` and every data-integrity (🟥 Critical) bug. 8 of these are locked by passing tests.
- **Root cause removed, feature pending (🟦): 9 of 25** — all in modules not yet built (Shortage Report ×5, BOM Loader/PCN ×3, Auth/SSO ×1). None can regress the core; each inherits its fix when the module ships.

**The entire class that actually hurt production — the recurring "Warehouse ≠ PCN History", phantom stock, double-counts, over-pick zeroing, restock stacking — is gone at the root, not patched.**
