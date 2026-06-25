# Warehouse vs PCN History Discrepancy Check

## Current State (Post Bug Fixes)

### ✅ Major Fixes Applied (Bugs #1-18)

**Bug #4 - THE Architectural Fix:**
- PCN History now **ANCHORS** to Warehouse value
- Walks **BACKWARD** from anchor (not forward replay)
- RNDT is **quantity-neutral**
- **SHOULD guarantee: PCN History = Warehouse**

**Bug #7 - Relabel-ADJTs in History:**
- is_relabel treated as quantity-neutral in History

**Bug #10 - Phantom Stock (15.3M units):**
- is_relabel treated as quantity-neutral in Warehouse reconcile
- Removed 1,439,125 phantom units

### 🔍 Monitoring in Place

**Nightly Integrity Check** (app.py @ L3452)
- Checks: `stored_above_ledger` (Warehouse > Ledger)
- Logs to `tblIntegrityCheckLog`
- Warns if regression detected

## ⚠️ User Report: "PCN History More Accurate"

**Observation:**
- User reports PCN History often shows correct value
- Warehouse sometimes incorrect
- **Suggests:** Warehouse < Ledger cases (missing stock, not phantom)

## 🔬 Diagnostic Query Provided

**File:** `diagnostic-warehouse-vs-history-discrepancies.sql`

**What it checks:**
1. **PHANTOM_STOCK**: Warehouse > Ledger (already monitored)
2. **MISSING_STOCK**: Warehouse < Ledger ⚠️ (NOT currently monitored!)
3. Shows count and total units affected

**How to run:**
```sql
psql -U postgres -d kosh_db -f diagnostic-warehouse-vs-history-discrepancies.sql
```

## 🎯 Expected Results

### Scenario A: All Fixed ✅
```
 status         | count | total_units_affected
----------------+-------+---------------------
 (no rows)
```
**Meaning:** Warehouse = Ledger for all PCNs

### Scenario B: PHANTOM_STOCK Found ⚠️
```
 status         | count | total_units_affected
----------------+-------+---------------------
 PHANTOM_STOCK  |   15  |        2,450
```
**Meaning:** Warehouse higher than ledger (Bug #10 regression)

**Action:**
- Check nightly integrity logs
- Verify is_relabel logic working
- May need on-hand reconcile run

### Scenario C: MISSING_STOCK Found ⚠️⚠️
```
 status         | count | total_units_affected
----------------+-------+---------------------
 MISSING_STOCK  |   42  |        8,730
```
**Meaning:** Warehouse LOWER than ledger (History shows more)

**Action Required:**
- **NEW BUG** - Warehouse not getting updates that History has
- Possible causes:
  1. Reconcile not running frequently enough
  2. Reconcile has downward-only guard that blocks corrections
  3. Some transaction types not updating Warehouse
  4. MFG Floor stock (mfg_qty) not being reconciled

**To investigate:**
```sql
-- See detailed discrepancies (uncomment in diagnostic query)
-- Then check transaction log for those PCNs
-- Compare what History sees vs what Warehouse shows
```

## 🔧 Potential Fix for MISSING_STOCK

If diagnostic shows MISSING_STOCK cases:

### 1. Check Reconcile Frequency
```python
# app.py - look for reconcile schedule
# Should run frequently (hourly or more)
```

### 2. Check Downward-Only Guard
```sql
-- If reconcile has: WHERE new_qty < current_qty
-- This would prevent UPWARD corrections!
```

### 3. Add Bidirectional Monitoring
```python
# Update nightly integrity check to also monitor:
# - warehouse < ledger (missing stock)
# - Not just warehouse > ledger (phantom stock)
```

### 4. Run Manual Reconcile
```sql
-- Force reconcile to update all Warehouse values to match ledger
-- See _ONHAND_RECONCILE_SQL in app.py
```

## 📊 Next Steps

1. **Run diagnostic query** on production database
2. **Check results** - any PHANTOM_STOCK or MISSING_STOCK?
3. **If discrepancies found:**
   - Uncomment detailed view in query
   - Identify specific PCNs affected
   - Check transaction history for those PCNs
   - Determine root cause
4. **Create Bug #19** if new issue found

## 💡 Key Insight

**Bug #4 fixed FORWARD REPLAY doubling** (History showed 2× Warehouse)

**But if Warehouse reconcile isn't running or has issues:**
- History could show CORRECT value (from ledger)
- Warehouse could show STALE value (not reconciled)
- Result: "PCN History more accurate than Warehouse" ← User's observation

**Solution:** Ensure on-hand reconcile runs regularly and updates Warehouse to match ledger.
