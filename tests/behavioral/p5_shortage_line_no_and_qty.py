#!/usr/bin/env python3
"""PHASE 5 — SR-3 (line-item number) + SR-6 (QTY/REQ never a silent 0).

Both bugs share one root cause: the BOM importer splits a wrapped description into
its OWN tblBOM row, which then carries prose where `line` and `qty` belong:

    line "110"                 | 8603-110 | ST1-DC12V-F | qty "1"   <- the real line
    line "350C FOR 3 SECONDS"  | 8603-110 | ST1-DC12V-F | qty "1"   <- import artifact

Those artifact rows share the aci_pn, mpn AND qty of the real row, so DISTINCT ON
(b.aci_pn) has to break the tie — and which row wins decides what line number the
report prints (SR-3) and, when the artifact's qty holds no number, whether QTY/REQ
read 0 (SR-6).

Proves two shipped fixes, importing the REAL SQL from shortage_sql.py:

  SR-3  BOM_PRIMARY_ORDER_BY prefers a NUMERIC `line`, so the real line always wins.
        RED-on-old: the previous ordering fell through to a plain text sort of
        `line`, so the winner depended on DB COLLATION. This test forces COLLATE "C"
        to show the old rule handing back "(SEE PICTURE" as the line number — under
        en_US the punctuation is folded and it passed BY LUCK, not by design.

  SR-6  UNPARSEABLE_QTY_SQL flags a qty that holds no readable number, carrying the
        RAW text, so the surfaces print "we could not read the BOM" instead of a
        bare 0. It must NOT flag a qty that parses ("1,000", "2 EA") nor a blank one
        (legitimately-empty reference lines — flagging those buries the signal).

Writes fixtures into kosh_test in ONE transaction and ROLLS BACK, leaving the copy
pristine. Exit 0 = pass.
"""
import os, sys, psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
import shortage_sql

DB = os.environ.get('TEST_DB', 'kosh_test')
if DB == 'kosh':
    print('REFUSING: this committing-class test must not target the live copy `kosh`.'); sys.exit(99)
CONN = dict(host=os.environ.get('PGHOST', 'localhost'), port=int(os.environ.get('PGPORT', '5434')),
            user=os.environ.get('PGUSER', 'aci'), password=os.environ['PGPASSWORD'], dbname=DB)

JOB = 'ZZJOBLINE'
# (line, aci_pn, mpn, qty, DESC) — one real line + its importer artifact, per case.
# '(SEE PICTURE' is chosen deliberately: '(' sorts BEFORE '1' in the C collation, so
# under the old text-sort tiebreak the artifact wins and prose becomes the line number.
ROWS = [
    ('10',            'ZZL-10', 'MPN-A', '1,000', 'RESISTOR 100K'),   # real line, comma qty
    ('(SEE PICTURE',  'ZZL-10', 'MPN-A', '1,000', 'BREAK AND USE'),   # artifact of the above
    ('20',            'ZZL-20', 'MPN-B', '2 EA',  'HEADER'),          # real line, unit suffix
    ('30',            'ZZL-30', 'MPN-C', 'USB-B-S-RA', 'SHIFTED'),    # qty holds an MPN -> UNREADABLE
    ('40',            'ZZL-40', 'MPN-D', '',     'REFERENCE ONLY'),   # blank qty -> must NOT flag
]

fails = []
def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)

# The shipped ordering, and the one it replaced (identical except the numeric-line
# term), so the RED/GREEN difference is attributable to exactly that change.
# Kept with their %% escapes: these are executed WITH params, so psycopg2 must not
# read the ILIKE wildcard as a placeholder.
NEW_ORDER = shortage_sql.BOM_PRIMARY_ORDER_BY
OLD_ORDER = """
        ORDER BY b.aci_pn,
                 (b."DESC" ILIKE '%%ZSUB%%'),
                 CASE WHEN b.qty ~ '^[0-9]+([.][0-9]+)?$' THEN b.qty::numeric ELSE 0 END DESC,
                 b.line COLLATE "C"
"""

def primary_lines(cur, order_by):
    """Which row wins per aci_pn under `order_by` — the report's line identity."""
    cur.execute(f"""
        SELECT DISTINCT ON (b.aci_pn) b.aci_pn, b.line, b.qty
        FROM warehouse."tblBOM" b WHERE b.job = %s {order_by}
    """, (JOB,))
    return {r['aci_pn']: (r['line'], r['qty']) for r in cur.fetchall()}

c = psycopg2.connect(**CONN); c.autocommit = False
cur = c.cursor(cursor_factory=RealDictCursor)
try:
    cur.execute('DELETE FROM warehouse."tblBOM" WHERE job = %s', (JOB,))
    for line, acipn, mpn, qty, desc in ROWS:
        cur.execute('INSERT INTO warehouse."tblBOM" (job, job_rev, line, aci_pn, mpn, qty, "DESC", created_at) '
                    "VALUES (%s,'A',%s,%s,%s,%s,%s, NOW())", (JOB, line, acipn, mpn, qty, desc))

    new = primary_lines(cur, NEW_ORDER)
    old = primary_lines(cur, OLD_ORDER)

    # ---- SR-3 GREEN: the real, numeric line wins ----------------------------
    check(new['ZZL-10'][0] == '10',   "SR-3 NEW: real line '10' wins over the import artifact")
    check(new['ZZL-20'][0] == '20',   "SR-3 NEW: line '20' intact")
    check(all(l.isdigit() for l, _ in new.values()),
                                      'SR-3 NEW: every line number printed is numeric')

    # ---- SR-3 RED-on-old: prose became the line number ----------------------
    check(old['ZZL-10'][0] == '(SEE PICTURE',
                                      "SR-3 OLD: artifact '(SEE PICTURE' won as the line no  (bug)")
    check(old != new,                 'SR-3 fix changes behavior (old != new)')

    # ---- SR-6: flag the unreadable qty, and ONLY that one -------------------
    cur.execute(shortage_sql.UNPARSEABLE_QTY_SQL, (JOB, JOB, JOB))
    flagged = {r['aci_pn']: r['raw_qty'] for r in cur.fetchall()}

    check(flagged.get('ZZL-30') == 'USB-B-S-RA',
                                      "SR-6: unreadable qty flagged, RAW text carried ['USB-B-S-RA']")
    check('ZZL-10' not in flagged,    "SR-6: comma qty '1,000' parses — not flagged")
    check('ZZL-20' not in flagged,    "SR-6: unit qty '2 EA' parses — not flagged")
    check('ZZL-40' not in flagged,    'SR-6: blank qty is NOT flagged (reference line, not an error)')
    check(set(flagged) == {'ZZL-30'}, 'SR-6: flags exactly the one unreadable line, nothing else')

    # The flag must describe the row the report actually SHOWS, or it points at a
    # line the user never sees — so it has to agree with the winning primary row.
    check(new['ZZL-30'][1] == 'USB-B-S-RA',
                                      "SR-6: flagged row IS the primary row the report renders")
finally:
    c.rollback(); c.close()

print(f"  -- {'ALL PASS' if not fails else str(len(fails))+' FAILED'} --")
sys.exit(1 if fails else 0)
