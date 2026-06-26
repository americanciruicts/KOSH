"""Bug #20 Fix Verification — bin/floor on-hand double-count

Static checks that the fix is present in app.py:
  1. PCN History anchor sums onhandqty + mfg_qty (not onhand only)
  2. reconcile_floor_onhand guard + its SQL exist
  3. The guard is wired into the background sync loop
  4. The false "0 rows with both onhandqty>0 AND mfg_qty>0" claim is gone
Behavioral guards: tests/regression_tests.py::
  test_floor_onhand_dedupe_zeroes_phantom_bin_not_floor_or_bins,
  test_pcn_history_anchor_counts_mfg_floor_stock
Date: 2026-06-26
"""
import sys
from pathlib import Path

app_py = Path(__file__).resolve().parents[2] / "app.py"
content = app_py.read_text(encoding="utf-8")

checks = [
    ("PCN History anchor includes mfg_qty (onhand + floor)",
     "COALESCE(onhandqty, 0)\n                        + CASE WHEN mfg_qty ~ '^-?[0-9]+$' THEN mfg_qty::int ELSE 0 END" in content),
    ("reconcile_floor_onhand function exists",
     "def reconcile_floor_onhand(cur):" in content),
    ("_FLOOR_ONHAND_DEDUPE_SQL exists and targets MFG floor rows",
     "_FLOOR_ONHAND_DEDUPE_SQL" in content
     and "LOWER(TRIM(COALESCE(loc_to, ''))) = 'mfg floor'" in content),
    ("guard is wired into the background sync loop",
     "floor_fixed = reconcile_floor_onhand(cur)" in content),
    ("false 'no row has both' assumption removed",
     "0 rows with both onhandqty>0 AND mfg_qty>0" not in content),
]

print("\n" + "=" * 70)
print("BUG #20 FIX VERIFICATION — bin/floor on-hand double-count")
print("=" * 70)
ok = True
for name, passed in checks:
    print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    ok = ok and passed
print("-" * 70)
print(f"[{'SUCCESS' if ok else 'FAIL'}] Bug #20 verification {'complete' if ok else 'failed'}")
sys.exit(0 if ok else 1)
