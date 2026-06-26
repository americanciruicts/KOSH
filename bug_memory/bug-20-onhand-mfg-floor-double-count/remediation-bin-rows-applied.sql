BEGIN;
-- Verified genuine doubles: parts were put away into a BIN (latest movement),
-- so onhandqty is the real qty and mfg_qty is a STALE floor count. Zero the
-- stale mfg_qty only. Prior mfg value logged to audit -> fully reversible, no
-- real stock lost (onhandqty untouched). Scoped to the 5 verified PCNs.
WITH tgt AS (
    SELECT id, pcn, item, mpn, onhandqty,
           CASE WHEN mfg_qty ~ '^-?[0-9]+$' THEN mfg_qty::int ELSE 0 END AS prior_mfg
    FROM pcb_inventory."tblWhse_Inventory"
    WHERE pcn::text IN ('37921','40044','42625','39355','44833')
      AND LOWER(TRIM(COALESCE(loc_to,''))) <> 'mfg floor'
      AND onhandqty > 0 AND mfg_qty ~ '^[1-9][0-9]*$' AND onhandqty = mfg_qty::int
),
logged AS (
    INSERT INTO pcb_inventory."tblReconcileAudit" (pcn, item, mpn, prior_qty, new_qty, source)
    SELECT pcn, item, mpn, prior_mfg, 0, 'bug20_bin_stale_mfg_zeroed' FROM tgt RETURNING 1
)
UPDATE pcb_inventory."tblWhse_Inventory" w SET mfg_qty = '0' FROM tgt WHERE w.id = tgt.id;
SELECT 'bin rows fixed' AS action, COUNT(*) FROM pcb_inventory."tblReconcileAudit"
  WHERE source='bug20_bin_stale_mfg_zeroed' AND reconciled_at >= NOW() - INTERVAL '1 minute';
SELECT COUNT(*) AS remaining_doubles FROM pcb_inventory."tblWhse_Inventory"
  WHERE onhandqty>0 AND mfg_qty ~ '^[1-9][0-9]*$' AND onhandqty = mfg_qty::int;
COMMIT;
