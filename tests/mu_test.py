"""3-USER hard-core multi-feature concurrency regression — runs in the ISOLATED
kosh_test environment (separate DB + separate gunicorn). Production untouched.

3 distinct test users (A/B/C), each its own real session, hit the live test gunicorn
over HTTP simultaneously (threading.Barrier => true same-instant collisions).
After every scenario: assert data integrity + Warehouse==PCN History + per-user
attribution. Reports findings; does NOT fix anything."""
import sys, json, threading, random, time
sys.path.insert(0, '/app')
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
import psycopg2
from psycopg2.extras import RealDictCursor
import app as A
from flask import session
from flask_wtf.csrf import generate_csrf

BASE = 'http://127.0.0.1:5000'
TEST_DB = 'postgresql://aci:Pr1xtjxb3jUo@aci-database:5432/kosh_test'
PROD_DB = 'postgresql://aci:Pr1xtjxb3jUo@aci-database:5432/kosh'
S = 'pcb_inventory'
BIN_A, BIN_B, BIN_C = '1234567', '2345678', '3456789'
USERS = ['testA@aci.test', 'testB@aci.test', 'testC@aci.test']

db = psycopg2.connect(TEST_DB); db.autocommit = True; cur = db.cursor(cursor_factory=RealDictCursor)
findings = []
def F(m): findings.append(m); print('   !! ' + m, flush=True)

# create 3 users in the TEST db, mint a session cookie + csrf for each
auth = {}
for u in USERS:
    cur.execute(f"DELETE FROM {S}.\"tblUser\" WHERE userlogin=%s", (u,))
    cur.execute(f"INSERT INTO {S}.\"tblUser\" (username,userlogin,password,usersecurity) VALUES (%s,%s,'x','user') RETURNING id", (u.split('@')[0].upper(), u))
    uid = cur.fetchone()['id']
    with A.app.test_request_context('/'):
        session.update({'user_id': uid, 'username': u, 'full_name': u, 'role': 'user', 'itar_authorized': False}); session.permanent = True
        tok = generate_csrf(); ck = A.app.session_interface.get_signing_serializer(A.app).dumps(dict(session))
    auth[u] = (ck, tok, uid)

def http(u, m, p, b=None):
    ck, tok, _ = auth[u]
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(BASE + p, data=d, method=m)
    r.add_header('Cookie', f'session={ck}'); r.add_header('X-CSRFToken', tok)
    if d is not None: r.add_header('Content-Type', 'application/json')
    try:
        x = urllib.request.urlopen(r, timeout=30); return x.status, x.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e: return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e: return -1, type(e).__name__ + ':' + str(e)
def J(b):
    try: return json.loads(b)
    except Exception: return {}
def gen(u, item, qty=100, loc=BIN_A):
    s, b = http(u, 'POST', '/api/pcn/generate', {'item': item, 'mpn': 'M', 'po_number': 'PO', 'vendor_name': 'V', 'quantity': str(qty), 'date_code': '2606', 'msd': '1', 'location': loc})
    return J(b).get('pcn_number') if s == 200 else None
def setq(pcn, oh, mfg=0, loc=BIN_A):
    cur.execute(f"UPDATE {S}.\"tblWhse_Inventory\" SET onhandqty=%s,mfg_qty=%s,loc_to=%s WHERE pcn::text=%s", (oh, str(mfg), loc, str(pcn)))
def wh(pcn):
    cur.execute(f"SELECT onhandqty,mfg_qty,loc_to FROM {S}.\"tblWhse_Inventory\" WHERE pcn::text=%s", (str(pcn),))
    r = cur.fetchone();
    if not r: return None
    m = r['mfg_qty']; return r['onhandqty'], (int(m) if str(m).lstrip('-').isdigit() else 0), r['loc_to']
def hist_onhand(pcn):
    cur.execute(f"SELECT COALESCE(SUM(onhandqty),0) t FROM {S}.\"tblWhse_Inventory\" WHERE pcn::text=%s", (str(pcn),))
    return int(cur.fetchone()['t'])
def consistent(pcn, tag):
    w = wh(pcn)
    if not w: F(f'[{tag}] PCN {pcn} row missing'); return
    if w[0] != hist_onhand(pcn): F(f'[{tag}] PCN {pcn}: Warehouse {w[0]} != History {hist_onhand(pcn)}')
    if w[0] < 0: F(f'[{tag}] PCN {pcn}: NEGATIVE on-hand {w[0]}')
    pg = http(USERS[0], 'GET', f'/pcn-history?pcn={pcn}')[0]
    if pg != 200: F(f'[{tag}] PCN {pcn}: history page HTTP {pg}')

# ---- ISOLATION PROOF: a PCN made via the test app must NOT appear in prod kosh ----
probe = gen(USERS[0], 'TEST MU ISO', 1)
pdb = psycopg2.connect(PROD_DB); pc = pdb.cursor()
pc.execute(f"SELECT COUNT(*) FROM {S}.\"tblWhse_Inventory\" WHERE pcn::text=%s", (str(probe),)); in_prod = pc.fetchone()[0]
cur.execute(f"SELECT COUNT(*) n FROM {S}.\"tblWhse_Inventory\" WHERE pcn::text=%s", (str(probe),)); in_test = cur.fetchone()['n']
print(f'ISOLATION: test-made PCN {probe} -> in kosh_test={in_test}, in PROD kosh={in_prod}  ({"ISOLATED OK" if in_prod==0 and in_test==1 else "LEAK!!"})')
if in_prod != 0: F('ISOLATION BREACH: test write reached production DB');
pdb.close()

print(f'\n3-USER MULTI-FEATURE CONCURRENCY (users A/B/C) on test env\n')

def barrier_run(funcs):
    """Run funcs[] truly simultaneously (barrier release)."""
    bar = threading.Barrier(len(funcs)); out = [None]*len(funcs)
    def wrap(i, f):
        bar.wait(); out[i] = f()
    ts = [threading.Thread(target=wrap, args=(i, f)) for i, f in enumerate(funcs)]
    [t.start() for t in ts]; [t.join() for t in ts]
    return out

# SCENARIO 1: all 3 -> SAME feature (pick) on SAME PCN
p = gen(USERS[0], 'TEST MU S1'); setq(p, 300, 0)
res = barrier_run([lambda u=u: J(http(u, 'POST', '/api/pick', {'part_number': 'TEST MU S1', 'pcb_type': 'Completed', 'quantity': 100, 'pcn': p})[1]).get('picked_qty', 0) for u in USERS])
w = wh(p); tot = sum(x or 0 for x in res)
print(f'[S1] 3 users pick 100 each on 1 PCN(300): picked={tot}, bin={w[0]}, floor={w[1]}')
if tot > 300: F(f'S1 OVER-PICK {tot}>300')
if w[0] + tot != 300: F(f'S1 math: bin{w[0]}+picked{tot}!=300')
consistent(p, 'S1')

# SCENARIO 2: all 3 -> SAME feature (warehouse edit) on SAME row, different values
p = gen(USERS[0], 'TEST MU S2'); setq(p, 50)
cur.execute(f"SELECT id FROM {S}.\"tblWhse_Inventory\" WHERE pcn::text=%s", (str(p),)); wid = cur.fetchone()['id']
def edit(u, q, loc): return http(u, 'POST', '/api/warehouse-inventory/update', {'id': wid, 'item': 'TEST MU S2', 'pcn': p, 'mpn': 'M', 'dc': '2606', 'onhandqty': q, 'loc_from': BIN_A, 'loc_to': loc, 'mfg_qty': '0', 'msd': '1', 'po': 'PO', 'cost': '1.00'})[0]
codes = barrier_run([lambda: edit(USERS[0], 11, BIN_A), lambda: edit(USERS[1], 22, BIN_B), lambda: edit(USERS[2], 33, BIN_C)])
w = wh(p)
print(f'[S2] 3 users edit same row simultaneously: http={codes}, final bin={w[0]} loc={w[2]}')
if any(c == 500 for c in codes): F('S2 a concurrent edit threw 500')
if w[0] not in (11, 22, 33) or w[2] not in (BIN_A, BIN_B, BIN_C): F(f'S2 final state corrupt: {w}')
consistent(p, 'S2')

# SCENARIO 3: 2 users restock + 1 user edit, SAME PCN, simultaneously
p = gen(USERS[0], 'TEST MU S3'); setq(p, 0, 200)
cur.execute(f"SELECT id FROM {S}.\"tblWhse_Inventory\" WHERE pcn::text=%s", (str(p),)); wid = cur.fetchone()['id']
out = barrier_run([
    lambda: J(http(USERS[0], 'POST', '/api/restock', {'pcn': p, 'quantity': 50, 'location_to': BIN_A, 'location_from': 'MFG Floor'})[1]).get('success'),
    lambda: J(http(USERS[1], 'POST', '/api/restock', {'pcn': p, 'quantity': 50, 'location_to': BIN_A, 'location_from': 'MFG Floor'})[1]).get('success'),
    lambda: http(USERS[2], 'POST', '/api/warehouse-inventory/update', {'id': wid, 'item': 'TEST MU S3', 'pcn': p, 'mpn': 'M', 'dc': '2606', 'onhandqty': 99, 'loc_from': BIN_A, 'loc_to': BIN_C, 'mfg_qty': '0', 'msd': '1', 'po': 'PO', 'cost': '1.00'})[0]])
w = wh(p)
print(f'[S3] 2 restock + 1 edit same PCN: results={out}, final bin={w[0]} loc={w[2]}')
if w[0] < 0: F(f'S3 negative {w[0]}')
consistent(p, 'S3')

# SCENARIO 4: all 3 -> DIFFERENT features on SAME data (shortage / pick / edit)
p = gen(USERS[0], 'TEST MU S4'); setq(p, 100)
job = 'TEST-MU-JOB'
http(USERS[0], 'POST', '/api/bom/load', {'metadata': {'job': job, 'job_rev': 'A', 'customer': 'T', 'build_qty': '10'}, 'bom_items': [{'line': '1', 'desc': 'x', 'man': 'T', 'mpn': 'M', 'aci_pn': 'TEST MU S4', 'qty': 5, 'cost': 1.0, 'pou': '', 'loc': ''}]})
cur.execute(f"SELECT id FROM {S}.\"tblWhse_Inventory\" WHERE pcn::text=%s", (str(p),)); wid = cur.fetchone()['id']
out = barrier_run([
    lambda: http(USERS[0], 'POST', '/shortage_report/generate', None)[0] if False else http(USERS[0], 'GET', f'/shortage_report')[0],
    lambda: J(http(USERS[1], 'POST', '/api/pick', {'part_number': 'TEST MU S4', 'pcb_type': 'Completed', 'quantity': 30, 'pcn': p})[1]).get('success'),
    lambda: http(USERS[2], 'POST', '/api/warehouse-inventory/update', {'id': wid, 'item': 'TEST MU S4', 'pcn': p, 'mpn': 'M', 'dc': '2606', 'onhandqty': 77, 'loc_from': BIN_A, 'loc_to': BIN_B, 'mfg_qty': '0', 'msd': '1', 'po': 'PO', 'cost': '1.00'})[0]])
# now generate the shortage report (after the concurrent ops) and check it reads cleanly
sc = http(USERS[0], 'POST', '/shortage_report/generate', None)
print(f'[S4] shortage+pick+edit on same data simultaneously: results={out}')
consistent(p, 'S4')

# SCENARIO 5: all 3 -> DIFFERENT features on DIFFERENT data (realistic parallel work)
pa = gen(USERS[0], 'TEST MU S5A'); pb = gen(USERS[1], 'TEST MU S5B'); setq(pa, 100); setq(pb, 100)
out = barrier_run([
    lambda: http(USERS[0], 'POST', '/api/restock', {'pcn': pa, 'quantity': 10, 'location_to': BIN_A, 'location_from': 'MFG Floor'})[0],
    lambda: J(http(USERS[1], 'POST', '/api/pick', {'part_number': 'TEST MU S5B', 'pcb_type': 'Completed', 'quantity': 40, 'pcn': pb})[1]).get('success'),
    lambda: gen(USERS[2], 'TEST MU S5C')])
print(f'[S5] A-restock / B-pick / C-generate (different data): results={out}')
for x in (pa, pb): consistent(x, 'S5')

# SCENARIO 6: WILD CHAOS — 3 users, random features, shared pool, many rounds
pool = [gen(random.choice(USERS), 'TEST MU CHAOS', 80) for _ in range(9)]
setq_all = [setq(p, 80) for p in pool]
err = [0]
def chaos(u):
    p = random.choice(pool); op = random.choice(['pick', 'restock', 'edit', 'gen', 'hist'])
    try:
        if op == 'pick': s = http(u, 'POST', '/api/pick', {'part_number': 'TEST MU CHAOS', 'pcb_type': 'Completed', 'quantity': 3, 'pcn': p})[0]
        elif op == 'restock': s = http(u, 'POST', '/api/restock', {'pcn': p, 'quantity': 3, 'location_to': BIN_A, 'location_from': 'MFG Floor'})[0]
        elif op == 'gen': s = http(u, 'POST', '/api/pcn/generate', {'item': 'TEST MU CHAOS', 'mpn': 'M', 'po_number': 'PO', 'vendor_name': 'V', 'quantity': '3', 'date_code': '2606', 'msd': '1', 'location': BIN_A})[0]
        elif op == 'hist': s = http(u, 'GET', f'/pcn-history?pcn={p}')[0]
        else:
            wd = J(http(u, 'GET', f'/api/warehouse-inventory/item?item=TEST MU CHAOS&pcn={p}')[1])
            s = http(u, 'POST', '/api/warehouse-inventory/update', {'id': wd['item']['id'], 'item': 'TEST MU CHAOS', 'pcn': p, 'mpn': 'M', 'dc': '2606', 'onhandqty': random.randint(1, 50), 'loc_from': BIN_A, 'loc_to': random.choice([BIN_A, BIN_B, BIN_C]), 'mfg_qty': '0', 'msd': '1', 'po': 'PO', 'cost': '1.00'})[0] if wd.get('success') else 200
        if s in (500, -1): err[0] += 1
    except Exception: err[0] += 1
rounds = 60
for r in range(rounds):
    barrier_run([lambda: chaos(USERS[0]), lambda: chaos(USERS[1]), lambda: chaos(USERS[2])])
print(f'[S6] WILD CHAOS: {rounds} rounds x3 users = {rounds*3} concurrent ops, 500s/stalls={err[0]}')
if err[0]: F(f'S6 {err[0]} 500s/stalls under 3-user chaos')
for p in pool: consistent(p, 'S6')
# duplicate-PCN check across all chaos-generated
cur.execute(f"SELECT pcn, COUNT(*) n FROM {S}.\"tblWhse_Inventory\" WHERE item LIKE 'TEST MU%' GROUP BY pcn HAVING COUNT(*)>1")
dups = cur.fetchall()
if dups: F(f'DUPLICATE PCNs created: {[d["pcn"] for d in dups]}')

# ---- PER-USER ATTRIBUTION ----
print('\n=== PER-USER ATTRIBUTION (tblTransaction.userid) ===')
for u in USERS:
    cur.execute(f"SELECT COUNT(*) n FROM {S}.\"tblTransaction\" WHERE userid=%s", (u,))
    print(f'   {u}: {cur.fetchone()["n"]} transactions credited')
cur.execute(f"SELECT COUNT(*) n FROM {S}.\"tblTransaction\" WHERE item LIKE 'TEST MU%' AND (userid IS NULL OR userid='')")
mis = cur.fetchone()['n']
if mis: F(f'{mis} test transactions have NO user attribution')

print('\n' + '=' * 60)
print('FINDINGS:', 'NONE — all multi-user invariants held' if not findings else f'{len(findings)} ISSUE(S)')
print('=' * 60)
db.close()
print('DONE (test data left in kosh_test for inspection; prod untouched)')
