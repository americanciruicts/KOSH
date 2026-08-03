#!/usr/bin/env python3
"""PHASE 5 — the approved-MPN rule must hold for a BRAND-NEW job and for an EXISTING
job that gets a NEW BOM (Preet, 2026-07-29: "if i generate a new job number shortage
report or existing job number but with new bom, will it generate with not-in-BOM line
item and not-in-BOM mpn?").

The guard is not baked in anywhere — `line_mpns` is rebuilt from tblBOM at generation
time for the job's CURRENT revision — so a new job and a re-BOM'd job must both come
out clean. This test proves that, and pins the revision edge cases that decide WHICH
BOM counts as current:

  A. brand-new job                     -> only its own BOM's MPNs count
  B. existing job, NEW rev letter      -> the NEW rev defines the approved set; an MPN
                                          that was only on the OLD rev is excluded
  C. existing job, SAME rev re-uploaded-> both uploads share the rev, so both are in
                                          the approved set (a re-upload ADDS, it does
                                          not replace)
  D. existing job, new BOM with BLANK  -> the blank-rev rows are IGNORED and the report
     job_rev                              still uses the OLD lettered rev

C and D are the traps: in both, a "new BOM" does NOT fully replace the old approved set.
Everything runs in ONE transaction against kosh_test and is ROLLED BACK.

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

JOB_NEW, JOB_REBOM = 'ZZJOBNEW', 'ZZJOBREBOM'
PN_NEW, PN_RE = 'ZZJOBNEW-10', 'ZZJOBREBOM-10'
MPN_BOM, MPN_OTHER = 'ZZCAP-100NF', 'ZZWRONG-999'      # on the BOM / never on any BOM
MPN_OLDREV, MPN_NEWREV = 'ZZOLD-REV-ONLY', 'ZZNEW-REV-ONLY'

fails = []
def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)


def placeholders(sql):
    return len(re.findall(r'%s', re.sub(r'%%', '', sql)))


OWN = shortage_sql.PCN_ROWS_SQL.format(line_mpns=shortage_sql.LINE_MPNS_CTE, negate='',
                                       approved=shortage_sql.mpn_approved('w.item', 'w.mpn'))
NP = placeholders(OWN)


def counted(cur, job):
    """{pcn: mpn} the report would COUNT for `job` — i.e. what reaches the report."""
    cur.execute(OWN, tuple([job] * (NP - 1) + [False]))
    return {str(r['pcn']): r['mpn'] for r in cur.fetchall()}


def add_bom(cur, job, pn, mpn, rev, desc='CAP TEST', at='2026-01-01 00:00:00+00'):
    """`at` must be set explicitly per upload. Every row inserted in ONE transaction
    gets the SAME CURRENT_TIMESTAMP (Postgres returns the transaction start time), so
    relying on the default would tie the "latest job_rev" lookup
    (ORDER BY created_at DESC LIMIT 1) and pick a revision arbitrarily. Real uploads
    land in separate transactions minutes or days apart; this models that."""
    cur.execute('INSERT INTO warehouse."tblBOM" (job, job_rev, line, aci_pn, mpn, man, "DESC", qty, cost, created_at) '
                "VALUES (%s,%s,'10',%s,%s,'ZZMAN',%s,'1','0.01',%s)", (job, rev, pn, mpn, desc, at))


def add_stock(cur, pn, mpn, pcn, qty):
    cur.execute('INSERT INTO warehouse."tblWhse_Inventory" (pcn,item,mpn,onhandqty,mfg_qty,loc_to) '
                "VALUES (%s,%s,%s,%s,'0','ZZBIN')", (pcn, pn, mpn, qty))


c = psycopg2.connect(**CONN); c.autocommit = False
cur = c.cursor(cursor_factory=RealDictCursor)
try:
    cur.execute("DELETE FROM warehouse.\"tblBOM\" WHERE job LIKE 'ZZJOB%'")
    cur.execute("DELETE FROM warehouse.\"tblWhse_Inventory\" WHERE item LIKE 'ZZJOB%'")

    # ── A. BRAND-NEW job number ────────────────────────────────────────────────
    add_bom(cur, JOB_NEW, PN_NEW, MPN_BOM, 'A', at='2026-01-01 09:00:00+00')
    add_stock(cur, PN_NEW, MPN_BOM,   'ZZP1', 500)   # right part   -> must count
    add_stock(cur, PN_NEW, MPN_OTHER, 'ZZP2', 900)   # wrong part   -> must NOT count
    got = counted(cur, JOB_NEW)
    check(got.get('ZZP1') == MPN_BOM, 'NEW job: the BOM part counts                    [ZZP1]')
    check('ZZP2' not in got,          'NEW job: a not-in-BOM MPN NEVER reaches the report [ZZP2]')
    check(set(got) == {'ZZP1'},       f'NEW job: nothing else leaks in                    {sorted(got)}')

    # ── B. EXISTING job re-BOM'd with a NEW rev letter ─────────────────────────
    add_bom(cur, JOB_REBOM, PN_RE, MPN_OLDREV, 'A', at='2026-01-01 09:00:00+00')
    add_stock(cur, PN_RE, MPN_OLDREV, 'ZZP3', 300)
    add_stock(cur, PN_RE, MPN_NEWREV, 'ZZP4', 400)
    add_stock(cur, PN_RE, MPN_OTHER,  'ZZP5', 700)
    got = counted(cur, JOB_REBOM)
    check(set(got) == {'ZZP3'}, f'rev A only: just the rev-A MPN counts                {sorted(got)}')

    add_bom(cur, JOB_REBOM, PN_RE, MPN_NEWREV, 'B', at='2026-03-01 09:00:00+00')   # the NEW BOM
    got = counted(cur, JOB_REBOM)
    check('ZZP4' in got,   'NEW BOM (rev B): the new BOM MPN now counts        [ZZP4]')
    check('ZZP3' not in got, 'NEW BOM (rev B): the OLD rev-only MPN is dropped   [ZZP3]')
    check('ZZP5' not in got, 'NEW BOM (rev B): not-in-BOM MPN still never shows  [ZZP5]')
    check(set(got) == {'ZZP4'}, f'NEW BOM (rev B): approved set is the NEW rev only   {sorted(got)}')

    # ── C. TRAP: same rev letter re-uploaded -> ADDS to the approved set ───────
    add_bom(cur, JOB_REBOM, PN_RE, MPN_OLDREV, 'B', at='2026-04-01 09:00:00+00')   # re-upload, SAME rev B
    got = counted(cur, JOB_REBOM)
    check(set(got) == {'ZZP3', 'ZZP4'},
          f'SAME-rev re-upload ADDS (does not replace) — both count  {sorted(got)}')
    check('ZZP5' not in got, '  ...but a not-in-BOM MPN is STILL excluded         [ZZP5]')

    # ── D. TRAP: new BOM uploaded with a BLANK job_rev -> ignored ──────────────
    cur.execute("DELETE FROM warehouse.\"tblBOM\" WHERE job=%s AND mpn=%s AND job_rev='B'",
                (JOB_REBOM, MPN_OLDREV))                       # undo C
    add_bom(cur, JOB_REBOM, PN_RE, MPN_OLDREV, '', at='2026-05-01 09:00:00+00')    # blank rev, newest
    got = counted(cur, JOB_REBOM)
    check(set(got) == {'ZZP4'},
          f'BLANK-rev upload is IGNORED; lettered rev B still rules  {sorted(got)}')
    check('ZZP5' not in got, '  ...and a not-in-BOM MPN is STILL excluded         [ZZP5]')

    # ── the invariant that matters, restated ──────────────────────────────────
    cur.execute("SELECT DISTINCT UPPER(mpn) m FROM warehouse.\"tblBOM\" WHERE job=%s AND COALESCE(mpn,'')<>''",
                (JOB_REBOM,))
    every_bom_mpn = {r['m'] for r in cur.fetchall()}
    check(all(m.upper() in every_bom_mpn for m in counted(cur, JOB_REBOM).values()),
          'INVARIANT: every MPN that reaches the report is on some BOM row')
finally:
    c.rollback(); c.close()

print(f"  -- {'ALL PASS' if not fails else str(len(fails))+' FAILED'} --")
sys.exit(1 if fails else 0)
