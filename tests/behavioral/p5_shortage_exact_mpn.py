#!/usr/bin/env python3
"""PHASE 5 — SR-2: shortage report same-MPN visibility rows match EXACT MPN only.

Proves the 2026-07-22 fix in _SHORTAGE_MATCH_SQL (app.py): the "same MPN under a
different part number" visibility rows must match the BOM line's MPN EXACTLY.
Previously the non-Chemring path NORMALIZED the MPN (stripped -, #, space, ., /),
which merged DISTINCT parts differing only by those characters — the "like" match
Theresa flagged.

Sets up 4 inventory rows in kosh_test in ONE transaction, then ROLLS BACK, so the
copy is left pristine. Runs the three match predicates that ship in app.py against
the same data:

  * NEW non-Chemring  : UPPER(p.mpn) = UPPER(bom_mpn)         (case-insensitive exact)
  * NEW Chemring      : p.mpn = bom_mpn                       (case-sensitive exact)
  * OLD normalized    : translate(p.mpn,'-# ./','') = key     (the buggy rule)

The RED/GREEN proof: the OLD rule pulls in the dash-differing distinct part;
the NEW rule does not. Exit 0 = pass.
"""
import os, sys, psycopg2

DB = os.environ.get('TEST_DB', 'kosh_test')
if DB == 'kosh':
    print('REFUSING: this committing-class test must not target the live copy `kosh`.'); sys.exit(99)
CONN = dict(host=os.environ.get('PGHOST', 'localhost'), port=int(os.environ.get('PGPORT', '5434')),
            user=os.environ.get('PGUSER', 'aci'), password=os.environ['PGPASSWORD'], dbname=DB)

ACI_PN, BOM_MPN = 'ZZTESTA', 'RC0805-100K'
# item, mpn, pcn, onhand — B=exact(same case), C=dash-differ (distinct part), D=exact(other case)
ROWS = [
    ('ZZTESTB', 'RC0805-100K', 'ZZPCNB', 70),   # exact same MPN, different PN  -> SHOULD show
    ('ZZTESTC', 'RC0805100K',  'ZZPCNC', 999),  # differs ONLY by the dash      -> must NOT show (new)
    ('ZZTESTD', 'rc0805-100k', 'ZZPCND', 5),     # same MPN, lowercased          -> SHOULD show (case-insensitive)
]
ALL_ITEMS = {r[0] for r in ROWS}

fails = []
def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)

# The three predicates exactly as they appear (or appeared) in _SHORTAGE_MATCH_SQL.
# NOTE: %% escapes the LIKE wildcard so psycopg2's param substitution leaves it alone.
POOL = ("SELECT item, mpn FROM warehouse.\"tblWhse_Inventory\" "
        "WHERE COALESCE(loc_to,'') <> 'MFG Floor' AND onhandqty > 0 AND item LIKE 'ZZTEST%%'")
def matched(cur, predicate):
    cur.execute(f"SELECT p.item FROM ({POOL}) p "
                f"WHERE UPPER(p.item) <> UPPER(%s) AND {predicate}", (ACI_PN, BOM_MPN))
    return {r[0] for r in cur.fetchall()}

NEW_LOOSE  = "UPPER(p.mpn) = UPPER(%s)"                                        # non-Chemring (new)
NEW_STRICT = "p.mpn = %s"                                                      # Chemring (kept)
OLD_NORM   = "lower(translate(p.mpn,'-# ./','')) = lower(translate(%s,'-# ./',''))"  # buggy old

c = psycopg2.connect(**CONN); c.autocommit = False
cur = c.cursor()
try:
    cur.execute("DELETE FROM warehouse.\"tblWhse_Inventory\" WHERE item LIKE 'ZZTEST%'")
    for item, mpn, pcn, oh in ROWS:
        cur.execute('INSERT INTO warehouse."tblWhse_Inventory" (pcn,item,mpn,onhandqty,mfg_qty,loc_to) '
                    "VALUES (%s,%s,%s,%s,'0',%s)", (pcn, item, mpn, oh, 'ZZBIN'))

    new_loose  = matched(cur, NEW_LOOSE)
    new_strict = matched(cur, NEW_STRICT)
    old_norm   = matched(cur, OLD_NORM)

    # GREEN — the new exact rule
    check('ZZTESTB' in new_loose,        'NEW: exact same MPN (same case) shows      [ZZTESTB]')
    check('ZZTESTD' in new_loose,        'NEW: exact same MPN (other case) shows     [ZZTESTD]')
    check('ZZTESTC' not in new_loose,    'NEW: dash-differing "like" MPN is EXCLUDED [ZZTESTC]')
    check(new_loose == {'ZZTESTB', 'ZZTESTD'}, 'NEW: matches exactly {B, D}, nothing else')

    # Chemring strict — case-sensitive exact (kept)
    check(new_strict == {'ZZTESTB'},     'Chemring strict: only byte-exact match     {B}')

    # RED-on-old — proves the bug the fix removes
    check('ZZTESTC' in old_norm,         'OLD rule WOULD merge the "like" part       [ZZTESTC]  (bug)')
    check(old_norm != new_loose,         'fix changes behavior (old != new result set)')
finally:
    c.rollback(); c.close()

print(f"  -- {'ALL PASS' if not fails else str(len(fails))+' FAILED'} --")
sys.exit(1 if fails else 0)
