# Bug #6 - Manual Bin Edits Didn't Stick
## 🟧 High - Manual Relocations Reverted Within 5 Minutes

**Date:** 06/16/2026  
**Severity:** 🟧 High  
**Status:** ✅ FIXED & TESTED

## The Bug

**Issue:** Manual location change in Warehouse editor reverted within 5 minutes

**Example:**
- ~2,435 stocked PCNs reverting in live data
- User manually moves PCN to new bin → within 5 min, location reverts to old bin

## Root Cause

Reconcile only treated these transaction types as placements:
- PTWY (put-away)
- RESTOCK
- INDF (indirect floor stock)
- STOCK

**Manual edit logs ADJT** (adjustment) which was **ignored** by reconcile!

**What happened:**
1. User manually edits location in Warehouse editor → logs ADJT transaction
2. Reconcile runs every ~5 minutes
3. Reconcile ignores ADJT, uses last PTWY/RESTOCK/INDF/STOCK instead
4. Location reverts to old bin ❌

## The Fix

**Added ADJT to the placements set:**
```sql
-- OLD (BROKEN):
AND trantype IN ('PTWY','RESTOCK','INDF','STOCK')  -- Missing ADJT!

-- NEW (FIXED):
AND trantype IN ('PTWY','RESTOCK','INDF','STOCK','ADJT')  -- ADJT included!
```

**Smart filter prevents relabel-ADJT pollution:**
- Manual location ADJT: `loc_to = "14051021"` (numeric bin) → ✅ Accepted
- Relabel ADJT: `loc_to = "8233L-5"` (item number) → ❌ Rejected (not numeric, not in locvocab)

**Function:**
- `_LOCATION_RECONCILE_SQL` @ [app.py:3052](../../app.py#L3052)

## Verification

**Test Results:** ✅ ALL 3 TESTS PASSED
- [PASS] ADJT in placements trantype list
- [PASS] ADJT manual edit behavior documented
- [PASS] Location filter rejects relabel-ADJTs

**Run test:** `python verify-bug-06-fix.py`

## Impact

Fixed ~2,435 stocked PCNs that were reverting.

**Now:**
- User edits location → ADJT logged
- Reconcile honors ADJT as latest placement
- Location stays changed ✅

---

**Commit:** 5de9e4c  
**Verified:** 2026-06-25  
**Status:** ✅ FIXED & TESTED
