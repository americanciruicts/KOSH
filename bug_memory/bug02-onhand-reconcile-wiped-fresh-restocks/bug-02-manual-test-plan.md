# Bug #2 - Manual Test Plan
## On-Hand Reconcile Fresh Restock Protection

**Test Date:** ___________  
**Tester:** ___________  
**Environment:** ☐ Staging  ☐ Production  
**Build/Commit:** ___________

---

## Pre-Test Setup

### Identify Test Candidate PCN

Find a part with incomplete ledger history (more picks than stock-ins):

```sql
WITH ledger_net AS (
    SELECT
        pcn,
        LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) as mpn_key,
        SUM(
            CASE
                WHEN trantype IN ('RESTOCK', 'STOCK', 'INDF') THEN
                    CASE WHEN tranqty ~ '^-?[0-9]+$' THEN tranqty::int ELSE 0 END
                WHEN trantype IN ('PICK', 'PURGE', 'SCRA') THEN
                    -ABS(CASE WHEN tranqty ~ '^-?[0-9]+$' THEN tranqty::int ELSE 0 END)
                ELSE 0
            END
        ) as net_qty,
        COUNT(*) FILTER (WHERE trantype IN ('PICK', 'PURGE', 'SCRA')) as pick_count,
        COUNT(*) FILTER (WHERE trantype IN ('RESTOCK', 'STOCK')) as stock_count
    FROM pcb_inventory.tblTransaction
    WHERE reversed = false
    GROUP BY pcn, LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', ''))
    HAVING SUM(
        CASE
            WHEN trantype IN ('RESTOCK', 'STOCK', 'INDF') THEN
                CASE WHEN tranqty ~ '^-?[0-9]+$' THEN tranqty::int ELSE 0 END
            WHEN trantype IN ('PICK', 'PURGE', 'SCRA') THEN
                -ABS(CASE WHEN tranqty ~ '^-?[0-9]+$' THEN tranqty::int ELSE 0 END)
            ELSE 0
        END
    ) < 0  -- Incomplete ledger
)
SELECT
    pcn,
    net_qty as ledger_would_compute,
    pick_count,
    stock_count,
    '⚠️ Vulnerable to Bug #2 if restocked' as note
FROM ledger_net
ORDER BY ABS(net_qty) DESC
LIMIT 10;
```

**Record your test PCN:** ___________  
**Ledger computed qty:** ___________  
**Pick count:** ___________  
**Stock count:** ___________

---

## Test Case 1: Fresh Restock Protection (Core Bug #2 Scenario)

**Objective:** Verify fresh restocks are NOT zeroed by reconcile

### Step 1: Record Current State

**Action:** Check current warehouse quantity for test PCN

```sql
SELECT
    pcn,
    item,
    mpn,
    onhandqty as current_warehouse_qty,
    loc_to
FROM pcb_inventory."tblWhse_Inventory"
WHERE pcn::text = 'YOUR_TEST_PCN';
```

**Current qty:** ___________  
**Status:** ☐ Pass ☐ Fail

### Step 2: Perform Fresh Restock

**Action:** Manually restock the part to a known quantity (e.g., 20 units)

1. Navigate to Restock page
2. Enter PCN: ___________
3. Enter quantity: **20**
4. Click "Restock"
5. Note the exact time: ___________

**Expected:** Success message, warehouse shows 20 units  
**Actual:** ___________  
**Status:** ☐ Pass ☐ Fail

### Step 3: Verify Latest Event is RESTOCK

```sql
WITH latest_event AS (
    SELECT DISTINCT ON (pcn, LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')))
        pcn,
        mpn,
        trantype AS last_type,
        tran_time
    FROM pcb_inventory.tblTransaction
    WHERE pcn::text = 'YOUR_TEST_PCN'
        AND reversed = false
        AND trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
    ORDER BY pcn,
             LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')),
             tran_time DESC NULLS LAST,
             id DESC
)
SELECT * FROM latest_event;
```

**Expected:** `last_type = 'RESTOCK'`  
**Actual:** ___________  
**Status:** ☐ Pass ☐ Fail

### Step 4: Wait for Reconcile or Trigger Manually

**Option A - Wait for scheduled reconcile:**
- Reconcile runs every 5 minutes
- Wait for next reconcile cycle
- Time waited: ___________

**Option B - Trigger manually (if you have access):**
```python
# Run reconcile function manually
# (Requires developer access)
```

**Reconcile completed at:** ___________  
**Status:** ☐ Pass ☐ Fail

### Step 5: Verify Quantity NOT Zeroed

**Action:** Check warehouse quantity after reconcile

```sql
SELECT
    pcn,
    item,
    mpn,
    onhandqty as warehouse_qty_after_reconcile,
    loc_to
FROM pcb_inventory."tblWhse_Inventory"
WHERE pcn::text = 'YOUR_TEST_PCN';
```

**CRITICAL CHECK:**  
**Expected:** onhandqty = **20** (NOT zeroed to 0!)  
**Actual:** ___________  
**Status:** ☐ Pass ☐ Fail

### Step 6: Verify PCN History Matches

**Action:** Compare warehouse qty with PCN History

```sql
-- Check PCN History computed balance
-- (Simplified - actual query may differ)
SELECT
    pcn,
    SUM(
        CASE
            WHEN trantype IN ('RESTOCK', 'STOCK', 'INDF') THEN tranqty::int
            WHEN trantype IN ('PICK', 'PURGE', 'SCRA') THEN -tranqty::int
            ELSE 0
        END
    ) as history_balance
FROM pcb_inventory.tblTransaction
WHERE pcn::text = 'YOUR_TEST_PCN'
    AND reversed = false
    AND tranqty ~ '^-?[0-9]+$'
GROUP BY pcn;
```

**Expected:** Warehouse qty = PCN History balance  
**Warehouse:** ___________  
**PCN History:** ___________  
**Status:** ☐ Pass ☐ Fail

---

## Test Case 2: Phantom Stock Can Be Lowered

**Objective:** Verify reconcile can still lower phantom-high stock (latest = PICK)

### Step 1: Find Part with Latest = PICK

```sql
WITH latest_event AS (
    SELECT DISTINCT ON (w.pcn, LOWER(TRANSLATE(COALESCE(w.mpn,''), '-# ./', '')))
        w.pcn,
        w.onhandqty,
        t.trantype AS last_type,
        t.tran_time
    FROM pcb_inventory."tblWhse_Inventory" w
    JOIN pcb_inventory.tblTransaction t
        ON t.pcn::text = w.pcn::text
    WHERE w.onhandqty > 0
        AND t.reversed = false
        AND t.trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
    ORDER BY w.pcn,
             LOWER(TRANSLATE(COALESCE(w.mpn,''), '-# ./', '')),
             t.tran_time DESC NULLS LAST,
             t.id DESC
)
SELECT pcn, onhandqty, last_type
FROM latest_event
WHERE last_type = 'PICK'
LIMIT 5;
```

**Test PCN:** ___________  
**Current qty:** ___________  
**Latest event:** ___________

### Step 2: Verify Reconcile Can Lower

**Action:** Wait for reconcile or trigger manually

**Expected:** If ledger suggests lower value, warehouse qty can be lowered  
**Actual:** ___________  
**Status:** ☐ Pass ☐ Fail

---

## Test Case 3: Sequential Restocks Protection

**Objective:** Multiple restocks in a row, latest should be protected

### Step 1: Perform First Restock

**Action:** Restock PCN to 10 units  
**Time:** ___________  
**Status:** ☐ Pass ☐ Fail

### Step 2: Perform Second Restock (Later)

**Action:** Restock same PCN to 15 units  
**Time:** ___________  
**Status:** ☐ Pass ☐ Fail

### Step 3: Verify Latest Event

```sql
-- Should show most recent RESTOCK as latest
```

**Expected:** latest_type = 'RESTOCK', latest qty = 15  
**Actual:** ___________  
**Status:** ☐ Pass ☐ Fail

### Step 4: Verify Protected After Reconcile

**Expected:** Qty remains 15 (not lowered)  
**Actual:** ___________  
**Status:** ☐ Pass ☐ Fail

---

## Test Case 4: Restock Then Pick (NOT Protected)

**Objective:** If pick happens after restock, should NOT be protected

### Step 1: Restock Part

**PCN:** ___________  
**Qty:** 30  
**Time:** ___________

### Step 2: Pick Some Units

**Action:** Create a pick transaction (or simulate via transaction log)  
**Qty picked:** 5  
**Time:** ___________

### Step 3: Verify Latest Event is PICK

**Expected:** latest_type = 'PICK' (not RESTOCK)  
**Actual:** ___________  
**Status:** ☐ Pass ☐ Fail

### Step 4: Verify NOT Protected

**Expected:** Reconcile CAN lower this (if ledger suggests)  
**Actual:** ___________  
**Status:** ☐ Pass ☐ Fail

---

## Test Case 5: Real-World Scenario (PCN 42137)

**Objective:** Test the exact scenario from the original bug report

### If PCN 42137 Exists:

1. Check current state:
   ```sql
   SELECT * FROM pcb_inventory."tblWhse_Inventory" WHERE pcn = '42137';
   ```
   **Current qty:** ___________

2. Check latest event:
   ```sql
   -- Use latest_event query
   ```
   **Latest type:** ___________

3. Check if backfilled:
   ```sql
   -- Check audit trail: restock_wipe_backfill_20260622
   ```
   **Backfilled?:** ☐ Yes ☐ No

**Status:** ☐ Pass ☐ Fail ☐ N/A

---

## Verification SQL (Post-Testing)

### Query 1: Count Protected vs Correctable Rows

```sql
WITH latest_events AS (
    SELECT DISTINCT ON (pcn, LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')))
        pcn,
        trantype as last_type
    FROM pcb_inventory.tblTransaction
    WHERE reversed = false
        AND trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
    ORDER BY pcn,
             LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')),
             tran_time DESC NULLS LAST,
             id DESC
)
SELECT
    COUNT(*) FILTER (WHERE last_type IN ('RESTOCK', 'STOCK')) as protected_rows,
    COUNT(*) FILTER (WHERE last_type IN ('PICK', 'PURGE', 'SCRA')) as correctable_rows,
    COUNT(*) as total_rows
FROM latest_events;
```

**Protected rows:** ___________  
**Correctable rows:** ___________  
**Total:** ___________

### Query 2: Find Recent Protected Restocks

```sql
-- Shows recent restocks that are protected
WITH recent_restocks AS (
    SELECT
        pcn,
        tran_time,
        tranqty
    FROM pcb_inventory.tblTransaction
    WHERE trantype IN ('RESTOCK', 'STOCK')
        AND tran_time >= CURRENT_DATE - INTERVAL '7 days'
        AND reversed = false
)
SELECT COUNT(*) as recent_protected_restocks
FROM recent_restocks;
```

**Recent protected restocks (7 days):** ___________

---

## Post-Test Checklist

- [ ] All test cases executed
- [ ] No fresh restocks were zeroed
- [ ] Phantom stock can still be lowered
- [ ] Sequential restocks handled correctly
- [ ] Restock-then-pick NOT protected (correct)
- [ ] Verification queries run successfully
- [ ] No errors in application logs
- [ ] PCN History = Warehouse Inventory consistency maintained

---

## Sign-Off

### Test Results Summary

| Test Case | Status | Notes |
|-----------|--------|-------|
| TC1: Fresh restock protection | ☐ Pass ☐ Fail | _____________ |
| TC2: Phantom stock lowerable | ☐ Pass ☐ Fail | _____________ |
| TC3: Sequential restocks | ☐ Pass ☐ Fail | _____________ |
| TC4: Restock-then-pick | ☐ Pass ☐ Fail | _____________ |
| TC5: PCN 42137 scenario | ☐ Pass ☐ Fail | _____________ |

### Overall Test Status

☐ **PASS** - All test cases passed, Bug #2 fix working correctly  
☐ **FAIL** - Issues found, requires investigation  
☐ **CONDITIONAL PASS** - Minor issues, acceptable for deployment

### Tester Sign-Off

**Name:** ___________  
**Date:** ___________  
**Signature:** ___________

### Developer Sign-Off

**Name:** ___________  
**Date:** ___________  
**Signature:** ___________

---

## Issues Found During Testing

| Issue # | Description | Severity | Status |
|---------|-------------|----------|--------|
| 1 | ___________ | ☐ High ☐ Med ☐ Low | ☐ Open ☐ Fixed |
| 2 | ___________ | ☐ High ☐ Med ☐ Low | ☐ Open ☐ Fixed |

**Next Steps:** ___________
