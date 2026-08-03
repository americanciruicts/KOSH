"""KOSH warehouse operations — the SNAPSHOT model (single source of truth).

`tblWhse_Inventory` is authoritative. For a PCN:
  onhandqty = qty in the BIN
  mfg_qty   = qty on the MFG FLOOR   (stored as text for legacy reasons)
  loc_to    = the bin code, or 'MFG Floor' when the stock is on the floor

DOMAIN RULE (Preet, 2026-07-17): picks are ALWAYS COMPLETE — a PCN's whole bin qty is
picked to the floor at once. So a PCN's stock is in EXACTLY ONE place: bin XOR floor.
A row with both onhandqty>0 AND mfg_qty>0 is dirty data, never a legit partial split.

There is NO ledger and NO reconciler. Every operation updates this one row inside the
caller's transaction, so Warehouse Inventory and PCN History — which both read this row —
can never disagree.

Each function takes an OPEN psycopg2 cursor and does NOT commit; the caller owns the txn.
"""

TBL = 'warehouse."tblWhse_Inventory"'
FLOOR = 'MFG Floor'


class WarehouseOpError(Exception):
    """A rejected operation (over-pick, bad qty, unknown PCN)."""


def _qty(v):
    """Coerce to a strictly-positive int or reject (no silent truncation)."""
    try:
        q = int(v)
    except (TypeError, ValueError):
        raise WarehouseOpError(f'quantity must be an integer, got {v!r}')
    if q <= 0:
        raise WarehouseOpError(f'quantity must be > 0, got {q}')
    return q


def _floor_int(mfg_qty):
    """mfg_qty is TEXT and can be blank/garbage; parse to a safe int (0 if unparseable)."""
    s = str(mfg_qty).strip() if mfg_qty is not None else ''
    return int(s) if s.lstrip('-').isdigit() else 0


def _lock_row(cur, pcn):
    """Return (bin_qty, floor_qty, loc_to) for a PCN with the row locked FOR UPDATE, so a
    caller can branch on the values and write without them changing underneath."""
    cur.execute(f'SELECT onhandqty, mfg_qty, loc_to FROM {TBL} WHERE pcn::text=%s FOR UPDATE',
                (str(pcn),))
    r = cur.fetchone()
    if not r:
        raise WarehouseOpError(f'PCN {pcn} not found in warehouse inventory')
    return int(r[0] or 0), _floor_int(r[1]), r[2]


def on_hand(cur, pcn):
    """Total on-hand for a PCN = bin + floor. ONE number, read from the one source."""
    bin_qty, floor_qty, _ = _lock_row(cur, pcn)
    return bin_qty + floor_qty


def pick(cur, pcn, qty):
    """Pick = move `qty` from the BIN to the MFG FLOOR for `pcn` (complete-pick model).

    Rejects an over-pick (can't pick more than the bin holds) instead of going negative.
    When the bin empties (the normal complete pick), loc_to flips to 'MFG Floor' and the
    row satisfies bin-XOR-floor.  Total (bin+floor) is conserved — nothing is minted.
    """
    qty = _qty(qty)
    bin_qty, floor_qty, _ = _lock_row(cur, pcn)
    if bin_qty < qty:
        raise WarehouseOpError(
            f'insufficient stock in bin: have {bin_qty}, need {qty} (pcn {pcn})')
    new_bin = bin_qty - qty
    new_floor = floor_qty + qty
    cur.execute(
        f"""UPDATE {TBL}
            SET onhandqty = %s,
                mfg_qty   = %s,
                loc_to    = CASE WHEN %s = 0 THEN %s ELSE loc_to END
            WHERE pcn::text = %s""",
        (new_bin, str(new_floor), new_bin, FLOOR, str(pcn)),
    )
    return {'pcn': str(pcn), 'moved': qty, 'bin': new_bin, 'floor': new_floor}
