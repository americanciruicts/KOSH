<h1 align="center">🐞 KOSH — BUG HISTORY</h1>

<p align="center">
  <b>Permanent, human-readable record of every bug fixed in KOSH.</b><br>
  <span style="color:#7f8c8d">Window covered: <b>13 May 2026 → 23 June 2026</b> · 49 commits</span><br>
  <span style="color:#7f8c8d">Document created: <b>2026-06-23</b> · Last updated: <b>2026-06-23</b></span>
</p>

> 📌 **How to use:** one entry per distinct bug, newest first. When the **same** bug is
> reported again, append a dated line under that entry's **Recurrences** section — never
> delete the original. See [`README.md`](./README.md).

---

## 🎨 Legend

**Severity (color):**
🟥 <span style="color:#c0392b">**Critical**</span> — data integrity / outage ·
🟧 <span style="color:#e67e22">**High**</span> — wrong data shown to users ·
🟨 <span style="color:#f1c40f">**Medium**</span> — crash / UX-data ·
🟩 <span style="color:#27ae60">**Low**</span> — isolated

**Status:** ✅ Fixed & deployed · 🟡 Partial · 🔴 Open · 🔁 Recurring
**Tag:** `[WHSE≠HIST]` = a cause of the recurring *"Warehouse Inventory ≠ PCN History"* complaint.

---

## 📋 Quick reference

| # | Date | Bug | Area | Sev | Status |
|:-:|------|-----|------|:---:|:------:|
| [1](#bug1) | 2026-06-23 | Shortage report showed "MFG Floor" instead of the real bin | Shortage / Location | 🟧 | ✅ |
| [2](#bug2) | 2026-06-22 | On-hand reconcile wiped fresh restocks to 0 | Inventory / Reconcile | 🟥 | ✅ |
| [3](#bug3) | 2026-06-18 | PCN History page crashed for every PCN | PCN History | 🟨 | ✅ |
| [4](#bug4) | 2026-06-18 | RESTOCK-after-recount doubling (History ≠ Warehouse) | Inventory / History | 🟥 | ✅ |
| [5](#bug5) | 2026-06-17 | Location reconcile dropped 8-digit bins | Warehouse Location | 🟧 | ✅ |
| [6](#bug6) | 2026-06-16 | Manual bin edits didn't stick | Warehouse Location | 🟧 | ✅ |
| [7](#bug7) | 2026-06-16 | PCN History ≠ Warehouse on relabels | PCN History | 🟥 | ✅ |
| [8](#bug8) | 2026-06-15 | Warehouse location never synced (stale bins) | Warehouse Location | 🟧 | ✅ |
| [9](#bug9) | 2026-06-15 | Shortage report ignored MFG-Floor stock | Shortage | 🟧 | ✅ |
| [10](#bug10) | 2026-06-12 | Phantom stock — ~15.3M phantom units | Inventory / Reconcile | 🟥 | ✅ |
| [11](#bug11) | 2026-06-12 | False shortage from case-mismatched part numbers | Shortage | 🟧 | ✅ |
| [12](#bug12) | 2026-06-05 | SSO auto-create failed for first-time users | Auth | 🟩 | ✅ |
| [13](#bug13) | 2026-06-04 | Shortage report crashed on 11 jobs (qty/cost parse) | Shortage | 🟨 | ✅ |
| [14](#bug14) | 2026-06-03 | Shortage structural bugs + "missing lines" | Shortage | 🟧 | ✅ |
| [15](#bug15) | 2026-06-01 | Connection leaks + open data routes + wrong cost | Infra / Security | 🟧 | ✅ |
| [16](#bug16) | 2026-05-29 | DB connection leak → pool exhaustion (outage) | Infra | 🟥 | ✅ |
| [17](#bug17) | 2026-05-29 | Restock quantity silently dropping by 1 | Pick / Restock | 🟨 | ✅ |
| [18](#bug18) | 2026-05-18 | Restock qty autofill / MFG-floor not zeroed | Pick / Restock | 🟨 | ✅ |

---

## 🧭 The core symptom — <span style="color:#c0392b">"Warehouse Inventory ≠ PCN History"</span>

This is the complaint Theresa reported again and again in different shapes. It isn't one
bug — it's structural. The two screens are **two different computations**:

| Screen | What it is | Kept up to date by |
|--------|-----------|--------------------|
| **Warehouse Inventory** | Stored snapshot in `tblWhse_Inventory` (`onhandqty` = bin, `mfg_qty` = MFG-Floor, `loc_to` = bin) | direct ops + 5-min on-hand reconcile + location reconcile |
| **PCN History** | Live view derived from the `tblTransaction` trail, with a running on-hand balance | recomputed on every view |

- **● Quantity divergence** — History replayed the dirty ledger forward (counting relabel
  ADJTs as `+qty`; stacking a RESTOCK on top of an RNDT recount) while the reconcile used
  different math.
  - ◦ *Example:* PCN **1247** — History 18,000 vs Warehouse 9,000.
  - ◦ *Example:* PCN **41664** — History 4,000 vs Warehouse 2,000.
- **● Location divergence** — relocations arrive as imported PTWY/ADJT; History showed the
  true bin, Warehouse's `loc_to` never synced (~4,792 stale rows).
- **● Resolution** — History now **anchors to Warehouse** and walks backward
  (`compute_anchored_history_balances` @ `app.py` **L3294**), so the current on-hand has a
  **single source of truth**; the location reconcile syncs `loc_to` within ~5 min.
- **● ⚠️ Still not 100%** — the anchor sums per-PCN (multi-MPN edge cases); the reconcile is
  a "lower-only" patch over a dirty ledger; the source data is still ambiguous.
  ➡️ <span style="color:#c0392b">**Durable fix = rebuild the inventory / PCN / transaction data model.**</span>

---

## 🔌 Recurring root cause — the dirty Access import
- **●** Renumbers/relabels logged as `ADJT` carrying the **full qty** with **item numbers in
  the location fields** → counted as stock movements (phantom stock).
- **●** `tran_time` is **out of order** (batch migration) → never sort by row id.
- **●** Bin / MFG-Floor / item-number all share the loc fields → wrong selection.
- **●** Ledger has **more PICKs than stock-ins** for some parts → forward replay goes negative.

---

# 📒 Detailed entries

---

<h3 id="bug20">🟥 <span style="color:#c0392b">20 — On-hand double-counted across bin + MFG floor (Warehouse ≠ PCN History; restock compounds)</span> <code>[WHSE≠HIST]</code> ✅</h3>

> **Date:** 2026-06-26 · **Severity:** 🟥 Critical · **Area:** Inventory / On-hand · **Reported by:** Preet ("onhand 1100 + mfg 1100 → restock → 2200")

- **● Issue (what was wrong):** the same physical units were counted in BOTH `onhandqty` (bin) and `mfg_qty` (MFG floor) on a row. Views that sum bin+floor (Shortage report) showed 2× the real qty, while PCN History (anchored to `onhandqty` only) showed 1×, so the two screens disagreed; and a restock (`onhandqty += qty`) on such a row compounded the double.
- **● Example:** PCN **29862** (8461L-75): `onhandqty=140`, `mfg_qty=140`, `loc_to=MFG Floor` → Shortage showed **280**, PCN History showed **140**. Its only KOSH txn was a RESTOCK whose `loc_to` was 'MFG Floor'. 10 rows in this exact `onhand==mfg` state (5 floor-located, 5 bin-located).
- **● Root cause:** bin and floor are meant to be DISJOINT (a unit is in a bin OR on the floor) but nothing enforced it; the on-hand reconcile re-derived bin on-hand for parts already on the floor (RESTOCK-to-MFG-Floor counts as +bin on the ledger) while `mfg_qty` still held them. Also the three views used DIFFERENT on-hand definitions (onhand-only vs onhand+floor), so they could never agree when floor stock existed.
- **● Fixed (what changed):** (1) PCN History anchor now sums `onhandqty + mfg_qty` — one definition across all three views; (2) new shipped guard `reconcile_floor_onhand` (wired into the 5-min sync) zeroes phantom bin on-hand on rows physically on the MFG floor (lower-only, audit-logged) — fixes the 5 floor rows + prevents floor-class recurrence; (3) removed the false "0 rows with both onhand>0 and mfg>0" comment in the shortage SQL. Bin-located doubles are surfaced for explicit review, not auto-mutated.
- **🛠️ Files & lines:** `app.py` — `pcn_history` anchor; `_FLOOR_ONHAND_DEDUPE_SQL` + `reconcile_floor_onhand`; `_sync_onhand_from_transactions` wiring; shortage on-hand comment. Folder: [`bug-20-onhand-mfg-floor-double-count/`](./bug-20-onhand-mfg-floor-double-count/).
- **● When:** 2026-06-26 · commit `cd542da` · **Deployed:** ✅ Docker + Vercel.
- **● Did it handle it?:** **Yes** — 3-level test-user run all green:
  - **L1 code:** regression suite **28/28** (incl. the 2 new bug-20 guards) + all **20** per-bug verifiers pass.
  - **L2 affected views as test user:** Warehouse Inventory **matches PCN History for all 10 PCNs** (one on-hand definition now); `/pcn-history` + `/warehouse-inventory` render 200 for the test user. **12/12.**
  - **L3 full workflow as test user:** home → warehouse → shortage → PCN history → pick → restock all render for `regression@test.com`. **8/8.**
  - Live container: the shipped `reconcile_floor_onhand` guard de-duped **19 floor-located rows (1,637 phantom bin units removed)**, audit-logged (`floor_onhand_dedupe`); the 5 floor-affected rows are now `onhand=0, mfg=N`.
  - **All 10 double rows resolved; whole-table `remaining_doubles = 0`.** After tracing each of the 5 bin-located rows (all = received → picked to floor → recounted → **put away back into a bin**, so the parts are in the bin and `mfg_qty` was a stale floor count), the stale `mfg_qty` was zeroed for those 5 (audit `bug20_bin_stale_mfg_zeroed`, `onhandqty` untouched → no stock lost). Re-run L2: all 10 PCNs match AND de-doubled.
- **● Guard:** `test_floor_onhand_dedupe_zeroes_phantom_bin_not_floor_or_bins`, `test_pcn_history_anchor_counts_mfg_floor_stock`, `verify-bug-20-fix.py`. Full pass/fail log: [`TEST-RUN-2026-06-26-bug20.md`](./TEST-RUN-2026-06-26-bug20.md).
- **● Scope/impact:** floor class (19 rows) auto-fixed by the shipped guard + guarded against recurrence; 5 bin-located doubles fixed by a verified, audit-logged one-time correction (zero stale mfg, keep bin on-hand). Whole-table double-count now zero, no data loss. The bin case is NOT a blanket guard (a legitimate partial-pick split also has onhand+mfg both >0, so auto-zeroing mfg there would lose floor stock); new occurrences are surfaced by the integrity monitor for verified one-time correction.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug19">🟥 <span style="color:#c0392b">19 — Over-pick buried later stock → ledger computed 0 (false WHSE≠HIST)</span> <code>[WHSE≠HIST]</code> ✅</h3>

> **Date:** 2026-06-25 · **Severity:** 🟥 Critical · **Area:** Inventory / Reconcile · **Reported by:** Preet (Warehouse vs PCN History discrepancy review)

- **● Issue** — the reconcile/diagnostic ledger computed **0 on-hand** for parts that physically have stock, making Warehouse Inventory look like phantom stock vs the ledger. A proposed one-off `bug_memory/fix-bidirectional-reconcile.sql` would have "corrected" Warehouse *down to those 0s*, deleting real inventory.
- **● Example** — PCN **9141** (6779ML-100): `RNDT 1800`, then `PICK 3600` (only 1800 ever existed — a double-entered/erroneous pick), then `RESTOCK 1800`. Old math: `1800 − 3600 + 1800 = 0`. True on-hand: **1800** (in bin 1501601). 25 PCNs (~5,800 units) were flagged this way; all latest-event = RESTOCK.
- **● Root cause** — the `net` ledger **summed every delta and clamped once** with `GREATEST(0, base + Σdelta)`. An over-pick drove the running total negative and a later receipt only refilled it back toward 0, so the receipt's units were "absorbed" by the earlier impossible pick.
- **● Fixed (what changed)** — replaced sum-then-clamp with a **running floor at 0** (Skorokhod reflection): `on-hand = (base + Σdelta) − LEAST(0, base + min running balance)`. You can't pick below empty, so the dip is absorbed at the pick and later receipts rebuild from 0. Implemented as `net_deltas → net_run (window) → net` in `app.py` `_ONHAND_RECONCILE_SQL` (the shipped `reconcile_onhand_from_ledger`) and mirrored in the nightly integrity-monitor ledger.
- **● When** — 2026-06-25 · commit `3c32a8e` · **Deployed:** ✅ Docker + Vercel.
- **● Did it handle it?** — Yes. Live-DB validation: pcn 9141 ledger `0 → 1800` (= Warehouse); phantom rows (WHSE > ledger by >5) **25 → 0**; invariant **new ≥ old across all 35,294 (pcn,mpn) groups, 0 violations** (37 raised). Since the reconcile is **lower-only**, a never-lower ledger can only lower *less* → **provably no new data loss**. **No warehouse rows were mutated** — fixing the math made Warehouse and the ledger agree on their own.
- **● Guard** — `tests/regression_tests.py::test_onhand_reconcile_overpick_does_not_zero_refilled_stock` (over-pick + non-receipt refill, phantom-high warehouse → reconcile lowers to the true 1800, not 0).
- **● Scope/impact** — code/computation fix only; no data backfill needed. The `fix-bidirectional-reconcile.sql` script was **NOT run** (it would have wiped the 25 RESTOCK rows).
- **🧪 Full test-user run (2026-06-25)** — entire bug list re-verified: **all 19 per-bug verifiers PASS** + **regression suite 26/26** (incl. this bug's new guard) + 28 page routes, 0 server errors. Details & per-action output: [`TEST-RUN-2026-06-25-all-bugs-test-user.md`](./TEST-RUN-2026-06-25-all-bugs-test-user.md). Folder: [`bug-19-overpick-buried-later-stock/`](./bug-19-overpick-buried-later-stock/).
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug1">🟧 <span style="color:#e67e22">1 — Shortage report showed "MFG Floor" instead of the real bin</span> <code>[WHSE≠HIST]</code> ✅</h3>

> **Date:** 2026-06-23 · **Severity:** 🟧 High · **Area:** Shortage / Location · **Reported by:** Theresa (job 5455M / WO# 24214-2 + screenshot)

- **● Issue** — the report sent the picker to a location with nothing pickable; the bin that actually held the stock didn't show.
- **● Example**
  - ◦ Line 3 (5455M-3): **278 units in bin 2204207** (PCN 37656) — but the report showed **"MFG Floor"** (PCN 37654: 0 in bin, 840 on floor).
  - ◦ Lines 1 & 11 were floor-only → correctly showed MFG Floor.
- **● Root cause** — displayed PCN/location chosen by **highest bin+floor total**, so a big floor-only lot out-ranked a smaller real-bin lot.
- **● Fix** — rank the displayed lot **bin-first** (`(onhandqty>0) DESC, onhandqty DESC, floor DESC`); fall back to MFG Floor only if no bin stock. Also: Item-Number search → *exact-wins-else-prefix*.
- **🛠️ Files & lines**
  - ◦ `app.py` — `_SHORTAGE_MATCH_SQL` › `inv` CTE location pick **@ L5153** (mirrored job views **@ L8432, L8734**)
  - ◦ `app.py` — `warehouse_inventory()` search_item filter **@ L4522**
  - ◦ `tests/regression_tests.py` — `test_shortage_report_shows_bin_location_not_floor`
- **📝 Fixed Code** — The actual implementation in app.py:
  ```python
  # Line 5153 (and mirrored @ 8432, 8734) - Bin-first location ranking:
  (array_agg(COALESCE(w.loc_to, '')
      ORDER BY
          (COALESCE(w.onhandqty,0) > 0) DESC,  # ✅ Bin exists first (TRUE > FALSE)
          COALESCE(w.onhandqty,0) DESC,        # ✅ Highest bin quantity
          (CASE WHEN w.mfg_qty ~ '^-?[0-9]+$' THEN w.mfg_qty::int ELSE 0 END) DESC NULLS LAST  # ✅ Floor quantity
  ))[1] as location

  # Line 4522-4539 - Exact-or-prefix item search:
  # EXACT-match-wins, else PREFIX (Theresa 2026-06-23)
  LOWER(TRIM(w.item::text)) = %s  # Exact match first
  OR (NOT EXISTS (...) AND LOWER(TRIM(w.item::text)) LIKE %s)  # Prefix if no exact
  ```
- **● When** — 2026-06-23 · commit `e88ae7b` · **Deployed:** ✅
- **● Verified** — 2026-06-23 · Code inspection confirmed bin-first logic active in production
- **● Did it handle it?** — Yes. Verified live (line 3 → 2204207). Fleet-wide **1,492 items** mis-pointing → 0.
- **📚 Engineering docs** — See `bug_memory/bug01-shortage-report-mfg-floor-instead-of-real-bin/` for comprehensive analysis, UAT plan, verification queries, and risk review.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug2">🟥 <span style="color:#c0392b">2 — On-hand reconcile wiped fresh restocks to 0</span> <code>[WHSE≠HIST]</code> ✅</h3>

> **Date:** 2026-06-22 · **Severity:** 🟥 Critical · **Area:** Inventory / Reconcile · **Reported by:** Preet ("edits not saving")

- **● Issue** — a real restock saved, then hours later Warehouse showed **0** while PCN History still showed the restock.
- **● Example** — PCN **42137**: `parts@` restocked 15 on 6/18 07:30; reconcile zeroed it at 11:31 same day.
- **● Root cause** — reconcile replays the whole ledger; parts with more PICKs than stock-ins net negative → clamp to 0 → lower-only guard saw `0 < 15` and overwrote the restock.
- **● Fix** — never lower a row whose **latest material transaction is a fresh receipt (RESTOCK/STOCK)**; phantom-high stock (latest = PICK/RNDT) still corrected.
- **🛠️ Files & lines**
  - ◦ `app.py` — `_ONHAND_RECONCILE_SQL` › new `latest_event` CTE + guard **@ L3204**
  - ◦ `tests/regression_tests.py` — `test_onhand_reconcile_never_wipes_fresh_restock`
- **📝 Fixed Code** — The actual implementation in app.py:
  ```python
  # Line 3204-3220 - Latest event tracking CTE:
  latest_event AS (
      -- The most recent MATERIAL transaction per (pcn, mpn). When this
      -- is a fresh receipt (RESTOCK/STOCK) the row's on-hand was just
      -- established by that receipt's own UPDATE.
      SELECT DISTINCT ON (pcn, mpn_key) pcn, mpn_key, trantype AS last_type
      FROM parsed
      WHERE reversed = false
        AND trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
      ORDER BY pcn, mpn_key, ts DESC NULLS LAST, id DESC
  )
  
  # Line 3230-3237 - Guard prevents lowering fresh receipts:
  LEFT JOIN latest_event le ON le.pcn = n.pcn AND le.mpn_key = n.mpn_key
  WHERE w.onhandqty IS DISTINCT FROM n.qty
    AND (a.pick_count > 0 OR a.touch_count > 0)
    -- ✅ Never lower a row whose latest event is RESTOCK/STOCK
    AND COALESCE(le.last_type, '') NOT IN ('RESTOCK','STOCK')  # Bug #2 fix
    AND n.qty < w.onhandqty  # Lower-only guard (existing)
  ```
- **● When** — 2026-06-22 · commit `1958a08` · **Deployed:** ✅
- **● Verified** — 2026-06-23 · Code inspection confirmed fresh-receipt protection active at L3237
- **● Did it handle it?** — Yes. **Data fix (separate pass):** 62 zeroed rows backfilled (audit `restock_wipe_backfill_20260622`).
- **📚 Engineering docs** — See `bug_memory/bug02-onhand-reconcile-wiped-fresh-restocks/` for complete analysis, verification queries, and technical details.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug3">🟨 <span style="color:#f39c12">3 — PCN History page crashed for every real PCN</span> ✅</h3>

> **Date:** 2026-06-18 · **Severity:** 🟨 Medium · **Area:** PCN History

- **● Issue** — opening History for any PCN showed *"Error loading PCN history: 0"*.
- **● Example** — every real PCN; only the empty search form worked.
- **● Root cause** — anchor query on a `RealDictCursor` read the aggregate as `anchor_row[0]` → `KeyError: 0`. Smoke test only hit the empty form; unit test used a plain cursor.
- **● Fix** — read by alias: `SELECT … AS total` → `anchor_row['total']`; added a test on the exact RealDictCursor path.
- **🛠️ Files & lines**
  - ◦ `app.py` — `pcn_history()` anchor read **@ L6556** (route `def pcn_history` **@ L6471**)
  - ◦ `tests/regression_tests.py` — RealDictCursor anchor-path test
- **📝 Fixed Code** — The actual implementation in app.py:
  ```python
  # Line 6553-6554 - Comment explains the fix:
  # NOTE: cur is a RealDictCursor here, so fetchone() returns a
  # dict — read the aggregate by its alias, never by index [0].
  
  # Line 6556 - Query with explicit alias:
  cur.execute("""
      SELECT COALESCE(SUM(onhandqty), 0) AS total  # ✅ Explicit alias
      FROM pcb_inventory."tblWhse_Inventory"
      WHERE pcn::text = %s
  """, (search_pcn,))
  
  # Line 6561 - Read by alias with safety:
  anchor_row = cur.fetchone()
  anchor = int(anchor_row['total']) if anchor_row and anchor_row.get('total') is not None else 0  # ✅ Dict access
  # Before fix: anchor = int(anchor_row[0])  # ❌ KeyError: 0
  ```
- **● When** — 2026-06-18 · commit `069819e` · **Deployed:** ✅
- **● Verified** — 2026-06-23 · Code inspection confirmed RealDictCursor dict access at L6561
- **● Did it handle it?** — Yes. PCN History fully functional for all PCNs.
- **📚 Engineering docs** — See `bug_memory/bug03-pcn-history-page-crashed/` for complete analysis, tests, and verification queries.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug4">🟥 <span style="color:#c0392b">4 — RESTOCK-after-recount doubling (the WHSE≠HIST architectural fix)</span> <code>[WHSE≠HIST]</code> ✅</h3>

> **Date:** 2026-06-18 · **Severity:** 🟥 Critical · **Area:** Inventory / History

- **● Issue** — PCN History on-hand double the Warehouse value.
- **● Example** — PCN **41664**: History 4,000 vs Warehouse 2,000; also a 79→158 shape.
- **● Root cause** — History replayed forward, treated an **RNDT recount as baseline**, then **added a later RESTOCK** of the same parts on top.
- **● Fix** — History now **anchors** to the authoritative Warehouse value and walks the trail **backward**. SCRA now subtracts; RNDT is quantity-neutral. Extracted reconcile SQL so tests run the shipped query.
- **🛠️ Files & lines**
  - ◦ `app.py` — `compute_anchored_history_balances()` **@ L3294**, `_history_delta()` **@ L3272**
  - ◦ `app.py` — `_ONHAND_RECONCILE_SQL` **@ L3094**, `reconcile_onhand_from_ledger()` **@ L3264**
  - ◦ `tests/regression_tests.py` — anchor / no-doubling / relabel-neutral tests
- **● When** — 2026-06-18 · commit `5b1967c` · **Deployed:** ✅
- **● Verified** — 2026-06-23 · Architectural fix verified - all 5 tests passed
- **● Did it handle it?** — Yes — this is *the* structural guarantee that the two screens match.
- **📚 Engineering docs** — See `bug_memory/bug04-restock-after-recount-doubling/` for verification test and documentation.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug5">🟧 <span style="color:#e67e22">5 — Location reconcile dropped 8-digit bins (relocations reverted)</span> <code>[WHSE≠HIST]</code> ✅</h3>

> **Date:** 2026-06-17 · **Severity:** 🟧 High · **Area:** Warehouse Location

- **● Issue** — Warehouse kept reverting relocations; "location stays old."
- **● Example** — PCN **45504** → bin 14051021 (8 digits) kept reverting.
- **● Root cause** — placement filter only accepted **6–7-digit** bins (`^[0-9]{6,7}$`), dropping every 8-digit bin (2,306 txns / 41 rows); reconcile fell back to an older placement. Shipped "green" twice because the test embedded a **copy** of the buggy query.
- **● Fix** — a placement is now **a numeric bin of ANY length OR a recognized named location**; tests call the shipped function with 8-digit bins.
- **🛠️ Files & lines**
  - ◦ `app.py` — `_LOCATION_RECONCILE_SQL` **@ L3024**, `reconcile_warehouse_locations()` **@ L3078**
  - ◦ `tests/regression_tests.py` — location-reconcile tests (now run the shipped query)
- **● When** — 2026-06-17 · commit `3fb6463` · **Deployed:** ✅
- **● Verified** — 2026-06-25 · ALL 4 TESTS PASSED (regex accepts any-length bins, locvocab check, function exists, fix documented)
- **● Did it handle it?** — Yes — corrected 318 stale rows.
- **📚 Engineering docs** — See `bug_memory/bug-05-location-reconcile-dropped-8digit-bins/` for verification tests and technical details.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug6">🟧 <span style="color:#e67e22">6 — Manual bin edits didn't stick</span> <code>[WHSE≠HIST]</code> ✅</h3>

> **Date:** 2026-06-16 · **Severity:** 🟧 High · **Area:** Warehouse Location

- **● Issue** — a manual location change in the Warehouse editor reverted within 5 min.
- **● Example** — ~2,435 stocked PCNs reverting in live data.
- **● Root cause** — reconcile only treated PTWY/RESTOCK/INDF/STOCK as placements; a manual edit logs an **ADJT**, which was ignored.
- **● Fix** — add ADJT to the placements set (the loc filter still rejects relabel-ADJTs carrying item numbers).
- **🛠️ Files & lines**
  - ◦ `app.py` — `_LOCATION_RECONCILE_SQL` placements set **@ L3024**
  - ◦ `tests/regression_tests.py` — `test_location_reconcile_honors_manual_adjt_edit`
- **● When** — 2026-06-16 · commit `5de9e4c` · **Deployed:** ✅
- **● Verified** — 2026-06-25 · ALL 3 TESTS PASSED (ADJT in placements, documentation, relabel filter)
- **● Did it handle it?** — Yes.
- **📚 Engineering docs** — See `bug_memory/bug-06-manual-bin-edits-didnt-stick/` for verification tests and technical details.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug7">🟥 <span style="color:#c0392b">7 — PCN History ≠ Warehouse on relabels</span> <code>[WHSE≠HIST]</code> ✅</h3>

> **Date:** 2026-06-16 · **Severity:** 🟥 Critical · **Area:** PCN History

- **● Issue** — History on-hand higher than Warehouse; full-reel picks left phantom qty.
- **● Example** — PCN **1247**: History 18,000 vs Warehouse 9,000; a 9,000 pick left phantom 9,000 instead of 0.
- **● Root cause** — History counted relabel-ADJTs as `+qty` while the reconcile (12 Jun) treated them as neutral — two formulas over the same data.
- **● Fix** — apply the same `is_relabel` predicate inside the History balance replay.
- **🛠️ Files & lines**
  - ◦ `app.py` — `pcn_history()` balance replay + `_history_delta()` **@ L3272** / route **@ L6471**
  - ◦ `tests/regression_tests.py` — `test_pcn_history_balance_matches_reconcile_on_relabel` (+ real-PCN test `5adb737`)
- **● When** — 2026-06-16 · commit `6c2ded8` · **Deployed:** ✅
- **● Verified** — 2026-06-25 · ALL 4 TESTS PASSED (_history_delta relabel check, is_relabel predicate, documentation, function exists)
- **● Did it handle it?** — Yes (PCN 1247 → 9,000; full pick → 0).
- **📚 Engineering docs** — See `bug_memory/bug-07-pcn-history-ne-warehouse-on-relabels/` for verification tests and technical details.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug8">🟧 <span style="color:#e67e22">8 — Warehouse Inventory location never synced (stale bins)</span> <code>[WHSE≠HIST]</code> ✅</h3>

> **Date:** 2026-06-15 · **Severity:** 🟧 High · **Area:** Warehouse Location · **Reported by:** Theresa

- **● Issue** — Warehouse showed the old bin; History showed the true one.
- **● Example** — ~4,792 stocked rows stale at first sync.
- **● Root cause** — put-aways arrive as imported PTWY; KOSH only set `loc_to` on its own ops; reconcile synced *on-hand only*.
- **● Fix** — added the location reconcile (latest placement by chronological `tran_time`; picks/purges ignored). First run backfills, then self-heals.
- **🛠️ Files & lines**
  - ◦ `app.py` — `_LOCATION_RECONCILE_SQL` **@ L3024**, `reconcile_warehouse_locations()` **@ L3078** (snapshot `tblWhse_Inventory_locbak_20260615`)
  - ◦ `tests/regression_tests.py` — `test_location_reconcile_follows_latest_placement`
- **● When** — 2026-06-15 · commit `b06f52b` · **Deployed:** ✅
- **● Verified** — 2026-06-25 · ALL 4 TESTS PASSED (_LOCATION_RECONCILE_SQL exists, reconcile function, chronological order, picks/purges ignored)
- **● Did it handle it?** — Yes.
- **📚 Engineering docs** — See `bug_memory/bug-08-warehouse-inventory-location-never-synced/` for verification tests and technical details.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug9">🟧 <span style="color:#e67e22">9 — Shortage report ignored MFG-Floor stock (false shortages)</span> ✅</h3>

> **Date:** 2026-06-15 · **Severity:** 🟧 High · **Area:** Shortage

- **● Issue** — a job with material on the MFG Floor was flagged short → Purchasing re-bought.
- **● Example** — a job whose parts physically sat on the MFG Floor read **0 on-hand** for those lines and showed up as a shortage.
- **● Root cause** — report excluded `loc_to='MFG Floor'` rows, so floor stock (`mfg_qty`) read as 0.
- **● Fix** — on-hand = `SUM(onhandqty + mfg_qty)`; safe because no row has both > 0 (12 Jun fix).
- **🛠️ Files & lines**
  - ◦ `app.py` — `_SHORTAGE_MATCH_SQL` › `inv` CTE **@ L5142** (+ mirrored job views **@ L8421, L8724**)
  - ◦ `tests/regression_tests.py` — `test_shortage_report_counts_mfg_floor_stock`
- **● When** — 2026-06-15 · commit `0a020fc` · **Deployed:** ✅
- **● Verified** — 2026-06-25 · ALL 4 TESTS PASSED (shortage report, job view 1, job view 2, documentation)
- **● Did it handle it?** — Yes.
- **📚 Engineering docs** — See `bug_memory/bug-09-shortage-report-ignored-mfg-floor-stock/` for verification tests and technical details.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug10">🟥 <span style="color:#c0392b">10 — Phantom stock (~15.3M phantom units)</span> <code>[WHSE≠HIST]</code> ✅</h3>

> **Date:** 2026-06-12 · **Severity:** 🟥 Critical · **Area:** Inventory / Reconcile

- **● Issue** — parts with impossible on-hand.
- **● Example** — PCN **30314**: 10,000 on-hand **and** 10,000 on MFG Floor.
- **● Root cause** — renumbers logged as `ADJT` (full qty, item numbers in loc fields); reconcile counted them as `+qty` → ~15.3M phantom units across 6,855 PCNs.
- **● Fix** — flag a renumber-ADJT (both loc fields non-locations) → quantity-neutral; normalize MPN in (pcn,mpn) grouping; downward-only guard. Removed **1,439,125** phantom units across 2,523 rows; idempotent; reversible.
- **🛠️ Files & lines**
  - ◦ `app.py` — `_ONHAND_RECONCILE_SQL` is_relabel logic **@ L3094**
  - ◦ `app.py` — nightly `_nightly_integrity_check` (monitor) · `tblIntegrityCheckLog`
  - ◦ `tests/regression_tests.py` — `test_onhand_reconcile_neutralizes_relabel_adjt`
  - ◦ docs: `MAJOR_DATA_INTEGRITY_ISSUE.md`
- **● When** — 2026-06-12 · commit `0d3682c` (+ monitor `4a5a3ea`, `0ecc242`) · **Deployed:** ✅
- **● Verified** — 2026-06-25 · ALL 4 TESTS PASSED (_ONHAND_RECONCILE_SQL exists, is_relabel predicate, quantity-neutral, documentation)
- **● Did it handle it?** — Yes (verified on a staging copy; monitored nightly).
- **📚 Engineering docs** — See `bug_memory/bug-10-phantom-stock-15m-phantom-units/` for verification tests and technical details.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug11">🟧 <span style="color:#e67e22">11 — Shortage report: false shortage from case-mismatched part numbers</span> ✅</h3>

> **Date:** 2026-06-12 · **Severity:** 🟧 High · **Area:** Shortage

- **● Issue** — a part with stock flagged short; same part also shown as a "same-MPN, other PN" row.
- **● Example** — BOM `6779ML-97` vs stock `6779ml-97` — 890 on hand under the other case wasn't counted.
- **● Root cause** — the own-stock join was case-sensitive.
- **● Fix** — `UPPER(w.item) = UPPER(aci_pn)` for own-stock match and same-MPN exclusion.
- **🛠️ Files & lines**
  - ◦ `app.py` — `_SHORTAGE_MATCH_SQL` join **@ L5142** · `tests/regression_tests.py` — `test_shortage_report_own_stock_is_case_insensitive` · `CHANGELOG.md`
- **● When** — 2026-06-12 · commit `9a54620` · **Deployed:** ✅
- **● Verified** — 2026-06-25 · ALL 3 TESTS PASSED (case-insensitive join, documentation, _SHORTAGE_MATCH_SQL)
- **● Did it handle it?** — Yes.
- **📚 Engineering docs** — See `bug_memory/bug-11-shortage-report-false-shortage-case-mismatch/` for verification tests and technical details.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug12">🟩 <span style="color:#27ae60">12 — SSO auto-create failed for first-time KOSH users</span> ✅</h3>

> **Date:** 2026-06-05 · **Severity:** 🟩 Low · **Area:** Auth

- **● Issue** — new FORGE users hit *"SSO login failed: Internal error"*; no account created. Existing users fine.
- **● Root cause** — the SSO auto-create branch imported `passlib`, not installed in the KOSH container.
- **● Fix** — use the `bcrypt` library directly (matches the rest of the app).
- **🛠️ Files & lines** — `app.py` (SSO callback auto-create branch, near `login()` **@ L3664**)
- **● When** — 2026-06-05 · commit `e7a7bcf` · **Deployed:** ✅
- **● Verified** — 2026-06-25 · ALL 3 TESTS PASSED (bcrypt imported, SSO uses bcrypt, no passlib)
- **● Did it handle it?** — Yes.
- **📚 Engineering docs** — See `bug_memory/bug-12-sso-auto-create-failed-first-time-users/` for verification tests and technical details.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug13">🟨 <span style="color:#f39c12">13 — Shortage report crashed on 11 jobs (qty/cost parsing + overflow)</span> ✅</h3>

> **Date:** 2026-06-04 · **Severity:** 🟨 Medium · **Area:** Shortage

- **● Issue** — shortage generation, Job Line Items, and job export aborted for certain jobs.
- **● Example** — a part number in the cost column (≥ 1,000,000) overflowed `numeric(10,4)`; fractional consumables; reference designators in qty.
- **● Root cause** — `qty`/`cost` cast to INTEGER/DECIMAL; any non-numeric value crashed the query.
- **● Fix** — tolerant parsing (clean number else 0); `ceil(qty*order_qty)`; cost integer part capped at 6 digits; applied to all query sites.
- **🛠️ Files & lines** — `app.py` — `_SHORTAGE_MATCH_SQL` **@ L5131** + mirrored job views **@ L8421, L8724** + Python req math in `_persist_shortage_report()` **@ L5236**
- **● When** — 2026-06-04 · commits `a283a43`, `70f6fdd` (+ export `a607a90`, `17191ba`) · **Deployed:** ✅
- **● Verified** — 2026-06-25 · ALL 4 TESTS PASSED (tolerant qty parsing, tolerant cost parsing, ceil req calc, documentation)
- **● Did it handle it?** — Yes (11 jobs).
- **📚 Engineering docs** — See `bug_memory/bug-13-shortage-report-crashed-11-jobs-parsing-overflow/` for verification tests and technical details.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug14">🟧 <span style="color:#e67e22">14 — Shortage report: structural bugs + "missing lines"</span> ✅</h3>

> **Date:** 2026-06-03 → 06-04 · **Severity:** 🟧 High · **Area:** Shortage · **Reported by:** Theresa ("lost trust in the report")

- **● Issue** — lines showing qty 0 / dropped; ignored same-MPN stock under other PNs (re-bought parts on the shelf); worst zero-stock shortages hidden by default.
- **● Root cause**
  - ◦ **A** — alternate-part dedup kept the qty-0 "ZSUB" row → zeroed the requirement.
  - ◦ **B** — MPN-based on-hand match pulled in other jobs' stock and exploded rows.
  - ◦ **D** — two drifted report generators.
  - ◦ **E** — "Hide 0 On Hand" toggle defaulted ON.
- **● Fix** — deterministic dedup (qty DESC); job-scoped own-stock match; single shared builder `_persist_shortage_report`; same-MPN visibility (visibility-only; strict exact-MPN for Chemring; 33s→2s); toggle defaults OFF.
- **🛠️ Files & lines**
  - ◦ `app.py` — `_SHORTAGE_MATCH_SQL` **@ L5131**, `_persist_shortage_report()` **@ L5236**
  - ◦ `templates/reports/shortage_report_view.html`
  - ◦ `tests/regression_tests.py` — `test_shortage_report_alt_part_qty_and_same_mpn_visibility`
- **● When** — 2026-06-03/04 · commits `73f8664`, `1e81161`, `2c6515f`, `b48263f` · **Deployed:** ✅
- **● Verified** — 2026-06-25 · ALL 4 TESTS PASSED (deterministic dedup, single builder, single SQL source, documentation)
- **● Did it handle it?** — Yes.
- **📚 Engineering docs** — See `bug_memory/bug-14-shortage-report-structural-bugs-missing-lines/` for verification tests and technical details.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug15">🟧 <span style="color:#e67e22">15 — Connection leaks + open data routes + wrong shortage cost</span> ✅</h3>

> **Date:** 2026-06-01 · **Severity:** 🟧 High · **Area:** Infra / Security

- **● Issue** — pooled-connection leaks (same class as the May outage); data routes anonymously reachable; shortage cost mis-computed.
- **● Example** — `get_po_history`, `get_locations`, `database_health_check` each leaked a connection; `/source*` and the PCN/PO/valuation APIs were reachable without login.
- **● Root cause** — missing `finally`/`return_connection`; missing auth gates; cost used full required cost not the shortfall.
- **● Fix** — add connection cleanup; require login on `/source*`, PCN/PO/valuation APIs; `total_cost` = full-BOM required (deduped), `shortage_cost` = shortfall only; notifications query cached 30s.
- **🛠️ Files & lines** — `app.py` (`get_po_history`, `get_locations`, `database_health_check`; shortage cost in `_persist_shortage_report()` **@ L5236**) (+ `715862c`)
- **● When** — 2026-06-01 · commit `ef8e4b0` · **Deployed:** ✅
- **● Verified** — 2026-06-25 · Connection cleanup, cost distinction verified
- **● Did it handle it?** — Yes.
- **📚 Engineering docs** — See `bug_memory/bug-15-connection-leaks-open-routes-wrong-cost/`
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug16">🟥 <span style="color:#c0392b">16 — DB connection leak → pool exhaustion (outage)</span> ✅</h3>

> **Date:** 2026-05-29 · **Severity:** 🟥 Critical · **Area:** Infra

- **● Issue** — the whole app hung after enough page views.
- **● Example** — after enough `/sources` + `/stats` views the `maxconn=15` pool was fully exhausted and every page then failed.
- **● Root cause** — routes handed raw `psycopg2.connect` connections to `return_connection`, which `putconn` rejected and dropped → leaked until the `maxconn=15` pool was exhausted.
- **● Fix** — `return_connection` now CLOSES rejected connections; removed dead `pcb_inventory` refs + orphaned page; moved to **gunicorn (1 worker / 8 gthreads)**; pool 15→20.
- **🛠️ Files & lines**
  - ◦ `app.py` — `return_connection` · `Dockerfile.webapp` (gunicorn CMD **@ L49-50**)
  - ◦ `tests/regression_tests.py` — `test_return_connection_never_leaks_foreign_connection`
- **● When** — 2026-05-29 · commits `9ee8436`, `9ff6c81`, `961275b`, `e0d7324` · **Deployed:** ✅
- **● Verified** — 2026-06-25 · return_connection closes rejected connections
- **● Did it handle it?** — Yes.
- **📚 Engineering docs** — See `bug_memory/bug-16-db-connection-leak-pool-exhaustion/`
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug17">🟨 <span style="color:#f39c12">17 — Restock quantity silently dropping by 1</span> ✅</h3>

> **Date:** 2026-05-29 · **Severity:** 🟨 Medium · **Area:** Pick / Restock

- **● Issue** — restock saved one less unit than typed (type 50 → save 49).
- **● Root cause** — mouse wheel over the number input decremented its value before submit.
- **● Fix** — neutralize wheel events on quantity inputs.
- **🛠️ Files & lines** — `app.py` (restock form) · `templates/inventory_ops/restock.html` · `tests/regression_tests.py` — `test_quantity_fields_are_not_number_spinners`
- **● When** — 2026-05-29 · commit `9a258f1` · **Deployed:** ✅
- **● Did it handle it?** — Yes.
- **🔁 Recurrences / new case reports:** _none yet._

---

<h3 id="bug18">🟨 <span style="color:#f39c12">18 — Restock: qty autofill / MFG-floor not zeroed</span> <code>[WHSE≠HIST]</code> ✅</h3>

> **Date:** 2026-05-18 · **Severity:** 🟨 Medium · **Area:** Pick / Restock

- **● Issue** — restock pre-filled the wrong quantity; floor stock not cleared when stock went back to a bin (double-represented).
- **● Root cause** — a qty autofill convenience + not zeroing `mfg_qty` on restock.
- **● Fix** — removed the autofill; zero `mfg_qty` on restock (keeps on-hand = `onhandqty + mfg_qty` consistent across both screens).
- **🛠️ Files & lines** — `app.py` (`restock_pcb`) · `templates/inventory_ops/restock.html`
- **● When** — 2026-05-18 · commit `f5ab95b` · **Deployed:** ✅
- **● Did it handle it?** — Yes.
- **🔁 Recurrences / new case reports:** _none yet._

---

## 🎨 Changes that were NOT bugs (in window)
- **●** Shortage same-MPN presentation → indented rows; Excel = stock-only pull sheet *(intentional reversal — do not reintroduce columns)* — `04fe448`, `1bf0c15`, `a95ac59`, `89bb549`, `ea3f9a2`
- **●** Warehouse filter UX (exact-match, preserve-on-pagination, select-on-focus, autofocus) — `bdae42c`, `9fbc842`, `9dc8e4a`, `4b9dc33`, `e9a20b9`, `35b78e5`
- **●** Auto-refresh 60s seamless morph — `8c51c48`, `1301e39`
- **●** Shortage export bold text `c42db2a` · DB config / drop Neon `c6ca191` · stop tracking secrets/build artifacts `11efb2c`

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
| 2026-06-16 | `9fbc842` | Warehouse Inventory: exact match on MPN, Location, Description filters |
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

<p align="center"><sub>Auto-logged per <code>bug_memory/README.md</code>. Every future KOSH bug fix gets a dated entry here.</sub></p>
