-- ============================================================================
-- KOSH — permanent guard: BIN XOR FLOOR on tblWhse_Inventory.
-- A trigger normalizes EVERY insert/update so the invariant can never be violated
-- by any code path, now or in the future:
--   * loc_to = 'MFG Floor'  ->  onhandqty = 0,  mfg_qty  = the qty
--   * loc_to = a bin        ->  onhandqty = the qty,  mfg_qty = 0
-- The "qty" is whichever column the writer populated (GREATEST, so a stray value in
-- the wrong column is moved, never summed into a double-count). Idempotent.
-- Run on STAGING and PRODUCTION.
-- ============================================================================
CREATE OR REPLACE FUNCTION warehouse.enforce_bin_xor_floor() RETURNS trigger AS $$
DECLARE
  bin_q int := GREATEST(COALESCE(NEW.onhandqty, 0), 0);
  flr_q int := CASE WHEN NEW.mfg_qty ~ '^[0-9]+$' THEN NEW.mfg_qty::int ELSE 0 END;
  qty   int := GREATEST(bin_q, flr_q);
BEGIN
  IF COALESCE(NEW.loc_to, '') = 'MFG Floor' THEN
     NEW.onhandqty := 0;            -- on the floor: bin holds nothing
     NEW.mfg_qty   := qty::text;    -- the qty lives on the floor
  ELSE
     NEW.onhandqty := qty;          -- in a bin: the qty lives in the bin
     NEW.mfg_qty   := '0';          -- floor holds nothing
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_bin_xor_floor ON warehouse."tblWhse_Inventory";
CREATE TRIGGER trg_bin_xor_floor
  BEFORE INSERT OR UPDATE ON warehouse."tblWhse_Inventory"
  FOR EACH ROW EXECUTE FUNCTION warehouse.enforce_bin_xor_floor();

-- verify the trigger exists
SELECT tgname, tgenabled FROM pg_trigger WHERE tgname = 'trg_bin_xor_floor';
