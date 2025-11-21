#!/usr/bin/env python3
"""
Import PCB inventory data from .mdb file to PostgreSQL
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
MDB_TABLE = 'tblPCB_Inventory'

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
        # Clear existing data
        cur.execute('TRUNCATE TABLE pcb_inventory."tblPCB_Inventory" RESTART IDENTITY CASCADE')
        print("Cleared existing PCB inventory data")

        # Prepare insert data
        insert_data = []
        for record in records:
            # Convert empty strings to None
            pcn = int(record.get('PCN', 0)) if record.get('PCN', '').strip() else None
            job = record.get('Job', '').strip() or None
            pcb_type = record.get('PCB_Type', '').strip() or None
            qty = int(record.get('Qty', 0)) if record.get('Qty', '').strip() else None
            location = record.get('Location', '').strip() or None
            checked_on = record.get('Checked on 8/14/25', '').strip() or None

            insert_data.append((
                pcn, job, pcb_type, qty, location, checked_on
            ))

        # Bulk insert using execute_values for better performance
        insert_query = """
            INSERT INTO pcb_inventory."tblPCB_Inventory"
            (pcn, job, pcb_type, qty, location, checked_on_8_14_25)
            VALUES %s
        """

        print(f"Importing {len(insert_data)} records to PostgreSQL...")
        execute_values(cur, insert_query, insert_data, page_size=100)

        conn.commit()
        print(f"Successfully imported {len(insert_data)} records")

        # Verify import
        cur.execute('SELECT COUNT(*) FROM pcb_inventory."tblPCB_Inventory"')
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
    print("Importing PCB Inventory Data from .mdb file")
    print("=" * 60)

    # Read data from .mdb
    records = read_mdb_data()

    if records:
        # Import to PostgreSQL
        import_to_postgresql(records)
        print("\n✓ Import completed successfully!")
    else:
        print("\n✗ No data found to import")

    print("=" * 60)

if __name__ == '__main__':
    main()
