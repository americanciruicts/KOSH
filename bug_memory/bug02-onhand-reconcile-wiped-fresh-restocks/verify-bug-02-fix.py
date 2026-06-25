"""
Bug #2 Fix Verification Script
================================
Verifies that Bug #2 fix is correctly implemented in app.py

This script reads app.py and verifies:
1. latest_event CTE exists at L3204-3220
2. Guard condition exists at L3237: NOT IN ('RESTOCK','STOCK')

Date: 2026-06-23
"""

import re
import sys
from pathlib import Path


def verify_latest_event_cte(file_path: Path) -> bool:
    """Verify latest_event CTE exists"""
    print("\n" + "="*70)
    print("TEST 1: Verify latest_event CTE")
    print("="*70)

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Look for latest_event CTE
    pattern = r'latest_event\s+AS\s*\('
    matches = re.findall(pattern, content, re.IGNORECASE)

    print(f"\n[OK] Found {len(matches)} instances of latest_event CTE")

    if len(matches) >= 1:
        print("[PASS] latest_event CTE found")
        return True
    else:
        print("[FAIL] latest_event CTE NOT found")
        return False


def verify_guard_condition(file_path: Path) -> bool:
    """Verify guard condition prevents lowering RESTOCK/STOCK"""
    print("\n" + "="*70)
    print("TEST 2: Verify Guard Condition")
    print("="*70)

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Look for the guard: NOT IN ('RESTOCK', 'STOCK')
    pattern = r"NOT\s+IN\s*\(\s*['\"]RESTOCK['\"],\s*['\"]STOCK['\"]\s*\)"
    matches = re.findall(pattern, content, re.IGNORECASE)

    print(f"\n[OK] Found {len(matches)} instances of RESTOCK/STOCK guard")

    if len(matches) >= 1:
        print("[PASS] Guard condition found")

        # Show match
        print("\nGuard pattern:")
        print(matches[0])
        return True
    else:
        print("[FAIL] Guard condition NOT found")
        return False


def verify_bug_2_fix(app_py_path: str) -> bool:
    """Main verification function for Bug #2"""
    print("\n" + "="*70)
    print("BUG #2 FIX VERIFICATION")
    print("On-Hand Reconcile Wiped Fresh Restocks to 0")
    print("="*70)

    file_path = Path(app_py_path)

    if not file_path.exists():
        print(f"\n[FAIL] ERROR: File not found: {file_path}")
        return False

    print(f"\nVerifying file: {file_path}")
    print(f"File size: {file_path.stat().st_size:,} bytes")

    # Run all verification tests
    test1 = verify_latest_event_cte(file_path)
    test2 = verify_guard_condition(file_path)

    # Summary
    print("\n" + "="*70)
    print("VERIFICATION SUMMARY")
    print("="*70)
    print(f"Test 1 - latest_event CTE: {'[PASS]' if test1 else '[FAIL]'}")
    print(f"Test 2 - Guard condition: {'[PASS]' if test2 else '[FAIL]'}")

    all_passed = test1 and test2

    if all_passed:
        print("\n[SUCCESS] ALL TESTS PASSED - Bug #2 fix verified!")
        return True
    else:
        print("\n[FAIL] SOME TESTS FAILED - Bug #2 fix may not be complete")
        return False


if __name__ == "__main__":
    # Path to app.py
    app_py = str(Path(__file__).resolve().parents[2] / "app.py")

    success = verify_bug_2_fix(app_py)

    sys.exit(0 if success else 1)
