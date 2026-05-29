#!/usr/bin/env python3
"""Backfill missing transactions for EVERY user notification in tblActivityLog.

Covers WAREHOUSE_EDIT, PICK, RESTOCK, STOCK, PURGE, PART_NUMBER_CHANGE.
For each notification, checks whether a matching transaction already exists
in tblTransaction (by pcn + trantype + ±30-min window against the
EST-stored tran_time). Inserts a synthetic transaction only when missing.

All created_at and tran_time are in America/New_York (that's how KOSH writes
both), so we compare them directly as naive timestamps.

Every insert writes a tblReconcileAudit row with source='backfill_notif'.

Usage:
    python backfill_all_notifications.py --dry-run
    python backfill_all_notifications.py --apply
"""
import os
import sys
import re
import argparse
import psycopg2


ACTION_TO_TRANTYPE = {
    'WAREHOUSE_EDIT':     'ADJT',
    'PICK':               'PICK',
    'RESTOCK':            'RESTOCK',
    'STOCK':              'STOCK',
    'PURGE':              'PURGE',
    'PART_NUMBER_CHANGE': 'PN_CHANGE',
}

PCN_RE = re.compile(r'PCN[:\s]+(\d+)', re.IGNORECASE)

ITEM_PATTERNS = [
    re.compile(r'(?:warehouse inventory|units of|records? for)\s*:?\s*([^\s(,]+)', re.IGNORECASE),
    re.compile(r'Restocked\s+\d+\s+units of\s+([^\s(,]+)', re.IGNORECASE),
    re.compile(r'Picked\s+\d+\s+units of\s+([^\s(,]+)', re.IGNORECASE),
    re.compile(r'Stocked\s+\d+\s+units of\s+([^\s(,]+)', re.IGNORECASE),
]

QTY_PATTERNS = {
    # Pick/Restock/Stock/Purge descriptions carry an ACTION quantity
    # ("Picked N units of X") which is a legitimate delta.
    'PICK':            re.compile(r'Picked\s+(\d+)', re.IGNORECASE),
    'RESTOCK':         re.compile(r'Restocked\s+(\d+)', re.IGNORECASE),
    'STOCK':           re.compile(r'Stocked\s+(\d+)', re.IGNORECASE),
    'PURGE':           re.compile(r'Purged\s+(\d+)', re.IGNORECASE),
    # WAREHOUSE_EDIT intentionally has no pattern: "Qty: N" in the notification
    # is the NEW on-hand state, not a delta. Writing it as tranqty corrupts
    # running-balance math. Backfilled ADJT rows carry tranqty=0 and act as
    # audit markers only — the real on-hand is in tblWhse_Inventory already.
    'PART_NUMBER_CHANGE': re.compile(r'(\d+)', re.IGNORECASE),
}


def parse_row(action, desc, details):
    desc = desc or ''
    details = details or ''
    pcn_m = PCN_RE.search(desc) or PCN_RE.search(details)
    pcn = pcn_m.group(1) if pcn_m else None
    item = None
    for pat in ITEM_PATTERNS:
        m = pat.search(desc)
        if m:
            item = m.group(1).rstrip(')').rstrip(',')
            break
    qty = None
    qpat = QTY_PATTERNS.get(action)
    if qpat:
        m = qpat.search(desc) or qpat.search(details)
        if m:
            qty = m.group(1)
    return item, pcn, qty


def main():
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--dry-run', action='store_true')
    g.add_argument('--apply', action='store_true')
    p.add_argument('--action', default=None,
                   help='Restrict to one action_type (else: all)')
    args = p.parse_args()

    db_url = os.environ.get('DATABASE_URL') or sys.exit('DATABASE_URL not set')
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()

        targets = [args.action] if args.action else list(ACTION_TO_TRANTYPE.keys())
        total_inserted = 0
        total_skipped = 0

        for action in targets:
            trantype = ACTION_TO_TRANTYPE.get(action)
            if not trantype:
                continue
            cur.execute("""
                SELECT id, COALESCE(username,''), created_at,
                       COALESCE(description,''), COALESCE(details,'')
                FROM pcb_inventory."tblActivityLog"
                WHERE action_type = %s
                ORDER BY id ASC
            """, (action,))
            rows = cur.fetchall()
            inserted = 0
            skipped = 0
            for aid, username, created_at, desc, details in rows:
                item, pcn, qty_str = parse_row(action, desc, details)
                if not pcn:
                    skipped += 1
                    continue
                # Dedupe: any existing txn of this trantype, same pcn,
                # within ±30 min (generous) — treat tran_time as naive EST,
                # created_at is also EST-naive (see line 2623 default).
                cur.execute("""
                    SELECT 1 FROM pcb_inventory."tblTransaction"
                    WHERE pcn::text = %s AND trantype = %s
                      AND (
                          CASE
                              WHEN tran_time ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                                  THEN tran_time::timestamp
                              WHEN tran_time ~ '^[0-9]{2}/[0-9]{2}/[0-9]{2}\s+[0-9]{2}:[0-9]{2}'
                                  THEN TO_TIMESTAMP(tran_time, 'MM/DD/YY HH24:MI:SS')::timestamp
                              ELSE NULL
                          END
                      ) BETWEEN %s::timestamp - INTERVAL '30 minutes'
                            AND %s::timestamp + INTERVAL '30 minutes'
                    LIMIT 1
                """, (pcn, trantype, created_at, created_at))
                if cur.fetchone():
                    skipped += 1
                    continue

                if args.apply:
                    # WAREHOUSE_EDIT: tranqty=0 (absolute, not a delta). Others
                    # use the real action qty parsed from the description.
                    tq_val = '0' if trantype == 'ADJT' else (qty_str or '0')
                    # Enrich with MPN/DC/MSD/PO/loc from tblWhse_Inventory so
                    # the history row shows the full context of the edit.
                    cur.execute("""
                        SELECT mpn, dc::text, msd, po, loc_to
                        FROM pcb_inventory."tblWhse_Inventory"
                        WHERE pcn::text = %s AND (item::text = %s OR %s = '')
                        LIMIT 1
                    """, (pcn, item or '', item or ''))
                    w = cur.fetchone()
                    w_mpn, w_dc, w_msd, w_po, w_loc = w if w else (None, None, None, None, None)
                    cur.execute("""
                        INSERT INTO pcb_inventory."tblTransaction"
                        (trantype, item, pcn, mpn, dc, msd, tranqty, tran_time,
                         loc_from, loc_to, po, userid)
                        VALUES (%s, %s, %s, %s, %s, %s, %s,
                                TO_CHAR(%s, 'MM/DD/YY HH24:MI:SS'),
                                %s, %s, %s, %s)
                    """, (trantype, item or '', pcn, w_mpn, w_dc, w_msd,
                          tq_val, created_at, None, w_loc, w_po, username))
                    cur.execute("""
                        INSERT INTO pcb_inventory."tblReconcileAudit"
                            (pcn, item, prior_qty, new_qty, source)
                        VALUES (%s, %s, NULL, NULL, 'backfill_notif')
                    """, (pcn, item or ''))
                inserted += 1
            total_inserted += inserted
            total_skipped += skipped
            print(f'{action:<22} → {trantype:<10}  '
                  f'{"inserted" if args.apply else "would insert"}={inserted:>4}  '
                  f'skipped={skipped:>4}  (total={len(rows)})')

        if args.apply:
            conn.commit()
        print()
        verb = 'Inserted' if args.apply else 'Would insert'
        print(f'{verb} {total_inserted} transactions; skipped {total_skipped}')
        if not args.apply:
            print('DRY RUN — rerun with --apply to write data.')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
