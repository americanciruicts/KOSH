"""End-to-end acceptance against the REWIRED app.py DatabaseManager, on the copy DB.

Drives the real stock_pcb / pick_pcb / restock_pcb methods (which now write the ledger
+ project the snapshot) and asserts Warehouse == PCN History at every step.

This suite COMMITS, so it must never run against production — testdb.target_db()
refuses `kosh` outright.  Default target: kosh_test.  Override with KOSH_TEST_DB.
Run inside a webapp container:  python /app/tests/acceptance_app.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import testdb

# Must be set BEFORE `import app` — app.py reads POSTGRES_DB at import time to build
# its connection pool.
os.environ['POSTGRES_DB'] = testdb.target_db()
sys.path.insert(0, '/app')

import app as A
import psycopg2

ITEM = 'ZZTEST-LEDGER-ITEM'
MPN = 'ZZ-LEDGER-MPN'
PCN = 90911
BIN = '9000001'

dbm = A.db_manager
fails = []


def snap(tag):
    conn = dbm.get_connection()
    try:
        cur = conn.cursor()
        # Warehouse projection (onhandqty=available, mfg_qty=floor)
        cur.execute("""SELECT COALESCE(onhandqty,0),
                              CASE WHEN mfg_qty ~ '^-?[0-9]+$' THEN mfg_qty::int ELSE 0 END
                       FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s""", (str(PCN),))
        r = cur.fetchone() or (0, 0)
        wh_bin, wh_floor = int(r[0]), int(r[1])
        # Ledger balance total
        cur.execute("SELECT COALESCE(SUM(qty),0) FROM warehouse.inventory_balance WHERE pcn_id=%s", (str(PCN),))
        bal = int(cur.fetchone()[0])
        # PCN History replay
        cur.execute("""SELECT COALESCE(SUM((CASE WHEN to_location_id IS NOT NULL THEN qty ELSE 0 END)
                                          -(CASE WHEN from_location_id IS NOT NULL THEN qty ELSE 0 END)),0)
                       FROM warehouse.inventory_txn WHERE pcn_id=%s AND reversed=false""", (str(PCN),))
        hist = int(cur.fetchone()[0])
        cur.close()
        return wh_bin, wh_floor, bal, hist
    finally:
        dbm.return_connection(conn)


def check(tag, exp_bin, exp_floor):
    wh_bin, wh_floor, bal, hist = snap(tag)
    wh_total = wh_bin + wh_floor
    ok = (wh_bin == exp_bin and wh_floor == exp_floor
          and wh_total == bal == hist == exp_bin + exp_floor)
    print(f'[{"PASS" if ok else "FAIL"}] {tag}: whse(bin={wh_bin},floor={wh_floor},total={wh_total}) '
          f'ledger_balance={bal} history={hist} (expected bin={exp_bin} floor={exp_floor})')
    if not ok:
        fails.append(tag)


# Clean any prior run of this test PCN from the copy (copy DB is disposable).
c = dbm.get_connection()
cur = c.cursor()
for t in ('inventory_balance',):
    cur.execute(f'DELETE FROM warehouse.{t} WHERE pcn_id=%s', (str(PCN),))
cur.execute('DELETE FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (str(PCN),))
cur.execute('DELETE FROM warehouse."tblTransaction" WHERE pcn::text=%s', (str(PCN),))
c.commit()
cur.execute("SET session_replication_role = replica")  # allow deleting append-only txn for test cleanup
c.commit()
cur.execute('DELETE FROM warehouse.inventory_txn WHERE pcn_id=%s', (str(PCN),))
c.commit()
cur.execute("SET session_replication_role = origin")
c.commit()
cur.close(); dbm.return_connection(c)

r = A.db_manager.stock_pcb(job=ITEM, pcb_type='Bare', quantity=3000,
                           location_from='Receiving Area', location_to=BIN,
                           username='tester@x.com', pcn=PCN, mpn=MPN, part_number=ITEM)
print('stock_pcb ->', r.get('success'), r.get('error', ''))
check('after stock 3000', 3000, 0)

r = A.db_manager.pick_pcb(job=ITEM, pcb_type='Bare', quantity=3000,
                          username='tester@x.com', work_order='WO-TEST', pcn=PCN)
print('pick_pcb ->', r.get('success'), r.get('error', ''))
check('after pick 3000 (NOT double)', 0, 3000)

r = A.db_manager.restock_pcb(pcn=PCN, item=ITEM, quantity=500,
                             location_from='MFG Floor', location_to=BIN, username='tester@x.com')
print('restock_pcb ->', r.get('success'), r.get('error', ''))
check('after restock 500', 500, 2500)

r = A.db_manager.pick_pcb(job=ITEM, pcb_type='Bare', quantity=600,
                          username='tester@x.com', work_order='WO-TEST', pcn=PCN)
print('over-pick 600 (bin has 500) ->', r.get('success'), '| rejected:', (not r.get('success')), '|', r.get('error', ''))
if r.get('success'):
    fails.append('over-pick not rejected')
check('after rejected over-pick (unchanged)', 500, 2500)

print('\n=== ACCEPTANCE (app methods): ' + ('ALL PASS' if not fails else f'FAILURES: {fails}') + ' ===')
sys.exit(1 if fails else 0)
