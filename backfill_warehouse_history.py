#!/usr/bin/env python3
"""Backfill missing ADJT transactions for recent warehouse edits.

Before this fix, update_warehouse_item only wrote an ADJT when on-hand qty
changed. Location / DC / MSD / PO edits left no transaction row — so PCNs
that Theresa touched (e.g. 42083) show only legacy Access history.

This script scans user_activity_log for WAREHOUSE_EDIT rows in the last N
days and inserts a matching ADJT in tblTransaction for any that lack one.
Idempotent: re-runnable; writes at most one ADJT per activity_log row.
Every backfill also writes a tblReconcileAudit row with source='backfill'.

Usage:
    python backfill_warehouse_history.py --days 3 --dry-run
    python backfill_warehouse_history.py --days 3 --apply
"""
import os
import sys
import argparse
import re
import psycopg2


FIND_SQL = """
SELECT a.id AS activity_id,
       a.username,
       a.created_at,
       a.description,
       a.details
FROM pcb_inventory."tblUserActivity" a
WHERE a.action = 'WAREHOUSE_EDIT'
  AND a.created_at >= NOW() - (%s || ' days')::interval
ORDER BY a.id ASC
"""


PCN_RE = re.compile(r'PCN[:\s]+(\d+)')
ITEM_RE = re.compile(r'warehouse inventory:\s*([^\s(]+)', re.IGNORECASE)


def parse_description(desc, details):
    """Pull (item, pcn, onhand_qty) from the activity log text."""
    text = f'{desc} {details or ""}'
    pcn_m = PCN_RE.search(text)
    item_m = ITEM_RE.search(desc or '')
    qty_m = re.search(r'Qty:\s*([-\d]+)', details or '')
    return (
        item_m.group(1) if item_m else None,
        pcn_m.group(1) if pcn_m else None,
        qty_m.group(1) if qty_m else None,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--days', type=int, default=3)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--dry-run', action='store_true')
    g.add_argument('--apply', action='store_true')
    args = p.parse_args()

    db_url = os.environ.get('DATABASE_URL') or sys.exit('DATABASE_URL not set')
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()

        # Detect column layout of tblActivityLog dynamically.
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='pcb_inventory' AND table_name='tblActivityLog'
        """)
        cols = {r[0] for r in cur.fetchall()}
        if not cols:
            print('ERROR: pcb_inventory."tblActivityLog" not found')
            sys.exit(1)

        # Try the standard column set; fall back if differently named.
        def col(*candidates):
            for c in candidates:
                if c in cols:
                    return c
            return None

        user_col = col('username', 'user_id', 'userid')
        time_col = col('created_at', 'timestamp', 'logged_at')
        action_col = col('action', 'action_type', 'event')
        desc_col = col('description', 'message', 'detail')
        details_col = col('details', 'extra', 'meta')

        if not (user_col and time_col and action_col):
            print(f'ERROR: tblActivityLog missing expected columns. Found: {sorted(cols)}')
            sys.exit(1)

        cur.execute(f"""
            SELECT id,
                   COALESCE({user_col}, ''),
                   {time_col},
                   COALESCE({desc_col or "''"}, '') AS description,
                   COALESCE({details_col or "''"}, '') AS details
            FROM pcb_inventory."tblActivityLog"
            WHERE ({action_col} = 'WAREHOUSE_EDIT' OR {action_col} ILIKE 'warehouse_edit%%')
              AND {time_col} >= NOW() - (%s || ' days')::interval
            ORDER BY id ASC
        """, (str(args.days),))
        rows = cur.fetchall()
        print(f'Found {len(rows)} WAREHOUSE_EDIT activity entries in last {args.days} days')

        inserted = 0
        skipped = 0
        for aid, username, created_at, desc, details in rows:
            item, pcn, qty_str = parse_description(desc, details)
            if not pcn or not item:
                skipped += 1
                continue
            # Skip if an ADJT / ADJT-like row already exists near this timestamp
            cur.execute("""
                SELECT 1 FROM pcb_inventory."tblTransaction"
                WHERE pcn::text = %s AND item::text = %s
                  AND trantype = 'ADJT'
                  AND COALESCE(userid,'') = %s
                  AND COALESCE(tran_ts, NOW()) BETWEEN %s::timestamptz - INTERVAL '3 minutes'
                                                   AND %s::timestamptz + INTERVAL '3 minutes'
                LIMIT 1
            """, (pcn, item, username or '', created_at, created_at))
            if cur.fetchone():
                skipped += 1
                continue

            if args.apply:
                cur.execute("""
                    INSERT INTO pcb_inventory."tblTransaction"
                    (trantype, item, pcn, tranqty, tran_time, userid)
                    VALUES ('ADJT', %s, %s, %s,
                            TO_CHAR(%s AT TIME ZONE 'America/New_York',
                                    'MM/DD/YY HH24:MI:SS'),
                            %s)
                """, (item, pcn, qty_str or '0', created_at, username or ''))
                cur.execute("""
                    INSERT INTO pcb_inventory."tblReconcileAudit"
                        (pcn, item, prior_qty, new_qty, source)
                    VALUES (%s, %s, NULL, NULL, 'backfill_warehouse_edit')
                """, (pcn, item))
            inserted += 1

        if args.apply:
            conn.commit()
            print(f'Inserted {inserted} ADJT rows, skipped {skipped} duplicates/unparsable')
        else:
            print(f'Would insert {inserted}, skip {skipped} — DRY RUN')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
