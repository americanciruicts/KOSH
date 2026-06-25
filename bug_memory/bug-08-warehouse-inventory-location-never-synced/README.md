# Bug #8 - Warehouse Inventory Location Never Synced
## 🟧 High - Stale Bins (~4,792 Rows)

**Date:** 06/15/2026  
**Severity:** 🟧 High  
**Reported by:** Theresa  
**Status:** ✅ FIXED & TESTED

## The Bug

**Issue:** Warehouse showed old bin; History showed the true one

**Example:**
- ~4,792 stocked rows had stale locations at first sync
- Warehouse: PCN in old bin "2205301"
- History: PCN actually in new bin "14051021"

## Root Cause

**KOSH only set `loc_to` on its own operations:**
- When KOSH did STOCK/RESTOCK → set loc_to ✅
- When Access did PTWY (put-away) → imported but loc_to NOT updated ❌

**Reconcile only synced on-hand qty, NOT location:**
- On-hand reconcile updated `onhandqty` from transaction log
- But `loc_to` was never synced from transaction log
- Result: Warehouse locations became increasingly stale

**What are put-aways (PTWY)?**
- Imported from Access database
- Record where parts were physically placed
- KOSH imported the transaction but never updated Warehouse `loc_to`

## The Fix

**Added location reconcile system:**

1. **Sync `loc_to` from transaction log** (just like on-hand qty)
2. **Latest placement wins** (chronological `tran_time`, DESC order)
3. **Only placement transactions count:**
   - PTWY (put-away) ✅
   - RESTOCK ✅
   - INDF (indirect floor stock) ✅
   - STOCK ✅
   - ADJT (manual edits) ✅
   - PICK ❌ (doesn't change location)
   - PURGE ❌ (doesn't change location)

**Functions:**
- `_LOCATION_RECONCILE_SQL` @ [app.py:3024](../../app.py#L3024)
- `reconcile_warehouse_locations()` @ [app.py:3078](../../app.py#L3078)

**SQL Logic:**
```sql
-- placements CTE: Find latest loc_to for each PCN
placements AS (
    SELECT pcn, loc_to, tran_time
    FROM tblTransaction
    WHERE trantype IN ('PTWY','RESTOCK','INDF','STOCK','ADJT')
      AND loc_to IS NOT NULL
),
latest_place AS (
    SELECT DISTINCT ON (pcn) pcn, loc_to AS place_loc
    FROM placements
    ORDER BY pcn, tran_time DESC, id DESC  -- Latest wins
)
UPDATE tblWhse_Inventory w
SET loc_to = p.place_loc
FROM latest_place p
WHERE w.pcn = p.pcn
```

## Verification

**Test Results:** ✅ ALL 4 TESTS PASSED
- [PASS] _LOCATION_RECONCILE_SQL exists
- [PASS] reconcile_warehouse_locations() function exists
- [PASS] Latest placement chronological order
- [PASS] Picks/purges ignored

**Run test:** `python verify-bug-08-fix.py`

## Impact

**First run:** Backfilled ~4,792 stale rows  
**Ongoing:** Self-heals (reconcile runs automatically)

**Now:**
- Warehouse locations sync from transaction log
- PTWY put-aways update loc_to
- Warehouse and History both show correct bin ✅

---

**Commit:** b06f52b  
**Verified:** 2026-06-25  
**Status:** ✅ FIXED & TESTED
