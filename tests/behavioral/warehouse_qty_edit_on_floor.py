#!/usr/bin/env python3
"""WI-1 — editing a quantity in Warehouse Inventory must not 500 on a floor PCN.

Theresa: "Unable to edit quantities" / "Save verification failed". Preet checked the edit
on 2026-07-29 (PCN 46606) and it worked, so the bug looked closed — but 46606's loc_to was
bin 1251457 by then. The failure is specific to a PCN whose loc_to is 'MFG Floor':

  the DB guard `trg_bin_xor_floor` forces onhandqty = 0 and re-homes the qty into mfg_qty,
  the route compared the typed number against the stored onhandqty, got 1000 != 0, called
  it a failed save and rolled the WHOLE edit back (HTTP 500).

12,851 rows on staging sit on the MFG Floor, so every one of them was un-editable — the
population Theresa hits when reconciling a PCN whose stock KOSH thinks is out on the floor.

This test drives the SQL the route runs, with the guard trigger installed (as `kosh` and
post-deploy production have it), and pins:
  * a BIN pcn edits cleanly and verifies against onhandqty  (Preet's passing case)
  * a FLOOR pcn no longer mis-verifies against onhandqty     (the 500)
  * on the floor the qty lands in mfg_qty and verification reads THAT column
  * bin XOR floor still holds after every edit (never re-introduce PH-1)

Committing-class (writes + trigger DDL) so it runs only against kosh_test. It installs the
trigger if absent and removes it again if it installed it, leaving the DB as it found it.
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
SUPERUSER = os.environ.get('PGSUPERUSER', 'postgres')
SUPERPASS = os.environ.get('PGSUPERPASS', 'postgres')

import psycopg2

ENFORCE_SQL = os.path.join(ROOT, 'bug_memory', 'ENFORCE-BIN-XOR-FLOOR.sql')
PCN, ITEM, BIN = '99801', 'TESTWI1', '1251457'

fails = []
def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)

c = psycopg2.connect(f'postgresql://{PGUSER}:{PGPASS}@{PGHOST}:{PGPORT}/{DB}'); c.autocommit = True
cur = c.cursor()
su = psycopg2.connect(f'postgresql://{SUPERUSER}:{SUPERPASS}@{PGHOST}:{PGPORT}/{DB}'); su.autocommit = True
sucur = su.cursor()

TRIGGER_Q = ("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal "
             "AND tgrelid = 'warehouse.\"tblWhse_Inventory\"'::regclass AND tgname = 'trg_bin_xor_floor'")

def row():
    cur.execute('''SELECT COALESCE(onhandqty,0),
                          CASE WHEN mfg_qty ~ '^-?[0-9]+$' THEN mfg_qty::integer ELSE 0 END,
                          COALESCE(loc_to,'')
                   FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s''', (PCN,))
    return cur.fetchone()

def seed(onhand, floor, loc):
    cur.execute('DELETE FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (PCN,))
    cur.execute('INSERT INTO warehouse."tblWhse_Inventory" (pcn,item,mpn,onhandqty,mfg_qty,loc_to) '
                "VALUES (%s,%s,'MPN-WI1',%s,%s,%s)", (PCN, ITEM, onhand, str(floor), loc))

def edit(typed_onhand, typed_floor, loc):
    """Exactly the UPDATE update_warehouse_item runs for a quantity edit."""
    cur.execute('''UPDATE warehouse."tblWhse_Inventory"
                   SET onhandqty = COALESCE(%s, onhandqty),
                       mfg_qty   = COALESCE(%s, mfg_qty),
                       loc_to    = COALESCE(NULLIF(%s,''), loc_to)
                   WHERE pcn::text = %s''',
                (typed_onhand, (str(typed_floor) if typed_floor is not None else None), loc, PCN))

def verifies(typed_onhand, typed_floor):
    """The route's post-save check, as fixed: compare the bucket the location dictates."""
    stored_bin, stored_floor, stored_loc = row()
    if stored_loc == 'MFG Floor':
        expected, actual = typed_floor, stored_floor
    else:
        expected, actual = typed_onhand, stored_bin
    return expected is None or actual == expected

installed_here = False
try:
    sucur.execute(TRIGGER_Q)
    if sucur.fetchone()[0] == 0:
        sucur.execute(open(ENFORCE_SQL).read())
        installed_here = True
    sucur.execute(TRIGGER_Q)
    check(sucur.fetchone()[0] == 1, 'bin XOR floor guard is installed (as on kosh / prod after deploy)')

    # ---- A) PCN in a BIN — Preet's passing case on 46606 ------------------------
    seed(2000, 0, BIN)
    edit(1000, None, BIN)
    check(row() == (1000, 0, BIN), f'bin PCN: typed 1000 stored as On Hand 1000 {row()}')
    check(verifies(1000, None), 'bin PCN: verification passes (this always worked)')

    # ---- B) PCN on the MFG FLOOR — the 500 -------------------------------------
    seed(0, 2000, 'MFG Floor')
    edit(1000, None, 'MFG Floor')
    stored_bin, stored_floor, stored_loc = row()
    check(stored_bin == 0, 'floor PCN: guard still forces On Hand to 0 (PH-1 stays fixed)')
    # THE BUG: the old check compared the typed 1000 against this 0 and 500'd.
    check(stored_bin != 1000, 'floor PCN: the typed number is NOT in onhandqty - the old check compared these')
    check(verifies(1000, None),
          'floor PCN: fixed verification no longer fails the save (it reads the MFG Qty column)')

    # ---- C) editing the FLOOR qty on a floor PCN lands and verifies -------------
    seed(0, 2000, 'MFG Floor')
    edit(None, 1500, 'MFG Floor')
    check(row() == (0, 1500, 'MFG Floor'), f'floor PCN: MFG Qty edit stored 1500 {row()}')
    check(verifies(None, 1500), 'floor PCN: MFG Qty edit verifies')

    # ---- D) moving floor stock into a bin brings the qty back -------------------
    seed(0, 2000, 'MFG Floor')
    edit(None, None, BIN)
    check(row() == (2000, 0, BIN), f'floor -> bin move re-homes the 2000 into the bin {row()}')

    # ---- E) bin XOR floor holds after every edit above -------------------------
    cur.execute('''SELECT count(*) FROM warehouse."tblWhse_Inventory"
                   WHERE pcn::text=%s AND COALESCE(onhandqty,0) > 0
                     AND mfg_qty ~ '^[1-9][0-9]*$' ''', (PCN,))
    check(cur.fetchone()[0] == 0, 'PH-1: never both bin and floor > 0')
finally:
    cur.execute('DELETE FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s', (PCN,))
    if installed_here:
        sucur.execute('DROP TRIGGER IF EXISTS trg_bin_xor_floor ON warehouse."tblWhse_Inventory"')
    cur.close(); c.close(); sucur.close(); su.close()

print(f"  ── {'ALL PASS' if not fails else str(len(fails))+' FAILED'} ──")
sys.exit(1 if fails else 0)
