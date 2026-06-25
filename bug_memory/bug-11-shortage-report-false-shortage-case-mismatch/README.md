# Bug #11 - Shortage Report False Shortage from Case Mismatch
## 🟧 High - Case-Sensitive Join Missed Stock

**Date:** 06/12/2026  
**Severity:** 🟧 High  
**Status:** ✅ FIXED & TESTED

## The Bug

**Issue:** Part with stock flagged as shortage; same part also shown as "same-MPN, other PN" row

**Example:**
- BOM line: `6779ML-97` (uppercase "ML")
- Stock: `6779ml-97` (lowercase "ml") - 890 units on hand
- Shortage report: Shows **0 on-hand** for BOM line ❌
- Also shows 890 units under "same-MPN, other PN" (different case)
- Result: False shortage flagged

## Root Cause

**Own-stock join was case-sensitive:**

```sql
-- OLD (BROKEN):
LEFT JOIN tblWhse_Inventory w
  ON w.item = bl.aci_pn  -- Case-sensitive!
```

**What happened:**
- BOM `6779ML-97` ≠ stock `6779ml-97` (case mismatch)
- Join fails → no match
- qty_on_hand = 0 (missed the 890 units)
- Flagged as shortage

**Why is there case mismatch?**
- Inventory stores same part number in mixed case
- BOM might have uppercase, stock might have lowercase
- Should be considered the SAME part!

## The Fix

**Make own-stock join case-insensitive:**

```sql
-- NEW (FIXED):
LEFT JOIN tblWhse_Inventory w
  ON UPPER(w.item) = UPPER(bl.aci_pn)  -- Case-insensitive!
```

**Also applied to same-MPN exclusion** (prevents double-counting)

**Location:**
- `_SHORTAGE_MATCH_SQL` › `inv` CTE @ [app.py:5159](../../app.py#L5159)

## Verification

**Test Results:** ✅ ALL 3 TESTS PASSED
- [PASS] Case-insensitive join (UPPER)
- [PASS] Case mismatch documentation
- [PASS] _SHORTAGE_MATCH_SQL exists

**Run test:** `python verify-bug-11-fix.py`

## Impact

**Now:**
- BOM `6779ML-97` matches stock `6779ml-97` ✅
- 890 units correctly counted
- No false shortage
- Case variations treated as same part

**Before:**
- BOM `6779ML-97`: qty_on_hand = 0 (missed 890 units)
- Flagged as shortage
- Purchasing would re-buy

**After:**
- BOM `6779ML-97`: qty_on_hand = 890 ✅
- No shortage
- No duplicate purchasing

---

**Commit:** 9a54620  
**Verified:** 2026-06-25  
**Status:** ✅ FIXED & TESTED
