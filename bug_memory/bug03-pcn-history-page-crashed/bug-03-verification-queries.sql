-- ============================================================================
-- Bug #3 Verification SQL Queries
-- PCN History Page Crashed for Every Real PCN
-- ============================================================================
-- Date: 06/18/2026
-- Purpose: Validate Bug #3 fix (cursor type mismatch)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- QUERY 1: Test the fix - Anchor query with RealDictCursor
-- ----------------------------------------------------------------------------
-- This query simulates what PCN History does
-- With the fix, this should return a result we can access by 'total'

DO $$
DECLARE
    test_result RECORD;
    anchor_value INTEGER;
BEGIN
    -- Simulate the anchor query
    SELECT COALESCE(SUM(onhandqty), 0) AS total
    INTO test_result
    FROM pcb_inventory."tblWhse_Inventory"
    WHERE pcn::text = '42137';  -- Test with a real PCN

    -- Access by alias 'total' (the fix)
    anchor_value := test_result.total;

    RAISE NOTICE 'Anchor value for PCN 42137: %', anchor_value;
    RAISE NOTICE '✅ Query works - can access result by alias';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE '❌ Query failed: %', SQLERRM;
END $$;

-- Expected: Should print anchor value successfully
-- Before fix: Would fail with KeyError in Python (can't test in SQL)


-- ----------------------------------------------------------------------------
-- QUERY 2: Verify column alias exists in query
-- ----------------------------------------------------------------------------
-- Check that the query has proper alias

SELECT
    'Checking PCN anchor query has alias' as test_name,
    'Should have AS total in query' as expected;

-- To verify in code, check:
-- SELECT COALESCE(SUM(onhandqty), 0) AS total  -- ✅ Has alias
-- NOT: SELECT COALESCE(SUM(onhandqty), 0)      -- ❌ No alias


-- ----------------------------------------------------------------------------
-- QUERY 3: Test with various PCNs
-- ----------------------------------------------------------------------------
-- Verify anchor calculation works for different PCNs

WITH test_pcns AS (
    SELECT pcn::text as test_pcn
    FROM pcb_inventory."tblWhse_Inventory"
    WHERE onhandqty > 0
    LIMIT 10
)
SELECT
    tp.test_pcn,
    COALESCE(SUM(w.onhandqty), 0) AS total
FROM test_pcns tp
LEFT JOIN pcb_inventory."tblWhse_Inventory" w
    ON w.pcn::text = tp.test_pcn
GROUP BY tp.test_pcn
ORDER BY tp.test_pcn;

-- Expected: Should return total for each PCN
-- This is what the fixed code does


-- ----------------------------------------------------------------------------
-- QUERY 4: Test empty result (PCN with no inventory)
-- ----------------------------------------------------------------------------
-- Verify the fix handles NULL/empty results

SELECT COALESCE(SUM(onhandqty), 0) AS total
FROM pcb_inventory."tblWhse_Inventory"
WHERE pcn::text = 'NONEXISTENT-PCN-99999';

-- Expected: total = 0 (COALESCE handles NULL)
-- The fixed code has safety: `if anchor_row and anchor_row.get('total') is not None else 0`


-- ----------------------------------------------------------------------------
-- QUERY 5: Find PCNs suitable for testing
-- ----------------------------------------------------------------------------
-- Get real PCNs to use for manual testing

SELECT
    pcn,
    item,
    mpn,
    onhandqty,
    mfg_qty,
    (onhandqty + mfg_qty) as total_qty
FROM pcb_inventory."tblWhse_Inventory"
WHERE onhandqty > 0
    OR mfg_qty > 0
ORDER BY pcn
LIMIT 20;

-- Use these PCNs to test PCN History page manually
-- Before fix: Any of these would crash the page
-- After fix: All should work


-- ----------------------------------------------------------------------------
-- QUERY 6: Verify transaction history exists for test PCNs
-- ----------------------------------------------------------------------------
-- Check that test PCNs have transaction history to display

WITH pcn_txn_count AS (
    SELECT
        pcn,
        COUNT(*) as txn_count,
        MIN(tran_time) as first_txn,
        MAX(tran_time) as last_txn
    FROM pcb_inventory.tblTransaction
    WHERE reversed = false
    GROUP BY pcn
)
SELECT
    w.pcn,
    w.item,
    w.onhandqty,
    tc.txn_count,
    tc.first_txn,
    tc.last_txn
FROM pcb_inventory."tblWhse_Inventory" w
JOIN pcn_txn_count tc ON w.pcn::text = tc.pcn
WHERE w.onhandqty > 0
ORDER BY tc.txn_count DESC
LIMIT 10;

-- These PCNs are good for manual testing (have history to display)


-- ----------------------------------------------------------------------------
-- QUERY 7: Code pattern audit - Find similar potential bugs
-- ----------------------------------------------------------------------------
-- Search for other queries that might have the same issue
-- (This is a manual code review helper)

SELECT
    'Audit other queries for missing aliases' as note,
    'Search code for: SELECT.*SUM|COUNT|AVG without AS alias' as action,
    'Check if using RealDictCursor and accessing by index' as check;

-- Manual audit commands:
-- grep -r "SELECT.*SUM\|COUNT\|AVG" app.py | grep -v " AS "
-- grep -r "RealDictCursor" app.py
-- grep -r "fetchone()\[" app.py


-- ============================================================================
-- MANUAL TEST PROCEDURE
-- ============================================================================

-- Test Case 1: PCN with inventory
-- 1. Pick a PCN from Query 5 above
-- 2. Navigate to PCN History page
-- 3. Enter PCN and click Search
-- Expected: Transaction history displays (no crash)

-- Test Case 2: PCN with no inventory
-- 1. Use PCN 'NONEXISTENT-99999'
-- 2. Navigate to PCN History page
-- 3. Enter PCN and click Search
-- Expected: Empty history or "No transactions" message (no crash)

-- Test Case 3: PCN with lots of history
-- 1. Pick top PCN from Query 6 (most transactions)
-- 2. Navigate to PCN History page
-- 3. Enter PCN and click Search
-- Expected: Full history displays, scrollable (no crash)

-- ============================================================================
-- END OF VERIFICATION QUERIES
-- ============================================================================
