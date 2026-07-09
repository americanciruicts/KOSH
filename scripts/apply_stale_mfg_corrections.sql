-- KOSH — apply the stale bin/floor double-count corrections (bug-20 class).
-- Zeroes the STALE mfg_qty (floor) on rows where stock is really in the bin; onhandqty
-- (bin) is UNTOUCHED so no real stock is lost. Prior mfg_qty is snapshot to
-- tblReconcileAudit first, so it is fully reversible.
--
-- RUN (from your shell — an in-place UPDATE on live inventory needs a human, by design):
--   PGPASSWORD='<prod-db-password>' docker exec -i -e PGPASSWORD aci-database \
--     psql -U aci -d kosh -v ON_ERROR_STOP=1 < scripts/apply_stale_mfg_corrections.sql
--
-- The shadow sync + inv_onhand will reflect the correction automatically after commit.
-- REVERSAL: for any pcn, restore mfg_qty from the audit row
--   (source='bug20_bin_stale_mfg_zeroed_20260709', prior_qty column).

SET lock_timeout='3s';
BEGIN;

-- 11 verified stale-double rows (25972 intentionally EXCLUDED — see below).
INSERT INTO pcb_inventory."tblReconcileAudit"(pcn, item, mpn, prior_qty, new_qty, source)
SELECT pcn, item, mpn,
       CASE WHEN mfg_qty ~ '^-?[0-9]+$' THEN mfg_qty::int ELSE NULL END, 0,
       'bug20_bin_stale_mfg_zeroed_20260709'
FROM pcb_inventory."tblWhse_Inventory"
WHERE id IN (51650,46960,65010,42408,37671,63162,65570,53118,64381,57858,63165);

UPDATE pcb_inventory."tblWhse_Inventory" SET mfg_qty='0'
WHERE id IN (51650,46960,65010,42408,37671,63162,65570,53118,64381,57858,63165)
  AND onhandqty > 0 AND mfg_qty ~ '^[1-9][0-9]*$';   -- guard: only if still stale

-- Expect: UPDATE 11
COMMIT;

-- ============================================================================
-- OPTIONAL — PCN 25972 (ACI-8182): bin 190 / floor 3000. Trace says the 3000
-- were picked to the floor in 2022 and almost certainly consumed in production
-- (only 190 restocked in 2026). But that is 2,810 units — CONFIRM nothing is
-- physically on the floor before running this. Uncomment to apply:
--
-- BEGIN;
-- INSERT INTO pcb_inventory."tblReconcileAudit"(pcn,item,mpn,prior_qty,new_qty,source)
--   SELECT pcn,item,mpn, CASE WHEN mfg_qty ~ '^-?[0-9]+$' THEN mfg_qty::int END, 0,
--          'bug20_bin_stale_mfg_zeroed_20260709'
--   FROM pcb_inventory."tblWhse_Inventory" WHERE id=46779;
-- UPDATE pcb_inventory."tblWhse_Inventory" SET mfg_qty='0' WHERE id=46779;
-- COMMIT;
