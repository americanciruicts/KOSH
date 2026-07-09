# KOSH — PHASE 0 READ-ONLY AUDIT

**Date:** 2026-07-09 · **DB:** `kosh` (container `aci-database`, schema `pcb_inventory`) · **Access:** read-only, role `aci`
**Writes performed:** NONE. Every query below is a `SELECT`/`WITH…SELECT`. No data was modified.

Ledger-derived on-hand is computed with the **exact** shipped math from `app.py` `_ONHAND_RECONCILE_SQL`
(running-floor reflection, `is_relabel` neutralization, RNDT baseline, post-RNDT window) so the audit
measures the real system, not a re-derivation. SQL saved in [`audit-queries.sql`](./audit-queries.sql).

---

## Table sizes
| Table | Rows |
|---|---:|
| `tblWhse_Inventory` | 34,673 |
| `tblTransaction` (the ledger) | 197,342 |
| `tblBOM` | 42,592 |

---

## Headline: the two screens agree *today* — because History is propped up
"Warehouse Inventory ≠ PCN History" is **currently masked**, not cured. PCN History anchors to the stored
Warehouse on-hand (`onhandqty + mfg_qty`) and walks the ledger backward (bug 4/7/20), so the two screens
agree **by construction**. The dirtiness that used to leak through is still in the raw ledger — if you ever
replayed the ledger forward as the source of truth, it would disagree with Warehouse for **~1 in 50 PCNs at
the bin level, and for essentially all floor-staged stock.** That is the case for the rebuild.

---

## Counts by known bug class

### 1. Warehouse vs ledger-derived on-hand (the WHSE≠HIST core)
| Measure | Count |
|---|---:|
| PCNs where **bin** on-hand (`onhandqty`) disagrees with forward-replayed ledger by >5 | **691** |
| &nbsp;&nbsp;↳ ledger **higher** than warehouse (dirty overcount — app correctly distrusts, keeps warehouse) | **515** |
| &nbsp;&nbsp;↳ warehouse **higher** than ledger, bin-only (phantom *bin* over-count) | **0** |
| &nbsp;&nbsp;↳ warehouse higher than ledger, any (incl. floor rows) | 2 |

**Read this carefully:** there are **zero** cases where warehouse bin stock exceeds what the ledger can
justify. Warehouse is conservative and trustworthy at the bin level. All 515 divergences are the ledger
*over*counting (relabel-ADJT phantoms + RESTOCK-after-recount, bugs 4/7/10), which the shipped lower-only
reconcile already refuses to trust. **Warehouse is the right thing to anchor to** — this validates the
Phase 3 plan (anchor opening balances to Warehouse, do NOT re-replay dirty history).

Worst *ledger-higher* offenders (warehouse trusted, ledger is the dirty one):
`11315 8008-180` whse 4700 / ledger 9700 · `1268 8176-155` 4000 / 9000 · `9240 8098-1-235` 3516 / 6873 ·
`2287 6590L-A-18` 3200 / 6400 (a whole family of `6590L-A-*` shows exact 2× — classic recount-doubling).

### 2. MFG-Floor stock — invisible to the ledger (the structural gap)
| Measure | Count |
|---|---:|
| Warehouse rows with floor qty > 0 | **12,700** |
| &nbsp;&nbsp;↳ floor-only (bin = 0, floor > 0) | 12,687 |
| **Total units living on the MFG Floor** | **4,744,889** |

The ledger has **no floor-increment event**. A bin→floor pick decrements bin; the floor quantity exists only
as the `mfg_qty` *column* on the warehouse row. So a forward replay computes on-hand = 0 for every
floor-staged part, and 4.7M units of real inventory are unrepresentable in the event log. This is the single
biggest reason History had to anchor to Warehouse, and it is the #1 target for the Phase 2 redesign
(floor becomes a first-class typed location with signed qty events).

### 3. Bin + floor double-counts (`onhandqty>0 AND mfg_qty>0`)
| Measure | Count |
|---|---:|
| Rows with both > 0 | **13** (all bin-located; the floor-located class was already deduped by bug 20's shipped guard) |
| Overlapping units (LEAST of the two per row) | ~2,985 |

All 13 need **per-row tracing**, not blanket zeroing — a legitimate partial-pick split also has both > 0
(bug 20 explicitly warns against auto-zeroing the bin class). Full list in the catalog. Largest:
`pcn 25972 ACI-8182` bin 190 / floor 3000; `pcn 34300 6163L-9` bin 1120 / floor 1110.

### 4. Phantom stock from relabel-ADJTs (item numbers in location fields)
| Measure | Count |
|---|---:|
| `ADJT` rows total | 18,679 |
| `ADJT` rows that are **renumbers** (both loc fields are item numbers, not locations) | **11,611** |

These are quantity-neutralized in the shipped ledger math (bug 10), so they don't inflate on-hand *today* —
but they are 6% of the entire ledger and are pure noise that the new model should type explicitly
(relabel event, qty 0) instead of re-detecting heuristically on every read.

### 5. Stale locations (bug 8 class)
| Measure | Count |
|---|---:|
| Stocked rows whose `loc_to` ≠ latest ledger placement | **0** ✅ |

The location reconcile (bugs 5/6/8) is fully caught up. This class is currently clean.

### 6. Negative-replay / over-picks (bug 19 class)
| Measure | Count |
|---|---:|
| (pcn,mpn) groups where naive sum-then-clamp = 0 but running-floor > 0 | **31** |
| Units correctly rescued by the running-floor logic | 6,738 |

The shipped Skorokhod-reflection fix (bug 19) is holding: these 31 groups would read 0 under the old math
and are correctly non-zero now.

### 7. Orphan PCNs (referential gaps)
| Measure | Count |
|---|---:|
| PCNs in Warehouse with **no** ledger activity | 10 |
| PCNs in the ledger with **no** Warehouse row | 267 |

### 8. Malformed / dirty ledger rows
| Measure | Count |
|---|---:|
| Rows with **blank** `trantype` | 197 |
| Rows with a **numeric** `trantype` (date-code misparsed into the type column, e.g. `1720`, `2422`) | 67 |
| Rows with `trantype` = `na`/`NA` | 12 |
| Rows with **unparseable** `tran_time` (can't sort chronologically) | 50 |
| Zero-qty PICK rows (bug 24 cosmetic "phantom → MFG Floor" class) | 2,968 |
| Reversed (soft-deleted) rows | 266 |
| MPN case-variant collisions on the same PCN (would break canonical part) | **0** ✅ |

---

## System liveness (sanity checks)
- **Nightly integrity monitor:** last ran **2026-07-09 14:51** (today) — ✅ running.
- **On-hand reconcile audit:** last `auto_reconcile` row **2026-06-22**. ⚠️ It only logs when it *changes*
  a row, so this may just mean nothing needed lowering for 17 days — but the background thread's liveness
  should be confirmed in Phase 1 (spot-check that the reconcile loop is still firing).
- **Reconcile audit history** confirms every prior fix is present: `floor_onhand_dedupe` (19),
  `bug20_bin_stale_mfg_zeroed` (5), `restock_wipe_backfill_20260622` (62), `neutralize_absolute_adjt` (929).

---

## Bottom line for the rebuild
1. **Anchor to Warehouse, never re-replay history.** Proven: warehouse bin stock is never phantom-high
   (0 cases); all divergence is the ledger overcounting. Warehouse is the trustworthy anchor.
2. **The floor must become a first-class ledger location.** 4.7M units / 12,700 rows are currently
   invisible to the event log — the root reason the two screens can't be *one* computation today.
3. **Type the events, don't re-detect them.** 11,611 relabel-ADJTs + ~276 malformed rows + 2,968 zero-qty
   picks are re-classified heuristically on every read. The new append-only ledger should carry explicit
   typed events so these become structurally impossible instead of test-guarded.
4. **Enforce bin/floor disjointness in the schema.** Only 13 rows violate it now (all need manual tracing),
   but a CHECK/one-location-per-lot-row invariant makes the whole class impossible going forward.

**STOP — awaiting approval before Phase 1.** No further queries or writes until you say go.
