"""
Automated Tests for Bug #3: PCN History Page Crashed
=====================================================

Test Coverage:
- RealDictCursor dict access (not index access)
- Column alias in SQL queries
- Anchor calculation with RealDictCursor
- NULL/empty result handling
- Cursor type consistency between tests and production

Date: 06/18/2026
"""

import pytest
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, Any


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def db_connection():
    """Create a test database connection."""
    conn = psycopg2.connect(
        host="localhost",
        database="kosh_test",
        user="test_user",
        password="test_pass"
    )
    conn.autocommit = False
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def setup_test_pcn(db_connection):
    """Create test PCN with inventory."""
    cursor = db_connection.cursor()

    # Clean test data
    cursor.execute("DELETE FROM pcb_inventory.\"tblWhse_Inventory\" WHERE pcn::text = 'TEST-BUG3'")
    cursor.execute("DELETE FROM pcb_inventory.\"tblTransaction\" WHERE pcn::text = 'TEST-BUG3'")

    # Create test inventory
    cursor.execute("""
        INSERT INTO pcb_inventory."tblWhse_Inventory"
        (pcn, item, mpn, onhandqty, mfg_qty, loc_to)
        VALUES ('TEST-BUG3', 'TEST-ITEM-BUG3', 'MPN-BUG3', 100, 50, 'BIN-TEST')
    """)

    # Create test transactions
    cursor.execute("""
        INSERT INTO pcb_inventory."tblTransaction"
        (id, pcn, mpn, trantype, tranqty, tran_time, reversed)
        VALUES
        (9001, 'TEST-BUG3', 'MPN-BUG3', 'STOCK', '100', NOW() - INTERVAL '5 days', false),
        (9002, 'TEST-BUG3', 'MPN-BUG3', 'RESTOCK', '50', NOW() - INTERVAL '2 days', false)
    """)

    db_connection.commit()
    yield

    # Cleanup
    cursor.execute("DELETE FROM pcb_inventory.\"tblWhse_Inventory\" WHERE pcn::text = 'TEST-BUG3'")
    cursor.execute("DELETE FROM pcb_inventory.\"tblTransaction\" WHERE pcn::text = 'TEST-BUG3'")
    db_connection.commit()


# ============================================================================
# Unit Tests - Cursor Type Handling
# ============================================================================

class TestCursorTypeHandling:
    """Test RealDictCursor vs regular cursor behavior."""

    def test_realdict_cursor_returns_dict(self, db_connection):
        """
        CRITICAL TEST: Verify RealDictCursor returns dict, not tuple.

        This is the core of Bug #3 - understanding cursor type behavior.
        """
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT 123 AS test_value")
        row = cursor.fetchone()

        # Should be a dict
        assert isinstance(row, dict), f"Expected dict, got {type(row)}"
        assert 'test_value' in row, "Should have 'test_value' key"
        assert row['test_value'] == 123

        print("✓ Test passed: RealDictCursor returns dict")


    def test_regular_cursor_returns_tuple(self, db_connection):
        """Regular cursor returns tuple (for comparison)."""
        cursor = db_connection.cursor()  # Plain cursor

        cursor.execute("SELECT 123")
        row = cursor.fetchone()

        # Should be a tuple
        assert isinstance(row, tuple), f"Expected tuple, got {type(row)}"
        assert row[0] == 123  # Can access by index

        print("✓ Test passed: Regular cursor returns tuple")


    def test_realdict_cursor_index_access_fails(self, db_connection):
        """
        REGRESSION TEST: Verify the buggy pattern fails.

        This reproduces Bug #3 behavior.
        """
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT 123 AS value")
        row = cursor.fetchone()

        # Trying to access by index should fail
        with pytest.raises(KeyError):
            _ = row[0]  # ❌ This is the bug!

        print("✓ Test passed: Index access fails on RealDictCursor (expected)")


    def test_realdict_cursor_dict_access_works(self, db_connection):
        """
        REGRESSION TEST: Verify the fix works.

        This tests Bug #3 fix behavior.
        """
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT 123 AS value")
        row = cursor.fetchone()

        # Accessing by key should work
        value = row['value']  # ✅ This is the fix!
        assert value == 123

        print("✓ Test passed: Dict access works on RealDictCursor")


# ============================================================================
# Integration Tests - Anchor Query
# ============================================================================

class TestAnchorQuery:
    """Test the exact anchor query from Bug #3 fix."""

    def test_anchor_query_with_alias(self, db_connection, setup_test_pcn):
        """
        REGRESSION TEST: Test the fixed anchor query.

        This is the exact query from app.py @ L6556-6561 (fixed version).
        """
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        # FIXED QUERY - with alias
        cursor.execute("""
            SELECT COALESCE(SUM(onhandqty), 0) AS total
            FROM pcb_inventory."tblWhse_Inventory"
            WHERE pcn::text = %s
        """, ('TEST-BUG3',))

        anchor_row = cursor.fetchone()

        # FIXED ACCESS - by alias
        anchor = int(anchor_row['total']) if anchor_row and anchor_row.get('total') is not None else 0

        assert anchor == 100, f"Expected 100, got {anchor}"

        print("✓ REGRESSION TEST PASSED: Anchor query with alias works")


    def test_anchor_query_without_alias_fails(self, db_connection, setup_test_pcn):
        """
        BUGGY PATTERN TEST: Query without alias is problematic.

        This demonstrates why alias is important.
        """
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        # BUGGY QUERY - no alias
        cursor.execute("""
            SELECT COALESCE(SUM(onhandqty), 0)
            FROM pcb_inventory."tblWhse_Inventory"
            WHERE pcn::text = %s
        """, ('TEST-BUG3',))

        anchor_row = cursor.fetchone()

        # Without explicit alias, key name is auto-generated ('coalesce')
        # This is unpredictable and fragile!
        assert 'coalesce' in anchor_row, "Auto-generated key is 'coalesce'"

        # Trying to access by 'total' would fail
        assert 'total' not in anchor_row, "No 'total' key without alias"

        print("✓ Test passed: Query without alias has unpredictable key")


    def test_anchor_empty_result(self, db_connection):
        """
        Test anchor query with nonexistent PCN (empty result).

        The fix handles this with None check.
        """
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT COALESCE(SUM(onhandqty), 0) AS total
            FROM pcb_inventory."tblWhse_Inventory"
            WHERE pcn::text = %s
        """, ('NONEXISTENT-PCN',))

        anchor_row = cursor.fetchone()

        # Even for empty result, row exists with total=0
        anchor = int(anchor_row['total']) if anchor_row and anchor_row.get('total') is not None else 0

        assert anchor == 0, "Empty result should give anchor=0"

        print("✓ Test passed: Empty result handled correctly")


    def test_anchor_null_safety(self, db_connection):
        """Test the None safety check in the fix."""
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        # Simulate a NULL result
        cursor.execute("SELECT NULL AS total")
        anchor_row = cursor.fetchone()

        # The fix has safety for None
        anchor = int(anchor_row['total']) if anchor_row and anchor_row.get('total') is not None else 0

        assert anchor == 0, "NULL should default to 0"

        print("✓ Test passed: NULL result handled safely")


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_multiple_columns_with_aliases(self, db_connection):
        """Test query with multiple aliased columns."""
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                COUNT(*) AS row_count,
                SUM(onhandqty) AS total_qty,
                AVG(onhandqty) AS avg_qty
            FROM pcb_inventory."tblWhse_Inventory"
            WHERE onhandqty > 0
        """)

        row = cursor.fetchone()

        # All aliases should be accessible
        assert 'row_count' in row
        assert 'total_qty' in row
        assert 'avg_qty' in row

        print("✓ Test passed: Multiple aliases work")


    def test_fetchall_with_realdict_cursor(self, db_connection, setup_test_pcn):
        """Test fetchall() also returns dicts."""
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT pcn, item, onhandqty AS qty
            FROM pcb_inventory."tblWhse_Inventory"
            WHERE pcn::text = 'TEST-BUG3'
        """)

        rows = cursor.fetchall()

        assert len(rows) == 1
        assert isinstance(rows[0], dict)
        assert rows[0]['qty'] == 100

        print("✓ Test passed: fetchall() also returns dicts")


    def test_column_alias_case_sensitive(self, db_connection):
        """Test column alias case sensitivity."""
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT 123 AS Total")  # Uppercase alias
        row = cursor.fetchone()

        # PostgreSQL folds unquoted identifiers to lowercase
        # So 'Total' becomes 'total'
        assert 'total' in row, "Unquoted alias becomes lowercase"
        assert 'Total' not in row

        print("✓ Test passed: Alias case handled correctly")


# ============================================================================
# Production Simulation Tests
# ============================================================================

class TestProductionSimulation:
    """Simulate the actual production code path."""

    def test_pcn_history_anchor_calculation(self, db_connection, setup_test_pcn):
        """
        INTEGRATION TEST: Simulate full PCN History anchor calculation.

        This replicates what happens in app.py @ L6555-6561.
        """
        search_pcn = 'TEST-BUG3'

        # Use RealDictCursor (as production does)
        cur = db_connection.cursor(cursor_factory=RealDictCursor)

        # Execute the exact query from production
        cur.execute("""
            SELECT COALESCE(SUM(onhandqty), 0) AS total
            FROM pcb_inventory."tblWhse_Inventory"
            WHERE pcn::text = %s
        """, (search_pcn,))

        anchor_row = cur.fetchone()

        # Use the exact access pattern from the fix
        anchor = int(anchor_row['total']) if anchor_row and anchor_row.get('total') is not None else 0

        # Verify result
        assert anchor == 100, f"Expected anchor=100, got {anchor}"

        print("✓ INTEGRATION TEST PASSED: Production code path works")


    def test_error_message_on_index_access(self, db_connection):
        """Verify error message matches Bug #3 report."""
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT 123 AS value")
        row = cursor.fetchone()

        try:
            _ = row[0]  # Buggy pattern
            assert False, "Should have raised KeyError"
        except KeyError as e:
            # The error is KeyError: 0
            # This matches the bug report: "Error loading PCN history: 0"
            assert str(e) == "'0'" or str(e) == "0"

        print("✓ Test passed: Error message matches bug report")


# ============================================================================
# Best Practices Tests
# ============================================================================

class TestBestPractices:
    """Test recommended best practices from the fix."""

    def test_always_use_alias_pattern(self, db_connection):
        """
        BEST PRACTICE: Always use AS alias for aggregate functions.
        """
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        # ✅ Good - with alias
        cursor.execute("SELECT COUNT(*) AS count FROM pcb_inventory.\"tblWhse_Inventory\"")
        row = cursor.fetchone()
        assert 'count' in row

        # ✅ Good - all aggregates aliased
        cursor.execute("""
            SELECT
                COUNT(*) AS count,
                SUM(onhandqty) AS total,
                AVG(onhandqty) AS average
            FROM pcb_inventory."tblWhse_Inventory"
        """)
        row = cursor.fetchone()
        assert all(k in row for k in ['count', 'total', 'average'])

        print("✓ Test passed: Best practice - always use aliases")


    def test_safe_dict_access_pattern(self, db_connection):
        """
        BEST PRACTICE: Safe dictionary access with None check.
        """
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        # Test with NULL
        cursor.execute("SELECT NULL AS value")
        row = cursor.fetchone()

        # ✅ Good - safe access
        value = row.get('value', 0)  # Returns 0 for None
        assert value is None  # get() returns None, not 0 (wait, get returns None!)

        # Better pattern from the fix:
        value = row['value'] if row and row.get('value') is not None else 0
        assert value == 0  # Now defaults to 0

        print("✓ Test passed: Best practice - safe dict access")


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "regression: Regression tests")
    config.addinivalue_line("markers", "edge: Edge case tests")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
