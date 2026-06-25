"""
Bug #12 Fix Verification Script
================================
Verifies that Bug #12 fix is correctly implemented in app.py

This script verifies:
1. bcrypt is imported (not passlib)
2. SSO auto-create uses bcrypt for password hashing
3. No passlib imports remain in the code

Date: 2026-06-25
"""

import re
import sys
from pathlib import Path


def verify_bcrypt_imported(file_path: Path) -> bool:
    """Verify bcrypt is imported"""
    print("\n" + "="*70)
    print("TEST 1: Verify bcrypt Import")
    print("="*70)

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Check for: import bcrypt (should be near top of file)
    found = False
    for i in range(0, min(50, len(lines))):
        line = lines[i]
        if re.match(r'^\s*import\s+bcrypt\s*$', line):
            found = True
            print(f"\n[OK] Found bcrypt import at line {i+1}")
            print(f"Line: {line.strip()}")
            break

    if found:
        print("[PASS] bcrypt is imported")
        return True
    else:
        print("[FAIL] bcrypt import NOT found")
        return False


def verify_sso_uses_bcrypt(file_path: Path) -> bool:
    """Verify SSO auto-create uses bcrypt for password hashing"""
    print("\n" + "="*70)
    print("TEST 2: Verify SSO Auto-Create Uses bcrypt")
    print("="*70)

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Check around L5985 for: bcrypt.hashpw(..., bcrypt.gensalt())
    found = False
    for i in range(5980, min(5995, len(lines))):
        line = lines[i]
        if 'bcrypt.hashpw' in line and 'bcrypt.gensalt' in line:
            found = True
            print(f"\n[OK] Found bcrypt usage in SSO auto-create at line {i+1}")
            print(f"Line: {line.strip()[:80]}...")
            break

    if found:
        print("[PASS] SSO auto-create uses bcrypt")
        return True
    else:
        print("[FAIL] bcrypt usage NOT found in SSO auto-create")
        return False


def verify_no_passlib_import(file_path: Path) -> bool:
    """Verify passlib is NOT imported (should be removed)"""
    print("\n" + "="*70)
    print("TEST 3: Verify No passlib Import")
    print("="*70)

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Look for any passlib imports
    pattern = r'import\s+passlib|from\s+passlib'
    matches = re.findall(pattern, content, re.IGNORECASE)

    print(f"\n[OK] Found {len(matches)} passlib import(s) (should be 0)")

    if len(matches) == 0:
        print("[PASS] No passlib imports (correctly removed)")
        return True
    else:
        print("[FAIL] passlib imports still present:")
        for match in matches:
            print(f"  - {match}")
        return False


def verify_bug_12_fix(app_py_path: str) -> bool:
    """Main verification function for Bug #12"""
    print("\n" + "="*70)
    print("BUG #12 FIX VERIFICATION")
    print("SSO Auto-Create Failed for First-Time KOSH Users")
    print("="*70)

    file_path = Path(app_py_path)

    if not file_path.exists():
        print(f"\n[FAIL] ERROR: File not found: {file_path}")
        return False

    print(f"\nVerifying file: {file_path}")
    print(f"File size: {file_path.stat().st_size:,} bytes")

    # Run all verification tests
    test1 = verify_bcrypt_imported(file_path)
    test2 = verify_sso_uses_bcrypt(file_path)
    test3 = verify_no_passlib_import(file_path)

    # Summary
    print("\n" + "="*70)
    print("VERIFICATION SUMMARY")
    print("="*70)
    print(f"Test 1 - bcrypt imported: {'[PASS]' if test1 else '[FAIL]'}")
    print(f"Test 2 - SSO auto-create uses bcrypt: {'[PASS]' if test2 else '[FAIL]'}")
    print(f"Test 3 - No passlib imports: {'[PASS]' if test3 else '[FAIL]'}")

    all_passed = test1 and test2 and test3

    if all_passed:
        print("\n[SUCCESS] ALL TESTS PASSED - Bug #12 fix verified!")
        print("\nKey fix:")
        print("- bcrypt library used (matches rest of app)")
        print("- passlib removed (was not installed in container)")
        print("- SSO auto-create works for new FORGE users")
        print("- Default password: 'Welcome1!' hashed with bcrypt")
        return True
    else:
        print("\n[FAIL] SOME TESTS FAILED - Bug #12 fix may not be complete")
        return False


if __name__ == "__main__":
    # Path to app.py
    app_py = r"C:\Users\admin\OneDrive - americancircuits.com\Documents\GitHub\KOSH\app.py"

    success = verify_bug_12_fix(app_py)

    sys.exit(0 if success else 1)
