-- Bug #20 remediation: remove the bin/floor double-count on the existing rows.
-- A unit is either in a bin (onhandqty) OR on the MFG floor (mfg_qty), never both.
-- Rows where onhandqty == mfg_qty are the same units counted twice.
--   * floor-located row (loc_to = 'MFG Floor')  -> parts are on the floor -> zero onhandqty
--   * bin-located row   (loc_to = a real bin)   -> parts are in the bin   -> zero mfg_qty
-- Every change is logged to tblReconcileAudit (reversible). Run inside one txn.

BEGIN;

-- Floor-located doubles: zero the phantom bin on-hand (same logic as the shipped
-- reconcile_floor_onhand guard, applied once here for immediacy + audit).
WITH dbl AS (
    SELECT id, pcn, item, mpn, onhandqty AS prior_qty
    FROM pcb_inventory."tblWhse_Inventory"
    WHERE LOWER(TRIM(COALESCE(loc_to,''))) = 'mfg floor'
      AND onhandqty > 0 AND mfg_qty ~ '^[1-9][0-9]*$'
      AND onhandqty = mfg_qty::int
),
logged AS (
    INSERT INTO pcb_inventory."tblReconcileAudit" (pcn, item, mpn, prior_qty, new_qty, source)
    SELECT pcn, item, mpn, prior_qty, 0, 'bug20_floor_dedupe' FROM dbl RETURNING 1
)
UPDATE pcb_inventory."tblWhse_Inventory" w SET onhandqty = 0 FROM dbl WHERE w.id = dbl.id;

-- Bin-located doubles: parts are in the bin; zero the phantom MFG-floor qty.
WITH dbl AS (
    SELECT id, pcn, item, mpn, onhandqty
    FROM pcb_inventory."tblWhse_Inventory"
    WHERE LOWER(TRIM(COALESCE(loc_to,''))) <> 'mfg floor'
      AND onhandqty > 0 AND mfg_qty ~ '^[1-9][0-9]*$'
      AND onhandqty = mfg_qty::int
),
logged AS (
    INSERT INTO pcb_inventory."tblReconcileAudit" (pcn, item, mpn, prior_qty, new_qty, source)
    SELECT pcn, item, mpn, onhandqty, onhandqty, 'bug20_bin_dedupe_mfg_zeroed' FROM dbl RETURNING 1
)
UPDATE pcb_inventory."tblWhse_Inventory" w SET mfg_qty = '0' FROM dbl WHERE w.id = dbl.id;

-- Report what changed in this run
SELECT source, COUNT(*) AS rows_fixed, SUM(prior_qty) AS units_dedeuped
FROM pcb_inventory."tblReconcileAudit"
WHERE source IN ('bug20_floor_dedupe','bug20_bin_dedupe_mfg_zeroed')
  AND reconciled_at >= NOW() - INTERVAL '1 minute'
GROUP BY source;

-- Verify: no rows left with the exact double signature
SELECT COUNT(*) AS remaining_double_rows
FROM pcb_inventory."tblWhse_Inventory"
WHERE onhandqty > 0 AND mfg_qty ~ '^[1-9][0-9]*$' AND onhandqty = mfg_qty::int;

COMMIT;
