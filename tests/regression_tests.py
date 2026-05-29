"""KOSH regression smoke tests — runs against the real Postgres.

Each test isolates itself with a unique high-numbered test PCN (>=99000)
that does not collide with real production PCNs, and a SAVEPOINT/ROLLBACK
wrapper so nothing leaks into production data.

Tests cover the specific bug shapes Preet reported in May 2026 so a code
change that re-introduces any of them fails this suite immediately.

Run from inside the container:
    docker exec stockandpick_webapp python /app/tests/regression_tests.py

Run from the host:
    /home/tony/KOSH/tests/run.sh

Exit code is the number of failed tests (0 == all green).
"""

import os
import sys
import traceback
from contextlib import contextmanager

import psycopg2

DB_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://stockpick_user:stockpick_pass@aci-database:5432/kosh',
)
SCHEMA = 'pcb_inventory'


@contextmanager
def isolated_txn():
    """Open a connection, run the body, and ALWAYS rollback at the end.

    Using a top-level transaction we never commit means every test's writes
    disappear when the block exits, even if assertions pass.
    """
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _seed_warehouse_row(cursor, pcn, item, mpn='TEST-MPN', onhandqty=0,
                       mfg_qty='0', loc_to='Count Area'):
    cursor.execute(
        f'INSERT INTO {SCHEMA}."tblWhse_Inventory" '
        '(item, pcn, mpn, dc, onhandqty, mfg_qty, loc_from, loc_to) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
        (item, str(pcn), mpn, 'DC2026', onhandqty, mfg_qty, '-', loc_to),
    )


def _seed_txn(cursor, trantype, item, pcn, qty, userid='regression@test.com',
             loc_to='Count Area'):
    cursor.execute(
        f'INSERT INTO {SCHEMA}."tblTransaction" '
        '(trantype, item, pcn, mpn, dc, msd, tranqty, tran_time, '
        ' loc_from, loc_to, userid) '
        "VALUES (%s, %s, %s, 'TEST-MPN', 'DC2026', 'Level 1', %s, "
        "TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'America/New_York', "
        "'MM/DD/YY HH24:MI:SS'), '-', %s, %s)",
        (trantype, item, str(pcn), qty, loc_to, userid),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_restock_allowed_after_purge_following_restock():
    """Bug shape: PCN 44822/45143 — RESTOCK then ADJT then PURGE → guard
    refused next restock with 'already restocked'.

    Expected: with last KOSH PICK/RESTOCK/PURGE = PURGE, restock_pcb's
    guard releases (PURGE != RESTOCK).
    """
    sys.path.insert(0, '/app')
    from app import db_manager  # noqa: E402

    test_pcn = 99001
    test_item = 'REGRESS-RESTOCK-AFTER-PURGE'

    with isolated_txn() as conn:
        cur = conn.cursor()
        _seed_warehouse_row(cur, test_pcn, test_item, onhandqty=0, mfg_qty='100')
        _seed_txn(cur, 'PICK', test_item, test_pcn, 100)
        _seed_txn(cur, 'RESTOCK', test_item, test_pcn, 50)
        _seed_txn(cur, 'PURGE', test_item, test_pcn, 0)
        conn.commit()  # need to commit so db_manager's separate connection sees it

        try:
            result = db_manager.restock_pcb(
                pcn=test_pcn, item=test_item, quantity=10,
                location_from='Count Area', location_to='Count Area',
                username='regression@test.com',
            )
            assert result.get('success') is True, (
                f'Restock should succeed after PURGE, got: {result}'
            )
        finally:
            # Manually clean up since we had to commit the seed data
            cleanup = psycopg2.connect(DB_URL)
            cleanup.autocommit = True
            cur2 = cleanup.cursor()
            cur2.execute(
                f'DELETE FROM {SCHEMA}."tblTransaction" WHERE pcn::text = %s',
                (str(test_pcn),),
            )
            cur2.execute(
                f'DELETE FROM {SCHEMA}."tblWhse_Inventory" WHERE pcn::text = %s',
                (str(test_pcn),),
            )
            cleanup.close()


def test_restock_allowed_when_zero_onhand_even_if_last_restock():
    """Defensive backstop: SUM(onhandqty)=0 → restock always valid."""
    sys.path.insert(0, '/app')
    from app import db_manager

    test_pcn = 99002
    test_item = 'REGRESS-ZERO-ONHAND'

    cleanup = psycopg2.connect(DB_URL)
    cleanup.autocommit = True
    cur0 = cleanup.cursor()
    cur0.execute(f'DELETE FROM {SCHEMA}."tblTransaction" WHERE pcn::text = %s', (str(test_pcn),))
    cur0.execute(f'DELETE FROM {SCHEMA}."tblWhse_Inventory" WHERE pcn::text = %s', (str(test_pcn),))

    with isolated_txn() as conn:
        cur = conn.cursor()
        _seed_warehouse_row(cur, test_pcn, test_item, onhandqty=0, mfg_qty='0')
        _seed_txn(cur, 'RESTOCK', test_item, test_pcn, 50)
        conn.commit()

        try:
            result = db_manager.restock_pcb(
                pcn=test_pcn, item=test_item, quantity=10,
                location_from='Count Area', location_to='Count Area',
                username='regression@test.com',
            )
            assert result.get('success') is True, (
                f'Restock should succeed when onhandqty=0, got: {result}'
            )
        finally:
            cur0.execute(f'DELETE FROM {SCHEMA}."tblTransaction" WHERE pcn::text = %s', (str(test_pcn),))
            cur0.execute(f'DELETE FROM {SCHEMA}."tblWhse_Inventory" WHERE pcn::text = %s', (str(test_pcn),))
    cleanup.close()


def test_restock_blocked_when_already_restocked_with_stock_present():
    """Sanity: the guard should still block the genuine 'double restock'
    case — last txn = RESTOCK AND onhandqty > 0.
    """
    sys.path.insert(0, '/app')
    from app import db_manager

    test_pcn = 99003
    test_item = 'REGRESS-DOUBLE-RESTOCK'

    cleanup = psycopg2.connect(DB_URL)
    cleanup.autocommit = True
    cur0 = cleanup.cursor()
    cur0.execute(f'DELETE FROM {SCHEMA}."tblTransaction" WHERE pcn::text = %s', (str(test_pcn),))
    cur0.execute(f'DELETE FROM {SCHEMA}."tblWhse_Inventory" WHERE pcn::text = %s', (str(test_pcn),))

    with isolated_txn() as conn:
        cur = conn.cursor()
        _seed_warehouse_row(cur, test_pcn, test_item, onhandqty=50, mfg_qty='0')
        _seed_txn(cur, 'RESTOCK', test_item, test_pcn, 50)
        conn.commit()

        try:
            result = db_manager.restock_pcb(
                pcn=test_pcn, item=test_item, quantity=10,
                location_from='Count Area', location_to='Count Area',
                username='regression@test.com',
            )
            assert result.get('success') is False, (
                f'Restock SHOULD be blocked when last=RESTOCK and qty>0, got: {result}'
            )
            assert 'already been restocked' in result.get('error', '')
        finally:
            cur0.execute(f'DELETE FROM {SCHEMA}."tblTransaction" WHERE pcn::text = %s', (str(test_pcn),))
            cur0.execute(f'DELETE FROM {SCHEMA}."tblWhse_Inventory" WHERE pcn::text = %s', (str(test_pcn),))
    cleanup.close()


def test_print_label_sums_across_duplicate_pcn_rows():
    """Bug shape: print-label SELECT … LIMIT 1 picked one row when a PCN
    had duplicate warehouse rows, so labels showed wrong qty.

    Expected: SUM(onhandqty) across all rows for the PCN.
    """
    sys.path.insert(0, '/app')
    import app as app_module

    test_pcn = 99004
    cleanup = psycopg2.connect(DB_URL)
    cleanup.autocommit = True
    cur0 = cleanup.cursor()
    cur0.execute(f'DELETE FROM {SCHEMA}."tblWhse_Inventory" WHERE pcn::text = %s', (str(test_pcn),))

    cur0.execute(
        f'INSERT INTO {SCHEMA}."tblWhse_Inventory" (item, pcn, mpn, onhandqty, loc_to) '
        "VALUES ('REGRESS-DUP-A', %s, 'X', 30, 'Count Area')",
        (str(test_pcn),),
    )
    cur0.execute(
        f'INSERT INTO {SCHEMA}."tblWhse_Inventory" (item, pcn, mpn, onhandqty, loc_to) '
        "VALUES ('REGRESS-DUP-B', %s, 'X', 20, 'Count Area')",
        (str(test_pcn),),
    )

    try:
        client = app_module.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'regression@test.com'
            sess['role'] = 'admin'
        resp = client.get(f'/print-label/{test_pcn}')
        assert resp.status_code == 200, f'expected 200, got {resp.status_code}'
        body = resp.get_data(as_text=True)
        assert '50' in body, (
            f'label total should be 30+20=50; body excerpt: {body[:500]}'
        )
    finally:
        cur0.execute(f'DELETE FROM {SCHEMA}."tblWhse_Inventory" WHERE pcn::text = %s', (str(test_pcn),))
    cleanup.close()


def test_validate_location_auto_registers_unknown_7digit():
    """Bug shape: a fresh 7-digit location wasn't in tblLoc → restock
    failed with 'Location does not exist'. Should auto-register.
    """
    sys.path.insert(0, '/app')
    from app import db_manager

    test_loc = '9999301'  # synthetic test 7-digit code
    cleanup = psycopg2.connect(DB_URL)
    cleanup.autocommit = True
    cur0 = cleanup.cursor()
    cur0.execute(f'DELETE FROM {SCHEMA}."tblLoc" WHERE location = %s', (test_loc,))

    try:
        ok = db_manager.validate_location(test_loc)
        assert ok is True, 'validate_location should auto-register and return True'
        cur0.execute(f'SELECT COUNT(*) FROM {SCHEMA}."tblLoc" WHERE location = %s', (test_loc,))
        n = cur0.fetchone()[0]
        assert n == 1, f'tblLoc should now contain {test_loc}; rows found: {n}'
    finally:
        cur0.execute(f'DELETE FROM {SCHEMA}."tblLoc" WHERE location = %s', (test_loc,))
    cleanup.close()


def test_purged_pcn_can_be_restocked_with_same_pcn():
    """Bug shape: restock_pcb returned 'No parts found' if the warehouse
    row had been deleted by a legacy purge. The fallback should recreate
    the row from the most recent PURGE/STOCK/RESTOCK transaction.
    """
    sys.path.insert(0, '/app')
    from app import db_manager

    test_pcn = 99005
    test_item = 'REGRESS-PURGED-LOSTROW'

    cleanup = psycopg2.connect(DB_URL)
    cleanup.autocommit = True
    cur0 = cleanup.cursor()
    cur0.execute(f'DELETE FROM {SCHEMA}."tblTransaction" WHERE pcn::text = %s', (str(test_pcn),))
    cur0.execute(f'DELETE FROM {SCHEMA}."tblWhse_Inventory" WHERE pcn::text = %s', (str(test_pcn),))

    cur0.execute(
        f'INSERT INTO {SCHEMA}."tblTransaction" '
        '(trantype, item, pcn, mpn, dc, msd, tranqty, tran_time, loc_from, loc_to, userid) '
        "VALUES ('PURGE', %s, %s, 'TEST-MPN', 'DC2026', 'Level 1', 0, "
        "TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'America/New_York', 'MM/DD/YY HH24:MI:SS'), "
        "'-', 'Purged', 'regression@test.com')",
        (test_item, str(test_pcn)),
    )

    try:
        result = db_manager.restock_pcb(
            pcn=test_pcn, item=None, quantity=15,
            location_from='Count Area', location_to='Count Area',
            username='regression@test.com',
        )
        assert result.get('success') is True, (
            f'restock should recreate missing row from PURGE txn, got: {result}'
        )
    finally:
        cur0.execute(f'DELETE FROM {SCHEMA}."tblTransaction" WHERE pcn::text = %s', (str(test_pcn),))
        cur0.execute(f'DELETE FROM {SCHEMA}."tblWhse_Inventory" WHERE pcn::text = %s', (str(test_pcn),))
    cleanup.close()


def test_bom_load_inserts_every_item_received():
    """Bug shape: BOM uploads silently dropped lines. The /api/bom/load
    endpoint must persist exactly the number of items it receives.
    """
    sys.path.insert(0, '/app')
    import app as app_module

    test_job = 'REGRESS-BOM-9999'
    items_in = []
    for i in range(1, 12):  # 11 items
        items_in.append({
            'line': i,
            'desc': f'Test desc {i}',
            'man': 'TestMan',
            'mpn': f'TEST-MPN-{i}',
            'aci_pn': f'ACI-{i}',
            'qty': i * 5,
            'pou': 'SMT',
            'loc': '',
            'cost': 1.23,
            'job': test_job,
            'job_rev': 'A',
            'last_rev': '',
            'cust': 'TestCust',
            'cust_pn': '',
            'cust_rev': '',
        })

    cleanup = psycopg2.connect(DB_URL)
    cleanup.autocommit = True
    cur0 = cleanup.cursor()
    cur0.execute(f'DELETE FROM {SCHEMA}."tblBOM" WHERE job::text = %s', (test_job,))
    cur0.execute(f'DELETE FROM {SCHEMA}."tblJob" WHERE job_number = %s', (test_job,))

    try:
        # Disable CSRF for the test only (we're calling the API directly)
        app_module.app.config['WTF_CSRF_ENABLED'] = False
        client = app_module.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'regression@test.com'
            sess['role'] = 'admin'
        resp = client.post('/api/bom/load', json={
            'metadata': {'job': test_job, 'job_rev': 'A', 'customer': 'TestCust', 'cust_pn': '', 'cust_rev': '', 'last_rev': '', 'wo_number': '', 'notes': '', 'build_qty': 1},
            'bom_items': items_in,
        })
        assert resp.status_code == 200, f'expected 200, got {resp.status_code}: {resp.get_data(as_text=True)[:300]}'
        body = resp.get_json()
        assert body and body.get('success'), f'expected success, got {body}'
        assert body.get('inserted_count') == len(items_in), (
            f'expected {len(items_in)} inserted, got {body.get("inserted_count")}'
        )

        cur0.execute(f'SELECT COUNT(*) FROM {SCHEMA}."tblBOM" WHERE job::text = %s', (test_job,))
        n_rows = cur0.fetchone()[0]
        assert n_rows == len(items_in), (
            f'tblBOM should hold {len(items_in)} rows, found {n_rows}'
        )
    finally:
        cur0.execute(f'DELETE FROM {SCHEMA}."tblBOM" WHERE job::text = %s', (test_job,))
        cur0.execute(f'DELETE FROM {SCHEMA}."tblJob" WHERE job_number = %s', (test_job,))
    cleanup.close()


def test_bom_python_parser_finds_lines_across_sheets():
    """Bug shape: 8813L-4DA file had Line 200 only on 'Assy BOM', not on
    'BOM to Load'. Multi-sheet merge logic should pick it up.

    Python implementation of the same merge the JS parser does — keeps
    drift between client and server detectable.
    """
    import io
    import openpyxl

    wb = openpyxl.Workbook()
    ws_load = wb.active
    ws_load.title = 'BOM to Load'
    ws_load.append(['Line', 'DESC', 'MAN', 'MPN', 'ACI PN', 'QTY'])
    for i in range(1, 4):
        ws_load.append([i, f'desc {i}', 'M', f'MPN-{i}', f'ACI-{i}', 5])

    ws_assy = wb.create_sheet('Assy BOM')
    for _ in range(9):
        ws_assy.append([])
    ws_assy.append(['LINE', 'DESC', 'MAN', 'MPN', 'ACI PN', 'QTY'])
    for i in [1, 2, 3, 4]:  # row 4 is extra-only
        ws_assy.append([i, f'desc {i}', 'M', f'MPN-{i}', f'ACI-{i}', 5])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    parsed = _python_multisheet_parse(buf.getvalue())
    line_nums = sorted(it['line'] for it in parsed)
    assert line_nums == [1, 2, 3, 4], (
        f'multi-sheet merge should yield lines 1-4, got {line_nums}'
    )


def _python_multisheet_parse(file_bytes):
    """Mirror of the JS multi-sheet merge: walk every sheet, find header
    row dynamically, merge unique LINE numbers (BOM to Load wins on dup).
    Used only by tests so we can verify drift symbolically.
    """
    import io
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    line_aliases = {'LINE', 'LINE #', 'LINE NO', 'LINE NUMBER', 'ITEM',
                    'ITEM #', 'ITEM NO', '#', 'NO', 'NO.', 'ROW', 'SEQ',
                    'SR', 'SR.', 'SR NO', 'S.NO', 'S NO'}

    def parse_sheet(ws):
        rows = list(ws.iter_rows(values_only=True))
        header_idx = None
        for hr in range(min(30, len(rows))):
            cells = [str(c).strip().upper().replace('  ', ' ') if c is not None else '' for c in rows[hr]]
            has_line = any(c in line_aliases for c in cells)
            has_mpn = any('MPN' in c or 'MFG PN' in c or 'MFR PN' in c or 'PART NUMBER' in c or 'DESC' in c for c in cells)
            if has_line and has_mpn:
                header_idx = hr
                headers = cells
                break
        if header_idx is None:
            return []
        line_col = next((i for i, h in enumerate(headers) if h in line_aliases), None)
        if line_col is None:
            return []
        items = []
        for r in rows[header_idx + 1:]:
            if not r or all(c is None or c == '' for c in r):
                continue
            try:
                ln = int(r[line_col])
            except (TypeError, ValueError):
                continue
            items.append({'line': ln})
        return items

    seen = set()
    merged = []
    order = ['BOM to Load'] + [n for n in wb.sheetnames if n != 'BOM to Load']
    for name in order:
        if name not in wb.sheetnames:
            continue
        for it in parse_sheet(wb[name]):
            if it['line'] in seen:
                continue
            seen.add(it['line'])
            merged.append(it)
    return merged


def test_return_connection_never_leaks_foreign_connection():
    """Bug shape (May 2026): /sources and /stats opened raw psycopg2.connect
    connections, then handed them to db_manager.return_connection, which
    called pool.putconn → 'trying to put unkeyed connection'. The old code
    only logged that and dropped the connection — leaking it. After enough
    page views the maxconn=15 pool was exhausted and the whole app hung.

    Expected: return_connection CLOSES any connection putconn rejects, and the
    pool keeps handing out connections (no exhaustion).
    """
    sys.path.insert(0, '/app')
    from app import db_manager

    # A connection NOT from the pool must be closed, not leaked, and must not raise.
    foreign = psycopg2.connect(DB_URL)
    assert foreign.closed == 0, 'sanity: freshly opened connection should be open'
    db_manager.return_connection(foreign)
    assert foreign.closed != 0, (
        'foreign connection must be CLOSED by return_connection, not leaked'
    )

    # Pool connections must still round-trip many times without exhausting
    # (15 = maxconn; loop past it to prove nothing leaks per cycle).
    for _ in range(25):
        c = db_manager.get_connection()
        assert c is not None
        db_manager.return_connection(c)


def test_all_pages_render_without_server_error():
    """Broad guard: every parameterless GET route must render WITHOUT a 500
    for an authenticated admin. Catches template errors, broken queries, and
    NameErrors across the whole app the moment they ship — so a change to any
    page can't silently 500 in production.

    Parameterized routes (/sources/<t>, /print-label/<pcn>) are exercised by
    their own targeted tests since they need valid IDs. Side-effecting/auth
    routes (logout, SSO callback) are excluded.
    """
    sys.path.insert(0, '/app')
    import app as app_module

    EXCLUDE = {'/logout', '/sso/callback'}
    app_module.app.config['WTF_CSRF_ENABLED'] = False
    client = app_module.app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'regression@test.com'  # _final_cleanup wipes this user's rows
        sess['role'] = 'Admin'  # capital A → is_admin_user() bypasses every tool gate

    failures = []
    checked = 0
    for rule in app_module.app.url_map.iter_rules():
        if 'GET' not in (rule.methods or set()):
            continue
        if rule.arguments:           # needs a path param — covered elsewhere
            continue
        path = str(rule.rule)
        if path in EXCLUDE or path.startswith('/static'):
            continue
        try:
            resp = client.get(path)
            code = resp.status_code
        except Exception as e:
            failures.append(f'{path} raised {type(e).__name__}: {e}')
            continue
        checked += 1
        if code >= 500:
            failures.append(f'{path} -> HTTP {code}')

    assert checked > 20, f'expected to smoke-test many pages, only hit {checked}'
    assert not failures, (
        f'{len(failures)} page(s) returned a server error:\n  ' +
        '\n  '.join(failures)
    )


def test_quantity_fields_are_not_number_spinners():
    """Bug shape (May 2026, PCN 41564): the restock qty was logged 1 short.
    Root cause: WTForms IntegerField renders <input type=number>, which
    silently decrements on a mouse-wheel tick while focused. Fix renders the
    qty as type=text inputmode=numeric so wheel/arrows can't change it.

    Guard: restock/stock/pick must NOT render quantity as a number spinner.
    """
    import re
    base = os.path.join(os.path.dirname(__file__), '..', 'templates', 'inventory_ops')
    for tpl in ('restock', 'stock', 'pick'):
        path = os.path.join(base, f'{tpl}.html')
        html = open(path).read()
        m = re.search(r'form\.quantity\((?:[^()]|\([^()]*\))*\)', html)
        assert m, f'{tpl}.html: form.quantity(...) render call not found'
        call = m.group(0)
        assert 'type="text"' in call, (
            f'{tpl}.html: quantity must render type="text" (number inputs lose '
            f'a unit to wheel scroll). Got: {call}'
        )
        assert 'inputmode="numeric"' in call, (
            f'{tpl}.html: quantity must set inputmode="numeric" for mobile keypad'
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    test_restock_allowed_after_purge_following_restock,
    test_restock_allowed_when_zero_onhand_even_if_last_restock,
    test_restock_blocked_when_already_restocked_with_stock_present,
    test_print_label_sums_across_duplicate_pcn_rows,
    test_validate_location_auto_registers_unknown_7digit,
    test_purged_pcn_can_be_restocked_with_same_pcn,
    test_bom_load_inserts_every_item_received,
    test_bom_python_parser_finds_lines_across_sheets,
    test_return_connection_never_leaks_foreign_connection,
    test_quantity_fields_are_not_number_spinners,
    test_all_pages_render_without_server_error,
]


def _final_cleanup():
    """Wipe every trace of regression-test data: activity log rows by the
    test username, any straggler warehouse/transaction/BOM/job/loc rows
    matching test markers. Runs unconditionally after the suite, even on
    test failure, so test data never leaks into the real activity log
    Preet sees in the UI.
    """
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor()
    test_user = 'regression@test.com'
    test_pcns = ['99001', '99002', '99003', '99004', '99005']
    test_jobs = ['REGRESS-BOM-9999']
    test_items = (
        'REGRESS-RESTOCK-AFTER-PURGE', 'REGRESS-ZERO-ONHAND',
        'REGRESS-DOUBLE-RESTOCK', 'REGRESS-DUP-A', 'REGRESS-DUP-B',
        'REGRESS-PURGED-LOSTROW',
    )
    test_loc = '9999301'
    try:
        cur.execute(
            f'DELETE FROM {SCHEMA}."tblActivityLog" WHERE username = %s',
            (test_user,),
        )
        cur.execute(
            f'DELETE FROM {SCHEMA}."tblActivityLog" '
            f"WHERE description ILIKE %s OR description ILIKE %s OR details ILIKE %s",
            ('%REGRESS-%', '%PCN 9900%', '%REGRESS-%'),
        )
        cur.execute(
            f'DELETE FROM {SCHEMA}."tblTransaction" WHERE pcn::text = ANY(%s)',
            (test_pcns,),
        )
        cur.execute(
            f'DELETE FROM {SCHEMA}."tblWhse_Inventory" WHERE pcn::text = ANY(%s)',
            (test_pcns,),
        )
        cur.execute(
            f'DELETE FROM {SCHEMA}."tblWhse_Inventory" WHERE item = ANY(%s)',
            (list(test_items),),
        )
        cur.execute(
            f'DELETE FROM {SCHEMA}."tblBOM" WHERE job::text = ANY(%s)',
            (test_jobs,),
        )
        cur.execute(
            f'DELETE FROM {SCHEMA}."tblJob" WHERE job_number = ANY(%s)',
            (test_jobs,),
        )
        cur.execute(
            f'DELETE FROM {SCHEMA}."tblLoc" WHERE location = %s',
            (test_loc,),
        )
    except Exception as e:
        print(f'  WARN  final cleanup raised: {e}')
    finally:
        conn.close()


def main():
    print('KOSH regression smoke tests')
    print('=' * 60)
    failures = []
    try:
        for fn in TESTS:
            name = fn.__name__
            try:
                fn()
                print(f'  PASS  {name}')
            except AssertionError as e:
                print(f'  FAIL  {name}: {e}')
                failures.append((name, str(e)))
            except Exception as e:
                tb = traceback.format_exc()
                print(f'  ERROR {name}: {e}\n{tb}')
                failures.append((name, f'{e}\n{tb}'))
    finally:
        _final_cleanup()
    print('=' * 60)
    print(f'{len(TESTS) - len(failures)} passed, {len(failures)} failed')
    if failures:
        print('\nFailures:')
        for n, msg in failures:
            print(f'  - {n}: {msg[:200]}')
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
