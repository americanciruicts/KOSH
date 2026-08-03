#!/usr/bin/env python3
"""PCN History must print the quantity RECORDED on every transaction, not only on PICK.

Theresa, PCN 44956 (2026-07-30): "The parts were restocked at what should have been 46pcs
based on the label created, however history shows restock at 150."

The 46 was in the database the whole time — on that very row. The table rendered `tranqty`
ONLY for PICK rows and printed a dash for everything else, so the put-away row showed no
quantity and the only number on it was the "On Hand" column, which is a computed running
BALANCE. Reading a balance as a quantity is then unavoidable, and it looked like KOSH had
lost 104 parts.

This is database-wide, not one PCN: 155,692 non-PICK rows across 35,134 PCNs had their
quantity suppressed. The fix is display-only, so it corrects every PCN the moment the code
ships — no data migration.

Read-only against $SCORE_DB (default kosh): it only SELECTs. Exit 0 = pass.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from history_balance import qty_display, compute_anchored_history_balances

import psycopg2
from psycopg2.extras import RealDictCursor

DB = os.environ.get('SCORE_DB', 'kosh')          # READ-ONLY here
CONN = dict(host=os.environ.get('PGHOST', 'localhost'), port=int(os.environ.get('PGPORT', '5434')),
            user=os.environ.get('PGUSER', 'aci'), password=os.environ['PGPASSWORD'], dbname=DB)

fails = []
def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)

# ---- the rule itself, independent of any data --------------------------------
check(qty_display({'trantype': 'PTWY',    'tranqty': '46'})    == 46,   'PTWY 46 prints 46 (was a dash)')
check(qty_display({'trantype': 'RNDT',    'tranqty': '46'})    == 46,   'RNDT 46 prints 46 (was a dash)')
check(qty_display({'trantype': 'RESTOCK', 'tranqty': '2000'})  == 2000, 'RESTOCK prints its qty (was a dash)')
check(qty_display({'trantype': 'INDF',    'tranqty': '150'})   == 150,  'INDF prints its qty (was a dash)')
check(qty_display({'trantype': 'PICK',    'tranqty': '-150'})  == 150,  'PICK prints unsigned (the row already says it left)')
check(qty_display({'trantype': 'PURGE',   'tranqty': '0'})     == 0,    'PURGE prints unsigned')
check(qty_display({'trantype': 'ADJT',    'tranqty': '-1000'}) == -1000,'ADJT keeps its SIGN - the sign is the meaning')
check(qty_display({'trantype': 'ADJT',    'tranqty': '30'})    == 30,   'ADJT positive delta prints +30')
check(qty_display({'trantype': 'PTWY',    'tranqty': None})    is None, 'no quantity -> dash, never a fabricated 0')
check(qty_display({'trantype': 'PTWY',    'tranqty': 'n/a'})   is None, 'unreadable quantity -> dash, never a fabricated 0')

c = psycopg2.connect(**CONN)
cur = c.cursor(cursor_factory=RealDictCursor)

# ---- Theresa's actual PCN ----------------------------------------------------
cur.execute("""
    SELECT id, trantype, tranqty, tran_time, loc_from, loc_to, reversed, false AS is_relabel,
           CASE WHEN tran_time ~ '^[0-9]{2}/[0-9]{2}/[0-9]{2}\\s+[0-9]{2}:[0-9]{2}'
                THEN TO_TIMESTAMP(tran_time,'MM/DD/YY HH24:MI:SS') ELSE NULL END AS sort_time
    FROM warehouse."tblTransaction"
    WHERE pcn::text = '44956' AND COALESCE(reversed,false) = false
""")
txns = [dict(r) for r in cur.fetchall()]
if not txns:
    print('  SKIP  PCN 44956 not present in this database copy')
else:
    cur.execute("""SELECT COALESCE(SUM(COALESCE(onhandqty,0)),0) AS a
                   FROM warehouse."tblWhse_Inventory" WHERE pcn::text = '44956'""")
    compute_anchored_history_balances(txns, int(cur.fetchone()['a']))
    rows = {r['trantype']: r for r in txns}
    ptwy = rows.get('PTWY')
    check(ptwy is not None and qty_display(ptwy) == 46,
          f"44956 put-away prints 46 - the label qty she expected (got {qty_display(ptwy) if ptwy else None})")
    check(ptwy is not None and qty_display(ptwy) != ptwy.get('balance'),
          '44956 put-away: the Qty column is NOT the On Hand balance (46 vs the balance she read as 150)')
    check(rows.get('RNDT') is not None and qty_display(rows['RNDT']) == 46,
          '44956 return-from-floor prints 46')

# ---- database-wide: no transaction type is silently blank --------------------
cur.execute("""
    SELECT trantype, count(*) AS n,
           count(*) FILTER (WHERE tranqty ~ '^-?[0-9]+$') AS numeric_qty
    FROM warehouse."tblTransaction"
    WHERE COALESCE(reversed,false) = false AND trantype <> 'PICK'
    GROUP BY trantype ORDER BY n DESC
""")
hidden_before = 0
blank_after = 0
for r in cur.fetchall():
    hidden_before += r['n']
    shown = qty_display({'trantype': r['trantype'], 'tranqty': '1'})
    blank_after += 0 if shown is not None else r['n']
    print(f"      {r['trantype']:16} rows={r['n']:>7}  with a readable qty={r['numeric_qty']:>7}")
check(hidden_before > 0, f'{hidden_before:,} non-PICK rows previously printed a dash instead of their quantity')
check(blank_after == 0, 'after the fix no transaction type is blanked by rule (only genuinely empty values)')

cur.close(); c.close()
print(f"  ── {'ALL PASS' if not fails else str(len(fails))+' FAILED'} ──")
sys.exit(1 if fails else 0)
