-- FIX: Bidirectional Warehouse Reconcile
-- Safely corrects BOTH phantom stock (warehouse > ledger) AND missing stock (warehouse < ledger)
--
-- SAFETY: Only corrects upward if:
-- 1. Discrepancy > threshold (5 units) - avoids churn on small differences
-- 2. Logged to audit table for review
-- 3. Can be rolled back if needed
--
-- Run this to reconcile Warehouse to match PCN History ledger in BOTH directions

BEGIN;

-- Create audit table if not exists
CREATE TABLE IF NOT EXISTS pcb_inventory."tblReconcileAudit" (
    id SERIAL PRIMARY KEY,
    reconciled_at TIMESTAMPTZ DEFAULT NOW(),
    pcn TEXT,
    item TEXT,
    mpn TEXT,
    prior_qty INTEGER,
    new_qty INTEGER,
    direction TEXT,  -- 'DOWNWARD' or 'UPWARD'
    source TEXT DEFAULT 'bidirectional_reconcile'
);

-- Reconcile logic (same as _ONHAND_RECONCILE_SQL but bidirectional)
WITH locvocab AS (
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
    SELECT DISTINCT ON (pcn, mpn_key)
        pcn, mpn_key, id AS rndt_id, ts AS rndt_ts, tranqty::integer AS rndt_qty
    FROM parsed
    WHERE trantype = 'RNDT' AND reversed = false
    ORDER BY pcn, mpn_key, ts DESC NULLS LAST, id DESC
),
net AS (
    SELECT
        t.pcn,
        t.mpn_key,
        GREATEST(0,
            COALESCE(MAX(r.rndt_qty), 0) +
            SUM(CASE
                WHEN t.is_relabel THEN 0
                WHEN t.trantype IN ('INDF','STOCK','PCN Generation','RESTOCK','ADJT')
                    THEN t.tranqty::integer
                WHEN t.trantype IN ('PICK','PURGE','SCRA')
                    THEN -t.tranqty::integer
                ELSE 0
            END)
        ) AS qty
    FROM parsed t
    LEFT JOIN last_rndt r
        ON t.pcn = r.pcn AND t.mpn_key = r.mpn_key
    WHERE t.reversed = false
      AND (r.rndt_id IS NULL
           OR (r.rndt_ts IS NOT NULL AND t.ts >= r.rndt_ts)
           OR (r.rndt_ts IS NULL AND t.id >= r.rndt_id))
    GROUP BY t.pcn, t.mpn_key
),
to_update AS (
    SELECT
        w.id,
        w.pcn,
        w.item,
        w.mpn,
        w.onhandqty AS prior_qty,
        n.qty AS new_qty,
        CASE
            WHEN n.qty < w.onhandqty THEN 'DOWNWARD'
            WHEN n.qty > w.onhandqty THEN 'UPWARD'
        END AS direction
    FROM pcb_inventory."tblWhse_Inventory" w
    JOIN net n
        ON w.pcn::text = n.pcn
        AND LOWER(TRANSLATE(COALESCE(w.mpn,''), '-# ./', '')) = n.mpn_key
    WHERE n.qty <> w.onhandqty  -- BIDIRECTIONAL: not just < but also >
      AND ABS(n.qty - w.onhandqty) > 5  -- Only fix significant discrepancies (> 5 units)
),
log_update AS (
    INSERT INTO pcb_inventory."tblReconcileAudit"
        (pcn, item, mpn, prior_qty, new_qty, direction, source)
    SELECT pcn, item, mpn, prior_qty, new_qty, direction, 'bidirectional_reconcile'
    FROM to_update
    RETURNING 1
)
UPDATE pcb_inventory."tblWhse_Inventory" w
SET onhandqty = u.new_qty
FROM to_update u
WHERE w.id = u.id;

-- Show what was updated
SELECT
    direction,
    COUNT(*) AS rows_updated,
    SUM(ABS(new_qty - prior_qty)) AS total_units_corrected
FROM pcb_inventory."tblReconcileAudit"
WHERE source = 'bidirectional_reconcile'
  AND reconciled_at >= NOW() - INTERVAL '1 minute'
GROUP BY direction
ORDER BY direction;

-- Show recent corrections (for review)
SELECT
    pcn, item, mpn,
    prior_qty AS warehouse_was,
    new_qty AS corrected_to,
    (new_qty - prior_qty) AS change,
    direction
FROM pcb_inventory."tblReconcileAudit"
WHERE source = 'bidirectional_reconcile'
  AND reconciled_at >= NOW() - INTERVAL '1 minute'
ORDER BY ABS(new_qty - prior_qty) DESC
LIMIT 20;

-- Verify: Check for remaining discrepancies
SELECT
    CASE
        WHEN w.onhandqty > n.qty THEN 'PHANTOM_STOCK'
        WHEN w.onhandqty < n.qty THEN 'MISSING_STOCK'
    END AS status,
    COUNT(*) AS count,
    SUM(ABS(w.onhandqty - n.qty)) AS total_units
FROM pcb_inventory."tblWhse_Inventory" w
JOIN net n
    ON w.pcn::text = n.pcn
    AND LOWER(TRANSLATE(COALESCE(w.mpn,''), '-# ./', '')) = n.mpn_key
WHERE w.onhandqty <> n.qty
  AND ABS(w.onhandqty - n.qty) > 5
GROUP BY status;

-- Uncomment to ROLLBACK instead of COMMIT (for testing):
-- ROLLBACK;

-- Commit the changes:
COMMIT;

-- After running, check PCN History vs Warehouse - they should now match!
