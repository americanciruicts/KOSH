-- ============================================================================
-- Bug #2 Verification SQL Queries
-- On-Hand Reconcile Wiped Fresh Restocks to 0
-- ============================================================================
-- Date: 06/22/2026
-- Purpose: Validate the Bug #2 fix in production/staging environments
-- ============================================================================

-- ----------------------------------------------------------------------------
-- QUERY 1: Identify protected rows (latest event = RESTOCK/STOCK)
-- ----------------------------------------------------------------------------
-- Shows rows that are now protected from being zeroed by reconcile
-- Expected: Should show rows with recent restocks

WITH latest_txn AS (
    SELECT DISTINCT ON (pcn, LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')))
        pcn,
        LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) as mpn_key,
        trantype,
        tran_time,
        tranqty
    FROM pcb_inventory.tblTransaction
    WHERE trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
        AND reversed = false
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
    lt.tranqty as latest_qty,
    CASE
        WHEN lt.trantype IN ('RESTOCK', 'STOCK') THEN '🛡️ PROTECTED (Bug #2 fix)'
        WHEN lt.trantype IN ('PICK', 'PURGE') THEN 'NORMAL (can be lowered)'
        ELSE 'OTHER'
    END as protection_status
FROM pcb_inventory."tblWhse_Inventory" w
JOIN latest_txn lt
    ON w.pcn::text = lt.pcn
    AND LOWER(TRANSLATE(COALESCE(w.mpn,''), '-# ./', '')) = lt.mpn_key
WHERE w.onhandqty > 0
    AND lt.trantype IN ('RESTOCK', 'STOCK')
ORDER BY lt.tran_time DESC
LIMIT 50;

-- Expected: Shows recent restocks that are protected
-- These rows will NOT be lowered by reconcile even if ledger replay = 0


-- ----------------------------------------------------------------------------
-- QUERY 2: Find parts with incomplete ledger (Bug #2 candidates)
-- ----------------------------------------------------------------------------
-- Parts where ledger replay would go negative (incomplete history)
-- These are the parts most vulnerable to Bug #2

WITH ledger_replay AS (
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
        ) as ledger_net,
        COUNT(*) FILTER (WHERE trantype IN ('PICK', 'PURGE', 'SCRA')) as pick_count,
        COUNT(*) FILTER (WHERE trantype IN ('RESTOCK', 'STOCK', 'INDF')) as stock_count
    FROM pcb_inventory.tblTransaction
    WHERE reversed = false
        AND trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF')
    GROUP BY pcn, LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', ''))
)
SELECT
    lr.pcn,
    w.item,
    w.mpn,
    w.onhandqty as warehouse_qty,
    lr.ledger_net as ledger_computed,
    GREATEST(0, lr.ledger_net) as ledger_clamped,
    lr.pick_count,
    lr.stock_count,
    CASE
        WHEN lr.ledger_net < 0 THEN '⚠️ INCOMPLETE LEDGER (more picks than stock-ins)'
        WHEN lr.ledger_net < w.onhandqty THEN 'Ledger lower than warehouse'
        ELSE 'OK'
    END as status
FROM ledger_replay lr
JOIN pcb_inventory."tblWhse_Inventory" w
    ON lr.pcn = w.pcn::text
    AND lr.mpn_key = LOWER(TRANSLATE(COALESCE(w.mpn,''), '-# ./', ''))
WHERE lr.ledger_net < 0  -- Incomplete ledger (would go negative)
    OR lr.ledger_net < w.onhandqty  -- Ledger suggests lowering
ORDER BY ABS(lr.ledger_net - w.onhandqty) DESC
LIMIT 100;

-- Expected: Shows parts with incomplete ledger history
-- Without Bug #2 fix, these parts' fresh restocks would be vulnerable to zeroing


-- ----------------------------------------------------------------------------
-- QUERY 3: Simulate Bug #2 scenario (would this row be protected?)
-- ----------------------------------------------------------------------------
-- Test a specific PCN to see if it would be protected

WITH pcn_to_test AS (
    SELECT 42137 as test_pcn  -- Change this to test different PCNs
),
latest_event AS (
    SELECT DISTINCT ON (t.pcn, LOWER(TRANSLATE(COALESCE(t.mpn,''), '-# ./', '')))
        t.pcn,
        t.mpn,
        t.trantype as last_type,
        t.tran_time,
        t.tranqty
    FROM pcb_inventory.tblTransaction t
    CROSS JOIN pcn_to_test p
    WHERE t.pcn::text = p.test_pcn::text
        AND t.reversed = false
        AND t.trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
    ORDER BY t.pcn,
             LOWER(TRANSLATE(COALESCE(t.mpn,''), '-# ./', '')),
             t.tran_time DESC NULLS LAST,
             t.id DESC
)
SELECT
    w.pcn,
    w.item,
    w.mpn,
    w.onhandqty as current_warehouse_qty,
    le.last_type,
    le.tran_time as last_event_time,
    le.tranqty as last_event_qty,
    CASE
        WHEN le.last_type IN ('RESTOCK', 'STOCK') THEN
            '✅ PROTECTED - Bug #2 fix prevents lowering this row'
        WHEN le.last_type IN ('PICK', 'PURGE', 'SCRA') THEN
            '⚠️ NOT PROTECTED - Can be lowered if ledger suggests'
        ELSE
            'OTHER - Check manually'
    END as protection_status
FROM pcb_inventory."tblWhse_Inventory" w
CROSS JOIN pcn_to_test p
LEFT JOIN latest_event le ON w.pcn::text = le.pcn::text
WHERE w.pcn::text = p.test_pcn::text;

-- Expected: Shows whether the test PCN would be protected
-- Change test_pcn value to test different parts


-- ----------------------------------------------------------------------------
-- QUERY 4: Recent restocks that would have been zeroed (without fix)
-- ----------------------------------------------------------------------------
-- Finds recent restocks on parts with incomplete ledgers
-- These are the "close calls" that Bug #2 fix saved

WITH recent_restocks AS (
    SELECT
        pcn,
        LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) as mpn_key,
        tran_time,
        tranqty,
        trantype
    FROM pcb_inventory.tblTransaction
    WHERE trantype IN ('RESTOCK', 'STOCK')
        AND tran_time >= CURRENT_DATE - INTERVAL '7 days'
        AND reversed = false
),
ledger_net AS (
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
        ) as net_qty
    FROM pcb_inventory.tblTransaction
    WHERE reversed = false
    GROUP BY pcn, LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', ''))
),
latest_event AS (
    SELECT DISTINCT ON (pcn, LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')))
        pcn,
        LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) as mpn_key,
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
    w.pcn,
    w.item,
    w.mpn,
    w.onhandqty as current_qty,
    rr.tran_time as restock_time,
    rr.tranqty as restock_qty,
    ln.net_qty as ledger_would_compute,
    GREATEST(0, ln.net_qty) as ledger_clamped,
    le.last_type,
    CASE
        WHEN ln.net_qty < w.onhandqty AND le.last_type IN ('RESTOCK', 'STOCK') THEN
            '🛡️ SAVED BY BUG #2 FIX'
        ELSE
            'Would not have been affected'
    END as outcome
FROM pcb_inventory."tblWhse_Inventory" w
JOIN recent_restocks rr
    ON w.pcn::text = rr.pcn
    AND LOWER(TRANSLATE(COALESCE(w.mpn,''), '-# ./', '')) = rr.mpn_key
JOIN ledger_net ln
    ON w.pcn::text = ln.pcn
    AND LOWER(TRANSLATE(COALESCE(w.mpn,''), '-# ./', '')) = ln.mpn_key
JOIN latest_event le
    ON w.pcn::text = le.pcn
    AND LOWER(TRANSLATE(COALESCE(w.mpn,''), '-# ./', '')) = le.mpn_key
WHERE ln.net_qty < w.onhandqty  -- Ledger would suggest lowering
    AND le.last_type IN ('RESTOCK', 'STOCK')  -- Protected by fix
ORDER BY rr.tran_time DESC
LIMIT 50;

-- Expected: Shows recent restocks that would have been zeroed without the fix
-- These are real-world examples of Bug #2 being prevented


-- ----------------------------------------------------------------------------
-- QUERY 5: Verify the backfill (62 rows restored)
-- ----------------------------------------------------------------------------
-- Check if the 62 backfilled rows are in good state

-- NOTE: This query assumes there's an audit trail table or log
-- If no audit table exists, this will need to be adapted

SELECT
    'Backfill verification query' as note,
    'Requires audit trail table or manual verification' as status;

-- To manually verify backfilled rows, compare:
-- 1. Current warehouse onhandqty
-- 2. Latest RESTOCK/STOCK transaction qty
-- 3. PCN History computed balance

-- Example manual verification for one PCN:
/*
WITH history_balance AS (
    SELECT
        pcn,
        SUM(
            CASE
                WHEN trantype IN ('RESTOCK', 'STOCK', 'INDF') THEN tranqty::int
                WHEN trantype IN ('PICK', 'PURGE', 'SCRA') THEN -tranqty::int
                ELSE 0
            END
        ) as history_qty
    FROM pcb_inventory.tblTransaction
    WHERE pcn::text = '42137'
        AND reversed = false
        AND tranqty ~ '^-?[0-9]+$'
    GROUP BY pcn
)
SELECT
    w.pcn,
    w.onhandqty as warehouse_qty,
    hb.history_qty,
    CASE
        WHEN w.onhandqty = hb.history_qty THEN '✅ MATCH'
        ELSE '⚠️ MISMATCH'
    END as status
FROM pcb_inventory."tblWhse_Inventory" w
JOIN history_balance hb ON w.pcn::text = hb.pcn::text
WHERE w.pcn::text = '42137';
*/


-- ----------------------------------------------------------------------------
-- QUERY 6: Count rows protected vs correctable
-- ----------------------------------------------------------------------------
-- Summary statistics for Bug #2 fix impact

WITH latest_events AS (
    SELECT DISTINCT ON (pcn, LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')))
        pcn,
        LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) as mpn_key,
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
    COUNT(*) FILTER (WHERE le.last_type IN ('RESTOCK', 'STOCK')) as protected_rows,
    COUNT(*) FILTER (WHERE le.last_type IN ('PICK', 'PURGE', 'SCRA')) as correctable_rows,
    COUNT(*) FILTER (WHERE le.last_type NOT IN ('RESTOCK', 'STOCK', 'PICK', 'PURGE', 'SCRA')) as other_rows,
    COUNT(*) as total_active_rows
FROM pcb_inventory."tblWhse_Inventory" w
LEFT JOIN latest_events le
    ON w.pcn::text = le.pcn
    AND LOWER(TRANSLATE(COALESCE(w.mpn,''), '-# ./', '')) = le.mpn_key
WHERE w.onhandqty > 0;

-- Expected output:
-- protected_rows: Rows whose latest event is RESTOCK/STOCK (protected by Bug #2 fix)
-- correctable_rows: Rows whose latest event is PICK/PURGE (can still be lowered)
-- other_rows: Other transaction types
-- total_active_rows: All rows with stock


-- ----------------------------------------------------------------------------
-- QUERY 7: Find potential future Bug #2 scenarios
-- ----------------------------------------------------------------------------
-- Parts that currently have stock but incomplete ledger
-- These would be vulnerable to Bug #2 if restocked

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
        ) as net_qty
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
    ) < 0  -- Negative ledger (incomplete)
)
SELECT
    w.pcn,
    w.item,
    w.mpn,
    w.onhandqty,
    ln.net_qty as ledger_net,
    ABS(ln.net_qty) as shortage_in_ledger,
    '⚠️ If restocked, would need Bug #2 protection' as note
FROM pcb_inventory."tblWhse_Inventory" w
JOIN ledger_net ln
    ON w.pcn::text = ln.pcn
    AND LOWER(TRANSLATE(COALESCE(w.mpn,''), '-# ./', '')) = ln.mpn_key
WHERE w.onhandqty > 0
ORDER BY ABS(ln.net_qty) DESC
LIMIT 100;

-- Expected: Parts with incomplete ledgers that are actively stocked
-- Any future restock on these parts will be protected by Bug #2 fix


-- ============================================================================
-- END OF VERIFICATION QUERIES
-- ============================================================================
-- Run these queries after deploying Bug #2 fix to validate correctness
-- Save output for audit trail
-- ============================================================================
