#!/usr/bin/env python3
"""Reconcile only PCNs that had transaction activity in the last N days.

Default: last 2 days (yesterday + today). This is targeted so we do not
resurrect legacy zeroed-out inventory. Uses the same math as the background
reconcile thread and writes full audit rows.

Usage:
    python reconcile_recent.py --days 2 --dry-run
    python reconcile_recent.py --days 2 --apply
"""
import os
import sys
import argparse
import psycopg2

SQL = """
WITH recent_pcns AS (
    SELECT DISTINCT pcn::text AS pcn, LOWER(TRIM(COALESCE(mpn,''))) AS mpn_key
    FROM pcb_inventory."tblTransaction"
    WHERE COALESCE(reversed, false) = false
      AND (
          -- tran_time newer than cutoff (handles MM/DD/YY format)
          CASE
              WHEN tran_time ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN tran_time::timestamptz
              WHEN tran_time ~ '^[0-9]{2}/[0-9]{2}/[0-9]{2}\\s+[0-9]{2}:[0-9]{2}' THEN TO_TIMESTAMP(tran_time, 'MM/DD/YY HH24:MI:SS')
              ELSE NULL
          END >= NOW() - (%s || ' days')::interval
      )
),
last_rndt AS (
    SELECT DISTINCT ON (pcn::text, LOWER(TRIM(COALESCE(mpn,''))))
           pcn::text AS pcn, LOWER(TRIM(COALESCE(mpn,''))) AS mpn_key,
           id AS rndt_id, tranqty::integer AS rndt_qty
    FROM pcb_inventory."tblTransaction"
    WHERE trantype = 'RNDT' AND COALESCE(reversed, false) = false
      AND tranqty ~ '^-?[0-9]+$'
    ORDER BY pcn::text, LOWER(TRIM(COALESCE(mpn,''))), id DESC
),
net AS (
    SELECT t.pcn::text AS pcn, LOWER(TRIM(COALESCE(t.mpn,''))) AS mpn_key,
           GREATEST(0,
             COALESCE(MAX(r.rndt_qty), 0)
             + SUM(CASE
                 WHEN t.trantype = 'INDF' THEN t.tranqty::integer
                 WHEN t.trantype = 'STOCK' THEN t.tranqty::integer
                 WHEN t.trantype = 'PCN Generation' THEN t.tranqty::integer
                 WHEN t.trantype = 'RESTOCK' THEN t.tranqty::integer
                 WHEN t.trantype = 'ADJT' THEN t.tranqty::integer
                 WHEN t.trantype = 'PICK' THEN -t.tranqty::integer
                 WHEN t.trantype = 'PURGE' THEN -t.tranqty::integer
                 ELSE 0 END)
           ) AS qty
    FROM pcb_inventory."tblTransaction" t
    LEFT JOIN last_rndt r
      ON t.pcn::text = r.pcn AND LOWER(TRIM(COALESCE(t.mpn,''))) = r.mpn_key
    WHERE COALESCE(t.reversed, false) = false
      AND t.tranqty ~ '^-?[0-9]+$'
      AND (r.rndt_id IS NULL OR t.id >= r.rndt_id)
    GROUP BY t.pcn::text, LOWER(TRIM(COALESCE(t.mpn,'')))
)
SELECT w.id, w.pcn::text, w.item, w.mpn,
       w.onhandqty AS stored, n.qty AS expected,
       (n.qty - w.onhandqty) AS delta
FROM pcb_inventory."tblWhse_Inventory" w
JOIN recent_pcns rp
  ON w.pcn::text = rp.pcn AND LOWER(TRIM(COALESCE(w.mpn,''))) = rp.mpn_key
JOIN net n
  ON w.pcn::text = n.pcn AND LOWER(TRIM(COALESCE(w.mpn,''))) = n.mpn_key
WHERE w.onhandqty IS DISTINCT FROM n.qty
ORDER BY ABS(n.qty - w.onhandqty) DESC
"""


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--days', type=int, default=2)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--dry-run', action='store_true')
    g.add_argument('--apply', action='store_true')
    a = p.parse_args()

    db_url = os.environ.get('DATABASE_URL') or sys.exit('DATABASE_URL not set')
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pcb_inventory."tblReconcileAudit" (
                id SERIAL PRIMARY KEY,
                pcn text, item text, mpn text,
                prior_qty integer, new_qty integer,
                source text, reconciled_at timestamptz DEFAULT NOW()
            )
        """)
        conn.commit()
        cur.execute(SQL, (str(a.days),))
        rows = cur.fetchall()
        print(f'Found {len(rows)} mismatches in PCNs touched in last {a.days} days\n')
        if not rows:
            return
        print(f'{"PCN":<10} {"Item":<20} {"MPN":<30} {"Stored":>8} {"Expected":>10} {"Delta":>8}')
        print('-' * 90)
        for _, pcn, item, mpn, stored, expected, delta in rows:
            print(f'{pcn:<10} {(item or "")[:19]:<20} {(mpn or "")[:29]:<30} '
                  f'{stored:>8} {expected:>10} {delta:>+8}')
        if a.apply:
            print(f'\nApplying {len(rows)} fixes...')
            for rid, pcn, item, mpn, stored, expected, _ in rows:
                cur.execute("""
                    INSERT INTO pcb_inventory."tblReconcileAudit"
                        (pcn, item, mpn, prior_qty, new_qty, source)
                    VALUES (%s, %s, %s, %s, %s, 'recent_fix')
                """, (pcn, item, mpn, stored, expected))
                cur.execute('UPDATE pcb_inventory."tblWhse_Inventory" SET onhandqty=%s WHERE id=%s',
                            (expected, rid))
            conn.commit()
            print(f'Applied {len(rows)} fixes + audit rows written.')
        else:
            print(f'\nDRY-RUN — no changes made. Rerun with --apply to fix.')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
