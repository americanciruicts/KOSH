# KOSH — Production Fix Orders

**Purpose:** hand this to the AI working on the live KOSH (`app.py` + the `kosh`
Postgres database) as a work order. It explains the ONE root cause behind almost
every bug in `bug_memory/BUG HISTORY.md`, the target design that makes those bugs
*impossible*, and a per-bug checklist to verify against.

Read this whole file before changing code. Do not ship patches one bug at a time —
that is exactly the "same bug again and again" pendulum. Fix the model.

---

## 0. The one root cause

KOSH computes "how much do we have" **two different ways**:

1. **Warehouse Inventory** = the stored snapshot `tblWhse_Inventory.onhandqty` (bin)
   + `mfg_qty` (floor).
2. **PCN History** = a balance **replayed from the `tblTransaction` ledger**.

Two computations over the same dirty Access-imported ledger **drift apart**. Every
`[WHSE≠HIST]` complaint, the phantom stock, the double-counts, the over-pick
zeroing, the restock-that-stacks — all of it is that drift, plus a dirty ledger
(relabels logged as `ADJT` carrying full qty with item numbers in the location
fields; out-of-order `tran_time`; more PICKs than stock-ins).

**Do not add another reconciler. Remove the second computation.**

---

## 1. Target design (the durable fix — this is the main order)

Adopt a **single source of truth**: an append-only ledger. Everything else is
*derived* from it.

| Concept | Rule |
|---|---|
| **One ledger** | `inventory_txn` (append-only). Every stock movement is one row. |
| **On-hand is derived** | never stored as an independent number. |
| **"MFG Floor" is just a location** | there is NO `onhandqty`+`mfg_qty` pair. A part's on-hand is `SUM(qty)` across its locations — one number. |
| **A PICK is a transfer** | bin → floor, in ONE transaction: bin `-= qty`, floor `+= qty`. Total conserved. |
| **Balance cache** | a `(pcn, location) → qty` table written **inside the same DB transaction** as every ledger row. It is a cache, never independent, so it cannot drift. |
| **No reconcilers** | delete the 5-minute `_sync_onhand_from_transactions` / location reconcile / floor dedupe threads. There is nothing to reconcile. |

Reference implementation (already built and tested against your real data):
`backend/app/migrations/0001_init.sql`, `backend/app/models.py`,
`backend/app/services/ledger.py`, and `docs/DATA_MODEL.md`. Mirror that model.

---

## 2. The 8 invariants — enforce every one

| # | Invariant | HOW to enforce (the order) |
|---|---|---|
| **I1** | On-hand at any `(pcn, location)` is **never negative** | `CHECK (qty >= 0)` on the balance table **AND** lock the source row + verify `qty >= amount` before every write. |
| **I2** | A unit is in **exactly one** location; bin & floor disjoint; transfers conserve total | Model floor as a location; make PICK/RESTOCK transfers. Remove the `onhandqty`+`mfg_qty` pair entirely. |
| **I3** | Warehouse Inventory == PCN History, always | Both read the SAME ledger; write the balance cache in the same txn as the ledger row. |
| **I4** | Part / MPN matching is **case-insensitive** everywhere | Make `part.aci_pn`, `part.mpn`, `pcn.mpn`, `user.username` type `CITEXT` (or compare with `UPPER()` in EVERY lookup — no exceptions). |
| **I5** | Corrections **never delete** history | Reversals write an inverse row + set `reversed = true`; queries filter `reversed = false`. |
| **I6** | Quantities are typed integers `> 0` | `INTEGER CHECK (qty > 0)` + validate in the API. No string parsing of qty/cost on the write path. |
| **I7** | A manual warehouse edit can't fill "both places" | An edit is an `ADJUST` scoped to ONE location. There is no two-number row to desync. |
| **I8** | Relabels/renumbers are **quantity-neutral** | A relabel changes part/pcn metadata; it is NOT a `+qty` ledger row. Never let item numbers land in location fields as stock. |

---

## 3. Per-bug checklist (verify each against the model above)

Most of these were already patched once in production; the order is to confirm the
STRUCTURAL guarantee, not re-patch. ✅ = made impossible by the model; the "Order"
column is what to verify/implement.

| # | Bug | Order |
|---|---|---|
| **core** | Warehouse ≠ PCN History | ✅ I3. Verify with the query in §5 — must return 0 mismatches across all PCNs. |
| 2 | Reconcile wiped fresh restocks | ✅ Delete the reconcile entirely (I3). No job may lower a stored on-hand. |
| 4 | RESTOCK-after-recount doubling | ✅ I2/I3. Recount = ADJUST; restock = transfer. No forward-replay-plus-restock. |
| 7 | History ≠ Warehouse on relabels | ✅ I8. Relabel is qty-neutral. |
| 10 | Phantom 15.3M units (relabel ADJT) | ✅ I8. A relabel never writes qty; locations are FK rows, not free-text item numbers. |
| 20 | On-hand double-counted bin+floor | ✅ I2. No `onhandqty`+`mfg_qty` pair. PICK empties the bin. |
| 24 | Phantom 0-qty PICK | ✅ I6 (`qty > 0`) + no hardcoded `loc_to` on picks. |
| 5,6,8 | Location stale / didn't stick / dropped 8-digit bins | ✅ Location comes from the latest ledger movement; `location.code` is free-form (any length). No location reconcile. |
| 19 | Over-pick → ledger computed 0 | ✅ I1. You cannot pick below empty; the write is rejected, not absorbed. |
| 17 | Restock qty drops by 1 (mouse wheel) | Front-end: block wheel events on focused `<input type=number>` (see `base.html` guard). |
| 18 | Restock qty autofill / floor not zeroed | ✅ I2. Restock is floor→bin; floor decrements in the same txn. |
| 15,16 | Connection leaks → pool exhaustion | Use one pooled session per request, closed in `finally`. No manual getconn/putconn that can leak. |
| 3 | PCN History crashed (`RealDictCursor[0]`) | Read aggregates by alias/name, never by positional index. |
| 13 | Shortage crashed on qty/cost parse | ✅ I6. Typed integer columns; no `int()` on dirty strings in the hot path. |
| 11,21 | Case-mismatch (false shortage / empty MPN dropdown) | ✅ I4. Every part/MPN lookup case-insensitive. |
| 9 | Shortage ignored MFG-floor stock | ✅ On-hand = SUM across all locations (floor included). |
| 1 | Shortage showed "MFG Floor" not the real bin | Rank displayed location **bin-first**: `(bin_qty>0) DESC, bin_qty DESC, floor DESC`. |
| 23 | Same-MPN over-matched (prefix) | Match **exact MPN only** (normalized, case-folded). No `LIKE prefix%`. |
| 25 | Shortage dropped non-short lines | Store the **FULL BOM**; flag lines where `on_hand < required`; never drop a matched line. |
| 22 | BOM Loader dropped lines / froze on bloat | Parser: never drop a row that has a real part id (ACI PN or MPN) for a bad LINE cell — give it a fallback line no.; COUNT and REPORT skipped rows (never silent). Read a bounded window / tight range so a sheet that declares 6,588 rows but holds 11 costs nothing. |
| 12 | SSO auto-create failed first-time users | Create the user on first successful SSO before issuing the session. |

---

## 4. Data migration order (one-time, sanitizing)

The live data is dirty. When you cut over to the new model, run a one-time importer
that, per `(pcn, mpn)`:

1. **Drop relabel-ADJT rows** (both location fields are non-locations / carry item
   numbers) — they were never stock (I8).
2. **Rebuild on-hand with a running floor at 0** (Skorokhod reflection): an over-pick
   can't drive the balance negative — the dip is absorbed at the pick, later receipts
   rebuild from 0 (I1). Do NOT sum-then-clamp once.
3. **Collapse any `onhand>0 AND mfg>0` double** into a single per-location balance:
   if the row is floor-located, put the whole qty on the floor and zero the phantom
   bin (I2).
4. Load current balances as **opening `STOCK` ledger rows** so Warehouse and History
   agree from row one (I3).

Keep the raw legacy tables untouched as a backup. Snapshot before running.
Reference: `backend/app/import_warehouse.py` (already loads your real 30,938-PCN
export into the clean model this way).

---

## 5. Acceptance tests — the AI must prove these before "done"

Run after the migration. All must pass.

**A. Warehouse == PCN History for every PCN (the #1 complaint):**
```sql
WITH wh AS (SELECT pcn_id, SUM(qty) q FROM inventory_balance GROUP BY pcn_id),
     h  AS (SELECT pcn_id, SUM((CASE WHEN to_location_id   IS NOT NULL THEN qty ELSE 0 END)
                              -(CASE WHEN from_location_id IS NOT NULL THEN qty ELSE 0 END)) q
            FROM inventory_txn WHERE reversed=false GROUP BY pcn_id)
SELECT COUNT(*) FILTER (WHERE COALESCE(wh.q,0) <> COALESCE(h.q,0)) AS mismatches
FROM wh FULL OUTER JOIN h USING (pcn_id);   -- MUST be 0
```

**B. Behavioural (script it):**
1. Stock 3000 into a bin → bin 3000, floor 0, total 3000.
2. Pick 3000 → **bin 0, floor 3000, total 3000 (NOT 6000).**
3. Restock 500 → bin 500, floor 2500, total 3000.
4. Try to pick 99999 → **rejected**, stock unchanged.
5. At every step, Warehouse total == PCN History on-hand.

**C. No negative balances:** `SELECT COUNT(*) FROM inventory_balance WHERE qty < 0;` → 0.

**D. Regression suite:** port the invariant tests
(`backend/tests/test_invariants.py`) — 8/8 must pass on Postgres.

---

## 6. Order of operations (rollout)

1. Build the clean schema + ledger service in a branch (do not touch prod tables).
2. Point it at a **copy** of the prod DB; run the §4 migration.
3. Run §5 acceptance tests on the copy. Fix until green.
4. Cut the app's read/write paths to the ledger service; **delete the reconcilers**.
5. Cut over prod during a maintenance window; keep legacy tables as backup.
6. Monitor the §5-A query daily — it must stay 0.

**Do not** keep the old snapshot+reconcile path "just in case." Two sources of truth
is the bug. One ledger, everything derived. That is the fix.
