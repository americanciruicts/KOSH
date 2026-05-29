# CRITICAL FIXES AND REQUIREMENTS - DO NOT REVERT

This document contains all critical fixes and requirements that must be maintained in the codebase. These were identified and fixed through extensive debugging. **DO NOT revert these changes under any circumstances.**

---

## 1. Location From Field - ALWAYS USE DASH

**REQUIREMENT**: When generating new PCNs, the `loc_from` field must be **"-"** (dash), NOT "Stock".

**Affected Tables**:
- `tblWhse_Inventory` (warehouse inventory)
- `tblTransaction` (transaction/PCN history)
- `po_history` (PO history)

**Code Locations in app.py**:
```python
# Line ~2609 - tblWhse_Inventory INSERT
cursor.execute("""
    INSERT INTO pcb_inventory."tblWhse_Inventory"
    (item, pcn, mpn, dc, onhandqty, loc_from, loc_to, msd, po)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
""", (
    data.get('item'),
    pcn_number,
    data.get('mpn') or '',
    data.get('date_code'),
    data.get('quantity', 0),
    '-',  # ← MUST BE DASH, NOT "Stock"
    data.get('location', 'Receiving Area'),
    data.get('msd'),
    data.get('po_number')
))

# Line ~2628 - tblTransaction INSERT
cursor.execute("""
    INSERT INTO pcb_inventory."tblTransaction"
    (trantype, item, pcn, mpn, dc, tranqty, tran_time, loc_from, loc_to, wo, po, userid)
    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s)
""", (
    'GEN',
    data.get('item'),
    pcn_number,
    data.get('mpn'),
    data.get('date_code'),
    data.get('quantity', 0),
    '-',  # ← MUST BE DASH, NOT "Stock"
    data.get('location', 'Receiving Area'),
    data.get('work_order'),
    data.get('po_number'),
    session.get('username', 'system')
))

# Line ~2592 - po_history INSERT
cursor.execute("""
    INSERT INTO pcb_inventory.po_history
    (po_number, item, pcn, mpn, date_code, quantity, transaction_type,
     transaction_date, location_from, location_to, user_id)
    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s)
""", (
    data.get('po_number'),
    data.get('item'),
    pcn_number,
    data.get('mpn'),
    data.get('date_code'),
    data.get('quantity'),
    'PCN Generation',
    '-',  # ← MUST BE DASH, NOT "Stock"
    'Inventory',
    session.get('username', 'system')
))
```

**Database Update Command** (for existing data):
```sql
UPDATE pcb_inventory."tblWhse_Inventory" SET loc_from = '-' WHERE loc_from = 'Stock';
UPDATE pcb_inventory."tblTransaction" SET loc_from = '-' WHERE loc_from = 'Stock';
UPDATE pcb_inventory.po_history SET location_from = '-' WHERE location_from = 'Stock';
```

---

## 2. PCN History - No Duplicates, Show Unique PCNs Only

**REQUIREMENT**: PCN history queries MUST return **unique PCNs only** (no duplicates). Each PCN should appear only once, showing the most recent transaction data.

**WHY**:
- Each PCN can have multiple transactions (GEN, PICK, STOCK, UPDATE, etc.)
- Without `DISTINCT ON`, PCN 43316 with 3 transactions would show 3 times in the list
- Users only want to see each PCN once with its current state
- The `tran_time` column is VARCHAR containing dates like "11/12/25" which sort alphabetically, NOT chronologically
- Using `DISTINCT ON (t.pcn)` with `ORDER BY t.pcn, t.id DESC` ensures only the most recent transaction per PCN is shown

**Code Locations in app.py**:
```python
# Line ~775 - get_pcn_history method
# CRITICAL: Use subquery to get unique PCNs AND sort by newest first
query = """
    SELECT * FROM (
        SELECT DISTINCT ON (t.pcn)  # ← Inner query: get unique PCNs
            t.record_no,
            t.trantype as status,
            t.item as job,
            t.pcn,
            t.id as transaction_id,  # ← MUST include id for sorting
            ...
        FROM pcb_inventory."tblTransaction" t
        LEFT JOIN pcb_inventory."tblWhse_Inventory" w ON t.pcn = w.pcn
        WHERE t.pcn IS NOT NULL
        ORDER BY t.pcn, t.id DESC  # ← Required for DISTINCT ON
    ) sub ORDER BY transaction_id DESC LIMIT %s  # ← Outer query: sort by newest
"""

# Line ~830 - search_pcn method (same pattern)
query = """
    SELECT * FROM (
        SELECT DISTINCT ON (t.pcn) ..., t.id as transaction_id, ...
        ORDER BY t.pcn, t.id DESC
    ) sub ORDER BY transaction_id DESC
"""
```

**WHY THIS WORKS**:
1. Inner query uses `DISTINCT ON (t.pcn)` to get one row per unique PCN
2. Inner query uses `ORDER BY t.pcn, t.id DESC` (required by PostgreSQL for DISTINCT ON)
3. Outer query sorts by `transaction_id DESC` to show NEWEST PCNs first
4. Result: Unique PCNs with newest at the top (auto-refresh shows new PCNs immediately)

**WRONG (DO NOT USE)**:
```python
# WITHOUT SUBQUERY - Sorts by PCN number, not newest!
query = """
    SELECT DISTINCT ON (t.pcn) ...
    FROM pcb_inventory."tblTransaction" t
    WHERE t.pcn IS NOT NULL
"""
query += " ORDER BY t.pcn, t.id DESC"  # ← Shows PCN 1, 2, 3... NOT newest first!
# Result: New PCN 43317 appears in middle/bottom, not at top!

# WITHOUT DISTINCT ON - Shows duplicate PCNs
query = """
    SELECT t.pcn, ...
    FROM pcb_inventory."tblTransaction" t
    WHERE t.pcn IS NOT NULL
"""
query += " ORDER BY t.id DESC"  # ← Shows ALL transactions, causing duplicates!
```

**Example**:
```sql
-- PCN 43316 has 3 transactions in database:
-- id: 165874, trantype: STOCK
-- id: 165873, trantype: PICK
-- id: 165872, trantype: GEN

-- WRONG (shows all 3):
SELECT * FROM tblTransaction WHERE pcn = 43316 ORDER BY id DESC;
-- Returns: 3 rows

-- CORRECT (shows only most recent):
SELECT DISTINCT ON (pcn) * FROM tblTransaction WHERE pcn = 43316 ORDER BY pcn, id DESC;
-- Returns: 1 row (STOCK, id 165874)
```

---

## 3. Pick Operation - Data Type Casting

**REQUIREMENT**: When inserting pick transactions, the `dc` field must be cast to integer because `tblWhse_Inventory.dc` is VARCHAR but `tblTransaction.dc` is INTEGER.

**Code Location in app.py** (~line 500):
```python
cursor.execute("""
    INSERT INTO pcb_inventory."tblTransaction"
    (trantype, item, pcn, mpn, dc, tranqty, tran_time, loc_from, loc_to, userid)
    SELECT
        'PICK',
        %s,
        pcn,
        mpn,
        dc::integer,  # ← MUST CAST TO INTEGER
        %s,
        CURRENT_TIMESTAMP,
        'Receiving Area',
        'MFG Floor',
        %s
    FROM pcb_inventory."tblWhse_Inventory"
    WHERE item::text = %s
    LIMIT 1
""", (job, quantity, username, job))
```

**ERROR WITHOUT CAST**:
```
psycopg2.errors.DatatypeMismatch: column "dc" is of type integer but expression is of type character varying
```

---

## 4. Database Column Names - USE CORRECT NAMES

**REQUIREMENT**: PostgreSQL column names in `tblTransaction` table do NOT have underscores. Always use the correct column names.

**CORRECT Column Names**:
- `trantype` (NOT `tran_type`)
- `tranqty` (NOT `tran_qty`)
- `userid` (NOT `user_id`)

**Code Examples**:
```python
# CORRECT:
SELECT trantype, tranqty, userid FROM pcb_inventory."tblTransaction"

# WRONG:
SELECT tran_type, tran_qty, user_id FROM pcb_inventory."tblTransaction"  # ← Will fail!
```

---

## 5. Connection Pool Management - ALWAYS INITIALIZE PROPERLY

**REQUIREMENT**: All database operations must initialize `conn = None` and `cursor = None` before the try block to prevent connection leaks.

**Code Pattern**:
```python
def some_database_function():
    conn = None  # ← MUST INITIALIZE
    cursor = None  # ← MUST INITIALIZE
    try:
        conn = self.get_connection()
        cursor = conn.cursor()
        # ... database operations ...
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error: {e}")
    finally:
        if cursor:  # ← CHECK BEFORE CLOSING
            cursor.close()
        if conn:  # ← CHECK BEFORE RETURNING
            self.return_connection(conn)
```

**WHY**: Without initialization, if an error occurs before connection/cursor creation, the finally block will try to close undefined variables, causing more errors and connection leaks.

---

## 6. PostgreSQL ON CONFLICT - DO NOT USE WITH PARTIAL CONSTRAINTS

**REQUIREMENT**: PostgreSQL does NOT support `ON CONFLICT` with PARTIAL unique constraints (constraints with WHERE clauses). Use simple INSERT statements instead.

**CORRECT Approach**:
```python
# Simple INSERT - no ON CONFLICT
cursor.execute("""
    INSERT INTO pcb_inventory."tblWhse_Inventory"
    (item, pcn, mpn, dc, onhandqty, loc_from, loc_to, msd, po)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
""", (...))
```

**WRONG (DO NOT USE)**:
```python
# This will FAIL if the unique constraint has a WHERE clause
cursor.execute("""
    INSERT INTO pcb_inventory."tblWhse_Inventory" (...)
    VALUES (...)
    ON CONFLICT (item, pcn, mpn) DO UPDATE ...  # ← FAILS with partial constraints
""", (...))
```

**ERROR MESSAGE**:
```
there is no unique or exclusion constraint matching the ON CONFLICT specification
```

---

## 7. Date Serialization - Handle Both Datetime and String

**REQUIREMENT**: The `tran_time` field is stored as VARCHAR, not timestamp. Code must handle both datetime objects and strings when serializing to JSON.

**Code Location** (~line 2994):
```python
for record in history:
    if record.get('generated_at'):
        # Handle both datetime objects and string dates
        if hasattr(record['generated_at'], 'isoformat'):
            record['generated_at'] = record['generated_at'].isoformat()
        # else: leave as string
```

---

## 8. Table and Column Name Case Sensitivity

**REQUIREMENT**: PostgreSQL is case-sensitive for quoted identifiers. Always use exact case in table/column names.

**CORRECT**:
```sql
SELECT * FROM pcb_inventory."tblTransaction"  -- Quoted, exact case
SELECT * FROM pcb_inventory."tblWhse_Inventory"  -- Quoted, exact case
SELECT * FROM pcb_inventory."tblPCB_Inventory"  -- Quoted, exact case
```

**Common Column Name Fixes**:
- Use `migrated_at` NOT `created_at` in warehouse and PCB inventory tables
- Use case-sensitive table names with quotes: `"tblTransaction"`, `"tblWhse_Inventory"`

---

## 9. Auto-Refresh for New PCNs

**REQUIREMENT**: After generating a new PCN, the frontend must auto-refresh the PCN history table to show the new PCN at the top.

**Implementation** (in generate_pcn.html ~line 586):
```javascript
setTimeout(() => {
    console.log('🔄 Auto-refreshing PCN history to show newly generated PCN:', result.pcn_number);
    loadPCNHistory();
    setTimeout(() => {
        const historySection = document.getElementById('pcnHistoryTable');
        if (historySection) {
            historySection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            const firstRow = document.querySelector('#pcnHistoryBody tr:first-child');
            if (firstRow) {
                firstRow.style.backgroundColor = '#d4edda';
                setTimeout(() => {
                    firstRow.style.backgroundColor = '';
                }, 3000);
            }
        }
    }, 800);
}, 1000);
```

---

## 10. PO History Table - Correct Table and Column Names

**REQUIREMENT**: The PO History page must query the `po_history` table, NOT `tblReceipt`.

**Correct Table Schema**:
```sql
po_history table columns:
- id
- po_number (NOT po)
- item
- pcn
- mpn
- date_code (NOT dc)
- quantity (NOT qty_rec)
- transaction_type (NOT tran_type)
- transaction_date (NOT date_rec)
- location_from (NOT loc_from)
- location_to (NOT loc_to)
- user_id
```

**Code Location in app.py** (~line 2334):
```python
# CORRECT:
query = """
    SELECT id, po_number, item, pcn, mpn, date_code, quantity,
           transaction_type, transaction_date, location_from, location_to, user_id
    FROM pcb_inventory.po_history
    WHERE 1=1
"""

# WRONG (DO NOT USE):
query = """
    SELECT pcn, tran_type, item, qty_rec, mpn, dc, msd, po,
           comments, date_rec, loc_from, loc_to, user_id
    FROM pcb_inventory."tblReceipt"  # ← WRONG TABLE!
    WHERE 1=1
"""
```

**Template File**: `templates/po_history.html` must use the correct column names:
- `receipt.transaction_date` (not `receipt.date_rec`)
- `receipt.po_number` (not `receipt.po`)
- `receipt.transaction_type` (not `receipt.tran_type`)
- `receipt.date_code` (not `receipt.dc`)
- `receipt.quantity` (not `receipt.qty_rec`)
- `receipt.location_from` (not `receipt.loc_from`)
- `receipt.location_to` (not `receipt.loc_to`)

---

## 11. PCN History Pagination - Sufficient Record Limit

**REQUIREMENT**: The frontend must request enough records to show ALL unique PCNs, not just a small subset.

**WHY**: With 31,798+ unique PCNs, a limit of 10,000 would only show the first 10,000 records, hiding the rest.

**Code Location in generate_pcn.html** (~line 882):
```javascript
// CORRECT: High limit to fetch all records
fetch(`/api/pcn/history?limit=100000&_=${timestamp}`, {

// WRONG (DO NOT USE):
fetch(`/api/pcn/history?limit=10000&_=${timestamp}`, {  // ← Too small! Only shows 10k out of 31k+ PCNs
```

**Note**: The limit should be higher than your maximum expected number of PCNs. Set to 100,000 to allow for future growth.

---

## 12. Testing Data Cleanup - Remove All Test PCNs

**REQUIREMENT**: Testing PCNs (items containing "TEST" in the name) must be deleted from ALL tables to maintain clean production data.

**WHY**:
- Testing PCNs create orphan records in warehouse inventory
- They don't appear in PCN History if they lack transaction records
- They clutter the database with non-production data
- Can cause confusion when reviewing inventory

**Cleanup Commands**:
```sql
-- Delete from warehouse inventory
DELETE FROM pcb_inventory."tblWhse_Inventory" WHERE item ILIKE '%test%';

-- Delete from transaction history
DELETE FROM pcb_inventory."tblTransaction" WHERE item ILIKE '%test%';

-- Delete from PO history
DELETE FROM pcb_inventory.po_history WHERE item ILIKE '%test%';
```

**Verification Command**:
```sql
-- Should return 0 for all tables
SELECT 'tblWhse_Inventory' as table_name, COUNT(*) as remaining_test_records
FROM pcb_inventory."tblWhse_Inventory" WHERE item ILIKE '%test%'
UNION ALL
SELECT 'tblTransaction', COUNT(*)
FROM pcb_inventory."tblTransaction" WHERE item ILIKE '%test%'
UNION ALL
SELECT 'po_history', COUNT(*)
FROM pcb_inventory.po_history WHERE item ILIKE '%test%';
```

**Orphan PCNs**: Testing PCNs often appear as "orphan" records - existing in `tblWhse_Inventory` but not in `tblTransaction`. This happens when data is inserted directly into the warehouse table without creating corresponding transaction records.

**Last Cleanup**: 2025-11-13
- Deleted 6 records from warehouse inventory
- Deleted 41 records from transaction table
- Deleted 4 records from PO history

---

## Summary Checklist for Any New Data Migration

When performing data migrations or transfers, ALWAYS verify:

- [ ] All "Stock" values in `loc_from` fields are replaced with "-"
- [ ] All PCN history queries use **subquery with DISTINCT ON** to show unique PCNs AND newest first
- [ ] Inner query: `SELECT DISTINCT ON (t.pcn) ... ORDER BY t.pcn, t.id DESC`
- [ ] Outer query: `SELECT * FROM (...) sub ORDER BY transaction_id DESC`
- [ ] Pick operation casts `dc::integer` in transaction insert
- [ ] Column names are correct: `trantype`, `tranqty`, `userid`
- [ ] All database functions initialize `conn = None` and `cursor = None`
- [ ] No `ON CONFLICT` clauses with partial unique constraints
- [ ] Date serialization handles both datetime and string types
- [ ] Table names use proper case: `"tblTransaction"`, `"tblWhse_Inventory"`
- [ ] Auto-refresh functionality is active after PCN generation
- [ ] PO History page queries `po_history` table with correct column names
- [ ] PCN History limit is set high enough (100,000) to show all records
- [ ] All testing PCNs (items with "TEST" in name) are deleted from all tables

---

**LAST UPDATED**: 2025-11-13

**CRITICAL**: These fixes solve production issues that caused connection pool exhaustion, data not appearing, and operations failing. DO NOT REVERT THESE CHANGES.
