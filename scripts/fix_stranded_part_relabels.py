"""Bug 28 backfill — re-file stock stranded under a PCN's OLD part number.

Part Number Change renamed only the legacy snapshot and left the ledger balance keyed
to the old part_id, so pick (which resolves part_id from the new name) read 0 against a
full bin, and project_warehouse — which sums by pcn REGARDLESS of part_id — added the
orphan on top of any edit ("expected 80, got 280").

This calls the SHIPPED ledger.relabel_pcn(), never a SQL copy of it: a backfill that
reimplements the fix is a second implementation that can drift from the first.

A relabel is metadata, not a movement (I8) — no inventory_txn qty row is written and
NO quantity changes. Every PCN's total is asserted identical before and after; any
PCN that would change total is rolled back and reported rather than committed.

Reversible: the pre-state of every moved row is recorded in
warehouse.part_relabel_fix_audit before anything is written.

  Dry run (default, rolls back):  python scripts/fix_stranded_part_relabels.py
  Apply to kosh_test:             python scripts/fix_stranded_part_relabels.py --apply
  Apply to production:            python scripts/fix_stranded_part_relabels.py --apply --db kosh
"""
import argparse
import os
import sys

sys.path.insert(0, '/app')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import psycopg2  # noqa: E402

import ledger  # noqa: E402

AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS warehouse.part_relabel_fix_audit (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pcn_id       text        NOT NULL,
    old_part_id  bigint      NOT NULL,
    old_item     text,
    new_item     text,
    location_id  bigint      NOT NULL,
    qty          integer     NOT NULL,
    fixed_at     timestamptz NOT NULL DEFAULT now(),
    fix_tag      text        NOT NULL
)
"""

# PCNs whose ledger balance is filed under an item that is not the snapshot's item.
STRANDED_SQL = """
SELECT w.pcn::text AS pcn, min(w.item) AS snapshot_item, min(w.mpn) AS snapshot_mpn,
       count(DISTINCT btrim(lower(w.item))) AS distinct_snapshot_items,
       sum(b.qty) AS stranded_qty
FROM warehouse."tblWhse_Inventory" w
JOIN warehouse.inventory_balance b ON b.pcn_id = w.pcn::text
JOIN warehouse.inv_part p USING (part_id)
WHERE b.qty > 0 AND btrim(lower(p.item_raw)) <> btrim(lower(w.item))
GROUP BY w.pcn
ORDER BY w.pcn
"""


def total_for(cur, pcn):
    cur.execute('SELECT COALESCE(SUM(qty),0) FROM warehouse.inventory_balance WHERE pcn_id=%s',
                (pcn,))
    return cur.fetchone()[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='commit (default: dry run, rolls back)')
    ap.add_argument('--db', default=os.environ.get('POSTGRES_DB', 'kosh_test'))
    ap.add_argument('--tag', default='bug28_part_relabel_20260716')
    args = ap.parse_args()

    conn = psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST', 'aci-database'),
        dbname=args.db,
        user=os.environ.get('POSTGRES_USER', 'aci'),
        password=os.environ.get('POSTGRES_PASSWORD'),
    )
    conn.autocommit = False
    cur = conn.cursor()

    print(f'target db : {args.db}')
    print(f'mode      : {"APPLY (will commit)" if args.apply else "DRY RUN (will roll back)"}\n')

    cur.execute(AUDIT_DDL)
    cur.execute(STRANDED_SQL)
    stranded = cur.fetchall()
    if not stranded:
        print('Nothing stranded — no PCN has balance filed under a foreign part number.')
        conn.rollback()
        return 0

    fixed = skipped = 0
    total_units = 0
    for pcn, item, mpn, distinct_items, stranded_qty in stranded:
        if distinct_items > 1:
            print(f'  SKIP pcn {pcn}: snapshot has {distinct_items} different items — '
                  f'ambiguous which one is current; needs a human.')
            skipped += 1
            continue

        before = total_for(cur, pcn)

        # Record the pre-state of exactly the rows relabel_pcn is about to move.
        cur.execute(
            """
            INSERT INTO warehouse.part_relabel_fix_audit
                (pcn_id, old_part_id, old_item, new_item, location_id, qty, fix_tag)
            SELECT b.pcn_id, b.part_id, p.item_raw, %s, b.location_id, b.qty, %s
            FROM warehouse.inventory_balance b
            JOIN warehouse.inv_part p USING (part_id)
            WHERE b.pcn_id = %s AND btrim(lower(p.item_raw)) <> btrim(lower(%s))
            """,
            (item, args.tag, pcn, item),
        )

        rows, moved = ledger.relabel_pcn(cur, pcn, item, mpn, user=args.tag)
        ledger.project_warehouse(cur, pcn)

        after = total_for(cur, pcn)
        if after != before:
            # A relabel that changes a total is a bug, not a fix. Refuse the whole run.
            conn.rollback()
            print(f'\n!! ABORTED on pcn {pcn}: total changed {before} -> {after}. '
                  f'A relabel must be quantity-neutral. Nothing was committed.')
            return 2

        print(f'  pcn {pcn:>6}: {rows} location(s), {moved:>5} units -> {item!r} '
              f'(total {before} unchanged)')
        fixed += 1
        total_units += moved

    print(f'\n{fixed} PCN(s) re-filed, {total_units} units, {skipped} skipped.')

    if args.apply:
        conn.commit()
        print(f'COMMITTED to {args.db}. Reversible via warehouse.part_relabel_fix_audit '
              f'(fix_tag = {args.tag!r}).')
    else:
        conn.rollback()
        print('DRY RUN — rolled back. Re-run with --apply to commit.')
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
