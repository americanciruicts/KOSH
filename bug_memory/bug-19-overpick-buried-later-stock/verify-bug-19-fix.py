"""Bug #19 Fix Verification — Over-pick buried later stock (running-floor ledger)

Verifies the running-floor reconcile is present in app.py:
  1. _ONHAND_RECONCILE_SQL builds a running cumulative delta (net_run window)
  2. The final on-hand uses the reflection formula
       (base + sum) - LEAST(0, base + deepest dip)
     instead of the old sum-then-clamp GREATEST(0, base + sum)
  3. The integrity monitor uses the same running-floor form
Static check only (no DB). The behavioral guard is the regression test
tests/regression_tests.py::test_onhand_reconcile_overpick_does_not_zero_refilled_stock
Date: 2026-06-25
"""
import sys
from pathlib import Path

app_py = Path(__file__).resolve().parents[2] / "app.py"
content = app_py.read_text(encoding="utf-8")

checks = []

# 1. running cumulative delta window exists
checks.append((
    "Running cumulative delta window (net_run)",
    "net_run" in content
    and "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in content
    and "SUM(delta) OVER" in content,
))

# 2. reflection formula present (running floor), old sum-then-clamp gone
checks.append((
    "Reflection formula  (base+sum) - LEAST(0, base+min dip)",
    "LEAST(0, MAX(base) + MIN(run_delta))" in content,
))

# 3. old buggy single-clamp net is gone from the shipped reconcile
checks.append((
    "Old GREATEST(0, base+SUM(...)) net removed from _ONHAND_RECONCILE_SQL",
    "COALESCE(MAX(r.rndt_qty), 0)\n                             + SUM(CASE" not in content,
))

# 4. monitor mirror present
checks.append((
    "Integrity monitor uses running-floor too",
    "LEAST(0, MAX(base)+MIN(run_delta))" in content,
))

print("\n" + "=" * 70)
print("BUG #19 FIX VERIFICATION — Over-pick buried later stock")
print("=" * 70)
ok = True
for name, passed in checks:
    print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    ok = ok and passed

print("-" * 70)
print(f"[{'SUCCESS' if ok else 'FAIL'}] Bug #19 verification {'complete' if ok else 'failed'}")
sys.exit(0 if ok else 1)
