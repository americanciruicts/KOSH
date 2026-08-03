#!/usr/bin/env python3
"""PHASE 2 — PH-1 / WI-2: PCN History must agree with Warehouse Inventory.

Preet, 2026-07-29, with two live PCNs:

  * PCN 46559 — timeline showed On Hand 60,900; tblWhse_Inventory said 300.
  * PCN 46602 — timeline showed On Hand 20,000; tblWhse_Inventory said 0.

Root cause: PCN History was the last screen still running the CONSERVATION (ledger)
model that Phase 6 deleted everywhere else. The old `_history_delta` summed signed
deltas — +qty for STOCK/RESTOCK, -qty for a PICK — so two STOCKs of 30000 ADDED to
60,000, and a PICK of 10000 SUBTRACTED instead of zeroing the PCN.

Under the model locked 2026-07-17 a transaction STATES the number: restock/stock SET
it, a pick makes it 0, and only an ADJT at one location is a signed delta. Replayed
that way both PCNs land exactly on their stored value.

This test drives the REAL logic in history_balance.py (kept out of app.py so it can be
imported) against the ACTUAL transaction rows for those two PCNs, then sweeps a broad
sample to prove the newest row equals the stored on-hand for every PCN — the Phase 2
exit gate that was never enforced.

Read-only against $SCORE_DB (default kosh): it only SELECTs.

Exit 0 = pass.
"""
import os, sys, psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from history_balance import compute_anchored_history_balances, apply_txn

DB = os.environ.get('SCORE_DB', 'kosh')          # READ-ONLY here
CONN = dict(host=os.environ.get('PGHOST', 'localhost'), port=int(os.environ.get('PGPORT', '5434')),
            user=os.environ.get('PGUSER', 'aci'), password=os.environ['PGPASSWORD'], dbname=DB)

fails = []
def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond: fails.append(label)

TXN = """
    SELECT id, trantype, tranqty, loc_from, loc_to,
           COALESCE(tran_time_ts, NULL) AS sort_time
    FROM (
        SELECT id, trantype, tranqty, loc_from, loc_to,
               CASE WHEN tran_time ~ '^[0-9]{2}/[0-9]{2}/[0-9]{2}'
                    THEN to_timestamp(tran_time, 'MM/DD/YY HH24:MI:SS') END AS tran_time_ts
        FROM warehouse."tblTransaction" WHERE pcn::text = %s
    ) t ORDER BY id
"""
STORED = 'SELECT COALESCE(SUM(COALESCE(onhandqty,0)),0) AS t FROM warehouse."tblWhse_Inventory" WHERE pcn::text = %s'


def newest_balance(cur, pcn):
    cur.execute(TXN, (pcn,))
    rows = [dict(r) for r in cur.fetchall()]
    if not rows:
        return None, None, None
    cur.execute(STORED, (pcn,))
    stored = int(cur.fetchone()['t'])
    _, matched = compute_anchored_history_balances(rows, stored)
    newest = max(rows, key=lambda r: ((r['sort_time'].timestamp() if r['sort_time'] else 0), r['id'] or 0))
    return newest['balance'], stored, matched


c = psycopg2.connect(**CONN)
cur = c.cursor(cursor_factory=RealDictCursor)
try:
    # ── the two PCNs Preet reported ────────────────────────────────────────────
    for pcn, want, was in (('46559', 300, 60900), ('46602', 0, 20000)):
        shown, stored, matched = newest_balance(cur, pcn)
        if shown is None:
            print(f'  SKIP  pcn {pcn} has no transactions in {DB}'); continue
        check(stored == want, f'pcn {pcn}: Warehouse Inventory stores {want}            [{stored}]')
        check(shown == stored, f'pcn {pcn}: history newest row == warehouse ({want}, was {was})  [{shown}]')
        check(matched, f'pcn {pcn}: the REPLAY itself reaches it — no anchor patch needed')

    # ── the one-number semantics, stated directly ──────────────────────────────
    check(apply_txn(30000, {'trantype': 'PICK', 'tranqty': '10000',
                            'loc_from': 'Receiving Area', 'loc_to': 'MFG Floor'}) == 0,
          'a PICK zeroes the PCN (it does NOT subtract the picked qty)')
    check(apply_txn(30000, {'trantype': 'RESTOCK', 'tranqty': '50',
                            'loc_from': 'MFG Floor', 'loc_to': '2203305'}) == 50,
          'a RESTOCK SETS on-hand to the qty entered (it does NOT add)')
    check(apply_txn(30000, {'trantype': 'STOCK', 'tranqty': '250',
                            'loc_from': 'Receiving Area', 'loc_to': '2203305'}) == 250,
          'a STOCK SETS on-hand to the received qty (it does NOT add)')
    check(apply_txn(50, {'trantype': 'ADJT', 'tranqty': '250',
                         'loc_from': '2203305', 'loc_to': '2203305'}) == 300,
          'an ADJT at one location IS a signed delta (the only additive case)')
    check(apply_txn(500, {'trantype': 'ADJT', 'tranqty': '9', 'loc_from': 'A', 'loc_to': 'B',
                          'is_relabel': True}) == 500,
          'a renumber/relabel is quantity-neutral')

    # ── system-wide: newest row must equal the stored number ───────────────────
    cur.execute('''SELECT DISTINCT pcn::text AS p FROM warehouse."tblTransaction"
                   WHERE pcn IS NOT NULL ORDER BY 1 LIMIT 400''')
    pcns = [r['p'] for r in cur.fetchall()]
    agree = disagree = 0
    unmatched_replay = 0
    bad = []
    for p in pcns:
        shown, stored, matched = newest_balance(cur, p)
        if shown is None: continue
        if not matched: unmatched_replay += 1
        if shown == stored: agree += 1
        else:
            disagree += 1
            if len(bad) < 5: bad.append((p, stored, shown))
    tot = agree + disagree
    check(disagree == 0,
          f'sweep of {tot} PCNs: newest row == warehouse on ALL of them   '
          f'[agree {agree} / disagree {disagree}]')
    for b in bad:
        print('       pcn=%-8s stored=%-9s history=%s' % b)
    print(f'       (replay reproduced the stored value unaided on {tot - unmatched_replay}/{tot}; '
          f'{unmatched_replay} needed the anchor — incomplete imported trail)')
finally:
    c.close()

print(f"  -- {'ALL PASS' if not fails else str(len(fails))+' FAILED'} --")
sys.exit(1 if fails else 0)
