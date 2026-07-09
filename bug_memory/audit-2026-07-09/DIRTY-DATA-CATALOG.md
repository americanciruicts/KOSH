# KOSH — DIRTY DATA PATTERN CATALOG (feeds the Phase 3 migration)

Every distinct dirty-data pattern found in the live `kosh` DB on 2026-07-09, with detection predicate,
observed count, current handling, and the translation rule the migration must apply. READ-ONLY findings.

Casting notes that bite: `mfg_qty` and `tranqty` are **text**; use
`col ~ '^-?[0-9]+$'` before `::int`. `tran_time` is **text** and out of chronological order — never sort
the ledger by `id` for business meaning; parse to timestamp (`tranqty_int` is a pre-cleaned int mirror).

---

## P1 — Relabel/renumber logged as `ADJT` carrying full qty, with ITEM NUMBERS in the location fields
- **Detect:** `trantype='ADJT'` AND `loc_from`/`loc_to` are neither a known location, a 6+ digit bin, nor
  blank, AND they differ. (Location vocabulary is learned from all non-ADJT `loc_to`/`loc_from`.)
- **Count:** **11,611** of 18,679 ADJT rows.
- **Current handling:** shipped ledger flags `is_relabel` → quantity-neutral (bug 10). Correct but
  re-detected on every read via a heuristic + a learned-vocabulary subquery.
- **Migration rule:** emit an explicit **`RELABEL` event with signed qty 0** (old_part → new_part carried
  in typed part fields, not the location columns). Never contributes to on-hand.

## P2 — MFG-Floor stock has no ledger representation (floor qty lives only as a warehouse column)
- **Detect:** `tblWhse_Inventory.mfg_qty ~ '^[1-9][0-9]*$'` (floor qty > 0).
- **Count:** **12,700** rows, **12,687** floor-only, **4,744,889** units.
- **Current handling:** History anchors to `onhandqty + mfg_qty`; ledger forward-replay yields 0 for these.
- **Migration rule:** MFG Floor becomes a **first-class typed location**. Seed each floor lot as an opening
  balance at that location (anchored to today's `mfg_qty`). Bin↔floor moves become signed transfer events
  (from_location/to_location) so on-hand at every location is a pure projection of the ledger.

## P3 — Bin/floor double-count (same lot row has bin qty AND floor qty)
- **Detect:** `onhandqty>0 AND mfg_qty ~ '^[1-9][0-9]*$'`.
- **Count:** **13** rows (all bin-located; floor-located class already deduped by bug 20 guard). ~2,985 overlap units.
- **Rows (id · pcn · item · bin · floor · loc):**
  - 51650 · 34300 · 6163L-9 · 1120 · 1110 · 1402510
  - 46960 · 26133 · 6163L-8 · 970 · 980 · 1406206
  - 65010 · 44500 · 8098-1-135 · 290 · 340 · 1603002
  - 42408 · 14196 · 6163L-7 · 210 · 220 · 1603002
  - 46779 · 25972 · ACI-8182 · 190 · 3000 · 3102004
  - 37671 · 8229 · 6163L-11 · 140 · 60 · 1603002
  - 63162 · 43341 · 7620-75 · 95 · 100 · Rec Area
  - 65570 · 45299 · 7593-16 · 90 · 10 · 1504004
  - 53118 · 36361 · 8620ML-265 · 30 · 1 · 1603002
  - 64381 · 44623 · 7620-20 · 20 · 50 · Rec Area
  - 57858 · 37846 · 7620-15 · 20 · 48 · 2205204
  - 63165 · 43344 · 6163L-3 · 8 · 9 · 2103504
  - 67382 · 46152 · 8567ML-20 · 1 · 1 · 2203403
- **Current handling:** NOT auto-fixed (bug 20 warns a legit partial-pick split looks identical). Surfaced only.
- **Migration rule:** **per-row human trace** each of the 13 before seeding (is it a partial split → two lots
  at two locations, or a stale duplicate → one). Then enforce **one location + one qty per lot row** with a
  DB CHECK so the state is unrepresentable afterward.

## P4 — Ledger forward-replay overcounts vs Warehouse (RESTOCK-after-recount / phantom doubling)
- **Detect:** per-PCN forward-replayed ledger `net` > warehouse `onhandqty` by >5.
- **Count:** **515** PCNs (bin-level). Many are exact 2× (e.g. whole `6590L-A-*` family).
- **Current handling:** lower-only reconcile refuses to raise warehouse (bugs 2/4/19). Warehouse trusted.
- **Migration rule:** do **NOT** re-replay history to seed balances. Anchor opening balances to today's
  Warehouse on-hand; translate only forward-going events into the new ledger.

## P5 — Over-pick / negative-replay (more picked than ever existed)
- **Detect:** naive `GREATEST(0, base+Σdelta)=0` but running-floor reflection `>0`.
- **Count:** **31** (pcn,mpn) groups; 6,738 units rescued.
- **Current handling:** running-floor reflection (bug 19) already correct.
- **Migration rule:** with balances anchored to Warehouse (not replayed), this class cannot recur. Keep the
  `qty >= 0` CHECK so an over-pick is rejected at write time rather than absorbed later.

## P6 — Malformed `trantype` (date-codes / blanks parsed into the type column)
- **Detect:** `trantype` blank (197), numeric like `1720`/`2422` (67), or `na`/`NA` (12).
- **Count:** **~276** rows.
- **Current handling:** ledger delta `ELSE 0` — they don't move qty, but they pollute the type space.
- **Migration rule:** quarantine to a `legacy_unmapped` event type (qty 0) with the raw row preserved for
  audit; never map them to a real movement.

## P7 — Unparseable `tran_time` (can't order chronologically)
- **Detect:** `tran_time` matches neither `YYYY-MM-DD…` nor `MM/DD/YY HH:MI…`.
- **Count:** **50** rows.
- **Current handling:** ledger sorts `ts DESC NULLS LAST, id`.
- **Migration rule:** new ledger carries a **monotonic seq** assigned at insert (not `tran_time`); legacy
  rows with unparseable time are ordered by a stable fallback and stamped with a synthetic occurred_at.

## P8 — Zero-qty PICK rows (cosmetic "phantom → MFG Floor" history, bug 24)
- **Detect:** `trantype='PICK' AND (tranqty='0' OR tranqty_int=0)`.
- **Count:** **2,968** (all legacy imports; the live pick path rejects 0-qty).
- **Current handling:** fixed per-PCN as reported (bug 24 reversed one row). Not mass-touched.
- **Migration rule:** exclude zero-qty movements from the new ledger (or carry as qty 0 non-events); they
  must never render as a location move.

## P9 — Orphan PCNs (referential gaps)
- **Detect:** Warehouse PCN with no ledger rows (10); ledger PCN with no Warehouse row (267).
- **Migration rule:** the new part/lot model keys on canonical part; warehouse-only PCNs seed as opening
  balances, ledger-only PCNs seed no balance (they resolved to 0) — flag both lists for review before cutover.

## P10 — Reversed rows already present (266)
- **Detect:** `reversed = true`.
- **Migration rule:** never migrate reversed rows as active events; preserve them as tombstones for audit.

## P11 — Duplicate/mirror clutter tables (schema hygiene, not qty)
- **Observed:** lowercase mirrors (`tbltransaction`, `tblwhse_inventory`, `tblbom`, …) alongside the real
  `tblTransaction`/`tblWhse_Inventory`/`tblBOM`, plus several `*_bak_*` snapshots.
- **Migration rule:** confirm which are live vs legacy before cutover; the new model reads only the
  canonical tables. (Do not drop anything — additive/reversible only.)

---

### Canonicalization status (good news)
- **0** MPN case-variant collisions on the same PCN — the `LOWER(TRANSLATE(mpn,'-# ./',''))` normalization
  used across the app is consistent, so a canonical `part` table can fold case/separators safely without
  merging distinct parts. (Still verify against `tblBOM.aci_pn` in Phase 2.)
- **0** stale locations — location reconcile is fully caught up.
