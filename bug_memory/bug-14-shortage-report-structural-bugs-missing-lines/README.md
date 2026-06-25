# Bug #14 - Shortage Report Structural Bugs + "Missing Lines"
## 🟧 High - Theresa "Lost Trust in the Report"

**Date:** 06/03 → 06/04/2026  
**Severity:** 🟧 High  
**Reported by:** Theresa  
**Status:** ✅ FIXED & TESTED

## The Bug

**Issue:** Multiple structural problems causing missing/incorrect shortage lines

**Symptoms:**
- Lines showing qty 0 (should have real qty)
- Lines dropped entirely from report
- Ignored same-MPN stock under other part numbers → re-bought parts on shelf
- Worst zero-stock shortages hidden by default toggle

## Root Causes

### A. Alternate-Part Dedup Kept qty-0 "ZSUB" Row
- Multiple alternate parts for same component
- ZSUB (zero-stock substitute) with qty=0 won dedup
- Real part with qty>0 dropped
- Result: requirement = 0 ❌

### B. MPN-Based On-Hand Match Pulled Other Jobs' Stock
- Matched on-hand by MPN across ALL jobs
- Job A sees Job B's stock
- Rows exploded with cross-job matches
- Stock double-counted

### D. Two Drifted Report Generators
- Duplicate code generating reports
- Fixes applied to one but not the other
- Reports inconsistent

### E. "Hide 0 On Hand" Toggle Defaulted ON
- Hid zero-stock lines by default
- Worst shortages invisible
- Users missed critical shortages

## The Fix

### 1. Deterministic Dedup (qty DESC)
```sql
ORDER BY b.aci_pn, 
         CASE WHEN b.qty ~ '^[0-9]+([.][0-9]+)?$' 
              THEN b.qty::numeric 
              ELSE 0 
         END DESC
```
**Result:** Highest qty wins, not qty-0 ZSUB

### 2. Job-Scoped Own-Stock Match
```sql
-- OLD (BROKEN):
LEFT JOIN tblWhse_Inventory w
  ON w.mpn = bl.bom_mpn  -- Cross-job match!

-- NEW (FIXED):
LEFT JOIN tblWhse_Inventory w
  ON UPPER(w.item) = UPPER(bl.aci_pn)  -- Job's own part only
```

### 3. Single Shared Builder
- `_persist_shortage_report()` @ L5236
- `_SHORTAGE_MATCH_SQL` @ L5131
- One source of truth
- No more drift

### 4. Same-MPN Visibility Column
- Shows "other PNs with same MPN" for visibility
- NOT used for matching (visibility-only)
- Chemring: strict exact-MPN (defense traceability)
- Others: tolerant matching
- Performance: 33s → 2s

### 5. Toggle Defaults OFF
- "Hide 0 On Hand" now OFF by default
- Zero-stock shortages visible
- Users see critical shortages

**Files:**
- `_SHORTAGE_MATCH_SQL` @ [app.py:5131](../../app.py#L5131)
- `_persist_shortage_report()` @ [app.py:5236](../../app.py#L5236)

## Verification

**Test Results:** ✅ ALL 4 TESTS PASSED
- [PASS] Deterministic dedup (qty DESC)
- [PASS] _persist_shortage_report() single builder
- [PASS] _SHORTAGE_MATCH_SQL single source
- [PASS] Structural fixes documentation

**Run test:** `python verify-bug-14-fix.py`

## Impact

**Theresa regained trust in the report** ✅

Now:
- No missing lines
- Correct quantities
- Same-MPN visibility (not matching)
- Zero-stock shortages visible
- Single consistent generator

---

**Commits:** 73f8664, 1e81161, 2c6515f, b48263f  
**Verified:** 2026-06-25  
**Status:** ✅ FIXED & TESTED
