#!/usr/bin/env python3
"""
Re-import BOM data from .mdb file to PostgreSQL.
Also creates missing tblJob records for any new jobs found in BOM.
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
    'database': 'kosh',
    'user': 'stockpick_user',
    'password': 'stockpick_pass'
}

# .mdb file path
MDB_PATH = '/app/INVENTORY TABLE.mdb'
MDB_TABLE = 'tblBOM'

# Column mapping: .mdb column name -> DB column name
COLUMN_MAP = {
    'Line': 'line',
    'DESC': 'DESC',
    'MAN': 'man',
    'MPN': 'mpn',
    'ACI PN': 'aci_pn',
    'QTY': 'qty',
    'POU': 'pou',
    'Loc': 'loc',
    'Cost': 'cost',
    'Job': 'job',
    'Job Rev': 'job_rev',
    'Last Rev': 'last_rev',
    'Cust': 'cust',
    'Cust PN': 'cust_pn',
    'Cust Rev': 'cust_rev',
    'Date_Loaded': 'date_loaded',
}


def read_mdb_data():
    """Read BOM data from Access database using mdb-export."""
    print(f"Reading data from {MDB_PATH}, table: {MDB_TABLE}")

    try:
        result = subprocess.run(
            ['mdb-export', MDB_PATH, MDB_TABLE],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            print(f"Error running mdb-export: {result.stderr}")
            return []

        csv_reader = csv.DictReader(io.StringIO(result.stdout))
        records = list(csv_reader)
        print(f"Found {len(records)} BOM records in .mdb file")
        return records

    except subprocess.TimeoutExpired:
        print("mdb-export command timed out")
        return []
    except Exception as e:
        print(f"Error reading .mdb file: {e}")
        return []


def import_bom_to_postgresql(records):
    """Import BOM records to PostgreSQL, replacing existing data."""
    if not records:
        print("No records to import")
        return

    print("Connecting to PostgreSQL...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        # Get current count
        cur.execute('SELECT COUNT(*) FROM pcb_inventory."tblBOM"')
        old_count = cur.fetchone()[0]
        print(f"Current tblBOM records: {old_count}")

        # Clear existing BOM data
        print("Clearing existing tblBOM data...")
        cur.execute('DELETE FROM pcb_inventory."tblBOM"')
        print(f"Deleted {old_count} existing records")

        # Prepare insert data
        insert_data = []
        for record in records:
            row = []
            for mdb_col, db_col in COLUMN_MAP.items():
                val = record.get(mdb_col, '').strip() if record.get(mdb_col) else None
                if val == '':
                    val = None
                row.append(val)
            insert_data.append(tuple(row))

        db_columns = list(COLUMN_MAP.values())
        col_names = ', '.join(f'"{c}"' for c in db_columns)

        insert_query = f"""
            INSERT INTO pcb_inventory."tblBOM" ({col_names})
            VALUES %s
        """

        print(f"Importing {len(insert_data)} BOM records...")
        execute_values(cur, insert_query, insert_data, page_size=500)

        conn.commit()
        print(f"Successfully imported {len(insert_data)} BOM records")

        # Verify
        cur.execute('SELECT COUNT(*) FROM pcb_inventory."tblBOM"')
        new_count = cur.fetchone()[0]
        print(f"Total BOM records in database: {new_count}")

        cur.execute('SELECT COUNT(DISTINCT job) FROM pcb_inventory."tblBOM"')
        job_count = cur.fetchone()[0]
        print(f"Distinct jobs in BOM: {job_count}")

    except Exception as e:
        conn.rollback()
        print(f"Error importing BOM: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def create_missing_jobs():
    """Create tblJob records for jobs that exist in BOM but not in tblJob."""
    print("\nChecking for missing tblJob records...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        # Find jobs in BOM that don't have a tblJob record
        cur.execute("""
            SELECT DISTINCT b.job, b.job_rev, b.cust, b.cust_pn, b.cust_rev, b.last_rev
            FROM pcb_inventory."tblBOM" b
            LEFT JOIN pcb_inventory."tblJob" j ON b.job = j.job_number
            WHERE j.job_number IS NULL
            ORDER BY b.job
        """)
        missing_jobs = cur.fetchall()
        print(f"Found {len(missing_jobs)} jobs in BOM without tblJob records")

        if not missing_jobs:
            print("All jobs already have tblJob records")
            return

        # Insert missing jobs
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        insert_data = []
        for job, job_rev, cust, cust_pn, cust_rev, last_rev in missing_jobs:
            insert_data.append((job, cust, cust_pn, job_rev, cust_rev, last_rev, now))

        insert_query = """
            INSERT INTO pcb_inventory."tblJob" (job_number, customer, cust_pn, job_rev, cust_rev, last_rev, created_at)
            VALUES %s
        """

        print(f"Creating {len(insert_data)} new tblJob records...")
        execute_values(cur, insert_query, insert_data, page_size=500)
        conn.commit()

        # Verify
        cur.execute('SELECT COUNT(*) FROM pcb_inventory."tblJob"')
        total_jobs = cur.fetchone()[0]
        print(f"Total tblJob records: {total_jobs}")

    except Exception as e:
        conn.rollback()
        print(f"Error creating jobs: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def main():
    print("=" * 60)
    print("Re-importing BOM data from .mdb file")
    print("=" * 60)

    # Read BOM data from .mdb
    records = read_mdb_data()

    if records:
        # Import to PostgreSQL
        import_bom_to_postgresql(records)

        # Create missing job records
        create_missing_jobs()

        print("\n> BOM re-import completed successfully!")
    else:
        print("\n> No BOM data found to import")

    print("=" * 60)


if __name__ == '__main__':
    main()
