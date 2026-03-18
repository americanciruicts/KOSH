#!/usr/bin/env python3
"""
Cleanup script: Fix MPN whitespace corruption introduced during Access -> KOSH migration.

The mdb-export tool introduced leading tabs, newlines, non-breaking spaces, and trailing
whitespace into MPN fields in tblTransaction, tblReceipt, and tblWhse_Inventory.

This script:
1. Shows all affected records (dry run by default)
2. Strips leading/trailing whitespace (tabs, newlines, \xa0) from MPN fields
3. Logs all changes

Usage:
    python cleanup_mpn_whitespace.py          # Dry run - show what would change
    python cleanup_mpn_whitespace.py --fix    # Actually fix the data
"""

import sys
import os
import psycopg2
from datetime import datetime

DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'aci-database'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'kosh'),
    'user': os.getenv('POSTGRES_USER', 'stockpick_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'stockpick_pass')
}

TABLES = [
    ('tblWhse_Inventory', 'id'),
    ('tblTransaction', 'id'),
    ('tblReceipt', 'id'),
]

# Characters to strip from MPN fields
WHITESPACE_CHARS = ' \t\n\r\xa0'


def find_dirty_mpns(cur):
    """Find all MPN values with leading/trailing whitespace."""
    all_dirty = []

    for table, pk in TABLES:
        cur.execute(f"""
            SELECT {pk}, mpn
            FROM pcb_inventory."{table}"
            WHERE mpn IS NOT NULL
              AND mpn != TRIM(BOTH FROM REPLACE(REPLACE(REPLACE(mpn, E'\\t', ''), E'\\n', ''), E'\\r', ''))
        """)
        rows = cur.fetchall()

        # Also catch non-breaking spaces (\xa0) and leading whitespace
        cur.execute(f"""
            SELECT {pk}, mpn
            FROM pcb_inventory."{table}"
            WHERE mpn IS NOT NULL
              AND (mpn LIKE E' %%' OR mpn LIKE E'%%\\t%%' OR mpn LIKE E'%%\\n%%'
                   OR mpn LIKE E'%%\\r%%' OR mpn != BTRIM(mpn))
        """)
        rows2 = cur.fetchall()

        # Combine unique
        seen = set()
        combined = []
        for row in rows + rows2:
            if row[0] not in seen:
                seen.add(row[0])
                # Check if stripping actually changes the value
                cleaned = row[1].strip(WHITESPACE_CHARS)
                # Also strip internal \xa0
                cleaned = cleaned.replace('\xa0', '')
                if cleaned != row[1]:
                    combined.append((row[0], row[1], cleaned))

        if combined:
            all_dirty.append((table, combined))

    return all_dirty


def main():
    dry_run = '--fix' not in sys.argv

    if dry_run:
        print("=" * 60)
        print("DRY RUN - No changes will be made")
        print("Run with --fix to apply changes")
        print("=" * 60)
    else:
        print("=" * 60)
        print("FIXING MPN WHITESPACE - Changes will be committed")
        print("=" * 60)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    dirty = find_dirty_mpns(cur)

    total_fixes = 0

    for table, records in dirty:
        pk = [t[1] for t in TABLES if t[0] == table][0]
        print(f"\n--- {table}: {len(records)} records to fix ---")

        for record_id, old_mpn, new_mpn in records:
            print(f"  ID {record_id}: {repr(old_mpn)} -> {repr(new_mpn)}")
            total_fixes += 1

            if not dry_run:
                cur.execute(f"""
                    UPDATE pcb_inventory."{table}"
                    SET mpn = %s
                    WHERE {pk} = %s
                """, (new_mpn, record_id))

    print(f"\n{'=' * 60}")
    print(f"Total records to fix: {total_fixes}")

    if not dry_run and total_fixes > 0:
        conn.commit()
        print(f"COMMITTED {total_fixes} fixes at {datetime.now()}")
    elif not dry_run:
        print("No changes needed.")
    else:
        print("Run with --fix to apply these changes.")

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
