# Bug #20 — On-hand double-counted across bin (onhandqty) + MFG floor (mfg_qty)

**Date:** 2026-06-26 · **Severity:** 🟥 Critical · **Area:** Inventory / On-hand · **Status:** ✅ Fixed & deployed · **Tag:** `[WHSE≠HIST]`

## Name
Bin/floor on-hand double-count — Warehouse Inventory ≠ PCN History, and restock compounds the double.

## Issue
The same physical units were counted in **both** `onhandqty` (warehouse bin) and `mfg_qty` (MFG floor) on the same row. Because:
- **Shortage report** on-hand = `SUM(onhandqty + mfg_qty)`,
- **PCN History** anchored to `SUM(onhandqty)` only,
- **Warehouse Inventory** page shows the two columns separately,

a part with 140 in the bin field **and** 140 in the floor field showed **280** on the shortage report but **140** in PCN History — the "Warehouse ≠ PCN History" mismatch. And a restock (`onhandqty += qty`) on such a row compounds it: **1100 + restock 1100 → 2200**.

## Example
PCN **29862** (8461L-75): `onhandqty=140`, `mfg_qty=140`, `loc_to=MFG Floor`. Its only KOSH-era txn is a **RESTOCK whose `loc_to` was 'MFG Floor'** (restocking onto the floor, not into a bin). 10 rows were in this exact `onhandqty == mfg_qty` state (5 floor-located, 5 bin-located).

## Level / severity
🟥 **Critical** — wrong on-hand shown to users on the shortage report, inconsistent across screens, and self-amplifying on restock.

## Affected files
- `app.py` — PCN History anchor (`pcn_history` route): summed `onhandqty` only.
- `app.py` — Shortage/job on-hand (`SUM(onhandqty + mfg_qty)`) carried a **false comment** asserting "0 rows with both onhandqty>0 AND mfg_qty>0" (37 rows actually had both).
- `app.py` — background sync (`_sync_onhand_from_transactions`): no invariant enforcing bin ⊥ floor.
- Data: `pcb_inventory."tblWhse_Inventory"` — 10 rows with the double.

## Why it was there / why it kept reappearing
The bin and floor counters are meant to be **disjoint** (a unit is in a bin OR on the floor). Nothing enforced that:
1. The shortage fix (bug #9) started summing bin + floor **on the assumption they never overlap** — but RESTOCK-to-`MFG Floor` + the on-hand reconcile re-deriving bin on-hand for parts already on the floor created overlap.
2. The three views used **different definitions** of on-hand (onhand-only vs onhand+floor), so PCN History and the shortage report could never agree when floor stock existed.
Prior fixes (bug #2 restock-wipe, bug #10 relabel-phantom, bug #18 zero-floor-on-restock) addressed other phantom sources but never reconciled the two on-hand **definitions** or enforced the disjoint invariant — so this class kept resurfacing.

## Fix (buggy path removed)
1. **PCN History anchor now = `SUM(onhandqty + mfg_qty)`** — all three views use ONE total-on-hand definition, so Warehouse = PCN History whenever floor stock exists.
2. **`reconcile_floor_onhand` guard** (shipped, runs every cycle in `_sync_onhand_from_transactions`): a row physically on the MFG floor (`loc_to='MFG Floor'`) cannot hold bin on-hand → zero the phantom `onhandqty`, keep `mfg_qty`. Lower-only, audit-logged (`tblReconcileAudit` source `floor_onhand_dedupe`). This both fixes the 5 floor rows and prevents floor-class recurrence.
3. **False comment corrected** in the shortage on-hand SQL.
4. **Bin-located doubles (5 rows):** deliberately NOT auto-mutated (deciding bin-vs-floor truth there isn't safe to automate). Surfaced for explicit review; remediation in `remediation-bug-20.sql` (bin half requires explicit authorization).

## Verified
- Regression: `test_floor_onhand_dedupe_zeroes_phantom_bin_not_floor_or_bins`, `test_pcn_history_anchor_counts_mfg_floor_stock`. Full suite green.
- Post-deploy: the floor guard zeroes the 5 floor rows' phantom on-hand (audit-logged); Warehouse total (onhand+mfg) == PCN History for those PCNs.

## Guard
The two regression tests above + this folder's `verify-bug-20-fix.py` (static: anchor sums mfg, guard function present) + the nightly integrity monitor counter for `onhandqty>0 AND mfg_qty>0`.
