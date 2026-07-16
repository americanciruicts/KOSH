"""Bug 28 (2026-07-16) — a Part Number Change must take the stock with it.

Theresa, mid-kit: "I am now not able to pick PCN's. Error message states insufficient
quantity available ... error updating item: Save verification failed: expected 80,
got 280."

A balance is keyed (part_id, pcn_id, location_id); the legacy snapshot is keyed by pcn
alone. Part Number Change renamed only the snapshot, so the balance stayed filed under
the OLD part_id. Pick resolves part_id from the NEW name, finds no row, and reports
"insufficient stock ... have 0" against a bin that is not empty. project_warehouse sums
by pcn REGARDLESS of part_id, so the orphaned balance also inflated the row total —
that is the 80 -> 280.

Runs against kosh_test only (testdb.py refuses production); it COMMITS.
"""
import os
import sys

sys.path.insert(0, '/app')
sys.path.insert(0, os.path.dirname(__file__))

import testdb  # noqa: E402  — must resolve/refuse the target DB before app import

os.environ['POSTGRES_DB'] = testdb.target_db()

import ledger  # noqa: E402

PCN = '990281'
BIN = '2203304'
OLD_ITEM, NEW_ITEM = 'TEST-6366-28', 'TEST-6390-28'
MPN = 'TEST-MPN-28'
QTY = 200       # what the PCN holds when it gets renamed
EDIT_QTY = 80   # what the operator then types into Whse Inv — 200 orphan + 80 = the
                # "expected 80, got 280" she saw.


def _cleanup(cur):
    """Reset the test PCN's balance + snapshot. inventory_txn is append-only at the DB
    level (trigger inventory_txn_append_only), so its rows are deliberately left behind
    — history is not ours to delete, and the balance reset is what the test needs."""
    cur.execute('DELETE FROM warehouse.inventory_balance WHERE pcn_id=%s', (PCN,))
    cur.execute('DELETE FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (PCN,))


def _totals(cur, pcn):
    """Total units filed against a PCN, across every part_id and location."""
    cur.execute('SELECT COALESCE(SUM(qty),0) FROM warehouse.inventory_balance WHERE pcn_id=%s',
                (pcn,))
    return cur.fetchone()[0]


def _qty_under(cur, pcn, item):
    cur.execute(
        """
        SELECT COALESCE(SUM(b.qty),0) FROM warehouse.inventory_balance b
        JOIN warehouse.inv_part p USING (part_id)
        WHERE b.pcn_id=%s AND btrim(lower(p.item_raw))=btrim(lower(%s))
        """,
        (pcn, item),
    )
    return cur.fetchone()[0]


def main():
    conn = testdb.connect()
    conn.autocommit = False
    cur = conn.cursor()
    results = []
    try:
        _cleanup(cur)

        # Stock QTY under the OLD part number, then rename the PCN to the NEW one.
        ledger.stock(cur, OLD_ITEM, MPN, PCN, QTY, BIN, user='test')
        cur.execute(
            """
            INSERT INTO warehouse."tblWhse_Inventory" (item, pcn, mpn, onhandqty, mfg_qty, loc_to)
            VALUES (%s, %s, %s, %s, 0, %s)
            """,
            (OLD_ITEM, PCN, MPN, QTY, BIN),
        )
        before = _totals(cur, PCN)
        print(f'  stocked {QTY} of {OLD_ITEM} at bin {BIN} (pcn {PCN}); total={before}')

        # The rename, exactly as the route does it: snapshot + ledger, one transaction.
        cur.execute('UPDATE warehouse."tblWhse_Inventory" SET item=%s WHERE pcn::text=%s',
                    (NEW_ITEM, PCN))
        # On the buggy baseline relabel_pcn does not exist and the route renamed only
        # the snapshot. Emulate that rather than erroring, so this suite demonstrates
        # the SYMPTOM Theresa reported (red) instead of an AttributeError.
        relabel = getattr(ledger, 'relabel_pcn', None)
        if relabel is None:
            print('  !! ledger.relabel_pcn missing — baseline behaviour: snapshot renamed, '
                  'ledger left under the old part number')
        else:
            rows, moved = relabel(cur, PCN, NEW_ITEM, MPN, user='test')
            print(f'  renamed {OLD_ITEM} -> {NEW_ITEM}; re-filed {rows} location(s), {moved} units')
        ledger.project_warehouse(cur, PCN)

        # TEST 1: a relabel must be quantity-neutral. Booking it as a movement is what
        # minted 15.3M phantom units in the 2026-06 reconcile (I8).
        after = _totals(cur, PCN)
        results.append(('relabel is quantity-neutral (no phantom stock)', before == after == QTY))
        print(f'\nTEST 1 total before={before} after={after}')

        # TEST 2: the stock is filed under the NEW part number, none left under the old.
        under_new, under_old = _qty_under(cur, PCN, NEW_ITEM), _qty_under(cur, PCN, OLD_ITEM)
        results.append(('stock moved to the new part number',
                        under_new == QTY and under_old == 0))
        print(f'TEST 2 under {NEW_ITEM}={under_new}, under {OLD_ITEM}={under_old}')

        # TEST 3: Theresa's first failure — picking under the new name must work.
        # Runs BEFORE the edit below: on the buggy baseline the edit writes a fresh row
        # under the new part, which would mask this.
        try:
            ledger.pick(cur, NEW_ITEM, MPN, PCN, QTY, BIN, user='test')
            picked, err = True, None
        except ledger.LedgerError as e:
            picked, err = False, str(e)
        results.append(('pick under the new part number succeeds', picked))
        print(f'TEST 3 pick {QTY} as {NEW_ITEM} -> {"OK" if picked else err}')

        # TEST 4: her second failure, the Whse Inv editor. Typing EDIT_QTY must store
        # EDIT_QTY — the orphan under the old part must not be added on top. This is
        # the exact "Save verification failed: expected 80, got 280". onhandqty is the
        # non-floor total, so the QTY the pick above moved to the floor is excluded and
        # a green run reads back exactly EDIT_QTY.
        ledger.set_pcn_snapshot(cur, NEW_ITEM, MPN, PCN, BIN, EDIT_QTY, None, user='test')
        ledger.project_warehouse(cur, PCN)
        cur.execute('SELECT onhandqty FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s',
                    (PCN,))
        row = cur.fetchone()
        snapshot = row[0] if row else None
        results.append((f'Whse Inv edit stores {EDIT_QTY} (not {QTY + EDIT_QTY})',
                        snapshot == EDIT_QTY))
        print(f'TEST 4 edited to {EDIT_QTY} -> snapshot onhandqty={snapshot} '
              f'(buggy baseline: {QTY + EDIT_QTY})')

        print('\n' + '=' * 64)
        for name, passed in results:
            print(f'  [{"PASS" if passed else "FAIL"}] {name}')
        print('=' * 64)
        return 0 if all(p for _, p in results) else 1
    finally:
        _cleanup(cur)
        conn.commit()
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
