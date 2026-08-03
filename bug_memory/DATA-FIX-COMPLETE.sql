-- ============================================================================
-- KOSH — inventory data cleanup. Enforces BIN XOR FLOOR (the correct model):
--   * loc_to = 'MFG Floor'  -> onhandqty = 0,  mfg_qty = floor qty,  loc_from = source bin
--   * loc_to = a bin        -> onhandqty = bin qty,  mfg_qty = 0
-- Floor qty + source bin are recovered from the last PICK in tblTransaction.
-- Idempotent, safe to re-run. Run STAGING first, then PRODUCTION at deploy time.
--   PGPASSWORD=<pw> psql -h <host> -p <port> -U <user> -d kosh -v ON_ERROR_STOP=1 -f bug_memory/DATA-FIX-COMPLETE.sql
--   (change final COMMIT to ROLLBACK for a dry run)
-- ============================================================================
BEGIN;

-- 0) PERMANENT GUARD: a BEFORE INSERT/UPDATE trigger that enforces BIN XOR FLOOR on
--    EVERY write (any transaction type, both directions), so this mismatch can never
--    recur. Created first so the data fixes below also pass through it.
CREATE OR REPLACE FUNCTION warehouse.enforce_bin_xor_floor() RETURNS trigger AS $fn$
DECLARE
  bin_q int := GREATEST(COALESCE(NEW.onhandqty, 0), 0);
  flr_q int := CASE WHEN NEW.mfg_qty ~ '^[0-9]+$' THEN NEW.mfg_qty::int ELSE 0 END;
  qty   int := GREATEST(bin_q, flr_q);
BEGIN
  IF COALESCE(NEW.loc_to, '') = 'MFG Floor' THEN
     NEW.onhandqty := 0;         NEW.mfg_qty := qty::text;
  ELSE
     NEW.onhandqty := qty;       NEW.mfg_qty := '0';
  END IF;
  RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_bin_xor_floor ON warehouse."tblWhse_Inventory";
CREATE TRIGGER trg_bin_xor_floor BEFORE INSERT OR UPDATE ON warehouse."tblWhse_Inventory"
  FOR EACH ROW EXECUTE FUNCTION warehouse.enforce_bin_xor_floor();

-- 1) BIN parts (loc_to is a real bin, not MFG Floor): the floor column must be 0.
UPDATE warehouse."tblWhse_Inventory"
   SET mfg_qty = '0'
 WHERE COALESCE(loc_to,'') <> 'MFG Floor' AND mfg_qty IS DISTINCT FROM '0';

-- 2) FLOOR parts (loc_to = 'MFG Floor'): onhandqty must be 0 and mfg_qty must hold the
--    floor quantity. Recover the floor qty and source bin from the last PICK. loc_from
--    becomes the bin the part was picked from (fall back to its last known bin).
WITH last_pick AS (
  SELECT DISTINCT ON (t.pcn::text) t.pcn::text AS pcn, t.tranqty AS floorqty, t.loc_from
  FROM warehouse."tblTransaction" t
  WHERE t.trantype = 'PICK' AND t.tranqty ~ '^[0-9]+$'
  ORDER BY t.pcn::text, t.id DESC
),
last_bin AS (
  SELECT DISTINCT ON (t.pcn::text) t.pcn::text AS pcn, t.loc_to AS bin
  FROM warehouse."tblTransaction" t
  WHERE t.trantype IN ('RESTOCK','PTWY','STOCK','INDF') AND t.loc_to ~ '^[0-9]+$'
  ORDER BY t.pcn::text, t.id DESC
)
UPDATE warehouse."tblWhse_Inventory" w
   SET onhandqty = 0,
       mfg_qty   = lp.floorqty,
       loc_from  = COALESCE(NULLIF(lp.loc_from, 'MFG Floor'), lb.bin, w.loc_from)
  FROM last_pick lp
  LEFT JOIN last_bin lb ON lb.pcn = lp.pcn
 WHERE w.pcn::text = lp.pcn AND COALESCE(w.loc_to,'') = 'MFG Floor';

-- 3) NEGATIVE on-hand -> 0.
UPDATE warehouse."tblWhse_Inventory" SET onhandqty = 0 WHERE COALESCE(onhandqty,0) < 0;

-- 4) KNOWN corrupt: PCN 43774 had an erroneous ADJT +2,204,290 over the real 14.
UPDATE warehouse."tblWhse_Inventory" SET onhandqty = 14
 WHERE pcn::text = '43774' AND onhandqty = 2204304;

-- ---- VERIFY (all must be 0) ------------------------------------------------
SELECT
  count(*) FILTER (WHERE COALESCE(loc_to,'')='MFG Floor' AND COALESCE(onhandqty,0)<>0)                          AS floor_with_bin_onhand,
  count(*) FILTER (WHERE COALESCE(loc_to,'')='MFG Floor' AND NOT (mfg_qty ~ '^[1-9][0-9]*$'))                   AS floor_missing_mfgqty,
  count(*) FILTER (WHERE COALESCE(loc_to,'')<>'MFG Floor' AND mfg_qty ~ '^[1-9][0-9]*$')                        AS bin_with_floor_qty,
  count(*) FILTER (WHERE COALESCE(onhandqty,0)>0 AND mfg_qty ~ '^[1-9][0-9]*$')                                 AS both_filled_double,
  count(*) FILTER (WHERE COALESCE(onhandqty,0)>1000000)                                                         AS absurd
FROM warehouse."tblWhse_Inventory";

-- Example row check (PCN 40562 should be: onhand 0, mfg_qty 100, loc_from a bin, loc_to MFG Floor)
SELECT pcn, item, onhandqty, mfg_qty, loc_from, loc_to FROM warehouse."tblWhse_Inventory" WHERE pcn::text='40562';

COMMIT;   -- <-- change to ROLLBACK for a dry run
