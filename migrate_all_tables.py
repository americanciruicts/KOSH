#!/usr/bin/env python3
"""
Complete Migration Script for ACI Inventory
Migrates ALL tables from Access database (INVENTORY TABLE.mdb) to PostgreSQL
"""

import subprocess
import csv
import io
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import re
import sys
import os
from datetime import datetime
from pathlib import Path

# PostgreSQL reserved keywords that need quoting
RESERVED_KEYWORDS = {
    'desc', 'order', 'group', 'user', 'table', 'select', 'from', 'where',
    'insert', 'update', 'delete', 'create', 'drop', 'alter', 'index', 'key',
    'primary', 'foreign', 'references', 'constraint', 'check', 'unique',
    'default', 'null', 'not', 'and', 'or', 'in', 'like', 'between', 'is',
    'exists', 'having', 'union', 'join', 'inner', 'outer', 'left', 'right',
    'on', 'as', 'distinct', 'all', 'any', 'some', 'case', 'when', 'then',
    'else', 'end', 'if', 'begin', 'commit', 'rollback', 'grant', 'revoke'
}

# Database configuration - use environment variables or defaults
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', 5432)),
    'database': os.environ.get('DB_NAME', 'pcb_inventory'),
    'user': os.environ.get('DB_USER', 'stockpick_user'),
    'password': os.environ.get('DB_PASSWORD', 'stockpick_pass')
}

MDB_FILE = os.environ.get('MDB_FILE', '/app/INVENTORY TABLE.mdb')


def safe_column_name(col_name):
    """Make column name safe for PostgreSQL."""
    # Clean the name - replace spaces and special characters
    clean_name = col_name.replace(' ', '_').replace('-', '_').replace('#', 'num').replace('/', '_')

    # Remove any other problematic characters
    clean_name = re.sub(r'[^\w]', '_', clean_name)

    # Special case: rename 'ID' column to avoid conflict with auto-generated primary key
    if clean_name.upper() == 'ID':
        clean_name = 'original_id'

    # Quote if it's a reserved keyword
    if clean_name.lower() in RESERVED_KEYWORDS:
        return f'"{clean_name}"'

    return clean_name


def detect_column_type(sample_values):
    """
    Detect PostgreSQL column type from sample values.
    Returns appropriate PostgreSQL data type.
    """
    if not sample_values:
        return 'TEXT'

    # Filter out None/empty values
    non_empty = [str(v).strip() for v in sample_values if v and str(v).strip()]

    if not non_empty:
        return 'TEXT'

    # Check if all values are integers
    try:
        for val in non_empty:
            int(val)
        return 'INTEGER'
    except (ValueError, TypeError):
        pass

    # Check if all values are numeric (float/decimal)
    try:
        for val in non_empty:
            float(val)
        return 'NUMERIC'
    except (ValueError, TypeError):
        pass

    # Check if all values are dates
    date_patterns = [
        r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
        r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
        r'\d{2}-\d{2}-\d{4}',  # MM-DD-YYYY
    ]

    all_dates = True
    for val in non_empty:
        is_date = any(re.match(pattern, str(val)) for pattern in date_patterns)
        if not is_date:
            all_dates = False
            break

    if all_dates:
        return 'TIMESTAMP'

    # Check maximum length for TEXT vs VARCHAR
    max_len = max(len(str(v)) for v in non_empty)

    if max_len <= 255:
        return f'VARCHAR({max(max_len * 2, 255)})'  # Give some buffer
    else:
        return 'TEXT'


def get_all_access_tables():
    """Get all table names and their data from Access database."""
    print("="*70)
    print("EXTRACTING DATA FROM ACCESS DATABASE")
    print("="*70)

    mdb_path = Path(MDB_FILE)
    if not mdb_path.exists():
        print(f"ERROR: MDB file not found: {MDB_FILE}")
        return {}

    print(f"MDB File: {MDB_FILE}")
    print(f"Size: {mdb_path.stat().st_size / (1024*1024):.2f} MB")

    # Get list of all tables
    try:
        result = subprocess.run(['mdb-tables', MDB_FILE],
                              capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"Error listing tables: {result.stderr}")
            return {}

        table_names = result.stdout.strip().split()
        print(f"\nFound {len(table_names)} total tables")

        # Filter out system tables
        user_tables = [t for t in table_names if not t.startswith('MSys')]
        print(f"User tables to migrate: {len(user_tables)}")
        print(f"Tables: {', '.join(user_tables)}\n")

    except Exception as e:
        print(f"Error: {e}")
        return {}

    # Extract data from each table
    all_data = {}

    for idx, table_name in enumerate(user_tables, 1):
        try:
            print(f"[{idx}/{len(user_tables)}] Processing: {table_name}")

            # Get record count
            count_result = subprocess.run(['mdb-count', MDB_FILE, table_name],
                                        capture_output=True, text=True, timeout=10)
            record_count = int(count_result.stdout.strip()) if count_result.returncode == 0 else 0
            print(f"  Records: {record_count}")

            if record_count == 0:
                print(f"  Skipping empty table")
                all_data[table_name] = {'records': [], 'count': 0, 'schema': []}
                continue

            # Export table data as CSV
            export_result = subprocess.run(['mdb-export', MDB_FILE, table_name],
                                         capture_output=True, text=True, timeout=120)

            if export_result.returncode != 0:
                print(f"  ERROR exporting: {export_result.stderr}")
                all_data[table_name] = {'records': [], 'count': 0, 'schema': []}
                continue

            # Parse CSV data
            csv_data = export_result.stdout
            if not csv_data.strip():
                all_data[table_name] = {'records': [], 'count': 0, 'schema': []}
                continue

            csv_reader = csv.DictReader(io.StringIO(csv_data))
            rows = list(csv_reader)

            # Get schema (column names and infer data types from sample data)
            schema = []
            if rows:
                for col_name in rows[0].keys():
                    sample_values = [row[col_name] for row in rows[:10] if row.get(col_name)]
                    data_type = detect_column_type(sample_values)

                    schema.append({
                        'name': col_name,
                        'safe_name': safe_column_name(col_name),
                        'type': data_type,
                        'sample_values': sample_values[:3]
                    })

            all_data[table_name] = {
                'records': rows,
                'count': len(rows),
                'schema': schema
            }

            print(f"  Extracted {len(rows)} records with {len(schema)} columns")

        except Exception as e:
            print(f"  ERROR processing: {e}")
            all_data[table_name] = {'records': [], 'count': 0, 'schema': []}

    print("\n" + "="*70)
    print("EXTRACTION COMPLETE")
    print("="*70)
    total_records = sum(t['count'] for t in all_data.values())
    print(f"Total records extracted: {total_records:,}")

    return all_data


def create_postgresql_schema():
    """Create the pcb_inventory schema if it doesn't exist."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Create schema
        cursor.execute("CREATE SCHEMA IF NOT EXISTS pcb_inventory")
        cursor.execute("SET search_path TO pcb_inventory, public")

        conn.commit()
        cursor.close()
        conn.close()

        print("✓ PostgreSQL schema ready")
        return True

    except Exception as e:
        print(f"ERROR creating schema: {e}")
        return False


def create_postgresql_tables(all_data):
    """Create PostgreSQL tables for all Access tables."""
    print("\n" + "="*70)
    print("CREATING POSTGRESQL TABLES")
    print("="*70)

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SET search_path TO pcb_inventory, public")

        created_count = 0
        skipped_count = 0

        for table_name, table_data in all_data.items():
            if table_data['count'] == 0:
                print(f"Skipping empty table: {table_name}")
                skipped_count += 1
                continue

            try:
                print(f"\nCreating table: {table_name}")

                # Drop table if exists (for clean migration)
                cursor.execute(f'DROP TABLE IF EXISTS pcb_inventory."{table_name}" CASCADE')

                # Create table with properly typed columns
                columns = []
                for col in table_data['schema']:
                    col_def = f"{col['safe_name']} {col['type']}"
                    columns.append(col_def)
                    print(f"  - {col['safe_name']}: {col['type']}")

                if columns:
                    create_sql = f'''
                    CREATE TABLE pcb_inventory."{table_name}" (
                        id SERIAL PRIMARY KEY,
                        {', '.join(columns)},
                        migrated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                    '''
                    cursor.execute(create_sql)
                    print(f"  ✓ Created with {len(columns)} columns")
                    created_count += 1

                conn.commit()

            except Exception as e:
                print(f"  ✗ ERROR: {e}")
                conn.rollback()

        cursor.close()
        conn.close()

        print("\n" + "="*70)
        print(f"Tables created: {created_count}")
        print(f"Tables skipped: {skipped_count}")
        print("="*70)

        return created_count > 0

    except Exception as e:
        print(f"ERROR connecting to PostgreSQL: {e}")
        return False


def migrate_table_data(all_data):
    """Migrate all table data to PostgreSQL."""
    print("\n" + "="*70)
    print("MIGRATING DATA TO POSTGRESQL")
    print("="*70)

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SET search_path TO pcb_inventory, public")

        total_migrated = 0
        migration_summary = {}

        for table_name, table_data in all_data.items():
            if table_data['count'] == 0:
                continue

            print(f"\nMigrating: {table_name}")

            records = table_data['records']
            successful = 0
            errors = 0

            for record in records:
                try:
                    # Map original column names to safe names and clean data
                    clean_record = {}
                    for col in table_data['schema']:
                        original_name = col['name']
                        safe_name = col['safe_name'].strip('"')
                        value = record.get(original_name, '')

                        # Clean and convert data
                        if value:
                            clean_value = str(value).replace('\x00', '')

                            # Handle data type conversions
                            if col['type'] == 'INTEGER':
                                try:
                                    clean_record[safe_name] = int(clean_value) if clean_value else None
                                except:
                                    clean_record[safe_name] = None
                            elif col['type'] == 'NUMERIC':
                                try:
                                    clean_record[safe_name] = float(clean_value) if clean_value else None
                                except:
                                    clean_record[safe_name] = None
                            else:
                                # Truncate very long text
                                if len(clean_value) > 10000:
                                    clean_value = clean_value[:10000] + '...[truncated]'
                                clean_record[safe_name] = clean_value
                        else:
                            clean_record[safe_name] = None

                    # Build INSERT statement
                    columns = list(clean_record.keys())
                    values = list(clean_record.values())

                    # Quote column names that need it
                    quoted_columns = []
                    for col_name in columns:
                        if col_name.lower() in RESERVED_KEYWORDS:
                            quoted_columns.append(f'"{col_name}"')
                        else:
                            quoted_columns.append(col_name)

                    placeholders = ', '.join(['%s'] * len(values))
                    columns_str = ', '.join(quoted_columns)

                    insert_sql = f'''
                    INSERT INTO pcb_inventory."{table_name}" ({columns_str})
                    VALUES ({placeholders})
                    '''

                    cursor.execute(insert_sql, values)
                    successful += 1

                except Exception as e:
                    errors += 1
                    if errors <= 3:  # Show first 3 errors only
                        print(f"    ERROR on record: {str(e)[:100]}")

            conn.commit()
            total_migrated += successful
            migration_summary[table_name] = {
                'successful': successful,
                'errors': errors,
                'total': len(records)
            }

            success_rate = (successful / len(records) * 100) if len(records) > 0 else 0
            print(f"  ✓ Migrated {successful:,}/{len(records):,} ({success_rate:.1f}%) | Errors: {errors}")

        cursor.close()
        conn.close()

        print("\n" + "="*70)
        print("MIGRATION SUMMARY")
        print("="*70)
        print(f"Total records migrated: {total_migrated:,}\n")

        print("Per-table breakdown:")
        for table, stats in sorted(migration_summary.items()):
            success_rate = (stats['successful'] / stats['total'] * 100) if stats['total'] > 0 else 0
            status = "✓" if stats['errors'] == 0 else "⚠"
            print(f"  {status} {table:30} {stats['successful']:6,}/{stats['total']:6,} ({success_rate:5.1f}%)")

        print("="*70)

        return total_migrated > 0

    except Exception as e:
        print(f"ERROR migrating data: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_migration(all_data):
    """Verify that data was successfully migrated."""
    print("\n" + "="*70)
    print("VERIFYING MIGRATION")
    print("="*70)

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SET search_path TO pcb_inventory, public")

        all_verified = True

        for table_name, table_data in all_data.items():
            if table_data['count'] == 0:
                continue

            try:
                # Count records in PostgreSQL
                cursor.execute(f'SELECT COUNT(*) as count FROM pcb_inventory."{table_name}"')
                pg_count = cursor.fetchone()['count']

                expected_count = table_data['count']

                if pg_count == expected_count:
                    print(f"  ✓ {table_name:30} {pg_count:6,} records")
                else:
                    print(f"  ✗ {table_name:30} {pg_count:6,} records (expected {expected_count:,})")
                    all_verified = False

            except Exception as e:
                print(f"  ✗ {table_name:30} ERROR: {e}")
                all_verified = False

        cursor.close()
        conn.close()

        print("="*70)

        if all_verified:
            print("✅ ALL TABLES VERIFIED SUCCESSFULLY!")
        else:
            print("⚠ SOME TABLES HAD VERIFICATION ISSUES")

        return all_verified

    except Exception as e:
        print(f"ERROR during verification: {e}")
        return False


def main():
    """Main migration function."""
    print("\n")
    print("="*70)
    print(" "*15 + "ACI INVENTORY MIGRATION TOOL")
    print(" "*10 + "Access Database → PostgreSQL Migration")
    print("="*70)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Step 1: Extract all data from Access
    print("\nSTEP 1: Extract data from Access database...")
    all_data = get_all_access_tables()
    if not all_data:
        print("✗ No data extracted from Access database")
        return False

    # Step 2: Create PostgreSQL schema
    print("\nSTEP 2: Create PostgreSQL schema...")
    if not create_postgresql_schema():
        print("✗ Failed to create PostgreSQL schema")
        return False

    # Step 3: Create PostgreSQL tables
    print("\nSTEP 3: Create tables in PostgreSQL...")
    if not create_postgresql_tables(all_data):
        print("✗ Failed to create PostgreSQL tables")
        return False

    # Step 4: Migrate data
    print("\nSTEP 4: Migrate data to PostgreSQL...")
    if not migrate_table_data(all_data):
        print("✗ Migration failed")
        return False

    # Step 5: Verify migration
    print("\nSTEP 5: Verify migration...")
    verify_migration(all_data)

    print("\n" + "="*70)
    print("MIGRATION COMPLETE!")
    print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nMigration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
