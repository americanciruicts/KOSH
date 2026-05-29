#!/usr/bin/env python3
"""One-time inventory reconciliation script.

Walks every (pcn, mpn) in tblWhse_Inventory, recomputes the expected
onhandqty from tblTransaction (using the same logic as the background
sync, including ADJT), and reports + optionally fixes any mismatch.

Usage:
    python reconcile_inventory.py --dry-run     # show mismatches only
    python reconcile_inventory.py --apply       # apply fixes and audit each

Every change is written to tblReconcileAudit with source='manual_script'.
"""
import os
import sys
import argparse
from datetime import datetime

import psycopg2

RECONCILE_SQL = """
WITH last_rndt AS (
    SELECT DISTINCT ON (pcn::text, LOWER(TRIM(COALESCE(mpn,''))))
           pcn::text AS pcn,
           LOWER(TRIM(COALESCE(mpn,''))) AS mpn_key,
           id AS rndt_id,
           tranqty::integer AS rndt_qty
    FROM pcb_inventory."tblTransaction"
    WHERE trantype = 'RNDT'
      AND COALESCE(reversed, false) = false
      AND tranqty ~ '^-?[0-9]+$'
    ORDER BY pcn::text, LOWER(TRIM(COALESCE(mpn,''))), id DESC
),
activity AS (
    SELECT pcn::text AS pcn,
           LOWER(TRIM(COALESCE(mpn,''))) AS mpn_key,
           SUM(CASE WHEN trantype = 'PICK' THEN 1 ELSE 0 END) AS pick_count,
           COUNT(*) FILTER (WHERE trantype IN ('RNDT','RESTOCK','ADJT')) AS touch_count
    FROM pcb_inventory."tblTransaction"
    WHERE COALESCE(reversed, false) = false
      AND tranqty ~ '^-?[0-9]+$'
    GROUP BY pcn::text, LOWER(TRIM(COALESCE(mpn,'')))
),
net AS (
    SELECT t.pcn::text AS pcn,
           LOWER(TRIM(COALESCE(t.mpn,''))) AS mpn_key,
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
                 ELSE 0
               END)
           ) AS qty
    FROM pcb_inventory."tblTransaction" t
    LEFT JOIN last_rndt r
      ON t.pcn::text = r.pcn
     AND LOWER(TRIM(COALESCE(t.mpn,''))) = r.mpn_key
    WHERE COALESCE(t.reversed, false) = false
      AND t.tranqty ~ '^-?[0-9]+$'
      AND (r.rndt_id IS NULL OR t.id >= r.rndt_id)
    GROUP BY t.pcn::text, LOWER(TRIM(COALESCE(t.mpn,'')))
)
SELECT w.id, w.pcn::text AS pcn, w.item, w.mpn,
       w.onhandqty AS stored_qty, n.qty AS expected_qty,
       (n.qty - w.onhandqty) AS delta
FROM pcb_inventory."tblWhse_Inventory" w
JOIN net n
  ON w.pcn::text = n.pcn
 AND LOWER(TRIM(COALESCE(w.mpn,''))) = n.mpn_key
JOIN activity a
  ON a.pcn = n.pcn AND a.mpn_key = n.mpn_key
WHERE w.onhandqty IS DISTINCT FROM n.qty
  AND (a.pick_count > 0 OR a.touch_count > 0)
ORDER BY ABS(n.qty - w.onhandqty) DESC
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument('--dry-run', action='store_true',
                     help='Report mismatches without modifying data')
    grp.add_argument('--apply', action='store_true',
                     help='Apply fixes and write audit records')
    args = parser.parse_args()

    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        sys.exit('DATABASE_URL not set')

    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pcb_inventory."tblReconcileAudit" (
                id SERIAL PRIMARY KEY,
                pcn text, item text, mpn text,
                prior_qty integer, new_qty integer,
                source text,
                reconciled_at timestamptz DEFAULT NOW()
            )
        """)
        conn.commit()

        cur.execute(RECONCILE_SQL)
        rows = cur.fetchall()
        print(f'Found {len(rows)} mismatches\n')

        if not rows:
            return

        print(f'{"PCN":<10} {"Item":<20} {"MPN":<30} {"Stored":>8} {"Expected":>10} {"Delta":>8}')
        print('-' * 90)
        for _, pcn, item, mpn, stored, expected, delta in rows[:50]:
            print(f'{pcn:<10} {(item or "")[:19]:<20} {(mpn or "")[:29]:<30} '
                  f'{stored:>8} {expected:>10} {delta:>+8}')
        if len(rows) > 50:
            print(f'... and {len(rows) - 50} more')

        if args.apply:
            print(f'\nApplying {len(rows)} fixes...')
            for row_id, pcn, item, mpn, stored, expected, _ in rows:
                cur.execute("""
                    INSERT INTO pcb_inventory."tblReconcileAudit"
                        (pcn, item, mpn, prior_qty, new_qty, source)
                    VALUES (%s, %s, %s, %s, %s, 'manual_script')
                """, (pcn, item, mpn, stored, expected))
                cur.execute("""
                    UPDATE pcb_inventory."tblWhse_Inventory"
                    SET onhandqty = %s
                    WHERE id = %s
                """, (expected, row_id))
            conn.commit()
            print(f'Applied {len(rows)} fixes. Audit rows written to tblReconcileAudit.')
        else:
            print(f'\nDRY-RUN: no changes made. Rerun with --apply to fix.')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
