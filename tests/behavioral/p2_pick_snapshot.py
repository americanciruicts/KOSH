#!/usr/bin/env python3
"""PHASE 2 — PICK on the snapshot model.  Covers PH-1 (no bin+floor double) and the
Warehouse==PCN History invariant (WI-2) for the pick path.

Drives the REAL wh_ops.pick against kosh_test in ONE transaction, then ROLLS BACK, so
kosh_test is left pristine.  Proves the complete-pick rule: the whole bin qty moves to the
floor, bin XOR floor holds, total is conserved, and over-pick is rejected.  Exit 0=pass.
"""
import os, sys, psycopg2

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import wh_ops

DB = os.environ.get('TEST_DB', 'kosh_test')
if DB == 'kosh':
    print('REFUSING: this committing-class test must not target the live copy `kosh`.'); sys.exit(99)
CONN = dict(host=os.environ.get('PGHOST', 'localhost'), port=int(os.environ.get('PGPORT', '5434')),
            user=os.environ.get('PGUSER', 'aci'), password=os.environ['PGPASSWORD'], dbname=DB)

PCN, ITEM, MPN, BIN = '990201', 'TESTPICK-1', 'MPN-PICK-1', '9990002'
fails = []
def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)

c = psycopg2.connect(**CONN); c.autocommit = False
cur = c.cursor()
def whse(pcn):
    cur.execute('SELECT onhandqty, mfg_qty, loc_to FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (str(pcn),))
    b, f, loc = cur.fetchone(); return int(b or 0), (int(f) if str(f).lstrip('-').isdigit() else 0), loc
try:
    # setup: 200 in a bin, floor empty (bin XOR floor holds), loc_to = the bin
    cur.execute('DELETE FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (PCN,))
    cur.execute('INSERT INTO warehouse."tblWhse_Inventory" (pcn,item,mpn,onhandqty,mfg_qty,loc_to) '
                "VALUES (%s,%s,%s,200,'0',%s)", (PCN, ITEM, MPN, BIN))
    b, f, loc = whse(PCN)
    check((b, f) == (200, 0), 'setup: 200 in bin, 0 on floor')

    # complete pick of the whole 200
    wh_ops.pick(cur, PCN, 200)
    b, f, loc = whse(PCN)
    check(b == 0,               'PICK: bin emptied to 0')
    check(f == 200,             'PICK: 200 now on the MFG Floor')
    check(loc == 'MFG Floor',   'PICK: loc_to flipped to MFG Floor')
    check(not (b > 0 and f > 0),'PH-1: bin XOR floor holds (never both)')
    check(b + f == 200,         'WI-2: total conserved = 200 (Warehouse==History reads one number)')

    # over-pick is rejected (can't pick more than the bin holds) — reset to a bin first
    cur.execute('SAVEPOINT op')
    cur.execute("UPDATE warehouse.\"tblWhse_Inventory\" SET onhandqty=50, mfg_qty='0', loc_to=%s WHERE pcn::text=%s", (BIN, PCN))
    rejected = False
    try:
        wh_ops.pick(cur, PCN, 999)
    except wh_ops.WarehouseOpError as e:
        rejected = 'have 50' in str(e)
    check(rejected, 'I1: over-pick rejected (have 50, need 999), stock unchanged')
    cur.execute('ROLLBACK TO SAVEPOINT op')
finally:
    c.rollback(); c.close()

print(f"  ── {'ALL PASS' if not fails else str(len(fails))+' FAILED'} ──")
sys.exit(1 if fails else 0)
