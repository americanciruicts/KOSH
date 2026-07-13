"""Acceptance B (behavioural) — drive the real ledger service against the copy DB.

Stock 3000 -> pick 3000 -> bin 0 / floor 3000 / total 3000 (NOT 6000);
restock 500 -> bin 500 / floor 2500; pick 99999 -> REJECTED;
Warehouse (balance) == PCN History (ledger replay) at EVERY step.

Runs inside one transaction and ROLLS BACK at the end, so the copy DB is left
pristine and the append-only trigger is respected (no test rows committed).
"""
import os
import sys
import psycopg2

sys.path.insert(0, '/app')  # ledger.py is copied next to app.py in the container
import ledger

PCN = 'ACCEPT_B_TESTPCN'
ITEM = 'ACCEPT-B-ITEM'
MPN = 'ACCEPT-B-MPN'
BIN = '9000001'
FLOOR = 'MFG Floor'

failures = []


def hist(cur, pcn):
    """PCN History on-hand = signed replay of the one ledger (WHERE reversed=false)."""
    cur.execute(
        """
        SELECT COALESCE(SUM((CASE WHEN to_location_id   IS NOT NULL THEN qty ELSE 0 END)
                           -(CASE WHEN from_location_id IS NOT NULL THEN qty ELSE 0 END)),0)
        FROM warehouse.inventory_txn WHERE pcn_id=%s AND reversed=false
        """,
        (pcn,),
    )
    return int(cur.fetchone()[0])


def loc_qty(cur, pcn, code):
    cur.execute(
        """
        SELECT COALESCE(SUM(b.qty),0) FROM warehouse.inventory_balance b
        JOIN warehouse.inv_location l USING(location_id)
        WHERE b.pcn_id=%s AND lower(l.code)=lower(%s)
        """,
        (pcn, code),
    )
    return int(cur.fetchone()[0])


def check(cur, label, exp_bin, exp_floor):
    warehouse_total = ledger.on_hand(cur, PCN)   # from balance cache
    history_total = hist(cur, PCN)               # from ledger replay
    b = loc_qty(cur, PCN, BIN)
    f = loc_qty(cur, PCN, FLOOR)
    ok = (b == exp_bin and f == exp_floor
          and warehouse_total == exp_bin + exp_floor
          and warehouse_total == history_total)
    status = 'PASS' if ok else 'FAIL'
    print(f'[{status}] {label}: bin={b} floor={f} '
          f'warehouse_total={warehouse_total} history_total={history_total} '
          f'(expected bin={exp_bin} floor={exp_floor} total={exp_bin+exp_floor})')
    if not ok:
        failures.append(label)


def main():
    conn = psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST', 'aci-database'),
        dbname='kosh_rebuild',
        user=os.environ.get('POSTGRES_USER', 'aci'),
        password=os.environ.get('POSTGRES_PASSWORD'),
    )
    conn.autocommit = False
    cur = conn.cursor()
    try:
        # 1) Stock 3000 into the bin.
        ledger.stock(cur, ITEM, MPN, PCN, 3000, BIN, user='acceptance')
        check(cur, 'after stock 3000', exp_bin=3000, exp_floor=0)

        # 2) Pick 3000 (bin -> floor). Total must stay 3000, NOT double to 6000.
        ledger.pick(cur, ITEM, MPN, PCN, 3000, BIN, user='acceptance')
        check(cur, 'after pick 3000', exp_bin=0, exp_floor=3000)

        # 3) Restock 500 (floor -> bin).
        ledger.restock(cur, ITEM, MPN, PCN, 500, BIN, user='acceptance')
        check(cur, 'after restock 500', exp_bin=500, exp_floor=2500)

        # 4) Over-pick 99999 from the bin -> MUST be rejected, stock unchanged.
        cur.execute('SAVEPOINT op')
        rejected = False
        try:
            ledger.pick(cur, ITEM, MPN, PCN, 99999, BIN, user='acceptance')
        except ledger.LedgerError as e:
            rejected = True
            cur.execute('ROLLBACK TO SAVEPOINT op')
            print(f'[PASS] over-pick 99999 REJECTED: {e}')
        if not rejected:
            failures.append('over-pick not rejected')
            print('[FAIL] over-pick 99999 was NOT rejected')
        check(cur, 'after rejected over-pick (unchanged)', exp_bin=500, exp_floor=2500)

        # 5) Restock the remaining floor; total conserved throughout.
        ledger.restock(cur, ITEM, MPN, PCN, 2500, BIN, user='acceptance')
        check(cur, 'after restock 2500', exp_bin=3000, exp_floor=0)

    finally:
        conn.rollback()   # leave the copy DB pristine
        cur.close()
        conn.close()

    print('\n=== ACCEPTANCE B: ' + ('ALL PASS' if not failures
          else f'{len(failures)} FAILURE(S): {failures}') + ' ===')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
