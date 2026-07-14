-- KOSH — go-forward fix for stale MFG-Floor phantoms — 2026-07-14
-- Adds the missing "consumed by production" event + the audit table the self-healing
-- floor janitor writes to. See ledger.consume() and app._floor_janitor().
BEGIN;

-- 1) CONSUME is a first-class txn type (floor -> out of system). Distinct from SHIP
--    (customer) / SCRAP (defective) / ADJUST (manual correction) so reports can tell
--    "eaten by a work order" apart from everything else.
ALTER TABLE warehouse.inventory_txn DROP CONSTRAINT IF EXISTS inventory_txn_txn_type_check;
ALTER TABLE warehouse.inventory_txn ADD  CONSTRAINT inventory_txn_txn_type_check
  CHECK (txn_type = ANY (ARRAY['STOCK','PICK','RESTOCK','TRANSFER','SHIP','PURGE',
                               'SCRAP','ADJUST','CONSUME']));

-- 2) Audit/reversal trail for every automatic consumption (I5: nothing is lost).
CREATE TABLE IF NOT EXISTS warehouse.floor_janitor_audit (
  audit_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_at       timestamptz NOT NULL DEFAULT now(),
  pcn_id       text   NOT NULL,
  part_id      bigint NOT NULL,
  item_raw     text,
  mpn_raw      text,
  location_id  bigint NOT NULL,
  consumed_qty integer NOT NULL,
  last_pick    timestamptz,
  age_days     integer,
  txn_id       bigint
);
CREATE INDEX IF NOT EXISTS floor_janitor_audit_run_idx ON warehouse.floor_janitor_audit(run_at);

COMMIT;
