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
    'database': 'kosh',
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
            pcn = record.get('PCN', '').strip() or None  # Keep as string/text
            mpn = record.get('MPN', '').strip() or None
            dc = record.get('DC', '').strip() or None  # Keep as string (can be "1-5", "2-3", etc.)

            # Convert OnHandQty to integer
            onhandqty_str = record.get('OnHandQty', '').strip()
            try:
                onhandqty = int(onhandqty_str) if onhandqty_str else None
            except ValueError:
                onhandqty = None

            loc_to = record.get('Loc_To', '').strip() or None
            mfg_qty = record.get('MFG_Qty', '').strip() or None  # Keep as text
            qty_old = record.get('Qty_Old', '').strip() or None  # Keep as text
            msd = record.get('MSD', '').strip() or None  # Keep as string (might not always be integer)
            po = record.get('PO', '').strip() or None
            cost = record.get('Cost', '').strip() or None

            insert_data.append((
                item, pcn, mpn, dc, onhandqty, loc_to,
                mfg_qty, qty_old, msd, po, cost
            ))

        # Idempotent re-import: for each row from Access
        #   - if (pcn, item, mpn) matches an existing row -> UPDATE quantities/locations
        #   - if PCN exists with a DIFFERENT (item, mpn)  -> SKIP + log a conflict
        #   - if PCN is new                                -> INSERT
        # This prevents the old blind bulk-insert from creating duplicate rows
        # every time this script is re-run (root cause of the 92 duplicate PCN
        # groups discovered on 2026-04-16, including PCN 45061).
        print(f"Importing {len(insert_data)} records to PostgreSQL (idempotent mode)...")
        inserted = updated = skipped_conflict = 0
        conflicts = []

        def _norm(v):
            return (v or '').strip().lower()

        for row in insert_data:
            item, pcn, mpn, dc, onhandqty, loc_to, mfg_qty, qty_old, msd, po, cost = row

            if not pcn:
                # Can't reason about a row with no PCN — fall back to a plain insert
                cur.execute("""
                    INSERT INTO pcb_inventory."tblWhse_Inventory"
                    (item, pcn, mpn, dc, onhandqty, loc_to, mfg_qty, qty_old, msd, po, cost)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, row)
                inserted += 1
                continue

            cur.execute("""
                SELECT id, item, mpn
                FROM pcb_inventory."tblWhse_Inventory"
                WHERE pcn::text = %s
            """, (str(pcn),))
            existing_rows = cur.fetchall()

            if not existing_rows:
                cur.execute("""
                    INSERT INTO pcb_inventory."tblWhse_Inventory"
                    (item, pcn, mpn, dc, onhandqty, loc_to, mfg_qty, qty_old, msd, po, cost)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, row)
                inserted += 1
                continue

            # Does any existing row match this (item, mpn)?
            match_id = None
            for ex_id, ex_item, ex_mpn in existing_rows:
                if _norm(ex_item) == _norm(item) and (
                    not _norm(ex_mpn) or not _norm(mpn) or _norm(ex_mpn) == _norm(mpn)
                ):
                    match_id = ex_id
                    break

            if match_id is not None:
                # Do NOT overwrite onhandqty, mfg_qty or loc_to from Access.
                # Access does NOT decrement OnHandQty on PICK, so its value is
                # stale for any part that KOSH has picked. KOSH's transaction
                # log + the on-hand reconcile thread are the source of truth
                # for live quantities and locations. Access only contributes
                # static metadata (item, mpn, dc, msd, po, cost, qty_old).
                cur.execute("""
                    UPDATE pcb_inventory."tblWhse_Inventory"
                    SET item = %s, mpn = %s, dc = %s,
                        qty_old = %s, msd = %s, po = %s, cost = %s,
                        migrated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (item, mpn, dc, qty_old, msd, po, cost, match_id))
                updated += 1
            else:
                # PCN in use by a different part — do NOT create a duplicate row.
                skipped_conflict += 1
                conflicts.append({
                    'pcn': pcn,
                    'incoming_item': item, 'incoming_mpn': mpn,
                    'existing': [(ex_item, ex_mpn) for _, ex_item, ex_mpn in existing_rows],
                })

        conn.commit()
        print(f"Re-import summary: inserted={inserted}, updated={updated}, "
              f"skipped_pcn_conflicts={skipped_conflict}")
        if conflicts:
            print("PCN conflicts (rows NOT imported to avoid duplication):")
            for c in conflicts[:50]:
                print(f"  PCN {c['pcn']}: incoming {c['incoming_item']}/{c['incoming_mpn']} "
                      f"vs existing {c['existing']}")
            if len(conflicts) > 50:
                print(f"  ... and {len(conflicts) - 50} more conflicts")

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
