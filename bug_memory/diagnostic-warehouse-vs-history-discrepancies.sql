-- DIAGNOSTIC: Warehouse vs PCN History Discrepancies
-- Checks BOTH directions: warehouse > ledger AND warehouse < ledger
-- Run this to find remaining cases where Warehouse ≠ PCN History

WITH locvocab AS (
    -- Real locations learned from non-ADJT activity
    SELECT DISTINCT LOWER(TRIM(loc_to)) AS v
    FROM pcb_inventory."tblTransaction"
    WHERE trantype <> 'ADJT' AND loc_to IS NOT NULL AND TRIM(loc_to) <> ''
    UNION
    SELECT DISTINCT LOWER(TRIM(loc_from))
    FROM pcb_inventory."tblTransaction"
    WHERE trantype <> 'ADJT' AND loc_from IS NOT NULL AND TRIM(loc_from) <> ''
    UNION VALUES ('mfg floor'),('rec area'),('receiving area'),('count area'),('n/a'),('na'),('')
),
parsed AS (
    -- Parse transactions with is_relabel logic
    SELECT
        pcn::text AS pcn,
        LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) AS mpn_key,
        id, trantype, tranqty,
        COALESCE(reversed, false) AS reversed,
        CASE
            WHEN tran_time ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN tran_time::timestamptz
            WHEN tran_time ~ '^[0-9]{2}/[0-9]{2}/[0-9]{2}\s+[0-9]{2}:[0-9]{2}'
                THEN TO_TIMESTAMP(tran_time, 'MM/DD/YY HH24:MI:SS')
            ELSE NULL
        END AS ts,
        -- is_relabel: ADJT with item numbers (not locations) in loc fields
        (trantype = 'ADJT'
           AND LOWER(TRIM(COALESCE(loc_from,''))) <> LOWER(TRIM(COALESCE(loc_to,'')))
           AND NOT (LOWER(TRIM(COALESCE(loc_to,''))) IN (SELECT v FROM locvocab)
                    OR COALESCE(loc_to,'') ~ '^[0-9]{6,}$'
                    OR TRIM(COALESCE(loc_to,'')) = '')
           AND NOT (LOWER(TRIM(COALESCE(loc_from,''))) IN (SELECT v FROM locvocab)
                    OR COALESCE(loc_from,'') ~ '^[0-9]{6,}$'
                    OR TRIM(COALESCE(loc_from,'')) = '')
        ) AS is_relabel
    FROM pcb_inventory."tblTransaction"
    WHERE tranqty ~ '^-?[0-9]+$'
),
last_rndt AS (
    -- Last RNDT (recount) per (pcn, mpn)
    SELECT DISTINCT ON (pcn, mpn_key)
        pcn, mpn_key, id AS rndt_id, ts AS rndt_ts, tranqty::integer AS rndt_qty
    FROM parsed
    WHERE trantype = 'RNDT' AND reversed = false
    ORDER BY pcn, mpn_key, ts DESC NULLS LAST, id DESC
),
ledger AS (
    -- Calculate on-hand from transaction ledger (same logic as PCN History)
    SELECT
        t.pcn,
        t.mpn_key,
        GREATEST(0,
            COALESCE(MAX(r.rndt_qty), 0) +
            SUM(CASE
                WHEN t.is_relabel THEN 0  -- Renumber = quantity-neutral
                WHEN t.trantype IN ('INDF','STOCK','PCN Generation','RESTOCK','ADJT')
                    THEN t.tranqty::integer
                WHEN t.trantype IN ('PICK','PURGE','SCRA')
                    THEN -t.tranqty::integer
                ELSE 0
            END)
        ) AS ledger_qty
    FROM parsed t
    LEFT JOIN last_rndt r
        ON t.pcn = r.pcn AND t.mpn_key = r.mpn_key
    WHERE t.reversed = false
      AND (r.rndt_id IS NULL
           OR (r.rndt_ts IS NOT NULL AND t.ts >= r.rndt_ts)
           OR (r.rndt_ts IS NULL AND t.id >= r.rndt_id))
    GROUP BY t.pcn, t.mpn_key
),
comparison AS (
    -- Compare Warehouse vs Ledger
    SELECT
        w.pcn,
        w.item,
        w.mpn,
        w.onhandqty AS warehouse_qty,
        COALESCE(w.mfg_qty::integer, 0) AS warehouse_mfg_qty,
        (w.onhandqty + COALESCE(CASE WHEN w.mfg_qty ~ '^-?[0-9]+$'
                                THEN w.mfg_qty::integer ELSE 0 END, 0)) AS warehouse_total,
        COALESCE(l.ledger_qty, 0) AS ledger_qty,
        w.loc_to AS warehouse_location,
        CASE
            WHEN w.onhandqty > COALESCE(l.ledger_qty, 0) THEN 'PHANTOM_STOCK'
            WHEN w.onhandqty < COALESCE(l.ledger_qty, 0) THEN 'MISSING_STOCK'
            WHEN w.onhandqty = COALESCE(l.ledger_qty, 0) THEN 'MATCH'
            ELSE 'NO_LEDGER'
        END AS status,
        (w.onhandqty - COALESCE(l.ledger_qty, 0)) AS discrepancy
    FROM pcb_inventory."tblWhse_Inventory" w
    LEFT JOIN ledger l
        ON w.pcn::text = l.pcn
        AND LOWER(TRANSLATE(COALESCE(w.mpn,''), '-# ./', '')) = l.mpn_key
    WHERE w.onhandqty > 0 OR l.ledger_qty > 0  -- Show any with stock
)
-- Show discrepancies
SELECT
    status,
    COUNT(*) AS count,
    SUM(ABS(discrepancy)) AS total_units_affected
FROM comparison
WHERE status IN ('PHANTOM_STOCK', 'MISSING_STOCK')
GROUP BY status
ORDER BY status;

-- Detailed view of discrepancies (top 20)
-- Uncomment to see specific PCNs:
/*
SELECT
    pcn, item, mpn,
    warehouse_qty, warehouse_mfg_qty, warehouse_total,
    ledger_qty,
    status, discrepancy,
    warehouse_location
FROM comparison
WHERE status IN ('PHANTOM_STOCK', 'MISSING_STOCK')
ORDER BY ABS(discrepancy) DESC
LIMIT 20;
*/
