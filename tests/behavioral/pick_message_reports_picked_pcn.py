#!/usr/bin/env python3
"""PICK notification — "Remaining" must describe the PCN that was picked.

Reported 2026-07-30: PCN 46607 of item 7942-16 held 50000 units and the whole PCN was
picked, but the success toast read "Remaining: 2000".  The 2000 was a DIFFERENT PCN
(45082) of the same item, still sitting in its bin — the pick never touched it.  The
pre-pick confirm dialog says "Remaining After Pick: 0" (it reads the PCN row), so the
toast directly contradicted it and read as 2000 units lost or left behind.

Drives the REAL DBManager.pick_pcb against kosh_test (it commits, so this is a
committing-class test) and asserts the fields the message is built from:
  - pcn_remaining_qty  -> 0 for the fully-picked PCN
  - new_qty            -> the item total, which legitimately still counts the other PCN
  - pcn / mpn / loc_from echoed back (they were absent, so both the toast and the
    history detail line rendered "PCN: -, MPN: -, From: -" for every pick)
Cleans up its own rows on the way out.  Exit 0 = pass.
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

# Point the app at kosh_test BEFORE importing it — importing app.py builds the
# connection pool and starts its daemon table-ensure threads.
os.environ['DATABASE_URL'] = DSN
os.environ['POSTGRES_HOST'] = PGHOST
os.environ['POSTGRES_PORT'] = PGPORT
os.environ['POSTGRES_DB'] = DB
os.environ['POSTGRES_USER'] = PGUSER
os.environ['POSTGRES_PASSWORD'] = PGPASS

import psycopg2
import app as kosh_app

# Mirror of the reported case: one PCN fully picked, a second PCN of the same item
# left untouched in its bin.
ITEM = 'TESTMSG-1'
MPN = 'MPN-TESTMSG-1'
PICK_PCN, PICK_QTY, PICK_BIN = '99301', 50000, '9990003'
OTHER_PCN, OTHER_QTY = '99302', 2000

fails = []
def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)

c = psycopg2.connect(DSN); c.autocommit = True
cur = c.cursor()

def cleanup():
    cur.execute('DELETE FROM warehouse."tblWhse_Inventory" WHERE pcn::text = ANY(%s)', ([PICK_PCN, OTHER_PCN],))
    cur.execute('DELETE FROM warehouse."tblTransaction" WHERE pcn::text = ANY(%s)', ([PICK_PCN, OTHER_PCN],))

try:
    cleanup()
    cur.execute('INSERT INTO warehouse."tblWhse_Inventory" (pcn,item,mpn,onhandqty,mfg_qty,loc_to) '
                "VALUES (%s,%s,%s,%s,'0',%s)", (PICK_PCN, ITEM, MPN, PICK_QTY, PICK_BIN))
    cur.execute('INSERT INTO warehouse."tblWhse_Inventory" (pcn,item,mpn,onhandqty,mfg_qty,loc_to) '
                "VALUES (%s,%s,%s,%s,'0',%s)", (OTHER_PCN, ITEM, MPN, OTHER_QTY, '9990004'))

    result = kosh_app.db_manager.pick_pcb(
        job=ITEM, pcb_type='Bare', quantity=PICK_QTY, pcn=int(PICK_PCN),
        username='test@americancircuits.com')

    check(result.get('success') is True, f'pick succeeded ({result.get("error")})')
    check(result.get('picked_qty') == PICK_QTY, f'picked_qty == {PICK_QTY}')
    # THE BUG: this was reported as the item total (2000) for a PCN that is now empty.
    check(result.get('pcn_remaining_qty') == 0,
          f'pcn_remaining_qty == 0 for the fully-picked PCN (got {result.get("pcn_remaining_qty")})')
    check(result.get('new_qty') == OTHER_QTY,
          f'new_qty == {OTHER_QTY} = the item total, which still counts PCN {OTHER_PCN}')
    check(str(result.get('pcn')) == PICK_PCN, f'pcn echoed back (got {result.get("pcn")})')
    check(result.get('mpn') == MPN, f'mpn echoed back (got {result.get("mpn")})')
    check(result.get('loc_from') == PICK_BIN, f'loc_from == source bin (got {result.get("loc_from")})')

    # The untouched PCN must still be in its bin — the pick moved only its own PCN.
    cur.execute('SELECT onhandqty FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (OTHER_PCN,))
    check(int(cur.fetchone()[0]) == OTHER_QTY, f'PCN {OTHER_PCN} untouched at {OTHER_QTY} in its bin')

    # And the message the operator sees must not contradict the confirm dialog, and must
    # talk about the picked PCN ONLY — no item-wide total, which is what confused them.
    # .get() throughout so pre-fix code fails as a FAIL line, not a KeyError traceback.
    msg = (f"Successfully picked {result.get('picked_qty')} units of {result.get('job')} "
           f"(PCN {result.get('pcn')}) from {result.get('loc_from')}. "
           f"PCN {result.get('pcn')} remaining: {result.get('pcn_remaining_qty')}")
    print(f"  toast -> {msg}")
    check('remaining: 0' in msg, 'toast tells the operator the picked PCN is empty')
    check(str(OTHER_QTY) not in msg, f'toast never mentions the untouched PCN\'s {OTHER_QTY} units')
finally:
    cleanup()
    cur.close(); c.close()

print(f"  ── {'ALL PASS' if not fails else str(len(fails))+' FAILED'} ──")
sys.exit(1 if fails else 0)
