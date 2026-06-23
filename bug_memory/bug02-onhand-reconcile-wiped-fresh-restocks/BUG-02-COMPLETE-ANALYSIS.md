# 🐛 Bug #2 - Complete Engineering Analysis & Fix
## On-Hand Reconcile Wiped Fresh Restocks to 0

---

## 📊 Executive Summary

| Field | Value |
|-------|-------|
| **Bug ID** | #2 |
| **Title** | On-hand reconcile wiped fresh restocks to 0 |
| **Severity** | 🟥 Critical |
| **Area** | Inventory / Reconcile |
| **Reported Date** | 06/22/2026 |
| **Reported By** | Preet ("edits not saving") |
| **Status** | ✅ Fixed & Deployed |
| **Deploy Date** | 06/22/2026 |
| **Commit** | `1958a08` |
| **Rows Affected** | 62 zeroed rows backfilled |
| **Business Impact** | Fresh restocks being wiped hours after saving |

---

## 🎯 The Problem

### User-Reported Issue

**From Preet's report (06/22/2026):**

> "Edits not saving - I restocked some parts and they're showing 0 again hours later."

### Specific Example

**PCN:** 42137
**Timeline:**
- **06/18 07:30** - `parts@` user restocked **15 units**
- **06/18 11:31** - On-hand reconcile ran and **zeroed it to 0 units**
- **Result:** Fresh restock disappeared, Warehouse showed 0, but PCN History still showed the restock

### Business Impact

1. **Data Integrity Crisis:**
   - Fresh inventory updates being silently erased
   - Warehouse Inventory ≠ PCN History (core system trust issue)
   - Users losing confidence in data persistence

2. **Operational Impact:**
   - Parts shown as out of stock when actually restocked
   - False shortages triggering unnecessary purchasing
   - Warehouse staff wasting time re-verifying stock

3. **Scale:**
   - **62 rows** sitting at 0 when they should have had stock
   - Affects every restock operation on parts with incomplete ledger history
   - Silent data loss (no error messages, no user notification)

---

## 🔍 Root Cause Analysis

### The Buggy Logic

The on-hand reconcile process works by:
1. Replaying the entire transaction ledger for each part
2. Computing net on-hand from all stock-in and stock-out transactions
3. Comparing computed value to stored warehouse value
4. Updating warehouse if different (with "lower-only" guard to prevent phantom stock)

**The problem:** Some parts have **incomplete ledger history** (more PICKs than stock-ins in the imported Access data).

```sql
-- Buggy behavior (reconstructed):
-- 1. Replay ledger for PCN 42137
SELECT SUM(
  CASE 
    WHEN trantype IN ('RESTOCK', 'STOCK') THEN tranqty  -- Stock in
    WHEN trantype IN ('PICK', 'PURGE') THEN -tranqty    -- Stock out
  END
) as computed_qty
FROM tblTransaction
WHERE pcn = 42137

-- 2. For parts with incomplete history:
--    - Historical picks: -50
--    - Historical restocks: +30
--    - Net: -20 → clamped to 0 (can't have negative stock)

-- 3. Current warehouse value: 15 (from fresh restock at 07:30)
-- 4. Computed value: 0 (from incomplete ledger replay)

-- 5. Lower-only guard:
IF computed_qty < current_warehouse_qty THEN
  UPDATE tblWhse_Inventory SET onhandqty = computed_qty  -- 15 → 0 ❌
END IF
```

### Why This Failed

**The Fatal Sequence:**

1. **07:30** - User restocks 15 units
   - Direct UPDATE to `tblWhse_Inventory`: `onhandqty = 15`
   - Transaction logged to `tblTransaction`
   - Everything looks good ✓

2. **11:31** - Scheduled reconcile runs
   - Replays **entire** transaction history (including old incomplete data)
   - Old incomplete ledger: more picks than stock-ins → nets to -20
   - Clamp negative to 0: `GREATEST(0, -20) = 0`
   - Lower-only guard: `0 < 15` → **overwrites fresh restock to 0** ❌

3. **Result:**
   - Warehouse Inventory: 0 (wrong)
   - PCN History: 15 (correct - shows the restock transaction)
   - User sees: "My edit didn't save" (actually it did, but reconcile wiped it)

### The Core Issue

**Mental model error:**

The reconcile assumed:
> "Ledger replay is authoritative; warehouse value is suspect"

**Reality:**
> "For parts with incomplete ledgers, **fresh receipts** are authoritative; ledger replay is suspect"

**The missing distinction:**
- **Fresh restock (RESTOCK/STOCK)** = authoritative (just happened, user-verified)
- **Replayed ledger value** = suspect (incomplete historical data)

The reconcile treated all warehouse values equally, not recognizing that a row whose **latest transaction is a fresh receipt** has a more authoritative on-hand than the ledger replay.

---

## ✅ The Fix

### Fixed Logic

**New approach: Protect fresh receipts from ledger-based overwriting**

```sql
-- FIXED QUERY (app.py @ L3204-3237)

-- Step 1: Identify latest transaction type per (pcn, mpn)
latest_event AS (
    -- The most recent MATERIAL transaction per (pcn, mpn). When this
    -- is a fresh receipt (RESTOCK/STOCK) the row's on-hand was just
    -- established by that receipt's own UPDATE. The historical Access
    -- ledger is INCOMPLETE for some parts (more PICKs than stock-ins),
    -- so replaying it nets negative -> GREATEST(0,...) clamps to 0, and
    -- the lower-only guard below would then WIPE the fresh restock.
    SELECT DISTINCT ON (pcn, mpn_key) 
        pcn, 
        mpn_key, 
        trantype AS last_type
    FROM parsed
    WHERE reversed = false
      AND trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
    ORDER BY pcn, mpn_key, 
             ts DESC NULLS LAST,  -- Chronological order
             id DESC              -- Tie-breaker
)

-- Step 2: Apply guard when updating
UPDATE tblWhse_Inventory
SET onhandqty = computed_qty
WHERE onhandqty IS DISTINCT FROM computed_qty
  AND ... (activity checks)
  -- ✅ CRITICAL FIX: Never lower a row whose most recent material 
  --    event is a fresh receipt
  AND COALESCE(latest_event.last_type, '') NOT IN ('RESTOCK', 'STOCK')
  -- Lower-only guard (existing protection)
  AND computed_qty < onhandqty
```

### How the Fix Works

**Protection logic:**

1. **Identify latest transaction** for each (pcn, mpn) pair
   - `DISTINCT ON (pcn, mpn_key)` + `ORDER BY ts DESC`
   - Gets the most recent material transaction

2. **Check if latest is a fresh receipt**
   - If `last_type IN ('RESTOCK', 'STOCK')` → **protect the row**
   - If `last_type IN ('PICK', 'PURGE', ...)` → allow correction

3. **Guard condition:**
   ```sql
   AND COALESCE(le.last_type, '') NOT IN ('RESTOCK','STOCK')
   ```
   - Prevents lowering rows where latest event is RESTOCK/STOCK
   - Allows lowering rows where latest event is PICK/PURGE/etc.

### Example with Fix Applied

**PCN 42137 scenario with fix:**

| Time | Event | Warehouse | Ledger Replay | Latest Event | Fix Behavior |
|------|-------|-----------|---------------|--------------|--------------|
| 06/18 07:30 | User restocks 15 | 15 | (not run yet) | RESTOCK | - |
| 06/18 11:31 | Reconcile runs | 15 | 0 (incomplete ledger) | RESTOCK | ✅ **Protected** - skip update |
| Result | - | **15** ✅ | 0 (ignored) | RESTOCK | Fresh restock preserved! |

**PCN with phantom stock (latest = PICK):**

| Time | Event | Warehouse | Ledger Replay | Latest Event | Fix Behavior |
|------|-------|-----------|---------------|--------------|--------------|
| Prior | Old data | 100 | 50 (correct) | PICK | - |
| Reconcile | Runs | 100 | 50 | PICK | ✅ **Allowed** - lower to 50 |
| Result | - | **50** ✅ | 50 | PICK | Phantom corrected! |

**The fix distinguishes:**
- ✅ Fresh receipts (RESTOCK/STOCK latest) → **protect** (authoritative)
- ✅ Consumed stock (PICK/PURGE latest) → **allow correction** (ledger is authoritative)

---

## 🛠️ Technical Implementation

### Files Modified

**Primary file:** `app.py`

**Location:** Line 3204-3237

### Code Changes

**Change #1: Added `latest_event` CTE (L3204-3220)**

```sql
, latest_event AS (
    -- Identify the most recent material transaction per (pcn, mpn)
    SELECT DISTINCT ON (pcn, mpn_key) 
        pcn, 
        mpn_key, 
        trantype AS last_type
    FROM parsed
    WHERE reversed = false
      AND trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
    ORDER BY pcn, mpn_key, 
             ts DESC NULLS LAST,
             id DESC
)
```

**Change #2: Join `latest_event` in update query (L3230)**

```sql
LEFT JOIN latest_event le
  ON le.pcn = n.pcn AND le.mpn_key = n.mpn_key
```

**Change #3: Guard against lowering fresh restocks (L3234-3237)**

```sql
-- Never lower a row whose most recent material event is a fresh
-- receipt: the receipt set the authoritative on-hand and the
-- incomplete historical ledger must not overwrite it. (2026-06-22)
AND COALESCE(le.last_type, '') NOT IN ('RESTOCK','STOCK')
```

### Additional Data Fix

**Separate remediation pass:** 62 rows backfilled

```sql
-- Audit trail: restock_wipe_backfill_20260622
-- Identified 62 rows that were zeroed by reconcile
-- Restored values from PCN History transaction log
-- Verified against physical inventory
```

---

## 📊 Impact Metrics

### Immediate Impact
- **Rows corrected:** 62 (backfilled from 0 to correct values)
- **Future protection:** All fresh restocks now protected from reconcile
- **Data integrity:** Warehouse Inventory = PCN History consistency restored

### Business Value
- ✅ User edits now persist (no silent data loss)
- ✅ Fresh restocks protected from erroneous zeroing
- ✅ Prevented false shortages from appearing
- ✅ Restored trust in inventory data

---

## 🔒 Data Safety

### Why This Fix is Safe

1. **Surgical targeting:**
   - Only affects rows where latest event is RESTOCK/STOCK
   - Does not protect phantom-high stock (latest = PICK still corrected)

2. **Preserves existing protections:**
   - Lower-only guard still active
   - Activity check (pick_count > 0) still required
   - Relabel neutralization (Bug #10 fix) still applies

3. **No schema changes:**
   - Pure SQL query logic change
   - No ALTER TABLE, no data migrations
   - Reversible (just remove the guard)

### Edge Cases Handled

**Case 1: Multiple restocks in sequence**
- Latest event = RESTOCK
- Protected ✓

**Case 2: Restock followed by pick**
- Latest event = PICK (not RESTOCK)
- NOT protected → allows correction ✓

**Case 3: Restock followed by another restock**
- Latest event = RESTOCK (most recent)
- Protected ✓

**Case 4: No transactions (new part)**
- latest_event.last_type = NULL
- `COALESCE(NULL, '') NOT IN (...)` = TRUE
- NOT protected → allows normal operation ✓

**Case 5: Only picks, no restocks**
- Latest event = PICK
- NOT protected → allows correction ✓

---

## 🧪 Verification Methods

### SQL Verification Query

```sql
-- Check for rows that would be affected by Bug #2
WITH latest_txn AS (
    SELECT DISTINCT ON (pcn, LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')))
        pcn,
        LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) as mpn_key,
        trantype,
        tran_time
    FROM tblTransaction
    WHERE trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT')
    ORDER BY pcn, 
             LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')),
             tran_time DESC NULLS LAST,
             id DESC
)
SELECT 
    w.pcn,
    w.item,
    w.mpn,
    w.onhandqty as current_qty,
    lt.trantype as latest_event,
    lt.tran_time as latest_event_time,
    CASE 
        WHEN lt.trantype IN ('RESTOCK', 'STOCK') THEN 'PROTECTED ✅'
        ELSE 'NORMAL'
    END as protection_status
FROM tblWhse_Inventory w
JOIN latest_txn lt 
    ON w.pcn::text = lt.pcn
    AND LOWER(TRANSLATE(COALESCE(w.mpn,''), '-# ./', '')) = lt.mpn_key
WHERE w.onhandqty > 0
    AND lt.trantype IN ('RESTOCK', 'STOCK')
ORDER BY lt.tran_time DESC
LIMIT 50;
```

**Expected:** Shows rows protected by the fix (latest event = RESTOCK/STOCK)

### Manual Test Case

**Reproduce Bug #2 scenario (with fix active):**

1. Find a part with incomplete ledger history
2. Manually restock to a known quantity (e.g., 25 units)
3. Note the time
4. Wait for reconcile to run (or trigger manually)
5. Check warehouse quantity

**Expected:** Quantity remains 25 (not zeroed) ✅

---

## 📚 Lessons Learned

### What Went Wrong

1. **Incomplete data assumption:**
   - Assumed ledger was complete and authoritative
   - Didn't account for Access migration data quality

2. **One-size-fits-all reconciliation:**
   - Treated all warehouse values equally
   - Didn't distinguish fresh updates from stale values

3. **Silent failure:**
   - No logging when reconcile lowered values
   - Users only discovered issue hours later

### What We Fixed

1. **Context-aware reconciliation:**
   - Check latest transaction type before lowering
   - Protect fresh receipts, correct phantom stock

2. **Data quality recognition:**
   - Acknowledge incomplete historical ledger
   - Trust fresh user operations over ledger replay

3. **Surgical protection:**
   - Only protect when latest = RESTOCK/STOCK
   - Still allow correction when latest = PICK/PURGE

### Prevention Strategy

**For future inventory fixes:**
1. ✅ Always consider data quality of imported legacy data
2. ✅ Distinguish "fresh authoritative updates" from "historical computed values"
3. ✅ Add logging for reconcile actions (future enhancement)
4. ✅ Test with parts that have incomplete ledger history
5. ✅ Monitor for "edits not saving" user complaints

---

## 🔗 Related Bugs

This fix works with:

- **Bug #4:** RESTOCK-after-recount doubling (anchored history)
  - Both involve reconciliation and RESTOCK handling
  - Bug #2 protects fresh RESTOCKs from being zeroed
  - Bug #4 prevents RESTOCKs from being double-counted

- **Bug #10:** Phantom stock (relabel neutralization)
  - Reconcile still corrects phantom-high stock
  - Bug #2 only protects fresh restocks, not phantom stock

---

## ✅ Final Status

**Bug #2:** ✅ **FIXED AND DEPLOYED**

**Verification:**
- ✅ Code inspection confirmed at app.py L3237
- ✅ 62 rows backfilled (audit trail: restock_wipe_backfill_20260622)
- ✅ No recurrences reported since fix
- ✅ Warehouse Inventory = PCN History consistency restored

**Confidence level:** 🟢 High
- Surgical fix targeting exact issue
- Preserves existing protections
- No schema changes, fully reversible

---

**Document version:** 1.0  
**Last updated:** 06/23/2026  
**Maintained by:** KOSH Engineering Team
