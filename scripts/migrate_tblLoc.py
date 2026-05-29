#!/usr/bin/env python3
"""
Migration script: Import tblLoc from INVENTORY TABLE.mdb into PostgreSQL.
Creates the tblLoc table in pcb_inventory schema and populates it with location data.
Enforces 7-digit numeric location constraint.

GATED: Refuses to run unless --i-know-this-overwrites-kosh-data is passed.
"""

import os
import sys
import psycopg2

if '--i-know-this-overwrites-kosh-data' not in sys.argv:
    print('REFUSED: migrate_tblLoc.py is a destructive re-import.')
    print('Re-run with --i-know-this-overwrites-kosh-data if intentional.')
    sys.exit(2)
sys.argv = [a for a in sys.argv if a != '--i-know-this-overwrites-kosh-data']

# Try to import access_parser for reading .mdb files
try:
    from access_parser import AccessParser
except ImportError:
    print("ERROR: access_parser not installed. Run: pip install access-parser")
    sys.exit(1)

# Database config (matches app.py)
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'aci-database'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'pcb_inventory'),
    'user': os.getenv('POSTGRES_USER', 'stockpick_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'stockpick_pass')
}

MDB_PATH = os.path.join(os.path.dirname(__file__), 'INVENTORY TABLE.mdb')


def migrate():
    """Read tblLoc from .mdb and insert into PostgreSQL."""

    # Step 1: Read from Access DB
    print(f"Reading tblLoc from: {MDB_PATH}")
    db = AccessParser(MDB_PATH)
    table = db.parse_table('tblLoc')

    areas = table['area']
    shelves = table['Shelf']
    locs = table['Loc']
    locations = table['Location']

    total = len(locations)
    print(f"Found {total} location records in .mdb")

    # Step 2: Connect to PostgreSQL
    print(f"Connecting to PostgreSQL at {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        # Step 3: Drop and recreate tblLoc table
        print("Creating pcb_inventory.tblLoc table...")
        cursor.execute('DROP TABLE IF EXISTS pcb_inventory."tblLoc" CASCADE;')
        cursor.execute("""
            CREATE TABLE pcb_inventory."tblLoc" (
                id SERIAL PRIMARY KEY,
                area INTEGER,
                shelf VARCHAR(10),
                loc VARCHAR(10),
                location VARCHAR(50) NOT NULL,
                CONSTRAINT uq_tblLoc_location UNIQUE (location),
                CONSTRAINT chk_location_format CHECK (
                    location ~ '^\\d{7,8}$'
                    OR location IN ('Receiving Area', 'Rec Area', 'Count Area', 'Stock Room', 'MFG Floor')
                )
            );
        """)

        # Step 4: Insert all 7-digit locations
        inserted = 0
        skipped = 0
        skipped_items = []

        for i in range(total):
            area = int(areas[i]) if areas[i] else None
            shelf = str(shelves[i]).strip() if shelves[i] else None
            loc_val = str(locs[i]).strip() if locs[i] else None
            location = str(locations[i]).strip()

            # Only import 7-digit numeric locations
            if len(location) == 7 and location.isdigit():
                cursor.execute("""
                    INSERT INTO pcb_inventory."tblLoc" (area, shelf, loc, location)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (location) DO NOTHING;
                """, (area, shelf, loc_val, location))
                inserted += 1
            else:
                skipped += 1
                if len(skipped_items) < 20:
                    skipped_items.append(location)

        # Step 5: Also insert standard text locations (without area/shelf/loc)
        standard_locations = ['Receiving Area', 'Rec Area', 'Count Area', 'Stock Room', 'MFG Floor']
        for std_loc in standard_locations:
            cursor.execute("""
                INSERT INTO pcb_inventory."tblLoc" (area, shelf, loc, location)
                VALUES (NULL, NULL, NULL, %s)
                ON CONFLICT (location) DO NOTHING;
            """, (std_loc,))

        # Step 6: Create index for fast lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tblLoc_location
            ON pcb_inventory."tblLoc" (location);
        """)

        conn.commit()

        print(f"\n=== Migration Complete ===")
        print(f"Inserted: {inserted} locations (7-digit)")
        print(f"Skipped:  {skipped} non-7-digit locations")
        if skipped_items:
            print(f"Skipped examples: {skipped_items}")
        print(f"Standard locations added: {len(standard_locations)}")

        # Verify
        cursor.execute('SELECT COUNT(*) FROM pcb_inventory."tblLoc";')
        count = cursor.fetchone()[0]
        print(f"Total records in tblLoc: {count}")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    migrate()
