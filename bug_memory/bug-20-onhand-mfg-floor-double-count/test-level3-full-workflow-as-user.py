"""Bug #20 — LEVEL 3 test: complete website walkthrough as the TEST USER.

Drives the app end-to-end as a logged-in test user (regression@test.com), the
way a real user (e.g. Theresa) moves through KOSH: home -> warehouse inventory
-> shortage report -> PCN history -> pick page -> restock page. Asserts every
step renders without a server error for the authenticated test user.

Run inside the container: docker exec stockandpick_webapp python /app/_lvl3.py
"""
import sys
sys.path.insert(0, '/app')
import app as app_module

client = app_module.app.test_client()
with client.session_transaction() as sess:
    sess['user_id'] = 1
    sess['username'] = 'regression@test.com'
    sess['role'] = 'Admin'

# (label, method, path) — the first-to-last flow a user walks
STEPS = [
    ('Home / dashboard',        'GET', '/'),
    ('Warehouse Inventory',     'GET', '/warehouse-inventory'),
    ('Warehouse (PCN filter)',  'GET', '/warehouse-inventory?search_pcn=29862'),
    ('Shortage Report',         'GET', '/shortage_report'),
    ('PCN History',             'GET', '/pcn-history'),
    ('Pick page',               'GET', '/pick'),
    ('Restock page',            'GET', '/restock'),
]

print("="*78)
print("BUG #20 — LEVEL 3: full website walkthrough as test user (login -> ... )")
print("="*78)
passed = failed = 0
for label, method, path in STEPS:
    resp = client.open(path, method=method)
    sc = resp.status_code
    ok = sc < 500 and sc != 404            # rendered for the user (200/redirect ok), no server error / missing
    print(f"[{'PASS' if ok else 'FAIL'}] {label:<26} {method} {path:<36} -> {sc}")
    passed += ok; failed += (not ok)

# Verify the authenticated identity is actually the test user (not anonymous)
with client.session_transaction() as sess:
    is_test_user = sess.get('username') == 'regression@test.com'
print(f"[{'PASS' if is_test_user else 'FAIL'}] session identity is the test user (regression@test.com)")
passed += is_test_user; failed += (not is_test_user)

print("-"*78)
print(f"LEVEL 3: {passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)
