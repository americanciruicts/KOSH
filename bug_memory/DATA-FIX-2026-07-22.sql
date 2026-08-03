-- KOSH data cleanup — 2026-07-22. Derived from tblTransaction history, NOT guessed.
-- Run on STAGING first:  PGPASSWORD=<pw> psql -h localhost -p 5434 -U aci -d kosh -f bug_memory/DATA-FIX-2026-07-22.sql
-- Review the VERIFY output before COMMIT (change COMMIT to ROLLBACK to dry-run).

BEGIN;

-- FIX 1 — 33 DOUBLE-COUNT rows: onhandqty is correct (matches the last RESTOCK in
-- history), mfg_qty is a stale floor number. Clear it so on-hand = one number.
-- (Also makes the nightly `double_count` integrity gate pass.)
UPDATE warehouse."tblWhse_Inventory"
   SET mfg_qty = '0'
 WHERE COALESCE(onhandqty,0) > 0 AND mfg_qty ~ '^[1-9][0-9]*$';

-- FIX 2 — PCN 43774 (7801L-1-2): current on-hand 2,204,304 is a data-entry error.
-- History: real qty 14 (PTWY 01/30/26), then an erroneous ADJT +2,204,290 (05/08/26)
-- => 14 + 2,204,290 = 2,204,304. Restore to 14 and log a corrective ADJT.
UPDATE warehouse."tblWhse_Inventory"
   SET onhandqty = 14
 WHERE pcn::text = '43774' AND onhandqty = 2204304;

INSERT INTO warehouse."tblTransaction"
   (trantype, item, pcn, mpn, tranqty, tran_time, loc_from, loc_to, userid)
SELECT 'ADJT', item, '43774', mpn, 14,
       TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'America/New_York','MM/DD/YY HH24:MI:SS'),
       loc_to, loc_to, 'data-cleanup: undo erroneous 2.2M ADJT, restore history value 14'
  FROM warehouse."tblWhse_Inventory" WHERE pcn::text = '43774';

-- VERIFY (want: double_count_remaining = 0, pcn43774_onhand = 14)
SELECT (SELECT count(*) FROM warehouse."tblWhse_Inventory"
          WHERE COALESCE(onhandqty,0) > 0 AND mfg_qty ~ '^[1-9][0-9]*$') AS double_count_remaining,
       (SELECT onhandqty FROM warehouse."tblWhse_Inventory" WHERE pcn::text = '43774') AS pcn43774_onhand;

COMMIT;   -- change to ROLLBACK to dry-run first
