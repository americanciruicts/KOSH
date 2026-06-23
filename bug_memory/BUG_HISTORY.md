# KOSH Bug History

Detailed record of bugs fixed in KOSH (newest at top). See `README.md` for the entry
template. **Window: 2026-05-13 → 2026-06-23** (49 commits). Each entry: symptom →
concrete example → root-cause mechanism → fix → scope → regression guard → commit.

Many entries are tagged **[WHSE≠HIST]** — they were causes of the recurring
"Warehouse Inventory data does not equal PCN History" complaint. Read that section
next; it's the spine of almost everything here.

---

## THE CORE SYMPTOM — "Warehouse Inventory data ≠ PCN History"

This is the complaint Theresa reported over and over in different shapes. It is not
one bug; it's a structural consequence of how the two screens were built.

### What the two screens actually are
- **Warehouse Inventory** = the *stored snapshot* in table `tblWhse_Inventory`
  (one+ row per PCN: `onhandqty` = bin qty, `mfg_qty` = MFG-Floor qty, `loc_to` = bin).
  It is maintained by three things: (1) direct operations (stock/pick/restock/edit
  write the row immediately), (2) a background **on-hand reconcile** every 5 min that
  recomputes `onhandqty` from the transaction ledger, and (3) a background **location
  reconcile** that sets `loc_to` from the latest placement.
- **PCN History** = a *derived view* computed live from the `tblTransaction` trail for
  one PCN — every PTWY/PICK/RESTOCK/RNDT/ADJT/INDF/SCRA row, with a running on-hand
  "balance" calculated per row.

So they are **two different computations over partly different inputs.** Whenever the
two computations used different rules, the numbers diverged — and the user saw
"Warehouse says X, History says Y."

### Why they diverged — two independent axes

**1) On-hand quantity divergence.**
The imported Access ledger is incomplete and dirty (see Root Cause below). PCN History
originally *replayed that ledger forward* to get on-hand, which produced wrong numbers
two ways:
   - It counted a **relabel/renumber ADJT** (which carries the part's full qty) as a
     real `+qty` movement → inflated History (e.g. **PCN 1247: History 18,000 vs
     Warehouse 9,000**; a full-reel pick then left a phantom 9,000 instead of 0).
   - It treated an **RNDT recount as a baseline and then added a later RESTOCK** of the
     same parts on top → doubling (e.g. **PCN 41664: History 4,000 vs Warehouse 2,000**;
     also a 79→158 shape).
Meanwhile the on-hand *reconcile* feeding Warehouse Inventory was patched (2026-06-12)
to neutralize relabels — so the two sides were now using **different math**, which is
exactly why they disagreed.

**2) Location divergence.**
Put-aways and relocations happen in the legacy Access system and arrive as imported
**PTWY/ADJT** transactions. PCN History showed those (so it had the *true* current
bin), but Warehouse Inventory's stored `loc_to` was only updated by KOSH's own
pick/restock — it never synced the imported placements. Result: **History showed the
real bin, Warehouse showed a stale one**, and Theresa could only find stock by opening
History. (~4,792 stale rows at first sync.)

### How it was resolved
- **On-hand — architectural fix (2026-06-18, `5b1967c`):** PCN History no longer
  replays the ledger for the absolute number. It **ANCHORS** to Warehouse Inventory:
  the newest History row's balance is *set equal to* the authoritative
  `SUM(onhandqty)` for that PCN, and the trail is walked **backward** from there
  (`compute_anchored_history_balances` / `_history_delta`). Because both screens now
  derive the current on-hand from the *same single source*, they **cannot disagree on
  the current quantity by construction.** (Plus relabel-neutral replay, 2026-06-16,
  so the per-row history deltas are sane.)
- **Location — reconcile (2026-06-15 → 06-17):** a background location reconcile sets
  Warehouse `loc_to` to each stocked PCN's latest real placement (numeric bin of any
  length, or a named area), honoring manual ADJT edits and 8-digit bins. So Warehouse
  catches up to what History shows within ~5 min.

### Residual risk / why it's still not 100% (and why a rebuild is recommended)
- The anchor uses `SUM(onhandqty)` **per PCN**. A PCN with multiple MPN rows, or a
  bin-stock row whose stored `loc_to` literally says "MFG Floor", are edge cases the
  anchor can't fully reason about (12 such items seen 2026-06-23).
- The on-hand reconcile is a **"lower-only", guarded remediation** of a dirty ledger,
  not a clean recomputation — it suppresses known-bad increases. That's a patch over a
  bad data model, not a cure.
- The **source ledger is still ambiguous** (relabels as quantity-ADJTs, item-numbers
  in location fields, out-of-order timestamps). Every new fix here is defense against
  the same root data problem.
→ The durable fix is to **rebuild the inventory / PCN / transaction data model** so
  Warehouse and History are two views of *one clean event log*, not two reconciled
  guesses over a dirty import.

---

## RECURRING ROOT CAUSE (the dirty Access import)
- Part **renumbers/relabels were logged as `ADJT` carrying the full quantity**, with
  old/new **item numbers in the `loc_from`/`loc_to` fields** (not real locations). The
  reconcile read them as stock movements → phantom stock.
- `tran_time` values are **out of chronological order** (Access migrated in batches),
  so ordering by row id is unsafe; everything must order by parsed `tran_time`.
- **Bin location, MFG-Floor, and item-number all share the loc fields**, so selection
  logic repeatedly picked the wrong thing.
- The ledger records **more PICKs than stock-ins** for some parts → forward replay
  nets negative.

---

## DETAILED BUG ENTRIES

## 2026-06-23 — Shortage report showed "MFG Floor" instead of the real bin  [WHSE≠HIST]
- **Reported by:** Theresa (job 5455M / WO# 24214-2 + a warehouse screenshot).
- **Symptom:** the report sent the picker to a location with nothing pickable, and the
  bin that actually held the stock "didn't show on the report."
- **Concrete example:** line 3 (5455M-3) — 278 units sat in **bin 2204207** under PCN
  37656, but the report displayed **"MFG Floor"** (PCN 37654, 0 in bin, 840 on floor).
  Lines 1 & 11 had stock only on the floor (correctly showed MFG Floor).
- **Root cause:** the displayed PCN/location was chosen with
  `array_agg(... ORDER BY (onhandqty + mfg_qty) DESC)[1]` — i.e. by the **highest
  bin+floor total**, so a big floor-only lot out-ranked a smaller real-bin lot and the
  report printed the floor location.
- **Fix:** rank the displayed lot **bin-first**:
  `ORDER BY (onhandqty>0) DESC, onhandqty DESC, floor DESC`. So a lot with real bin
  stock always wins; it falls back to MFG Floor only when nothing is in a bin. Lives in
  the shared `_SHORTAGE_MATCH_SQL`, so it fixes **every** job/report. On-hand SUM still
  includes floor qty, so this did not re-introduce false shortages.
- **Relation to WHSE≠HIST:** same family — the report's "where is it" disagreed with
  where History/the bin said the stock was.
- **Scope:** fleet-wide, **1,492 items** were mis-pointing to a floor lot → 0 after fix.
- **Also in commit:** Warehouse **Item-Number search** changed exact-only →
  exact-wins-else-prefix (`1234L-5` → only that item; `1234L-`/`1234L` → all variants).
- **Guard:** `test_shortage_report_shows_bin_location_not_floor`.
- **Commit:** `e88ae7b` | **Deployed:** yes 2026-06-23 (docker + vercel).

## 2026-06-22 — On-hand reconcile wiped fresh restocks to 0  [WHSE≠HIST]
- **Reported by:** Preet ("user edits/restocks stuff and it's not getting saved";
  Warehouse 0 vs PCN History correct).
- **Symptom:** a real restock saved, then hours later Warehouse showed **0** on-hand
  while PCN History still correctly showed the restock.
- **Concrete example:** PCN 42137 — `parts@` restocked 15 units on 6/18 at 07:30; the
  reconcile zeroed it at 11:31 the same day.
- **Root cause:** the 5-min on-hand reconcile replays the whole ledger. For parts whose
  ledger has more PICKs than stock-ins, the replay nets negative → `GREATEST(0,…)`
  clamps to 0 → the **lower-only guard** then saw `computed 0 < stored 15` and
  overwrote the fresh restock.
- **Fix:** never lower a row whose **most recent material transaction is a fresh
  receipt (RESTOCK/STOCK)** — the receipt is authoritative and the incomplete
  historical ledger must not override it. Genuine phantom-high stock (latest event =
  PICK/RNDT) is still corrected.
- **Relation to WHSE≠HIST:** a direct cause — the reconcile drove Warehouse below what
  History (and reality) showed.
- **Scope + data fix:** **62 production rows** sitting at 0 were backfilled to their
  restock qty (audit tag `restock_wipe_backfill_20260622`). Code fix and data fix were
  separate passes.
- **Guard:** `test_onhand_reconcile_never_wipes_fresh_restock`.
- **Commit:** `1958a08` | **Deployed:** yes 2026-06-22.

## 2026-06-18 — PCN History page crashed for every real PCN (hotfix)
- **Symptom:** opening History for any PCN showed "Error loading PCN history: 0".
- **Root cause:** the new anchor query runs on a `RealDictCursor` (returns dicts), but
  the code read the aggregate as `anchor_row[0]` → `KeyError: 0`. It slipped through
  because the page smoke-test only hit the empty search form and the unit test used a
  plain (tuple) cursor.
- **Fix:** read the aggregate by alias — `SELECT … AS total` → `anchor_row['total']`.
  Added a regression test that exercises the exact RealDictCursor data path the route
  uses, so this class can't recur.
- **Commit:** `069819e` | **Deployed:** yes 2026-06-18.

## 2026-06-18 — RESTOCK-after-recount doubling (the WHSE≠HIST architectural fix)  [WHSE≠HIST]
- **Symptom:** PCN History on-hand was double the Warehouse value.
- **Concrete example:** PCN 41664 — History 4,000 vs Warehouse 2,000; also a 79→158
  shape on other parts.
- **Root cause:** History replayed the incomplete ledger forward, treated an **RNDT
  recount as a baseline**, then **added a later RESTOCK of the same parts on top**.
- **Fix (architectural):** PCN History now **anchors** its on-hand to the authoritative
  Warehouse value and walks the transaction trail **backward** from it
  (`compute_anchored_history_balances` / `_history_delta`) — so the two views can never
  disagree on the current number. Also: **SCRA** now subtracts (was unhandled, left
  scrapped qty on hand); **RNDT** treated as quantity-neutral in History. Extracted
  `_ONHAND_RECONCILE_SQL` so the regression suite runs the shipped query, not a copy.
- **Relation to WHSE≠HIST:** this is *the* fix that structurally guarantees they match.
- **Guard:** anchor + no-doubling + relabel-neutral tests.
- **Commit:** `5b1967c` | **Deployed:** yes 2026-06-18.

## 2026-06-17 — Location reconcile dropped 8-digit bins (relocations reverted)  [WHSE≠HIST]
- **Symptom:** Warehouse kept reverting relocations to certain bins; "location stays
  old" even after editing.
- **Concrete example:** PCN 45504 → bin 14051021 (8 digits) kept reverting.
- **Root cause:** the placement filter only accepted **6–7-digit** bins
  (`^[0-9]{6,7}$`), silently dropping every **8-digit** bin (2,306 txns / 41 rows) and
  named locations like "back room". With the real placement excluded, the reconcile
  fell back to an older placement and overwrote the edit ~5 min later. It had shipped
  "green" **twice** because the regression test embedded a *copy* of the buggy
  `{6,7}` query and used 7-digit bins.
- **Fix:** a placement location is now **a numeric bin of ANY length OR a recognized
  named location** (learned from non-ADJT activity, so it survives the 10-char loc
  truncation). Extracted `_LOCATION_RECONCILE_SQL` / `reconcile_warehouse_locations()`;
  tests now call the **shipped** function with **8-digit** bins.
- **Relation to WHSE≠HIST:** location axis — kept Warehouse's bin stale vs History.
- **Scope:** corrected 318 stale rows.
- **Commit:** `3fb6463` | **Deployed:** yes 2026-06-17.

## 2026-06-16 — Manual bin edits didn't stick  [WHSE≠HIST]
- **Symptom:** a manual location change in the Warehouse editor reverted within 5 min.
- **Root cause:** the location reconcile only treated PTWY/RESTOCK/INDF/STOCK as
  placements. A manual edit saves `loc_to` **and** logs an `ADJT` carrying the new bin —
  but ADJT was ignored, so the reconcile reverted the row to the last imported PTWY.
- **Fix:** add ADJT to the placements set. The loc filter still rejects a relabel/
  renumber ADJT (which carries an item number in `loc_to`), so phantom locations are
  never written.
- **Scope:** live data showed **2,435 stocked PCNs** reverting this way.
- **Guard:** `test_location_reconcile_honors_manual_adjt_edit`.
- **Commit:** `5de9e4c` | **Deployed:** yes 2026-06-16.

## 2026-06-16 — PCN History didn't match Warehouse on relabels  [WHSE≠HIST]
- **Symptom:** History on-hand higher than Warehouse; full-reel picks left phantom qty.
- **Concrete example:** PCN 1247 — History 18,000 vs Warehouse 9,000; a 9,000 pick
  left a phantom 9,000 instead of 0.
- **Root cause:** History's running balance still counted relabel-ADJTs as `+qty`,
  while the reconcile feeding Warehouse had been fixed (6/12) to treat them as neutral.
  Same data, two different formulas → mismatch.
- **Fix:** apply the identical `is_relabel` predicate (same location vocabulary as the
  reconcile) inside the History balance replay, so relabels are quantity-neutral on
  both screens. PCN 1247 now resolves to 9,000 and each full pick lands at 0.
- **Guard:** `test_pcn_history_balance_matches_reconcile_on_relabel` + a real-PCN test
  (`5adb737`) exercised against live relabel PCNs incl. 1247.
- **Commit:** `6c2ded8` | **Deployed:** yes 2026-06-16.

## 2026-06-15 — Warehouse Inventory location never synced (stale bins)  [WHSE≠HIST]
- **Symptom:** Warehouse showed the old bin; History showed the true one; Theresa could
  only find stock via History.
- **Root cause:** put-aways/relocations arrive as imported **PTWY** transactions, but
  KOSH only set `loc_to` on its own pick/restock ops and the reconcile synced *on-hand
  only* — never location.
- **Fix:** add a location reconcile to the 5-min loop: set `loc_to` to each stocked
  PCN's latest **placement** (PTWY/RESTOCK/INDF/STOCK to a real bin), ordered by
  chronological `tran_time` (NOT row id, which the Access import left out of order).
  Picks/purges are ignored so a partial pick can't drag remaining bin stock onto the
  floor. First run backfilled **~4,792** stale rows; self-heals after.
- **Guard:** `test_location_reconcile_follows_latest_placement`. loc_to snapshotted to
  `tblWhse_Inventory_locbak_20260615` for rollback.
- **Commit:** `b06f52b` | **Deployed:** yes 2026-06-15.

## 2026-06-15 — Shortage report ignored MFG-Floor stock (false shortages)
- **Symptom:** a job whose material was physically on the MFG Floor was flagged short,
  so Purchasing re-bought parts already on hand.
- **Root cause:** the report excluded `loc_to='MFG Floor'` rows entirely, so floor
  stock (held in `mfg_qty`) read as 0 on-hand.
- **Fix:** on-hand = `SUM(onhandqty + mfg_qty)`. Safe because the 6/12 relabel fix
  guarantees no row has both `onhandqty>0` AND `mfg_qty>0` (no double-count).
- **Guard:** `test_shortage_report_counts_mfg_floor_stock`.
- **Commit:** `0a020fc` | **Deployed:** yes 2026-06-15.

## 2026-06-12 — Phantom stock root cause (~15.3M phantom units)  [WHSE≠HIST]
- **Symptom:** parts with impossible on-hand.
- **Concrete example:** PCN 30314 — 10,000 on-hand AND 10,000 on MFG Floor.
- **Root cause:** part renumbers logged as `ADJT` carrying the part's **full qty** with
  old/new **item numbers** in `loc_from`/`loc_to`. The reconcile counted them as `+qty`,
  injecting **~15.3M phantom units across 6,855 PCNs**.
- **Fix:** flag a renumber-ADJT (both loc fields are non-locations, learned from data
  so it survives the 10-char `loc_to` truncation) and treat it as **quantity-neutral**.
  Normalize MPN in the (pcn,mpn) grouping (strip `-# ./`) so reel spelling variants
  don't fragment history. Temporary downward-only guard while the separate reconcile
  non-convergence is worked. Removed **1,439,125** phantom units across 2,523 rows;
  zero phantom created; idempotent; reversible via the Phase-0 snapshot.
- **Relation to WHSE≠HIST:** this fix is *why* History had to be made relabel-neutral
  too (6/16) — otherwise the two screens used different relabel math.
- **Guard:** `test_onhand_reconcile_neutralizes_relabel_adjt` + nightly integrity
  monitor (`_nightly_integrity_check`, `tblIntegrityCheckLog`). Plan:
  `MAJOR_DATA_INTEGRITY_ISSUE.md`. Phase/monitor commits `4a5a3ea`, `0ecc242`; docs
  `b05281f`, `7d6cead`.
- **Commit:** `0d3682c` | **Deployed:** yes 2026-06-12.

## 2026-06-12 — Shortage report: false shortage from case-mismatched part numbers
- **Symptom:** a part with stock was flagged short, and the same part also appeared as
  a "same-MPN, other PN" row.
- **Concrete example:** BOM `6779ML-97` vs stock `6779ml-97` — 890 on hand under the
  other case wasn't counted.
- **Root cause:** the own-stock join was case-sensitive.
- **Fix:** `UPPER(w.item)=UPPER(aci_pn)` for the own-stock match and the same-MPN
  exclusion. Genuinely different PNs with the same MPN still show as visibility rows.
- **Guard:** `test_shortage_report_own_stock_is_case_insensitive`.
- **Commit:** `9a54620` | **Deployed:** yes 2026-06-12.

## 2026-06-12 — Shortage report same-MPN presentation reworked (not a bug)
- Moved same-MPN/other-PN stock from two columns to indented row entries; Excel export
  became a stock-only **pull sheet** (rows with on-hand>0), with same-MPN rows carrying
  the parent line's QTY/ORDER/REQ. **Intentional reversal — do not reintroduce the
  columns.** Matching logic unchanged (tolerant; strict exact-MPN for Chemring).
- **Commits:** `04fe448`, `1bf0c15`, `a95ac59`, `89bb549`, `ea3f9a2`.

## 2026-06-05 — SSO auto-create failed for first-time KOSH users
- **Symptom:** brand-new FORGE users hit "SSO login failed: Internal error"; no account
  was created. Existing users were unaffected (they skip auto-create).
- **Root cause:** the SSO auto-create branch imported `passlib`, which isn't installed
  in the KOSH container.
- **Fix:** use the `bcrypt` library directly (matching the rest of the app's hashing).
- **Commit:** `e7a7bcf` | **Deployed:** yes 2026-06-05.

## 2026-06-04 — Shortage report crashed on 11 jobs (qty/cost parsing + overflow)
- **Symptom:** shortage generation, Job Line Items, and job export all aborted for
  certain jobs.
- **Root cause:** `qty`/`cost` were cast to INTEGER/DECIMAL, so any non-numeric value
  (fractional consumables like 0.0357, or misaligned rows holding a reference
  designator / MPN / a part number ≥ 1,000,000 that overflowed `numeric(10,4)`) crashed
  the whole query.
- **Fix:** tolerant parsing — a clean number is used, anything else becomes 0;
  requirements computed as `ceil(qty * order_qty)` so fractional consumables round the
  total up and never under-order; cost integer part capped at 6 digits. Applied to all
  three query sites + the Python req math. Fixed 11 real jobs.
- **Commits:** `a283a43`, `70f6fdd` (+ export zero-on-hand corrections `a607a90`,
  `17191ba`) | **Deployed:** yes 2026-06-04.

## 2026-06-03/04 — Shortage report structural bugs + "missing lines"
- **Symptoms:** lines showing qty 0 or silently dropped; the report ignored same-MPN
  stock filed under other jobs' part numbers (parts on the shelf flagged short and
  re-bought); the most critical zero-stock shortages hidden by default.
- **Root causes:**
  - **A** — alternate parts (same `aci_pn`, e.g. "ZSUB FOR ABOVE") have blank/0 qty;
    the BOM dedup `DISTINCT ON (aci_pn) ORDER BY aci_pn, line` could keep the qty-0 row,
    zeroing the line's requirement and dropping a real shortage. → order by **qty DESC**.
  - **B** — on-hand matched by `(aci_pn=item OR bom_mpn=mpn)`, so the MPN branch pulled
    in every other job's stock of the same MPN and exploded one BOM line into a row per
    foreign PCN. → match the job's **own** part only (`item=aci_pn`), sum its lots,
    one row per line.
  - **D** — the Shortage Report page and the Job-tab button had **two duplicate ~80-line
    generators** that had drifted. → one shared `_persist_shortage_report`.
  - **E** — the "Hide 0 On Hand" toggle defaulted ON, hiding parts with no stock at all
    (the worst shortages); users saw e.g. 14 of 51 lines and called it inaccurate. →
    default OFF.
- **Then restored same-MPN visibility** (`1e81161`) as visibility-only (does not
  double-allocate another job's committed stock), customer-aware (tolerant generally,
  strict exact-MPN for Chemring; perf 33s→2s via a materialized `mpn_pool`).
- **Guard:** `test_shortage_report_alt_part_qty_and_same_mpn_visibility`.
- **Commits:** `73f8664`, `1e81161`, `2c6515f`, `b48263f` | **Deployed:** yes 2026-06.

## 2026-06-01 — Connection leaks + open data routes + wrong shortage cost
- **Root cause/fixes:** `get_po_history`, `get_locations`, `database_health_check`
  leaked a pooled connection (same class as the May pool-exhaustion outage) → added
  `finally`/`return_connection`. Several data routes (`/source*`, PCN/PO/valuation
  APIs) were anonymously reachable → require login. Shortage `total_cost` corrected to
  full-BOM required cost (deduped per line) and `shortage_cost` to the shortfall only.
  Notifications page heavy query cached 30s (`715862c`).
- **Commit:** `ef8e4b0` | **Deployed:** yes 2026-06-01.

## 2026-05-29 — DB connection leak → pool exhaustion (outage class) + gunicorn
- **Symptom:** the whole app hung after enough page views.
- **Root cause:** routes handed raw `psycopg2.connect` connections to
  `return_connection`, which `putconn` rejected and then dropped — leaking them until
  the `maxconn=15` pool was exhausted.
- **Fix:** `return_connection` now CLOSES any connection putconn rejects; removed dead
  `pcb_inventory` DB refs and the orphaned PCB Inventory page (also fixed page 500s
  found by an all-pages smoke test). Switched the container from the single-threaded
  Flask dev server to **gunicorn (1 worker / 8 gthreads)** so one slow query no longer
  stalls every user; pool bumped 15→20.
- **Commits:** `9ee8436`, `9ff6c81`, `961275b`, `e0d7324` | **Deployed:** yes 2026-05-29.

## 2026-05-29 — Restock qty silently dropping by 1
- **Symptom:** restock saved one less unit than typed.
- **Root cause:** scrolling the mouse wheel while hovering the number input decremented
  its value before submit.
- **Fix:** neutralize wheel events on quantity inputs.
- **Commit:** `9a258f1` | **Deployed:** yes 2026-05-29.

## 2026-05-18 — Restock: stop autofilling qty; zero MFG floor on restock
- **Fix:** removed the qty autofill (it pre-filled wrong quantities) and zero the
  MFG-floor qty when stock is restocked back into a bin (so floor stock isn't
  double-represented once it's back in a bin).
- **Relation to WHSE≠HIST:** keeping `mfg_qty` correct on restock is what lets on-hand
  (`onhandqty + mfg_qty`) stay consistent between the two screens.
- **Commit:** `f5ab95b` | **Deployed:** yes 2026-05-18.

---

## Infra / UX / cosmetic in window (summary — not bugs)
- **Warehouse filter UX** (06-16): exact match on PCN/Item then MPN/Location/
  Description (`bdae42c`, `9fbc842`); preserve filters across pagination + auto-apply
  per-page (`9dc8e4a`); select-all on focus (`4b9dc33`); auto-remove a cleared filter
  (`e9a20b9`); autofocus PCN filter (`35b78e5`, 05-22). *(Note: 06-16 made Item an
  exact match; 06-23 then changed it to exact-wins-else-prefix per Theresa.)*
- **Auto-refresh** (06-08/09): 60s seamless in-place DOM morph, holds during data
  entry; pill stacked above dark-mode toggle (`8c51c48`, `1301e39`).
- **Shortage export** bold all text (`c42db2a`, 06-17).
- **Infra:** DB config → user `aci`, drop Neon (`c6ca191`, 06-17); stop tracking
  secrets/build artifacts (`11efb2c`, 06-16).

---

## APPENDIX — COMPLETE COMMIT INDEX (2026-05-13 → 2026-06-23, 49 commits)
- 2026-06-23 | `e88ae7b` | Shortage report: show real bin location, not MFG Floor; item search exact-or-prefix
- 2026-06-22 | `1958a08` | Stop on-hand reconcile from wiping fresh restocks
- 2026-06-18 | `069819e` | Hotfix: PCN History anchor query must read RealDictCursor result by alias
- 2026-06-18 | `5b1967c` | Anchor PCN History on-hand to Warehouse Inventory; fix RESTOCK-after-recount doubling
- 2026-06-17 | `c42db2a` | Shortage Report export: bold all text
- 2026-06-17 | `3fb6463` | Reconcile: honor any-length numeric bins + text locations (fix recurring stale location)
- 2026-06-17 | `c6ca191` | Update KOSH DB config: rename user to aci, new password, remove Neon DB
- 2026-06-16 | `11efb2c` | Sync local changes; stop tracking secrets and build artifacts
- 2026-06-16 | `5de9e4c` | Reconcile: honor manual location-edit ADJT so relocations stick
- 2026-06-16 | `e9a20b9` | Warehouse Inventory: clearing an applied filter auto-removes it
- 2026-06-16 | `4b9dc33` | Warehouse Inventory: select-all on focus for filter fields
- 2026-06-16 | `9dc8e4a` | Warehouse Inventory: preserve filters across pagination + auto-apply Per Page
- 2026-06-16 | `9fbc842` | Warehouse Inventory: exact match on MPN, Location, Description filters too
- 2026-06-16 | `bdae42c` | Warehouse Inventory: exact match on PCN and Item Number filters
- 2026-06-16 | `5adb737` | tests: add real-PCN relabel-neutral history balance test
- 2026-06-16 | `6c2ded8` | PCN History: use relabel-neutral on-hand so it matches Warehouse
- 2026-06-15 | `b06f52b` | Reconcile: sync Warehouse Inventory location from latest placement
- 2026-06-15 | `0a020fc` | Shortage report: count MFG-Floor stock in on-hand
- 2026-06-12 | `b05281f` | Doc: add TODO/status checklist + April-1-2 label-mismatch findings
- 2026-06-12 | `7d6cead` | Doc: record #1 (nightly monitor) + #2 (stale-loc fix) done; monitor verified live
- 2026-06-12 | `0ecc242` | Add nightly integrity monitor (Phase 6)
- 2026-06-12 | `4a5a3ea` | Data integrity: Phase 3 done; integrity monitor + Group C review list
- 2026-06-12 | `0d3682c` | On-hand: neutralize relabel-ADJT phantom in reconcile (downward-only, guarded)
- 2026-06-12 | `ea3f9a2` | Shortage report: Excel = stock-only pull sheet; same-MPN rows carry requirement
- 2026-06-12 | `89bb549` | Shortage report export: stop dropping zero-on-hand lines (honor Hide-0 toggle)
- 2026-06-12 | `a95ac59` | Shortage report: drop arrow icon + tint from same-MPN rows in digital view
- 2026-06-12 | `9a54620` | Shortage report: fix false shortage from case-mismatched part numbers
- 2026-06-12 | `1bf0c15` | Shortage report: render same-MPN/other-PN entries as full table rows
- 2026-06-12 | `04fe448` | Shortage report: replace cross-job same-MPN columns with row entries
- 2026-06-09 | `1301e39` | Stack auto-refresh pill above dark-mode toggle so both are visible
- 2026-06-08 | `8c51c48` | Auto-refresh: 60s interval + seamless in-place morph (no visible reload)
- 2026-06-05 | `e7a7bcf` | Fix SSO auto-create failing for first-time KOSH users
- 2026-06-04 | `17191ba` | Shortage report: Excel export omits zero-on-hand; revert print-CSS approach
- 2026-06-04 | `a607a90` | Shortage report: digital view shows all lines; print drops zero-on-hand
- 2026-06-04 | `70f6fdd` | Shortage report: guard cost magnitude against numeric(10,4) overflow
- 2026-06-04 | `a283a43` | Shortage report/job views: tolerant numeric parsing for qty & cost
- 2026-06-04 | `b48263f` | Shortage report: customer-aware tolerant same-MPN visibility + restore hide-0 default
- 2026-06-04 | `2c6515f` | Shortage report: show 0-on-hand shortages by default
- 2026-06-03 | `1e81161` | Shortage report: surface same-MPN stock under other part numbers
- 2026-06-03 | `73f8664` | Fix shortage report: alternate-part qty, job-scoped on-hand, single builder
- 2026-06-01 | `715862c` | Speed up notifications page: cache the heavy correlation query (30s)
- 2026-06-01 | `ef8e4b0` | Fix connection leaks, lock down data routes, correct shortage costs
- 2026-05-29 | `e0d7324` | Speed: run under gunicorn (concurrency) + global auto-refresh toggle
- 2026-05-29 | `961275b` | Remove orphaned inventory/inventory.html (PCB Inventory page template)
- 2026-05-29 | `9ff6c81` | Remove PCB Inventory tab/page; fix page 500s; harden return_connection
- 2026-05-29 | `9ee8436` | Fix DB connection leak (pool exhaustion) + remove dead pcb_inventory DB refs
- 2026-05-29 | `9a258f1` | Fix restock qty silently dropping by 1 (number-input wheel decrement)
- 2026-05-22 | `35b78e5` | Autofocus PCN filter on warehouse inventory page
- 2026-05-18 | `f5ab95b` | Fix restock: remove qty autofill, zero MFG floor on restock
