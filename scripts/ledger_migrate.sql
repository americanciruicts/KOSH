-- One-time migration into the canonical ledger (COPY DB only).
-- Source: the already-clean append-only inv_event model (Skorokhod reflection +
-- relabel-ADJT drop + double-collapse were applied when inv_event was seeded;
-- the check `replay(inv_event) == inv_location_balance` returns 0 mismatches).
--
-- We therefore project inv_event's real movements into inventory_txn and load the
-- derived balances into inventory_balance.  Because both come from the same events,
-- Warehouse (balance) == PCN History (ledger replay) by construction (I3).

SET search_path = warehouse;

BEGIN;

TRUNCATE inventory_balance;
-- inventory_txn is append-only (trigger blocks DELETE); rebuild by recreating rows
-- only when empty.  Guard so re-running the migration is explicit.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM inventory_txn) THEN
    RAISE EXCEPTION 'inventory_txn already seeded; drop & recreate schema to re-migrate';
  END IF;
END $$;

-- 1) Project real movements (exclude LEGACY audit rows and qty=0 no-ops -> I6).
INSERT INTO inventory_txn
    (txn_type, part_id, pcn_id, qty, from_location_id, to_location_id,
     occurred_at, created_by, note)
SELECT CASE e.event_type
           WHEN 'OPENING' THEN 'STOCK'
           WHEN 'RECEIPT' THEN 'STOCK'
           ELSE e.event_type                       -- PICK/RESTOCK/TRANSFER/ADJUST/PURGE/SCRAP
       END,
       e.part_id, e.pcn, e.qty, e.from_location, e.to_location,
       e.occurred_at, e.created_by, e.note
FROM inv_event e
WHERE e.event_type NOT IN ('LEGACY', 'RELABEL')     -- I8: relabels are not movements
  AND e.qty > 0
  AND (e.from_location IS NOT NULL OR e.to_location IS NOT NULL)
ORDER BY e.event_id;

-- 2) Load the derived balances (the reflected, double-collapsed, non-negative cache).
INSERT INTO inventory_balance (part_id, pcn_id, location_id, qty)
SELECT part_id, pcn, location_id, qty::int
FROM inv_location_balance
WHERE qty > 0;

COMMIT;

-- ---------------------------------------------------------------------------
-- ACCEPTANCE A (structural): Warehouse (balance) == PCN History (ledger replay)
-- ---------------------------------------------------------------------------
\echo '=== ACCEPTANCE A: mismatches (MUST be 0) ==='
WITH wh AS (SELECT pcn_id, SUM(qty) q FROM inventory_balance GROUP BY pcn_id),
     h  AS (SELECT pcn_id,
                   SUM((CASE WHEN to_location_id   IS NOT NULL THEN qty ELSE 0 END)
                      -(CASE WHEN from_location_id IS NOT NULL THEN qty ELSE 0 END)) q
            FROM inventory_txn WHERE reversed=false GROUP BY pcn_id)
SELECT COUNT(*) FILTER (WHERE COALESCE(wh.q,0) <> COALESCE(h.q,0)) AS mismatches
FROM wh FULL OUTER JOIN h USING (pcn_id);

-- ---------------------------------------------------------------------------
-- ACCEPTANCE C: no negative balances
-- ---------------------------------------------------------------------------
\echo '=== ACCEPTANCE C: negative balances (MUST be 0) ==='
SELECT COUNT(*) AS negatives FROM inventory_balance WHERE qty < 0;

\echo '=== seeded counts ==='
SELECT (SELECT count(*) FROM inventory_txn)     AS txn_rows,
       (SELECT count(*) FROM inventory_balance) AS balance_rows;
