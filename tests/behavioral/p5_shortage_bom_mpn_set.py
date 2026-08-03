#!/usr/bin/env python3
"""PHASE 5 — the BOM approved-MPN set. Three failures Theresa reported on job 7946L
(handwritten note, "Shortage Report updates.jpg", flagged LIVE):

  1. 7946L-10  "sub has 3 more PCNs available. Not shown on Shortage Report"
  2. 7946L-30  "PCN's 29534, 28800, 36430 not options, MPN does not match"
  3. 7946L-55  "PCN 31639 different MPN NO dash, system put dash in"

ROOT CAUSE (one bug, three faces): the report answered "is this the right part?"
three different ways and none of them used the list the BOM already declares —
the line's primary MPN plus its "ZSUB FOR ABOVE" alternates.

  * on-hand + per-PCN rows matched on ACI PART NUMBER ONLY, never comparing the
    MPN, so anything ever filed under 7946L-30 counted as a 4.7uF 1206 cap;
  * the cross-part-number search DID compare MPN exactly (SR-2, 2026-07-22) but
    only ever searched the PRIMARY MPN, so approved ZSUB stock under another PN
    was invisible to both paths;
  * the per-PCN sub-rows printed the LINE's BOM MPN instead of each PCN's own,
    stamping the dashed "EEE-FC1E101P" over PCN 31639's real "EEEFC1E101P".

The fix introduces the `line_mpns` CTE (primary + ZSUBs, current job_rev) and makes
every stock lookup honour it, keeping SR-2's exact-string rule (case-folded, or
byte-exact for Chemring). Stock that fails the test is NOT dropped silently — it
is reported by `unmatched_pcn_rows_by_acipn` so it shows as a flagged
"NOT ON BOM — verify" row instead of quietly changing a total.

This test IMPORTS the shipped SQL from shortage_sql.py and runs it against the REAL
7946L data in kosh_test, so it cannot pass against a stale copy of the query (which
is why that SQL was lifted out of app.py — app.py builds a Flask app and a DB pool
at module scope and cannot be imported from a test). The only fixture written is
line 10's missing ZSUB alternate row (the kosh_test clone carries an older job_rev
than production), inserted in ONE transaction that is ROLLED BACK.

Exit 0 = pass.
"""
import os, re, sys, psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
import shortage_sql

DB = os.environ.get('TEST_DB', 'kosh_test')
if DB == 'kosh':
    print('REFUSING: this committing-class test must not target the live copy `kosh`.'); sys.exit(99)
CONN = dict(host=os.environ.get('PGHOST', 'localhost'), port=int(os.environ.get('PGPORT', '5434')),
            user=os.environ.get('PGUSER', 'aci'), password=os.environ['PGPASSWORD'], dbname=DB)
JOB, STRICT = '7946L', False          # 7946L is not a Chemring job -> case-insensitive exact

# ── the numbers Theresa's three complaints reduce to ────────────────────────────
# line 10: 1080 primary (PCN 42940) + 5900 approved ZSUB (PCN 40273) — both on the
#          BOM, so on-hand must NOT move; the 3 missing PCNs must appear.
# line 30: 1270 real C1206C475K5PACTU; 450 units of two OTHER parts must drop out.
# line 55: 1506 dashed EEE-FC1E101P; PCN 31639's 500 must drop out AND be flagged.
L10_ONHAND, L30_ONHAND, L55_ONHAND = 6980, 1270, 1506
L30_BAD = {'29534': ('CM316X5R475K50AT', 230), '28800': ('CM316X5R475K50AT', 190),
           '36430': ('C0805C471K5RAC7800', 30)}
L55_BAD = {'31639': ('EEEFC1E101P', 500)}
L10_SUB_PCNS = {'11807': ('8019-3', 100), '11806': ('8041-3', 100), '11805': ('8188L-5', 7)}
ZSUB_MPN = 'C0603C104M5RACTU'

fails = []
def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)


def placeholders(sql):
    """Count real %s params, ignoring %% escapes."""
    return len(re.findall(r'%s', re.sub(r'%%', '', sql)))


def pcn_rows_sql(negate):
    """Assemble the per-PCN row query exactly as app.py's helpers do."""
    return shortage_sql.PCN_ROWS_SQL.format(
        line_mpns=shortage_sql.LINE_MPNS_CTE, negate=negate,
        approved=shortage_sql.mpn_approved('w.item', 'w.mpn'))


MATCH_SQL = shortage_sql.SHORTAGE_MATCH_SQL
OWN_SQL = pcn_rows_sql('')
UNMATCHED_SQL = pcn_rows_sql('NOT ')

# line_mpns(job x3) + bom_lines(job x3) + inv strict + 2x cross-PN strict
n = placeholders(MATCH_SQL)
if n != 9:
    print(f'  FAIL  SHORTAGE_MATCH_SQL takes {n} params, expected 9 '
          f'(6 job + 3 strict). Update this test alongside the query.')
    sys.exit(1)
MATCH_PARAMS = (JOB, JOB, JOB, JOB, JOB, JOB, STRICT, STRICT, STRICT)

c = psycopg2.connect(**CONN); c.autocommit = False
cur = c.cursor(cursor_factory=RealDictCursor)
try:
    # ── FIXTURE: line 10's approved ZSUB alternate, on the CURRENT job_rev ──────
    cur.execute('SELECT job_rev FROM warehouse."tblBOM" WHERE job=%s AND job_rev IS NOT NULL '
                "AND job_rev != '' ORDER BY created_at DESC LIMIT 1", (JOB,))
    rev = (cur.fetchone() or {}).get('job_rev')
    cur.execute('SELECT man, cost, cust, qty FROM warehouse."tblBOM" WHERE job=%s AND line=%s '
                "AND \"DESC\" NOT ILIKE '%%ZSUB%%' LIMIT 1", (JOB, '10'))
    prim = cur.fetchone()
    cur.execute('INSERT INTO warehouse."tblBOM" (job, job_rev, line, aci_pn, mpn, man, "DESC", qty, cost, cust) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (JOB, rev, '10', '7946L-10', ZSUB_MPN, prim['man'], 'ZSUB FOR ABOVE',
                 prim['qty'], prim['cost'], prim['cust']))

    # ── RED-on-old proof: the retired "PN only, no MPN check" on-hand rule ──────
    cur.execute("""
        SELECT COALESCE(SUM(COALESCE(w.onhandqty,0)),0) AS oh
        FROM warehouse."tblWhse_Inventory" w
        WHERE UPPER(w.item) = %s AND COALESCE(w.loc_to,'') != 'MFG Floor'
    """, ('7946L-30',))
    old_l30 = int(cur.fetchone()['oh'])
    check(old_l30 == 1720, f'OLD rule counts 7946L-30 as 1720 (450 wrong-MPN units)  [{old_l30}]  (bug)')

    # ── the real report query ───────────────────────────────────────────────────
    cur.execute(MATCH_SQL, MATCH_PARAMS)
    rows = {str(r['line_no']): r for r in cur.fetchall()}
    for ln in ('10', '30', '55'):
        if ln not in rows: sys.exit(f'FATAL: line {ln} missing from report output')

    check(int(rows['30']['qty_on_hand']) == L30_ONHAND,
          f"line 30 on-hand excludes non-BOM MPNs = {L30_ONHAND}  [{rows['30']['qty_on_hand']}]")
    check(int(rows['55']['qty_on_hand']) == L55_ONHAND,
          f"line 55 on-hand excludes no-dash EEEFC1E101P = {L55_ONHAND}  [{rows['55']['qty_on_hand']}]")
    check(int(rows['10']['qty_on_hand']) == L10_ONHAND,
          f"line 10 on-hand UNCHANGED — approved ZSUB still counts = {L10_ONHAND}  [{rows['10']['qty_on_hand']}]")
    check(int(rows['30']['qty_on_hand']) != old_l30, 'fix changes line 30 (new != old on-hand)')

    # ── complaint 1: the 3 ZSUB PCNs under OTHER part numbers now surface ───────
    subs = {str(s['pcn']): s for s in (rows['10']['other_mpn_locations'] or [])}
    for pcn, (item, qty) in L10_SUB_PCNS.items():
        s = subs.get(pcn)
        check(s is not None and s['item'] == item and int(s['qty']) == qty,
              f'line 10 lists ZSUB PCN {pcn} @ {item} qty {qty}'
              + ('' if s else '   [MISSING]'))
        check(bool(s and s.get('is_zsub')), f'  ...and PCN {pcn} is labelled a ZSUB (not a primary match)')

    # ── complaint 2 + 3: per-PCN rows carry the RIGHT parts and their OWN MPN ───
    cur.execute(OWN_SQL, tuple([JOB] * (placeholders(OWN_SQL) - 1) + [STRICT]))
    own = {}
    for r in cur.fetchall():
        own.setdefault(r['aci_pn'], {})[str(r['pcn'])] = r

    l30 = own.get('7946L-30', {})
    check(set(l30) == {'40102', '37714', '16791'},
          f'line 30 offers ONLY the real C1206C475K5PACTU PCNs  [{sorted(l30)}]')
    for pcn in L30_BAD:
        check(pcn not in l30, f'  ...PCN {pcn} is no longer offered as a pull option')

    l55 = own.get('7946L-55', {})
    check(set(l55) == {'40278', '31633'}, f'line 55 offers only dashed-MPN PCNs  [{sorted(l55)}]')
    check(all(r['mpn'] for r in l55.values()), 'line 55 per-PCN rows carry their OWN mpn (not the BOM line MPN)')
    check(l55.get('40278', {}).get('mpn') == 'EEE-FC1E101P', "  ...PCN 40278 mpn = 'EEE-FC1E101P'")

    # ── nothing vanishes silently: excluded stock is reported as flagged ────────
    cur.execute(UNMATCHED_SQL, tuple([JOB] * (placeholders(UNMATCHED_SQL) - 1) + [STRICT]))
    bad = {}
    for r in cur.fetchall():
        bad.setdefault(r['aci_pn'], {})[str(r['pcn'])] = r

    b30 = bad.get('7946L-30', {})
    check(set(b30) == set(L30_BAD), f'line 30 flags the 3 non-BOM PCNs  [{sorted(b30)}]')
    for pcn, (mpn, qty) in L30_BAD.items():
        r = b30.get(pcn, {})
        check(r.get('mpn') == mpn and int(r.get('qty') or 0) == qty,
              f'  ...PCN {pcn} flagged with its REAL mpn {mpn} qty {qty}')

    b55 = bad.get('7946L-55', {})
    check(set(b55) == set(L55_BAD), f'line 55 flags the no-dash PCN 31639  [{sorted(b55)}]')
    check(b55.get('31639', {}).get('mpn') == 'EEEFC1E101P',
          "  ...PCN 31639 flagged as 'EEEFC1E101P' — the dash is NOT printed over it")

    # excluded + counted must equal what the old rule blindly summed (nothing lost)
    check(L30_ONHAND + sum(q for _, q in L30_BAD.values()) == old_l30,
          'line 30: counted + flagged == old total (no units disappeared)')
finally:
    c.rollback(); c.close()

print(f"  -- {'ALL PASS' if not fails else str(len(fails))+' FAILED'} --")
sys.exit(1 if fails else 0)
