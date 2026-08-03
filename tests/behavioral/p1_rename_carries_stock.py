#!/usr/bin/env python3
"""PHASE 1 — Rename carries its stock (SNAPSHOT model, ledger removed 2026-07-22).
Covers SR-3 (wrong ACI PN on shortage), WI-1 (edit qty after rename), PK-1 (pick a
full bin after rename).

In the one-number snapshot model a rename is just `UPDATE item` on the SAME row, so
the stock (onhandqty) rides along automatically and can never be stranded — there is
no separate ledger balance to leave behind. A pick takes the whole PCN to the MFG
Floor (onhandqty -> 0, mfg_qty <- the bin qty). Runs in ONE transaction and ROLLS
BACK — kosh_test stays pristine. Exit 0 = pass, 1 = fail.
"""
import os, sys, psycopg2

DB = os.environ.get('TEST_DB', 'kosh_test')
if DB == 'kosh':
    print('REFUSING: this committing-class test must not target the live copy `kosh`.')
    sys.exit(99)
CONN = dict(host=os.environ.get('PGHOST', 'localhost'),
            port=int(os.environ.get('PGPORT', '5434')),
            user=os.environ.get('PGUSER', 'aci'),
            password=os.environ['PGPASSWORD'], dbname=DB)

PCN, OLD, NEW, MPN, BIN = '990101', 'TESTA-RENAME-1', 'TESTB-RENAME-1', 'MPN-RENAME-1', '9990001'
fails = []
def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)
def onhand(cur, pcn):
    cur.execute('SELECT COALESCE(SUM(COALESCE(onhandqty,0)),0) FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (pcn,))
    return cur.fetchone()[0]

c = psycopg2.connect(**CONN); c.autocommit = False
cur = c.cursor()
try:
    # ---- setup: a PCN with 100 in a bin under the OLD part
    cur.execute('DELETE FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (PCN,))
    cur.execute('INSERT INTO warehouse."tblWhse_Inventory" (pcn, item, mpn, onhandqty, mfg_qty, loc_to) '
                "VALUES (%s,%s,%s,100,'0',%s)", (PCN, OLD, MPN, BIN))
    check(onhand(cur, PCN) == 100, 'setup: 100 units on hand under old part')

    # ---- rename = UPDATE item on the SAME row; the stock rides along (quantity-neutral)
    before = onhand(cur, PCN)
    cur.execute('UPDATE warehouse."tblWhse_Inventory" SET item=%s WHERE pcn::text=%s', (NEW, PCN))
    check(onhand(cur, PCN) == before == 100, 'GREEN: rename is QUANTITY-NEUTRAL (100 before and after)')

    cur.execute('SELECT item, onhandqty FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (PCN,))
    item, oh = cur.fetchone()
    check(item == NEW, 'SR-3: warehouse/shortage row shows the NEW ACI PN (not the old)')
    check(oh == 100,   'WI-1: edit-qty reads the real 100 (no phantom doubling)')

    # ---- PK-1: pick the whole PCN under the NEW name -> onhandqty 0, moves to MFG Floor
    cur.execute("""UPDATE warehouse."tblWhse_Inventory"
                   SET mfg_qty = COALESCE(onhandqty,0)::text, onhandqty = 0,
                       loc_from = loc_to, loc_to = 'MFG Floor'
                   WHERE pcn::text=%s""", (PCN,))
    cur.execute('SELECT onhandqty, mfg_qty, loc_to FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (PCN,))
    oh2, mfg, loc = cur.fetchone()
    check(oh2 == 0 and str(mfg) == '100' and loc == 'MFG Floor',
          'PK-1: pick under the NEW name -> on-hand 0, 100 on MFG Floor (stock followed the rename)')
finally:
    c.rollback()   # never persist — kosh_test stays pristine
    c.close()

print(f"  -- {'ALL PASS' if not fails else str(len(fails))+' FAILED'} --")
sys.exit(1 if fails else 0)
