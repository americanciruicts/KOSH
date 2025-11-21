#!/usr/bin/env python3
"""
Migration Script: Import PCB Inventory from Access Database (.mdb) to PostgreSQL

This script reads data from tblPCB_Inventory in the Access database and
imports it into the PostgreSQL pcb_inventory schema.
"""

import subprocess
import csv
import io
import psycopg2
from psycopg2.extras import execute_values
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'host': 'aci-database',
    'port': 5432,
    'database': 'pcb_inventory',
    'user': 'stockpick_user',
    'password': 'stockpick_pass'
}

# Access database path
MDB_PATH = "/app/INVENTORY TABLE.mdb"
MDB_TABLE = "tblPCB_Inventory"

def read_mdb_data():
    """Read data from Access database using mdb-export."""
    logger.info(f"Reading data from {MDB_PATH}, table: {MDB_TABLE}")

    try:
        # Use mdb-export to get CSV data
        result = subprocess.run(
            ['mdb-export', MDB_PATH, MDB_TABLE],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            logger.error(f"Error reading .mdb file: {result.stderr}")
            return []

        # Parse CSV data
        csv_data = result.stdout
        if not csv_data.strip():
            logger.warning("No data found in .mdb table")
            return []

        csv_reader = csv.DictReader(io.StringIO(csv_data))
        records = list(csv_reader)

        logger.info(f"Successfully read {len(records)} records from .mdb file")
        return records

    except subprocess.TimeoutExpired:
        logger.error("Timeout while reading .mdb file")
        return []
    except Exception as e:
        logger.error(f"Error reading .mdb file: {e}")
        return []

def clear_existing_data(conn):
    """Clear existing data from PostgreSQL table."""
    logger.info("Clearing existing PCB inventory data from PostgreSQL...")

    try:
        with conn.cursor() as cur:
            # Delete all records from tblPCB_Inventory
            cur.execute("DELETE FROM pcb_inventory.\"tblPCB_Inventory\"")
            deleted_count = cur.rowcount
            conn.commit()
            logger.info(f"Deleted {deleted_count} existing records")
            return True
    except Exception as e:
        logger.error(f"Error clearing data: {e}")
        conn.rollback()
        return False

def import_to_postgresql(records):
    """Import records to PostgreSQL database."""
    if not records:
        logger.warning("No records to import")
        return False

    logger.info(f"Importing {len(records)} records to PostgreSQL...")

    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(**DB_CONFIG)
        logger.info("Connected to PostgreSQL database")

        # Clear existing data
        if not clear_existing_data(conn):
            logger.error("Failed to clear existing data")
            conn.close()
            return False

        # Prepare data for insertion
        insert_data = []
        skipped = 0

        for record in records:
            try:
                # Extract and clean data
                pcn = int(record.get('PCN', 0)) if record.get('PCN') else None
                job = record.get('Job', '').strip()
                pcb_type = record.get('PCB_Type', '').strip()
                qty = int(record.get('Qty', 0)) if record.get('Qty') else 0
                location = record.get('Location', '').strip()
                checked_on = record.get('Checked on 8/14/25', '').strip()

                # Skip records without essential data
                if not pcn:
                    skipped += 1
                    continue

                insert_data.append((
                    pcn,
                    job,
                    pcb_type,
                    qty,
                    location,
                    checked_on
                ))

            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping invalid record: {record}. Error: {e}")
                skipped += 1
                continue

        if not insert_data:
            logger.error("No valid records to import after filtering")
            conn.close()
            return False

        logger.info(f"Prepared {len(insert_data)} valid records for import (skipped {skipped})")

        # Insert data using batch insert for better performance
        with conn.cursor() as cur:
            insert_query = """
                INSERT INTO pcb_inventory."tblPCB_Inventory"
                (pcn, job, pcb_type, qty, location, checked_on_8_14_25)
                VALUES %s
            """

            execute_values(cur, insert_query, insert_data, page_size=100)
            conn.commit()

            logger.info(f"Successfully imported {len(insert_data)} records to PostgreSQL")

        # Verify import
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM pcb_inventory.\"tblPCB_Inventory\"")
            count = cur.fetchone()[0]
            logger.info(f"Total records in PostgreSQL after import: {count}")

        conn.close()
        return True

    except psycopg2.Error as e:
        logger.error(f"PostgreSQL error: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False
    except Exception as e:
        logger.error(f"Unexpected error during import: {e}")
        if 'conn' in locals():
            conn.close()
        return False

def main():
    """Main migration function."""
    logger.info("=" * 60)
    logger.info("PCB Inventory Migration: Access (.mdb) -> PostgreSQL")
    logger.info("=" * 60)

    # Step 1: Read data from .mdb file
    records = read_mdb_data()

    if not records:
        logger.error("Migration failed: No data to import")
        return False

    # Step 2: Import to PostgreSQL
    success = import_to_postgresql(records)

    if success:
        logger.info("=" * 60)
        logger.info("Migration completed successfully!")
        logger.info("=" * 60)
    else:
        logger.error("=" * 60)
        logger.error("Migration failed!")
        logger.error("=" * 60)

    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
