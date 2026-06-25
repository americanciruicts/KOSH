# Bug #19 — Over-pick buried later stock (ledger computed 0)

**Date:** 2026-06-25 · **Severity:** 🟥 Critical · **Area:** Inventory / Reconcile · **Status:** ✅ Fixed & deployed · **Tag:** `[WHSE≠HIST]`

## Issue
The reconcile/diagnostic ledger computed **0 on-hand** for parts that physically have stock, so Warehouse Inventory looked like phantom stock versus the ledger. A proposed one-off `bug_memory/fix-bidirectional-reconcile.sql` would have "corrected" Warehouse *down to those 0s* — deleting real inventory.

## Example
PCN **9141** (6779ML-100): `RNDT 1800`, then `PICK 3600` (only 1800 ever existed — a double-entered / erroneous pick), then `RESTOCK 1800`.
- Old math: `1800 − 3600 + 1800 = 0`, clamped by `GREATEST(0, …)` to **0**.
- True on-hand: **1800** (in bin 1501601, the RESTOCK landing spot).
25 PCNs (~5,800 units) were flagged this way; all had `RESTOCK` as their latest event.

## Root cause
The `net` ledger **summed every delta and clamped once** at the end. An over-pick drove the running total negative and a later receipt only refilled it back toward 0, so the receipt's units were absorbed by the impossible earlier pick.

## Fix
Replaced sum-then-clamp with a **running floor at 0** (Skorokhod reflection):

```
on-hand = (base + Σdelta) − LEAST(0, base + deepest running balance)
```

You cannot pick below empty, so the dip is absorbed at the pick and later receipts rebuild from 0. Implemented in `app.py`:
- `_ONHAND_RECONCILE_SQL` (`net_deltas → net_run` window → `net`) — the shipped `reconcile_onhand_from_ledger`.
- The nightly integrity-monitor ledger mirrors the same form.

The computed value is **always ≥** the old `GREATEST(0, sum)`, and the reconcile is **lower-only**, so the change can never lower more than before — only less. **No warehouse data was mutated**; fixing the math made Warehouse and the ledger agree.

## Verified
- Live DB: pcn 9141 `0 → 1800` (= Warehouse); phantom rows (WHSE > ledger by >5) **25 → 0**; invariant **new ≥ old, 0 violations across 35,294 (pcn,mpn) groups**.
- Regression: `tests/regression_tests.py::test_onhand_reconcile_overpick_does_not_zero_refilled_stock` (over-pick + non-receipt refill, phantom-high warehouse → reconcile lowers to the true 1800, not 0). Full suite **26/26**.

## Guard
`test_onhand_reconcile_overpick_does_not_zero_refilled_stock` + this folder's `verify-bug-19-fix.py` (static check that the running-floor form is present).

## Files
- `app.py` — `_ONHAND_RECONCILE_SQL` and the integrity-monitor ledger.
- `tests/regression_tests.py` — the over-pick regression test.
- Commit `3c32a8e`.
