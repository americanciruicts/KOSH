"""Bug #23 verify — shortage same-MPN visibility is EXACT, not prefix.

Seeds a BOM line (MPN '1.5KE15') plus two stock rows under OTHER part numbers:
the exact same MPN (must show) and a longer distinct MPN '1.5KE150CA' that
merely starts the same (must NOT show). Builds the shortage report and asserts
only the exact one is counted. Everything runs in a transaction that is ALWAYS
rolled back — nothing persists.

Run inside the container:
  docker exec stockandpick_webapp python3 /tmp/verify-bug-23-fix.py
Exit code 0 = pass.
"""
import os, sys
sys.path.insert(0, '/app')
import app as a
import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA = 'pcb_inventory'
JOB, ACI, MPN = 'VERIFY-BUG23', 'RBUG23-1', '1.5KE15'

conn = psycopg2.connect(os.environ['DATABASE_URL']); conn.autocommit = False
cur = conn.cursor(cursor_factory=RealDictCursor)

def seed_whse(pcn, item, mpn, qty):
    cur.execute(
        f'INSERT INTO {SCHEMA}."tblWhse_Inventory" '
        '(item,pcn,mpn,dc,onhandqty,mfg_qty,loc_from,loc_to) '
        'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
        (item, str(pcn), mpn, 'DC', qty, '0', '-', 'Count Area'))

ok = False
try:
    cur.execute(f'INSERT INTO {SCHEMA}."tblBOM" (line,"DESC",man,mpn,aci_pn,qty,cost,job,job_rev) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                ('10', 'tvs', 'M', MPN, ACI, '10', '1', JOB, 'A'))
    seed_whse(99340, ACI, MPN, 0)            # own stock 0
    seed_whse(99341, 'OTHER-23', MPN, 7)     # exact same MPN under other PN -> MUST show
    seed_whse(99342, 'OTHER-23B', '1.5KE150CA', 999)  # longer distinct -> MUST NOT show

    res = a._persist_shortage_report(cur, JOB, order_qty=1, report_name='v', notes='', username='verify')
    cur.execute(f'SELECT other_mpn_onhand, other_mpn_locations '
                f'FROM {SCHEMA}."tblShortageReportItems" WHERE report_id=%s', (res['report_id'],))
    row = cur.fetchone()
    onhand = row['other_mpn_onhand']
    longer_present = '1.5KE150CA' in (row['other_mpn_locations'] or '')
    ok = (onhand == 7) and not longer_present
    print(f"  other_mpn_onhand = {onhand}  (want 7, the exact '1.5KE15' only)")
    print(f"  distinct longer '1.5KE150CA' present = {longer_present}  (want False)")
    print('  ' + ('PASS' if ok else 'FAIL'))
finally:
    conn.rollback()   # never persist
    conn.close()

print('RESULT:', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
