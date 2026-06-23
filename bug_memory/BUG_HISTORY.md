# 🐞 KOSH — Bug History

> Permanent, human-readable record of every bug fixed in KOSH.
> **Window covered:** 13 May 2026 → 23 June 2026 (49 commits).
> See [`README.md`](./README.md) for how to add entries.

**Status legend:** ✅ Fixed & deployed · 🟡 Partial · 🔴 Open · 🔁 Recurring (came back)

---

## 📋 Quick reference

| # | Date | Bug | Area | Status |
|---|------|-----|------|:------:|
| 1 | 2026-06-23 | Shortage report showed "MFG Floor" instead of the real bin | Shortage / Location | ✅ |
| 2 | 2026-06-22 | On-hand reconcile wiped fresh restocks to 0 | Inventory / Reconcile | ✅ |
| 3 | 2026-06-18 | PCN History page crashed for every PCN | PCN History | ✅ |
| 4 | 2026-06-18 | RESTOCK-after-recount doubling (History ≠ Warehouse) | Inventory / History | ✅ |
| 5 | 2026-06-17 | Location reconcile dropped 8-digit bins | Warehouse Location | ✅ |
| 6 | 2026-06-16 | Manual bin edits didn't stick | Warehouse Location | ✅ |
| 7 | 2026-06-16 | PCN History ≠ Warehouse on relabels | PCN History | ✅ |
| 8 | 2026-06-15 | Warehouse location never synced (stale bins) | Warehouse Location | ✅ |
| 9 | 2026-06-15 | Shortage report ignored MFG-Floor stock | Shortage | ✅ |
| 10 | 2026-06-12 | Phantom stock — ~15.3M phantom units | Inventory / Reconcile | ✅ |
| 11 | 2026-06-12 | False shortage from case-mismatched part numbers | Shortage | ✅ |
| 12 | 2026-06-05 | SSO auto-create failed for first-time users | Auth | ✅ |
| 13 | 2026-06-04 | Shortage report crashed on 11 jobs (qty/cost parsing) | Shortage | ✅ |
| 14 | 2026-06-03 | Shortage structural bugs + "missing lines" | Shortage | ✅ |
| 15 | 2026-06-01 | Connection leaks + open data routes + wrong cost | Infra / Security | ✅ |
| 16 | 2026-05-29 | DB connection leak → pool exhaustion (outage) | Infra | ✅ |
| 17 | 2026-05-29 | Restock quantity silently dropping by 1 | Pick / Restock | ✅ |
| 18 | 2026-05-18 | Restock qty autofill / MFG-floor not zeroed | Pick / Restock | ✅ |

🏷️ **Tag [WHSE≠HIST]** marks bugs that caused the recurring *"Warehouse Inventory data ≠ PCN History"* complaint (9 of them). Read that section next.

---

## 🧭 The core symptom — "Warehouse Inventory ≠ PCN History"

This is the complaint Theresa reported again and again in different shapes. It isn't one
bug — it's a structural consequence of how the two screens are built.

### What the two screens actually are
| Screen | What it is | Maintained by |
|--------|-----------|---------------|
| **Warehouse Inventory** | The *stored snapshot* in `tblWhse_Inventory` (per PCN: `onhandqty` = bin qty, `mfg_qty` = MFG-Floor qty, `loc_to` = bin) | Direct ops (stock/pick/restock/edit) **+** a 5-min on-hand reconcile **+** a location reconcile |
| **PCN History** | A *derived view* computed live from the `tblTransaction` trail, with a running on-hand balance per row | Recomputed on every view from the transaction log |

They are **two different computations over partly different inputs.** Whenever those
computations used different rules, the numbers diverged — and the user saw
*"Warehouse says X, History says Y."*

### Why they diverged — two independent axes

**1) Quantity.** PCN History originally *replayed the dirty Access ledger forward*, which
produced wrong numbers two ways:
- It counted a **relabel/renumber ADJT** (which carries the part's full qty) as a real
  `+qty` movement → inflated History. *Example: PCN 1247 — History 18,000 vs Warehouse 9,000.*
- It treated an **RNDT recount as a baseline and then added a later RESTOCK** on top →
  doubling. *Example: PCN 41664 — History 4,000 vs Warehouse 2,000.*

Meanwhile the reconcile feeding Warehouse used **different math**, so the two never matched.

**2) Location.** Put-aways/relocations happen in Access and arrive as imported **PTWY/ADJT**
transactions. PCN History showed them (so it had the *true* current bin), but Warehouse's
stored `loc_to` was only updated by KOSH's own pick/restock — it never synced the imports.
Result: **History showed the real bin, Warehouse showed a stale one** (~4,792 stale rows),
and Theresa could only find stock via History.

### How it was resolved
- **Quantity (architectural fix, 18 Jun, `5b1967c`):** PCN History no longer computes its
  own absolute number — it **anchors to Warehouse Inventory** and walks the trail backward
  from it. Both screens now derive the current on-hand from the **same single source**, so
  they **cannot disagree by construction.**
- **Location (15–17 Jun):** a background location reconcile syncs Warehouse `loc_to` to each
  PCN's latest real placement (any-length bin or named area, honoring manual edits), so
  Warehouse catches up to what History shows within ~5 min.

### ⚠️ Why it's still not 100% (and why a rebuild is recommended)
- The anchor sums `onhandqty` **per PCN**; multi-MPN-per-PCN rows and bin-rows whose stored
  location literally says "MFG Floor" are edge cases it can't fully reason about.
- The on-hand reconcile is a **"lower-only", guarded remediation** of a dirty ledger — a
  patch, not a clean recompute.
- The **source ledger is still ambiguous** (relabels as quantity-ADJTs, item-numbers in
  location fields, out-of-order timestamps).

➡️ **The durable fix is to rebuild the inventory / PCN / transaction data model** so
Warehouse and History become two views of *one clean event log*, not two reconciled guesses
over a dirty import.

---

## 🔌 Recurring root cause — the dirty Access import
- Part **renumbers/relabels were logged as `ADJT` carrying the full quantity**, with old/new
  **item numbers in the `loc_from`/`loc_to` fields** (not real locations) → reconcile read
  them as stock movements → phantom stock.
- `tran_time` values are **out of chronological order** (Access migrated in batches) → never
  order by row id; always parse `tran_time`.
- **Bin location, MFG-Floor, and item-number all share the loc fields** → selection logic
  repeatedly picked the wrong thing.
- The ledger records **more PICKs than stock-ins** for some parts → forward replay nets negative.

---

# 📒 Detailed entries (newest first)

---

### 1. Shortage report showed "MFG Floor" instead of the real bin — `[WHSE≠HIST]` ✅
**Date:** 2026-06-23 · **Area:** Shortage / Location · **Reported by:** Theresa (job 5455M / WO# 24214-2 + screenshot)

- **Issue:** the report sent the picker to a location with nothing pickable, and the bin that actually held the stock "didn't show on the report."
- **Example:** line 3 (5455M-3) — **278 units in bin 2204207** (PCN 37656), but the report displayed **"MFG Floor"** (PCN 37654: 0 in bin, 840 on floor). Lines 1 & 11 were floor-only (correctly showed MFG Floor).
- **Root cause:** the displayed PCN/location was chosen by **highest bin+floor total** (`ORDER BY (onhandqty + mfg_qty) DESC`), so a big floor-only lot out-ranked a smaller real-bin lot.
- **Fixed:** rank the displayed lot **bin-first** (`(onhandqty>0) DESC, onhandqty DESC, floor DESC`); fall back to MFG Floor only when nothing is in a bin. In the shared `_SHORTAGE_MATCH_SQL`, so it covers every job/report. On-hand SUM still includes floor qty (no false-shortage regression). Also changed Item-Number search to *exact-wins-else-prefix*.
- **When:** 2026-06-23 · commit `e88ae7b` · **Deployed:** ✅
- **Did it handle it?** Yes — verified live: line 3 → bin 2204207. Fleet-wide **1,492 items** were mis-pointing → 0.
- **Guard:** `test_shortage_report_shows_bin_location_not_floor`

**Recurrences / new case reports:** _none yet._

---

### 2. On-hand reconcile wiped fresh restocks to 0 — `[WHSE≠HIST]` ✅
**Date:** 2026-06-22 · **Area:** Inventory / Reconcile · **Reported by:** Preet ("edits not saving")

- **Issue:** a real restock saved, then hours later Warehouse showed **0** while PCN History still correctly showed the restock.
- **Example:** PCN 42137 — `parts@` restocked 15 units on 6/18 07:30; the reconcile zeroed it at 11:31 the same day.
- **Root cause:** the 5-min reconcile replays the whole ledger; for parts with more PICKs than stock-ins it nets negative → clamps to 0 → the lower-only guard saw `0 < 15` and overwrote the fresh restock.
- **Fixed:** never lower a row whose **most recent material transaction is a fresh receipt (RESTOCK/STOCK)** — the receipt is authoritative. Phantom-high stock (latest event = PICK/RNDT) is still corrected.
- **When:** 2026-06-22 · commit `1958a08` · **Deployed:** ✅
- **Did it handle it?** Yes. **Data fix (separate pass):** 62 zeroed rows backfilled to their restock qty (audit tag `restock_wipe_backfill_20260622`).
- **Guard:** `test_onhand_reconcile_never_wipes_fresh_restock`

**Recurrences / new case reports:** _none yet._

---

### 3. PCN History page crashed for every real PCN ✅
**Date:** 2026-06-18 · **Area:** PCN History

- **Issue:** opening History for any PCN showed *"Error loading PCN history: 0"*.
- **Example:** every real PCN; only the empty search form worked.
- **Root cause:** the anchor query runs on a `RealDictCursor` (returns dicts) but the code read the aggregate as `anchor_row[0]` → `KeyError: 0`. The smoke test only hit the empty form; the unit test used a plain cursor.
- **Fixed:** read the aggregate by alias — `SELECT … AS total` → `anchor_row['total']`; added a test on the exact RealDictCursor path.
- **When:** 2026-06-18 · commit `069819e` · **Deployed:** ✅
- **Did it handle it?** Yes.
- **Guard:** RealDictCursor anchor-path regression test

**Recurrences / new case reports:** _none yet._

---

### 4. RESTOCK-after-recount doubling — the WHSE≠HIST architectural fix — `[WHSE≠HIST]` ✅
**Date:** 2026-06-18 · **Area:** Inventory / History

- **Issue:** PCN History on-hand was double the Warehouse value.
- **Example:** PCN 41664 — History 4,000 vs Warehouse 2,000; also a 79→158 shape elsewhere.
- **Root cause:** History replayed the ledger forward, treated an **RNDT recount as a baseline**, then **added a later RESTOCK of the same parts on top**.
- **Fixed:** History now **anchors** its on-hand to the authoritative Warehouse value and walks the trail **backward** (`compute_anchored_history_balances` / `_history_delta`) — so the two views can't disagree. **SCRA** now subtracts (was unhandled); **RNDT** treated as quantity-neutral. Extracted `_ONHAND_RECONCILE_SQL` so tests run the shipped query.
- **When:** 2026-06-18 · commit `5b1967c` · **Deployed:** ✅
- **Did it handle it?** Yes — this is *the* structural fix that makes the two screens match.
- **Guard:** anchor + no-doubling + relabel-neutral tests

**Recurrences / new case reports:** _none yet._

---

### 5. Location reconcile dropped 8-digit bins (relocations reverted) — `[WHSE≠HIST]` ✅
**Date:** 2026-06-17 · **Area:** Warehouse Location

- **Issue:** Warehouse kept reverting relocations; "location stays old" even after editing.
- **Example:** PCN 45504 → bin 14051021 (8 digits) kept reverting to the old bin.
- **Root cause:** the placement filter only accepted **6–7-digit** bins (`^[0-9]{6,7}$`), silently dropping every **8-digit** bin (2,306 txns / 41 rows) and named locations; the reconcile fell back to an older placement and overwrote the edit ~5 min later. It shipped "green" **twice** because the test embedded a *copy* of the buggy query.
- **Fixed:** a placement location is now **a numeric bin of ANY length OR a recognized named location**. Extracted `_LOCATION_RECONCILE_SQL` / `reconcile_warehouse_locations()`; tests call the **shipped** function with **8-digit** bins.
- **When:** 2026-06-17 · commit `3fb6463` · **Deployed:** ✅
- **Did it handle it?** Yes — corrected 318 stale rows.
- **Guard:** location-reconcile tests (now run the shipped query)

**Recurrences / new case reports:** _none yet._

---

### 6. Manual bin edits didn't stick — `[WHSE≠HIST]` ✅
**Date:** 2026-06-16 · **Area:** Warehouse Location

- **Issue:** a manual location change in the Warehouse editor reverted within 5 minutes.
- **Example:** ~2,435 stocked PCNs were reverting this way in live data.
- **Root cause:** the reconcile only treated PTWY/RESTOCK/INDF/STOCK as placements; a manual edit logs an **ADJT** carrying the new bin, which was ignored, so it reverted to the last imported PTWY.
- **Fixed:** add ADJT to the placements set (the loc filter still rejects a relabel ADJT carrying an item number, so phantom locations are never written).
- **When:** 2026-06-16 · commit `5de9e4c` · **Deployed:** ✅
- **Did it handle it?** Yes.
- **Guard:** `test_location_reconcile_honors_manual_adjt_edit`

**Recurrences / new case reports:** _none yet._

---

### 7. PCN History ≠ Warehouse on relabels — `[WHSE≠HIST]` ✅
**Date:** 2026-06-16 · **Area:** PCN History

- **Issue:** History on-hand higher than Warehouse; full-reel picks left phantom qty.
- **Example:** PCN 1247 — History 18,000 vs Warehouse 9,000; a 9,000 pick left a phantom 9,000 instead of 0.
- **Root cause:** History's running balance still counted relabel-ADJTs as `+qty`, while the reconcile feeding Warehouse had been fixed (12 Jun) to treat them as neutral. Same data, two formulas.
- **Fixed:** apply the identical `is_relabel` predicate inside the History balance replay, so relabels are quantity-neutral on both screens. PCN 1247 now resolves to 9,000 and each full pick lands at 0.
- **When:** 2026-06-16 · commit `6c2ded8` (+ real-PCN test `5adb737`) · **Deployed:** ✅
- **Did it handle it?** Yes.
- **Guard:** `test_pcn_history_balance_matches_reconcile_on_relabel`

**Recurrences / new case reports:** _none yet._

---

### 8. Warehouse Inventory location never synced (stale bins) — `[WHSE≠HIST]` ✅
**Date:** 2026-06-15 · **Area:** Warehouse Location · **Reported by:** Theresa

- **Issue:** Warehouse showed the old bin; History showed the true one; Theresa could only find stock via History.
- **Example:** ~4,792 stocked rows were stale at first sync.
- **Root cause:** put-aways/relocations arrive as imported **PTWY** transactions, but KOSH only set `loc_to` on its own pick/restock ops and the reconcile synced *on-hand only*.
- **Fixed:** added a location reconcile — set `loc_to` to each stocked PCN's latest placement, ordered by chronological `tran_time` (not row id); picks/purges ignored. First run backfills, then self-heals.
- **When:** 2026-06-15 · commit `b06f52b` · **Deployed:** ✅ (loc_to snapshot `tblWhse_Inventory_locbak_20260615` for rollback)
- **Did it handle it?** Yes.
- **Guard:** `test_location_reconcile_follows_latest_placement`

**Recurrences / new case reports:** _none yet._

---

### 9. Shortage report ignored MFG-Floor stock (false shortages) ✅
**Date:** 2026-06-15 · **Area:** Shortage

- **Issue:** a job whose material was physically on the MFG Floor was flagged short, so Purchasing re-bought parts already on hand.
- **Example:** any job with floor-held material read 0 on-hand for those parts.
- **Root cause:** the report excluded `loc_to='MFG Floor'` rows entirely, so floor stock (held in `mfg_qty`) read as 0.
- **Fixed:** on-hand = `SUM(onhandqty + mfg_qty)`. Safe because the 12 Jun relabel fix guarantees no row has both > 0 (no double-count).
- **When:** 2026-06-15 · commit `0a020fc` · **Deployed:** ✅
- **Did it handle it?** Yes.
- **Guard:** `test_shortage_report_counts_mfg_floor_stock`

**Recurrences / new case reports:** _none yet._

---

### 10. Phantom stock — ~15.3M phantom units — `[WHSE≠HIST]` ✅
**Date:** 2026-06-12 · **Area:** Inventory / Reconcile

- **Issue:** parts with impossible on-hand.
- **Example:** PCN 30314 — 10,000 on-hand **and** 10,000 on MFG Floor.
- **Root cause:** part renumbers logged as `ADJT` carrying the full qty with old/new **item numbers** in the location fields; the reconcile counted them as `+qty` → ~15.3M phantom units across 6,855 PCNs.
- **Fixed:** flag a renumber-ADJT (both loc fields are non-locations, learned from data) and treat it as **quantity-neutral**; normalize MPN in the (pcn,mpn) grouping; temporary downward-only guard. Removed **1,439,125** phantom units across 2,523 rows; idempotent; reversible.
- **When:** 2026-06-12 · commit `0d3682c` (+ monitor `4a5a3ea`, `0ecc242`) · **Deployed:** ✅
- **Did it handle it?** Yes — verified on a staging copy; nightly integrity monitor watches for regressions. Plan: `MAJOR_DATA_INTEGRITY_ISSUE.md`.
- **Guard:** `test_onhand_reconcile_neutralizes_relabel_adjt` + nightly `_nightly_integrity_check`

**Recurrences / new case reports:** _none yet._

---

### 11. Shortage report — false shortage from case-mismatched part numbers ✅
**Date:** 2026-06-12 · **Area:** Shortage

- **Issue:** a part with stock was flagged short, and the same part also appeared as a "same-MPN, other PN" row.
- **Example:** BOM `6779ML-97` vs stock `6779ml-97` — 890 on hand under the other case wasn't counted.
- **Root cause:** the own-stock join was case-sensitive.
- **Fixed:** `UPPER(w.item) = UPPER(aci_pn)` for the own-stock match and the same-MPN exclusion.
- **When:** 2026-06-12 · commit `9a54620` · **Deployed:** ✅
- **Did it handle it?** Yes.
- **Guard:** `test_shortage_report_own_stock_is_case_insensitive`

**Recurrences / new case reports:** _none yet._

---

### 12. SSO auto-create failed for first-time KOSH users ✅
**Date:** 2026-06-05 · **Area:** Auth

- **Issue:** brand-new FORGE users hit *"SSO login failed: Internal error"*; no account was created. Existing users unaffected.
- **Example:** any first-time SSO login.
- **Root cause:** the SSO auto-create branch imported `passlib`, which isn't installed in the KOSH container.
- **Fixed:** use the `bcrypt` library directly (matching the rest of the app's hashing).
- **When:** 2026-06-05 · commit `e7a7bcf` · **Deployed:** ✅
- **Did it handle it?** Yes.
- **Guard:** _(none specific)_

**Recurrences / new case reports:** _none yet._

---

### 13. Shortage report crashed on 11 jobs (qty/cost parsing + overflow) ✅
**Date:** 2026-06-04 · **Area:** Shortage

- **Issue:** shortage generation, Job Line Items, and job export all aborted for certain jobs.
- **Example:** 11 real jobs; e.g. a part number sitting in the cost column (≥ 1,000,000) overflowed `numeric(10,4)`.
- **Root cause:** `qty`/`cost` were cast to INTEGER/DECIMAL, so any non-numeric value (fractional consumables, misaligned rows, reference designators / MPNs in the cost column) crashed the whole query.
- **Fixed:** tolerant parsing — clean number used, else 0; requirements `ceil(qty * order_qty)`; cost integer part capped at 6 digits. Applied to all query sites.
- **When:** 2026-06-04 · commits `a283a43`, `70f6fdd` (+ export `a607a90`, `17191ba`) · **Deployed:** ✅
- **Did it handle it?** Yes — fixed 11 jobs.
- **Guard:** _(covered by shortage suite)_

**Recurrences / new case reports:** _none yet._

---

### 14. Shortage report — structural bugs + "missing lines" ✅
**Date:** 2026-06-03 → 06-04 · **Area:** Shortage · **Reported by:** Theresa ("lost trust in the report")

- **Issue:** lines showing qty 0 or silently dropped; the report ignored same-MPN stock under other part numbers (parts on the shelf flagged short and re-bought); the most critical zero-stock shortages hidden by default.
- **Example:** a job showing 14 of 51 lines; "ZSUB FOR ABOVE" alternate rows collapsing a line to qty 0.
- **Root cause:** (A) alternate-part dedup kept the qty-0 row → zeroed the requirement; (B) MPN-based on-hand match pulled in other jobs' stock and exploded rows; (D) two drifted report generators; (E) "Hide 0 On Hand" toggle defaulted ON.
- **Fixed:** deterministic dedup (qty DESC), job-scoped own-stock match, single shared builder (`_persist_shortage_report`), same-MPN visibility (visibility-only; strict exact-MPN for Chemring; perf 33s→2s), toggle defaults OFF.
- **When:** 2026-06-03/04 · commits `73f8664`, `1e81161`, `2c6515f`, `b48263f` · **Deployed:** ✅
- **Did it handle it?** Yes.
- **Guard:** `test_shortage_report_alt_part_qty_and_same_mpn_visibility`

**Recurrences / new case reports:** _none yet._

---

### 15. Connection leaks + open data routes + wrong shortage cost ✅
**Date:** 2026-06-01 · **Area:** Infra / Security

- **Issue:** pooled-connection leaks (same class as the May outage); several data routes anonymously reachable; shortage cost mis-computed.
- **Example:** `get_po_history`, `get_locations`, `database_health_check` each leaked; `/source*`, PCN/PO/valuation APIs open.
- **Root cause:** missing `finally`/`return_connection`; missing auth gates; cost used full required cost instead of the shortfall.
- **Fixed:** added connection cleanup; required login on those routes; `total_cost` = full-BOM required cost (deduped), `shortage_cost` = shortfall only. Notifications heavy query cached 30s.
- **When:** 2026-06-01 · commit `ef8e4b0` (+ `715862c`) · **Deployed:** ✅
- **Did it handle it?** Yes.
- **Guard:** _(connection-return regression test added 5/29)_

**Recurrences / new case reports:** _none yet._

---

### 16. DB connection leak → pool exhaustion (outage) ✅
**Date:** 2026-05-29 · **Area:** Infra

- **Issue:** the whole app hung after enough page views.
- **Example:** the `maxconn=15` pool exhausted; every page then failed.
- **Root cause:** routes handed raw `psycopg2.connect` connections to `return_connection`, which `putconn` rejected and then dropped — leaking them.
- **Fixed:** `return_connection` now CLOSES any connection putconn rejects; removed dead `pcb_inventory` refs + the orphaned PCB Inventory page; moved to **gunicorn (1 worker / 8 gthreads)** so one slow query no longer stalls everyone; pool 15→20.
- **When:** 2026-05-29 · commits `9ee8436`, `9ff6c81`, `961275b`, `e0d7324` · **Deployed:** ✅
- **Did it handle it?** Yes.
- **Guard:** `test_return_connection_never_leaks_foreign_connection`

**Recurrences / new case reports:** _none yet._

---

### 17. Restock quantity silently dropping by 1 ✅
**Date:** 2026-05-29 · **Area:** Pick / Restock

- **Issue:** restock saved one less unit than typed.
- **Example:** type 50, save 49.
- **Root cause:** scrolling the mouse wheel while hovering the number input decremented its value before submit.
- **Fixed:** neutralize wheel events on quantity inputs.
- **When:** 2026-05-29 · commit `9a258f1` · **Deployed:** ✅
- **Did it handle it?** Yes.
- **Guard:** `test_quantity_fields_are_not_number_spinners`

**Recurrences / new case reports:** _none yet._

---

### 18. Restock — qty autofill / MFG-floor not zeroed — `[WHSE≠HIST]` ✅
**Date:** 2026-05-18 · **Area:** Pick / Restock

- **Issue:** restock pre-filled the wrong quantity, and floor stock wasn't cleared when stock went back into a bin (so it could be double-represented).
- **Example:** restocking a part left `mfg_qty` non-zero alongside the new bin qty.
- **Root cause:** a qty autofill convenience + not zeroing `mfg_qty` on restock.
- **Fixed:** removed the autofill; zero `mfg_qty` on restock. (Keeps on-hand = `onhandqty + mfg_qty` consistent across the two screens.)
- **When:** 2026-05-18 · commit `f5ab95b` · **Deployed:** ✅
- **Did it handle it?** Yes.
- **Guard:** _(none specific)_

**Recurrences / new case reports:** _none yet._

---

## 🎨 Changes that were not bugs (in window)
- **Shortage same-MPN presentation** (12 Jun): moved same-MPN stock from columns to indented rows; Excel export became a stock-only pull sheet. **Intentional reversal — do not reintroduce the columns.** Commits `04fe448`, `1bf0c15`, `a95ac59`, `89bb549`, `ea3f9a2`.
- **Warehouse filter UX** (16 Jun): exact-match filters, preserve filters across pagination, select-on-focus, auto-remove cleared filter, autofocus PCN. Commits `bdae42c`, `9fbc842`, `9dc8e4a`, `4b9dc33`, `e9a20b9`, `35b78e5`.
- **Auto-refresh** (08–09 Jun): 60s seamless in-place morph, holds during data entry. `8c51c48`, `1301e39`.
- **Shortage export bold text** `c42db2a`; **DB config / drop Neon** `c6ca191`; **stop tracking secrets/build artifacts** `11efb2c`.

---

## 📑 Appendix — complete commit index (13 May → 23 Jun 2026, 49 commits)

| Date | Commit | Summary |
|------|--------|---------|
| 2026-06-23 | `e88ae7b` | Shortage report: show real bin location, not MFG Floor; item search exact-or-prefix |
| 2026-06-22 | `1958a08` | Stop on-hand reconcile from wiping fresh restocks |
| 2026-06-18 | `069819e` | Hotfix: PCN History anchor must read RealDictCursor result by alias |
| 2026-06-18 | `5b1967c` | Anchor PCN History on-hand to Warehouse; fix RESTOCK-after-recount doubling |
| 2026-06-17 | `c42db2a` | Shortage Report export: bold all text |
| 2026-06-17 | `3fb6463` | Reconcile: honor any-length numeric bins + text locations |
| 2026-06-17 | `c6ca191` | Update KOSH DB config: rename user to aci, new password, remove Neon |
| 2026-06-16 | `11efb2c` | Sync local changes; stop tracking secrets and build artifacts |
| 2026-06-16 | `5de9e4c` | Reconcile: honor manual location-edit ADJT so relocations stick |
| 2026-06-16 | `e9a20b9` | Warehouse Inventory: clearing an applied filter auto-removes it |
| 2026-06-16 | `4b9dc33` | Warehouse Inventory: select-all on focus for filter fields |
| 2026-06-16 | `9dc8e4a` | Warehouse Inventory: preserve filters across pagination + auto-apply Per Page |
| 2026-06-16 | `9fbc842` | Warehouse Inventory: exact match on MPN, Location, Description filters too |
| 2026-06-16 | `bdae42c` | Warehouse Inventory: exact match on PCN and Item Number filters |
| 2026-06-16 | `5adb737` | tests: add real-PCN relabel-neutral history balance test |
| 2026-06-16 | `6c2ded8` | PCN History: use relabel-neutral on-hand so it matches Warehouse |
| 2026-06-15 | `b06f52b` | Reconcile: sync Warehouse Inventory location from latest placement |
| 2026-06-15 | `0a020fc` | Shortage report: count MFG-Floor stock in on-hand |
| 2026-06-12 | `b05281f` | Doc: TODO/status checklist + April label-mismatch findings |
| 2026-06-12 | `7d6cead` | Doc: record nightly monitor + stale-loc fix done |
| 2026-06-12 | `0ecc242` | Add nightly integrity monitor (Phase 6) |
| 2026-06-12 | `4a5a3ea` | Data integrity: Phase 3 done; integrity monitor + Group C review list |
| 2026-06-12 | `0d3682c` | On-hand: neutralize relabel-ADJT phantom in reconcile (guarded) |
| 2026-06-12 | `ea3f9a2` | Shortage report: Excel = stock-only pull sheet; same-MPN rows carry requirement |
| 2026-06-12 | `89bb549` | Shortage report export: stop dropping zero-on-hand lines |
| 2026-06-12 | `a95ac59` | Shortage report: drop arrow icon + tint from same-MPN rows |
| 2026-06-12 | `9a54620` | Shortage report: fix false shortage from case-mismatched part numbers |
| 2026-06-12 | `1bf0c15` | Shortage report: render same-MPN/other-PN entries as full table rows |
| 2026-06-12 | `04fe448` | Shortage report: replace cross-job same-MPN columns with row entries |
| 2026-06-09 | `1301e39` | Stack auto-refresh pill above dark-mode toggle |
| 2026-06-08 | `8c51c48` | Auto-refresh: 60s interval + seamless in-place morph |
| 2026-06-05 | `e7a7bcf` | Fix SSO auto-create failing for first-time KOSH users |
| 2026-06-04 | `17191ba` | Shortage report: Excel export omits zero-on-hand; revert print-CSS |
| 2026-06-04 | `a607a90` | Shortage report: digital view shows all lines; print drops zero-on-hand |
| 2026-06-04 | `70f6fdd` | Shortage report: guard cost magnitude against numeric(10,4) overflow |
| 2026-06-04 | `a283a43` | Shortage report/job views: tolerant numeric parsing for qty & cost |
| 2026-06-04 | `b48263f` | Shortage report: customer-aware tolerant same-MPN + restore hide-0 default |
| 2026-06-04 | `2c6515f` | Shortage report: show 0-on-hand shortages by default |
| 2026-06-03 | `1e81161` | Shortage report: surface same-MPN stock under other part numbers |
| 2026-06-03 | `73f8664` | Fix shortage report: alternate-part qty, job-scoped on-hand, single builder |
| 2026-06-01 | `715862c` | Speed up notifications page: cache the heavy correlation query (30s) |
| 2026-06-01 | `ef8e4b0` | Fix connection leaks, lock down data routes, correct shortage costs |
| 2026-05-29 | `e0d7324` | Speed: run under gunicorn (concurrency) + global auto-refresh toggle |
| 2026-05-29 | `961275b` | Remove orphaned inventory/inventory.html |
| 2026-05-29 | `9ff6c81` | Remove PCB Inventory tab/page; fix page 500s; harden return_connection |
| 2026-05-29 | `9ee8436` | Fix DB connection leak (pool exhaustion) + remove dead pcb_inventory refs |
| 2026-05-29 | `9a258f1` | Fix restock qty silently dropping by 1 (number-input wheel decrement) |
| 2026-05-22 | `35b78e5` | Autofocus PCN filter on warehouse inventory page |
| 2026-05-18 | `f5ab95b` | Fix restock: remove qty autofill, zero MFG floor on restock |
