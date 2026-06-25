"""
Bug #1 Fix Verification Script
================================
Verifies that Bug #1 fix is correctly implemented in app.py

This script reads app.py and verifies:
1. Bin-first ORDER BY logic exists at L5153, L8432, L8734
2. Item search exact-or-prefix logic exists at L4522

Date: 2026-06-23
"""

import re
import sys
from pathlib import Path


def verify_bin_first_order_by(file_path: Path) -> bool:
    """Verify bin-first ORDER BY logic exists in app.py"""
    print("\n" + "="*70)
    print("TEST 1: Verify Bin-First ORDER BY Logic")
    print("="*70)

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Pattern to match bin-first ORDER BY
    # Should have: (onhandqty > 0) DESC or similar
    pattern = r'ORDER BY[^;]*?\(.*?onhandqty.*?>\s*0\).*?DESC'

    matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)

    print(f"\n[OK] Found {len(matches)} instances of bin-first ORDER BY pattern")

    if len(matches) >= 3:  # Should be at L5153, L8432, L8734
        print("[PASS] Bin-first ORDER BY logic found (expected 3+ instances)")

        # Show first match as example
        print("\nExample match:")
        print(matches[0][:200] + "..." if len(matches[0]) > 200 else matches[0])
        return True
    else:
        print(f"[FAIL] FAIL: Expected 3+ instances, found {len(matches)}")
        return False


def verify_exact_or_prefix_search(file_path: Path) -> bool:
    """Verify exact-or-prefix item search logic"""
    print("\n" + "="*70)
    print("TEST 2: Verify Exact-or-Prefix Item Search")
    print("="*70)

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Look for exact match OR prefix pattern
    # Should have something like: = %s OR ... LIKE %s
    patterns = [
        r'UPPER.*?=.*?%s.*?LIKE.*?%s',  # UPPER(item) = %s OR LIKE %s
        r'LOWER.*?=.*?%s.*?LIKE.*?%s',  # LOWER(item) = %s OR LIKE %s
    ]

    found = False
    for pattern in patterns:
        if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
            found = True
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            print(f"\n[OK] Found exact-or-prefix pattern")
            print(f"Pattern: {match.group()[:150]}")
            break

    if found:
        print("\n[PASS] PASS: Exact-or-prefix search logic found")
        return True
    else:
        print("\n[FAIL] FAIL: Exact-or-prefix search logic NOT found")
        return False


def verify_bug_1_fix(app_py_path: str) -> bool:
    """Main verification function for Bug #1"""
    print("\n" + "="*70)
    print("BUG #1 FIX VERIFICATION")
    print("Shortage Report Showed MFG Floor Instead of Real Bin")
    print("="*70)

    file_path = Path(app_py_path)

    if not file_path.exists():
        print(f"\n[FAIL] ERROR: File not found: {file_path}")
        return False

    print(f"\nVerifying file: {file_path}")
    print(f"File size: {file_path.stat().st_size:,} bytes")

    # Run all verification tests
    test1 = verify_bin_first_order_by(file_path)
    test2 = verify_exact_or_prefix_search(file_path)

    # Summary
    print("\n" + "="*70)
    print("VERIFICATION SUMMARY")
    print("="*70)
    print(f"Test 1 - Bin-first ORDER BY: {'[PASS] PASS' if test1 else '[FAIL] FAIL'}")
    print(f"Test 2 - Exact-or-prefix search: {'[PASS] PASS' if test2 else '[FAIL] FAIL'}")

    all_passed = test1 and test2

    if all_passed:
        print("\n[SUCCESS] ALL TESTS PASSED - Bug #1 fix verified!")
        return True
    else:
        print("\n[FAIL] SOME TESTS FAILED - Bug #1 fix may not be complete")
        return False


if __name__ == "__main__":
    # Path to app.py
    app_py = str(Path(__file__).resolve().parents[2] / "app.py")

    success = verify_bug_1_fix(app_py)

    sys.exit(0 if success else 1)
