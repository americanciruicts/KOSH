"""KOSH ledger service — the SINGLE source of truth for on-hand.

Every stock movement is one append-only `inventory_txn` row, and the
`inventory_balance` cache is updated in the SAME database transaction.  On-hand is
always DERIVED from the ledger; it is never stored as an independent number.  There
is no `onhandqty`+`mfg_qty` pair and no reconciler — there is nothing to reconcile.

All functions take an OPEN psycopg2 cursor and DO NOT commit — the caller owns the
transaction, so the ledger row and the balance update commit atomically together.

Invariants enforced here (see DATA_MODEL.md):
  I1  balance never negative: source row locked FOR UPDATE + verified before write.
  I2  floor is a location; PICK/RESTOCK are transfers (total conserved).
  I3  Warehouse & PCN History both read this one ledger.
  I4  part/mpn matched case-insensitively (inv_part normalized keys).
  I5  reversals flag reversed=true + apply the inverse; history is never deleted.
  I6  qty is a validated positive integer; no string parsing on the write path.
  I7  a manual edit is an ADJUST at ONE location.
  I8  relabels/renumbers are metadata, never a qty movement (not handled here).
"""

FLOOR_CODE = 'MFG Floor'


class LedgerError(Exception):
    """Raised for any rejected movement (over-pick, bad qty, unknown part)."""


# --------------------------------------------------------------------------- #
# Validation (I6)
# --------------------------------------------------------------------------- #
def _qty(value):
    """Coerce to a strictly-positive int or reject.  No silent truncation."""
    try:
        q = int(value)
    except (TypeError, ValueError):
        raise LedgerError(f'quantity must be an integer, got {value!r}')
    if q <= 0:
        raise LedgerError(f'quantity must be > 0, got {q}')
    return q


# --------------------------------------------------------------------------- #
# Master-data resolution (get-or-create), case-insensitive (I4)
# --------------------------------------------------------------------------- #
def resolve_part(cur, item, mpn):
    """Return part_id for (item, mpn), creating it if new.  Matching is on the
    normalized keys (upper + punctuation-stripped), so case/format never splits a
    part.  I4."""
    if not item or not str(item).strip():
        raise LedgerError('item (ACI PN) is required')
    cur.execute(
        """
        INSERT INTO warehouse.inv_part (item_raw, mpn_raw)
        VALUES (%s, %s)
        ON CONFLICT (item_key, mpn_key) DO UPDATE SET item_raw = EXCLUDED.item_raw
        RETURNING part_id
        """,
        (str(item).strip(), (str(mpn).strip() if mpn is not None else None)),
    )
    return cur.fetchone()[0]


def _classify(code):
    c = code.strip()
    if c.isdigit() and len(c) >= 6:
        return 'BIN'
    if c.lower() == FLOOR_CODE.lower():
        return 'FLOOR'
    return 'STAGING'


def resolve_location(cur, code):
    """Return location_id for a location code, creating it if new.  Case-insensitive
    (unique on lower(code)).  Bins are numeric >=6 digits; 'MFG Floor' is a FLOOR."""
    if not code or not str(code).strip():
        raise LedgerError('location code is required')
    code = str(code).strip()
    cur.execute(
        """
        INSERT INTO warehouse.inv_location (code, kind)
        VALUES (%s, %s)
        ON CONFLICT (lower(code)) DO UPDATE SET code = warehouse.inv_location.code
        RETURNING location_id
        """,
        (code, _classify(code)),
    )
    return cur.fetchone()[0]


# --------------------------------------------------------------------------- #
# Balance cache maintenance (I1) — written in the caller's transaction
# --------------------------------------------------------------------------- #
def _add(cur, part_id, pcn, location_id, amount):
    """Increment a (part,pcn,location) balance by `amount` (>0)."""
    cur.execute(
        """
        INSERT INTO warehouse.inventory_balance (part_id, pcn_id, location_id, qty)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (part_id, pcn_id, location_id)
        DO UPDATE SET qty = warehouse.inventory_balance.qty + EXCLUDED.qty
        """,
        (part_id, str(pcn), location_id, amount),
    )


def _locked_balance(cur, part_id, pcn, location_id):
    """Current qty at one (part,pcn,location), row locked FOR UPDATE so a caller can
    branch on it and then write without the value changing underneath (I1)."""
    cur.execute(
        """
        SELECT qty FROM warehouse.inventory_balance
        WHERE part_id=%s AND pcn_id=%s AND location_id=%s
        FOR UPDATE
        """,
        (part_id, str(pcn), location_id),
    )
    row = cur.fetchone()
    return row[0] if row else 0


def _subtract(cur, part_id, pcn, location_id, amount, where='source'):
    """Decrement a balance by `amount`, locking the row first and verifying it holds
    enough (I1).  Rejects an over-pick instead of driving the balance negative."""
    cur.execute(
        """
        SELECT qty FROM warehouse.inventory_balance
        WHERE part_id=%s AND pcn_id=%s AND location_id=%s
        FOR UPDATE
        """,
        (part_id, str(pcn), location_id),
    )
    row = cur.fetchone()
    have = row[0] if row else 0
    if have < amount:
        raise LedgerError(
            f'insufficient stock at {where}: have {have}, need {amount} '
            f'(pcn {pcn}, location {location_id})'
        )
    cur.execute(
        """
        UPDATE warehouse.inventory_balance SET qty = qty - %s
        WHERE part_id=%s AND pcn_id=%s AND location_id=%s
        """,
        (amount, part_id, str(pcn), location_id),
    )


def _record(cur, txn_type, part_id, pcn, qty, from_loc, to_loc,
            created_by='system', wo=None, po=None, cost=None, note=None,
            reverses_txn_id=None):
    cur.execute(
        """
        INSERT INTO warehouse.inventory_txn
            (txn_type, part_id, pcn_id, qty, from_location_id, to_location_id,
             created_by, wo, po, cost, note, reverses_txn_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING txn_id
        """,
        (txn_type, part_id, str(pcn), qty, from_loc, to_loc,
         created_by, wo, po, cost, note, reverses_txn_id),
    )
    return cur.fetchone()[0]


# --------------------------------------------------------------------------- #
# Public operations
# --------------------------------------------------------------------------- #
def stock(cur, item, mpn, pcn, qty, to_bin, *, user='system', wo=None, po=None,
          cost=None, note=None):
    """Receive `qty` into `to_bin` (external -> bin)."""
    qty = _qty(qty)
    part_id = resolve_part(cur, item, mpn)
    to_loc = resolve_location(cur, to_bin)
    _add(cur, part_id, pcn, to_loc, qty)
    return _record(cur, 'STOCK', part_id, pcn, qty, None, to_loc,
                   created_by=user, wo=wo, po=po, cost=cost, note=note)


def pick(cur, item, mpn, pcn, qty, from_bin, *, to_floor=FLOOR_CODE, user='system',
         wo=None, note=None):
    """PICK = transfer bin -> floor in ONE txn (I2).  Bin decrements, floor
    increments, total conserved.  Over-pick is rejected (I1)."""
    qty = _qty(qty)
    part_id = resolve_part(cur, item, mpn)
    from_loc = resolve_location(cur, from_bin)
    to_loc = resolve_location(cur, to_floor)
    if from_loc == to_loc:
        raise LedgerError('pick source and destination are the same location')
    _subtract(cur, part_id, pcn, from_loc, qty, where=f'bin {from_bin}')
    _add(cur, part_id, pcn, to_loc, qty)
    return _record(cur, 'PICK', part_id, pcn, qty, from_loc, to_loc,
                   created_by=user, wo=wo, note=note)


def restock(cur, item, mpn, pcn, qty, to_bin, *, from_floor=FLOOR_CODE, user='system',
            note=None):
    """RESTOCK = transfer floor -> bin in ONE txn (I2).  Floor decrements in the same
    transaction, so it can never be left un-zeroed; the bin the pick emptied gets it
    back (190 returns as 190, not 3190)."""
    qty = _qty(qty)
    part_id = resolve_part(cur, item, mpn)
    from_loc = resolve_location(cur, from_floor)
    to_loc = resolve_location(cur, to_bin)
    if from_loc == to_loc:
        raise LedgerError('restock source and destination are the same location')
    _subtract(cur, part_id, pcn, from_loc, qty, where='MFG Floor')
    _add(cur, part_id, pcn, to_loc, qty)
    return _record(cur, 'RESTOCK', part_id, pcn, qty, from_loc, to_loc,
                   created_by=user, note=note)


def found(cur, item, mpn, pcn, qty, to_bin, *, user='system', note=None):
    """FOUND = `qty` units physically exist and are entering `to_bin`, but the ledger
    did NOT believe they were on the floor (external -> bin).

    This is the counterpart to consume(): CONSUME is stock the ledger thinks exists
    but doesn't, FOUND is stock that exists but the ledger doesn't know about.  Both
    exist because the floor balance is an INFERENCE (no consumption event for years,
    plus the >6mo stale-floor sweep), and an inference is wrong in both directions.

    It is a DISTINCT type rather than a silent top-up inside restock() on purpose:
    units that appear from nowhere stay LABELLED as appearing from nowhere, so the
    phantom-stock guard is preserved and each row is a measurable place where the
    floor inference was wrong.  Over-restock can no longer be REJECTED (the parts are
    in the operator's hand), so instead it is RECORDED."""
    qty = _qty(qty)
    part_id = resolve_part(cur, item, mpn)
    to_loc = resolve_location(cur, to_bin)
    _add(cur, part_id, pcn, to_loc, qty)
    return _record(cur, 'FOUND', part_id, pcn, qty, None, to_loc,
                   created_by=user, note=note)


def restock_physical(cur, item, mpn, pcn, qty, to_bin, *, from_floor=FLOOR_CODE,
                     user='system', note=None):
    """Restock `qty` units the operator is physically holding into `to_bin`.

    The operator's hands are the authority here, not the floor balance, so this NEVER
    rejects for a short floor (that rejection is what blocked Theresa on PCN 38159).
    It splits the movement by what the ledger can actually account for:

        transfer = min(floor_balance, qty)  -> RESTOCK (floor -> bin), conserving
        shortfall = qty - transfer          -> FOUND    (external -> bin), labelled

    So the honest case (floor holds the parts) is byte-for-byte the old behaviour, and
    only the units the ledger genuinely can't account for get the FOUND label.  Both
    rows land in the caller's ONE transaction (I2).

    Use this for the operator-facing restock path ONLY.  Automated reversals must keep
    using the strict restock() — a reversal that mints stock is a bug, not a find.

    Returns {'transferred': int, 'found': int, 'txn_ids': [int, ...]}.
    """
    qty = _qty(qty)
    part_id = resolve_part(cur, item, mpn)
    from_loc = resolve_location(cur, from_floor)
    to_loc = resolve_location(cur, to_bin)
    if from_loc == to_loc:
        raise LedgerError('restock source and destination are the same location')

    on_floor = _locked_balance(cur, part_id, pcn, from_loc)
    transfer = min(on_floor, qty) if on_floor > 0 else 0
    shortfall = qty - transfer
    txn_ids = []

    if transfer:
        _subtract(cur, part_id, pcn, from_loc, transfer, where='MFG Floor')
        _add(cur, part_id, pcn, to_loc, transfer)
        txn_ids.append(_record(cur, 'RESTOCK', part_id, pcn, transfer, from_loc, to_loc,
                               created_by=user, note=note))
    if shortfall:
        found_note = (
            f'restock of {qty} exceeded MFG Floor balance {on_floor}; '
            f'{shortfall} booked as physically found'
        )
        txn_ids.append(found(cur, item, mpn, pcn, shortfall, to_bin, user=user,
                             note=f'{note}; {found_note}' if note else found_note))

    return {'transferred': transfer, 'found': shortfall, 'txn_ids': txn_ids}


def ship(cur, item, mpn, pcn, qty, from_location, *, txn_type='SHIP', user='system',
         wo=None, note=None):
    """Consume/remove `qty` out of the system (location -> external).  Used for
    SHIP / PURGE / SCRAP."""
    qty = _qty(qty)
    if txn_type not in ('SHIP', 'PURGE', 'SCRAP'):
        raise LedgerError(f'ship() bad txn_type {txn_type}')
    part_id = resolve_part(cur, item, mpn)
    from_loc = resolve_location(cur, from_location)
    _subtract(cur, part_id, pcn, from_loc, qty, where=str(from_location))
    return _record(cur, txn_type, part_id, pcn, qty, from_loc, None,
                   created_by=user, wo=wo, note=note)


def consume(cur, item, mpn, pcn, qty, *, from_location=FLOOR_CODE, user='system',
            wo=None, note=None):
    """Record production CONSUMPTION of `qty` off the floor (floor -> out of system).

    This is the event KOSH never had (see app._floor_janitor): parts picked bin->floor
    for a job are eaten when the job runs, but nothing decremented the floor, so floor
    counts froze forever (the 'stale MFG-Floor phantom'). CONSUME closes that gap: it is
    a transfer OUT (like ship) that lowers the floor and conserves nothing (the parts
    leave the system). Over-consume is rejected (I1); history is preserved (I5)."""
    qty = _qty(qty)
    part_id = resolve_part(cur, item, mpn)
    from_loc = resolve_location(cur, from_location)
    _subtract(cur, part_id, pcn, from_loc, qty, where=str(from_location))
    return _record(cur, 'CONSUME', part_id, pcn, qty, from_loc, None,
                   created_by=user, wo=wo, note=note)


def adjust(cur, item, mpn, pcn, delta, location, *, user='system', note=None):
    """Manual signed correction at ONE location (I7).  delta>0 raises, delta<0 lowers.
    A single edit can never fill two places."""
    if delta == 0:
        raise LedgerError('adjust delta must be non-zero')
    part_id = resolve_part(cur, item, mpn)
    loc = resolve_location(cur, location)
    amount = _qty(abs(int(delta)))
    if delta > 0:
        _add(cur, part_id, pcn, loc, amount)
        return _record(cur, 'ADJUST', part_id, pcn, amount, None, loc,
                       created_by=user, note=note)
    _subtract(cur, part_id, pcn, loc, amount, where=str(location))
    return _record(cur, 'ADJUST', part_id, pcn, amount, loc, None,
                   created_by=user, note=note)


def set_balance(cur, item, mpn, pcn, target_qty, location, *, user='system', note=None):
    """Set the on-hand at ONE location to an absolute value via an ADJUST for the
    difference (I7).  This is the 'manual warehouse edit' path — it can only touch the
    one location named, so it can never desync a second place."""
    target_qty = int(target_qty)
    if target_qty < 0:
        raise LedgerError('target qty cannot be negative')
    part_id = resolve_part(cur, item, mpn)
    loc = resolve_location(cur, location)
    cur.execute(
        "SELECT qty FROM warehouse.inventory_balance "
        "WHERE part_id=%s AND pcn_id=%s AND location_id=%s FOR UPDATE",
        (part_id, str(pcn), loc),
    )
    row = cur.fetchone()
    current = row[0] if row else 0
    delta = target_qty - current
    if delta == 0:
        return None
    return adjust(cur, item, mpn, pcn, delta, location, user=user,
                  note=note or f'manual set to {target_qty}')


def set_pcn_snapshot(cur, item, mpn, pcn, bin_code, bin_qty, floor_qty, *, user='system'):
    """Apply a manual warehouse edit as ADJUST rows at ONE available location + the
    floor (I7).  Makes the PCN's balances exactly: `bin_code` = bin_qty (every OTHER
    non-floor location zeroed, so an edit can't fill two places), MFG Floor = floor_qty.
    Each of bin_qty / floor_qty may be None to leave that side unchanged.  History is
    preserved — every change is an ADJUST, never an in-place overwrite (I5)."""
    if bin_qty is not None:
        # Zero any other non-floor location so the available stock lands in ONE place.
        cur.execute(
            """
            SELECT l.code FROM warehouse.inventory_balance b
            JOIN warehouse.inv_location l USING (location_id)
            WHERE b.pcn_id=%s AND l.kind<>'FLOOR' AND b.qty>0
            """,
            (str(pcn),),
        )
        others = [c[0] for c in cur.fetchall()]
        for code in others:
            if bin_code and code.strip().lower() == str(bin_code).strip().lower():
                continue
            set_balance(cur, item, mpn, pcn, 0, code, user=user, note='manual edit (moved)')
        if bin_code:
            set_balance(cur, item, mpn, pcn, bin_qty, bin_code, user=user, note='manual edit')
    if floor_qty is not None:
        set_balance(cur, item, mpn, pcn, floor_qty, FLOOR_CODE, user=user, note='manual edit')


def relabel_pcn(cur, pcn, new_item, new_mpn, *, user='system'):
    """Re-file a PCN's balances onto (new_item, new_mpn) after a part number change.

    A relabel is metadata, NOT a stock movement (I8): the parts never leave the bin, so
    this writes NO inventory_txn row and changes NO quantity — it only corrects *which
    part* the existing balance is filed under.  Booking a relabel as a qty movement is
    exactly what minted the 15.3M phantom units behind the 2026-06 reconcile; the total
    before and after this call is identical by construction.

    Needed because a balance is keyed (part_id, pcn_id, location_id) while the legacy
    snapshot is keyed by pcn alone.  Renaming only the snapshot leaves the balance under
    the OLD part_id, so pick resolves the new name to a different part_id, finds no row,
    and reports "insufficient stock … have 0" against a bin that is not empty (bug 28).

    Returns (rows_moved, qty_moved).
    """
    new_part_id = resolve_part(cur, new_item, new_mpn)
    cur.execute(
        """
        SELECT part_id, location_id, qty FROM warehouse.inventory_balance
        WHERE pcn_id = %s AND part_id <> %s
        ORDER BY part_id, location_id
        FOR UPDATE
        """,
        (str(pcn), new_part_id),
    )
    stale = cur.fetchall()
    moved_qty = 0
    for old_part_id, location_id, qty in stale:
        # Delete first, then _add: if the PCN already holds stock at this location under
        # the new part, the two must MERGE into one row, not collide on the PK.
        cur.execute(
            """
            DELETE FROM warehouse.inventory_balance
            WHERE part_id=%s AND pcn_id=%s AND location_id=%s
            """,
            (old_part_id, str(pcn), location_id),
        )
        if qty:
            _add(cur, new_part_id, pcn, location_id, qty)
            moved_qty += int(qty)
    return len(stale), moved_qty


def zero_out(cur, pcn, *, user='system', note='pcn removed'):
    """Drive a PCN's on-hand to 0 by appending an ADJUST-out at every location that
    still holds stock (I5: history preserved — we never DELETE ledger rows).  After
    this the ledger replay nets to 0, so Warehouse and PCN History agree at 0."""
    cur.execute(
        """
        SELECT p.item_raw, p.mpn_raw, l.code, b.qty
        FROM warehouse.inventory_balance b
        JOIN warehouse.inv_part p USING (part_id)
        JOIN warehouse.inv_location l USING (location_id)
        WHERE b.pcn_id=%s AND b.qty>0
        """,
        (str(pcn),),
    )
    rows = cur.fetchall()
    for item_raw, mpn_raw, code, qty in rows:
        adjust(cur, item_raw, mpn_raw, pcn, -int(qty), code, user=user, note=note)
    return len(rows)


def reverse(cur, txn_id, *, user='system'):
    """Reverse a ledger row (I5): flag it reversed=true and apply the inverse to the
    balance in the same transaction.  History is never deleted."""
    cur.execute(
        "SELECT txn_type, part_id, pcn_id, qty, from_location_id, to_location_id, "
        "reversed FROM warehouse.inventory_txn WHERE txn_id=%s FOR UPDATE",
        (txn_id,),
    )
    row = cur.fetchone()
    if not row:
        raise LedgerError(f'txn {txn_id} not found')
    ttype, part_id, pcn, qty, from_loc, to_loc, already = row
    if already:
        raise LedgerError(f'txn {txn_id} already reversed')
    # Inverse: whatever the original added, remove; whatever it removed, add back.
    if to_loc is not None:
        _subtract(cur, part_id, pcn, to_loc, qty, where='reversal target')
    if from_loc is not None:
        _add(cur, part_id, pcn, from_loc, qty)
    cur.execute(
        "UPDATE warehouse.inventory_txn "
        "SET reversed=true, reversed_at=now(), note=COALESCE(note,'')||%s "
        "WHERE txn_id=%s",
        (f' [reversed by {user}]', txn_id),
    )
    return txn_id


# --------------------------------------------------------------------------- #
# Reads — Warehouse Inventory and PCN History both derive from this one ledger (I3)
# --------------------------------------------------------------------------- #
def project_warehouse(cur, pcn):
    """Rebuild the legacy tblWhse_Inventory row(s) for `pcn` FROM the ledger balance,
    in the caller's transaction.  This makes the old snapshot a same-transaction
    *projection* of the one ledger (a read cache), never an independent number: it is
    overwritten from inventory_balance on every write and no background job touches it,
    so onhandqty/mfg_qty can never drift from the ledger.  Legacy reads keep working
    during the read-migration; the columns are slated for removal once every read is on
    inventory_balance.

    Projection rule (I2 breakdown of the ONE number):
      onhandqty = SUM(available balances = everything NOT on the MFG Floor:
                      bins + staging like Count Area / Receiving / Stock Room)
      mfg_qty   = SUM(FLOOR balances)
      loc_to    = the available location holding the most (bin-first primary location)
    """
    cur.execute(
        """
        WITH bal AS (
            SELECT b.qty, l.kind, l.code
            FROM warehouse.inventory_balance b
            JOIN warehouse.inv_location l USING (location_id)
            WHERE b.pcn_id = %s AND b.qty > 0
        ),
        agg AS (
            SELECT COALESCE(SUM(qty) FILTER (WHERE kind<>'FLOOR'),0) AS bin_qty,
                   COALESCE(SUM(qty) FILTER (WHERE kind='FLOOR'),0)  AS floor_qty,
                   (SELECT code FROM bal WHERE kind<>'FLOOR'
                    ORDER BY (kind='BIN') DESC, qty DESC LIMIT 1) AS primary_loc
            FROM bal
        )
        UPDATE warehouse."tblWhse_Inventory" w
        SET onhandqty = a.bin_qty,
            mfg_qty   = a.floor_qty::text,
            loc_to    = COALESCE(a.primary_loc, w.loc_to),
            migrated_at = CURRENT_TIMESTAMP
        FROM agg a
        WHERE w.pcn::text = %s
        """,
        (str(pcn), str(pcn)),
    )


def on_hand(cur, pcn):
    """Total on-hand for a pcn = SUM(qty) across all its locations.  ONE number."""
    cur.execute(
        "SELECT COALESCE(SUM(qty),0) FROM warehouse.inventory_balance WHERE pcn_id=%s",
        (str(pcn),),
    )
    return int(cur.fetchone()[0])


def breakdown(cur, pcn):
    """Per-location breakdown for a pcn, bin-first (so the display shows the real bin,
    not 'MFG Floor').  Returns list of (code, kind, qty)."""
    cur.execute(
        """
        SELECT l.code, l.kind, b.qty
        FROM warehouse.inventory_balance b
        JOIN warehouse.inv_location l USING (location_id)
        WHERE b.pcn_id=%s AND b.qty > 0
        ORDER BY (l.kind='BIN') DESC, b.qty DESC
        """,
        (str(pcn),),
    )
    return cur.fetchall()
