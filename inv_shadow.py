"""KOSH inventory shadow-sync (Phase 4a).

Keeps the new event-derived on-hand projection (`pcb_inventory.inv_onhand`, built
on the append-only `inv_event` ledger) aligned to the AUTHORITATIVE warehouse
(`tblWhse_Inventory`) in near-real-time, by emitting typed ADJUST events for any
per-(pcn, location) difference.

Design guarantees (why this is safe to run against the LIVE prod DB while users work):
  * It touches NO user write path — stock/pick/restock/purge are completely unchanged.
    This runs in its own background thread with its own pooled connection.
  * It only READS the live tables (tblWhse_Inventory, tblTransaction) with ACCESS
    SHARE (compatible with the app's INSERT/UPDATE) and only WRITES to the new
    inv_* tables. `lock_timeout` keeps it from ever queuing behind a user.
  * It is fail-safe: any error rolls back the whole pass and is logged; the next
    pass retries. It can never raise into the app.
  * It is incremental: after a one-time full pass it only reconciles PCNs that had
    a NEW transaction since the last pass (watermark on tblTransaction.id), so each
    pass is tiny.

This is the shadow mechanism for the build-alongside phase. Reads are NOT cut over
here — the app still serves 100% from the old path. Cutover is a later, separate step.
"""

import threading
import time
import logging

logger = logging.getLogger('app')

# One-time idempotent hardening. A case-insensitive unique index lets us auto-add
# new locations without ever creating a case-duplicate.
_INIT_SQL = (
    'CREATE UNIQUE INDEX IF NOT EXISTS inv_location_lc_uidx '
    'ON pcb_inventory.inv_location (lower(code))',
)

# Auto-register any location referenced by an in-scope warehouse row.
_ENSURE_LOC = """
INSERT INTO pcb_inventory.inv_location(code, kind)
SELECT DISTINCT ON (lower(trim(w.loc_to))) trim(w.loc_to),
   CASE WHEN trim(w.loc_to) ~ '^[0-9]{6,}$' THEN 'BIN'
        WHEN lower(trim(w.loc_to)) = 'mfg floor' THEN 'FLOOR'
        ELSE 'STAGING' END
FROM pcb_inventory."tblWhse_Inventory" w
WHERE trim(coalesce(w.loc_to,'')) <> ''
  AND ( %(full)s OR w.pcn::text IN
        (SELECT DISTINCT pcn::text FROM pcb_inventory."tblTransaction" WHERE id > %(since)s) )
ORDER BY lower(trim(w.loc_to))
ON CONFLICT ((lower(code))) DO NOTHING
"""

# Auto-register any (item, mpn) part referenced by an in-scope warehouse row.
_ENSURE_PART = """
INSERT INTO pcb_inventory.inv_part(item_raw, mpn_raw)
SELECT DISTINCT w.item, w.mpn
FROM pcb_inventory."tblWhse_Inventory" w
WHERE trim(coalesce(w.item,'')) <> ''
  AND ( %(full)s OR w.pcn::text IN
        (SELECT DISTINCT pcn::text FROM pcb_inventory."tblTransaction" WHERE id > %(since)s) )
ON CONFLICT (item_key, mpn_key) DO NOTHING
"""

# The reconcile itself: ADJUST every (pcn, part, location) where the event-derived
# balance differs from the current warehouse. d>0 -> raise (to_location); d<0 -> lower.
_SYNC = """
WITH scope AS (
    SELECT DISTINCT w.pcn::text AS pcn
    FROM pcb_inventory."tblWhse_Inventory" w
    WHERE %(full)s OR w.pcn::text IN
          (SELECT DISTINCT pcn::text FROM pcb_inventory."tblTransaction" WHERE id > %(since)s)
),
wparts AS (
    SELECT w.pcn::text AS pcn, w.item, w.mpn, w.loc_to, w.onhandqty, w.mfg_qty, p.part_id
    FROM pcb_inventory."tblWhse_Inventory" w
    JOIN scope s ON s.pcn = w.pcn::text
    JOIN pcb_inventory.inv_part p
      ON p.item_key = upper(translate(coalesce(w.item,''),'-# ./',''))
     AND p.mpn_key  = upper(translate(coalesce(w.mpn,''), '-# ./',''))
),
target AS (
    SELECT pcn, part_id, code, SUM(qty) AS qty FROM (
        SELECT pcn, part_id,
               CASE WHEN trim(coalesce(loc_to,'')) = '' THEN 'UNKNOWN' ELSE trim(loc_to) END AS code,
               GREATEST(coalesce(onhandqty,0),0) AS qty
        FROM wparts WHERE coalesce(onhandqty,0) > 0
        UNION ALL
        SELECT pcn, part_id, 'MFG Floor', mfg_qty::int
        FROM wparts WHERE mfg_qty ~ '^[1-9][0-9]*$'
    ) u GROUP BY pcn, part_id, code
),
current AS (
    SELECT b.pcn, b.part_id, l.code, b.qty
    FROM pcb_inventory.inv_location_balance b
    JOIN pcb_inventory.inv_location l USING (location_id)
    JOIN scope s ON s.pcn = b.pcn
),
delta AS (
    SELECT COALESCE(t.pcn, c.pcn) AS pcn,
           COALESCE(t.part_id, c.part_id) AS part_id,
           COALESCE(t.code, c.code) AS code,
           COALESCE(t.qty,0) - COALESCE(c.qty,0) AS d
    FROM target t
    FULL JOIN current c
      ON t.pcn = c.pcn AND t.part_id = c.part_id AND lower(t.code) = lower(c.code)
)
INSERT INTO pcb_inventory.inv_event
       (event_type, part_id, pcn, qty, from_location, to_location, created_by, note)
SELECT 'ADJUST', d.part_id, d.pcn, ABS(d.d),
       CASE WHEN d.d < 0 THEN l.location_id END,
       CASE WHEN d.d > 0 THEN l.location_id END,
       'shadow_sync', 'sync warehouse->ledger'
FROM delta d
JOIN pcb_inventory.inv_location l ON lower(l.code) = lower(d.code)
WHERE d.d <> 0
"""

_INTERVAL = 60
_last_id = 0


# ---------------------------------------------------------------------------
# Real-time hook: reconcile inv_onhand to warehouse for a SPECIFIC set of PCNs,
# on the CALLER's open cursor, inside the caller's transaction (no commit here).
# Used by the write paths (pick/restock/stock/purge/reverse) to emit typed events
# at operation time, atomically with the warehouse change. Same delta math as the
# background sync, so the two can never double-count (idempotent: delta 0 -> no-op).
# ---------------------------------------------------------------------------
_ENSURE_LOC_PCNS = """
INSERT INTO pcb_inventory.inv_location(code, kind)
SELECT DISTINCT ON (lower(trim(w.loc_to))) trim(w.loc_to),
   CASE WHEN trim(w.loc_to) ~ '^[0-9]{6,}$' THEN 'BIN'
        WHEN lower(trim(w.loc_to)) = 'mfg floor' THEN 'FLOOR' ELSE 'STAGING' END
FROM pcb_inventory."tblWhse_Inventory" w
WHERE trim(coalesce(w.loc_to,'')) <> '' AND w.pcn::text = ANY(%(pcns)s)
ORDER BY lower(trim(w.loc_to))
ON CONFLICT ((lower(code))) DO NOTHING
"""

_ENSURE_PART_PCNS = """
INSERT INTO pcb_inventory.inv_part(item_raw, mpn_raw)
SELECT DISTINCT w.item, w.mpn
FROM pcb_inventory."tblWhse_Inventory" w
WHERE trim(coalesce(w.item,'')) <> '' AND w.pcn::text = ANY(%(pcns)s)
ON CONFLICT (item_key, mpn_key) DO NOTHING
"""

_SYNC_PCNS = """
WITH scope AS (SELECT DISTINCT p AS pcn FROM unnest(%(pcns)s::text[]) AS p),
wparts AS (
    SELECT w.pcn::text AS pcn, w.item, w.mpn, w.loc_to, w.onhandqty, w.mfg_qty, p.part_id
    FROM pcb_inventory."tblWhse_Inventory" w
    JOIN scope s ON s.pcn = w.pcn::text
    JOIN pcb_inventory.inv_part p
      ON p.item_key = upper(translate(coalesce(w.item,''),'-# ./',''))
     AND p.mpn_key  = upper(translate(coalesce(w.mpn,''), '-# ./',''))
),
target AS (
    SELECT pcn, part_id, code, SUM(qty) AS qty FROM (
        SELECT pcn, part_id,
               CASE WHEN trim(coalesce(loc_to,'')) = '' THEN 'UNKNOWN' ELSE trim(loc_to) END AS code,
               GREATEST(coalesce(onhandqty,0),0) AS qty
        FROM wparts WHERE coalesce(onhandqty,0) > 0
        UNION ALL
        SELECT pcn, part_id, 'MFG Floor', mfg_qty::int FROM wparts WHERE mfg_qty ~ '^[1-9][0-9]*$'
    ) u GROUP BY pcn, part_id, code
),
current AS (
    SELECT b.pcn, b.part_id, l.code, b.qty
    FROM pcb_inventory.inv_location_balance b
    JOIN pcb_inventory.inv_location l USING (location_id)
    JOIN scope s ON s.pcn = b.pcn
),
delta AS (
    SELECT COALESCE(t.pcn,c.pcn) AS pcn, COALESCE(t.part_id,c.part_id) AS part_id,
           COALESCE(t.code,c.code) AS code, COALESCE(t.qty,0) - COALESCE(c.qty,0) AS d
    FROM target t FULL JOIN current c
      ON t.pcn=c.pcn AND t.part_id=c.part_id AND lower(t.code)=lower(c.code)
)
INSERT INTO pcb_inventory.inv_event
       (event_type, part_id, pcn, qty, from_location, to_location, created_by, note)
SELECT %(etype)s, d.part_id, d.pcn, ABS(d.d),
       CASE WHEN d.d < 0 THEN l.location_id END,
       CASE WHEN d.d > 0 THEN l.location_id END,
       %(cby)s, %(note)s
FROM delta d JOIN pcb_inventory.inv_location l ON lower(l.code) = lower(d.code)
WHERE d.d <> 0
"""


def sync_pcns(cur, pcns, event_type='ADJUST', created_by='shadow_sync', note='realtime'):
    """Reconcile inv_onhand to warehouse for `pcns` on an OPEN cursor, emitting
    `event_type` events. Caller owns the transaction (this does NOT commit).
    Returns the number of events written. Raises on error (caller wraps in a
    SAVEPOINT so a failure here can never affect the real operation)."""
    pcns = [str(p) for p in (pcns or []) if p is not None and str(p).strip() != '']
    if not pcns:
        return 0
    cur.execute(_ENSURE_LOC_PCNS, {'pcns': pcns})
    cur.execute(_ENSURE_PART_PCNS, {'pcns': pcns})
    cur.execute(_SYNC_PCNS, {'pcns': pcns, 'etype': event_type, 'cby': created_by, 'note': note})
    return cur.rowcount


def sync_scope(cur, pcns=None, item=None, event_type='ADJUST', created_by='shadow_sync'):
    """Convenience wrapper: sync an explicit PCN list, or ALL PCNs of an item
    (for FIFO picks / purge-all where the specific PCNs aren't known)."""
    if not pcns and item:
        cur.execute('SELECT DISTINCT pcn::text FROM pcb_inventory."tblWhse_Inventory" WHERE item::text ILIKE %s',
                    (item,))
        pcns = [r[0] for r in cur.fetchall()]
    return sync_pcns(cur, pcns, event_type=event_type, created_by=created_by)


def realtime_sync(cur, pcns=None, item=None, event_type='ADJUST', username='system'):
    """Fail-safe real-time hook for the write paths. Wraps sync_scope in a
    SAVEPOINT so ANY error is contained and can never break the user's operation.
    Call right before the operation's conn.commit(), on the same cursor."""
    try:
        cur.execute('SAVEPOINT inv_dw')
        n = sync_scope(cur, pcns=pcns, item=item, event_type=event_type,
                       created_by=(username or 'system'))
        cur.execute('RELEASE SAVEPOINT inv_dw')
        return n
    except Exception as e:
        try:
            cur.execute('ROLLBACK TO SAVEPOINT inv_dw')
        except Exception:
            pass
        logger.warning(f'inv realtime sync skipped: {e}')
        return -1


def sync_once(db, full):
    """Run one reconcile pass on a fresh pooled connection. Returns (adjusts, max_txn_id).
    Never raises."""
    global _last_id
    conn = None
    try:
        conn = db.get_connection()
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute("SET lock_timeout = '3s'")
        cur.execute("SET statement_timeout = '120s'")
        for stmt in _INIT_SQL:
            cur.execute(stmt)
        cur.execute('SELECT COALESCE(MAX(id),0) FROM pcb_inventory."tblTransaction"')
        maxid = cur.fetchone()[0]
        params = {'full': full, 'since': _last_id}
        cur.execute(_ENSURE_LOC, params)
        cur.execute(_ENSURE_PART, params)
        cur.execute(_SYNC, params)
        adjusts = cur.rowcount
        conn.commit()
        _last_id = maxid
        return adjusts, maxid
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.warning(f'inv shadow sync pass skipped: {e}')
        return -1, None
    finally:
        if conn:
            try:
                db.return_connection(conn)
            except Exception:
                pass


# Do a FULL reconcile every Nth pass (~10 min) in addition to the per-pass
# incremental sync. The incremental path only reconciles PCNs that got a NEW
# tblTransaction row, so a DIRECT warehouse edit made without a transaction
# (e.g. an admin SQL correction) would otherwise never be picked up. The periodic
# full sweep makes the shadow self-healing against ANY divergence.
_FULL_EVERY = 10


def _loop(db):
    time.sleep(25)  # let the app settle on boot
    passes = 0
    while True:
        full = (passes % _FULL_EVERY == 0)  # pass 0 (boot) + every ~10 min
        adjusts, _ = sync_once(db, full=full)
        if adjusts > 0:
            logger.info(f'inv shadow sync: {adjusts} adjust event(s) (full={full})')
        if adjusts >= 0:
            passes += 1
        time.sleep(_INTERVAL)


def start_inv_shadow_sync(db):
    """Spawn the shadow-sync daemon. Safe to call once at import time."""
    threading.Thread(target=_loop, args=(db,), daemon=True).start()
    logger.info('inv shadow sync thread started')
