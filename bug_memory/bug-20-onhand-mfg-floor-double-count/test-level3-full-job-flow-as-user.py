"""Bug #20 — LEVEL 3 (FULL JOB FLOW) as the TEST USER.

The real end-to-end workflow Preet asked for, driven as regression@test.com:
  1. upload a job file (BOM) on the job page  -> /api/bom/load
  2. generate the shortage report             -> stock must be visible
  3. check Warehouse Inventory == PCN History  (start)
  4. PICK the job                              -> /api/pick
  5. check Warehouse == PCN History again      (bin->floor, total conserved)
  6. RESTOCK                                   -> restock_pcb
  7. check Warehouse == PCN History again      (floor->bin, NO double)

Proves on-hand is conserved and never doubles, and the two screens agree at
every step. Synthetic PCN 99950 / job E2E-JOB-9950, cleaned up at the end.
Run: docker exec stockandpick_webapp python /app/_lvl3full.py
"""
import sys; sys.path.insert(0, '/app')
import app as app_module
from app import db_manager, compute_anchored_history_balances, _persist_shortage_report
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone

SCHEMA = 'pcb_inventory'
ITEM, PCN, JOB, BIN, START, PICKQ = 'E2E-ITEM-9950', 99950, 'E2E-JOB-9950', '1601001', 100, 30
fails = []

def check(name, cond, detail=''):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ''))
    if not cond:
        fails.append(name)

# CSRF is a browser-form guard; the test client calls the JSON APIs directly
# (same pattern as tests/regression_tests.py). Real browser flow keeps CSRF on.
app_module.app.config['WTF_CSRF_ENABLED'] = False
client = app_module.app.test_client()
with client.session_transaction() as s:
    s['user_id'] = 1; s['username'] = 'regression@test.com'; s['role'] = 'Admin'; s['itar_authorized'] = True

conn = db_manager.get_connection(); conn.autocommit = True
cur = conn.cursor(cursor_factory=RealDictCursor)

def cleanup():
    cur.execute(f'DELETE FROM {SCHEMA}."tblShortageReportItems" WHERE report_id IN (SELECT id FROM {SCHEMA}."tblShortageReport" WHERE job::text=%s)', (JOB,))
    cur.execute(f'DELETE FROM {SCHEMA}."tblShortageReport" WHERE job::text=%s', (JOB,))
    cur.execute(f'DELETE FROM {SCHEMA}."tblTransaction" WHERE pcn::text=%s', (str(PCN),))
    cur.execute(f'DELETE FROM {SCHEMA}."tblWhse_Inventory" WHERE pcn::text=%s', (str(PCN),))
    cur.execute(f'DELETE FROM {SCHEMA}."tblBOM" WHERE job::text=%s', (JOB,))
    cur.execute(f'DELETE FROM {SCHEMA}."tblJob" WHERE job_number=%s', (JOB,))

def wh_total():
    cur.execute(f"""SELECT COALESCE(SUM(COALESCE(onhandqty,0)
        + CASE WHEN mfg_qty ~ '^-?[0-9]+$' THEN mfg_qty::int ELSE 0 END),0) t
        FROM {SCHEMA}."tblWhse_Inventory" WHERE pcn::text=%s""", (str(PCN),))
    return int(cur.fetchone()['t'])

def wh_row():
    cur.execute(f"""SELECT onhandqty, CASE WHEN mfg_qty ~ '^-?[0-9]+$' THEN mfg_qty::int ELSE 0 END m, loc_to
        FROM {SCHEMA}."tblWhse_Inventory" WHERE pcn::text=%s""", (str(PCN),))
    r = cur.fetchone(); return (r['onhandqty'], r['m'], r['loc_to']) if r else (None, None, None)

def hist_onhand():
    # exactly what the PCN History page shows: walk the trail backward from the
    # warehouse anchor (onhand + mfg) and read the newest row's balance.
    cur.execute(f"""SELECT trantype, tranqty, COALESCE(reversed,false) reversed, id,
        CASE WHEN tran_time ~ '^[0-9]{{4}}-' THEN tran_time::timestamptz
             WHEN tran_time ~ '^[0-9]{{2}}/' THEN to_timestamp(tran_time,'MM/DD/YY HH24:MI:SS') END sort_time
        FROM {SCHEMA}."tblTransaction" WHERE pcn::text=%s""", (str(PCN),))
    txns = [dict(r) for r in cur.fetchall()]
    for t in txns:
        t['is_relabel'] = False
    anchor = wh_total()
    compute_anchored_history_balances(txns, anchor)
    if not txns:
        return anchor
    newest = max(txns, key=lambda r: (1 if r['sort_time'] else 0,
                                      r['sort_time'] or datetime(1970, 1, 1, tzinfo=timezone.utc),
                                      r['id'] or 0))
    return int(newest['balance'])

def check_both(stage, exp_total, exp_onhand, exp_mfg):
    wt, ho = wh_total(), hist_onhand(); oh, m, loc = wh_row()
    check(f"{stage}: Warehouse == PCN History", wt == ho, f"WH={wt} Hist={ho}")
    check(f"{stage}: total conserved, no double", wt == exp_total, f"total={wt} expect={exp_total}")
    check(f"{stage}: bin={exp_onhand} floor={exp_mfg}", oh == exp_onhand and m == exp_mfg, f"onhand={oh} mfg={m} @ {loc}")

print("=" * 80)
print("BUG #20 — LEVEL 3 (FULL JOB FLOW) as test user regression@test.com")
print("=" * 80)
cleanup()
# seed: START units in a bin + a STOCK txn so PCN History has a trail
cur.execute(f"""INSERT INTO {SCHEMA}."tblWhse_Inventory" (item,pcn,mpn,dc,onhandqty,mfg_qty,loc_from,loc_to)
               VALUES (%s,%s,'E2E-MPN','DC2026',%s,'0','-',%s)""", (ITEM, str(PCN), START, BIN))
cur.execute(f"""INSERT INTO {SCHEMA}."tblTransaction" (trantype,item,pcn,mpn,tranqty,tran_time,loc_from,loc_to,userid)
               VALUES ('STOCK',%s,%s,'E2E-MPN',%s,'01/05/26 09:00:00','Rec Area',%s,'regression@test.com')""",
            (ITEM, str(PCN), str(START), BIN))

# STEP 1 — upload the job file (BOM) on the job page
bom_item = {'line': 1, 'aci_pn': ITEM, 'mpn': 'E2E-MPN', 'desc': 'e2e part', 'qty': 30,
            'cust': 'TestCust', 'man': 'X', 'loc': '', 'pou': '', 'job': JOB, 'job_rev': 'A',
            'cust_pn': '', 'cust_rev': '', 'last_rev': '', 'cost': 1.0}
r = client.post('/api/bom/load', json={'metadata': {'job': JOB, 'job_rev': 'A', 'customer': 'TestCust',
    'cust_pn': '', 'cust_rev': '', 'last_rev': '', 'wo_number': '', 'notes': '', 'build_qty': 1},
    'bom_items': [bom_item]})
jb = r.get_json() if r.is_json else {}
check("STEP 1: upload job BOM (/api/bom/load)", r.status_code == 200 and jb.get('inserted_count') == 1,
      f"status={r.status_code} inserted={jb.get('inserted_count')}")

# STEP 2 — shortage report sees the stock: 100 on hand covers the 30 required,
# so the line is NOT short -> shortage_count 0 (the report counted the stock).
rep = _persist_shortage_report(cur, JOB, 1, 'E2E Report', '', 'regression@test.com')
check("STEP 2: shortage report counts the stock (no false shortage)",
      rep is not None and rep['total_bom_lines'] == 1 and rep['shortage_count'] == 0,
      f"lines={rep and rep['total_bom_lines']} shortages={rep and rep['shortage_count']}")

# STEP 3 — check the two screens (start)
check_both("STEP 3 (start)", START, START, 0)

# STEP 4 — PICK the job
r = client.post('/api/pick', json={'part_number': ITEM, 'pcb_type': 'Completed', 'quantity': PICKQ, 'pcn': PCN})
pj = r.get_json() if r.is_json else {}
check("STEP 4: pick 30 (/api/pick)", r.status_code == 200 and pj.get('success'),
      f"status={r.status_code} {pj.get('error','ok')}")

# STEP 5 — check the two again (bin->floor, total still 100)
check_both("STEP 5 (after pick)", START, START - PICKQ, PICKQ)

# STEP 6 — RESTOCK
rr = db_manager.restock_pcb(pcn=PCN, item=ITEM, quantity=PICKQ, location_from='MFG Floor',
                            location_to=BIN, username='regression@test.com')
check("STEP 6: restock 30 (restock_pcb)", rr.get('success'), rr.get('error', 'ok'))

# STEP 7 — check the two again (floor->bin, NO double: still 100, not 200)
check_both("STEP 7 (after restock)", START, START, 0)

cleanup()
cur.close(); db_manager.return_connection(conn)
print("-" * 80)
print(f"LEVEL 3 FULL JOB FLOW: {'ALL PASS' if not fails else f'{len(fails)} FAILED: ' + ', '.join(fails)}")
sys.exit(0 if not fails else 1)
