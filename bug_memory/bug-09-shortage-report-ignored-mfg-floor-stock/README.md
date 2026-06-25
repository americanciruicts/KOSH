# Bug #9 - Shortage Report Ignored MFG-Floor Stock
## 🟧 High - False Shortages Triggered Duplicate Purchasing

**Date:** 06/15/2026  
**Severity:** 🟧 High  
**Status:** ✅ FIXED & TESTED

## The Bug

**Issue:** Job with material on MFG Floor was flagged short → Purchasing re-bought parts

**Example:**
- Job has parts physically sitting on MFG Floor
- Shortage report shows **0 on-hand** for those lines
- Job flagged as shortage
- Purchasing orders duplicates ❌

## Root Cause

**Shortage report excluded `loc_to='MFG Floor'` rows:**
- Parts on MFG Floor stored with `mfg_qty > 0`
- Shortage report only counted `onhandqty` (bin stock)
- Ignored `mfg_qty` (floor stock)
- Result: Floor stock read as 0 on-hand

**What is MFG Floor stock?**
- Parts moved from bins to manufacturing floor
- Stored in `mfg_qty` field (not `onhandqty`)
- Location = "MFG Floor"
- Physically exists but wasn't counted!

## The Fix

**Include MFG Floor stock in on-hand calculation:**

```sql
-- OLD (BROKEN):
SUM(onhandqty) as qty_on_hand  -- Missing floor stock!

-- NEW (FIXED):
SUM(onhandqty + CASE WHEN mfg_qty ~ '^-?[0-9]+$' 
                THEN mfg_qty::int ELSE 0 END) as qty_on_hand
```

**Why is this safe?**
- Physical on-hand per lot = bin on-hand + floor qty
- These **never overlap** (Task-1 fix guarantees 0 rows with both `onhandqty>0` AND `mfg_qty>0`)
- Summing can't double-count
- `mfg_qty` is TEXT → parse defensively with regex

**Applied in 3 locations:**
1. `_SHORTAGE_MATCH_SQL` › `inv` CTE @ [app.py:5150](../../app.py#L5150)
2. Job view 1 @ [app.py:8429](../../app.py#L8429)
3. Job view 2 @ [app.py:8731](../../app.py#L8731)

## Verification

**Test Results:** ✅ ALL 4 TESTS PASSED
- [PASS] Shortage report includes mfg_qty
- [PASS] Job view 1 includes mfg_qty
- [PASS] Job view 2 includes mfg_qty
- [PASS] MFG Floor documentation

**Run test:** `python verify-bug-09-fix.py`

## Impact

**Now:**
- Shortage report includes floor stock ✅
- Jobs with MFG Floor material show correct on-hand
- No false shortages
- No duplicate purchasing

**Example:**
- Part on MFG Floor: `onhandqty=0`, `mfg_qty=500`
- Before: qty_on_hand = 0 (flagged shortage)
- After: qty_on_hand = 500 (no shortage) ✅

---

**Commit:** 0a020fc  
**Verified:** 2026-06-25  
**Status:** ✅ FIXED & TESTED
