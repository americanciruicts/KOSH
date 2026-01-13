#!/usr/bin/env python3
"""
Re-import warehouse inventory data from .mdb file to PostgreSQL
"""

import subprocess
import psycopg2
from psycopg2.extras import execute_values
import csv
import io

# Database configuration
DB_CONFIG = {
    'host': 'aci-database',
    'port': 5432,
    'database': 'pcb_inventory',
    'user': 'stockpick_user',
    'password': 'stockpick_pass'
}

# .mdb file path
MDB_PATH = '/app/INVENTORY TABLE.mdb'
MDB_TABLE = 'tblWhse_Inventory'

def read_mdb_data():
    """Read data from Access database using mdb-export."""
    print(f"Reading data from {MDB_PATH}, table: {MDB_TABLE}")

    try:
        # Use mdb-export to export data as CSV
        result = subprocess.run(
            ['mdb-export', MDB_PATH, MDB_TABLE],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            print(f"Error running mdb-export: {result.stderr}")
            return []

        # Parse CSV output
        csv_reader = csv.DictReader(io.StringIO(result.stdout))
        records = list(csv_reader)
        print(f"Found {len(records)} records in .mdb file")
        return records

    except subprocess.TimeoutExpired:
        print("mdb-export command timed out")
        return []
    except Exception as e:
        print(f"Error reading .mdb file: {e}")
        return []

def import_to_postgresql(records):
    """Import records to PostgreSQL database."""
    if not records:
        print("No records to import")
        return

    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        # Prepare insert data
        insert_data = []
        for record in records:
            # Convert empty strings to None
            item = record.get('Item', '').strip() or None
            pcn = int(record.get('PCN', 0)) if record.get('PCN', '').strip() else None
            mpn = record.get('MPN', '').strip() or None
            dc = record.get('DC', '').strip() or None  # Keep as string (can be "1-5", "2-3", etc.)
            onhandqty = int(record.get('OnHandQty', 0)) if record.get('OnHandQty', '').strip() else None
            loc_to = record.get('Loc_To', '').strip() or None
            mfg_qty = int(record.get('MFG_Qty', 0)) if record.get('MFG_Qty', '').strip() else None
            qty_old = int(record.get('Qty_Old', 0)) if record.get('Qty_Old', '').strip() else None
            msd = record.get('MSD', '').strip() or None  # Keep as string (might not always be integer)
            po = record.get('PO', '').strip() or None
            cost = record.get('Cost', '').strip() or None

            insert_data.append((
                item, pcn, mpn, dc, onhandqty, loc_to,
                mfg_qty, qty_old, msd, po, cost
            ))

        # Bulk insert using execute_values for better performance
        insert_query = """
            INSERT INTO pcb_inventory."tblWhse_Inventory"
            (item, pcn, mpn, dc, onhandqty, loc_to, mfg_qty, qty_old, msd, po, cost)
            VALUES %s
        """

        print(f"Importing {len(insert_data)} records to PostgreSQL...")
        execute_values(cur, insert_query, insert_data, page_size=100)

        conn.commit()
        print(f"Successfully imported {len(insert_data)} records")

        # Verify import
        cur.execute('SELECT COUNT(*) FROM pcb_inventory."tblWhse_Inventory"')
        count = cur.fetchone()[0]
        print(f"Total records in database: {count}")

    except Exception as e:
        conn.rollback()
        print(f"Error importing to PostgreSQL: {e}")
        raise
    finally:
        cur.close()
        conn.close()

def main():
    """Main function."""
    print("=" * 60)
    print("Re-importing Warehouse Inventory from .mdb file")
    print("=" * 60)

    # Read data from .mdb
    records = read_mdb_data()

    if records:
        # Import to PostgreSQL
        import_to_postgresql(records)
        print("\n✓ Re-import completed successfully!")
    else:
        print("\n✗ No data found to import")

    print("=" * 60)

if __name__ == '__main__':
    main()
