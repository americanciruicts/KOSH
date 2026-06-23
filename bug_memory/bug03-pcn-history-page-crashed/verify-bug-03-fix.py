"""
Bug #3 Fix Verification Script
================================
Verifies that Bug #3 fix is correctly implemented in app.py

This script reads app.py and verifies:
1. Query has AS total alias at L6556
2. Read by alias anchor_row['total'] at L6561 (not anchor_row[0])

Date: 2026-06-23
"""

import re
import sys
from pathlib import Path


def verify_query_has_alias(file_path: Path) -> bool:
    """Verify query has AS total alias"""
    print("\n" + "="*70)
    print("TEST 1: Verify Query Has AS total Alias")
    print("="*70)

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Look for: COALESCE(SUM(onhandqty), 0) AS total
    pattern = r'COALESCE\s*\(\s*SUM\s*\(\s*onhandqty\s*\)\s*,\s*0\s*\)\s+AS\s+total'
    matches = re.findall(pattern, content, re.IGNORECASE)

    print(f"\n[OK] Found {len(matches)} instances of 'AS total' alias")

    if len(matches) >= 1:
        print("[PASS] Query has AS total alias")
        return True
    else:
        print("[FAIL] Query missing AS total alias")
        return False


def verify_dict_access_not_index(file_path: Path) -> bool:
    """Verify reads by alias, not by index"""
    print("\n" + "="*70)
    print("TEST 2: Verify Dict Access (not Index)")
    print("="*70)

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Look for: anchor_row['total'] (good)
    # Should NOT find: anchor_row[0] (bad)

    good_pattern = r"anchor_row\s*\[\s*['\"]total['\"]\s*\]"
    bad_pattern = r"anchor_row\s*\[\s*0\s*\]"

    good_matches = re.findall(good_pattern, content)
    bad_matches = re.findall(bad_pattern, content)

    print(f"\n[OK] Found {len(good_matches)} instances of anchor_row['total']")
    print(f"[OK] Found {len(bad_matches)} instances of anchor_row[0] (should be 0)")

    if len(good_matches) >= 1 and len(bad_matches) == 0:
        print("[PASS] Using dict access (not index access)")
        return True
    else:
        if len(good_matches) == 0:
            print("[FAIL] Missing dict access anchor_row['total']")
        if len(bad_matches) > 0:
            print("[FAIL] Found buggy index access anchor_row[0]")
        return False


def verify_bug_3_fix(app_py_path: str) -> bool:
    """Main verification function for Bug #3"""
    print("\n" + "="*70)
    print("BUG #3 FIX VERIFICATION")
    print("PCN History Page Crashed for Every Real PCN")
    print("="*70)

    file_path = Path(app_py_path)

    if not file_path.exists():
        print(f"\n[FAIL] ERROR: File not found: {file_path}")
        return False

    print(f"\nVerifying file: {file_path}")
    print(f"File size: {file_path.stat().st_size:,} bytes")

    # Run all verification tests
    test1 = verify_query_has_alias(file_path)
    test2 = verify_dict_access_not_index(file_path)

    # Summary
    print("\n" + "="*70)
    print("VERIFICATION SUMMARY")
    print("="*70)
    print(f"Test 1 - Query has AS total: {'[PASS]' if test1 else '[FAIL]'}")
    print(f"Test 2 - Dict access (not index): {'[PASS]' if test2 else '[FAIL]'}")

    all_passed = test1 and test2

    if all_passed:
        print("\n[SUCCESS] ALL TESTS PASSED - Bug #3 fix verified!")
        return True
    else:
        print("\n[FAIL] SOME TESTS FAILED - Bug #3 fix may not be complete")
        return False


if __name__ == "__main__":
    # Path to app.py
    app_py = r"C:\Users\admin\OneDrive - americancircuits.com\Documents\GitHub\KOSH\app.py"

    success = verify_bug_3_fix(app_py)

    sys.exit(0 if success else 1)
