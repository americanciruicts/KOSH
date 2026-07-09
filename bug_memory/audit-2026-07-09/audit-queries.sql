-- Reusable ledger-derived on-hand per (pcn, mpn_key), faithful to app.py _ONHAND_RECONCILE_SQL.
-- READ ONLY. Included as a WITH-prefix by each audit query.
WITH locvocab AS (
    SELECT DISTINCT LOWER(TRIM(loc_to)) AS v FROM pcb_inventory."tblTransaction"
        WHERE trantype <> 'ADJT' AND loc_to IS NOT NULL AND TRIM(loc_to) <> ''
    UNION
    SELECT DISTINCT LOWER(TRIM(loc_from)) FROM pcb_inventory."tblTransaction"
        WHERE trantype <> 'ADJT' AND loc_from IS NOT NULL AND TRIM(loc_from) <> ''
    UNION VALUES ('mfg floor'),('rec area'),('receiving area'),('count area'),('n/a'),('na'),('')
),
parsed AS (
    SELECT
        pcn::text AS pcn,
        LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) AS mpn_key,
        id, trantype, tranqty, COALESCE(reversed, false) AS reversed,
        CASE
            WHEN tran_time ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN tran_time::timestamptz
            WHEN tran_time ~ '^[0-9]{2}/[0-9]{2}/[0-9]{2}\s+[0-9]{2}:[0-9]{2}' THEN TO_TIMESTAMP(tran_time, 'MM/DD/YY HH24:MI:SS')
            ELSE NULL
        END AS ts,
        (trantype = 'ADJT'
           AND LOWER(TRIM(COALESCE(loc_from,''))) <> LOWER(TRIM(COALESCE(loc_to,'')))
           AND NOT (LOWER(TRIM(COALESCE(loc_to,'')))  IN (SELECT v FROM locvocab) OR COALESCE(loc_to,'')  ~ '^[0-9]{6,}$' OR TRIM(COALESCE(loc_to,'')) = '')
           AND NOT (LOWER(TRIM(COALESCE(loc_from,''))) IN (SELECT v FROM locvocab) OR COALESCE(loc_from,'') ~ '^[0-9]{6,}$' OR TRIM(COALESCE(loc_from,'')) = '')
        ) AS is_relabel
    FROM pcb_inventory."tblTransaction"
),
last_rndt AS (
    SELECT DISTINCT ON (pcn, mpn_key) pcn, mpn_key, id AS rndt_id, ts AS rndt_ts, tranqty::integer AS rndt_qty
    FROM parsed
    WHERE trantype = 'RNDT' AND reversed = false AND tranqty ~ '^-?[0-9]+$'
    ORDER BY pcn, mpn_key, ts DESC NULLS LAST, id DESC
),
net_deltas AS (
    SELECT t.pcn, t.mpn_key, COALESCE(r.rndt_qty, 0) AS base, t.ts, t.id,
           (CASE
                 WHEN t.is_relabel THEN 0
                 WHEN t.trantype = 'INDF' THEN t.tranqty::integer
                 WHEN t.trantype = 'STOCK' THEN t.tranqty::integer
                 WHEN t.trantype = 'PCN Generation' THEN t.tranqty::integer
                 WHEN t.trantype = 'RESTOCK' THEN t.tranqty::integer
                 WHEN t.trantype = 'ADJT' THEN t.tranqty::integer
                 WHEN t.trantype = 'PICK' THEN -t.tranqty::integer
                 WHEN t.trantype = 'PURGE' THEN -t.tranqty::integer
                 WHEN t.trantype = 'SCRA' THEN -t.tranqty::integer
                 ELSE 0
            END) AS delta
    FROM parsed t
    LEFT JOIN last_rndt r ON t.pcn = r.pcn AND t.mpn_key = r.mpn_key
    WHERE t.reversed = false AND t.tranqty ~ '^-?[0-9]+$'
      AND (r.rndt_id IS NULL
           OR (r.rndt_ts IS NOT NULL AND t.ts IS NOT NULL AND t.ts >= r.rndt_ts)
           OR (r.rndt_ts IS NULL AND t.id >= r.rndt_id))
),
net_run AS (
    SELECT pcn, mpn_key, base, delta,
           SUM(delta) OVER (PARTITION BY pcn, mpn_key ORDER BY ts ASC NULLS FIRST, id ASC
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS run_delta
    FROM net_deltas
),
net AS (
    SELECT pcn, mpn_key,
           (MAX(base) + COALESCE(SUM(delta), 0)) - LEAST(0, MAX(base) + MIN(run_delta)) AS qty,
           -- naive sum-then-clamp (pre-bug19) to detect over-pick class
           GREATEST(0, MAX(base) + COALESCE(SUM(delta), 0)) AS qty_naive
    FROM net_run GROUP BY pcn, mpn_key
)

-- ============================================================================
-- The WITH-block above (locvocab..net) is the reusable ledger-derived on-hand,
-- faithful to app.py _ONHAND_RECONCILE_SQL. Prepend it to any SELECT on `net`.
-- Each audit query below is READ ONLY. Counts captured 2026-07-09.
-- Run: docker exec -e PGPASSWORD=<pw> aci-database psql -U aci -d kosh
-- ============================================================================

-- A. Bin+floor double-counts (13; ~2985 overlap units)
--   onhandqty>0 AND mfg_qty ~ '^[1-9][0-9]*$'  (loc breakdown: all bin-located)
-- B. Relabel-ADJT phantoms (11,611 / 18,679)  -- see is_relabel predicate in the CTE
-- C. Malformed rows: blank trantype 197, numeric 67, na 12; unparseable tran_time 50
-- D. Over-pick groups (31): SELECT count(*) FROM net WHERE qty_naive=0 AND qty>0;
-- E. Bin vs ledger mismatch >5 (691; 515 ledger-higher, 0 warehouse-higher bin-only)
-- F. MFG floor stock: 12,700 rows / 12,687 floor-only / 4,744,889 units
-- G. Stale locations: 0
-- The exact statements are reproduced in the shell history / report; this file
-- carries the shared CTE so any of A–F can be re-run verbatim.
