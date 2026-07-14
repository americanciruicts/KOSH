-- KOSH — clear STALE MFG-Floor counts (consumed picks) — 2yr+ high-confidence tier.
-- Rule (Preet): a part picked to the floor for a job, never restocked, is CONSUMED once
-- the job is done. These rows have bin=0, mfg_qty = the exact pick qty, no restock after
-- the pick, and the pick was >2 years ago -> the parts are gone, so mfg_qty must be 0.
-- onhandqty (bin) is already 0, so on-hand ends at 0. Prior mfg_qty is snapshot to
-- tblReconcileAudit first -> fully reversible.
--
-- MAGNITUDE: ~5,719 rows, ~2,146,506 units set to 0. This is a large, deliberate writedown
-- of stock that was consumed years ago and never cleared. Review the qualifying count it
-- prints before it commits (it's all one transaction).
--
-- RUN (from your shell):
--   PGPASSWORD='<prod-db-password>' docker exec -i -e PGPASSWORD aci-database \
--     psql -U aci -d kosh -v ON_ERROR_STOP=1 < scripts/fix_stale_floor_2yr.sql
--
-- To be MORE conservative, change '2 years' below to '3 years' (~1.85M units, 5,181 rows).
-- REVERSAL: restore mfg_qty per pcn from tblReconcileAudit source='stale_floor_consumed_2yr_20260709'.
-- AFTER running, tell me and I'll sync inv_onhand + verify reconcile.

SET lock_timeout='3s';
SET statement_timeout='180s';
BEGIN;

CREATE TEMP TABLE _qual ON COMMIT DROP AS
WITH tx AS (
  SELECT pcn::text pcn, trantype, tranqty tq,
    CASE WHEN tran_time ~ '^[0-9]{4}-' THEN tran_time::timestamptz
         WHEN tran_time ~ '^[0-9]{2}/[0-9]{2}/[0-9]{2}\s' THEN TO_TIMESTAMP(tran_time,'MM/DD/YY HH24:MI:SS') END ts
  FROM pcb_inventory."tblTransaction" WHERE COALESCE(reversed,false)=false),
lastpick AS (
  SELECT DISTINCT ON (pcn) pcn, CASE WHEN tq ~ '^[0-9]+$' THEN tq::int END pick_qty
  FROM tx WHERE trantype='PICK' ORDER BY pcn, ts DESC NULLS LAST),
agg AS (
  SELECT pcn, MAX(ts) FILTER (WHERE trantype='PICK') last_pick,
         MAX(ts) FILTER (WHERE trantype='RESTOCK') last_restock
  FROM tx GROUP BY pcn)
SELECT w.id, w.pcn::text pcn, w.item, w.mpn, w.mfg_qty::int AS prior_floor
FROM pcb_inventory."tblWhse_Inventory" w
JOIN agg a ON a.pcn = w.pcn::text
LEFT JOIN lastpick lp ON lp.pcn = w.pcn::text
WHERE w.onhandqty = 0
  AND w.mfg_qty ~ '^[1-9][0-9]*$'
  AND lp.pick_qty = w.mfg_qty::int
  AND (a.last_restock IS NULL OR a.last_restock < a.last_pick)
  AND a.last_pick < now() - interval '2 years';

SELECT 'qualifying_rows=' || count(*) || '  units_to_clear=' || COALESCE(SUM(prior_floor),0) FROM _qual;

INSERT INTO pcb_inventory."tblReconcileAudit"(pcn, item, mpn, prior_qty, new_qty, source)
  SELECT pcn, item, mpn, prior_floor, 0, 'stale_floor_consumed_2yr_20260709' FROM _qual;

UPDATE pcb_inventory."tblWhse_Inventory" w SET mfg_qty='0' FROM _qual q WHERE w.id = q.id;

COMMIT;
