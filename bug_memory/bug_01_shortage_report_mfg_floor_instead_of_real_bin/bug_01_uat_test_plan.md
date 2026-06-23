# Bug #1 - UAT Test Plan
## Shortage Report Bin-First Location Selection

**Test Date:** ___________
**Tester:** ___________
**Environment:** ☐ Staging  ☐ Production
**Build/Commit:** ___________

---

## Pre-Test Setup

### Database State Verification

Run this query to identify test candidates:

```sql
-- Find items with both bin stock AND floor-only PCNs
-- (These are candidates for Bug #1 scenario)
WITH inv AS (
    SELECT
        UPPER(TRIM(item)) as item_normalized,
        item,
        pcn,
        loc_to,
        onhandqty,
        mfg_qty,
        (onhandqty + mfg_qty) as total_qty
    FROM tblWhse_Inventory
    WHERE onhandqty > 0 OR mfg_qty > 0
),
bin_stock AS (
    SELECT item_normalized, MAX(onhandqty) as max_bin
    FROM inv WHERE onhandqty > 0
    GROUP BY item_normalized
),
floor_only AS (
    SELECT item_normalized, MAX(mfg_qty) as max_floor
    FROM inv WHERE onhandqty = 0 AND mfg_qty > 0
    GROUP BY item_normalized
)
SELECT
    b.item_normalized,
    b.max_bin as bin_qty,
    f.max_floor as floor_qty
FROM bin_stock b
JOIN floor_only f ON b.item_normalized = f.item_normalized
WHERE f.max_floor > b.max_bin  -- Floor qty exceeds bin qty (bug scenario)
ORDER BY (f.max_floor - b.max_bin) DESC
LIMIT 20;
```

**Expected:** At least 5 items with this pattern
**Actual:** ___________
**Status:** ☐ Pass ☐ Fail

---

## Test Case 1: Reproduce Original Bug #1 Scenario

**Objective:** Verify the exact scenario from job 5455M line 3 is fixed

### Step 1: Find Test Item
```sql
-- Find an item with bin stock that would have shown MFG Floor before the fix
SELECT
    item,
    pcn,
    loc_to,
    onhandqty as bin_qty,
    mfg_qty as floor_qty,
    (onhandqty + mfg_qty) as total
FROM tblWhse_Inventory
WHERE item = 'TEST_ITEM_HERE'  -- Replace with actual test item
ORDER BY pcn;
```

**Record your test item:**
- Item Number: ___________
- Bin PCN: ___________
- Bin Location: ___________
- Bin Qty: ___________
- Floor PCN: ___________
- Floor Qty: ___________

### Step 2: Create Test Job BOM
```sql
-- Insert test BOM line
INSERT INTO tblBOM (job_number, line_number, item_number, qty, description)
VALUES ('UAT-TEST-001', 1, 'YOUR_ITEM_HERE', 50, 'UAT Test for Bug #1');
```

**Expected:** BOM line created
**Actual:** ___________
**Status:** ☐ Pass ☐ Fail

### Step 3: Generate Shortage Report

**Action:** Navigate to Shortage Report → Enter Job Number: `UAT-TEST-001` → Generate

**Expected Results:**
- ✓ Report displays successfully
- ✓ Line 1 shows the **bin location** (e.g., "2204207")
- ✓ Line 1 does **NOT** show "MFG Floor"
- ✓ On-hand quantity shows bin + floor total
- ✓ Location column clearly indicates the bin

**Actual Results:**
- Location shown: ___________
- On-hand bin: ___________
- On-hand floor: ___________
- Total on-hand: ___________

**Status:** ☐ Pass ☐ Fail

**Screenshot:** ☐ Attached

### Step 4: Verify Picker Can Use Location

**Action:** Physically verify (or simulate) that the displayed bin location contains stock

**Expected:** Bin location shown in report has pickable stock
**Actual:** ___________
**Status:** ☐ Pass ☐ Fail

---

## Test Case 2: Floor-Only Items Show MFG Floor

**Objective:** Items with ONLY floor stock should still show "MFG Floor"

### Step 1: Find Floor-Only Item
```sql
SELECT item, pcn, mfg_qty
FROM tblWhse_Inventory
WHERE onhandqty = 0 AND mfg_qty > 0
LIMIT 5;
```

**Test item:** ___________
**Floor qty:** ___________

### Step 2: Add to Test BOM
```sql
INSERT INTO tblBOM (job_number, line_number, item_number, qty)
VALUES ('UAT-TEST-001', 2, 'YOUR_FLOOR_ITEM', 10);
```

### Step 3: Regenerate Shortage Report

**Expected Results:**
- ✓ Line 2 shows "MFG Floor" as location
- ✓ On-hand bin = 0
- ✓ On-hand floor = (actual floor qty)

**Actual Results:**
- Location: ___________
- On-hand bin: ___________
- On-hand floor: ___________

**Status:** ☐ Pass ☐ Fail

---

## Test Case 3: Multiple Bins - Highest Quantity Wins

**Objective:** When multiple bins exist, highest bin qty location should be shown

### Step 1: Find Item with Multiple Bins
```sql
SELECT item, pcn, loc_to, onhandqty
FROM tblWhse_Inventory
WHERE item IN (
    SELECT item
    FROM tblWhse_Inventory
    WHERE onhandqty > 0
    GROUP BY item
    HAVING COUNT(*) > 1
)
ORDER BY item, onhandqty DESC;
```

**Test item:** ___________

| PCN | Location | Bin Qty |
|-----|----------|---------|
| ___ | ________ | _______ |
| ___ | ________ | _______ |
| ___ | ________ | _______ |

**Highest bin qty location:** ___________

### Step 2: Add to BOM and Generate Report

**Expected:** Report shows the location with **highest bin qty**
**Actual:** ___________
**Status:** ☐ Pass ☐ Fail

---

## Test Case 4: Case-Insensitive Item Matching

**Objective:** BOM item numbers should match inventory regardless of case

### Step 1: Verify Case Mismatch Exists
```sql
-- Check if inventory has mixed case items
SELECT item, COUNT(*)
FROM tblWhse_Inventory
WHERE item != UPPER(item)
GROUP BY item
LIMIT 5;
```

**Test item (lowercase):** ___________

### Step 2: Insert BOM with Uppercase
```sql
INSERT INTO tblBOM (job_number, line_number, item_number, qty)
VALUES ('UAT-TEST-001', 3, UPPER('your_lowercase_item'), 25);
```

### Step 3: Generate Report

**Expected:** Item matched case-insensitively, location shown
**Actual:** ___________
**Status:** ☐ Pass ☐ Fail

---

## Test Case 5: Item Number Search - Exact vs Prefix

**Objective:** Warehouse Inventory search should prioritize exact match, fall back to prefix

### Step 1: Search Exact Match

**Action:** Navigate to Warehouse Inventory → Search Item: `6779ML-97` (exact)

**Expected:**
- ✓ Returns exact match first
- ✓ Bin location displayed correctly

**Actual:** ___________
**Status:** ☐ Pass ☐ Fail

### Step 2: Search Prefix

**Action:** Search Item: `6779` (prefix)

**Expected:**
- ✓ Returns all items starting with "6779"
- ✓ Includes `6779ML-97`, `6779ML-98`, etc.

**Actual count:** ___________
**Status:** ☐ Pass ☐ Fail

---

## Test Case 6: 8-Digit Bin Numbers

**Objective:** 8-digit bin locations should be supported (related to Bug #5)

### Step 1: Find 8-Digit Bin
```sql
SELECT item, pcn, loc_to, onhandqty
FROM tblWhse_Inventory
WHERE LENGTH(loc_to) >= 8
    AND loc_to ~ '^[0-9]{8,}$'
    AND onhandqty > 0
LIMIT 5;
```

**Test item:** ___________
**8-digit bin:** ___________

### Step 2: Add to BOM and Generate Report

**Expected:** 8-digit bin location displayed correctly (not truncated)
**Actual:** ___________
**Status:** ☐ Pass ☐ Fail

---

## Test Case 7: Real Production Job Test

**Objective:** Test with a real production job from the original bug report

### Step 1: Use Original Job 5455M

**Action:** Generate shortage report for job `5455M` (original bug job)

**Expected Results:**
- ✓ All lines show correct bin locations
- ✓ No lines incorrectly show "MFG Floor" when bin stock exists
- ✓ Picker locations are actionable

**Lines verified:** ___________
**Issues found:** ___________
**Status:** ☐ Pass ☐ Fail

---

## Test Case 8: Shortage Report Export (Excel)

**Objective:** Excel export should include correct locations

### Step 1: Generate and Export

**Action:** Generate shortage report for `UAT-TEST-001` → Click "Export to Excel"

### Step 2: Verify Excel Contents

**Expected:**
- ✓ Location column shows bin locations (not MFG Floor for bin stock)
- ✓ All test items from above test cases present
- ✓ Formatting intact

**Status:** ☐ Pass ☐ Fail

---

## Test Case 9: Performance - Large Job

**Objective:** Report generation should complete in reasonable time

### Step 1: Select Large Job
```sql
-- Find a job with 50+ BOM lines
SELECT job_number, COUNT(*) as line_count
FROM tblBOM
GROUP BY job_number
HAVING COUNT(*) >= 50
ORDER BY COUNT(*) DESC
LIMIT 5;
```

**Test job:** ___________
**Line count:** ___________

### Step 2: Generate Report and Time

**Action:** Generate shortage report → Record time

**Expected:** < 10 seconds
**Actual:** ___________
**Status:** ☐ Pass ☐ Fail

---

## Test Case 10: Concurrent Access

**Objective:** Multiple users generating reports should not interfere

### Step 1: Multi-User Test

**Action:**
1. User A: Generate report for Job X
2. User B (simultaneously): Generate report for Job Y
3. User A: Verify results
4. User B: Verify results

**Expected:** Both reports correct, no cross-contamination
**Actual:** ___________
**Status:** ☐ Pass ☐ Fail

---

## Verification SQL Queries

### Query 1: Count Items Fixed by Bug #1 Patch
```sql
-- How many items now show bin instead of floor?
WITH old_logic AS (
    SELECT
        UPPER(item) as item,
        pcn,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(item)
            ORDER BY (onhandqty + mfg_qty) DESC  -- Old: total qty
        ) as rank
    FROM tblWhse_Inventory
    WHERE onhandqty > 0 OR mfg_qty > 0
),
new_logic AS (
    SELECT
        UPPER(item) as item,
        pcn,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(item)
            ORDER BY (onhandqty > 0) DESC, onhandqty DESC, mfg_qty DESC  -- New: bin first
        ) as rank
    FROM tblWhse_Inventory
    WHERE onhandqty > 0 OR mfg_qty > 0
)
SELECT COUNT(*) as items_corrected
FROM old_logic o
JOIN new_logic n ON o.item = n.item AND o.rank = 1 AND n.rank = 1
WHERE o.pcn != n.pcn;
```

**Expected:** > 0 (at least 1,492 per bug report)
**Actual:** ___________

### Query 2: Verify No Bin Stock Shows as MFG Floor
```sql
-- Should return 0 rows (no bin stock incorrectly showing as floor)
WITH ranked AS (
    SELECT
        item, pcn, loc_to, onhandqty, mfg_qty,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(item)
            ORDER BY (onhandqty > 0) DESC, onhandqty DESC, mfg_qty DESC
        ) as rank
    FROM tblWhse_Inventory
    WHERE onhandqty > 0 OR mfg_qty > 0
)
SELECT item, pcn, loc_to, onhandqty, mfg_qty
FROM ranked
WHERE rank = 1
    AND onhandqty = 0  -- No bin stock
    AND EXISTS (  -- But other PCNs have bin stock
        SELECT 1 FROM tblWhse_Inventory w2
        WHERE UPPER(w2.item) = UPPER(ranked.item)
            AND w2.onhandqty > 0
    );
```

**Expected:** 0 rows
**Actual:** ___________

---

## Post-Test Cleanup

```sql
-- Remove UAT test data
DELETE FROM tblBOM WHERE job_number = 'UAT-TEST-001';
-- Add any other test data cleanup here
```

**Status:** ☐ Completed

---

## Sign-Off

### Test Results Summary

| Test Case | Status | Notes |
|-----------|--------|-------|
| TC1: Bug #1 Scenario | ☐ Pass ☐ Fail | _____________ |
| TC2: Floor-Only Items | ☐ Pass ☐ Fail | _____________ |
| TC3: Multiple Bins | ☐ Pass ☐ Fail | _____________ |
| TC4: Case-Insensitive | ☐ Pass ☐ Fail | _____________ |
| TC5: Search Exact/Prefix | ☐ Pass ☐ Fail | _____________ |
| TC6: 8-Digit Bins | ☐ Pass ☐ Fail | _____________ |
| TC7: Real Job 5455M | ☐ Pass ☐ Fail | _____________ |
| TC8: Excel Export | ☐ Pass ☐ Fail | _____________ |
| TC9: Performance | ☐ Pass ☐ Fail | _____________ |
| TC10: Concurrent Access | ☐ Pass ☐ Fail | _____________ |

### Overall Test Status

☐ **PASS** - All test cases passed, ready for production
☐ **FAIL** - Issues found, requires fixes
☐ **CONDITIONAL PASS** - Minor issues, acceptable for deployment

### Tester Sign-Off

**Name:** ___________
**Date:** ___________
**Signature:** ___________

### Business User Sign-Off (Theresa / Warehouse Manager)

**Name:** ___________
**Date:** ___________
**Signature:** ___________
**Comments:** ___________

---

## Issues Found During UAT

| Issue # | Description | Severity | Status |
|---------|-------------|----------|--------|
| 1 | ___________ | ☐ High ☐ Med ☐ Low | ☐ Open ☐ Fixed |
| 2 | ___________ | ☐ High ☐ Med ☐ Low | ☐ Open ☐ Fixed |
| 3 | ___________ | ☐ High ☐ Med ☐ Low | ☐ Open ☐ Fixed |

**Next Steps:** ___________
