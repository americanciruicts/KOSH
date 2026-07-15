-- KOSH — add the FOUND event so restock is never blocked by the floor balance — 2026-07-15
-- ============================================================================
-- WHY (Theresa, 2026-07-15): restock was rejecting parts with
--   "insufficient stock at MFG Floor: have 0, need 62"  (PCN 38159).
-- Restock is modelled as a pure floor->bin TRANSFER, so it demands the floor
-- already hold the qty. But the floor balance is an INFERENCE, not a physical
-- fact: KOSH had no consumption event for years, and the 2026-07-14 stale-floor
-- cleanup zeroed 9,859 PCNs whose last pick was >6 months old on the assumption
-- the parts were consumed. When that inference is wrong (parts picked at zero,
-- not found, purged, or simply never consumed), the parts still physically come
-- back and MUST be restockable — Theresa's day-one requirement.
--
-- FOUND = "these units physically exist and are going into a bin, but the ledger
-- did not believe they were on the floor" (external -> bin). It is deliberately a
-- DISTINCT type, not a silent absorption into RESTOCK, so that:
--   * the guard against phantom stock is preserved — units that appear from
--     nowhere are LABELLED as appearing from nowhere, never hidden in a transfer;
--   * reports/audits can measure exactly how often the floor inference was wrong
--     (each FOUND row is a place the stale-floor rule or a zero-pick lost track);
--   * reversal stays possible (I5).
-- The alternative — dropping the floor check in restock() — would restore the
-- exact hole that manufactured the phantom stock in the first place.
-- ============================================================================
BEGIN;

-- 1) FOUND is a first-class txn type (external -> bin), alongside CONSUME.
ALTER TABLE warehouse.inventory_txn DROP CONSTRAINT IF EXISTS inventory_txn_txn_type_check;
ALTER TABLE warehouse.inventory_txn ADD  CONSTRAINT inventory_txn_txn_type_check
  CHECK (txn_type = ANY (ARRAY['STOCK','PICK','RESTOCK','TRANSFER','SHIP','PURGE',
                               'SCRAP','ADJUST','CONSUME','FOUND']));

COMMIT;
