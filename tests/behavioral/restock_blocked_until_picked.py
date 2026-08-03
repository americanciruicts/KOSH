#!/usr/bin/env python3
"""RESTOCK ONCE, THEN PICK — a PCN already sitting in a bin cannot be restocked again.

Theresa, 2026-07-30: "Whenever a PCN is restocked, I should never be allowed to restock it
again without being picked first.  The restock function, at one time, would not allow
restock of a PCN twice without a pick function being performed first.  I am not sure how
this function disappeared, but it will need to be reinstated."

It disappeared on 2026-07-22 with the ledger removal, on the reasoning that a restock SETs
the on-hand so a repeat cannot double-count.  That protects the arithmetic, not the
process: the second restock silently overwrites the first count and nothing records that
two different numbers were claimed for one PCN.

On the snapshot model "restocked and not yet picked" IS "on-hand > 0" — a restock sets it
above zero, a pick zeroes it — so that is what the guard tests.  This drives the REAL
DBManager.restock_pcb / pick_pcb against kosh_test (they commit, so this is a
committing-class test) through the full cycle, and pins the deliberate escape hatch: a PCN
with 0 on hand and stock on the MFG Floor stays restockable, so no PCN can become both
un-pickable and un-restockable.  Cleans up its own rows.  Exit 0 = pass.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

DB = os.environ.get('TEST_DB', 'kosh_test')
if DB == 'kosh':
    print('REFUSING: this committing-class test must not target the live copy `kosh`.'); sys.exit(99)

PGHOST = os.environ.get('PGHOST', 'localhost')
PGPORT = os.environ.get('PGPORT', '5434')
PGUSER = os.environ.get('PGUSER', 'aci')
PGPASS = os.environ['PGPASSWORD']
DSN = f'postgresql://{PGUSER}:{PGPASS}@{PGHOST}:{PGPORT}/{DB}'

# Point the app at kosh_test BEFORE importing it — importing app.py builds the pool.
os.environ['DATABASE_URL'] = DSN
os.environ['POSTGRES_HOST'] = PGHOST
os.environ['POSTGRES_PORT'] = PGPORT
os.environ['POSTGRES_DB'] = DB
os.environ['POSTGRES_USER'] = PGUSER
os.environ['POSTGRES_PASSWORD'] = PGPASS

import psycopg2
import app as kosh_app

USER = 'test@americancircuits.com'
IN_BIN_PCN, IN_BIN_ITEM, BIN = '99501', 'TESTRS-BIN', '9990005'
ON_FLOOR_PCN, ON_FLOOR_ITEM = '99502', 'TESTRS-FLOOR'

fails = []
def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)

c = psycopg2.connect(DSN); c.autocommit = True
cur = c.cursor()

def state(pcn):
    cur.execute('SELECT COALESCE(onhandqty,0), mfg_qty, loc_to FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (pcn,))
    row = cur.fetchone()
    return (int(row[0]), row[1], row[2]) if row else None

def cleanup():
    pcns = [IN_BIN_PCN, ON_FLOOR_PCN]
    cur.execute('DELETE FROM warehouse."tblWhse_Inventory" WHERE pcn::text = ANY(%s)', (pcns,))
    cur.execute('DELETE FROM warehouse."tblTransaction" WHERE pcn::text = ANY(%s)', (pcns,))

def restock(pcn, qty, loc_from, loc_to):
    return kosh_app.db_manager.restock_pcb(pcn=int(pcn), quantity=qty, location_from=loc_from,
                                           location_to=loc_to, username=USER)

try:
    cleanup()

    # ---- a PCN sitting in a bin: 20 units, nothing on the floor ------------------
    cur.execute('INSERT INTO warehouse."tblWhse_Inventory" (pcn,item,mpn,onhandqty,mfg_qty,loc_to) '
                "VALUES (%s,%s,'MPN-RS',20,'0',%s)", (IN_BIN_PCN, IN_BIN_ITEM, BIN))
    check(state(IN_BIN_PCN) == (20, '0', BIN), f'setup: 20 units in bin {BIN}')

    r = restock(IN_BIN_PCN, 20, 'MFG Floor', 'Count Area')
    # THE BUG: this used to succeed, over and over, with no pick in between.
    check(r.get('success') is False, f'restock of a PCN already in a bin is REJECTED (got success={r.get("success")})')
    check('picked before it can be restocked' in (r.get('error') or ''),
          f'error tells the operator to pick it first (got: {r.get("error")})')
    check(state(IN_BIN_PCN) == (20, '0', BIN), 'rejected restock left the stock untouched')

    r2 = restock(IN_BIN_PCN, 999, 'MFG Floor', 'Count Area')
    check(r2.get('success') is False, 'a different quantity does not slip past the guard either')
    check(state(IN_BIN_PCN) == (20, '0', BIN), 'still 20 in the bin — no silent overwrite')

    # ---- pick it, then the restock must go through -------------------------------
    p = kosh_app.db_manager.pick_pcb(job=IN_BIN_ITEM, pcb_type='Bare', quantity=20,
                                     pcn=int(IN_BIN_PCN), username=USER)
    check(p.get('success') is True, f'pick succeeds ({p.get("error")})')
    check(state(IN_BIN_PCN)[0] == 0, 'pick zeroed the bin on-hand')

    r3 = restock(IN_BIN_PCN, 20, 'MFG Floor', 'Count Area')
    check(r3.get('success') is True, f'restock AFTER a pick is allowed ({r3.get("error")})')
    check(state(IN_BIN_PCN) == (20, '0', 'Count Area'), 'restock put 20 back into Count Area')

    # ---- and it is blocked again immediately: one restock per pick ---------------
    r4 = restock(IN_BIN_PCN, 20, 'MFG Floor', 'Count Area')
    check(r4.get('success') is False, 'the NEXT restock is blocked again — one restock per pick')

    # ---- escape hatch: 0 on hand with stock on the floor stays restockable -------
    # This is Theresa's PCN 44598 shape (0 on hand, 20 in MFG QTY). The parts are not in a
    # bin, so restocking is the legitimate way to put them back. A PCN must never be both
    # un-pickable and un-restockable.
    cur.execute('INSERT INTO warehouse."tblWhse_Inventory" (pcn,item,mpn,onhandqty,mfg_qty,loc_to) '
                "VALUES (%s,%s,'MPN-RS',0,'20','MFG Floor')", (ON_FLOOR_PCN, ON_FLOOR_ITEM))
    r5 = restock(ON_FLOOR_PCN, 20, 'MFG Floor', 'Count Area')
    check(r5.get('success') is True, f'0 on hand + 20 on the MFG Floor is still restockable ({r5.get("error")})')
    check(state(ON_FLOOR_PCN) == (20, '0', 'Count Area'), 'floor stock came back into a bin')
finally:
    cleanup()
    cur.close(); c.close()

print(f"  ── {'ALL PASS' if not fails else str(len(fails))+' FAILED'} ──")
sys.exit(1 if fails else 0)
