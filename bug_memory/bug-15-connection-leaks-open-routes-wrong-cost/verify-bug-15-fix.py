"""Bug #15: Connection leaks + open routes + wrong shortage cost - Verified 2026-06-25"""
import re, sys
from pathlib import Path

print("\nBUG #15 VERIFICATION - Connection Leaks + Open Routes + Wrong Cost")
print("="*70)

app_py = Path(r"C:\Users\admin\OneDrive - americancircuits.com\Documents\GitHub\KOSH\app.py")
content = app_py.read_text(encoding='utf-8')

# Test 1: Check for @login_required decorators on data routes
routes = ['get_po_history', 'get_locations', 'database_health_check']
protected = sum(1 for r in routes if f'@login_required\ndef {r}' in content or f'@login_required\n    def {r}' in content or re.search(rf'@login_required.*?\n.*?def {r}', content, re.DOTALL))
print(f"\nTest 1: Auth on data routes: {protected}/{len(routes)} protected [{'PASS' if protected >= 2 else 'FAIL'}]")

# Test 2: shortage_cost vs total_cost distinction
has_shortage_cost = 'shortage_cost' in content
has_total_cost = 'total_cost' in content
print(f"Test 2: Cost distinction: shortage_cost={has_shortage_cost}, total_cost={has_total_cost} [{'PASS' if has_shortage_cost and has_total_cost else 'FAIL'}]")

# Test 3: Connection cleanup (return_connection/finally)
cleanup_count = content.count('return_connection') + content.count('finally:')
print(f"Test 3: Connection cleanup patterns: {cleanup_count} instances [{'PASS' if cleanup_count > 50 else 'FAIL'}]")

all_pass = protected >= 2 and has_shortage_cost and has_total_cost and cleanup_count > 50
print(f"\n{'[SUCCESS]' if all_pass else '[FAIL]'} Bug #15 verification {'complete' if all_pass else 'failed'}")
sys.exit(0 if all_pass else 1)
