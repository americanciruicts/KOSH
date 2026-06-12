-- KOSH inventory integrity check (read-only).
-- Every row should report count 0 (or be INFO). Non-zero = investigate.
-- Run: docker exec aci-database psql -U stockpick_user -d kosh -f /path/integrity_check.sql
-- Intended to back a nightly monitor (Phase 6). Covers the defects found 2026-06-12.

\echo '=== KOSH integrity check ==='

-- 1. On-hand double-count: a row must NOT carry stock in BOTH on-hand and mfg_qty.
SELECT 'double_count_onhand_and_mfg' AS check, count(*) AS violations
FROM pcb_inventory."tblWhse_Inventory"
WHERE onhandqty > 0 AND mfg_qty ~ '^-?[0-9]+$' AND mfg_qty::int > 0;

-- 2. Negative on-hand (should never happen).
SELECT 'negative_onhand' AS check, count(*) AS violations
FROM pcb_inventory."tblWhse_Inventory" WHERE onhandqty < 0;

-- 3. PCN collision: one PCN bound to >1 genuinely different item, each with live stock
--    (excludes rename history where only one row has stock). Phase 5 detector.
SELECT 'pcn_collision' AS check, count(*) AS violations FROM (
  SELECT pcn FROM pcb_inventory."tblWhse_Inventory"
  WHERE pcn ~ '^[0-9]+$' AND onhandqty > 0
  GROUP BY pcn HAVING count(DISTINCT lower(item)) > 1
) t;

-- 4. Stored on-hand must match the renumber-aware ledger derivation (reconcile drift).
--    NOTE: a TEMPORARY downward-only guard is active during remediation, so rows where
--    the ledger derives MORE than stored are expected (the non-convergence backlog).
--    This counts rows where stored is ABOVE the ledger (should be ~0 once reconciled).
WITH lv AS (
  SELECT DISTINCT lower(trim(loc_to)) v FROM pcb_inventory."tblTransaction" WHERE trantype<>'ADJT' AND loc_to IS NOT NULL AND trim(loc_to)<>''
  UNION SELECT DISTINCT lower(trim(loc_from)) FROM pcb_inventory."tblTransaction" WHERE trantype<>'ADJT' AND loc_from IS NOT NULL AND trim(loc_from)<>''
  UNION VALUES ('mfg floor'),('rec area'),('receiving area'),('count area'),('n/a'),('na'),('')
),
parsed AS (
  SELECT pcn::text pcn, lower(translate(coalesce(mpn,''),'-# ./','')) mpn_key, id, trantype, tranqty, coalesce(reversed,false) reversed,
    CASE WHEN tran_time ~ '^[0-9]{4}-' THEN tran_time::timestamptz
         WHEN tran_time ~ '^[0-9]{2}/[0-9]{2}/[0-9]{2}' THEN to_timestamp(tran_time,'MM/DD/YY HH24:MI:SS') ELSE NULL END ts,
    (trantype='ADJT' AND lower(trim(coalesce(loc_from,'')))<>lower(trim(coalesce(loc_to,'')))
       AND NOT (lower(trim(coalesce(loc_to,'')))  IN (SELECT v FROM lv) OR coalesce(loc_to,'')  ~ '^[0-9]{6,}$' OR trim(coalesce(loc_to,''))='')
       AND NOT (lower(trim(coalesce(loc_from,''))) IN (SELECT v FROM lv) OR coalesce(loc_from,'') ~ '^[0-9]{6,}$' OR trim(coalesce(loc_from,''))='')) is_relabel
  FROM pcb_inventory."tblTransaction" WHERE tranqty ~ '^-?[0-9]+$'
),
last_rndt AS (SELECT DISTINCT ON (pcn,mpn_key) pcn,mpn_key,id rndt_id,ts rndt_ts,tranqty::int rndt_qty
  FROM parsed WHERE trantype='RNDT' AND reversed=false ORDER BY pcn,mpn_key,ts DESC NULLS LAST,id DESC),
net AS (SELECT t.pcn,t.mpn_key, GREATEST(0, COALESCE(MAX(r.rndt_qty),0)+SUM(CASE WHEN t.is_relabel THEN 0
     WHEN t.trantype IN ('INDF','STOCK','PCN Generation','RESTOCK','ADJT') THEN t.tranqty::int
     WHEN t.trantype IN ('PICK','PURGE') THEN -t.tranqty::int ELSE 0 END)) qty
  FROM parsed t LEFT JOIN last_rndt r ON t.pcn=r.pcn AND t.mpn_key=r.mpn_key
  WHERE t.reversed=false AND (r.rndt_id IS NULL OR (r.rndt_ts IS NOT NULL AND t.ts>=r.rndt_ts) OR (r.rndt_ts IS NULL AND t.id>=r.rndt_id))
  GROUP BY t.pcn,t.mpn_key)
SELECT 'stored_above_ledger (phantom not yet cleared)' AS check, count(*) AS violations
FROM pcb_inventory."tblWhse_Inventory" w JOIN net n
  ON w.pcn::text=n.pcn AND lower(translate(coalesce(w.mpn,''),'-# ./',''))=n.mpn_key
WHERE w.onhandqty > n.qty;

-- 5. INFO: relabel-ADJTs created in the last 2 days (from the Access re-import).
--    Not a violation — the reconcile neutralizes them — but watch for spikes.
SELECT 'INFO_recent_relabel_adjt_2d' AS check, count(*) AS info
FROM pcb_inventory."tblTransaction"
WHERE trantype='ADJT' AND COALESCE(reversed,false)=false
  AND tran_time ~ ('^' || to_char(CURRENT_DATE, 'MM/DD/YY'));

\echo '=== end integrity check ==='
