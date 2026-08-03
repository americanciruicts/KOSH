#!/usr/bin/env python3
"""Quantity has no business ceiling — 0 or more is accepted everywhere.

Preet, 2026-07-31: "can u remove the high limit, user can enter any qty, pick any qty, no
limitation? just not negative, it can be 0 to any number for stock, generate pcn, pick or
restock."

History: the original cap was 10,000, which blocked real reel quantities and stopped PCNs
being generated. It was raised to 100,000, which blocked them again. Guessing a ceiling has
failed twice, so there is no longer a business bound — a warehouse quantity is whatever is
physically there.

ONE bound remains and it is deliberate: warehouse."tblWhse_Inventory".onhandqty is a
Postgres `integer`, so 2,147,483,647 is the largest value that can be STORED. Without the
check Postgres raises mid-transaction and the operator gets an opaque 500 with everything
rolled back; with it they get a sentence. Raising it further means altering the column to
bigint first — this test pins that, so nobody "removes the last limit" and ships 500s.

Drives the REAL DBManager methods against kosh_test (committing-class). Cleans up.
Exit 0 = pass.
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
os.environ.update(DATABASE_URL=DSN, POSTGRES_HOST=PGHOST, POSTGRES_PORT=PGPORT,
                  POSTGRES_DB=DB, POSTGRES_USER=PGUSER, POSTGRES_PASSWORD=PGPASS)

import psycopg2
import app as kosh_app

USER = 'test@americancircuits.com'
PCN, ITEM, BIN = '99901', 'TESTQTY-1', '9990009'
BIG = 5_000_000                 # far above both old caps (10,000 and 100,000)

fails = []
def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)

c = psycopg2.connect(DSN); c.autocommit = True
cur = c.cursor()

def state():
    cur.execute('SELECT COALESCE(onhandqty,0), mfg_qty, loc_to FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (PCN,))
    r = cur.fetchone(); return (int(r[0]), r[1], r[2]) if r else None

def clean():
    cur.execute('DELETE FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (PCN,))
    cur.execute('DELETE FROM warehouse."tblTransaction" WHERE pcn::text=%s', (PCN,))

try:
    # ---- the validator itself -------------------------------------------------
    from app import validate_quantity, MAX_QTY
    check(validate_quantity(0)[0] is True,            'validate_quantity accepts 0')
    check(validate_quantity(10_001)[0] is True,       'accepts 10,001 (the ORIGINAL cap is gone)')
    check(validate_quantity(100_001)[0] is True,      'accepts 100,001 (the SECOND cap is gone)')
    check(validate_quantity(BIG)[0] is True,          f'accepts {BIG:,}')
    check(validate_quantity(MAX_QTY)[0] is True,      f'accepts the int4 limit {MAX_QTY:,}')
    check(validate_quantity(-1)[0] is False,          'still rejects -1 (negatives are the one rule)')
    check(validate_quantity(MAX_QTY + 1)[0] is False, 'rejects above int4 - it could not be STORED')
    check(validate_quantity('abc')[0] is False,       'rejects non-numeric')

    # ---- a real pick of a quantity both old caps would have refused ------------
    clean()
    cur.execute('INSERT INTO warehouse."tblWhse_Inventory" (pcn,item,mpn,onhandqty,mfg_qty,loc_to) '
                "VALUES (%s,%s,'MPN-QTY',%s,'0',%s)", (PCN, ITEM, BIG, BIN))
    r = kosh_app.db_manager.pick_pcb(job=ITEM, pcb_type='Bare', quantity=BIG,
                                     pcn=int(PCN), username=USER)
    check(r.get('success') is True, f'pick of {BIG:,} succeeds ({r.get("error")})')
    check(state()[0] == 0, 'pick emptied the bin')

    # ---- restock the same oversized quantity back ------------------------------
    r = kosh_app.db_manager.restock_pcb(pcn=int(PCN), quantity=BIG, location_from='MFG Floor',
                                        location_to='Count Area', username=USER)
    check(r.get('success') is True, f'restock of {BIG:,} succeeds ({r.get("error")})')
    check(state()[0] == BIG, f'{BIG:,} stored intact - not truncated or capped')

    # ---- above int4 is refused CLEANLY, not as a 500 ---------------------------
    clean()
    cur.execute('INSERT INTO warehouse."tblWhse_Inventory" (pcn,item,mpn,onhandqty,mfg_qty,loc_to) '
                "VALUES (%s,%s,'MPN-QTY',0,'0',%s)", (PCN, ITEM, BIN))
    r = kosh_app.db_manager.restock_pcb(pcn=int(PCN), quantity=MAX_QTY + 1, location_from='MFG Floor',
                                        location_to='Count Area', username=USER)
    check(r.get('success') is False, 'above int4 is refused')
    check('0 or more' in (r.get('error') or ''), f'refusal explains the limit (got: {r.get("error")})')
    check(state()[0] == 0, 'the refused restock changed nothing')

    # ---- a negative is still refused ------------------------------------------
    r = kosh_app.db_manager.restock_pcb(pcn=int(PCN), quantity=-5, location_from='MFG Floor',
                                        location_to='Count Area', username=USER)
    check(r.get('success') is False, 'a negative quantity is still refused')
finally:
    clean()
    cur.close(); c.close()

print(f"  ── {'ALL PASS' if not fails else str(len(fails))+' FAILED'} ──")
sys.exit(1 if fails else 0)
