#!/usr/bin/env python3
"""REGRESSION GUARD for the bugs that are ALREADY FIXED and working.

Preet, 2026-07-31: "the ones I mentioned below should not get altered and work as it's
working right now — those bugs are already fixed."

Every fix in KOSH so far has had a habit of becoming the next complaint (the PH-1 guard
trigger is exactly what broke WI-1). This file pins the CURRENT, WORKING behaviour of each
closed item so any later change has to prove it did not disturb them. It is deliberately
cheap and fast: mostly assertions against the shipped source/SQL plus a few read-only
queries, so it can be run before AND after every change.

READ-ONLY against $SCORE_DB (default kosh). Exit 0 = nothing regressed.

If an assertion here fails, the change under test broke a closed bug. Do not "fix" this
file to make it pass — fix the change, or bring the trade-off to Preet.
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import psycopg2

DB = os.environ.get('SCORE_DB', 'kosh')          # READ-ONLY here
CONN = dict(host=os.environ.get('PGHOST', 'localhost'), port=int(os.environ.get('PGPORT', '5434')),
            user=os.environ.get('PGUSER', 'aci'), password=os.environ['PGPASSWORD'], dbname=DB)

APP = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()
SHORT = open(os.path.join(ROOT, 'shortage_sql.py'), encoding='utf-8').read()
HIST = open(os.path.join(ROOT, 'history_balance.py'), encoding='utf-8').read()
WHSE_TMPL = open(os.path.join(ROOT, 'templates', 'pcn', 'pcn_history.html'), encoding='utf-8').read()

fails = []
def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)

print("── QTY CAP — no business ceiling; 0 or more is accepted ──")
# Rule changed 2026-07-31 (Preet): the 10,000 cap blocked real reel quantities, 100,000
# blocked them again, so the app no longer guesses an upper bound. The ONLY bound left is
# the int4 limit of the onhandqty column, which exists so an oversized entry gets a
# sentence instead of an opaque 500.
# Match the VALIDATION sites only — a loose regex picks up prose ("on-hand quantity > 0")
# and the location-range label '10000-10999', which are not ceilings.
ceilings = re.findall(r'quantity\s*>\s*(\w+)\s*:', APP) + re.findall(r'<=\s*(\w+)\s*,\s*qty\)', APP)
check(len(ceilings) >= 4, f'the quantity validation sites are still present (found {len(ceilings)})')
check(all(c == 'MAX_QTY' for c in ceilings),
      f'every ceiling is the int4 storage limit, never a business number (found {sorted(set(ceilings))})')
check('MAX_QTY = 2147483647' in APP, 'MAX_QTY is the int4 upper bound')
check(not re.search(r'quantity\s*>\s*\d+\s*:', APP), 'no hard-coded numeric quantity ceiling anywhere')
check(not re.search(r'quantity\s*<\s*1\b', APP), 'no site rejects 0 (stock / PCN / pick / restock all accept it)')
check('IntegerField(\'Quantity\', validators=[InputRequired(), NumberRange(min=0)])' in APP,
      'the stock form accepts 0 (InputRequired, not DataRequired which treats 0 as missing)')
check('IntegerField(\'Quantity to Restock\', validators=[InputRequired(), NumberRange(min=0)])' in APP,
      'the restock form accepts 0')

print("── SR-2 — exact MPN, no fuzzy matching ──")
check('UPPER(w.item) = UPPER(bl.aci_pn)' in APP, 'main stock joins on the EXACT ACI PN')
check('similarity(' not in APP, 'no trigram similarity() anywhere')
check("ILIKE '%' ||" not in APP and "ILIKE '%'||" not in APP, 'no ILIKE %…% fuzzy part matching')

print("── SR-5 — dropped BOM lines: the DISTINCT stays keyed on aci_pn ──")
check('DISTINCT ON (b.aci_pn)' in SHORT, 'shortage SQL keeps DISTINCT ON (b.aci_pn)')
check('DISTINCT ON (b.line)' not in SHORT and 'DISTINCT ON (b.line)' not in APP,
      'nobody re-keyed the DISTINCT on b.line (that publishes 344 import artifacts)')

print("── SR-6 — QTY/REQ must never be a silent 0 ──")
check('UNPARSEABLE_QTY_SQL' in SHORT, 'UNPARSEABLE_QTY_SQL still shipped')
check('UNREADABLE' in APP, 'unreadable qty still surfaces as UNREADABLE, not 0')

print("── SR-7 — a line's own stock is case-insensitive in BOTH copies ──")
check(APP.count('UPPER(w.item) = UPPER(bl.aci_pn)') >= 2, 'both query copies normalise case')
check(not re.search(r'ON\s+w\.item\s*=\s*bl\.aci_pn', APP), 'no case-SENSITIVE own-stock join left')

print("── SR-1 — ZSUB substitutes are carried, not collapsed ──")
check('is_zsub' in SHORT, 'the ZSUB flag is read from the BOM')
check('ZSUB' in SHORT, 'ZSUB alternates are still handled')

print("── SR-3 — a rename carries its stock (no ledger) ──")
check('def part_number_change' in APP, 'part_number_change still exists')
check('relabel_pcn' not in APP, 'it does NOT call the deleted ledger relabel_pcn')

print("── SR-4 — per-PCN rows, not one combined qty ──")
check('def attach_line_subrows' in APP, 'per-PCN sub-row breakdown still shipped')

print("── SR-8 — MFG Floor is never shown as a location ──")
check(APP.count("!= 'MFG Floor'") >= 3, f"floor excluded from the location pick in every copy (found {APP.count(chr(33)+chr(61)+chr(32)+chr(39)+'MFG Floor'+chr(39))})")

print("── SR-9 — on-hand is bin only, floor is NOT added ──")
check('onhandqty + CASE WHEN mfg_qty' not in APP, 'the shortage on-hand does not add mfg_qty')
check('floor counts as on-hand' not in APP, 'the old "floor counts as on-hand" rule is gone')

print("── SO-1 — kitting must not sign the user out ──")
check("app.config['SESSION_COOKIE_SAMESITE']" in APP, 'SameSite is set explicitly')
check("SECRET_KEY" in APP, 'an explicit SECRET_KEY is pinned')

print("── PK-1 — the pick gate and the pick write read the SAME number ──")
check('SUM(onhandqty) as total_qty' in APP, 'availability gate reads the stored onhandqty')
check('ledger.pick' not in APP and 'ledger._subtract' not in APP, 'the pick does NOT go through a ledger')

print("── RS-1 — restock works for parts physically in hand ──")
check('qty at zero' not in APP, 'no "qty at zero" refusal')
check('restock_physical' not in APP, 'no ledger restock_physical path')

print("── WI-1 — the quantity edit verifies against the right column ──")
check('stored_bin, stored_floor, stored_loc = verify' in APP, 'the read-back reads bin, floor AND location')
check("if stored_loc == 'MFG Floor':" in APP, 'on the floor it verifies the MFG Qty column')

print("── PH-1 / WI-2 — no double count, and the Qty column is not a balance ──")
check('_SETTERS' in HIST and 'is_relabel' in HIST, 'the relabel guard that stops phantom on-hand is intact')
check('qty_display' in HIST, 'the Qty column has its own value, separate from the balance')
check('txn.qty_display' in WHSE_TMPL, 'the template prints the recorded qty, not the balance')
check('title="On-hand in a bin AFTER this transaction' in WHSE_TMPL, 'On Hand is labelled as a running balance')

print("── live data invariants (the scoreboard gates) ──")
c = psycopg2.connect(**CONN); cur = c.cursor()
def q(sql):
    cur.execute(sql); return cur.fetchone()[0]
check(q("""SELECT count(*) FROM warehouse."tblWhse_Inventory"
           WHERE COALESCE(onhandqty,0)>0 AND mfg_qty ~ '^[1-9][0-9]*$'""") == 0, 'PH-1 double_count = 0')
check(q("""SELECT count(*) FROM warehouse."tblWhse_Inventory" WHERE COALESCE(onhandqty,0)<0""") == 0, 'no negative bin')
check(q("""SELECT count(*) FROM warehouse."tblWhse_Inventory" WHERE mfg_qty ~ '^-[0-9]+$'""") == 0, 'no negative floor')
check(q("""SELECT count(*) FROM warehouse."tblWhse_Inventory"
           WHERE COALESCE(loc_to,'')='MFG Floor' AND COALESCE(onhandqty,0)<>0""") == 0, 'no floor row holding bin stock')
check(q("""SELECT count(*) FROM warehouse."tblWhse_Inventory"
           WHERE COALESCE(loc_to,'')<>'MFG Floor' AND mfg_qty ~ '^[1-9][0-9]*$'""") == 0, 'no bin row holding floor stock')
cur.close(); c.close()

print(f"  ── {'NOTHING REGRESSED' if not fails else str(len(fails))+' REGRESSED'} ──")
sys.exit(1 if fails else 0)
