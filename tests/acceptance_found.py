"""Acceptance FOUND — restock is never blocked by the MFG Floor balance.

Theresa, 2026-07-15: restock refused PCN 38159 with "insufficient stock at MFG
Floor: have 0, need 62" even though PCN History showed it picked at 62. The floor
balance is an inference (no consumption event for years + the 2026-07-14 >6mo
stale-floor sweep zeroed 9,859 PCNs), so it must never veto parts the operator is
physically holding.

Covers:
  * floor 0        -> whole restock lands, entirely as FOUND (Theresa's exact case)
  * floor >= qty   -> unchanged legacy behaviour, pure transfer, ZERO found
  * floor short    -> split: transfer what the floor has, FOUND the remainder
  * strict restock() STILL rejects an over-restock (reverse_pick must not mint stock)
  * a FOUND row reverses cleanly (I5)
  * Warehouse projection == ledger balance at every step

Runs inside one transaction and ROLLS BACK at the end, so the DB is left pristine.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/app')  # ledger.py is copied next to app.py in the container
import ledger
import testdb

PCN = 'ACCEPT_FOUND_TESTPCN'
ITEM = 'ACCEPT-FOUND-ITEM'
MPN = 'ACCEPT-FOUND-MPN'
BIN = '9000002'
FLOOR = 'MFG Floor'

failures = []


def hist(cur, pcn):
    """PCN History on-hand = signed replay of the one ledger (WHERE reversed=false)."""
    cur.execute(
        """
        SELECT COALESCE(SUM((CASE WHEN to_location_id   IS NOT NULL THEN qty ELSE 0 END)
                           -(CASE WHEN from_location_id IS NOT NULL THEN qty ELSE 0 END)),0)
        FROM warehouse.inventory_txn WHERE pcn_id=%s AND reversed=false
        """,
        (pcn,),
    )
    return int(cur.fetchone()[0])


def loc_qty(cur, pcn, code):
    cur.execute(
        """
        SELECT COALESCE(SUM(b.qty),0) FROM warehouse.inventory_balance b
        JOIN warehouse.inv_location l USING(location_id)
        WHERE b.pcn_id=%s AND lower(l.code)=lower(%s)
        """,
        (pcn, code),
    )
    return int(cur.fetchone()[0])


def check(cur, label, exp_bin, exp_floor):
    warehouse_total = ledger.on_hand(cur, PCN)
    history_total = hist(cur, PCN)
    b = loc_qty(cur, PCN, BIN)
    f = loc_qty(cur, PCN, FLOOR)
    ok = (b == exp_bin and f == exp_floor
          and warehouse_total == exp_bin + exp_floor
          and warehouse_total == history_total)
    status = 'PASS' if ok else 'FAIL'
    print(f'[{status}] {label}: bin={b} floor={f} '
          f'warehouse_total={warehouse_total} history_total={history_total} '
          f'(expected bin={exp_bin} floor={exp_floor} total={exp_bin+exp_floor})')
    if not ok:
        failures.append(label)


def expect_split(label, split, exp_transfer, exp_found):
    ok = split['transferred'] == exp_transfer and split['found'] == exp_found
    print(f"[{'PASS' if ok else 'FAIL'}] {label}: transferred={split['transferred']} "
          f"found={split['found']} (expected transferred={exp_transfer} found={exp_found})")
    if not ok:
        failures.append(label)


def found_rows(cur, pcn):
    cur.execute(
        "SELECT COALESCE(SUM(qty),0) FROM warehouse.inventory_txn "
        "WHERE pcn_id=%s AND txn_type='FOUND' AND reversed=false",
        (pcn,),
    )
    return int(cur.fetchone()[0])


def main():
    conn = testdb.connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        # ---- 1) THERESA'S CASE: nothing on the floor, operator holds 62 parts. ----
        # Old code: LedgerError, restock refused. New: it lands, labelled FOUND.
        split = ledger.restock_physical(cur, ITEM, MPN, PCN, 62, BIN, user='acceptance')
        expect_split('floor 0, restock 62 -> all FOUND', split, exp_transfer=0, exp_found=62)
        check(cur, 'after restock 62 onto empty floor', exp_bin=62, exp_floor=0)

        # The units are LABELLED, not smuggled in as a transfer.
        f = found_rows(cur, PCN)
        ok = f == 62
        print(f"[{'PASS' if ok else 'FAIL'}] FOUND rows recorded: {f} (expected 62)")
        if not ok:
            failures.append('FOUND not recorded')

        # ---- 2) HONEST CASE: floor covers it -> pure transfer, nothing found. ----
        ledger.pick(cur, ITEM, MPN, PCN, 62, BIN, user='acceptance')
        check(cur, 'after pick 62 back to floor', exp_bin=0, exp_floor=62)
        split = ledger.restock_physical(cur, ITEM, MPN, PCN, 40, BIN, user='acceptance')
        expect_split('floor 62, restock 40 -> pure transfer', split,
                     exp_transfer=40, exp_found=0)
        check(cur, 'after restock 40 (22 left on floor)', exp_bin=40, exp_floor=22)

        # ---- 3) SHORT FLOOR: transfer what exists, FOUND the rest. ----
        # Floor has 22; operator physically holds 50.
        split = ledger.restock_physical(cur, ITEM, MPN, PCN, 50, BIN, user='acceptance')
        expect_split('floor 22, restock 50 -> split 22/28', split,
                     exp_transfer=22, exp_found=28)
        check(cur, 'after short-floor restock 50', exp_bin=90, exp_floor=0)

        # ---- 4) The strict path MUST still reject: reversals cannot mint stock. ----
        cur.execute('SAVEPOINT sp')
        rejected = False
        try:
            ledger.restock(cur, ITEM, MPN, PCN, 9999, BIN, user='acceptance')
        except ledger.LedgerError as e:
            rejected = True
            cur.execute('ROLLBACK TO SAVEPOINT sp')
            print(f'[PASS] strict restock() over-restock REJECTED: {e}')
        if not rejected:
            failures.append('strict restock() did not reject over-restock')
            print('[FAIL] strict restock() failed to reject over-restock')
        check(cur, 'after rejected strict over-restock (unchanged)', exp_bin=90, exp_floor=0)

        # ---- 5) A FOUND row reverses cleanly (I5). ----
        cur.execute(
            "SELECT txn_id, qty FROM warehouse.inventory_txn "
            "WHERE pcn_id=%s AND txn_type='FOUND' AND reversed=false "
            "ORDER BY txn_id DESC LIMIT 1",
            (PCN,),
        )
        txn_id, qty = cur.fetchone()
        ledger.reverse(cur, txn_id, user='acceptance')
        check(cur, f'after reversing FOUND txn {txn_id} (-{qty})',
              exp_bin=90 - qty, exp_floor=0)

        # ---- 6) Warehouse projection agrees with the ledger (I3). ----
        cur.execute(
            'INSERT INTO warehouse."tblWhse_Inventory" (pcn, item, mpn, onhandqty, mfg_qty) '
            "VALUES (%s,%s,%s,0,'0')",
            (PCN, ITEM, MPN),
        )
        ledger.project_warehouse(cur, PCN)
        cur.execute(
            'SELECT COALESCE(onhandqty,0), '
            "CASE WHEN mfg_qty ~ '^-?[0-9]+$' THEN mfg_qty::int ELSE 0 END "
            'FROM warehouse."tblWhse_Inventory" WHERE pcn::text=%s',
            (PCN,),
        )
        proj_bin, proj_floor = cur.fetchone()
        exp_bin, exp_floor = loc_qty(cur, PCN, BIN), loc_qty(cur, PCN, FLOOR)
        ok = proj_bin == exp_bin and proj_floor == exp_floor
        print(f"[{'PASS' if ok else 'FAIL'}] Warehouse projection == ledger: "
              f'onhandqty={proj_bin} mfg_qty={proj_floor} '
              f'(expected {exp_bin}/{exp_floor})')
        if not ok:
            failures.append('projection != ledger')

    finally:
        conn.rollback()   # leave the DB pristine
        cur.close()
        conn.close()

    print('\n=== ACCEPTANCE FOUND: ' + ('ALL PASS' if not failures
          else f'{len(failures)} FAILURE(S): {failures}') + ' ===')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
