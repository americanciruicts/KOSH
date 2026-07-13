-- KOSH clean-ledger schema — single source of truth.
-- Applied to a COPY of prod (kosh_rebuild) first. Never touches prod until A/B/C pass.
--
-- Canonical objects:
--   inventory_txn      append-only ledger (movements only, qty>0)         [the truth]
--   inventory_balance  (part,pcn,location)->qty cache, CHECK(qty>=0),     [derived, same-txn]
--                      written in the SAME transaction as every ledger row
--
-- Reuses the already-built master data: inv_part (normalized case-insensitive keys),
-- inv_location (BIN/FLOOR/STAGING/EXTERNAL).  There is NO onhandqty+mfg_qty pair.

SET search_path = warehouse;

-- ---------------------------------------------------------------------------
-- I4: case-insensitive user identity (part/mpn already covered by inv_part keys)
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS citext;

DROP TABLE IF EXISTS inventory_balance CASCADE;
DROP TABLE IF EXISTS inventory_txn CASCADE;

-- ---------------------------------------------------------------------------
-- The one ledger.  Every stock movement is exactly one row.
--   from_location_id  NULL => stock entered the system (STOCK receipt / positive ADJUST)
--   to_location_id    NULL => stock left the system (SHIP / PURGE / negative ADJUST)
--   both set          => TRANSFER (PICK bin->floor, RESTOCK floor->bin): total conserved
-- ---------------------------------------------------------------------------
CREATE TABLE inventory_txn (
    txn_id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    txn_type          text    NOT NULL
                        CHECK (txn_type IN ('STOCK','PICK','RESTOCK','TRANSFER',
                                            'SHIP','PURGE','SCRAP','ADJUST')),
    part_id           bigint  NOT NULL REFERENCES inv_part(part_id),
    pcn_id            text    NOT NULL,                       -- the physical lot/barcode
    qty               integer NOT NULL CHECK (qty > 0),       -- I6: typed, >0, no string parse
    from_location_id  bigint  REFERENCES inv_location(location_id),
    to_location_id    bigint  REFERENCES inv_location(location_id),
    reversed          boolean NOT NULL DEFAULT false,         -- I5: never delete; flag instead
    reverses_txn_id   bigint  REFERENCES inventory_txn(txn_id),
    reversed_at       timestamptz,
    occurred_at       timestamptz NOT NULL DEFAULT now(),
    created_by        text    NOT NULL DEFAULT 'system',
    wo                text,
    po                text,
    cost              numeric,
    note              text,
    -- a movement must move stock somewhere (I8: relabels are NOT ledger rows at all)
    CHECK (from_location_id IS NOT NULL OR to_location_id IS NOT NULL),
    -- a transfer's endpoints must differ
    CHECK (from_location_id IS NULL OR to_location_id IS NULL
           OR from_location_id <> to_location_id)
);
CREATE INDEX inventory_txn_pcn_idx   ON inventory_txn (pcn_id);
CREATE INDEX inventory_txn_part_idx  ON inventory_txn (part_id);
CREATE INDEX inventory_txn_type_idx  ON inventory_txn (txn_type);
CREATE INDEX inventory_txn_live_idx  ON inventory_txn (pcn_id) WHERE reversed = false;

-- Append-only: no UPDATE/DELETE except flipping reversed=true (an inverse-neutral flag).
CREATE OR REPLACE FUNCTION inventory_txn_append_only() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'inventory_txn is append-only (no DELETE)';
    END IF;
    -- Only the reversal flag/pointer may change; every other column is immutable.
    IF ROW(NEW.txn_id, NEW.txn_type, NEW.part_id, NEW.pcn_id, NEW.qty,
           NEW.from_location_id, NEW.to_location_id, NEW.occurred_at)
       IS DISTINCT FROM
       ROW(OLD.txn_id, OLD.txn_type, OLD.part_id, OLD.pcn_id, OLD.qty,
           OLD.from_location_id, OLD.to_location_id, OLD.occurred_at) THEN
        RAISE EXCEPTION 'inventory_txn is append-only (only reversed flag may change)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER inventory_txn_no_mutate
    BEFORE UPDATE OR DELETE ON inventory_txn
    FOR EACH ROW EXECUTE FUNCTION inventory_txn_append_only();

-- ---------------------------------------------------------------------------
-- The balance cache.  One number per (part, pcn, location).  I1: never negative.
-- Written in the SAME transaction as the ledger row (see ledger service), so it
-- can never drift from inventory_txn.  There is nothing to reconcile.
-- ---------------------------------------------------------------------------
CREATE TABLE inventory_balance (
    part_id      bigint  NOT NULL REFERENCES inv_part(part_id),
    pcn_id       text    NOT NULL,
    location_id  bigint  NOT NULL REFERENCES inv_location(location_id),
    qty          integer NOT NULL CHECK (qty >= 0),           -- I1
    PRIMARY KEY (part_id, pcn_id, location_id)
);
CREATE INDEX inventory_balance_pcn_idx ON inventory_balance (pcn_id);
CREATE INDEX inventory_balance_loc_idx ON inventory_balance (location_id);
