"""Exercise the ledger helpers behind reverse_pick / update_warehouse_item / delete_pcn.
Rolls back at the end (copy DB stays pristine)."""
import os, sys
sys.path.insert(0, '/app')
import psycopg2, ledger

PCN, ITEM, MPN, BIN = 'ACCEPT_X_PCN', 'ACCEPT-X-ITEM', 'ACCEPT-X-MPN', '9000002'
fails = []

def total(cur):
    return ledger.on_hand(cur, PCN)

def hist(cur):
    cur.execute("""SELECT COALESCE(SUM((CASE WHEN to_location_id IS NOT NULL THEN qty ELSE 0 END)
                       -(CASE WHEN from_location_id IS NOT NULL THEN qty ELSE 0 END)),0)
                   FROM warehouse.inventory_txn WHERE pcn_id=%s AND reversed=false""", (PCN,))
    return int(cur.fetchone()[0])

def chk(cur, tag, exp):
    t, h = total(cur), hist(cur)
    ok = (t == h == exp)
    print(f'[{"PASS" if ok else "FAIL"}] {tag}: on_hand={t} history={h} (expected {exp})')
    if not ok: fails.append(tag)

conn = psycopg2.connect(host='aci-database', dbname='kosh_rebuild', user='aci',
                        password=os.environ['POSTGRES_PASSWORD'])
conn.autocommit = False
cur = conn.cursor()
try:
    tid = ledger.stock(cur, ITEM, MPN, PCN, 1000, BIN, user='x')
    chk(cur, 'stock 1000', 1000)
    ledger.reverse(cur, tid, user='x')
    chk(cur, 'reverse stock -> 0', 0)

    ledger.stock(cur, ITEM, MPN, PCN, 1000, BIN, user='x')
    ledger.pick(cur, ITEM, MPN, PCN, 400, BIN, user='x')
    chk(cur, 'stock1000 + pick400', 1000)  # transfer conserves total

    # manual edit: set available(bin)=800, floor=100  -> total 900
    ledger.set_pcn_snapshot(cur, ITEM, MPN, PCN, BIN, 800, 100, user='x')
    chk(cur, 'manual set bin800/floor100', 900)

    n = ledger.zero_out(cur, PCN, user='x')
    chk(cur, f'zero_out ({n} locs) -> 0', 0)
finally:
    conn.rollback(); cur.close(); conn.close()

print('\n=== ACCEPTANCE EXTRA: ' + ('ALL PASS' if not fails else f'FAIL {fails}') + ' ===')
sys.exit(1 if fails else 0)
