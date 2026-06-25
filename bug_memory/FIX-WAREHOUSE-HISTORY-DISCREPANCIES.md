# FIX: Warehouse vs PCN History Discrepancies

## 🔍 Problem Identified

**Root Cause:** On-hand reconcile has **DOWNWARD-ONLY guard** (app.py @ L3249)
```python
AND n.qty < w.onhandqty  # Only corrects when ledger < warehouse
```

**Effect:**
- ✅ Prevents upward corrections (protects against Bug #4 phantom doubling)
- ❌ Cannot fix legitimate cases where Warehouse < Ledger
- Result: **"PCN History more accurate than Warehouse"** ← Your observation!

**Why it exists:**
- Protects against RESTOCK-after-recount doubling (Bug #4)
- Design: Real receipts should update via restock_pcb/stock operations
- Reconcile only fixes downward (phantom stock removal)

**Why it's a problem:**
- If Warehouse gets out of sync in downward direction (shows less than actual)
- Reconcile can't fix it
- PCN History shows correct value (from ledger)
- Warehouse shows stale/incorrect value

## ✅ Solution: Bidirectional Reconcile + Enhanced Monitoring

### Fix #1: Manual Bidirectional Reconcile (Immediate)

**File:** `fix-bidirectional-reconcile.sql`

**What it does:**
- Reconciles Warehouse to match Ledger in BOTH directions
- DOWNWARD: Removes phantom stock (warehouse > ledger)
- UPWARD: Fixes missing stock (warehouse < ledger)

**Safety:**
- Only fixes discrepancies > 5 units (avoids churn)
- Logs all changes to tblReconcileAudit
- Shows before/after for review
- Can be rolled back if needed

**How to run:**
```bash
# BACKUP FIRST!
pg_dump -U postgres kosh_db > kosh_backup_$(date +%Y%m%d).sql

# Run reconcile
psql -U postgres -d kosh_db -f bug_memory/fix-bidirectional-reconcile.sql

# Review results:
# - Shows rows updated by direction (DOWNWARD/UPWARD)
# - Shows top 20 corrections with details
# - Verifies remaining discrepancies
```

**Expected output:**
```
 direction | rows_updated | total_units_corrected
-----------+--------------+----------------------
 DOWNWARD  |          12  |                3,450
 UPWARD    |          28  |                6,720
(2 rows)
```

**Rollback if needed:**
```sql
-- Restore from audit log:
BEGIN;
UPDATE pcb_inventory."tblWhse_Inventory" w
SET onhandqty = a.prior_qty
FROM pcb_inventory."tblReconcileAudit" a
WHERE w.pcn::text = a.pcn
  AND a.source = 'bidirectional_reconcile'
  AND a.reconciled_at >= '2026-06-25 12:00:00';  -- Adjust timestamp
COMMIT;
```

### Fix #2: Enhanced Monitoring (Permanent)

**File:** `fix-app-py-bidirectional-monitoring.patch`

**What it does:**
- Updates nightly integrity check to monitor BOTH directions
- Adds `stored_below_ledger` column to tblIntegrityCheckLog
- Logs warnings for warehouse < ledger cases

**How to apply:**

1. Edit `app.py` @ L3506-3520 (see patch file for exact changes)
2. Add stored_below_ledger monitoring query
3. Update table schema (add column)
4. Update INSERT statement
5. Update warning condition

**After applying:**
```bash
# Restart app to pick up changes
sudo systemctl restart kosh

# Check logs:
tail -f /var/log/kosh/app.log | grep "INTEGRITY CHECK"
```

**Expected log:**
```
INFO: Nightly integrity check: all clear
# OR if issues found:
WARNING: INTEGRITY CHECK regression: double_count=0 negatives=0 
         collisions=0 above_ledger=0 below_ledger=28
```

### Fix #3: Diagnostic Dashboard (Optional)

Add to admin page to show real-time discrepancies:

```python
# In admin route:
@app.route('/admin/inventory_health')
@login_required
def inventory_health():
    # Run diagnostic query
    # Show:
    # - PHANTOM_STOCK count
    # - MISSING_STOCK count
    # - Top discrepancies by PCN
    # - Trend over time (from tblIntegrityCheckLog)
```

## 🎯 Recommended Execution Plan

### Phase 1: Immediate Fix (Today)

1. **Backup database**
2. **Run diagnostic** to quantify the issue:
   ```bash
   psql -U postgres -d kosh_db -f bug_memory/diagnostic-warehouse-vs-history-discrepancies.sql
   ```
3. **Run bidirectional reconcile** to fix current discrepancies:
   ```bash
   psql -U postgres -d kosh_db -f bug_memory/fix-bidirectional-reconcile.sql
   ```
4. **Verify fix** - re-run diagnostic, should show minimal discrepancies

### Phase 2: Permanent Monitoring (This Week)

1. **Apply app.py patch** for bidirectional monitoring
2. **Restart app**
3. **Monitor nightly integrity logs** for 7 days
4. **If stored_below_ledger appears:**
   - Investigate which operations are failing to update Warehouse
   - Check restock_pcb/stock_pcb operations
   - May need to fix those operations

### Phase 3: Root Cause Analysis (Ongoing)

If upward discrepancies keep appearing:

**Investigate:**
1. Which transaction types cause warehouse < ledger?
2. Are RESTOCK/STOCK operations failing to update Warehouse?
3. Are PICK operations over-subtracting?
4. Is mfg_qty being reconciled correctly?

**Check transaction log for affected PCNs:**
```sql
-- For a specific PCN with warehouse < ledger:
SELECT 
    tran_time, trantype, tranqty, reversed,
    loc_from, loc_to,
    created_at
FROM pcb_inventory."tblTransaction"
WHERE pcn = '12345'  -- Replace with affected PCN
ORDER BY id DESC
LIMIT 50;
```

**Compare to Warehouse value:**
```sql
SELECT pcn, item, onhandqty, mfg_qty, loc_to
FROM pcb_inventory."tblWhse_Inventory"
WHERE pcn = '12345';
```

## 📊 Success Metrics

**Before fix:**
- Warehouse ≠ PCN History for many PCNs
- User: "PCN History more accurate"
- stored_below_ledger > 0 (if we were monitoring)

**After fix:**
- Warehouse = PCN History for all PCNs (± 5 units tolerance)
- stored_below_ledger = 0 in nightly checks
- User confidence restored

## ⚠️ Important Notes

**Why not just remove the downward-only guard?**
- Removing it could allow Bug #4 (phantom doubling) to return
- Better to:
  1. Keep guard in automatic reconcile (prevents regression)
  2. Add bidirectional monitoring (detects issues)
  3. Manual reconcile when needed (fixes verified issues)

**When to run manual reconcile:**
- After detecting stored_below_ledger > 0 in nightly checks
- After bulk imports or data migrations
- When users report Warehouse < PCN History discrepancies
- Monthly as maintenance (preventive)

**Future improvement:**
Consider making reconcile fully bidirectional with smart guards:
- If ledger > warehouse AND recent RESTOCK exists → apply upward correction
- If ledger > warehouse AND no recent activity → flag for review
- Keep phantom protection but allow verified upward corrections

## 📁 Files Created

1. ✅ `diagnostic-warehouse-vs-history-discrepancies.sql` - Detect issues
2. ✅ `fix-bidirectional-reconcile.sql` - Fix current issues
3. ✅ `fix-app-py-bidirectional-monitoring.patch` - Prevent future issues
4. ✅ `WAREHOUSE-vs-HISTORY-DISCREPANCY-CHECK.md` - Investigation guide
5. ✅ `FIX-WAREHOUSE-HISTORY-DISCREPANCIES.md` - This file

**All committed to GitHub and ready to use!**
