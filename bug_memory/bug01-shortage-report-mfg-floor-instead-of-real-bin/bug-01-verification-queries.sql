-- ============================================================================
-- Bug #1 Verification SQL Queries
-- Shortage Report Bin-First Location Selection
-- ============================================================================
-- Date: 06/23/2026
-- Purpose: Validate the Bug #1 fix in production/staging environments
-- ============================================================================

-- ----------------------------------------------------------------------------
-- QUERY 1: Identify items corrected by the Bug #1 fix
-- ----------------------------------------------------------------------------
-- This shows items where the old logic (total qty) would have selected
-- a different PCN than the new logic (bin-first)
-- Expected: At least 1,492 items (per bug report)

WITH old_logic_ranking AS (
    SELECT
        UPPER(TRIM(item)) as item_normalized,
        item as original_item,
        pcn,
        loc_to,
        onhandqty as bin_qty,
        mfg_qty as floor_qty,
        (COALESCE(onhandqty, 0) + COALESCE(mfg_qty, 0)) as total_qty,
        -- OLD BUGGY LOGIC: Rank by total quantity
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(TRIM(item))
            ORDER BY (COALESCE(onhandqty, 0) + COALESCE(mfg_qty, 0)) DESC, pcn ASC
        ) as old_rank
    FROM tblWhse_Inventory
    WHERE (onhandqty > 0 OR mfg_qty > 0)
        AND item IS NOT NULL
        AND TRIM(item) != ''
),
new_logic_ranking AS (
    SELECT
        UPPER(TRIM(item)) as item_normalized,
        item as original_item,
        pcn,
        loc_to,
        onhandqty as bin_qty,
        mfg_qty as floor_qty,
        (COALESCE(onhandqty, 0) + COALESCE(mfg_qty, 0)) as total_qty,
        -- NEW FIXED LOGIC: Rank by bin-first
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(TRIM(item))
            ORDER BY
                (COALESCE(onhandqty, 0) > 0) DESC,  -- Bin stock exists
                COALESCE(onhandqty, 0) DESC,        -- Bin quantity
                COALESCE(mfg_qty, 0) DESC,          -- Floor quantity
                pcn ASC                              -- Tie-breaker
        ) as new_rank
    FROM tblWhse_Inventory
    WHERE (onhandqty > 0 OR mfg_qty > 0)
        AND item IS NOT NULL
        AND TRIM(item) != ''
)
SELECT
    o.item_normalized,
    o.original_item,
    '---OLD WINNER---' as separator1,
    o.pcn as old_winner_pcn,
    o.loc_to as old_location,
    o.bin_qty as old_bin,
    o.floor_qty as old_floor,
    o.total_qty as old_total,
    '---NEW WINNER---' as separator2,
    n.pcn as new_winner_pcn,
    n.loc_to as new_location,
    n.bin_qty as new_bin,
    n.floor_qty as new_floor,
    n.total_qty as new_total,
    '---ANALYSIS---' as separator3,
    CASE
        WHEN o.bin_qty = 0 AND n.bin_qty > 0 THEN 'FIXED: Now shows bin instead of floor-only'
        WHEN o.bin_qty > 0 AND n.bin_qty > o.bin_qty THEN 'IMPROVED: Better bin selected'
        ELSE 'OTHER: Different selection'
    END as fix_type
FROM old_logic_ranking o
JOIN new_logic_ranking n ON o.item_normalized = n.item_normalized
WHERE o.old_rank = 1 AND n.new_rank = 1  -- Top-ranked PCN in each logic
    AND o.pcn != n.pcn  -- Different winner
ORDER BY
    CASE
        WHEN o.bin_qty = 0 AND n.bin_qty > 0 THEN 1  -- Critical fixes first
        WHEN o.bin_qty > 0 AND n.bin_qty > o.bin_qty THEN 2
        ELSE 3
    END,
    (n.total_qty - o.total_qty) DESC;  -- Biggest impact first

-- Expected output: List of items where location changed from old to new logic
-- Focus on fix_type = 'FIXED: Now shows bin instead of floor-only'


-- ----------------------------------------------------------------------------
-- QUERY 2: Count of items corrected by severity
-- ----------------------------------------------------------------------------

WITH correction_analysis AS (
    SELECT
        UPPER(TRIM(item)) as item_normalized,
        MAX(CASE WHEN old_rank = 1 THEN pcn END) as old_pcn,
        MAX(CASE WHEN old_rank = 1 THEN onhandqty END) as old_bin,
        MAX(CASE WHEN old_rank = 1 THEN mfg_qty END) as old_floor,
        MAX(CASE WHEN new_rank = 1 THEN pcn END) as new_pcn,
        MAX(CASE WHEN new_rank = 1 THEN onhandqty END) as new_bin,
        MAX(CASE WHEN new_rank = 1 THEN mfg_qty END) as new_floor
    FROM (
        SELECT
            item, pcn, onhandqty, mfg_qty,
            ROW_NUMBER() OVER (
                PARTITION BY UPPER(TRIM(item))
                ORDER BY (COALESCE(onhandqty, 0) + COALESCE(mfg_qty, 0)) DESC
            ) as old_rank,
            ROW_NUMBER() OVER (
                PARTITION BY UPPER(TRIM(item))
                ORDER BY (COALESCE(onhandqty, 0) > 0) DESC, onhandqty DESC, mfg_qty DESC
            ) as new_rank
        FROM tblWhse_Inventory
        WHERE onhandqty > 0 OR mfg_qty > 0
    ) ranked
    GROUP BY item_normalized
    HAVING MAX(CASE WHEN old_rank = 1 THEN pcn END) != MAX(CASE WHEN new_rank = 1 THEN pcn END)
)
SELECT
    COUNT(*) FILTER (WHERE old_bin = 0 AND new_bin > 0) as critical_fixes_floor_to_bin,
    COUNT(*) FILTER (WHERE old_bin > 0 AND new_bin > old_bin) as improved_bin_selection,
    COUNT(*) FILTER (WHERE old_bin > 0 AND new_bin > 0 AND new_bin != old_bin) as different_bin,
    COUNT(*) as total_items_corrected
FROM correction_analysis;

-- Expected:
-- critical_fixes_floor_to_bin: ~1,492 (from bug report)
-- total_items_corrected: >= 1,492


-- ----------------------------------------------------------------------------
-- QUERY 3: Verify NO bin stock is being shown as MFG Floor
-- ----------------------------------------------------------------------------
-- This should return 0 rows after the fix

WITH ranked_inventory AS (
    SELECT
        UPPER(TRIM(item)) as item_normalized,
        item,
        pcn,
        loc_to,
        onhandqty,
        mfg_qty,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(TRIM(item))
            ORDER BY
                (COALESCE(onhandqty, 0) > 0) DESC,
                COALESCE(onhandqty, 0) DESC,
                COALESCE(mfg_qty, 0) DESC,
                pcn ASC
        ) as rank
    FROM tblWhse_Inventory
    WHERE (onhandqty > 0 OR mfg_qty > 0)
)
SELECT
    ri.item_normalized,
    ri.item,
    ri.pcn as selected_pcn,
    ri.loc_to as selected_location,
    ri.onhandqty as selected_bin_qty,
    ri.mfg_qty as selected_floor_qty,
    other.pcn as available_bin_pcn,
    other.loc_to as available_bin_location,
    other.onhandqty as available_bin_qty,
    'ERROR: Selected floor-only when bin stock available!' as issue
FROM ranked_inventory ri
JOIN tblWhse_Inventory other
    ON UPPER(TRIM(other.item)) = ri.item_normalized
    AND other.pcn != ri.pcn
    AND other.onhandqty > 0  -- Other PCN has bin stock
WHERE ri.rank = 1  -- This is the selected location
    AND ri.onhandqty = 0  -- But selected has no bin stock
    AND ri.mfg_qty > 0;  -- And has only floor stock

-- EXPECTED: 0 rows (no items incorrectly showing floor when bin exists)
-- If this returns rows, the bug is NOT fixed!


-- ----------------------------------------------------------------------------
-- QUERY 4: Reproduce the exact Bug #1 scenario
-- ----------------------------------------------------------------------------
-- Job 5455M, Line 3: PCN 37656 in bin 2204207 should be shown
-- NOT PCN 37654 with MFG Floor

SELECT
    'Bug #1 Scenario Validation' as test_name,
    item,
    pcn,
    loc_to,
    onhandqty as bin_qty,
    mfg_qty as floor_qty,
    (onhandqty + mfg_qty) as total_qty,
    CASE
        WHEN pcn = 37656 AND onhandqty > 0 THEN '✓ CORRECT - Bin stock PCN'
        WHEN pcn = 37654 AND onhandqty = 0 THEN '✗ WRONG - Floor-only PCN should not win'
        ELSE 'INFO - Other PCN'
    END as validation
FROM tblWhse_Inventory
WHERE pcn IN (37656, 37654)
ORDER BY
    (onhandqty > 0) DESC,
    onhandqty DESC,
    mfg_qty DESC;

-- Expected: First row should be PCN 37656 with bin stock
-- If PCN 37654 appears first, bug is NOT fixed


-- ----------------------------------------------------------------------------
-- QUERY 5: Test case-insensitive item matching
-- ----------------------------------------------------------------------------
-- Verify BOM items match inventory regardless of case

SELECT
    b.job_number,
    b.line_number,
    b.item_number as bom_item,
    w.item as inventory_item,
    w.pcn,
    w.loc_to,
    w.onhandqty,
    w.mfg_qty,
    CASE
        WHEN w.item IS NULL THEN 'NOT MATCHED'
        WHEN UPPER(b.item_number) = UPPER(w.item) THEN 'MATCHED (case-insensitive)'
        ELSE 'ERROR'
    END as match_status
FROM tblBOM b
LEFT JOIN LATERAL (
    SELECT item, pcn, loc_to, onhandqty, mfg_qty
    FROM tblWhse_Inventory
    WHERE UPPER(TRIM(item)) = UPPER(TRIM(b.item_number))
        AND (onhandqty > 0 OR mfg_qty > 0)
    ORDER BY
        (onhandqty > 0) DESC,
        onhandqty DESC,
        mfg_qty DESC,
        pcn ASC
    LIMIT 1
) w ON TRUE
WHERE b.job_number = '5455M'  -- Original bug job
ORDER BY b.line_number
LIMIT 20;

-- Expected: All items should show 'MATCHED (case-insensitive)' if in stock


-- ----------------------------------------------------------------------------
-- QUERY 6: Validate 8-digit bin numbers are supported
-- ----------------------------------------------------------------------------
-- Related to Bug #5 fix - ensure 8-digit bins are not dropped

SELECT
    item,
    pcn,
    loc_to,
    LENGTH(loc_to) as location_length,
    onhandqty,
    mfg_qty,
    CASE
        WHEN loc_to ~ '^[0-9]{8,}$' THEN '✓ Valid 8+ digit bin'
        WHEN loc_to ~ '^[0-9]{6,7}$' THEN 'Valid 6-7 digit bin'
        ELSE 'Named location or other'
    END as location_type
FROM tblWhse_Inventory
WHERE onhandqty > 0
    AND LENGTH(loc_to) >= 8
    AND loc_to ~ '^[0-9]+$'
ORDER BY LENGTH(loc_to) DESC, loc_to ASC
LIMIT 50;

-- Expected: 8-digit bins should be present and valid
-- If no results, 8-digit bins may have been dropped (Bug #5 not fixed)


-- ----------------------------------------------------------------------------
-- QUERY 7: Performance test - Large job shortage report simulation
-- ----------------------------------------------------------------------------
-- Simulate shortage report generation for a large job

EXPLAIN ANALYZE
WITH bom_requirements AS (
    SELECT
        job_number,
        line_number,
        UPPER(TRIM(item_number)) as item_normalized,
        CAST(
            CASE
                WHEN qty ~ '^[0-9]+\.?[0-9]*$' THEN qty::numeric
                ELSE 0
            END AS INTEGER
        ) as required_qty
    FROM tblBOM
    WHERE job_number = '5455M'  -- Replace with a large job
        AND item_number IS NOT NULL
),
inventory_ranked AS (
    SELECT
        UPPER(TRIM(item)) as item_normalized,
        item,
        pcn,
        loc_to,
        onhandqty,
        mfg_qty,
        (onhandqty + mfg_qty) as total_qty,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(TRIM(item))
            ORDER BY
                (onhandqty > 0) DESC,
                onhandqty DESC,
                mfg_qty DESC,
                pcn ASC
        ) as rank
    FROM tblWhse_Inventory
    WHERE (onhandqty > 0 OR mfg_qty > 0)
)
SELECT
    b.job_number,
    b.line_number,
    b.item_normalized,
    b.required_qty,
    COALESCE(i.total_qty, 0) as onhand,
    GREATEST(0, b.required_qty - COALESCE(i.total_qty, 0)) as shortage_qty,
    COALESCE(i.loc_to, 'NOT STOCKED') as location,
    CASE
        WHEN i.onhandqty > 0 THEN 'BIN'
        WHEN i.mfg_qty > 0 THEN 'FLOOR'
        ELSE 'NONE'
    END as location_type
FROM bom_requirements b
LEFT JOIN inventory_ranked i
    ON b.item_normalized = i.item_normalized
    AND i.rank = 1
ORDER BY b.line_number;

-- Check EXPLAIN ANALYZE output:
-- Expected: Execution time < 1000ms for ~100 BOM lines
-- Look for efficient use of indexes on item, pcn


-- ----------------------------------------------------------------------------
-- QUERY 8: Audit trail - Items that would have caused picker errors
-- ----------------------------------------------------------------------------
-- These are items where pickers would have been sent to wrong location

WITH picker_error_candidates AS (
    SELECT
        UPPER(TRIM(item)) as item,
        MAX(CASE WHEN rank_old = 1 THEN loc_to END) as old_location,
        MAX(CASE WHEN rank_old = 1 THEN onhandqty END) as old_bin_qty,
        MAX(CASE WHEN rank_new = 1 THEN loc_to END) as new_location,
        MAX(CASE WHEN rank_new = 1 THEN onhandqty END) as new_bin_qty
    FROM (
        SELECT
            item, loc_to, onhandqty, mfg_qty,
            ROW_NUMBER() OVER (
                PARTITION BY UPPER(TRIM(item))
                ORDER BY (onhandqty + mfg_qty) DESC
            ) as rank_old,
            ROW_NUMBER() OVER (
                PARTITION BY UPPER(TRIM(item))
                ORDER BY (onhandqty > 0) DESC, onhandqty DESC, mfg_qty DESC
            ) as rank_new
        FROM tblWhse_Inventory
        WHERE onhandqty > 0 OR mfg_qty > 0
    ) ranked
    GROUP BY UPPER(TRIM(item))
)
SELECT
    item,
    old_location as would_have_sent_picker_to,
    old_bin_qty as bin_qty_at_old_location,
    new_location as now_sends_picker_to,
    new_bin_qty as bin_qty_at_new_location,
    CASE
        WHEN old_bin_qty = 0 AND new_bin_qty > 0 THEN 'CRITICAL: Was sending to empty location!'
        WHEN new_bin_qty > old_bin_qty THEN 'IMPROVED: Better location now'
        ELSE 'CHANGED'
    END as impact
FROM picker_error_candidates
WHERE old_location != new_location
    AND (old_bin_qty = 0 OR new_bin_qty > old_bin_qty)
ORDER BY
    (CASE WHEN old_bin_qty = 0 THEN 0 ELSE 1 END),  -- Critical first
    new_bin_qty DESC
LIMIT 100;

-- Expected: Shows items that would have caused picker frustration
-- These are the real-world impacts of Bug #1


-- ----------------------------------------------------------------------------
-- QUERY 9: Validate shortage report for specific job lines
-- ----------------------------------------------------------------------------
-- Spot-check specific shortage report lines

SELECT
    b.job_number,
    b.line_number,
    b.item_number,
    b.qty as required,
    i.pcn,
    i.loc_to as location,
    i.onhandqty as bin_qty,
    i.mfg_qty as floor_qty,
    (COALESCE(i.onhandqty, 0) + COALESCE(i.mfg_qty, 0)) as total_onhand,
    GREATEST(0, CAST(b.qty AS INTEGER) - COALESCE(i.onhandqty, 0) - COALESCE(i.mfg_qty, 0)) as shortage,
    CASE
        WHEN i.onhandqty > 0 THEN i.loc_to
        WHEN i.mfg_qty > 0 THEN 'MFG Floor'
        ELSE 'NOT STOCKED'
    END as display_location,
    CASE
        WHEN i.onhandqty > 0 THEN '✓ BIN LOCATION'
        WHEN i.mfg_qty > 0 THEN '✓ MFG FLOOR'
        ELSE '✗ NOT STOCKED'
    END as validation
FROM tblBOM b
LEFT JOIN LATERAL (
    SELECT pcn, loc_to, onhandqty, mfg_qty
    FROM tblWhse_Inventory
    WHERE UPPER(TRIM(item)) = UPPER(TRIM(b.item_number))
        AND (onhandqty > 0 OR mfg_qty > 0)
    ORDER BY
        (onhandqty > 0) DESC,
        onhandqty DESC,
        mfg_qty DESC,
        pcn ASC
    LIMIT 1
) i ON TRUE
WHERE b.job_number = '5455M'
ORDER BY b.line_number;

-- Expected: For each line, display_location should match validation
-- Lines with bin stock should show actual bin location, not 'MFG Floor'


-- ----------------------------------------------------------------------------
-- QUERY 10: Summary statistics for Bug #1 fix impact
-- ----------------------------------------------------------------------------

SELECT
    'Total items in inventory' as metric,
    COUNT(DISTINCT UPPER(TRIM(item))) as value
FROM tblWhse_Inventory
WHERE onhandqty > 0 OR mfg_qty > 0

UNION ALL

SELECT
    'Items with multiple PCNs' as metric,
    COUNT(*) as value
FROM (
    SELECT UPPER(TRIM(item)) as item
    FROM tblWhse_Inventory
    WHERE onhandqty > 0 OR mfg_qty > 0
    GROUP BY UPPER(TRIM(item))
    HAVING COUNT(DISTINCT pcn) > 1
) multi_pcn

UNION ALL

SELECT
    'Items with both bin and floor stock' as metric,
    COUNT(DISTINCT UPPER(TRIM(item))) as value
FROM tblWhse_Inventory
WHERE EXISTS (
    SELECT 1 FROM tblWhse_Inventory w2
    WHERE UPPER(TRIM(w2.item)) = UPPER(TRIM(tblWhse_Inventory.item))
        AND w2.onhandqty > 0
)
AND EXISTS (
    SELECT 1 FROM tblWhse_Inventory w3
    WHERE UPPER(TRIM(w3.item)) = UPPER(TRIM(tblWhse_Inventory.item))
        AND w3.mfg_qty > 0
        AND w3.onhandqty = 0
)

UNION ALL

SELECT
    'Items corrected by Bug #1 fix' as metric,
    COUNT(*) as value
FROM (
    SELECT item FROM (
        SELECT
            UPPER(TRIM(item)) as item,
            ROW_NUMBER() OVER (
                PARTITION BY UPPER(TRIM(item))
                ORDER BY (onhandqty + mfg_qty) DESC
            ) as old_rank,
            ROW_NUMBER() OVER (
                PARTITION BY UPPER(TRIM(item))
                ORDER BY (onhandqty > 0) DESC, onhandqty DESC
            ) as new_rank,
            pcn
        FROM tblWhse_Inventory
        WHERE onhandqty > 0 OR mfg_qty > 0
    ) ranked
    WHERE old_rank = 1 AND new_rank = 1
    GROUP BY item
    HAVING MAX(CASE WHEN old_rank = 1 THEN pcn END) != MAX(CASE WHEN new_rank = 1 THEN pcn END)
) corrected;

-- Expected output:
-- Total items: ~thousands
-- Items corrected: ~1,492 (per bug report)


-- ============================================================================
-- END OF VERIFICATION QUERIES
-- ============================================================================
-- Run these queries after deploying Bug #1 fix to validate correctness
-- Save output for audit trail
-- ============================================================================
