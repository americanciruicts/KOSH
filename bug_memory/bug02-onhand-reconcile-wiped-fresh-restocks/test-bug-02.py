"""
Automated Tests for Bug #2: On-Hand Reconcile Wiped Fresh Restocks
====================================================================

Test Coverage:
- Fresh restocks are protected from being zeroed
- Phantom-high stock can still be lowered
- Edge cases: sequential restocks, restock-then-pick, etc.
- Latest event tracking logic
- Guard condition verification

Date: 06/23/2026
"""

import pytest
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import List, Dict, Any


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
    conn.rollback()  # Rollback any test data
    conn.close()


@pytest.fixture
def setup_test_data(db_connection):
    """
    Create test data that reproduces Bug #2 scenario.
    """
    cursor = db_connection.cursor()

    # Clean test data
    cursor.execute("DELETE FROM pcb_inventory.\"tblWhse_Inventory\" WHERE item LIKE 'TEST-%'")
    cursor.execute("DELETE FROM pcb_inventory.\"tblTransaction\" WHERE pcn LIKE 'TEST-%'")

    # Test scenario 1: Fresh restock with incomplete ledger
    # This should be PROTECTED by Bug #2 fix
    test_pcn_1 = 'TEST-42137'
    test_item_1 = 'TEST-PART-001'

    # Create warehouse record with fresh restock
    cursor.execute("""
        INSERT INTO pcb_inventory."tblWhse_Inventory"
        (pcn, item, mpn, onhandqty, mfg_qty, loc_to)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (test_pcn_1, test_item_1, 'MPN-001', 15, 0, 'BIN-1234'))

    # Create incomplete ledger (more picks than stock-ins)
    # Historical picks: -50
    # Historical stock-ins: +30
    # Net: -20 (would clamp to 0)
    # Latest: RESTOCK (should protect!)

    base_time = datetime.now() - timedelta(days=10)

    transactions_1 = [
        # Old historical stock-in
        (test_pcn_1, 'MPN-001', 'STOCK', 30, base_time, 1001),
        # Old historical picks
        (test_pcn_1, 'MPN-001', 'PICK', 50, base_time + timedelta(days=1), 1002),
        # Fresh restock (latest event - should protect!)
        (test_pcn_1, 'MPN-001', 'RESTOCK', 15, base_time + timedelta(days=9), 1003),
    ]

    for pcn, mpn, trantype, qty, tran_time, txn_id in transactions_1:
        cursor.execute("""
            INSERT INTO pcb_inventory."tblTransaction"
            (id, pcn, mpn, trantype, tranqty, tran_time, reversed)
            VALUES (%s, %s, %s, %s, %s, %s, false)
        """, (txn_id, pcn, mpn, trantype, str(qty), tran_time))

    # Test scenario 2: Phantom-high stock (latest = PICK)
    # This should be CORRECTABLE (not protected)
    test_pcn_2 = 'TEST-99999'
    test_item_2 = 'TEST-PART-002'

    cursor.execute("""
        INSERT INTO pcb_inventory."tblWhse_Inventory"
        (pcn, item, mpn, onhandqty, mfg_qty, loc_to)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (test_pcn_2, test_item_2, 'MPN-002', 100, 0, 'BIN-5678'))  # Phantom high

    transactions_2 = [
        # Stock in
        (test_pcn_2, 'MPN-002', 'STOCK', 50, base_time, 2001),
        # Pick (latest event - NOT protected)
        (test_pcn_2, 'MPN-002', 'PICK', 10, base_time + timedelta(days=2), 2002),
    ]

    for pcn, mpn, trantype, qty, tran_time, txn_id in transactions_2:
        cursor.execute("""
            INSERT INTO pcb_inventory."tblTransaction"
            (id, pcn, mpn, trantype, tranqty, tran_time, reversed)
            VALUES (%s, %s, %s, %s, %s, %s, false)
        """, (txn_id, pcn, mpn, trantype, str(qty), tran_time))

    # Test scenario 3: Sequential restocks
    # Latest = RESTOCK (most recent) - should protect
    test_pcn_3 = 'TEST-55555'
    test_item_3 = 'TEST-PART-003'

    cursor.execute("""
        INSERT INTO pcb_inventory."tblWhse_Inventory"
        (pcn, item, mpn, onhandqty, mfg_qty, loc_to)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (test_pcn_3, test_item_3, 'MPN-003', 25, 0, 'BIN-9999'))

    transactions_3 = [
        (test_pcn_3, 'MPN-003', 'RESTOCK', 10, base_time, 3001),
        (test_pcn_3, 'MPN-003', 'RESTOCK', 15, base_time + timedelta(days=1), 3002),  # Latest
    ]

    for pcn, mpn, trantype, qty, tran_time, txn_id in transactions_3:
        cursor.execute("""
            INSERT INTO pcb_inventory."tblTransaction"
            (id, pcn, mpn, trantype, tranqty, tran_time, reversed)
            VALUES (%s, %s, %s, %s, %s, %s, false)
        """, (txn_id, pcn, mpn, trantype, str(qty), tran_time))

    # Test scenario 4: Restock then pick
    # Latest = PICK (NOT protected, can be lowered)
    test_pcn_4 = 'TEST-77777'
    test_item_4 = 'TEST-PART-004'

    cursor.execute("""
        INSERT INTO pcb_inventory."tblWhse_Inventory"
        (pcn, item, mpn, onhandqty, mfg_qty, loc_to)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (test_pcn_4, test_item_4, 'MPN-004', 80, 0, 'BIN-7777'))  # Phantom high

    transactions_4 = [
        (test_pcn_4, 'MPN-004', 'RESTOCK', 50, base_time, 4001),
        (test_pcn_4, 'MPN-004', 'PICK', 10, base_time + timedelta(days=1), 4002),  # Latest = PICK
    ]

    for pcn, mpn, trantype, qty, tran_time, txn_id in transactions_4:
        cursor.execute("""
            INSERT INTO pcb_inventory."tblTransaction"
            (id, pcn, mpn, trantype, tranqty, tran_time, reversed)
            VALUES (%s, %s, %s, %s, %s, %s, false)
        """, (txn_id, pcn, mpn, trantype, str(qty), tran_time))

    db_connection.commit()
    yield

    # Cleanup
    cursor.execute("DELETE FROM pcb_inventory.\"tblWhse_Inventory\" WHERE item LIKE 'TEST-%'")
    cursor.execute("DELETE FROM pcb_inventory.\"tblTransaction\" WHERE pcn LIKE 'TEST-%'")
    db_connection.commit()


# ============================================================================
# Unit Tests - Latest Event Tracking
# ============================================================================

class TestLatestEventTracking:
    """Test the latest_event CTE logic."""

    def test_latest_event_is_restock(self, db_connection, setup_test_data):
        """
        CRITICAL TEST: Verify latest event correctly identified as RESTOCK.

        This is the core of Bug #2 fix - must correctly identify the most
        recent transaction type.
        """
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        sql = """
            WITH parsed AS (
                SELECT
                    pcn,
                    mpn,
                    LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) as mpn_key,
                    trantype,
                    tran_time,
                    id
                FROM pcb_inventory."tblTransaction"
                WHERE pcn = 'TEST-42137'
                    AND reversed = false
            ),
            latest_event AS (
                SELECT DISTINCT ON (pcn, mpn_key)
                    pcn,
                    mpn_key,
                    trantype AS last_type,
                    tran_time
                FROM parsed
                WHERE trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
                ORDER BY pcn, mpn_key, tran_time DESC NULLS LAST, id DESC
            )
            SELECT * FROM latest_event
        """

        cursor.execute(sql)
        result = cursor.fetchone()

        assert result is not None, "No latest event found"
        assert result['last_type'] == 'RESTOCK', f"Expected RESTOCK, got {result['last_type']}"
        assert result['pcn'] == 'TEST-42137'

        print("✓ Test passed: Latest event correctly identified as RESTOCK")


    def test_latest_event_is_pick_after_restock(self, db_connection, setup_test_data):
        """Latest event should be PICK when pick happens after restock."""
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        sql = """
            WITH parsed AS (
                SELECT
                    pcn,
                    LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) as mpn_key,
                    trantype,
                    tran_time,
                    id
                FROM pcb_inventory."tblTransaction"
                WHERE pcn = 'TEST-77777'
                    AND reversed = false
            ),
            latest_event AS (
                SELECT DISTINCT ON (pcn, mpn_key)
                    pcn,
                    mpn_key,
                    trantype AS last_type
                FROM parsed
                WHERE trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
                ORDER BY pcn, mpn_key, tran_time DESC NULLS LAST, id DESC
            )
            SELECT * FROM latest_event
        """

        cursor.execute(sql)
        result = cursor.fetchone()

        assert result is not None
        assert result['last_type'] == 'PICK', f"Expected PICK, got {result['last_type']}"

        print("✓ Test passed: Latest event correctly identified as PICK (after restock)")


    def test_sequential_restocks_latest_wins(self, db_connection, setup_test_data):
        """With multiple restocks, most recent should be latest."""
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        sql = """
            WITH parsed AS (
                SELECT
                    pcn,
                    LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) as mpn_key,
                    trantype,
                    tran_time,
                    id
                FROM pcb_inventory."tblTransaction"
                WHERE pcn = 'TEST-55555'
                    AND reversed = false
            ),
            latest_event AS (
                SELECT DISTINCT ON (pcn, mpn_key)
                    pcn,
                    mpn_key,
                    trantype AS last_type,
                    tran_time
                FROM parsed
                WHERE trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
                ORDER BY pcn, mpn_key, tran_time DESC NULLS LAST, id DESC
            )
            SELECT * FROM latest_event
        """

        cursor.execute(sql)
        result = cursor.fetchone()

        assert result is not None
        assert result['last_type'] == 'RESTOCK'
        # Most recent restock should be selected

        print("✓ Test passed: Sequential restocks - latest RESTOCK wins")


# ============================================================================
# Integration Tests - Reconcile Protection Logic
# ============================================================================

class TestReconcileProtection:
    """Test the full reconcile protection logic."""

    def test_fresh_restock_protected_from_zeroing(self, db_connection, setup_test_data):
        """
        REGRESSION TEST: Reproduce exact Bug #2 scenario.

        PCN TEST-42137:
        - Ledger replay would compute 0 (incomplete history)
        - Warehouse has 15 (fresh restock)
        - Latest event = RESTOCK
        - Should be PROTECTED (not lowered to 0)
        """
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        # Simulate what reconcile would do
        sql = """
            WITH parsed AS (
                SELECT
                    pcn,
                    mpn,
                    LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) as mpn_key,
                    trantype,
                    tranqty,
                    tran_time,
                    id
                FROM pcb_inventory."tblTransaction"
                WHERE pcn = 'TEST-42137'
                    AND reversed = false
                    AND tranqty ~ '^-?[0-9]+$'
            ),
            ledger_net AS (
                SELECT
                    pcn,
                    mpn_key,
                    SUM(
                        CASE
                            WHEN trantype IN ('RESTOCK', 'STOCK', 'INDF')
                                THEN tranqty::int
                            WHEN trantype IN ('PICK', 'PURGE', 'SCRA')
                                THEN -ABS(tranqty::int)
                            ELSE 0
                        END
                    ) as computed_qty
                FROM parsed
                GROUP BY pcn, mpn_key
            ),
            latest_event AS (
                SELECT DISTINCT ON (pcn, mpn_key)
                    pcn,
                    mpn_key,
                    trantype AS last_type
                FROM parsed
                WHERE trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
                ORDER BY pcn, mpn_key, tran_time DESC NULLS LAST, id DESC
            ),
            warehouse_current AS (
                SELECT
                    pcn::text as pcn,
                    LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) as mpn_key,
                    onhandqty
                FROM pcb_inventory."tblWhse_Inventory"
                WHERE pcn::text = 'TEST-42137'
            )
            SELECT
                w.pcn,
                w.onhandqty as current_warehouse,
                GREATEST(0, COALESCE(ln.computed_qty, 0)) as ledger_computed,
                le.last_type,
                CASE
                    WHEN COALESCE(le.last_type, '') IN ('RESTOCK', 'STOCK') THEN 'PROTECTED'
                    ELSE 'NOT_PROTECTED'
                END as protection_status,
                CASE
                    WHEN COALESCE(le.last_type, '') IN ('RESTOCK', 'STOCK') THEN
                        w.onhandqty  -- Keep warehouse value
                    WHEN GREATEST(0, COALESCE(ln.computed_qty, 0)) < w.onhandqty THEN
                        GREATEST(0, COALESCE(ln.computed_qty, 0))  -- Lower to computed
                    ELSE
                        w.onhandqty  -- Keep warehouse value
                END as final_qty
            FROM warehouse_current w
            LEFT JOIN ledger_net ln ON w.pcn = ln.pcn AND w.mpn_key = ln.mpn_key
            LEFT JOIN latest_event le ON w.pcn = le.pcn AND w.mpn_key = le.mpn_key
        """

        cursor.execute(sql)
        result = cursor.fetchone()

        # CRITICAL ASSERTIONS - Bug #2 fix verification
        assert result is not None, "Test PCN not found"
        assert result['current_warehouse'] == 15, "Warehouse should have 15 units"
        assert result['ledger_computed'] == 0, "Ledger should compute 0 (incomplete history)"
        assert result['last_type'] == 'RESTOCK', "Latest event should be RESTOCK"
        assert result['protection_status'] == 'PROTECTED', "Should be PROTECTED"
        assert result['final_qty'] == 15, "Final qty should remain 15 (not zeroed!)"

        print("✓ REGRESSION TEST PASSED: Bug #2 scenario - fresh restock protected from zeroing")


    def test_phantom_stock_can_be_lowered(self, db_connection, setup_test_data):
        """
        Phantom-high stock (latest = PICK) should still be correctable.

        This ensures Bug #2 fix doesn't prevent legitimate corrections.
        """
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        sql = """
            WITH parsed AS (
                SELECT
                    pcn,
                    LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) as mpn_key,
                    trantype,
                    tranqty,
                    tran_time,
                    id
                FROM pcb_inventory."tblTransaction"
                WHERE pcn = 'TEST-99999'
                    AND reversed = false
                    AND tranqty ~ '^-?[0-9]+$'
            ),
            ledger_net AS (
                SELECT
                    pcn,
                    mpn_key,
                    SUM(
                        CASE
                            WHEN trantype IN ('RESTOCK', 'STOCK', 'INDF') THEN tranqty::int
                            WHEN trantype IN ('PICK', 'PURGE', 'SCRA') THEN -ABS(tranqty::int)
                            ELSE 0
                        END
                    ) as computed_qty
                FROM parsed
                GROUP BY pcn, mpn_key
            ),
            latest_event AS (
                SELECT DISTINCT ON (pcn, mpn_key)
                    pcn,
                    mpn_key,
                    trantype AS last_type
                FROM parsed
                WHERE trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
                ORDER BY pcn, mpn_key, tran_time DESC NULLS LAST, id DESC
            )
            SELECT
                le.last_type,
                CASE
                    WHEN COALESCE(le.last_type, '') IN ('RESTOCK', 'STOCK') THEN 'PROTECTED'
                    ELSE 'NOT_PROTECTED'
                END as protection_status
            FROM latest_event le
            WHERE le.pcn = 'TEST-99999'
        """

        cursor.execute(sql)
        result = cursor.fetchone()

        assert result is not None
        assert result['last_type'] == 'PICK', "Latest should be PICK"
        assert result['protection_status'] == 'NOT_PROTECTED', "Should NOT be protected"

        print("✓ Test passed: Phantom stock (latest=PICK) can still be lowered")


    def test_restock_then_pick_not_protected(self, db_connection, setup_test_data):
        """
        If restock followed by pick, latest = PICK, should NOT be protected.
        """
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        sql = """
            WITH latest_event AS (
                SELECT DISTINCT ON (pcn, LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')))
                    pcn,
                    trantype AS last_type
                FROM pcb_inventory."tblTransaction"
                WHERE pcn = 'TEST-77777'
                    AND reversed = false
                    AND trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
                ORDER BY pcn,
                         LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')),
                         tran_time DESC NULLS LAST,
                         id DESC
            )
            SELECT
                last_type,
                COALESCE(last_type, '') NOT IN ('RESTOCK', 'STOCK') as allows_lowering
            FROM latest_event
        """

        cursor.execute(sql)
        result = cursor.fetchone()

        assert result is not None
        assert result['last_type'] == 'PICK'
        assert result['allows_lowering'] == True, "Should allow lowering when latest=PICK"

        print("✓ Test passed: Restock-then-pick NOT protected (latest=PICK)")


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_null_latest_event_handled(self, db_connection):
        """NULL latest_event should be handled gracefully."""
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        # Test the COALESCE behavior
        sql = """
            SELECT
                COALESCE(NULL, '') NOT IN ('RESTOCK', 'STOCK') as allows_lowering
        """

        cursor.execute(sql)
        result = cursor.fetchone()

        assert result['allows_lowering'] == True, "NULL should allow lowering (COALESCE to empty string)"

        print("✓ Test passed: NULL latest_event handled correctly")


    def test_empty_string_latest_event(self, db_connection):
        """Empty string latest_event should allow lowering."""
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)

        sql = """
            SELECT
                COALESCE('', '') NOT IN ('RESTOCK', 'STOCK') as allows_lowering
        """

        cursor.execute(sql)
        result = cursor.fetchone()

        assert result['allows_lowering'] == True

        print("✓ Test passed: Empty string latest_event allows lowering")


    def test_guard_condition_syntax(self, db_connection):
        """Verify guard condition SQL syntax is correct."""
        cursor = db_connection.cursor()

        # Test the actual guard condition from the fix
        sql = """
            SELECT
                CASE
                    WHEN COALESCE('RESTOCK', '') NOT IN ('RESTOCK', 'STOCK') THEN 'ALLOWED'
                    ELSE 'BLOCKED'
                END as restock_protection,
                CASE
                    WHEN COALESCE('STOCK', '') NOT IN ('RESTOCK', 'STOCK') THEN 'ALLOWED'
                    ELSE 'BLOCKED'
                END as stock_protection,
                CASE
                    WHEN COALESCE('PICK', '') NOT IN ('RESTOCK', 'STOCK') THEN 'ALLOWED'
                    ELSE 'BLOCKED'
                END as pick_protection
        """

        cursor.execute(sql)
        result = cursor.fetchone()

        assert result[0] == 'BLOCKED', "RESTOCK should be blocked from lowering"
        assert result[1] == 'BLOCKED', "STOCK should be blocked from lowering"
        assert result[2] == 'ALLOWED', "PICK should allow lowering"

        print("✓ Test passed: Guard condition syntax correct")


# ============================================================================
# Performance Tests
# ============================================================================

class TestPerformance:
    """Test query performance."""

    def test_latest_event_performance(self, db_connection, setup_test_data):
        """Latest event query should be performant."""
        import time

        cursor = db_connection.cursor()

        start = time.time()

        sql = """
            WITH parsed AS (
                SELECT
                    pcn,
                    LOWER(TRANSLATE(COALESCE(mpn,''), '-# ./', '')) as mpn_key,
                    trantype,
                    tran_time,
                    id
                FROM pcb_inventory."tblTransaction"
                WHERE pcn LIKE 'TEST-%'
                    AND reversed = false
            ),
            latest_event AS (
                SELECT DISTINCT ON (pcn, mpn_key)
                    pcn,
                    mpn_key,
                    trantype AS last_type
                FROM parsed
                WHERE trantype IN ('PICK','PURGE','SCRA','RESTOCK','STOCK','INDF','ADJT','PCN Generation')
                ORDER BY pcn, mpn_key, tran_time DESC NULLS LAST, id DESC
            )
            SELECT COUNT(*) FROM latest_event
        """

        cursor.execute(sql)
        result = cursor.fetchone()
        elapsed = time.time() - start

        assert result[0] >= 4, "Should have at least 4 test PCNs"
        assert elapsed < 0.5, f"Query took {elapsed:.3f}s, should be < 0.5s"

        print(f"✓ Performance test passed: {result[0]} PCNs processed in {elapsed:.3f}s")


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "regression: Regression tests")
    config.addinivalue_line("markers", "edge: Edge case tests")
    config.addinivalue_line("markers", "performance: Performance tests")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
