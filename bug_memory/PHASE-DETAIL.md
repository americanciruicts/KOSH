# KOSH — DETAILED PHASE BREAKDOWN

Granular, in-parts plan for the two big areas. Companion to `ACTION-PLAN.md` (high level) and
`FIX-PLAN.md` (per-issue). Model is locked (see `ACTION-PLAN.md` §THE MODEL): one number per
PCN, **pick → 0**, **restock → SET**, floor = status, both screens read the one number, no
ledger, no reconciler. Every part: reproduce RED → fix → GREEN on `kosh_test`, re-run the whole
gate. ⚑ = an OPEN QUESTION that must be answered (a gate) before that part ships.

---

# PART A — INVENTORY ENGINE (Phase 2, in parts)

## 2a — Build `wh_ops.py` to the one-number model (pure functions, no ledger)
- `pick(cur, pcn)` → set `onhandqty=0`, `mfg_qty='0'`, `loc_to='MFG Floor'` (status). Returns
  the qty that was on hand (for the history/audit row). Picks the WHOLE PCN (complete pick).
- `restock(cur, pcn, qty, bin)` → **SET** `onhandqty=qty`, `mfg_qty='0'`, `loc_to=bin`. Never
  rejects for "floor at zero" (it's a recount, not a transfer) — this is RS-1, fixed by the model.
- `stock(cur, pcn, qty, bin)` → receive: set `onhandqty=qty`, `loc_to=bin` (new/again-received).
- `set_qty(cur, pcn, qty)` → manual warehouse edit: SET `onhandqty=qty` (WI-1 edit path).
- `rename(cur, pcn, new_item)` → `UPDATE item` only (no stock move; can't strand in this model).
- Each: lock the row `FOR UPDATE`, validate qty (`>=0`; pick needs no qty), one `UPDATE`.
- **Test** `p2_ops.py` (rollback): pick→0; restock a picked-to-0 PCN→SET; stock; manual edit;
  rename carries; every op leaves ONE number (mfg_qty always '0').
- **Gate:** all ops green in isolation.
- ⚑ **Q1 — job-level pick:** the PCN-pick (Theresa's path) zeroes the PCN. When a *job* pick
  spans several PCNs for a quantity, is it always "pick these whole PCNs" (complete), or can the
  last PCN be partial? (Model says complete; confirm the job-FIFO path.)

## 2b — Wire the write paths to `wh_ops`, remove the ledger
- `pick_pcb` (app.py ~L1036): keep all validation/blocking/audit; replace the `ledger.pick` +
  `project_warehouse` block (L1300-1307) with `wh_ops.pick`.
- `restock_pcb` (~L1390): replace `ledger.restock_physical`/`restock` with `wh_ops.restock` (SET).
- `stock_pcb` (~L840): replace `ledger.stock` + project with `wh_ops.stock`.
- `part_number_change` (~L4303): drop `ledger.relabel_pcn`/`project_warehouse`; keep `UPDATE item`.
- Manual warehouse-inventory edit path → `wh_ops.set_qty`.
- Keep the `tblTransaction` audit inserts (history record) in every path.
- **Test:** drive each real route against `kosh_test` (verify via the running staging container);
  re-point `p1_rename_carries_stock.py` at the snapshot rename.
- **Gate:** each operation produces the right single number; suite green.

## 2c — PCN History reads the stored number (WI-2)
- `pcn_history` (app.py ~L6586): current on-hand shown = `tblWhse_Inventory.onhandqty` (the one
  number). STOP replaying `inventory_balance`/ledger to derive a balance.
- The transaction trail stays as a display-only audit list; its running number follows pick→0 /
  restock→SET so the latest value equals the stored `onhandqty`.
- **Test** `p2_whse_equals_history.py`: for a sample of real PCNs and after each op, the number
  PCN History shows == the number Warehouse Inventory shows. Whole-table check in the scoreboard.
- **Gate:** Warehouse == PCN History for every PCN. **This is the WI-2 fix.**

## 2d — Delete the reconciler threads
- Remove `_sync_onhand_from_transactions` + `reconcile_onhand_from_ledger` +
  `reconcile_warehouse_locations` + `reconcile_floor_onhand` + `_floor_janitor` +
  `_nightly_integrity_check` (or repoint the nightly check read-only at the scoreboard).
- **Test:** after an op, wait/confirm nothing rewrites the number (no background overwrite) — this
  is the bug-2 (restock-wipe) guard.
- **Gate:** on-hand stable; no thread writes `tblWhse_Inventory`.

## 2e — One-time data clean (floor becomes a status)
- On-hand is `onhandqty`. Floor no longer counts, so set `mfg_qty='0'` across the board
  (audited, reversible). This makes the 33 "double" rows and the 2,854 stale-floor rows
  correct-by-definition (a picked PCN with onhandqty=0 is simply 0; a bin PCN keeps its bin qty).
- **Test:** scoreboard `double_count → 0`, `stale_floor → 0`; no PCN's `onhandqty` changed by the
  cleanup (only `mfg_qty` zeroed).
- ⚑ **Q2 — physical truth:** for the ~33 rows with `onhandqty>0 AND mfg_qty>0`, is the bin number
  the real on-hand (zero the floor), always? (Model says yes; Theresa can spot-verify a few.)

## 2f — End-to-end verify on the running staging app
- Drive stock → pick → restock through the real UI/container; confirm both screens agree at every
  step and restock-from-0 works. **Gate:** green + Preet spot-check.

---

# PART B — SHORTAGE REPORT & BOM LOADER (Phase 5, in parts)

## 5a — Availability rule (the on-hand a shortage uses) ⚑ GATE FIRST
- New model: shortage on-hand = the ONE number (`onhandqty`); a **picked PCN reads 0 / not
  available**. This REVERSES bug 9 ("count the floor"). Implement in `_SHORTAGE_MATCH_SQL` (on-hand
  = `onhandqty`, drop the `+ mfg_qty`).
- ⚑ **Q3:** when a job's own parts are already picked & staged for THAT job, should its shortage
  show them as covered or as 0? (Decide with Theresa before shipping — this is the exact bug-9 flip.)
- **Test:** a picked PCN contributes 0 to availability; an in-bin PCN contributes its qty.

## 5b — Exact-MPN only (SR-2)
- In `_SHORTAGE_MATCH_SQL` remove the prefix/`LIKE` branch; match normalized **exact** MPN only
  (case + `-# ./` folded). So `1234` never pulls `12345`/`123456`.
- **Test** (`p5_shortage_exact_mpn`): exact MPN counts; a longer distinct MPN does NOT appear.
- **Gate:** no "like"-MPN rows.

## 5c — Per-PCN breakout (SR-4)
- Change the report/builder so each line lists **every PCN holding stock** (PCN, qty, location),
  not just the summed total.
- ⚑ **Q4:** show all PCNs, or only those with qty > 0? Format Theresa wants (rows under the line?).
- **Test:** a line with 3 stocked PCNs shows all 3.

## 5d — BOM substitutes (SR-1) ⚑ NEEDS REAL BOM DATA
- Goal: a line's BOM-listed **substitute** parts count as valid stock, so a covered-by-substitute
  line isn't a false shortage.
- **Step 1 (investigate):** open a real BOM (`tblBOM` + a sample xlsx) and determine how subs are
  represented — a column, separate rows, a `ZSUB`/alternate marker (bug 14 mentioned "ZSUB").
- **Step 2 (fix):** include the line's substitutes as alternate stock sources in the match.
- **Test:** a line with a stocked substitute is NOT flagged short; a line with no sub/stock is.
- ⚑ **Q5:** exactly how are substitutes stored in your BOM?

## 5e — SR-3 wrong ACI PN
- Already handled by Phase 1 (rename updates the part); verify it shows on the shortage report.

## 5f — BOM Loader (verify, don't assume) ⚑ GATE
- The 7-16 issue list does NOT flag the BOM loader; bugs 21/22 (case-sensitive lookup, line-drop,
  bloat) appear addressed.
- ⚑ **Q6:** is the BOM loader still failing? If so, symptom + the exact file. Reproduce from that
  file FIRST (the bug-21 lesson: it was "fixed" wrong once because it shipped without a repro),
  then fix. If not failing, mark verified-OK.

## 5g — Report must list EVERY BOM line (missing-lines) — from the emails, NOT on the 7-16 list
- Theresa 2026-06-03: *"This report was missing several lines of data… **This is where trust was
  lost**."* And 2026-06-23: *"one line item that did not show on the shortage report."*
- Cause class (bug 25): the builder persisted ONLY lines below requirement, so fully-stocked (or
  floor-stocked) lines silently vanished. Same job re-run gave different line counts.
- **Fix:** the stored report = the FULL BOM, every matched line; "shortage count" only counts the
  lines actually below requirement. A line may never be dropped silently.
- **Test:** generate for a job → report line count == BOM line count; re-running is stable.

## 5h — QTY and REQ columns must never be blank/0 when the BOM has a value
- Theresa 2026-06-03: *"the QTY column and the REQ column… had '0'… which required the need to
  refer to the BOM to know what qty was needed to build"* — and the same job ran fine for Preet,
  so it is data/parse-dependent, not job-wide.
- Cause class (bug 13): non-numeric/odd qty & cost values fell back to 0 instead of parsing.
- **Fix:** tolerant, correct parsing of BOM qty; REQ = qty × order_qty (rounded up). Never emit 0
  where the BOM has a real number; if truly unparseable, flag the line loudly instead of showing 0.
- **Test:** a BOM with fractional/odd qty values yields correct QTY/REQ, never a silent 0.

## 5i — A line's OWN stock must be included
- Theresa 2026-06-03: *"not including other PCN's with the same MPN for several line items
  **including the line item itself**"* — i.e. the line's own part's stock was missing too.
- **Fix:** the match must always count the line's own part stock (case-insensitive), plus exact-MPN
  stock under other part numbers (5b). Verify both halves.
- **Test:** a line whose own part has stock shows it; same-MPN-other-PN stock also shows.

## Out of this plan's scope (flagged, needs a decision)
- **SO-1 (signed out while kitting)** is real and covered, but in `ACTION-PLAN.md` **Phase 4**
  (auth/CSRF), not in Part A/B above — it is unrelated to inventory or the shortage report.

---

# ✅ COVERAGE MATRIX — every reported issue → where it is fixed

| # | Source | Issue | Covered by |
|---|---|---|---|
| E1/E2 | 6-03 email | QTY & REQ columns show "0" | **5h** |
| E3 | 6-03 email | Report missing several lines ("trust was lost") | **5g** |
| E4 | 6-03 email | Same-MPN PCNs not included, incl. the line itself | **5i** + 5b |
| E5 | 6-17 KOSH.eml | Whse Inv not showing latest transactions vs History | **2c** |
| E6 | 6-17 email | Data wrong on 9 lines | model (2a-2e) + 5b/5g/5h |
| E7 | 6-23 email | A line item did not show on the report | **5g** |
| E8 | 6-23 email | Line shown is not actually in stock | **2e + 5a** (picked = 0) |
| E10 | 7-01 email | Whse Inv not reflecting last PCN-History entry | **2c** |
| SR-1 | xlsx 7-16 | Substitutes not generated | **5d** |
| SR-2 | xlsx 7-16 | Lists "like" MPNs | **5b** |
| SR-3 | xlsx 7-16 | Wrong ACI PN (6366L-9 vs 6390L-8) | **5e** (via Phase 1) |
| SR-4 | xlsx 7-16 | PCNs not listed, only total qty | **5c** |
| WI-1 | xlsx 7-16 | Unable to edit quantities | **2a/2b** (`set_qty`) |
| PK-1 | xlsx 7-16 | Unable to pick — insufficient qty | **2a/2b** + Phase 1 |
| SO-1 | xlsx 7-16 | Signed out after each transaction | **ACTION-PLAN Phase 4** |
| PH-1 | xlsx 7-16 | Same qty on hand and picked | **2e** (floor = status) |
| WI-2 | xlsx 7-16 | PCN History ≠ Whse Inventory | **2c** |
| RS-1 | xlsx 7-16 | Restock stops working, "qty at zero" | **2a** (restock = SET) |

---

# Open questions to answer (gates), collected
- **Q1** job-level pick: always complete PCNs, or can the last be partial?
- **Q2** the 33 both-rows: is the bin number always the real on-hand?
- **Q3** shortage availability: does a job's own picked/staged stock count as covered for that job?
- **Q4** per-PCN breakout: all PCNs or only qty>0; display format.
- **Q5** how substitutes are represented in the BOM.
- **Q6** is the BOM loader currently broken (and on which file)?
