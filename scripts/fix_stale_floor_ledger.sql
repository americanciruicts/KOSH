-- KOSH — clear STALE MFG-Floor phantom stock in the LEDGER (post-rebuild) — 2026-07-14
-- ============================================================================
-- WHY: KOSH has no "consumed by production" event. Parts picked bin->floor for a
-- job stay frozen on the floor forever once the job eats them (floor only clears on
-- RESTOCK). The ledger rebuild faithfully seeded those frozen floor counts, so ~3.5M
-- phantom units inflate on-hand. Warehouse(tblWhse_Inventory projection) and PCN
-- History(inventory_balance) already AGREE on the phantom; this fix removes it from
-- BOTH atomically so they keep agreeing at the correct, lower number.
--
-- RULE (Preet): floor stock whose most-recent PICK was >6 months ago = the job is
-- done = whatever is still on the floor is the consumed-and-never-cleared phantom ->
-- set floor to 0. Bin qty is untouched. A LATER partial restock does NOT make it
-- clean (only the restocked part came back; the rest was consumed).
-- e.g. PCN 43585: picked 10000 (Nov-2025), 3340 restocked to a bin, 6660 consumed ->
--      bin 3340 kept, floor 6660 phantom removed -> total 3340.
--
-- SAFETY:
--   * one transaction, audit snapshot FIRST -> fully reversible.
--   * excludes any PCN with a real (non-seed) PICK in the new ledger (live staged job).
--   * excludes floor picked <6 months ago (might be a live job on the floor now).
--   * appends an ADJUST ledger row per PCN (history preserved, I5) + zeroes the
--     balance + re-projects tblWhse_Inventory, exactly like the app write path.
--
-- REVERSAL: for each row in warehouse.stale_floor_fix_audit, add the floor qty back
--   via a positive ADJUST at 'MFG Floor' and re-project. (source tag below.)
-- ============================================================================
\set AGE_CUTOFF '6 months'
\set SRC 'stale_floor_fix_20260714'

SET lock_timeout='5s';
SET statement_timeout='600s';
BEGIN;

-- Reversal/audit table (created once; safe to re-run).
CREATE TABLE IF NOT EXISTS warehouse.stale_floor_fix_audit (
  audit_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_src      text NOT NULL,
  pcn_id       text NOT NULL,
  part_id      bigint NOT NULL,
  item_raw     text,
  mpn_raw      text,
  location_id  bigint NOT NULL,
  prior_floor  integer NOT NULL,
  last_pick    timestamptz,
  txn_id       bigint,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- 1) Qualifying set: floor balance whose legacy pick is old & never restocked-after,
--    and which has no recent real ledger pick.
CREATE TEMP TABLE _qual ON COMMIT DROP AS
WITH floor_bal AS (
  SELECT b.pcn_id, b.part_id, b.location_id, b.qty AS floor_qty
  FROM warehouse.inventory_balance b
  JOIN warehouse.inv_location l USING(location_id)
  WHERE l.kind='FLOOR' AND b.qty>0
),
legacy AS (
  SELECT pcn::text pcn, trantype,
    CASE WHEN tran_time ~ '^[0-9]{4}-' THEN tran_time::timestamptz
         WHEN tran_time ~ '^[0-9]{2}/[0-9]{2}/[0-9]{2}\s' THEN TO_TIMESTAMP(tran_time,'MM/DD/YY HH24:MI:SS') END ts
  FROM warehouse."tblTransaction" WHERE COALESCE(reversed,false)=false
),
agg AS (
  SELECT pcn,
    MAX(ts) FILTER (WHERE trantype='PICK')    AS last_pick,
    MAX(ts) FILTER (WHERE trantype='RESTOCK') AS last_restock
  FROM legacy GROUP BY pcn
),
recent_ledger_pick AS (   -- real (non-seed) pick in the NEW ledger => live staged job, KEEP
  SELECT DISTINCT pcn_id FROM warehouse.inventory_txn
  WHERE txn_type='PICK' AND reversed=false AND created_by<>'phase3_seed'
)
SELECT f.pcn_id, f.part_id, f.location_id, f.floor_qty, a.last_pick
FROM floor_bal f
JOIN agg a ON a.pcn = f.pcn_id
LEFT JOIN recent_ledger_pick r ON r.pcn_id = f.pcn_id
WHERE r.pcn_id IS NULL                                   -- no live ledger pick
  AND a.last_pick IS NOT NULL
  AND a.last_pick < now() - interval :'AGE_CUTOFF';       -- job done >6mo ago; residual = phantom

SELECT 'QUALIFYING pcns=' || count(*) || '  phantom_units=' || COALESCE(SUM(floor_qty),0)
FROM _qual;

-- 2) Snapshot BEFORE (reversibility).
INSERT INTO warehouse.stale_floor_fix_audit
  (run_src, pcn_id, part_id, item_raw, mpn_raw, location_id, prior_floor, last_pick)
SELECT :'SRC', q.pcn_id, q.part_id, p.item_raw, p.mpn_raw, q.location_id, q.floor_qty, q.last_pick
FROM _qual q JOIN warehouse.inv_part p USING(part_id);

-- 3) Append the ADJUST-out ledger rows (floor -> external). History preserved (I5).
INSERT INTO warehouse.inventory_txn
  (txn_type, part_id, pcn_id, qty, from_location_id, to_location_id, created_by, note)
SELECT 'ADJUST', q.part_id, q.pcn_id, q.floor_qty, q.location_id, NULL, :'SRC',
       'stale MFG-Floor phantom cleared (consumed pick, last pick '
       || COALESCE(to_char(q.last_pick,'YYYY-MM-DD'),'?') || ')'
FROM _qual q;

-- 4) Zero the floor BALANCE (bin balances untouched).
UPDATE warehouse.inventory_balance b
SET qty = 0
FROM _qual q
WHERE b.part_id=q.part_id AND b.pcn_id=q.pcn_id AND b.location_id=q.location_id;

-- 5) Re-project tblWhse_Inventory for affected PCNs (floor -> 0; bin unchanged) so the
--    Warehouse page matches the ledger / PCN History.
UPDATE warehouse."tblWhse_Inventory" w
SET mfg_qty='0', migrated_at=CURRENT_TIMESTAMP
FROM (SELECT DISTINCT pcn_id FROM _qual) q
WHERE w.pcn::text = q.pcn_id;

-- 6) Acceptance: Warehouse projection MUST equal ledger balance for every touched PCN.
--    If not, RAISE -> the whole transaction rolls back (nothing is committed).
DO $$
DECLARE m int;
BEGIN
  SELECT count(*) INTO m
  FROM (SELECT DISTINCT pcn_id FROM _qual) q
  JOIN warehouse."tblWhse_Inventory" w ON w.pcn::text=q.pcn_id
  LEFT JOIN LATERAL (
    SELECT COALESCE(SUM(CASE WHEN l.kind<>'FLOOR' THEN bal.qty END),0) AS bin,
           COALESCE(SUM(CASE WHEN l.kind='FLOOR'  THEN bal.qty END),0) AS floor
    FROM warehouse.inventory_balance bal JOIN warehouse.inv_location l USING(location_id)
    WHERE bal.pcn_id=q.pcn_id
  ) b ON true
  WHERE COALESCE(w.onhandqty,0) <> b.bin
     OR COALESCE(NULLIF(w.mfg_qty,''),'0')::int <> b.floor;
  IF m <> 0 THEN
    RAISE EXCEPTION 'ACCEPTANCE FAILED: % PCNs where Warehouse<>ledger; rolling back', m;
  END IF;
  RAISE NOTICE 'ACCEPTANCE OK: Warehouse == ledger for all touched PCNs';
END $$;

COMMIT;
