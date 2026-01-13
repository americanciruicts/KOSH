#!/usr/bin/env python3
"""
Import receipt/PO data from .mdb file to PostgreSQL
"""

import subprocess
import psycopg2
from psycopg2.extras import execute_values
import csv
import io
from datetime import datetime

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
MDB_TABLE = 'tblReceipt'

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

def parse_datetime(date_str):
    """Parse Access datetime format."""
    if not date_str or date_str.strip() == '':
        return None
    try:
        # Format: "11/22/16 20:43:14"
        return datetime.strptime(date_str, "%m/%d/%y %H:%M:%S")
    except:
        try:
            # Try alternative format
            return datetime.strptime(date_str, "%m/%d/%Y %H:%M:%S")
        except:
            return None

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
        cur.execute('TRUNCATE TABLE pcb_inventory."tblReceipt" RESTART IDENTITY CASCADE')
        print("Cleared existing receipt data")

        # Prepare insert data
        insert_data = []
        for record in records:
            # Convert empty strings to None
            pcn = int(record.get('PCN', 0)) if record.get('PCN', '').strip() else None
            tran_type = record.get('TranType', '').strip() or None
            item = record.get('Item', '').strip() or None
            qty_rec = int(record.get('Qty_Rec', 0)) if record.get('Qty_Rec', '').strip() else None
            mpn = record.get('MPN', '').strip() or None
            dc = record.get('DC', '').strip() or None
            msd = record.get('MSD', '').strip() or None
            po = record.get('PO', '').strip() or None
            comments = record.get('Comments', '').strip() or None
            date_rec = parse_datetime(record.get('Date_Rec', ''))
            loc_from = record.get('Loc_From', '').strip() or None
            loc_to = record.get('Loc_To', '').strip() or None
            user_id = record.get('UserID', '').strip() or None

            insert_data.append((
                pcn, tran_type, item, qty_rec, mpn, dc, msd, po,
                comments, date_rec, loc_from, loc_to, user_id
            ))

        # Bulk insert using execute_values for better performance
        insert_query = """
            INSERT INTO pcb_inventory."tblReceipt"
            (pcn, tran_type, item, qty_rec, mpn, dc, msd, po,
             comments, date_rec, loc_from, loc_to, user_id)
            VALUES %s
        """

        print(f"Importing {len(insert_data)} records to PostgreSQL...")
        execute_values(cur, insert_query, insert_data, page_size=100)

        conn.commit()
        print(f"Successfully imported {len(insert_data)} records")

        # Verify import
        cur.execute('SELECT COUNT(*) FROM pcb_inventory."tblReceipt"')
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
    print("Importing Receipt/PO Data from .mdb file")
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
