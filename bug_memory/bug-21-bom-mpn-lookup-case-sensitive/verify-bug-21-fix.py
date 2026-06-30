"""Bug #21 verify — /api/bom/mpns/<part> is CASE-INSENSITIVE.

Seeds one BOM row (committed so the endpoint's own connection sees it),
queries the MPN-dropdown endpoint with exact / lower / upper casing, asserts
the MPN comes back every time, then deletes the seed.

Run inside the container:
  docker exec stockandpick_webapp python3 /tmp/verify-bug-21-fix.py
Exit code 0 = pass.
"""
import os, sys
sys.path.insert(0, '/app')
import app as a
import psycopg2

SCHEMA = 'pcb_inventory'
JOB, ACI, MPN = 'VERIFY-BUG21', 'CASETEST-21', 'VERIFY-MPN-21'

conn = psycopg2.connect(os.environ['DATABASE_URL']); conn.autocommit = True
cur = conn.cursor()
cur.execute(f'DELETE FROM {SCHEMA}."tblBOM" WHERE job=%s', (JOB,))
cur.execute(
    f'INSERT INTO {SCHEMA}."tblBOM" (line,"DESC",man,mpn,aci_pn,qty,cost,job,job_rev) '
    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
    ('10', 'verify', 'M', MPN, ACI, '1', '1', JOB, 'A'))

a.app.config['WTF_CSRF_ENABLED'] = False
client = a.app.test_client()
with client.session_transaction() as s:
    s['user_id'] = 1; s['username'] = 'verify@test.com'; s['role'] = 'Admin'

fails = 0
try:
    for variant in (ACI, ACI.lower(), ACI.upper()):
        body = client.get('/api/bom/mpns/' + variant).get_json()
        got = [m['mpn'] for m in body.get('mpns', [])]
        ok = MPN in got
        print(('  PASS' if ok else '  FAIL'), 'query', repr(variant), '->', got)
        fails += 0 if ok else 1
finally:
    cur.execute(f'DELETE FROM {SCHEMA}."tblBOM" WHERE job=%s', (JOB,))
    conn.close()

print('RESULT:', 'ALL PASS' if fails == 0 else f'{fails} FAILED')
sys.exit(1 if fails else 0)
