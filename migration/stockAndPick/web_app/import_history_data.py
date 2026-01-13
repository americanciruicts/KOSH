#!/usr/bin/env python3
"""
Import transaction history and part number list from .mdb file to PostgreSQL
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

def read_mdb_table(table_name):
    """Read data from Access database using mdb-export."""
    print(f"Reading data from {MDB_PATH}, table: {table_name}")

    try:
        result = subprocess.run(
            ['mdb-export', MDB_PATH, table_name],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            print(f"Error running mdb-export: {result.stderr}")
            return []

        csv_reader = csv.DictReader(io.StringIO(result.stdout))
        records = list(csv_reader)
        print(f"Found {len(records)} records in {table_name}")
        return records

    except subprocess.TimeoutExpired:
        print(f"mdb-export command timed out for {table_name}")
        return []
    except Exception as e:
        print(f"Error reading {table_name}: {e}")
        return []

def parse_datetime(date_str):
    """Parse Access datetime format."""
    if not date_str or date_str.strip() == '':
        return None
    try:
        return datetime.strptime(date_str, "%m/%d/%y %H:%M:%S")
    except:
        try:
            return datetime.strptime(date_str, "%m/%d/%Y %H:%M:%S")
        except:
            return None

def import_transactions(records):
    """Import transaction records to PostgreSQL."""
    if not records:
        print("No transaction records to import")
        return

    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        # Clear existing data
        cur.execute('TRUNCATE TABLE pcb_inventory."tblTransaction" RESTART IDENTITY CASCADE')
        print("Cleared existing transaction data")

        # Prepare insert data
        insert_data = []
        for record in records:
            record_no = int(record.get('Record_NO', 0)) if record.get('Record_NO', '').strip() else None
            tran_type = record.get('TranType', '').strip() or None
            item = record.get('Item', '').strip() or None
            pcn = int(record.get('PCN', 0)) if record.get('PCN', '').strip() else None
            mpn = record.get('MPN', '').strip() or None
            dc = record.get('DC', '').strip() or None
            tran_qty = int(record.get('TranQty', 0)) if record.get('TranQty', '').strip() else None
            tran_time = parse_datetime(record.get('Tran_Time', ''))
            loc_from = record.get('Loc_From', '').strip() or None
            loc_to = record.get('Loc_To', '').strip() or None
            wo = record.get('WO', '').strip() or None
            po = record.get('PO', '').strip() or None
            user_id = record.get('UserID', '').strip() or None

            insert_data.append((
                record_no, tran_type, item, pcn, mpn, dc, tran_qty,
                tran_time, loc_from, loc_to, wo, po, user_id
            ))

        # Bulk insert
        insert_query = """
            INSERT INTO pcb_inventory."tblTransaction"
            (record_no, tran_type, item, pcn, mpn, dc, tran_qty,
             tran_time, loc_from, loc_to, wo, po, user_id)
            VALUES %s
        """

        print(f"Importing {len(insert_data)} transaction records...")
        execute_values(cur, insert_query, insert_data, page_size=1000)

        conn.commit()
        print(f"Successfully imported {len(insert_data)} transaction records")

        # Verify import
        cur.execute('SELECT COUNT(*) FROM pcb_inventory."tblTransaction"')
        count = cur.fetchone()[0]
        print(f"Total transaction records in database: {count}")

    except Exception as e:
        conn.rollback()
        print(f"Error importing transactions: {e}")
        raise
    finally:
        cur.close()
        conn.close()

def import_pn_list(records):
    """Import part number list to PostgreSQL."""
    if not records:
        print("No part number records to import")
        return

    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        # Clear existing data
        cur.execute('TRUNCATE TABLE pcb_inventory."tblPN_List" RESTART IDENTITY CASCADE')
        print("Cleared existing part number data")

        # Prepare insert data
        insert_data = []
        for record in records:
            item = record.get('ITEM', '').strip() or None
            description = record.get('DESC', '').strip() or None

            if item:  # Only insert if item is not null
                insert_data.append((item, description))

        # Bulk insert
        insert_query = """
            INSERT INTO pcb_inventory."tblPN_List"
            (item, description)
            VALUES %s
        """

        print(f"Importing {len(insert_data)} part number records...")
        execute_values(cur, insert_query, insert_data, page_size=1000)

        conn.commit()
        print(f"Successfully imported {len(insert_data)} part number records")

        # Verify import
        cur.execute('SELECT COUNT(*) FROM pcb_inventory."tblPN_List"')
        count = cur.fetchone()[0]
        print(f"Total part number records in database: {count}")

    except Exception as e:
        conn.rollback()
        print(f"Error importing part numbers: {e}")
        raise
    finally:
        cur.close()
        conn.close()

def main():
    """Main function."""
    print("=" * 60)
    print("Importing History Data from .mdb file")
    print("=" * 60)

    # Import transactions (PCN and PO history)
    print("\n--- Transaction History ---")
    transaction_records = read_mdb_table('tblTransaction')
    if transaction_records:
        import_transactions(transaction_records)

    # Import part number list
    print("\n--- Part Number List ---")
    pn_records = read_mdb_table('tblPN_List')
    if pn_records:
        import_pn_list(pn_records)

    print("\n" + "=" * 60)
    print("✓ All history data imported successfully!")
    print("=" * 60)

if __name__ == '__main__':
    main()
